import hashlib
import json
import os
from datetime import UTC, date, datetime

import polars as pl
import pytest

from axiom.common.models import UNIVERSE
from axiom.data import storage
from axiom.data.providers import CSVProvider
from axiom.data.storage import SnapshotStore
from axiom.data.validation import parse_time, validate


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


def test_rewriting_a_corrupted_snapshot_repairs_it(bars, tmp_path):
    store = SnapshotStore(tmp_path)
    identity = store.write(bars)
    next((tmp_path / "validated" / identity).rglob("bars.parquet")).write_bytes(b"torn")
    assert store.write(bars) == identity
    assert store.read(identity).height == bars.height
    assert len(list((tmp_path / "validated").glob(identity + ".corrupt-*"))) == 1


def test_timestamp_validation_and_csv_roundtrip(bars, tmp_path):
    bars.write_csv(tmp_path / "SPY.csv")
    imported = CSVProvider(tmp_path).fetch(UNIVERSE[0], date(2020, 1, 1), date(2022, 1, 1))
    clean, report = check(imported)
    assert clean.height == bars.height and not report.rejected_records
    with pytest.raises(ValueError, match="UTC-aware"):
        parse_time("2020-01-02T00:00:00")
    with pytest.raises(ValueError):
        parse_time("not-a-date")


@pytest.mark.parametrize("platform_name,expected", [("nt", os.O_RDWR), ("posix", os.O_RDONLY)])
def test_fsync_opens_files_writable_only_on_windows(tmp_path, monkeypatch, platform_name, expected):
    # CI runs on Linux only; this pins the Windows branch that e7f2085 fixed.
    target = tmp_path / "bars.parquet"
    target.write_bytes(b"x")
    seen = []
    real_open = os.open

    def fake_open(path, flags, *rest):
        seen.append(flags)
        return real_open(path, os.O_RDONLY)

    monkeypatch.setattr(storage.os, "fsync", lambda fd: None)
    monkeypatch.setattr(storage.os, "open", fake_open)
    monkeypatch.setattr(storage.os, "name", platform_name)
    storage._fsync(target)
    assert seen == [expected]


def test_snapshot_read_rejects_manifest_paths_outside_the_snapshot(bars, tmp_path):
    store = SnapshotStore(tmp_path)
    identity = store.write(bars)
    manifest_path = tmp_path / "validated" / identity / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    (tmp_path / "outside.parquet").write_bytes(b"x")
    manifest["parts"][0]["path"] = "../../outside.parquet"
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="escapes root"):
        store.read(identity)


def test_snapshot_read_rejects_parts_with_rewritten_hashes(bars, tmp_path):
    store = SnapshotStore(tmp_path)
    identity = store.write(bars)
    root = tmp_path / "validated" / identity
    manifest = json.loads((root / "manifest.json").read_text())
    part = root / manifest["parts"][0]["path"]
    pl.read_parquet(part).with_columns(pl.col("close") * 2).write_parquet(part)
    manifest["parts"][0]["sha256"] = hashlib.sha256(part.read_bytes()).hexdigest()
    (root / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="content hash mismatch"):
        store.read(identity)


def test_snapshot_write_rejects_an_empty_frame(bars, tmp_path):
    with pytest.raises(ValueError, match="empty"):
        SnapshotStore(tmp_path).write(bars.head(0))


def test_write_does_not_report_an_unhealed_corrupt_snapshot(bars, tmp_path, monkeypatch):
    store = SnapshotStore(tmp_path)
    identity = store.write(bars)
    root = tmp_path / "validated" / identity
    part = next(root.rglob("*.parquet"))
    part.write_bytes(part.read_bytes() + b"x")
    real_rename = storage.Path.rename

    def blocked(self, target):
        if ".corrupt-" in str(target):
            raise PermissionError("file in use")
        return real_rename(self, target)

    monkeypatch.setattr(storage.Path, "rename", blocked)
    with pytest.raises(OSError):
        store.write(bars)
