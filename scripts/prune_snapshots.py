"""List (and with --delete, remove) snapshot directories no dataset row refers to.

Covers staging leftovers (``*.partial-*``), set-aside corrupt publishes (``*.corrupt-*``)
and published snapshots whose ingest transaction rolled back after the write. Dry run by
default. Directories modified in the last --min-age-minutes are skipped, because an
in-flight ingest publishes its snapshot before its dataset row commits. Deleting is
refused when the database knows no datasets at all (a wrong or empty DATABASE_URL would
otherwise mark every snapshot as debris) unless --force is given.
"""

import argparse
import shutil
import sys
import time

from sqlalchemy import make_url, select

from axiom.metadata import DatasetRow, database
from axiom.settings import Settings

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--delete", action="store_true", help="remove what is listed")
parser.add_argument("--min-age-minutes", type=float, default=60.0)
parser.add_argument("--force", action="store_true", help="delete even if no dataset rows exist")
args = parser.parse_args()
settings = Settings()
url = make_url(settings.database_url)
print(f"Database {url.host}:{url.port}/{url.database}; data root {settings.data_root.resolve()}")
engine, sessions = database(settings.database_url)
with sessions() as db:
    known = set(db.scalars(select(DatasetRow.id)))
engine.dispose()
validated = settings.data_root / "validated"
cutoff = time.time() - args.min_age_minutes * 60
candidates = (
    sorted(path for path in validated.iterdir() if path.is_dir() and path.name not in known)
    if validated.exists()
    else []
)
orphans = [path for path in candidates if path.stat().st_mtime < cutoff]
if len(candidates) > len(orphans):
    print(f"Skipped {len(candidates) - len(orphans)} directories younger than the minimum age")
if args.delete and orphans and not known and not args.force:
    sys.exit(
        "Refusing to delete: this database has no dataset rows. Check DATABASE_URL or pass --force."
    )
for path in orphans:
    print(("Deleting " if args.delete else "Orphan ") + str(path))
    if args.delete:
        shutil.rmtree(path)
print(f"{len(orphans)} orphaned snapshot directories" + ("" if args.delete else " (dry run)"))
