"""Missing-data instruction builders for data-source onboarding."""

from pathlib import Path

from src.data_sources.capabilities import XAU_OPTIONS_OI_OPTIONAL_COLUMNS
from src.models.data_sources import (
    DataSourceMissingDataAction,
    DataSourceProviderType,
    DataSourceWorkflowType,
    MissingDataSeverity,
)

XAU_OPTIONS_OI_REQUIRED_COLUMNS = [
    "date_or_timestamp",
    "expiry",
    "strike",
    "option_type",
    "open_interest",
]


def crypto_processed_features_action(
    symbol: str = "BTCUSDT",
    timeframe: str = "15m",
) -> DataSourceMissingDataAction:
    normalized_symbol = symbol.strip().upper()
    normalized_timeframe = timeframe.strip()
    return DataSourceMissingDataAction(
        action_id=f"crypto-{normalized_symbol.lower()}-{normalized_timeframe}-processed-features",
        workflow_type=DataSourceWorkflowType.CRYPTO_MULTI_ASSET,
        provider_type=DataSourceProviderType.BINANCE_PUBLIC,
        asset=normalized_symbol,
        severity=MissingDataSeverity.BLOCKING,
        title=f"Create {normalized_symbol} processed features",
        instructions=[
            f"Download {normalized_symbol} {normalized_timeframe} public Binance research data.",
            "Run feature processing to create processed features before evidence execution.",
            (
                "Use public market and public derivatives endpoints only; do not configure "
                "private trading keys."
            ),
        ],
        blocking=True,
    )


def proxy_ohlcv_action(symbol: str = "SPY", timeframe: str = "1d") -> DataSourceMissingDataAction:
    normalized_symbol = symbol.strip().upper()
    normalized_timeframe = timeframe.strip()
    return DataSourceMissingDataAction(
        action_id=(
            f"proxy-{normalized_symbol.lower().replace('=', '-')}-"
            f"{normalized_timeframe}-ohlcv"
        ),
        workflow_type=DataSourceWorkflowType.PROXY_OHLCV,
        provider_type=DataSourceProviderType.YAHOO_FINANCE,
        asset=normalized_symbol,
        severity=MissingDataSeverity.BLOCKING,
        title=f"Create {normalized_symbol} OHLCV proxy features",
        instructions=[
            (
                f"Download or import Yahoo Finance OHLCV data for {normalized_symbol} "
                f"{normalized_timeframe}."
            ),
            "Run feature processing as an OHLCV-only proxy asset before evidence execution.",
            (
                "Do not treat Yahoo Finance as a source for crypto OI, funding, "
                "gold options OI, futures OI, IV, or XAUUSD execution data."
            ),
        ],
        blocking=True,
    )


def xau_options_oi_schema_action(
    file_path: str | Path | None = None,
) -> DataSourceMissingDataAction:
    expected_path = Path(file_path).as_posix() if file_path else "data/raw/xau/options_oi.csv"
    return DataSourceMissingDataAction(
        action_id="xau-local-options-schema",
        workflow_type=DataSourceWorkflowType.XAU_VOL_OI,
        provider_type=DataSourceProviderType.LOCAL_FILE,
        asset="XAU",
        severity=MissingDataSeverity.BLOCKING,
        title="Provide local XAU options OI file",
        instructions=[
            "Import a local CSV or Parquet gold options OI file.",
            "Required columns: date or timestamp, expiry, strike, option_type, and open_interest.",
            f"Expected local options OI file: {expected_path}",
            "Yahoo GC=F and GLD are OHLCV proxies only and are not gold options OI sources.",
        ],
        required_columns=XAU_OPTIONS_OI_REQUIRED_COLUMNS,
        optional_columns=XAU_OPTIONS_OI_OPTIONAL_COLUMNS,
        blocking=True,
    )


def optional_vendor_key_action(
    provider_type: DataSourceProviderType,
    env_var_name: str,
) -> DataSourceMissingDataAction:
    provider_label = provider_type.value.replace("_optional", "").replace("_", " ").title()
    return DataSourceMissingDataAction(
        action_id=f"configure-{provider_type.value}",
        workflow_type=DataSourceWorkflowType.OPTIONAL_VENDOR,
        provider_type=provider_type,
        asset=None,
        severity=MissingDataSeverity.OPTIONAL,
        title=f"Configure {provider_label} research key if available",
        instructions=[
            (
                f"Set {env_var_name} in a local .env file if this optional paid "
                "research source is available."
            ),
            "Do not commit .env files or secret values.",
            "This optional provider is not required for the public/local MVP first evidence run.",
        ],
        blocking=False,
    )


def default_missing_data_actions() -> list[DataSourceMissingDataAction]:
    return [
        crypto_processed_features_action("BTCUSDT", "15m"),
        crypto_processed_features_action("ETHUSDT", "15m"),
        crypto_processed_features_action("SOLUSDT", "15m"),
        proxy_ohlcv_action("SPY", "1d"),
        proxy_ohlcv_action("QQQ", "1d"),
        proxy_ohlcv_action("GLD", "1d"),
        proxy_ohlcv_action("GC=F", "1d"),
        xau_options_oi_schema_action(),
    ]
