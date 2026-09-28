# Testing Axiom

This file covers how to run the checks, what the suite covers, what is only checked
against synthetic data, and which CI jobs have actually been seen to pass. It is kept
current by the test-coverage owner. Last verified: **2026-09-28**, against a working
tree based on `2dc01ae` that also had uncommitted edits. Every count below comes from a
real run. Before you repeat a claim here, run the command again. Don't take the
numbers on trust.

## 1. Running the checks

### CI-parity run (Linux/macOS, PostgreSQL available)

CI (`.github/workflows/ci.yml`, job `python`) runs these commands in this order. If
you run the same commands locally, you get the same result:

```bash
uv sync --frozen --extra dev --extra yahoo
export DATABASE_URL=postgresql+psycopg://axiom:<password>@localhost:5432/axiom
export AXIOM_TEST_DATABASE_URL="$DATABASE_URL"   # a disposable/test database
export API_TOKEN=<any string of 24+ characters>
uv run alembic upgrade head
uv run ruff check axiom tests scripts alembic
uv run ruff format --check axiom tests scripts alembic
uv run mypy axiom
uv run python scripts/build_native.py           # otherwise the native-kernel test skips
uv run pytest -q -rs                            # -rs prints the reason for every skip
```

Local runs should use `-rs`. CI's `pytest -q` doesn't print skip reasons, so a skip
there doesn't show up unless you look for it.

CI uses `axiom:test-password@localhost:5432/axiom` with API token
`ci-test-token-01234567890123456789`. Those are throwaway CI values, not secrets.

### Windows dev machine (isolated dev cluster)

The repo has its own development cluster, managed by `scripts/local_db.py`
(`POSTGRES_BIN` defaults to `C:\Program Files\PostgreSQL\18\bin`). It listens on
port 55442. Follow these steps:

1. Probe the port first: `Test-NetConnection -ComputerName 127.0.0.1 -Port 55442`.
   Don't assume whether it's running.
2. Run `.venv\Scripts\python.exe scripts\local_db.py start` only if it isn't already
   running.
3. Set `AXIOM_TEST_DATABASE_URL` to the `DATABASE_URL` from `.env` for this shell only.
   Don't print the value, and don't edit `.env`.
4. `.venv\Scripts\python.exe -m pytest -q -rs`
5. Run `scripts\local_db.py stop` only if you started it in step 2.

Running tests against the real dev database is safe. The `pg` fixture
(`tests/test_platform.py`, `def pg(tmp_path)`) opens one connection and begins an
outer transaction. It binds the session factory with
`join_transaction_mode="create_savepoint"` and rolls everything back on teardown. It
also points `Settings.data_root` at pytest's `tmp_path`, so snapshots never touch
`data/platform`. The fixture does run `Base.metadata.create_all()`, which only creates
missing tables. Still run `alembic upgrade head` so the schema is the migrated one.

### Without a database

Plain `uv run pytest -q -rs` with no `AXIOM_TEST_DATABASE_URL` is still useful. Every
`pg`-fixtured test skips with
`AXIOM_TEST_DATABASE_URL required for PostgreSQL integration`, and everything else
runs. These skips are expected locally. **In CI they never happen**, because the job
always provides a `postgres:18-alpine` service. Verified 2026-09-28 (before the
concurrent edits added more `pg` tests): `40 passed, 6 skipped`.

### Coverage

`pytest-cov` is not a declared dev dependency. Run it ad hoc:

```bash
COVERAGE_FILE=/tmp/axiom.coverage uv run --with pytest-cov pytest --cov=axiom --cov-report=term-missing -q
```

Set `COVERAGE_FILE` outside the repo. The default `.coverage` lands in the repo root
and isn't gitignored.

### Recorded results (2026-09-28, PostgreSQL 5432, native kernel built)

