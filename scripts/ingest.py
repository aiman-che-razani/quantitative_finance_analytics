"""Explicit provider ingestion; Yahoo failures never fall back to synthetic data."""

import argparse
import json
from datetime import date

from axiom.data.incremental import ingest_incremental
from axiom.data.providers import YahooProvider
from axiom.data.stable import StableSyntheticProvider
from axiom.data.universe import UNIVERSE_60
from axiom.metadata import database
from axiom.settings import Settings

parser = argparse.ArgumentParser()
parser.add_argument("--provider", choices=["synthetic", "yahoo"], required=True)
parser.add_argument("--symbols", default="SPY,QQQ,TLT")
parser.add_argument("--start", type=date.fromisoformat, required=True)
parser.add_argument("--end", type=date.fromisoformat, required=True)
args = parser.parse_args()
if args.end > date.today() or args.end <= args.start:
    parser.error("Require start < end <= today (end exclusive)")
requested = set(args.symbols.upper().split(","))
universe = [i for i in UNIVERSE_60 if i.symbol in requested]
if {i.symbol for i in universe} != requested:
    parser.error("Unknown instrument")
settings = Settings()
engine, sessions = database(settings.database_url)
provider = StableSyntheticProvider() if args.provider == "synthetic" else YahooProvider()
result = ingest_incremental(
    sessions,
    settings.data_root,
    provider,
    universe,
    args.start,
    args.end,
    "synthetic-v2" if args.provider == "synthetic" else "yahoo",
)
print(json.dumps({k: v for k, v in result.items() if k != "instruments"}, indent=2))
engine.dispose()
