from src.models.research import ResearchAssetClass, ResearchAssetConfig, ResearchRunRequest
from src.research.orchestration import ResearchOrchestrator
from src.research.report_store import ResearchReportStore
from tests.helpers.research_data import write_synthetic_research_features


def test_yahoo_ohlcv_only_asset_completes_with_unsupported_oi_funding_labels(
    isolated_data_paths,
):
    feature_path = isolated_data_paths / "processed" / "spy_1d_features.parquet"
    write_synthetic_research_features(
        feature_path,
        symbol="SPY",
        rows=24,
        include_open_interest=False,
        include_funding=False,
    )
    request = ResearchRunRequest(
        assets=[
            ResearchAssetConfig(
                symbol="SPY",
                provider="yahoo_finance",
                asset_class=ResearchAssetClass.EQUITY_PROXY,
                timeframe="1d",
                feature_path=feature_path,
            )
        ]
    )

    run = ResearchOrchestrator().run(request)

    assert run.status == "completed"
    assert run.completed_count == 1
    asset = run.assets[0]
    assert asset.symbol == "SPY"
    assert asset.status == "completed"
    assert asset.preflight.capability_snapshot.supports_open_interest is False
    assert asset.preflight.capability_snapshot.supports_funding_rate is False
    assert asset.preflight.capability_snapshot.detected_open_interest is False
    assert asset.preflight.capability_snapshot.detected_funding_rate is False
    assert any("OHLCV-only" in note for note in asset.limitations)
    assert asset.strategy_comparison
    assert {row.category for row in asset.strategy_comparison} >= {"strategy", "baseline"}

    comparison = ResearchReportStore().read_comparison(run.research_run_id)
    assert comparison.data == asset.strategy_comparison
