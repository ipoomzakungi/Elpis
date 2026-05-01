from fastapi.testclient import TestClient

from src.main import app
from src.research_execution.report_store import ResearchExecutionReportStore
from tests.helpers.test_research_execution_data import write_synthetic_execution_features


def test_crypto_execution_run_persists_ready_and_missing_assets(isolated_data_paths):
    processed_root = isolated_data_paths / "processed"
    write_synthetic_execution_features(
        processed_root / "btcusdt_15m_features.parquet",
        symbol="BTCUSDT",
        rows=16,
    )
    client = TestClient(app)

    response = client.post(
        "/api/v1/research/execution-runs",
        json={
            "name": "mixed crypto evidence",
            "research_only_acknowledged": True,
            "crypto": {
                "enabled": True,
                "primary_assets": ["BTCUSDT", "SOLUSDT"],
                "timeframe": "15m",
                "processed_feature_root": str(processed_root),
            },
        },
    )

    assert response.status_code == 201
    payload = response.json()
    run_id = payload["execution_run_id"]
    assert payload["evidence_summary"]["status"] == "partial"
    assert payload["evidence_summary"]["crypto_summary"]["ready_assets"] == ["BTCUSDT"]
    assert payload["evidence_summary"]["crypto_summary"]["blocked_assets"] == ["SOLUSDT"]
    assert any(
        result["asset"] == "BTCUSDT" and result["ready"] is True
        for result in payload["preflight_results"]
    )
    assert any(
        result["asset"] == "SOLUSDT" and result["status"] == "blocked"
        for result in payload["preflight_results"]
    )

    store = ResearchExecutionReportStore()
    loaded = store.read_run(run_id)
    assert loaded.execution_run_id == run_id
    assert loaded.evidence_summary is not None
    assert loaded.evidence_summary.crypto_summary["completed_asset_count"] == 1
    assert loaded.evidence_summary.crypto_summary["blocked_asset_count"] == 1
    assert loaded.artifact_paths["metadata"].endswith("/metadata.json")
    assert loaded.artifact_paths["normalized_config"].endswith("/normalized_config.json")
    assert loaded.artifact_paths["evidence"].endswith("/evidence.json")
    assert loaded.artifact_paths["markdown"].endswith("/evidence.md")
    assert loaded.artifact_paths["missing_data"].endswith("/missing_data.json")

    evidence = client.get(f"/api/v1/research/execution-runs/{run_id}/evidence")
    assert evidence.status_code == 200
    assert evidence.json()["crypto_summary"]["blocked_assets"] == ["SOLUSDT"]

    missing = client.get(f"/api/v1/research/execution-runs/{run_id}/missing-data")
    assert missing.status_code == 200
    assert any("SOLUSDT" in item for item in missing.json()["missing_data_checklist"])
