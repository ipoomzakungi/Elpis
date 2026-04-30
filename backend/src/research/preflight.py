"""Processed-feature and capability preflight for multi-asset research."""

from src.models.research import ResearchAssetConfig, ResearchPreflightResult


class ResearchPreflightNotImplementedError(NotImplementedError):
    """Raised until story implementation adds concrete preflight behavior."""


def preflight_research_asset(asset: ResearchAssetConfig) -> ResearchPreflightResult:
    """Preflight one research asset.

    Concrete path resolution, provider capability inspection, and feature-column
    checks are implemented in the user-story phases.
    """
    raise ResearchPreflightNotImplementedError(
        f"Research preflight is not implemented yet for {asset.symbol}"
    )


def preflight_research_assets(
    assets: list[ResearchAssetConfig],
) -> list[ResearchPreflightResult]:
    return [preflight_research_asset(asset) for asset in assets if asset.enabled]

