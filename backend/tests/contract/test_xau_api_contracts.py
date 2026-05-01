from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)


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
