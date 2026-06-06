from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.routes.xau_daily_workbench import get_xau_daily_workbench_service
from src.main import app
from src.xau_daily_workbench.service import XauDailyWorkbenchService
from tests.unit.test_xau_daily_workbench_service import _write_temp_bundle


@pytest.fixture()
def client_and_service(tmp_path: Path) -> Iterator[tuple[TestClient, XauDailyWorkbenchService]]:
    service = XauDailyWorkbenchService(reports_dir=tmp_path / "data" / "reports")
    app.dependency_overrides[get_xau_daily_workbench_service] = lambda: service
    with TestClient(app) as client:
        yield client, service
    app.dependency_overrides.clear()


def test_xau_daily_workbench_routes_are_registered_in_openapi() -> None:
    client = TestClient(app)

    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/research/xau/workbench/run" in paths
    assert "/api/v1/research/xau/workbench/latest" in paths
    assert "/api/v1/research/xau/workbench/runs/{run_id}" in paths
    assert "/api/v1/research/xau/workbench/maps/{map_id}" in paths
    assert "/api/v1/research/xau/workbench/candidates/{map_id}" in paths


def test_run_endpoint_returns_map_and_candidate_ids(client_and_service) -> None:
    client, service = client_and_service
    input_dir = _write_temp_bundle(service.workbench_store.reports_dir.parent.parent)

    response = client.post(
        "/api/v1/research/xau/workbench/run",
        json={
            "session_date": "2026-06-02",
            "expiration_code": "OG1M6",
            "traded_instrument": "XAUUSD",
            "cme_source": "local_bundle",
            "input_dir": str(input_dir),
            "map_id": "test_xau_workbench_api",
            "gc_reference_price": 4549.2,
            "traded_reference_price": 4536.7,
            "session_open_price": 4538.0,
            "run_candidates": True,
            "research_only_acknowledged": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["map_id"] == "test_xau_workbench_api"
    assert payload["candidate_set_id"]
    assert payload["research_only"] is True
    assert payload["signal_allowed"] is False
    assert payload["candidate_set"]["signal_allowed"] is False


def test_latest_endpoint_handles_empty_state(client_and_service) -> None:
    client, _service = client_and_service

    response = client.get("/api/v1/research/xau/workbench/latest")

    assert response.status_code == 200
    payload = response.json()
    assert payload["readiness"] == "blocked"
    assert payload["latest_run"] is None
    assert payload["missing_inputs"][0]["input_name"] == "xau_daily_workbench_run"
    assert payload["signal_allowed"] is False
    assert payload["research_only"] is True


def test_map_and_candidate_endpoints_roundtrip(client_and_service) -> None:
    client, service = client_and_service
    input_dir = _write_temp_bundle(service.workbench_store.reports_dir.parent.parent)
    created = client.post(
        "/api/v1/research/xau/workbench/run",
        json={
            "session_date": "2026-06-02",
            "expiration_code": "OG1M6",
            "traded_instrument": "XAUUSD",
            "cme_source": "local_bundle",
            "input_dir": str(input_dir),
            "map_id": "test_xau_workbench_api_roundtrip",
            "gc_reference_price": 4549.2,
            "traded_reference_price": 4536.7,
            "session_open_price": 4538.0,
            "run_candidates": True,
            "research_only_acknowledged": True,
        },
    ).json()

    map_response = client.get(
        f"/api/v1/research/xau/workbench/maps/{created['map_id']}"
    )
    candidate_response = client.get(
        f"/api/v1/research/xau/workbench/candidates/{created['map_id']}"
    )
    run_response = client.get(
        f"/api/v1/research/xau/workbench/runs/{created['run_id']}"
    )

    assert run_response.status_code == 200
    assert run_response.json()["run_id"] == created["run_id"]
    assert map_response.status_code == 200
    assert map_response.json()["daily_map"]["signal_allowed"] is False
    assert candidate_response.status_code == 200
    assert candidate_response.json()["candidate_set_id"] == created["candidate_set_id"]
    assert candidate_response.json()["candidate_set"]["signal_allowed"] is False
