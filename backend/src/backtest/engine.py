from datetime import datetime
from pathlib import Path
from typing import Any

import polars as pl

from src.backtest.metrics import calculate_metrics
from src.backtest.portfolio import (
    apply_entry_slippage,
    calculate_entry_fee,
    calculate_position_size,
    close_position,
    evaluate_exit,
)
from src.backtest.report_store import ReportStore
from src.config import get_settings
from src.models.backtest import (
    BacktestRun,
    BacktestRunRequest,
    BacktestRunResponse,
    BacktestStatus,
    BaselineMode,
    EquityPoint,
    Position,
    StrategyConfig,
    StrategyMode,
    TradeRecord,
    TradeSide,
)
from src.reports.writer import NO_INTRABAR_LIMITATION, RESEARCH_ONLY_WARNING
from src.repositories.parquet_repo import ParquetRepository

BASE_REQUIRED_COLUMNS = {
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "atr",
    "range_high",
    "range_low",
    "range_mid",
}
REGIME_REQUIRED_MODES = {StrategyMode.GRID_RANGE, StrategyMode.BREAKOUT}


class BacktestFeatureNotFoundError(FileNotFoundError):
    def __init__(self, symbol: str, timeframe: str, feature_path: Path):
        self.symbol = symbol
        self.timeframe = timeframe
        self.feature_path = feature_path
        super().__init__(str(feature_path))


