from fastapi import APIRouter, Depends

from src.api.validation import api_error
from src.models.xau_ft2_candidate import (
    XauFt2AcknowledgementRequest,
    XauFt2LatestResponse,
)
from src.xau_ft2_candidate.service import XauFt2CandidateService

router = APIRouter()


def get_xau_ft2_candidate_service() -> XauFt2CandidateService:
    return XauFt2CandidateService()


@router.get(
    "/research/xau/ft2-candidate/latest",
    response_model=XauFt2LatestResponse,
)
async def get_latest_ft2_candidate(
    service: XauFt2CandidateService = Depends(get_xau_ft2_candidate_service),
) -> XauFt2LatestResponse:
    return service.latest()


@router.post("/research/xau/ft2-candidate/{alert_id}/acknowledge")
async def acknowledge_ft2_candidate(
    alert_id: str,
    request: XauFt2AcknowledgementRequest,
    service: XauFt2CandidateService = Depends(get_xau_ft2_candidate_service),
) -> dict:
    try:
        return service.acknowledge(alert_id, request)
    except FileNotFoundError as exc:
        api_error(404, "NOT_FOUND", str(exc))

    raise RuntimeError("unreachable")
