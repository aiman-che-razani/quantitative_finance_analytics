"""PostgreSQL metadata; large bars remain immutable Parquet files."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, create_engine, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class InstrumentRow(Base):
    __tablename__ = "instruments"
    symbol: Mapped[str] = mapped_column(String(16), primary_key=True)
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB)


class DatasetRow(Base):
    __tablename__ = "datasets"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("datasets.id"))
    provider: Mapped[str] = mapped_column(String(64))
    symbols: Mapped[list[str]] = mapped_column(JSONB)
    quality: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class HeadRow(Base):
    __tablename__ = "ingestion_heads"
    stream: Mapped[str] = mapped_column(String(64), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"))


class ExperimentRow(Base):
    __tablename__ = "experiments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(24))
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"))
    config: Mapped[dict[str, Any]] = mapped_column(JSONB)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PaperRow(Base):
    __tablename__ = "paper_accounts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB)
    state: Mapped[dict[str, Any]] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


def database(url: str):
    engine = create_engine(
        url, pool_pre_ping=True, pool_size=5, max_overflow=5, connect_args={"connect_timeout": 5}
    )
    return engine, sessionmaker(engine, expire_on_commit=False)
