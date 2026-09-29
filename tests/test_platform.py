import os
import threading
from datetime import date, datetime, timedelta, timezone

import numpy as np
import polars as pl
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from axiom import paper
from axiom.api import create_app
from axiom.backtest.events import ExecutionConfig, run_events
from axiom.backtest.orders import Order
from axiom.common.models import UNIVERSE, FeatureConfig
from axiom.data.incremental import ingest_incremental
from axiom.data.providers import SyntheticProvider
from axiom.data.stable import StableSyntheticProvider
from axiom.data.validation import validate
from axiom.features.pipeline import FeaturePipeline
from axiom.metadata import Base, ExperimentRow, PaperRow, database
from axiom.ml.walkforward import null_auc, random_walk_surrogate, splits, walk_forward
from axiom.platform import run_experiment
from axiom.risk.engine import RiskConfig
from axiom.settings import Settings


def event_frame():
    return pl.DataFrame(
        {
            "instrument": ["SPY"] * 5,
            "timestamp": [
                datetime(2020, 1, 1, tzinfo=timezone.utc) + timedelta(days=i) for i in range(5)
            ],
            "open": [100.0] * 5,
            "high": [101.0] * 5,
            "low": [99.0] * 5,
            "close": [100.0] * 5,
            "volume": [10.0] * 5,
            "ready": [True] * 5,
        }
    )


def test_partial_fills_are_next_bar_and_reconcile():
    result = run_events(
        event_frame(),
        "buy_hold",
        ExecutionConfig(commission_bps=0, slippage_bps=0, spread_bps=0, participation=0.1),
        explicit_orders={0: [Order("1", "SPY", 3)]},
    )
    assert [f["units"] for f in result["fills"]] == [1, 1, 1]
    assert result["fills"][0]["timestamp"].startswith("2020-01-02")
    assert result["final"]["equity"] == 100000


def test_flat_signal_cancels_unfilled_entry():
    data = event_frame().with_columns(pl.Series("prediction", [1, 0, 0, 0, 0]))
    result = run_events(data, "ml", ExecutionConfig(order_type="limit", order_offset=0.1))
    assert result["pending_orders"] == []
    assert result["fills"] == []
    assert any(e["event_type"] == "CANCEL" for e in result["events"])


def test_horizon_purges_and_nonoverlapping_test_windows():
    previous_end = 0
    for a, b, c, d, e, f in splits(2000):
        assert b - 1 + 5 < c
        assert d - 1 + 5 < e
        assert e >= previous_end
        previous_end = f


def test_walk_forward_reports_all_four_models():
    # ~6 years of synthetic daily bars: enough past the 200-session feature
    # warm-up for several purged folds (train=504/validation=126/test=126),
    # without the ~17-fold cost a full multi-decade range would add.
    start, end = date(2015, 1, 1), date(2021, 1, 1)
    raw = SyntheticProvider().fetch(UNIVERSE[0], start, end)
    frame, report = validate(raw, "SPY", start, end)
    assert not report.missing_periods
    features = FeaturePipeline(FeatureConfig()).transform(frame)
    result = walk_forward(features, ExecutionConfig())
    names = {"naive", "logistic", "random_forest", "xgboost"}
    assert result["folds"], "expected at least one purged fold"
    for fold in result["folds"]:
        assert set(fold["models"]) == names
        for metrics in fold["models"].values():
            assert 0 <= metrics["accuracy"] <= 1
            assert 0 <= metrics["balanced_accuracy"] <= 1
            assert metrics["log_loss"] >= 0
            if metrics["roc_auc"] is not None:
                assert 0 <= metrics["roc_auc"] <= 1
    assert set(result["out_of_sample_trading"]) == names
    for trading in result["out_of_sample_trading"].values():
        assert trading["equity"]
        assert "sharpe" in trading["metrics"]
    assert set(result["pooled_test_auc"]) == names


