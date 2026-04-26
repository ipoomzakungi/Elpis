from fastapi import APIRouter, Depends

from src.api.dependencies import get_provider_registry
from src.models.providers import ProviderDownloadRequest, ProviderDownloadResult, ProviderInfo
from src.providers.registry import ProviderRegistry
from src.services.data_downloader import DataDownloader

router = APIRouter()


@router.get("/providers")
async def list_providers(registry: ProviderRegistry = Depends(get_provider_registry)) -> dict:
    """List registered provider metadata."""
    return {"providers": registry.list_providers()}


@router.get("/providers/{provider_name}", response_model=ProviderInfo)
async def get_provider_details(
    provider_name: str,
    registry: ProviderRegistry = Depends(get_provider_registry),
) -> ProviderInfo:
    """Get metadata for a registered provider."""
    return registry.get_provider_info(provider_name)


@router.get("/providers/{provider_name}/symbols")
async def get_provider_symbols(
    provider_name: str,
    registry: ProviderRegistry = Depends(get_provider_registry),
) -> dict:
    """Get supported symbols for a registered provider."""
    provider = registry.get_provider(provider_name)
    return {"provider": provider.name, "symbols": provider.get_supported_symbols()}


@router.post("/data/download", response_model=ProviderDownloadResult)
async def download_provider_data(request: ProviderDownloadRequest) -> ProviderDownloadResult:
    """Download research data through the provider layer."""
    downloader = DataDownloader()
    return await downloader.download_provider_data(request)
