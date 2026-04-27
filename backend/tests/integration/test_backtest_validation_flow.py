import polars as pl
from fastapi.testclient import TestClient

from src.main import app

from tests.helpers.test_backtest_validation_data import write_validation_features


def test_validation_flow_persists_stress_and_sensitivity_artifacts(isolated_data_paths):
    feature_path = isolated_data_paths / "processed" / "validation_flow_features.parquet"
    write_validation_features(feature_path, row_count=16)

    client = TestClient(app)
    response = client.post("/api/v1/backtests/validation/run", json=_validation_payload(feature_path))

    assert response.status_code == 200, response.text
    payload = response.json()
    validation_run_id = payload["validation_run_id"]
    run_path = isolated_data_paths / "reports" / validation_run_id

    assert payload["status"] == "completed"
    assert payload["stress_results"]
    assert payload["sensitivity_results"]
    assert (run_path / "validation_stress.parquet").exists()
    assert (run_path / "validation_sensitivity.parquet").exists()
    assert (run_path / "validation_report.json").exists()
    assert (run_path / "validation_report.md").exists()

    stress_frame = pl.read_parquet(run_path / "validation_stress.parquet")
    sensitivity_frame = pl.read_parquet(run_path / "validation_sensitivity.parquet")
    assert stress_frame.height == len(payload["stress_results"])
    assert sensitivity_frame.height == len(payload["sensitivity_results"])

    stress_response = client.get(f"/api/v1/backtests/validation/{validation_run_id}/stress")
    sensitivity_response = client.get(f"/api/v1/backtests/validation/{validation_run_id}/sensitivity")
    assert stress_response.status_code == 200
    assert sensitivity_response.status_code == 200
    assert stress_response.json()["data"] == payload["stress_results"]
    assert sensitivity_response.json()["data"] == payload["sensitivity_results"]


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
        "stress_profiles": ["normal", "high_fee", "high_slippage", "worst_reasonable_cost"],
        "sensitivity_grid": {
            "grid_entry_threshold": [0.1],
            "atr_stop_buffer": [1.0],
            "breakout_risk_reward_multiple": [1.5, 2.0],
            "fee_slippage_profile": ["normal"],
        },
        "walk_forward": {"split_count": 3, "minimum_rows_per_split": 20},
        "include_real_data_check": False,
    }