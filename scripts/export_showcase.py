import json
from pathlib import Path

from sqlalchemy import select

from axiom.metadata import DatasetRow, database
from axiom.platform import run_experiment
from axiom.settings import Settings

settings = Settings()
engine, sessions = database(settings.database_url)
reports = []
with sessions() as db:
    datasets = list(
        db.scalars(
            select(DatasetRow)
            .where(DatasetRow.provider.in_(["yahoo", "synthetic-v2"]))
            .order_by(DatasetRow.created_at.desc())
        )
    )
seen = set()
for dataset in datasets:
    if dataset.provider in seen:
        continue
    seen.add(dataset.provider)
    for strategy in ["ema_trend", "rsi_reversion", "buy_hold"]:
        result = run_experiment(sessions, settings, dataset.id, ["SPY"], strategy)
        equity = result["simulation"]["equity"]
        stride = max(1, len(equity) // 240)
        indices = sorted(set(range(0, len(equity), stride)) | {len(equity) - 1})
        metrics = {k: v for k, v in result["metrics"].items() if not isinstance(v, (list, dict))}
        reports.append(
            {
                "id": result["id"],
                "provenance": result["provenance"],
                "strategy": strategy,
                "provider": dataset.provider,
                "symbol": "SPY",
                "dataset_id": dataset.id,
                "metrics": metrics,
                "series": [
                    {
                        "date": equity[i]["timestamp"][:10],
                        "equity": equity[i]["equity"],
                        "benchmark": result["benchmark"]["equity"][i]["equity"],
                    }
                    for i in indices
                ],
                "monthly_returns": result["metrics"]["monthly_returns"],
            }
        )
output = Path("docs/showcase.json")
output.write_text(json.dumps(reports, indent=2), encoding="utf-8")
print("Exported", len(reports), "auditable research views")
engine.dispose()