| Run | Result |
|---|---|
| `uv run pytest -q -rs` at `2dc01ae` + uncommitted edits (first run) | `45 passed, 2 warnings`, 0 skipped |
| Same, after concurrent edits added tests | `46 passed`, `47 passed`, then `48 passed`, 0 skipped |
| No `AXIOM_TEST_DATABASE_URL` | `40 passed, 6 skipped` (all 6 are the `pg` skip) |
| `ruff check` / `ruff format --check` / `mypy axiom` | `All checks passed!` / `61 files already formatted` / `Success: no issues found in 36 source files` |
| Coverage (`--cov=axiom`), 47-test tree | **83% total** (1417 stmts, 239 missed) |
| After adding the section 3 gap tests (same day) | `70 passed, 2 warnings`, 0 skipped; coverage ~88% in a scratch run |

The two warnings come from third-party code (`starlette.testclient` deprecations), not
from Axiom.

## 2. Test layout and data patterns

The tests are flat `tests/test_*.py` files, one per subsystem. `testpaths = ["tests"]`.

| File | Covers | Needs DB |
|---|---|---|
| `test_analytics.py` | V0.1 metrics (initial equity, null for undefined ratios) | no |
| `test_backtest.py` | V0.1 engine: next-open execution, costs, no same-close fill, marking open positions | no |
| `test_execution.py` | `Account` reversal/fees, stop/limit/stop-limit pricing, risk clipping, short leverage, all three loss circuit breakers | no |
| `test_features.py` | causality, Wilder RSI edges, Bollinger population std | no |
| `test_integration.py` | V0.1 CLI path (`ingest`/`research`) on `tmp_path`, reproducibility, missing-session rejection, provenance | no |
| `test_kernels.py` | rolling-mean backend agreement; native `.so`/`.dll` vs reference (skips if not built) | no |
| `test_validation.py` | OHLC/session/duplicate/conflict rules, snapshot idempotence and tamper detection, staging cleanup | no |
| `test_platform.py` | V0.2+ platform: partial fills, cancel-on-flat, purge math, walk-forward four models, replay serialization guard (no DB); incremental overlap merge + paper idempotency, STALE_INPUT / RISK_REJECTION / TICK_FAILED alerts, experiment provenance, API auth and input rejection (`pg`) | partly |

Data generators. Pick one on purpose:

- `SyntheticProvider` (`axiom/data/providers.py`; the `bars` fixture in
  `tests/conftest.py`). Seeded and fast. Good for feature and pipeline tests that
  don't need a dataset identity to stay stable across calls.
- `StableSyntheticProvider` (`axiom/data/stable.py`). Date-addressed: the same
  symbol and day always give the same bytes. Use it whenever a test re-ingests
  overlapping ranges (incremental merge, paper replay).

Known traps (both verified):

- **Feature warm-up.** `FeatureConfig`'s default EMA and Bollinger periods are 200, so
  `ready` first becomes true at index 199. On shorter ranges, `run_events` raises
  `ValueError("Insufficient feature warm-up")`. Any strategy, ML or paper test needs
  more than about 200 sessions. The platform tests use 2019-01-01 to 2021-01-01.
- **"Tiny" concentration doesn't always reject.** With the default capital of 100000,
  `max_concentration=1e-9` still produces an approvable `MODIFY` of about 1e-6 units,
  which is above `assess()`'s `1e-8` floor. Use `1e-15` to get a reliable `REJECT`.
  Work out `equity * max_concentration` before you trust a "should obviously reject"
  test.
- **Content-addressed datasets dedupe across providers.** If you ingest byte-identical
  bars under a different `provider_name`, you get the *existing* `DatasetRow` back,
  and its original `provider` is kept (`axiom/data/incremental.py`,
  `if db.get(DatasetRow, identity) is None`). A test that needs a second provider
  must ingest different content, for example a different date range.

## 3. What is covered, and how strongly

"Covered" means a test fails if the behaviour regresses. It doesn't mean a line
happened to execute.

- **Order execution and pricing.** Strong unit coverage in `test_execution.py`.
- **Risk engine.** Leverage, concentration, all three loss breakers, the
  `Nonpositive equity` and `Short positions disabled` rejections, and
  `risk_per_trade` stop-based sizing are covered (the last via the stop-loss exit test).
- **Event replay (`axiom/backtest/events.py`).** Partial fills, cancel-on-flat,
  serialization equivalence, and stop-loss / take-profit exits at the trigger price
  are covered. Every rule strategy's `target()` decisions are asserted
  (`test_execution.py::test_event_strategy_targets`), including the short gate.
