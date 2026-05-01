"""Coordinator for grouped multi-asset research reports."""

import hashlib
from datetime import datetime
from pathlib import Path

from src.backtest.engine import BacktestEngine
from src.backtest.validation import ValidationReportService
from src.models.backtest import (
    BacktestAssumptions,
    BacktestRunRequest,
    BacktestStatus,
    BaselineMode,
    ReportFormat,
    SensitivityGrid,
    StrategyConfig,
    StrategyMode,
    ValidationRunRequest,
    WalkForwardConfig,
)
from src.models.research import (
    ResearchAssetClassification,
    ResearchAssetConfig,
    ResearchAssetResult,
    ResearchAssetRunStatus,
    ResearchPreflightResult,
    ResearchPreflightStatus,
    ResearchRun,
    ResearchRunRequest,
)
from src.reports.writer import RESEARCH_ONLY_WARNING
from src.research.aggregation import (
    classify_asset_evidence,
    comparison_rows_from_backtest_metrics,
    validation_summaries_from_run,
)
from src.research.preflight import preflight_research_assets
from src.research.report_store import ResearchReportStore


class ResearchExecutionNotImplementedError(NotImplementedError):
    """Raised until story implementation adds concrete grouped execution."""


class ResearchOrchestrator:
    """Skeleton service for multi-asset research orchestration."""

    def __init__(
        self,
        report_store: ResearchReportStore | None = None,
        backtest_engine: BacktestEngine | None = None,
        validation_service: ValidationReportService | None = None,
    ):
        self.report_store = report_store or ResearchReportStore()
        self.backtest_engine = backtest_engine or BacktestEngine()
        self.validation_service = validation_service or ValidationReportService(
            report_store=self.report_store.report_store
        )

    def run(self, request: ResearchRunRequest) -> ResearchRun:
        created_at = datetime.utcnow()
        preflight_results = preflight_research_assets(request.assets)
        asset_configs = [asset for asset in request.assets if asset.enabled]
        assets = []
        for asset_config, preflight in zip(asset_configs, preflight_results, strict=True):
            if preflight.status == ResearchPreflightStatus.READY:
                backtest_request = _backtest_request(asset_config, preflight, request)
                backtest_response = self.backtest_engine.run(backtest_request)
                comparison_rows = comparison_rows_from_backtest_metrics(
                    symbol=asset_config.symbol,
                    provider=asset_config.provider,
                    metrics=backtest_response.metrics,
                )
                validation_run = self.validation_service.run(
                    _validation_request(backtest_request, request)
                )
                validation_summaries = validation_summaries_from_run(
                    asset_config.symbol,
                    validation_run,
                )
                assets.append(
                    _asset_result(
                        asset_config,
                        preflight,
                        comparison_rows,
                        validation_run_id=validation_run.validation_run_id,
                        validation_summaries=validation_summaries,
                    )
                )
                continue
            assets.append(_asset_result(asset_config, preflight))

        completed_count = sum(
            1 for asset in assets if asset.status == ResearchAssetRunStatus.COMPLETED
        )
        blocked_count = sum(1 for asset in assets if asset.status == ResearchAssetRunStatus.BLOCKED)
        warnings = [
            (
                "Grouped report is a research comparison only and does not imply "
                "profitability, predictive power, safety, or live readiness."
            )
        ]
        if blocked_count:
            warnings.append(
                "Some configured assets were blocked by missing or incomplete processed features."
            )
        status = _run_status(completed_count=completed_count, blocked_count=blocked_count)
        run = ResearchRun(
            research_run_id=_research_run_id(created_at),
            status=status,
            created_at=created_at,
            completed_at=datetime.utcnow(),
            request=request,
            assets=assets,
            completed_count=completed_count,
            blocked_count=blocked_count,
            warnings=warnings,
            limitations=[
                RESEARCH_ONLY_WARNING,
                "Feature 005 US1 uses existing processed feature files only; no synthetic "
                "fallback is used for missing real-data research inputs.",
                "Strategy comparison and validation aggregation are independent per-asset "
                "research evidence, not a portfolio result or live-readiness claim.",
            ],
        )
        return self.report_store.write_run_outputs(run)


