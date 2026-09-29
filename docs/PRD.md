# Axiom — Product Requirements Document

Status: living document. Owner: `prd` agent. Last verified: 2026-09-28 against `README.md`, `docs/roadmap.md`, `docs/benchmarks/results.json`, `docs/validation-v1.md`, `docs/verification-evidence.json`, the CI workflow, and the `axiom/` source tree. Every measured number below is re-derived from those files at verification time, not carried over from a prior draft.

## 1. Problem & user

Axiom is a local, single-user research workspace for one solo quant/engineer (Aiman) who wants reproducible daily-bar research, backtesting and paper-tracking on his own machine, plus a legible, honestly-labeled artifact he can show on his portfolio site without exposing a live backend or a private API token. It is not a multiuser product, not a broker, and not a hosted service (README.md:1-3, :132, :152; `docs/roadmap.md:19`).

## 2. Goals / non-goals

**Goals**
- Deterministic, auditable daily-bar research: ingest → validate → snapshot → feature → backtest/ML → risk-checked orders → ledger → analytics → durable experiment record (README.md "Architecture" diagram, lines 58-72).
- Two coexisting generations: the filesystem-only V0.1 CLI (`axiom/cli.py` → `axiom/research.py`, documented in `docs/v0.1-guide.md`) stays available alongside the PostgreSQL-backed V0.2+ platform; any new proposal must say which generation it targets (README.md:3; `docs/architecture-v1.md:5`).
- A portfolio-safe public showcase: `docs/showcase.json`, produced by `scripts/export_showcase.py`, lets the `personalportfolio` `dev` route show precomputed, provenance-stamped, explicitly synthetic-vs-observed results without a private API token, while the interactive workspace stays on `127.0.0.1:8821` (README.md:150-152). Verified: `docs/showcase.json` exists and its first record carries `provenance.dataset_id`, `code_commit`, `code_tree_sha256`, `working_tree_dirty`, and `provenance.provider: "yahoo"`.

**Non-goals (V1.0, verbatim from README.md:16, :54, :106, :132, :156)**
- Exchange connectivity, real-money execution, tick-level simulation, a publicly authenticated multiuser service.
- Point-in-time universe membership, total-return adjustment, borrow/financing/margin/taxes, real order routing.
- Daily US ETF price data only — no tick/quote feed.
- Public deployment without a real auth layer, TLS, quotas, backups (Docker Compose binds only to `127.0.0.1`, verified in `compose.yaml:27,42`).

New non-goals should be appended here with a reason, never silently removed.

## 3. Capability status table

Statuses: **CI** = implemented and covered by the automated suite (`.github/workflows/ci.yml`, verified: `postgres:18-alpine` service container + `ruff check` + `ruff format --check` + `mypy axiom scripts` + `scripts/build_native.py` + `pytest -q` in the `python` job; a separate `dashboard` job runs `npm run typecheck` and `npm run build`; a `docker` job builds and smoke-tests Compose). **Synthetic-only** = implemented and exercised, but the only measured evidence is synthetic data. **Manual/undertested** = implemented but not exercised by `pytest -q`; evidence is a hand-run checklist in `docs/validation-v1.md` or absent from the repo entirely.

