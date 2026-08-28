Usage
=====

This page works through the library in the order you're likely to need it:
basic requests, waiting on several at once, error handling, tuning the
worker pool and connection pool together, streaming, sharing resources
across sessions, the ``hooks`` mechanism, ``ProcessPoolExecutor``, and
finally a thread-safety caveat that applies no matter which of the above
you use.

All of the examples create a plain :class:`~requests_futures.sessions.FuturesSession`
unless noted otherwise.

Basic usage
-----------

``get``, ``post``, and the rest of the usual :class:`~requests.Session`
methods all return a :class:`~concurrent.futures.Future` instead of a
:class:`~requests.Response`. The request is already running by the time the
call returns; call :meth:`~concurrent.futures.Future.result` when you
actually need the response.

.. code-block:: python

    from requests_futures.sessions import FuturesSession

    session = FuturesSession()

    # both requests start immediately, on separate worker threads
    future_one = session.get('https://httpbin.org/get')
    future_two = session.get('https://httpbin.org/get?foo=bar')

    # .result() blocks only if the response isn't back yet
    response_one = future_one.result()
    print(response_one.status_code, response_one.content)

    response_two = future_two.result()
    print(response_two.status_code, response_two.content)

Tying extra information to the request/response
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The response knows the request that produced it via ``response.request``, so
the URL (and headers, method, body, ...) are available without tracking
them yourself:

.. code-block:: python

    from concurrent.futures import as_completed
    from requests_futures.sessions import FuturesSession

    session = FuturesSession()
    futures = [session.get(f'https://httpbin.org/get?i={i}') for i in range(3)]

    for future in as_completed(futures):
        response = future.result()
        print(response.request.url, response.json())

For information that isn't derivable from the request itself, attach it to
the future object -- nothing stops you from setting your own attributes on
it:

.. code-block:: python

    from concurrent.futures import as_completed
    from requests_futures.sessions import FuturesSession

    session = FuturesSession()

    futures = []
    for i in range(3):
        future = session.get('https://httpbin.org/get')
        future.i = i
        futures.append(future)

    for future in as_completed(futures):
        response = future.result()
        print(future.i, response.json())

Waiting with ``as_completed`` and a timeout
--------------------------------------------

