import hashlib
import json
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
from src.strategies.baselines import (
    generate_buy_hold_signals,
    generate_no_trade_signals,
    generate_price_breakout_signals,
)
from src.strategies.breakout_strategy import generate_breakout_signals
from src.strategies.grid_strategy import generate_grid_range_signals

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
BACKTEST_LIMITATIONS = [
    RESEARCH_ONLY_WARNING,
    NO_INTRABAR_LIMITATION,
    "Signals are simulated at the next bar open; no intrabar tick order is inferred.",
    "v0 assumes no leverage, no compounding, and at most one open position per strategy mode.",
]


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
        data_identity = self._data_identity(features, feature_path, request)

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
            config_hash=self._config_hash(request),
            data_identity=data_identity,
            limitations=BACKTEST_LIMITATIONS,
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
        baseline_modes = self._requested_baselines(request, enabled_strategies)
        if not enabled_strategies and baseline_modes == [BaselineMode.NO_TRADE]:
            warnings.append("No-trade baseline selected; no simulated positions were opened.")
            return []
        if len(rows) < 2:
            warnings.append("Not enough bars to enter on the next bar open.")
            return []

        signals_by_mode = self._signals_by_mode(request, rows, enabled_strategies, baseline_modes)
        trades: list[TradeRecord] = []
        for signals in signals_by_mode.values():
            trades.extend(
                self._simulate_signals(
                    run_id=run_id,
                    request=request,
                    rows=rows,
                    signals=signals,
                    starting_trade_index=len(trades) + 1,
                )
            )

        if not trades and signals_by_mode:
            warnings.append("No valid signals produced completed trades for this run.")
        elif not signals_by_mode:
            warnings.append("No strategy or baseline signals were requested for this run.")
        return trades

    def _requested_baselines(
        self,
        request: BacktestRunRequest,
        enabled_strategies: list[StrategyConfig],
    ) -> list[BaselineMode]:
        if enabled_strategies and "baselines" not in request.model_fields_set:
            return []
        return list(request.baselines)

    def _signals_by_mode(
        self,
        request: BacktestRunRequest,
        rows: list[dict[str, Any]],
        enabled_strategies: list[StrategyConfig],
        baseline_modes: list[BaselineMode],
    ) -> dict[StrategyMode, list]:
        signals_by_mode: dict[StrategyMode, list] = {}
        for strategy in enabled_strategies:
            allow_short = strategy.allow_short
            if allow_short is None:
                allow_short = request.assumptions.allow_short
            if strategy.mode == StrategyMode.GRID_RANGE:
                signals_by_mode[StrategyMode.GRID_RANGE] = generate_grid_range_signals(
                    rows,
                    config=strategy,
                    allow_short=allow_short,
                )
            elif strategy.mode == StrategyMode.BREAKOUT:
                signals_by_mode[StrategyMode.BREAKOUT] = generate_breakout_signals(
                    rows,
                    config=strategy,
                    allow_short=allow_short,
                )
            elif strategy.mode == StrategyMode.NO_TRADE:
                signals_by_mode[StrategyMode.NO_TRADE] = generate_no_trade_signals()

        for baseline_mode in baseline_modes:
            if baseline_mode == BaselineMode.BUY_HOLD:
                signals_by_mode[StrategyMode.BUY_HOLD] = generate_buy_hold_signals(rows)
            elif baseline_mode == BaselineMode.PRICE_BREAKOUT:
                signals_by_mode[StrategyMode.PRICE_BREAKOUT] = generate_price_breakout_signals(
                    rows,
                    allow_short=request.assumptions.allow_short,
                )
            elif baseline_mode == BaselineMode.NO_TRADE:
                signals_by_mode[StrategyMode.NO_TRADE] = generate_no_trade_signals()

        return signals_by_mode

    def _simulate_signals(
        self,
        run_id: str,
        request: BacktestRunRequest,
        rows: list[dict[str, Any]],
        signals: list,
        starting_trade_index: int,
    ) -> list[TradeRecord]:
        trades: list[TradeRecord] = []
        next_available_entry_index = 1
        for signal in signals:
            if signal.entry_bar_index >= len(rows):
                continue
            if signal.entry_bar_index < next_available_entry_index:
                continue

            position = self._open_position_from_signal(
                request=request,
                rows=rows,
                signal=signal,
                position_index=starting_trade_index + len(trades),
            )
            for index in range(signal.entry_bar_index, len(rows)):
                exit_decision = evaluate_exit(
                    position=position,
                    bar=rows[index],
                    is_final_bar=index == len(rows) - 1,
                )
                if exit_decision is None:
                    continue

                trades.append(
                    close_position(
                        run_id=run_id,
                        trade_index=starting_trade_index + len(trades),
                        position=position,
                        exit_timestamp=rows[index]["timestamp"],
                        raw_exit_price=exit_decision.price,
                        exit_reason=exit_decision.reason,
                        assumptions=request.assumptions,
                        signal_timestamp=signal.signal_timestamp,
                        symbol=request.symbol,
                        timeframe=request.timeframe,
                        provider=request.provider,
                        regime_at_signal=signal.regime,
                        holding_bars=max(0, index - signal.entry_bar_index),
                    )
                )
                next_available_entry_index = index + 1
                break
        return trades

    def _open_position_from_signal(
        self,
        request: BacktestRunRequest,
        rows: list[dict[str, Any]],
        signal,
        position_index: int,
    ) -> Position:
        entry_bar = rows[signal.entry_bar_index]
        entry_raw_price = float(entry_bar["open"])
        entry_price = apply_entry_slippage(
            side=signal.side,
            price=entry_raw_price,
            slippage_rate=request.assumptions.slippage_rate,
        )
        quantity, notional = calculate_position_size(
            equity=request.initial_equity,
            entry_price=entry_price,
            stop_loss=signal.stop_loss,
            risk_per_trade=request.assumptions.risk_per_trade,
        )
        entry_fee = calculate_entry_fee(notional, request.assumptions.fee_rate)

        return Position(
            position_id=f"P{position_index:06d}",
            strategy_mode=signal.strategy_mode,
            side=signal.side,
            entry_timestamp=entry_bar["timestamp"],
            entry_price=entry_price,
            quantity=quantity,
            notional=notional,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            entry_fee=entry_fee,
        )

    def _build_equity_curve(
        self,
        request: BacktestRunRequest,
        rows: list[dict[str, Any]],
        trades: list[TradeRecord],
    ) -> list[EquityPoint]:
        equity_curve: list[EquityPoint] = []
        modes = self._equity_modes(request, trades)

        for mode in modes:
            mode_trades = [trade for trade in trades if trade.strategy_mode == mode]
            equity_curve.extend(self._build_mode_equity_curve(request, rows, mode_trades, mode))

        return equity_curve

    def _build_mode_equity_curve(
        self,
        request: BacktestRunRequest,
        rows: list[dict[str, Any]],
        trades: list[TradeRecord],
        strategy_mode: StrategyMode,
    ) -> list[EquityPoint]:
        realized_pnl = 0.0
        peak_equity = request.initial_equity
        trades_by_exit_timestamp: dict[Any, list[TradeRecord]] = {}
        for trade in trades:
            trades_by_exit_timestamp.setdefault(trade.exit_timestamp, []).append(trade)
        entry_timestamps = {trade.entry_timestamp for trade in trades}
        exit_timestamps = {trade.exit_timestamp for trade in trades}
        equity_curve: list[EquityPoint] = []

        for row in rows:
            timestamp = row["timestamp"]
            for trade in trades_by_exit_timestamp.get(timestamp, []):
                realized_pnl += trade.net_pnl
            equity = request.initial_equity + realized_pnl
            peak_equity = max(peak_equity, equity)
            drawdown = (equity - peak_equity) / peak_equity if peak_equity else 0.0
            equity_curve.append(
                EquityPoint(
                    timestamp=timestamp,
                    strategy_mode=strategy_mode,
                    equity=equity,
                    drawdown=drawdown,
                    drawdown_pct=drawdown * 100,
                    realized_pnl=realized_pnl,
                    open_position=timestamp in entry_timestamps
                    and timestamp not in exit_timestamps,
                )
            )

        return equity_curve

    def _equity_modes(
        self,
        request: BacktestRunRequest,
        trades: list[TradeRecord],
    ) -> list[StrategyMode]:
        modes: list[StrategyMode] = []
        for strategy in request.strategies:
            if strategy.enabled and strategy.mode not in modes:
                modes.append(strategy.mode)
        for baseline in self._requested_baselines(
            request,
            [strategy for strategy in request.strategies if strategy.enabled],
        ):
            mode = StrategyMode(baseline.value)
            if mode not in modes:
                modes.append(mode)
        for trade in trades:
            if trade.strategy_mode not in modes:
                modes.append(trade.strategy_mode)
        if not modes:
            return [StrategyMode.NO_TRADE]
        return modes

    def _run_id(self, request: BacktestRunRequest) -> str:
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
        return f"bt_{timestamp}_{request.symbol.lower()}_{request.timeframe}"

    def _config_hash(self, request: BacktestRunRequest) -> str:
        payload = json.dumps(request.model_dump(mode="json"), sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _data_identity(
        self,
        features: pl.DataFrame,
        feature_path: Path,
        request: BacktestRunRequest,
    ) -> dict[str, Any]:
        sorted_features = features.sort("timestamp")
        first_timestamp = _timestamp_to_text(sorted_features["timestamp"][0])
        last_timestamp = _timestamp_to_text(sorted_features["timestamp"][-1])
        content_hash = hashlib.sha256(feature_path.read_bytes()).hexdigest()
        return {
            "provider": request.provider,
            "symbol": request.symbol,
            "timeframe": request.timeframe,
            "feature_path": feature_path.as_posix(),
            "exists": feature_path.exists(),
            "row_count": features.height,
            "first_timestamp": first_timestamp,
            "last_timestamp": last_timestamp,
            "columns": list(features.columns),
            "content_hash": content_hash,
        }


def _timestamp_to_text(value: Any) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value)
