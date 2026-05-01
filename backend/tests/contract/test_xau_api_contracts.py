from fastapi.testclient import TestClient

from src.main import app
from tests.helpers.test_xau_data import sample_xau_report_request, write_sample_xau_options_csv

client = TestClient(app)


def _report_payload(source_path) -> dict:
    return sample_xau_report_request(source_path).model_dump(mode="json")


def test_xau_report_creation_returns_validation_error_for_missing_required_columns(tmp_path):
    source_path = tmp_path / "gold_options.csv"
    source_path.write_text("timestamp,strike,option_type\n2026-04-30,2400,call\n", encoding="utf-8")

    response = client.post(
        "/api/v1/xau/vol-oi/reports",
        json={"options_oi_file_path": str(source_path)},
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "VALIDATION_ERROR"
    assert "Gold options OI file" in payload["error"]["message"]
    assert any(
        "Missing required columns" in item["message"] for item in payload["error"]["details"]
    )


def test_xau_report_creation_returns_validation_error_for_unsafe_path():
    response = client.post(
        "/api/v1/xau/vol-oi/reports",
        json={"options_oi_file_path": "../gold_options.csv"},
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "VALIDATION_ERROR"
    assert any("Unsafe file path" in item["message"] for item in payload["error"]["details"])


def test_xau_report_creation_rejects_invalid_reference_type(tmp_path):
    source_path = tmp_path / "gold_options.csv"
    source_path.write_text(
        "timestamp,expiry,strike,option_type,open_interest\n2026-04-30,2026-05-07,2400,call,100\n",
        encoding="utf-8",
    )

    response = client.post(
        "/api/v1/xau/vol-oi/reports",
        json={
            "options_oi_file_path": str(source_path),
            "spot_reference": {
                "source": "manual",
                "symbol": "GC",
                "price": 2410,
                "reference_type": "futures",
            },
        },
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "VALIDATION_ERROR"
    assert "spot_reference" in payload["error"]["details"][0]["message"]


def test_xau_report_read_endpoints_return_report_walls_and_zones(tmp_path):
    source_path = write_sample_xau_options_csv(tmp_path / "gold_options.csv")

    with TestClient(app) as test_client:
        create_response = test_client.post(
            "/api/v1/xau/vol-oi/reports",
            json=_report_payload(source_path),
        )
        report_id = create_response.json()["report_id"]

        list_response = test_client.get("/api/v1/xau/vol-oi/reports")
        detail_response = test_client.get(f"/api/v1/xau/vol-oi/reports/{report_id}")
        walls_response = test_client.get(f"/api/v1/xau/vol-oi/reports/{report_id}/walls")
        zones_response = test_client.get(f"/api/v1/xau/vol-oi/reports/{report_id}/zones")

    assert create_response.status_code == 200
    created = create_response.json()
    assert created["report_id"] == report_id
    assert created["wall_count"] == 2
    assert created["zone_count"] >= 1
    assert created["basis_snapshot"]["basis_source"] == "computed"
    assert created["expected_range"]["source"] == "iv"
    assert any(artifact["artifact_type"] == "walls" for artifact in created["artifacts"])
    assert any(artifact["artifact_type"] == "zones" for artifact in created["artifacts"])

    assert list_response.status_code == 200
    listed = list_response.json()["reports"]
    assert any(report["report_id"] == report_id for report in listed)

    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["report_id"] == report_id
    assert detail["walls"]
    assert detail["zones"]
    assert any("research annotations" in warning for warning in detail["warnings"])

    assert walls_response.status_code == 200
    walls_payload = walls_response.json()
    assert walls_payload["report_id"] == report_id
    assert len(walls_payload["data"]) == created["wall_count"]
    assert walls_payload["data"][0]["wall_score"] > 0
    assert walls_payload["data"][0]["spot_equivalent_level"] is not None

    assert zones_response.status_code == 200
    zones_payload = zones_response.json()
    assert zones_payload["report_id"] == report_id
    assert len(zones_payload["data"]) == created["zone_count"]
    assert all("not trading signals" in " ".join(row["notes"]) for row in zones_payload["data"])


def test_xau_report_read_endpoints_return_structured_not_found_errors():
    with TestClient(app) as test_client:
        detail_response = test_client.get("/api/v1/xau/vol-oi/reports/unknown_report")
        walls_response = test_client.get("/api/v1/xau/vol-oi/reports/unknown_report/walls")
        zones_response = test_client.get("/api/v1/xau/vol-oi/reports/unknown_report/zones")

    for response in (detail_response, walls_response, zones_response):
        payload = response.json()
        assert response.status_code == 404
        assert payload["error"]["code"] == "NOT_FOUND"
        assert "unknown_report" in payload["error"]["message"]
