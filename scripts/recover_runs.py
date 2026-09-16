"""Explicit maintenance: mark old interrupted synchronous runs after stopping API workers."""

import argparse
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from axiom.metadata import ExperimentRow, database
from axiom.settings import Settings

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--older-than-hours", type=int, default=24)
args = parser.parse_args()
if args.older_than_hours < 1:
    parser.error("Minimum age is one hour")
engine, sessions = database(Settings().database_url)
with sessions.begin() as db:
    rows = list(
        db.scalars(
            select(ExperimentRow)
            .where(
                ExperimentRow.status == "RUNNING",
                ExperimentRow.created_at
                < datetime.now(timezone.utc) - timedelta(hours=args.older_than_hours),
            )
            .with_for_update()
        )
    )
    for row in rows:
        row.status = "INTERRUPTED"
        row.error = "Marked interrupted by explicit maintenance"
        row.finished_at = datetime.now(timezone.utc)
print("Marked", len(rows), "interrupted runs")
engine.dispose()
