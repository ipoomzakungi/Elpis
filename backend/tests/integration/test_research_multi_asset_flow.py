from src.models.research import (
    ResearchAssetClass,
    ResearchAssetConfig,
    ResearchRunRequest,
)
from src.research.orchestration import ResearchOrchestrator
from src.research.report_store import ResearchReportStore
from tests.helpers.research_data import write_synthetic_research_features


def test_mixed_available_and_missing_assets_are_persisted(isolated_data_paths):
    feature_path = isolated_data_paths / "processed" / "btcusdt_15m_features.parquet"
    write_synthetic_research_features(feature_path, rows=20)
    request = ResearchRunRequest(
        assets=[
            ResearchAssetConfig(
                symbol="BTCUSDT",
                provider="binance",
                asset_class=ResearchAssetClass.CRYPTO,
                timeframe="15m",
                feature_path=feature_path,
            ),
            ResearchAssetConfig(
                symbol="SPY",
                provider="yahoo_finance",
                asset_class=ResearchAssetClass.EQUITY_PROXY,
                timeframe="1d",
            ),
        ]
    )

    run = ResearchOrchestrator().run(request)

    assert run.status == "partial"
    assert run.completed_count == 1
    assert run.blocked_count == 1
    completed = next(asset for asset in run.assets if asset.symbol == "BTCUSDT")
    blocked = next(asset for asset in run.assets if asset.symbol == "SPY")
    assert completed.status == "completed"
    assert completed.data_identity["row_count"] == 20
    assert completed.data_identity["content_hash"]
    assert blocked.status == "blocked"
    assert blocked.classification == "missing_data"
    assert blocked.preflight.instructions

    store = ResearchReportStore()
    loaded = store.read_run(run.research_run_id)
    assert loaded.research_run_id == run.research_run_id
    assert loaded.completed_count == 1
    assert loaded.blocked_count == 1
    assets = store.read_assets(run.research_run_id)
    assert len(assets.data) == 2
    assert {artifact.artifact_type for artifact in loaded.artifacts}

