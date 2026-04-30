from dataclasses import dataclass
from datetime import datetime
from itertools import product
from pathlib import Path

import polars as pl

from src.backtest.engine import BacktestEngine, BacktestFeatureNotFoundError
from src.backtest.metrics import calculate_trade_concentration
from src.backtest.report_store import ReportStore
from src.models.backtest import (
    BacktestRunRequest,
    BacktestRunResponse,
    BacktestStatus,
    CostStressProfile,
    CostStressProfileName,
    ModeMetrics,
    ParameterSensitivityResult,
    RegimeCoverageReport,
    SensitivityGrid,
    StrategyConfig,
    StrategyMode,
    StressOutcome,
    StressResult,
    TradeRecord,
    ValidationConcentrationResponse,
    ValidationRun,
    ValidationRunListResponse,
    ValidationRunRequest,
    ValidationSensitivityResponse,
    ValidationSplitStatus,
    ValidationStressResponse,
    ValidationWalkForwardResponse,
    WalkForwardConfig,
    WalkForwardResult,
)
from src.reports.writer import RESEARCH_ONLY_WARNING

MAX_SENSITIVITY_GRID_SIZE = 64
HIGH_FEE_RATE = 0.001
HIGH_SLIPPAGE_RATE = 0.001


@dataclass(frozen=True)
class WalkForwardFeatureSplit:
    split_id: str
    frame: pl.DataFrame
    start_timestamp: datetime
    end_timestamp: datetime
    row_count: int
    status: ValidationSplitStatus
    notes: list[str]


class ValidationExecutionNotImplementedError(NotImplementedError):
    """Raised while validation execution is still a scaffold."""


