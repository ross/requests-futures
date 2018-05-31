#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Tests for Requests."""

from concurrent.futures import Future, ProcessPoolExecutor
from os import environ
from sys import version_info
try:
    from sys import pypy_version_info
except ImportError:
    pypy_version_info = None
from unittest import TestCase, main, skipIf

from requests import Response, session
from requests.adapters import DEFAULT_POOLSIZE
from requests_futures.sessions import FuturesSession

HTTPBIN = environ.get('HTTPBIN_URL', 'http://httpbin.org/')


def httpbin(*suffix):
    """Returns url for HTTPBIN resource."""
    return HTTPBIN + '/'.join(suffix)


class RequestsTestCase(TestCase):

    def test_futures_session(self):
        # basic futures get
        sess = FuturesSession()
        future = sess.get(httpbin('get'))
        self.assertIsInstance(future, Future)
        resp = future.result()
        self.assertIsInstance(resp, Response)
        self.assertEqual(200, resp.status_code)

        # non-200, 404
        future = sess.get(httpbin('status/404'))
        resp = future.result()
        self.assertEqual(404, resp.status_code)

        def cb(s, r):
            self.assertIsInstance(s, FuturesSession)
            self.assertIsInstance(r, Response)
            # add the parsed json data to the response
            r.data = r.json()

        future = sess.get(httpbin('get'), background_callback=cb)
        # this should block until complete
        resp = future.result()
        self.assertEqual(200, resp.status_code)
        # make sure the callback was invoked
        self.assertTrue(hasattr(resp, 'data'))

        def rasing_cb(s, r):
            raise Exception('boom')

        future = sess.get(httpbin('get'), background_callback=rasing_cb)
        with self.assertRaises(Exception) as cm:
            resp = future.result()
        self.assertEqual('boom', cm.exception.args[0])

    def test_supplied_session(self):
        """ Tests the `session` keyword argument. """
        requests_session = session()
        requests_session.headers['Foo'] = 'bar'
        sess = FuturesSession(session=requests_session)
        future = sess.get(httpbin('headers'))
        self.assertIsInstance(future, Future)
        resp = future.result()
        self.assertIsInstance(resp, Response)
        self.assertEqual(200, resp.status_code)
        self.assertEqual(resp.json()['headers']['Foo'], 'bar')

    def test_max_workers(self):
        """ Tests the `max_workers` shortcut. """
        from concurrent.futures import ThreadPoolExecutor
        session = FuturesSession()
        self.assertEqual(session.executor._max_workers, 2)
        session = FuturesSession(max_workers=5)
        self.assertEqual(session.executor._max_workers, 5)
        session = FuturesSession(executor=ThreadPoolExecutor(max_workers=10))
        self.assertEqual(session.executor._max_workers, 10)
        session = FuturesSession(executor=ThreadPoolExecutor(max_workers=10),
                                 max_workers=5)
        self.assertEqual(session.executor._max_workers, 10)

    def test_adapter_kwargs(self):
        """ Tests the `adapter_kwargs` shortcut. """
        from concurrent.futures import ThreadPoolExecutor
        session = FuturesSession()
        self.assertFalse(session.get_adapter('http://')._pool_block)
        session = FuturesSession(max_workers=DEFAULT_POOLSIZE + 1,
                                 adapter_kwargs={'pool_block': True})
        adapter = session.get_adapter('http://')
        self.assertTrue(adapter._pool_block)
        self.assertEqual(adapter._pool_connections, DEFAULT_POOLSIZE + 1)
        self.assertEqual(adapter._pool_maxsize, DEFAULT_POOLSIZE + 1)
        session = FuturesSession(executor=ThreadPoolExecutor(max_workers=10),
                                 adapter_kwargs={'pool_connections': 20})
        self.assertEqual(session.get_adapter('http://')._pool_connections, 20)

    def test_redirect(self):
        """ Tests for the ability to cleanly handle redirects. """
        sess = FuturesSession()
        future = sess.get(httpbin('redirect-to?url=get'))
        self.assertIsInstance(future, Future)
        resp = future.result()
        self.assertIsInstance(resp, Response)
        self.assertEqual(200, resp.status_code)

        future = sess.get(httpbin('redirect-to?url=status/404'))
        resp = future.result()
        self.assertEqual(404, resp.status_code)

    def test_context(self):

        class FuturesSessionTestHelper(FuturesSession):

            def __init__(self, *args, **kwargs):
                super(FuturesSessionTestHelper, self).__init__(*args, **kwargs)
                self._exit_called = False

            def __exit__(self, *args, **kwargs):
                self._exit_called = True
                return super(FuturesSessionTestHelper, self).__exit__(*args,
                                                                      **kwargs)

        passout = None
        with FuturesSessionTestHelper() as sess:
            passout = sess
            future = sess.get(httpbin('get'))
            self.assertIsInstance(future, Future)
            resp = future.result()
            self.assertIsInstance(resp, Response)
            self.assertEqual(200, resp.status_code)

        self.assertTrue(passout._exit_called)


