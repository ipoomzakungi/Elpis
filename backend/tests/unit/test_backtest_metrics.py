from datetime import datetime, timedelta

import pytest

from src.backtest.metrics import calculate_metrics
from src.models.backtest import EquityPoint, ExitReason, StrategyMode, TradeRecord, TradeSide


def _trade(index: int, pnl: float, holding_bars: int = 2) -> TradeRecord:
    timestamp = datetime(2026, 4, 1) + timedelta(minutes=15 * index)
    return TradeRecord(
        trade_id=f"T{index:06d}",
        run_id="test_run",
        strategy_mode=StrategyMode.GRID_RANGE,
        provider="binance",
        symbol="BTCUSDT",
        timeframe="15m",
        side=TradeSide.LONG,
        regime_at_signal="RANGE",
        signal_timestamp=timestamp,
        entry_timestamp=timestamp + timedelta(minutes=15),
        entry_price=100.0,
        exit_timestamp=timestamp + timedelta(minutes=15 * (holding_bars + 1)),
        exit_price=100.0 + pnl,
        exit_reason=ExitReason.TAKE_PROFIT if pnl > 0 else ExitReason.STOP_LOSS,
        quantity=1.0,
        notional=100.0,
        gross_pnl=pnl,
        fees=0.0,
        slippage=0.0,
        net_pnl=pnl,
        return_pct=pnl / 100.0,
        holding_bars=holding_bars,
    )


def _equity(
    value: float,
    drawdown: float = 0.0,
    strategy_mode: StrategyMode = StrategyMode.GRID_RANGE,
) -> EquityPoint:
    return EquityPoint(
        timestamp=datetime(2026, 4, 1),
        strategy_mode=strategy_mode,
        equity=value,
        drawdown=drawdown,
        drawdown_pct=drawdown * 100,
        realized_pnl=value - 1000.0,
        open_position=False,
    )


def test_calculate_metrics_with_wins_and_losses():
    metrics = calculate_metrics(
        trades=[_trade(1, 50.0), _trade(2, -25.0), _trade(3, 75.0)],
        equity_curve=[_equity(1000.0), _equity(1100.0), _equity(1075.0, -0.02)],
        initial_equity=1000.0,
    )

    assert metrics.total_return == pytest.approx(0.075)
    assert metrics.total_return_pct == pytest.approx(7.5)
    assert metrics.max_drawdown == pytest.approx(-0.02)
    assert metrics.max_drawdown_pct == pytest.approx(-2.0)
    assert metrics.profit_factor == pytest.approx(5.0)
    assert metrics.win_rate == pytest.approx(2 / 3)
    assert metrics.average_win == pytest.approx(62.5)
    assert metrics.average_loss == pytest.approx(-25.0)
    assert metrics.expectancy == pytest.approx((50 - 25 + 75) / 3)
    assert metrics.number_of_trades == 3
    assert metrics.average_holding_bars == pytest.approx(2.0)
    assert metrics.max_consecutive_losses == 1


def test_calculate_metrics_handles_no_trades():
    metrics = calculate_metrics(
        trades=[],
        equity_curve=[_equity(1000.0), _equity(1000.0)],
        initial_equity=1000.0,
    )

    assert metrics.total_return == 0
    assert metrics.number_of_trades == 0
    assert metrics.profit_factor is None
    assert metrics.win_rate is None
    assert metrics.average_win is None
    assert metrics.average_loss is None
    assert metrics.expectancy is None
    assert "No trades" in " ".join(metrics.notes)


def test_calculate_metrics_handles_only_wins_and_only_losses():
    only_wins = calculate_metrics(
        trades=[_trade(1, 10.0), _trade(2, 20.0)],
        equity_curve=[_equity(1030.0)],
        initial_equity=1000.0,
    )
    only_losses = calculate_metrics(
        trades=[_trade(1, -10.0), _trade(2, -20.0)],
        equity_curve=[_equity(970.0, -0.03)],
        initial_equity=1000.0,
    )

    assert only_wins.profit_factor is None
    assert only_wins.average_loss is None
    assert only_wins.max_consecutive_losses == 0
    assert only_losses.profit_factor == 0
    assert only_losses.average_win is None
    assert only_losses.max_consecutive_losses == 2


def test_calculate_metrics_omits_global_total_return_for_multi_mode_comparison():
    metrics = calculate_metrics(
        trades=[_trade(1, 50.0)],
        equity_curve=[
            _equity(1050.0, strategy_mode=StrategyMode.GRID_RANGE),
            _equity(1200.0, strategy_mode=StrategyMode.BUY_HOLD),
        ],
        initial_equity=1000.0,
    )

    assert metrics.total_return is None
    assert metrics.total_return_pct is None
    assert metrics.return_by_strategy_mode["grid_range"]["total_return_pct"] == pytest.approx(5.0)
    assert metrics.return_by_strategy_mode["buy_hold"]["total_return_pct"] == pytest.approx(20.0)
    assert any("independent strategy modes" in note for note in metrics.notes)