class ValidationReportService:
    def __init__(self, report_store: ReportStore | None = None):
        self.report_store = report_store or ReportStore()

    def run(self, request: ValidationRunRequest) -> ValidationRun:
        validation_run_id = _validation_run_id(request)
        base_result = self._run_backtest(request.base_config)
        stress_results = self.run_cost_stress(request)
        sensitivity_results = self.run_parameter_sensitivity(request)
        walk_forward_results = self.run_walk_forward(
            request=request,
            validation_run_id=validation_run_id,
        )
        base_features = _load_validation_features(request.base_config)
        base_trades = self.report_store.read_all_trades(base_result.run_id)
        base_equity = self.report_store.read_equity_curve(base_result.run_id)
        regime_coverage = calculate_regime_coverage(
            features=base_features,
            trades=base_trades,
        )
        concentration_report = calculate_trade_concentration(
            trades=base_trades,
            equity_curve=base_equity,
        )
        validation_run = ValidationRun(
            validation_run_id=validation_run_id,
            status=BacktestStatus.COMPLETED,
            created_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            symbol=request.base_config.symbol,
            provider=request.base_config.provider,
            timeframe=request.base_config.timeframe,
            source_backtest_config=request.base_config,
            data_identity=base_result.data_identity,
            mode_metrics=_mode_metrics_from_response(base_result),
            stress_results=stress_results,
            sensitivity_results=sensitivity_results,
            walk_forward_results=walk_forward_results,
            regime_coverage=regime_coverage,
            concentration_report=concentration_report,
            warnings=[
                RESEARCH_ONLY_WARNING,
                "Cost stress and parameter sensitivity outputs are bounded research checks only.",
                (
                    "Walk-forward outputs are chronological validation windows only; "
                    "no model training occurred."
                ),
            ],
        )
        return self.report_store.write_validation_outputs(validation_run)

    def run_cost_stress(self, request: ValidationRunRequest) -> list[StressResult]:
        profiles = build_cost_stress_profiles(
            base_fee_rate=request.base_config.assumptions.fee_rate,
            base_slippage_rate=request.base_config.assumptions.slippage_rate,
            selected_names=request.stress_profiles,
        )
        normal_returns: dict[StrategyMode, float | None] = {}
        results: list[StressResult] = []

        for profile in profiles:
            response = self._run_backtest(_request_with_cost_profile(request.base_config, profile))
            mode_metrics = _mode_metrics_from_response(response)
            if profile.name == CostStressProfileName.NORMAL:
                normal_returns = {
                    metric.strategy_mode: metric.total_return_pct for metric in mode_metrics
                }
            for metric in mode_metrics:
                outcome = _stress_outcome(metric, normal_returns.get(metric.strategy_mode))
                results.append(
                    StressResult(
                        profile=profile,
                        strategy_mode=metric.strategy_mode,
                        category=metric.category,
                        metrics=metric,
                        outcome=outcome,
                        notes=_stress_notes(outcome),
                    )
                )
        return results

    def run_parameter_sensitivity(
        self,
        request: ValidationRunRequest,
    ) -> list[ParameterSensitivityResult]:
        validate_sensitivity_grid_size(request.sensitivity_grid)
        profiles = {
            profile.name: profile
            for profile in build_cost_stress_profiles(
                base_fee_rate=request.base_config.assumptions.fee_rate,
                base_slippage_rate=request.base_config.assumptions.slippage_rate,
            )
        }
        results: list[ParameterSensitivityResult] = []

        for entry_threshold, atr_stop_buffer, risk_reward, profile_name in _grid_combinations(
            request.base_config,
            request.sensitivity_grid,
        ):
            profile = profiles[profile_name]
            sensitivity_request = _request_with_sensitivity_parameters(
                request.base_config,
                profile=profile,
                entry_threshold=entry_threshold,
                atr_stop_buffer=atr_stop_buffer,
                risk_reward_multiple=risk_reward,
            )
            response = self._run_backtest(sensitivity_request)
            parameter_set_id = _parameter_set_id(
                entry_threshold=entry_threshold,
                atr_stop_buffer=atr_stop_buffer,
                risk_reward_multiple=risk_reward,
                profile_name=profile_name,
            )
            for metric in _mode_metrics_from_response(response):
                results.append(
                    ParameterSensitivityResult(
                        parameter_set_id=parameter_set_id,
                        grid_entry_threshold=entry_threshold,
                        atr_stop_buffer=atr_stop_buffer,
                        breakout_risk_reward_multiple=risk_reward,
                        stress_profile_name=profile_name,
                        strategy_mode=metric.strategy_mode,
                        metrics=metric,
                    )
                )

        return apply_fragility_flags(results)

    def run_walk_forward(
        self,
        request: ValidationRunRequest,
        validation_run_id: str,
    ) -> list[WalkForwardResult]:
        features = _load_validation_features(request.base_config)
        splits = generate_walk_forward_splits(features, request.walk_forward)
        results: list[WalkForwardResult] = []

        for split in splits:
            if split.status == ValidationSplitStatus.INSUFFICIENT_DATA:
                results.append(
                    WalkForwardResult(
                        split_id=split.split_id,
                        start_timestamp=split.start_timestamp,
                        end_timestamp=split.end_timestamp,
                        row_count=split.row_count,
                        trade_count=0,
                        status=split.status,
                        mode_metrics=[],
                        notes=split.notes,
                    )
                )
                continue

            split_path = self._write_walk_forward_features(
                validation_run_id=validation_run_id,
                split=split,
            )
            split_request = request.base_config.model_copy(update={"feature_path": split_path})
            response = self._run_backtest(split_request)
            mode_metrics = _mode_metrics_from_response(response)
            trade_count = sum(metric.number_of_trades for metric in mode_metrics)
            results.append(
                WalkForwardResult(
                    split_id=split.split_id,
                    start_timestamp=split.start_timestamp,
                    end_timestamp=split.end_timestamp,
                    row_count=split.row_count,
                    trade_count=trade_count,
                    status=split.status,
                    mode_metrics=mode_metrics,
                    notes=[
                        "Chronological split evaluated independently; no training, paper trading, "
                        "shadow trading, or live trading occurred."
                    ],
                )
            )

        return results

    def _write_walk_forward_features(
        self,
        validation_run_id: str,
        split: WalkForwardFeatureSplit,
    ) -> Path:
        run_path = self.report_store.create_run_dir(validation_run_id)
        split_path = run_path / f"{split.split_id}_features.parquet"
        split.frame.write_parquet(split_path)
        return split_path

    def _run_backtest(self, request: BacktestRunRequest) -> BacktestRunResponse:
        return BacktestEngine(report_store=self.report_store).run(request)

    def list_runs(self) -> ValidationRunListResponse:
        return ValidationRunListResponse(runs=self.report_store.list_validation_run_summaries())

    def read_run(self, validation_run_id: str) -> ValidationRun:
        return self.report_store.read_validation_run(validation_run_id)

    def read_stress_results(self, validation_run_id: str) -> ValidationStressResponse:
        run = self.read_run(validation_run_id)
        return ValidationStressResponse(
            validation_run_id=validation_run_id,
            data=run.stress_results,
        )

    def read_sensitivity_results(self, validation_run_id: str) -> ValidationSensitivityResponse:
        run = self.read_run(validation_run_id)
        return ValidationSensitivityResponse(
            validation_run_id=validation_run_id,
            data=run.sensitivity_results,
        )

    def read_walk_forward_results(self, validation_run_id: str) -> ValidationWalkForwardResponse:
        run = self.read_run(validation_run_id)
        return ValidationWalkForwardResponse(
            validation_run_id=validation_run_id,
            data=run.walk_forward_results,
        )

    def read_concentration_results(self, validation_run_id: str) -> ValidationConcentrationResponse:
        run = self.read_run(validation_run_id)
        return ValidationConcentrationResponse(
            validation_run_id=validation_run_id,
            regime_coverage=run.regime_coverage,
            concentration_report=run.concentration_report,
        )


