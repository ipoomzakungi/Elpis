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


def test_detail_and_outcome_routes_keep_foundation_placeholder_errors(journal_store):
    invalid = client.get("/api/v1/xau/forward-journal/entries/bad%20id")
    assert invalid.status_code == 400
    assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"

    detail = client.get("/api/v1/xau/forward-journal/entries/journal_report")
    assert detail.status_code == 501
    assert detail.json()["error"]["code"] == "NOT_IMPLEMENTED"

    outcomes = client.get("/api/v1/xau/forward-journal/entries/journal_report/outcomes")
    assert outcomes.status_code == 501
    assert outcomes.json()["error"]["code"] == "NOT_IMPLEMENTED"
