from fastapi.testclient import TestClient

from src.main import app


def test_xau_execution_run_blocks_missing_options_file_with_schema_instructions(
    isolated_data_paths,
):
    missing_path = isolated_data_paths / "raw" / "xau" / "missing_options.csv"
    client = TestClient(app)

    response = client.post(
        "/api/v1/research/execution-runs",
        json={
            "name": "missing xau evidence",
            "research_only_acknowledged": True,
            "xau": {
                "enabled": True,
                "options_oi_file_path": str(missing_path),
            },
        },
    )

    assert response.status_code == 201
    payload = response.json()
    evidence = payload["evidence_summary"]
    xau_summary = evidence["xau_summary"]
    assert evidence["status"] == "blocked"
    assert evidence["decision"] == "data_blocked"
    assert xau_summary["status"] == "blocked"
    assert xau_summary["wall_count"] == 0
    assert xau_summary["zone_count"] == 0
    assert xau_summary["report_ids"] == []
    assert xau_summary["basis_snapshot_status"] == "unavailable"
    assert xau_summary["expected_range_status"] == "unavailable"
    assert any(
        "date or timestamp" in item and "open_interest" in item
        for item in xau_summary["missing_data_actions"]
    )
    assert any(
        "Yahoo GC=F and GLD are OHLCV proxies only" in item
        for item in xau_summary["limitations"]
    )
    assert any("missing_options.csv" in item for item in evidence["missing_data_checklist"])


def test_xau_execution_run_blocks_missing_existing_report_reference(isolated_data_paths):
    client = TestClient(app)

    response = client.post(
        "/api/v1/research/execution-runs",
        json={
            "name": "missing xau report reference",
            "research_only_acknowledged": True,
            "xau": {
                "enabled": True,
                "existing_xau_report_id": "xau_vol_oi_missing_reference",
            },
        },
    )

    assert response.status_code == 201
    evidence = response.json()["evidence_summary"]
    workflow = next(
        result for result in evidence["workflow_results"] if result["workflow_type"] == "xau_vol_oi"
    )
    assert workflow["status"] == "blocked"
    assert workflow["decision"] == "data_blocked"
    assert workflow["report_ids"] == []
    assert any("xau_vol_oi_missing_reference" in item for item in workflow["missing_data_actions"])
    assert evidence["xau_summary"]["missing_report_id"] == "xau_vol_oi_missing_reference"
