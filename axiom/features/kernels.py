"""Equivalent rolling-mean kernels for measured backend comparisons."""

import ctypes
import os
from collections.abc import Callable
from pathlib import Path

import numpy as np
import polars as pl
from numba import njit


def python_mean(values, window):
    output = np.full(len(values), np.nan)
    total = 0.0
    for i, value in enumerate(values):
        total += float(value)
        if i >= window:
            total -= float(values[i - window])
        if i >= window - 1:
            output[i] = total / window
    return output


numba_mean: Callable[[np.ndarray, int], np.ndarray] = njit(cache=True)(python_mean)


def numpy_mean(values, window):
    output = np.full(len(values), np.nan)
    if len(values) >= window:
        output[window - 1 :] = np.convolve(values, np.ones(window) / window, mode="valid")
    return output


def polars_mean(values, window):
    return pl.Series(values).rolling_mean(window).to_numpy()


def native_mean(values, window):
    if window < 1:
        raise ValueError("Positive window required")
    library = (
        Path(__file__).resolve().parents[2]
        / "native"
        / ("rolling.dll" if os.name == "nt" else "rolling.so")
    )
    if not library.exists():
        # e.g. the Docker image, which does not build native/; a clear 422, not a 500.
        raise ValueError("native rolling kernel is not built on this machine")
    lib = ctypes.CDLL(str(library))
    function = lib.rolling_mean
    pointer = np.ctypeslib.ndpointer(dtype=np.float64, ndim=1, flags="C_CONTIGUOUS")
    function.argtypes = [pointer, pointer, ctypes.c_int, ctypes.c_int]
    function.restype = None
    values = np.ascontiguousarray(values, dtype=np.float64)
    output = np.empty_like(values)
    function(values, output, len(values), window)
    output[: window - 1] = np.nan
    return output