def build_cost_stress_profiles(
    base_fee_rate: float,
    base_slippage_rate: float,
    selected_names: list[CostStressProfileName] | None = None,
) -> list[CostStressProfile]:
    high_fee_rate = min(max(base_fee_rate * 2, HIGH_FEE_RATE), 0.1)
    high_slippage_rate = min(max(base_slippage_rate * 3, HIGH_SLIPPAGE_RATE), 0.1)
    profiles = {
        CostStressProfileName.NORMAL: CostStressProfile(
            name=CostStressProfileName.NORMAL,
            fee_rate=base_fee_rate,
            slippage_rate=base_slippage_rate,
            description="Base fee and slippage assumptions from the validation configuration.",
        ),
        CostStressProfileName.HIGH_FEE: CostStressProfile(
            name=CostStressProfileName.HIGH_FEE,
            fee_rate=high_fee_rate,
            slippage_rate=base_slippage_rate,
            description="Higher fee assumption with base slippage unchanged.",
        ),
        CostStressProfileName.HIGH_SLIPPAGE: CostStressProfile(
            name=CostStressProfileName.HIGH_SLIPPAGE,
            fee_rate=base_fee_rate,
            slippage_rate=high_slippage_rate,
            description="Higher slippage assumption with base fee unchanged.",
        ),
        CostStressProfileName.WORST_REASONABLE_COST: CostStressProfile(
            name=CostStressProfileName.WORST_REASONABLE_COST,
            fee_rate=high_fee_rate,
            slippage_rate=high_slippage_rate,
            description=(
                "Combined higher fee and higher slippage assumptions for local research stress."
            ),
        ),
    }
    names = selected_names or list(CostStressProfileName)
    unique_names = list(dict.fromkeys(names))
    return [profiles[name] for name in unique_names]


def validate_sensitivity_grid_size(
    grid: SensitivityGrid,
    max_size: int = MAX_SENSITIVITY_GRID_SIZE,
) -> int:
    size = _grid_axis_size(grid.grid_entry_threshold)
    size *= _grid_axis_size(grid.atr_stop_buffer)
    size *= _grid_axis_size(grid.breakout_risk_reward_multiple)
    size *= _grid_axis_size(grid.fee_slippage_profile)
    if size > max_size:
        raise ValueError(f"parameter grid exceeds local validation limit ({size} > {max_size})")
    return size


