from fastapi.testclient import TestClient

from src.main import app


def test_research_execution_list_placeholder_returns_empty_runs(isolated_data_paths):
    client = TestClient(app)

    response = client.get("/api/v1/research/execution-runs")

    assert response.status_code == 200
    assert response.json() == {"runs": []}


def test_research_execution_run_placeholder_returns_not_implemented():
    client = TestClient(app)

    response = client.post(
        "/api/v1/research/execution-runs",
        json={
            "research_only_acknowledged": True,
            "crypto": {"enabled": True, "primary_assets": ["BTCUSDT"]},
        },
    )

    assert response.status_code == 501
    body = response.json()
    assert body["error"]["code"] == "NOT_IMPLEMENTED"
    assert "not implemented" in body["error"]["message"].lower()


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
