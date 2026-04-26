import polars as pl

from src.backtest.engine import BacktestEngine
from src.backtest.report_store import ReportStore
from src.models.backtest import (
    BacktestRunRequest,
    BacktestStatus,
    ReportArtifactType,
    StrategyConfig,
    StrategyMode,
)


def test_backtest_engine_writes_deterministic_artifacts(
    sample_backtest_features: pl.DataFrame,
    isolated_data_paths,
):
    feature_path = isolated_data_paths / "processed" / "synthetic_features.parquet"
    feature_path.parent.mkdir(parents=True, exist_ok=True)
    sample_backtest_features.write_parquet(feature_path)
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
                    enabled=True,
                    atr_buffer=1.0,
                    risk_reward_multiple=1.0,
                )
            ],
        )
    )

    artifact_types = {artifact.artifact_type for artifact in result.artifacts}
    run_path = report_store.run_path(result.run_id)

    assert result.status == BacktestStatus.COMPLETED
    assert result.metrics is not None
    assert result.metrics.number_of_trades >= 1
    assert ReportArtifactType.METADATA in artifact_types
    assert ReportArtifactType.CONFIG in artifact_types
    assert ReportArtifactType.TRADES in artifact_types
    assert ReportArtifactType.EQUITY in artifact_types
    assert ReportArtifactType.METRICS in artifact_types
    assert ReportArtifactType.REPORT_JSON in artifact_types
    assert (run_path / "metadata.json").exists()
    assert (run_path / "config.json").exists()
    assert (run_path / "trades.parquet").exists()
    assert (run_path / "equity.parquet").exists()
    assert (run_path / "metrics.json").exists()
    assert (run_path / "report.json").exists()

    trades = pl.read_parquet(run_path / "trades.parquet")
    equity = pl.read_parquet(run_path / "equity.parquet")

    assert trades.height == result.metrics.number_of_trades
    assert equity.height == sample_backtest_features.height
    assert trades["entry_timestamp"][0] == sample_backtest_features["timestamp"][1]


def test_backtest_engine_writes_inspectable_no_trade_artifacts(
    sample_backtest_features: pl.DataFrame,
    isolated_data_paths,
):
    feature_path = isolated_data_paths / "processed" / "synthetic_features.parquet"
    feature_path.parent.mkdir(parents=True, exist_ok=True)
    sample_backtest_features.write_parquet(feature_path)
    report_store = ReportStore(base_path=isolated_data_paths / "reports")
    engine = BacktestEngine(report_store=report_store)

    result = engine.run(
        BacktestRunRequest(
            symbol="BTCUSDT",
            provider="binance",
            timeframe="15m",
            feature_path=feature_path,
            initial_equity=10000,
            strategies=[],
            baselines=["no_trade"],
        )
    )

    trades = pl.read_parquet(report_store.run_path(result.run_id) / "trades.parquet")
    equity = pl.read_parquet(report_store.run_path(result.run_id) / "equity.parquet")

    assert result.status == BacktestStatus.COMPLETED
    assert result.metrics is not None
    assert result.metrics.number_of_trades == 0
    assert trades.height == 0
    assert equity["equity"].to_list() == [10000.0] * sample_backtest_features.height
