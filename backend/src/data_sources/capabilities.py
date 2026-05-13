"""Provider capability matrix for research data-source onboarding."""

from collections.abc import Iterable

from src.free_derivatives.processing import (
    ARTIFACT_SCOPE_LIMITATION,
    CFTC_CATEGORY_LIMITATION,
    CFTC_WEEKLY_POSITIONING_LIMITATION,
    DERIBIT_CRYPTO_OPTIONS_LIMITATION,
    DERIBIT_UNSUPPORTED_UNDERLYING_LIMITATION,
    GVZ_NOT_STRIKE_LEVEL_OI_LIMITATION,
    GVZ_PROXY_LIMITATION,
    PUBLIC_ONLY_LIMITATION,
)
from src.models.data_sources import (
    DataSourceCapability,
    DataSourceLocalFileCapabilityDetection,
    DataSourceProviderType,
    DataSourceTier,
)

YAHOO_UNSUPPORTED_CAPABILITIES = [
    "crypto_open_interest",
    "open_interest",
    "funding",
    "gold_options_oi",
    "futures_oi",
    "iv",
    "implied_volatility",
    "xauusd_spot_execution",
]

FORBIDDEN_CAPABILITIES = [
    "live_trading",
    "paper_trading",
    "shadow_trading",
    "private_trading_keys",
    "broker_integration",
    "real_order_execution",
    "wallet_private_keys",
]

OHLCV_REQUIRED_COLUMNS = {"open", "high", "low", "close", "volume"}
XAU_OPTIONS_OI_REQUIRED_COLUMNS = {"expiry", "strike", "option_type", "open_interest"}
XAU_OPTIONS_OI_OPTIONAL_COLUMNS = [
    "oi_change",
    "volume",
    "implied_volatility",
    "underlying_futures_price",
    "xauusd_spot_price",
    "delta",
    "gamma",
]


