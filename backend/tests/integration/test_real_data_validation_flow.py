from fastapi.testclient import TestClient

from src.main import app
from tests.helpers.test_backtest_validation_data import write_validation_features


def test_real_data_validation_uses_existing_processed_features(isolated_data_paths):
    feature_path = isolated_data_paths / "processed" / "btcusdt_15m_features.parquet"
    write_validation_features(feature_path, row_count=20)

    client = TestClient(app)
    response = client.post(
        "/api/v1/backtests/validation/run",
        json=_real_data_payload(),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "completed"
    assert body["data_identity"]["source_kind"] == "processed_features"
    assert body["data_identity"]["feature_path"].endswith("btcusdt_15m_features.parquet")
    assert body["data_identity"]["row_count"] == 20
    assert body["data_identity"]["first_timestamp"]
    assert body["data_identity"]["last_timestamp"]
    assert body["data_identity"]["content_hash"]
    assert any("Historical simulation outputs only" in warning for warning in body["warnings"])
    assert any("data source" in warning.lower() for warning in body["warnings"])


def test_real_data_validation_returns_missing_data_instructions(isolated_data_paths):
    client = TestClient(app)

    response = client.post(
        "/api/v1/backtests/validation/run",
        json=_real_data_payload(),
    )

    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "NOT_FOUND"
    assert "Processed features not found for BTCUSDT 15m" in error["message"]
    messages = " ".join(detail["message"] for detail in error["details"])
    assert "POST /api/v1/download" in messages
    assert "POST /api/v1/process" in messages
    assert "btcusdt_15m_features.parquet" in messages


def _real_data_payload() -> dict:
    return {
        "base_config": {
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
                    "mode": "breakout",
                    "enabled": True,
                    "allow_short": True,
                    "atr_buffer": 1.0,
                    "risk_reward_multiple": 1.5,
                }
            ],
            "baselines": ["buy_hold", "no_trade"],
            "report_format": "json",
        },
        "capital_sizing": {
            "buy_hold_capital_fraction": 1.0,
            "buy_hold_sizing_mode": "capital_fraction",
            "active_risk_per_trade": 0.01,
            "leverage": 1,
            "notional_cap_enabled": True,
        },
        "stress_profiles": ["normal"],
        "sensitivity_grid": {
            "grid_entry_threshold": [0.1],
            "atr_stop_buffer": [1.0],
            "breakout_risk_reward_multiple": [1.5],
            "fee_slippage_profile": ["normal"],
        },
        "walk_forward": {"split_count": 3, "minimum_rows_per_split": 4},
        "include_real_data_check": True,
    }
