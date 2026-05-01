from fastapi.testclient import TestClient

from src.main import app
from src.research_execution.report_store import ResearchExecutionReportStore
from tests.helpers.test_xau_data import sample_xau_report_request, write_sample_xau_options_csv


def test_xau_execution_run_generates_report_and_evidence_summary(isolated_data_paths):
    options_path = isolated_data_paths / "raw" / "xau" / "gold_options.csv"
    options_path.parent.mkdir(parents=True, exist_ok=True)
    write_sample_xau_options_csv(options_path)
    xau_request = sample_xau_report_request(options_path).model_dump(mode="json")
    client = TestClient(app)

    response = client.post(
        "/api/v1/research/execution-runs",
        json={
            "name": "xau evidence",
            "research_only_acknowledged": True,
            "xau": {
                "enabled": True,
                "options_oi_file_path": xau_request["options_oi_file_path"],
                "spot_reference": xau_request["spot_reference"],
                "futures_reference": xau_request["futures_reference"],
                "volatility_snapshot": xau_request["volatility_snapshot"],
                "include_2sd_range": True,
            },
        },
    )

    assert response.status_code == 201
    payload = response.json()
    run_id = payload["execution_run_id"]
    evidence = payload["evidence_summary"]
    xau_summary = evidence["xau_summary"]
    assert evidence["status"] == "completed"
    assert xau_summary["status"] == "completed"
    assert len(xau_summary["report_ids"]) == 1
    assert xau_summary["linked_xau_report_id"] == xau_summary["report_ids"][0]
    assert xau_summary["source_validation_summary"]["is_valid"] is True
    assert xau_summary["source_validation_summary"]["accepted_row_count"] == 2
    assert xau_summary["basis_snapshot_status"] == "available"
    assert xau_summary["basis_snapshot"]["basis_source"] == "computed"
    assert xau_summary["basis_snapshot"]["mapping_available"] is True
    assert xau_summary["expected_range_status"] == "available"
    assert xau_summary["expected_range"]["source"] == "iv"
    assert xau_summary["wall_count"] > 0
    assert xau_summary["zone_count"] > 0
    assert any("research annotations" in warning for warning in xau_summary["warnings"])
    assert any("Yahoo Finance GC=F and GLD" in item for item in xau_summary["limitations"])

    loaded = ResearchExecutionReportStore().read_run(run_id)
    assert loaded.evidence_summary is not None
    assert loaded.evidence_summary.xau_summary["linked_xau_report_id"] == (
        xau_summary["linked_xau_report_id"]
    )

    evidence_response = client.get(f"/api/v1/research/execution-runs/{run_id}/evidence")
    assert evidence_response.status_code == 200
    assert evidence_response.json()["xau_summary"]["wall_count"] == xau_summary["wall_count"]
