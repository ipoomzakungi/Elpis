from fastapi import APIRouter, HTTPException

from src.models.xau_reaction import (
    XauReactionReport,
    XauReactionReportListResponse,
    XauReactionReportRequest,
    XauReactionTableResponse,
    XauRiskPlanTableResponse,
)

router = APIRouter()


@router.post("/xau/reaction-reports", response_model=XauReactionReport)
async def create_xau_reaction_report(
    request: XauReactionReportRequest,
) -> XauReactionReport:
    """Placeholder for creating research-only XAU reaction reports."""

    _not_implemented()


@router.get("/xau/reaction-reports", response_model=XauReactionReportListResponse)
async def list_xau_reaction_reports() -> XauReactionReportListResponse:
    """Placeholder for listing saved XAU reaction reports."""

    _not_implemented()


@router.get("/xau/reaction-reports/{report_id}", response_model=XauReactionReport)
async def get_xau_reaction_report(report_id: str) -> XauReactionReport:
    """Placeholder for reading one saved XAU reaction report."""

    _not_implemented()


@router.get(
    "/xau/reaction-reports/{report_id}/reactions",
    response_model=XauReactionTableResponse,
)
async def get_xau_reaction_rows(report_id: str) -> XauReactionTableResponse:
    """Placeholder for reading saved XAU reaction rows."""

    _not_implemented()


@router.get(
    "/xau/reaction-reports/{report_id}/risk-plan",
    response_model=XauRiskPlanTableResponse,
)
async def get_xau_reaction_risk_plan(report_id: str) -> XauRiskPlanTableResponse:
    """Placeholder for reading saved XAU bounded risk-plan rows."""

    _not_implemented()


def _not_implemented() -> None:
    raise HTTPException(
        status_code=501,
        detail={
            "error": {
                "code": "NOT_IMPLEMENTED",
                "message": (
                    "XAU reaction report endpoints are registered, but report creation and "
                    "persistence are not implemented in this foundation slice."
                ),
                "details": [],
            }
        },
    )
