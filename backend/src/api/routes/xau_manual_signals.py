from fastapi import APIRouter, Depends

from src.api.validation import api_error
from src.models.xau_tiered_manual_signal import (
    XauManualSignalAcknowledgement,
    XauManualSignalAcknowledgementRequest,
    XauManualSignalLatestResponse,
)
from src.xau_tiered_manual_signal.service import XauTieredManualSignalService

router = APIRouter()


def get_xau_tiered_manual_signal_service() -> XauTieredManualSignalService:
    return XauTieredManualSignalService()


@router.get(
    "/research/xau/manual-signals/latest",
    response_model=XauManualSignalLatestResponse,
)
async def get_latest_xau_manual_signal(
    service: XauTieredManualSignalService = Depends(
        get_xau_tiered_manual_signal_service
    ),
) -> XauManualSignalLatestResponse:
    """Read the latest research-only XAU manual signal and acknowledgement."""

    return service.latest()


@router.post(
    "/research/xau/manual-signals/{signal_id}/acknowledge",
    response_model=XauManualSignalAcknowledgement,
)
async def acknowledge_xau_manual_signal(
    signal_id: str,
    request: XauManualSignalAcknowledgementRequest,
    service: XauTieredManualSignalService = Depends(
        get_xau_tiered_manual_signal_service
    ),
) -> XauManualSignalAcknowledgement:
    """Journal a manual acknowledgement; this does not submit or manage an order."""

    try:
        return service.acknowledge(signal_id, request)
    except FileNotFoundError as exc:
        api_error(404, "NOT_FOUND", str(exc))
    except ValueError as exc:
        api_error(400, "VALIDATION_ERROR", str(exc))

    raise RuntimeError("unreachable")
