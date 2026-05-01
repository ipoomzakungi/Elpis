"""Aggregation contracts for grouped multi-asset research reports."""

from dataclasses import dataclass

from src.models.backtest import (
    DrawdownRecoveryStatus,
    MetricsSummary,
    StressOutcome,
    ValidationRun,
    ValidationSplitStatus,
)
from src.models.research import (
    ConcentrationAssetRow,
    ConcentrationWarningLevel,
    RegimeCoverageAssetRow,
    ResearchAssetClassification,
    ResearchAssetResult,
    ResearchAssetRunStatus,
    ResearchPreflightStatus,
    StrategyComparisonRow,
    StressSurvivalRow,
    WalkForwardStabilityRow,
)


@dataclass(frozen=True)
class ResearchValidationSummaries:
    stress: list[StressSurvivalRow]
    walk_forward: list[WalkForwardStabilityRow]
    regime_coverage: list[RegimeCoverageAssetRow]
    concentration: list[ConcentrationAssetRow]
    sensitivity_fragile: bool
    notes: list[str]


def classify_asset_result(asset_result: ResearchAssetResult) -> ResearchAssetClassification:
    """Classify an asset from persisted evidence fields."""
    return classify_asset_evidence(asset_result)


def classify_asset_evidence(
    asset_result: ResearchAssetResult,
    *,
    sensitivity_fragile: bool = False,
) -> ResearchAssetClassification:
    """Classify one asset using research-only robustness evidence."""
    if asset_result.status == ResearchAssetRunStatus.BLOCKED:
        if asset_result.preflight.status == ResearchPreflightStatus.MISSING_DATA:
            return ResearchAssetClassification.MISSING_DATA
        return ResearchAssetClassification.INCONCLUSIVE

    if _has_no_trade_evidence(asset_result):
        return ResearchAssetClassification.NOT_WORTH_CONTINUING

    if sensitivity_fragile or _has_fragile_evidence(asset_result):
        return ResearchAssetClassification.FRAGILE

    if _has_complete_clean_validation_evidence(asset_result):
        return ResearchAssetClassification.ROBUST

    return ResearchAssetClassification.INCONCLUSIVE


def collect_strategy_comparison(
    asset_results: list[ResearchAssetResult],
) -> list[StrategyComparisonRow]:
    return [row for result in asset_results for row in result.strategy_comparison]


def comparison_rows_from_backtest_metrics(
    *,
    symbol: str,
    provider: str,
    metrics: MetricsSummary | None,
) -> list[StrategyComparisonRow]:
    """Convert single-asset backtest metrics into grouped research comparison rows."""
    if metrics is None:
        return []

    rows: list[StrategyComparisonRow] = []
    for row in metrics.baseline_comparison:
        mode = row.get("strategy_mode") or row.get("mode")
        if not mode:
            continue
        rows.append(
            StrategyComparisonRow(
                symbol=symbol,
                provider=provider,
                mode=str(mode),
                category=str(row.get("category") or "strategy"),
                total_return_pct=row.get("total_return_pct"),
                max_drawdown_pct=row.get("max_drawdown_pct"),
                number_of_trades=int(row.get("number_of_trades") or 0),
                profit_factor=row.get("profit_factor"),
                win_rate=row.get("win_rate"),
                notes=[
                    "Independent strategy/baseline comparison; not a portfolio result.",
                ],
            )
        )
    return rows


def validation_summaries_from_run(
    symbol: str,
    validation_run: ValidationRun,
) -> ResearchValidationSummaries:
    """Build grouped research validation summary rows from a validation run."""
    stress = [
        StressSurvivalRow(
            symbol=symbol,
            mode=result.strategy_mode.value,
            profile=result.profile.name.value,
            outcome=result.outcome.value,
            survived=_stress_survived(result.outcome),
            notes=list(result.notes),
        )
        for result in validation_run.stress_results
    ]
    sensitivity_fragile = any(
        result.fragility_flag for result in validation_run.sensitivity_results
    )
    notes = []
    if sensitivity_fragile:
        notes.append(
            "Parameter sensitivity flagged isolated strong settings; treat the asset as fragile "
            "research evidence."
        )

    walk_forward = [
        WalkForwardStabilityRow(
            symbol=symbol,
            split_id=result.split_id,
            status=result.status.value,
            row_count=result.row_count,
            trade_count=result.trade_count,
            stable=_walk_forward_stable(result),
            notes=list(result.notes),
        )
        for result in validation_run.walk_forward_results
    ]
    regime_coverage = [
        RegimeCoverageAssetRow(
            symbol=symbol,
            regime=regime,
            bar_count=bar_count,
            trade_count=validation_run.regime_coverage.trades_per_regime.get(regime, 0),
            return_pct=_regime_return_pct(validation_run, regime),
            notes=_regime_notes(validation_run, regime),
        )
        for regime, bar_count in validation_run.regime_coverage.bar_counts.items()
    ]
    concentration = [
        ConcentrationAssetRow(
            symbol=symbol,
            top_1_profit_contribution_pct=(
                validation_run.concentration_report.top_1_profit_contribution_pct
            ),
            top_5_profit_contribution_pct=(
                validation_run.concentration_report.top_5_profit_contribution_pct
            ),
            top_10_profit_contribution_pct=(
                validation_run.concentration_report.top_10_profit_contribution_pct
            ),
            max_consecutive_losses=validation_run.concentration_report.max_consecutive_losses,
            drawdown_recovery_status=(
                validation_run.concentration_report.drawdown_recovery_status.value
            ),
            warning_level=_concentration_warning_level(validation_run),
            notes=_concentration_notes(validation_run),
        )
    ]
    return ResearchValidationSummaries(
        stress=stress,
        walk_forward=walk_forward,
        regime_coverage=regime_coverage,
        concentration=concentration,
        sensitivity_fragile=sensitivity_fragile,
        notes=notes,
    )


