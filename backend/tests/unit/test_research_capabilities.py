from src.models.research import (
    ResearchAssetClass,
    ResearchAssetConfig,
    ResearchFeatureGroup,
    ResearchPreflightStatus,
)
from src.research.preflight import preflight_research_asset
from tests.helpers.research_data import write_synthetic_research_features


def test_binance_capabilities_include_oi_funding_and_volume_when_columns_exist(
    isolated_data_paths,
):
    feature_path = isolated_data_paths / "processed" / "btcusdt_15m_features.parquet"
    write_synthetic_research_features(feature_path, rows=12)
    asset = ResearchAssetConfig(
        symbol="BTCUSDT",
        provider="binance",
        asset_class=ResearchAssetClass.CRYPTO,
        timeframe="15m",
        feature_path=feature_path,
        required_feature_groups=[
            ResearchFeatureGroup.OHLCV,
            ResearchFeatureGroup.REGIME,
            ResearchFeatureGroup.OPEN_INTEREST,
            ResearchFeatureGroup.FUNDING,
            ResearchFeatureGroup.VOLUME_CONFIRMATION,
        ],
    )

    result = preflight_research_asset(asset)

    assert result.status == ResearchPreflightStatus.READY
    assert result.capability_snapshot.supports_ohlcv is True
    assert result.capability_snapshot.supports_open_interest is True
    assert result.capability_snapshot.supports_funding_rate is True
    assert result.capability_snapshot.detected_ohlcv is True
    assert result.capability_snapshot.detected_regime is True
    assert result.capability_snapshot.detected_open_interest is True
    assert result.capability_snapshot.detected_funding_rate is True


def test_yahoo_requested_oi_or_funding_is_labeled_unsupported(isolated_data_paths):
    feature_path = isolated_data_paths / "processed" / "spy_1d_features.parquet"
    write_synthetic_research_features(
        feature_path,
        symbol="SPY",
        rows=12,
        include_open_interest=False,
        include_funding=False,
    )
    asset = ResearchAssetConfig(
        symbol="SPY",
        provider="yahoo_finance",
        asset_class=ResearchAssetClass.EQUITY_PROXY,
        timeframe="1d",
        feature_path=feature_path,
        required_feature_groups=[
            ResearchFeatureGroup.OHLCV,
            ResearchFeatureGroup.REGIME,
            ResearchFeatureGroup.OPEN_INTEREST,
            ResearchFeatureGroup.FUNDING,
        ],
    )

    result = preflight_research_asset(asset)

    assert result.status == ResearchPreflightStatus.UNSUPPORTED_CAPABILITY
    assert result.capability_snapshot.supports_open_interest is False
    assert result.capability_snapshot.supports_funding_rate is False
    assert result.capability_snapshot.detected_open_interest is False
    assert result.capability_snapshot.detected_funding_rate is False
    assert any("ohlcv-only" in warning.lower() for warning in result.warnings)
    assert any("unsupported" in instruction.lower() for instruction in result.instructions)


def test_gold_proxy_assets_include_source_limitation_notes(isolated_data_paths):
    feature_path = isolated_data_paths / "processed" / "gc=f_1d_features.parquet"
    write_synthetic_research_features(
        feature_path,
        symbol="GC=F",
        rows=12,
        include_open_interest=False,
        include_funding=False,
    )
    asset = ResearchAssetConfig(
        symbol="GC=F",
        provider="yahoo_finance",
        asset_class=ResearchAssetClass.GOLD_PROXY,
        timeframe="1d",
        feature_path=feature_path,
    )

    result = preflight_research_asset(asset)

    assert result.status == ResearchPreflightStatus.READY
    notes = " ".join(result.capability_snapshot.limitation_notes)
    assert "OHLCV proxies only" in notes
    assert "gold options OI" in notes
    assert "XAU/USD spot execution" in notes


def test_local_file_capabilities_are_derived_from_available_columns(isolated_data_paths):
    feature_path = isolated_data_paths / "processed" / "local_asset_1d_features.parquet"
    write_synthetic_research_features(
        feature_path,
        symbol="LOCAL_ASSET",
        rows=12,
        include_open_interest=True,
        include_funding=False,
    )
    asset = ResearchAssetConfig(
        symbol="LOCAL_ASSET",
        provider="local_file",
        asset_class=ResearchAssetClass.LOCAL_DATASET,
        timeframe="1d",
        feature_path=feature_path,
    )

    result = preflight_research_asset(asset)

    assert result.status == ResearchPreflightStatus.READY
    assert result.capability_snapshot.supports_ohlcv is True
    assert result.capability_snapshot.supports_open_interest is True
    assert result.capability_snapshot.supports_funding_rate is False
    assert result.capability_snapshot.detected_open_interest is True
    assert result.capability_snapshot.detected_funding_rate is False
