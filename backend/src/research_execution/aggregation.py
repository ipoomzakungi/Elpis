"""Evidence aggregation skeletons for research execution runs."""

from typing import Any

from src.models.research_execution import (
    ResearchEvidenceDecision,
    ResearchEvidenceDecisionResult,
    ResearchExecutionPreflightResult,
    ResearchExecutionWorkflowResult,
    ResearchExecutionWorkflowStatus,
)
from src.models.xau import XauVolatilitySource, XauVolOiReport


def classify_preflight_decision(
    preflight_results: list[ResearchExecutionPreflightResult],
) -> ResearchEvidenceDecisionResult:
    """Classify preflight-only evidence until full aggregation is implemented."""

    return classify_workflow_evidence(preflight_results, report_ids=[])


def classify_workflow_evidence(
    preflight_results: list[ResearchExecutionPreflightResult],
    *,
    report_ids: list[str] | None = None,
    warnings: list[str] | None = None,
    limitations: list[str] | None = None,
    missing_data_actions: list[str] | None = None,
) -> ResearchEvidenceDecisionResult:
    """Classify one workflow using bounded research-only evidence labels."""

    if not preflight_results:
        return ResearchEvidenceDecisionResult(
            decision=ResearchEvidenceDecision.INCONCLUSIVE,
            reason="No workflow preflight results or report evidence are available.",
        )

    statuses = [result.status for result in preflight_results]
    if any(status == ResearchExecutionWorkflowStatus.FAILED for status in statuses):
        return ResearchEvidenceDecisionResult(
            decision=ResearchEvidenceDecision.REJECT,
            reason="At least one workflow evidence rule failed during preflight.",
        )

    if all(status == ResearchExecutionWorkflowStatus.BLOCKED for status in statuses):
        return ResearchEvidenceDecisionResult(
            decision=ResearchEvidenceDecision.DATA_BLOCKED,
            reason="All requested workflow inputs are blocked by missing data.",
        )

    if any(status == ResearchExecutionWorkflowStatus.BLOCKED for status in statuses):
        return ResearchEvidenceDecisionResult(
            decision=ResearchEvidenceDecision.REFINE,
            reason="Some workflow inputs are usable, but at least one input remains blocked.",
        )

    unsupported = _deduplicate(
        capability
        for result in preflight_results
        for capability in result.unsupported_capabilities
    )
    combined_missing = _deduplicate(
        [
            *[action for result in preflight_results for action in result.missing_data_actions],
            *(missing_data_actions or []),
        ]
    )
    combined_limitations = _deduplicate(
        [
            *[limitation for result in preflight_results for limitation in result.limitations],
            *(limitations or []),
        ]
    )
    combined_warnings = _deduplicate(
        [
            *[warning for result in preflight_results for warning in result.warnings],
            *(warnings or []),
        ]
    )
    significant_warnings = [
        warning for warning in combined_warnings if not _is_research_only_warning(warning)
    ]

    if unsupported or combined_missing or combined_limitations or significant_warnings:
        return ResearchEvidenceDecisionResult(
            decision=ResearchEvidenceDecision.REFINE,
            reason=(
                "Workflow evidence is usable, but unsupported capabilities, missing-data "
                "actions, warnings, or limitations remain."
            ),
            warnings=significant_warnings,
        )

    if not report_ids:
        return ResearchEvidenceDecisionResult(
            decision=ResearchEvidenceDecision.INCONCLUSIVE,
            reason=(
                "Preflight passed, but linked report evidence is not available yet."
            ),
        )

    return ResearchEvidenceDecisionResult(
        decision=ResearchEvidenceDecision.CONTINUE,
        reason="Workflow evidence sections are present and acceptable under research assumptions.",
    )


def classify_final_evidence(
    workflow_results: list[ResearchExecutionWorkflowResult],
) -> ResearchEvidenceDecisionResult:
    """Classify the final execution evidence across workflow results."""

    if not workflow_results:
        return ResearchEvidenceDecisionResult(
            decision=ResearchEvidenceDecision.INCONCLUSIVE,
            reason="No workflow results are available for final evidence classification.",
        )

    decisions = [result.decision for result in workflow_results]
    if any(decision == ResearchEvidenceDecision.REJECT for decision in decisions):
        return ResearchEvidenceDecisionResult(
            decision=ResearchEvidenceDecision.REJECT,
            reason="At least one workflow produced a failed evidence rule.",
        )

    if all(decision == ResearchEvidenceDecision.DATA_BLOCKED for decision in decisions):
        return ResearchEvidenceDecisionResult(
            decision=ResearchEvidenceDecision.DATA_BLOCKED,
            reason="All requested workflows are blocked by missing required inputs.",
        )

    if any(
        decision in {ResearchEvidenceDecision.DATA_BLOCKED, ResearchEvidenceDecision.REFINE}
        for decision in decisions
    ):
        return ResearchEvidenceDecisionResult(
            decision=ResearchEvidenceDecision.REFINE,
            reason=(
                "Some evidence is usable, but missing data, unsupported capabilities, "
                "warnings, or limitations remain."
            ),
        )

    if all(decision == ResearchEvidenceDecision.CONTINUE for decision in decisions):
        return ResearchEvidenceDecisionResult(
            decision=ResearchEvidenceDecision.CONTINUE,
            reason="All workflow evidence sections are acceptable under research assumptions.",
        )

    return ResearchEvidenceDecisionResult(
        decision=ResearchEvidenceDecision.INCONCLUSIVE,
        reason="Workflow evidence is incomplete or insufficient for a stronger decision label.",
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


def _is_research_only_warning(value: str) -> bool:
    lowered = value.lower()
    return (
        "research-only" in lowered
        or "research decisions only" in lowered
        or "does not imply profitability" in lowered
        or "do not claim profitability" in lowered
        or "not trading approvals" in lowered
    )
