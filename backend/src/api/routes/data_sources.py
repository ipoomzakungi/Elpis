from fastapi import APIRouter, HTTPException, status

from src.api.validation import data_source_not_found, invalid_data_source_config
from src.data_sources.capabilities import capability_matrix
from src.data_sources.first_run import FirstEvidenceRunOrchestrator
from src.data_sources.missing_data import default_missing_data_actions
from src.data_sources.preflight import run_data_source_preflight
from src.data_sources.readiness import data_source_readiness
from src.data_sources.report_store import DataSourceFirstRunReportStore
from src.models.data_sources import (
    DataSourceCapabilityListResponse,
    DataSourceMissingDataResponse,
    DataSourcePreflightRequest,
    DataSourcePreflightResult,
    DataSourceReadiness,
    FirstEvidenceRunRequest,
    FirstEvidenceRunResult,
)

router = APIRouter()


@router.get("/data-sources/readiness", response_model=DataSourceReadiness)
async def get_data_source_readiness() -> DataSourceReadiness:
    """Return research-only data-source readiness without exposing secret values."""

    return data_source_readiness()


@router.get("/data-sources/capabilities", response_model=DataSourceCapabilityListResponse)
async def get_data_source_capabilities() -> DataSourceCapabilityListResponse:
    """Return the static research data-source capability matrix."""

    return DataSourceCapabilityListResponse(capabilities=capability_matrix())


@router.get("/data-sources/missing-data", response_model=DataSourceMissingDataResponse)
async def get_data_source_missing_data() -> DataSourceMissingDataResponse:
    """Return default missing-data instructions for the first evidence workflow."""

    return DataSourceMissingDataResponse(actions=default_missing_data_actions())


@router.post("/data-sources/preflight", response_model=DataSourcePreflightResult)
async def run_data_source_preflight_endpoint(
    request: DataSourcePreflightRequest,
) -> DataSourcePreflightResult:
    """Check local data-source readiness without fetching external data."""

    return run_data_source_preflight(request)


@router.post(
    "/evidence/first-run",
    response_model=FirstEvidenceRunResult,
    status_code=status.HTTP_201_CREATED,
)
async def run_first_evidence(request: FirstEvidenceRunRequest) -> FirstEvidenceRunResult:
    """Run a research-only first evidence wrapper around feature 007."""

    try:
        return FirstEvidenceRunOrchestrator().run(request)
    except ValueError as exc:
        invalid_data_source_config(str(exc))

    raise HTTPException(status_code=500, detail="First evidence run failed")


@router.get(
    "/evidence/first-run/{first_run_id}",
    response_model=FirstEvidenceRunResult,
)
async def get_first_evidence(first_run_id: str) -> FirstEvidenceRunResult:
    """Read one persisted first evidence run wrapper."""

    try:
        return DataSourceFirstRunReportStore().read_first_run(first_run_id)
    except FileNotFoundError:
        data_source_not_found(first_run_id)
    except ValueError as exc:
        invalid_data_source_config(str(exc))

    raise HTTPException(status_code=500, detail="First evidence run read failed")
