import json
from pathlib import Path

import polars as pl
from sqlalchemy import select

from axiom.common.models import FeatureConfig
from axiom.data.storage import SnapshotStore
from axiom.metadata import DatasetRow, database
from axiom.ml.walkforward import null_auc
from axiom.platform import run_experiment
from axiom.settings import Settings

settings = Settings()
engine, sessions = database(settings.database_url)
with sessions() as db:
    dataset = db.scalar(
        select(DatasetRow)
        .where(DatasetRow.provider == "synthetic-v2")
        .order_by(DatasetRow.created_at.desc())
    )
if dataset is None:
    raise SystemExit("No synthetic-v2 dataset; run scripts/demo_platform.py first")
result = run_experiment(sessions, settings, dataset.id, ["SPY"], kind="ml")
print("ML experiment", result["id"], "folds", len(result["folds"]))
bars = SnapshotStore(settings.data_root).read(dataset.id).filter(pl.col("instrument") == "SPY")
null = null_auc(bars, FeatureConfig(), surrogates=20)
engine.dispose()


summary = {
    "id": result["id"],
    "provenance": result["provenance"],
    "data_note": (
        "synthetic-v2 is a noise-free deterministic price formula, so near-perfect "
        "classification and trading metrics are expected; they validate software "
        "behaviour, not predictive skill."
    ),
    "pooled_test_auc": result["pooled_test_auc"],
    "null_auc_reference": null,
    "folds": result["folds"],
    "trading": {
        name: {k: v for k, v in entry["metrics"].items() if not isinstance(v, (list, dict))}
        for name, entry in result["out_of_sample_trading"].items()
    },
}
Path("docs/ml-validation.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
