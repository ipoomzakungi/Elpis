"""Aggregation contracts for grouped multi-asset research reports."""

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

