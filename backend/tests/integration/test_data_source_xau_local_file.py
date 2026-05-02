import pytest
from fastapi.testclient import TestClient

from src.main import app
from tests.helpers.test_xau_data import (
    write_sample_xau_options_csv,
    write_sample_xau_options_parquet,
)


@pytest.mark.parametrize("suffix", ["csv", "parquet"])
def test_xau_local_file_preflight_accepts_csv_and_parquet(isolated_data_paths, suffix):
    options_path = isolated_data_paths / "raw" / "xau" / f"options.{suffix}"
    options_path.parent.mkdir(parents=True, exist_ok=True)
    if suffix == "csv":
        write_sample_xau_options_csv(options_path)
    else:
        write_sample_xau_options_parquet(options_path)
    client = TestClient(app)

    response = client.post(
        "/api/v1/data-sources/preflight",
        json={
            "crypto_assets": [],
            "proxy_assets": [],
            "xau_options_oi_file_path": str(options_path),
            "research_only_acknowledged": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["xau_result"]["status"] == "ready"
    assert payload["xau_result"]["row_count"] == 2
    assert payload["xau_result"]["missing_data_actions"] == []


def test_xau_local_file_preflight_blocks_missing_schema_columns(isolated_data_paths):
    options_path = isolated_data_paths / "raw" / "xau" / "invalid.csv"
    options_path.parent.mkdir(parents=True, exist_ok=True)
    options_path.write_text("date,strike,option_type\n2026-05-01,2400,call\n", encoding="utf-8")
    client = TestClient(app)

    response = client.post(
        "/api/v1/data-sources/preflight",
        json={
            "crypto_assets": [],
            "proxy_assets": [],
            "xau_options_oi_file_path": str(options_path),
            "research_only_acknowledged": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "blocked"
    action = payload["xau_result"]["missing_data_actions"][0]
    assert action["action_id"] == "xau-local-options-schema"
    assert "expiry" in action["required_columns"]
    assert "open_interest" in action["required_columns"]
