"""Immutable single-writer Parquet snapshots with completion manifests."""

import hashlib
import json
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
            return identity
        stage = target.with_name(identity + ".partial-" + str(uuid.uuid4()))
        parts = []
        partitioned = frame.with_columns(pl.col("timestamp").dt.year().alias("year"))
        for (symbol, year), group in partitioned.partition_by(
            ["instrument", "year"], as_dict=True
        ).items():
            relative = Path(
                f"asset_class=etf/timeframe=1d/symbol={symbol}/year={year}/bars.parquet"
            )
            output = stage / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            group.drop("year").write_parquet(output, compression="zstd")
            parts.append(
                {
                    "path": relative.as_posix(),
                    "rows": group.height,
                    "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                }
            )
        manifest = {"version": 1, "dataset_id": identity, "rows": frame.height, "parts": parts}
        (stage / "manifest.json").write_text(json.dumps(manifest, indent=2))
        stage.rename(target)
        return identity

    def read(self, identity: str) -> pl.DataFrame:
        import re

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
