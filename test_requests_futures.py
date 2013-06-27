#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Tests for Requests."""

from concurrent.futures import Future
from requests import Response
from os import environ
from requests_futures.sessions import FuturesSession
from unittest import TestCase, main

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


if __name__ == '__main__':
    main()
