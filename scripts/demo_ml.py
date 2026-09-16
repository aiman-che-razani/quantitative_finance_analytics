import json
from pathlib import Path

from sqlalchemy import select

from axiom.metadata import DatasetRow, database
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
result = run_experiment(sessions, settings, dataset.id, ["SPY"], kind="ml")
print("ML experiment", result["id"], "folds", len(result["folds"]))
engine.dispose()


summary = {
    "id": result["id"],
    "provenance": result["provenance"],
    "folds": result["folds"],
    "trading": {
        name: {k: v for k, v in entry["metrics"].items() if not isinstance(v, (list, dict))}
        for name, entry in result["out_of_sample_trading"].items()
    },
}
Path("docs/ml-validation.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
