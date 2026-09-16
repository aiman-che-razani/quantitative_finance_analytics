"""Daily event replay. Signals at close can first execute on the next bar."""

from dataclasses import asdict, replace
from typing import Literal

import numpy as np
import polars as pl
from pydantic import BaseModel, ConfigDict, Field

from axiom.backtest.orders import Order, execution_price
from axiom.portfolio.account import Account
from axiom.risk.engine import RiskConfig, assess

STRATEGIES = [
    "buy_hold",
    "ema_trend",
    "ema_crossover",
    "rsi_reversion",
    "bollinger_reversion",
    "momentum",
    "combined",
    "ml",
]


class ExecutionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    initial_capital: float = Field(default=100000, gt=0, le=1e10)
    commission_bps: float = Field(default=2.5, ge=0, le=100)
    slippage_bps: float = Field(default=1, ge=0, le=100)
    spread_bps: float = Field(default=1, ge=0, le=100)
    participation: float = Field(default=0.01, gt=0, le=1)
    stop_loss: float | None = Field(default=None, gt=0, lt=1)
    take_profit: float | None = Field(default=None, gt=0, le=10)
    order_type: Literal["market", "limit", "stop", "stop_limit"] = "market"
    order_offset: float = Field(default=0.005, ge=0, le=0.2)
    risk: RiskConfig = Field(default_factory=RiskConfig)


def target(row: dict, strategy: str, current: int = 0, allow_short: bool = False) -> int:
    if not row["ready"]:
        return 0
    down = -1 if allow_short else 0
    if strategy == "buy_hold":
        return 1
    if strategy == "ema_trend":
        return 1 if row["close"] >= row["ema"] else down
    if strategy == "ema_crossover" and row["ema_fast"] is None:
        return 0
    if strategy == "momentum" and row["momentum"] is None:
        return 0
    if strategy == "ema_crossover":
        return 1 if row["ema_fast"] >= row["ema"] else down
    if strategy == "momentum":
        return 1 if row["momentum"] > 0 else down
    if strategy == "rsi_reversion":
        return 1 if row["rsi"] < 30 else 0 if row["rsi"] > 50 else current
    if strategy == "bollinger_reversion":
        return (
            1
            if row["close"] < row["bb_lower"]
            else 0
            if row["close"] > row["bb_middle"]
            else current
        )
    if strategy == "combined":
        return (
            1
            if row["close"] >= row["ema"] and row["rsi"] < 45 and row["close"] < row["bb_middle"]
            else 0
        )
    if strategy == "ml":
        return int(row.get("prediction", 0))
    raise ValueError("Unknown strategy")


