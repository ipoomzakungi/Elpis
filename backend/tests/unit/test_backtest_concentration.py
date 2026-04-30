from datetime import datetime, timedelta

import pytest

from src.backtest.metrics import calculate_trade_concentration
from src.models.backtest import (
    DrawdownRecoveryStatus,
    EquityPoint,
    ExitReason,
    StrategyMode,
    TradeRecord,
    TradeSide,
)


def test_calculate_trade_concentration_reports_profit_share_and_best_worst_trades():
    trades = [
        _trade(1, 100.0),
        _trade(2, 50.0),
        _trade(3, -40.0),
        _trade(4, 10.0),
        _trade(5, -5.0),
        _trade(6, 25.0),
    ]

    report = calculate_trade_concentration(trades=trades, equity_curve=[])

    assert report.top_1_profit_contribution_pct == pytest.approx(100 / 185 * 100)
    assert report.top_5_profit_contribution_pct == pytest.approx(185 / 185 * 100)
    assert report.top_10_profit_contribution_pct == pytest.approx(185 / 185 * 100)
    assert [trade.net_pnl for trade in report.best_trades[:3]] == [100.0, 50.0, 25.0]
    assert [trade.net_pnl for trade in report.worst_trades[:2]] == [-40.0, -5.0]
    assert report.max_consecutive_losses == 1
    assert any("top trade contribution" in note for note in report.notes)


def test_calculate_trade_concentration_reports_consecutive_losses_and_recovery():
    trades = [_trade(1, -10.0), _trade(2, -20.0), _trade(3, 30.0)]
    equity_curve = [
        _equity(0, equity=1000.0, drawdown_pct=0.0),
        _equity(1, equity=950.0, drawdown_pct=-5.0),
        _equity(2, equity=930.0, drawdown_pct=-7.0),
        _equity(3, equity=1002.0, drawdown_pct=0.0),
    ]

    report = calculate_trade_concentration(trades=trades, equity_curve=equity_curve)

    assert report.max_consecutive_losses == 2
    assert report.drawdown_recovery_status == DrawdownRecoveryStatus.RECOVERED
    assert report.drawdown_recovery_bars == 2


def test_calculate_trade_concentration_marks_unrecovered_drawdown():
    report = calculate_trade_concentration(
        trades=[_trade(1, -25.0)],
        equity_curve=[
            _equity(0, equity=1000.0, drawdown_pct=0.0),
            _equity(1, equity=975.0, drawdown_pct=-2.5),
            _equity(2, equity=980.0, drawdown_pct=-2.0),
        ],
    )

    assert report.drawdown_recovery_status == DrawdownRecoveryStatus.NOT_RECOVERED
    assert report.drawdown_recovery_bars is None
    assert any("did not recover" in note for note in report.notes)


def _trade(index: int, net_pnl: float) -> TradeRecord:
    timestamp = datetime(2026, 4, 1) + timedelta(minutes=15 * index)
    return TradeRecord(
        trade_id=f"T{index:06d}",
        run_id="concentration_run",
        strategy_mode=StrategyMode.GRID_RANGE,
        provider="binance",
        symbol="BTCUSDT",
        timeframe="15m",
        side=TradeSide.LONG,
        regime_at_signal="RANGE",
        signal_timestamp=timestamp,
        entry_timestamp=timestamp + timedelta(minutes=15),
        entry_price=100.0,
        exit_timestamp=timestamp + timedelta(minutes=30),
        exit_price=100.0 + net_pnl,
        exit_reason=ExitReason.TAKE_PROFIT if net_pnl >= 0 else ExitReason.STOP_LOSS,
        quantity=1.0,
        notional=100.0,
        gross_pnl=net_pnl,
        fees=0.0,
        slippage=0.0,
        net_pnl=net_pnl,
        return_pct=net_pnl / 100.0,
        holding_bars=1,
    )


def _equity(index: int, equity: float, drawdown_pct: float) -> EquityPoint:
    return EquityPoint(
        timestamp=datetime(2026, 4, 1) + timedelta(minutes=15 * index),
        strategy_mode=StrategyMode.GRID_RANGE,
        equity=equity,
        drawdown=drawdown_pct / 100,
        drawdown_pct=drawdown_pct,
        realized_pnl=equity - 1000.0,
        open_position=False,
    )
