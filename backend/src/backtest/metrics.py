from collections.abc import Sequence
from typing import Any

from src.models.backtest import EquityPoint, MetricsSummary, StrategyMode, TradeRecord

BASELINE_MODES = {
    StrategyMode.BUY_HOLD,
    StrategyMode.PRICE_BREAKOUT,
    StrategyMode.NO_TRADE,
}


def calculate_metrics(
    trades: Sequence[TradeRecord],
    equity_curve: Sequence[EquityPoint],
    initial_equity: float,
) -> MetricsSummary:
    notes: list[str] = []
    strategy_modes = _strategy_modes(trades, equity_curve)
    if len(strategy_modes) > 1:
        total_return = None
        total_return_pct = None
        notes.append(
            "Summary total return is omitted because this run compares independent strategy modes; "
            "use return_by_strategy_mode and baseline_comparison for per-mode results."
        )
    else:
        final_equity = equity_curve[-1].equity if equity_curve else initial_equity
        total_return = (final_equity - initial_equity) / initial_equity if initial_equity else 0.0
        total_return_pct = total_return * 100
    max_drawdown = min((point.drawdown for point in equity_curve), default=0.0)

    winning_trades = [trade for trade in trades if trade.net_pnl > 0]
    losing_trades = [trade for trade in trades if trade.net_pnl < 0]
    gross_wins = sum(trade.net_pnl for trade in winning_trades)
    gross_losses = abs(sum(trade.net_pnl for trade in losing_trades))

    if not trades:
        notes.append("No trades were generated for this run; trade ratios are undefined.")

    profit_factor = _profit_factor(gross_wins, gross_losses, notes)
    win_rate = len(winning_trades) / len(trades) if trades else None
    average_win = gross_wins / len(winning_trades) if winning_trades else None
    average_loss = -gross_losses / len(losing_trades) if losing_trades else None
    expectancy = sum(trade.net_pnl for trade in trades) / len(trades) if trades else None
    average_holding_bars = (
        sum(trade.holding_bars for trade in trades) / len(trades) if trades else None
    )

    if trades and average_win is None:
        notes.append("Average win is undefined because there were no winning trades.")
    if trades and average_loss is None:
        notes.append("Average loss is undefined because there were no losing trades.")

    return MetricsSummary(
        total_return=total_return,
        total_return_pct=total_return_pct,
        max_drawdown=max_drawdown,
        max_drawdown_pct=max_drawdown * 100,
        profit_factor=profit_factor,
        win_rate=win_rate,
        average_win=average_win,
        average_loss=average_loss,
        expectancy=expectancy,
        number_of_trades=len(trades),
        average_holding_bars=average_holding_bars,
        max_consecutive_losses=_max_consecutive_losses(trades),
        return_by_regime=_group_trades_by_regime(trades),
        return_by_strategy_mode=_group_by_strategy_mode(trades, equity_curve, initial_equity),
        return_by_symbol_provider=_group_trades_by_symbol_provider(trades),
        baseline_comparison=_baseline_comparison(trades, equity_curve, initial_equity),
        notes=notes,
    )


def _profit_factor(gross_wins: float, gross_losses: float, notes: list[str]) -> float | None:
    if gross_losses == 0:
        notes.append("Profit factor is undefined because there were no losing trades.")
        return None
    if gross_wins == 0:
        return 0.0
    return gross_wins / gross_losses


def _max_consecutive_losses(trades: Sequence[TradeRecord]) -> int:
    longest = 0
    current = 0
    for trade in trades:
        if trade.net_pnl < 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def _strategy_modes(
    trades: Sequence[TradeRecord],
    equity_curve: Sequence[EquityPoint],
) -> set[StrategyMode]:
    modes = {point.strategy_mode for point in equity_curve}
    modes.update(trade.strategy_mode for trade in trades)
    return modes


def _group_trades_by_regime(trades: Sequence[TradeRecord]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[TradeRecord]] = {}
    for trade in trades:
        grouped.setdefault(trade.regime_at_signal or "unknown", []).append(trade)
    return {key: _trade_group_summary(group_trades) for key, group_trades in grouped.items()}


def _group_trades_by_symbol_provider(trades: Sequence[TradeRecord]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[TradeRecord]] = {}
    for trade in trades:
        provider = trade.provider or "unknown"
        grouped.setdefault(f"{provider}:{trade.symbol}", []).append(trade)
    return {key: _trade_group_summary(group_trades) for key, group_trades in grouped.items()}


def _group_by_strategy_mode(
    trades: Sequence[TradeRecord],
    equity_curve: Sequence[EquityPoint],
    initial_equity: float,
) -> dict[str, dict[str, Any]]:
    modes = {point.strategy_mode for point in equity_curve}
    modes.update(trade.strategy_mode for trade in trades)
    return {
        mode.value: _strategy_mode_summary(mode, trades, equity_curve, initial_equity)
        for mode in sorted(modes, key=lambda item: item.value)
    }


def _baseline_comparison(
    trades: Sequence[TradeRecord],
    equity_curve: Sequence[EquityPoint],
    initial_equity: float,
) -> list[dict[str, Any]]:
    grouped = _group_by_strategy_mode(trades, equity_curve, initial_equity)
    rows = []
    for strategy_mode, summary in grouped.items():
        mode = StrategyMode(strategy_mode)
        rows.append(
            {
                "strategy_mode": strategy_mode,
                "category": "baseline" if mode in BASELINE_MODES else "strategy",
                **summary,
            }
        )
    return rows


def _strategy_mode_summary(
    mode: StrategyMode,
    trades: Sequence[TradeRecord],
    equity_curve: Sequence[EquityPoint],
    initial_equity: float,
) -> dict[str, Any]:
    mode_trades = [trade for trade in trades if trade.strategy_mode == mode]
    mode_equity = [point for point in equity_curve if point.strategy_mode == mode]
    final_equity = mode_equity[-1].equity if mode_equity else initial_equity
    total_return = (final_equity - initial_equity) / initial_equity if initial_equity else 0.0
    max_drawdown = min((point.drawdown for point in mode_equity), default=0.0)
    summary = _trade_group_summary(mode_trades)
    summary.update(
        {
            "total_return": total_return,
            "total_return_pct": total_return * 100,
            "max_drawdown": max_drawdown,
            "max_drawdown_pct": max_drawdown * 100,
        }
    )
    return summary


def _trade_group_summary(trades: Sequence[TradeRecord]) -> dict[str, Any]:
    net_pnl = sum(trade.net_pnl for trade in trades)
    notional = sum(trade.notional for trade in trades)
    return_pct = net_pnl / notional if notional else 0.0
    wins = [trade for trade in trades if trade.net_pnl > 0]
    return {
        "number_of_trades": len(trades),
        "net_pnl": net_pnl,
        "return_pct": return_pct,
        "return_pct_display": return_pct * 100,
        "win_rate": len(wins) / len(trades) if trades else None,
    }
