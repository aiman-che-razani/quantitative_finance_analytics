import numpy as np

from axiom.features.kernels import numba_mean, numpy_mean, polars_mean, python_mean


def test_rolling_kernels_agree_on_warmup_and_values():
    values = np.random.default_rng(42).normal(size=1000)
    expected = numpy_mean(values, 20)
    for kernel in [python_mean, polars_mean, numba_mean]:
        np.testing.assert_allclose(kernel(values, 20), expected, atol=1e-12, equal_nan=True)


def test_native_matches_reference_when_built():
    import os
    from pathlib import Path

    import pytest

    from axiom.features.kernels import native_mean

    library = Path("native") / ("rolling.dll" if os.name == "nt" else "rolling.so")
    if not library.exists():
        pytest.skip("Run scripts/build_native.py first")
    values = np.random.default_rng(17).normal(size=1000)
    np.testing.assert_allclose(
        native_mean(values, 26), numpy_mean(values, 26), atol=1e-12, equal_nan=True
    )