class BacktestEngine:
    def __init__(
        self,
        repository: ParquetRepository | None = None,
        report_store: ReportStore | None = None,
    ):
        self.repository = repository or ParquetRepository()
        self.report_store = report_store or ReportStore()

    def run(self, request: BacktestRunRequest) -> BacktestRunResponse:
        features, feature_path = self._load_features(request)
        self._validate_features(features, request)

        rows = features.sort("timestamp").to_dicts()
        run_id = self._run_id(request)
        warnings = [RESEARCH_ONLY_WARNING, NO_INTRABAR_LIMITATION]

        trades = self._simulate_trades(run_id, request, rows, warnings)
        equity_curve = self._build_equity_curve(request, rows, trades)
        metrics = calculate_metrics(
            trades=trades,
            equity_curve=equity_curve,
            initial_equity=request.initial_equity,
        )
        run = BacktestRun(
            run_id=run_id,
            status=BacktestStatus.COMPLETED,
            created_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            symbol=request.symbol,
            provider=request.provider,
            timeframe=request.timeframe,
            feature_path=feature_path.as_posix(),
            config=request,
            artifacts=[],
            warnings=warnings,
        )
        run = self.report_store.write_run_outputs(
            run=run,
            trades=trades,
            equity_curve=equity_curve,
            metrics=metrics,
            report_format=request.report_format,
        )
        return BacktestRunResponse(**run.model_dump(), metrics=metrics)

    def _load_features(self, request: BacktestRunRequest) -> tuple[pl.DataFrame, Path]:
        if request.feature_path is not None:
            feature_path = Path(request.feature_path)
            if not feature_path.exists():
                raise BacktestFeatureNotFoundError(request.symbol, request.timeframe, feature_path)
            return pl.read_parquet(feature_path), feature_path

        feature_path = self._default_feature_path(request.symbol, request.timeframe)
        features = self.repository.load_features(symbol=request.symbol, interval=request.timeframe)
        if features is None:
            raise BacktestFeatureNotFoundError(request.symbol, request.timeframe, feature_path)
        return features, feature_path

    def _default_feature_path(self, symbol: str, timeframe: str) -> Path:
        settings = get_settings()
        return settings.data_processed_path / f"{symbol.lower()}_{timeframe}_features.parquet"

    def _validate_features(self, features: pl.DataFrame, request: BacktestRunRequest) -> None:
        if features.is_empty():
            raise ValueError("processed feature data is empty")

        required_columns = set(BASE_REQUIRED_COLUMNS)
        if any(strategy.mode in REGIME_REQUIRED_MODES for strategy in request.strategies):
            required_columns.add("regime")

        missing = sorted(required_columns - set(features.columns))
        if missing:
            raise ValueError(f"processed features missing required columns: {', '.join(missing)}")

    def _simulate_trades(
        self,
        run_id: str,
        request: BacktestRunRequest,
        rows: list[dict[str, Any]],
        warnings: list[str],
    ) -> list[TradeRecord]:
        enabled_strategies = [strategy for strategy in request.strategies if strategy.enabled]
        if not enabled_strategies and request.baselines == [BaselineMode.NO_TRADE]:
            warnings.append("No-trade baseline selected; no simulated positions were opened.")
            return []
        if len(rows) < 2:
            warnings.append("Not enough bars to enter on the next bar open.")
            return []

        strategy = (
            enabled_strategies[0]
            if enabled_strategies
            else StrategyConfig(mode=StrategyMode.NO_TRADE)
        )
        if strategy.mode == StrategyMode.NO_TRADE:
            warnings.append("No-trade strategy selected; no simulated positions were opened.")
            return []

        position = self._open_first_position(request, rows, strategy)
        if position is None:
            warnings.append("No valid signal had a next bar open for entry.")
            return []

        signal_timestamp = rows[0]["timestamp"]
        for index in range(1, len(rows)):
            exit_decision = evaluate_exit(
                position=position,
                bar=rows[index],
                is_final_bar=index == len(rows) - 1,
            )
            if exit_decision is None:
                continue
            return [
                close_position(
                    run_id=run_id,
                    trade_index=1,
                    position=position,
                    exit_timestamp=rows[index]["timestamp"],
                    raw_exit_price=exit_decision.price,
                    exit_reason=exit_decision.reason,
                    assumptions=request.assumptions,
                    signal_timestamp=signal_timestamp,
                    symbol=request.symbol,
                    timeframe=request.timeframe,
                    provider=request.provider,
                    regime_at_signal=rows[0].get("regime"),
                    holding_bars=max(0, index - 1),
                )
            ]

        return []

    def _open_first_position(
        self,
        request: BacktestRunRequest,
        rows: list[dict[str, Any]],
        strategy: StrategyConfig,
    ) -> Position | None:
        entry_bar = rows[1]
        signal_bar = rows[0]
        entry_raw_price = float(entry_bar["open"])
        atr = float(signal_bar.get("atr") or 0.0)
        stop_distance = max(atr * (strategy.atr_buffer or 1.0), entry_raw_price * 0.005, 0.01)
        stop_loss = max(0.01, entry_raw_price - stop_distance)
        risk_reward = strategy.risk_reward_multiple or 1.0
        take_profit = entry_raw_price + (entry_raw_price - stop_loss) * risk_reward

        if strategy.take_profit and strategy.take_profit.mode == "range_mid":
            range_mid = float(signal_bar.get("range_mid") or 0.0)
            if range_mid > entry_raw_price:
                take_profit = range_mid

        entry_price = apply_entry_slippage(
            side=TradeSide.LONG,
            price=entry_raw_price,
            slippage_rate=request.assumptions.slippage_rate,
        )
        quantity, notional = calculate_position_size(
            equity=request.initial_equity,
            entry_price=entry_price,
            stop_loss=stop_loss,
            risk_per_trade=request.assumptions.risk_per_trade,
        )
        entry_fee = calculate_entry_fee(notional, request.assumptions.fee_rate)

        return Position(
            position_id="P000001",
            strategy_mode=strategy.mode,
            side=TradeSide.LONG,
            entry_timestamp=entry_bar["timestamp"],
            entry_price=entry_price,
            quantity=quantity,
            notional=notional,
            stop_loss=stop_loss,
            take_profit=take_profit,
            entry_fee=entry_fee,
        )

    def _build_equity_curve(
        self,
        request: BacktestRunRequest,
        rows: list[dict[str, Any]],
        trades: list[TradeRecord],
    ) -> list[EquityPoint]:
        realized_pnl = 0.0
        peak_equity = request.initial_equity
        trade_by_exit_timestamp = {trade.exit_timestamp: trade for trade in trades}
        entry_timestamps = {trade.entry_timestamp for trade in trades}
        exit_timestamps = {trade.exit_timestamp for trade in trades}
        equity_curve: list[EquityPoint] = []

        for row in rows:
            timestamp = row["timestamp"]
            if timestamp in trade_by_exit_timestamp:
                realized_pnl += trade_by_exit_timestamp[timestamp].net_pnl
            equity = request.initial_equity + realized_pnl
            peak_equity = max(peak_equity, equity)
            drawdown = (equity - peak_equity) / peak_equity if peak_equity else 0.0
            equity_curve.append(
                EquityPoint(
                    timestamp=timestamp,
                    strategy_mode=trades[0].strategy_mode if trades else StrategyMode.NO_TRADE,
                    equity=equity,
                    drawdown=drawdown,
                    drawdown_pct=drawdown * 100,
                    realized_pnl=realized_pnl,
                    open_position=timestamp in entry_timestamps
                    and timestamp not in exit_timestamps,
                )
            )

        return equity_curve

    def _run_id(self, request: BacktestRunRequest) -> str:
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
        return f"bt_{timestamp}_{request.symbol.lower()}_{request.timeframe}"
