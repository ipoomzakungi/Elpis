from fastapi.testclient import TestClient

from src.main import app
from src.research_execution.report_store import ResearchExecutionReportStore
from tests.helpers.research_data import write_synthetic_research_features


def test_proxy_execution_run_keeps_ready_and_limited_assets_visible(isolated_data_paths):
    processed_root = isolated_data_paths / "processed"
    write_synthetic_research_features(
        processed_root / "spy_1d_features.parquet",
        symbol="SPY",
        rows=10,
        include_regime=False,
        include_open_interest=False,
        include_funding=False,
    )
    client = TestClient(app)

    response = client.post(
        "/api/v1/research/execution-runs",
        json={
            "name": "proxy evidence",
            "research_only_acknowledged": True,
            "proxy": {
                "enabled": True,
                "assets": ["SPY", "GC=F"],
                "provider": "yahoo_finance",
                "timeframe": "1d",
                "processed_feature_root": str(processed_root),
                "required_capabilities": [
                    "ohlcv",
                    "open_interest",
                    "funding",
                    "gold_options_oi",
                    "futures_oi",
                    "iv",
                    "xauusd_spot_execution",
                ],
                "existing_research_run_id": "research_existing_proxy",
            },
        },
    )

    assert response.status_code == 201
    payload = response.json()
    run_id = payload["execution_run_id"]
    evidence = payload["evidence_summary"]
    proxy_summary = evidence["proxy_summary"]
    assert evidence["status"] == "partial"
    assert proxy_summary["ready_assets"] == ["SPY"]
    assert proxy_summary["blocked_assets"] == ["GC=F"]
    assert proxy_summary["provider"] == "yahoo_finance"
    assert proxy_summary["unsupported_capabilities_by_asset"]["SPY"] == [
        "open_interest",
        "funding",
        "gold_options_oi",
        "futures_oi",
        "iv",
        "xauusd_spot_execution",
    ]
    assert any(
        "OHLCV-only" in limitation
        for limitations in proxy_summary["limitations_by_asset"].values()
        for limitation in limitations
    )
    assert any(
        "not CME gold options OI" in limitation
        for limitation in proxy_summary["limitations_by_asset"]["GC=F"]
    )
    assert any("GC=F" in item for item in evidence["missing_data_checklist"])
    workflow = next(
        result
        for result in evidence["workflow_results"]
        if result["workflow_type"] == "proxy_ohlcv"
    )
    assert workflow["report_ids"] == ["research_existing_proxy"]
    assert workflow["status"] == "partial"
    assert any("Yahoo" in limitation for limitation in workflow["limitations"])

    loaded = ResearchExecutionReportStore().read_run(run_id)
    assert loaded.evidence_summary is not None
    assert loaded.evidence_summary.proxy_summary["blocked_assets"] == ["GC=F"]

    detail = client.get(f"/api/v1/research/execution-runs/{run_id}")
    assert detail.status_code == 200
    assert detail.json()["evidence_summary"]["proxy_summary"]["ready_assets"] == ["SPY"]

    evidence_response = client.get(f"/api/v1/research/execution-runs/{run_id}/evidence")
    assert evidence_response.status_code == 200
    assert evidence_response.json()["proxy_summary"]["blocked_assets"] == ["GC=F"]
