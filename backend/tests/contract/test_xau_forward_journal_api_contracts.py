from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from src.api.routes.xau_forward_journal import get_xau_forward_journal_report_store
from src.main import app
from src.xau_forward_journal.report_store import XauForwardJournalReportStore
from tests.helpers.test_xau_forward_journal_data import (
    synthetic_forward_journal_create_payload,
    write_synthetic_source_reports,
)

client = TestClient(app)


@pytest.fixture
def journal_store(tmp_path) -> Iterator[XauForwardJournalReportStore]:
    reports_dir = tmp_path / "data" / "reports"
    store = XauForwardJournalReportStore(reports_dir=reports_dir)
    app.dependency_overrides[get_xau_forward_journal_report_store] = lambda: store
    try:
        yield store
    finally:
        app.dependency_overrides.pop(get_xau_forward_journal_report_store, None)


def test_forward_journal_routes_are_registered_in_openapi():
    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/xau/forward-journal/entries" in paths
    assert "/api/v1/xau/forward-journal/entries/{journal_id}" in paths
    assert "/api/v1/xau/forward-journal/entries/{journal_id}/outcomes" in paths


def test_create_forward_journal_entry_from_synthetic_source_reports(journal_store):
    write_synthetic_source_reports(journal_store.reports_dir)

    response = client.post(
        "/api/v1/xau/forward-journal/entries",
        json=synthetic_forward_journal_create_payload(),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["journal_id"].startswith("xau_forward_journal_")
    assert body["snapshot_key"] in body["journal_id"]
    assert body["snapshot"]["capture_window"] == "daily_snapshot"
    assert body["snapshot"]["capture_session"] is None
    assert len(body["source_reports"]) == 5
    assert len(body["top_oi_walls"]) == 2
    assert len(body["top_oi_change_walls"]) == 1
    assert len(body["top_volume_walls"]) == 1
    assert len(body["reaction_summaries"]) == 2
    assert len(body["outcomes"]) == 5
    assert body["artifacts"][0]["path"].startswith("data/reports/xau_forward_journal/")


def test_create_forward_journal_entry_is_idempotent_for_pending_outcomes(journal_store):
    write_synthetic_source_reports(journal_store.reports_dir)
    payload = synthetic_forward_journal_create_payload()

    first = client.post("/api/v1/xau/forward-journal/entries", json=payload)
    second = client.post("/api/v1/xau/forward-journal/entries", json=payload)

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["journal_id"] == first.json()["journal_id"]
    assert len(list(journal_store.report_root().glob("*"))) == 1


def test_create_forward_journal_entry_returns_structured_missing_source_error(journal_store):
    response = client.post(
        "/api/v1/xau/forward-journal/entries",
        json=synthetic_forward_journal_create_payload(),
    )

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "SOURCE_REPORT_NOT_FOUND"
    assert {detail["field"] for detail in body["error"]["details"]} == {
        "vol2vol_report_id",
        "matrix_report_id",
        "fusion_report_id",
        "xau_vol_oi_report_id",
        "xau_reaction_report_id",
    }


def test_create_forward_journal_entry_returns_structured_incompatible_source_error(
    journal_store,
):
    write_synthetic_source_reports(journal_store.reports_dir, product="Copper (HX|HG)")

    response = client.post(
        "/api/v1/xau/forward-journal/entries",
        json=synthetic_forward_journal_create_payload(),
    )

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "INCOMPATIBLE_SOURCE_REPORTS"
    assert any("product" in detail["field"] for detail in body["error"]["details"])


def test_create_forward_journal_entry_rejects_invalid_request_fields(journal_store):
    payload = synthetic_forward_journal_create_payload()
    payload["research_only_acknowledged"] = False

    response = client.post("/api/v1/xau/forward-journal/entries", json=payload)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def _completed_outcome_payload(label: str = "stayed_inside_range") -> dict:
    return {
        "outcomes": [
            {
                "window": "30m",
                "label": label,
                "observation_start": "2026-05-14T03:08:04Z",
                "observation_end": "2026-05-14T03:38:04Z",
                "open": 4707.2,
                "high": 4712.0,
                "low": 4701.5,
                "close": 4706.0,
                "reference_wall_id": "wall_1",
                "reference_wall_level": 4675.0,
                "notes": ["Synthetic outcome observation."],
            }
        ],
        "update_note": "Attach synthetic outcome observation.",
        "research_only_acknowledged": True,
    }


def test_detail_route_keeps_foundation_placeholder_but_outcomes_validate_ids(
    journal_store,
):
    invalid = client.get("/api/v1/xau/forward-journal/entries/bad%20id")
    assert invalid.status_code == 400
    assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"

    detail = client.get("/api/v1/xau/forward-journal/entries/journal_report")
    assert detail.status_code == 501
    assert detail.json()["error"]["code"] == "NOT_IMPLEMENTED"

    outcomes = client.get("/api/v1/xau/forward-journal/entries/bad%20id/outcomes")
    assert outcomes.status_code == 400
    assert outcomes.json()["error"]["code"] == "VALIDATION_ERROR"


def test_update_and_get_forward_journal_outcomes(journal_store):
    write_synthetic_source_reports(journal_store.reports_dir)
    created = client.post(
        "/api/v1/xau/forward-journal/entries",
        json=synthetic_forward_journal_create_payload(),
    )
    journal_id = created.json()["journal_id"]

    update = client.post(
        f"/api/v1/xau/forward-journal/entries/{journal_id}/outcomes",
        json=_completed_outcome_payload(),
    )
    read = client.get(f"/api/v1/xau/forward-journal/entries/{journal_id}/outcomes")

    assert update.status_code == 200
    assert update.json()["outcomes"][0]["status"] == "completed"
    assert update.json()["outcomes"][0]["label"] == "stayed_inside_range"
    assert read.status_code == 200
    assert read.json()["outcomes"][0]["label"] == "stayed_inside_range"


def test_update_outcomes_returns_structured_invalid_window_error(journal_store):
    response = client.post(
        "/api/v1/xau/forward-journal/entries/journal_report/outcomes",
        json={
            "outcomes": [{"window": "2h", "label": "pending"}],
            "research_only_acknowledged": True,
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_outcome_routes_return_structured_missing_entry_error(journal_store):
    get_response = client.get("/api/v1/xau/forward-journal/entries/missing/outcomes")
    post_response = client.post(
        "/api/v1/xau/forward-journal/entries/missing/outcomes",
        json=_completed_outcome_payload(),
    )

    assert get_response.status_code == 404
    assert get_response.json()["error"]["code"] == "NOT_FOUND"
    assert post_response.status_code == 404
    assert post_response.json()["error"]["code"] == "NOT_FOUND"


def test_update_outcomes_returns_structured_conflict_error(journal_store):
    write_synthetic_source_reports(journal_store.reports_dir)
    created = client.post(
        "/api/v1/xau/forward-journal/entries",
        json=synthetic_forward_journal_create_payload(),
    )
    journal_id = created.json()["journal_id"]

    first = client.post(
        f"/api/v1/xau/forward-journal/entries/{journal_id}/outcomes",
        json=_completed_outcome_payload("wall_held"),
    )
    conflict_payload = _completed_outcome_payload("wall_rejected")
    conflict_payload["update_note"] = None
    conflict = client.post(
        f"/api/v1/xau/forward-journal/entries/{journal_id}/outcomes",
        json=conflict_payload,
    )

    assert first.status_code == 200
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "OUTCOME_CONFLICT"


def test_update_outcomes_rejects_unsafe_notes(journal_store):
    write_synthetic_source_reports(journal_store.reports_dir)
    created = client.post(
        "/api/v1/xau/forward-journal/entries",
        json=synthetic_forward_journal_create_payload(),
    )
    journal_id = created.json()["journal_id"]
    payload = _completed_outcome_payload()
    payload["update_note"] = "Bearer secret-token"

    response = client.post(
        f"/api/v1/xau/forward-journal/entries/{journal_id}/outcomes",
        json=payload,
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
