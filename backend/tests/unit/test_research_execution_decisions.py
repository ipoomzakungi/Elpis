from src.models.research_execution import (
    ResearchEvidenceDecision,
    ResearchExecutionPreflightResult,
    ResearchExecutionWorkflowStatus,
    ResearchExecutionWorkflowType,
)
from src.research_execution.aggregation import classify_preflight_decision


def test_decision_skeleton_marks_all_blocked_as_data_blocked():
    decision = classify_preflight_decision(
        [
            ResearchExecutionPreflightResult(
                workflow_type=ResearchExecutionWorkflowType.CRYPTO_MULTI_ASSET,
                status=ResearchExecutionWorkflowStatus.BLOCKED,
                asset="ETHUSDT",
                ready=False,
                missing_data_actions=["Process ETHUSDT features first."],
            )
        ]
    )

    assert decision.decision == ResearchEvidenceDecision.DATA_BLOCKED
    assert "missing data" in decision.reason.lower()


def test_decision_skeleton_marks_ready_without_evidence_as_inconclusive():
    decision = classify_preflight_decision(
        [
            ResearchExecutionPreflightResult(
                workflow_type=ResearchExecutionWorkflowType.CRYPTO_MULTI_ASSET,
                status=ResearchExecutionWorkflowStatus.COMPLETED,
                asset="BTCUSDT",
                ready=True,
                row_count=100,
            )
        ]
    )

    assert decision.decision == ResearchEvidenceDecision.INCONCLUSIVE
    assert "preflight passed" in decision.reason.lower()


def test_decision_skeleton_marks_mixed_ready_and_blocked_as_refine():
    decision = classify_preflight_decision(
        [
            ResearchExecutionPreflightResult(
                workflow_type=ResearchExecutionWorkflowType.CRYPTO_MULTI_ASSET,
                status=ResearchExecutionWorkflowStatus.COMPLETED,
                asset="BTCUSDT",
                ready=True,
                row_count=100,
            ),
            ResearchExecutionPreflightResult(
                workflow_type=ResearchExecutionWorkflowType.CRYPTO_MULTI_ASSET,
                status=ResearchExecutionWorkflowStatus.BLOCKED,
                asset="SOLUSDT",
                ready=False,
                missing_data_actions=["Process SOLUSDT features first."],
            ),
        ]
    )

    assert decision.decision == ResearchEvidenceDecision.REFINE
    assert "blocked" in decision.reason.lower()
