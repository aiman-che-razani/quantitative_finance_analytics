import json
from pathlib import Path

from sqlalchemy import select

from axiom.metadata import DatasetRow, database
from axiom.platform import run_experiment
from axiom.settings import Settings

LABELS = {
    "synthetic-v2": {
        "data_kind": "SYNTHETIC",
        "disclaimer": (
            "Deterministic synthetic prices; validates software behaviour only, "
            "not predictive or trading skill."
        ),
    },
    "yahoo": {
        "data_kind": "OBSERVED",
        "disclaimer": (
            "Observed Yahoo daily prices, price-return only (dividends excluded); "
            "single hand-picked ETF, subject to selection bias; simulated backtest, "
            "not real trading."
        ),
    },
}
output = Path("docs/showcase.json")
previous = json.loads(output.read_text(encoding="utf-8")) if output.exists() else []

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
                **LABELS[dataset.provider],
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
# A provider with no local dataset (e.g. Yahoo on a machine without network access)
# keeps its previously exported records, relabelled; their provenance still names the
# commit that produced them, so regenerate on a machine that has the data.
for record in previous:
    if record["provider"] not in seen:
        reports.append({**record, **LABELS[record["provider"]]})
        print("Kept previous", record["provider"], record["strategy"], "record (not recomputed)")
order = {"yahoo": 0, "synthetic-v2": 1}
reports.sort(key=lambda record: order.get(record["provider"], 2))
output.write_text(json.dumps(reports, indent=2), encoding="utf-8")
print("Exported", len(reports), "auditable research views")
engine.dispose()
