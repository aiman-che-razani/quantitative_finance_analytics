"""Durable experiments around immutable input snapshots."""

import hashlib
import json
import os
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import polars as pl

from axiom.analytics.extended import analyze
from axiom.backtest.events import ExecutionConfig, run_events
from axiom.common.models import FeatureConfig
from axiom.data.storage import SnapshotStore
from axiom.features.pipeline import FeaturePipeline
from axiom.metadata import DatasetRow, ExperimentRow


def run_experiment(
    sessions,
    settings,
    dataset_id,
    symbols,
    strategy="ema_trend",
    execution=None,
    features=None,
    kind="backtest",
    ml_options=None,
):
    execution = execution or ExecutionConfig()
    features = features or FeatureConfig()
    identity = str(uuid.uuid4())
    config = {
        "symbols": symbols,
        "strategy": strategy,
        "execution": execution.model_dump(),
        "features": features.model_dump(),
        "ml": ml_options or {},
    }
    with sessions.begin() as db:
        dataset = db.get(DatasetRow, dataset_id)
        if dataset is None or not symbols or not set(symbols) <= set(dataset.symbols):
            raise ValueError("Unknown dataset or symbols")
        provider = dataset.provider
        db.add(
            ExperimentRow(
                id=identity, kind=kind, status="RUNNING", dataset_id=dataset_id, config=config
            )
        )
    try:
        bars = (
            SnapshotStore(settings.data_root)
            .read(dataset_id)
            .filter(pl.col("instrument").is_in(symbols))
        )
        frame = FeaturePipeline(features).transform(bars)
        if kind == "ml":
            from axiom.ml.walkforward import walk_forward

            result = walk_forward(frame, execution, **(ml_options or {}))
        elif kind == "backtest":
            replay = run_events(frame, strategy, execution)
            benchmark = run_events(frame, "buy_hold", execution, first_index=replay["first_index"])
            result = {
                "simulation": replay,
                "benchmark": {"equity": benchmark["equity"], "metrics": analyze(benchmark)},
                "metrics": analyze(replay, benchmark),
            }
            returns = (
                frame.pivot(on="instrument", index="timestamp", values="simple_return")
                .drop("timestamp")
                .drop_nulls()
            )
            corr = np.atleast_2d(
                np.nan_to_num(np.corrcoef(returns.select(symbols).to_numpy(), rowvar=False))
            )
            result["asset_correlations"] = {
                s: {t: float(corr[i, j]) for j, t in enumerate(symbols)}
                for i, s in enumerate(symbols)
            }
        else:
            raise ValueError("Unknown experiment kind")
        commit = os.environ.get("GIT_COMMIT", "unavailable")
        dirty = None
        if shutil.which("git"):
            commit = (
                subprocess.run(
                    ["git", "rev-parse", "HEAD"], capture_output=True, text=True
                ).stdout.strip()
                or commit
            )
            dirty = bool(
                subprocess.run(
                    ["git", "status", "--porcelain"], capture_output=True, text=True
                ).stdout.strip()
            )
        source_root = Path(__file__).resolve().parent
        digest = hashlib.sha256()
        for source in sorted(source_root.rglob("*.py")):
            digest.update(source.relative_to(source_root).as_posix().encode())
            digest.update(source.read_bytes())
        result["provenance"] = {
            "dataset_id": dataset_id,
            "provider": provider,
            "code_commit": commit,
            "code_tree_sha256": digest.hexdigest(),
            "working_tree_dirty": dirty,
            "config": config,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        # Strict JSON also catches NaN leaking from analytics before persistence.
        json.dumps(result, allow_nan=False)
        with sessions.begin() as db:
            row = db.get(ExperimentRow, identity)
            row.status = "SUCCEEDED"
            row.result = result
            row.finished_at = datetime.now(timezone.utc)
        return {"id": identity, **result}
    except Exception as exc:
        with sessions.begin() as db:
            row = db.get(ExperimentRow, identity)
            row.status = "FAILED"
            row.error = str(exc)[:1000]
            row.finished_at = datetime.now(timezone.utc)
        raise
