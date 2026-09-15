"""Canonical daily bars and explicit data-quality evidence."""

import math
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from typing import Any

import polars as pl

from axiom.data.providers import sessions

SCHEMA_TYPES: dict[str, pl.DataType] = {
    "instrument": pl.String(),
    "timestamp": pl.Datetime("us", "UTC"),
    "timeframe": pl.String(),
    "open": pl.Float64(),
    "high": pl.Float64(),
    "low": pl.Float64(),
    "close": pl.Float64(),
    "volume": pl.Float64(),
    "source": pl.String(),
    "ingested_at": pl.Datetime("us", "UTC"),
    "price_basis": pl.String(),
}
SCHEMA = pl.Schema(SCHEMA_TYPES)


@dataclass
class QualityReport:
    input_rows: int = 0
    accepted_rows: int = 0
    duplicate_rows: int = 0
    rejected_records: list[dict[str, Any]] = field(default_factory=list)
    missing_periods: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_time(value: Any, date_label: bool = False) -> datetime:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, date):
        result = datetime.combine(value, datetime.min.time(), UTC)
    else:
        text = str(value)
        result = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if len(text) == 10 and date_label:
            result = result.replace(tzinfo=UTC)
    if result.tzinfo is None:
        raise ValueError("timestamp must be UTC-aware or a daily YYYY-MM-DD session label")
    return result.astimezone(UTC)


def validate(
    frame: pl.DataFrame, symbol: str, start: date, end: date
) -> tuple[pl.DataFrame, QualityReport]:
    if set(SCHEMA) - set(frame.columns):
        raise ValueError(f"missing required columns: {sorted(set(SCHEMA) - set(frame.columns))}")
    report = QualityReport(input_rows=frame.height)
    expected = set(sessions(start, end))
    records: dict[datetime, dict[str, Any]] = {}
    conflicts: set[datetime] = set()
    for number, source in enumerate(frame.iter_rows(named=True)):
        try:
            row = dict(source)
            stamp = parse_time(row["timestamp"], date_label=True)
            if not start <= stamp.date() < end:
                raise ValueError("observation outside requested interval")
            if stamp.hour or stamp.minute or stamp.second or stamp.microsecond:
                raise ValueError("daily timestamp must be a midnight UTC session label")
            if stamp.date() not in expected:
                raise ValueError("not a market session")
            if row["instrument"] != symbol or row["timeframe"] != "1d":
                raise ValueError("instrument or timeframe mismatch")
            if row["price_basis"] not in ("raw_price", "synthetic") or not row["source"]:
                raise ValueError("explicit supported source/price basis required")
            if (row["price_basis"] == "synthetic") != str(row["source"]).startswith("synthetic"):
                raise ValueError("source and synthetic price basis disagree")
            row["timestamp"] = stamp
            row["ingested_at"] = parse_time(row["ingested_at"])
            if row["ingested_at"] > datetime.now(UTC):
                raise ValueError("ingestion timestamp is in the future")
            for field_name in ("open", "high", "low", "close", "volume"):
                row[field_name] = float(row[field_name])
                if not math.isfinite(row[field_name]):
                    raise ValueError("non-finite numeric value")
            if min(row[x] for x in ("open", "high", "low", "close")) <= 0 or row["volume"] < 0:
                raise ValueError("price must be positive and volume nonnegative")
            if (
                row["low"] > min(row["open"], row["close"])
                or row["high"] < max(row["open"], row["close"])
                or row["low"] > row["high"]
            ):
                raise ValueError("inconsistent OHLC")
            if stamp in records:
                keys = [key for key in SCHEMA if key != "ingested_at"]
                if any(records[stamp][key] != row[key] for key in keys):
                    conflicts.add(stamp)
                    raise ValueError("conflicting duplicate observation")
                report.duplicate_rows += 1
            else:
                records[stamp] = {key: row[key] for key in SCHEMA}
        except (TypeError, ValueError, OverflowError) as error:
            report.rejected_records.append({"row": number, "reason": str(error)})
    for stamp in conflicts:
        records.pop(stamp, None)
    ordered = [records[key] for key in sorted(records)]
    if len({(row["source"], row["price_basis"]) for row in ordered}) > 1:
        raise ValueError("cannot mix sources or price bases in one instrument snapshot")
    report.accepted_rows = len(ordered)
    report.missing_periods = [
        day.isoformat() for day in sorted(expected - {r["timestamp"].date() for r in ordered})
    ]
    if ordered and ordered[-1]["timestamp"].date() < max(expected):
        report.warnings.append("stale relative to requested final market session")
    for previous, current in zip(ordered, ordered[1:]):
        if abs(current["close"] / previous["close"] - 1) > 0.5:
            report.warnings.append(f"abnormal >50% close change at {current['timestamp'].date()}")
    if any(row["volume"] == 0 for row in ordered):
        report.warnings.append("zero-volume observations")
    return pl.DataFrame(ordered, schema=SCHEMA), report
