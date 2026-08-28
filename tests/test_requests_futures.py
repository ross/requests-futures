#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Tests for Requests."""

import logging
from concurrent.futures import Future, ProcessPoolExecutor
from os.path import basename
from threading import Event, Thread
from time import monotonic, sleep
from unittest import TestCase, main

import pytest
from requests import Response, Session, session
from requests.adapters import (
    DEFAULT_POOLSIZE,
    DEFAULT_RETRIES,
    BaseAdapter,
    HTTPAdapter,
    Retry,
)

from requests_futures.sessions import PICKLE_ERROR, FuturesSession

logging.basicConfig(level=logging.DEBUG)
logging.getLogger('urllib3.connectionpool').level = logging.WARNING


@pytest.fixture(scope="class", autouse=True)
def httpbin_on_class(request, httpbin):
    request.cls.httpbin = httpbin


class RequestsTestCase(TestCase):
    def make_session(self, *args, **kwargs):
        """Builds a FuturesSession and registers it to be closed at the
        end of the test, so tests don't leak executor threads."""
        sess = FuturesSession(*args, **kwargs)
        self.addCleanup(sess.close)
        return sess

    def test_futures_session(self):
        # basic futures get
        sess = self.make_session()
        future = sess.get(self.httpbin.join('get'))
        self.assertIsInstance(future, Future)
        resp = future.result()
        self.assertIsInstance(resp, Response)
        self.assertEqual(200, resp.status_code)

        # non-200, 404
        future = sess.get(self.httpbin.join('status/404'))
        resp = future.result()
        self.assertEqual(404, resp.status_code)

        def cb(s, r):
            self.assertIsInstance(s, FuturesSession)
            self.assertIsInstance(r, Response)
            # add the parsed json data to the response
            r.data = r.json()

        future = sess.get(self.httpbin.join('get'), background_callback=cb)
        # this should block until complete
        resp = future.result()
        self.assertEqual(200, resp.status_code)
        # make sure the callback was invoked
        self.assertTrue(hasattr(resp, 'data'))

        def rasing_cb(s, r):
            raise Exception('boom')

        future = sess.get(
            self.httpbin.join('get'), background_callback=rasing_cb
        )
        with self.assertRaises(Exception) as cm:
            resp = future.result()
        self.assertEqual('boom', cm.exception.args[0])

    def test_background_callback_falsy_return(self):
        """A background_callback's falsy return value must not be
        discarded in favor of the Response."""
        sess = self.make_session()

        def cb(s, r):
            return {}

        future = sess.get(self.httpbin.join('get'), background_callback=cb)
        self.assertEqual({}, future.result())

    def test_background_callback_deprecated(self):
        """A background_callback param must emit a DeprecationWarning
        attributed to the caller, not to sessions.py."""
        sess = self.make_session()

        def cb(s, r):
            pass

        with self.assertWarns(DeprecationWarning) as cm:
            future = sess.get(self.httpbin.join('get'), background_callback=cb)
        self.assertIn('hooks', str(cm.warning))
        # pins stacklevel: the warning points at this file, not sessions.py
        self.assertEqual(basename(__file__), basename(cm.filename))
        future.result()

    def test_hooks_response(self):
        """A `hooks={'response': fn}` hook runs against the Response, and
        unlike `background_callback` never replaces what the future
        resolves to: hook return values are requests' own business."""
        sess = self.make_session()

        def hook(response, *args, **kwargs):
            response.hooked = True

        future = sess.get(self.httpbin.join('get'), hooks={'response': hook})
        resp = future.result()
        self.assertIsInstance(resp, Response)
        self.assertEqual(200, resp.status_code)
        self.assertTrue(resp.hooked)

    def test_options(self):
        sess = self.make_session()
        future = sess.options(self.httpbin.join('get'))
        self.assertIsInstance(future, Future)
        resp = future.result()
        self.assertIsInstance(resp, Response)
        self.assertEqual(200, resp.status_code)

    def test_head(self):
        sess = self.make_session()
        future = sess.head(self.httpbin.join('get'))
        self.assertIsInstance(future, Future)
        resp = future.result()
        self.assertIsInstance(resp, Response)
        self.assertEqual(200, resp.status_code)

    def test_post(self):
        sess = self.make_session()
        future = sess.post(self.httpbin.join('post'), data={'a': 'b'})
        self.assertIsInstance(future, Future)
        resp = future.result()
        self.assertIsInstance(resp, Response)
        self.assertEqual(200, resp.status_code)
        self.assertEqual({'a': 'b'}, resp.json()['form'])

        future = sess.post(self.httpbin.join('post'), json={'a': 'b'})
        resp = future.result()
        self.assertEqual(200, resp.status_code)
        self.assertEqual({'a': 'b'}, resp.json()['json'])

    def test_put(self):
        sess = self.make_session()
        future = sess.put(self.httpbin.join('put'), data={'a': 'b'})
        self.assertIsInstance(future, Future)
        resp = future.result()
        self.assertIsInstance(resp, Response)
        self.assertEqual(200, resp.status_code)
        self.assertEqual({'a': 'b'}, resp.json()['form'])

    def test_patch(self):
        sess = self.make_session()
        future = sess.patch(self.httpbin.join('patch'), data={'a': 'b'})
        self.assertIsInstance(future, Future)
        resp = future.result()
        self.assertIsInstance(resp, Response)
        self.assertEqual(200, resp.status_code)
        self.assertEqual({'a': 'b'}, resp.json()['form'])

    def test_delete(self):
        sess = self.make_session()
        future = sess.delete(self.httpbin.join('delete'))
        self.assertIsInstance(future, Future)
        resp = future.result()
        self.assertIsInstance(resp, Response)
        self.assertEqual(200, resp.status_code)

    def test_supplied_session(self):
        """Tests the `session` keyword argument."""
        requests_session = session()
        requests_session.headers['Foo'] = 'bar'
        sess = self.make_session(session=requests_session)
        future = sess.get(self.httpbin.join('headers'))
        self.assertIsInstance(future, Future)
        resp = future.result()
        self.assertIsInstance(resp, Response)
        self.assertEqual(200, resp.status_code)
        self.assertEqual(resp.json()['headers']['Foo'], 'bar')

    def test_max_workers(self):
        """Tests the `max_workers` shortcut."""
        from concurrent.futures import ThreadPoolExecutor

        session = self.make_session()
        self.assertEqual(session.executor._max_workers, 8)
        session = self.make_session(max_workers=5)
        self.assertEqual(session.executor._max_workers, 5)
        executor = ThreadPoolExecutor(max_workers=10)
        self.addCleanup(executor.shutdown)
        session = self.make_session(executor=executor)
        self.assertEqual(session.executor._max_workers, 10)
        session = self.make_session(executor=executor, max_workers=5)
        self.assertEqual(session.executor._max_workers, 10)

    def test_adapter_kwargs(self):
        """Tests the `adapter_kwargs` shortcut."""
        from concurrent.futures import ThreadPoolExecutor

        session = self.make_session()
        self.assertFalse(session.get_adapter('http://')._pool_block)
        session = self.make_session(
            max_workers=DEFAULT_POOLSIZE + 1,
            adapter_kwargs={'pool_block': True},
        )
        adapter = session.get_adapter('http://')
        self.assertTrue(adapter._pool_block)
        self.assertEqual(adapter._pool_connections, DEFAULT_POOLSIZE + 1)
        self.assertEqual(adapter._pool_maxsize, DEFAULT_POOLSIZE + 1)
        executor = ThreadPoolExecutor(max_workers=10)
        self.addCleanup(executor.shutdown)
        session = self.make_session(
            executor=executor, adapter_kwargs={'pool_connections': 20}
        )
        self.assertEqual(session.get_adapter('http://')._pool_connections, 20)

    def test_adapter_kwargs_with_supplied_session(self):
        """`adapter_kwargs`/`max_workers` sizing must apply to the
        supplied `session`, since that's what actually serves requests."""
        requests_session = session()
        futures_session = self.make_session(
            session=requests_session, max_workers=DEFAULT_POOLSIZE + 1
        )
        adapter = requests_session.get_adapter('http://')
        self.assertEqual(adapter._pool_connections, DEFAULT_POOLSIZE + 1)
        self.assertEqual(adapter._pool_maxsize, DEFAULT_POOLSIZE + 1)
        # the FuturesSession itself should be left with its defaults
        self.assertEqual(
            futures_session.get_adapter('http://')._pool_maxsize,
            DEFAULT_POOLSIZE,
        )

        requests_session = session()
        self.make_session(
            session=requests_session, adapter_kwargs={'pool_block': True}
        )
        self.assertTrue(requests_session.get_adapter('http://')._pool_block)

    def test_supplied_session_adapter_preserved(self):
        """Applying pool sizing to a supplied session must reconfigure its
        existing adapters in place rather than replace them, so retry
        policy and custom adapter behavior survive."""
        requests_session = session()
        retrying_adapter = HTTPAdapter(
            max_retries=Retry(total=5), pool_block=True
        )
        requests_session.mount('https://', retrying_adapter)
        self.make_session(
            session=requests_session, max_workers=DEFAULT_POOLSIZE + 1
        )
        adapter = requests_session.get_adapter('https://')
        self.assertIs(adapter, retrying_adapter)
        self.assertEqual(adapter.max_retries.total, 5)
        self.assertTrue(adapter._pool_block)
        self.assertEqual(adapter._pool_connections, DEFAULT_POOLSIZE + 1)
        self.assertEqual(adapter._pool_maxsize, DEFAULT_POOLSIZE + 1)
        self.assertEqual(
            adapter.poolmanager.connection_pool_kw['maxsize'],
            DEFAULT_POOLSIZE + 1,
        )

        # a custom adapter subclass keeps its class and its own attributes
        class CustomAdapter(HTTPAdapter):
            def __init__(self, marker, **kwargs):
                self.marker = marker
                super(CustomAdapter, self).__init__(**kwargs)

        requests_session = session()
        custom_adapter = CustomAdapter('mine')
        requests_session.mount('https://', custom_adapter)
        self.make_session(
            session=requests_session, max_workers=DEFAULT_POOLSIZE + 1
        )
        adapter = requests_session.get_adapter('https://')
        self.assertIs(adapter, custom_adapter)
        self.assertIsInstance(adapter, CustomAdapter)
        self.assertEqual(adapter.marker, 'mine')
        self.assertEqual(adapter._pool_maxsize, DEFAULT_POOLSIZE + 1)

        # adapter_kwargs' max_retries is applied the same way
        requests_session = session()
        requests_session.mount('https://', HTTPAdapter())
        self.make_session(
            session=requests_session, adapter_kwargs={'max_retries': 3}
        )
        self.assertEqual(
            requests_session.get_adapter('https://').max_retries.total, 3
        )

        # max_retries=DEFAULT_RETRIES matches HTTPAdapter's own handling
        # (a bare Retry(0, read=False) rather than Retry.from_int)
        requests_session = session()
        requests_session.mount('https://', HTTPAdapter())
        self.make_session(
            session=requests_session,
            adapter_kwargs={'max_retries': DEFAULT_RETRIES},
        )
        self.assertEqual(
            requests_session.get_adapter('https://').max_retries.total, 0
        )

        # a non-HTTPAdapter is left alone rather than blowing up
        class MockAdapter(BaseAdapter):
            def send(self, *args, **kwargs):
                pass

            def close(self):
                pass

        requests_session = session()
        mock_adapter = MockAdapter()
        requests_session.mount('http://', mock_adapter)
        self.make_session(
            session=requests_session, max_workers=DEFAULT_POOLSIZE + 1
        )
        self.assertIs(requests_session.get_adapter('http://'), mock_adapter)

    def test_supplied_session_proxy_manager_resized(self):
        """A supplied session's cached proxy managers must pick up new
        pool sizing too, since `init_poolmanager` alone doesn't touch
        them."""
        requests_session = session()
        adapter = requests_session.get_adapter('http://')
        stale_proxy_manager = adapter.proxy_manager_for('http://proxy.example')
        self.assertEqual(
            stale_proxy_manager.connection_pool_kw['maxsize'], DEFAULT_POOLSIZE
        )

        self.make_session(
            session=requests_session,
            max_workers=DEFAULT_POOLSIZE + 1,
            adapter_kwargs={'pool_block': True},
        )

        # same adapter, but the proxy manager was rebuilt at the new size
        self.assertIs(requests_session.get_adapter('http://'), adapter)
        proxy_manager = adapter.proxy_manager_for('http://proxy.example')
        self.assertIsNot(proxy_manager, stale_proxy_manager)
        self.assertEqual(
            proxy_manager.connection_pool_kw['maxsize'], DEFAULT_POOLSIZE + 1
        )
        self.assertTrue(proxy_manager.connection_pool_kw['block'])

        # when pool settings are unchanged, the cached proxy manager (and
        # its warm connections) is left alone
        requests_session = session()
        adapter = requests_session.get_adapter('http://')
        cached_proxy_manager = adapter.proxy_manager_for('http://proxy.example')
        self.make_session(
            session=requests_session, adapter_kwargs={'max_retries': 3}
        )
        self.assertIs(
            adapter.proxy_manager_for('http://proxy.example'),
            cached_proxy_manager,
        )
        self.assertEqual(adapter.max_retries.total, 3)

    def test_redirect(self):
        """Tests for the ability to cleanly handle redirects."""
        sess = self.make_session()
        future = sess.get(self.httpbin.join('redirect-to?url=get'))
        self.assertIsInstance(future, Future)
        resp = future.result()
        self.assertIsInstance(resp, Response)
        self.assertEqual(200, resp.status_code)

        future = sess.get(self.httpbin.join('redirect-to?url=status/404'))
        resp = future.result()
        self.assertEqual(404, resp.status_code)

    def test_context(self):
        class FuturesSessionTestHelper(FuturesSession):
            def __init__(self, *args, **kwargs):
                super(FuturesSessionTestHelper, self).__init__(*args, **kwargs)
                self._exit_called = False

            def __exit__(self, *args, **kwargs):
                self._exit_called = True
                return super(FuturesSessionTestHelper, self).__exit__(
                    *args, **kwargs
                )

        passout = None
        with FuturesSessionTestHelper() as sess:
            passout = sess
            future = sess.get(self.httpbin.join('get'))
            self.assertIsInstance(future, Future)
            resp = future.result()
            self.assertIsInstance(resp, Response)
            self.assertEqual(200, resp.status_code)

        self.assertTrue(passout._exit_called)

    def test_close_cancels_queued_requests(self):
        request_started = Event()
        finish_request = Event()
        request_finished = Event()
        adapter_closed = Event()
        adapter_closed_after_request = Event()
        session = FuturesSession(max_workers=1)

        class TrackingAdapter(BaseAdapter):
            def send(self, *args, **kwargs):
                pass

            def close(self):
                if request_finished.is_set():
                    adapter_closed_after_request.set()
                adapter_closed.set()

        session.mount('test://', TrackingAdapter())

        def request():
            request_started.set()
            finish_request.wait()
            request_finished.set()

        running = session.executor.submit(request)
        self.assertTrue(request_started.wait(timeout=1))
        queued = session.executor.submit(lambda: None)
        close_thread = Thread(target=session.close)
        close_thread.start()

        try:
            deadline = monotonic() + 1
            while not queued.done() and monotonic() < deadline:
                sleep(0.01)
            self.assertTrue(queued.cancelled())
        finally:
            finish_request.set()
            close_thread.join(timeout=1)

        self.assertFalse(close_thread.is_alive())
        running.result()
        self.assertTrue(adapter_closed.is_set())
        self.assertTrue(adapter_closed_after_request.is_set())

    def test_close_does_not_close_supplied_session(self):
        class TrackingSession(Session):
            def __init__(self):
                super(TrackingSession, self).__init__()
                self.close_calls = 0

            def close(self):
                self.close_calls += 1
                super(TrackingSession, self).close()

        requests_session = TrackingSession()
        futures_session = FuturesSession(session=requests_session)
        futures_session.close()

        self.assertEqual(requests_session.close_calls, 0)
        requests_session.close()
        self.assertEqual(requests_session.close_calls, 1)

    def test_close_waits_for_requests_with_supplied_executor(self):
        from concurrent.futures import ThreadPoolExecutor

        request_started = Event()
        finish_request = Event()
        request_finished = Event()
        adapter_closed = Event()
        adapter_closed_after_request = Event()
        executor = ThreadPoolExecutor(max_workers=1)
        session = FuturesSession(executor=executor)
        close_threads = []

        class TrackingAdapter(BaseAdapter):
            def send(self, request, **kwargs):
                request_started.set()
                finish_request.wait()
                request_finished.set()
                response = Response()
                response.request = request
                response.status_code = 200
                response.url = request.url
                return response

            def close(self):
                if request_finished.is_set():
                    adapter_closed_after_request.set()
                adapter_closed.set()

        try:
            session.mount('test://', TrackingAdapter())
            running = session.get('test://running')
            self.assertTrue(request_started.wait(timeout=1))
            queued = session.get('test://queued')
            unrelated = executor.submit(lambda: 'unrelated')
            close_threads = [Thread(target=session.close) for _ in range(2)]
            for close_thread in close_threads:
                close_thread.start()

            deadline = monotonic() + 1
            while not queued.done() and monotonic() < deadline:
                sleep(0.01)
            self.assertTrue(queued.cancelled())
            self.assertTrue(
                all(close_thread.is_alive() for close_thread in close_threads)
            )
            with self.assertRaisesRegex(RuntimeError, 'after close'):
                session.get('test://closing')

            finish_request.set()
            for close_thread in close_threads:
                close_thread.join(timeout=1)
            self.assertTrue(
                all(
                    not close_thread.is_alive()
                    for close_thread in close_threads
                )
            )
            self.assertEqual(running.result().status_code, 200)
            self.assertEqual(unrelated.result(), 'unrelated')
            self.assertTrue(adapter_closed.is_set())
            self.assertTrue(adapter_closed_after_request.is_set())
            with self.assertRaisesRegex(RuntimeError, 'after close'):
                session.get('test://closed')
            self.assertTrue(executor.submit(lambda: True).result())
        finally:
            finish_request.set()
            for close_thread in close_threads:
                close_thread.join(timeout=1)
            executor.shutdown()


