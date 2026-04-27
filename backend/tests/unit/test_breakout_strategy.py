from datetime import datetime, timedelta

from src.models.backtest import StrategyConfig, StrategyMode, TradeSide
from src.strategies.breakout_strategy import generate_breakout_signals


def _row(index: int, close: float, regime: str) -> dict:
	timestamp = datetime(2026, 4, 1) + timedelta(minutes=15 * index)
	return {
		"timestamp": timestamp,
		"open": close,
		"high": close + 2.0,
		"low": close - 2.0,
		"close": close,
		"atr": 5.0,
		"range_high": 120.0,
		"range_low": 100.0,
		"range_mid": 110.0,
		"regime": regime,
	}


def test_breakout_generates_long_for_breakout_up():
	rows = [_row(0, 124.0, "BREAKOUT_UP"), _row(1, 125.0, "BREAKOUT_UP")]
	config = StrategyConfig(mode=StrategyMode.BREAKOUT, atr_buffer=1.0, risk_reward_multiple=2.0)

	signals = generate_breakout_signals(rows, config=config, allow_short=True)

	assert len(signals) == 1
	signal = signals[0]
	assert signal.side == TradeSide.LONG
	assert signal.entry_bar_index == 1
	assert signal.stop_loss == 119.0
	assert signal.take_profit == 134.0
	assert signal.regime == "BREAKOUT_UP"


def test_breakout_generates_optional_short_for_breakout_down():
	rows = [_row(0, 96.0, "BREAKOUT_DOWN"), _row(1, 95.0, "BREAKOUT_DOWN")]
	config = StrategyConfig(mode=StrategyMode.BREAKOUT, atr_buffer=1.0, risk_reward_multiple=1.5)

	short_signals = generate_breakout_signals(rows, config=config, allow_short=True)
	long_only_signals = generate_breakout_signals(rows, config=config, allow_short=False)

	assert len(short_signals) == 1
	assert short_signals[0].side == TradeSide.SHORT
	assert short_signals[0].entry_bar_index == 1
	assert short_signals[0].stop_loss == 101.0
	assert short_signals[0].take_profit == 88.5
	assert long_only_signals == []


def test_breakout_suppresses_non_breakout_regimes_and_final_bar_signals():
	rows = [_row(0, 124.0, "RANGE"), _row(1, 126.0, "BREAKOUT_UP")]
	config = StrategyConfig(mode=StrategyMode.BREAKOUT, atr_buffer=1.0, risk_reward_multiple=2.0)

	signals = generate_breakout_signals(rows, config=config, allow_short=True)

	assert signals == []