def apply_fragility_flags(
    results: list[ParameterSensitivityResult],
) -> list[ParameterSensitivityResult]:
    grouped: dict[StrategyMode, list[ParameterSensitivityResult]] = {}
    for result in results:
        grouped.setdefault(result.strategy_mode, []).append(result)

    flagged_results: list[ParameterSensitivityResult] = []
    for result in results:
        mode_results = grouped[result.strategy_mode]
        positive_results = [
            item
            for item in mode_results
            if item.metrics.total_return_pct is not None and item.metrics.total_return_pct > 0
        ]
        is_fragile = (
            len(mode_results) > 1 and len(positive_results) == 1 and result in positive_results
        )
        notes = list(result.notes)
        if is_fragile:
            notes.append(
                "Isolated positive historical result within the bounded parameter grid; "
                "treat as fragile research evidence."
            )
        flagged_results.append(
            result.model_copy(update={"fragility_flag": is_fragile, "notes": notes})
        )
    return flagged_results


def generate_walk_forward_splits(
    features: pl.DataFrame,
    config: WalkForwardConfig,
) -> list[WalkForwardFeatureSplit]:
    if features.is_empty():
        return []
    if "timestamp" not in features.columns:
        raise ValueError("walk-forward validation requires a timestamp column")

    sorted_features = features.sort("timestamp")
    split_sizes = _walk_forward_split_sizes(sorted_features.height, config.split_count)
    splits: list[WalkForwardFeatureSplit] = []
    offset = 0

    for index, split_size in enumerate(split_sizes, start=1):
        frame = sorted_features.slice(offset, split_size)
        offset += split_size
        if frame.is_empty():
            continue

        row_count = frame.height
        status = (
            ValidationSplitStatus.EVALUATED
            if row_count >= config.minimum_rows_per_split
            else ValidationSplitStatus.INSUFFICIENT_DATA
        )
        notes = []
        if status == ValidationSplitStatus.INSUFFICIENT_DATA:
            notes.append(
                f"Split has {row_count} rows, fewer than the configured minimum "
                f"of {config.minimum_rows_per_split}; no backtest was run for this window."
            )

        splits.append(
            WalkForwardFeatureSplit(
                split_id=f"split_{index:03d}",
                frame=frame,
                start_timestamp=frame["timestamp"][0],
                end_timestamp=frame["timestamp"][-1],
                row_count=row_count,
                status=status,
                notes=notes,
            )
        )

    return splits


EXPECTED_REGIMES = ("RANGE", "BREAKOUT_UP", "BREAKOUT_DOWN", "AVOID")


def calculate_regime_coverage(
    features: pl.DataFrame,
    trades: list[TradeRecord],
) -> RegimeCoverageReport:
    bar_counts = {regime: 0 for regime in EXPECTED_REGIMES}
    bar_counts["UNKNOWN"] = 0
    coverage_notes: list[str] = []

    if "regime" not in features.columns:
        bar_counts["UNKNOWN"] = features.height
        coverage_notes.append(
            "Feature data did not include regime labels; all bars were counted as UNKNOWN."
        )
    else:
        for value in features["regime"].to_list():
            regime = _normalize_regime(value)
            if regime in EXPECTED_REGIMES:
                bar_counts[regime] += 1
            else:
                bar_counts["UNKNOWN"] += 1
        if bar_counts["UNKNOWN"]:
            coverage_notes.append(
                "Feature data contained unknown regime labels; they were grouped as UNKNOWN."
            )

    trades_by_regime: dict[str, list[TradeRecord]] = {}
    for trade in trades:
        regime = _normalize_regime(trade.regime_at_signal)
        if regime not in EXPECTED_REGIMES:
            regime = "UNKNOWN"
        trades_by_regime.setdefault(regime, []).append(trade)

    return RegimeCoverageReport(
        bar_counts=bar_counts,
        trades_per_regime={
            regime: len(trades_by_regime.get(regime, []))
            for regime in (*EXPECTED_REGIMES, "UNKNOWN")
        },
        return_by_regime={
            regime: _trade_group_summary(trades_by_regime.get(regime, []))
            for regime in (*EXPECTED_REGIMES, "UNKNOWN")
            if trades_by_regime.get(regime)
        },
        coverage_notes=coverage_notes,
    )


