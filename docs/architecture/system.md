# Axiom — System Architecture

Owner: `architecture` agent (`.claude/agents/architecture.md`). This document is
verified against the code as of the commit noted in git history for this file;
re-verify `path:line` citations before relying on them after further changes.

Axiom is a **single-user, local-first quantitative research system**. V1.0 is
explicitly *not* exchange connectivity, real-money execution, tick-level
simulation, or a publicly authenticated multiuser service (`README.md:54`).

For narrative/historical detail, prose walkthroughs and setup instructions,
see the existing docs rather than duplicating them here:
`docs/architecture-v1.md`, `docs/architecture-v0.1.md`, `docs/project-brief.md`,
`docs/methodology-v1.md`, `docs/operations.md`, `docs/roadmap.md`,
`docs/v0.1-guide.md`. This file is the current, verified component map and
invariant list; those files are point-in-time references and are not rewritten
here.

## Two coexisting generations

Axiom ships two real, independently runnable code paths. Neither is dead code.

### V0.1 (legacy, filesystem-only)

`axiom/cli.py:15` (`main`) → `axiom/research.py` (`ingest` at `research.py:24`,
`research` at `research.py:61`) → `axiom/backtest/engine.py` (`run`, imported at
`research.py:15`) + `axiom/strategies/simple.py` (`SimpleStrategy`, imported at
`research.py:21`). Reads/writes plain directories via `--data`/`--output`
(default `data/`, `reports/`; `cli.py:17-18`); no PostgreSQL. Still exercised by
`tests/test_backtest.py`, `tests/test_analytics.py` and `tests/test_integration.py`.
Documented in `docs/v0.1-guide.md`. Per this agent's brief: do not remove
without an ADR.

### V0.2+ platform (current)

Package `axiom/`:

- `common/models.py` — shared pydantic config: `Instrument` (`models.py:9`), the
  10-symbol `UNIVERSE` (`models.py:23-37`, confirmed 10 entries), `FeatureConfig`
  (`models.py:40`), legacy `BacktestConfig` (`models.py:52`).
- `data/`
  - `providers.py` — `Provider` protocol (`providers.py:25`); `CSVProvider`
    (`:30`), `SyntheticProvider` (`:42`), `YahooProvider` (`:78`); no silent
    fallback between them.
  - `validation.py` — `validate()` (`validation.py:56`) → `(clean DataFrame,
    QualityReport)`.
  - `storage.py` — `SnapshotStore`: content-addressed immutable Parquet
    (`storage.py:11-73`).
  - `incremental.py` — `ingest_incremental`: the PostgreSQL-locked merge
    (`incremental.py:18-98`).
  - `universe.py` — `UNIVERSE_60` (`universe.py:6`), `benchmark_universe`
    (`:9-12`, bounded to 1..342 simulated instruments).
- `features/pipeline.py` — `FeaturePipeline` (`pipeline.py:31`), one causal
  transform shared by rule strategies, ML and the `/market` endpoint (used from
  `platform.py:60`, `paper.py:86`, `api.py:99`) + `features/kernels.py` —
  interchangeable rolling-mean backends: `python_mean`/`numba_mean`
  (`kernels.py:12-24`), `numpy_mean` (`:27`), `polars_mean` (`:34`), and
  `native_mean` (`:38`), a C++ shared library via `ctypes` built by
  `scripts/build_native.py`.
- `backtest/orders.py` — `Order` (`orders.py:6`), `execution_price` (`:34`):
  market/limit/stop/stop-limit fill logic.
- `backtest/events.py` — `run_events` (`events.py:77`): the V0.3+ daily event
  replay engine; `STRATEGIES` list (`:14-23`); signal function `target()`
  (`:40`).
- `backtest/engine.py` — older V0.1 engine, still used by `axiom/research.py`.
- `portfolio/account.py` — `Account` (`account.py:16`): signed positions,
  average-cost ledger, self-reconciling `mark()` (`:93-117`).
- `risk/engine.py` — `RiskConfig` (`engine.py:8`), `assess()` (`:26-72`):
  pre-trade leverage/concentration/drawdown/loss-limit checks that can
  APPROVE, MODIFY or REJECT a fill.
- `ml/walkforward.py` — `walk_forward` (`walkforward.py:41`): expanding, purged
  train/validation/test splits, one instrument at a time (`:44-45`).
- `analytics/extended.py` — `analyze()` (`extended.py:6`): the V0.2+ metrics
  used by the platform + `analytics/metrics.py` — `summarize()`, the older
  V0.1 metrics used by `axiom/research.py`.
