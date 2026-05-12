from fastapi.testclient import TestClient

from src.main import app
from tests.helpers.test_xau_reaction_data import sample_xau_reaction_report_request


def test_xau_reaction_routes_are_registered():
    registered_paths = {route.path for route in app.routes}

    assert "/api/v1/xau/reaction-reports" in registered_paths
    assert "/api/v1/xau/reaction-reports/{report_id}" in registered_paths
    assert "/api/v1/xau/reaction-reports/{report_id}/reactions" in registered_paths
    assert "/api/v1/xau/reaction-reports/{report_id}/risk-plan" in registered_paths


def test_xau_reaction_placeholder_endpoints_return_structured_not_implemented():
    client = TestClient(app)
    request = sample_xau_reaction_report_request().model_dump(mode="json")

    responses = [
        client.post("/api/v1/xau/reaction-reports", json=request),
        client.get("/api/v1/xau/reaction-reports"),
        client.get("/api/v1/xau/reaction-reports/xau_reaction_20260512"),
        client.get("/api/v1/xau/reaction-reports/xau_reaction_20260512/reactions"),
        client.get("/api/v1/xau/reaction-reports/xau_reaction_20260512/risk-plan"),
    ]

    for response in responses:
        payload = response.json()
        assert response.status_code == 501
        assert payload["error"]["code"] == "NOT_IMPLEMENTED"
        assert "foundation slice" in payload["error"]["message"]
