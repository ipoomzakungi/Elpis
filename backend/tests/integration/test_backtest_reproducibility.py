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


def test_backtest_rerun_reproduces_stable_artifacts(sample_backtest_features, isolated_data_paths):
	feature_path = isolated_data_paths / "processed" / "btcusdt_15m_features.parquet"
	feature_path.parent.mkdir(parents=True, exist_ok=True)
	sample_backtest_features.write_parquet(feature_path)

	report_store = ReportStore(base_path=isolated_data_paths / "reports")
	engine = BacktestEngine(report_store=report_store)
	request = BacktestRunRequest(
		symbol="BTCUSDT",
		provider="binance",
		timeframe="15m",
		feature_path=feature_path,
		initial_equity=10000,
		strategies=[
			StrategyConfig(
				mode=StrategyMode.GRID_RANGE,
				enabled=True,
				allow_short=True,
				entry_threshold=0.2,
				atr_buffer=1.0,
				take_profit=TakeProfitConfig(mode="range_mid"),
			),
			StrategyConfig(
				mode=StrategyMode.BREAKOUT,
				enabled=True,
				allow_short=True,
				atr_buffer=1.0,
				risk_reward_multiple=1.5,
			),
		],
		baselines=[BaselineMode.BUY_HOLD, BaselineMode.PRICE_BREAKOUT, BaselineMode.NO_TRADE],
		report_format=ReportFormat.BOTH,
	)

	first = engine.run(request)
	second = engine.run(request)

	first_path = report_store.run_path(first.run_id)
	second_path = report_store.run_path(second.run_id)

	assert _stable_trades(first_path / "trades.parquet") == _stable_trades(
		second_path / "trades.parquet"
	)
	assert _stable_equity(first_path / "equity.parquet") == _stable_equity(
		second_path / "equity.parquet"
	)
	assert _read_json(first_path / "metrics.json") == _read_json(second_path / "metrics.json")

	first_metadata = _read_json(first_path / "metadata.json")
	second_metadata = _read_json(second_path / "metadata.json")
	assert first_metadata["config"] == second_metadata["config"]
	assert first_metadata["data_identity"] == second_metadata["data_identity"]
	assert first_metadata["limitations"] == second_metadata["limitations"]
	assert first_metadata["warnings"] == second_metadata["warnings"]

	report = _read_json(first_path / "report.json")
	assert report["data_identity"]["content_hash"]
	assert report["assumptions"]["leverage"] == 1
	assert any("intrabar" in limitation.lower() for limitation in report["limitations"])


def _stable_trades(path) -> list[dict]:
	frame = pl.read_parquet(path).drop("run_id")
	return frame.to_dicts()


def _stable_equity(path) -> list[dict]:
	return pl.read_parquet(path).to_dicts()


def _read_json(path) -> dict:
	return json.loads(path.read_text(encoding="utf-8"))