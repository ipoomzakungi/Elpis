import pytest

from src.data_sources.preflight import DataSourcePreflightService, resolve_processed_feature_path
from src.models.data_sources import (
    DataSourcePreflightRequest,
    DataSourceProviderType,
    DataSourceReadinessStatus,
    FirstEvidenceRunStatus,
)
from tests.helpers.research_data import write_synthetic_research_features
from tests.helpers.test_xau_data import write_sample_xau_options_csv


def test_processed_feature_path_resolution_stays_inside_processed_root(isolated_data_paths):
    processed_root = isolated_data_paths / "processed"

    resolved = resolve_processed_feature_path("BTCUSDT", "15m", processed_root)

    assert resolved == processed_root.resolve() / "btcusdt_15m_features.parquet"


def test_processed_feature_path_resolution_rejects_outside_root(isolated_data_paths):
    with pytest.raises(ValueError, match="inside data/processed"):
        resolve_processed_feature_path("BTCUSDT", "15m", isolated_data_paths / "outside")


def test_preflight_ready_crypto_and_xau_local_schema_detection(isolated_data_paths):
    processed_root = isolated_data_paths / "processed"
    raw_root = isolated_data_paths / "raw"
    write_synthetic_research_features(
        processed_root / "btcusdt_15m_features.parquet",
        symbol="BTCUSDT",
        rows=8,
    )
    options_path = raw_root / "xau" / "options.csv"
    options_path.parent.mkdir(parents=True, exist_ok=True)
    write_sample_xau_options_csv(options_path)
    request = DataSourcePreflightRequest(
        crypto_assets=["BTCUSDT"],
        proxy_assets=[],
        processed_feature_root=processed_root,
        xau_options_oi_file_path=options_path,
        research_only_acknowledged=True,
    )

    result = DataSourcePreflightService().run(request, environ={})

    assert result.status == FirstEvidenceRunStatus.COMPLETED
    assert result.crypto_results[0].status == DataSourceReadinessStatus.READY
    assert result.crypto_results[0].row_count == 8
    assert result.xau_result is not None
    assert result.xau_result.status == DataSourceReadinessStatus.READY
    assert result.xau_result.provider_type == DataSourceProviderType.LOCAL_FILE
    assert result.xau_result.row_count == 2


def test_preflight_invalid_xau_schema_returns_required_columns(isolated_data_paths):
    invalid_path = isolated_data_paths / "raw" / "xau" / "invalid.csv"
    invalid_path.parent.mkdir(parents=True, exist_ok=True)
    invalid_path.write_text("date,strike,option_type\n2026-05-01,2400,call\n", encoding="utf-8")
    request = DataSourcePreflightRequest(
        crypto_assets=[],
        proxy_assets=[],
        xau_options_oi_file_path=invalid_path,
        research_only_acknowledged=True,
    )

    result = DataSourcePreflightService().run(request, environ={})

    assert result.status == FirstEvidenceRunStatus.BLOCKED
    assert result.xau_result is not None
    assert result.xau_result.status == DataSourceReadinessStatus.BLOCKED
    assert result.xau_result.missing_data_actions
    action = result.xau_result.missing_data_actions[0]
    assert action.action_id == "xau-local-options-schema"
    assert "expiry" in action.required_columns
    assert "open_interest" in action.required_columns


def test_preflight_missing_crypto_and_proxy_actions_are_actionable(isolated_data_paths):
    request = DataSourcePreflightRequest(
        crypto_assets=["ETHUSDT"],
        proxy_assets=["SPY"],
        processed_feature_root=isolated_data_paths / "processed",
        xau_options_oi_file_path=isolated_data_paths / "raw" / "xau" / "missing.csv",
        requested_capabilities=["ohlcv", "open_interest", "funding", "iv"],
        research_only_acknowledged=True,
    )

    result = DataSourcePreflightService().run(request, environ={})

    assert result.status == FirstEvidenceRunStatus.BLOCKED
    crypto = result.crypto_results[0]
    proxy = result.proxy_results[0]
    assert crypto.status == DataSourceReadinessStatus.BLOCKED
    assert proxy.status == DataSourceReadinessStatus.BLOCKED
    assert any(
        "public Binance" in item
        for action in crypto.missing_data_actions
        for item in action.instructions
    )
    assert any(
        "Yahoo Finance" in item
        for action in proxy.missing_data_actions
        for item in action.instructions
    )
    assert proxy.unsupported_capabilities == ["open_interest", "funding", "iv"]
