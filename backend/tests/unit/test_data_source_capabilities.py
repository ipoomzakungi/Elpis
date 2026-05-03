from src.data_sources.capabilities import (
    YAHOO_UNSUPPORTED_CAPABILITIES,
    capability_matrix,
    detect_local_file_capabilities,
    get_capability,
    unsupported_capabilities_for_provider,
)
from src.models.data_sources import DataSourceProviderType, DataSourceTier
from tests.helpers.test_data_source_data import ohlcv_columns, xau_options_oi_columns


def test_binance_public_capability_matrix_is_public_research_only():
    capability = get_capability(DataSourceProviderType.BINANCE_PUBLIC)

    assert capability.tier == DataSourceTier.TIER_0_PUBLIC_LOCAL
    assert capability.requires_key is False
    assert capability.is_optional is False
    assert "crypto_ohlcv" in capability.supports
    assert "limited_public_open_interest" in capability.supports
    assert "public_funding" in capability.supports
    assert "execution" in capability.unsupported
    assert any("deeper history" in note.lower() for note in capability.limitations)


def test_yahoo_finance_is_ohlcv_only_with_derivatives_limitations():
    capability = get_capability(DataSourceProviderType.YAHOO_FINANCE)

    assert capability.supports == ["ohlcv_proxy"]
    for unsupported in YAHOO_UNSUPPORTED_CAPABILITIES:
        assert unsupported in capability.unsupported
    assert any("ohlcv/proxy-only" in note.lower() for note in capability.limitations)
    assert unsupported_capabilities_for_provider(
        DataSourceProviderType.YAHOO_FINANCE,
        ["open_interest", "funding", "iv", "xauusd_spot_execution"],
    ) == ["open_interest", "funding", "iv", "xauusd_spot_execution"]


def test_capability_matrix_includes_optional_and_forbidden_sources():
    provider_types = {row.provider_type for row in capability_matrix()}

    assert DataSourceProviderType.KAIKO_OPTIONAL in provider_types
    assert DataSourceProviderType.TARDIS_OPTIONAL in provider_types
    assert DataSourceProviderType.COINGLASS_OPTIONAL in provider_types
    assert DataSourceProviderType.CRYPTOQUANT_OPTIONAL in provider_types
    assert DataSourceProviderType.CME_QUIKSTRIKE_LOCAL_OR_OPTIONAL in provider_types
    assert DataSourceProviderType.FORBIDDEN_PRIVATE_TRADING in provider_types


def test_local_file_schema_detection_for_ohlcv_and_xau_options_oi():
    ohlcv = detect_local_file_capabilities(ohlcv_columns())
    xau = detect_local_file_capabilities(xau_options_oi_columns())
    incomplete = detect_local_file_capabilities(["date", "expiry", "strike", "option_type"])

    assert ohlcv.supports_ohlcv is True
    assert "ohlcv" in ohlcv.detected_capabilities
    assert xau.supports_xau_options_oi is True
    assert "gold_options_oi" in xau.detected_capabilities
    assert incomplete.supports_xau_options_oi is False
    assert "open_interest" in incomplete.missing_xau_options_oi_columns
