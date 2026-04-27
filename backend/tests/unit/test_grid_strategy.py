from datetime import datetime, timedelta

from src.models.backtest import StrategyConfig, StrategyMode, TakeProfitConfig, TradeSide
from src.strategies.grid_strategy import generate_grid_range_signals


def _row(index: int, close: float, regime: str = "RANGE") -> dict:
	timestamp = datetime(2026, 4, 1) + timedelta(minutes=15 * index)
	return {
		"timestamp": timestamp,
		"open": close,
		"high": close + 2.0,
		"low": close - 2.0,
		"close": close,
		"atr": 4.0,
		"range_high": 120.0,
		"range_low": 100.0,
		"range_mid": 110.0,
		"regime": regime,
	}


def test_grid_range_generates_long_near_lower_range_only_in_range_regime():
	rows = [_row(0, 102.0), _row(1, 105.0), _row(2, 115.0, regime="AVOID")]
	config = StrategyConfig(
		mode=StrategyMode.GRID_RANGE,
		entry_threshold=0.15,
		atr_buffer=1.0,
		take_profit=TakeProfitConfig(mode="range_mid"),
	)

	signals = generate_grid_range_signals(rows, config=config, allow_short=True)

	assert len(signals) == 1
	signal = signals[0]
	assert signal.strategy_mode == StrategyMode.GRID_RANGE
	assert signal.side == TradeSide.LONG
	assert signal.entry_bar_index == 1
	assert signal.stop_loss == 96.0
	assert signal.take_profit == 110.0
	assert signal.regime == "RANGE"


def test_grid_range_generates_optional_short_near_upper_range():
	rows = [_row(0, 118.0), _row(1, 115.0)]
	config = StrategyConfig(mode=StrategyMode.GRID_RANGE, entry_threshold=0.15, atr_buffer=0.5)

	short_signals = generate_grid_range_signals(rows, config=config, allow_short=True)
	long_only_signals = generate_grid_range_signals(rows, config=config, allow_short=False)

	assert len(short_signals) == 1
	assert short_signals[0].side == TradeSide.SHORT
	assert short_signals[0].entry_bar_index == 1
	assert short_signals[0].stop_loss == 122.0
	assert short_signals[0].take_profit == 110.0
	assert long_only_signals == []


def test_grid_range_skips_final_bar_signals_without_next_open():
	rows = [_row(0, 105.0), _row(1, 101.0)]
	config = StrategyConfig(mode=StrategyMode.GRID_RANGE, entry_threshold=0.2)

	signals = generate_grid_range_signals(rows, config=config, allow_short=True)

	assert signals == []
