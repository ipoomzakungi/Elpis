from src.models.research_execution import (
    CryptoResearchWorkflowConfig,
    ProxyResearchWorkflowConfig,
    ResearchExecutionWorkflowStatus,
    XauVolOiWorkflowConfig,
)
from src.research_execution.preflight import (
    preflight_crypto_processed_features,
    preflight_proxy_ohlcv_assets,
    preflight_xau_options_file,
)
from tests.helpers.research_data import write_synthetic_research_features


def test_crypto_preflight_ready_asset_reads_processed_features(isolated_data_paths):
    feature_path = isolated_data_paths / "processed" / "btcusdt_15m_features.parquet"
    write_synthetic_research_features(feature_path, rows=8)
    config = CryptoResearchWorkflowConfig(
        primary_assets=["BTCUSDT"],
        processed_feature_root=isolated_data_paths / "processed",
    )

    result = preflight_crypto_processed_features(config)[0]

    assert result.workflow_type == "crypto_multi_asset"
    assert result.asset == "BTCUSDT"
    assert result.status == ResearchExecutionWorkflowStatus.COMPLETED
    assert result.ready is True
    assert result.row_count == 8
    assert result.date_start is not None
    assert result.date_end is not None
    assert result.missing_data_actions == []
    assert result.unsupported_capabilities == []


def test_crypto_preflight_missing_features_returns_download_and_process_instructions(
    isolated_data_paths,
):
    config = CryptoResearchWorkflowConfig(
        primary_assets=["ETHUSDT"],
        processed_feature_root=isolated_data_paths / "processed",
    )

    result = preflight_crypto_processed_features(config)[0]

    assert result.status == ResearchExecutionWorkflowStatus.BLOCKED
    assert result.ready is False
    assert result.row_count is None
    assert any("download" in instruction.lower() for instruction in result.missing_data_actions)
    assert any("process" in instruction.lower() for instruction in result.missing_data_actions)
    assert any("ETHUSDT" in instruction for instruction in result.missing_data_actions)


def test_crypto_preflight_rejects_processed_path_outside_processed_root(isolated_data_paths):
    outside_root = isolated_data_paths / "outside"
    config = CryptoResearchWorkflowConfig(
        primary_assets=["BTCUSDT"],
        processed_feature_root=outside_root,
    )

    result = preflight_crypto_processed_features(config)[0]

    assert result.status == ResearchExecutionWorkflowStatus.BLOCKED
    assert any("inside data/processed" in action for action in result.missing_data_actions)


def test_proxy_preflight_labels_yahoo_unsupported_capabilities(isolated_data_paths):
    feature_path = isolated_data_paths / "processed" / "spy_1d_features.parquet"
    write_synthetic_research_features(
        feature_path,
        symbol="SPY",
        rows=5,
        include_regime=False,
        include_open_interest=False,
        include_funding=False,
    )
    config = ProxyResearchWorkflowConfig(
        assets=["SPY"],
        required_capabilities=["ohlcv", "open_interest", "funding", "iv"],
        processed_feature_root=isolated_data_paths / "processed",
    )

    result = preflight_proxy_ohlcv_assets(config)[0]

    assert result.status == ResearchExecutionWorkflowStatus.COMPLETED
    assert result.ready is True
    assert result.unsupported_capabilities == ["open_interest", "funding", "iv"]
    assert any("OHLCV-only" in limitation for limitation in result.limitations)
    assert any("unsupported" in warning.lower() for warning in result.warnings)


def test_proxy_preflight_missing_gc_f_preserves_gold_proxy_limitations(isolated_data_paths):
    config = ProxyResearchWorkflowConfig(
        assets=["GC=F"],
        provider="yfinance",
        required_capabilities=["ohlcv", "gold_options_oi", "futures_oi", "iv"],
        processed_feature_root=isolated_data_paths / "processed",
    )

    result = preflight_proxy_ohlcv_assets(config)[0]

    assert result.status == ResearchExecutionWorkflowStatus.BLOCKED
    assert result.source_identity == "yahoo_finance"
    assert result.unsupported_capabilities == ["gold_options_oi", "futures_oi", "iv"]
    assert result.capability_snapshot["provider"] == "yahoo_finance"
    assert result.capability_snapshot["detected_ohlcv"] is False
    assert any(
        "Download or import OHLCV data for GC=F" in action for action in result.missing_data_actions
    )
    assert any("gold OHLCV proxies only" in limitation for limitation in result.limitations)
    assert any("not CME gold options OI" in limitation for limitation in result.limitations)


def test_xau_preflight_missing_options_file_returns_schema_instructions(isolated_data_paths):
    missing_path = isolated_data_paths / "raw" / "xau" / "missing_options.csv"
    config = XauVolOiWorkflowConfig(options_oi_file_path=missing_path)

    result = preflight_xau_options_file(config)

    assert result.workflow_type == "xau_vol_oi"
    assert result.status == ResearchExecutionWorkflowStatus.BLOCKED
    assert result.ready is False
    assert any("CSV or Parquet" in instruction for instruction in result.missing_data_actions)
    assert any(
        "date" in instruction and "open_interest" in instruction
        for instruction in result.missing_data_actions
    )


def test_xau_preflight_valid_options_file_is_ready(isolated_data_paths):
    options_path = isolated_data_paths / "raw" / "xau" / "options.csv"
    options_path.parent.mkdir(parents=True, exist_ok=True)
    options_path.write_text(
        "\n".join(
            [
                "date,expiry,strike,option_type,open_interest",
                "2026-05-01,2026-05-17,2400,call,1000",
                "2026-05-01,2026-05-17,2300,put,900",
            ]
        ),
        encoding="utf-8",
    )
    config = XauVolOiWorkflowConfig(options_oi_file_path=options_path)

    result = preflight_xau_options_file(config)

    assert result.status == ResearchExecutionWorkflowStatus.COMPLETED
    assert result.ready is True
    assert result.row_count == 2
    assert result.missing_data_actions == []
