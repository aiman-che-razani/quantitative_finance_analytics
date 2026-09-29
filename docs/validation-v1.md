# V1.0 validation — 2026-09-17 (Asia/Kuala_Lumpur)

## Data and research

- PostgreSQL 18 isolated native cluster, Alembic migration to revision 0001.
- 60 instruments, 165,960 synthetic daily bars, 2015–2025. First incremental extension deduplicated 1,320 overlapping bars. Repeated imports preserved the content ID.
- Full 60-instrument EMA portfolio experiment completed and persisted. Synthetic results are engineering evidence only.
- Yahoo SPY ingestion fetched and validated 502 observed daily bars for 2024–2025. No synthetic fallback.
- An explicit live-data paper tick subsequently ingested completed Yahoo bars and advanced a SPY account through 2026-09-15, reporting nine cumulative fills and no alerts (observed in a local run; no committed artifact records the fill count). The UTC execution date was September 16; current-day bars were excluded.
- [ML evidence](ml-validation.json): 15 complete purged walk-forward folds, four models, separate prediction and out-of-sample trading metrics. Input was synthetic and does not demonstrate real predictive performance.

## Scaling

[Baseline](benchmarks/baseline.json) and [optimized measurements](benchmarks/results.json) cover 342 simulated instruments and 859,788 bars. Profiled replay: 56.66 seconds to 17.05 seconds; 11,100 fills and identical reported final equity. A regression test compares complete replay outputs with and without the position-serialization optimization. Feature computation: 1.81 seconds in the final measured run; sampled process peak RSS: 1,910 MiB. Machine: Windows 11, Python 3.12.14, 16 logical CPUs.

Python, NumPy, Polars, Numba and C++ rolling kernels agreed within numerical tolerance before timing. Measurements include profiling overhead for the full pipeline and reflect ambient system load; they are not production latency guarantees. The two runs had materially different ambient load (the unchanged Python kernel ran 1.68× faster in the second run), and the pre-optimization code and its profile are not committed, so the 56.66 s → 17.05 s figure is not an isolated measure of the optimization. Synthetic floating-point values can differ in last bits between platform math libraries, so content IDs may differ across Windows/Linux even when numerical results agree.

## Automated checks

- 36 Python tests at commit 810b8e7 (more have been added since; see `docs/TESTING.md`) including live PostgreSQL transactional integration and the compiled native kernel.
- Ruff lint/format and mypy checks.
- Next.js production build and TypeScript checks for the Axiom dashboard.
- Portfolio production/static-export build on `dev`.
- Chromium: submit research, view price charts, open experiment history, create/advance paper accounts, mobile overflow checks, change saved portfolio experiments; no JavaScript page errors.
- Docker Compose: PostgreSQL health, migrations, non-root API and dashboard; 60-instrument ingestion/research inside the container; proxy research request, rejected cross-origin POST, source fingerprint persistence, idempotent paper replay and ML imports.

The only local test warnings are upstream FastAPI/Starlette HTTPX/AnyIO deprecations. No test failures are waived. GitHub Actions independently checks PostgreSQL tests, native compilation, Python static checks, the dashboard build and a Docker Compose build-and-smoke job after push. (Historical, 2026-09-17. The current workflow also runs Python 3.14, a Windows job and a Node 26 dashboard typecheck and build; see docs/TESTING.md.)

## Screenshots

- [Research](screenshots/research.png)
- [Market data](screenshots/market.png)
- [Mobile](screenshots/mobile.png)
- [Portfolio](screenshots/portfolio.png)

## Operational boundaries

Local single-user daily data and paper execution. Research requests use one process with bounded concurrency and durable status; crash recovery is an explicit maintenance command. Paper replay is deterministic and idempotent but replays the full prefix. No production portfolio deployment, external user-authentication layer or real-money execution was performed.
