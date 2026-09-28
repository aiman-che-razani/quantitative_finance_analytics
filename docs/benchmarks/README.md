# Evidence ledger

Owner: `evidence` agent. This page records which public figures are backed by a
checked-in artifact, the exact field that backs each one, and when it was last
checked. It is a point-in-time audit. It does not set policy on what Axiom may
claim; that is `docs/PRD.md`.

**Last audited:** 2026-09-28, against `HEAD` = `2dc01ae`. Every figure below was
read directly from the named file and field during that audit, not copied from
another document. At audit time the working tree also had uncommitted edits by
another session, in `axiom/backtest/events.py` (`events_truncated` flag) and
`axiom/analytics/extended.py` (zero-safe benchmark returns), among other files.
Neither changes any recorded figure: the benchmark runs with
`record_events=False`, and no recorded benchmark equity is zero. Re-audit once
those edits are committed.

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
| `docs/ml-validation.json` | SYNTHETIC | `provenance.code_commit` = `810b8e7`, `working_tree_dirty` = false, `created_at` 2026-09-16T17:06:17Z | No (`axiom/ml/`, `platform.py` unchanged) | Current. A one-off recorded run: `test_walk_forward_reports_all_four_models` only checks that the models fit and score, not these numbers |
| `docs/verification-evidence.json` | OBSERVED | V0.1 CLI (`axiom/research.py`, `backtest/engine.py`), "Generated from the pre-commit working tree" (`note`), i.e. before `e7e6c96` (2026-09-15) | Additive only. `features/pipeline.py` gained non-default backends and extra columns in `810b8e7`; the default polars path used here is unchanged. | Current for V0.1. **Not** evidence for the V0.2+ event engine |
| `docs/showcase.json` | 3 OBSERVED + 3 SYNTHETIC | `scripts/export_showcase.py`; all 6 records `code_commit` `810b8e7`, **`working_tree_dirty: true`**, `created_at` 2026-09-16T17:06:19–23Z | Backtest path no; `code_tree_sha256` `2c1d1b6e…` no longer matches HEAD's Python source (`api.py`, `orders.py`, `storage.py`, `paper.py` changed in `572094e`/`2dc01ae`, none of them in the backtest arithmetic) | Numbers current; source hash stale |
| `docs/validation-v1.md` | mixed | Hand-written 2026-09-17 | See the per-line table below | Partly stale (test count, CI jobs) |
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
deterministic synthetic series the logistic model shows `trading.logistic.sharpe`
9.30, `total_return` 18.12 (+1,812%), and `win_rate` 1.0. That is expected
leakage-free fitting of an intentionally predictable synthetic pattern, **not
predictive skill** (README.md:156; methodology-v1.md:31). No public doc
currently quotes these numbers.

### Observed-price evidence (OBSERVED)

| Public figure | Where quoted | Artifact field | OK? |
|---|---|---|---|
| 10 instruments | verification.md:14 | `verification-evidence.json` `instrument_count` = 10 (DIA EEM EFA GLD IEF IWM QQQ SLV SPY TLT) | yes |
| 12,580 rows, 1,258/symbol | verification.md:19; PRD.md:42, :97 | `accepted_rows` = 12580 (= 10 × 1,258 NYSE sessions 2020–2024) | yes |
| 0 missing / 0 rejected | verification.md:20-21; PRD.md:42 | `missing_sessions` = 0, `rejected_records` = 0 | yes |
| 2020-01-01 to 2025-01-01 excl. | verification.md:20 | `download_interval` | yes |
| research 3.5154 s / synthetic 3.5910 s | verification.md:16, :24 | `historical_research_duration_s` 3.5154, `synthetic_research_duration_s` 3.5910 | yes (single observations; `note`) |
| Showcase SPY Yahoo runs | README.md:152 (via link) | `showcase.json[0..2]`, `provider` = `yahoo`, dataset `9f11067e…`, series 2024-10-16 → 2026-09-15 | provider tag present; see findings |

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
| 36 Python tests | validation-v1.md:20 | `pytest --collect-only` at `810b8e7` = 36. **HEAD `2dc01ae` = 46** |
| Chromium / Docker checklists | validation-v1.md:24-25 | Process claims; no log artifact committed |

## Open findings (2026-09-28)

Ranked by how misleading each one is. The exact replacement text is in the
evidence agent's audit report. These files are owned elsewhere and have not been
edited here.

1. `docs/showcase.json`: the three SYNTHETIC records show strategies beating
   buy-and-hold (`ema_trend` +92.96% vs `buy_hold` +45.80%; `rsi_reversion`
   Sharpe 1.90 vs 0.58). The only in-file label is the code string
   `provider: "synthetic-v2"`. There is no human-readable synthetic or bias
   disclaimer, and no top-level metadata. README.md:152's "explicitly
   identifies" holds only if the portfolio page adds the labels, and that page
   was not checkable in this environment.
2. README.md:110 "profiler evidence identifies the removed work": the backing
   `pipeline.prof` is git-ignored and absent, no baseline profile exists, and
   the untouched Python kernel was 1.68× faster in the "after" run.
3. README.md:156 "The fixed-universe Yahoo study": no recorded 60-ETF Yahoo
   study exists. The recorded Yahoo studies are the 10-ETF V0.1 run and the
   SPY-only showcase runs, and neither artifact carries the bias caveat.
4. PRD.md:42 files `verification-evidence.json` under V1.0. It is V0.1-engine evidence.
5. validation-v1.md:9 (paper tick, 9 fills) has no artifact.
6. Stale: validation-v1.md:20 (36 tests, now 46); README.md:148 and
   validation-v1.md:27 omit the Docker CI job (`.github/workflows/ci.yml:48-84`,
   added `572094e`).
7. Stale citations: PRD.md:37 (`test_platform.py:132` → `:278`), PRD.md:41
   (`:152` → `:309`), PRD.md:34 (`test_execution.py` "6 tests" → 8 functions /
   12 cases); architecture/system.md:228 attributes 56.66 s to "README prose",
   but it is `baseline.json` `event_replay_seconds`.
8. `showcase.json`: all records `working_tree_dirty: true`, and
   `code_tree_sha256` no longer matches HEAD source. No backtest-path code
   changed, so the numbers are still valid.

## How to re-audit

1. `git log --format='%h %ad' -- <artifact>` against `git log -- <code it measures>`.
   An artifact older than a behavioural change to its code is stale.
2. Re-read each field above from the file itself. Do not trust this table.
3. Never regenerate an artifact to "check" it. Report the gap to the owner of
   `scripts/benchmark.py` / `scripts/export_showcase.py` instead.
