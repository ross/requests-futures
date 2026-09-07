# -*- coding: utf-8 -*-
"""
requests_futures.otel
~~~~~~~~~~~~~~~~~~~~~

Optional OpenTelemetry tracing support for
:class:`~requests_futures.sessions.FuturesSession`. Requires the ``otel``
extra: ``pip install requests-futures[otel]``.

:class:`~requests_futures.sessions.FuturesSession` already propagates the
calling thread's :mod:`contextvars` context into the worker thread that
actually runs a request, so any span that is current at submit time
correctly becomes the parent of whatever span
``opentelemetry-instrumentation-requests`` creates inside ``Session.send``
on that worker thread. What's still missing is a span for the time between
submitting a request and a worker thread actually picking it up --
invisible to that inner span, since it doesn't start until ``Session.send``
runs. This module closes that gap: instrumenting ``FuturesSession`` opens a
span at submit time and closes it when the resulting ``Future`` resolves,
covering the full submit -> ``result()`` window, and becomes the parent of
the inner span::

    from opentelemetry.instrumentation.requests import RequestsInstrumentor
    from requests_futures.otel import FuturesSessionInstrumentor

    RequestsInstrumentor().instrument()
    FuturesSessionInstrumentor().instrument()
"""

from functools import wraps

from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode

from requests_futures.sessions import FuturesSession

_WRAPPED_MARKER = '_opentelemetry_requests_futures_wrapped'


def _extract_method_url(args, kwargs):
    """FuturesSession.request(self, *args, **kwargs) forwards straight to
    Session.request(method, url, ...) -- both are required, positional-or-
    keyword, so they're always present in some combination of args/kwargs
    for any call that will actually succeed."""
    method = args[0] if args else kwargs.get('method')
    url = args[1] if len(args) > 1 else kwargs.get('url')
    return method, url


class FuturesSessionInstrumentor:
    """Patches :class:`~requests_futures.sessions.FuturesSession.request`
    to open a span around the executor submit call, closing it when the
    returned :class:`~concurrent.futures.Future` resolves -- covering the
    time a request spends queued for a worker thread, which the ``CLIENT``
    span ``opentelemetry-instrumentation-requests`` creates inside
    ``Session.send`` (on the worker thread, once it starts) does not.

    Hand-rolled rather than an
    :class:`opentelemetry.instrumentation.instrumentor.BaseInstrumentor`
    subclass: that pulls in ``opentelemetry-instrumentation``, which has no
    stable release, for a single-method patch that doesn't need its
    machinery. This mirrors its public shape by hand
    (``instrument()``/``uninstrument()``, a guarded singleton), using only
    the stable ``opentelemetry-api``.

    ``FuturesSession`` already propagates the calling thread's
    ``contextvars`` context into the worker thread, so the span opened
    here -- current for the duration of the (synchronous) submit call --
    correctly becomes the parent of that inner ``CLIENT`` span once both
    are instrumented.

    No ``opentelemetry_instrumentor`` entry point is registered, so
    ``opentelemetry-instrument`` zero-code auto-discovery won't find this;
    call :meth:`instrument` explicitly.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._is_instrumented = False
        return cls._instance

    @property
    def is_instrumented(self):
        return self._is_instrumented

    def instrument(self, tracer_provider=None):
        """Patch :class:`~requests_futures.sessions.FuturesSession` so
        every request opens a span at submit time. A no-op if already
        instrumented.

        :param tracer_provider: The :class:`~opentelemetry.trace.TracerProvider`
            to get a tracer from. Defaults to the global one.
        """
        if self._is_instrumented:
            return
        tracer = trace.get_tracer(
            'requests_futures.otel', None, tracer_provider
        )
        wrapped = FuturesSession.request

        @wraps(wrapped)
        def instrumented_request(session, *args, **kwargs):
            method, url = _extract_method_url(args, kwargs)
            span = tracer.start_span(
                f'{method} (queued)',
                kind=SpanKind.INTERNAL,
                attributes={'http.request.method': method, 'url.full': url},
            )
            with trace.use_span(span, end_on_exit=False):
                future = wrapped(session, *args, **kwargs)

            def _end_span(fut):
                if fut.cancelled():
                    span.set_status(Status(StatusCode.ERROR, 'cancelled'))
                else:
                    exc = fut.exception()
                    if exc is not None:
                        span.record_exception(exc)
                        span.set_status(
                            Status(
                                StatusCode.ERROR, f'{type(exc).__name__}: {exc}'
                            )
                        )
                span.end()

            future.add_done_callback(_end_span)
            return future

        setattr(instrumented_request, _WRAPPED_MARKER, True)
        FuturesSession.request = instrumented_request
        self._is_instrumented = True

    def uninstrument(self):
        """Undo :meth:`instrument`. A no-op if not instrumented."""
        if not self._is_instrumented:
            return
        current = FuturesSession.request
        if getattr(current, _WRAPPED_MARKER, False):
            FuturesSession.request = current.__wrapped__
        self._is_instrumented = False
