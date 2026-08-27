# -*- coding: utf-8 -*-
"""
requests_futures
~~~~~~~~~~~~~~~~

This module provides a small add-on for the requests http library. It makes use
of python 3.3's concurrent.futures or the futures backport for previous
releases of python.

    from requests_futures.sessions import FuturesSession

    session = FuturesSession()
    # request is run in the background
    future = session.get('http://httpbin.org/get')
    # ... do other stuff ...
    # wait for the request to complete, if it hasn't already
    response = future.result()
    print('response status: {0}'.format(response.status_code))
    print(response.content)

"""

from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from functools import partial
from pickle import dumps
from warnings import warn

from requests import Session
from requests.adapters import DEFAULT_POOLSIZE, DEFAULT_RETRIES, Retry


def wrap(self, sup, background_callback, *args_, **kwargs_):
    """A global top-level is required for ProcessPoolExecutor"""
    resp = sup(*args_, **kwargs_)
    result = background_callback(self, resp)
    return resp if result is None else result


def _configure_adapters(session, adapter_kwargs):
    """Apply `adapter_kwargs` to the adapters already mounted on `session`.

    Adapters are reconfigured in place, rather than replaced, so that a
    supplied session keeps its retry policy and any custom adapter behavior
    while still picking up the pool sizing.
    """
    for prefix in ('https://', 'http://'):
        adapter = session.get_adapter(prefix)
        if not hasattr(adapter, 'init_poolmanager'):
            # not an HTTPAdapter, pool sizing doesn't apply, leave it alone
            continue
        if 'max_retries' in adapter_kwargs:
            max_retries = adapter_kwargs['max_retries']
            # matches HTTPAdapter.__init__'s own handling
            if max_retries == DEFAULT_RETRIES:
                adapter.max_retries = Retry(0, read=False)
            else:
                adapter.max_retries = Retry.from_int(max_retries)

        pool_connections = adapter_kwargs.get(
            'pool_connections', adapter._pool_connections
        )
        pool_maxsize = adapter_kwargs.get('pool_maxsize', adapter._pool_maxsize)
        pool_block = adapter_kwargs.get('pool_block', adapter._pool_block)
        if (pool_connections, pool_maxsize, pool_block) == (
            adapter._pool_connections,
            adapter._pool_maxsize,
            adapter._pool_block,
        ):
            # nothing to resize, leave the existing pools and their warm
            # connections alone
            continue

        adapter.init_poolmanager(
            pool_connections, pool_maxsize, block=pool_block
        )
        # cached proxy managers were built with the old pool settings and
        # init_poolmanager() doesn't touch them, so drop them to be rebuilt
        # from the new settings on next use
        for proxy_manager in adapter.proxy_manager.values():
            proxy_manager.clear()
        adapter.proxy_manager.clear()


PICKLE_ERROR = (
    'Cannot pickle request. Refer to documentation: https://'
    'github.com/ross/requests-futures/#using-processpoolexecutor'
)


