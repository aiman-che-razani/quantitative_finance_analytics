> Archived V0.1 methodology. For the current shared portfolio engine, see [V1.0 methodology](methodology-v1.md).

# Execution, features and metric conventions

## Feature causality

One FeaturePipeline serves every rule and will later serve ML. All calculations
are trailing. EMA uses alpha=2/(period+1), recursive `adjust=False`, first close
as seed and a full-period warm-up. RSI uses Wilder's initial arithmetic average
of the first period gains/losses, followed by alpha=1/period smoothing. Flat
prices yield RSI 50; only gains yield 100; only losses yield 0. Bollinger bands
use trailing mean and population standard deviation (`ddof=0`). Warm-up is null,
never filled with future values. Prefix-invariance tests prove future rows do
not alter earlier feature values.

The initial strategy is an **EMA trend filter** (close >= EMA), not an EMA-pair
crossover. RSI reversion enters at <=30 and exits at >=50. The combined rule
enters above the EMA when price is at/below the lower Bollinger band and RSI<=40;
it exits below EMA or at RSI>=60. These fixed demo rules are not optimized or
claimed profitable. The full strategy ladder remains on the roadmap.

## Execution and accounting

Only completed session t features influence the order filled at session t+1
open. There is no same-close execution. A closing signal on the last bar cannot
create an unobservable next-bar trade. Warm-up is common across strategy and
benchmark; initial equity is recorded at the immediately preceding session close.

Each symbol is an independent long/flat account. On entry:

`fill_price = open * (1 + slippage)`

`units = cash / (fill_price * (1 + commission))`

On exit:

`cash += units * open * (1 - slippage) * (1 - commission)`

Commissions and slippage are per side. There is no leverage, shorting, borrowing,
partial fill, order book, limit/stop semantics or separate spread in this slice.
Fractional units permit exact cash allocation without pretending to implement
broker lot sizes. V0.3 must add execution domain models rather than silently
extending these assumptions. Portfolio equity is cash plus close-marked holdings.
Ledger P&L must reconcile within float64 research tolerances. Open-trade P&L
includes entry commission, but no hypothetical exit commission is charged.

## Metrics

Total return is final/initial equity - 1. CAGR uses elapsed calendar years
(365.25 days); annualized volatility and Sharpe use 252 daily sessions. Sharpe
assumes zero risk-free rate and sample return standard deviation. Undefined
ratios return null, never fabricated zeros/infinities. Maximum drawdown includes
the initial capital point. Exposure is average close-marked invested fraction.
Win rate uses closed trades only. Profit factor is null when no loss denominator
exists. Transaction commission total excludes slippage, which is already in fill
prices. Dividends are excluded: all historical returns are price returns.

## Interpretation limits

A fixed present-day ETF list still has selection/survivorship bias. Data obtained
now is not a point-in-time vintage. The exchange-session calendar is a proxy;
provider OHLC values, halt behavior and action metadata require independent checks.
Results assume liquid, fully filled orders regardless of bar volume; do not scale
capital and infer real capacity. No ML, walk-forward validation or untouched
research test period is implemented in V0.1. Positive backtest results alone do
not validate a strategy. Comparing this price-only next-open engine numerically
with the older Golden Cross adjusted-close demo is not an apples-to-apples test.
