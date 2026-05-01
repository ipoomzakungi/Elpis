from fastapi.testclient import TestClient

from src.main import app


def test_research_execution_list_placeholder_returns_empty_runs(isolated_data_paths):
    client = TestClient(app)

    response = client.get("/api/v1/research/execution-runs")

    assert response.status_code == 200
    assert response.json() == {"runs": []}


def test_research_execution_run_creates_crypto_preflight_evidence(isolated_data_paths):
    feature_path = isolated_data_paths / "processed" / "btcusdt_15m_features.parquet"
    from tests.helpers.test_research_execution_data import write_synthetic_execution_features

    write_synthetic_execution_features(feature_path, rows=12)
    client = TestClient(app)

    response = client.post(
        "/api/v1/research/execution-runs",
        json={
            "name": "crypto evidence contract",
            "research_only_acknowledged": True,
            "crypto": {
                "enabled": True,
                "primary_assets": ["BTCUSDT", "ETHUSDT"],
                "processed_feature_root": str(isolated_data_paths / "processed"),
                "existing_research_run_id": "research_existing_crypto",
            },
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["execution_run_id"].startswith("rex_")
    assert body["name"] == "crypto evidence contract"
    assert body["evidence_summary"]["status"] == "partial"
    assert body["evidence_summary"]["decision"] == "refine"
    assert body["evidence_summary"]["crypto_summary"]["completed_asset_count"] == 1
    assert body["evidence_summary"]["crypto_summary"]["blocked_asset_count"] == 1
    assert body["evidence_summary"]["workflow_results"][0]["report_ids"] == [
        "research_existing_crypto"
    ]
    assert any(
        "ETHUSDT" in instruction
        for instruction in body["evidence_summary"]["missing_data_checklist"]
    )

    list_response = client.get("/api/v1/research/execution-runs")
    assert list_response.status_code == 200
    listed = list_response.json()["runs"]
    assert len(listed) == 1
    assert listed[0]["execution_run_id"] == body["execution_run_id"]
    assert listed[0]["status"] == "partial"

    detail_response = client.get(f"/api/v1/research/execution-runs/{body['execution_run_id']}")
    assert detail_response.status_code == 200
    assert detail_response.json()["execution_run_id"] == body["execution_run_id"]


def test_research_execution_detail_returns_structured_not_found():
    client = TestClient(app)

    response = client.get("/api/v1/research/execution-runs/missing-run")

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert "missing-run" in body["error"]["message"]


def test_research_execution_evidence_returns_structured_not_found():
    client = TestClient(app)

    response = client.get("/api/v1/research/execution-runs/missing-run/evidence")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_research_execution_missing_data_returns_structured_not_found():
    client = TestClient(app)

    response = client.get("/api/v1/research/execution-runs/missing-run/missing-data")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
