# Axiom — System Architecture

Owner: `architecture` agent (`.claude/agents/architecture.md`). Every
`path:line` citation below was re-verified against branch `audit-fixes-2` at
commit `0e88254` (2026-09-29). Re-verify citations before relying on them after
further changes.

Axiom is a **single-user, local-first quantitative research system**. V1.0 is
explicitly *not* exchange connectivity, real-money execution, tick-level
simulation, or a publicly authenticated multiuser service (`README.md:54`).

For narrative/historical detail, prose walkthroughs and setup instructions,
see the existing docs rather than duplicating them here:
`docs/architecture-v1.md`, `docs/architecture-v0.1.md`, `docs/project-brief.md`,
`docs/methodology-v1.md`, `docs/operations.md`, `docs/roadmap.md`,
`docs/v0.1-guide.md`. This file is the current, verified component map and
invariant list; those files are point-in-time references and are not rewritten
here. Decision records live in `docs/decisions/` (0001: V0.1/V0.2+ coexistence;
0002: schema constraints, paper feature persistence, corrupt-snapshot repair).

## Two coexisting generations

Axiom ships two real, independently runnable code paths. Neither is dead code
(ADR 0001).

### V0.1 (legacy, filesystem-only)

`axiom/cli.py:15` (`main`) → `axiom/research.py` (`ingest` at `research.py:24`,
`research` at `research.py:61`) → `axiom/backtest/engine.py` (`run`, imported at
`research.py:15`) + `axiom/strategies/simple.py` (`SimpleStrategy`, imported at
`research.py:21`). Reads/writes plain directories via `--data`/`--output`
(default `data/`, `reports/`; `cli.py:17-18`); no PostgreSQL. Still exercised by
`tests/test_backtest.py`, `tests/test_analytics.py` and `tests/test_integration.py`.
Documented in `docs/v0.1-guide.md`. Do not remove without an ADR.

### V0.2+ platform (current)

Package `axiom/`:

- `common/models.py` — shared pydantic config: `Instrument` (`models.py:9`), the
  10-symbol `UNIVERSE` (`models.py:23-37`), `FeatureConfig` (`models.py:40-49`,
  `extra="forbid"`, frozen), legacy `BacktestConfig` (`models.py:52`).
- `data/`
  - `providers.py` — `Provider` protocol (`providers.py:25`); `CSVProvider`
    (`:30`), `SyntheticProvider` (`:42`), `YahooProvider` (`:78`); no silent
    fallback between them.
  - `stable.py` — `StableSyntheticProvider` (`stable.py:13`): date-addressed
    synthetic bars (`source="synthetic-v2"`) so overlapping downloads are
    identical; the provider `scripts/ingest.py:28` uses for `--provider
    synthetic`.
  - `validation.py` — `validate()` (`validation.py:56-123`) → `(clean DataFrame,
    QualityReport)`.
  - `storage.py` — `SnapshotStore` (`storage.py:18-106`): content-addressed
    immutable Parquet with a completion manifest, plus module helpers
    `_part_path` (`:109-113`), `_parts_intact` (`:116-125`) and `_fsync`
    (`:128-137`). See "Snapshot publish and repair" below.
  - `incremental.py` — `ingest_incremental`: the PostgreSQL-locked merge
    (`incremental.py:18-99`).
  - `universe.py` — `UNIVERSE_60` (`universe.py:6`), `benchmark_universe`
    (`:9-12`, bounded to 1..342 simulated instruments).
- `features/pipeline.py` — `FeaturePipeline` (`pipeline.py:32`), one causal
  transform shared by rule strategies, ML, paper replay and the `/market`
  endpoint (used from `platform.py:60`, `paper.py:108`, `api.py:116`,
  `research.py:87`) + `features/kernels.py` — interchangeable rolling-mean
  backends: `python_mean` (`kernels.py:13`), `numba_mean` (`:25`),
  `numpy_mean` (`:28`), `polars_mean` (`:35`), and `native_mean` (`:39`), a
  C++ shared library via `ctypes` built by `scripts/build_native.py`.
