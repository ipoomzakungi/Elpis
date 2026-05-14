from fastapi import APIRouter, Depends, status

from src.api.validation import api_error
from src.models.xau_quikstrike_fusion import (
    XauFusionMissingContextResponse,
    XauFusionReportStatus,
    XauFusionRowsResponse,
    XauQuikStrikeFusionListResponse,
    XauQuikStrikeFusionReport,
    XauQuikStrikeFusionRequest,
    validate_xau_fusion_safe_id,
)
from src.quikstrike.report_store import QuikStrikeReportStore
from src.quikstrike_matrix.report_store import QuikStrikeMatrixReportStore
from src.xau_quikstrike_fusion.orchestration import (
    create_xau_quikstrike_fusion_report as orchestrate_xau_quikstrike_fusion_report,
)
from src.xau_quikstrike_fusion.report_store import XauQuikStrikeFusionReportStore

router = APIRouter()


def get_xau_quikstrike_fusion_report_store() -> XauQuikStrikeFusionReportStore:
    return XauQuikStrikeFusionReportStore()


@router.post(
    "/xau/quikstrike-fusion/reports",
    response_model=XauQuikStrikeFusionReport,
    status_code=status.HTTP_201_CREATED,
)
async def create_xau_quikstrike_fusion_report(
    request: XauQuikStrikeFusionRequest,
    store: XauQuikStrikeFusionReportStore = Depends(get_xau_quikstrike_fusion_report_store),
) -> XauQuikStrikeFusionReport:
    """Create a local-only XAU QuikStrike fusion report from saved source reports."""

    try:
        report = orchestrate_xau_quikstrike_fusion_report(
            request,
            vol2vol_store=QuikStrikeReportStore(reports_dir=store.reports_dir),
            matrix_store=QuikStrikeMatrixReportStore(reports_dir=store.reports_dir),
            report_store=store,
        )
    except ValueError as exc:
        _validation_error(str(exc))

    _raise_if_blocked_for_api(report)
    return report


@router.get(
    "/xau/quikstrike-fusion/reports",
    response_model=XauQuikStrikeFusionListResponse,
)
async def list_xau_quikstrike_fusion_reports(
    store: XauQuikStrikeFusionReportStore = Depends(get_xau_quikstrike_fusion_report_store),
) -> XauQuikStrikeFusionListResponse:
    """List saved local-only XAU QuikStrike fusion reports."""

    return store.list_reports()


@router.get(
    "/xau/quikstrike-fusion/reports/{report_id}",
    response_model=XauQuikStrikeFusionReport,
)
async def get_xau_quikstrike_fusion_report(
    report_id: str,
    store: XauQuikStrikeFusionReportStore = Depends(get_xau_quikstrike_fusion_report_store),
) -> XauQuikStrikeFusionReport:
    """Read one saved local-only XAU QuikStrike fusion report."""

    _validate_report_id(report_id)
    try:
        return store.read_report(report_id)
    except FileNotFoundError:
        _not_found(report_id)

    raise RuntimeError("unreachable")


@router.get(
    "/xau/quikstrike-fusion/reports/{report_id}/rows",
    response_model=XauFusionRowsResponse,
)
async def get_xau_quikstrike_fusion_rows(
    report_id: str,
    store: XauQuikStrikeFusionReportStore = Depends(get_xau_quikstrike_fusion_report_store),
) -> XauFusionRowsResponse:
    """Read fused rows for one saved local-only XAU QuikStrike fusion report."""

    _validate_report_id(report_id)
    try:
        return store.read_rows_response(report_id)
    except FileNotFoundError:
        _not_found(report_id)

    raise RuntimeError("unreachable")


@router.get(
    "/xau/quikstrike-fusion/reports/{report_id}/missing-context",
    response_model=XauFusionMissingContextResponse,
)
async def get_xau_quikstrike_fusion_missing_context(
    report_id: str,
    store: XauQuikStrikeFusionReportStore = Depends(get_xau_quikstrike_fusion_report_store),
) -> XauFusionMissingContextResponse:
    """Read structured missing-context reasons for one saved fusion report."""

    _validate_report_id(report_id)
    try:
        return store.read_missing_context_response(report_id)
    except FileNotFoundError:
        _not_found(report_id)

    raise RuntimeError("unreachable")


def _validate_report_id(report_id: str) -> None:
    try:
        validate_xau_fusion_safe_id(report_id, "report_id")
    except ValueError as exc:
        _validation_error(str(exc))


def _validation_error(message: str) -> None:
    api_error(400, "VALIDATION_ERROR", message)


def _not_found(report_id: str) -> None:
    api_error(
        404,
        "NOT_FOUND",
        f"XAU QuikStrike fusion report '{report_id}' was not found",
    )


def _raise_if_blocked_for_api(report: XauQuikStrikeFusionReport) -> None:
    if report.status != XauFusionReportStatus.BLOCKED:
        return

    source_not_found_details: list[dict[str, str]] = []
    if report.vol2vol_source.status == "missing":
        source_not_found_details.append(
            {
                "field": "vol2vol_report_id",
                "message": f"Vol2Vol report '{report.vol2vol_source.report_id}' was not found",
            }
        )
    if report.matrix_source.status == "missing":
        source_not_found_details.append(
            {
                "field": "matrix_report_id",
                "message": f"Matrix report '{report.matrix_source.report_id}' was not found",
            }
        )
    if source_not_found_details:
        api_error(
            404,
            "SOURCE_NOT_FOUND",
            "Selected QuikStrike source report was not found",
            source_not_found_details,
        )

    incompatible_details = [
        {
            "field": item.context_key,
            "message": item.message,
        }
        for item in (report.context_summary.missing_context if report.context_summary else [])
        if item.context_key.endswith("_product")
    ]
    if incompatible_details:
        api_error(
            400,
            "INCOMPATIBLE_SOURCE_REPORTS",
            "Selected QuikStrike reports cannot be fused",
            incompatible_details,
        )

    blocked_details = [
        {
            "field": item.context_key,
            "message": item.message,
        }
        for item in (report.context_summary.missing_context if report.context_summary else [])
        if item.blocks_fusion
    ]
    api_error(
        400,
        "BLOCKED_FUSION",
        "Selected QuikStrike reports could not produce a fusion report",
        blocked_details,
    )
