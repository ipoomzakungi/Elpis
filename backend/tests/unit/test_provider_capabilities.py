import polars as pl
import pytest

from src.models.providers import ProviderCapability, ProviderDataType, ProviderInfo, ProviderSymbol
from src.providers.base import validate_normalized_frame
from src.providers.binance_provider import BinanceProvider
from src.providers.errors import ProviderNotFoundError, ProviderValidationError
from src.providers.registry import ProviderRegistry
from src.providers.yahoo_finance_provider import YahooFinanceProvider


class FakeProvider:
    name = "fake_provider"

    def get_provider_info(self) -> ProviderInfo:
        return ProviderInfo(
            provider=self.name,
            display_name="Fake Provider",
            supports_ohlcv=True,
            supports_open_interest=False,
            supports_funding_rate=False,
            requires_auth=False,
            supported_timeframes=["1d"],
            default_symbol="FAKE",
            limitations=["Test provider only"],
            capabilities=[
                ProviderCapability(data_type=ProviderDataType.OHLCV, supported=True),
                ProviderCapability(
                    data_type=ProviderDataType.OPEN_INTEREST,
                    supported=False,
                    unsupported_reason="Not available in fake provider",
                ),
            ],
        )

    def get_supported_symbols(self) -> list[ProviderSymbol]:
        return [
            ProviderSymbol(
                symbol="FAKE",
                display_name="Fake Symbol",
                asset_class="other",
                supports_ohlcv=True,
                supports_open_interest=False,
                supports_funding_rate=False,
            )
        ]

    def get_supported_timeframes(self) -> list[str]:
        return ["1d"]

    def validate_symbol(self, symbol: str) -> str:
        return symbol.upper()

    def validate_timeframe(self, timeframe: str) -> str:
        return timeframe

    async def fetch_ohlcv(self, request):
        return pl.DataFrame()

    async def fetch_open_interest(self, request):
        return pl.DataFrame()

    async def fetch_funding_rate(self, request):
        return pl.DataFrame()


def test_validate_normalized_frame_accepts_ohlcv_schema():
    frame = pl.DataFrame(
        {
            "timestamp": [],
            "provider": [],
            "symbol": [],
            "timeframe": [],
            "open": [],
            "high": [],
            "low": [],
            "close": [],
            "volume": [],
        }
    )

    assert validate_normalized_frame(frame, "ohlcv") is frame


def test_validate_normalized_frame_rejects_missing_columns():
    frame = pl.DataFrame({"timestamp": []})

    with pytest.raises(ProviderValidationError) as error:
        validate_normalized_frame(frame, "ohlcv")

    assert error.value.code == "VALIDATION_ERROR"
    assert "open" in error.value.message


def test_provider_capability_requires_reason_when_unsupported():
    with pytest.raises(ValueError, match="unsupported_reason"):
        ProviderCapability(data_type=ProviderDataType.FUNDING_RATE, supported=False)


def test_provider_registry_lists_provider_metadata():
    registry = ProviderRegistry([FakeProvider()])

    providers = registry.list_providers()

    assert [provider.provider for provider in providers] == ["fake_provider"]
    assert providers[0].supports_ohlcv is True


def test_provider_registry_resolves_names_case_insensitively():
    registry = ProviderRegistry([FakeProvider()])

    provider = registry.get_provider("FAKE_PROVIDER")

    assert provider.name == "fake_provider"


def test_provider_registry_raises_structured_error_for_unknown_provider():
    registry = ProviderRegistry()

    with pytest.raises(ProviderNotFoundError) as error:
        registry.get_provider("unknown")

    assert error.value.code == "PROVIDER_NOT_FOUND"
    assert error.value.status_code == 404
    assert "unknown" in error.value.message


def test_binance_provider_reports_public_research_capabilities():
    provider = BinanceProvider()

    info = provider.get_provider_info()

    assert info.provider == "binance"
    assert info.supports_ohlcv is True
    assert info.supports_open_interest is True
    assert info.supports_funding_rate is True
    assert info.requires_auth is False
    assert info.default_symbol == "BTCUSDT"
    assert "15m" in info.supported_timeframes
    assert any("public Binance" in limitation for limitation in info.limitations)


def test_binance_provider_validates_symbol_and_timeframe():
    provider = BinanceProvider()

    assert provider.validate_symbol("btcusdt") == "BTCUSDT"
    assert provider.validate_timeframe("15m") == "15m"

    with pytest.raises(ProviderValidationError):
        provider.validate_symbol("ETHUSDT")

    with pytest.raises(ProviderValidationError):
        provider.validate_timeframe("1h")


def test_yahoo_finance_provider_reports_ohlcv_only_capabilities():
    provider = YahooFinanceProvider()

    info = provider.get_provider_info()

    assert info.provider == "yahoo_finance"
    assert info.supports_ohlcv is True
    assert info.supports_open_interest is False
    assert info.supports_funding_rate is False
    assert info.requires_auth is False
    assert info.default_symbol == "SPY"
    assert set(info.supported_timeframes) == {"1d", "1h"}
    assert any("OHLCV-only" in limitation for limitation in info.limitations)


def test_yahoo_finance_provider_validates_curated_symbols_and_timeframes():
    provider = YahooFinanceProvider()

    assert provider.validate_symbol("spy") == "SPY"
    assert provider.validate_symbol("gc=f") == "GC=F"
    assert provider.validate_timeframe("1D") == "1d"

    with pytest.raises(ProviderValidationError):
        provider.validate_symbol("ABC")

    with pytest.raises(ProviderValidationError):
        provider.validate_timeframe("15m")
