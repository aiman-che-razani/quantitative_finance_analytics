from datetime import datetime

import numpy as np


def analyze(result: dict, benchmark: dict | None = None) -> dict:
    rows = result["equity"]
    values = np.array([r["equity"] for r in rows], dtype=float)
    returns = (
        np.divide(values[1:], values[:-1], out=np.ones(len(values) - 1), where=values[:-1] != 0) - 1
    )
    dd = values / np.maximum.accumulate(values) - 1
    std = float(returns.std(ddof=1)) if len(returns) > 1 else 0
    mean = float(returns.mean()) if len(returns) else 0
    downside = float(np.sqrt(np.mean(np.minimum(returns, 0) ** 2))) if len(returns) else 0
    years = (
        (
            datetime.fromisoformat(rows[-1]["timestamp"])
            - datetime.fromisoformat(rows[0]["timestamp"])
        ).total_seconds()
        / 86400
        / 365.25
    )
    cagr = (
        float((values[-1] / values[0]) ** (1 / years) - 1) if years > 0 and values[-1] > 0 else None
    )
    pnls = np.array([t["pnl"] for t in result["trades"]], dtype=float)
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]
    duration = max_duration = 0
    for d in dd:
        duration = duration + 1 if d < 0 else 0
        max_duration = max(max_duration, duration)
    threshold = float(np.quantile(returns, 0.05)) if len(returns) else 0
    tail = returns[returns <= threshold]
    months: dict[str, float] = {}
    for i in range(1, len(rows)):
        month = rows[i]["timestamp"][:7]
        months[month] = months.get(month, 1.0) * (1 + returns[i - 1])
    rolling_sharpe = []
    rolling_vol = []
    for i in range(len(returns)):
        window = returns[max(0, i - 62) : i + 1]
        sigma = float(window.std(ddof=1)) if len(window) > 1 else 0
        rolling_sharpe.append(
            float(window.mean() / sigma * np.sqrt(252)) if sigma > 1e-12 else None
        )
        rolling_vol.append(sigma * np.sqrt(252))
    beta = correlation = None
    if benchmark and len(benchmark["equity"]) == len(rows):
        b = np.array([r["equity"] for r in benchmark["equity"]])
        br = np.divide(b[1:], b[:-1], out=np.ones(len(b) - 1), where=b[:-1] != 0) - 1
        if np.var(br) > 1e-15:
            beta = float(np.cov(returns, br, ddof=1)[0, 1] / np.var(br, ddof=1))
        if std > 1e-15 and np.std(br) > 1e-15:
            correlation = float(np.corrcoef(returns, br)[0, 1])
    return {
        "total_return": float(values[-1] / values[0] - 1),
        "cagr": cagr,
        "annualized_return": mean * 252,
        "annualized_volatility": std * np.sqrt(252),
        "sharpe": mean / std * np.sqrt(252) if std > 1e-12 else None,
        "sortino": mean / downside * np.sqrt(252) if downside > 1e-12 else None,
        "calmar": cagr / abs(float(dd.min())) if cagr is not None and dd.min() < 0 else None,
        "max_drawdown": float(dd.min()),
        "average_drawdown": float(dd.mean()),
        "drawdown_duration_bars": max_duration,
        "win_rate": float(len(wins) / len(pnls)) if len(pnls) else None,
        "loss_rate": float(len(losses) / len(pnls)) if len(pnls) else None,
        "average_winner": float(wins.mean()) if len(wins) else None,
        "average_loser": float(losses.mean()) if len(losses) else None,
        "profit_factor": float(wins.sum() / abs(losses.sum())) if len(losses) else None,
        "expectancy": float(pnls.mean()) if len(pnls) else None,
        "number_of_trades": len(pnls),
        "average_holding_bars": float(np.mean([t["bars_held"] for t in result["trades"]]))
        if len(pnls)
        else None,
        "turnover": sum(abs(f["units"] * f["price"]) for f in result["fills"])
        / float(values.mean())
        if abs(float(values.mean())) > 1e-12
        else None,
        "exposure": float(
            np.mean([r["gross_exposure"] / r["equity"] if r["equity"] > 0 else 0 for r in rows])
        ),
        "var_95": max(0, -threshold),
        "cvar_95": max(0, -float(tail.mean())) if len(tail) else 0,
        "beta": beta,
        "benchmark_correlation": correlation,
        "monthly_returns": {m: float(v - 1) for m, v in months.items()},
        "drawdown": dd.tolist(),
        "returns": returns.tolist(),
        "rolling_sharpe": rolling_sharpe,
        "rolling_volatility": rolling_vol,
        "trade_pnl": pnls.tolist(),
    }
