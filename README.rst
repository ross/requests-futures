Requests-Futures: Asynchronous Python HTTP Requests for Humans
==============================================================

Small add-on for the requests_ http library. Makes use of python 3.3's
`concurrent.futures`_ or the backport_ for prior versions of python.

The additional API is minimal and obeys the standard behavior of futures. The
synchronous code of two request show below.

.. code-block: python

    from requests import Session

    session = Session()
    # first requests starts and blocks until finished
    response_one = session.get('http://httpbin.org/get')
    # second request starts once first is finished
    response_two = session.get('http://httpbin.org/get?foo=bar')
    # both requests are complete
    print('response one status: {0}'.format(response_one.status_code))
    print(response_one.content)
    print('response two status: {0}'.format(response_two.status_code))
    print(response_two.content)

The above requests can be made asynchronous by making the following
modifications.

.. code-block: python

    from requests_futures.sessions import FuturesSession

    session = FuturesSession()
    # first request is started in background
    future_one = session.get('http://httpbin.org/get')
    # second requests is started immediately 
    future_two = session.get('http://httpbin.org/get?foo=bar')
    # wait for the first request to complete, if it hasn't already
    response_one = future_one.result()
    print('response one status: {0}'.format(response_one.status_code))
    print(response_one.content)
    # wait for the second request to complete, if it hasn't already
    response_two = future_two.result()
    print('response two status: {0}'.format(response_two.status_code))
    print(response_two.content)

By default a ThreadPoolExecutor is created with 2 workers. If you would like to
adjust that value or share a executor across multiple sessions you can provide
one to the FuturesSession constructor.

.. code-block: python

    from concurrent.futures import ThreadPoolExecutor
    from requests_futures.sessions import FuturesSession

    session = FuturesSession(executor=ThreadPoolExecutor(max_workers=10))
    # ...

That's it. The api of requests.Session is preserved without any modifications
beyond returning a Future rather than Response. As with all futures exceptions
are shifted (thrown) to the future.result() call so try/except blocks should be
moved there.

Working in the Background
=========================

There is one additional parameter to the various request function,
background_callback, which allows you to work with the Response objects in the
background thread. This can be useful for shifting work out of the foreground,
for a simple example take json parsing.

.. code-block: python

    from pprint import pprint
    from requests_futures.sessions import FuturesSession

    session = FuturesSession()

    def bg_cb(sess, resp):
        # parse the json storing the result on the response object
        resp.data = resp.json()

    future = session.get('http://httpbin.org/get', background_callback=bg_cb)
    # do some other stuff, send some more requests while this one works
    response = future.result()
    print('response status {0}'.format(response.status_code)
    # data will have been attached to the response object in the background
    pprint(response.data)


Installation
============

Python 3.3:

    pip install requests requests-futures

Prior versions:

    pip install futures requests requests-futures

.. _`requests`: https://github.com/kennethreitz/requests
.. _`concurrent.futures`: http://docs.python.org/dev/library/concurrent.futures.html
.. _backport: https://pypi.python.org/pypi/futures