def collect_stress_survival(asset_results: list[ResearchAssetResult]) -> list[StressSurvivalRow]:
    return [row for result in asset_results for row in result.stress_summary]


def collect_walk_forward_stability(
    asset_results: list[ResearchAssetResult],
) -> list[WalkForwardStabilityRow]:
    return [row for result in asset_results for row in result.walk_forward_summary]


def collect_regime_coverage(
    asset_results: list[ResearchAssetResult],
) -> list[RegimeCoverageAssetRow]:
    return [row for result in asset_results for row in result.regime_coverage_summary]


def collect_concentration(asset_results: list[ResearchAssetResult]) -> list[ConcentrationAssetRow]:
    return [row for result in asset_results for row in result.concentration_summary]


def _stress_survived(outcome: StressOutcome) -> bool | None:
    if outcome == StressOutcome.REMAINED_POSITIVE:
        return True
    if outcome == StressOutcome.TURNED_NEGATIVE:
        return False
    return None


def _walk_forward_stable(result) -> bool | None:
    if result.status == ValidationSplitStatus.INSUFFICIENT_DATA:
        return None
    if not result.mode_metrics:
        return False
    returns = [metric.total_return_pct for metric in result.mode_metrics]
    if any(value is None for value in returns):
        return None
    return all(value >= 0 for value in returns if value is not None)


def _regime_return_pct(validation_run: ValidationRun, regime: str) -> float | None:
    summary = validation_run.regime_coverage.return_by_regime.get(regime)
    if not summary:
        return None
    value = summary.get("return_pct_display")
    return float(value) if value is not None else None


def _regime_notes(validation_run: ValidationRun, regime: str) -> list[str]:
    if regime.upper() == "UNKNOWN":
        return list(validation_run.regime_coverage.coverage_notes)
    return []


def _concentration_warning_level(validation_run: ValidationRun) -> ConcentrationWarningLevel:
    report = validation_run.concentration_report
    top_1 = report.top_1_profit_contribution_pct or 0.0
    top_5 = report.top_5_profit_contribution_pct or 0.0
    if (
        top_1 >= 80
        or top_5 >= 90
        or report.max_consecutive_losses >= 4
        or report.drawdown_recovery_status == DrawdownRecoveryStatus.NOT_RECOVERED
    ):
        return ConcentrationWarningLevel.HIGH
    if top_1 >= 50 or top_5 >= 75 or report.max_consecutive_losses >= 2:
        return ConcentrationWarningLevel.WATCH
    return ConcentrationWarningLevel.NONE


def _concentration_notes(validation_run: ValidationRun) -> list[str]:
    notes = list(validation_run.concentration_report.notes)
    warning_level = _concentration_warning_level(validation_run)
    if warning_level == ConcentrationWarningLevel.HIGH:
        notes.append("High concentration warning from trade contribution or recovery evidence.")
    elif warning_level == ConcentrationWarningLevel.WATCH:
        notes.append("Watch concentration warning from trade contribution or loss-streak evidence.")
    else:
        notes.append("No concentration warning from current validation evidence.")
    return notes


def _has_no_trade_evidence(asset_result: ResearchAssetResult) -> bool:
    if not asset_result.strategy_comparison:
        return False
    return all(row.number_of_trades == 0 for row in asset_result.strategy_comparison)


def _has_fragile_evidence(asset_result: ResearchAssetResult) -> bool:
    if any(row.survived is False for row in asset_result.stress_summary):
        return True
    if any(row.stable is False for row in asset_result.walk_forward_summary):
        return True
    return any(
        row.warning_level in {ConcentrationWarningLevel.WATCH, ConcentrationWarningLevel.HIGH}
        for row in asset_result.concentration_summary
    )


def _has_complete_clean_validation_evidence(asset_result: ResearchAssetResult) -> bool:
    return (
        bool(asset_result.strategy_comparison)
        and bool(asset_result.stress_summary)
        and bool(asset_result.walk_forward_summary)
        and bool(asset_result.regime_coverage_summary)
        and bool(asset_result.concentration_summary)
        and all(row.survived is not False for row in asset_result.stress_summary)
        and all(row.stable is not False for row in asset_result.walk_forward_summary)
        and all(
            row.warning_level == ConcentrationWarningLevel.NONE
            for row in asset_result.concentration_summary
        )
    )
