import pytest

from src.models.research import (
    ResearchAssetClass,
    ResearchAssetConfig,
    ResearchFeatureGroup,
    ResearchPreflightStatus,
)
from src.research.preflight import preflight_research_asset
from tests.helpers.research_data import write_synthetic_research_features


def test_preflight_ready_asset_reads_existing_processed_features(isolated_data_paths):
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
    assert result.row_count == 12
    assert result.first_timestamp is not None
    assert result.last_timestamp is not None
    assert result.capability_snapshot.detected_ohlcv is True
    assert result.capability_snapshot.detected_regime is True
    assert result.capability_snapshot.detected_open_interest is True
    assert result.capability_snapshot.detected_funding_rate is True
    assert result.missing_columns == []
    assert result.instructions == []


def test_preflight_missing_default_path_returns_actionable_instructions(isolated_data_paths):
    asset = ResearchAssetConfig(
        symbol="SPY",
        provider="yahoo_finance",
        asset_class=ResearchAssetClass.EQUITY_PROXY,
        timeframe="1d",
    )

    result = preflight_research_asset(asset)

    assert result.status == ResearchPreflightStatus.MISSING_DATA
    assert result.row_count is None
    assert result.feature_path.endswith("spy_1d_features.parquet")
    assert any("download" in instruction.lower() for instruction in result.instructions)
    assert any("process" in instruction.lower() for instruction in result.instructions)
    assert any("SPY" in instruction for instruction in result.instructions)


def test_preflight_rejects_feature_paths_outside_processed_directory(isolated_data_paths):
    outside_path = isolated_data_paths / "outside_features.parquet"
    write_synthetic_research_features(outside_path)
    asset = ResearchAssetConfig(
        symbol="BTCUSDT",
        provider="binance",
        asset_class=ResearchAssetClass.CRYPTO,
        timeframe="15m",
        feature_path=outside_path,
    )

    with pytest.raises(ValueError, match="processed feature path must stay inside"):
        preflight_research_asset(asset)


def test_preflight_unreadable_processed_file_is_incomplete(isolated_data_paths):
    bad_path = isolated_data_paths / "processed" / "btcusdt_15m_features.parquet"
    bad_path.parent.mkdir(parents=True, exist_ok=True)
    bad_path.write_text("not parquet", encoding="utf-8")
    asset = ResearchAssetConfig(
        symbol="BTCUSDT",
        provider="binance",
        asset_class=ResearchAssetClass.CRYPTO,
        timeframe="15m",
        feature_path=bad_path,
    )

    result = preflight_research_asset(asset)

    assert result.status == ResearchPreflightStatus.INCOMPLETE_FEATURES
    assert any("could not be read" in warning.lower() for warning in result.warnings)
    assert any("reprocess" in instruction.lower() for instruction in result.instructions)

