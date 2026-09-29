# Testing Axiom

This file covers how to run the checks, what the suite covers, what is only checked
against synthetic data, and which CI jobs have actually been seen to pass. The
test-coverage owner keeps it current. Last verified: **2026-09-29**, on branch
`audit-fixes-2` at `0e88254` (tracked source and tests clean; only other docs had
uncommitted edits). Every count below comes from a real run. Before you repeat a claim
here, run the command again. Don't take the numbers on trust.

## 1. Running the checks

### CI-parity run (Linux/macOS, PostgreSQL available)

CI (`.github/workflows/ci.yml`, job `python`) runs these commands in this order, on
Python 3.12 and 3.14. If you run the same commands locally, you should get the same
result:

```bash
uv sync --frozen --extra dev --extra yahoo
export DATABASE_URL=postgresql+psycopg://axiom:<password>@localhost:5432/axiom
export AXIOM_TEST_DATABASE_URL="$DATABASE_URL"   # a disposable/test database
export API_TOKEN=<any string of 24+ characters>
uv run alembic upgrade head
uv run ruff check axiom tests scripts alembic
uv run ruff format --check axiom tests scripts alembic
uv run mypy axiom scripts
uv run python scripts/build_native.py           # otherwise the native-kernel test skips
uv run pytest -q -rs                            # -rs prints the reason for every skip
```

Use `-rs` locally. CI's `python` job runs `pytest -q` without it, so a skip there
doesn't show up unless you look for it. (The `windows` job does use `-rs`.)

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
5. Run `scripts\local_db.py stop` only if you started it in step 2, then probe again
   to confirm the port is closed.

This procedure doesn't include a migration step, on purpose. The test owner never runs
migrations. Running tests against the real dev database is still safe, because the
`pg` fixture (`tests/test_platform.py`, `def pg(tmp_path)`) does three things:

- It runs `Base.metadata.create_all()`, which creates any missing tables but never
  alters existing ones.
- It opens one connection, begins an outer transaction, binds the session factory with
  `join_transaction_mode="create_savepoint"`, and rolls everything back on teardown.
- It points `Settings.data_root` at pytest's `tmp_path`, so snapshots never touch
  `data/platform`.

The catch is schema drift. `create_all()` won't add a constraint or index that a newer
migration introduced to a table that already exists. So if the dev database is behind
`alembic upgrade head`, the tests run against the old schema. Whoever owns the database
should migrate it. The test run won't do it. CI always migrates first (see above), so
CI is where the migrated schema is proven.

### Without a database

Plain `pytest -q -rs` with no `AXIOM_TEST_DATABASE_URL` is still useful. Every
`pg`-fixtured test skips with
`AXIOM_TEST_DATABASE_URL required for PostgreSQL integration`, and everything else
runs. These skips are expected locally and in CI's `windows` job, which has no
database. CI's `python` job always provides a `postgres:18-alpine` service, so they
never happen there.

### Coverage

Neither `pytest-cov` nor `coverage` is installed in the project `.venv` (checked
2026-09-29), and `uv` isn't available on the Windows machine. Where `uv` is available:

```bash
COVERAGE_FILE=/tmp/axiom.coverage uv run --with pytest-cov pytest --cov=axiom --cov-report=term-missing -q
```

`.coverage` is gitignored (`.gitignore` line 34), but keeping the data file outside the
repo is still tidier.

**Windows workaround (stdlib `trace`, no install).** This works with the existing
`.venv`. Put `--coverdir` outside the repo, and ignore the interpreter and `.venv` by
absolute path so third-party modules stay out of the summary:

```powershell
.venv\Scripts\python.exe -m trace --count --summary --missing `
  --coverdir $env:TEMP\axiom-trace `
  --ignore-dir "$(.venv\Scripts\python.exe -c 'import sys;print(sys.base_prefix)')" `
  --ignore-dir "$PWD\.venv" `
  --module pytest -q -p no:cacheprovider tests
```

`trace` reports per-module line percentages and writes `.cover` files that mark missed
lines with `>>>>>>`. Its figures count lines differently from `coverage.py`, so don't
compare them with the pytest-cov numbers below. It's also much slower than a normal
run. Verified to work on `tests/test_backtest.py` (2026-09-29; for example,
`axiom.strategies.simple` 64%). No full-suite `trace` figure has been recorded.

### Recorded results

2026-09-29, `audit-fixes-2` `0e88254`, Windows 11, Python `.venv`, isolated dev cluster
on port 55442 (it was stopped, so I started it for the run, stopped it afterwards and
confirmed the port was closed), native kernel built:

