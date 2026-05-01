from fastapi import APIRouter, HTTPException

from src.api.validation import (
    invalid_xau_config,
    xau_options_file_invalid,
    xau_report_not_found,
)
from src.models.xau import (
    XauVolOiReport,
    XauVolOiReportListResponse,
    XauVolOiReportRequest,
    XauWallTableResponse,
    XauZoneTableResponse,
)
from src.xau.orchestration import XauReportOrchestrator, XauReportValidationError
from src.xau.report_store import XauReportStore

router = APIRouter()


@router.post("/xau/vol-oi/reports", response_model=XauVolOiReport)
async def run_xau_vol_oi_report(request: XauVolOiReportRequest) -> XauVolOiReport:
    """Run a local XAU Vol-OI source-validation report."""

    try:
        return XauReportOrchestrator().run(request)
    except XauReportValidationError as exc:
        xau_options_file_invalid(
            "Gold options OI file is missing or invalid",
            _validation_details(exc.validation_report.errors),
        )
    except ValueError as exc:
        invalid_xau_config(str(exc))

    raise HTTPException(status_code=500, detail="XAU Vol-OI report run failed")


@router.get("/xau/vol-oi/reports", response_model=XauVolOiReportListResponse)
async def list_xau_vol_oi_reports() -> XauVolOiReportListResponse:
    """List saved XAU Vol-OI reports."""

    return XauReportStore().list_reports()


@router.get("/xau/vol-oi/reports/{report_id}", response_model=XauVolOiReport)
async def get_xau_vol_oi_report(report_id: str) -> XauVolOiReport:
    """Read saved XAU Vol-OI report metadata."""

    try:
        return XauReportStore().read_report(report_id)
    except ValueError as exc:
        invalid_xau_config(str(exc))
    except FileNotFoundError:
        xau_report_not_found(report_id)

    raise HTTPException(status_code=500, detail="XAU Vol-OI report read failed")


@router.get("/xau/vol-oi/reports/{report_id}/walls", response_model=XauWallTableResponse)
async def get_xau_vol_oi_walls(report_id: str) -> XauWallTableResponse:
    """Read saved scored XAU wall rows."""

    try:
        return XauReportStore().read_walls(report_id)
    except ValueError as exc:
        invalid_xau_config(str(exc))
    except FileNotFoundError:
        xau_report_not_found(report_id)

    raise HTTPException(status_code=500, detail="XAU wall table read failed")


@router.get("/xau/vol-oi/reports/{report_id}/zones", response_model=XauZoneTableResponse)
async def get_xau_vol_oi_zones(report_id: str) -> XauZoneTableResponse:
    """Read saved XAU zone classification rows."""

    try:
        return XauReportStore().read_zones(report_id)
    except ValueError as exc:
        invalid_xau_config(str(exc))
    except FileNotFoundError:
        xau_report_not_found(report_id)

    raise HTTPException(status_code=500, detail="XAU zone table read failed")


def _validation_details(errors: list[str]) -> list[dict[str, str]]:
    return [{"field": "options_oi_file_path", "message": error} for error in errors]
