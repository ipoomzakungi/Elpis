from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.routes.quikstrike_matrix import get_quikstrike_matrix_report_store
from src.main import app
from src.quikstrike_matrix.report_store import QuikStrikeMatrixReportStore


@pytest.fixture()
def client_and_store(
    tmp_path: Path,
) -> Iterator[tuple[TestClient, QuikStrikeMatrixReportStore]]:
    store = QuikStrikeMatrixReportStore(reports_dir=tmp_path / "data" / "reports")
    app.dependency_overrides[get_quikstrike_matrix_report_store] = lambda: store
    with TestClient(app) as client:
        yield client, store
    app.dependency_overrides.clear()


def test_quikstrike_matrix_routes_are_registered():
    client = TestClient(app)
    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/quikstrike-matrix/extractions/from-fixture" in paths
    assert "/api/v1/quikstrike-matrix/extractions" in paths
    assert "/api/v1/quikstrike-matrix/extractions/{extraction_id}" in paths
    assert "/api/v1/quikstrike-matrix/extractions/{extraction_id}/rows" in paths
    assert "/api/v1/quikstrike-matrix/extractions/{extraction_id}/conversion" in paths


def test_create_list_detail_rows_and_conversion_contracts(client_and_store):
    client, _store = client_and_store

    created = client.post(
        "/api/v1/quikstrike-matrix/extractions/from-fixture",
        json=_payload(),
    )
    assert created.status_code == 201
    report = created.json()
    extraction_id = report["extraction_id"]
    assert report["status"] == "completed"
    assert report["row_count"] == 2
    assert report["conversion_result"]["status"] == "completed"

    listing = client.get("/api/v1/quikstrike-matrix/extractions")
    assert listing.status_code == 200
    assert listing.json()["extractions"][0]["extraction_id"] == extraction_id

    detail = client.get(f"/api/v1/quikstrike-matrix/extractions/{extraction_id}")
    assert detail.status_code == 200
    assert detail.json()["extraction_id"] == extraction_id

    rows = client.get(f"/api/v1/quikstrike-matrix/extractions/{extraction_id}/rows")
    assert rows.status_code == 200
    assert len(rows.json()["rows"]) == 2

    conversion = client.get(
        f"/api/v1/quikstrike-matrix/extractions/{extraction_id}/conversion"
    )
    assert conversion.status_code == 200
    assert conversion.json()["conversion_result"]["status"] == "completed"
    assert len(conversion.json()["rows"]) == 2


def test_invalid_missing_blocked_and_secret_payload_contracts(client_and_store):
    client, _store = client_and_store

    invalid_ack = _payload()
    invalid_ack["research_only_acknowledged"] = False
    invalid_response = client.post(
        "/api/v1/quikstrike-matrix/extractions/from-fixture",
        json=invalid_ack,
    )
    assert invalid_response.status_code == 400
    assert invalid_response.json()["error"]["code"] == "VALIDATION_ERROR"

    missing = client.get("/api/v1/quikstrike-matrix/extractions/missing_run")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "NOT_FOUND"

    blocked_payload = _payload()
    blocked_payload["tables_by_view"]["open_interest_matrix"]["html_table"] = (
        "<table><tr><th>Total</th><td>999</td></tr></table>"
    )
    blocked = client.post(
        "/api/v1/quikstrike-matrix/extractions/from-fixture",
        json=blocked_payload,
    )
    assert blocked.status_code == 201
    assert blocked.json()["conversion_result"]["status"] == "blocked"

    secret_payload = _payload()
    secret_payload["cookies"] = "blocked"
    secret_response = client.post(
        "/api/v1/quikstrike-matrix/extractions/from-fixture",
        json=secret_payload,
    )
    assert secret_response.status_code == 400
    assert secret_response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_api_response_contains_no_secret_values_or_execution_wording(client_and_store):
    client, _store = client_and_store
    response = client.post("/api/v1/quikstrike-matrix/extractions/from-fixture", json=_payload())
    payload = response.text.lower()

    assert response.status_code == 201
    for forbidden in ("bearer abc", "set-cookie:", "__viewstate", "sessionid="):
        assert forbidden not in payload
    for forbidden in ("buy", "sell", "profit", "profitable"):
        assert forbidden not in payload


def _payload() -> dict:
    timestamp = datetime(2026, 5, 13, tzinfo=UTC).isoformat()
    return {
        "requested_views": ["open_interest_matrix"],
        "metadata_by_view": {
            "open_interest_matrix": {
                "capture_timestamp": timestamp,
                "product": "Gold (OG|GC)",
                "option_product_code": "OG|GC",
                "futures_symbol": "GC",
                "source_menu": "OPEN INTEREST Matrix",
                "selected_view_type": "open_interest_matrix",
                "selected_view_label": "OI Matrix",
                "raw_visible_text": "Gold (OG|GC) OPEN INTEREST Matrix",
            }
        },
        "tables_by_view": {
            "open_interest_matrix": {
                "view_type": "open_interest_matrix",
                "html_table": (
                    "<table><thead><tr><th>Strike</th>"
                    "<th colspan='2'>G2RK6 GC 2 DTE 4722.6</th></tr>"
                    "<tr><th></th><th>Call</th><th>Put</th></tr></thead>"
                    "<tbody><tr><th>4700</th><td>120</td><td>95</td></tr></tbody></table>"
                ),
            }
        },
        "persist_report": True,
        "research_only_acknowledged": True,
    }
