from fastapi.testclient import TestClient

from src.main import app
from tests.helpers.research_data import write_synthetic_research_features


def test_research_run_list_and_detail_contracts(isolated_data_paths):
    feature_path = isolated_data_paths / "processed" / "btcusdt_15m_features.parquet"
    write_synthetic_research_features(feature_path, rows=16)

    client = TestClient(app)
    run_response = client.post("/api/v1/research/runs", json=_mixed_research_payload(feature_path))

    assert run_response.status_code == 200, run_response.text
    run_body = run_response.json()
    research_run_id = run_body["research_run_id"]
    assert run_body["status"] == "partial"
    assert run_body["completed_count"] == 1
    assert run_body["blocked_count"] == 1
    assert len(run_body["assets"]) == 2
    assert {artifact["artifact_type"] for artifact in run_body["artifacts"]} >= {
        "research_metadata",
        "research_config",
        "research_asset_summary",
        "research_comparison",
        "research_report_json",
        "research_report_markdown",
    }

    list_response = client.get("/api/v1/research/runs")
    assert list_response.status_code == 200
    listed = [
        row for row in list_response.json()["runs"] if row["research_run_id"] == research_run_id
    ]
    assert len(listed) == 1
    assert listed[0]["completed_count"] == 1
    assert listed[0]["blocked_count"] == 1
    assert listed[0]["asset_count"] == 2

    detail_response = client.get(f"/api/v1/research/runs/{research_run_id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["research_run_id"] == research_run_id

    assets_response = client.get(f"/api/v1/research/runs/{research_run_id}/assets")
    assert assets_response.status_code == 200
    assets = assets_response.json()["data"]
    assert [asset["symbol"] for asset in assets] == ["BTCUSDT", "SPY"]
    assert assets[0]["status"] == "completed"
    assert assets[1]["status"] == "blocked"
    assert assets[1]["preflight"]["instructions"]

    comparison_response = client.get(f"/api/v1/research/runs/{research_run_id}/comparison")
    assert comparison_response.status_code == 200
    comparison_rows = comparison_response.json()["data"]
    assert comparison_rows
    assert {row["symbol"] for row in comparison_rows} == {"BTCUSDT"}
    assert {row["category"] for row in comparison_rows} >= {"strategy", "baseline"}
    assert all("mode" in row for row in comparison_rows)


def test_research_comparison_endpoint_returns_structured_missing_report_error():
    client = TestClient(app)

    response = client.get("/api/v1/research/runs/missing-run/comparison")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_research_detail_endpoint_returns_structured_missing_report_error():
    client = TestClient(app)

    response = client.get("/api/v1/research/runs/missing-run")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
    assert "Research run 'missing-run' was not found" in response.json()["error"]["message"]


def _mixed_research_payload(feature_path) -> dict:
    return {
        "assets": [
            {
                "symbol": "BTCUSDT",
                "provider": "binance",
                "asset_class": "crypto",
                "timeframe": "15m",
                "feature_path": str(feature_path),
                "required_feature_groups": [
                    "ohlcv",
                    "regime",
                    "oi",
                    "funding",
                    "volume_confirmation",
                ],
            },
            {
                "symbol": "SPY",
                "provider": "yahoo_finance",
                "asset_class": "equity_proxy",
                "timeframe": "1d",
                "required_feature_groups": ["ohlcv", "regime"],
            },
        ],
        "report_format": "both",
    }
