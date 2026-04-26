import polars as pl

from src.models.providers import (
    ProviderCapability,
    ProviderDataType,
    ProviderDownloadRequest,
    ProviderInfo,
    ProviderSymbol,
)
from src.providers.base import validate_normalized_frame
from src.providers.errors import ProviderValidationError
from src.services.binance_client import BinanceClient


class BinanceProvider:
    """Research provider for public Binance USD-M Futures market data."""

    name = "binance"
    display_name = "Binance USD-M Futures"
    default_symbol = "BTCUSDT"
    supported_timeframes = ["15m"]

    def __init__(self, client: BinanceClient | None = None):
        self._client = client
        self._owns_client = client is None

    @property
    def client(self) -> BinanceClient:
        if self._client is None:
            self._client = BinanceClient()
        return self._client

    def get_provider_info(self) -> ProviderInfo:
        return ProviderInfo(
            provider=self.name,
            display_name=self.display_name,
            supports_ohlcv=True,
            supports_open_interest=True,
            supports_funding_rate=True,
            requires_auth=False,
            supported_timeframes=self.supported_timeframes,
            default_symbol=self.default_symbol,
            limitations=[
                "Uses public Binance USD-M Futures market data only",
                "Binance official OI is acceptable for v0 prototype research but not enough "
                "for serious multi-year OI research",
            ],
            capabilities=[
                ProviderCapability(data_type=ProviderDataType.OHLCV, supported=True),
                ProviderCapability(data_type=ProviderDataType.OPEN_INTEREST, supported=True),
                ProviderCapability(data_type=ProviderDataType.FUNDING_RATE, supported=True),
            ],
        )

    def get_supported_symbols(self) -> list[ProviderSymbol]:
        return [
            ProviderSymbol(
                symbol=self.default_symbol,
                display_name="Bitcoin / Tether USD-M Perpetual",
                asset_class="crypto",
                supports_ohlcv=True,
                supports_open_interest=True,
                supports_funding_rate=True,
                notes=["Public Binance USD-M Futures research baseline"],
            )
        ]

    def get_supported_timeframes(self) -> list[str]:
        return self.supported_timeframes.copy()

    def validate_symbol(self, symbol: str) -> str:
        normalized = symbol.upper().strip()
        if normalized != self.default_symbol:
            raise ProviderValidationError(
                f"Symbol '{symbol}' is not supported by provider '{self.name}'"
            )
        return normalized

    def validate_timeframe(self, timeframe: str) -> str:
        normalized = timeframe.strip()
        if normalized not in self.supported_timeframes:
            raise ProviderValidationError(
                f"Timeframe '{timeframe}' is not supported by provider '{self.name}'"
            )
        return normalized

    async def fetch_ohlcv(self, request: ProviderDownloadRequest) -> pl.DataFrame:
        symbol = self.validate_symbol(request.symbol or self.default_symbol)
        timeframe = self.validate_timeframe(request.timeframe)
        data = await self.client.download_ohlcv(
            symbol=symbol, interval=timeframe, days=request.days or 30
        )
        return self._normalize_ohlcv(data, symbol=symbol, timeframe=timeframe)

    async def fetch_open_interest(self, request: ProviderDownloadRequest) -> pl.DataFrame:
        symbol = self.validate_symbol(request.symbol or self.default_symbol)
        timeframe = self.validate_timeframe(request.timeframe)
        data = await self.client.download_open_interest(
            symbol=symbol,
            period=timeframe,
            days=request.days or 30,
        )
        return self._normalize_open_interest(data, symbol=symbol, timeframe=timeframe)

    async def fetch_funding_rate(self, request: ProviderDownloadRequest) -> pl.DataFrame:
        symbol = self.validate_symbol(request.symbol or self.default_symbol)
        timeframe = self.validate_timeframe(request.timeframe)
        data = await self.client.download_funding_rate(symbol=symbol, days=request.days or 30)
        return self._normalize_funding_rate(data, symbol=symbol, timeframe=timeframe)

    async def close(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.close()

    def _normalize_ohlcv(self, data: pl.DataFrame, symbol: str, timeframe: str) -> pl.DataFrame:
        if data.is_empty():
            return data

        normalized = data.with_columns(
            [
                pl.lit(self.name).alias("provider"),
                pl.lit(symbol).alias("symbol"),
                pl.lit(timeframe).alias("timeframe"),
                pl.lit("binance_usdm_futures").alias("source"),
            ]
        )
        validate_normalized_frame(normalized, ProviderDataType.OHLCV.value)
        return normalized

    def _normalize_open_interest(
        self,
        data: pl.DataFrame,
        symbol: str,
        timeframe: str,
    ) -> pl.DataFrame:
        if data.is_empty():
            return data

        normalized = data.with_columns(
            [
                pl.lit(self.name).alias("provider"),
                pl.lit(symbol).alias("symbol"),
                pl.lit(timeframe).alias("timeframe"),
                pl.lit("binance_usdm_futures").alias("source"),
            ]
        )
        validate_normalized_frame(normalized, ProviderDataType.OPEN_INTEREST.value)
        return normalized

    def _normalize_funding_rate(
        self,
        data: pl.DataFrame,
        symbol: str,
        timeframe: str,
    ) -> pl.DataFrame:
        if data.is_empty():
            return data

        normalized = data.with_columns(
            [
                pl.lit(self.name).alias("provider"),
                pl.lit(symbol).alias("symbol"),
                pl.lit(timeframe).alias("timeframe"),
                pl.lit("binance_usdm_futures").alias("source"),
            ]
        )
        validate_normalized_frame(normalized, ProviderDataType.FUNDING_RATE.value)
        return normalized