def _normalize_regime(value) -> str:
    if value is None:
        return "UNKNOWN"
    normalized = str(value).strip().upper()
    return normalized or "UNKNOWN"


def _trade_group_summary(trades: list[TradeRecord]) -> dict[str, float | int | None]:
    net_pnl = sum(trade.net_pnl for trade in trades)
    notional = sum(trade.notional for trade in trades)
    wins = [trade for trade in trades if trade.net_pnl > 0]
    return {
        "number_of_trades": len(trades),
        "net_pnl": net_pnl,
        "return_pct": net_pnl / notional if notional else 0.0,
        "return_pct_display": (net_pnl / notional * 100) if notional else 0.0,
        "win_rate": len(wins) / len(trades) if trades else None,
    }


def _walk_forward_split_sizes(row_count: int, split_count: int) -> list[int]:
    base_size = row_count // split_count
    remainder = row_count % split_count
    return [base_size + (1 if index < remainder else 0) for index in range(split_count)]


def _load_validation_features(request: BacktestRunRequest) -> pl.DataFrame:
    if request.feature_path is None:
        return BacktestEngine()._load_features(request)[0]
    feature_path = Path(request.feature_path)
    if not feature_path.exists():
        raise BacktestFeatureNotFoundError(request.symbol, request.timeframe, feature_path)
    return pl.read_parquet(feature_path)


def _request_with_cost_profile(
    request: BacktestRunRequest,
    profile: CostStressProfile,
) -> BacktestRunRequest:
    assumptions = request.assumptions.model_copy(
        update={"fee_rate": profile.fee_rate, "slippage_rate": profile.slippage_rate}
    )
    return request.model_copy(update={"assumptions": assumptions})


def _request_with_sensitivity_parameters(
    request: BacktestRunRequest,
    profile: CostStressProfile,
    entry_threshold: float,
    atr_stop_buffer: float,
    risk_reward_multiple: float,
) -> BacktestRunRequest:
    strategies = [
        _strategy_with_sensitivity_parameters(
            strategy,
            entry_threshold=entry_threshold,
            atr_stop_buffer=atr_stop_buffer,
            risk_reward_multiple=risk_reward_multiple,
        )
        for strategy in request.strategies
    ]
    return _request_with_cost_profile(request, profile).model_copy(
        update={"strategies": strategies}
    )


def _strategy_with_sensitivity_parameters(
    strategy: StrategyConfig,
    entry_threshold: float,
    atr_stop_buffer: float,
    risk_reward_multiple: float,
) -> StrategyConfig:
    updates: dict[str, float] = {}
    if strategy.mode == StrategyMode.GRID_RANGE:
        updates["entry_threshold"] = entry_threshold
        updates["atr_buffer"] = atr_stop_buffer
    if strategy.mode == StrategyMode.BREAKOUT:
        updates["atr_buffer"] = atr_stop_buffer
        updates["risk_reward_multiple"] = risk_reward_multiple
    return strategy.model_copy(update=updates) if updates else strategy


