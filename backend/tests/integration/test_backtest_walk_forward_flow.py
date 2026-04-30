import polars as pl
from fastapi.testclient import TestClient

from src.main import app
from src.models.backtest import ValidationSplitStatus
from tests.helpers.test_backtest_validation_data import write_validation_features


def test_validation_flow_persists_walk_forward_artifacts(isolated_data_paths):
    feature_path = isolated_data_paths / "processed" / "walk_forward_features.parquet"
    write_validation_features(feature_path, row_count=18)

    client = TestClient(app)
    response = client.post(
        "/api/v1/backtests/validation/run",
        json=_validation_payload(feature_path, split_count=3, minimum_rows_per_split=4),
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    validation_run_id = payload["validation_run_id"]
    run_path = isolated_data_paths / "reports" / validation_run_id

    assert payload["walk_forward_results"]
    assert [row["row_count"] for row in payload["walk_forward_results"]] == [6, 6, 6]
    assert {row["status"] for row in payload["walk_forward_results"]} == {
        ValidationSplitStatus.EVALUATED.value
    }
    assert all(row["trade_count"] >= 0 for row in payload["walk_forward_results"])
    assert (run_path / "validation_walk_forward.parquet").exists()

    frame = pl.read_parquet(run_path / "validation_walk_forward.parquet")
    assert frame.height == len(payload["walk_forward_results"])
    assert frame["split_id"].to_list() == ["split_001", "split_002", "split_003"]

    walk_forward_response = client.get(
        f"/api/v1/backtests/validation/{validation_run_id}/walk-forward"
    )
    assert walk_forward_response.status_code == 200
    assert walk_forward_response.json()["data"] == payload["walk_forward_results"]


def test_validation_flow_marks_insufficient_walk_forward_windows(isolated_data_paths):
    feature_path = isolated_data_paths / "processed" / "insufficient_walk_forward_features.parquet"
    write_validation_features(feature_path, row_count=12)

    client = TestClient(app)
    response = client.post(
        "/api/v1/backtests/validation/run",
        json=_validation_payload(feature_path, split_count=3, minimum_rows_per_split=10),
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    rows = payload["walk_forward_results"]

    assert [row["row_count"] for row in rows] == [4, 4, 4]
    assert {row["status"] for row in rows} == {ValidationSplitStatus.INSUFFICIENT_DATA.value}
    assert all(row["trade_count"] == 0 for row in rows)
    assert all("fewer than the configured minimum" in row["notes"][0] for row in rows)


def _validation_payload(feature_path, split_count: int, minimum_rows_per_split: int) -> dict:
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
        "walk_forward": {
            "split_count": split_count,
            "minimum_rows_per_split": minimum_rows_per_split,
        },
        "include_real_data_check": False,
    }
