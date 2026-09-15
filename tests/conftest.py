from datetime import date

import pytest

from axiom.common.models import UNIVERSE
from axiom.data.providers import SyntheticProvider
from axiom.data.validation import validate


@pytest.fixture
def bars():
    start, end = date(2020, 1, 1), date(2022, 1, 1)
    raw = SyntheticProvider().fetch(UNIVERSE[0], start, end)
    frame, report = validate(raw, "SPY", start, end)
    assert not report.missing_periods
    return frame