def capability_matrix() -> list[DataSourceCapability]:
    """Return the canonical v0 data-source capability matrix."""

    return [
        DataSourceCapability(
            provider_type=DataSourceProviderType.BINANCE_PUBLIC,
            display_name="Binance Public",
            tier=DataSourceTier.TIER_0_PUBLIC_LOCAL,
            supports=[
                "crypto_ohlcv",
                "limited_public_open_interest",
                "public_funding",
            ],
            unsupported=["private_account_data", "execution"],
            requires_key=False,
            requires_local_file=False,
            is_optional=False,
            limitations=[
                "Uses public market data endpoints only.",
                "Official historical OI can be limited; deeper history may require vendor data.",
                "No private account data, broker integration, or order execution.",
            ],
        ),
        DataSourceCapability(
            provider_type=DataSourceProviderType.YAHOO_FINANCE,
            display_name="Yahoo Finance",
            tier=DataSourceTier.TIER_0_PUBLIC_LOCAL,
            supports=["ohlcv_proxy"],
            unsupported=YAHOO_UNSUPPORTED_CAPABILITIES,
            requires_key=False,
            requires_local_file=False,
            is_optional=False,
            limitations=[
                "Yahoo Finance is OHLCV/proxy-only for this research platform.",
                (
                    "It is not a source for crypto OI, funding, gold options OI, "
                    "futures OI, IV, or XAUUSD execution data."
                ),
            ],
        ),
        DataSourceCapability(
            provider_type=DataSourceProviderType.LOCAL_FILE,
            display_name="Local CSV/Parquet",
            tier=DataSourceTier.TIER_0_PUBLIC_LOCAL,
            supports=["schema_dependent_ohlcv", "schema_dependent_xau_options_oi"],
            unsupported=["execution", "private_account_data"],
            requires_key=False,
            requires_local_file=True,
            is_optional=False,
            limitations=[
                "Local file capabilities depend on required columns and parseable timestamps.",
                "Generated and imported data files must remain ignored and untracked.",
            ],
        ),
        DataSourceCapability(
            provider_type=DataSourceProviderType.CFTC_COT,
            display_name="CFTC COT Gold Positioning",
            tier=DataSourceTier.TIER_0_PUBLIC_LOCAL,
            supports=[
                "weekly_gold_positioning",
                "futures_only_cot",
                "futures_and_options_combined_cot",
            ],
            unsupported=["strike_level_options_oi", "intraday_wall_data", "execution"],
            requires_key=False,
            requires_local_file=False,
            is_optional=False,
            limitations=[
                CFTC_WEEKLY_POSITIONING_LIMITATION,
                CFTC_CATEGORY_LIMITATION,
                PUBLIC_ONLY_LIMITATION,
                ARTIFACT_SCOPE_LIMITATION,
            ],
        ),
        DataSourceCapability(
            provider_type=DataSourceProviderType.GVZ,
            display_name="GVZ Gold Volatility Proxy",
            tier=DataSourceTier.TIER_0_PUBLIC_LOCAL,
            supports=["gold_volatility_proxy", "daily_gvz_close"],
            unsupported=[
                "cme_gold_options_iv_surface",
                "strike_level_options_oi",
                "execution",
            ],
            requires_key=False,
            requires_local_file=False,
            is_optional=False,
            limitations=[
                GVZ_PROXY_LIMITATION,
                GVZ_NOT_STRIKE_LEVEL_OI_LIMITATION,
                PUBLIC_ONLY_LIMITATION,
                ARTIFACT_SCOPE_LIMITATION,
            ],
        ),
        DataSourceCapability(
            provider_type=DataSourceProviderType.DERIBIT_PUBLIC_OPTIONS,
            display_name="Deribit Public Options",
            tier=DataSourceTier.TIER_0_PUBLIC_LOCAL,
            supports=[
                "crypto_options_open_interest",
                "crypto_options_iv",
                "public_option_snapshots",
            ],
            unsupported=[
                "gold_options_oi",
                "xau_options_oi",
                "private_account_data",
                "execution",
            ],
            requires_key=False,
            requires_local_file=False,
            is_optional=False,
            limitations=[
                DERIBIT_CRYPTO_OPTIONS_LIMITATION,
                DERIBIT_UNSUPPORTED_UNDERLYING_LIMITATION,
                PUBLIC_ONLY_LIMITATION,
                ARTIFACT_SCOPE_LIMITATION,
            ],
        ),
        DataSourceCapability(
            provider_type=DataSourceProviderType.KAIKO_OPTIONAL,
            display_name="Kaiko",
            tier=DataSourceTier.TIER_1_OPTIONAL_PAID_RESEARCH,
            supports=["normalized_crypto_derivatives", "open_interest_research"],
            unsupported=["execution", "private_account_data"],
            requires_key=True,
            requires_local_file=False,
            is_optional=True,
            limitations=[
                "Optional paid research source; absent key does not block MVP.",
            ],
        ),
        DataSourceCapability(
            provider_type=DataSourceProviderType.TARDIS_OPTIONAL,
            display_name="Tardis",
            tier=DataSourceTier.TIER_1_OPTIONAL_PAID_RESEARCH,
            supports=["native_exchange_archive", "replay_research_data"],
            unsupported=["execution", "private_account_data"],
            requires_key=True,
            requires_local_file=False,
            is_optional=True,
            limitations=[
                "Optional paid research archive; absent key does not block MVP.",
            ],
        ),
        DataSourceCapability(
            provider_type=DataSourceProviderType.COINGLASS_OPTIONAL,
            display_name="CoinGlass",
            tier=DataSourceTier.TIER_1_OPTIONAL_PAID_RESEARCH,
            supports=["aggregate_derivatives_overlay"],
            unsupported=["execution", "private_account_data"],
            requires_key=True,
            requires_local_file=False,
            is_optional=True,
            limitations=[
                "Optional aggregate/dashboard overlay source; absent key does not block MVP.",
            ],
        ),
        DataSourceCapability(
            provider_type=DataSourceProviderType.CRYPTOQUANT_OPTIONAL,
            display_name="CryptoQuant",
            tier=DataSourceTier.TIER_1_OPTIONAL_PAID_RESEARCH,
            supports=["aggregate_research_overlay"],
            unsupported=["execution", "private_account_data"],
            requires_key=True,
            requires_local_file=False,
            is_optional=True,
            limitations=[
                (
                    "Optional aggregate/on-chain/dashboard overlay source; absent key "
                    "does not block MVP."
                ),
            ],
        ),
        DataSourceCapability(
            provider_type=DataSourceProviderType.CME_QUIKSTRIKE_LOCAL_OR_OPTIONAL,
            display_name="CME/QuikStrike Gold Options",
            tier=DataSourceTier.TIER_1_OPTIONAL_PAID_RESEARCH,
            supports=["local_gold_options_oi_import", "optional_gold_options_vendor_access"],
            unsupported=["yahoo_gold_options_oi", "xauusd_spot_execution", "execution"],
            requires_key=True,
            requires_local_file=True,
            is_optional=True,
            limitations=[
                "Local CSV/Parquet import is the MVP path for gold options OI.",
                (
                    "Yahoo GC=F and GLD are OHLCV proxies only, not options OI, "
                    "futures OI, IV, or XAUUSD execution data."
                ),
            ],
        ),
        DataSourceCapability(
            provider_type=DataSourceProviderType.FORBIDDEN_PRIVATE_TRADING,
            display_name="Private Trading Credentials",
            tier=DataSourceTier.TIER_2_FORBIDDEN_V0,
            supports=[],
            unsupported=FORBIDDEN_CAPABILITIES,
            requires_key=False,
            requires_local_file=False,
            is_optional=False,
            limitations=[
                "Private trading, broker, wallet, and execution credentials are forbidden in v0.",
            ],
            forbidden_reason=(
                "v0 is research-only and cannot onboard private trading, broker, wallet, "
                "or execution credentials."
            ),
        ),
    ]


