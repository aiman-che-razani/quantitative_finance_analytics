from datetime import date

from axiom.data.incremental import ingest_incremental
from axiom.data.stable import StableSyntheticProvider
from axiom.data.universe import UNIVERSE_60
from axiom.metadata import database
from axiom.platform import run_experiment
from axiom.settings import Settings

settings = Settings()
engine, sessions = database(settings.database_url)
first = ingest_incremental(
    sessions,
    settings.data_root,
    StableSyntheticProvider(),
    UNIVERSE_60,
    date(2015, 1, 1),
    date(2022, 1, 1),
    "synthetic-v2",
)
second = ingest_incremental(
    sessions,
    settings.data_root,
    StableSyntheticProvider(),
    UNIVERSE_60,
    date(2021, 12, 1),
    date(2026, 1, 1),
    "synthetic-v2",
)
print(
    "Dataset",
    second["dataset_id"],
    "rows",
    second["rows"],
    "overlap",
    second["duplicate_rows"],
    flush=True,
)
result = run_experiment(
    sessions, settings, second["dataset_id"], [i.symbol for i in UNIVERSE_60], "ema_trend"
)
print("Experiment", result["id"], "return", result["metrics"]["total_return"], flush=True)
engine.dispose()
