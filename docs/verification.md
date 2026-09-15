# V0.1 verification — 2026-09-15

## Environment and checks

Project-local Python 3.12.14; dependency versions recorded in `uv.lock`.
Offline tests: **20 passed**. Ruff lint/format and mypy are required commit checks.
Tests cover calendar holidays, OHLC/volume errors, exact/conflicting duplicates,
stale/missing sessions, CSV parsing, snapshot idempotence/tampering, Wilder RSI,
Bollinger values, feature causality, next-open execution, costs/cash constraints,
open positions, benchmark alignment, metric conventions and ten-symbol repeatability.

## End-to-end observations

The offline synthetic workflow completed for all ten symbols. Repeated fixed-seed
runs produce the same dataset ID and numeric results; experiment UUIDs differ.
Synthetic research duration observed: 3.5910 s, excluding synthetic generation and
input capture. This is one host observation, not a 342-instrument speed benchmark.

Yahoo historical ingestion also succeeded: **12,580 rows**, 1,258 per symbol,
2020-01-01 through 2025-01-01 exclusive. No rejected rows or missing expected
sessions; no split events reported by the provider in the interval. Quality
validation does not independently establish price accuracy or point-in-time vintage.

Historical research completed in 3.5154 s after ingestion. Strategy and baseline
both used the common warm-up/evaluation window and identical costs. Full per-symbol
results and assumptions are recorded in `verification-evidence.json`; negative and
underperforming results are retained. These are price-return historical simulations,
not dividend-reinvested returns, recommendations or future-performance estimates.

Local full artifacts:
- `data/yahoo/quality/8b527396-f7b6-42e9-b1a2-9f4899696b64.json`
- `reports/historical/0456104b-b783-4db5-b9f1-6d81ee209fa7/report.json`
- Equity CSVs and ledgers beside that report.

## Issues found and resolved

- Only Python 3.9 was runnable initially; installed a project-local 3.12 runtime.
- Calendar bounds initialized on New Year's Day caused an out-of-bounds error;
  expanded internal calendar construction and kept the requested session interval.
- Schema typing needed explicit Polars dtype instances for static checking.
- An unanchored `data/` ignore pattern also excluded `axiom/data`; anchored it to
  `/data/`, so provider, validation and storage source is committed and linted.

## Acceptance and limits

V0.1 vertical slice is implemented and verified. No later-phase ML, API, Next.js,
PostgreSQL, execution adapter or portfolio page replacement is claimed complete.
Before public dashboard integration, establish data-display rights, add the next
stages' accounting/risk features and preserve the documented execution semantics.