- `backtest/orders.py` — `Order` (`orders.py:9`), `execution_price` (`:35`):
  market/limit/stop/stop-limit fill logic.
- `backtest/events.py` — `run_events` (`events.py:79-298`): the V0.3+ daily
  event replay engine; `MAX_EVENTS` (`:14`); `STRATEGIES` list (`:16-25`);
  `ExecutionConfig` (`:28-39`); signal function `target()` (`:42`).
- `backtest/engine.py` — older V0.1 engine, still used by `axiom/research.py`.
- `portfolio/account.py` — `Account` (`account.py:16`): signed positions,
  average-cost ledger, self-reconciling `mark()` (`:93-117`).
- `risk/engine.py` — `RiskConfig` (`engine.py:8`), `assess()` (`:26-72`):
  pre-trade leverage/concentration/drawdown/loss-limit checks that can
  APPROVE, MODIFY or REJECT a fill.
- `ml/walkforward.py` — `splits` (`walkforward.py:32-40`), `walk_forward`
  (`:43-172`): expanding, purged train/validation/test splits, one instrument
  at a time (`:52-53`); `random_walk_surrogate` (`:175-185`) and `null_auc`
  (`:188-212`). See "Walk-forward ML" below.
- `analytics/extended.py` — `analyze()` (`extended.py:8`): the V0.2+ metrics
  used by the platform + `analytics/metrics.py` — `summarize()`
  (`metrics.py:12`), the older V0.1 metrics used by `axiom/research.py`.
- `metadata.py` — SQLAlchemy ORM rows (`InstrumentRow`, `DatasetRow`,
  `HeadRow`, `ExperimentRow`, `PaperRow`; `metadata.py:15-72`), the
  `EXPERIMENT_STATUSES`/`EXPERIMENT_KINDS` constants (`:38-39`) and the
  `_one_of` CHECK-text builder (`:42-44`), + `database(url)`
  engine/sessionmaker factory (`:75-79`).
- `platform.py` — `run_experiment`: the durable-experiment orchestrator
  (`platform.py:23-133`).
- `paper.py` — `PaperConflict` (`paper.py:17`, → HTTP 409),
  `UnknownPaperAccount` (`:21`, → HTTP 404), `STALE_AFTER_DAYS = 4` (`:26`),
  `create_account` (`:29-48`), `advance` (`:51-135`), `record_tick_failure`
  (`:138-155`): the persistent paper-replay path.
- `api.py` — FastAPI app, `create_app()` (`api.py:52-235`); admission gate
  `threading.BoundedSemaphore(settings.max_active_runs)` (`:55`).
- `settings.py` — `Settings`, pydantic-settings from `.env` (`settings.py:7-13`;
  `max_active_runs` 1..8, default 2).

### `scripts/` (operator maintenance)

- `scripts/recover_runs.py` — marks `RUNNING` experiments older than
  `--older-than-hours` (min 1, default 24) as `INTERRUPTED`
  (`recover_runs.py:17-32`). Run only after stopping API workers.
- `scripts/prune_snapshots.py` — lists, and with `--delete` removes, every
  directory under `<data_root>/validated/` whose name is not a `datasets.id`
  (`prune_snapshots.py:30-40`): staging leftovers (`*.partial-*`), set-aside
  corrupt publishes (`*.corrupt-*`), and published snapshots whose ingest
  transaction rolled back. Dry run by default. Directories modified within
  `--min-age-minutes` (default 60) are skipped (`:34`, `:40-42`), because an
  in-flight ingest publishes its snapshot before its dataset row commits.
  `--delete` is refused when the database has **no** dataset rows at all
  unless `--force` is given (`:43-46`), so a wrong/empty `DATABASE_URL` cannot
  mark every snapshot as debris. It prints the target database host/port/name
  and data root first (`:27-28`). Raw captures under `<data_root>/raw/` are
  not touched.
