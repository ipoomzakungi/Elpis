"""Aggregation contracts for grouped multi-asset research reports."""

from src.models.backtest import MetricsSummary
from src.models.research import (
    ConcentrationAssetRow,
    RegimeCoverageAssetRow,
    ResearchAssetClassification,
    ResearchAssetResult,
    StrategyComparisonRow,
    StressSurvivalRow,
    WalkForwardStabilityRow,
)


def classify_asset_result(asset_result: ResearchAssetResult) -> ResearchAssetClassification:
    """Return the existing classification until detailed evidence rules are added."""
    return asset_result.classification


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
