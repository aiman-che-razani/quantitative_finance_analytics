import json
from datetime import date

from axiom.common.models import UNIVERSE, BacktestConfig, FeatureConfig
from axiom.data.providers import SyntheticProvider
from axiom.research import ingest, research


def test_ten_instrument_research_reproducible(tmp_path):
    quality = ingest(
        SyntheticProvider(42), UNIVERSE, date(2020, 1, 1), date(2022, 1, 1), tmp_path / "data"
    )
    assert quality["eligible_for_research"]
    repeated = ingest(
        SyntheticProvider(42), UNIVERSE, date(2020, 1, 1), date(2022, 1, 1), tmp_path / "data"
    )
    assert quality["dataset_id"] == repeated["dataset_id"]
    args = (
        tmp_path / "data",
        quality["dataset_id"],
        tmp_path / "reports",
        FeatureConfig(),
        BacktestConfig(),
    )
    first = research(*args)
    second = research(*args)
    assert first["instruments"] == second["instruments"]
    assert len(first["instruments"]) == 10
    assert first["price_basis"] == ["synthetic"]
    assert first["experiment_id"] != second["experiment_id"]
    assert (
        json.loads((tmp_path / "reports" / first["experiment_id"] / "report.json").read_text())[
            "dataset_id"
        ]
        == quality["dataset_id"]
    )


def test_missing_session_does_not_publish_research_snapshot(tmp_path):
    class MissingProvider:
        def fetch(self, instrument, start, end):
            return SyntheticProvider().fetch(instrument, start, end).slice(1)

    quality = ingest(MissingProvider(), UNIVERSE[:1], date(2020, 1, 1), date(2022, 1, 1), tmp_path)
    assert not quality["eligible_for_research"]
    assert "dataset_id" not in quality
    assert list((tmp_path / "quality").glob("*.json"))
