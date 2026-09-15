"""Metric conventions are explicit and independent of presentation."""

from datetime import datetime
from typing import Any

import numpy as np

from axiom.backtest.engine import BacktestResult
from axiom.common.models import BacktestConfig


def summarize(result: BacktestResult, config: BacktestConfig) -> dict[str, Any]:
    equity = np.array([row["equity"] for row in result.equity], dtype=float)
    returns = equity[1:] / equity[:-1] - 1
    drawdown = equity / np.maximum.accumulate(equity) - 1
    years = (
        datetime.fromisoformat(result.equity[-1]["timestamp"])
        - datetime.fromisoformat(result.equity[0]["timestamp"])
    ).total_seconds() / (365.25 * 86400)
    std = float(returns.std(ddof=1)) if len(returns) > 1 else 0.0
    closed = [trade for trade in result.trades if not trade["open"]]
    wins = [trade["pnl"] for trade in closed if trade["pnl"] > 0]
    losses = [trade["pnl"] for trade in closed if trade["pnl"] < 0]
    return dict(
        total_return=float(equity[-1] / equity[0] - 1),
        cagr=float((equity[-1] / equity[0]) ** (1 / years) - 1) if years else None,
        annualized_volatility=std * np.sqrt(config.annualization),
        sharpe=float(returns.mean() / std * np.sqrt(config.annualization)) if std > 1e-15 else None,
        max_drawdown=float(drawdown.min()),
        final_equity=float(equity[-1]),
        exposure=float(np.mean([row["exposure"] for row in result.equity[1:]])),
        n_trades=len(result.trades),
        n_closed_trades=len(closed),
        win_rate=len(wins) / len(closed) if closed else None,
        average_winner=float(np.mean(wins)) if wins else None,
        average_loser=float(np.mean(losses)) if losses else None,
        profit_factor=sum(wins) / abs(sum(losses)) if losses else None,
        transaction_commissions=sum(fill["commission"] for fill in result.fills),
        realized_pnl=result.realized_pnl,
        unrealized_pnl=result.unrealized_pnl,
    )
