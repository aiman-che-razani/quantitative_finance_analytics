"""List (and with --delete, remove) snapshot directories no dataset row refers to.

Covers staging leftovers (``*.partial-*``), set-aside corrupt publishes (``*.corrupt-*``)
and published snapshots whose ingest transaction rolled back after the write. Dry run by
default; stop ingestion before deleting so an in-flight write is not mistaken for debris.
"""

import argparse
import shutil

from sqlalchemy import select

from axiom.metadata import DatasetRow, database
from axiom.settings import Settings

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--delete", action="store_true", help="remove what is listed")
args = parser.parse_args()
settings = Settings()
engine, sessions = database(settings.database_url)
with sessions() as db:
    known = set(db.scalars(select(DatasetRow.id)))
engine.dispose()
validated = settings.data_root / "validated"
orphans = (
    sorted(path for path in validated.iterdir() if path.is_dir() and path.name not in known)
    if validated.exists()
    else []
)
for path in orphans:
    print(("Deleting " if args.delete else "Orphan ") + str(path))
    if args.delete:
        shutil.rmtree(path)
print(f"{len(orphans)} orphaned snapshot directories" + ("" if args.delete else " (dry run)"))
