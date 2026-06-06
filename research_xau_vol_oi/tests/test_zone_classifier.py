from datetime import UTC, datetime

from research_xau_vol_oi.config import Signal
from research_xau_vol_oi.zone_classifier import classify_bar


def _bar(**overrides):
    base = {
        "timestamp": datetime(2026, 5, 21, 10, 0, tzinfo=UTC),
        "open": 2400.0,
        "high": 2404.0,
        "low": 2396.0,
        "close": 2400.0,
        "one_sd_remaining": 20.0,
        "sigma_position": 0.0,
        "data_quality_state": "VALID",
    }
    base.update(overrides)
    return base


def _wall(**overrides):
    base = {
        "timestamp": datetime(2026, 5, 21, 9, 0, tzinfo=UTC),
        "wall_id": "wall_2405",
        "wall_level": 2405.0,
        "wall_score": 0.30,
        "wall_side": "resistance",
        "basis": 7.0,
        "basis_available": True,
        "largest_near_expiry_wall": False,
        "low_oi_gap_to_next_wall": False,
        "dte": 2,
    }
    base.update(overrides)
    return base


def test_no_trade_when_basis_missing() -> None:
    event = classify_bar(_bar(), wall=_wall(basis=None, basis_available=False))

    assert event["signal"] == Signal.NO_TRADE.value


def test_no_trade_middle_inside_1sd_without_near_wall() -> None:
    event = classify_bar(_bar(close=2400.0, sigma_position=0.2), wall=_wall(wall_level=2440.0))

    assert event["signal"] == Signal.NO_TRADE_MIDDLE.value


def test_watch_wall_when_price_approaches_strong_wall() -> None:
    event = classify_bar(_bar(close=2403.0, high=2404.0), wall=_wall(wall_level=2405.0))

    assert event["signal"] == Signal.WATCH_WALL.value


def test_fade_wall_short_on_resistance_rejection() -> None:
    event = classify_bar(
        _bar(high=2410.0, close=2401.0, sigma_position=1.3),
        wall=_wall(wall_level=2405.0, wall_side="resistance"),
    )

    assert event["signal"] == Signal.FADE_WALL_SHORT.value


def test_fade_wall_long_on_support_rejection() -> None:
    event = classify_bar(
        _bar(low=2390.0, close=2399.0, sigma_position=-1.3),
        wall=_wall(wall_level=2395.0, wall_side="support"),
    )

    assert event["signal"] == Signal.FADE_WALL_LONG.value


def test_break_wall_long_requires_next_bar_hold() -> None:
    event = classify_bar(
        _bar(close=2410.0, high=2411.0, sigma_position=1.2),
        wall=_wall(wall_level=2405.0, wall_side="resistance"),
        next_bar=_bar(close=2408.0),
    )

    assert event["signal"] == Signal.BREAK_WALL_LONG.value


def test_break_wall_short_requires_next_bar_hold() -> None:
    event = classify_bar(
        _bar(close=2390.0, low=2389.0, sigma_position=-1.2),
        wall=_wall(wall_level=2395.0, wall_side="support"),
        next_bar=_bar(close=2392.0),
    )

    assert event["signal"] == Signal.BREAK_WALL_SHORT.value


def test_pin_risk_near_largest_near_expiry_wall() -> None:
    event = classify_bar(
        _bar(close=2404.0, high=2404.5, low=2401.0),
        wall=_wall(wall_level=2405.0, largest_near_expiry_wall=True, wall_side="mixed"),
    )

    assert event["signal"] == Signal.PIN_RISK.value


def test_squeeze_risk_in_low_oi_gap() -> None:
    event = classify_bar(
        _bar(close=2404.0, high=2404.5, low=2401.0),
        wall=_wall(
            wall_level=2405.0,
            wall_side="mixed",
            low_oi_gap_to_next_wall=True,
            largest_near_expiry_wall=False,
        ),
    )

    assert event["signal"] == Signal.SQUEEZE_RISK.value
