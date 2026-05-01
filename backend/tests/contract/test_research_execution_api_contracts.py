from fastapi.testclient import TestClient

from src.main import app
from src.xau.orchestration import XauReportOrchestrator
from tests.helpers.research_data import write_synthetic_research_features
from tests.helpers.test_xau_data import sample_xau_report_request, write_sample_xau_options_csv


def test_research_execution_list_placeholder_returns_empty_runs(isolated_data_paths):
    client = TestClient(app)

    response = client.get("/api/v1/research/execution-runs")

    assert response.status_code == 200
    assert response.json() == {"runs": []}


def test_research_execution_run_creates_crypto_preflight_evidence(isolated_data_paths):
    feature_path = isolated_data_paths / "processed" / "btcusdt_15m_features.parquet"
    from tests.helpers.test_research_execution_data import write_synthetic_execution_features

    write_synthetic_execution_features(feature_path, rows=12)
    client = TestClient(app)

    response = client.post(
        "/api/v1/research/execution-runs",
        json={
            "name": "crypto evidence contract",
            "research_only_acknowledged": True,
            "crypto": {
                "enabled": True,
                "primary_assets": ["BTCUSDT", "ETHUSDT"],
                "processed_feature_root": str(isolated_data_paths / "processed"),
                "existing_research_run_id": "research_existing_crypto",
            },
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["execution_run_id"].startswith("rex_")
    assert body["name"] == "crypto evidence contract"
    assert body["evidence_summary"]["status"] == "partial"
    assert body["evidence_summary"]["decision"] == "refine"
    assert body["evidence_summary"]["crypto_summary"]["completed_asset_count"] == 1
    assert body["evidence_summary"]["crypto_summary"]["blocked_asset_count"] == 1
    assert body["evidence_summary"]["workflow_results"][0]["report_ids"] == [
        "research_existing_crypto"
    ]
    assert any(
        "ETHUSDT" in instruction
        for instruction in body["evidence_summary"]["missing_data_checklist"]
    )

    list_response = client.get("/api/v1/research/execution-runs")
    assert list_response.status_code == 200
    listed = list_response.json()["runs"]
    assert len(listed) == 1
    assert listed[0]["execution_run_id"] == body["execution_run_id"]
    assert listed[0]["status"] == "partial"

    detail_response = client.get(f"/api/v1/research/execution-runs/{body['execution_run_id']}")
    assert detail_response.status_code == 200
    assert detail_response.json()["execution_run_id"] == body["execution_run_id"]


def test_research_execution_run_returns_proxy_limitations_in_contract(isolated_data_paths):
    processed_root = isolated_data_paths / "processed"
    write_synthetic_research_features(
        processed_root / "gld_1d_features.parquet",
        symbol="GLD",
        rows=7,
        include_regime=False,
        include_open_interest=False,
        include_funding=False,
    )
    client = TestClient(app)

    response = client.post(
        "/api/v1/research/execution-runs",
        json={
            "name": "proxy limitation contract",
            "research_only_acknowledged": True,
            "proxy": {
                "enabled": True,
                "assets": ["GLD"],
                "provider": "yahoo_finance",
                "processed_feature_root": str(processed_root),
                "required_capabilities": ["ohlcv", "open_interest", "funding", "iv"],
            },
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["evidence_summary"]["status"] == "completed"
    assert body["evidence_summary"]["proxy_summary"]["ready_assets"] == ["GLD"]
    assert body["evidence_summary"]["proxy_summary"]["unsupported_capabilities_by_asset"][
        "GLD"
    ] == ["open_interest", "funding", "iv"]
    assert any(
        "OHLCV-only" in limitation
        for limitation in body["evidence_summary"]["proxy_summary"]["limitations_by_asset"]["GLD"]
    )

    evidence_response = client.get(
        f"/api/v1/research/execution-runs/{body['execution_run_id']}/evidence"
    )
    assert evidence_response.status_code == 200
    evidence = evidence_response.json()
    assert evidence["proxy_summary"]["ready_assets"] == ["GLD"]
    assert any("OHLCV-only" in limitation for limitation in evidence["limitations"])


def test_research_execution_detail_returns_structured_not_found():
    client = TestClient(app)

    response = client.get("/api/v1/research/execution-runs/missing-run")

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert "missing-run" in body["error"]["message"]


def test_research_execution_evidence_returns_structured_not_found():
    client = TestClient(app)

    response = client.get("/api/v1/research/execution-runs/missing-run/evidence")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_research_execution_missing_data_returns_structured_not_found():
    client = TestClient(app)

    response = client.get("/api/v1/research/execution-runs/missing-run/missing-data")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_research_execution_evidence_and_missing_data_endpoints_return_final_sections(
    isolated_data_paths,
):
    feature_path = isolated_data_paths / "processed" / "btcusdt_15m_features.parquet"
    from tests.helpers.test_research_execution_data import write_synthetic_execution_features

    write_synthetic_execution_features(feature_path, rows=10)
    client = TestClient(app)

    create_response = client.post(
        "/api/v1/research/execution-runs",
        json={
            "name": "final evidence contract",
            "research_only_acknowledged": True,
            "crypto": {
                "enabled": True,
                "primary_assets": ["BTCUSDT", "ETHUSDT"],
                "processed_feature_root": str(isolated_data_paths / "processed"),
                "existing_research_run_id": "research_contract_ready",
            },
        },
    )

    assert create_response.status_code == 201
    run_id = create_response.json()["execution_run_id"]

    evidence_response = client.get(f"/api/v1/research/execution-runs/{run_id}/evidence")
    assert evidence_response.status_code == 200
    evidence = evidence_response.json()
    assert evidence["execution_run_id"] == run_id
    assert evidence["status"] == "partial"
    assert evidence["decision"] == "refine"
    assert evidence["workflow_results"][0]["report_ids"] == ["research_contract_ready"]
    assert evidence["workflow_results"][0]["decision"] == "refine"
    assert any(
        "research decisions only" in warning
        for warning in evidence["research_only_warnings"]
    )
    assert any("ETHUSDT" in action for action in evidence["missing_data_checklist"])

    missing_response = client.get(f"/api/v1/research/execution-runs/{run_id}/missing-data")
    assert missing_response.status_code == 200
    missing_data = missing_response.json()
    assert missing_data["execution_run_id"] == run_id
    assert missing_data["missing_data_checklist"] == evidence["missing_data_checklist"]


def test_research_execution_run_accepts_existing_xau_report_reference(isolated_data_paths):
    source_path = isolated_data_paths / "raw" / "xau" / "gold_options.csv"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    write_sample_xau_options_csv(source_path)
    existing_report = XauReportOrchestrator().run(sample_xau_report_request(source_path))
    client = TestClient(app)

    response = client.post(
        "/api/v1/research/execution-runs",
        json={
            "name": "existing xau evidence contract",
            "research_only_acknowledged": True,
            "xau": {
                "enabled": True,
                "existing_xau_report_id": existing_report.report_id,
            },
        },
    )

    assert response.status_code == 201
    body = response.json()
    xau_summary = body["evidence_summary"]["xau_summary"]
    workflow = next(
        result
        for result in body["evidence_summary"]["workflow_results"]
        if result["workflow_type"] == "xau_vol_oi"
    )
    assert body["evidence_summary"]["status"] == "completed"
    assert workflow["report_ids"] == [existing_report.report_id]
    assert xau_summary["linked_xau_report_id"] == existing_report.report_id
    assert xau_summary["wall_count"] == existing_report.wall_count
    assert xau_summary["zone_count"] == existing_report.zone_count


def test_research_execution_run_labels_missing_xau_report_reference(isolated_data_paths):
    client = TestClient(app)

    response = client.post(
        "/api/v1/research/execution-runs",
        json={
            "name": "missing xau report contract",
            "research_only_acknowledged": True,
            "xau": {
                "enabled": True,
                "existing_xau_report_id": "xau_vol_oi_missing_contract",
            },
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["evidence_summary"]["status"] == "blocked"
    assert body["evidence_summary"]["decision"] == "data_blocked"
    assert body["evidence_summary"]["xau_summary"]["missing_report_id"] == (
        "xau_vol_oi_missing_contract"
    )
    assert any(
        "xau_vol_oi_missing_contract" in item
        for item in body["evidence_summary"]["missing_data_checklist"]
    )
