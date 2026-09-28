from datetime import UTC, date, datetime

import polars as pl
import pytest

from axiom.data.storage import SnapshotStore
from axiom.data.validation import validate


def check(frame):
    return validate(frame, "SPY", date(2020, 1, 1), date(2022, 1, 1))


def test_calendar_holidays_and_complete_data(bars):
    frame, report = check(bars)
    assert not report.missing_periods and not report.rejected_records
    assert date(2020, 1, 1) not in frame["timestamp"].dt.date().to_list()
    assert frame["timestamp"].dt.weekday().max() <= 5


def test_exact_duplicate_and_conflict(bars):
    frame, report = check(pl.concat([bars, bars.head(1)]))
    assert frame.height == bars.height and report.duplicate_rows == 1
    altered = bars.head(1).with_columns((pl.col("volume") + 1).alias("volume"))
    frame, report = check(pl.concat([bars, altered]))
    assert frame.height == bars.height - 1
    assert report.rejected_records and len(report.missing_periods) == 1


@pytest.mark.parametrize(
    "column,value", [("close", float("nan")), ("volume", -1), ("low", 0), ("high", 1)]
)
def test_reject_bad_numeric_data(bars, column, value):
    bad = (
        bars.with_row_index()
        .with_columns(
            pl.when(pl.col("index") == 0).then(value).otherwise(pl.col(column)).alias(column)
        )
        .drop("index")
    )
    _, report = check(bad)
    assert len(report.rejected_records) == 1


def test_missing_and_stale(bars):
    _, report = check(bars.slice(1, bars.height - 2))
    assert len(report.missing_periods) == 2
    assert any("stale" in warning for warning in report.warnings)


def test_snapshot_idempotence_and_tamper_detection(bars, tmp_path):
    store = SnapshotStore(tmp_path)
    identity = store.write(bars)
    repeat = store.write(bars.with_columns(pl.lit(datetime.now(UTC)).alias("ingested_at")))
    assert identity == repeat
    assert store.read(identity).height == bars.height
    target = next((tmp_path / "validated" / identity).rglob("bars.parquet"))
    target.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="hash mismatch"):
        store.read(identity)
    with pytest.raises(ValueError):
        store.read("../outside")


def test_snapshot_write_cleans_staging_and_tolerates_concurrent_publish(
    bars, tmp_path, monkeypatch
):
    store = SnapshotStore(tmp_path)

    def fail(self, frame, identity, stage):
        (stage / "partial").mkdir(parents=True)
        raise OSError("disk full")

    with monkeypatch.context() as patched:
        patched.setattr(SnapshotStore, "_stage", fail)
        with pytest.raises(OSError, match="disk full"):
            store.write(bars)
    assert not any((tmp_path / "validated").glob("*"))
    # A writer that loses the rename race to a concurrent publisher returns its identity.
    real_stage = SnapshotStore._stage

    def race(self, frame, identity, stage):
        real_stage(self, frame, identity, stage)
        real_stage(self, frame, identity, stage.with_name(identity))  # the other writer

    monkeypatch.setattr(SnapshotStore, "_stage", race)
    identity = store.write(bars)
    assert [p.name for p in (tmp_path / "validated").iterdir()] == [identity]
    assert store.read(identity).height == bars.height


def test_timestamp_validation_and_csv_roundtrip(bars, tmp_path):
    from axiom.common.models import UNIVERSE
    from axiom.data.providers import CSVProvider
    from axiom.data.validation import parse_time

    bars.write_csv(tmp_path / "SPY.csv")
    imported = CSVProvider(tmp_path).fetch(UNIVERSE[0], date(2020, 1, 1), date(2022, 1, 1))
    clean, report = check(imported)
    assert clean.height == bars.height and not report.rejected_records
    with pytest.raises(ValueError, match="UTC-aware"):
        parse_time("2020-01-02T00:00:00")
    with pytest.raises(ValueError):
        parse_time("not-a-date")
