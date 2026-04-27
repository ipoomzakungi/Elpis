from datetime import datetime, timedelta

import pytest

from src.backtest.engine import BacktestEngine
from src.models.backtest import (
    BacktestRunRequest,
    ExitReason,
    StrategyMode,
    TradeRecord,
    TradeSide,
)


def test_mode_equity_curve_marks_open_positions_to_close_price():
    start = datetime(2026, 4, 1)
    rows = [
        _row(start, close=100.0),
        _row(start + timedelta(minutes=15), close=101.0),
        _row(start + timedelta(minutes=30), close=95.0),
        _row(start + timedelta(minutes=45), close=120.0),
    ]
    trade = _trade(
        entry_timestamp=rows[1]["timestamp"],
        exit_timestamp=rows[3]["timestamp"],
        entry_price=100.0,
        quantity=10.0,
        net_pnl=200.0,
    )

    equity_curve = BacktestEngine()._build_mode_equity_curve(
        request=BacktestRunRequest(initial_equity=10000.0),
        rows=rows,
        trades=[trade],
        strategy_mode=StrategyMode.GRID_RANGE,
    )

    assert equity_curve[1].realized_equity == pytest.approx(10000.0)
    assert equity_curve[1].unrealized_pnl == pytest.approx(10.0)
    assert equity_curve[1].total_equity == pytest.approx(10010.0)
    assert equity_curve[1].equity == pytest.approx(10010.0)
    assert equity_curve[1].open_position is True
    assert equity_curve[1].equity_basis == "total_mark_to_market"

    assert equity_curve[2].realized_equity == pytest.approx(10000.0)
    assert equity_curve[2].unrealized_pnl == pytest.approx(-50.0)
    assert equity_curve[2].total_equity == pytest.approx(9950.0)
    assert equity_curve[2].drawdown == pytest.approx((9950.0 - 10010.0) / 10010.0)

    assert equity_curve[3].realized_equity == pytest.approx(10200.0)
    assert equity_curve[3].unrealized_pnl == pytest.approx(0.0)
    assert equity_curve[3].total_equity == pytest.approx(10200.0)
    assert equity_curve[3].open_position is False
    assert equity_curve[3].equity_basis == "realized_only"


def test_mode_equity_curve_labels_no_trade_equity_as_realized_only():
    start = datetime(2026, 4, 1)

    equity_curve = BacktestEngine()._build_mode_equity_curve(
        request=BacktestRunRequest(initial_equity=10000.0),
        rows=[_row(start, close=100.0), _row(start + timedelta(minutes=15), close=101.0)],
        trades=[],
        strategy_mode=StrategyMode.NO_TRADE,
    )

    assert [point.equity_basis for point in equity_curve] == ["realized_only", "realized_only"]
    assert [point.realized_equity for point in equity_curve] == [10000.0, 10000.0]
    assert [point.total_equity for point in equity_curve] == [10000.0, 10000.0]
    assert [point.unrealized_pnl for point in equity_curve] == [0.0, 0.0]


def _row(timestamp: datetime, close: float) -> dict:
    return {
        "timestamp": timestamp,
        "open": close,
        "high": close + 2.0,
        "low": close - 2.0,
        "close": close,
    }


def _trade(
    entry_timestamp: datetime,
    exit_timestamp: datetime,
    entry_price: float,
    quantity: float,
    net_pnl: float,
) -> TradeRecord:
    notional = entry_price * quantity
    return TradeRecord(
        trade_id="T000001",
        run_id="test_run",
        strategy_mode=StrategyMode.GRID_RANGE,
        provider="binance",
        symbol="BTCUSDT",
        timeframe="15m",
        side=TradeSide.LONG,
        regime_at_signal="RANGE",
        signal_timestamp=entry_timestamp - timedelta(minutes=15),
        entry_timestamp=entry_timestamp,
        entry_price=entry_price,
        exit_timestamp=exit_timestamp,
        exit_price=entry_price + (net_pnl / quantity),
        exit_reason=ExitReason.END_OF_DATA,
        quantity=quantity,
        notional=notional,
        gross_pnl=net_pnl,
        fees=0.0,
        slippage=0.0,
        net_pnl=net_pnl,
        return_pct=net_pnl / notional,
        holding_bars=2,
    )