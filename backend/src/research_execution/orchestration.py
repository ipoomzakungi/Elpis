"""Research execution runbook orchestration."""

from datetime import datetime

from src.models.research_execution import (
    CryptoResearchWorkflowConfig,
    ResearchEvidenceSummary,
    ResearchExecutionPreflightResult,
    ResearchExecutionRun,
    ResearchExecutionRunRequest,
    ResearchExecutionWorkflowResult,
    ResearchExecutionWorkflowStatus,
    ResearchExecutionWorkflowType,
)
from src.reports.writer import RESEARCH_ONLY_WARNING
from src.research_execution.aggregation import classify_preflight_decision
from src.research_execution.preflight import preflight_crypto_processed_features
from src.research_execution.report_store import ResearchExecutionReportStore


class ResearchExecutionNotImplementedError(NotImplementedError):
    """Raised until story phases implement execution orchestration."""


class ResearchExecutionOrchestrator:
    """Coordinates existing research systems without adding strategy logic."""

    def __init__(self, report_store: ResearchExecutionReportStore | None = None):
        self.report_store = report_store or ResearchExecutionReportStore()

    def run(self, request: ResearchExecutionRunRequest) -> ResearchExecutionRun:
        """Run the currently implemented research execution workflow slice."""

        if request.crypto is None or not request.crypto.enabled:
            raise ResearchExecutionNotImplementedError(
                "Only crypto research execution is implemented in this phase"
            )

        created_at = datetime.utcnow()
        execution_run_id = _execution_run_id(created_at)
        normalized_request = ResearchExecutionRunRequest.model_validate(
            request.model_dump(mode="python")
        )
        preflight_results = preflight_crypto_processed_features(normalized_request.crypto)
        workflow_result = _crypto_workflow_result(normalized_request.crypto, preflight_results)
        evidence_summary = _evidence_summary(
            execution_run_id=execution_run_id,
            created_at=created_at,
            workflow_result=workflow_result,
            preflight_results=preflight_results,
        )
        run = ResearchExecutionRun(
            execution_run_id=execution_run_id,
            name=normalized_request.name,
            normalized_config=normalized_request,
            preflight_results=preflight_results,
            evidence_summary=evidence_summary,
            artifact_paths=self.report_store.artifact_paths(execution_run_id),
            created_at=created_at,
            updated_at=datetime.utcnow(),
        )
        return self.report_store.write_run_outputs(run)


def _crypto_workflow_result(
    config: CryptoResearchWorkflowConfig,
    preflight_results: list[ResearchExecutionPreflightResult],
) -> ResearchExecutionWorkflowResult:
    decision = classify_preflight_decision(preflight_results)
    status = _workflow_status(preflight_results)
    report_ids = []
    if config.existing_research_run_id:
        report_ids.append(config.existing_research_run_id)
    missing_actions = _flatten_unique(
        action for result in preflight_results for action in result.missing_data_actions
    )
    warnings = _flatten_unique(
        [
            *[warning for result in preflight_results for warning in result.warnings],
            (
                "Crypto workflow evidence is research-only and does not imply "
                "profitability, predictive power, safety, or live readiness."
            ),
        ]
    )
    limitations = _flatten_unique(
        [
            *[limitation for result in preflight_results for limitation in result.limitations],
            (
                "Feature 007 US1 records processed-feature readiness and blocked assets; "
                "it does not create strategy logic or execution behavior."
            ),
        ]
    )
    ready_assets = [result.asset for result in preflight_results if result.ready and result.asset]
    blocked_assets = [
        result.asset
        for result in preflight_results
        if result.status == ResearchExecutionWorkflowStatus.BLOCKED and result.asset
    ]
    reason = decision.reason
    if ready_assets and blocked_assets:
        reason = (
            f"Crypto workflow has ready assets {', '.join(ready_assets)} and blocked assets "
            f"{', '.join(blocked_assets)}."
        )
    elif ready_assets:
        reason = (
            f"Crypto workflow preflight completed for {', '.join(ready_assets)}; "
            "strategy evidence aggregation is deferred to later phases."
        )
    return ResearchExecutionWorkflowResult(
        workflow_type=ResearchExecutionWorkflowType.CRYPTO_MULTI_ASSET,
        status=status,
        decision=decision.decision,
        decision_reason=reason,
        report_ids=report_ids,
        asset_results=preflight_results,
        warnings=warnings,
        limitations=limitations,
        missing_data_actions=missing_actions,
    )


def _evidence_summary(
    *,
    execution_run_id: str,
    created_at: datetime,
    workflow_result: ResearchExecutionWorkflowResult,
    preflight_results: list[ResearchExecutionPreflightResult],
) -> ResearchEvidenceSummary:
    ready_assets = [result.asset for result in preflight_results if result.ready and result.asset]
    blocked_assets = [
        result.asset
        for result in preflight_results
        if result.status == ResearchExecutionWorkflowStatus.BLOCKED and result.asset
    ]
    return ResearchEvidenceSummary(
        execution_run_id=execution_run_id,
        status=workflow_result.status,
        decision=workflow_result.decision,
        workflow_results=[workflow_result],
        crypto_summary={
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
                    "date_end": result.date_end.isoformat()
                    if result.date_end is not None
                    else None,
                }
                for result in preflight_results
                if result.asset is not None and result.date_start is not None
            },
        },
        missing_data_checklist=workflow_result.missing_data_actions,
        limitations=workflow_result.limitations,
        research_only_warnings=[
            "Evidence labels are research decisions only and do not claim profitability, "
            "predictive power, safety, or live readiness.",
            RESEARCH_ONLY_WARNING,
        ],
        created_at=created_at,
    )


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


def _execution_run_id(created_at: datetime) -> str:
    return f"rex_{created_at.strftime('%Y%m%d_%H%M%S_%f')}_crypto"


def _flatten_unique(values) -> list[str]:
    result = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