| Run | Result |
|---|---|
| `.venv\Scripts\python.exe -m pytest -q -rs` with `AXIOM_TEST_DATABASE_URL` | `84 passed, 2 warnings in 39.76s`, 0 skipped |
| Same, with no `AXIOM_TEST_DATABASE_URL` | `69 passed, 15 skipped, 2 warnings in 12.23s`. All 15 skips are the `pg` skip in `tests/test_platform.py`. |
| `ruff check axiom tests scripts alembic` | `All checks passed!` |
| `ruff format --check axiom tests scripts alembic` | `63 files already formatted` |
| `mypy axiom scripts` | `Success: no issues found in 51 source files` |

The two warnings come from third-party code (fastapi/`starlette.testclient`
deprecations: `httpx` and `anyio.abc.BlockingPortal`), not from Axiom.

History, kept for context. These are older trees and aren't re-verified:

| Date / tree | Result |
|---|---|
| 2026-09-28, `2dc01ae` + uncommitted edits, PostgreSQL 5432 | `45` passed, then `46`, `47` and `48` as tests were added, 0 skipped. Without a DB: `40 passed, 6 skipped`. Coverage (pytest-cov, 47-test tree): 83% total (1417 statements, 239 missed). |
| 2026-09-28, after the first gap tests | `70 passed`, 0 skipped. About 88% coverage in a scratch run. |
| 2026-09-29, before `4f4d702` | `74 passed`, 0 skipped |
| 2026-09-29, `4f4d702` / `0e88254` | `84 passed` (the current row above) |

## 2. Test layout and data patterns

The tests are flat `tests/test_*.py` files, one per subsystem. `testpaths = ["tests"]`.
There are 84 test items (some tests are parametrized).

| File | Covers | Needs DB |
|---|---|---|
| `test_analytics.py` | V0.1 metrics (initial equity, null for undefined ratios) | no |
| `test_backtest.py` | V0.1 engine: next-open execution, costs, no same-close fill, marking open positions, strategy/baseline share a window | no |
| `test_execution.py` | `Account` reversal/fees, stop/limit/stop-limit pricing, risk clipping, short leverage, all three loss circuit breakers, event-strategy `target()` decisions and short gate, disabled-short / nonpositive-equity rejections | no |
| `test_features.py` | causality, Wilder RSI edges, Bollinger population std | no |
| `test_integration.py` | V0.1 path (`ingest`/`research` called directly) on `tmp_path`: reproducibility, missing-session rejection, provenance | no |
| `test_kernels.py` | rolling-mean backend agreement; native `.so`/`.dll` vs reference (skips if not built) | no |
| `test_validation.py` | OHLC/session/duplicate/conflict rules, timestamps and CSV round trip, snapshot idempotence and tamper detection, staging cleanup, corrupt-snapshot repair, fsync open mode, manifest path escape, rewritten part hashes, empty publish | no |
| `test_platform.py` | V0.2+ platform. No DB: partial fills, cancel-on-flat, purge math, walk-forward (four models), random-walk surrogate, `null_auc`, replay serialization guard, stop-loss/take-profit, volume cap. With `pg` (15 tests): incremental merge/conflict/gap, paper idempotency, alerts, experiments, API | partly |

Data generators. Pick one on purpose:

- `SyntheticProvider` (`axiom/data/providers.py`; the `bars` fixture in
  `tests/conftest.py`). Seeded and fast. Good for feature and pipeline tests that
  don't need a dataset identity to stay stable across calls.
- `StableSyntheticProvider` (`axiom/data/stable.py`). Date-addressed: the same
  symbol and day always give the same bytes. Use it whenever a test re-ingests
  overlapping ranges (incremental merge, gap rejection, paper replay).

Known traps (all verified):

- **Feature warm-up.** `FeatureConfig`'s default EMA and Bollinger periods are 200, so
  `ready` first becomes true at index 199. On shorter ranges, `run_events` raises
  `ValueError("Insufficient feature warm-up")`. Any strategy, ML or paper test needs
  more than about 200 sessions. The platform tests use 2019-01-01 to 2021-01-01, and
  the ML tests use 2015-01-01 to 2021-01-01.
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
- **OS-specific code paths.** `storage` opens files differently for `fsync` on Windows
  (`os.O_RDWR`) than on POSIX. `test_fsync_opens_files_writable_only_on_windows`
  monkeypatches `storage.os.name` so both branches run on any OS. For anything else
  that depends on the OS, write the same kind of test. Don't rely on the Linux CI job
  alone (see section 5).

## 3. What is covered, and how strongly

"Covered" means a test fails if the behaviour regresses. It doesn't mean a line
happened to execute.

- **Order execution and pricing.** Strong unit coverage in `test_execution.py`.
- **Risk engine.** Leverage, concentration, all three loss breakers, the
  `Nonpositive equity` and `Short positions disabled` rejections, and
  `risk_per_trade` stop-based sizing are covered (the last through the stop-loss exit
  test).
