"""Expanding, purged train/validation/test splits on one instrument."""

from datetime import datetime
from typing import Any

import numpy as np
import polars as pl
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, balanced_accuracy_score, log_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from axiom.analytics.extended import analyze
from axiom.backtest.events import ExecutionConfig, run_events

FEATURES = [
    "rsi",
    "ema_distance",
    "bb_position",
    "volatility",
    "momentum",
    "volume_change",
    "lagged_return",
]


def splits(length, train=504, validation=126, test=126, horizon=5):
    if min(train, validation, test, horizon) < 1:
        raise ValueError("Positive split sizes required")
    test_start = train + validation + 2 * horizon
    while test_start + test <= length:
        validation_start = test_start - horizon - validation
        train_end = validation_start - horizon
        yield (0, train_end, validation_start, test_start - horizon, test_start, test_start + test)
        test_start += test


def walk_forward(
    frame: pl.DataFrame, execution: ExecutionConfig, horizon=5, train=504, validation=126, test=126
):
    if frame["instrument"].n_unique() != 1:
        raise ValueError("Walk-forward research currently requires one instrument")
    data = (
        frame.sort("timestamp")
        .with_columns(
            (pl.col("close").shift(-horizon) / pl.col("close") - 1).alias("forward_return")
        )
        .drop_nulls(FEATURES + ["forward_return"])
        .filter(pl.col("ready"))
    )
    x = data.select(FEATURES).to_numpy()
    y = (data["forward_return"].to_numpy() > 0).astype(int)
    if not np.isfinite(x).all():
        raise ValueError("Nonfinite ML features")
    predictions: dict[str, list[tuple[datetime, int]]] = {
        name: [] for name in ["naive", "logistic", "random_forest", "xgboost"]
    }
    folds = []
    for a, b, c, d, e, f in splits(len(data), train, validation, test, horizon):
        if len(np.unique(y[a:b])) < 2 or len(np.unique(y[c:d])) < 2:
            raise ValueError("Both classes required in train and validation")
        # Every candidate is fitted on training data only; selection uses validation only.
        candidates = []
        for strength in [0.1, 1.0, 10.0]:
            candidate = make_pipeline(
                StandardScaler(), LogisticRegression(C=strength, max_iter=1000, random_state=42)
            )
            candidate.fit(x[a:b], y[a:b])
            candidates.append(
                (
                    log_loss(y[c:d], candidate.predict_proba(x[c:d]), labels=[0, 1]),
                    strength,
                    candidate,
                )
            )
        _, strength, logistic = min(candidates, key=lambda item: item[0])
        models = {
            "naive": DummyClassifier(strategy="prior"),
            "logistic": logistic,
            "random_forest": RandomForestClassifier(
                n_estimators=100, max_depth=5, min_samples_leaf=10, random_state=42, n_jobs=1
            ),
            "xgboost": XGBClassifier(
                n_estimators=100,
                max_depth=3,
                learning_rate=0.05,
                subsample=1,
                colsample_bytree=1,
                random_state=42,
                n_jobs=1,
                eval_metric="logloss",
            ),
        }
        fold: dict[str, Any] = {
            "train": [str(data["timestamp"][a]), str(data["timestamp"][b - 1])],
            "last_train_label": str(data["timestamp"][b - 1 + horizon]),
            "validation": [str(data["timestamp"][c]), str(data["timestamp"][d - 1])],
            "last_validation_label": str(data["timestamp"][d - 1 + horizon]),
            "test": [str(data["timestamp"][e]), str(data["timestamp"][f - 1])],
            "logistic_C": strength,
            "models": {},
        }
        for name, model in models.items():
            if name != "logistic":
                model.fit(x[a:b], y[a:b])
            probability = model.predict_proba(x[e:f])[:, 1]
            prediction = (probability >= 0.5).astype(int)
            fold["models"][name] = {
                "accuracy": float(accuracy_score(y[e:f], prediction)),
                "balanced_accuracy": float(balanced_accuracy_score(y[e:f], prediction)),
                "log_loss": float(log_loss(y[e:f], probability, labels=[0, 1])),
                "roc_auc": float(roc_auc_score(y[e:f], probability))
                if len(np.unique(y[e:f])) == 2
                else None,
            }
            predictions[name].extend(zip(data["timestamp"][e:f].to_list(), prediction.tolist()))
        folds.append(fold)
    if not folds:
        raise ValueError("Insufficient history for a complete purged fold")
    trading = {}
    for name, pairs in predictions.items():
        # Predictions are available at the close; the engine fills on the next open.
        prediction_frame = pl.DataFrame(
            {"timestamp": [p[0] for p in pairs], "prediction": [p[1] for p in pairs]},
            schema_overrides={"timestamp": frame.schema["timestamp"]},
        )
        start, end = pairs[0][0], pairs[-1][0]
        replay = frame.join(prediction_frame, on="timestamp", how="left").with_columns(
            pl.col("prediction").fill_null(0)
        )
        all_dates = replay["timestamp"].to_list()
        first = all_dates.index(start) + 1
        last = min(len(all_dates), all_dates.index(end) + 2)
        result = run_events(replay.head(last), "ml", execution, first_index=first)
        benchmark = run_events(replay.head(last), "buy_hold", execution, first_index=first)
        trading[name] = {
            "metrics": analyze(result, benchmark),
            "equity": result["equity"],
            "fills": result["fills"],
        }
    return {
        "features": FEATURES,
        "horizon": horizon,
        "seed": 42,
        "folds": folds,
        "out_of_sample_trading": trading,
        "assumptions": "Single instrument; expanding training; horizon purge at both boundaries; no test-driven tuning; next-open fills; no model refit on validation.",
    }