- **Paper replay.** Idempotency, backwards-clock rejection, STALE_INPUT,
  RISK_REJECTION, TICK_FAILED, the "Previously processed bars changed" integrity
  check, `Incompatible dataset`, unknown account and today-or-later `as_of` are covered.
- **Experiments (`axiom/platform.py`).** Success, provenance and the `FAILED`
  status write are covered. `kind="ml"` through `run_experiment` is not.
- **Incremental ingest.** Overlap merge, dedupe and the `Conflicting overlap`
  rejection (head unchanged) are covered. The `would create a gap` rejection is not.
- **API (`axiom/api.py`).** Auth (including non-ASCII), request validation
  (path-traversal `dataset_id`, duplicate symbols, extra fields, non-UUID ids),
  a full experiment create/get round trip, 404s, a paper create/advance round
  trip, backwards-clock 422 and the 429 capacity gate are covered.
- **Zero coverage:** `axiom/cli.py` (the V0.1 path is tested by calling
  `ingest`/`research` directly, not through the CLI), `axiom/__main__.py`,
  `axiom/data/universe.py`, and `SimpleStrategy`'s `ema_trend`/`rsi_reversion`/
  `combined` branches (`axiom/strategies/simple.py`, 67%).
- **`scripts/*.py`** have no tests anywhere in the repo. `paper_tick.py`'s alert-merge
  logic was extracted to `axiom.paper.record_tick_failure`, which is tested.
- **Dashboard.** CI runs `npm ci`, `npm run typecheck` (added 2026-09-28) and
  `npm run build`. There are no frontend unit tests.

## 4. Synthetic-only evidence

Every dataset in the automated suite is synthetic (`SyntheticProvider`,
`StableSyntheticProvider`, or hand-built frames). No test calls the Yahoo provider or
any network source. So the suite proves mechanics: causality, accounting, risk gating,
idempotency, purge boundaries. It says nothing about real-market behaviour.
Specifically:

- The walk-forward ML test checks that the four models fit and that their metrics are
  in range. It doesn't check predictive quality. The "15 purged folds" figure in
  `docs/validation-v1.md` / `docs/ml-validation.json` is a **recorded run**, not a
  pytest assertion.
- Benchmarks (`scripts/benchmark.py`, `docs/benchmarks/`) are recorded observations
  and don't run in CI. They can't catch a performance regression.
- The data-quality rules in `test_validation.py` use injected faults on synthetic
  bars. Real-provider quirks (splits, adjusted vs unadjusted prices, late bars) are not
  exercised.

## 5. CI jobs and whether each is proven

Checked through the public GitHub Actions API on 2026-09-28
(`repos/aiman-che-razani/quantitative_finance_analytics/actions/runs`):

| Job | What it does | Observed result |
|---|---|---|
| `python` | Postgres 18 service, `alembic upgrade head`, ruff check, ruff format check, mypy, native build, `pytest -q` | **Passed** on `main` `52d6bb1` and `572094e`. **Failed** on branch `claude/zen-pasteur-qh493f` `2dc01ae` at `ruff format --check` (a long line in `tests/test_platform.py`, reformatted in the next commit). Pytest did not run in that job. |
| `dashboard` | `npm ci`, `npm run typecheck`, `npm run build` in `apps/dashboard` | Passed on all three runs (before typecheck was added). No tests. |
| `docker` | Builds images, runs `docker compose up` with ephemeral secrets, polls `/health`, runs `scripts/demo_platform.py` in the API container, polls the dashboard, tears down | **Passed** on `main` `572094e` and on `2dc01ae`. This is its first observed passes; it is no longer unverified. It is an end-to-end smoke test: it proves the stack starts and the demo runs, but it asserts nothing beyond the demo script's exit code. |

CI runs on `push` and `pull_request` with no path filters. Job logs need
authentication, so skip counts in CI aren't visible from the public API. The job
always sets `AXIOM_TEST_DATABASE_URL`, so the `pg` tests are expected to run there.
