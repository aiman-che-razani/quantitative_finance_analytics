"""Command-line V0.1 workflows. Global directory options precede the subcommand."""

import argparse
import json
import logging
from datetime import date
from pathlib import Path
from typing import Any

from axiom.common.models import UNIVERSE, BacktestConfig, FeatureConfig
from axiom.data.providers import CSVProvider, Provider, SyntheticProvider, YahooProvider
from axiom.research import ingest, research


def main() -> None:
    parser = argparse.ArgumentParser(description="Axiom V0.1: reproducible daily-bar research")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--output", type=Path, default=Path("reports"))
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("demo", "ingest"):
        command = sub.add_parser(name)
        command.add_argument("--start", type=date.fromisoformat, default=date(2020, 1, 1))
        command.add_argument("--end", type=date.fromisoformat, default=date(2025, 1, 1))
        command.add_argument(
            "--symbols", nargs="+", default=[instrument.symbol for instrument in UNIVERSE]
        )
        command.add_argument("--seed", type=int, default=42)
        if name == "ingest":
            command.add_argument("--provider", choices=["csv", "yahoo", "synthetic"], required=True)
            command.add_argument("--csv-dir", type=Path)
    command = sub.add_parser("research")
    command.add_argument("--dataset", required=True)
    command.add_argument(
        "--strategy",
        choices=["ema_trend", "rsi_reversion", "combined", "buy_hold"],
        default="ema_trend",
    )
    command.add_argument(
        "--config", type=Path, help="JSON with features and backtest configuration"
    )
    sub.add_parser("universe")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    result: Any
    if args.command == "universe":
        result = [instrument.model_dump(mode="json") for instrument in UNIVERSE]
    elif args.command == "research":
        settings = json.loads(args.config.read_text()) if args.config else {}
        if set(settings) - {"features", "backtest"}:
            parser.error("configuration accepts features and backtest sections only")
        result = research(
            args.data,
            args.dataset,
            args.output,
            FeatureConfig(**settings.get("features", {})),
            BacktestConfig(**settings.get("backtest", {})),
            args.strategy,
        )
    else:
        wanted = set(args.symbols)
        universe = [instrument for instrument in UNIVERSE if instrument.symbol in wanted]
        if len(universe) != len(wanted):
            parser.error("symbols must belong to the initial universe")
        provider: Provider = SyntheticProvider(args.seed)
        if args.command == "ingest":
            if args.provider == "yahoo":
                provider = YahooProvider()
            elif args.provider == "csv":
                if args.csv_dir is None:
                    parser.error("CSV provider requires --csv-dir")
                provider = CSVProvider(args.csv_dir)
        quality = ingest(provider, universe, args.start, args.end, args.data)
        if not quality["eligible_for_research"]:
            print(json.dumps(quality, indent=2))
            raise SystemExit(
                "Data-quality gate failed; inspect saved quality report. No research run executed."
            )
        if args.command == "demo":
            result = research(
                args.data, quality["dataset_id"], args.output, FeatureConfig(), BacktestConfig()
            )
        else:
            result = quality
    print(json.dumps(result, indent=2, allow_nan=False))
