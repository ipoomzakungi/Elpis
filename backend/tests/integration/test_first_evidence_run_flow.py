from fastapi.testclient import TestClient

from src.data_sources.report_store import DataSourceFirstRunReportStore
from src.main import app
from src.research_execution.report_store import ResearchExecutionReportStore
from tests.helpers.research_data import write_synthetic_research_features


def test_first_evidence_run_flow_links_execution_and_preserves_missing_data(
    isolated_data_paths,
):
    processed_root = isolated_data_paths / "processed"
    write_synthetic_research_features(
        processed_root / "btcusdt_15m_features.parquet",
        symbol="BTCUSDT",
        rows=14,
    )
    write_synthetic_research_features(
        processed_root / "spy_1d_features.parquet",
        symbol="SPY",
        rows=9,
        include_regime=False,
        include_open_interest=False,
        include_funding=False,
    )
    client = TestClient(app)

    response = client.post(
        "/api/v1/evidence/first-run",
        json={
            "name": "first evidence mixed flow",
            "research_only_acknowledged": True,
            "use_existing_research_report_ids": ["research_crypto_existing"],
            "preflight": {
                "crypto_assets": ["BTCUSDT", "ETHUSDT"],
                "proxy_assets": ["SPY", "GC=F"],
                "processed_feature_root": str(processed_root),
                "xau_options_oi_file_path": str(
                    isolated_data_paths / "raw" / "xau" / "missing_options.csv"
                ),
                "requested_capabilities": [
                    "ohlcv",
                    "open_interest",
                    "funding",
                    "iv",
                    "gold_options_oi",
                    "futures_oi",
                    "xauusd_spot_execution",
                ],
                "research_only_acknowledged": True,
            },
        },
    )

    assert response.status_code == 201
    payload = response.json()
    first_run_id = payload["first_run_id"]
    execution_run_id = payload["execution_run_id"]

    assert payload["status"] == "partial"
    assert payload["decision"] == "refine"
    assert payload["linked_research_report_ids"] == ["research_crypto_existing"]
    assert payload["preflight_result"]["crypto_results"][0]["status"] == "ready"
    assert payload["preflight_result"]["crypto_results"][1]["status"] == "blocked"
    assert payload["preflight_result"]["proxy_results"][0]["status"] == "ready"
    assert payload["preflight_result"]["proxy_results"][1]["status"] == "blocked"
    assert payload["preflight_result"]["xau_result"]["status"] == "blocked"
    assert any(
        action["asset"] == "ETHUSDT"
        for action in payload["missing_data_actions"]
    )
    assert any(
        "XAU" in action["title"] or action["asset"] == "XAU"
        for action in payload["missing_data_actions"]
    )
    assert any(
        "research" in warning.lower()
        for warning in payload["research_only_warnings"]
    )

    wrapper = DataSourceFirstRunReportStore().read_first_run(first_run_id)
    assert wrapper.execution_run_id == execution_run_id
    execution = ResearchExecutionReportStore().read_run(execution_run_id)
    assert execution.evidence_summary is not None
    assert execution.evidence_summary.crypto_summary["ready_assets"] == ["BTCUSDT"]
    assert execution.evidence_summary.crypto_summary["blocked_assets"] == ["ETHUSDT"]
    assert execution.evidence_summary.proxy_summary["ready_assets"] == ["SPY"]
    assert execution.evidence_summary.proxy_summary["blocked_assets"] == ["GC=F"]

    detail = client.get(f"/api/v1/evidence/first-run/{first_run_id}")
    assert detail.status_code == 200
    assert detail.json()["execution_run_id"] == execution_run_id

    missing = client.get("/api/v1/evidence/first-run/not-a-real-run")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "NOT_FOUND"
