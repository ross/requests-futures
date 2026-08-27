# AGENTS.md

This file provides guidance to AI coding agents (Claude Code, Codex, etc.) when working with code in
this repository.

## Commands

This repo follows the "Scripts to Rule Them All" convention: everything under `script/` sources
`env/bin/activate` and **errors out if the venv doesn't exist**. Always run `./script/bootstrap` first
— never invoke `pytest`/`black`/`pyflakes` directly, they won't be on `PATH` until the venv is active.

- `./script/bootstrap` — creates `env/`, installs pinned `requirements.txt`, symlinks
  `.git_hooks_pre-commit` as the git pre-commit hook, sets `blame.ignoreRevsFile`. Override the venv
  location/interpreter with `VENV_NAME` / `VENV_PYTHON`.
- `./script/test [args...]` — runs pytest with `PYTHONPATH=.`. Args pass through, so a single test is:
  `./script/test tests/test_requests_futures.py::RequestsTestCase::test_max_workers`
- `./script/coverage [args...]` — pytest with branch coverage (html/xml/term reports). Also greps
  `requests_futures/` for `# pragma: no.*cover` and **fails if any is found** — coverage may not be
  disabled in this codebase.
- `./script/lint` — pyflakes over `*.py requests_futures/*.py tests/*.py`.
- `./script/format [--check]` — isort then black (line-length 80, no string normalization, no magic
  trailing comma; see `pyproject.toml`). Use `--check` for a non-mutating run.
- `./script/cibuild` — what CI runs: bootstrap, lint, format --check, coverage.
- `./script/cibuild-setup-py` — builds sdist/wheel in a throwaway venv and runs tests against the
  *installed* package, to validate packaging.
- `./script/update-requirements` — regenerates `requirements.txt` via `proviso`; never hand-edit that
  file.
- `./script/release` — maintainer-only: tags `v$__version__`, pushes the tag, builds, `twine upload`.

The installed pre-commit hook runs lint + format check + coverage, so a commit fails locally if any of
those fail — running them yourself before committing avoids a rejected commit.

Each linked `git worktree` needs its own `./script/bootstrap` run because each worktree has its own
`env/` virtualenv. The pre-commit hook is installed once in Git's shared hooks directory and runs the
checks from the worktree being committed.

## Architecture

The entire library is `requests_futures/sessions.py` (~200 lines), built around one class,
`FuturesSession(requests.Session)`:

- It overrides only `request()`, which submits the call to a `concurrent.futures` executor and returns
  a `Future` instead of a `Response`. The HTTP verb methods (`get`, `post`, etc.) are overridden purely
  to fix docstrings/`:rtype:`; they just delegate to `super()`.
- `request()` deliberately builds `partial(Session.request, self)` rather than calling `super()` —
  calling `super()` would break pickling under `ProcessPoolExecutor`. The module-level `wrap()`
  function exists for the same reason (a bound method isn't picklable). Before submitting to a
  `ProcessPoolExecutor`, it probes `dumps(func)` and raises `RuntimeError(PICKLE_ERROR)` on failure.
  Any change to `request()` must preserve process-pool picklability.
- Executor ownership: `_owned_executor` is only `True` when `FuturesSession` created the
  `ThreadPoolExecutor` itself (no `executor=` passed). `close()` only shuts down the executor in that
  case, so a caller-supplied executor shared across multiple sessions survives. `max_workers` is
  ignored whenever `executor` is explicitly passed.
- Connection-pool sizing: when the executor is created here (not caller-supplied) and
  `max_workers > DEFAULT_POOLSIZE` (from `requests.adapters`), `pool_connections`/`pool_maxsize` are
  raised to `max_workers` — otherwise urllib3's default pool size throttles the extra worker threads.
  `adapter_kwargs` is merged over those computed defaults and applies regardless of executor
  ownership. Either way, sizing reconfigures the `HTTPAdapter`s already mounted on whichever session
  will actually serve requests (the supplied `session=`, if any, otherwise the `FuturesSession`
  itself) in place via `_configure_adapters()`/`init_poolmanager()`, rather than mounting fresh
  adapters — so a supplied session's retry policy and any custom adapter subclass survive.
  `_configure_adapters()` also drops the adapter's cached proxy managers (`init_poolmanager()`
  doesn't touch them) whenever the pool settings actually change, so proxied requests pick up the
  new size too; when they don't change, it's a no-op and existing pools/proxy managers are left
  alone.
- `background_callback` (invoked via `wrap()`) is deprecated in favor of requests' native `hooks`
  mechanism; it just logs a deprecation warning and is kept for back-compat.

Tests (`tests/test_requests_futures.py`) run against a local `pytest-httpbin` server injected by the
`httpbin_on_class` autouse fixture as `self.httpbin` (used as `self.httpbin.join('get')`) — not a live
network call, despite the module-level `HTTPBIN` env-var fallback constant. The `ProcessPoolExecutor`
test cases require module-global callback functions and a module-global `FuturesSession` subclass
(`TopLevelContextHelper`) because anything submitted to a process pool must be picklable — follow that
pattern for any new process-pool test.

Python support matrix is 3.10–3.14 (see the CI matrix in `.github/workflows/`). `setup.py`'s
classifiers are stale (still list 2.7/3.6-3.8) and the code still uses the py2-compatible
`super(FuturesSession, self)` idiom rather than bare `super()` — match that existing style rather than
modernizing it in unrelated changes.

## Workflow

- Branch before making changes; never commit directly to `main`.
- Before committing, run `./script/test`, `./script/coverage`, `./script/lint`, and `./script/format`.
- Add a changelog entry for user-facing changes: this repo has no changelog-generation tool, so hand-edit
  `CHANGELOG.md` following the existing `## vX.Y.Z - YYYY-MM-DD - <title>` + bullet-list format used by
  prior entries, as part of the first commit on the branch.
- There is no coverage-report helper here; read `./script/coverage`'s `htmlcov/` output or its terminal
  report directly to find gaps.
- Push with `git push --set-upstream origin <branch>`, then open the PR with
  `gh pr create --title "<title>" --body "<body>" --assignee "@me"`. Link related issues/PRs with
  `/cc #NUM REASON` (or `/cc Fixes #NUM` when the PR closes the issue), one per line, in the PR body.
- The package version lives in `requests_futures/__init__.py` as `__version__`; `script/release` reads
  it directly to compute the git tag.
