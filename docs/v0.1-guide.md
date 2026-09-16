# Axiom — Quantitative Research & Execution Platform

**V0.1: a tested daily-data research pipeline.** Axiom is being built iteratively
as a modular monolith. This milestone implements Data -> Validation -> Parquet ->
Features -> Strategy -> Backtest -> Results. The full execution platform and web
dashboard are later milestones.

## Run now (Windows, this checkout)

```powershell
Set-Location 'C:\Users\nadee\Documents\quantitative_finance_analytics'
.\.venv\Scripts\python.exe -m axiom demo
```

This generates **synthetic** data for ten instruments, validates it and writes
independent strategy/buy-and-hold results under `reports/<experiment-id>/`.
Synthetic metrics are software evidence, not historical market performance.
The command prints the dataset ID, experiment ID, assumptions and per-symbol results.

## Install on another machine

Python **3.12+** is required. With [uv](https://docs.astral.sh/uv/):

```sh
uv sync --frozen --extra dev --extra yahoo
uv run axiom demo
```

`uv.lock` fixes the dependency versions. The optional Yahoo extra adds historical
data downloads. In this checkout the Python runtime and bootstrap tooling are
local and ignored by Git; `.venv` is already configured. Base runtime packages
are Polars (frames/Parquet), NumPy (numerics), Pydantic (configuration) and
exchange-calendars (market sessions). No database service is needed for V0.1.

## Historical research

```powershell
.\.venv\Scripts\python.exe -m axiom --data data/yahoo ingest --provider yahoo --start 2020-01-01 --end 2025-01-01
# Copy dataset_id from the output:
.\.venv\Scripts\python.exe -m axiom --data data/yahoo --output reports/historical research --dataset DATASET_ID --strategy ema_trend --config configs/default.json
```

End dates are exclusive. The initial universe is SPY, QQQ, IWM, DIA, EFA, EEM,
TLT, IEF, GLD and SLV. Each is a separate USD account, not a combined portfolio.
Provider failure never silently substitutes synthetic prices. Downloaded market
data remains local and ignored by Git. Review provider terms before redistribution.

**Execution assumptions:** completed-bar signal -> next session open; fractional
long/flat positions; full cash allocation; default commission 2.5 bps per side
plus adverse slippage 1 bp per side; cash earns zero; dividends excluded; splits
inside the requested Yahoo interval rejected; final positions marked, not forcibly
liquidated. Returns are **price returns**, not dividend-reinvested total returns.
Strategy and benchmark share warm-up, evaluation dates and cost settings.
Historical simulations are not investment advice or evidence of future profitability.

## What is implemented

- Provider protocol: canonical CSV, Yahoo and deterministic synthetic sources.
- Daily schema validation, market sessions, duplicate conflicts, missing/stale
  reports, numeric/OHLC checks and strict research eligibility.
- Immutable content-addressed Parquet snapshots, file hashes and raw provenance.
- Shared causal features: Wilder RSI(26), recursive EMA(200), Bollinger(200,1.19),
  simple returns and EMA distance; configurable periods.
- EMA trend, RSI reversion, combined rule and buy-and-hold signal generators.
- Next-open replay, fill/trade ledger, cash/position/P&L invariants.
- Returns, CAGR, volatility, Sharpe, drawdown, exposure and trade statistics.
- Reproducible JSON reports, equity CSVs and feature Parquet per experiment.

## Tests and checks

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check axiom tests
.\.venv\Scripts\python.exe -m ruff format --check axiom tests
.\.venv\Scripts\python.exe -m mypy axiom
```

See [verification](docs/verification.md) for measured results and limitations.

## Design and next stages

- [V0.1 architecture and plan](docs/architecture-v0.1.md)
- [Operations and file formats](docs/operations.md)
- [Execution and metric conventions](docs/methodology.md)
- [Roadmap and portfolio integration](docs/roadmap.md)

No production logic lives only in notebooks. PostgreSQL, full event/order/risk
semantics, API/Next.js dashboard, ML, 342-instrument benchmarks and native
optimization are deliberately deferred until their stages. This milestone does
not modify the existing Golden Cross Tearsheet in the personal portfolio.
