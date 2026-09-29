# Evidence ledger

Owner: `evidence` agent. This page records which public figures are backed by a
checked-in artifact, the exact field that backs each one, and when it was last
checked. It is a point-in-time audit. It does not set policy on what Axiom may
claim; that is `docs/PRD.md`.

**Last audited:** 2026-09-29, against `HEAD` = `0e88254` (branch `audit-fixes-2`),
clean working tree. Every figure below was read directly from the named file and
field during that audit, not copied from another document. The previous audit
(2026-09-28, `2dc01ae`) was done over uncommitted edits; those have since been
committed and change no recorded figure.

## Data-kind key

| Kind | Meaning | Artifacts |
|---|---|---|
| **SYNTHETIC** | `synthetic-v2` / `StableSyntheticProvider` / `benchmark_universe` (`SIM0000`–`SIM0341`). Validates software behaviour only. Deterministic patterns, so it says nothing about predictive or trading skill. | `results.json`, `baseline.json`, `kernels.png`, `ml-validation.json`, `showcase.json` records 3–5 |
| **OBSERVED** | `yahoo` provider, real completed daily bars. Price-return only (dividends excluded). Fixed, hand-picked ETF lists, so it has **selection and survivorship bias**. | `verification-evidence.json` (10 ETFs, V0.1 engine), `showcase.json` records 0–2 (SPY only, V1.0 engine) |

No artifact records real-money trading. None exists: `axiom/paper.py` is
simulated execution only.

## Artifact inventory and freshness

| Artifact | Kind | Produced by / when | Code it depends on changed since? | Status |
|---|---|---|---|---|
| `docs/benchmarks/results.json` | SYNTHETIC | `scripts/benchmark.py`; committed in `810b8e7` (2026-09-17). The file has no commit or timestamp field of its own. | No. `axiom/backtest/events.py`, `portfolio/`, `features/`, `data/stable.py`, `data/universe.py` are unchanged since `810b8e7` (`572094e` only moved an import in `backtest/orders.py`). | Current, but not pinned to a commit |
| `docs/benchmarks/baseline.json` | SYNTHETIC | Same script, run on the **pre-optimization** engine. That engine was never committed: the first commit containing `events.py` is `810b8e7`, which is already optimized. | n/a | **Cannot be reproduced from any commit** |
| `docs/benchmarks/kernels.png` | SYNTHETIC | `scripts/benchmark.py:112-118`, from the `results.json` run. The bars visually match `results.json` `kernels.*.median_seconds`. | No | Current |
| `docs/benchmarks/pipeline.prof` | SYNTHETIC | Written by `scripts/benchmark.py:83`, but **git-ignored** (`.gitignore:33` `/docs/benchmarks/*.prof`) and **not in the repo**. Each run overwrites the same filename, so no baseline profile could have been kept beside it. | n/a | **Missing**: backs no public claim |
| `docs/ml-validation.json` | SYNTHETIC | `scripts/demo_ml.py`; `provenance.code_commit` = `856baa9`, `working_tree_dirty` = false, 2026-09-29, Linux (dataset `c4b279e6…`: the same 165,960 synthetic-v2 rows as the Windows-built `8ce51d9e…`; content IDs differ across platforms) | No | Current. Regenerated after the prior-bar volume fix; adds `pooled_test_auc`, `null_auc_reference` (20 random-walk surrogates) and a `data_note`. A one-off recorded run: tests check that models fit and score, not these numbers |
| `docs/verification-evidence.json` | OBSERVED | V0.1 CLI (`axiom/research.py`, `backtest/engine.py`), "Generated from the pre-commit working tree" (`note`), i.e. before `e7e6c96` (2026-09-15) | Additive only. `features/pipeline.py` gained non-default backends and extra columns in `810b8e7`; the default polars path used here is unchanged. | Current for V0.1. **Not** evidence for the V0.2+ event engine |
| `docs/showcase.json` | 3 OBSERVED + 3 SYNTHETIC | `scripts/export_showcase.py`, committed in `0e88254`. All six records: `provenance.code_commit` = `4f4d702`, `working_tree_dirty` = false, `created_at` 2026-09-29T03:09Z. OBSERVED records 0–2: Yahoo dataset `9f11067e…`; `metrics`, `series` and `monthly_returns` are identical to the previous (`810b8e7`, dirty) export, so the prior-bar volume cap does not bind for them. SYNTHETIC records 3–5: rebuilt from the Windows-built dataset `8ce51d9e…` (same 165,960 rows as the Linux-built `c4b279e6…`); every changed number differs by at most 1.6e-13 relative. Every record has `data_kind` and `disclaimer`. | No | Current and reproducible from a clean commit |
| `docs/validation-v1.md` | mixed | Hand-written 2026-09-17 | See the per-line table below | Partly stale (CI job list at :27) |
| `docs/verification.md` | mixed | Hand-written 2026-09-15 (V0.1) | — | Historical record; its figures reconcile |

