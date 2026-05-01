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
    XauVolOiWorkflowConfig,
)
from src.models.xau import XauVolOiReport, XauVolOiReportRequest
from src.reports.writer import RESEARCH_ONLY_WARNING
from src.research_execution.aggregation import (
    classify_preflight_decision,
    summarize_preflight_assets,
    summarize_proxy_preflight,
    summarize_xau_evidence,
)
from src.research_execution.preflight import (
    preflight_crypto_processed_features,
    preflight_proxy_ohlcv_assets,
    preflight_xau_options_file,
    xau_missing_data_instructions,
)
from src.research_execution.report_store import ResearchExecutionReportStore
from src.xau.orchestration import XauReportOrchestrator, XauReportValidationError
from src.xau.report_store import XauReportStore


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
                "Only crypto, proxy OHLCV, and XAU Vol-OI research execution are "
                "implemented in this phase"
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
        xau_summary = None
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

        if normalized_request.xau is not None and normalized_request.xau.enabled:
            xau_preflight, xau_report, missing_report_id = self._run_xau_workflow(
                normalized_request.xau
            )
            preflight_results.extend(xau_preflight)
            workflow_results.append(
                _xau_workflow_result(
                    normalized_request.xau,
                    xau_preflight,
                    xau_report,
                )
            )
            xau_summary = summarize_xau_evidence(
                xau_preflight,
                xau_report,
                missing_report_id=missing_report_id,
            )

        evidence_summary = _evidence_summary(
            execution_run_id=execution_run_id,
            created_at=created_at,
            workflow_results=workflow_results,
            crypto_summary=crypto_summary,
            proxy_summary=proxy_summary,
            xau_summary=xau_summary,
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

    def _run_xau_workflow(
        self,
        config: XauVolOiWorkflowConfig,
    ) -> tuple[list[ResearchExecutionPreflightResult], XauVolOiReport | None, str | None]:
        if config.existing_xau_report_id:
            try:
                report = XauReportStore().read_report(config.existing_xau_report_id)
            except FileNotFoundError:
                return (
                    [_missing_xau_report_result(config.existing_xau_report_id)],
                    None,
                    config.existing_xau_report_id,
                )
            return (
                [_xau_preflight_result_from_report(report, source_identity="xau_vol_oi_report")],
                report,
                None,
            )

        preflight = preflight_xau_options_file(config)
        if not preflight.ready:
            return ([preflight], None, None)

        try:
            request = _xau_report_request(config)
            report = XauReportOrchestrator().run(request)
        except XauReportValidationError as exc:
            return ([_xau_blocked_result_from_validation_error(exc)], None, None)

        return (
            [_xau_preflight_result_from_report(report, source_identity="local_options_oi")],
            report,
            None,
        )


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


def _xau_workflow_result(
    config: XauVolOiWorkflowConfig,
    preflight_results: list[ResearchExecutionPreflightResult],
    xau_report: XauVolOiReport | None,
) -> ResearchExecutionWorkflowResult:
    decision = classify_preflight_decision(preflight_results)
    status = _workflow_status(preflight_results)
    report_ids = [xau_report.report_id] if xau_report is not None else []
    if xau_report is None and config.existing_xau_report_id and status != "blocked":
        report_ids.append(config.existing_xau_report_id)

    missing_actions = _flatten_unique(
        [
            *[action for result in preflight_results for action in result.missing_data_actions],
            *(
                xau_report.missing_data_instructions
                if xau_report is not None
                else []
            ),
        ]
    )
    warnings = _flatten_unique(
        [
            *[warning for result in preflight_results for warning in result.warnings],
            *(xau_report.warnings if xau_report is not None else []),
            (
                "XAU Vol-OI workflow evidence is research-only and does not imply "
                "profitability, predictive power, safety, or live readiness."
            ),
        ]
    )
    limitations = _flatten_unique(
        [
            *[limitation for result in preflight_results for limitation in result.limitations],
            *(xau_report.limitations if xau_report is not None else []),
            (
                "Yahoo GC=F and GLD are OHLCV proxies only, not gold options OI, "
                "futures OI, IV, or XAUUSD execution sources."
            ),
        ]
    )
    reason = decision.reason
    if xau_report is not None:
        reason = (
            f"XAU Vol-OI workflow linked report {xau_report.report_id} with "
            f"{xau_report.wall_count} wall rows and {xau_report.zone_count} zone rows."
        )
    return ResearchExecutionWorkflowResult(
        workflow_type=ResearchExecutionWorkflowType.XAU_VOL_OI,
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
    xau_summary: dict | None,
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
        xau_summary=xau_summary,
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
        or (request.xau is not None and request.xau.enabled)
    )


def _xau_report_request(config: XauVolOiWorkflowConfig) -> XauVolOiReportRequest:
    if config.options_oi_file_path is None:
        raise ValueError("options_oi_file_path is required when creating an XAU report")
    return XauVolOiReportRequest.model_validate(
        {
            "options_oi_file_path": config.options_oi_file_path,
            "spot_reference": config.spot_reference,
            "futures_reference": config.futures_reference,
            "manual_basis": config.manual_basis,
            "volatility_snapshot": config.volatility_snapshot,
            "include_2sd_range": config.include_2sd_range,
        }
    )


def _xau_preflight_result_from_report(
    report: XauVolOiReport,
    *,
    source_identity: str,
) -> ResearchExecutionPreflightResult:
    rows = report.source_validation.rows
    timestamps = sorted(row.timestamp for row in rows)
    return ResearchExecutionPreflightResult(
        workflow_type=ResearchExecutionWorkflowType.XAU_VOL_OI,
        status=ResearchExecutionWorkflowStatus.COMPLETED,
        asset="XAU",
        source_identity=source_identity,
        ready=True,
        feature_path=report.source_validation.file_path,
        row_count=report.source_validation.accepted_row_count,
        date_start=timestamps[0] if timestamps else None,
        date_end=timestamps[-1] if timestamps else None,
        missing_data_actions=report.missing_data_instructions,
        capability_snapshot={
            "source": source_identity,
            "supports_gold_options_oi": True,
            "supports_ohlcv": False,
            "supports_funding": False,
            "supports_open_interest": False,
            "basis_mapping_available": bool(
                report.basis_snapshot and report.basis_snapshot.mapping_available
            ),
            "expected_range_available": bool(
                report.expected_range
                and getattr(report.expected_range.source, "value", report.expected_range.source)
                != "unavailable"
            ),
            "wall_count": report.wall_count,
            "zone_count": report.zone_count,
            "linked_xau_report_id": report.report_id,
        },
        warnings=report.warnings,
        limitations=report.limitations,
    )


def _missing_xau_report_result(report_id: str) -> ResearchExecutionPreflightResult:
    return ResearchExecutionPreflightResult(
        workflow_type=ResearchExecutionWorkflowType.XAU_VOL_OI,
        status=ResearchExecutionWorkflowStatus.BLOCKED,
        asset="XAU",
        source_identity="xau_vol_oi_report",
        ready=False,
        missing_data_actions=[
            f"XAU Vol-OI report '{report_id}' was not found.",
            "Create the report with POST /api/v1/xau/vol-oi/reports before referencing it.",
            "Alternatively provide options_oi_file_path to create a report during execution.",
            *xau_missing_data_instructions(None),
        ],
        limitations=[
            (
                "XAU Vol-OI evidence requires an existing feature 006 report or local "
                "options OI input."
            ),
            "Yahoo GC=F and GLD are OHLCV proxies only and are not gold options OI sources.",
        ],
    )


def _xau_blocked_result_from_validation_error(
    exc: XauReportValidationError,
) -> ResearchExecutionPreflightResult:
    report = exc.validation_report
    return ResearchExecutionPreflightResult(
        workflow_type=ResearchExecutionWorkflowType.XAU_VOL_OI,
        status=ResearchExecutionWorkflowStatus.BLOCKED,
        asset="XAU",
        source_identity="local_options_oi",
        ready=False,
        feature_path=report.file_path,
        row_count=report.accepted_row_count,
        missing_data_actions=[*report.errors, *report.instructions],
        warnings=report.warnings,
        limitations=[
            "XAU Vol-OI requires a valid local gold options OI CSV or Parquet import.",
            "Yahoo GC=F and GLD are OHLCV proxies only and are not gold options OI sources.",
        ],
    )