def _asset_result(
    asset_config: ResearchAssetConfig,
    preflight: ResearchPreflightResult,
    strategy_comparison=None,
    validation_run_id: str | None = None,
    validation_summaries=None,
) -> ResearchAssetResult:
    if preflight.status == ResearchPreflightStatus.READY:
        comparison_rows = list(strategy_comparison or [])
        stress_summary = list(validation_summaries.stress) if validation_summaries else []
        walk_forward_summary = (
            list(validation_summaries.walk_forward) if validation_summaries else []
        )
        regime_coverage_summary = (
            list(validation_summaries.regime_coverage) if validation_summaries else []
        )
        concentration_summary = (
            list(validation_summaries.concentration) if validation_summaries else []
        )
        warnings = [*preflight.warnings]
        if validation_summaries:
            warnings.extend(validation_summaries.notes)
        result = ResearchAssetResult(
            symbol=asset_config.symbol,
            provider=asset_config.provider,
            asset_class=asset_config.asset_class,
            status=ResearchAssetRunStatus.COMPLETED,
            classification=ResearchAssetClassification.INCONCLUSIVE,
            preflight=preflight,
            validation_run_id=validation_run_id,
            data_identity=_data_identity(
                preflight,
                source_kind="explicit_feature_path"
                if asset_config.feature_path is not None
                else "processed_features",
            ),
            strategy_comparison=comparison_rows,
            stress_summary=stress_summary,
            walk_forward_summary=walk_forward_summary,
            regime_coverage_summary=regime_coverage_summary,
            concentration_summary=concentration_summary,
            warnings=warnings,
            limitations=[
                *preflight.capability_snapshot.limitation_notes,
                "Strategy and baseline rows are independent comparisons, not a combined "
                "portfolio result.",
                "Validation summaries are robustness diagnostics only and do not imply "
                "profitability, predictive power, safety, or live readiness.",
            ],
        )
        return result.model_copy(
            update={
                "classification": classify_asset_evidence(
                    result,
                    sensitivity_fragile=bool(
                        validation_summaries and validation_summaries.sensitivity_fragile
                    ),
                )
            }
        )

    classification = (
        ResearchAssetClassification.MISSING_DATA
        if preflight.status == ResearchPreflightStatus.MISSING_DATA
        else ResearchAssetClassification.INCONCLUSIVE
    )
    return ResearchAssetResult(
        symbol=asset_config.symbol,
        provider=asset_config.provider,
        asset_class=asset_config.asset_class,
        status=ResearchAssetRunStatus.BLOCKED,
        classification=classification,
        preflight=preflight,
        warnings=preflight.warnings,
        limitations=preflight.capability_snapshot.limitation_notes,
    )


def _backtest_request(
    asset_config: ResearchAssetConfig,
    preflight: ResearchPreflightResult,
    research_request: ResearchRunRequest,
) -> BacktestRunRequest:
    strategies: list[StrategyConfig] = []
    if research_request.strategy_set.include_grid_range:
        strategies.append(
            StrategyConfig(
                mode=StrategyMode.GRID_RANGE,
                enabled=True,
                allow_short=research_request.base_assumptions.allow_short,
            )
        )
    if research_request.strategy_set.include_breakout:
        strategies.append(
            StrategyConfig(
                mode=StrategyMode.BREAKOUT,
                enabled=True,
                allow_short=research_request.base_assumptions.allow_short,
            )
        )

    baselines = [BaselineMode(mode) for mode in research_request.strategy_set.baselines]
    return BacktestRunRequest(
        symbol=asset_config.symbol,
        provider=asset_config.provider,
        timeframe=asset_config.timeframe,
        feature_path=Path(preflight.feature_path),
        initial_equity=research_request.base_assumptions.initial_equity,
        assumptions=BacktestAssumptions(
            fee_rate=research_request.base_assumptions.fee_rate,
            slippage_rate=research_request.base_assumptions.slippage_rate,
            risk_per_trade=research_request.base_assumptions.risk_per_trade,
            allow_short=research_request.base_assumptions.allow_short,
            leverage=1,
            allow_compounding=False,
            max_positions=1,
        ),
        strategies=strategies,
        baselines=baselines,
        report_format=ReportFormat.JSON,
    )


def _validation_request(
    backtest_request: BacktestRunRequest,
    research_request: ResearchRunRequest,
) -> ValidationRunRequest:
    grid = research_request.validation_config.sensitivity_grid
    walk_forward = research_request.validation_config.walk_forward
    return ValidationRunRequest(
        base_config=backtest_request,
        stress_profiles=list(research_request.validation_config.stress_profiles),
        sensitivity_grid=SensitivityGrid(
            grid_entry_threshold=list(grid.grid_entry_threshold),
            atr_stop_buffer=list(grid.atr_stop_buffer),
            breakout_risk_reward_multiple=list(grid.breakout_risk_reward_multiple),
            fee_slippage_profile=list(grid.fee_slippage_profile),
        ),
        walk_forward=WalkForwardConfig(
            split_count=walk_forward.split_count,
            minimum_rows_per_split=walk_forward.minimum_rows_per_split,
        ),
        include_real_data_check=True,
    )


def _data_identity(preflight: ResearchPreflightResult, source_kind: str) -> dict:
    path = Path(preflight.feature_path)
    identity = {
        "source_kind": source_kind,
        "feature_path": preflight.feature_path,
        "exists": path.exists(),
        "row_count": preflight.row_count,
        "first_timestamp": preflight.first_timestamp.isoformat()
        if preflight.first_timestamp
        else None,
        "last_timestamp": preflight.last_timestamp.isoformat()
        if preflight.last_timestamp
        else None,
    }
    if path.exists():
        identity["content_hash"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return identity


def _run_status(completed_count: int, blocked_count: int) -> BacktestStatus:
    if completed_count and not blocked_count:
        return BacktestStatus.COMPLETED
    if completed_count:
        return BacktestStatus.PARTIAL
    return BacktestStatus.FAILED


def _research_run_id(created_at: datetime) -> str:
    return f"research_{created_at.strftime('%Y%m%d_%H%M%S_%f')}_multi_asset"