| Phase | Capability | Status | Evidence |
|---|---|---|---|
| V0.2 | Incremental provider ingestion, advisory-locked overlap dedup, conflict/gap rejection | CI | `axiom/data/incremental.py` (advisory lock present); `tests/test_platform.py:87` `test_incremental_overlap_and_paper_idempotency`; `tests/test_validation.py:21` `test_exact_duplicate_and_conflict` |
| V0.2 | Immutable content-addressed Parquet snapshots, tamper detection | CI | `tests/test_validation.py:51` `test_snapshot_idempotence_and_tamper_detection` |
| V0.2 | 60-symbol universe, strict data-quality validation | CI | `tests/test_validation.py` (6 tests: calendar/holiday completeness, duplicate/conflict, bad-numeric rejection, missing/stale, snapshot integrity, timestamp/CSV roundtrip) |
| V0.2 | Causal shared feature pipeline, 3 interchangeable rolling-mean backends (Polars/Numba/C++) | CI | `axiom/features/pipeline.py`, `axiom/features/kernels.py`; `tests/test_features.py:9` `test_feature_pipeline_is_causal`; `tests/test_kernels.py` (kernel agreement + native-vs-reference) |
| V0.3 | Event-replay backtest: market/limit/stop/stop-limit orders, longs/shorts, partial fills, signed average-cost ledger | CI | `axiom/backtest/events.py` (order_type literal confirmed at line 35: `"market" \| "limit" \| "stop" \| "stop_limit"`); `tests/test_execution.py` (6 tests incl. stop-gap/limit protection, stop-limit sequencing, short leverage); `tests/test_backtest.py` (5 tests incl. next-open execution, fractional-cash costs) |
| V0.3 | Pre-trade risk checks: leverage, concentration, drawdown, daily/portfolio loss limits, position sizing | CI | `axiom/risk/engine.py:10-14` (all 5 config fields present); `max_leverage` tested (`tests/test_execution.py::test_short_leverage_reserves_commissions`), `max_concentration` tested (`::test_risk_clips_and_allows_exit_during_loss_halt`), and, as of 2026-09-28, `max_drawdown`/`daily_loss_limit`/`portfolio_loss_limit` are each independently isolated and tested (`::test_loss_circuit_breakers_reject_in_isolation`, parametrized) — see §3a. |
| V0.3 | Portfolio analytics, benchmark comparison | CI | `tests/test_analytics.py:8` `test_metrics_include_initial_equity_and_null_undefined_ratios` |
| V0.4 | FastAPI bearer-token auth + Next.js server-side proxy keeping the token out of the browser | CI + manual | Auth: `tests/test_platform.py:132` `test_api_requires_authentication`. Proxy: `apps/dashboard/app/api/[...path]/route.ts` verified to hold the token server-side, enforce a same-origin check on POST, cap body at 65536 bytes, and set `AbortSignal.timeout(300000)` (the "300s proxy timeout" cited in the brief). Not itself under `pytest`; exercised by the Chromium checklist in `docs/validation-v1.md:24`. |
| V0.4 | Durable, provenance-stamped experiments (git commit, dirty flag, sha256 of `axiom/` source tree) | CI | `axiom/platform.py:87-116` sets `code_commit`, `working_tree_dirty`, and `code_tree_sha256`, persisted on the `ExperimentRow`; asserted by `tests/test_platform.py::test_experiment_provenance_is_recorded` (2026-09-28). This row was previously miscited to `axiom/research.py:117-133`, the *separate* V0.1 CLI path's own (now also tested, see §3a #4) provenance fields — that path writes a JSON report to disk, not an `ExperimentRow`, and is not what "durable" refers to here. |
| V0.4 | Docker Compose: non-root app user, loopback-only ports | CI + manual | `Dockerfile:10-11` (`useradd --uid 10001` + `USER axiom`); `compose.yaml:27,42` (`127.0.0.1:8820:8820`, `127.0.0.1:8821:8821`), named volumes `pgdata`/`bars`/`reports`. Built and smoke-tested in CI by the `docker` job in `.github/workflows/ci.yml` (Compose up, API health, demo ingestion/research, dashboard response), plus the manual checklist in `docs/validation-v1.md:25`. |
| V0.5 | Walk-forward ML: naive, logistic, random forest, XGBoost; purged expanding train/val/test splits; OOS trading metrics kept separate from classification metrics | Synthetic-only, CI-tested | `axiom/ml/walkforward.py:10-107` confirms all four models (`DummyClassifier`, `LogisticRegression`, `RandomForestClassifier`, `XGBClassifier`). Purge-boundary logic (`tests/test_platform.py::test_horizon_purges_and_nonoverlapping_test_windows`) and, as of 2026-09-28, all four models fitting/scoring by name (`::test_walk_forward_reports_all_four_models`) are both tested — see §3a. The "15 complete purged walk-forward folds, four models" figure (`docs/validation-v1.md:10`) remains a recorded run (`docs/ml-validation.json`), not itself a pytest assertion, and is explicitly synthetic ("does not demonstrate real predictive performance"). |
| V0.6 | Measured 342-instrument × 2,514-session synthetic workload; Python/NumPy/Polars/Numba/C++ kernel timing; profiling-driven optimization | CI (kernel checks) + recorded benchmark | `docs/benchmarks/results.json`: 342 instruments, 2,514 sessions, 859,788 rows; feature stage 1.806 s; event replay 17.0475 s (README's "17.05 s" rounds this); 11,100 fills; final equity 172,505.976; peak RSS 1,910.29 MiB. Before/after replay figures (56.66 s → 17.05 s) are asserted in `docs/validation-v1.md:14`, with a regression test comparing replay output with/without the optimization: `tests/test_platform.py:152` `test_mark_serialization_optimization_preserves_replay`. |
| V1.0 | Optional Yahoo completed-daily-bar ingestion | CI + recorded | Yahoo SPY: 502 observed daily bars, 2024-2025, no synthetic fallback (`docs/validation-v1.md:8`). Separate V0.1-engine 10-instrument Yahoo backtest evidence (independent per-symbol accounts; not the V0.2+ event engine) in `docs/verification-evidence.json`: 12,580 accepted rows, 0 missing sessions, 0 rejected records, 2020-01-01 to 2025-01-01 (exclusive). |
| V1.0 | Scheduled paper ticks; persistent, row-locked, idempotent paper accounts | CI | Row lock: `axiom/paper.py:42` (`.with_for_update()`). Idempotency + backwards-rejection: `tests/test_platform.py:87-129`. Live-data tick: 9 cumulative fills, no alerts, through 2026-09-15 (`docs/validation-v1.md:9`). |
| V1.0 | `STALE_INPUT` / `RISK_REJECTION` / `TICK_FAILED` alerting, operational UI | CI | `STALE_INPUT` and `RISK_REJECTION` logic: `axiom/paper.py:80-95`, both driven and asserted by `tests/test_platform.py::test_paper_stale_input_alert` / `::test_paper_risk_rejection_alert` (2026-09-28). `TICK_FAILED`: `axiom.paper.record_tick_failure`, called from `scripts/paper_tick.py`, tested by `tests/test_platform.py::test_record_tick_failure_merges_alerts`. |

### 3a. Capabilities claimed as implemented but lacking test coverage, ranked by importance

1. **Fully fixed 2026-09-28.**
   `tests/test_platform.py::test_paper_stale_input_alert` and
   `::test_paper_risk_rejection_alert` drive a paper account into each
   state and assert the resulting `alerts` list, running against the `pg`
   fixture's isolated PostgreSQL transaction. `TICK_FAILED`'s actual logic
   — merge into existing alerts rather than clobber them on a failed
   scheduled tick — was extracted from `scripts/paper_tick.py`'s inline
   `except` block into `axiom.paper.record_tick_failure()`, so it's now
   unit-tested (`::test_record_tick_failure_merges_alerts`) without needing
   to drive the script's CLI/sleep loop itself; the script is now a thin
   wrapper that calls it and prints. The `--live-data`/`--loop`/`--interval`
   scheduling machinery around it remains untested, consistent with every
   other `scripts/` entry point in this repo (none have dedicated tests).
2. **Fixed 2026-09-28.** `tests/test_platform.py::test_walk_forward_reports_all_four_models`
   runs `walk_forward` on ~6 years of synthetic data and asserts, per fold,
   that all four models (naive/logistic/random_forest/xgboost) produce
   in-range classification metrics and a populated out-of-sample trading
   replay — so a regression in any one model's fit/predict/score wiring now
   fails a test, not just a one-off recorded run.
3. **Fixed 2026-09-28.** `tests/test_execution.py::test_loss_circuit_breakers_reject_in_isolation`
   parametrizes all three thresholds (`max_drawdown`, `daily_loss_limit`,
   `portfolio_loss_limit`), isolating each so only it can be responsible for
   the reject, plus a companion test confirming a small in-limits move is
   approved/modified rather than rejected for any reason.
4. **Fully fixed 2026-09-28.**
   `tests/test_platform.py::test_experiment_provenance_is_recorded` asserts
   `code_commit`, `code_tree_sha256`, `config` and `created_at` are all
   populated on a real `run_experiment` call (`axiom/platform.py:87-116`),
   and that the same provenance lands in the persisted `ExperimentRow`. The
   separate V0.1 CLI path's own provenance fields (`axiom/research.py:117-133`)
   are now covered too, via an extension to the existing
   `tests/test_integration.py::test_ten_instrument_research_reproducible`
   (`code_commit` checked against a live `git rev-parse HEAD`, `axiom_version`
   and `working_tree_dirty`'s type both asserted).
5. **Fixed 2026-09-28, with one caveat.** `.github/workflows/ci.yml` now has
   a `docker` job that builds the real images, brings up the full
   `docker compose` stack with ephemeral generated secrets, waits for
   `/health`, runs `scripts/demo_platform.py` against it, checks the
   dashboard responds, and tears everything down. **Caveat:** this job has
   not yet been observed to pass on an actual GitHub Actions run (or a
   local Docker daemon — none was available in the environment that wrote
   it); its command sequence was verified against `compose.yaml`,
   `Dockerfile`/`apps/dashboard/Dockerfile` and the README's own Docker
   section, but treat its first real CI run as the actual verification.

## 4. Success metrics

| Metric | How measured | Verified figure / source |
|---|---|---|
| Ingestion data-quality rejection/gap rate | `tests/test_validation.py` (duplicate/conflict, bad-numeric, missing/stale cases); Yahoo evidence shows 0 rejected records, 0 missing sessions out of 12,580 accepted rows (`docs/verification-evidence.json`) | Pass/fail per test; 0/12,580 observed |
| Snapshot hash-verification integrity | `tests/test_validation.py:51` tamper-detection test; repeated Yahoo/synthetic imports preserve content ID (`docs/validation-v1.md:6-7`) | Pass/fail |
| Backtest ledger reconciliation | Reconciliation is asserted per-scenario, not via a single named "invariant" in `docs/architecture-v1.md` (that file, read in full, has no numbered invariants — see Open Questions / brief-accuracy note in the handback). Evidence: `tests/test_execution.py` reversal/fee reconciliation, `tests/test_backtest.py:41` fractional-cash constraint, `tests/test_platform.py:38` partial-fill reconciliation, `tests/test_platform.py:152` optimization-preserves-replay | Pass/fail per test |
| Risk-decision correctness | Per-scenario tests in `tests/test_execution.py`; see §3a gap for 3 of 5 config thresholds | Partial |
| ML fold count / OOS metric stability | Recorded run only: 15 purged folds, 4 models, prediction metrics reported separately from OOS trading metrics (`docs/validation-v1.md:10`, backed by `docs/ml-validation.json`) | Recorded, not test-asserted (§3a) |
| API/proxy latency, 300 s proxy timeout | `apps/dashboard/app/api/[...path]/route.ts`: `AbortSignal.timeout(300000)` | Verified in source |
| Paper-account replay determinism (same `as_of` → same fills) | `tests/test_platform.py:123-127` (`again == state`; prefix-preserving replay) | Pass |

## 5. Requirements as user stories

1. **As a researcher, I can re-ingest an overlapping date range and get the same dataset id if the data is unchanged, or an explicit rejection if it conflicts.**
   Acceptance: `tests/test_platform.py:87` `test_incremental_overlap_and_paper_idempotency` (repeat ingest returns same `dataset_id`); `tests/test_validation.py:21` `test_exact_duplicate_and_conflict`. Implementation: `axiom/data/incremental.py`.

2. **As a researcher, I can run a backtest with any of market/limit/stop/stop-limit orders, including shorts and partial fills, and trust that the ledger reconciles.**
   Acceptance: `tests/test_execution.py` (stop/limit/stop-limit cases, short leverage), `tests/test_backtest.py` (next-open execution, fractional-cash costs), `tests/test_platform.py:38` (partial-fill reconciliation). Implementation: `axiom/backtest/events.py`.

3. **As a researcher, every order is subject to pre-trade risk checks (leverage, concentration, drawdown, daily/portfolio loss, position sizing) with no bypass path.**
   Acceptance (partial — see §3a gap): `tests/test_execution.py:32,60`. Implementation: `axiom/risk/engine.py`; single call site confirmed at `axiom/backtest/events.py:225` (`assess(...)`), and `axiom/paper.py` routes exclusively through `run_events` (`axiom/paper.py:10,87`), so no separate paper order path bypasses the risk engine.

4. **As a researcher, I can run walk-forward ML with purged splits and see out-of-sample trading metrics reported separately from classification metrics.**
   Acceptance (partial — see §3a gap): fold/purge boundaries tested at `tests/test_platform.py:58`; no per-model test. Implementation: `axiom/ml/walkforward.py`. Evidence of a full run: `docs/ml-validation.json`, summarized in `docs/validation-v1.md:10`.

5. **As a researcher, I can call the API only with a bearer token, and the browser never sees that token.**
   Acceptance: `tests/test_platform.py:132` `test_api_requires_authentication`; `apps/dashboard/app/api/[...path]/route.ts` holds `API_TOKEN` server-side only. Implementation: `axiom/api.py`.

6. **As a researcher, every experiment records enough provenance (dataset hash, code commit, dirty flag, source-tree hash) to know exactly what produced a result.**
   Acceptance (2026-09-28): `tests/test_platform.py::test_experiment_provenance_is_recorded` for the V0.4 platform path; `tests/test_integration.py::test_ten_instrument_research_reproducible` for the separate V0.1 CLI path. Implementation: `axiom/platform.py:87-116` (platform) and `axiom/research.py:117-133` (V0.1); downstream consumption verified in `docs/showcase.json`'s `provenance` block.

7. **As a researcher, I can advance a paper account's clock and get the same fills if I repeat the tick, and a rejection if I try to move it backwards.**
   Acceptance: `tests/test_platform.py:120-129`. Implementation: `axiom/paper.py` (row-locked at line 42).

8. **As a researcher, if a scheduled paper tick fails, or input goes stale, or a risk check rejects a fill, I see that reflected as an alert on the account.**
   Acceptance (2026-09-28): `tests/test_platform.py::test_paper_stale_input_alert`, `::test_paper_risk_rejection_alert`, `::test_record_tick_failure_merges_alerts`. Implementation: `axiom/paper.py:80-95` (`STALE_INPUT`, `RISK_REJECTION`) and `axiom/paper.py::record_tick_failure` (`TICK_FAILED`, extracted from `scripts/paper_tick.py`'s failure handler so the merge-not-replace alert logic is unit-testable; the script itself is now a thin wrapper calling it).

## 6. Honesty & scope requirements

- Synthetic and provider-sourced data are never silently interchanged. Verified mechanism: `docs/showcase.json`'s `provenance.provider` field (seen as `"yahoo"` in the first record) and README.md:94 ("Providers never silently substitute simulated data").
- No result in this repo is described as real trading. Verified: `axiom/paper.py:1` module docstring reads "Idempotent paper replay; never sends orders to a broker."; README.md:106 confirms "No real-money broker adapter exists."
- ML out-of-sample trading metrics and classification metrics are reported together, never substituted for each other (README.md:83, :50; `axiom/ml/walkforward.py`).
- The risk engine's pre-trade checks apply to every fill; verified single-call-site architecture in §5 story 3.
- Performance/scale claims cite `docs/benchmarks/results.json` and are labeled development-machine observations, not service guarantees (README.md:110, matching `docs/benchmarks/results.json`'s own `"method"` field text).
- The fixed 60-ETF Yahoo universe carries survivorship/selection bias, called out explicitly (README.md:41, :156; `docs/architecture-v1.md:7`).

## 7. Open questions

Carried from README.md:156 "Limitations and next improvements," none with a committed timeline:

- Total-return adjustment (dividends currently excluded — "price returns only," `docs/verification-evidence.json` `assumptions.dividends`).
- Point-in-time universe membership (current universe is fixed, not a historical constituent database — README.md:41).
- Multi-timeframe / tick-level execution (daily bars only).
- Aligned-session requirement for multi-asset portfolio replay (README.md:156: "Shared portfolio replay currently requires aligned sessions").
- ATR/RSI smoothing-method consistency: README.md:156 states ATR uses a simple rolling mean while RSI uses Wilder smoothing — an intentional but unresolved inconsistency, not a bug.
- Protective exits become active only on the bar *after* entry (README.md:156) — open question whether same-bar protection is ever wanted given the next-open execution model.

## 8. Roadmap

Cross-checked against `docs/roadmap.md:9-17` "Potential future work" — nothing below is invented independently of that list.

**Now:** all five §3a coverage gaps identified in this PRD are closed as of
2026-09-28 (paper-account alerting including `TICK_FAILED`, walk-forward
model coverage, the three risk-engine circuit breakers, V0.2+ and V0.1
provenance, and a Docker CI job — the last with the caveat noted in §3a #5
that it hasn't yet been observed passing on a real run). No further
no-scope-change coverage work is currently identified; the next PRD update
should re-audit §3 against the code before assuming this list is still
exhaustive.

**Next** (from `docs/roadmap.md:11-15`):
- Point-in-time instrument membership and corporate-action-aware total returns.
- Multiple timeframes and tick/quote-level execution models.
- Persisted event checkpoints to replace whole-prefix paper replay.

**Later** (from `docs/roadmap.md:13-17`):
- Borrow inventory, financing, margin liquidations, exchange calendars beyond US ETFs.
- A durable worker queue for asynchronous multiuser research.
- Public authentication, authorization, quotas and managed backups before any external hosting.
- Additional ML datasets and embargo-aware model selection across research campaigns.

Per `docs/roadmap.md:19`: real-money automated execution remains outside scope; the portfolio replacement lives on `dev`, and production deployment is a separate, not-yet-taken decision.
