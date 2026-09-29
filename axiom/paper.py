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


class PaperConflict(ValueError):
    """The request is valid but conflicts with the account's recorded state (HTTP 409)."""


# Calendar days without a new bar after which a paper account is flagged STALE_INPUT.
STALE_AFTER_DAYS = 4


def create_account(sessions, dataset_id, symbols, strategy, execution, features=None):
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
                    "features": (features or FeatureConfig()).model_dump(),
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
            raise LookupError("Unknown paper account")
        cfg = row.config
        dataset_id = dataset_id or cfg["dataset_id"]
        dataset = db.get(DatasetRow, dataset_id)
        original = db.get(DatasetRow, cfg["dataset_id"])
        if (
            dataset is None
            or original is None
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
                raise PaperConflict("Paper clock cannot move backwards")
            prefix = bars.filter(pl.col("timestamp").dt.strftime("%Y-%m-%d") <= last)
            if fingerprint(prefix) != row.state["input_hash"]:
                raise PaperConflict("Previously processed bars changed")
            if latest_stamp.date().isoformat() == last:
                alerts = [a for a in row.state.get("alerts", []) if a != "STALE_INPUT"]
                if (as_of - latest_stamp.date()).days > STALE_AFTER_DAYS:
                    alerts.append("STALE_INPUT")
                row.state = {**row.state, "alerts": alerts}
                row.updated_at = datetime.now(timezone.utc)
                return row.state
        # Accounts created before features were stored replay with the defaults.
        frame = FeaturePipeline(FeatureConfig(**cfg.get("features", {}))).transform(bars)
        replay = run_events(
            frame, cfg["strategy"], ExecutionConfig(**cfg["execution"]), record_events=False
        )
        latest = latest_stamp.date()
        alerts = []
        if (as_of - latest).days > STALE_AFTER_DAYS:
            alerts.append("STALE_INPUT")
        # Only a rejection in the latest session is current; an old one must not re-alert.
        if any(
            d["action"] == "REJECT" and d["timestamp"][:10] == latest.isoformat()
            for d in replay["risk_decisions"]
        ):
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


def record_tick_failure(sessions, account_id: str, error: str) -> None:
    """Mark a paper account TICK_FAILED after an uncaught error during a scheduled
    tick (scripts/paper_tick.py's --loop). Merges into any alerts already on the
    account rather than replacing them, so a failed tick doesn't erase a prior
    STALE_INPUT/RISK_REJECTION the operator still needs to see. The error text is
    kept as ``last_error`` (truncated like ExperimentRow.error). A missing account
    is silently ignored: the caller has already logged the error and there is
    nothing left to mark."""
    with sessions.begin() as db:
        account = db.scalar(select(PaperRow).where(PaperRow.id == account_id).with_for_update())
        if account is not None:
            account.state = {
                **account.state,
                "alerts": sorted(set(account.state.get("alerts", [])) | {"TICK_FAILED"}),
                "last_error": error[:1000],
            }
