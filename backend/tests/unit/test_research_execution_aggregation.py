from src.models.research_execution import (
    ResearchEvidenceDecision,
    ResearchExecutionPreflightResult,
    ResearchExecutionWorkflowResult,
    ResearchExecutionWorkflowStatus,
    ResearchExecutionWorkflowType,
)
from src.research_execution.aggregation import (
    classify_final_evidence,
    classify_workflow_evidence,
)


def test_workflow_decision_is_data_blocked_when_required_inputs_are_missing():
    result = classify_workflow_evidence(
        [
            _preflight_result(
                status=ResearchExecutionWorkflowStatus.BLOCKED,
                ready=False,
                missing_data_actions=["Download and process BTCUSDT features first."],
            )
        ],
        report_ids=[],
    )

    assert result.decision == ResearchEvidenceDecision.DATA_BLOCKED
    assert "missing data" in result.reason.lower()


def test_workflow_decision_is_inconclusive_without_enough_evidence():
    result = classify_workflow_evidence(
        [_preflight_result(status=ResearchExecutionWorkflowStatus.COMPLETED, ready=True)],
        report_ids=[],
    )

    assert result.decision == ResearchEvidenceDecision.INCONCLUSIVE
    assert "report evidence" in result.reason.lower()


def test_workflow_decision_is_refine_when_usable_evidence_has_limitations():
    result = classify_workflow_evidence(
        [
            _preflight_result(
                status=ResearchExecutionWorkflowStatus.COMPLETED,
                ready=True,
                unsupported_capabilities=["open_interest"],
                limitations=["Yahoo Finance is OHLCV-only for this proxy asset."],
            )
        ],
        report_ids=["research_proxy_existing"],
    )

    assert result.decision == ResearchEvidenceDecision.REFINE
    assert "limitations" in result.reason.lower()


def test_workflow_decision_can_continue_when_required_sections_are_acceptable():
    result = classify_workflow_evidence(
        [_preflight_result(status=ResearchExecutionWorkflowStatus.COMPLETED, ready=True)],
        report_ids=["research_ready_existing"],
        warnings=[
            "Evidence labels are research decisions only and do not imply profitability.",
        ],
    )

    assert result.decision == ResearchEvidenceDecision.CONTINUE
    assert "acceptable" in result.reason.lower()


def test_workflow_decision_rejects_failed_evidence_rule():
    result = classify_workflow_evidence(
        [_preflight_result(status=ResearchExecutionWorkflowStatus.FAILED, ready=False)],
        report_ids=["research_failed_existing"],
    )

    assert result.decision == ResearchEvidenceDecision.REJECT
    assert "failed" in result.reason.lower()


def test_final_evidence_decision_preserves_all_bounded_labels():
    assert classify_final_evidence([]).decision == ResearchEvidenceDecision.INCONCLUSIVE

    assert (
        classify_final_evidence(
            [_workflow_result(ResearchEvidenceDecision.DATA_BLOCKED)]
        ).decision
        == ResearchEvidenceDecision.DATA_BLOCKED
    )
    assert (
        classify_final_evidence(
            [
                _workflow_result(ResearchEvidenceDecision.CONTINUE),
                _workflow_result(ResearchEvidenceDecision.REFINE),
            ]
        ).decision
        == ResearchEvidenceDecision.REFINE
    )
    assert (
        classify_final_evidence(
            [_workflow_result(ResearchEvidenceDecision.REJECT)]
        ).decision
        == ResearchEvidenceDecision.REJECT
    )
    assert (
        classify_final_evidence(
            [_workflow_result(ResearchEvidenceDecision.CONTINUE)]
        ).decision
        == ResearchEvidenceDecision.CONTINUE
    )


def _preflight_result(
    *,
    status: ResearchExecutionWorkflowStatus,
    ready: bool,
    missing_data_actions: list[str] | None = None,
    unsupported_capabilities: list[str] | None = None,
    limitations: list[str] | None = None,
) -> ResearchExecutionPreflightResult:
    return ResearchExecutionPreflightResult(
        workflow_type=ResearchExecutionWorkflowType.CRYPTO_MULTI_ASSET,
        status=status,
        asset="BTCUSDT",
        ready=ready,
        missing_data_actions=missing_data_actions or [],
        unsupported_capabilities=unsupported_capabilities or [],
        limitations=limitations or [],
    )


def _workflow_result(decision: ResearchEvidenceDecision) -> ResearchExecutionWorkflowResult:
    status = (
        ResearchExecutionWorkflowStatus.BLOCKED
        if decision == ResearchEvidenceDecision.DATA_BLOCKED
        else ResearchExecutionWorkflowStatus.FAILED
        if decision == ResearchEvidenceDecision.REJECT
        else ResearchExecutionWorkflowStatus.COMPLETED
    )
    return ResearchExecutionWorkflowResult(
        workflow_type=ResearchExecutionWorkflowType.CRYPTO_MULTI_ASSET,
        status=status,
        decision=decision,
        decision_reason=f"{decision.value} fixture",
    )
