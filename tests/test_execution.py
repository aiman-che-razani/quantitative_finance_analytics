import pytest

from axiom.backtest.events import target
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


@pytest.mark.parametrize(
    "config_kwargs,peak,day_start",
    [
        (
            {"max_drawdown": 0.05, "daily_loss_limit": 0.99, "portfolio_loss_limit": 0.99},
            10000,
            9000,
        ),
        (
            {"max_drawdown": 0.99, "daily_loss_limit": 0.05, "portfolio_loss_limit": 0.99},
            9000,
            10000,
        ),
        (
            {"max_drawdown": 0.99, "daily_loss_limit": 0.99, "portfolio_loss_limit": 0.05},
            9000,
            9000,
        ),
    ],
    ids=["max_drawdown", "daily_loss_limit", "portfolio_loss_limit"],
)
def test_loss_circuit_breakers_reject_in_isolation(config_kwargs, peak, day_start):
    # Long 100 SPY @ cost 100 (equity == account.initial == 10000), then marked
    # down to 90: equity drops to 9000, a realized 10% loss. Each case tightens
    # exactly one of the three loss-limit fields below that 10% and picks
    # peak/day_start so the OTHER two ratios are exactly 0 (not just loose),
    # isolating which check actually fires. The proposed order (+10, same
    # direction as the existing +100 position) is not risk-reducing, so it
    # reaches the equity/loss checks instead of being auto-approved.
    a = Account(10000)
    a.fill("SPY", 100, 100, 0, "t0", 0, "1")
    cfg = RiskConfig(**config_kwargs)
    decision = assess(a, "SPY", 10, 90, {"SPY": 90}, cfg, peak, day_start, 0)
    assert decision.action == "REJECT"
    assert decision.reason == "Portfolio loss circuit breaker"


def test_loss_circuit_breakers_allow_within_limits():
    # Same shape as above but a small 1% mark-to-market move and default
    # thresholds: none of the three circuit breakers should fire, and the
    # order should be approved/modified rather than rejected for any reason.
    a = Account(10000)
    a.fill("SPY", 10, 100, 0, "t0", 0, "1")
    decision = assess(a, "SPY", 10, 90, {"SPY": 90}, RiskConfig(), 10000, 10000, 0)
    assert decision.action in ("APPROVE", "MODIFY")
    assert decision.reason != "Portfolio loss circuit breaker"


@pytest.mark.parametrize(
    "strategy,row,current,expected",
    [
        ("ema_trend", {"close": 99, "ema": 100}, 1, 0),
        ("ema_trend", {"close": 101, "ema": 100}, 0, 1),
        ("ema_crossover", {"ema_fast": 101, "ema": 100}, 0, 1),
        ("ema_crossover", {"ema_fast": None, "ema": 100}, 1, 0),
        ("momentum", {"momentum": -0.1}, 1, 0),
        ("momentum", {"momentum": None}, 1, 0),
        ("rsi_reversion", {"rsi": 25}, 0, 1),
        ("rsi_reversion", {"rsi": 40}, 1, 1),
        ("rsi_reversion", {"rsi": 55}, 1, 0),
        ("bollinger_reversion", {"close": 89, "bb_lower": 90, "bb_middle": 100}, 0, 1),
        ("bollinger_reversion", {"close": 95, "bb_lower": 90, "bb_middle": 100}, 1, 1),
        ("bollinger_reversion", {"close": 101, "bb_lower": 90, "bb_middle": 100}, 1, 0),
        ("combined", {"close": 99, "ema": 98, "rsi": 40, "bb_middle": 100}, 0, 1),
        ("combined", {"close": 99, "ema": 98, "rsi": 50, "bb_middle": 100}, 1, 0),
    ],
)
def test_event_strategy_targets(strategy, row, current, expected):
    assert target({"ready": True, **row}, strategy, current) == expected
    assert target({"ready": False, **row}, strategy, current) == 0


def test_event_strategy_targets_go_short_only_when_allowed():
    row = {"ready": True, "close": 99, "ema": 100}
    assert target(row, "ema_trend", 1, allow_short=False) == 0
    assert target(row, "ema_trend", 1, allow_short=True) == -1
    with pytest.raises(ValueError, match="Unknown strategy"):
        target(row, "nope")


def test_risk_rejects_disabled_short_and_nonpositive_equity():
    account = Account(10000)
    cfg = RiskConfig()
    short = assess(account, "SPY", -10, 100, {"SPY": 100}, cfg, 10000, 10000, 0)
    assert (short.action, short.units, short.reason) == ("REJECT", 0, "Short positions disabled")
    account.fill("SPY", -100, 100, 0, "a", 0, "1")  # short 100 @ 100: cash 20000
    # SPY doubles: equity = 20000 - 100 * 200 = 0, checked before the loss breakers.
    broke = assess(account, "QQQ", 1, 100, {"SPY": 200}, cfg, 10000, 10000, 0)
    assert (broke.action, broke.reason) == ("REJECT", "Nonpositive equity")
