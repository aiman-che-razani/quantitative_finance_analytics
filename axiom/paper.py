"""Idempotent paper replay; never sends orders to a broker."""

import hashlib
import uuid
from datetime import datetime, timezone

import polars as pl
from sqlalchemy import select

from axiom.backtest.events import ExecutionConfig, run_events
from axiom.common.models import FeatureConfig
from axiom.data.storage import SnapshotStore
from axiom.features.pipeline import FeaturePipeline
from axiom.metadata import DatasetRow, PaperRow


def create_account(sessions, dataset_id, symbols, strategy, execution):
    identity = str(uuid.uuid4())
    with sessions.begin() as db:
        dataset = db.get(DatasetRow, dataset_id)
        if dataset is None or not symbols or not set(symbols) <= set(dataset.symbols):
            raise ValueError("Unknown dataset or symbols")
        db.add(
            PaperRow(
                id=identity,
                config={
                    "dataset_id": dataset_id,
                    "symbols": symbols,
                    "strategy": strategy,
                    "execution": execution.model_dump(),
                },
                state={"last_session": None, "alerts": [], "fills": []},
            )
        )
    return identity


def advance(sessions, settings, identity, as_of, dataset_id=None):
    if as_of >= datetime.now(timezone.utc).date():
        raise ValueError("Only prior completed daily sessions may be replayed")
    with sessions.begin() as db:
        row = db.scalar(select(PaperRow).where(PaperRow.id == identity).with_for_update())
        if row is None:
            raise ValueError("Unknown paper account")
        cfg = row.config
        dataset_id = dataset_id or cfg["dataset_id"]
        dataset = db.get(DatasetRow, dataset_id)
        original = db.get(DatasetRow, cfg["dataset_id"])
        if (
            dataset is None
            or dataset.provider != original.provider
            or not set(cfg["symbols"]) <= set(dataset.symbols)
        ):
            raise ValueError("Incompatible dataset")
        bars = (
            SnapshotStore(settings.data_root)
            .read(dataset_id)
            .filter(
                pl.col("instrument").is_in(cfg["symbols"])
                & (pl.col("timestamp").dt.date() <= as_of)
            )
        )

        def fingerprint(frame):
            return hashlib.sha256(
                frame.sort(["instrument", "timestamp"]).drop("ingested_at").write_json().encode()
            ).hexdigest()

        latest_stamp = bars["timestamp"].max()
        if not isinstance(latest_stamp, datetime):
            raise ValueError("No bars at requested date")
        last = row.state.get("last_session")
        if last:
            if as_of.isoformat() < last:
                raise ValueError("Paper clock cannot move backwards")
            prefix = bars.filter(pl.col("timestamp").dt.strftime("%Y-%m-%d") <= last)
            if fingerprint(prefix) != row.state["input_hash"]:
                raise ValueError("Previously processed bars changed")
            if latest_stamp.date().isoformat() == last:
                alerts = [a for a in row.state.get("alerts", []) if a != "STALE_INPUT"]
                if (as_of - latest_stamp.date()).days > 4:
                    alerts.append("STALE_INPUT")
                row.state = {**row.state, "alerts": alerts}
                row.updated_at = datetime.now(timezone.utc)
                return row.state
        frame = FeaturePipeline(FeatureConfig()).transform(bars)
        replay = run_events(
            frame, cfg["strategy"], ExecutionConfig(**cfg["execution"]), record_events=False
        )
        latest = latest_stamp.date()
        alerts = []
        if (as_of - latest).days > 4:
            alerts.append("STALE_INPUT")
        if any(d["action"] == "REJECT" for d in replay["risk_decisions"][-len(cfg["symbols"]) :]):
            alerts.append("RISK_REJECTION")
        state = {
            "last_session": latest.isoformat(),
            "input_hash": fingerprint(bars),
            "provider": dataset.provider,
            "mode": "historical paper replay",
            "alerts": alerts,
            "fills": replay["fills"],
            "equity": replay["equity"],
            "account": replay["final"],
        }
        row.state = state
        row.config = {**cfg, "dataset_id": dataset_id}
        row.updated_at = datetime.now(timezone.utc)
        return state
