from collections.abc import Sequence

from src.models.backtest import EquityPoint, MetricsSummary, TradeRecord


def calculate_metrics(
    trades: Sequence[TradeRecord],
    equity_curve: Sequence[EquityPoint],
    initial_equity: float,
) -> MetricsSummary:
    notes: list[str] = []
    final_equity = equity_curve[-1].equity if equity_curve else initial_equity
    total_return = (final_equity - initial_equity) / initial_equity if initial_equity else 0.0
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
        total_return_pct=total_return * 100,
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
        return_by_regime={},
        return_by_strategy_mode={},
        return_by_symbol_provider={},
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