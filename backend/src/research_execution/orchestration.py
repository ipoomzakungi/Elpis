"""Research execution runbook orchestration."""

from datetime import datetime

from src.models.research_execution import (
    CryptoResearchWorkflowConfig,
    ProxyResearchWorkflowConfig,
    ResearchEvidenceDecision,
    ResearchEvidenceSummary,
    ResearchExecutionPreflightResult,
    ResearchExecutionRun,
    ResearchExecutionRunRequest,
    ResearchExecutionWorkflowResult,
    ResearchExecutionWorkflowStatus,
    ResearchExecutionWorkflowType,
)
from src.reports.writer import RESEARCH_ONLY_WARNING
from src.research_execution.aggregation import (
    classify_preflight_decision,
    summarize_preflight_assets,
    summarize_proxy_preflight,
)
from src.research_execution.preflight import (
    preflight_crypto_processed_features,
    preflight_proxy_ohlcv_assets,
)
from src.research_execution.report_store import ResearchExecutionReportStore


class ResearchExecutionNotImplementedError(NotImplementedError):
    """Raised until story phases implement execution orchestration."""


class ResearchExecutionOrchestrator:
    """Coordinates existing research systems without adding strategy logic."""

    def __init__(self, report_store: ResearchExecutionReportStore | None = None):
        self.report_store = report_store or ResearchExecutionReportStore()

    def run(self, request: ResearchExecutionRunRequest) -> ResearchExecutionRun:
        """Run the currently implemented research execution workflow slice."""

        if not _has_supported_workflow(request):
            raise ResearchExecutionNotImplementedError(
                "Only crypto and proxy OHLCV research execution are implemented in this phase"
            )

        created_at = datetime.utcnow()
        execution_run_id = _execution_run_id(created_at)
        normalized_request = ResearchExecutionRunRequest.model_validate(
            request.model_dump(mode="python")
        )
        preflight_results: list[ResearchExecutionPreflightResult] = []
        workflow_results: list[ResearchExecutionWorkflowResult] = []
        crypto_summary = None
        proxy_summary = None
        if normalized_request.crypto is not None and normalized_request.crypto.enabled:
            crypto_preflight = preflight_crypto_processed_features(normalized_request.crypto)
            preflight_results.extend(crypto_preflight)
            workflow_results.append(
                _crypto_workflow_result(normalized_request.crypto, crypto_preflight)
            )
            crypto_summary = summarize_preflight_assets(crypto_preflight)

        if normalized_request.proxy is not None and normalized_request.proxy.enabled:
            proxy_preflight = preflight_proxy_ohlcv_assets(normalized_request.proxy)
            preflight_results.extend(proxy_preflight)
            workflow_results.append(
                _proxy_workflow_result(normalized_request.proxy, proxy_preflight)
            )
            proxy_summary = summarize_proxy_preflight(
                proxy_preflight,
                normalized_request.proxy.provider,
            )

        evidence_summary = _evidence_summary(
            execution_run_id=execution_run_id,
            created_at=created_at,
            workflow_results=workflow_results,
            crypto_summary=crypto_summary,
            proxy_summary=proxy_summary,
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


def _proxy_workflow_result(
    config: ProxyResearchWorkflowConfig,
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
                "Proxy OHLCV workflow evidence is research-only and does not imply "
                "profitability, predictive power, safety, or live readiness."
            ),
        ]
    )
    limitations = _flatten_unique(
        [
            *[limitation for result in preflight_results for limitation in result.limitations],
            (
                "Yahoo/proxy assets are comparison inputs only and are not sources of "
                "crypto OI, funding, gold options OI, futures OI, IV, or XAUUSD execution data."
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
            f"Proxy workflow has OHLCV-ready assets {', '.join(ready_assets)} and blocked "
            f"assets {', '.join(blocked_assets)}."
        )
    elif ready_assets:
        reason = (
            f"Proxy workflow preflight completed for {', '.join(ready_assets)} as "
            "OHLCV-only research comparison assets."
        )
    return ResearchExecutionWorkflowResult(
        workflow_type=ResearchExecutionWorkflowType.PROXY_OHLCV,
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
    workflow_results: list[ResearchExecutionWorkflowResult],
    crypto_summary: dict | None,
    proxy_summary: dict | None,
) -> ResearchEvidenceSummary:
    status = _overall_status(workflow_results)
    decision = _overall_decision(workflow_results)
    missing_data = _flatten_unique(
        action for result in workflow_results for action in result.missing_data_actions
    )
    limitations = _flatten_unique(
        limitation for result in workflow_results for limitation in result.limitations
    )
    return ResearchEvidenceSummary(
        execution_run_id=execution_run_id,
        status=status,
        decision=decision,
        workflow_results=workflow_results,
        crypto_summary=crypto_summary,
        proxy_summary=proxy_summary,
        missing_data_checklist=missing_data,
        limitations=limitations,
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


def _overall_status(
    workflow_results: list[ResearchExecutionWorkflowResult],
) -> ResearchExecutionWorkflowStatus:
    if not workflow_results:
        return ResearchExecutionWorkflowStatus.SKIPPED
    statuses = [result.status for result in workflow_results]
    if all(status == ResearchExecutionWorkflowStatus.COMPLETED for status in statuses):
        return ResearchExecutionWorkflowStatus.COMPLETED
    if all(status == ResearchExecutionWorkflowStatus.BLOCKED for status in statuses):
        return ResearchExecutionWorkflowStatus.BLOCKED
    if all(status == ResearchExecutionWorkflowStatus.FAILED for status in statuses):
        return ResearchExecutionWorkflowStatus.FAILED
    return ResearchExecutionWorkflowStatus.PARTIAL


def _overall_decision(
    workflow_results: list[ResearchExecutionWorkflowResult],
) -> ResearchEvidenceDecision:
    if not workflow_results:
        return ResearchEvidenceDecision.INCONCLUSIVE
    decisions = [result.decision for result in workflow_results]
    if all(decision == ResearchEvidenceDecision.DATA_BLOCKED for decision in decisions):
        return ResearchEvidenceDecision.DATA_BLOCKED
    if any(decision == ResearchEvidenceDecision.REFINE for decision in decisions):
        return ResearchEvidenceDecision.REFINE
    if any(decision == ResearchEvidenceDecision.DATA_BLOCKED for decision in decisions):
        return ResearchEvidenceDecision.REFINE
    if any(decision == ResearchEvidenceDecision.REJECT for decision in decisions):
        return ResearchEvidenceDecision.REJECT
    if all(decision == ResearchEvidenceDecision.CONTINUE for decision in decisions):
        return ResearchEvidenceDecision.CONTINUE
    return ResearchEvidenceDecision.INCONCLUSIVE


def _execution_run_id(created_at: datetime) -> str:
    return f"rex_{created_at.strftime('%Y%m%d_%H%M%S_%f')}_evidence"


def _flatten_unique(values) -> list[str]:
    result = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _has_supported_workflow(request: ResearchExecutionRunRequest) -> bool:
    return bool(
        (request.crypto is not None and request.crypto.enabled)
        or (request.proxy is not None and request.proxy.enabled)
    )