# << test process pool executor >>
# see discussion https://github.com/ross/requests-futures/issues/11
def global_cb_modify_response(s, r):
    """ add the parsed json data to the response """
    assert s, FuturesSession
    assert r, Response
    r.data = r.json()
    r.__attrs__.append('data')  # required for pickling new attribute


def global_cb_return_result(s, r):
    """ simply return parsed json data """
    assert s, FuturesSession
    assert r, Response
    return r.json()


def global_rasing_cb(s, r):
    raise Exception('boom')


# pickling instance method supported only from here
unsupported_platform = version_info < (3, 4) and not pypy_version_info
session_required = version_info < (3, 5,) and not pypy_version_info


@skipIf(unsupported_platform, 'not supported in python < 3.4')
class RequestsProcessPoolTestCase(TestCase):

    def setUp(self):
        self.proc_executor = ProcessPoolExecutor(max_workers=2)
        self.session = session()

    @skipIf(session_required, 'not supported in python < 3.5')
    def test_futures_session(self):
        self._assert_futures_session()

    @skipIf(not session_required, 'fully supported on python >= 3.5')
    def test_exception_raised(self):
        with self.assertRaises(RuntimeError):
            self._assert_futures_session()

    def test_futures_existing_session(self):
        self.session.headers['Foo'] = 'bar'
        self._assert_futures_session(session=self.session)

    def _assert_futures_session(self, session=None):
        # basic futures get
        if session:
            sess = FuturesSession(executor=self.proc_executor, session=session)
        else:
            sess = FuturesSession(executor=self.proc_executor)

        future = sess.get(httpbin('get'))
        self.assertIsInstance(future, Future)
        resp = future.result()
        self.assertIsInstance(resp, Response)
        self.assertEqual(200, resp.status_code)

        # non-200, 404
        future = sess.get(httpbin('status/404'))
        resp = future.result()
        self.assertEqual(404, resp.status_code)

        future = sess.get(httpbin('get'),
                          background_callback=global_cb_modify_response)
        # this should block until complete
        resp = future.result()
        if session:
            self.assertEqual(resp.json()['headers']['Foo'], 'bar')
        self.assertEqual(200, resp.status_code)
        # make sure the callback was invoked
        self.assertTrue(hasattr(resp, 'data'))

        future = sess.get(httpbin('get'),
                          background_callback=global_cb_return_result)
        # this should block until complete
        resp = future.result()
        # make sure the callback was invoked
        self.assertIsInstance(resp, dict)

        future = sess.get(httpbin('get'), background_callback=global_rasing_cb)
        with self.assertRaises(Exception) as cm:
            resp = future.result()
        self.assertEqual('boom', cm.exception.args[0])

        # Tests for the ability to cleanly handle redirects
        future = sess.get(httpbin('redirect-to?url=get'))
        self.assertIsInstance(future, Future)
        resp = future.result()
        self.assertIsInstance(resp, Response)
        self.assertEqual(200, resp.status_code)

        future = sess.get(httpbin('redirect-to?url=status/404'))
        resp = future.result()
        self.assertEqual(404, resp.status_code)

    @skipIf(session_required, 'not supported in python < 3.5')
    def test_context(self):
        self._assert_context()

    def test_context_with_session(self):
        self._assert_context(session=self.session)

    def _assert_context(self, session=None):
        if session:
            helper_instance = TopLevelContextHelper(executor=self.proc_executor,
                                                    session=self.session)
        else:
            helper_instance = TopLevelContextHelper(executor=self.proc_executor)
        passout = None
        with helper_instance as sess:
            passout = sess
            future = sess.get(httpbin('get'))
            self.assertIsInstance(future, Future)
            resp = future.result()
            self.assertIsInstance(resp, Response)
            self.assertEqual(200, resp.status_code)

        self.assertTrue(passout._exit_called)


class TopLevelContextHelper(FuturesSession):
    def __init__(self, *args, **kwargs):
        super(TopLevelContextHelper, self).__init__(
            *args, **kwargs)
        self._exit_called = False

    def __exit__(self, *args, **kwargs):
        self._exit_called = True
        return super(TopLevelContextHelper, self).__exit__(
            *args, **kwargs)


@skipIf(not unsupported_platform, 'Exception raised when unsupported')
class ProcessPoolExceptionRaisedTestCase(TestCase):
    def test_exception_raised(self):
        executor = ProcessPoolExecutor(max_workers=2)
        sess = FuturesSession(executor=executor, session=session())
        with self.assertRaises(RuntimeError):
            sess.get(httpbin('get'))


if __name__ == '__main__':
    main()
