from datetime import UTC, datetime, timedelta

import polars as pl

from research_xau_vol_oi.config import Signal
from research_xau_vol_oi.signal_score import score_signal_event, score_signal_events


def _bar(**overrides):
    base = {
        "timestamp": datetime(2026, 5, 21, 10, 0, tzinfo=UTC),
        "open": 2398.0,
        "high": 2410.0,
        "low": 2396.0,
        "close": 2400.0,
        "session_open": 2395.0,
        "one_sd_remaining": 20.0,
        "sigma_position": 1.2,
        "data_quality_state": "VALID",
        "rv_percent": 12.0,
        "volume": 200.0,
        "vol_regime": "BALANCED",
        "wall_level": 2405.0,
        "wall_score": 0.45,
        "distance_to_nearest_wall": 5.0,
        "freshness_weight": 1.6,
        "dte_weight": 0.9,
        "wall_side": "resistance",
        "basis_available": True,
        "next_wall_distance": 30.0,
    }
    base.update(overrides)
    return base


def _event(signal=Signal.FADE_WALL_SHORT.value, **overrides):
    timestamp = datetime(2026, 5, 21, 10, 0, tzinfo=UTC)
    base = {
        "event_timestamp": timestamp,
        "source_bar_timestamp": timestamp,
        "available_wall_timestamp": timestamp - timedelta(minutes=15),
        "signal": signal,
        "reason": "resistance_rejection",
        "close": 2400.0,
        "sigma_position": 1.2,
        "wall_level": 2405.0,
        "wall_score": 0.45,
        "distance_to_nearest_wall": 5.0,
        "freshness_weight": 1.6,
        "dte_weight": 0.9,
        "wall_side": "resistance",
        "basis_available": True,
    }
    base.update(overrides)
    return base


def test_bad_data_quality_forces_no_trade() -> None:
    result = score_signal_event(
        _event(),
        bar=_bar(data_quality_state="MISSING_IV"),
    )

    assert result.signal_label == Signal.NO_TRADE.value
    assert result.signal_score == 0
    assert result.trade_direction == "NONE"
    assert "bad data quality" in result.risk_warning


def test_middle_1sd_blocks_low_score_reversal() -> None:
    result = score_signal_event(
        _event(wall_score=0.20),
        bar=_bar(sigma_position=0.4, wall_score=0.20),
    )

    assert result.signal_label == Signal.NO_TRADE_MIDDLE.value
    assert result.trade_direction == "NONE"
    assert "inside middle 1SD" in result.risk_warning


def test_middle_1sd_allows_high_score_confirmed_reversal() -> None:
    result = score_signal_event(
        _event(wall_score=0.50),
        bar=_bar(sigma_position=0.4, wall_score=0.50),
    )

    assert result.signal_label == Signal.FADE_WALL_SHORT.value
    assert result.trade_direction == "SHORT"
    assert result.signal_score >= 60
    assert result.invalidation_level == 2407.0


def test_reversal_requires_rejection() -> None:
    result = score_signal_event(
        _event(),
        bar=_bar(high=2403.0, close=2402.0),
    )

    assert result.signal_label == Signal.NO_TRADE.value
    assert "rejection not confirmed" in result.risk_warning


def test_breakout_requires_acceptance_and_vol_expansion() -> None:
    result = score_signal_event(
        _event(Signal.BREAK_WALL_LONG.value, reason="accepted_above_resistance"),
        bar=_bar(close=2410.0, high=2412.0, rv_percent=12.0),
        previous_bar=_bar(timestamp=datetime(2026, 5, 21, 9, 45, tzinfo=UTC), rv_percent=11.5),
        next_bar=_bar(timestamp=datetime(2026, 5, 21, 10, 15, tzinfo=UTC), close=2411.0),
    )

    assert result.signal_label == Signal.NO_TRADE.value
    assert "volatility expansion not confirmed" in result.risk_warning

    confirmed = score_signal_event(
        _event(Signal.BREAK_WALL_LONG.value, reason="accepted_above_resistance"),
        bar=_bar(close=2410.0, high=2412.0, rv_percent=13.0, vol_regime="RV_PREMIUM"),
        previous_bar=_bar(timestamp=datetime(2026, 5, 21, 9, 45, tzinfo=UTC), rv_percent=10.0),
        next_bar=_bar(timestamp=datetime(2026, 5, 21, 10, 15, tzinfo=UTC), close=2411.0),
    )

    assert confirmed.signal_label == Signal.BREAK_WALL_LONG.value
    assert confirmed.trade_direction == "LONG"


def test_extreme_sigma_adds_smaller_size_warning() -> None:
    result = score_signal_event(
        _event(
            Signal.BREAK_WALL_SHORT.value,
            reason="accepted_below_support",
            wall_side="support",
            wall_level=2395.0,
        ),
        bar=_bar(
            close=2390.0,
            low=2388.0,
            sigma_position=-2.2,
            rv_percent=13.0,
            vol_regime="RV_PREMIUM",
            wall_side="support",
            wall_level=2395.0,
            wall_score=0.50,
        ),
        previous_bar=_bar(timestamp=datetime(2026, 5, 21, 9, 45, tzinfo=UTC), rv_percent=10.0),
        next_bar=_bar(timestamp=datetime(2026, 5, 21, 10, 15, tzinfo=UTC), close=2390.0),
    )

    assert result.signal_label == Signal.BREAK_WALL_SHORT.value
    assert "smaller size warning" in result.risk_warning


def test_pin_risk_warns_not_to_chase_direction() -> None:
    result = score_signal_event(
        _event(Signal.PIN_RISK.value, reason="largest_near_expiry_wall_near_price"),
        bar=_bar(wall_side="mixed"),
    )

    assert result.signal_label == Signal.PIN_RISK.value
    assert result.trade_direction == "NONE"
    assert result.signal_score <= 45
    assert "do not chase direction" in result.risk_warning


def test_score_signal_events_returns_bounded_scores() -> None:
    features = pl.DataFrame(
        [
            _bar(timestamp=datetime(2026, 5, 21, 9, 45, tzinfo=UTC), rv_percent=10.0),
            _bar(),
            _bar(timestamp=datetime(2026, 5, 21, 10, 15, tzinfo=UTC), close=2398.0),
        ]
    )
    events = pl.DataFrame([_event()])

    scores = score_signal_events(features, events)

    assert scores.height == 1
    assert scores.get_column("signal_score").min() >= 0
    assert scores.get_column("signal_score").max() <= 100
    assert {
        "signal_label",
        "signal_score",
        "trade_direction",
        "entry_reason",
        "invalidation_level",
        "target_level",
        "risk_warning",
    }.issubset(scores.columns)
