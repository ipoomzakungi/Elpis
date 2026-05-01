from fastapi import APIRouter

from src.data_sources.capabilities import capability_matrix
from src.data_sources.missing_data import default_missing_data_actions
from src.data_sources.readiness import data_source_readiness
from src.models.data_sources import (
    DataSourceCapabilityListResponse,
    DataSourceMissingDataResponse,
    DataSourceReadiness,
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
