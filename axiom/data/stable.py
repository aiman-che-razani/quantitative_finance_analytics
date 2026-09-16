"""Date-addressed synthetic observations: overlapping downloads are identical."""

import hashlib
from datetime import UTC, date, datetime

import numpy as np
import polars as pl

from axiom.common.models import Instrument
from axiom.data.providers import sessions


class StableSyntheticProvider:
    def fetch(self, instrument: Instrument, start: date, end: date) -> pl.DataFrame:
        days = sessions(start, end)
        return synthetic_frame(instrument.symbol, days)


def synthetic_frame(symbol: str, days: list[date]) -> pl.DataFrame:
    t = np.array([(d - date(2000, 1, 1)).days for d in days], dtype=float)
    salt = int.from_bytes(hashlib.sha256(symbol.encode()).digest()[:4], "big")
    phase = (salt % 10000) / 1000

    def price(x):
        return (50 + salt % 100) * np.exp(
            0.00003 * x + 0.12 * np.sin(x / 170 + phase) + 0.025 * np.sin(x / 7 + phase)
        )

    closing = price(t)
    opening = price(t - 0.5)
    return pl.DataFrame(
        {
            "instrument": [symbol] * len(days),
            "timestamp": [d.isoformat() for d in days],
            "timeframe": ["1d"] * len(days),
            "open": opening,
            "high": np.maximum(opening, closing) * 1.005,
            "low": np.minimum(opening, closing) * 0.995,
            "close": closing,
            "volume": 100000 + ((t * 7919 + salt) % 100000),
            "source": ["synthetic-v2"] * len(days),
            "ingested_at": [datetime.now(UTC).isoformat()] * len(days),
            "price_basis": ["synthetic"] * len(days),
        }
    )
