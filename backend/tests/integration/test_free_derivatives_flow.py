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


def test_free_derivatives_fixture_flow_preserves_partial_source_results(
    client_and_store,
):
    client, store, tmp_path = client_and_store
    response = client.post(
        "/api/v1/data-sources/bootstrap/free-derivatives",
        json=_partial_fixture_request(tmp_path),
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "partial"
    source_statuses = {
        result["source"]: result["status"] for result in payload["source_results"]
    }
    assert source_statuses == {
        "cftc_cot": "completed",
        "gvz": "skipped",
        "deribit_public_options": "partial",
    }
    assert any(
        "missing public IV/OI" in warning
        for result in payload["source_results"]
        for warning in result["warnings"]
    )
    assert store.read_run(payload["run_id"]).status.value == "partial"

    detail_response = client.get(
        f"/api/v1/data-sources/bootstrap/free-derivatives/runs/{payload['run_id']}"
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["source_results"][1]["missing_data_actions"]


def test_free_derivatives_responses_avoid_secret_values_and_execution_prompts(
    client_and_store,
):
    client, _, tmp_path = client_and_store
    response = client.post(
        "/api/v1/data-sources/bootstrap/free-derivatives",
        json=_partial_fixture_request(tmp_path, run_label="flow_no_secrets"),
    )

    assert response.status_code == 201
    payload_text = json.dumps(response.json()).lower()
    forbidden_fragments = [
        "api_key",
        "secret_value",
        "private_key",
        "wallet_address",
        "/private/",
        "execute order",
        "place order",
        "trade now",
        "live ready",
        "guaranteed",
        "profitable",
    ]
    for fragment in forbidden_fragments:
        assert fragment not in payload_text


def _partial_fixture_request(
    tmp_path: Path,
    *,
    run_label: str = "flow_partial",
) -> dict[str, object]:
    return {
        "include_cftc": True,
        "include_gvz": True,
        "include_deribit": True,
        "run_label": run_label,
        "research_only_acknowledged": True,
        "cftc": {
            "local_fixture_paths": [str(_write_cftc_csv(tmp_path / f"{run_label}_cot.csv"))],
        },
        "deribit": {
            "underlyings": ["BTC"],
            "snapshot_timestamp": "2026-05-12T10:00:00Z",
            "fixture_instruments_path": str(
                _write_json(
                    tmp_path / f"{run_label}_instruments.json",
                    [{"instrument_name": "BTC-27JUN25-100000-C", "is_active": True}],
                )
            ),
            "fixture_summary_path": str(
                _write_json(
                    tmp_path / f"{run_label}_summary.json",
                    [{"instrument_name": "BTC-27JUN25-100000-C", "volume": "3"}],
                )
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
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return path


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path
