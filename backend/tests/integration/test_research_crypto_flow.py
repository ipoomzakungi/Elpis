from src.models.research import ResearchRunRequest
from src.research.orchestration import ResearchOrchestrator
from src.research.report_store import ResearchReportStore
from tests.helpers.research_data import write_synthetic_research_features


def test_crypto_like_research_run_persists_validation_aggregation_artifacts(
    isolated_data_paths,
):
    feature_path = isolated_data_paths / "processed" / "btcusdt_15m_features.parquet"
    write_synthetic_research_features(feature_path, rows=30)
    request = ResearchRunRequest.model_validate(
        {
            "assets": [
                {
                    "symbol": "BTCUSDT",
                    "provider": "binance",
                    "asset_class": "crypto",
                    "timeframe": "15m",
                    "feature_path": str(feature_path),
                    "required_feature_groups": [
                        "ohlcv",
                        "regime",
                        "oi",
                        "funding",
                        "volume_confirmation",
                    ],
                }
            ],
            "validation_config": {
                "stress_profiles": ["normal", "high_fee"],
                "sensitivity_grid": {
                    "grid_entry_threshold": [0.2],
                    "atr_stop_buffer": [1.0],
                    "breakout_risk_reward_multiple": [1.5],
                    "fee_slippage_profile": ["normal"],
                },
                "walk_forward": {"split_count": 2, "minimum_rows_per_split": 6},
            },
            "report_format": "both",
        }
    )

    run = ResearchOrchestrator().run(request)

    assert run.status == "completed"
    assert run.completed_count == 1
    asset = run.assets[0]
    assert asset.validation_run_id
    assert asset.stress_summary
    assert asset.walk_forward_summary
    assert asset.regime_coverage_summary
    assert asset.concentration_summary
    assert asset.classification in {"robust", "fragile", "inconclusive", "not_worth_continuing"}

    artifact_types = {artifact.artifact_type.value for artifact in run.artifacts}
    assert artifact_types >= {
        "research_stress_summary",
        "research_walk_forward_summary",
        "research_regime_coverage_summary",
        "research_concentration_summary",
    }

    store = ResearchReportStore()
    validation = store.read_validation_aggregation(run.research_run_id)
    assert validation.stress == asset.stress_summary
    assert validation.walk_forward == asset.walk_forward_summary
    assert validation.regime_coverage == asset.regime_coverage_summary
    assert validation.concentration == asset.concentration_summary

    report = store.report_store.read_json(run.research_run_id, "research_report.json")
    assert report["validation_summary"]["stress"]
    assert report["validation_summary"]["walk_forward"]
    assert report["validation_summary"]["regime_coverage"]
    assert report["validation_summary"]["concentration"]