:func:`concurrent.futures.as_completed` accepts a ``timeout`` measured from
the call itself, not per-future. If it elapses before every future is done,
it raises :class:`concurrent.futures.TimeoutError` -- the futures that
weren't yet done keep running in the background regardless, so it's up to
you to decide whether to still wait on them, or to cancel them via
:meth:`~concurrent.futures.Future.cancel` (which only succeeds for a future
that hasn't started running yet).

.. code-block:: python

    from concurrent.futures import TimeoutError, as_completed
    from requests_futures.sessions import FuturesSession

    session = FuturesSession()
    futures = [
        session.get(f'https://httpbin.org/delay/{i}') for i in range(1, 4)
    ]

    try:
        for future in as_completed(futures, timeout=2):
            print(future.result().status_code)
    except TimeoutError:
        print('some requests were still in flight after 2 seconds')

Error handling across the future boundary
------------------------------------------

Two different kinds of error surface at two different points:

* **At submit time** -- i.e. from the ``session.get(...)`` call itself.
  This happens for problems `request()` (or the executor it hands work to)
  can detect before the request ever runs:

  * When the executor is a :class:`~concurrent.futures.ProcessPoolExecutor`,
    an unpicklable callable or argument (a local function passed as
    `hooks`, a file-like `data=`) raises ``RuntimeError`` with a pointer to
    the :ref:`ProcessPoolExecutor section <processpoolexecutor>` below,
    chaining the original pickling error as ``__cause__``.
  * Submitting **after** :meth:`~requests_futures.sessions.FuturesSession.close`
    also raises synchronously, but the exact exception depends on how the
    session was built:

    * With the default, self-owned executor (no ``executor=`` supplied --
      the common case), ``close()`` has already shut that executor down,
      so the submit call itself raises ``RuntimeError('cannot schedule new
      futures after shutdown')`` -- that message comes from
      `concurrent.futures` itself, not from `requests-futures`. This is
      true whether or not ``session=`` was also supplied.
    * With a supplied ``executor=`` and no ``session=``, ``close()`` leaves
      the executor running but rejects new submissions itself, with
      ``RuntimeError('cannot schedule new futures after close')``.
    * With both a supplied ``executor=`` *and* a supplied ``session=``,
      ``close()`` never touches the executor, so submitting after
      ``close()`` keeps working.

* **At** :meth:`~concurrent.futures.Future.result` **time** -- everything
  else: connection errors, timeouts, non-2xx status codes (`requests` only
  raises those if you call :meth:`~requests.Response.raise_for_status`
  yourself), and any exception raised by a `hooks` callback. Move your
  `try`/`except` there:

.. code-block:: python

    from requests.exceptions import RequestException
    from requests_futures.sessions import FuturesSession

    session = FuturesSession()
    future = session.get('https://httpbin.org/status/500')

    try:
        response = future.result()
        response.raise_for_status()
    except RequestException as e:
        print(f'request failed: {e}')

Retries via a mounted ``HTTPAdapter``
--------------------------------------

Retries are configured the same way as plain `requests`: mount an
:class:`~requests.adapters.HTTPAdapter` with a :class:`urllib3.util.Retry`
policy, either directly on a session you supply, or via `adapter_kwargs`.

.. code-block:: python

    from requests import Session
    from requests.adapters import HTTPAdapter, Retry
    from requests_futures.sessions import FuturesSession

    retry = Retry(
        total=5, backoff_factor=0.5, status_forcelist=[502, 503, 504]
    )
    requests_session = Session()
    requests_session.mount('https://', HTTPAdapter(max_retries=retry))

    session = FuturesSession(session=requests_session)
    future = session.get('https://httpbin.org/status/503')
    print(future.result().status_code)

``FuturesSession`` only reads pool-sizing arguments (`max_workers`,
`adapter_kwargs`) out of the adapter -- it never replaces it. Internally,
`_configure_adapters()` reconfigures the adapter *in place*
(``init_poolmanager()``) rather than mounting a fresh one, so a supplied
session's retry policy, and any custom :class:`~requests.adapters.HTTPAdapter`
subclass, survive untouched. The same applies to `adapter_kwargs` passed
without a `session=`: it configures the adapters `FuturesSession` mounts on
itself, again without replacing them.

.. _sizing-max-workers:

Sizing ``max_workers`` against the connection pool
-----------------------------------------------------

By default a session opens a :class:`~concurrent.futures.ThreadPoolExecutor`
with 8 workers -- but `requests`' underlying connection pool
(:data:`~requests.adapters.DEFAULT_POOLSIZE`, currently 10) is sized
independently. With the default adapter settings (`pool_block=False`),
raising `max_workers` past the pool size doesn't block the extra worker
threads -- urllib3 just opens a fresh connection whenever the pool is
empty. The cost instead is connection churn: a connection that's returned
to an already-full pool gets closed and discarded rather than reused, so
those extra workers pay a new TCP/TLS handshake on every request instead
of reusing a warm connection. (Passing `pool_block=True` changes this to
real blocking -- worker threads then wait for a pooled connection to free
up instead of opening new ones -- which trades throughput for a hard cap
on open connections.) Either way, an undersized pool quietly defeats the
point of using a thread pool of that size in the first place.

`FuturesSession` only protects you from this automatically when it creates
the executor itself -- that is, whenever you *don't* pass `executor=`,
whether or not you pass `session=`. In that case, a `max_workers` bigger
than the pool is enough on its own: the pool is grown to match
(`pool_connections`/`pool_maxsize` both set to `max_workers`), applied to
whichever session actually serves requests:

.. code-block:: python

    from requests_futures.sessions import FuturesSession

    # max_workers > DEFAULT_POOLSIZE, so the pool is grown to match
    # automatically (pool_connections=pool_maxsize=max_workers)
    session = FuturesSession(max_workers=20)

.. code-block:: python

    from requests import Session
    from requests_futures.sessions import FuturesSession

    # same automatic growth, applied to requests_session's adapters instead
    # of the FuturesSession's own (requests_session is what actually serves
    # requests here)
    requests_session = Session()
    session = FuturesSession(session=requests_session, max_workers=20)

`adapter_kwargs` lets you override or fine-tune that sizing on top of
whatever `max_workers` computed, in either case above.

The trap is once you pass your own `executor=`: `max_workers` is then
ignored *entirely*, including for pool sizing -- there is no `max_workers`
value left to size the pool from, since the executor already exists. Size
both the executor and, via `adapter_kwargs`, the pool yourself:

.. code-block:: python

    from concurrent.futures import ThreadPoolExecutor
    from requests_futures.sessions import FuturesSession

    session = FuturesSession(
        executor=ThreadPoolExecutor(max_workers=20),
        adapter_kwargs={'pool_connections': 20, 'pool_maxsize': 20},
    )

Streaming
---------

``stream=True`` defers downloading the response body until you iterate
:attr:`~requests.Response.iter_content` /
:attr:`~requests.Response.iter_lines`, or otherwise read the body -- but by
the time ``future.result()`` returns you, that's already happening on
`FuturesSession`'s background thread, which has moved on to its next queued
request. There is no built-in way to keep iterating the body *on* that
worker thread once ``result()`` has returned control to you, so:

* If you actually need incremental processing of a large body, consume it
  as far as you need *inside* a `hooks` callback, on the background thread,
  and attach the result to the response -- the same way you'd pre-parse
  JSON there (see below).
* Otherwise, just don't set ``stream=True``: let `FuturesSession` finish
  downloading the body in the background, so it's already sitting in
  ``response.content`` by the time you call `result()`.

.. code-block:: python

    from requests_futures.sessions import FuturesSession

    session = FuturesSession()


    def consume_in_background(response, *args, **kwargs):
        # runs on the worker thread, while the caller is free to do other
        # things
        total = 0
        for chunk in response.iter_content(chunk_size=8192):
            total += len(chunk)
        response.total_bytes = total


    future = session.get(
        'https://httpbin.org/stream/20',
        stream=True,
        hooks={'response': consume_in_background},
    )
    response = future.result()
    print(response.total_bytes)

Sharing one executor across several sessions
-----------------------------------------------

Passing the same `executor=` to more than one `FuturesSession` is a
reasonable way to cap the *total* number of background workers across
several logical clients, instead of each session getting its own pool of 8:

.. code-block:: python

    from concurrent.futures import ThreadPoolExecutor
    from requests_futures.sessions import FuturesSession

    executor = ThreadPoolExecutor(max_workers=10)
    api_session = FuturesSession(executor=executor)
    cdn_session = FuturesSession(executor=executor)

Because neither session created `executor`, `_owned_executor` is `False` for
both, so calling :meth:`~requests_futures.sessions.FuturesSession.close` on
either one **never shuts the executor down** -- it stays usable by the other
session (and by anything else still holding a reference to it). Shut it
down yourself, once every session sharing it is done with it:

.. code-block:: python

    api_session.close()   # closes api_session's own connections only
    cdn_session.close()   # ditto for cdn_session
    executor.shutdown()   # now it's safe to stop the shared pool

The exception is a session built with *both* a supplied `executor=` and no
`session=`: for that one combination, `close()` still cancels and waits for
that session's own queued futures (tracked separately per-session) before
returning, without touching the executor itself -- see
:meth:`requests_futures.sessions.FuturesSession.request` for exactly which
combination that is.

``hooks`` (the recommended replacement for ``background_callback``)
------------------------------------------------------------------------

`background_callback` is deprecated (it now raises a `DeprecationWarning`)
in favor of `requests`' own hooks_ mechanism, which does the same job --
running code against the response before `.result()` returns it -- without
a `requests-futures`-specific API to learn.

.. _hooks: https://requests.readthedocs.io/en/latest/user/advanced/#event-hooks

.. code-block:: python

    from requests_futures.sessions import FuturesSession

    session = FuturesSession()


    def parse_json(response, *args, **kwargs):
        # mutate the response in place; nothing needs to be returned
        response.data = response.json()


    future = session.get(
        'https://httpbin.org/get', hooks={'response': parse_json}
    )
    response = future.result()
    print(response.data)

A hook can also be set once, on the session, rather than per-request:

.. code-block:: python

    session = FuturesSession()
    session.hooks['response'] = parse_json

    response = session.get('https://httpbin.org/get').result()
    print(response.data)

A response hook's return value has the same contract as
`background_callback`'s: `requests`' own `dispatch_hook()` assigns a
hook's return value back over the response whenever it isn't `None`, so
returning something replaces the response for the rest of `Session.send`
-- and therefore what `.result()` returns -- exactly like the module-level
:func:`~requests_futures.sessions.wrap` does for `background_callback`.
The examples above return nothing and mutate `response` in place, which is
the common case, but a hook that returns a value works too:

.. code-block:: python

    def parse_json(response, *args, **kwargs):
        # replaces the Response with its parsed body entirely
        return response.json()


    future = session.get(
        'https://httpbin.org/get', hooks={'response': parse_json}
    )
    print(future.result())  # a dict, not a Response

.. _processpoolexecutor:

Using ``ProcessPoolExecutor``
------------------------------

Passing a :class:`~concurrent.futures.ProcessPoolExecutor` runs each request
in a worker process instead of a worker thread. This trades the GIL (not
usually a bottleneck for I/O-bound HTTP requests anyway) for real process
isolation -- useful mainly when handling very large responses that you want
released back to the OS by recycling the worker process, or when a
`hooks` callback does CPU-heavy work you want to run in parallel.

Everything the executor pickles when it submits a call -- the function,
positional arguments, and keyword arguments -- must be importable by name.
In practice that means:

* Any `hooks` callback (or deprecated `background_callback`) must be a
  module-level function, not a local function, a lambda, or a bound method.
* Request arguments must themselves be picklable -- a file-like `data=`
  object generally isn't.
* A `FuturesSession` subclass used with a process pool must be defined at
  module scope so worker processes can import it.
* The :class:`~requests.Response` itself has to travel back from the
  worker process to the parent, and :meth:`~requests.Response.__getstate__`
  only pickles the fixed set of attributes in
  :attr:`~requests.Response.__attrs__` (``_content``, `status_code`,
  `headers`, and so on) -- **not** arbitrary attributes a `hooks` callback
  added, like the `response.data` from the earlier examples. Append the
  attribute's name to `response.__attrs__` from inside the callback before
  it returns, or it silently disappears when the response is unpickled in
  the parent process.

`FuturesSession` checks all of this up front and raises `RuntimeError` at
submit time (see `Error handling across the future boundary`_) rather than
letting a raw pickling error surface later from `.result()`.

.. code-block:: python

    from concurrent.futures import ProcessPoolExecutor
    from requests_futures.sessions import FuturesSession


    # Module-level, and therefore importable by name -- a local function or
    # a lambda here would fail to pickle as soon as it's submitted.
    def parse_json(response, *args, **kwargs):
        response.data = response.json()
        # required so the new `data` attribute survives being pickled back
        # from the worker process -- see the bullet above
        response.__attrs__.append('data')


    if __name__ == '__main__':
        # the process-start guard above matters here too: on platforms
        # where multiprocessing defaults to "spawn" (macOS, Windows), the
        # worker processes re-import this module, and without the guard
        # they would each try to recreate the executor themselves
        session = FuturesSession(executor=ProcessPoolExecutor(max_workers=4))
        future = session.get(
            'https://httpbin.org/get', hooks={'response': parse_json}
        )
        response = future.result()
        print(response.data)

Thread-safety caveat
---------------------

:class:`requests.Session` -- and therefore `FuturesSession`, which is one --
**is not thread-safe**. Nothing about `FuturesSession` changes that; it just
makes it much easier to run into, because the default configuration hands
out exactly *one* session to 8 worker threads at once.

Concretely, this matters whenever a request mutates shared session state:

* The cookie jar. A response with `Set-Cookie` headers updates
  ``session.cookies`` in place. Two responses landing on two different
  worker threads at the same time can interleave those updates
  unpredictably, or, on some Python versions/collection implementations,
  corrupt the jar's internal structure outright.
* ``session.headers`` (or ``session.auth``, ``session.params``, ...) --
  mutating any of these from one thread while another thread's request is
  reading them to build its own request is a data race, not merely a
  logical inconsistency.

What to do instead:

* If different logical clients need different cookies, auth, or headers,
  give each one its own `FuturesSession` (optionally sharing one
  `executor=` across them, as above) rather than mutating one shared
  session concurrently.
* If you need per-request headers/auth/cookies that vary independently of
  any session-level default, pass them as arguments to `get`/`post`/etc.
  (``session.get(url, headers={...})``) instead of mutating
  ``session.headers`` -- `requests` merges per-request values over the
  session's own without touching shared state.
* Treat "set it once before making any requests, never touch it again" as
  the only safe way to use session-level mutable state (`headers`, `auth`,
  `cookies`) with a `FuturesSession` that has more than one worker.
