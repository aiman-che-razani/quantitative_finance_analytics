# Project: Axiom — Quantitative Research & Execution Platform

I want to build a production-quality portfolio engineering project called **Axiom — Quantitative Research & Execution Platform**.

The objective is to create an end-to-end quantitative finance platform covering:

**Market Data → Ingestion → Validation → Storage → ETL → Feature Engineering → Strategy Research → Backtesting → Risk → Machine Learning → Analytics → API → Interactive Dashboard**

This is not intended to be a toy trading bot or a collection of Jupyter notebooks. Design it as a modular, testable, reproducible software platform demonstrating capabilities in:

* Python
* SQL
* data engineering
* quantitative finance
* financial time-series analysis
* statistics
* machine learning
* software architecture
* backend development
* performance engineering
* C++ or Rust optimization
* testing
* Docker
* CI/CD
* production deployment

Do not overengineer the initial implementation. Begin with a modular monolith and introduce distributed or streaming technologies only when there is a genuine technical requirement.

---

# 1. Core Technology Stack

Use primarily:

* Python 3.12+
* Polars
* Pandas where interoperability is useful
* NumPy
* SciPy
* Parquet
* PostgreSQL
* SQLAlchemy
* Pydantic
* scikit-learn
* XGBoost
* PyTorch for later experiments
* FastAPI
* Next.js
* TypeScript
* Plotly or Lightweight Charts
* pytest
* Docker / Docker Compose
* GitHub Actions

For performance engineering, progressively compare:

**Python loops → vectorized implementation → Polars → Numba → C++ or Rust**

Do NOT introduce Kafka initially.

Kafka should only be introduced later if live streaming creates a legitimate need for event streaming.

---

# 2. Market Data Layer

Build a market-data ingestion system capable of eventually handling approximately **342 instruments**.

Start with 10 instruments and progressively scale to:

10 → 50 → 100 → 342 instruments.

Support:

* OHLCV
* multiple timeframes
* instrument metadata
* market metadata
* incremental ingestion
* historical backfills
* duplicate detection
* missing-data detection
* timestamp validation
* OHLC consistency validation
* abnormal/invalid price detection
* volume validation
* stale-data detection
* market-calendar awareness
* partitioned storage

Design provider interfaces so different sources can be connected without modifying the rest of the platform.

Possible adapters may include:

* CSV
* Yahoo Finance or another accessible historical-data source
* MetaTrader 5
* future broker/exchange APIs

Create a canonical market-data schema containing at least:

instrument
timestamp
timeframe
open
high
low
close
volume
source
ingested_at

Create a separate instrument metadata model containing fields such as:

symbol
asset_class
exchange
currency
sector
industry
timezone
active_from
active_to

Use:

**Parquet for large historical time-series datasets**

and

**PostgreSQL for metadata, experiments, strategies, backtest results and operational information.**

Make ingestion idempotent.

Running the same ingestion job multiple times must not create duplicate observations.

---

# 3. Data Architecture

Implement logical data layers:

RAW
↓
CLEAN
↓
VALIDATED
↓
FEATURES

Use sensible Parquet partitioning based on characteristics such as:

asset class
timeframe
symbol
year/month

Do not create excessive small files.

Create data-quality reports showing:

* rows ingested
* duplicate rows
* missing periods
* invalid observations
* rejected records
* validation warnings
* ingestion duration

---

# 4. Feature Engine

Build a reusable feature-engineering framework.

Do NOT simply create disconnected indicator functions.

Create a generic feature interface allowing:

raw market data
→ feature definitions
→ feature pipeline
→ feature matrix

Implement initially:

* RSI
* EMA
* Bollinger Bands
* ATR
* simple returns
* logarithmic returns
* rolling volatility
* momentum
* rolling mean
* rolling standard deviation
* rolling min/max
* volume change
* distance from moving averages

Support configurable parameters.

Include an initial technical configuration containing:

RSI period = 26
EMA period = 200
Bollinger period = 200
Bollinger standard deviation = 1.19

The architecture must ensure that conventional strategies and ML models consume features generated from the SAME feature pipeline.

Prevent accidental future-data access.

---

# 5. Strategy Framework

Create an extensible strategy interface.

Strategies should receive market events/features and generate signals without directly manipulating portfolio state.

Implement progressively:

1. Buy and Hold
2. EMA crossover
3. RSI mean reversion
4. Bollinger mean reversion
5. Momentum
6. RSI + EMA + Bollinger combined strategy
7. Machine-learning strategy

Keep strategy logic separate from:

* execution
* portfolio management
* risk management
* analytics

---

# 6. Event-Driven Backtesting Engine

This is one of the most important components.

Build our own event-driven backtester instead of making Backtrader or another framework the core engine.

Architecture:

MarketEvent
→ Strategy
→ SignalEvent
→ Portfolio
→ OrderEvent
→ ExecutionHandler
→ FillEvent
→ Portfolio

Create clear domain models for:

* Instrument
* Bar
* Signal
* Order
* Fill
* Trade
* Position
* Portfolio
* Account

Support:

