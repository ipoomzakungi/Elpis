import json

import polars as pl

from src.backtest.engine import BacktestEngine
from src.backtest.report_store import ReportStore
from src.models.backtest import (
	BaselineMode,
	BacktestRunRequest,
	ReportFormat,
	StrategyConfig,
	StrategyMode,
	TakeProfitConfig,
)


def test_backtest_engine_outputs_strategy_and_baseline_comparisons(isolated_data_paths):
	feature_path = isolated_data_paths / "processed" / "comparison_features.parquet"
	feature_path.parent.mkdir(parents=True, exist_ok=True)
	_comparison_features().write_parquet(feature_path)

	report_store = ReportStore(base_path=isolated_data_paths / "reports")
	engine = BacktestEngine(report_store=report_store)
	result = engine.run(
		BacktestRunRequest(
			symbol="BTCUSDT",
			provider="binance",
			timeframe="15m",
			feature_path=feature_path,
			initial_equity=10000,
			strategies=[
				StrategyConfig(
					mode=StrategyMode.GRID_RANGE,
					entry_threshold=0.15,
					atr_buffer=1.0,
					take_profit=TakeProfitConfig(mode="range_mid"),
					allow_short=True,
				),
				StrategyConfig(
					mode=StrategyMode.BREAKOUT,
					atr_buffer=1.0,
					risk_reward_multiple=1.5,
					allow_short=True,
				),
			],
			baselines=[BaselineMode.BUY_HOLD, BaselineMode.PRICE_BREAKOUT, BaselineMode.NO_TRADE],
			report_format=ReportFormat.JSON,
		)
	)

	run_path = report_store.run_path(result.run_id)
	trades = pl.read_parquet(run_path / "trades.parquet")
	report = json.loads((run_path / "report.json").read_text(encoding="utf-8"))

	assert result.metrics is not None
	assert {"grid_range", "breakout", "buy_hold", "price_breakout", "no_trade"}.issubset(
		result.metrics.return_by_strategy_mode
	)
	assert {"RANGE", "BREAKOUT_UP", "BREAKOUT_DOWN"}.issubset(
		result.metrics.return_by_regime
	)
	assert "binance:BTCUSDT" in result.metrics.return_by_symbol_provider
	assert {row["strategy_mode"] for row in result.metrics.baseline_comparison}.issuperset(
		{"buy_hold", "price_breakout", "no_trade"}
	)
	assert {"grid_range", "breakout", "buy_hold", "price_breakout"}.issubset(
		set(trades["strategy_mode"].to_list())
	)
	assert "baseline_comparison" in report
	assert "return_by_strategy_mode" in report
	assert "return_by_regime" in report


def _comparison_features() -> pl.DataFrame:
	rows = [
		{
			"timestamp": "2026-04-01T00:00:00",
			"open": 101.0,
			"high": 103.0,
			"low": 99.0,
			"close": 102.0,
			"volume": 1000.0,
			"atr": 4.0,
			"range_high": 120.0,
			"range_low": 100.0,
			"range_mid": 110.0,
			"regime": "RANGE",
		},
		{
			"timestamp": "2026-04-01T00:15:00",
			"open": 104.0,
			"high": 112.0,
			"low": 101.0,
			"close": 111.0,
			"volume": 1001.0,
			"atr": 4.0,
			"range_high": 120.0,
			"range_low": 100.0,
			"range_mid": 110.0,
			"regime": "RANGE",
		},
		{
			"timestamp": "2026-04-01T00:30:00",
			"open": 122.0,
			"high": 126.0,
			"low": 121.0,
			"close": 124.0,
			"volume": 1002.0,
			"atr": 5.0,
			"range_high": 120.0,
			"range_low": 100.0,
			"range_mid": 110.0,
			"regime": "BREAKOUT_UP",
		},
		{
			"timestamp": "2026-04-01T00:45:00",
			"open": 125.0,
			"high": 134.0,
			"low": 123.0,
			"close": 131.0,
			"volume": 1003.0,
			"atr": 5.0,
			"range_high": 120.0,
			"range_low": 100.0,
			"range_mid": 110.0,
			"regime": "BREAKOUT_UP",
		},
		{
			"timestamp": "2026-04-01T01:00:00",
			"open": 98.0,
			"high": 99.0,
			"low": 90.0,
			"close": 94.0,
			"volume": 1004.0,
			"atr": 4.0,
			"range_high": 120.0,
			"range_low": 100.0,
			"range_mid": 110.0,
			"regime": "BREAKOUT_DOWN",
		},
		{
			"timestamp": "2026-04-01T01:15:00",
			"open": 94.0,
			"high": 96.0,
			"low": 86.0,
			"close": 88.0,
			"volume": 1005.0,
			"atr": 4.0,
			"range_high": 120.0,
			"range_low": 100.0,
			"range_mid": 110.0,
			"regime": "BREAKOUT_DOWN",
		},
	]
	return pl.DataFrame(rows).with_columns(pl.col("timestamp").str.to_datetime())