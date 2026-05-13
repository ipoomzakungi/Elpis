from fastapi import APIRouter, Depends, HTTPException, status

from src.models.xau_quikstrike_fusion import (
    XauQuikStrikeFusionRequest,
    validate_xau_fusion_safe_id,
)
from src.xau_quikstrike_fusion.report_store import XauQuikStrikeFusionReportStore

router = APIRouter()

FUSION_PLACEHOLDER_LIMITATIONS = [
    "XAU QuikStrike fusion routes are registered for local research inspection only.",
    "Fusion source loading, matching, persistence, and downstream XAU report creation are planned "
    "for later 014 slices.",
]


def get_xau_quikstrike_fusion_report_store() -> XauQuikStrikeFusionReportStore:
    return XauQuikStrikeFusionReportStore()


@router.post(
    "/xau/quikstrike-fusion/reports",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
)
async def create_xau_quikstrike_fusion_report(
    request: XauQuikStrikeFusionRequest,
    store: XauQuikStrikeFusionReportStore = Depends(get_xau_quikstrike_fusion_report_store),
) -> dict:
    """Placeholder for creating a local-only XAU QuikStrike fusion report."""

    _ = request
    _ = store
    _not_implemented("XAU QuikStrike fusion report creation is not implemented in this slice")


@router.get("/xau/quikstrike-fusion/reports")
async def list_xau_quikstrike_fusion_reports(
    store: XauQuikStrikeFusionReportStore = Depends(get_xau_quikstrike_fusion_report_store),
) -> dict:
    """Return a structured placeholder list response for saved fusion reports."""

    return {
        "reports": [],
        "placeholder": True,
        "report_root": store.report_root().as_posix(),
        "limitations": FUSION_PLACEHOLDER_LIMITATIONS,
    }


@router.get("/xau/quikstrike-fusion/reports/{report_id}")
async def get_xau_quikstrike_fusion_report(report_id: str) -> dict:
    """Placeholder for reading one saved fusion report."""

    _validate_report_id(report_id)
    _not_implemented("XAU QuikStrike fusion report reads are not implemented in this slice")


@router.get("/xau/quikstrike-fusion/reports/{report_id}/rows")
async def get_xau_quikstrike_fusion_rows(report_id: str) -> dict:
    """Placeholder for reading fused rows for one report."""

    _validate_report_id(report_id)
    _not_implemented("XAU QuikStrike fusion row reads are not implemented in this slice")


@router.get("/xau/quikstrike-fusion/reports/{report_id}/missing-context")
async def get_xau_quikstrike_fusion_missing_context(report_id: str) -> dict:
    """Placeholder for reading structured missing-context reasons for one report."""

    _validate_report_id(report_id)
    _not_implemented(
        "XAU QuikStrike fusion missing-context reads are not implemented in this slice"
    )


def _validate_report_id(report_id: str) -> None:
    try:
        validate_xau_fusion_safe_id(report_id, "report_id")
    except ValueError as exc:
        _validation_error(str(exc))


def _validation_error(message: str) -> None:
    raise HTTPException(
        status_code=400,
        detail={"error": {"code": "VALIDATION_ERROR", "message": message, "details": []}},
    )


def _not_implemented(message: str) -> None:
    raise HTTPException(
        status_code=501,
        detail={
            "error": {
                "code": "NOT_IMPLEMENTED",
                "message": message,
                "details": FUSION_PLACEHOLDER_LIMITATIONS,
            }
        },
    )