- `scripts/paper_tick.py` — scheduled tick: optional `--live-data` Yahoo
  ingest (`paper_tick.py:41-56`), then `advance(..., today - 1 day, ...)`
  (`:57`); on any exception it calls `record_tick_failure` with only the
  exception type (`:74-82`), and re-raises unless `--loop`.

### `apps/dashboard/`

Next.js app router. `app/page.tsx` (945 lines) is the entire client workspace,
with tabs `Research`, `Market data`, `Experiments`, `ML research`, `Paper
accounts` (`page.tsx:430-434`). `app/api/[...path]/route.ts` (85 lines) is the
sole server-side proxy that holds the API token. In order it: rejects any
request whose `Host` hostname is not in the allow-list (`route.ts:4-9`,
`:22-23`; `AXIOM_ALLOWED_HOSTS`, default `127.0.0.1,localhost,[::1]`, a
DNS-rebinding guard → 403); restricts the path to the known route shapes
(`:26-31`, → 404); rejects a cross-origin POST whose `Origin` host differs from
`Host` (`:32-42`, → 403); returns 503 if `API_TOKEN` is unset (`:43-48`); caps
bodies at 64 KiB (`:3`, `:49-53`, → 413); and forwards to `AXIOM_API_URL`
(default `http://127.0.0.1:8820`) with a 300 s timeout (`:54-67`), mapping
upstream failure to 502 (`:75-82`).

### `alembic/`

Two migrations:

- `alembic/versions/0001_metadata.py` — the initial five tables
  (`instruments`, `datasets`, `ingestion_heads`, `experiments`,
  `paper_accounts`).
- `alembic/versions/0002_indexes_and_checks.py` — purely additive: indexes
  `ix_datasets_created_at`, `ix_datasets_parent_id`,
  `ix_experiments_created_at`, `ix_experiments_status_created_at`,
  `ix_experiments_dataset_id`, `ix_paper_accounts_updated_at`
  (`0002_indexes_and_checks.py:16-21`) and CHECK constraints
  `ck_experiments_status`/`ck_experiments_kind` with frozen literal value
  lists (`:22-27`). Upgrade precondition: existing `status`/`kind` values
  must already be in the allowed sets (`:3-4`). Rationale and the rule for
  adding a status/kind: ADR 0002.

`metadata.py` mirrors the post-0002 schema: the same index names
(`metadata.py:23`, `:25`, `:50-51`, `:58`, `:68`) and the CHECK text generated
from `EXPERIMENT_STATUSES`/`EXPERIMENT_KINDS` (`:52-53`), which renders to the
same strings the migration hard-codes. Note that the test suite builds its
schema with `Base.metadata.create_all` (`tests/test_platform.py:122`), not by
running the migrations, so model/migration parity is not test-enforced.

### `native/rolling.cpp`

An optional C++ rolling-mean kernel built by `scripts/build_native.py`; local
build artifact (`.dll`/`.so`/`.obj`/`.lib`/`.exp`), never committed
(`.gitignore:26-30`), loaded via `ctypes` from `features/kernels.py::native_mean`.

## Data flow

```
CSV / Yahoo / Synthetic / StableSynthetic providers
        │  Provider.fetch()
        ▼
data/validation.py::validate()  ──► QualityReport (rejects, not guesses)
        │  clean DataFrame
        ▼
data/incremental.py::ingest_incremental()   (PostgreSQL advisory-locked merge)
        │  data/storage.py::SnapshotStore.write()  (content-addressed Parquet;
        │                                           file first, row second)
        ▼
immutable Parquet snapshot + PostgreSQL DatasetRow/HeadRow
        │
        ▼
features/pipeline.py::FeaturePipeline.transform()   (one causal transform)
        │
        ├─► backtest/events.py::run_events()  (rule strategies, STRATEGIES)
        │        │
        │        ├─► risk/engine.py::assess()      (every fill, every bar)
        │        └─► portfolio/account.py::Account  (self-reconciling ledger)
        │
        ├─► ml/walkforward.py::walk_forward()  (purged walk-forward, then run_events with strategy "ml")
        │
        └─► analytics/extended.py::analyze()   (metrics on the equity curve)
        │
        ▼
platform.py::run_experiment()  (provenance, durable ExperimentRow)
        │
        ▼
api.py (FastAPI, token-authed)  ──►  apps/dashboard (Next.js, app/api/[...path]/route.ts proxy)

Separate path:
immutable Parquet snapshot ──► paper.py::advance()  (row-locked, append-only, whole-prefix replay
                                                     with the account's persisted FeatureConfig)
```

