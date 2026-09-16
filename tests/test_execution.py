import pytest

from axiom.backtest.orders import Order, execution_price
from axiom.portfolio.account import Account
from axiom.risk.engine import RiskConfig, assess


def test_reversal_reconciles_fees_and_short_profit():
    a = Account(10000)
    a.fill("SPY", 10, 100, 1, "a", 0, "1")
    a.fill("SPY", -15, 110, 1.5, "b", 1, "2")
    assert a.positions["SPY"].units == -5
    assert a.mark({"SPY": 90})["equity"] == pytest.approx(10197.5)
    a.fill("SPY", 5, 90, 0.5, "c", 2, "3")
    assert sum(t["pnl"] for t in a.trades) == pytest.approx(197)
    assert a.mark({"SPY": 90})["equity"] == pytest.approx(10197)


def test_stop_gap_and_limit_price_protection():
    bar = {"open": 110, "high": 115, "low": 95}
    assert execution_price(Order("1", "SPY", 1, "stop", stop=105), bar, 10) == pytest.approx(110.11)
    assert execution_price(Order("2", "SPY", 1, "limit", limit=100), bar, 10) == 100


def test_stop_limit_unknown_sequence_defers_fill():
    order = Order("1", "SPY", 1, "stop_limit", limit=106, stop=105)
    assert execution_price(order, {"open": 100, "high": 110, "low": 99}, 0) is None
    assert order.triggered
    assert execution_price(order, {"open": 104, "high": 110, "low": 99}, 0) == 104


def test_risk_clips_and_allows_exit_during_loss_halt():
    a = Account(10000)
    cfg = RiskConfig(max_concentration=0.1)
    d = assess(a, "SPY", 100, 100, {"SPY": 100}, cfg, 10000, 10000, 0)
    assert d.action == "MODIFY"
    assert d.units == 10
    a.fill("SPY", 10, 100, 0, "a", 0, "1")
    assert assess(a, "SPY", -10, 50, {"SPY": 50}, cfg, 20000, 20000, 0).action == "APPROVE"
    assert assess(a, "SPY", 1, 50, {"SPY": 50}, cfg, 20000, 20000, 0).action == "REJECT"


@pytest.mark.parametrize(
    "units,kind,limit,stop,expected",
    [
        (-1, "limit", 105, None, 110),
        (-1, "stop", None, 105, 105),
        (1, "stop_limit", 106, 105, None),
    ],
)
def test_sell_orders_and_gap_above_stop_limit(units, kind, limit, stop, expected):
    bar = {"open": 110, "high": 115, "low": 107}
    if kind == "stop":
        bar = {"open": 110, "high": 115, "low": 100}
    assert execution_price(Order("x", "SPY", units, kind, limit, stop), bar, 0) == expected


def test_short_leverage_reserves_commissions():
    account = Account(10000)
    config = RiskConfig(allow_short=True, max_leverage=1)
    decision = assess(account, "SPY", -200, 100, {"SPY": 100}, config, 10000, 10000, 0.01)
    account.fill("SPY", decision.units, 100, abs(decision.units) * 100 * 0.01, "a", 0, "1")
    assert account.mark({"SPY": 100})["leverage"] <= 1 + 1e-12
