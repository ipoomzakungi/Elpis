from fastapi.testclient import TestClient

from src.main import app
from tests.helpers.test_backtest_validation_data import write_validation_features


def test_validation_concentration_endpoint_returns_coverage_and_concentration_sections(
    isolated_data_paths,
):
    feature_path = isolated_data_paths / "processed" / "coverage_features.parquet"
    write_validation_features(feature_path, row_count=18)

    client = TestClient(app)
    response = client.post(
        "/api/v1/backtests/validation/run",
        json=_validation_payload(feature_path),
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    validation_run_id = payload["validation_run_id"]
    concentration_response = client.get(
        f"/api/v1/backtests/validation/{validation_run_id}/concentration"
    )

    assert concentration_response.status_code == 200
    body = concentration_response.json()
    assert body["validation_run_id"] == validation_run_id
    assert body["regime_coverage"]["bar_counts"]["RANGE"] > 0
    assert "UNKNOWN" in body["regime_coverage"]["bar_counts"]
    assert "top_1_profit_contribution_pct" in body["concentration_report"]
    assert "max_consecutive_losses" in body["concentration_report"]


def test_validation_concentration_endpoint_returns_structured_missing_report_error():
    client = TestClient(app)

    response = client.get("/api/v1/backtests/validation/missing-run/concentration")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def _validation_payload(feature_path) -> dict:
    return {
        "base_config": {
            "symbol": "BTCUSDT",
            "provider": "binance",
            "timeframe": "15m",
            "feature_path": str(feature_path),
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
        "include_real_data_check": False,
    }
