"""Validated configuration shared by providers, features and research."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Instrument(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    symbol: str = Field(pattern=r"^[A-Z][A-Z0-9.]{0,9}$")
    asset_class: Literal["etf"] = "etf"
    exchange: str
    currency: Literal["USD"] = "USD"
    sector: str | None = None
    industry: str | None = None
    timezone: str = "America/New_York"
    calendar: Literal["XNYS"] = "XNYS"
    active_from: date | None = None
    active_to: date | None = None


UNIVERSE = [
    Instrument(symbol=symbol, exchange=exchange)
    for symbol, exchange in (
        ("SPY", "ARCX"),
        ("QQQ", "XNAS"),
        ("IWM", "ARCX"),
        ("DIA", "ARCX"),
        ("EFA", "ARCX"),
        ("EEM", "ARCX"),
        ("TLT", "XNAS"),
        ("IEF", "XNAS"),
        ("GLD", "ARCX"),
        ("SLV", "ARCX"),
    )
]


class FeatureConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    rsi_period: int = Field(default=26, ge=2, le=1000)
    ema_period: int = Field(default=200, ge=2, le=1000)
    bollinger_period: int = Field(default=200, ge=2, le=1000)
    bollinger_std: float = Field(default=1.19, gt=0, le=10)


class BacktestConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    initial_capital: float = Field(default=10000, gt=0, le=1e12)
    commission_bps_per_side: float = Field(default=2.5, ge=0, le=100)
    slippage_bps_per_side: float = Field(default=1.0, ge=0, le=100)
    annualization: int = Field(default=252, ge=1, le=366)

    @model_validator(mode="after")
    def reasonable_costs(self) -> "BacktestConfig":
        if self.commission_bps_per_side + self.slippage_bps_per_side >= 10000:
            raise ValueError("costs must be below the full notional")
        return self
