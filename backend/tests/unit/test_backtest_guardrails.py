import pytest
from pydantic import ValidationError

from src.models.backtest import BacktestRunRequest


def _valid_payload() -> dict:
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
                "allow_short": True,
                "entry_threshold": 0.15,
                "atr_buffer": 1.0,
            }
        ],
        "baselines": ["buy_hold"],
        "report_format": "json",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("broker", "paper-broker"),
        ("api_key", "secret"),
        ("private_key", "secret"),
        ("live_trading", True),
        ("order_type", "market"),
    ],
)
def test_backtest_request_rejects_live_trading_fields(field: str, value):
    payload = _valid_payload()
    payload[field] = value

    with pytest.raises(ValidationError, match="live-trading fields are not allowed"):
        BacktestRunRequest.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("fee_rate", -0.0001),
        ("fee_rate", 0.2),
        ("slippage_rate", -0.0001),
        ("slippage_rate", 0.2),
        ("risk_per_trade", 0),
        ("risk_per_trade", 1.5),
        ("max_positions", 2),
        ("leverage", 2),
    ],
)
def test_backtest_request_rejects_invalid_assumptions(field: str, value):
    payload = _valid_payload()
    payload["assumptions"][field] = value

    with pytest.raises(ValidationError):
        BacktestRunRequest.model_validate(payload)


def test_backtest_request_rejects_unexpected_config_keys():
    payload = _valid_payload()
    payload["strategies"][0]["unexpected"] = "not allowed"

    with pytest.raises(ValidationError):
        BacktestRunRequest.model_validate(payload)


def test_backtest_request_rejects_nested_private_execution_fields():
    payload = _valid_payload()
    payload["strategies"][0]["exchange_secret"] = "secret"

    with pytest.raises(ValidationError, match="live-trading fields are not allowed"):
        BacktestRunRequest.model_validate(payload)