def _mode_metrics_from_response(response: BacktestRunResponse) -> list[ModeMetrics]:
    if response.metrics is None:
        return []
    rows = []
    for strategy_mode, summary in response.metrics.return_by_strategy_mode.items():
        mode = StrategyMode(strategy_mode)
        rows.append(
            ModeMetrics(
                strategy_mode=mode,
                category=str(summary.get("category") or _mode_category(mode)),
                total_return_pct=summary.get("total_return_pct"),
                max_drawdown_pct=summary.get("max_drawdown_pct"),
                number_of_trades=int(summary.get("number_of_trades") or 0),
                profit_factor=summary.get("profit_factor"),
                win_rate=summary.get("win_rate"),
                expectancy=summary.get("expectancy"),
                equity_basis=str(summary.get("equity_basis") or "realized_only"),
                notes=[],
            )
        )
    return rows


def _stress_outcome(metric: ModeMetrics, normal_return_pct: float | None) -> StressOutcome:
    if metric.number_of_trades == 0:
        return StressOutcome.NO_TRADES
    if metric.total_return_pct is None:
        return StressOutcome.NOT_EVALUABLE
    if normal_return_pct is not None and normal_return_pct > 0 and metric.total_return_pct <= 0:
        return StressOutcome.TURNED_NEGATIVE
    if metric.total_return_pct > 0:
        return StressOutcome.REMAINED_POSITIVE
    return StressOutcome.TURNED_NEGATIVE


def _stress_notes(outcome: StressOutcome) -> list[str]:
    if outcome == StressOutcome.REMAINED_POSITIVE:
        return ["Positive historical return under this cost assumption; not a profitability claim."]
    if outcome == StressOutcome.TURNED_NEGATIVE:
        return ["Non-positive historical return under this cost assumption."]
    if outcome == StressOutcome.NO_TRADES:
        return ["No completed trades under this cost assumption."]
    return ["Cost stress row could not be evaluated from available metrics."]


def _grid_combinations(
    request: BacktestRunRequest,
    grid: SensitivityGrid,
):
    return product(
        _numeric_values(grid.grid_entry_threshold, _default_grid_entry_threshold(request)),
        _numeric_values(grid.atr_stop_buffer, _default_atr_stop_buffer(request)),
        _numeric_values(
            grid.breakout_risk_reward_multiple,
            _default_breakout_risk_reward_multiple(request),
        ),
        grid.fee_slippage_profile or [CostStressProfileName.NORMAL],
    )


def _numeric_values(values: list[float], default: float) -> list[float]:
    return values or [default]


def _grid_axis_size(values: list | tuple) -> int:
    return max(1, len(values))


def _default_grid_entry_threshold(request: BacktestRunRequest) -> float:
    for strategy in request.strategies:
        if strategy.mode == StrategyMode.GRID_RANGE and strategy.entry_threshold is not None:
            return strategy.entry_threshold
    return 0.5


def _default_atr_stop_buffer(request: BacktestRunRequest) -> float:
    for strategy in request.strategies:
        if strategy.atr_buffer is not None:
            return strategy.atr_buffer
    return 1.0


def _default_breakout_risk_reward_multiple(request: BacktestRunRequest) -> float:
    for strategy in request.strategies:
        if strategy.mode == StrategyMode.BREAKOUT and strategy.risk_reward_multiple is not None:
            return strategy.risk_reward_multiple
    return 1.5


def _parameter_set_id(
    entry_threshold: float,
    atr_stop_buffer: float,
    risk_reward_multiple: float,
    profile_name: CostStressProfileName,
) -> str:
    return (
        f"entry_{_parameter_value(entry_threshold)}__atr_{_parameter_value(atr_stop_buffer)}__"
        f"rr_{_parameter_value(risk_reward_multiple)}__cost_{profile_name.value}"
    )


def _parameter_value(value: float) -> str:
    return str(value)


def _mode_category(mode: StrategyMode) -> str:
    if mode in {StrategyMode.BUY_HOLD, StrategyMode.PRICE_BREAKOUT, StrategyMode.NO_TRADE}:
        return "baseline"
    return "strategy"


def _validation_run_id(request: ValidationRunRequest) -> str:
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    return f"val_{timestamp}_{request.base_config.symbol.lower()}_{request.base_config.timeframe}"
