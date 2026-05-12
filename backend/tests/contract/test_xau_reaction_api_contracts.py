from fastapi.testclient import TestClient

from src.main import app
from src.xau.report_store import XauReportStore
from tests.helpers.test_xau_reaction_data import (
    sample_feature006_xau_report,
    sample_xau_reaction_full_context_request,
)


def test_xau_reaction_routes_are_registered():
    registered_paths = {route.path for route in app.routes}

    assert "/api/v1/xau/reaction-reports" in registered_paths
    assert "/api/v1/xau/reaction-reports/{report_id}" in registered_paths
    assert "/api/v1/xau/reaction-reports/{report_id}/reactions" in registered_paths
    assert "/api/v1/xau/reaction-reports/{report_id}/risk-plan" in registered_paths


def test_create_xau_reaction_report_contract_persists_research_sections():
    XauReportStore().save_source_validation_report(sample_feature006_xau_report())
    client = TestClient(app)

    response = client.post(
        "/api/v1/xau/reaction-reports",
        json=sample_xau_reaction_full_context_request().model_dump(mode="json"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["report_id"].startswith("xau_reaction_")
    assert payload["source_report_id"] == "xau_vol_oi_synthetic_20260512"
    assert payload["status"] == "completed"
    assert payload["source_wall_count"] == 1
    assert payload["source_zone_count"] == 1
    assert payload["reaction_count"] == 1
    assert payload["risk_plan_count"] == 1
    assert payload["freshness_state"]["state"] == "VALID"
    assert payload["vol_regime_state"]["vrp_regime"] == "iv_premium"
    assert payload["open_regime_state"]["open_side"] == "above_open"
    assert payload["warnings"]
    assert payload["limitations"]
    assert {artifact["artifact_type"] for artifact in payload["artifacts"]} >= {
        "metadata",
        "report_json",
        "report_markdown",
        "reactions",
        "risk_plans",
    }
    _assert_no_directional_or_readiness_wording(payload)


def test_list_detail_reactions_and_risk_plan_contracts_return_saved_report_sections():
    XauReportStore().save_source_validation_report(sample_feature006_xau_report())
    client = TestClient(app)
    create_response = client.post(
        "/api/v1/xau/reaction-reports",
        json=sample_xau_reaction_full_context_request().model_dump(mode="json"),
    )
    report_id = create_response.json()["report_id"]

    list_response = client.get("/api/v1/xau/reaction-reports")
    detail_response = client.get(f"/api/v1/xau/reaction-reports/{report_id}")
    reactions_response = client.get(f"/api/v1/xau/reaction-reports/{report_id}/reactions")
    risk_plan_response = client.get(f"/api/v1/xau/reaction-reports/{report_id}/risk-plan")

    assert list_response.status_code == 200
    assert [item["report_id"] for item in list_response.json()["reports"]] == [report_id]

    assert detail_response.status_code == 200
    assert detail_response.json()["report_id"] == report_id
    assert detail_response.json()["reactions"][0]["wall_id"] == "wall_2400_call"

    assert reactions_response.status_code == 200
    reaction_payload = reactions_response.json()
    assert reaction_payload["report_id"] == report_id
    assert reaction_payload["data"][0]["reaction_label"] == "BREAKOUT_CANDIDATE"

    assert risk_plan_response.status_code == 200
    risk_payload = risk_plan_response.json()
    assert risk_payload["report_id"] == report_id
    assert risk_payload["data"][0]["reaction_id"] == reaction_payload["data"][0]["reaction_id"]


def test_missing_source_report_returns_structured_not_found():
    request = sample_xau_reaction_full_context_request().model_copy(
        update={"source_report_id": "missing_xau_report"}
    )
    client = TestClient(app)

    response = client.post(
        "/api/v1/xau/reaction-reports",
        json=request.model_dump(mode="json"),
    )

    assert response.status_code == 404
    payload = response.json()
    assert payload["error"]["code"] == "NOT_FOUND"
    assert "missing_xau_report" in payload["error"]["message"]


def test_invalid_reaction_request_returns_structured_validation_error():
    request = sample_xau_reaction_full_context_request().model_dump(mode="json")
    request["research_only_acknowledged"] = False
    client = TestClient(app)

    response = client.post("/api/v1/xau/reaction-reports", json=request)

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "VALIDATION_ERROR"
    assert payload["error"]["details"]


def test_blocked_source_report_returns_structured_missing_data_error():
    blocked_report = sample_feature006_xau_report().model_copy(
        update={"walls": [], "zones": [], "wall_count": 0, "zone_count": 0}
    )
    XauReportStore().save_source_validation_report(blocked_report)
    client = TestClient(app)

    response = client.post(
        "/api/v1/xau/reaction-reports",
        json=sample_xau_reaction_full_context_request().model_dump(mode="json"),
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "MISSING_DATA"
    assert payload["error"]["details"][0]["field"] == "source_report_id"


def test_missing_reaction_report_sections_return_structured_not_found():
    client = TestClient(app)

    responses = [
        client.get("/api/v1/xau/reaction-reports/missing_reaction_report"),
        client.get("/api/v1/xau/reaction-reports/missing_reaction_report/reactions"),
        client.get("/api/v1/xau/reaction-reports/missing_reaction_report/risk-plan"),
    ]

    for response in responses:
        assert response.status_code == 404
        payload = response.json()
        assert payload["error"]["code"] == "NOT_FOUND"
        assert "missing_reaction_report" in payload["error"]["message"]


def _assert_no_directional_or_readiness_wording(payload: dict) -> None:
    text = str(payload).lower()
    forbidden_terms = [
        "buy",
        "sell",
        "execute",
        "execution",
        "live",
        "guaranteed",
        "profitable",
        "safe",
        "signal",
    ]
    for term in forbidden_terms:
        assert term not in text
