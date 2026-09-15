import numpy as np
import pytest
from polars.testing import assert_frame_equal

from axiom.common.models import FeatureConfig
from axiom.features.pipeline import FeaturePipeline, wilder_rsi


def test_feature_pipeline_is_causal(bars):
    pipeline = FeaturePipeline(FeatureConfig())
    full = pipeline.transform(bars)
    prefix = pipeline.transform(bars.head(300))
    assert_frame_equal(full.head(300), prefix)
    assert full["ready"].to_list().index(True) == 199


def test_wilder_rsi_monotonic_and_flat():
    assert wilder_rsi(np.arange(40, dtype=float) + 1, 26)[-1] == 100
    assert wilder_rsi(np.arange(40, dtype=float)[::-1] + 1, 26)[-1] == 0
    assert wilder_rsi(np.ones(40), 26)[-1] == 50
    assert all(value is None for value in wilder_rsi(np.ones(10), 26))


def test_bollinger_population_std_and_parameters(bars):
    cfg = FeatureConfig(bollinger_period=20, bollinger_std=1.19)
    result = FeaturePipeline(cfg).transform(bars)
    sample = bars["close"].to_numpy()[:20]
    assert result["bb_upper"][19] == pytest.approx(sample.mean() + 1.19 * sample.std(ddof=0))
    with pytest.raises(ValueError):
        FeatureConfig(bollinger_std=float("nan"))
    with pytest.raises(ValueError):
        FeatureConfig(ema_period=0)
