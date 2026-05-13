from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.routes.xau_quikstrike_fusion import get_xau_quikstrike_fusion_report_store
from src.main import app
from src.xau_quikstrike_fusion.report_store import XauQuikStrikeFusionReportStore


@pytest.fixture()
def client_and_store(tmp_path: Path) -> Iterator[tuple[TestClient, XauQuikStrikeFusionReportStore]]:
    store = XauQuikStrikeFusionReportStore(reports_dir=tmp_path / "data" / "reports")
    app.dependency_overrides[get_xau_quikstrike_fusion_report_store] = lambda: store
    with TestClient(app) as client:
        yield client, store
    app.dependency_overrides.clear()


def test_xau_quikstrike_fusion_routes_are_registered_in_openapi():
    client = TestClient(app)

    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/xau/quikstrike-fusion/reports" in paths
    assert "/api/v1/xau/quikstrike-fusion/reports/{report_id}" in paths
    assert "/api/v1/xau/quikstrike-fusion/reports/{report_id}/rows" in paths
    assert "/api/v1/xau/quikstrike-fusion/reports/{report_id}/missing-context" in paths


def test_xau_quikstrike_fusion_list_returns_structured_placeholder(client_and_store):
    client, store = client_and_store

    response = client.get("/api/v1/xau/quikstrike-fusion/reports")

    assert response.status_code == 200
    payload = response.json()
    assert payload["reports"] == []
    assert payload["placeholder"] is True
    assert payload["report_root"] == store.report_root().as_posix()
    assert payload["limitations"]


def test_xau_quikstrike_fusion_create_returns_structured_placeholder_error(
    client_and_store,
):
    client, _store = client_and_store

    response = client.post(
        "/api/v1/xau/quikstrike-fusion/reports",
        json=_request_payload(),
    )

    assert response.status_code == 501
    assert response.json()["error"]["code"] == "NOT_IMPLEMENTED"


def test_xau_quikstrike_fusion_invalid_request_and_ids_are_structured(client_and_store):
    client, _store = client_and_store

    invalid_ack = client.post(
        "/api/v1/xau/quikstrike-fusion/reports",
        json={**_request_payload(), "research_only_acknowledged": False},
    )
    invalid_id = client.get("/api/v1/xau/quikstrike-fusion/reports/bad%20id")

    assert invalid_ack.status_code == 400
    assert invalid_ack.json()["error"]["code"] == "VALIDATION_ERROR"
    assert invalid_id.status_code == 400
    assert invalid_id.json()["error"]["code"] == "VALIDATION_ERROR"


def test_xau_quikstrike_fusion_detail_rows_and_missing_context_are_placeholders(
    client_and_store,
):
    client, _store = client_and_store

    detail = client.get("/api/v1/xau/quikstrike-fusion/reports/fusion_report")
    rows = client.get("/api/v1/xau/quikstrike-fusion/reports/fusion_report/rows")
    missing = client.get(
        "/api/v1/xau/quikstrike-fusion/reports/fusion_report/missing-context"
    )

    assert detail.status_code == 501
    assert rows.status_code == 501
    assert missing.status_code == 501
    assert detail.json()["error"]["code"] == "NOT_IMPLEMENTED"
    assert rows.json()["error"]["code"] == "NOT_IMPLEMENTED"
    assert missing.json()["error"]["code"] == "NOT_IMPLEMENTED"


def _request_payload() -> dict:
    return {
        "vol2vol_report_id": "vol2vol_report",
        "matrix_report_id": "matrix_report",
        "xauusd_spot_reference": 4692.1,
        "gc_futures_reference": 4696.7,
        "session_open_price": None,
        "realized_volatility": None,
        "candle_context": [],
        "create_xau_vol_oi_report": False,
        "create_xau_reaction_report": False,
        "run_label": "foundation-contract",
        "persist_report": True,
        "research_only_acknowledged": True,
    }
