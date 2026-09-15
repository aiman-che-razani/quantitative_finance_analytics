from datetime import UTC, datetime, timedelta

import polars as pl
import pytest

from axiom.backtest.engine import run
from axiom.common.models import BacktestConfig, FeatureConfig
from axiom.features.pipeline import FeaturePipeline
from axiom.strategies.simple import SimpleStrategy


def example(opens, closes):
    return pl.DataFrame(
        {
            "instrument": ["SPY"] * len(opens),
            "timestamp": [
                datetime(2020, 1, 1, tzinfo=UTC) + timedelta(days=i) for i in range(len(opens))
            ],
            "open": opens,
            "close": closes,
        }
    )


def test_next_open_execution_and_pnl_reconcile():
    bars = example([10.0, 20.0, 30.0, 40.0], [11.0, 22.0, 33.0, 44.0])
    result = run(
        bars,
        [1, 0, 0, 0],
        BacktestConfig(initial_capital=100, commission_bps_per_side=0, slippage_bps_per_side=0),
    )
    assert result.fills[0]["price"] == 20
    assert result.fills[0]["units"] == 5
    assert result.fills[1]["price"] == 30
    assert result.equity[-1]["equity"] == 150
    assert result.realized_pnl == 50
    for row in result.equity:
        assert row["cash"] + row["units"] * row["close"] == pytest.approx(row["equity"])


def test_costs_and_fractional_cash_constraint():
    bars = example([10.0, 10.0, 10.0], [10.0, 10.0, 10.0])
    cfg = BacktestConfig(initial_capital=100, commission_bps_per_side=10, slippage_bps_per_side=10)
    result = run(bars, [1, 0, 0], cfg)
    expected = 100 / (10.01 * 1.001) * 9.99 * 0.999
    assert result.equity[-1]["equity"] == pytest.approx(expected)
    assert all(row["cash"] >= 0 for row in result.equity)
    assert result.trades[0]["pnl"] == pytest.approx(expected - 100)


def test_last_signal_cannot_fill_on_same_close():
    result = run(example([10.0, 10.0, 10.0], [10.0, 10.0, 10.0]), [0, 0, 1], BacktestConfig())
    assert not result.fills
    assert result.equity[-1]["equity"] == 10000


def test_open_position_is_marked_not_force_liquidated():
    cfg = BacktestConfig(commission_bps_per_side=0, slippage_bps_per_side=0)
    result = run(example([10.0, 10.0, 10.0], [10.0, 10.0, 11.0]), [1, 1, 1], cfg)
    assert len(result.fills) == 1 and result.trades[0]["open"]
    assert result.unrealized_pnl == pytest.approx(1000)


def test_strategy_and_baseline_share_window(bars):
    features = FeaturePipeline(FeatureConfig()).transform(bars)
    config = BacktestConfig()
    strategy = run(features, SimpleStrategy().signals(features), config)
    baseline = run(
        features,
        SimpleStrategy("buy_hold").signals(features),
        config,
        first_index=strategy.first_index,
    )
    assert strategy.first_index == baseline.first_index == 200
    assert [row["timestamp"] for row in strategy.equity] == [
        row["timestamp"] for row in baseline.equity
    ]
    with pytest.raises(ValueError):
        run(features, [2] * features.height, config)
