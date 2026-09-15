"""V0.1 orchestration and reproducible experiment output."""

import json
import subprocess
import time
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

import polars as pl

from axiom import __version__
from axiom.analytics.metrics import summarize
from axiom.backtest.engine import run
from axiom.common.models import BacktestConfig, FeatureConfig, Instrument
from axiom.data.providers import Provider
from axiom.data.storage import SnapshotStore
from axiom.data.validation import validate
from axiom.features.pipeline import FeaturePipeline
from axiom.strategies.simple import SimpleStrategy


def ingest(
    provider: Provider, universe: list[Instrument], start: date, end: date, root: Path
) -> dict[str, Any]:
    started = time.perf_counter()
    store = SnapshotStore(root)
    frames, reports = [], {}
    for instrument in universe:
        raw = provider.fetch(instrument, start, end)
        capture = store.capture(instrument.symbol, raw)
        validated, quality = validate(raw, instrument.symbol, start, end)
        reports[instrument.symbol] = dict(quality.to_dict(), raw_capture=str(capture))
        frames.append(validated)
    report_id = str(uuid.uuid4())
    destination = root / "quality" / f"{report_id}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    eligible = all(
        not report["rejected_records"]
        and not report["missing_periods"]
        and report["accepted_rows"] > 0
        for report in reports.values()
    )
    report = dict(
        report_id=report_id,
        instruments=reports,
        eligible_for_research=eligible,
        duration_s=time.perf_counter() - started,
        start=start.isoformat(),
        end_exclusive=end.isoformat(),
    )
    combined = pl.concat(frames)
    if combined.height and eligible:
        report["dataset_id"] = store.write(combined)
    report["duration_s"] = time.perf_counter() - started
    destination.write_text(json.dumps(report, indent=2))
    return report


def research(
    root: Path,
    dataset_id: str,
    output: Path,
    feature_config: FeatureConfig,
    backtest_config: BacktestConfig,
    strategy: Literal["ema_trend", "rsi_reversion", "combined", "buy_hold"] = "ema_trend",
) -> dict[str, Any]:
    started = time.perf_counter()
    bars = SnapshotStore(root).read(dataset_id)
    from datetime import timedelta

    for group in bars.partition_by("instrument"):
        symbol = group["instrument"][0]
        first = group["timestamp"].min()
        last = group["timestamp"].max()
        if not isinstance(first, datetime) or not isinstance(last, datetime):
            raise ValueError("expected a nonempty datetime series")
        _, quality = validate(
            group,
            symbol,
            first.date(),
            last.date() + timedelta(days=1),
        )
        if quality.missing_periods or quality.rejected_records:
            raise ValueError("research requires complete validated sessions; inspect data quality")
    features = FeaturePipeline(feature_config).transform(bars)
    identity = str(uuid.uuid4())
    target = output / identity
    target.mkdir(parents=True, exist_ok=False)
    features.write_parquet(target / "features.parquet")
    results = {}
    for group in features.partition_by("instrument"):
        symbol = group["instrument"][0]
        signals = SimpleStrategy(strategy).signals(group)
        strategy_result = run(group, signals, backtest_config)
        benchmark = run(
            group,
            SimpleStrategy("buy_hold").signals(group),
            backtest_config,
            first_index=strategy_result.first_index,
        )
        values = {}
        for label, result in (("strategy", strategy_result), ("buy_and_hold", benchmark)):
            pl.DataFrame(result.equity).write_csv(target / f"{symbol}-{label}-equity.csv")
            (target / f"{symbol}-{label}-ledger.json").write_text(
                json.dumps({"fills": result.fills, "trades": result.trades}, indent=2)
            )
            values[label] = summarize(result, backtest_config)
        results[symbol] = dict(
            values,
            start=strategy_result.equity[0]["timestamp"],
            end=strategy_result.equity[-1]["timestamp"],
            evaluation_bars=len(strategy_result.equity) - 1,
        )
    code_root = Path(__file__).resolve().parents[1]
    code_commit = None
    working_tree_dirty = None
    if (code_root / ".git").exists():
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=code_root, capture_output=True, text=True
        )
        status = subprocess.run(
            ["git", "status", "--porcelain"], cwd=code_root, capture_output=True, text=True
        )
        code_commit = revision.stdout.strip() if revision.returncode == 0 else None
        working_tree_dirty = bool(status.stdout.strip()) if status.returncode == 0 else None
    report = dict(
        experiment_id=identity,
        axiom_version=__version__,
        dataset_id=dataset_id,
        code_commit=code_commit,
        working_tree_dirty=working_tree_dirty,
        strategy=strategy,
        feature_config=feature_config.model_dump(),
        backtest_config=backtest_config.model_dump(),
        source=bars["source"].unique().sort().to_list(),
        price_basis=bars["price_basis"].unique().sort().to_list(),
        assumptions={
            "execution": "previous close signal, next session open",
            "positions": "fractional long/flat",
            "accounts": "one independent account per symbol; not a multiasset portfolio",
            "cash_yield": 0,
            "dividends": "excluded: price returns only",
            "end_position": "marked, not liquidated",
            "annualization": "252 daily returns; CAGR uses actual elapsed calendar days",
            "risk_free_rate": 0,
        },
        instruments=results,
        duration_s=time.perf_counter() - started,
    )
    (target / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False))
    return dict(report, output=str(target))
