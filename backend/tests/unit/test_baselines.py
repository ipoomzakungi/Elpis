from datetime import datetime, timedelta

from src.models.backtest import StrategyMode, TradeSide
from src.strategies.baselines import (
	generate_buy_hold_signals,
	generate_no_trade_signals,
	generate_price_breakout_signals,
)


def _row(index: int, close: float, range_high: float = 120.0, range_low: float = 100.0) -> dict:
	timestamp = datetime(2026, 4, 1) + timedelta(minutes=15 * index)
	return {
		"timestamp": timestamp,
		"open": close,
		"high": close + 2.0,
		"low": close - 2.0,
		"close": close,
		"atr": 4.0,
		"range_high": range_high,
		"range_low": range_low,
		"range_mid": (range_high + range_low) / 2,
		"regime": "AVOID",
	}


def test_buy_hold_generates_single_long_signal_without_regime_filter():
	rows = [_row(0, 110.0), _row(1, 112.0), _row(2, 114.0)]

	signals = generate_buy_hold_signals(rows)

	assert len(signals) == 1
	assert signals[0].strategy_mode == StrategyMode.BUY_HOLD
	assert signals[0].side == TradeSide.LONG
	assert signals[0].entry_bar_index == 1
	assert signals[0].stop_loss == 0.01
	assert signals[0].take_profit is None


def test_price_breakout_baseline_uses_price_only_without_regime_filter():
	rows = [_row(0, 124.0), _row(1, 126.0), _row(2, 96.0), _row(3, 94.0)]

	signals = generate_price_breakout_signals(rows, allow_short=True)

	assert [signal.side for signal in signals] == [TradeSide.LONG, TradeSide.SHORT]
	assert [signal.strategy_mode for signal in signals] == [
		StrategyMode.PRICE_BREAKOUT,
		StrategyMode.PRICE_BREAKOUT,
	]
	assert signals[0].entry_bar_index == 1
	assert signals[1].entry_bar_index == 3


def test_price_breakout_respects_short_setting_and_no_trade_is_empty():
	rows = [_row(0, 96.0), _row(1, 94.0)]

	assert generate_price_breakout_signals(rows, allow_short=False) == []
	assert generate_no_trade_signals() == []