def test_random_walk_surrogate_keeps_shape_and_volatility():
    start, end = date(2015, 1, 1), date(2021, 1, 1)
    frame, _ = validate(SyntheticProvider().fetch(UNIVERSE[0], start, end), "SPY", start, end)
    surrogate = random_walk_surrogate(frame, seed=3)
    assert surrogate.height == frame.height
    assert surrogate["volume"].to_list() == frame.sort("timestamp")["volume"].to_list()
    assert (surrogate["high"] >= surrogate["low"]).all()

    def vol(f):
        return float(np.std(np.diff(np.log(f["close"].to_numpy())), ddof=1))

    assert vol(surrogate) == pytest.approx(vol(frame), rel=0.1)
    assert random_walk_surrogate(frame, seed=3)["close"].to_list() == surrogate["close"].to_list()


@pytest.fixture
def pg(tmp_path):
    url = os.environ.get("AXIOM_TEST_DATABASE_URL")
    if not url:
        pytest.skip("AXIOM_TEST_DATABASE_URL required for PostgreSQL integration")
    engine, _ = database(url)
    Base.metadata.create_all(engine)
    with engine.connect() as connection:
        transaction = connection.begin()
        sessions = sessionmaker(
            connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        settings = Settings(
            database_url=url, api_token="test-token-01234567890123456789", data_root=tmp_path
        )
        yield sessions, settings
        transaction.rollback()
    engine.dispose()


def test_incremental_overlap_and_paper_idempotency(pg):
    sessions, settings = pg
    provider = StableSyntheticProvider()
    first = ingest_incremental(
        sessions,
        settings.data_root,
        provider,
        UNIVERSE[:1],
        date(2019, 1, 1),
        date(2021, 1, 1),
        "test-stable",
    )
    second = ingest_incremental(
        sessions,
        settings.data_root,
        provider,
        UNIVERSE[:1],
        date(2020, 12, 1),
        date(2022, 1, 1),
        "test-stable",
    )
    assert second["parent_id"] == first["dataset_id"]
    assert second["duplicate_rows"] > 0
    third = ingest_incremental(
        sessions,
        settings.data_root,
        provider,
        UNIVERSE[:1],
        date(2020, 12, 1),
        date(2022, 1, 1),
        "test-stable",
    )
    assert third["dataset_id"] == second["dataset_id"]
    identity = paper.create_account(
        sessions, second["dataset_id"], ["SPY"], "buy_hold", ExecutionConfig()
    )
    state = paper.advance(sessions, settings, identity, date(2021, 6, 1))
    again = paper.advance(sessions, settings, identity, date(2021, 6, 1))
    assert again == state
    later = paper.advance(sessions, settings, identity, date(2021, 12, 31))
    assert later["fills"][: len(state["fills"])] == state["fills"]
    with pytest.raises(ValueError, match="backwards"):
        paper.advance(sessions, settings, identity, date(2021, 1, 1))


def test_paper_stale_input_alert(pg):
    sessions, settings = pg
    dataset = ingest_incremental(
        sessions,
        settings.data_root,
        StableSyntheticProvider(),
        UNIVERSE[:1],
        date(2019, 1, 1),
        date(2021, 1, 1),
        "test-stable",
    )
    identity = paper.create_account(
        sessions, dataset["dataset_id"], ["SPY"], "buy_hold", ExecutionConfig()
    )
    # The dataset's last bar is near 2020-12-31; asking to advance to a much
    # later date (with no newer bars available) should surface STALE_INPUT.
    state = paper.advance(sessions, settings, identity, date(2021, 6, 1))
    assert "STALE_INPUT" in state["alerts"]


def test_paper_risk_rejection_alert(pg):
    sessions, settings = pg
    dataset = ingest_incremental(
        sessions,
        settings.data_root,
        StableSyntheticProvider(),
        UNIVERSE[:1],
        date(2019, 1, 1),
        date(2021, 1, 1),
        "test-stable",
    )
    # A concentration limit this tight caps the allowed position size below
    # assess()'s own 1e-8 "insufficient capital" floor regardless of price
    # (1e-9 alone is not tight enough against the 100000 default equity: it
    # clips to a tiny but still-approvable MODIFY instead of a REJECT), so
    # buy_hold's every attempted entry is rejected by the risk engine every
    # bar, and the last risk decision at replay time should carry a REJECT.
    identity = paper.create_account(
        sessions,
        dataset["dataset_id"],
        ["SPY"],
        "buy_hold",
        ExecutionConfig(risk=RiskConfig(max_concentration=1e-15)),
    )
    state = paper.advance(sessions, settings, identity, date(2020, 12, 31))
    assert "RISK_REJECTION" in state["alerts"]
    assert "STALE_INPUT" not in state["alerts"]


def test_record_tick_failure_merges_alerts(pg):
    # This is the part of scripts/paper_tick.py's --loop failure handling that
    # holds real logic (merge into existing alerts, don't clobber them);
    # extracted to axiom.paper so it's testable without driving the script's
    # CLI/sleep loop itself.
    sessions, settings = pg
    dataset = ingest_incremental(
        sessions,
        settings.data_root,
        StableSyntheticProvider(),
        UNIVERSE[:1],
        date(2019, 1, 1),
        date(2021, 1, 1),
        "test-stable",
    )
    identity = paper.create_account(
        sessions, dataset["dataset_id"], ["SPY"], "buy_hold", ExecutionConfig()
    )
    paper.record_tick_failure(sessions, identity, "boom")
    with sessions() as db:
        assert db.get(PaperRow, identity).state["alerts"] == ["TICK_FAILED"]
    with sessions.begin() as db:
        row = db.get(PaperRow, identity)
        row.state = {**row.state, "alerts": ["STALE_INPUT"]}
    paper.record_tick_failure(sessions, identity, "boom again")
    with sessions() as db:
        state = db.get(PaperRow, identity).state
        assert state["alerts"] == ["STALE_INPUT", "TICK_FAILED"]
        assert state["last_error"] == "boom again"
    # A missing account is a no-op, not an error (the caller already logged it).
    paper.record_tick_failure(sessions, "00000000-0000-0000-0000-000000000000", "boom")


def test_experiment_provenance_is_recorded(pg):
    sessions, settings = pg
    dataset = ingest_incremental(
        sessions,
        settings.data_root,
        StableSyntheticProvider(),
        UNIVERSE[:1],
        date(2019, 1, 1),
        date(2021, 1, 1),
        "test-stable",
    )
    result = run_experiment(
        sessions,
        settings,
        dataset["dataset_id"],
        ["SPY"],
        "buy_hold",
        ExecutionConfig(),
        FeatureConfig(),
        "backtest",
    )
    provenance = result["provenance"]
    assert provenance["dataset_id"] == dataset["dataset_id"]
    assert provenance["provider"] == "test-stable"
    assert provenance["code_commit"]
    assert len(provenance["code_tree_sha256"]) == 64
    assert provenance["config"]["strategy"] == "buy_hold"
    assert provenance["config"]["symbols"] == ["SPY"]
    assert provenance["created_at"]
    with sessions() as db:
        row = db.get(ExperimentRow, result["id"])
        assert row.status == "SUCCEEDED"
        assert row.result["provenance"]["dataset_id"] == dataset["dataset_id"]


def test_api_requires_authentication(pg):
    _, settings = pg
    with TestClient(create_app(settings)) as client:
        assert client.get("/health").status_code == 401
        assert (
            client.get("/health", headers={"Authorization": "Bearer " + settings.api_token}).json()[
                "status"
            ]
            == "ok"
        )
        assert (
            client.post(
                "/experiments",
                headers={"Authorization": "Bearer " + settings.api_token},
                json={"dataset_id": "../../etc", "symbols": ["SPY"]},
            ).status_code
            == 422
        )
        # Non-ASCII credentials must fail closed as 401, not crash compare_digest.
        assert (
            client.get("/health", headers=[(b"authorization", b"Bearer \xe9")]).status_code == 401
        )


def test_api_rejects_duplicate_symbols_and_unknown_accounts(pg):
    _, settings = pg
    auth = {"Authorization": "Bearer " + settings.api_token}
    with TestClient(create_app(settings)) as client:
        duplicate = client.post(
            "/experiments", headers=auth, json={"dataset_id": "a" * 64, "symbols": ["SPY", "SPY"]}
        )
        assert duplicate.status_code == 422
        missing = client.post(
            "/paper/00000000-0000-0000-0000-000000000000/advance",
            headers=auth,
            json={"as_of": "2020-06-01"},
        )
        assert missing.status_code == 404
        assert client.get("/experiments/not-a-uuid", headers=auth).status_code == 422


def test_advance_request_rejects_unknown_fields():
    from pydantic import ValidationError

    from axiom.api import AdvanceRequest

    with pytest.raises(ValidationError):
        AdvanceRequest.model_validate({"as_of": "2024-01-02", "bogus": 1})


def test_mark_serialization_optimization_preserves_replay(monkeypatch):
    from axiom.portfolio.account import Account

    config = ExecutionConfig(participation=0.1)
    optimized = run_events(event_frame(), "buy_hold", config)
    original = Account.mark

    def full_mark(self, prices, include_positions=True):
        return original(self, prices, include_positions=True)

    monkeypatch.setattr(Account, "mark", full_mark)
    assert run_events(event_frame(), "buy_hold", config) == optimized


@pytest.mark.parametrize(
    "exit_kwargs,exit_bar,exit_price",
    [
        ({"stop_loss": 0.05}, {"low": 90.0}, 95.0),
        ({"take_profit": 0.05}, {"high": 106.0}, 105.0),
    ],
)
def test_stop_loss_and_take_profit_exit_at_trigger_price(exit_kwargs, exit_bar, exit_price):
    frame = event_frame().with_columns(pl.lit(1e6).alias("volume"))
    for column, value in exit_bar.items():
        frame = frame.with_columns(
            pl.when(pl.int_range(pl.len()) == 2).then(value).otherwise(pl.col(column)).alias(column)
        )
    config = ExecutionConfig(
        commission_bps=0, slippage_bps=0, spread_bps=0, participation=1, **exit_kwargs
    )
    result = run_events(frame, "buy_hold", config)
    entry, exit_fill = result["fills"][0], result["fills"][1]
    # stop_loss also caps entry size via risk_per_trade: 100000 * 0.02 / 0.05 = 40000.
    expected_units = 400.0 if "stop_loss" in exit_kwargs else 1000.0
    assert entry["timestamp"].startswith("2020-01-02")
    assert entry["units"] == pytest.approx(expected_units)
    assert entry["price"] == pytest.approx(100.0)
    assert exit_fill["timestamp"].startswith("2020-01-03")
    assert exit_fill["units"] == pytest.approx(-expected_units)
    assert exit_fill["price"] == pytest.approx(exit_price)
    assert result["trades"][0]["pnl"] == pytest.approx(expected_units * (exit_price - 100.0))


class ShiftedStableProvider(StableSyntheticProvider):
    """Same dates as StableSyntheticProvider, every price 1% higher: a 'corrected' feed."""

    def fetch(self, instrument, start, end):
        frame = super().fetch(instrument, start, end)
        return frame.with_columns(pl.col(c) * 1.01 for c in ("open", "high", "low", "close"))


def test_paper_rejects_changed_history_and_foreign_provider(pg):
    sessions, settings = pg
    original = ingest_incremental(
        sessions,
        settings.data_root,
        StableSyntheticProvider(),
        UNIVERSE[:1],
        date(2019, 1, 1),
        date(2021, 1, 1),
        "test-stable",
    )
    identity = paper.create_account(
        sessions, original["dataset_id"], ["SPY"], "buy_hold", ExecutionConfig()
    )
    before = paper.advance(sessions, settings, identity, date(2020, 6, 1))
    # Same provider name and symbols, but different bars for already-replayed sessions.
    corrected = ingest_incremental(
        sessions,
        settings.data_root,
        ShiftedStableProvider(),
        UNIVERSE[:2],
        date(2019, 1, 1),
        date(2021, 1, 1),
        "test-stable",
    )
    with pytest.raises(ValueError, match="Previously processed bars changed"):
        paper.advance(sessions, settings, identity, date(2020, 12, 1), corrected["dataset_id"])
    foreign = ingest_incremental(
        sessions,
        settings.data_root,
        StableSyntheticProvider(),
        UNIVERSE[:1],
        date(2019, 1, 1),
        date(2021, 2, 1),  # different content, so not deduplicated onto the original row
        "test-other-provider",
    )
    with pytest.raises(ValueError, match="Incompatible dataset"):
        paper.advance(sessions, settings, identity, date(2020, 12, 1), foreign["dataset_id"])
    with pytest.raises(LookupError, match="Unknown paper account"):
        paper.advance(sessions, settings, "00000000-0000-0000-0000-000000000000", date(2020, 6, 1))
    with pytest.raises(ValueError, match="Only prior completed"):
        paper.advance(sessions, settings, identity, date.today())
    with sessions() as db:
        row = db.get(PaperRow, identity)
        assert row.state == before
        assert row.config["dataset_id"] == original["dataset_id"]


def test_failed_experiment_is_recorded_as_failed(pg):
    sessions, settings = pg
    # ~150 sessions: short of the 200-session EMA/Bollinger warm-up.
    dataset = ingest_incremental(
        sessions,
        settings.data_root,
        StableSyntheticProvider(),
        UNIVERSE[:1],
        date(2020, 6, 1),
        date(2021, 1, 1),
        "test-short",
    )
    with pytest.raises(ValueError, match="Insufficient feature warm-up"):
        run_experiment(
            sessions,
            settings,
            dataset["dataset_id"],
            ["SPY"],
            "ema_trend",
            ExecutionConfig(),
            FeatureConfig(),
            "backtest",
        )
    with sessions() as db:
        rows = (
            db.query(ExperimentRow).filter(ExperimentRow.dataset_id == dataset["dataset_id"]).all()
        )
        assert len(rows) == 1
        assert rows[0].status == "FAILED"
        assert "Insufficient feature warm-up" in rows[0].error
        assert rows[0].finished_at is not None
        assert rows[0].result is None


def test_incremental_conflicting_overlap_is_rejected_and_head_unchanged(pg):
    from axiom.metadata import HeadRow

    sessions, settings = pg
    first = ingest_incremental(
        sessions,
        settings.data_root,
        StableSyntheticProvider(),
        UNIVERSE[:1],
        date(2019, 1, 1),
        date(2021, 1, 1),
        "test-conflict",
    )
    with pytest.raises(ValueError, match="Conflicting overlap"):
        ingest_incremental(
            sessions,
            settings.data_root,
            ShiftedStableProvider(),
            UNIVERSE[:1],
            date(2020, 12, 1),
            date(2022, 1, 1),
            "test-conflict",
        )
    with sessions() as db:
        heads = db.query(HeadRow).filter(HeadRow.dataset_id == first["dataset_id"]).all()
        assert len(heads) == 1


def test_api_experiment_and_paper_round_trip(pg, monkeypatch):
    sessions, settings = pg
    dataset = ingest_incremental(
        sessions,
        settings.data_root,
        StableSyntheticProvider(),
        UNIVERSE[:1],
        date(2019, 1, 1),
        date(2021, 1, 1),
        "test-stable",
    )
    monkeypatch.setattr("axiom.api.database", lambda url: (sessions.kw["bind"].engine, sessions))
    headers = {"Authorization": "Bearer " + settings.api_token}
    body = {"dataset_id": dataset["dataset_id"], "symbols": ["SPY"], "strategy": "buy_hold"}
    with TestClient(create_app(settings)) as client:
        created = client.post("/experiments", headers=headers, json=body)
        assert created.status_code == 200
        fetched = client.get(f"/experiments/{created.json()['id']}", headers=headers).json()
        assert fetched["status"] == "SUCCEEDED"
        assert fetched["result"]["provenance"]["dataset_id"] == dataset["dataset_id"]
        missing = client.get("/experiments/00000000-0000-0000-0000-000000000000", headers=headers)
        assert missing.status_code == 404
        ml = client.post("/experiments", headers=headers, json={**body, "strategy": "ml"})
        assert ml.status_code == 422
        qqq = client.post("/experiments", headers=headers, json={**body, "symbols": ["QQQ"]})
        assert qqq.status_code == 422
        market = client.get(f"/market/{dataset['dataset_id']}?symbol=QQQ", headers=headers)
        assert market.status_code == 404
        account = client.post("/paper", headers=headers, json=body).json()["id"]
        advanced = client.post(
            f"/paper/{account}/advance", headers=headers, json={"as_of": "2020-12-31"}
        )
        assert advanced.status_code == 200
        assert advanced.json()["fills"]
        backwards = client.post(
            f"/paper/{account}/advance", headers=headers, json={"as_of": "2020-06-01"}
        )
        assert backwards.status_code == 409
        tuned = client.post(
            "/paper", headers=headers, json={**body, "features": {"ema_period": 50}}
        ).json()["id"]
        with sessions() as db:
            assert db.get(PaperRow, tuned).config["features"]["ema_period"] == 50
        assert (
            client.post("/paper", headers=headers, json={**body, "kind": "ml"}).status_code == 422
        )
    busy = threading.BoundedSemaphore(1)
    busy.acquire()
    monkeypatch.setattr("axiom.api.threading.BoundedSemaphore", lambda n: busy)
    with TestClient(create_app(settings)) as client:
        assert client.post("/experiments", headers=headers, json=body).status_code == 429


def test_take_profit_does_not_replace_a_market_exit_filling_at_the_open():
    # Long from day 1; the day-2 close signals flat, so the exit fills at the day-3 open
    # (101). Day 3's high of 120 must not upgrade that exit to the 5% take-profit limit.
    frame = event_frame().with_columns(
        pl.lit(1e9).alias("volume"),
        pl.Series("prediction", [1, 1, 0, 0, 0]),
        pl.Series("open", [100.0, 100.0, 100.0, 101.0, 101.0]),
        pl.Series("high", [101.0, 101.0, 101.0, 120.0, 102.0]),
    )
    config = ExecutionConfig(
        commission_bps=0, slippage_bps=0, spread_bps=0, participation=1, take_profit=0.05
    )
    result = run_events(frame, "ml", config)
    exit_fill = result["fills"][1]
    assert exit_fill["timestamp"].startswith("2020-01-04")
    assert exit_fill["price"] == pytest.approx(101.0)


def test_fill_size_is_capped_by_prior_bar_volume_not_execution_day_volume():
    # The day-2 open fill may only use volume known at the day-1 close.
    frame = event_frame().with_columns(pl.Series("volume", [100.0, 1e9, 1e9, 1e9, 1e9]))
    config = ExecutionConfig(commission_bps=0, slippage_bps=0, spread_bps=0, participation=0.1)
    first = run_events(frame, "buy_hold", config)["fills"][0]
    assert first["timestamp"].startswith("2020-01-02")
    assert first["units"] == pytest.approx(10.0)


def test_successful_repeat_tick_clears_tick_failure(pg):
    sessions, settings = pg
    dataset = ingest_incremental(
        sessions,
        settings.data_root,
        StableSyntheticProvider(),
        UNIVERSE[:1],
        date(2019, 1, 1),
        date(2021, 1, 1),
        "test-stable",
    )
    identity = paper.create_account(
        sessions, dataset["dataset_id"], ["SPY"], "buy_hold", ExecutionConfig()
    )
    paper.advance(sessions, settings, identity, date(2020, 12, 31))
    with sessions() as db:
        before = db.get(PaperRow, identity).updated_at
    paper.record_tick_failure(sessions, identity, "TimeoutError (details in the tick log)")
    with sessions() as db:
        assert db.get(PaperRow, identity).updated_at > before
    state = paper.advance(sessions, settings, identity, date(2021, 1, 2))
    assert "TICK_FAILED" not in state["alerts"] and "last_error" not in state


def test_paper_stale_alert_persists_on_repeat_ticks_without_new_bars(pg):
    sessions, settings = pg
    dataset = ingest_incremental(
        sessions,
        settings.data_root,
        StableSyntheticProvider(),
        UNIVERSE[:1],
        date(2019, 1, 1),
        date(2021, 1, 1),
        "test-stable",
    )
    identity = paper.create_account(
        sessions, dataset["dataset_id"], ["SPY"], "buy_hold", ExecutionConfig()
    )
    paper.advance(sessions, settings, identity, date(2020, 12, 31))
    first = paper.advance(sessions, settings, identity, date(2021, 1, 2))
    assert "STALE_INPUT" not in first["alerts"]
    for as_of in (date(2021, 6, 1), date(2021, 6, 2)):
        alerts = paper.advance(sessions, settings, identity, as_of)["alerts"]
        assert alerts.count("STALE_INPUT") == 1


def test_null_auc_summarises_every_model_deterministically():
    start, end = date(2015, 1, 1), date(2021, 1, 1)
    frame, _ = validate(SyntheticProvider().fetch(UNIVERSE[0], start, end), "SPY", start, end)
    result = null_auc(frame, FeatureConfig(), surrogates=2)
    assert result["surrogates"] == 2
    assert set(result["models"]) == {"naive", "logistic", "random_forest", "xgboost"}
    for stats in result["models"].values():
        assert 0 <= stats["mean"] <= stats["p95"] <= 1
    assert null_auc(frame, FeatureConfig(), surrogates=2) == result


def test_api_list_and_market_endpoints_return_recorded_rows(pg, monkeypatch):
    sessions, settings = pg
    dataset = ingest_incremental(
        sessions,
        settings.data_root,
        StableSyntheticProvider(),
        UNIVERSE[:1],
        date(2019, 1, 1),
        date(2021, 1, 1),
        "test-stable",
    )
    monkeypatch.setattr("axiom.api.database", lambda url: (sessions.kw["bind"].engine, sessions))
    headers = {"Authorization": "Bearer " + settings.api_token}
    body = {"dataset_id": dataset["dataset_id"], "symbols": ["SPY"], "strategy": "buy_hold"}
    with TestClient(create_app(settings)) as client:
        experiment = client.post("/experiments", headers=headers, json=body).json()["id"]
        account = client.post("/paper", headers=headers, json=body).json()["id"]
        row = next(
            d
            for d in client.get("/datasets", headers=headers).json()
            if d["id"] == dataset["dataset_id"]
        )
        assert row["symbols"] == ["SPY"] and row["rows"] > 200
        listed = client.get("/experiments", headers=headers).json()
        assert any(e["id"] == experiment and e["status"] == "SUCCEEDED" for e in listed)
        assert all("result" not in e for e in listed)
        assert any(a["id"] == account for a in client.get("/paper", headers=headers).json())
        bars = client.get(f"/market/{dataset['dataset_id']}?symbol=SPY", headers=headers).json()
        assert 0 < len(bars) <= 3000
        assert {"timestamp", "open", "high", "low", "close", "volume"} <= set(bars[0])
        assert "ml" not in client.get("/strategies", headers=headers).json()["strategies"]
        assert client.get("/instruments", headers=headers).status_code == 200
        unknown = client.post(
            "/paper/00000000-0000-0000-0000-000000000000/advance",
            headers=headers,
            json={"as_of": "2020-12-31"},
        )
        assert unknown.status_code == 404
        paper_ml = client.post("/paper", headers=headers, json={**body, "strategy": "ml"})
        assert paper_ml.status_code == 422


def test_incremental_ingest_rejects_a_gap_and_keeps_the_head(pg):
    sessions, settings = pg
    provider = StableSyntheticProvider()
    first = ingest_incremental(
        sessions,
        settings.data_root,
        provider,
        UNIVERSE[:1],
        date(2019, 1, 1),
        date(2020, 1, 1),
        "gap",
    )
    with pytest.raises(ValueError, match="would create a gap"):
        ingest_incremental(
            sessions,
            settings.data_root,
            provider,
            UNIVERSE[:1],
            date(2020, 6, 1),
            date(2021, 1, 1),
            "gap",
        )
    again = ingest_incremental(
        sessions,
        settings.data_root,
        provider,
        UNIVERSE[:1],
        date(2019, 1, 1),
        date(2020, 1, 1),
        "gap",
    )
    assert again["dataset_id"] == first["dataset_id"]
