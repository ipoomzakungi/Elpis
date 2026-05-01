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