The V0.1 path is a parallel, simpler pipeline that never touches PostgreSQL:
`cli.py` → `research.py::ingest`/`research` → `backtest/engine.py::run` +
`strategies/simple.py::SimpleStrategy` → `analytics/metrics.py::summarize()`,
writing to plain `data/`/`reports/` directories.

## Snapshot publish and repair (`axiom/data/storage.py`)

The module docstring (`storage.py:1-5`) states the concurrency contract:
concurrent writers of the *same content* are tolerated — the first publish wins
and the others treat the published directory as their own. (It no longer
claims a single writer.)

`SnapshotStore.write` (`storage.py:29-60`):

1. Refuses an empty frame (`:30-31`). Identity = sha256 of the frame sorted by
   `(instrument, timestamp)` with `ingested_at` dropped, serialised with
   Polars `write_json()` (`:32-34`).
2. If `validated/<id>/manifest.json` exists **and** `_parts_intact` confirms
   every manifest part exists inside the snapshot and matches its recorded
   sha256 (`:35-37`), return early (idempotent write). `_parts_intact`
   resolves each part through the shared `_part_path` helper, so a manifest
   path escaping the snapshot root counts as not intact; any
   `OSError`/`ValueError`/`KeyError`/`TypeError` also counts as not intact
   (`:116-125`).
3. Otherwise the existing publish is torn or corrupted: it is renamed aside to
   `<id>.corrupt-<uuid>` for inspection (`:38-41`). If that rename raises
   `OSError` (another writer is healing the same snapshot, or on Windows a
   reader holds a file open) it is ignored and the publish race decides
   (`:42-45`).
4. Stage into `<id>.partial-<uuid>` (`:46-48`, `_stage` at `:62-89`), then
   `rename()` the stage onto `validated/<id>` (`:49`). On `OSError` the stage
   is removed and, if a manifest now exists at the target, the identity is
   returned (a concurrent writer won) (`:50-55`); any other exception removes
   the stage and re-raises (`:56-58`).

`read()` (`storage.py:91-106`) rejects a non-hex/non-64-char ID (`:92-93`),
resolves each part via `_part_path` (path-containment check, `:98`,
`:109-113`), re-verifies every part's sha256 (`:99-100`) and the whole-frame
content hash (`:102-105`) before returning data.

**Durability (`_fsync`, `storage.py:128-137`).** Each Parquet part is fsynced
after writing (`:77`), then the manifest (`:87`), then every staged directory
(`:88-89`), then the parent `validated/` directory after the publish rename
(`:59`). On Windows directories are skipped entirely (`:130-131`: Windows
cannot open a directory for fsync), so the rename itself is not made durable
there; files are opened `O_RDWR` on Windows because its `_commit` needs a
writable descriptor, and `O_RDONLY` on POSIX (`:132-133`).

**Dataset IDs are platform-dependent.** The hash is over exact serialised
values, so the same logical rows can hash differently on different OS/runtimes.
The same 165,960 synthetic-v2 rows (60 instruments, same symbols and
sessions) have content ID `8ce51d9e…` when built on Windows and `c4b279e6…`
when built on Linux (`docs/benchmarks/README.md`, the `docs/ml-validation.json`
and `docs/showcase.json` rows of the evidence table; `docs/ml-validation.json:4`
records the Linux ID). The values are not bit-identical: they differ by at
most ~1.6e-13 relative, which `docs/validation-v1.md:16` attributes to
last-bit differences between platform math libraries in the generator
(`stable.py:24-27` uses `np.exp`/`np.sin`). An ID is reproducible on one
platform, not a cross-platform identity; do not build cross-machine dedupe,
shared caches, or hard-coded IDs in tests/docs on it.