- `metadata.py` — SQLAlchemy ORM rows (`InstrumentRow`, `DatasetRow`,
  `HeadRow`, `ExperimentRow`, `PaperRow`; `metadata.py:15-55`) + `database(url)`
  engine/sessionmaker factory (`:58-62`).
- `platform.py` — `run_experiment`: the durable-experiment orchestrator
  (`platform.py:23-129`).
- `paper.py` — `create_account` (`paper.py:17`), `advance` (`:38-109`): the
  persistent paper-replay path.
- `api.py` — FastAPI app, `create_app()` (`api.py:36-208`).
- `settings.py` — `Settings`, pydantic-settings from `.env` (`settings.py:7-13`).

### `apps/dashboard/`

Next.js app router. `app/page.tsx` (749 lines) is the entire client workspace,
with tabs `Research`, `Market data`, `Experiments`, `ML research`, `Paper
accounts` (`page.tsx:339-343`). `app/api/[...path]/route.ts` (60 lines) is the
sole server-side proxy that holds the API token.

### `alembic/`

One migration so far, `alembic/versions/0001_metadata.py`, which mirrors
`metadata.py`'s `Base` tables (`instruments`, `datasets`, `ingestion_heads`,
`experiments`, `paper_accounts`) column-for-column.

### `native/rolling.cpp`

An optional C++ rolling-mean kernel built by `scripts/build_native.py`; local
build artifact (`.dll`/`.so`/`.obj`/`.lib`/`.exp`), never committed
(`.gitignore:26-30`), loaded via `ctypes` from `features/kernels.py::native_mean`.

## Data flow

```
CSV / Yahoo / Synthetic providers
        │  Provider.fetch()
        ▼
data/validation.py::validate()  ──► QualityReport (rejects, not guesses)
        │  clean DataFrame
        ▼
data/storage.py::SnapshotStore.write()   (V0.2+, content-addressed Parquet)
        │                                 data/incremental.py::ingest_incremental()
        ▼                                 (PostgreSQL advisory-locked merge)
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
immutable Parquet snapshot ──► paper.py::advance()  (row-locked, append-only, whole-prefix replay)
```

The V0.1 path is a parallel, simpler pipeline that never touches PostgreSQL:
`cli.py` → `research.py::ingest`/`research` → `backtest/engine.py::run` +
`strategies/simple.py::SimpleStrategy` → `analytics/metrics.py::summarize()`,
writing to plain `data/`/`reports/` directories.

## Invariants — verified against code

All 13 invariants in this agent's brief were checked against the current code
and **none have drifted**. Citations below were re-verified line-by-line.

1. **Immutable, content-addressed snapshots.** `SnapshotStore.write`
   (`axiom/data/storage.py:22`) hashes the sorted, canonicalized frame (minus
   `ingested_at`) to a sha256 `dataset_id` (`:25-26`); if a manifest already
   exists at that identity it returns early (`:28-29`, idempotent write).
   `read()` (`:54-73`) re-verifies every part's sha256 (`:66`) and the
   whole-frame hash (`:70-72`) before returning data, and refuses a path that
   escapes the snapshot root (`:63-65`). Confirmed, not mutable in place.
2. **File first, pointer second.** `write()` stages to
   `<hash>.partial-<uuid>` (`storage.py:30`) and only `rename()`s it into
   place after the manifest is written (`:50-51`). README states this
   explicitly (`README.md:74`): "A failed SQL transaction can leave an
   unreferenced immutable snapshot, but never a partially published dataset
   pointer." Confirmed.
3. **One advisory lock per provider/universe stream.** `ingest_incremental`
   (`axiom/data/incremental.py:41-45`) hashes `(provider_name, sorted
   symbols)` into a `stream` id and takes `pg_advisory_xact_lock` keyed on it
   before merging (`:45`). Confirmed.
4. **Overlap must agree exactly, or the merge is rejected.** A conflicting
   overlap raises `ValueError("Conflicting overlap: publish an explicitly
   corrected dataset instead")` (`incremental.py:51-52`); a merge that would
   still leave a gap or rejected record raises `ValueError("Incremental merge
   would create a gap")` (`:62-63`). Confirmed, citations exact.
