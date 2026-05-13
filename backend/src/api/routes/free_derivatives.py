from fastapi import APIRouter, Depends, status

from src.api.validation import api_error, invalid_data_source_config
from src.free_derivatives.orchestration import assemble_placeholder_bootstrap_run
from src.free_derivatives.report_store import FreeDerivativesReportStore
from src.models.free_derivatives import (
    FreeDerivativesBootstrapRequest,
    FreeDerivativesBootstrapRun,
    FreeDerivativesBootstrapRunListResponse,
    FreeDerivativesRunStatus,
    validate_filesystem_safe_id,
)

router = APIRouter()


def get_free_derivatives_report_store() -> FreeDerivativesReportStore:
    return FreeDerivativesReportStore()


@router.post(
    "/data-sources/bootstrap/free-derivatives",
    response_model=FreeDerivativesBootstrapRun,
    status_code=status.HTTP_201_CREATED,
)
async def run_free_derivatives_bootstrap(
    request: FreeDerivativesBootstrapRequest,
    store: FreeDerivativesReportStore = Depends(get_free_derivatives_report_store),
) -> FreeDerivativesBootstrapRun:
    """Run fixture-backed free derivatives bootstrap and persist the report."""

    try:
        run = assemble_placeholder_bootstrap_run(request, store=store)
    except ValueError as exc:
        invalid_data_source_config(str(exc))
    if run.status == FreeDerivativesRunStatus.BLOCKED:
        api_error(
            400,
            "MISSING_DATA",
            "No enabled free derivatives source could run with the provided request.",
            [
                {
                    "field": result.source.value,
                    "message": "; ".join(result.missing_data_actions or result.warnings),
                }
                for result in run.source_results
            ],
        )
    return store.persist_run(run)

    raise RuntimeError("unreachable")


@router.get(
    "/data-sources/bootstrap/free-derivatives/runs",
    response_model=FreeDerivativesBootstrapRunListResponse,
)
async def list_free_derivatives_bootstrap_runs(
    store: FreeDerivativesReportStore = Depends(get_free_derivatives_report_store),
) -> FreeDerivativesBootstrapRunListResponse:
    """List saved free derivatives runs."""

    return store.list_runs()


@router.get(
    "/data-sources/bootstrap/free-derivatives/runs/{run_id}",
    response_model=FreeDerivativesBootstrapRun,
)
async def get_free_derivatives_bootstrap_run(
    run_id: str,
    store: FreeDerivativesReportStore = Depends(get_free_derivatives_report_store),
) -> FreeDerivativesBootstrapRun:
    """Read one persisted free derivatives run."""

    try:
        validate_filesystem_safe_id(run_id, label="run_id")
    except ValueError as exc:
        invalid_data_source_config(str(exc))

    try:
        return store.read_run(run_id)
    except FileNotFoundError:
        api_error(404, "NOT_FOUND", f"Free derivatives run '{run_id}' was not found")

    raise RuntimeError("unreachable")