def get_capability(provider_type: DataSourceProviderType | str) -> DataSourceCapability:
    normalized = DataSourceProviderType(provider_type)
    for capability in capability_matrix():
        if capability.provider_type == normalized:
            return capability
    raise ValueError(f"Unknown data-source provider type: {provider_type}")


def unsupported_capabilities_for_provider(
    provider_type: DataSourceProviderType | str,
    requested_capabilities: Iterable[str],
) -> list[str]:
    capability = get_capability(provider_type)
    unsupported_aliases = {_normalize_capability(value) for value in capability.unsupported}
    unsupported: list[str] = []
    for requested in requested_capabilities:
        normalized = _normalize_capability(requested)
        if normalized in unsupported_aliases and normalized not in unsupported:
            unsupported.append(normalized)
    return unsupported


def detect_local_file_capabilities(
    columns: Iterable[str],
) -> DataSourceLocalFileCapabilityDetection:
    available = sorted({_normalize_column(column) for column in columns if column.strip()})
    available_set = set(available)
    timestamp_present = bool({"timestamp", "date"} & available_set)
    missing_ohlcv = sorted(
        column for column in OHLCV_REQUIRED_COLUMNS if column not in available_set
    )
    if not timestamp_present:
        missing_ohlcv.insert(0, "date_or_timestamp")

    missing_xau = sorted(
        column for column in XAU_OPTIONS_OI_REQUIRED_COLUMNS if column not in available_set
    )
    if not timestamp_present:
        missing_xau.insert(0, "date_or_timestamp")

    supports_ohlcv = not missing_ohlcv
    supports_xau = not missing_xau
    detected: list[str] = []
    if supports_ohlcv:
        detected.append("ohlcv")
    if supports_xau:
        detected.append("gold_options_oi")

    return DataSourceLocalFileCapabilityDetection(
        available_columns=available,
        detected_capabilities=detected,
        missing_ohlcv_columns=missing_ohlcv,
        missing_xau_options_oi_columns=missing_xau,
        supports_ohlcv=supports_ohlcv,
        supports_xau_options_oi=supports_xau,
    )


def _normalize_capability(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "crypto_oi": "crypto_open_interest",
        "oi": "open_interest",
        "openinterest": "open_interest",
        "funding_rate": "funding",
        "implied_volatility": "implied_volatility",
        "xau_execution": "xauusd_spot_execution",
        "xauusd_execution": "xauusd_spot_execution",
    }
    compact = "".join(character for character in normalized if character.isalnum())
    return aliases.get(normalized) or aliases.get(compact) or normalized


def _normalize_column(value: str) -> str:
    return value.strip().lower().replace(" ", "_").replace("-", "_")