## Verified figures

### Scaling benchmark (SYNTHETIC; Windows 11, Python 3.12.14, 16 logical CPUs; `results.json` `platform`/`python`/`cpu_logical`)

| Public figure | Where quoted | Artifact field | Raw value | OK? |
|---|---|---|---|---|
| 342 simulated instruments | README.md:51, :110; validation-v1.md:14 | `results.json` `instruments` | 342 | yes |
| 2,514 sessions | README.md:51 | `results.json` `sessions` | 2514 | yes |
| 859,788 bars/rows | README.md:110; validation-v1.md:14; `kernels.png` title | `results.json` `rows` (= 342 × 2,514) | 859788 | yes |
| ten calendar years | README.md:110 | `results.json` `start`/`end_exclusive` | 2016-01-01 / 2026-01-01 | yes |
| replay 56.66 s (before) | README.md:110; validation-v1.md:14 | `baseline.json` `event_replay_seconds` | 56.65694249999797 | yes (see caveat) |
| replay 17.05 s (after) | README.md:110; validation-v1.md:14 | `results.json` `event_replay_seconds` | 17.047534400000586 | yes (see caveat) |
| same 11,100 fills | README.md:110; validation-v1.md:14 | `fills` in both files | 11100 / 11100 | yes |
| same final equity | README.md:110; validation-v1.md:14 | `final_equity` in both files | 172505.97556883167 (identical) | yes |
| features 1.81 s | README.md:110; validation-v1.md:14 | `results.json` `feature_seconds` | 1.8060154000013426 | yes |
| peak RSS ≈ 1,910 MiB | README.md:110; validation-v1.md:14 | `results.json` `peak_rss_mb`, computed as `rss / 1024**2` (`benchmark.py:101`), so the unit really is MiB | 1910.2890625 | yes |

Caveats that belong with the before/after figures:

- **Ambient load was materially different between the two runs.** Kernels whose
  code did not change also ran faster in the "after" run: Python rolling-mean
  median 0.2836 → 0.1686 s (1.68×; `baseline.json`/`results.json`
  `kernels.python.median_seconds`), Numba cold 2.574 → 0.501 s, C++ cold
  0.0240 → 0.0039 s. The 3.3× replay gain therefore mixes the optimization with
  machine-state differences, and no committed artifact separates the two.
- The "profiler evidence" cited by README.md:110 is `pipeline.prof`. It is
  git-ignored and absent, and even the local copy can only be the "after" profile.
- `feature_seconds` and `event_replay_seconds` are **single cProfile-instrumented
  observations** (`benchmark.py:73-82`). The `method` string's "Five warm
  repetitions, median wall time" applies only to the `kernels` block.
- Behavioural equivalence of the optimization is regression-tested on a small
  fixture (`tests/test_platform.py:309`
  `test_mark_serialization_optimization_preserves_replay`, `buy_hold`,
  `event_frame()`), not on the 342-instrument workload. On that workload the
  identical `fills`/`final_equity` across both JSON files is the evidence.

### Walk-forward ML (SYNTHETIC; `ml-validation.json`, `provenance.provider` = `synthetic-v2`, SPY, `ema_trend` features)

| Public figure | Where quoted | Artifact field | OK? |
|---|---|---|---|
| 15 complete purged folds | validation-v1.md:10; PRD.md:40 | `len(folds)` = 15 | yes |
| four models | validation-v1.md:10 | `folds[*].models` keys = naive, logistic, random_forest, xgboost | yes |

**Do not quote the trading block without the SYNTHETIC label.** On this
noise-free synthetic series the logistic model shows `trading.logistic.sharpe`
9.32, `total_return` 18.12 (+1,812%), and pooled test AUC 0.993, against a
random-walk null 95th percentile of 0.546 (`null_auc_reference`). A leakage
audit (2026-09-28) confirmed train/validation/test boundaries are tight and that
random walks give Sharpe ≈ −0.1, so this is leakage-free fitting of an
intentionally predictable pattern, **not predictive skill** (README.md:156;
methodology-v1.md). No public doc currently quotes these numbers.

### Observed-price evidence (OBSERVED)

| Public figure | Where quoted | Artifact field | OK? |
|---|---|---|---|
| 10 instruments | verification.md:14 | `verification-evidence.json` `instrument_count` = 10 (DIA EEM EFA GLD IEF IWM QQQ SLV SPY TLT) | yes |
| 12,580 rows, 1,258/symbol | verification.md:19; PRD.md:42, :97 | `accepted_rows` = 12580 (= 10 × 1,258 NYSE sessions 2020–2024) | yes |
| 0 missing / 0 rejected | verification.md:20-21; PRD.md:42 | `missing_sessions` = 0, `rejected_records` = 0 | yes |
| 2020-01-01 to 2025-01-01 excl. | verification.md:20 | `download_interval` | yes |
| research 3.5154 s / synthetic 3.5910 s | verification.md:16, :24 | `historical_research_duration_s` 3.5154, `synthetic_research_duration_s` 3.5910 | yes (single observations; `note`) |
| Showcase SPY Yahoo runs | README.md:152 (via link) | `showcase.json[0..2]`, `provider` = `yahoo`, `data_kind` = `OBSERVED`, dataset `9f11067e…`, series 2024-10-16 → 2026-09-15 | yes |

