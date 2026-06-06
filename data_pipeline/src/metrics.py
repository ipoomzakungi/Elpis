from __future__ import annotations

import math
from datetime import datetime
from statistics import mean, pstdev
from typing import Any


def calculate_summary_metrics(
    trades: list[dict[str, Any]],
    equity_curve: list[dict[str, Any]],
    initial_cash: float,
    annualization_periods: int = 252 * 24 * 60,
) -> dict[str, Any]:
    final_equity = equity_curve[-1]["equity"] if equity_curve else initial_cash
    net_profit = final_equity - initial_cash
    total_return = net_profit / initial_cash if initial_cash else 0.0
    max_drawdown = min((point["drawdown"] for point in equity_curve), default=0.0)

    wins = [trade for trade in trades if trade["net_pnl"] > 0]
    losses = [trade for trade in trades if trade["net_pnl"] < 0]
    gross_profit = sum(trade["net_pnl"] for trade in wins)
    gross_loss = abs(sum(trade["net_pnl"] for trade in losses))
    profit_factor = None if gross_loss == 0 else gross_profit / gross_loss
    win_rate = len(wins) / len(trades) if trades else None
    average_trade = sum(trade["net_pnl"] for trade in trades) / len(trades) if trades else None
    average_holding_minutes = _average_holding_minutes(trades)
    sharpe_ratio = _sharpe_ratio(equity_curve, annualization_periods)

    return {
        "initial_cash": initial_cash,
        "final_equity": final_equity,
        "total_return": total_return,
        "total_return_pct": total_return * 100,
        "net_profit": net_profit,
        "max_drawdown": max_drawdown,
        "max_drawdown_pct": max_drawdown * 100,
        "win_rate": win_rate,
        "win_rate_pct": win_rate * 100 if win_rate is not None else None,
        "profit_factor": profit_factor,
        "average_trade": average_trade,
        "number_of_trades": len(trades),
        "average_holding_minutes": average_holding_minutes,
        "sharpe_ratio": sharpe_ratio,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
    }


def _average_holding_minutes(trades: list[dict[str, Any]]) -> float | None:
    if not trades:
        return None
    durations: list[float] = []
    for trade in trades:
        entry = trade["entry_time"]
        exit_ = trade["exit_time"]
        if isinstance(entry, str):
            entry = datetime.fromisoformat(entry.replace("Z", "+00:00"))
        if isinstance(exit_, str):
            exit_ = datetime.fromisoformat(exit_.replace("Z", "+00:00"))
        durations.append((exit_ - entry).total_seconds() / 60)
    return mean(durations)


def _sharpe_ratio(equity_curve: list[dict[str, Any]], annualization_periods: int) -> float | None:
    if len(equity_curve) < 3:
        return None
    returns: list[float] = []
    previous = equity_curve[0]["equity"]
    for point in equity_curve[1:]:
        equity = point["equity"]
        if previous:
            returns.append((equity - previous) / previous)
        previous = equity
    if len(returns) < 2:
        return None
    volatility = pstdev(returns)
    if volatility == 0:
        return None
    return (mean(returns) / volatility) * math.sqrt(annualization_periods)