- **Event replay (`axiom/backtest/events.py`).** Partial fills, cancel-on-flat,
  serialization equivalence, stop-loss and take-profit exits at the trigger price, a
  take-profit not replacing a market exit at the open, and fill size capped by the
  prior bar's volume are covered. Every rule strategy's `target()` decisions are
  asserted (`test_execution.py::test_event_strategy_targets`), including the short
  gate.
- **Snapshot storage (`axiom/data/storage.py`).** Idempotent publish, tamper
  detection, staging cleanup with a concurrent publish, and repair by rewriting are
  covered. So are the fsync open mode on both OS branches
  (`test_fsync_opens_files_writable_only_on_windows`), a manifest path escaping the
  snapshot (`escapes root`), parts whose manifest hashes were rewritten to match
  (`content hash mismatch`), and publishing an empty frame (`empty`).
- **Paper replay (`axiom/paper.py`).** These are covered:
  - Idempotency and backwards-clock rejection.
  - The `STALE_INPUT`, `RISK_REJECTION` and `TICK_FAILED` alerts, and alert merging.
  - `STALE_INPUT` appearing exactly once across repeated ticks with no new bars
    (`test_paper_stale_alert_persists_on_repeat_ticks_without_new_bars`).
  - A successful tick clearing `TICK_FAILED` and `last_error`, and
    `record_tick_failure` bumping `updated_at`
    (`test_successful_repeat_tick_clears_tick_failure`).
  - The "Previously processed bars changed" integrity check and
    `Incompatible dataset`.
  - Unknown accounts, and an `as_of` of today or later.
- **Experiments (`axiom/platform.py`).** Success, provenance and the `FAILED` status
  write are covered. `run_experiment(kind="ml")` is **not**. The ML path is only tested
  by calling `walk_forward` directly.
- **Walk-forward ML.** The four models fit and their metrics are in range. The purge
  boundaries, the random-walk surrogate's shape, volatility and seed determinism, and
  `null_auc` are covered. `null_auc` checks that all four models are summarised, that
  `0 <= mean <= p95 <= 1`, and that two calls give identical results.
- **Incremental ingest.** Overlap merge, dedupe, the `Conflicting overlap` rejection
  (head unchanged) and the `would create a gap` rejection (head unchanged; the original
  range re-ingests to the same `dataset_id`) are covered.
- **API (`axiom/api.py`).** These are covered:
  - Auth, including a non-ASCII token.
  - Request validation: path-traversal `dataset_id`, duplicate symbols, extra fields,
    non-UUID ids.
  - A full experiment create/get round trip.
  - 404s for a missing experiment, market data for an unknown symbol, and an unknown
    paper account on `/advance` (now `UnknownPaperAccount`).
  - 422 for `strategy: "ml"` on `/experiments` and on `/paper`, for `kind: "ml"` on
    `/paper`, and for a symbol that isn't in the dataset.
  - A paper create/advance round trip, and paper feature overrides being stored.
  - **409** for a backwards clock (`PaperConflict`, `axiom/api.py`). An older version
    of this file said 422, which was wrong.
  - The 429 capacity gate.
  - The `/datasets`, `/experiments`, `/paper` and `/market` list endpoints returning
    recorded rows. `/experiments` leaves out `result`, `/market` returns between 1 and
    3000 bars with OHLCV fields, and `/strategies` doesn't list `ml`.

  `/instruments` is only checked for a 200 response.
- **Gaps (no regression-catching test):**
  - `SimpleStrategy` (`axiom/strategies/simple.py`, the V0.1 vectorized strategy).
    `rsi_reversion` and `combined` are never run. `ema_trend` (the default) and
    `buy_hold` are run by `test_strategy_and_baseline_share_window`, but only the
    shared window is asserted, not the signals. (`test_event_strategy_targets` tests
    the *event-replay* `target()`, which is a different function.)
  - `run_experiment(kind="ml")` and its `Unknown experiment kind` branch.
  - `axiom/cli.py` and `axiom/__main__.py`. The V0.1 path is tested by calling
    `ingest`/`research` directly, not through the CLI.
  - `axiom/data/universe.py`.
  - The native-kernel missing-library 422 (a `4f4d702` change) has no test.
  - `scripts/*.py`. Nothing in the repo tests them. That includes
    `scripts/prune_snapshots.py`, whose new safety guards (refuse `--delete` with no
    dataset rows unless `--force`, and `--min-age-minutes`) are untested even though
    it deletes data. `paper_tick.py`'s alert-merge logic was extracted to
    `axiom.paper.record_tick_failure`, which is tested.
- **Dashboard.** CI runs `npm ci`, `npm run typecheck` and `npm run build` on Node 26.
  There are no frontend unit tests.

## 4. Synthetic-only evidence

