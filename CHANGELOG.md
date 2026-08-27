## v1.0.3 - 2026-08-27 - Mind the pool you're actually using

* Fix `max_workers`/`adapter_kwargs` connection pool sizing being mounted onto the unused
  `FuturesSession` instead of the supplied `session=`, which is what actually serves requests

## v1.0.2 - 2024-11-15 - Helps if you have the address right

* Correct setup.py email addr

## v1.0.1 - 2023-06-19 - The first one in the CHANGELOG

* Add pytest.mark.network to test cases
* pyproject.toml config for black, isort, and pytest
