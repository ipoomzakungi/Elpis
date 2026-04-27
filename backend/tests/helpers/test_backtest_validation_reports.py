from datetime import datetime, timedelta

from src.models.backtest import (
    BacktestRun,
    BacktestRunRequest,
    BacktestStatus,
    EquityPoint,
    ExitReason,
    MetricsSummary,
    StrategyMode,
    TradeRecord,
    TradeSide,
)


def make_trade_record(
    index: int = 1,
    strategy_mode: StrategyMode = StrategyMode.GRID_RANGE,
    net_pnl: float = 25.0,
    notional: float = 1000.0,
) -> TradeRecord:
    timestamp = datetime(2026, 4, 1) + timedelta(minutes=15 * index)
    return TradeRecord(
        trade_id=f"T{index:06d}",
        run_id="test_run",
        strategy_mode=strategy_mode,
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
        quantity=notional / 100.0,
        notional=notional,
        gross_pnl=net_pnl,
        fees=0.0,
        slippage=0.0,
        net_pnl=net_pnl,
        return_pct=net_pnl / notional,
        holding_bars=1,
    )


def make_equity_point(
    index: int = 0,
    strategy_mode: StrategyMode = StrategyMode.GRID_RANGE,
    equity: float = 10000.0,
    realized_pnl: float = 0.0,
    open_position: bool = False,
) -> EquityPoint:
    return EquityPoint(
        timestamp=datetime(2026, 4, 1) + timedelta(minutes=15 * index),
        strategy_mode=strategy_mode,
        equity=equity,
        drawdown=0.0,
        drawdown_pct=0.0,
        realized_pnl=realized_pnl,
        open_position=open_position,
    )


def make_metrics_summary() -> MetricsSummary:
    return MetricsSummary(
        total_return=0.0,
        total_return_pct=0.0,
        max_drawdown=0.0,
        max_drawdown_pct=0.0,
        number_of_trades=0,
        max_consecutive_losses=0,
    )


def make_backtest_run(feature_path: str = "data/processed/test_features.parquet") -> BacktestRun:
    return BacktestRun(
        run_id="test_run",
        status=BacktestStatus.COMPLETED,
        created_at=datetime(2026, 4, 1),
        completed_at=datetime(2026, 4, 1, 0, 1),
        symbol="BTCUSDT",
        provider="binance",
        timeframe="15m",
        feature_path=feature_path,
        config=BacktestRunRequest(baselines=[]),
    )