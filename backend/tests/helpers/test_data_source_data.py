"""Shared fixtures for data-source onboarding tests."""

from src.models.data_sources import DataSourceProviderType


def ohlcv_columns() -> list[str]:
    return ["timestamp", "open", "high", "low", "close", "volume"]


def xau_options_oi_columns() -> list[str]:
    return ["date", "expiry", "strike", "option_type", "open_interest"]


def optional_vendor_environment(secret_value: str = "super-secret-value") -> dict[str, str]:
    return {
        "KAIKO_API_KEY": secret_value,
        "TARDIS_API_KEY": "",
    }


def find_provider(payload: list, provider_type: DataSourceProviderType):
    for item in payload:
        if item.provider_type == provider_type:
            return item
    raise AssertionError(f"provider not found: {provider_type}")