* BUY
* SELL
* LONG
* SHORT

Order types:

* market
* limit
* stop
* stop-limit

Model:

* commissions
* spread
* slippage
* cash constraints
* position sizing
* stop loss
* take profit
* partial fills where appropriate
* configurable execution assumptions

Ensure accounting consistency.

Cash + positions must reconcile with portfolio equity.

Write comprehensive unit tests for order processing, fills, positions and P&L.

---

# 7. Risk Engine

Build risk management as a separate subsystem.

Support:

## Position risk

* position size
* concentration
* leverage
* risk per trade

## Portfolio risk

* volatility
* correlations
* beta
* Value at Risk
* Conditional Value at Risk
* portfolio exposure

## Trading risk

* maximum drawdown
* stop loss
* maximum exposure
* daily loss limits
* portfolio loss limits

Allow the risk engine to:

APPROVE
MODIFY
REJECT

an order.

Record the reason for every risk decision.

---

# 8. Portfolio Accounting

Track:

* cash
* realized P&L
* unrealized P&L
* positions
* average entry price
* transaction costs
* portfolio equity
* leverage
* gross exposure
* net exposure

Maintain an auditable transaction ledger.

The same sequence of events should always reproduce the same portfolio state.

---

# 9. Analytics Engine

Calculate at minimum:

* Total Return
* Annualized Return
* CAGR
* Annualized Volatility
* Sharpe Ratio
* Sortino Ratio
* Calmar Ratio
* Maximum Drawdown
* Average Drawdown
* Drawdown Duration
* Win Rate
* Loss Rate
* Average Winner
* Average Loser
* Profit Factor
* Expectancy
* Turnover
* Exposure
* Number of Trades
* Average Holding Period

Generate data for:

* equity curve
* benchmark comparison
* drawdown/underwater chart
* rolling Sharpe
* rolling volatility
* monthly returns
* return distribution
* trade P&L distribution
* exposure over time

Create reusable analytics functions independent of the frontend.

---

# 10. Benchmarking

Every strategy should be compared against an appropriate baseline.

At minimum support:

**Buy and Hold**

Do not present a strategy as successful merely because it produced positive returns.

Compare:

strategy return
vs benchmark return

strategy risk
vs benchmark risk

strategy drawdown
vs benchmark drawdown

risk-adjusted performance.

---

# 11. Machine-Learning Research Engine

Build ML only after the conventional research and backtesting infrastructure works correctly.

Start with:

Naive Baseline
→ Logistic Regression
→ Random Forest
→ XGBoost
→ Neural Network

Example prediction target:

**Whether the future N-period return is positive.**

Potential features include:

* RSI
* ATR
* volatility
* momentum
* EMA distance
* Bollinger position
* lagged returns
* volume changes
* rolling statistics

Implement proper financial time-series methodology.

Use:

TRAIN
→ VALIDATION
→ TEST

and later:

**walk-forward validation**

Do NOT randomly shuffle time-series observations.

Explicitly design safeguards against:

* look-ahead bias
* survivorship bias
* data leakage
* target leakage
* overfitting

Report ML metrics separately from trading metrics.

A classifier with high predictive accuracy does not automatically represent a profitable strategy.

---

# 12. Experiment Tracking

Every research/backtest run should produce a unique experiment ID.

Store:

* experiment ID
* timestamp
* strategy
* parameters
* feature configuration
* universe
* timeframe
* start date
* end date
* initial capital
* dataset version
* code/git commit where available
* execution assumptions
* performance metrics
* runtime
* experiment notes

The objective is reproducible quantitative research.

Given the same:

dataset
configuration
code version
random seed

the system should reproduce the same result.

---

# 13. Performance Engineering

Create a formal benchmark workload.

Example:

**Calculate a standard feature set and execute a strategy across 342 instruments over approximately 10 years of historical data.**

Benchmark progressively:

1. naive Python
2. vectorized NumPy/Pandas
3. Polars
4. Numba
5. C++ or Rust optimized module

Measure:

* runtime
* speedup
* throughput
* bars processed per second
* CPU utilization where practical
* peak memory usage

Do not fabricate benchmark numbers.

Record actual measurements.

Only optimize code after profiling identifies genuine bottlenecks.

---

# 14. API

Build a FastAPI backend.

Possible endpoints:

GET /instruments

GET /strategies

GET /features

POST /backtests

GET /backtests/{id}

GET /backtests/{id}/trades

GET /backtests/{id}/equity

GET /backtests/{id}/metrics

GET /experiments

GET /experiments/{id}

POST /ml/experiments

Use Pydantic request/response schemas.

Validate all user-supplied parameters.

Do not allow arbitrary remote code execution through strategy parameters.

---

# 15. Portfolio Dashboard

Build a polished web interface using:

Next.js + TypeScript

Visitors should be able to choose:

Symbol/Universe
Strategy
Date Range
Initial Capital
Strategy Parameters

Then click:

**RUN BACKTEST**

Display:

* equity curve
* benchmark
* drawdown
* trades
* positions
* performance metrics
* risk metrics
* monthly returns
* experiment information
* execution assumptions