def run_events(
    features: pl.DataFrame,
    strategy: str,
    config: ExecutionConfig,
    first_index: int | None = None,
    explicit_orders: dict[int, list[Order]] | None = None,
    record_events: bool = True,
) -> dict:
    if strategy not in STRATEGIES or features.is_empty():
        raise ValueError("Invalid research input")
    required = {
        "instrument",
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "ready",
        "ema",
        "ema_fast",
        "momentum",
        "rsi",
        "bb_lower",
        "bb_middle",
        "prediction",
    }
    features = features.select([c for c in features.columns if c in required])
    groups = {
        g["instrument"][0]: g.to_dicts()
        for g in features.sort(["instrument", "timestamp"]).partition_by("instrument")
    }
    symbols = sorted(groups)
    stamps = [row["timestamp"] for row in groups[symbols[0]]]
    if any([r["timestamp"] for r in rows] != stamps for rows in groups.values()):
        raise ValueError("Portfolio requires aligned daily sessions")
    ready = [i for i in range(len(stamps)) if all(groups[s][i]["ready"] for s in symbols)]
    if not ready:
        raise ValueError("Insufficient feature warm-up")
    first = first_index if first_index is not None else ready[0] + 1
    if not 1 <= first < len(stamps) or not all(groups[s][first - 1]["ready"] for s in symbols):
        raise ValueError("No causal execution window")
    account = Account(config.initial_capital)
    pending: dict[str, Order] = {}
    events: list[dict] = []
    risk_log = []
    equity = []
    counter = 0
    peak = config.initial_capital
    last_equity = config.initial_capital
    fee_rate = config.commission_bps / 10000

    def event(event_type, **values):
        if record_events and len(events) < 20000:
            events.append({**values, "event_type": event_type})

    def orders_at(i):
        nonlocal counter
        if explicit_orders is not None:
            for order in explicit_orders.get(i, []):
                pending[order.symbol] = replace(order)
            return
        for s in symbols:
            row = groups[s][i]
            p = account.positions.get(s)
            held = p.units if p else 0
            direction = int(np.sign(held))
            signal = target(row, strategy, direction, config.risk.allow_short)
            event("SIGNAL", timestamp=str(stamps[i]), symbol=s, target=signal)
            if direction == signal:
                if signal == 0 and s in pending:
                    event("CANCEL", order_id=pending[s].id, reason="signal became flat")
                    del pending[s]
                continue
            # Close before reversing; opposite entry can occur after the next signal.
            units = -held if held else signal * last_equity / len(symbols) / row["close"]
            if abs(units) < 1e-8:
                continue
            if s in pending:
                existing = pending[s]
                if np.sign(existing.units) == np.sign(units):
                    continue
                event("CANCEL", order_id=existing.id, reason="signal changed")
            counter += 1
            kind = config.order_type if not held else "market"
            side = 1 if units > 0 else -1
            limit = (
                row["close"] * (1 - side * config.order_offset)
                if kind == "limit"
                else row["close"] * (1 + side * config.order_offset * 2)
            )
            stop = row["close"] * (1 + side * config.order_offset)
            order = Order(
                str(counter),
                s,
                units,
                kind,
                limit if kind in {"limit", "stop_limit"} else None,
                stop if kind in {"stop", "stop_limit"} else None,
            )
            pending[s] = order
            event("ORDER", timestamp=str(stamps[i]), **asdict(order))

    marks = {s: groups[s][first - 1]["close"] for s in symbols}
    initial = account.mark(marks, include_positions=False)
    initial.pop("positions")
    equity.append({"timestamp": str(stamps[first - 1]), **initial})
    orders_at(first - 1)
    for i in range(first, len(stamps)):
        bars = {s: groups[s][i] for s in symbols}
        marks = {s: bar["open"] for s, bar in bars.items()}
        day_start = last_equity
        liquidity = {s: float(bars[s]["volume"]) * config.participation for s in symbols}
        for s in symbols:
            event("MARKET", timestamp=str(stamps[i]), symbol=s)
            p = account.positions.get(s)
            if p and p.units and (config.stop_loss or config.take_profit):
                direction = 1 if p.units > 0 else -1
                stop = p.average * (1 - direction * config.stop_loss) if config.stop_loss else None
                take = (
                    p.average * (1 + direction * config.take_profit) if config.take_profit else None
                )
                hit_stop = stop and (
                    bars[s]["low"] <= stop if direction > 0 else bars[s]["high"] >= stop
                )
                hit_take = take and (
                    bars[s]["high"] >= take if direction > 0 else bars[s]["low"] <= take
                )
                if hit_stop or hit_take:
                    counter += 1
                    pending[s] = Order(
                        str(counter),
                        s,
                        -p.units,
                        "stop" if hit_stop else "limit",
                        take if not hit_stop else None,
                        stop if hit_stop else None,
                    )
        for s in symbols:
            order = pending.get(s)
            if order is None:
                continue
            price = execution_price(order, bars[s], config.slippage_bps + config.spread_bps / 2)
            if price is None:
                continue
            units = float(np.sign(order.units)) * min(abs(order.units), liquidity[s])
            if abs(units) < 1e-10:
                continue
            decision = assess(
                account,
                s,
                units,
                price,
                marks,
                config.risk,
                peak,
                day_start,
                fee_rate,
                config.stop_loss,
            )
            risk_log.append(
                {"timestamp": str(stamps[i]), "order_id": order.id, "symbol": s, **asdict(decision)}
            )
            if decision.action == "REJECT":
                del pending[s]
                continue
            units = decision.units
            account.fill(
                s, units, price, abs(units * price) * fee_rate, str(stamps[i]), i, order.id
            )
            event(
                "FILL",
                timestamp=str(stamps[i]),
                symbol=s,
                order_id=order.id,
                units=units,
                price=price,
            )
            order.units -= units
            if abs(order.units) < 1e-7 or decision.action == "MODIFY":
                del pending[s]
        marks = {s: bar["close"] for s, bar in bars.items()}
        state = account.mark(marks, include_positions=False)
        state.pop("positions")
        equity.append({"timestamp": str(stamps[i]), **state})
        last_equity = state["equity"]
        peak = max(peak, last_equity)
        if last_equity <= 0:
            break
        if i < len(stamps) - 1:
            orders_at(i)
    final = account.mark(marks)
    return {
        "equity": equity,
        "fills": account.ledger,
        "trades": account.trades,
        "risk_decisions": risk_log,
        "positions": final["positions"],
        "first_index": first,
        "events": events,
        "events_truncated": len(events) >= 20000,
        "pending_orders": [asdict(o) for o in pending.values()],
        "final": final,
    }
