"""First evidence run orchestration for data-source onboarding."""

from collections.abc import Iterable
from datetime import datetime

from src.data_sources.preflight import DataSourcePreflightService
from src.data_sources.report_store import DataSourceFirstRunReportStore
from src.models.data_sources import (
    DataSourcePreflightResult,
    FirstEvidenceRunRequest,
    FirstEvidenceRunResult,
    FirstEvidenceRunStatus,
)
from src.models.research_execution import (
    CryptoResearchWorkflowConfig,
    ProxyResearchWorkflowConfig,
    ResearchExecutionRun,
    ResearchExecutionRunRequest,
    ResearchExecutionWorkflowStatus,
    ResearchExecutionWorkflowType,
    XauVolOiWorkflowConfig,
)
from src.research_execution.orchestration import ResearchExecutionOrchestrator

FIRST_RUN_RESEARCH_ONLY_WARNING = (
    "First evidence run orchestration is research-only and delegates to existing evidence "
    "workflows; it does not fetch external data, trade, or create execution behavior."
)


class FirstEvidenceRunNotImplementedError(NotImplementedError):
    """Compatibility error type for older placeholder tests."""


class FirstEvidenceRunOrchestrator:
    """Run data-source preflight and delegate evidence creation to feature 007."""

    def __init__(
        self,
        *,
        preflight_service: DataSourcePreflightService | None = None,
        research_execution_orchestrator: ResearchExecutionOrchestrator | None = None,
        report_store: DataSourceFirstRunReportStore | None = None,
    ):
        self.preflight_service = preflight_service or DataSourcePreflightService()
        self.research_execution_orchestrator = (
            research_execution_orchestrator or ResearchExecutionOrchestrator()
        )
        self.report_store = report_store or DataSourceFirstRunReportStore()

    def run(self, request: FirstEvidenceRunRequest) -> FirstEvidenceRunResult:
        """Run local preflight first, then delegate evidence creation."""

        normalized_request = FirstEvidenceRunRequest.model_validate(
            request.model_dump(mode="python")
        )
        created_at = datetime.utcnow()
        first_run_id = _first_run_id(created_at)
        preflight_result = self.preflight_service.run(normalized_request.preflight)

        if _should_stop_before_delegation(normalized_request, preflight_result):
            return self.report_store.write_first_run(
                _blocked_without_delegation(
                    first_run_id=first_run_id,
                    created_at=created_at,
                    preflight_result=preflight_result,
                )
            )

        execution_request = build_research_execution_request(
            normalized_request,
            preflight_result,
        )
        execution_run = self.research_execution_orchestrator.run(execution_request)
        result = _result_from_execution(
            first_run_id=first_run_id,
            created_at=created_at,
            request=normalized_request,
            preflight_result=preflight_result,
            execution_run=execution_run,
        )
        return self.report_store.write_first_run(result)


def build_research_execution_request(
    request: FirstEvidenceRunRequest,
    preflight_result: DataSourcePreflightResult,
) -> ResearchExecutionRunRequest:
    """Translate data-source preflight inputs to feature 007 execution config."""

    preflight = request.preflight
    crypto = None
    if preflight.crypto_assets or preflight.optional_crypto_assets:
        crypto = CryptoResearchWorkflowConfig(
            primary_assets=preflight.crypto_assets,
            optional_assets=preflight.optional_crypto_assets,
            timeframe=preflight.crypto_timeframe,
            processed_feature_root=preflight.processed_feature_root,
            required_capabilities=_crypto_required_capabilities(
                preflight.requested_capabilities
            ),
            existing_research_run_id=_report_id_at(
                request.use_existing_research_report_ids,
                0,
            ),
        )

    proxy = None
    if preflight.proxy_assets:
        proxy = ProxyResearchWorkflowConfig(
            assets=preflight.proxy_assets,
            provider="yahoo_finance",
            timeframe=preflight.proxy_timeframe,
            processed_feature_root=preflight.processed_feature_root,
            required_capabilities=preflight.requested_capabilities or ["ohlcv"],
            existing_research_run_id=_report_id_at(
                request.use_existing_research_report_ids,
                1,
            )
            or _report_id_at(request.use_existing_research_report_ids, 0),
        )

    xau = XauVolOiWorkflowConfig(
        options_oi_file_path=None
        if request.use_existing_xau_report_id
        else preflight.xau_options_oi_file_path,
        existing_xau_report_id=request.use_existing_xau_report_id,
    )

    return ResearchExecutionRunRequest(
        name=request.name,
        description=(
            "First evidence run generated from data-source onboarding preflight. "
            "Research-only; not live, paper, shadow, broker, or execution behavior."
        ),
        crypto=crypto,
        proxy=proxy,
        xau=xau,
        evidence_options={
            "source": "data_source_first_run",
            "preflight_status": preflight_result.status.value,
            "run_when_partial": request.run_when_partial,
        },
        reference_report_ids=request.use_existing_research_report_ids,
        research_only_acknowledged=request.research_only_acknowledged,
    )


