"""Signals are target exposures; only the engine changes portfolio state."""

from dataclasses import dataclass
from typing import Literal, Protocol

import polars as pl


class Strategy(Protocol):
    def signals(self, features: pl.DataFrame) -> list[int | None]: ...


@dataclass
class SimpleStrategy:
    name: Literal["ema_trend", "rsi_reversion", "combined", "buy_hold"] = "ema_trend"

    def signals(self, features: pl.DataFrame) -> list[int | None]:
        if self.name not in ("ema_trend", "rsi_reversion", "combined", "buy_hold"):
            raise ValueError("unknown strategy")
        if features["instrument"].n_unique() != 1:
            raise ValueError("each V0.1 account trades exactly one instrument")
        output: list[int | None] = []
        position = 0
        for row in features.iter_rows(named=True):
            if not row["ready"]:
                output.append(None)
                continue
            if self.name == "buy_hold":
                position = 1
            elif self.name == "ema_trend":
                position = int(row["close"] >= row["ema"])
            elif self.name == "rsi_reversion":
                if row["rsi"] <= 30:
                    position = 1
                elif row["rsi"] >= 50:
                    position = 0
            else:
                if (
                    row["close"] >= row["ema"]
                    and row["close"] <= row["bb_lower"]
                    and row["rsi"] <= 40
                ):
                    position = 1
                elif row["close"] < row["ema"] or row["rsi"] >= 60:
                    position = 0
            output.append(position)
        return output
