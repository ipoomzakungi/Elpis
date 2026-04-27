from fastapi.testclient import TestClient

from src.main import app
from src.repositories.parquet_repo import ParquetRepository


def _run_payload() -> dict:
    return {
        "symbol": "BTCUSDT",
        "provider": "binance",
        "timeframe": "15m",
        "initial_equity": 10000,
        "assumptions": {
            "fee_rate": 0.0004,
            "slippage_rate": 0.0002,
            "risk_per_trade": 0.01,
            "max_positions": 1,
            "allow_short": True,
            "allow_compounding": False,
            "leverage": 1,
            "ambiguous_intrabar_policy": "stop_first",
        },
        "strategies": [
            {
                "mode": "grid_range",
                "enabled": True,
                "allow_short": False,
                "atr_buffer": 1.0,
                "risk_reward_multiple": 1.0,
            }
        ],
        "baselines": [],
        "report_format": "json",
    }


def test_run_backtest_endpoint_contract_success(sample_backtest_features):
    ParquetRepository().save_features(sample_backtest_features, symbol="BTCUSDT", interval="15m")

    with TestClient(app) as client:
        response = client.post("/api/v1/backtests/run", json=_run_payload())

    payload = response.json()
    assert response.status_code == 200
    assert payload["status"] == "completed"
    assert payload["symbol"] == "BTCUSDT"
    assert payload["timeframe"] == "15m"
    assert payload["metrics"]["number_of_trades"] >= 1
    assert any(artifact["artifact_type"] == "trades" for artifact in payload["artifacts"])
    assert any("historical simulation" in warning for warning in payload["warnings"])


def test_run_backtest_endpoint_contract_missing_features():
    with TestClient(app) as client:
        response = client.post("/api/v1/backtests/run", json=_run_payload())

    payload = response.json()
    assert response.status_code == 404
    assert payload["error"]["code"] == "NOT_FOUND"
    assert "Processed features not found" in payload["error"]["message"]


def test_run_backtest_endpoint_contract_invalid_config(sample_backtest_features):
    ParquetRepository().save_features(sample_backtest_features, symbol="BTCUSDT", interval="15m")
    payload = _run_payload()
    payload["assumptions"]["leverage"] = 2

    with TestClient(app) as client:
        response = client.post("/api/v1/backtests/run", json=payload)

    body = response.json()
    assert response.status_code == 400
    assert body["error"]["code"] == "VALIDATION_ERROR"


def test_run_backtest_endpoint_contract_no_trade_response(sample_backtest_features):
    ParquetRepository().save_features(sample_backtest_features, symbol="BTCUSDT", interval="15m")
    payload = _run_payload()
    payload["strategies"] = []
    payload["baselines"] = ["no_trade"]

    with TestClient(app) as client:
        response = client.post("/api/v1/backtests/run", json=payload)

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "completed"
    assert body["metrics"]["number_of_trades"] == 0
    assert any("No trades" in note for note in body["metrics"]["notes"])


def test_backtest_report_read_endpoints_contract(sample_backtest_features):
    ParquetRepository().save_features(sample_backtest_features, symbol="BTCUSDT", interval="15m")

    with TestClient(app) as client:
        run_response = client.post("/api/v1/backtests/run", json=_run_payload())
        run_id = run_response.json()["run_id"]

        list_response = client.get("/api/v1/backtests")
        detail_response = client.get(f"/api/v1/backtests/{run_id}")
        trades_response = client.get(f"/api/v1/backtests/{run_id}/trades?limit=1&offset=0")
        metrics_response = client.get(f"/api/v1/backtests/{run_id}/metrics")
        equity_response = client.get(f"/api/v1/backtests/{run_id}/equity")

    assert list_response.status_code == 200
    runs = list_response.json()["runs"]
    assert any(run["run_id"] == run_id for run in runs)
    assert runs[0]["strategy_modes"]

    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["run_id"] == run_id
    assert detail["artifacts"]
    assert detail["config"]["symbol"] == "BTCUSDT"

    assert trades_response.status_code == 200
    trades_payload = trades_response.json()
    assert trades_payload["meta"] == {"count": 1, "limit": 1, "offset": 0}
    assert trades_payload["data"][0]["run_id"] == run_id
    assert trades_payload["data"][0]["strategy_mode"] == "grid_range"

    assert metrics_response.status_code == 200
    metrics_payload = metrics_response.json()
    assert metrics_payload["run_id"] == run_id
    assert metrics_payload["summary"]["number_of_trades"] >= 1
    assert metrics_payload["return_by_strategy_mode"]

    assert equity_response.status_code == 200
    equity_payload = equity_response.json()
    assert equity_payload["run_id"] == run_id
    assert equity_payload["meta"]["count"] >= len(sample_backtest_features)
    assert equity_payload["data"][0]["strategy_mode"] == "grid_range"


def test_backtest_report_read_endpoints_contract_missing_run():
    with TestClient(app) as client:
        response = client.get("/api/v1/backtests/unknown_run")

    payload = response.json()
    assert response.status_code == 404
    assert payload["error"]["code"] == "NOT_FOUND"
    assert "unknown_run" in payload["error"]["message"]


def test_backtest_report_read_endpoints_contract_missing_artifact(
    sample_backtest_features,
    isolated_data_paths,
):
    ParquetRepository().save_features(sample_backtest_features, symbol="BTCUSDT", interval="15m")

    with TestClient(app) as client:
        run_response = client.post("/api/v1/backtests/run", json=_run_payload())
        run_id = run_response.json()["run_id"]

    metrics_path = isolated_data_paths / "reports" / run_id / "metrics.json"
    metrics_path.unlink()

    with TestClient(app) as client:
        response = client.get(f"/api/v1/backtests/{run_id}/metrics")

    payload = response.json()
    assert response.status_code == 404
    assert payload["error"]["code"] == "NOT_FOUND"
    assert run_id in payload["error"]["message"]
