requests-futures
================

Asynchronous Python HTTP requests, for humans, using `requests`_ and Python's
built-in `concurrent.futures`_.

.. _requests: https://requests.readthedocs.io/en/latest/
.. _concurrent.futures: https://docs.python.org/3/library/concurrent.futures.html

``requests_futures.sessions.FuturesSession`` is a drop-in-ish
:class:`~requests.Session` subclass: every request-making method (``get``,
``post``, ``head``, ...) still works exactly as it does on a plain
``Session``, except it returns a :class:`~concurrent.futures.Future`
immediately, instead of blocking for a :class:`~requests.Response`. The
request itself runs in a background thread (or process, if you supply a
:class:`~concurrent.futures.ProcessPoolExecutor`), so several requests can be
in flight at once.

Install
-------

.. code-block:: shell

    pip install requests-futures

Quickstart
----------

.. code-block:: python

    from requests_futures.sessions import FuturesSession

    session = FuturesSession()

    # the request is sent immediately, in the background
    future = session.get('https://httpbin.org/get')

    # ... do other work here while it's in flight ...

    # blocks only if the response isn't back yet
    response = future.result()
    print(response.status_code, response.json())

See :doc:`usage` for the fuller picture: multiple requests with
``as_completed``, error handling across the future boundary, retries,
sizing the worker pool, streaming, sharing an executor across sessions,
``hooks``, ``ProcessPoolExecutor``, and the thread-safety caveats that come
with sharing a ``Session``.

Documentation
-------------

.. toctree::
   :maxdepth: 2

   usage
   api

Indices and tables
-------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
