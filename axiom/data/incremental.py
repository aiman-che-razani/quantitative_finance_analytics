import hashlib
import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import polars as pl
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert

from axiom.common.models import Instrument
from axiom.data.providers import Provider
from axiom.data.storage import SnapshotStore
from axiom.data.validation import validate
from axiom.metadata import DatasetRow, HeadRow, InstrumentRow


def ingest_incremental(
    sessions,
    root: Path,
    provider: Provider,
    universe: list[Instrument],
    start: date,
    end: date,
    provider_name: str,
) -> dict:
    if not universe or len({i.symbol for i in universe}) != len(universe):
        raise ValueError("universe must be nonempty and unique")
    started = time.perf_counter()
    store = SnapshotStore(root)
    reports, frames = {}, []
    for instrument in universe:
        raw = provider.fetch(instrument, start, end)
        capture = store.capture(instrument.symbol, raw)
        clean, quality = validate(raw, instrument.symbol, start, end)
        if quality.rejected_records or quality.missing_periods or clean.is_empty():
            raise ValueError(f"Data quality failed for {instrument.symbol}: {quality.to_dict()}")
        reports[instrument.symbol] = {**quality.to_dict(), "raw_capture": str(capture)}
        frames.append(clean)
    incoming = pl.concat(frames)
    stream = hashlib.sha256(
        json.dumps([provider_name, sorted(i.symbol for i in universe)]).encode()
    ).hexdigest()
    with sessions.begin() as db:
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": int(stream[:15], 16)})
        head = db.get(HeadRow, stream)
        parent = head.dataset_id if head else None
        combined = pl.concat([store.read(parent), incoming]) if parent else incoming
        keys = [c for c in combined.columns if c != "ingested_at"]
        distinct = combined.unique(subset=keys)
        if distinct.group_by(["instrument", "timestamp"]).len().filter(pl.col("len") > 1).height:
            raise ValueError("Conflicting overlap: publish an explicitly corrected dataset instead")
        combined = combined.unique(subset=["instrument", "timestamp"], keep="first").sort(
            ["instrument", "timestamp"]
        )
        for group in combined.partition_by("instrument"):
            lower, upper = group["timestamp"].min(), group["timestamp"].max()
            assert isinstance(lower, datetime) and isinstance(upper, datetime)
            _, quality = validate(
                group, group["instrument"][0], lower.date(), upper.date() + timedelta(days=1)
            )
            if quality.missing_periods or quality.rejected_records:
                raise ValueError("Incremental merge would create a gap")
        identity = store.write(combined)
        report = {
            "rows": combined.height,
            "incoming_rows": incoming.height,
            "duplicate_rows": sum(f.height for f in frames)
            + (store.read(parent).height if parent else 0)
            - combined.height,
            "instruments": reports,
            "duration_seconds": time.perf_counter() - started,
        }
        for instrument in universe:
            db.execute(
                insert(InstrumentRow)
                .values(symbol=instrument.symbol, definition=instrument.model_dump(mode="json"))
                .on_conflict_do_update(
                    index_elements=[InstrumentRow.symbol],
                    set_={"definition": instrument.model_dump(mode="json")},
                )
            )
        if db.get(DatasetRow, identity) is None:
            db.add(
                DatasetRow(
                    id=identity,
                    parent_id=parent,
                    provider=provider_name,
                    symbols=sorted(i.symbol for i in universe),
                    quality=report,
                )
            )
            db.flush()
        if head:
            head.dataset_id = identity
        else:
            db.add(HeadRow(stream=stream, dataset_id=identity))
    return {"dataset_id": identity, "parent_id": parent, **report}
