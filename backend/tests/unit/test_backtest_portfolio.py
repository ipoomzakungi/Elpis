from datetime import datetime, timedelta

import pytest

from src.backtest.portfolio import (
    apply_entry_slippage,
    apply_exit_slippage,
    calculate_position_sizing,
    calculate_position_size,
    close_position,
    evaluate_exit,
)
from src.models.backtest import (
    BacktestAssumptions,
    ExitReason,
    Position,
    StrategyMode,
    TradeSide,
)


def test_calculate_position_size_uses_fixed_fractional_risk():
    quantity, notional = calculate_position_size(
        equity=10000.0,
        entry_price=100.0,
        stop_loss=95.0,
        risk_per_trade=0.01,
    )

    assert quantity == pytest.approx(20.0)
    assert notional == pytest.approx(2000.0)


def test_calculate_position_sizing_caps_notional_to_available_equity():
    sizing = calculate_position_sizing(
        equity=10000.0,
        entry_price=100.0,
        stop_loss=99.99,
        risk_per_trade=0.01,
        max_notional=10000.0,
    )

    assert sizing.requested_notional > 10000.0
    assert sizing.notional == pytest.approx(10000.0)
    assert sizing.quantity == pytest.approx(100.0)
    assert sizing.capped is True


def test_slippage_is_adverse_for_entries_and_exits():
    assert apply_entry_slippage(TradeSide.LONG, 100.0, 0.001) == pytest.approx(100.1)
    assert apply_entry_slippage(TradeSide.SHORT, 100.0, 0.001) == pytest.approx(99.9)
    assert apply_exit_slippage(TradeSide.LONG, 100.0, 0.001) == pytest.approx(99.9)
    assert apply_exit_slippage(TradeSide.SHORT, 100.0, 0.001) == pytest.approx(100.1)


def test_evaluate_exit_uses_stop_first_when_stop_and_take_profit_hit_same_bar():
    position = Position(
        position_id="P1",
        strategy_mode=StrategyMode.GRID_RANGE,
        side=TradeSide.LONG,
        entry_timestamp=datetime(2026, 4, 1),
        entry_price=100.0,
        quantity=1.0,
        notional=100.0,
        stop_loss=95.0,
        take_profit=105.0,
        entry_fee=0.0,
    )
    bar = {"high": 106.0, "low": 94.0, "close": 100.0}

    exit_decision = evaluate_exit(position, bar, is_final_bar=False)

    assert exit_decision is not None
    assert exit_decision.reason == ExitReason.STOP_LOSS
    assert exit_decision.price == 95.0


def test_close_position_calculates_long_and_short_net_pnl_with_fees_and_slippage():
    assumptions = BacktestAssumptions(fee_rate=0.001, slippage_rate=0.001)
    entry_timestamp = datetime(2026, 4, 1)
    exit_timestamp = entry_timestamp + timedelta(minutes=30)
    long_position = Position(
        position_id="P1",
        strategy_mode=StrategyMode.GRID_RANGE,
        side=TradeSide.LONG,
        entry_timestamp=entry_timestamp,
        entry_price=100.0,
        quantity=2.0,
        notional=200.0,
        stop_loss=95.0,
        take_profit=110.0,
        entry_fee=0.2,
    )
    short_position = long_position.model_copy(
        update={"position_id": "P2", "side": TradeSide.SHORT, "entry_price": 100.0}
    )

    long_trade = close_position(
        run_id="test_run",
        trade_index=1,
        position=long_position,
        exit_timestamp=exit_timestamp,
        raw_exit_price=110.0,
        exit_reason=ExitReason.TAKE_PROFIT,
        assumptions=assumptions,
        signal_timestamp=entry_timestamp,
        symbol="BTCUSDT",
        timeframe="15m",
        provider="binance",
        regime_at_signal="RANGE",
        holding_bars=2,
    )
    short_trade = close_position(
        run_id="test_run",
        trade_index=2,
        position=short_position,
        exit_timestamp=exit_timestamp,
        raw_exit_price=90.0,
        exit_reason=ExitReason.TAKE_PROFIT,
        assumptions=assumptions,
        signal_timestamp=entry_timestamp,
        symbol="BTCUSDT",
        timeframe="15m",
        provider="binance",
        regime_at_signal="RANGE",
        holding_bars=2,
    )

    assert long_trade.net_pnl > 0
    assert short_trade.net_pnl > 0
    assert long_trade.fees > long_position.entry_fee
    assert short_trade.slippage > 0


def test_close_position_records_notional_cap_in_assumptions_snapshot():
    assumptions = BacktestAssumptions(fee_rate=0.0, slippage_rate=0.0)
    timestamp = datetime(2026, 4, 1)
    position = Position(
        position_id="P1",
        strategy_mode=StrategyMode.GRID_RANGE,
        side=TradeSide.LONG,
        entry_timestamp=timestamp,
        entry_price=100.0,
        quantity=100.0,
        notional=10000.0,
        stop_loss=99.99,
        take_profit=None,
        entry_fee=0.0,
        requested_notional=1000000.0,
        notional_cap=10000.0,
        sizing_notes=["Position notional capped to available equity for no-leverage v0."],
    )

    trade = close_position(
        run_id="test_run",
        trade_index=1,
        position=position,
        exit_timestamp=timestamp + timedelta(minutes=15),
        raw_exit_price=101.0,
        exit_reason=ExitReason.END_OF_DATA,
        assumptions=assumptions,
        signal_timestamp=timestamp,
        symbol="BTCUSDT",
        timeframe="15m",
        provider="binance",
        regime_at_signal="RANGE",
        holding_bars=1,
    )

    assert trade.assumptions_snapshot["sizing"]["capped"] is True
    assert trade.assumptions_snapshot["sizing"]["requested_notional"] == pytest.approx(1000000.0)
    assert trade.assumptions_snapshot["sizing"]["capped_notional"] == pytest.approx(10000.0)


def test_evaluate_exit_returns_end_of_data_on_final_bar():
    position = Position(
        position_id="P1",
        strategy_mode=StrategyMode.GRID_RANGE,
        side=TradeSide.LONG,
        entry_timestamp=datetime(2026, 4, 1),
        entry_price=100.0,
        quantity=1.0,
        notional=100.0,
        stop_loss=95.0,
        take_profit=105.0,
        entry_fee=0.0,
    )
    bar = {"high": 102.0, "low": 98.0, "close": 101.0}

    exit_decision = evaluate_exit(position, bar, is_final_bar=True)

    assert exit_decision is not None
    assert exit_decision.reason == ExitReason.END_OF_DATA
    assert exit_decision.price == 101.0
