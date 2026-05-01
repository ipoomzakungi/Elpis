from src.models.research_execution import ProxyResearchWorkflowConfig
from src.research_execution.preflight import preflight_proxy_ohlcv_assets
from tests.helpers.research_data import write_synthetic_research_features


def test_yahoo_proxy_labels_derivative_capabilities_as_unsupported(isolated_data_paths):
    feature_path = isolated_data_paths / "processed" / "spy_1d_features.parquet"
    write_synthetic_research_features(
        feature_path,
        symbol="SPY",
        rows=6,
        include_regime=False,
        include_open_interest=False,
        include_funding=False,
    )
    config = ProxyResearchWorkflowConfig(
        assets=["SPY"],
        provider="Yahoo",
        processed_feature_root=isolated_data_paths / "processed",
        required_capabilities=[
            "ohlcv",
            "open interest",
            "funding_rate",
            "gold options OI",
            "futures OI",
            "implied volatility",
            "XAUUSD spot execution",
        ],
    )

    result = preflight_proxy_ohlcv_assets(config)[0]

    assert result.status == "completed"
    assert result.source_identity == "yahoo_finance"
    assert result.unsupported_capabilities == [
        "open_interest",
        "funding",
        "gold_options_oi",
        "futures_oi",
        "iv",
        "xauusd_spot_execution",
    ]
    assert result.capability_snapshot["provider"] == "yahoo_finance"
    assert result.capability_snapshot["supports_ohlcv"] is True
    assert result.capability_snapshot["supports_open_interest"] is False
    assert result.capability_snapshot["supports_funding"] is False
    assert result.capability_snapshot["supports_gold_options_oi"] is False
    assert result.capability_snapshot["supports_futures_oi"] is False
    assert result.capability_snapshot["supports_iv"] is False
    assert result.capability_snapshot["supports_xauusd_spot_execution"] is False
    assert result.capability_snapshot["detected_ohlcv"] is True
    assert result.capability_snapshot["detected_open_interest"] is False
    assert any("OHLCV-only" in limitation for limitation in result.limitations)
    assert any("unsupported" in warning.lower() for warning in result.warnings)


def test_local_file_proxy_derives_capability_from_processed_columns(isolated_data_paths):
    feature_path = isolated_data_paths / "processed" / "custom_1d_features.parquet"
    write_synthetic_research_features(
        feature_path,
        symbol="CUSTOM",
        rows=6,
        include_regime=False,
        include_open_interest=True,
        include_funding=True,
    )
    config = ProxyResearchWorkflowConfig(
        assets=["CUSTOM"],
        provider="local_file",
        processed_feature_root=isolated_data_paths / "processed",
        required_capabilities=["ohlcv", "open_interest", "funding"],
    )

    result = preflight_proxy_ohlcv_assets(config)[0]

    assert result.status == "completed"
    assert result.unsupported_capabilities == []
    assert result.capability_snapshot["provider"] == "local_file"
    assert result.capability_snapshot["detected_ohlcv"] is True
    assert result.capability_snapshot["detected_open_interest"] is True
    assert result.capability_snapshot["detected_funding"] is True
