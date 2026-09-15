import pytest

from axiom.analytics.metrics import summarize
from axiom.backtest.engine import BacktestResult
from axiom.common.models import BacktestConfig


def test_metrics_include_initial_equity_and_null_undefined_ratios():
    rows = [
        dict(timestamp=f"2020-01-0{i + 1}T00:00:00+00:00", equity=value, exposure=0.0)
        for i, value in enumerate((100.0, 80.0, 100.0))
    ]
    result = BacktestResult(rows, [], [], 1, 0, 0)
    metrics = summarize(result, BacktestConfig(initial_capital=100))
    assert metrics["total_return"] == 0
    assert metrics["max_drawdown"] == pytest.approx(-0.2)
    assert metrics["win_rate"] is None and metrics["profit_factor"] is None
    for row in rows:
        row["equity"] = 100.0
    assert summarize(result, BacktestConfig(initial_capital=100))["sharpe"] is None