**Repair and cleanup.** The corrupt-snapshot repair is covered by
`tests/test_validation.py:96-102`. `*.corrupt-*` and `*.partial-*`
directories are never deleted automatically; `scripts/prune_snapshots.py`
(above) is the explicit cleanup path. Rationale: ADR 0002.

## Paper replay (`axiom/paper.py`)

- `create_account` (`paper.py:29-48`) persists `dataset_id`, `symbols`,
  `strategy`, the full `ExecutionConfig`, and the account's `FeatureConfig`
  (`:43`, defaults when none given). `POST /paper` accepts `features`
  (`api.py:31`, `:214`).
- `advance` (`paper.py:51-135`) replays with
  `FeatureConfig(**cfg.get("features", {}))` (`:108`): accounts created
  before features were persisted replay with the defaults, which is what
  every tick used before persistence. Error mapping in the API
  (`api.py:226-231`): `UnknownPaperAccount` → 404, `PaperConflict` → 409,
  other `ValueError` → 422.
- A successful repeat tick (same latest session) drops `STALE_INPUT` and
  `TICK_FAILED` from alerts, re-adds `STALE_INPUT` if still stale, and removes
  `last_error` (`paper.py:93-106`). A full replay writes a fresh state with no
  `TICK_FAILED`/`last_error` (`:113-132`). `RISK_REJECTION` is raised only
  for a rejection in the latest session (`:116-121`).
- `record_tick_failure` (`paper.py:138-155`) merges `TICK_FAILED` into
  existing alerts and stores a truncated `last_error` (served by `GET /paper`).

## Event replay details (`axiom/backtest/events.py`)

- Recorded events are capped at `MAX_EVENTS = 20000` (`events.py:14`,
  `:133-140`); overflow sets `events_truncated` in the result (`:295`).
  Paper replay passes `record_events=False` (`paper.py:110`).
- Fill size is capped at `participation ×` the **prior** bar's volume
  (`events.py:198-200`), because orders fill at this bar's open, before its
  full-day volume is known.
- A pending market exit decided at the prior close is not upgraded to a
  take-profit limit when the bar reaches the take-profit level
  (`events.py:216-223`); a stop hit still takes precedence (`:223-232`).

## Walk-forward ML (`axiom/ml/walkforward.py`)

- `walk_forward` also returns `pooled_test_auc` per model — ROC AUC over all
  pooled out-of-sample test rows (`walkforward.py:69-70`, `:130-131`,
  `:135-140`, `:169`). With `trade=False` it returns only `folds` and
  `pooled_test_auc` (`:141-142`).
- `random_walk_surrogate(bars, seed)` (`:175-185`) replaces one instrument's
  prices with a driftless Gaussian random walk, volatility-matched to the
  input closes, keeping bar shape and volume.
- `null_auc(bars, features, surrogates=20, seed=0, ...)` (`:188-212`) runs
  `walk_forward(trade=False)` on surrogates and reports each model's pooled
  AUC `mean` and `p95`; a real pooled AUC is only evidence of skill if it
  clears that `p95`, not 0.5 (`:193`).

## Experiment failure path (`axiom/platform.py`)

`run_experiment` catches `BaseException` (`platform.py:122`), so
`KeyboardInterrupt`/`SystemExit` also mark the row `FAILED` with
`str(exc) or type(exc).__name__` truncated to 1000 chars (`:125-130`). A
failure while marking is swallowed (`:131-132`) so it cannot mask the original
error, which is always re-raised (`:133`); a row left `RUNNING` by that case
(or by a hard process kill) is what `scripts/recover_runs.py` handles.

