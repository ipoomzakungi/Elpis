from fastapi.testclient import TestClient

from src.main import app


def test_free_derivatives_routes_are_registered_in_openapi():
    client = TestClient(app)

    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/data-sources/bootstrap/free-derivatives" in paths
    assert "/api/v1/data-sources/bootstrap/free-derivatives/runs" in paths
    assert "/api/v1/data-sources/bootstrap/free-derivatives/runs/{run_id}" in paths


def test_free_derivatives_bootstrap_placeholder_returns_structured_response():
    client = TestClient(app)

    response = client.post(
        "/api/v1/data-sources/bootstrap/free-derivatives",
        json={
            "include_cftc": True,
            "include_gvz": True,
            "include_deribit": True,
            "run_label": "foundation_smoke",
            "research_only_acknowledged": True,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["run_id"] == "free_derivatives_foundation_smoke"
    assert payload["status"] == "blocked"
    assert {row["source"] for row in payload["source_results"]} == {
        "cftc_cot",
        "gvz",
        "deribit_public_options",
    }
    assert payload["artifacts"] == []
    assert any("research-only" in warning.lower() for warning in payload["warnings"])
    assert "api_key" not in response.text


def test_free_derivatives_bootstrap_rejects_missing_research_acknowledgement():
    client = TestClient(app)

    response = client.post(
        "/api/v1/data-sources/bootstrap/free-derivatives",
        json={"research_only_acknowledged": False},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_free_derivatives_list_and_missing_detail_contracts_are_structured():
    client = TestClient(app)

    list_response = client.get("/api/v1/data-sources/bootstrap/free-derivatives/runs")
    missing_response = client.get(
        "/api/v1/data-sources/bootstrap/free-derivatives/runs/not_a_real_run"
    )

    assert list_response.status_code == 200
    assert list_response.json() == {"runs": []}
    assert missing_response.status_code == 404
    assert missing_response.json()["error"]["code"] == "NOT_FOUND"


def test_readiness_capabilities_and_missing_data_include_free_derivatives_sources():
    client = TestClient(app)

    readiness = client.get("/api/v1/data-sources/readiness")
    capabilities = client.get("/api/v1/data-sources/capabilities")
    missing_data = client.get("/api/v1/data-sources/missing-data")

    assert readiness.status_code == 200
    assert capabilities.status_code == 200
    assert missing_data.status_code == 200

    readiness_providers = {
        row["provider_type"] for row in readiness.json()["provider_statuses"]
    }
    capability_providers = {
        row["provider_type"] for row in capabilities.json()["capabilities"]
    }
    action_providers = {row["provider_type"] for row in missing_data.json()["actions"]}

    for provider in {"cftc_cot", "gvz", "deribit_public_options"}:
        assert provider in readiness_providers
        assert provider in capability_providers
        assert provider in action_providers

    assert "Weekly broad positioning" in capabilities.text
    assert "GLD-options-derived volatility proxy" in capabilities.text
    assert "crypto options data only" in capabilities.text

