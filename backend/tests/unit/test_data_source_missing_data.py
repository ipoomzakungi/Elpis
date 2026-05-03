from src.data_sources.missing_data import (
    crypto_processed_features_action,
    default_missing_data_actions,
    optional_vendor_key_action,
    proxy_ohlcv_action,
    xau_options_oi_schema_action,
)
from src.models.data_sources import (
    DataSourceProviderType,
    DataSourceWorkflowType,
    MissingDataSeverity,
)


def test_crypto_missing_data_action_points_to_public_binance_processing():
    action = crypto_processed_features_action("BTCUSDT", "15m")

    assert action.workflow_type == DataSourceWorkflowType.CRYPTO_MULTI_ASSET
    assert action.provider_type == DataSourceProviderType.BINANCE_PUBLIC
    assert action.asset == "BTCUSDT"
    assert action.blocking is True
    assert action.severity == MissingDataSeverity.BLOCKING
    assert any("public Binance" in instruction for instruction in action.instructions)
    assert any(
        "do not configure private trading keys" in instruction.lower()
        for instruction in action.instructions
    )


def test_proxy_missing_data_action_preserves_yahoo_ohlcv_only_limits():
    action = proxy_ohlcv_action("GC=F", "1d")

    assert action.workflow_type == DataSourceWorkflowType.PROXY_OHLCV
    assert action.provider_type == DataSourceProviderType.YAHOO_FINANCE
    assert action.asset == "GC=F"
    assert any("OHLCV-only" in instruction for instruction in action.instructions)
    assert any("gold options OI" in instruction for instruction in action.instructions)


def test_xau_options_oi_schema_action_lists_required_and_optional_columns():
    action = xau_options_oi_schema_action("data/raw/xau/options.csv")

    assert action.provider_type == DataSourceProviderType.LOCAL_FILE
    assert action.workflow_type == DataSourceWorkflowType.XAU_VOL_OI
    assert action.required_columns == [
        "date_or_timestamp",
        "expiry",
        "strike",
        "option_type",
        "open_interest",
    ]
    assert "implied_volatility" in action.optional_columns
    assert any("Yahoo GC=F and GLD are OHLCV proxies only" in item for item in action.instructions)


def test_optional_vendor_action_is_non_blocking_and_hides_values():
    action = optional_vendor_key_action(DataSourceProviderType.KAIKO_OPTIONAL, "KAIKO_API_KEY")
    payload = action.model_dump_json()

    assert action.severity == MissingDataSeverity.OPTIONAL
    assert action.blocking is False
    assert "KAIKO_API_KEY" in payload
    assert "secret-value" not in payload
    assert any("not required" in instruction for instruction in action.instructions)


def test_default_missing_data_actions_cover_crypto_proxy_and_xau():
    actions = default_missing_data_actions()
    workflows = {action.workflow_type for action in actions}

    assert DataSourceWorkflowType.CRYPTO_MULTI_ASSET in workflows
    assert DataSourceWorkflowType.PROXY_OHLCV in workflows
    assert DataSourceWorkflowType.XAU_VOL_OI in workflows
