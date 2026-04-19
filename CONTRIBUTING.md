# Contributing — Testing Policy

**Rule #1 — No new feature ships without tests.**
Every PR that adds behavior must also add tests that would have failed
before the change. CI enforces this: the `unit-and-api`, `e2e`, and `ui`
jobs must all be green before merge.

---

## Test layout

```
tests/
  conftest.py            Shared fixtures (tmp_trade_data, tmp_cache,
                         groww_mock, groww_broken, api_client,
                         regression_golden, block_network autouse).
  _golden/               Frozen JSON response shapes — never edit by hand.
  unit/    @pytest.mark.unit   Pure-Python, <100 ms, no I/O.
  api/     @pytest.mark.api    FastAPI TestClient, all external HTTP mocked.
  e2e/     @pytest.mark.slow   Full CLI / pipeline runs against seeded cache.
  ui/      @pytest.mark.ui     Playwright against a live uvicorn.
```

Run subsets:

```bash
pytest -m unit          # <5 s, run on every save
pytest -m "unit or api" # default CI gate
pytest -m slow          # e2e (CI only)
pytest -m ui            # Playwright (CI only, after `playwright install`)
```

---

## Policy — adding a new feature

1. **New pure function?** → add a `tests/unit/test_<module>.py` case with
   at least one happy-path and one edge-case assertion.
2. **New FastAPI endpoint?** → add a `tests/api/test_<area>.py` case that
   calls it via `api_client` and snapshots the response with
   `regression_golden("<endpoint_name>", r.json())`.
3. **New UI page or interaction?** → add a `tests/ui/test_<page>.py`
   case that loads the page under the `live_server` fixture and asserts
   at least one user-visible element.
4. **New data source or scanner?** → mock the network call (use
   `groww_mock`, `responses`, or `monkeypatch`). **Never** hit the real
   internet in unit or api tests.

## Policy — changing an existing feature

* If you intentionally change an API response shape, delete the stale
  `tests/_golden/*.json` file and regenerate:
  ```bash
  UPDATE_GOLDEN=1 pytest -m api
  ```
  and mention the drift in the PR description.
* If you're renaming a public function or endpoint, grep the tests first.
  A red test here is the early warning that a downstream feature will
  also break.

## Policy — Groww-only data source

The `should_use_non_groww_source()` gate is the load-bearing invariant
that keeps the scanner from silently falling back to geo-blocked Yahoo /
NSE endpoints. There is a unit test pinning it; do not weaken it without
a matching PR description and a test update.

## Running locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
playwright install chromium   # one-time, only if you want UI tests
pytest                        # default: runs unit + api
```

## Coverage target

* **Today:** 40 % (enforced in CI via `--cov-fail-under=40`).
* **90-day target:** 60 %.
* **Long-term:** 75 %.

Raise the threshold in `.github/workflows/ci.yml` whenever you add a
feature that lifts coverage — never lower it.

