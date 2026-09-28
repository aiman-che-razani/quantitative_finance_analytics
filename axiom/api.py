"""Authenticated local research API. Slow writes have bounded admission."""

import secrets
import threading
from contextlib import asynccontextmanager
from datetime import date
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Path
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select, text
from sqlalchemy.orm import defer

from axiom import paper
from axiom.backtest.events import STRATEGIES, ExecutionConfig
from axiom.common.models import FeatureConfig
from axiom.metadata import DatasetRow, ExperimentRow, InstrumentRow, PaperRow, database
from axiom.platform import run_experiment
from axiom.settings import Settings

DatasetId = Annotated[str, Path(pattern="^[0-9a-f]{64}$")]
RecordId = Annotated[str, Path(pattern="^[0-9a-f-]{36}$")]


class ResearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset_id: str = Field(pattern="^[0-9a-f]{64}$")
    symbols: list[str] = Field(min_length=1, max_length=342)
    strategy: str = "ema_trend"
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    features: FeatureConfig = Field(default_factory=FeatureConfig)
    kind: Literal["backtest", "ml"] = "backtest"

    @field_validator("symbols")
    @classmethod
    def unique_symbols(cls, symbols: list[str]) -> list[str]:
        if len(set(symbols)) != len(symbols):
            raise ValueError("Duplicate symbols")
        return symbols


class AdvanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of: date
    dataset_id: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")


def create_app(settings=None):
    settings = settings or Settings()
    engine, sessions = database(settings.database_url)
    gate = threading.BoundedSemaphore(settings.max_active_runs)

    @asynccontextmanager
    async def lifespan(app):
        yield
        engine.dispose()

    def auth(authorization: str = Header(default="")):
        expected = ("Bearer " + settings.api_token).encode()
        if not secrets.compare_digest(authorization.encode(), expected):
            raise HTTPException(401, "Authentication required")

    app = FastAPI(
        title="Axiom Research", version="1.0.0", dependencies=[Depends(auth)], lifespan=lifespan
    )

    @app.get("/health")
    def health():
        with sessions() as db:
            db.execute(text("SELECT 1"))
        return {"status": "ok", "execution": "paper-only"}

    @app.get("/instruments")
    def instruments():
        with sessions() as db:
            return [
                r.definition
                for r in db.scalars(select(InstrumentRow).order_by(InstrumentRow.symbol))
            ]

    @app.get("/datasets")
    def datasets():
        with sessions() as db:
            return [
                {
                    "id": r.id,
                    "parent_id": r.parent_id,
                    "provider": r.provider,
                    "symbols": r.symbols,
                    "rows": r.quality["rows"],
                    "created_at": r.created_at,
                }
                for r in db.scalars(
                    select(DatasetRow).order_by(DatasetRow.created_at.desc()).limit(100)
                )
            ]

    @app.get("/market/{identity}")
    def market(identity: DatasetId, symbol: str = "SPY"):
        import polars as pl

        from axiom.data.storage import SnapshotStore
        from axiom.features.pipeline import FeaturePipeline

        with sessions() as db:
            dataset = db.get(DatasetRow, identity)
            if dataset is None or symbol not in dataset.symbols:
                raise HTTPException(404, "Unknown dataset or symbol")
        bars = (
            SnapshotStore(settings.data_root).read(identity).filter(pl.col("instrument") == symbol)
        )
        features = FeaturePipeline(FeatureConfig()).transform(bars)
        return (
            features.select(
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "ema",
                "rsi",
                "bb_upper",
                "bb_lower",
            )
            .tail(3000)
            .to_dicts()
        )

    @app.get("/strategies")
    def strategies():
        return {
            "strategies": [s for s in STRATEGIES if s != "ml"],
            "features": list(FeatureConfig.model_fields),
        }

    @app.get("/experiments")
    def experiments():
        with sessions() as db:
            return [
                {
                    "id": r.id,
                    "kind": r.kind,
                    "status": r.status,
                    "dataset_id": r.dataset_id,
                    "config": r.config,
                    "created_at": r.created_at,
                    "error": r.error,
                }
                for r in db.scalars(
                    select(ExperimentRow)
                    .options(defer(ExperimentRow.result))
                    .order_by(ExperimentRow.created_at.desc())
                    .limit(100)
                )
            ]

    @app.get("/experiments/{identity}")
    def experiment(identity: RecordId):
        with sessions() as db:
            r = db.get(ExperimentRow, identity)
            if r is None:
                raise HTTPException(404, "Unknown experiment")
            return {"id": r.id, "status": r.status, "result": r.result, "error": r.error}

    @app.post("/experiments")
    def research(request: ResearchRequest):
        if request.strategy not in STRATEGIES or request.strategy == "ml":
            raise HTTPException(422, "Unknown rule strategy")
        if not gate.acquire(blocking=False):
            raise HTTPException(429, "Research capacity busy")
        try:
            return run_experiment(
                sessions,
                settings,
                request.dataset_id,
                request.symbols,
                request.strategy,
                request.execution,
                request.features,
                request.kind,
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        finally:
            gate.release()

    @app.get("/paper")
    def accounts():
        with sessions() as db:
            return [
                {"id": r.id, "config": r.config, "state": r.state}
                for r in db.scalars(
                    select(PaperRow).order_by(PaperRow.updated_at.desc()).limit(100)
                )
            ]

    @app.post("/paper")
    def new_account(request: ResearchRequest):
        if request.strategy not in STRATEGIES or request.strategy == "ml":
            raise HTTPException(422, "Unknown paper strategy")
        try:
            return {
                "id": paper.create_account(
                    sessions,
                    request.dataset_id,
                    request.symbols,
                    request.strategy,
                    request.execution,
                )
            }
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.post("/paper/{identity}/advance")
    def advance(identity: RecordId, request: AdvanceRequest):
        if not gate.acquire(blocking=False):
            raise HTTPException(429, "Research capacity busy")
        try:
            return paper.advance(sessions, settings, identity, request.as_of, request.dataset_id)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        finally:
            gate.release()

    return app
