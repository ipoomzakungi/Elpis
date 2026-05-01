"""Evidence aggregation skeletons for research execution runs."""

from typing import Any

from src.models.research_execution import (
    ResearchEvidenceDecision,
    ResearchEvidenceDecisionResult,
    ResearchExecutionPreflightResult,
    ResearchExecutionWorkflowStatus,
)
from src.models.xau import XauVolatilitySource, XauVolOiReport


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


def summarize_xau_evidence(
    preflight_results: list[ResearchExecutionPreflightResult],
    xau_report: XauVolOiReport | None = None,
    *,
    missing_report_id: str | None = None,
) -> dict[str, Any]:
    """Aggregate XAU workflow readiness and report evidence into one summary."""

    status = _workflow_status(preflight_results)
    missing_actions = _deduplicate(
        action for result in preflight_results for action in result.missing_data_actions
    )
    warnings = _deduplicate(
        warning for result in preflight_results for warning in result.warnings
    )
    limitations = _deduplicate(
        limitation for result in preflight_results for limitation in result.limitations
    )
    report_ids = [xau_report.report_id] if xau_report is not None else []

    if xau_report is None:
        return {
            "status": status.value,
            "report_ids": report_ids,
            "linked_xau_report_id": None,
            "missing_report_id": missing_report_id,
            "source_validation_summary": None,
            "basis_snapshot_status": "unavailable",
            "basis_snapshot": None,
            "expected_range_status": "unavailable",
            "expected_range": None,
            "wall_count": 0,
            "zone_count": 0,
            "warnings": warnings,
            "limitations": limitations,
            "missing_data_actions": missing_actions,
        }

    source_validation = xau_report.source_validation
    basis_snapshot = (
        xau_report.basis_snapshot.model_dump(mode="json")
        if xau_report.basis_snapshot is not None
        else None
    )
    expected_range = (
        xau_report.expected_range.model_dump(mode="json")
        if xau_report.expected_range is not None
        else None
    )
    expected_range_available = (
        xau_report.expected_range is not None
        and xau_report.expected_range.source != XauVolatilitySource.UNAVAILABLE
    )
    return {
        "status": status.value,
        "report_ids": report_ids,
        "linked_xau_report_id": xau_report.report_id,
        "missing_report_id": missing_report_id,
        "source_validation_summary": {
            "is_valid": source_validation.is_valid,
            "source_row_count": source_validation.source_row_count,
            "accepted_row_count": source_validation.accepted_row_count,
            "rejected_row_count": source_validation.rejected_row_count,
            "required_columns_missing": source_validation.required_columns_missing,
            "optional_columns_present": source_validation.optional_columns_present,
            "errors": source_validation.errors,
            "instructions": source_validation.instructions,
        },
        "basis_snapshot_status": (
            "available"
            if xau_report.basis_snapshot is not None
            and xau_report.basis_snapshot.mapping_available
            else "unavailable"
        ),
        "basis_snapshot": basis_snapshot,
        "expected_range_status": "available" if expected_range_available else "unavailable",
        "expected_range": expected_range,
        "wall_count": xau_report.wall_count,
        "zone_count": xau_report.zone_count,
        "warnings": _deduplicate([*warnings, *xau_report.warnings]),
        "limitations": _deduplicate([*limitations, *xau_report.limitations]),
        "missing_data_actions": _deduplicate(
            [*missing_actions, *xau_report.missing_data_instructions]
        ),
    }


def _workflow_status(
    preflight_results: list[ResearchExecutionPreflightResult],
) -> ResearchExecutionWorkflowStatus:
    if not preflight_results:
        return ResearchExecutionWorkflowStatus.SKIPPED
    statuses = [result.status for result in preflight_results]
    if all(status == ResearchExecutionWorkflowStatus.COMPLETED for status in statuses):
        return ResearchExecutionWorkflowStatus.COMPLETED
    if all(status == ResearchExecutionWorkflowStatus.BLOCKED for status in statuses):
        return ResearchExecutionWorkflowStatus.BLOCKED
    if any(status == ResearchExecutionWorkflowStatus.FAILED for status in statuses):
        return ResearchExecutionWorkflowStatus.FAILED
    return ResearchExecutionWorkflowStatus.PARTIAL


def _deduplicate(values) -> list[str]:
    result = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
