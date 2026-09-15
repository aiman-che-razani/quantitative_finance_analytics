"""One causal feature pipeline for rule-based research and later ML consumers."""

from dataclasses import dataclass
from typing import Protocol

import numpy as np
import polars as pl

from axiom.common.models import FeatureConfig


class FeatureTransform(Protocol):
    def transform(self, bars: pl.DataFrame) -> pl.DataFrame: ...


def wilder_rsi(close: np.ndarray, period: int) -> list[float | None]:
    output: list[float | None] = [None] * len(close)
    if len(close) <= period:
        return output
    changes = np.diff(close)
    gains, losses = np.maximum(changes, 0), np.maximum(-changes, 0)
    up, down = float(gains[:period].mean()), float(losses[:period].mean())
    for i in range(period, len(close)):
        if i > period:
            up = (up * (period - 1) + gains[i - 1]) / period
            down = (down * (period - 1) + losses[i - 1]) / period
        output[i] = 50.0 if up == down == 0 else 100.0 if down == 0 else 100 - 100 / (1 + up / down)
    return output


@dataclass
class FeaturePipeline:
    config: FeatureConfig

    def transform(self, bars: pl.DataFrame) -> pl.DataFrame:
        if bars.is_empty():
            raise ValueError("no bars")
        outputs = []
        for group in bars.sort(["instrument", "timestamp"]).partition_by("instrument"):
            cfg = self.config
            group = (
                group.with_columns(
                    pl.Series("rsi", wilder_rsi(group["close"].to_numpy(), cfg.rsi_period)),
                    pl.col("close")
                    .ewm_mean(span=cfg.ema_period, adjust=False, min_samples=cfg.ema_period)
                    .alias("ema"),
                    pl.col("close").rolling_mean(cfg.bollinger_period).alias("bb_middle"),
                    pl.col("close").rolling_std(cfg.bollinger_period, ddof=0).alias("bb_std"),
                    (pl.col("close") / pl.col("close").shift(1) - 1).alias("simple_return"),
                )
                .with_columns(
                    (pl.col("bb_middle") + cfg.bollinger_std * pl.col("bb_std")).alias("bb_upper"),
                    (pl.col("bb_middle") - cfg.bollinger_std * pl.col("bb_std")).alias("bb_lower"),
                    (pl.col("close") / pl.col("ema") - 1).alias("ema_distance"),
                )
                .with_columns(
                    pl.all_horizontal(
                        pl.col("rsi").is_not_null(),
                        pl.col("ema").is_not_null(),
                        pl.col("bb_middle").is_not_null(),
                    ).alias("ready")
                )
            )
            outputs.append(group)
        return pl.concat(outputs).sort(["instrument", "timestamp"])
