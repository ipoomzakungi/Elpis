import csv
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.routes.free_derivatives import get_free_derivatives_report_store
from src.free_derivatives.report_store import FreeDerivativesReportStore
from src.main import app


@pytest.fixture()
def client_and_store(
    tmp_path: Path,
) -> Iterator[tuple[TestClient, FreeDerivativesReportStore, Path]]:
    store = FreeDerivativesReportStore(
        raw_dir=tmp_path / "raw",
        processed_dir=tmp_path / "processed",
        reports_dir=tmp_path / "reports",
    )
    app.dependency_overrides[get_free_derivatives_report_store] = lambda: store
    with TestClient(app) as client:
        yield client, store, tmp_path
    app.dependency_overrides.clear()


def test_free_derivatives_routes_are_registered_in_openapi():
    client = TestClient(app)

    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/data-sources/bootstrap/free-derivatives" in paths
    assert "/api/v1/data-sources/bootstrap/free-derivatives/runs" in paths
    assert "/api/v1/data-sources/bootstrap/free-derivatives/runs/{run_id}" in paths


def test_free_derivatives_bootstrap_creates_fixture_backed_report(
    client_and_store,
):
    client, store, tmp_path = client_and_store

    response = client.post(
        "/api/v1/data-sources/bootstrap/free-derivatives",
        json=_fixture_request(tmp_path, run_label="contract_create"),
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["run_id"] == "free_derivatives_contract_create"
    assert payload["status"] == "completed"
    assert {row["source"] for row in payload["source_results"]} == {
        "cftc_cot",
        "gvz",
        "deribit_public_options",
    }
    assert {row["status"] for row in payload["source_results"]} == {"completed"}
    assert {"run_metadata", "run_json", "run_markdown"}.issubset(
        {artifact["artifact_type"] for artifact in payload["artifacts"]}
    )
    assert any("research-only" in warning.lower() for warning in payload["warnings"])
    assert "api_key" not in response.text.lower()
    assert store.read_run(payload["run_id"]).run_id == payload["run_id"]


def test_free_derivatives_list_and_detail_return_saved_runs(client_and_store):
    client, _, tmp_path = client_and_store
    create_response = client.post(
        "/api/v1/data-sources/bootstrap/free-derivatives",
        json=_fixture_request(tmp_path, run_label="contract_list"),
    )
    assert create_response.status_code == 201
    run_id = create_response.json()["run_id"]

    list_response = client.get("/api/v1/data-sources/bootstrap/free-derivatives/runs")
    detail_response = client.get(
        f"/api/v1/data-sources/bootstrap/free-derivatives/runs/{run_id}"
    )

    assert list_response.status_code == 200
    assert list_response.json()["runs"][0]["run_id"] == run_id
    assert list_response.json()["runs"][0]["artifact_count"] >= 3
    assert detail_response.status_code == 200
    assert detail_response.json()["run_id"] == run_id
    assert detail_response.json()["source_results"][0]["artifacts"]


def test_free_derivatives_invalid_missing_and_blocked_requests_are_structured(
    client_and_store,
):
    client, _, _ = client_and_store

    invalid_response = client.post(
        "/api/v1/data-sources/bootstrap/free-derivatives",
        json={"research_only_acknowledged": False},
    )
    missing_response = client.get(
        "/api/v1/data-sources/bootstrap/free-derivatives/runs/not_a_real_run"
    )
    blocked_response = client.post(
        "/api/v1/data-sources/bootstrap/free-derivatives",
        json={
            "include_cftc": True,
            "include_gvz": True,
            "include_deribit": True,
            "run_label": "contract_blocked",
            "research_only_acknowledged": True,
        },
    )

    assert invalid_response.status_code == 400
    assert invalid_response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert missing_response.status_code == 404
    assert missing_response.json()["error"]["code"] == "NOT_FOUND"
    assert blocked_response.status_code == 400
    assert blocked_response.json()["error"]["code"] == "MISSING_DATA"
    assert blocked_response.json()["error"]["details"]


def test_readiness_capabilities_and_missing_data_include_free_derivatives_sources():
    client = TestClient(app)

    readiness = client.get("/api/v1/data-sources/readiness")
    capabilities = client.get("/api/v1/data-sources/capabilities")
    missing_data = client.get("/api/v1/data-sources/missing-data")

    assert readiness.status_code == 200
    assert capabilities.status_code == 200
    assert missing_data.status_code == 200

    readiness_rows = {
        row["provider_type"]: row for row in readiness.json()["provider_statuses"]
    }
    capability_rows = {
        row["provider_type"]: row for row in capabilities.json()["capabilities"]
    }
    action_providers = {row["provider_type"] for row in missing_data.json()["actions"]}

    for provider in {"cftc_cot", "gvz", "deribit_public_options"}:
        assert provider in readiness_rows
        assert provider in capability_rows
        assert provider in action_providers
        assert readiness_rows[provider]["status"] == "ready"
        assert readiness_rows[provider]["secret_value_returned"] is False
        assert readiness_rows[provider]["missing_actions"]

    assert "Weekly broad positioning" in capabilities.text
    assert "GLD-options-derived volatility proxy" in capabilities.text
    assert "crypto options data only" in capabilities.text


def _fixture_request(tmp_path: Path, *, run_label: str) -> dict[str, object]:
    return {
        "include_cftc": True,
        "include_gvz": True,
        "include_deribit": True,
        "run_label": run_label,
        "research_only_acknowledged": True,
        "cftc": {
            "categories": ["futures_only", "futures_and_options_combined"],
            "local_fixture_paths": [
                str(_write_cftc_csv(tmp_path / f"{run_label}_cot.csv"))
            ],
        },
        "gvz": {
            "start_date": "2025-01-01",
            "end_date": "2025-01-04",
            "local_fixture_path": str(_write_gvz_csv(tmp_path / f"{run_label}_gvz.csv")),
        },
        "deribit": {
            "underlyings": ["BTC", "ETH"],
            "snapshot_timestamp": "2026-05-12T10:00:00Z",
            "fixture_instruments_path": str(
                _write_json(tmp_path / f"{run_label}_instruments.json", _sample_instruments())
            ),
            "fixture_summary_path": str(
                _write_json(tmp_path / f"{run_label}_summary.json", _sample_summary_rows())
            ),
        },
    }


def _write_cftc_csv(path: Path) -> Path:
    rows = [
        {
            "report_category": "futures_only",
            "As_of_Date_In_Form_YYMMDD": "250107",
            "Market_and_Exchange_Names": "GOLD - COMMODITY EXCHANGE INC.",
            "Open_Interest_All": "1000",
            "Noncommercial_Long_All": "130",
            "Noncommercial_Short_All": "70",
            "Commercial_Long_All": "200",
            "Commercial_Short_All": "210",
        },
        {
            "report_category": "futures_and_options_combined",
            "As_of_Date_In_Form_YYMMDD": "250107",
            "Market_and_Exchange_Names": "GOLD - COMMODITY EXCHANGE INC.",
            "Open_Interest_All": "2000",
            "Noncommercial_Long_All": "230",
            "Noncommercial_Short_All": "120",
            "Commercial_Long_All": "400",
            "Commercial_Short_All": "420",
        },
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return path


def _write_gvz_csv(path: Path) -> Path:
    rows = [
        {"DATE": "2025-01-01", "GVZCLS": "17.5"},
        {"DATE": "2025-01-02", "GVZCLS": "."},
        {"DATE": "2025-01-04", "GVZCLS": "18.25"},
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return path


def _sample_instruments() -> list[dict[str, object]]:
    return [
        {"instrument_name": "BTC-27JUN25-100000-C", "is_active": True},
        {"instrument_name": "BTC-27JUN25-90000-P", "is_active": True},
        {"instrument_name": "ETH-28MAR25-3500-P", "is_active": True},
    ]


def _sample_summary_rows() -> list[dict[str, object]]:
    return [
        {
            "instrument_name": "BTC-27JUN25-100000-C",
            "open_interest": 12.5,
            "mark_iv": 62.1,
            "bid_iv": 61.8,
            "ask_iv": 62.4,
            "underlying_price": 100500,
            "volume": 42,
        },
        {
            "instrument_name": "BTC-27JUN25-90000-P",
            "open_interest": 7.0,
            "mark_iv": 70.1,
            "bid_iv": 69.8,
            "ask_iv": 70.4,
            "underlying_price": 100500,
            "volume": 11,
        },
        {
            "instrument_name": "ETH-28MAR25-3500-P",
            "open_interest": 25,
            "mark_iv": 55.0,
            "bid_iv": 54.6,
            "ask_iv": 55.4,
            "underlying_price": 3400,
            "volume": 9,
        },
    ]


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path
