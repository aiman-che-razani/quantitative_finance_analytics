from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from axiom.portfolio.account import Account


class RiskConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    max_leverage: float = Field(default=1, gt=0, le=3)
    max_concentration: float = Field(default=1, gt=0, le=1)
    max_drawdown: float = Field(default=0.3, gt=0, le=1)
    daily_loss_limit: float = Field(default=0.1, gt=0, le=1)
    portfolio_loss_limit: float = Field(default=0.4, gt=0, le=1)
    risk_per_trade: float = Field(default=0.02, gt=0, le=0.2)
    allow_short: bool = False


@dataclass
class Decision:
    action: str
    units: float
    reason: str


def assess(
    account: Account,
    symbol: str,
    units: float,
    price: float,
    marks: dict[str, float],
    config: RiskConfig,
    peak: float,
    day_start: float,
    fee_rate: float,
    stop_loss: float | None = None,
) -> Decision:
    state = account.mark(marks | {symbol: price}, include_positions=False)
    equity = state["equity"]
    old = account.positions.get(symbol)
    held = old.units if old else 0.0
    if held * units < 0 and abs(units) <= abs(held):
        return Decision("APPROVE", units, "Risk-reducing close")
    if equity <= 0:
        return Decision("REJECT", 0, "Nonpositive equity")
    if (
        equity / peak - 1 <= -config.max_drawdown
        or equity / day_start - 1 <= -config.daily_loss_limit
        or equity / account.initial - 1 <= -config.portfolio_loss_limit
    ):
        return Decision("REJECT", 0, "Portfolio loss circuit breaker")
    if held + units < 0 and not config.allow_short:
        return Decision("REJECT", 0, "Short positions disabled")
    other = state["gross_exposure"] - abs(held * price)
    max_position = min(equity * config.max_concentration, equity * config.max_leverage - other)
    if stop_loss:
        max_position = min(max_position, equity * config.risk_per_trade / stop_loss)
    max_position = max(0.0, max_position) / (1 + config.max_leverage * fee_rate)
    target = max(-max_position / price, min(max_position / price, held + units))
    allowed = target - held
    if allowed * units <= 0:
        return Decision("REJECT", 0, "Exposure limit")
    if allowed > 0:
        # Cash cannot finance new longs; covering shorts is handled above.
        allowed = min(allowed, max(0, account.cash) / (price * (1 + fee_rate)))
    if abs(allowed) < 1e-8:
        return Decision("REJECT", 0, "Insufficient capital")
    return Decision(
        "MODIFY" if abs(allowed - units) > 1e-8 else "APPROVE",
        allowed,
        "Position/cash/risk limits" if abs(allowed - units) > 1e-8 else "Within limits",
    )
