from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)


def _create_payload() -> dict[str, object]:
    return {
        "snapshot_time": "2026-05-14T03:08:04Z",
        "capture_session": "quikstrike-gold-am-session",
        "vol2vol_report_id": "quikstrike_20260513_101537",
        "matrix_report_id": "quikstrike_matrix_20260513_155058",
        "fusion_report_id": "xau_quikstrike_fusion_20260514_030803",
        "xau_vol_oi_report_id": "xau_vol_oi_20260514_030804",
        "xau_reaction_report_id": "xau_reaction_20260514_030804",
        "futures_price_at_snapshot": 4707.2,
        "event_news_flag": "none_known",
        "notes": ["Forward evidence snapshot from synthetic report ids."],
        "persist_report": True,
        "research_only_acknowledged": True,
    }


def _outcome_payload() -> dict[str, object]:
    return {
        "outcomes": [
            {
                "window": "30m",
                "status": "pending",
                "label": "pending",
                "notes": ["Synthetic outcome placeholder."],
            }
        ],
        "update_note": "Synthetic update placeholder.",
        "research_only_acknowledged": True,
    }


def test_forward_journal_routes_are_registered_in_openapi():
    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/xau/forward-journal/entries" in paths
    assert "/api/v1/xau/forward-journal/entries/{journal_id}" in paths
    assert "/api/v1/xau/forward-journal/entries/{journal_id}/outcomes" in paths


def test_list_forward_journal_entries_returns_empty_foundation_response():
    response = client.get("/api/v1/xau/forward-journal/entries")

    assert response.status_code == 200
    assert response.json() == {"entries": []}


def test_create_forward_journal_entry_returns_structured_placeholder_error():
    response = client.post("/api/v1/xau/forward-journal/entries", json=_create_payload())

    assert response.status_code == 501
    body = response.json()
    assert body["error"]["code"] == "NOT_IMPLEMENTED"
    assert "foundation slice" in body["error"]["message"]
    detail_messages = [item["message"] for item in body["error"]["details"]]
    assert any("research-only" in message for message in detail_messages)


def test_detail_and_outcome_routes_validate_ids_and_return_placeholder_errors():
    invalid = client.get("/api/v1/xau/forward-journal/entries/bad%20id")
    assert invalid.status_code == 400
    assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"

    detail = client.get("/api/v1/xau/forward-journal/entries/journal_report")
    assert detail.status_code == 501
    assert detail.json()["error"]["code"] == "NOT_IMPLEMENTED"

    outcomes = client.get("/api/v1/xau/forward-journal/entries/journal_report/outcomes")
    assert outcomes.status_code == 501
    assert outcomes.json()["error"]["code"] == "NOT_IMPLEMENTED"

    update = client.post(
        "/api/v1/xau/forward-journal/entries/journal_report/outcomes",
        json=_outcome_payload(),
    )
    assert update.status_code == 501
    assert update.json()["error"]["code"] == "NOT_IMPLEMENTED"

