import os
from datetime import date, datetime, timedelta, timezone

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
from axiom.ml.walkforward import splits, walk_forward
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
        assert db.get(PaperRow, identity).state["alerts"] == ["STALE_INPUT", "TICK_FAILED"]
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
