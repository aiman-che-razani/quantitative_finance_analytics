"""Signed positions and an auditable average-cost ledger."""

import math
from dataclasses import asdict, dataclass, field


@dataclass
class Position:
    units: float = 0.0
    average: float = 0.0
    entry_fees: float = 0.0
    entry_bar: int = 0


@dataclass
class Account:
    initial: float
    cash: float = field(init=False)
    realized: float = 0.0
    fees: float = 0.0
    positions: dict[str, Position] = field(default_factory=dict)
    trades: list[dict] = field(default_factory=list)
    ledger: list[dict] = field(default_factory=list)

    def __post_init__(self):
        self.cash = self.initial

    def fill(
        self,
        symbol: str,
        delta: float,
        price: float,
        fee: float,
        stamp: str,
        index: int,
        order_id: str,
    ):
        if not all(math.isfinite(x) for x in [delta, price, fee]) or price <= 0 or fee < 0:
            raise ValueError("Invalid fill")
        p = self.positions.setdefault(symbol, Position())
        old = p.units
        if old * delta < 0:
            closing = min(abs(old), abs(delta))
            gross = closing * (price - p.average) * (1 if old > 0 else -1)
            entry_fee = p.entry_fees * closing / abs(old)
            exit_fee = fee * closing / abs(delta)
            self.realized += gross
            self.trades.append(
                {
                    "symbol": symbol,
                    "timestamp": stamp,
                    "units": closing,
                    "direction": "LONG" if old > 0 else "SHORT",
                    "pnl": gross - entry_fee - exit_fee,
                    "gross_pnl": gross,
                    "bars_held": index - p.entry_bar,
                }
            )
            p.entry_fees -= entry_fee
            if abs(delta) > abs(old):
                p.average = price
                p.entry_fees = fee - exit_fee
                p.entry_bar = index
        else:
            p.average = (
                (abs(old) * p.average + abs(delta) * price) / (abs(old) + abs(delta))
                if delta
                else p.average
            )
            p.entry_fees += fee
            if old == 0:
                p.entry_bar = index
        p.units = old + delta
        if abs(p.units) < 1e-10:
            p.units = 0.0
            p.average = 0.0
            p.entry_fees = 0.0
        self.cash -= delta * price + fee
        self.fees += fee
        self.ledger.append(
            {
                "order_id": order_id,
                "symbol": symbol,
                "timestamp": stamp,
                "units": delta,
                "price": price,
                "commission": fee,
                "cash_after": self.cash,
                "position_after": p.units,
            }
        )

    def mark(self, prices: dict[str, float], include_positions: bool = True) -> dict:
        value = sum(p.units * prices[s] for s, p in self.positions.items())
        unrealized = sum(p.units * (prices[s] - p.average) for s, p in self.positions.items())
        equity = self.cash + value
        if not math.isclose(
            equity - self.initial,
            self.realized + unrealized - self.fees,
            abs_tol=1e-6,
            rel_tol=1e-9,
        ):
            raise ArithmeticError("Portfolio ledger failed reconciliation")
        gross = sum(abs(p.units * prices[s]) for s, p in self.positions.items())
        return {
            "cash": self.cash,
            "equity": equity,
            "realized_pnl": self.realized,
            "unrealized_pnl": unrealized,
            "commissions": self.fees,
            "gross_exposure": gross,
            "net_exposure": value,
            "leverage": gross / equity if equity > 0 else None,
            "positions": {s: asdict(p) for s, p in self.positions.items()}
            if include_positions
            else {},
        }
