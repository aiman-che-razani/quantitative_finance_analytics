# Execution, analytics and research methodology

## Daily execution semantics

A close-time signal can first fill at the next session's open. Target direction changes create orders; positions are not rebalanced to fixed weights every day. Initial entries divide current portfolio equity equally across selected symbols. Exits occur before reversing on a later signal. Fractions of shares are permitted.

Market orders pay adverse slippage plus half the quoted spread. Limit orders cannot fill worse than their limit and can improve on opening gaps. Stops fill at the open after a gap or at the trigger plus adverse impact. An intrabar stop-limit trigger defers limit eligibility until the next bar because daily OHLC cannot establish the price path. An opening-gap trigger can evaluate the limit in that bar. Volume participation caps fill quantity; remaining units stay pending until filled, canceled by a changed signal, or removed by a risk modification/rejection. Protective stop-loss/take-profit orders apply to positions held before the bar. If both are touched, the stop is chosen first. These conservative rules are deterministic, not an exchange matching simulation.

Long and short positions use signed average-cost accounting. Cash changes by negative signed notional minus commission. Reversals allocate closing and opening fees proportionately. Every mark checks `equity - initial = realized gross P&L + unrealized P&L - commissions`. Trades in analytics are realized closing fills, which may be partial closes, not necessarily complete round trips. Open positions are marked to the last close instead of being forced closed.

## Risk

Risk can approve, reduce or reject requested quantity. Limits cover gross leverage, single-name concentration, drawdown from peak, daily loss from prior close, loss from initial capital, and per-entry loss budget when a stop distance is configured. New long purchases must be cash-financed; enabling gross leverage above one does not add a margin loan facility. Shorts require explicit permission. Closing exposure is permitted during a loss halt. Fee reserves reduce available exposure. Limits constrain orders when assessed, not subsequent market moves; there is no forced margin liquidation. Allocation and fill ordering are deterministic in sorted-symbol order.

## Metrics

Returns are portfolio-equity percentage changes. Annualized mean and volatility use 252 sessions; CAGR uses actual elapsed calendar time. Sharpe assumes a zero risk-free rate. Sortino uses root-mean-square negative daily returns. Calmar divides CAGR by absolute maximum drawdown. Drawdown duration counts bars below the running peak, including an unfinished episode. Historical 95% VaR and CVaR use the empirical left return tail; they are summaries, not forward loss guarantees. Turnover is gross traded notional divided by mean equity; exposure is mean gross exposure/equity. Undefined metrics are JSON null, never infinity.

Monthly returns compound equity returns. Rolling metrics use up to 63 trailing observations and disclose short initial windows. Beta and correlation compare aligned strategy and buy-and-hold returns. The benchmark uses the same shared account, initial window, execution costs and configured risk limits. A non-market configured entry order also applies to the benchmark, so it is an implementation comparison rather than a frictionless index. Asset correlations use pairwise aligned feature returns. Dividend-reinvested total returns are not modeled.

## Features and leakage

Each instrument resets its own rolling calculations. RSI uses Wilder smoothing; EMA is causal and unadjusted; Bollinger standard deviation uses population variance. ATR is a simple rolling average of true range. Additional features include lagged/simple/log returns, momentum, rolling min/max/mean/std, volatility, volume change and normalized Bollinger position. Null warm-up rows are excluded from fitting.

Walk-forward ML supports one instrument at a time. The target is whether close-to-close return over the next five sessions is positive. Training expands; each 126-session validation and test block is chronological. A five-session purge separates training labels from validation observations and validation labels from test observations. Scalers fit on training only. Logistic C is selected using validation log loss from 0.1, 1 and 10; no test-driven parameter selection occurs. Random forest and XGBoost use fixed bounded settings and seed 42. The naive model predicts the training prior. Models are not refitted on validation. Test predictions become close-time long/flat signals and enter the same next-open event engine. Prediction accuracy, balanced accuracy, log loss and ROC AUC are separate from trading returns.

## Provenance and limits

Snapshots are content-addressed without ingestion timestamps and checked on every read. Dataset lineages and quality counts are stored in PostgreSQL. Experiments preserve provider, exact dataset ID, config, code commit when available and a hash of Python source bytes. A dirty working tree is labeled rather than represented as a clean commit. Containers without Git report an unavailable commit unless GIT_COMMIT is supplied; their source fingerprint remains available.

Current ETF names are not historical constituents. Unknown exchange metadata remains UNVERIFIED. Yahoo prices exclude dividends and reject observed split intervals. No borrow fees, financing, taxes or intraday liquidity/queue-position estimates are included. Synthetic price patterns are intentionally deterministic for repeatable tests; their apparent predictability is not evidence about markets.
