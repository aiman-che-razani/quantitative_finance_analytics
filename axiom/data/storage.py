"""Immutable single-writer Parquet snapshots with completion manifests."""

import hashlib
import json
import os
import re
import shutil
import uuid
from pathlib import Path

import polars as pl


class SnapshotStore:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def capture(self, symbol: str, raw: pl.DataFrame) -> Path:
        target = self.root / "raw" / symbol / f"{uuid.uuid4()}.parquet"
        target.parent.mkdir(parents=True, exist_ok=True)
        raw.write_parquet(target)
        return target

    def write(self, frame: pl.DataFrame) -> str:
        if frame.is_empty():
            raise ValueError("cannot publish an empty snapshot")
        canonical = frame.sort(["instrument", "timestamp"]).drop("ingested_at").write_json()
        identity = hashlib.sha256(canonical.encode()).hexdigest()
        target = self.root / "validated" / identity
        if (target / "manifest.json").exists():
            if _parts_intact(target):
                return identity
            # A torn or corrupted publish must not be permanent: set it aside for
            # inspection and republish the same content from this verified frame.
            target.rename(target.with_name(identity + ".corrupt-" + str(uuid.uuid4())))
        stage = target.with_name(identity + ".partial-" + str(uuid.uuid4()))
        try:
            self._stage(frame, identity, stage)
            stage.rename(target)
        except OSError:
            shutil.rmtree(stage, ignore_errors=True)
            # A concurrent writer published the same content-addressed snapshot first.
            if (target / "manifest.json").exists():
                return identity
            raise
        except BaseException:
            shutil.rmtree(stage, ignore_errors=True)
            raise
        _fsync(target.parent)
        return identity

    def _stage(self, frame: pl.DataFrame, identity: str, stage: Path) -> None:
        parts = []
        partitioned = frame.with_columns(pl.col("timestamp").dt.year().alias("year"))
        for (symbol, year, timeframe), group in partitioned.partition_by(
            ["instrument", "year", "timeframe"], as_dict=True
        ).items():
            # asset_class is fixed to "etf" because Instrument.asset_class is still a
            # single-value Literal today (axiom/common/models.py); timeframe comes from
            # the group key so a partition's path always matches its actual rows.
            relative = Path(
                f"asset_class=etf/timeframe={timeframe}/symbol={symbol}/year={year}/bars.parquet"
            )
            output = stage / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            group.drop("year").write_parquet(output, compression="zstd")
            _fsync(output)
            parts.append(
                {
                    "path": relative.as_posix(),
                    "rows": group.height,
                    "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                }
            )
        manifest = {"version": 1, "dataset_id": identity, "rows": frame.height, "parts": parts}
        (stage / "manifest.json").write_text(json.dumps(manifest, indent=2))
        _fsync(stage / "manifest.json")
        for directory in {p.parent for p in stage.rglob("*.parquet")} | {stage}:
            _fsync(directory)

    def read(self, identity: str) -> pl.DataFrame:
        if not re.fullmatch(r"[0-9a-f]{64}", identity):
            raise ValueError("invalid dataset ID")
        root = self.root / "validated" / identity
        manifest = json.loads((root / "manifest.json").read_text())
        frames = []
        for part in manifest["parts"]:
            path = (root / part["path"]).resolve()
            if root.resolve() not in path.parents:
                raise ValueError("snapshot path escapes root")
            if hashlib.sha256(path.read_bytes()).hexdigest() != part["sha256"]:
                raise ValueError("snapshot file hash mismatch")
            frames.append(pl.read_parquet(path, hive_partitioning=False))
        frame = pl.concat(frames).sort(["instrument", "timestamp"])
        canonical = frame.drop("ingested_at").write_json()
        if hashlib.sha256(canonical.encode()).hexdigest() != identity:
            raise ValueError("snapshot content hash mismatch")
        return frame


def _parts_intact(target: Path) -> bool:
    try:
        manifest = json.loads((target / "manifest.json").read_text())
        return all(
            hashlib.sha256((target / part["path"]).read_bytes()).hexdigest() == part["sha256"]
            for part in manifest["parts"]
        )
    except (OSError, ValueError, KeyError, TypeError):
        return False


def _fsync(path: Path) -> None:
    """Flush a file or directory entry to disk so a published snapshot survives power loss."""
    if path.is_dir() and os.name == "nt":
        return  # Windows cannot open a directory for fsync
    # Windows fsync (_commit) needs a writable descriptor; POSIX accepts read-only.
    fd = os.open(path, os.O_RDWR if os.name == "nt" else os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
