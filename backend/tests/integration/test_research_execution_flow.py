from fastapi.testclient import TestClient

from src.main import app
from tests.helpers.research_data import write_synthetic_research_features
from tests.helpers.test_research_execution_data import write_synthetic_execution_features
from tests.helpers.test_xau_data import sample_xau_report_request, write_sample_xau_options_csv


def test_mixed_workflow_execution_produces_final_evidence_summary(isolated_data_paths):
    processed_root = isolated_data_paths / "processed"
    write_synthetic_execution_features(
        processed_root / "btcusdt_15m_features.parquet",
        symbol="BTCUSDT",
        rows=18,
    )
    write_synthetic_research_features(
        processed_root / "spy_1d_features.parquet",
        symbol="SPY",
        rows=9,
        include_regime=False,
        include_open_interest=False,
        include_funding=False,
    )
    options_path = isolated_data_paths / "raw" / "xau" / "gold_options.csv"
    options_path.parent.mkdir(parents=True, exist_ok=True)
    write_sample_xau_options_csv(options_path)
    xau_request = sample_xau_report_request(options_path).model_dump(mode="json")
    client = TestClient(app)

    response = client.post(
        "/api/v1/research/execution-runs",
        json={
            "name": "final mixed evidence",
            "research_only_acknowledged": True,
            "crypto": {
                "enabled": True,
                "primary_assets": ["BTCUSDT", "ETHUSDT"],
                "timeframe": "15m",
                "processed_feature_root": str(processed_root),
                "existing_research_run_id": "research_crypto_ready",
            },
            "proxy": {
                "enabled": True,
                "assets": ["SPY"],
                "provider": "yahoo_finance",
                "timeframe": "1d",
                "processed_feature_root": str(processed_root),
                "required_capabilities": ["ohlcv", "open_interest", "funding"],
                "existing_research_run_id": "research_proxy_ready",
            },
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
    evidence = payload["evidence_summary"]
    run_id = payload["execution_run_id"]

    assert evidence["status"] == "partial"
    assert evidence["decision"] == "refine"
    assert evidence["crypto_summary"]["ready_assets"] == ["BTCUSDT"]
    assert evidence["crypto_summary"]["blocked_assets"] == ["ETHUSDT"]
    assert evidence["proxy_summary"]["ready_assets"] == ["SPY"]
    assert evidence["xau_summary"]["wall_count"] > 0
    assert evidence["xau_summary"]["zone_count"] > 0
    assert len(evidence["workflow_results"]) == 3
    assert any("ETHUSDT" in action for action in evidence["missing_data_checklist"])
    assert any("OHLCV-only" in limitation for limitation in evidence["limitations"])
    assert any(
        "do not claim profitability" in warning
        for warning in evidence["research_only_warnings"]
    )

    report_ids = {
        workflow["workflow_type"]: workflow["report_ids"]
        for workflow in evidence["workflow_results"]
    }
    assert report_ids["crypto_multi_asset"] == ["research_crypto_ready"]
    assert report_ids["proxy_ohlcv"] == ["research_proxy_ready"]
    assert report_ids["xau_vol_oi"] == [evidence["xau_summary"]["linked_xau_report_id"]]

    detail = client.get(f"/api/v1/research/execution-runs/{run_id}")
    assert detail.status_code == 200
    assert detail.json()["evidence_summary"]["decision"] == "refine"

    evidence_response = client.get(f"/api/v1/research/execution-runs/{run_id}/evidence")
    assert evidence_response.status_code == 200
    assert evidence_response.json()["workflow_results"][0]["decision"] in {
        "continue",
        "refine",
        "data_blocked",
        "inconclusive",
        "reject",
    }

    missing_response = client.get(f"/api/v1/research/execution-runs/{run_id}/missing-data")
    assert missing_response.status_code == 200
    assert any("ETHUSDT" in action for action in missing_response.json()["missing_data_checklist"])