def _result_from_execution(
    *,
    first_run_id: str,
    created_at: datetime,
    request: FirstEvidenceRunRequest,
    preflight_result: DataSourcePreflightResult,
    execution_run: ResearchExecutionRun,
) -> FirstEvidenceRunResult:
    evidence = execution_run.evidence_summary
    evidence_payload = evidence.model_dump(mode="json") if evidence is not None else None
    status = (
        _first_run_status_from_execution(evidence.status)
        if evidence is not None
        else FirstEvidenceRunStatus.FAILED
    )
    decision = evidence.decision.value if evidence is not None else None
    return FirstEvidenceRunResult(
        first_run_id=first_run_id,
        status=status,
        execution_run_id=execution_run.execution_run_id,
        evidence_report_path=execution_run.artifact_paths.get("evidence"),
        decision=decision,
        linked_research_report_ids=_linked_research_report_ids(request, execution_run),
        linked_xau_report_ids=_linked_xau_report_ids(request, execution_run),
        preflight_result=preflight_result,
        evidence_summary=evidence_payload,
        missing_data_actions=preflight_result.missing_data_actions,
        research_only_warnings=_dedupe(
            [
                FIRST_RUN_RESEARCH_ONLY_WARNING,
                *preflight_result.warnings,
                *(evidence.research_only_warnings if evidence is not None else []),
            ]
        ),
        limitations=_dedupe(
            [
                *preflight_result.limitations,
                *(evidence.limitations if evidence is not None else []),
            ]
        ),
        created_at=created_at,
    )


def _blocked_without_delegation(
    *,
    first_run_id: str,
    created_at: datetime,
    preflight_result: DataSourcePreflightResult,
) -> FirstEvidenceRunResult:
    return FirstEvidenceRunResult(
        first_run_id=first_run_id,
        status=FirstEvidenceRunStatus.BLOCKED,
        decision="data_blocked",
        preflight_result=preflight_result,
        missing_data_actions=preflight_result.missing_data_actions,
        research_only_warnings=_dedupe(
            [
                FIRST_RUN_RESEARCH_ONLY_WARNING,
                "First evidence run was not delegated because run_when_partial is false.",
                *preflight_result.warnings,
            ]
        ),
        limitations=preflight_result.limitations,
        created_at=created_at,
    )


def _should_stop_before_delegation(
    request: FirstEvidenceRunRequest,
    preflight_result: DataSourcePreflightResult,
) -> bool:
    return (
        not request.run_when_partial
        and preflight_result.status != FirstEvidenceRunStatus.COMPLETED
    )


def _first_run_status_from_execution(
    status: ResearchExecutionWorkflowStatus,
) -> FirstEvidenceRunStatus:
    if status == ResearchExecutionWorkflowStatus.COMPLETED:
        return FirstEvidenceRunStatus.COMPLETED
    if status == ResearchExecutionWorkflowStatus.PARTIAL:
        return FirstEvidenceRunStatus.PARTIAL
    if status == ResearchExecutionWorkflowStatus.FAILED:
        return FirstEvidenceRunStatus.FAILED
    return FirstEvidenceRunStatus.BLOCKED


def _linked_research_report_ids(
    request: FirstEvidenceRunRequest,
    execution_run: ResearchExecutionRun,
) -> list[str]:
    evidence = execution_run.evidence_summary
    report_ids = list(request.use_existing_research_report_ids)
    if evidence is not None:
        report_ids.extend(
            report_id
            for workflow in evidence.workflow_results
            if workflow.workflow_type
            in {
                ResearchExecutionWorkflowType.CRYPTO_MULTI_ASSET,
                ResearchExecutionWorkflowType.PROXY_OHLCV,
            }
            for report_id in workflow.report_ids
        )
    return _dedupe(report_ids)


def _linked_xau_report_ids(
    request: FirstEvidenceRunRequest,
    execution_run: ResearchExecutionRun,
) -> list[str]:
    evidence = execution_run.evidence_summary
    report_ids = [request.use_existing_xau_report_id] if request.use_existing_xau_report_id else []
    if evidence is not None:
        report_ids.extend(
            report_id
            for workflow in evidence.workflow_results
            if workflow.workflow_type == ResearchExecutionWorkflowType.XAU_VOL_OI
            for report_id in workflow.report_ids
        )
    return _dedupe(report_ids)


def _crypto_required_capabilities(requested_capabilities: Iterable[str]) -> list[str]:
    capabilities = ["ohlcv"]
    for capability in requested_capabilities:
        if capability in {"open_interest", "funding"} and capability not in capabilities:
            capabilities.append(capability)
    return capabilities


def _report_id_at(report_ids: list[str], index: int) -> str | None:
    if index >= len(report_ids):
        return None
    return report_ids[index]


def _first_run_id(created_at: datetime) -> str:
    return f"first_{created_at.strftime('%Y%m%d_%H%M%S_%f')}_evidence"


def _dedupe(values: Iterable[str | None]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        if value and value not in deduped:
            deduped.append(value)
    return deduped
