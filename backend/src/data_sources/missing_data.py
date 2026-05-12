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


def cftc_cot_source_action() -> DataSourceMissingDataAction:
    return DataSourceMissingDataAction(
        action_id="free-derivatives-cftc-cot-source",
        workflow_type=DataSourceWorkflowType.FREE_DERIVATIVES,
        provider_type=DataSourceProviderType.CFTC_COT,
        asset="XAU",
        severity=MissingDataSeverity.INFORMATIONAL,
        title="Collect or import CFTC COT gold positioning",
        instructions=[
            "Use official public CFTC COT historical files or a local fixture/import file.",
            "Filter gold/COMEX rows and preserve futures-only versus combined report labels.",
            "Do not treat CFTC COT as strike-level XAU options OI or intraday wall data.",
        ],
        blocking=False,
    )


def gvz_source_action() -> DataSourceMissingDataAction:
    return DataSourceMissingDataAction(
        action_id="free-derivatives-gvz-source",
        workflow_type=DataSourceWorkflowType.FREE_DERIVATIVES,
        provider_type=DataSourceProviderType.GVZ,
        asset="XAU",
        severity=MissingDataSeverity.INFORMATIONAL,
        title="Collect or import GVZ daily close proxy volatility",
        instructions=[
            "Use a public GVZCLS daily close path or a local CSV fixture/import file.",
            "Label GVZ as a GLD-options-derived volatility proxy.",
            "Do not present GVZ as a CME gold options implied-volatility surface.",
        ],
        blocking=False,
    )


def deribit_public_options_action() -> DataSourceMissingDataAction:
    return DataSourceMissingDataAction(
        action_id="free-derivatives-deribit-public-options",
        workflow_type=DataSourceWorkflowType.FREE_DERIVATIVES,
        provider_type=DataSourceProviderType.DERIBIT_PUBLIC_OPTIONS,
        asset=None,
        severity=MissingDataSeverity.INFORMATIONAL,
        title="Collect Deribit public crypto options snapshots",
        instructions=[
            "Use Deribit public market-data endpoints or local mocked fixture responses.",
            "Normalize crypto options IV and open interest fields where public data is available.",
            "Do not use private account, order, wallet, broker, or paid vendor credentials.",
        ],
        blocking=False,
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
        cftc_cot_source_action(),
        gvz_source_action(),
        deribit_public_options_action(),
        xau_options_oi_schema_action(),
    ]