# << test process pool executor >>
# see discussion https://github.com/ross/requests-futures/issues/11
def global_cb_modify_response(s, r):
    """add the parsed json data to the response"""
    assert s, FuturesSession
    assert r, Response
    r.data = r.json()
    # reassign rather than .append(): __attrs__ is a class attribute
    # shared by every Response, and workers are reused across requests
    r.__attrs__ = r.__attrs__ + ['data']


def global_cb_return_result(s, r):
    """simply return parsed json data"""
    assert s, FuturesSession
    assert r, Response
    return r.json()


def global_rasing_cb(s, r):
    raise Exception('boom')


def global_hook_mark_response(response, *args, **kwargs):
    """A `hooks={'response': fn}` callable, module-global because anything
    submitted to a ProcessPoolExecutor must be picklable."""
    response.hooked = True
    # reassign rather than .append(): __attrs__ is a class attribute
    # shared by every Response, and workers are reused across requests
    response.__attrs__ = response.__attrs__ + ['hooked']


class RequestsProcessPoolTestCase(TestCase):
    def setUp(self):
        self.proc_executor = ProcessPoolExecutor(max_workers=2)
        self.addCleanup(self.proc_executor.shutdown)
        self.session = session()

    def test_futures_session(self):
        self._assert_futures_session()

    def test_futures_existing_session(self):
        self.session.headers['Foo'] = 'bar'
        self._assert_futures_session(session=self.session)

    def test_hooks_response(self):
        """A `hooks={'response': fn}` hook runs in the worker process and
        the future still resolves to the (mutated) Response."""
        sess = FuturesSession(executor=self.proc_executor, session=self.session)
        future = sess.get(
            self.httpbin.join('get'),
            hooks={'response': global_hook_mark_response},
        )
        resp = future.result()
        self.assertIsInstance(resp, Response)
        self.assertEqual(200, resp.status_code)
        self.assertTrue(resp.hooked)

    def _assert_futures_session(self, session=None):
        # basic futures get
        if session:
            sess = FuturesSession(executor=self.proc_executor, session=session)
        else:
            sess = FuturesSession(executor=self.proc_executor)

        future = sess.get(self.httpbin.join('get'))
        self.assertIsInstance(future, Future)
        resp = future.result()
        self.assertIsInstance(resp, Response)
        self.assertEqual(200, resp.status_code)

        # non-200, 404
        future = sess.get(self.httpbin.join('status/404'))
        resp = future.result()
        self.assertEqual(404, resp.status_code)

        future = sess.get(
            self.httpbin.join('get'),
            background_callback=global_cb_modify_response,
        )
        # this should block until complete
        resp = future.result()
        if session:
            self.assertEqual(resp.json()['headers']['Foo'], 'bar')
        self.assertEqual(200, resp.status_code)
        # make sure the callback was invoked
        self.assertTrue(hasattr(resp, 'data'))

        future = sess.get(
            self.httpbin.join('get'),
            background_callback=global_cb_return_result,
        )
        # this should block until complete
        resp = future.result()
        # make sure the callback was invoked
        self.assertIsInstance(resp, dict)

        future = sess.get(
            self.httpbin.join('get'), background_callback=global_rasing_cb
        )
        with self.assertRaises(Exception) as cm:
            resp = future.result()
        self.assertEqual('boom', cm.exception.args[0])

        # Tests for the ability to cleanly handle redirects
        future = sess.get(self.httpbin.join('redirect-to?url=get'))
        self.assertIsInstance(future, Future)
        resp = future.result()
        self.assertIsInstance(resp, Response)
        self.assertEqual(200, resp.status_code)

        future = sess.get(self.httpbin.join('redirect-to?url=status/404'))
        resp = future.result()
        self.assertEqual(404, resp.status_code)

    def test_unpicklable_hooks_raises(self):
        """A `hooks` callable that can't be pickled must raise RuntimeError
        at submit time, not a raw pickling error out of the Future."""

        def local_hook(r, *args, **kwargs):
            return r

        sess = FuturesSession(executor=self.proc_executor, session=self.session)
        with self.assertRaises(RuntimeError) as cm:
            sess.get(self.httpbin.join('get'), hooks={'response': local_hook})
        self.assertEqual(PICKLE_ERROR, str(cm.exception))
        self.assertIsNotNone(cm.exception.__cause__)

    def test_unpicklable_data_raises(self):
        """An unpicklable request argument (e.g. a file-like `data=`) must
        raise RuntimeError at submit time."""
        sess = FuturesSession(executor=self.proc_executor, session=self.session)
        f = open(__file__)
        try:
            with self.assertRaises(RuntimeError) as cm:
                sess.post(self.httpbin.join('post'), data=f)
            self.assertEqual(PICKLE_ERROR, str(cm.exception))
            self.assertIsNotNone(cm.exception.__cause__)
        finally:
            f.close()

    def test_unpicklable_background_callback_raises(self):
        """A local-function `background_callback` must raise RuntimeError
        at submit time."""

        def local_cb(s, r):
            return r

        sess = FuturesSession(executor=self.proc_executor, session=self.session)
        with self.assertRaises(RuntimeError) as cm:
            sess.get(self.httpbin.join('get'), background_callback=local_cb)
        self.assertEqual(PICKLE_ERROR, str(cm.exception))
        self.assertIsNotNone(cm.exception.__cause__)

    def test_picklable_request_args_submitted(self):
        """Ordinary picklable kwargs must still go through the widened
        pickle check."""
        sess = FuturesSession(executor=self.proc_executor, session=self.session)
        future = sess.get(self.httpbin.join('get'), params={'a': 'b'})
        resp = future.result()
        self.assertEqual(200, resp.status_code)

    def test_context(self):
        self._assert_context()

    def test_context_with_session(self):
        self._assert_context(session=self.session)

    def _assert_context(self, session=None):
        if session:
            helper_instance = TopLevelContextHelper(
                executor=self.proc_executor, session=self.session
            )
        else:
            helper_instance = TopLevelContextHelper(executor=self.proc_executor)
        passout = None
        with helper_instance as sess:
            passout = sess
            future = sess.get(self.httpbin.join('get'))
            self.assertIsInstance(future, Future)
            resp = future.result()
            self.assertIsInstance(resp, Response)
            self.assertEqual(200, resp.status_code)

        self.assertTrue(passout._exit_called)


class TopLevelContextHelper(FuturesSession):
    def __init__(self, *args, **kwargs):
        super(TopLevelContextHelper, self).__init__(*args, **kwargs)
        self._exit_called = False

    def __exit__(self, *args, **kwargs):
        self._exit_called = True
        return super(TopLevelContextHelper, self).__exit__(*args, **kwargs)


if __name__ == '__main__':
    main()
