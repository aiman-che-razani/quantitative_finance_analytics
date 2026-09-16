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
from axiom.common.models import UNIVERSE
from axiom.data.incremental import ingest_incremental
from axiom.data.stable import StableSyntheticProvider
from axiom.metadata import Base, database
from axiom.ml.walkforward import splits
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


def test_mark_serialization_optimization_preserves_replay(monkeypatch):
    from axiom.portfolio.account import Account

    config = ExecutionConfig(participation=0.1)
    optimized = run_events(event_frame(), "buy_hold", config)
    original = Account.mark

    def full_mark(self, prices, include_positions=True):
        return original(self, prices, include_positions=True)

    monkeypatch.setattr(Account, "mark", full_mark)
    assert run_events(event_frame(), "buy_hold", config) == optimized