class FuturesSession(Session):
    def __init__(
        self,
        executor=None,
        max_workers=8,
        session=None,
        adapter_kwargs=None,
        *args,
        **kwargs,
    ):
        """Creates a FuturesSession

        Notes
        ~~~~~
        * `ProcessPoolExecutor` may be used with Python > 3.4;
          see README for more information.

        * If you provide both `executor` and `max_workers`, the latter is
          ignored and provided executor is used as is.
        """
        _adapter_kwargs = {}
        super(FuturesSession, self).__init__(*args, **kwargs)
        self._owned_executor = executor is None
        if executor is None:
            executor = ThreadPoolExecutor(max_workers=max_workers)
            # set connection pool size equal to max_workers if needed
            if max_workers > DEFAULT_POOLSIZE:
                _adapter_kwargs.update(
                    {
                        'pool_connections': max_workers,
                        'pool_maxsize': max_workers,
                    }
                )

        _adapter_kwargs.update(adapter_kwargs or {})

        if _adapter_kwargs:
            # configure whichever session will actually serve requests: the
            # supplied one, if any, otherwise self. `self.session` isn't
            # assigned yet, so the `session` argument is used directly here.
            _configure_adapters(session or self, _adapter_kwargs)

        self.executor = executor
        self.session = session

    def request(self, *args, **kwargs):
        """Maintains the existing api for Session.request.

        Used by all of the higher level methods, e.g. Session.get.

        The background_callback param allows you to do some processing on the
        response in the background, e.g. call resp.json() so that json parsing
        happens in the background thread. It is deprecated; use `hooks`
        instead.

        When the executor is a `ProcessPoolExecutor`, the function *and* its
        arguments must all be picklable, since that's what gets sent to the
        worker process; this is verified up front so a bad `hooks` callable
        or file-like `data=` raises `RuntimeError` here rather than a raw
        pickling error out of the returned `Future`.

        :rtype : concurrent.futures.Future
        """
        if self.session:
            func = self.session.request
        else:
            # avoid calling super to not break pickled method
            func = partial(Session.request, self)

        background_callback = kwargs.pop('background_callback', None)
        if background_callback:
            # stacklevel 4: warn -> request -> requests' Session.<verb> ->
            # our <verb> -> caller
            warn(
                '`background_callback` is DEPRECATED. Use `hooks` instead. '
                'Will be removed in 2.0.',
                DeprecationWarning,
                stacklevel=4,
            )
            func = partial(wrap, self, func, background_callback)

        if isinstance(self.executor, ProcessPoolExecutor):
            # verify the whole call can be pickled, not just the function;
            # the executor pickles these same objects when submitting, so
            # anything rejected here would have failed there too, but with
            # a raw error out of future.result() instead of a pointer to
            # the docs. Pickle's failure mode varies by object and python
            # version, so the catch is broad; the original is preserved as
            # __cause__.
            try:
                dumps((func, args, kwargs))
            except Exception as e:
                raise RuntimeError(PICKLE_ERROR) from e

        return self.executor.submit(func, *args, **kwargs)

    def close(self):
        super(FuturesSession, self).close()
        if self._owned_executor:
            self.executor.shutdown(cancel_futures=True)

    def get(self, url, **kwargs):
        r"""
        Sends a GET request. Returns :class:`Future` object.

        :param url: URL for the new :class:`Request` object.
        :param \*\*kwargs: Optional arguments that ``request`` takes.
        :rtype : concurrent.futures.Future
        """
        return super(FuturesSession, self).get(url, **kwargs)

    def options(self, url, **kwargs):
        r"""Sends a OPTIONS request. Returns :class:`Future` object.

        :param url: URL for the new :class:`Request` object.
        :param \*\*kwargs: Optional arguments that ``request`` takes.
        :rtype : concurrent.futures.Future
        """
        return super(FuturesSession, self).options(url, **kwargs)

    def head(self, url, **kwargs):
        r"""Sends a HEAD request. Returns :class:`Future` object.

        :param url: URL for the new :class:`Request` object.
        :param \*\*kwargs: Optional arguments that ``request`` takes.
        :rtype : concurrent.futures.Future
        """
        return super(FuturesSession, self).head(url, **kwargs)

    def post(self, url, data=None, json=None, **kwargs):
        r"""Sends a POST request. Returns :class:`Future` object.

        :param url: URL for the new :class:`Request` object.
        :param data: (optional) Dictionary, list of tuples, bytes, or file-like
            object to send in the body of the :class:`Request`.
        :param json: (optional) json to send in the body of the :class:`Request`.
        :param \*\*kwargs: Optional arguments that ``request`` takes.
        :rtype : concurrent.futures.Future
        """
        return super(FuturesSession, self).post(
            url, data=data, json=json, **kwargs
        )

    def put(self, url, data=None, **kwargs):
        r"""Sends a PUT request. Returns :class:`Future` object.

        :param url: URL for the new :class:`Request` object.
        :param data: (optional) Dictionary, list of tuples, bytes, or file-like
            object to send in the body of the :class:`Request`.
        :param \*\*kwargs: Optional arguments that ``request`` takes.
        :rtype : concurrent.futures.Future
        """
        return super(FuturesSession, self).put(url, data=data, **kwargs)

    def patch(self, url, data=None, **kwargs):
        r"""Sends a PATCH request. Returns :class:`Future` object.

        :param url: URL for the new :class:`Request` object.
        :param data: (optional) Dictionary, list of tuples, bytes, or file-like
            object to send in the body of the :class:`Request`.
        :param \*\*kwargs: Optional arguments that ``request`` takes.
        :rtype : concurrent.futures.Future
        """
        return super(FuturesSession, self).patch(url, data=data, **kwargs)

    def delete(self, url, **kwargs):
        r"""Sends a DELETE request. Returns :class:`Future` object.

        :param url: URL for the new :class:`Request` object.
        :param \*\*kwargs: Optional arguments that ``request`` takes.
        :rtype : concurrent.futures.Future
        """
        return super(FuturesSession, self).delete(url, **kwargs)
