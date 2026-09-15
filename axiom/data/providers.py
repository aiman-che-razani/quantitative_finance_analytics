"""Swappable inputs. No implicit synthetic fallback after provider failure."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Protocol

import exchange_calendars as xcals
import numpy as np
import polars as pl

from axiom.common.models import Instrument


def sessions(start: date, end: date) -> list[date]:
    """US ETF calendar proxy; end is exclusive."""
    if start >= end:
        raise ValueError("start must precede end")
    calendar = xcals.get_calendar(
        "XNYS", start=start - timedelta(days=14), end=end + timedelta(days=14)
    )
    return [value.date() for value in calendar.sessions_in_range(start, end - timedelta(days=1))]


class Provider(Protocol):
    def fetch(self, instrument: Instrument, start: date, end: date) -> pl.DataFrame: ...


@dataclass
class CSVProvider:
    directory: Path

    def fetch(self, instrument: Instrument, start: date, end: date) -> pl.DataFrame:
        frame = pl.read_csv(self.directory / f"{instrument.symbol}.csv", infer_schema_length=0)
        if "timestamp" not in frame.columns:
            raise ValueError("CSV must contain timestamp and explicit canonical provenance columns")
        # Validate all supplied rows before date selection in orchestration.
        return frame


@dataclass
class SyntheticProvider:
    seed: int = 42

    def fetch(self, instrument: Instrument, start: date, end: date) -> pl.DataFrame:
        import hashlib

        salt = int.from_bytes(hashlib.sha256(instrument.symbol.encode()).digest()[:4], "big")
        rng = np.random.default_rng(self.seed + salt)
        days = sessions(start, end)
        close = 100.0
        now = datetime.now(UTC).isoformat()
        rows = []
        for i, day in enumerate(days):
            opening = close * float(np.exp(rng.normal(0, 0.003)))
            close = opening * float(np.exp(0.0002 + 0.002 * np.sin(i / 45) + rng.normal(0, 0.01)))
            spread = abs(float(rng.normal(0.004, 0.002)))
            rows.append(
                dict(
                    instrument=instrument.symbol,
                    timestamp=day.isoformat(),
                    timeframe="1d",
                    open=opening,
                    high=max(opening, close) * (1 + spread),
                    low=min(opening, close) * (1 - spread),
                    close=close,
                    volume=float(rng.integers(10000, 1000000)),
                    source=f"synthetic-v1-seed-{self.seed}",
                    ingested_at=now,
                    price_basis="synthetic",
                )
            )
        if not rows:
            raise ValueError("requested range contains no market sessions")
        return pl.DataFrame(rows)


class YahooProvider:
    def fetch(self, instrument: Instrument, start: date, end: date) -> pl.DataFrame:
        import yfinance as yf

        data = yf.download(
            instrument.symbol,
            start=start.isoformat(),
            end=end.isoformat(),
            interval="1d",
            auto_adjust=False,
            actions=True,
            progress=False,
            threads=False,
            multi_level_index=False,
        )
        if data is None or data.empty:
            raise ValueError(f"Yahoo returned no data for {instrument.symbol}; no fallback used")
        if "Stock Splits" not in data.columns:
            raise ValueError("provider did not return split information")
        if (data["Stock Splits"].fillna(0) != 0).any():
            raise ValueError("V0.1 cannot account for a split inside the requested window")
        now = datetime.now(UTC).isoformat()
        return pl.DataFrame(
            [
                dict(
                    instrument=instrument.symbol,
                    timestamp=stamp.date().isoformat(),
                    timeframe="1d",
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=float(row["Volume"]),
                    source="yahoo-yfinance",
                    ingested_at=now,
                    price_basis="raw_price",
                )
                for stamp, row in data.iterrows()
            ]
        )
