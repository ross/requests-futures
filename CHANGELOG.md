## v1.0.3 - 2026-08-27 - Mind the pool you're actually using

* Fix `max_workers`/`adapter_kwargs` connection pool sizing being applied to the unused
  `FuturesSession` instead of the supplied `session=`, which is what actually serves requests
* Pool sizing now reconfigures the target session's existing adapters in place, preserving
  retry policy and custom adapter behavior instead of replacing them, and rebuilds cached
  proxy managers so proxied requests pick up the new pool size

## v1.0.2 - 2024-11-15 - Helps if you have the address right

* Correct setup.py email addr

## v1.0.1 - 2023-06-19 - The first one in the CHANGELOG

* Add pytest.mark.network to test cases
* pyproject.toml config for black, isort, and pytest
