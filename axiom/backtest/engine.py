"""V0.1 fractional-unit, long/flat next-open replay with an auditable ledger."""

import math
from dataclasses import dataclass
from typing import Any

import polars as pl

from axiom.common.models import BacktestConfig


@dataclass
class BacktestResult:
    equity: list[dict[str, Any]]
    fills: list[dict[str, Any]]
    trades: list[dict[str, Any]]
    first_index: int
    realized_pnl: float
    unrealized_pnl: float


def run(
    bars: pl.DataFrame,
    signals: list[int | None],
    config: BacktestConfig,
    first_index: int | None = None,
) -> BacktestResult:
    if bars.height != len(signals) or bars["instrument"].n_unique() != 1:
        raise ValueError("bar/signal length mismatch or multiple instruments")
    if not bars["timestamp"].is_sorted() or bars["timestamp"].n_unique() != bars.height:
        raise ValueError("bars must be sorted and unique")
    if any(value not in (None, 0, 1) for value in signals):
        raise ValueError("only long/flat targets are supported")
    if first_index is None:
        ready = next((i for i, value in enumerate(signals) if value is not None), None)
        if ready is None:
            raise ValueError("insufficient feature warm-up")
        first_index = ready + 1
    if not 1 <= first_index < bars.height or signals[first_index - 1] is None:
        raise ValueError("need a causal signal and at least one execution bar")
    rows = bars.to_dicts()
    fee = config.commission_bps_per_side / 10000
    slip = config.slippage_bps_per_side / 10000
    cash, units, realized = config.initial_capital, 0.0, 0.0
    entry: dict[str, Any] | None = None
    fills: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    equity = [
        dict(
            timestamp=rows[first_index - 1]["timestamp"].isoformat(),
            equity=cash,
            cash=cash,
            units=0.0,
            close=rows[first_index - 1]["close"],
            exposure=0.0,
        )
    ]
    for i in range(first_index, len(rows)):
        row, target = rows[i], signals[i - 1]
        if target is None:
            raise ValueError("signal becomes unavailable inside the evaluation window")
        opening, closing = float(row["open"]), float(row["close"])
        if not all(math.isfinite(value) and value > 0 for value in (opening, closing)):
            raise ValueError("invalid execution or mark price")
        stamp = row["timestamp"].isoformat()
        if target == 1 and units == 0:
            price = opening * (1 + slip)
            units = cash / (price * (1 + fee))
            commission = units * price * fee
            entry = dict(
                entry_date=stamp,
                entry_price=price,
                units=units,
                entry_cost=cash,
                entry_commission=commission,
                entry_index=i,
            )
            cash -= units * price + commission
            if abs(cash) < 1e-8:
                cash = 0.0
            fills.append(
                dict(
                    timestamp=stamp,
                    signal_timestamp=rows[i - 1]["timestamp"].isoformat(),
                    side="BUY",
                    units=units,
                    price=price,
                    commission=commission,
                    cash_after=cash,
                )
            )
        elif target == 0 and units > 0:
            if entry is None:
                raise RuntimeError("position without entry ledger")
            price = opening * (1 - slip)
            commission = units * price * fee
            proceeds = units * price - commission
            pnl = proceeds - entry["entry_cost"]
            cash += proceeds
            realized += pnl
            trades.append(
                dict(
                    entry_date=entry["entry_date"],
                    exit_date=stamp,
                    bars_held=i - entry["entry_index"],
                    pnl=pnl,
                    net_return=pnl / entry["entry_cost"],
                    open=False,
                )
            )
            fills.append(
                dict(
                    timestamp=stamp,
                    signal_timestamp=rows[i - 1]["timestamp"].isoformat(),
                    side="SELL",
                    units=units,
                    price=price,
                    commission=commission,
                    cash_after=cash,
                )
            )
            units, entry = 0.0, None
        value = cash + units * closing
        if cash < -1e-7 or units < 0 or not math.isfinite(value):
            raise ArithmeticError("cash/position invariant violated")
        equity.append(
            dict(
                timestamp=stamp,
                equity=value,
                cash=cash,
                units=units,
                close=closing,
                exposure=units * closing / value,
            )
        )
    unrealized = 0.0
    if entry is not None:
        unrealized = units * float(rows[-1]["close"]) - entry["entry_cost"]
        trades.append(
            dict(
                entry_date=entry["entry_date"],
                exit_date=None,
                bars_held=len(rows) - entry["entry_index"],
                pnl=unrealized,
                net_return=unrealized / entry["entry_cost"],
                open=True,
            )
        )
    if not math.isclose(
        equity[-1]["equity"] - config.initial_capital,
        realized + unrealized,
        rel_tol=1e-9,
        abs_tol=1e-6,
    ):
        raise ArithmeticError("ledger P&L does not reconcile")
    return BacktestResult(equity, fills, trades, first_index, realized, unrealized)
