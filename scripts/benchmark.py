"""Reproducible synthetic workload, not a historical trading claim."""

import cProfile
import json
import platform
import statistics
import threading
import time
from datetime import date
from pathlib import Path

import numpy as np
import polars as pl
import psutil

from axiom.backtest.events import ExecutionConfig, run_events
from axiom.common.models import FeatureConfig
from axiom.data.providers import sessions
from axiom.data.stable import synthetic_frame
from axiom.data.universe import benchmark_universe
from axiom.features.kernels import native_mean, numba_mean, numpy_mean, polars_mean, python_mean
from axiom.features.pipeline import FeaturePipeline

output = Path("docs/benchmarks")
output.mkdir(parents=True, exist_ok=True)
process = psutil.Process()
peak = [process.memory_info().rss]
stop = threading.Event()


def sample():
    while not stop.wait(0.02):
        peak[0] = max(peak[0], process.memory_info().rss)


thread = threading.Thread(target=sample, daemon=True)
thread.start()
start = time.perf_counter()
cpu = time.process_time()
days = sessions(date(2016, 1, 1), date(2026, 1, 1))
frames = [synthetic_frame(i.symbol, days) for i in benchmark_universe()]
bars = pl.concat(frames).with_columns(
    pl.col("timestamp").str.to_datetime(time_zone="UTC"),
    pl.col("ingested_at").str.to_datetime(time_zone="UTC"),
)
del frames
print("Prepared", bars.height, "bars", flush=True)
values = bars["close"].to_numpy()
reference = numpy_mean(values, 200)
kernels = {}
for name, kernel in [
    ("python", python_mean),
    ("numpy", numpy_mean),
    ("polars", polars_mean),
    ("numba", numba_mean),
    ("cpp", native_mean),
]:
    before = time.perf_counter()
    actual = kernel(values, 200)
    cold = time.perf_counter() - before
    np.testing.assert_allclose(actual, reference, rtol=1e-9, atol=1e-8, equal_nan=True)
    timings = []
    for _ in range(5):
        before = time.perf_counter()
        kernel(values, 200)
        timings.append(time.perf_counter() - before)
    kernels[name] = {
        "cold_seconds": cold,
        "median_seconds": statistics.median(timings),
        "rows_per_second": len(values) / statistics.median(timings),
    }
    print(name, kernels[name], flush=True)
profiler = cProfile.Profile()
profiler.enable()
before = time.perf_counter()
features = FeaturePipeline(FeatureConfig()).transform(bars)
feature_seconds = time.perf_counter() - before
print("Features", feature_seconds, flush=True)
before = time.perf_counter()
result = run_events(features, "ema_trend", ExecutionConfig(), record_events=False)
replay_seconds = time.perf_counter() - before
profiler.disable()
profiler.dump_stats(str(output / "pipeline.prof"))
stop.set()
thread.join()
report = {
    "source": "synthetic-v2",
    "instruments": 342,
    "sessions": len(days),
    "rows": bars.height,
    "start": "2016-01-01",
    "end_exclusive": "2026-01-01",
    "platform": platform.platform(),
    "python": platform.python_version(),
    "cpu_logical": psutil.cpu_count(),
    "kernels": kernels,
    "feature_seconds": feature_seconds,
    "event_replay_seconds": replay_seconds,
    "total_seconds": time.perf_counter() - start,
    "process_cpu_seconds": time.process_time() - cpu,
    "peak_rss_mb": peak[0] / 1024**2,
    "fills": len(result["fills"]),
    "final_equity": result["final"]["equity"],
    "method": "Five warm repetitions, median wall time. Kernel comparison uses one contiguous synthetic series; portfolio features reset per instrument. Peak RSS sampled every 20 ms, includes interpreter and JIT. No ingestion or network timing included in replay.",
}
(output / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

fig, ax = plt.subplots(figsize=(8, 4))
ax.bar(kernels.keys(), [v["median_seconds"] for v in kernels.values()], color="#47836a")
ax.set_yscale("log")
ax.set_ylabel("Median seconds (log scale)")
ax.set_title(f"Rolling mean · {bars.height:,} synthetic rows · window 200")
fig.tight_layout()
fig.savefig(output / "kernels.png", dpi=160)
print(json.dumps(report, indent=2), flush=True)
