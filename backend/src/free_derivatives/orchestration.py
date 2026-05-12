from datetime import UTC, datetime

from src.free_derivatives.processing import (
    FREE_DERIVATIVES_NO_REPLACEMENT_LIMITATION,
    FREE_DERIVATIVES_RESEARCH_ONLY_WARNING,
    foundational_limitations,
    source_limitations,
)
from src.models.free_derivatives import (
    FreeDerivativesBootstrapRequest,
    FreeDerivativesBootstrapRun,
    FreeDerivativesRunStatus,
    FreeDerivativesSource,
    FreeDerivativesSourceResult,
    FreeDerivativesSourceStatus,
    create_free_derivatives_run_id,
)


def assemble_placeholder_bootstrap_run(
    request: FreeDerivativesBootstrapRequest,
) -> FreeDerivativesBootstrapRun:
    """Build a structured placeholder run without collecting external data."""

    created_at = datetime.now(UTC)
    enabled_sources = _enabled_sources(request)
    source_results = [
        FreeDerivativesSourceResult(
            source=source,
            status=FreeDerivativesSourceStatus.SKIPPED,
            requested_items=["foundation_placeholder"],
            skipped_items=["source-specific implementation is deferred"],
            warnings=[
                (
                    "Placeholder only: source collection and parsing are not implemented "
                    "in this foundation slice."
                )
            ],
            limitations=source_limitations(source),
            missing_data_actions=[
                (
                    "Continue with the source-specific implementation tasks before "
                    "running real or fixture collection."
                )
            ],
        )
        for source in enabled_sources
    ]

    return FreeDerivativesBootstrapRun(
        run_id=create_free_derivatives_run_id(request.run_label, created_at=created_at),
        status=FreeDerivativesRunStatus.BLOCKED,
        created_at=created_at,
        completed_at=created_at,
        request=request,
        source_results=source_results,
        artifacts=[],
        warnings=[FREE_DERIVATIVES_RESEARCH_ONLY_WARNING],
        limitations=foundational_limitations(),
        missing_data_actions=[
            (
                "CFTC, GVZ, and Deribit source-specific parsers are not implemented "
                "in this foundation slice."
            ),
            FREE_DERIVATIVES_NO_REPLACEMENT_LIMITATION,
        ],
        research_only_warnings=[
            (
                "No live trading, paper trading, broker integration, wallet handling, "
                "paid vendors, or execution behavior is included."
            )
        ],
    )


def _enabled_sources(request: FreeDerivativesBootstrapRequest) -> list[FreeDerivativesSource]:
    sources: list[FreeDerivativesSource] = []
    if request.include_cftc:
        sources.append(FreeDerivativesSource.CFTC_COT)
    if request.include_gvz:
        sources.append(FreeDerivativesSource.GVZ)
    if request.include_deribit:
        sources.append(FreeDerivativesSource.DERIBIT_PUBLIC_OPTIONS)
    return sources

