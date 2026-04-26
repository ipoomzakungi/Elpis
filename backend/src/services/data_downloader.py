import logging
from pathlib import Path

import polars as pl

from src.models.providers import (
    DataArtifact,
    ProviderDataType,
    ProviderDownloadRequest,
    ProviderDownloadResult,
    ProviderDownloadStatus,
    UnsupportedCapability,
)
from src.providers.errors import UnsupportedCapabilityError
from src.providers.registry import ProviderRegistry, create_default_provider_registry
from src.repositories.parquet_repo import ParquetRepository

logger = logging.getLogger(__name__)


class DataDownloader:
    """Orchestrate research data downloads through registered providers."""

    def __init__(self, provider_registry: ProviderRegistry | None = None):
        self.provider_registry = provider_registry or create_default_provider_registry()
        self._owns_provider_registry = provider_registry is None
        self.parquet_repo = ParquetRepository()

    async def download_all(
        self,
        symbol: str = "BTCUSDT",
        interval: str = "15m",
        days: int = 30,
    ) -> dict:
        """Download all data types (OHLCV, OI, Funding)."""
        request = ProviderDownloadRequest(
            provider="binance",
            symbol=symbol,
            timeframe=interval,
            days=days,
            data_types=[
                ProviderDataType.OHLCV,
                ProviderDataType.OPEN_INTEREST,
                ProviderDataType.FUNDING_RATE,
            ],
        )
        result = await self.download_provider_data(request)
        return {artifact.data_type.value: artifact.rows for artifact in result.artifacts}

    async def download_provider_data(
        self,
        request: ProviderDownloadRequest,
    ) -> ProviderDownloadResult:
        """Download requested data types through the selected provider."""
        provider = self.provider_registry.get_provider(request.provider)
        provider_info = provider.get_provider_info()
        symbol = provider.validate_symbol(request.symbol or provider_info.default_symbol or "")
        timeframe = provider.validate_timeframe(request.timeframe)
        data_types = request.data_types or self._default_data_types(provider_info)
        artifacts: list[DataArtifact] = []
        skipped: list[UnsupportedCapability] = []

        try:
            for data_type in data_types:
                try:
                    frame = await self._fetch_data_type(provider, request, data_type)
                except UnsupportedCapabilityError as exc:
                    skipped.append(
                        UnsupportedCapability(
                            provider=request.provider,
                            data_type=data_type,
                            reason=exc.details[0].get("reason", exc.message),
                        )
                    )
                    continue

                if frame.is_empty():
                    logger.warning(
                        "No %s data downloaded for %s %s from %s",
                        data_type.value,
                        symbol,
                        timeframe,
                        request.provider,
                    )
                    continue

                filepath = self.parquet_repo.save_provider_data(
                    frame,
                    data_type=data_type.value,
                    provider=request.provider,
                    symbol=symbol,
                    interval=timeframe,
                )
                artifacts.append(
                    self._artifact_from_frame(
                        filepath=filepath,
                        frame=frame,
                        data_type=data_type,
                        provider=request.provider,
                        symbol=symbol,
                        timeframe=timeframe,
                    )
                )

            if not artifacts and not skipped:
                raise RuntimeError(f"No data downloaded from {provider_info.display_name}")

            status = ProviderDownloadStatus.COMPLETED
            message = f"Downloaded {provider_info.display_name} research data"
            if skipped:
                status = (
                    ProviderDownloadStatus.PARTIAL if artifacts else ProviderDownloadStatus.FAILED
                )
                message = (
                    f"Downloaded supported {provider_info.display_name} data; "
                    "skipped unsupported capabilities"
                )

            return ProviderDownloadResult(
                status=status,
                provider=request.provider,
                symbol=symbol,
                timeframe=timeframe,
                completed_data_types=[artifact.data_type for artifact in artifacts],
                skipped_data_types=skipped,
                artifacts=artifacts,
                message=message,
                warnings=[],
            )
        except Exception:
            logger.exception("Provider data download failed for %s %s", symbol, timeframe)
            raise
        finally:
            if self._owns_provider_registry:
                await self._close_provider(provider)

    async def download_ohlcv(
        self,
        symbol: str = "BTCUSDT",
        interval: str = "15m",
        days: int = 30,
    ) -> int:
        """Download OHLCV data only."""
        request = ProviderDownloadRequest(
            provider="binance",
            symbol=symbol,
            timeframe=interval,
            days=days,
            data_types=[ProviderDataType.OHLCV],
        )
        result = await self.download_provider_data(request)
        return result.artifacts[0].rows if result.artifacts else 0

    async def download_open_interest(
        self,
        symbol: str = "BTCUSDT",
        interval: str = "15m",
        days: int = 30,
    ) -> int:
        """Download open interest data only."""
        request = ProviderDownloadRequest(
            provider="binance",
            symbol=symbol,
            timeframe=interval,
            days=days,
            data_types=[ProviderDataType.OPEN_INTEREST],
        )
        result = await self.download_provider_data(request)
        return result.artifacts[0].rows if result.artifacts else 0

    async def download_funding_rate(
        self,
        symbol: str = "BTCUSDT",
        days: int = 30,
    ) -> int:
        """Download funding rate data only."""
        request = ProviderDownloadRequest(
            provider="binance",
            symbol=symbol,
            timeframe="15m",
            days=days,
            data_types=[ProviderDataType.FUNDING_RATE],
        )
        result = await self.download_provider_data(request)
        return result.artifacts[0].rows if result.artifacts else 0

    def _default_data_types(self, provider_info) -> list[ProviderDataType]:
        data_types = []
        if provider_info.supports_ohlcv:
            data_types.append(ProviderDataType.OHLCV)
        if provider_info.supports_open_interest:
            data_types.append(ProviderDataType.OPEN_INTEREST)
        if provider_info.supports_funding_rate:
            data_types.append(ProviderDataType.FUNDING_RATE)
        return data_types

    async def _fetch_data_type(
        self, provider, request, data_type: ProviderDataType
    ) -> pl.DataFrame:
        if data_type == ProviderDataType.OHLCV:
            return await provider.fetch_ohlcv(request)
        if data_type == ProviderDataType.OPEN_INTEREST:
            return await provider.fetch_open_interest(request)
        if data_type == ProviderDataType.FUNDING_RATE:
            return await provider.fetch_funding_rate(request)
        raise ValueError(f"Unsupported provider data type '{data_type}'")

    def _artifact_from_frame(
        self,
        filepath: Path,
        frame: pl.DataFrame,
        data_type: ProviderDataType,
        provider: str,
        symbol: str,
        timeframe: str,
    ) -> DataArtifact:
        return DataArtifact(
            data_type=data_type,
            path=filepath.as_posix(),
            rows=len(frame),
            provider=provider,
            symbol=symbol,
            timeframe=timeframe,
            first_timestamp=frame["timestamp"].min() if "timestamp" in frame.columns else None,
            last_timestamp=frame["timestamp"].max() if "timestamp" in frame.columns else None,
        )

    async def _close_provider(self, provider) -> None:
        close = getattr(provider, "close", None)
        if close is not None:
            await close()
