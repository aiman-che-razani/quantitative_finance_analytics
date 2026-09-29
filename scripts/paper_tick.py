"""Scheduled completed-daily-bar ingestion and paper replay; no broker adapter."""

import argparse
import json
import time
from datetime import date, datetime, timedelta, timezone

from axiom.data.incremental import ingest_incremental
from axiom.data.providers import YahooProvider
from axiom.data.universe import UNIVERSE_60
from axiom.metadata import DatasetRow, PaperRow, database
from axiom.paper import advance, record_tick_failure
from axiom.settings import Settings

parser = argparse.ArgumentParser()
parser.add_argument("account")
parser.add_argument(
    "--live-data", action="store_true", help="Explicitly fetch newly completed Yahoo daily bars"
)
parser.add_argument("--loop", action="store_true")
parser.add_argument("--interval", type=int, default=900)
args = parser.parse_args()
if args.interval < 60:
    parser.error("Minimum polling interval is 60 seconds")
settings = Settings()
engine, sessions = database(settings.database_url)


def tick():
    today = datetime.now(timezone.utc).date()
    with sessions() as db:
        row = db.get(PaperRow, args.account)
        if row is None:
            raise ValueError("Unknown account")
        cfg = row.config
        state = row.state
        dataset = db.get(DatasetRow, cfg["dataset_id"])
        if args.live_data and dataset.provider != "yahoo":
            raise ValueError("Live data requires an existing Yahoo-backed account")
    identity = cfg["dataset_id"]
    if args.live_data:
        start = (
            date.fromisoformat(state["last_session"]) - timedelta(days=7)
            if state.get("last_session")
            else today - timedelta(days=14)
        )
        result = ingest_incremental(
            sessions,
            settings.data_root,
            YahooProvider(),
            [i for i in UNIVERSE_60 if i.symbol in dataset.symbols],
            start,
            today,
            "yahoo",
        )
        identity = result["dataset_id"]
    state = advance(sessions, settings, args.account, today - timedelta(days=1), identity)
    print(
        json.dumps(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "last_session": state["last_session"],
                "alerts": state["alerts"],
                "fills": len(state["fills"]),
            }
        ),
        flush=True,
    )


while True:
    try:
        tick()
    except Exception as exc:
        print(json.dumps({"alert": "TICK_FAILED", "error": str(exc)}), flush=True)
        try:
            record_tick_failure(
                sessions, args.account, f"{type(exc).__name__} (details in the tick log)"
            )
        except Exception as mark_exc:
            # e.g. the database is the thing that failed; keep the loop alive.
            print(json.dumps({"alert": "TICK_MARK_FAILED", "error": str(mark_exc)}), flush=True)
        if not args.loop:
            raise
    if not args.loop:
        break
    time.sleep(args.interval)
engine.dispose()
