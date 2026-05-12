from fastapi import APIRouter, status

from src.api.validation import api_error, invalid_data_source_config
from src.free_derivatives.orchestration import assemble_placeholder_bootstrap_run
from src.models.free_derivatives import (
    FreeDerivativesBootstrapRequest,
    FreeDerivativesBootstrapRun,
    FreeDerivativesBootstrapRunListResponse,
    validate_filesystem_safe_id,
)

router = APIRouter()


@router.post(
    "/data-sources/bootstrap/free-derivatives",
    response_model=FreeDerivativesBootstrapRun,
    status_code=status.HTTP_201_CREATED,
)
async def run_free_derivatives_bootstrap(
    request: FreeDerivativesBootstrapRequest,
) -> FreeDerivativesBootstrapRun:
    """Return a structured research-only placeholder run for free derivatives data."""

    try:
        return assemble_placeholder_bootstrap_run(request)
    except ValueError as exc:
        invalid_data_source_config(str(exc))

    raise RuntimeError("unreachable")


@router.get(
    "/data-sources/bootstrap/free-derivatives/runs",
    response_model=FreeDerivativesBootstrapRunListResponse,
)
async def list_free_derivatives_bootstrap_runs() -> FreeDerivativesBootstrapRunListResponse:
    """List saved free derivatives runs once persistence is implemented."""

    return FreeDerivativesBootstrapRunListResponse(runs=[])


@router.get(
    "/data-sources/bootstrap/free-derivatives/runs/{run_id}",
    response_model=FreeDerivativesBootstrapRun,
)
async def get_free_derivatives_bootstrap_run(run_id: str) -> FreeDerivativesBootstrapRun:
    """Read one free derivatives run once persistence is implemented."""

    try:
        validate_filesystem_safe_id(run_id, label="run_id")
    except ValueError as exc:
        invalid_data_source_config(str(exc))

    api_error(404, "NOT_FOUND", f"Free derivatives run '{run_id}' was not found")
    raise RuntimeError("unreachable")