`verification-evidence.json` comes from the **V0.1** engine, with one
independent account per symbol (`assumptions.accounts`). It is not evidence for
the V0.2+ event engine, risk layer, or shared portfolio. The only committed
observed-price output of the V1.0 engine is `showcase.json` records 0–2 (SPY only).

### Figures recorded in prose only (no machine-readable artifact)

These appear only in `docs/validation-v1.md` or `docs/verification.md`.
They are consistent with the session calendar and the scripts, but no committed
file records them:

| Figure | Where | Consistency check done |
|---|---|---|
| 60 instruments, 165,960 synthetic bars, 2015–2025 | validation-v1.md:6 | 60 × 2,766 sessions (2015–2025); `UNIVERSE_60` = 10 + 50 (`axiom/data/universe.py:5-6`) |
| 1,320 overlapping bars deduplicated | validation-v1.md:6 | `scripts/demo_platform.py` overlap Dec 2021 = 22 sessions × 60 |
| 502 observed Yahoo SPY bars, 2024–2025 | validation-v1.md:8; PRD.md:42 | 252 + 250 sessions |
| paper tick through 2026-09-15, 9 cumulative fills, no alerts | validation-v1.md:9 | **None possible**. The showcase Yahoo series does end 2026-09-15, which corroborates the data extent only |
| 20 V0.1 tests passed | verification.md:6 | `pytest --collect-only` at `e7e6c96` = 20 |
| 36 Python tests | validation-v1.md:20 | `pytest --collect-only` at `810b8e7` = 36 (the line says so). **HEAD `0e88254` = 84** |
| Chromium / Docker checklists | validation-v1.md:24-25 | Process claims; no log artifact committed |

## Where the ML AUC figures appear

- Every walk-forward result (`axiom/ml/walkforward.py:142`, `:169`) carries
  `pooled_test_auc`. The random-walk null (`null_auc()`) is computed only by
  `scripts/demo_ml.py:27` and recorded as `ml-validation.json`
  `null_auc_reference`. methodology-v1.md:25 now says this.
- Since `4f4d702` the dashboard's ML view shows pooled test AUC
  (`apps/dashboard/app/page.tsx:893-908`) with a caveat that it computes no null,
  so the values are not evidence of skill. No null is computed there.

## Public surfaces

- README.md:27, :148 describe the CI matrix (Python 3.12 + 3.14, Windows job,
  Node 26, Docker smoke) as *configured*. Those jobs were added in `4f4d702` on
  `audit-fixes-2` and no passing run has been observed. Say "passes" only after
  one is.
- The portfolio route `/work/quantitative-finance-analytics/` is live on
  nadeemrazani.com (README.md:152). Production (`personalportfolio` `main`)
  still serves the older showcase copy (all records `810b8e7`, dirty, no
  `data_kind`; the page falls back to labeling by `provider`). The portfolio
  `dev` branch at `d1520f6` holds a copy that parses identical to
  `docs/showcase.json` at `0e88254`, and shows each record's `disclaimer`.
  Production matches only once `dev` is promoted.

## Open findings

Resolved on 2026-09-28/29: showcase records carry `data_kind` and a disclaimer;
all six records are now exported from clean commit `4f4d702` (the
"reproducible" item is closed); README/validation-v1/PRD overclaims were
corrected; stale PRD citations were updated; the portfolio `dev` page displays
`data_kind` and the disclaimers.

Still open:

1. `baseline.json` cannot be reproduced from any commit, and `results.json` has no
   commit field. The 11,100 fills / final equity were re-checked on 2026-09-29 and are
   unchanged by the volume fix; the timings were not re-measured.
2. validation-v1.md:27 still lists the pre-`4f4d702` CI jobs and says Actions
   "independently checks" them. It should list the configured matrix and not
   imply the new jobs have passed.
3. Portfolio (`personalportfolio` `dev` `d1520f6`,
   `app/work/quantitative-finance-analytics/page.tsx:64`) says "74 tests";
   `pytest --collect-only` at `0e88254` = 84. Production is not yet promoted.

## How to re-audit

1. `git log --format='%h %ad' -- <artifact>` against `git log -- <code it measures>`.
   An artifact older than a behavioural change to its code is stale.
2. Re-read each field above from the file itself. Do not trust this table.
3. Never regenerate an artifact to "check" it. Report the gap to the owner of
   `scripts/benchmark.py` / `scripts/export_showcase.py` instead.
