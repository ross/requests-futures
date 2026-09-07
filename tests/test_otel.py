#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Tests for requests_futures.otel."""

from threading import Event
from time import monotonic, sleep
from unittest import TestCase, main

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.trace import SpanKind, StatusCode

from requests_futures.otel import FuturesSessionInstrumentor
from requests_futures.sessions import FuturesSession


@pytest.fixture(scope="class", autouse=True)
def httpbin_on_class(request, httpbin):
    request.cls.httpbin = httpbin


class OtelTestCase(TestCase):
    def setUp(self):
        # belt-and-suspenders: FuturesSessionInstrumentor is a singleton
        # patching the shared FuturesSession class, so every test starts
        # (and ends) from a guaranteed-pristine state regardless of what
        # the test itself does or whether it fails partway through.
        self._original_request = FuturesSession.request
        self.addCleanup(self._restore)

    def _restore(self):
        FuturesSession.request = self._original_request
        FuturesSessionInstrumentor()._is_instrumented = False

    def make_session(self, *args, **kwargs):
        """Builds a FuturesSession and registers it to be closed at the
        end of the test, so tests don't leak executor threads."""
        sess = FuturesSession(*args, **kwargs)
        self.addCleanup(sess.close)
        return sess

    def instrument(self, **kwargs):
        """Instruments FuturesSession against a fresh, isolated tracer
        provider + in-memory exporter, and registers cleanup."""
        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        instrumentor = FuturesSessionInstrumentor()
        instrumentor.instrument(tracer_provider=provider, **kwargs)
        self.addCleanup(instrumentor.uninstrument)
        return instrumentor, provider, exporter

    @staticmethod
    def wait_for_spans(exporter, count, timeout=2.0):
        """add_done_callback's callback isn't guaranteed to have run by
        the time future.result() returns on another thread, so polling
        (rather than asserting immediately) is required to avoid
        flakiness."""
        deadline = monotonic() + timeout
        spans = exporter.get_finished_spans()
        while len(spans) < count and monotonic() < deadline:
            sleep(0.01)
            spans = exporter.get_finished_spans()
        return spans

    def test_instrument_wraps_request(self):
        original = FuturesSession.request
        instrumentor, _, _ = self.instrument()
        self.assertIsNot(FuturesSession.request, original)
        self.assertTrue(instrumentor.is_instrumented)
        self.assertIs(FuturesSession.request.__wrapped__, original)

    def test_uninstrument_restores_original(self):
        original = FuturesSession.request
        instrumentor, _, _ = self.instrument()
        instrumentor.uninstrument()
        self.assertIs(FuturesSession.request, original)
        self.assertFalse(instrumentor.is_instrumented)

    def test_uninstrument_does_not_clobber_foreign_patch(self):
        """If something else replaces FuturesSession.request after we
        instrumented (an unusual, pathological case), uninstrument() must
        not blindly restore our own captured original over it."""
        instrumentor, _, _ = self.instrument()

        def other_patch(self, *args, **kwargs):
            raise AssertionError('should not be called')

        FuturesSession.request = other_patch
        instrumentor.uninstrument()

        self.assertIs(FuturesSession.request, other_patch)
        self.assertFalse(instrumentor.is_instrumented)

    def test_double_instrument_is_noop(self):
        instrumentor, provider, _ = self.instrument()
        wrapped_once = FuturesSession.request
        instrumentor.instrument(tracer_provider=provider)
        self.assertIs(FuturesSession.request, wrapped_once)

    def test_uninstrument_when_not_instrumented_is_noop(self):
        instrumentor = FuturesSessionInstrumentor()
        self.assertFalse(instrumentor.is_instrumented)
        instrumentor.uninstrument()
        self.assertFalse(instrumentor.is_instrumented)

    def test_uninstrument_stops_creating_spans(self):
        instrumentor, _, exporter = self.instrument()
        sess = self.make_session()

        future = sess.get(self.httpbin.join('get'))
        future.result()
        self.wait_for_spans(exporter, 1)
        self.assertEqual(len(exporter.get_finished_spans()), 1)

        instrumentor.uninstrument()

        future = sess.get(self.httpbin.join('get'))
        future.result()
        sleep(0.05)
        self.assertEqual(len(exporter.get_finished_spans()), 1)

    def test_span_parented_under_caller_span(self):
        _, provider, exporter = self.instrument()
        tracer = provider.get_tracer(__name__)
        sess = self.make_session()

        with tracer.start_as_current_span('parent') as parent:
            parent_context = parent.get_span_context()
            future = sess.get(self.httpbin.join('get'))
            future.result()

        spans = self.wait_for_spans(exporter, 2)
        self.assertEqual(len(spans), 2)
        queued_span = next(s for s in spans if s.name != 'parent')

        self.assertEqual(queued_span.kind, SpanKind.INTERNAL)
        self.assertEqual(queued_span.parent.span_id, parent_context.span_id)
        self.assertEqual(queued_span.context.trace_id, parent_context.trace_id)
        self.assertEqual(queued_span.attributes['http.request.method'], 'GET')
        self.assertEqual(
            queued_span.attributes['url.full'], self.httpbin.join('get')
        )

    def test_span_ends_on_success(self):
        _, _, exporter = self.instrument()
        sess = self.make_session()

        future = sess.get(self.httpbin.join('get'))
        future.result()

        spans = self.wait_for_spans(exporter, 1)
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].status.status_code, StatusCode.UNSET)

    def test_span_records_exception(self):
        _, _, exporter = self.instrument()
        sess = self.make_session()

        def raise_hook(response, *args, **kwargs):
            raise ValueError('boom')

        future = sess.get(
            self.httpbin.join('get'), hooks={'response': raise_hook}
        )
        with self.assertRaises(ValueError):
            future.result()

        spans = self.wait_for_spans(exporter, 1)
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.status.status_code, StatusCode.ERROR)
        self.assertIn('ValueError: boom', span.status.description)
        exception_events = [e for e in span.events if e.name == 'exception']
        self.assertEqual(len(exception_events), 1)
        self.assertEqual(
            exception_events[0].attributes['exception.type'], 'ValueError'
        )

    def test_cancelled_future_ends_span_as_error(self):
        _, _, exporter = self.instrument()
        sess = self.make_session(max_workers=1)

        request_started = Event()
        finish_request = Event()

        def block_hook(response, *args, **kwargs):
            request_started.set()
            finish_request.wait(timeout=2)

        first = sess.get(
            self.httpbin.join('get?which=first'), hooks={'response': block_hook}
        )
        self.assertTrue(request_started.wait(timeout=1))

        # still queued behind `first` (max_workers=1), so this cancels
        # cleanly -- Future.cancel() invokes done callbacks synchronously,
        # so no polling is needed here
        queued = sess.get(self.httpbin.join('get?which=second'))
        self.assertTrue(queued.cancel())

        finish_request.set()
        first.result()

        spans = exporter.get_finished_spans()
        second_span = next(
            s
            for s in spans
            if s.attributes['url.full'].endswith('which=second')
        )
        self.assertEqual(second_span.status.status_code, StatusCode.ERROR)
        self.assertEqual(second_span.status.description, 'cancelled')

    def test_method_url_from_kwargs_only(self):
        _, _, exporter = self.instrument()
        sess = self.make_session()

        future = sess.request(method='GET', url=self.httpbin.join('get'))
        future.result()

        spans = self.wait_for_spans(exporter, 1)
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].attributes['http.request.method'], 'GET')
        self.assertEqual(
            spans[0].attributes['url.full'], self.httpbin.join('get')
        )

    def test_url_from_kwarg_with_positional_method(self):
        _, _, exporter = self.instrument()
        sess = self.make_session()

        future = sess.request('GET', url=self.httpbin.join('get'))
        future.result()

        spans = self.wait_for_spans(exporter, 1)
        self.assertEqual(len(spans), 1)
        self.assertEqual(
            spans[0].attributes['url.full'], self.httpbin.join('get')
        )


if __name__ == '__main__':
    main()