5. **Providers never silently substitute.** `YahooProvider.fetch` raises if
   any `Stock Splits` value is nonzero in the window (`providers.py:97-98`,
   "V0.1 cannot account for a split inside the requested window") rather than
   adjusting or falling back; `SyntheticProvider` and `YahooProvider` are
   distinct dataclasses/classes never auto-selected for each other. Confirmed.
6. **Validation is strict and explicit.** `validate()`
   (`axiom/data/validation.py:56-123`) rejects non-market sessions (`:73-74`),
   intraday timestamps (`:71-72`), OHLC inconsistency (`:91-96`),
   non-finite/non-positive prices (`:85-90`), future `ingested_at`
   (`:83-84`), and mixed source/price-basis within one instrument snapshot
   (`:110-111`); conflicting duplicates are dropped and reported, not guessed
   at (`:97-101`, `:107-108`). A missing session is reported via
   `missing_periods` (`:113-115`), never imputed. Confirmed.
7. **Next-open (or later) execution only; no same-bar fills on the signal
   bar.** `run_events` marks/signals off bar `first - 1`'s close-derived
   `ready` features (`events.py:180-184`), then opens/fills orders starting
   at bar `first`'s `open` (`:185-187`); `first` requires the prior bar's
   features to be `ready` for every symbol (`:117`). Confirmed.
8. **Portfolio replay requires aligned sessions.** `run_events` raises
   `ValueError("Portfolio requires aligned daily sessions")` if symbols'
   timestamp vectors differ (`events.py:111-112`). Confirmed, exact citation.
9. **Every fill is risk-checked before it lands in the ledger.**
   `risk.engine.assess()` is called for every symbol with a live pending
   order on every bar (`events.py:225-236`); a closing trade that reduces
   risk is always approved (`risk/engine.py:42-43`,
   `Decision("APPROVE", units, "Risk-reducing close")`). Confirmed.
10. **The ledger self-checks every mark.** `Account.mark()` raises
    `ArithmeticError("Portfolio ledger failed reconciliation")` if
    `equity - initial != realized + unrealized - fees` outside tolerance
    (`portfolio/account.py:97-103`). Confirmed, deliberate crash-on-corruption
    invariant; not caught anywhere in `events.py`.
11. **Provenance travels with every experiment.** `run_experiment`
    (`platform.py:87-116`) records `code_commit` (`:87-100`),
    `working_tree_dirty` (`:96-100`), `code_tree_sha256` — a sha256 over every
    `.py` file under `axiom/` (`:101-105`), the full `config` and
    `created_at` (`:106-114`), and calls `json.dumps(result,
    allow_nan=False)` (`:116`) before persisting. Confirmed.
12. **Paper replay is deterministic and append-only.** `paper.advance()`
    takes `with_for_update()` (`paper.py:42`), refuses to move the clock
    backwards (`:74-75`, `"Paper clock cannot move backwards"`), refuses if
    previously processed bars changed via a content-hash check on the
    historical prefix (`:76-78`, `fingerprint()`), and returns the same
    state for a repeated tick on the same `as_of` (`:79-85`). It replays the
    full history each tick (`:55-62`, `:86-89` transform/run_events over the
    whole filtered prefix, not just the new bar). Confirmed.
13. **Schema and protocol changes get an ADR.** Policy statement, not a code
    assertion; recorded here as the standing rule for `metadata.py`'s tables,
    the Parquet snapshot manifest format (`storage.py`), the
    `FeatureConfig`/`ExecutionConfig`/`RiskConfig` shapes, and the V0.1/V0.2+
    split.

### Structure/benchmark facts cross-checked

- Benchmark numbers in `docs/benchmarks/results.json` match the README's
  "Measured scaling" section and this brief exactly: 859,788 rows, 342
  instruments, `event_replay_seconds` 17.05 (from a prior 56.66s baseline per
  README prose), `feature_seconds` 1.81, `peak_rss_mb` 1910.29. No invented
  numbers were introduced in this document.
- `README.md:85` confirms "synchronous [POSTs] with durable status records
  and a bounded per-process admission gate"; `api.py:39` implements the gate
  as `threading.BoundedSemaphore(settings.max_active_runs)`.

## Reviewing a proposal

See this agent's brief (`.claude/agents/architecture.md`, "Reviewing a
proposal") for the standing checklist: which layer owns a change, which
invariants it touches, whether it needs a new Alembic migration or changes the
snapshot manifest (→ `database` agent), its endpoint/proxy shape (→ `api`
agent), its threat surface (→ `security` agent), and whether it fits V1.0's
stated scope or is future work (→ `prd` agent).
