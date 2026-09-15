# Roadmap and portfolio integration

## Current milestone: V0.1

Architecture and first complete command-line data/features/backtest pipeline.
This is the stopping point requested by the attached development brief. Verify
this stage before implementing additional infrastructure.

## Later milestones

- V0.2: PostgreSQL, instrument/experiment metadata, incremental ingestion,
  richer feature framework, 50+ instruments and transactional version tracking.
- V0.3: event-driven domain model, orders/fills, shorts, limit/stop/stop-limit,
  accounting, risk APPROVE/MODIFY/REJECT and comprehensive analytics.
- V0.4: FastAPI, Next.js/TypeScript interactive backtests, Docker and integration
  into the portfolio page at `/work/quantitative-finance-analytics/` on `dev`.
- V0.5: time-ordered ML train/validation/test, walk-forward evaluation and leakage
  safeguards; prediction metrics remain separate from trading performance.
- V0.6: scale toward 342 instruments, profile actual bottlenecks and compare
  vectorization/Polars/Numba/native implementations with measured workloads.
- V1.0: evaluate live data and paper execution only after reliable research.

The existing Golden Cross Tearsheet remains intact in `personalportfolio`.
Axiom's future dashboard should reuse its portfolio design language while making
actual executed research jobs distinct from precomputed result viewing. That
replacement is not part of this V0.1 commit. Real-money automated trading is
outside initial development scope.
