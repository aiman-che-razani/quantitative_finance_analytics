"""Order objects and conservative daily-bar execution-price rules."""

import math
from dataclasses import dataclass
from typing import Literal


@dataclass
class Order:
    id: str
    symbol: str
    units: float
    kind: Literal["market", "limit", "stop", "stop_limit"] = "market"
    limit: float | None = None
    stop: float | None = None
    triggered: bool = False

    def __post_init__(self):
        if (
            not math.isfinite(self.units)
            or self.units == 0
            or self.kind not in {"market", "limit", "stop", "stop_limit"}
        ):
            raise ValueError("Invalid order")
        if self.kind in {"limit", "stop_limit"} and (
            self.limit is None or not math.isfinite(self.limit) or self.limit <= 0
        ):
            raise ValueError("Positive limit required")
        if self.kind in {"stop", "stop_limit"} and (
            self.stop is None or not math.isfinite(self.stop) or self.stop <= 0
        ):
            raise ValueError("Positive stop required")


def execution_price(order: Order, bar: dict, impact_bps: float) -> float | None:
    buy = order.units > 0
    opening = float(bar["open"])
    kind = order.kind
    if kind in {"stop", "stop_limit"} and not order.triggered:
        trigger = order.stop
        assert trigger is not None
        gap = opening >= trigger if buy else opening <= trigger
        touched = bar["high"] >= trigger if buy else bar["low"] <= trigger
        if not touched:
            return None
        order.triggered = True
        if kind == "stop_limit" and not gap:
            return None  # Unknown intrabar sequence: defer limit eligibility.
        if kind == "stop":
            raw = opening if gap else trigger
            return raw * (1 + (1 if buy else -1) * impact_bps / 10000)
    if kind in {"limit", "stop_limit"}:
        limit = order.limit
        assert limit is not None
        marketable = opening <= limit if buy else opening >= limit
        if not marketable and not (bar["low"] <= limit if buy else bar["high"] >= limit):
            return None
        raw = opening if marketable else limit
        impacted = raw * (1 + (1 if buy else -1) * impact_bps / 10000)
        return min(impacted, limit) if buy else max(impacted, limit)
    return opening * (1 + (1 if buy else -1) * impact_bps / 10000)
