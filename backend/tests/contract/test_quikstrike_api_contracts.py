from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.routes.quikstrike import get_quikstrike_report_store
from src.main import app
from src.quikstrike.report_store import QuikStrikeReportStore


@pytest.fixture()
def client_and_store(tmp_path: Path) -> Iterator[tuple[TestClient, QuikStrikeReportStore]]:
    store = QuikStrikeReportStore(reports_dir=tmp_path / "data" / "reports")
    app.dependency_overrides[get_quikstrike_report_store] = lambda: store
    with TestClient(app) as client:
        yield client, store
    app.dependency_overrides.clear()


def test_quikstrike_routes_are_registered_in_openapi():
    client = TestClient(app)

    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/quikstrike/extractions/from-fixture" in paths
    assert "/api/v1/quikstrike/extractions" in paths
    assert "/api/v1/quikstrike/extractions/{extraction_id}" in paths
    assert "/api/v1/quikstrike/extractions/{extraction_id}/rows" in paths
    assert "/api/v1/quikstrike/extractions/{extraction_id}/conversion" in paths


def test_create_list_detail_rows_and_conversion_contract(client_and_store):
    client, store = client_and_store

    create_response = client.post(
        "/api/v1/quikstrike/extractions/from-fixture",
        json=_fixture_request(),
    )

    assert create_response.status_code == 201
    payload = create_response.json()
    extraction_id = payload["extraction_id"]
    assert payload["status"] == "completed"
    assert payload["row_count"] == 2
    assert payload["strike_mapping"]["confidence"] == "high"
    assert payload["conversion_result"]["status"] == "completed"
    assert payload["conversion_result"]["row_count"] == 2
    assert "cookie" not in str(payload).lower().replace("cookies", "")
    assert store.read_report(extraction_id).extraction_id == extraction_id

    list_response = client.get("/api/v1/quikstrike/extractions")
    detail_response = client.get(f"/api/v1/quikstrike/extractions/{extraction_id}")
    rows_response = client.get(f"/api/v1/quikstrike/extractions/{extraction_id}/rows")
    conversion_response = client.get(
        f"/api/v1/quikstrike/extractions/{extraction_id}/conversion"
    )

    assert list_response.status_code == 200
    assert list_response.json()["extractions"][0]["extraction_id"] == extraction_id
    assert detail_response.status_code == 200
    assert detail_response.json()["extraction_id"] == extraction_id
    assert rows_response.status_code == 200
    assert len(rows_response.json()["rows"]) == 2
    assert conversion_response.status_code == 200
    assert conversion_response.json()["conversion_result"]["status"] == "completed"
    assert len(conversion_response.json()["rows"]) == 2


def test_missing_invalid_and_secret_bearing_requests_are_structured(client_and_store):
    client, _ = client_and_store

    missing_response = client.get("/api/v1/quikstrike/extractions/missing_extraction")
    invalid_id_response = client.get("/api/v1/quikstrike/extractions/../bad")
    secret_response = client.post(
        "/api/v1/quikstrike/extractions/from-fixture",
        json={**_fixture_request(), "headers": {"Cookie": "not allowed"}},
    )
    invalid_ack_response = client.post(
        "/api/v1/quikstrike/extractions/from-fixture",
        json={**_fixture_request(), "research_only_acknowledged": False},
    )

    assert missing_response.status_code == 404
    assert missing_response.json()["error"]["code"] == "NOT_FOUND"
    assert invalid_id_response.status_code in {400, 404}
    assert secret_response.status_code == 400
    assert secret_response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert invalid_ack_response.status_code == 400
    assert invalid_ack_response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_quikstrike_api_preserves_blocked_conversion_status(client_and_store):
    client, _ = client_and_store
    request = _fixture_request()
    for series in request["highcharts_by_view"]["open_interest"]["series"]:
        for point in series.get("points", []):
            point["strike_id"] = None
            point["name"] = None
            point["category"] = None

    response = client.post("/api/v1/quikstrike/extractions/from-fixture", json=request)

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "partial"
    assert payload["strike_mapping"]["confidence"] == "partial"
    assert payload["conversion_result"]["status"] == "blocked"
    assert payload["conversion_result"]["blocked_reasons"]


def _fixture_request() -> dict:
    return {
        "requested_views": ["open_interest"],
        "dom_metadata_by_view": {
            "open_interest": {
                "product": "Gold",
                "option_product_code": "OG|GC",
                "futures_symbol": "GC",
                "expiration": "2026-05-15",
                "dte": 2.59,
                "future_reference_price": 4722.6,
                "source_view": "QUIKOPTIONS VOL2VOL",
                "selected_view_type": "open_interest",
                "surface": "QUIKOPTIONS VOL2VOL",
                "raw_header_text": (
                    "Gold (OG|GC) OG3K6 (2.59 DTE) vs 4722.6 - Open Interest"
                ),
                "raw_selector_text": (
                    "Metals Precious Metals Gold (OG|GC) OG3K6 15 May 2026"
                ),
                "warnings": [],
                "limitations": ["Local user-controlled QuikStrike extraction only."],
            }
        },
        "highcharts_by_view": {
            "open_interest": {
                "chart_title": "OG3K6 Open Interest",
                "view_type": "open_interest",
                "series": [
                    {
                        "series_name": "Put",
                        "series_type": "put",
                        "point_count": 1,
                        "points": [
                            {
                                "series_type": "put",
                                "x": 4700,
                                "y": 120,
                                "name": "4700",
                                "category": "4700",
                                "strike_id": "strike-4700",
                                "metadata_keys": ["StrikeId"],
                            }
                        ],
                        "warnings": [],
                        "limitations": [],
                    },
                    {
                        "series_name": "Call",
                        "series_type": "call",
                        "point_count": 1,
                        "points": [
                            {
                                "series_type": "call",
                                "x": 4700,
                                "y": 95,
                                "name": "4700",
                                "category": "4700",
                                "strike_id": "strike-4700",
                                "metadata_keys": ["StrikeId"],
                            }
                        ],
                        "warnings": [],
                        "limitations": [],
                    },
                ],
                "chart_warnings": [],
                "chart_limitations": [],
            }
        },
        "run_label": "contract",
        "report_format": "both",
        "research_only_acknowledged": True,
    }
