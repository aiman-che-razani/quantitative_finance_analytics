# Axiom v1 architecture

Daily providers -> strict quality validation -> immutable Parquet versions -> shared causal features -> strategy events -> risk decisions -> execution -> one auditable multiasset portfolio -> analytics. PostgreSQL stores instrument metadata, version lineage, experiment configuration/results and paper-account checkpoints. FastAPI exposes bounded research jobs; a Next.js server proxy keeps backend credentials out of browsers. The personal portfolio embeds an exported, explicitly precomputed Axiom report and links to the local interactive workspace.

The original v0.1 API remains available for reproducibility. New code lives in metadata, data/incremental, backtest/events, portfolio, risk, ml, platform and apps/dashboard. ML uses ordered train/validation/test windows with purged label horizons; predictions and trading metrics are separate. V0.6 compares Python, NumPy, Polars, Numba and a C++ kernel and measures the full 342-instrument pipeline on synthetic data. V1.0 offers closed-daily-bar polling and simulated paper execution only.

Data is explicitly synthetic or provider-sourced; no silent fallback. Current-universe research does not remove survivorship bias. Dividends, borrow fees and exchange microstructure are not inferred from daily OHLCV. Stop-limit ambiguity is handled conservatively. No live-money endpoints exist.
