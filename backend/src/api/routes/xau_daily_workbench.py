from fastapi import APIRouter, Depends

from src.api.validation import api_error
from src.models.xau_daily_structural_map import validate_xau_daily_structural_map_safe_id
from src.models.xau_daily_workbench import (
    XauDailyWorkbenchCandidateResponse,
    XauDailyWorkbenchLatestResponse,
    XauDailyWorkbenchMapResponse,
    XauDailyWorkbenchRunRequest,
    XauDailyWorkbenchRunResult,
)
from src.xau_daily_workbench.report_store import validate_xau_daily_workbench_safe_id
from src.xau_daily_workbench.service import XauDailyWorkbenchService

router = APIRouter()


def get_xau_daily_workbench_service() -> XauDailyWorkbenchService:
    return XauDailyWorkbenchService()


@router.post(
    "/research/xau/workbench/run",
    response_model=XauDailyWorkbenchRunResult,
)
async def run_xau_daily_workbench(
    request: XauDailyWorkbenchRunRequest,
    service: XauDailyWorkbenchService = Depends(get_xau_daily_workbench_service),
) -> XauDailyWorkbenchRunResult:
    """Run the local research-only XAU daily workbench."""

    return service.run(request)


@router.get(
    "/research/xau/workbench/latest",
    response_model=XauDailyWorkbenchLatestResponse,
)
async def get_latest_xau_daily_workbench(
    service: XauDailyWorkbenchService = Depends(get_xau_daily_workbench_service),
) -> XauDailyWorkbenchLatestResponse:
    """Read the latest local research-only XAU daily workbench run."""

    return service.latest()


@router.get(
    "/research/xau/workbench/runs/{run_id}",
    response_model=XauDailyWorkbenchRunResult,
)
async def get_xau_daily_workbench_run(
    run_id: str,
    service: XauDailyWorkbenchService = Depends(get_xau_daily_workbench_service),
) -> XauDailyWorkbenchRunResult:
    """Read one persisted XAU daily workbench run."""

    _validate_run_id(run_id)
    try:
        return service.read_run(run_id)
    except FileNotFoundError:
        _not_found("XAU daily workbench run", run_id)

    raise RuntimeError("unreachable")


@router.get(
    "/research/xau/workbench/maps/{map_id}",
    response_model=XauDailyWorkbenchMapResponse,
)
async def get_xau_daily_workbench_map(
    map_id: str,
    service: XauDailyWorkbenchService = Depends(get_xau_daily_workbench_service),
) -> XauDailyWorkbenchMapResponse:
    """Read one persisted XAU daily structural map through the workbench API."""

    _validate_map_id(map_id)
    try:
        return service.read_map(map_id)
    except FileNotFoundError:
        _not_found("XAU daily structural map", map_id)

    raise RuntimeError("unreachable")


@router.get(
    "/research/xau/workbench/candidates/{map_id}",
    response_model=XauDailyWorkbenchCandidateResponse,
)
async def get_xau_daily_workbench_candidates(
    map_id: str,
    service: XauDailyWorkbenchService = Depends(get_xau_daily_workbench_service),
) -> XauDailyWorkbenchCandidateResponse:
    """Read persisted Feature 021 candidate sidecars for a workbench map."""

    _validate_map_id(map_id)
    try:
        return service.read_candidates(map_id)
    except FileNotFoundError:
        _not_found("XAU daily workbench candidates", map_id)

    raise RuntimeError("unreachable")


def _validate_map_id(map_id: str) -> None:
    try:
        validate_xau_daily_structural_map_safe_id(map_id, "map_id")
    except ValueError as exc:
        api_error(400, "VALIDATION_ERROR", str(exc))


def _validate_run_id(run_id: str) -> None:
    try:
        validate_xau_daily_workbench_safe_id(run_id, "run_id")
    except ValueError as exc:
        api_error(400, "VALIDATION_ERROR", str(exc))


def _not_found(kind: str, identifier: str) -> None:
    api_error(404, "NOT_FOUND", f"{kind} '{identifier}' was not found")
