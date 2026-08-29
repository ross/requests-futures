## 1.1.0 - 2026-08-28

Minor:
* Cancel queued requests on close

Patch:
* Remove the unused __build__ attribute and the Python 2.7 NullHandler fallback - [#199](https://github.com/ross/requests-futures/pull/199)
* Close owned sessions after their background requests finish, including when
using a supplied executor, and reject requests after close - [#197](https://github.com/ross/requests-futures/pull/197)
* Pickle check covers request arguments, not just the callable - [#196](https://github.com/ross/requests-futures/pull/196)
* background_callback now emits a DeprecationWarning instead of a log line - [#198](https://github.com/ross/requests-futures/pull/198)
* Fix pool sizing for supplied sessions
* Preserve falsy callback results

## v1.0.2 - 2024-11-15 - Helps if you have the address right

* Correct setup.py email addr

## v1.0.1 - 2023-06-19 - The first one in the CHANGELOG

* pyproject.toml config for black, isort, and pytest