## Invariants — verified against code

Checked line-by-line at `0e88254`. Numbering follows the 14 invariants in
the agent brief (`.claude/agents/architecture.md`, "Invariants"); where the
brief and this section disagree, re-verify against code.

1. **Immutable, content-addressed snapshots.** `SnapshotStore.write`
   (`axiom/data/storage.py:29-60`) hashes the sorted, canonicalized frame
   (minus `ingested_at`) to a sha256 `dataset_id` (`:32-33`). It returns early
   only if the manifest exists **and** `_parts_intact` verifies every part
   (`:35-37`, `:116-125`); a torn/corrupt publish is set aside as
   `<id>.corrupt-<uuid>` (an `OSError` there is tolerated) and the same content
   republished (`:38-49`). `read()` (`:91-106`) re-verifies every part's
   sha256 (`:99-100`) and the whole-frame hash (`:102-105`), and refuses a part
   path escaping the snapshot root via `_part_path` (`:109-113`). A snapshot
   is never modified in place: repair replaces the directory with a freshly
   staged copy of content that hashes to the same ID. Confirmed.
2. **Dataset IDs are platform-dependent.** See "Dataset IDs are
   platform-dependent" above: `8ce51d9e…` (Windows) vs `c4b279e6…` (Linux)
   for the same logical synthetic-v2 rows. Confirmed against
   `docs/benchmarks/README.md` and `docs/ml-validation.json:4`.
3. **File first, pointer second.** `write()` stages to `<id>.partial-<uuid>`
   (`storage.py:46`), writes and fsyncs parts and manifest (`:62-89`), and
   only then `rename()`s it into place (`:49`), fsyncing the parent on POSIX
   (`:59`). `ingest_incremental` calls `store.write` (`incremental.py:65`)
   before adding the `DatasetRow`/head (`:84-98`) in the same transaction.
   README states this explicitly (`README.md:74`). Orphans are handled by
   `scripts/prune_snapshots.py`. Confirmed.
4. **One advisory lock per provider/universe stream.** `ingest_incremental`
   hashes `(provider_name, sorted symbols)` into a `stream` id
   (`incremental.py:41-43`) and takes `pg_advisory_xact_lock` keyed on it
   before merging (`:45`). Confirmed.
5. **Overlap must agree exactly, or the merge is rejected.** A conflicting
   overlap raises `ValueError("Conflicting overlap: publish an explicitly
   corrected dataset instead")` (`incremental.py:52-53`); a merge that would
   leave a gap or rejected record raises `ValueError("Incremental merge would
   create a gap")` (`:63-64`). Confirmed.
6. **Providers never silently substitute.** `YahooProvider.fetch` raises on
   empty data ("no fallback used", `providers.py:93-94`), on missing split
   information (`:95-96`) and on any nonzero `Stock Splits` in the window
   (`:97-98`); `scripts/ingest.py` selects the provider explicitly
   (`ingest.py:28`). Confirmed.
7. **Validation is strict and explicit.** `validate()`
   (`axiom/data/validation.py:56-123`) rejects intraday timestamps
   (`:71-72`), non-market sessions (`:73-74`), future `ingested_at`
   (`:83-84`), non-finite/non-positive prices (`:85-90`), OHLC inconsistency
   (`:91-96`), and mixed source/price-basis within one instrument snapshot
   (`:110-111`); conflicting duplicates are dropped and reported
   (`:97-101`, `:107-108`). A missing session is reported via
   `missing_periods` (`:113-115`), never imputed. Confirmed.
8. **Next-open (or later) execution only.** `first` defaults to the bar after
   the first all-`ready` bar and must have a `ready` prior bar for every
   symbol (`events.py:115-120`); the initial mark and first orders use bar
   `first - 1`'s close (`:189-193`); fills start at bar `first`'s open
   (`:194`, `:237`), and each bar's new orders are generated after its close
   (`:284-285`). Fill size is capped by the prior bar's volume ×
   participation (`:198-200`). Confirmed.