Include a section explaining how the engine works.

The dashboard should clearly state that results are historical simulations and not investment advice.

---

# 16. Repository Architecture

Start with a modular monolith similar to:

axiom/

apps/

* api/
* dashboard/

axiom/

* data/

  * providers/
  * ingestion/
  * validation/
  * storage/
* features/
* strategies/
* backtest/
* risk/
* portfolio/
* analytics/
* ml/
* experiments/
* common/

research/

tests/

* unit/
* integration/
* regression/

benchmarks/

configs/

migrations/

docker/

docs/

pyproject.toml
docker-compose.yml
README.md

Jupyter notebooks may be used for exploratory research.

Production business logic must NOT exist exclusively inside notebooks.

---

# 17. Engineering Quality

Use:

* type hints
* docstrings
* structured logging
* configuration management
* deterministic random seeds
* clear exception handling
* dependency injection where useful
* linting
* formatting
* static type checking
* unit tests
* integration tests
* regression tests

Do not create unnecessary abstractions.

Prefer readable engineering over clever code.

Add tests whenever an important subsystem is implemented.

Financial calculations should receive particularly strong testing.

---

# 18. Docker and Deployment

Containerize:

* API
* PostgreSQL
* frontend

Use Docker Compose for local development.

Eventually deploy Axiom to a VPS.

Create separate development and production configuration.

Never commit:

* passwords
* API keys
* database credentials
* broker credentials

Use environment variables/secrets.

---

# 19. CI/CD

Use GitHub Actions for:

lint
→ type check
→ unit tests
→ integration tests
→ build

Later add deployment automation.

Do not allow deployment if tests fail.

---

# 20. Development Roadmap

Build incrementally.

## Axiom V0.1

Implement:

* repository structure
* Python environment
* 10 instruments
* daily OHLCV
* data provider abstraction
* Parquet storage
* validation
* RSI
* EMA
* Bollinger Bands
* simple strategy
* simple backtest
* basic analytics
* tests

The objective is to obtain the first complete:

**Data → Features → Strategy → Backtest → Results**

pipeline.

## Axiom V0.2

Add:

* 50+ instruments
* PostgreSQL
* metadata
* incremental ingestion
* feature framework
* experiment tracking
* dataset versioning

## Axiom V0.3

Add:

* event-driven backtester
* order management
* execution simulation
* portfolio accounting
* commissions
* slippage
* position sizing
* risk engine
* comprehensive analytics

## Axiom V0.4

Add:

* FastAPI
* Next.js dashboard
* Docker
* interactive portfolio backtesting

## Axiom V0.5

Add:

* Logistic Regression
* Random Forest
* XGBoost
* walk-forward validation
* ML experiment tracking
* leakage safeguards

## Axiom V0.6

Scale toward:

* 342 instruments
* profiling
* performance benchmarks
* Polars optimization
* Numba
* C++ or Rust acceleration

## Axiom V1.0

Only after the research platform is reliable, consider:

* live market-data ingestion
* paper trading
* execution adapters
* scheduled strategy execution
* monitoring
* alerting
* operational dashboards

Do not connect the platform to real-money automated execution during the initial development phases.

---

# 21. Documentation

Maintain technical documentation throughout development.

The README should eventually explain:

1. Problem being solved
2. Architecture
3. Technology stack
4. Data pipeline
5. Feature engine
6. Backtesting architecture
7. Risk methodology
8. ML methodology
9. Bias/leakage prevention
10. Performance benchmarks
11. Testing strategy
12. Deployment architecture
13. Screenshots
14. Limitations
15. Future improvements

Create architecture diagrams where useful.

---

# 22. Important Development Rules

Do NOT generate the entire platform in one response.

We will build Axiom iteratively.

For every development stage:

1. Explain what we are building.
2. Explain why the component exists.
3. Show its relationship to the overall architecture.
4. Propose the files/directories involved.
5. Implement production-quality code.
6. Explain important design decisions.
7. Create appropriate tests.
8. Tell me exactly how to run it.
9. Tell me what successful output should look like.
10. Stop after completing and verifying that stage.

Do not jump ahead unless necessary.

If an architectural decision will create problems later, point it out before implementing it.

When multiple approaches exist, compare them briefly and select the one most appropriate for Axiom.

Treat this as an engineering project that I need to understand and defend technically during interviews, not merely code that needs to run.

---

# FIRST TASK

Start with **Axiom V0.1**.

Before writing implementation code:

1. Refine the system architecture.
2. Define the V0.1 scope precisely.
3. Design the repository structure.
4. Define the major Python interfaces/classes.
5. Define the market-data schema.
6. Define the Parquet storage/partitioning strategy.
7. Define the testing strategy.
8. Define the initial 10-instrument universe.
9. Recommend the initial historical-data source and explain why.
10. Identify potential architectural mistakes we should avoid now.

Then present the proposed V0.1 implementation plan.

Do NOT implement later phases yet.

Once the architecture is established, begin implementing Axiom V0.1 one milestone at a time.
