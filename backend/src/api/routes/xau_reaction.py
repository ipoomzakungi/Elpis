from fastapi import APIRouter, HTTPException

from src.models.xau_reaction import (
    XauReactionReport,
    XauReactionReportListResponse,
    XauReactionReportRequest,
    XauReactionTableResponse,
    XauRiskPlanTableResponse,
    validate_filesystem_safe_id,
)
from src.xau_reaction.orchestration import (
    XauReactionReportBlockedError,
    XauReactionReportOrchestrator,
)
from src.xau_reaction.report_store import XauReactionReportStore

router = APIRouter()


@router.post("/xau/reaction-reports", response_model=XauReactionReport)
async def create_xau_reaction_report(
    request: XauReactionReportRequest,
) -> XauReactionReport:
    """Create and persist a research-only XAU reaction report."""

    try:
        return XauReactionReportOrchestrator().run(request)
    except FileNotFoundError:
        _not_found(
            f"Source XAU Vol-OI report '{request.source_report_id}' was not found",
        )
    except XauReactionReportBlockedError as exc:
        _missing_data(str(exc), exc.details)
    except ValueError as exc:
        _validation_error(str(exc))

    raise HTTPException(status_code=500, detail="XAU reaction report creation failed")


@router.get("/xau/reaction-reports", response_model=XauReactionReportListResponse)
async def list_xau_reaction_reports() -> XauReactionReportListResponse:
    """List saved research-only XAU reaction reports."""

    return XauReactionReportStore().list_reports()


@router.get("/xau/reaction-reports/{report_id}", response_model=XauReactionReport)
async def get_xau_reaction_report(report_id: str) -> XauReactionReport:
    """Read one saved research-only XAU reaction report."""

    try:
        validate_filesystem_safe_id(report_id)
        return XauReactionReportStore().read_report(report_id)
    except ValueError as exc:
        _validation_error(str(exc))
    except FileNotFoundError:
        _not_found(f"XAU reaction report '{report_id}' was not found")

    raise HTTPException(status_code=500, detail="XAU reaction report read failed")


@router.get(
    "/xau/reaction-reports/{report_id}/reactions",
    response_model=XauReactionTableResponse,
)
async def get_xau_reaction_rows(report_id: str) -> XauReactionTableResponse:
    """Read saved XAU reaction rows."""

    try:
        validate_filesystem_safe_id(report_id)
        return XauReactionReportStore().read_reactions(report_id)
    except ValueError as exc:
        _validation_error(str(exc))
    except FileNotFoundError:
        _not_found(f"XAU reaction report '{report_id}' was not found")

    raise HTTPException(status_code=500, detail="XAU reaction rows read failed")


@router.get(
    "/xau/reaction-reports/{report_id}/risk-plan",
    response_model=XauRiskPlanTableResponse,
)
async def get_xau_reaction_risk_plan(report_id: str) -> XauRiskPlanTableResponse:
    """Read saved XAU bounded risk-plan rows."""

    try:
        validate_filesystem_safe_id(report_id)
        return XauReactionReportStore().read_risk_plan(report_id)
    except ValueError as exc:
        _validation_error(str(exc))
    except FileNotFoundError:
        _not_found(f"XAU reaction report '{report_id}' was not found")

    raise HTTPException(status_code=500, detail="XAU risk-plan rows read failed")


def _not_found(message: str) -> None:
    raise HTTPException(
        status_code=404,
        detail={"error": {"code": "NOT_FOUND", "message": message, "details": []}},
    )


def _validation_error(message: str) -> None:
    raise HTTPException(
        status_code=400,
        detail={"error": {"code": "VALIDATION_ERROR", "message": message, "details": []}},
    )


def _missing_data(message: str, details: list[dict[str, str]]) -> None:
    raise HTTPException(
        status_code=400,
        detail={"error": {"code": "MISSING_DATA", "message": message, "details": details}},
    )