9. **Portfolio replay requires aligned sessions.** `run_events` raises
   `ValueError("Portfolio requires aligned daily sessions")` if symbols'
   timestamp vectors differ (`events.py:113-114`). Confirmed.
10. **Every fill is risk-checked before it lands in the ledger.**
    `assess()` is called for every pending order that has a price and
    nonzero size, every bar (`events.py:233-254`), before `account.fill`
    (`:262-264`); a `REJECT` drops the order (`:258-260`). A risk-reducing
    close is always approved (`risk/engine.py:42-43`). Confirmed.
11. **The ledger self-checks every mark.** `Account.mark()` raises
    `ArithmeticError("Portfolio ledger failed reconciliation")` outside
    tolerance (`portfolio/account.py:97-103`). Not caught in `events.py`.
    Confirmed.
12. **Provenance travels with every experiment.** `run_experiment` records
    `code_commit` (`GIT_COMMIT` env, overridden by `git rev-parse HEAD` when
    git is available; `platform.py:87-95`), `working_tree_dirty` (`:96-99`),
    `code_tree_sha256` over every `.py` under `axiom/` (`:100-104`),
    `dataset_id`, `provider`, the full `config` and `created_at`
    (`:105-113`), and calls `json.dumps(result, allow_nan=False)` (`:115`)
    before persisting. Any `BaseException` marks the row `FAILED`
    (`:122-133`; see "Experiment failure path"). Confirmed.
13. **Paper replay is deterministic and append-only.** `paper.advance()`
    refuses an `as_of` on or after today's UTC date (`paper.py:52-53`); takes
    `with_for_update()` (`:55`); raises `UnknownPaperAccount` (→ 404) for a
    missing account (`:56-57`); requires a replacement dataset to exist, share
    the original dataset's `provider`, and cover the account's symbols
    (`:59-68`, → 422); raises `PaperConflict` (→ 409) if the clock would move
    backwards (`:88-89`) or previously processed bars changed (content hash
    of the historical prefix, `:90-92`); returns the stored state for a
    repeated tick on the same latest session, clearing
    `TICK_FAILED`/`last_error` (`:93-106`); and replays with the account's
    persisted `FeatureConfig` (`:108`). It replays the full filtered history
    each tick (`:69-76`, `:108-111`). Confirmed.
14. **Schema and protocol changes get an ADR.** Policy, not a code
    assertion: `metadata.py`'s tables and CHECK constants, the Parquet
    snapshot manifest format (`storage.py:85`, `"version": 1`), the
    `FeatureConfig`/`ExecutionConfig`/`RiskConfig` shapes, and the V0.1/V0.2+
    split. Migration 0002, paper feature persistence and corrupt-snapshot
    repair are recorded in ADR 0002.

### Structure/benchmark facts cross-checked

- `docs/benchmarks/results.json` matches the README's "Measured scaling"
  section (`README.md:110`): 859,788 rows, 342 instruments,
  `event_replay_seconds` 17.05 (from a 56.66 s earlier run per README prose),
  `feature_seconds` 1.81, `peak_rss_mb` 1910.29. Development-machine
  observations, not guarantees. No numbers were introduced in this document.
- `README.md:85` confirms synchronous research POSTs with durable status and
  a bounded per-process admission gate; `api.py:55` implements it, and both
  `POST /experiments` and `POST /paper/{id}/advance` return 429 when it is
  full (`api.py:174-175`, `:222-223`).

## Reviewing a proposal

See this agent's brief (`.claude/agents/architecture.md`, "Reviewing a
proposal") for the standing checklist: which layer owns a change, which
invariants it touches, whether it needs a new Alembic migration or changes the
snapshot manifest (→ `database` agent), its endpoint/proxy shape (→ `api`
agent), its threat surface (→ `security` agent), and whether it fits V1.0's
stated scope or is future work (→ `prd` agent).
