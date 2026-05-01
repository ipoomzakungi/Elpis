"""Evidence aggregation skeletons for research execution runs."""

from src.models.research_execution import (
    ResearchEvidenceDecision,
    ResearchEvidenceDecisionResult,
    ResearchExecutionPreflightResult,
    ResearchExecutionWorkflowStatus,
)


def classify_preflight_decision(
    preflight_results: list[ResearchExecutionPreflightResult],
) -> ResearchEvidenceDecisionResult:
    """Classify preflight-only evidence until full aggregation is implemented."""

    if not preflight_results:
        return ResearchEvidenceDecisionResult(
            decision=ResearchEvidenceDecision.INCONCLUSIVE,
            reason="No workflow preflight results are available yet.",
        )

    statuses = [result.status for result in preflight_results]
    if all(status == ResearchExecutionWorkflowStatus.BLOCKED for status in statuses):
        return ResearchEvidenceDecisionResult(
            decision=ResearchEvidenceDecision.DATA_BLOCKED,
            reason="All requested workflow inputs are blocked by missing data.",
        )

    if any(status == ResearchExecutionWorkflowStatus.BLOCKED for status in statuses):
        return ResearchEvidenceDecisionResult(
            decision=ResearchEvidenceDecision.REFINE,
            reason="Some workflow inputs are ready, but at least one input remains blocked.",
        )

    if any(status == ResearchExecutionWorkflowStatus.FAILED for status in statuses):
        return ResearchEvidenceDecisionResult(
            decision=ResearchEvidenceDecision.INCONCLUSIVE,
            reason="At least one workflow preflight failed before evidence aggregation.",
        )

    return ResearchEvidenceDecisionResult(
        decision=ResearchEvidenceDecision.INCONCLUSIVE,
        reason=(
            "Preflight passed, but strategy and validation evidence has not been aggregated yet."
        ),
    )


def summarize_preflight_assets(
    preflight_results: list[ResearchExecutionPreflightResult],
) -> dict:
    """Aggregate asset-level preflight rows into a workflow evidence section."""

    ready_assets = [result.asset for result in preflight_results if result.ready and result.asset]
    blocked_assets = [
        result.asset
        for result in preflight_results
        if result.status == ResearchExecutionWorkflowStatus.BLOCKED and result.asset
    ]
    return {
        "asset_count": len(preflight_results),
        "completed_asset_count": len(ready_assets),
        "blocked_asset_count": len(blocked_assets),
        "ready_assets": ready_assets,
        "blocked_assets": blocked_assets,
        "row_counts": {
            result.asset: result.row_count
            for result in preflight_results
            if result.asset is not None and result.row_count is not None
        },
        "date_ranges": {
            result.asset: {
                "date_start": result.date_start.isoformat()
                if result.date_start is not None
                else None,
                "date_end": result.date_end.isoformat() if result.date_end is not None else None,
            }
            for result in preflight_results
            if result.asset is not None and result.date_start is not None
        },
    }


def summarize_proxy_preflight(
    preflight_results: list[ResearchExecutionPreflightResult],
    provider: str,
) -> dict:
    """Aggregate Yahoo/proxy OHLCV preflight rows with source limitations."""

    summary = summarize_preflight_assets(preflight_results)
    summary.update(
        {
            "provider": provider,
            "unsupported_capabilities_by_asset": {
                result.asset: result.unsupported_capabilities
                for result in preflight_results
                if result.asset is not None and result.unsupported_capabilities
            },
            "capability_snapshots_by_asset": {
                result.asset: result.capability_snapshot
                for result in preflight_results
                if result.asset is not None
            },
            "limitations_by_asset": {
                result.asset: result.limitations
                for result in preflight_results
                if result.asset is not None and result.limitations
            },
        }
    )
    return summary