Every dataset in the automated suite is synthetic (`SyntheticProvider`,
`StableSyntheticProvider`, or hand-built frames). No test calls the Yahoo provider or
any network source. So the suite proves mechanics: causality, accounting, risk gating,
idempotency, purge boundaries, snapshot integrity. It says nothing about how anything
behaves on real market data. Specifically:

- The walk-forward ML and `null_auc` tests check that the models fit, that the metrics
  are in range and that runs are deterministic. They don't check predictive quality.
  The "15 purged folds" figure in `docs/validation-v1.md` / `docs/ml-validation.json`
  is a **recorded run**, not a pytest assertion.
- Benchmarks (`scripts/benchmark.py`, `docs/benchmarks/`) are recorded observations
  and don't run in CI. They can't catch a performance regression.
- The data-quality rules in `test_validation.py` use injected faults on synthetic
  bars. Real-provider quirks (splits, adjusted vs unadjusted prices, late bars) aren't
  tested.

## 5. CI jobs and whether each is proven

Checked through the public GitHub Actions API on 2026-09-29
(`https://api.github.com/repos/aiman-che-razani/quantitative_finance_analytics/actions/runs`,
plus `.../runs/<id>/jobs`). There are 24 runs in total.

**Branch `audit-fixes-2`.** `?branch=audit-fixes-2` returned `total_count` 2, both
`push` events, both `completed` / `success`. These are the first observed runs of the
new matrix, `windows` job and Node 26 dashboard:

| Run | Commit | Created → updated (UTC) | Jobs (all `completed` / `success`) |
|---|---|---|---|
| 36515900426 | `4f4d702` | 03:09:36 → 03:10:57 | `python (3.12)`, `python (3.14)`, `windows`, `dashboard`, `docker` |
| 36515956881 | `0e88254` | 03:10:21 → 03:11:43 | `python (3.12)`, `python (3.14)`, `windows`, `dashboard`, `docker` |

In both runs, every checked step reported `success`: ruff check, ruff format check,
mypy and `pytest -q` in both `python` legs; `pytest -q -rs` in `windows`; `npm ci`,
`npm run typecheck` and `npm run build` in `dashboard`; and `demo_platform.py` in
`docker`.

| Job | What it does | Observed result |
|---|---|---|
| `python` (matrix 3.12, 3.14) | Postgres 18 service (digest-pinned), `alembic upgrade head`, ruff check, ruff format check, `mypy axiom scripts`, native build, `pytest -q` | **Both legs passed** on `4f4d702` and `0e88254`. Before that, it was single-version and **Linux-only**. That version passed on `main` `52d6bb1`, `572094e`, `f4cde5b`, `e7f2085`, `83952d9` and `af2fd75`, and on `claude/zen-pasteur-qh493f` `b83f53d`, `2c0d611`, `53ed9bf` and `a451390`. It **failed** on `2dc01ae` at `ruff format --check`; pytest didn't run in that job. |
| `windows` (new) | `windows-latest`, Python 3.12, `uv sync --frozen --extra dev`, `pytest -q -rs`. No PostgreSQL, so the 15 `pg` tests are expected to skip. The native kernel isn't built, so that test is expected to skip as well. | **Passed** on `4f4d702` and `0e88254`. The job logs need authentication, so the actual pass/skip counts haven't been seen. |
| `dashboard` | Node 26: `npm ci`, `npm run typecheck`, `npm run build` in `apps/dashboard` | Passed on both `audit-fixes-2` runs (first observed on Node 26). Earlier runs used Node 22. No tests. |
| `docker` | Builds images, runs `docker compose up` with ephemeral secrets, polls `/health`, runs `scripts/demo_platform.py` in the API container, polls the dashboard, tears down | Passed on both `audit-fixes-2` runs, and earlier on `main` `572094e` and on `2dc01ae`. It's an end-to-end smoke test. It proves the stack starts and the demo runs, but it asserts nothing beyond the demo script's exit code. |

**Why the Windows job exists: the fsync incident.** Until `4f4d702`, every CI run was
Linux-only. Snapshot publishing called `os.fsync` on files opened read-only. POSIX
allows that, but Windows (`_commit`) rejects it with `EBADF`, so publishing snapshots failed on the Windows dev
machine while every Linux CI run stayed green. `e7f2085` ("Open files writable for
fsync on Windows") fixed it. The fix is now pinned down by
`test_fsync_opens_files_writable_only_on_windows`, which runs both branches on any OS,
and by the `windows` job itself. The lesson: a green Linux run proved nothing about
Windows.

All actions are pinned to commit SHAs, and the workflow token is `contents: read`. CI
runs on `push` and `pull_request` with no path filters. Job logs need authentication,
so skip counts in CI can't be seen through the public API. The `python` job always sets
`AXIOM_TEST_DATABASE_URL`, so the `pg` tests are expected to run there.
