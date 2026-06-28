from fastapi import APIRouter, Depends

from src.api.validation import api_error
from src.models.xau_candidate_outcome import (
    XauCandidateOutcomeLatestResponse,
    XauCandidateOutcomeRunRequest,
    XauCandidateOutcomeRunResult,
)
from src.xau_candidate_outcomes.report_store import validate_xau_candidate_outcome_safe_id
from src.xau_candidate_outcomes.service import XauCandidateOutcomeService

router = APIRouter()


def get_xau_candidate_outcome_service() -> XauCandidateOutcomeService:
    return XauCandidateOutcomeService()


@router.post(
    "/research/xau/candidate-outcomes/run",
    response_model=XauCandidateOutcomeRunResult,
)
async def run_xau_candidate_outcomes(
    request: XauCandidateOutcomeRunRequest,
    service: XauCandidateOutcomeService = Depends(get_xau_candidate_outcome_service),
) -> XauCandidateOutcomeRunResult:
    """Run local research-only forward outcomes for saved XAU candidates."""

    try:
        return service.run(request)
    except FileNotFoundError as exc:
        api_error(404, "NOT_FOUND", str(exc))

    raise RuntimeError("unreachable")


@router.get(
    "/research/xau/candidate-outcomes/latest",
    response_model=XauCandidateOutcomeLatestResponse,
)
async def get_latest_xau_candidate_outcomes(
    service: XauCandidateOutcomeService = Depends(get_xau_candidate_outcome_service),
) -> XauCandidateOutcomeLatestResponse:
    """Read the latest local research-only XAU candidate outcome run."""

    return service.latest()


@router.get(
    "/research/xau/candidate-outcomes/{outcome_run_id}",
    response_model=XauCandidateOutcomeRunResult,
)
async def get_xau_candidate_outcome_run(
    outcome_run_id: str,
    service: XauCandidateOutcomeService = Depends(get_xau_candidate_outcome_service),
) -> XauCandidateOutcomeRunResult:
    """Read one persisted XAU candidate outcome run."""

    _validate_outcome_run_id(outcome_run_id)
    try:
        return service.read_result(outcome_run_id)
    except FileNotFoundError:
        api_error(404, "NOT_FOUND", f"XAU candidate outcome run '{outcome_run_id}' was not found")

    raise RuntimeError("unreachable")


def _validate_outcome_run_id(outcome_run_id: str) -> None:
    try:
        validate_xau_candidate_outcome_safe_id(outcome_run_id, "outcome_run_id")
    except ValueError as exc:
        api_error(400, "VALIDATION_ERROR", str(exc))
