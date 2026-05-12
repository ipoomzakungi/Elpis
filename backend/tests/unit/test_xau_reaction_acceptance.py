import pytest
from pydantic import ValidationError

from src.models.xau_reaction import (
    XauAcceptanceDirection,
    XauAcceptanceInput,
)
from src.xau_reaction.acceptance import classify_acceptance


def test_classify_acceptance_marks_wick_rejection_without_breakout():
    result = classify_acceptance(
        XauAcceptanceInput(
            wall_level=2400.0,
            high=2408.0,
            low=2399.0,
            close=2399.0,
            next_bar_open=2398.0,
            buffer_points=2.0,
        )
    )

    assert result.wick_rejection is True
    assert result.accepted_beyond_wall is False
    assert result.confirmed_breakout is False
    assert result.failed_breakout is False
    assert result.direction == XauAcceptanceDirection.ABOVE


def test_classify_acceptance_marks_confirmed_breakout_on_close_and_next_bar_hold():
    result = classify_acceptance(
        XauAcceptanceInput(
            wall_id="call_wall_2400",
            wall_level=2400.0,
            high=2410.0,
            low=2397.0,
            close=2405.0,
            next_bar_open=2404.0,
            buffer_points=2.0,
        )
    )

    assert result.wall_id == "call_wall_2400"
    assert result.accepted_beyond_wall is True
    assert result.confirmed_breakout is True
    assert result.failed_breakout is False
    assert result.direction == XauAcceptanceDirection.ABOVE


def test_classify_acceptance_marks_failed_breakout_when_next_bar_does_not_hold():
    result = classify_acceptance(
        XauAcceptanceInput(
            wall_level=2400.0,
            high=2408.0,
            low=2398.0,
            close=2405.0,
            next_bar_open=2401.0,
            buffer_points=2.0,
        )
    )

    assert result.accepted_beyond_wall is True
    assert result.confirmed_breakout is False
    assert result.failed_breakout is True
    assert result.wick_rejection is False


def test_classify_acceptance_returns_neutral_without_acceptance_or_rejection():
    result = classify_acceptance(
        XauAcceptanceInput(
            wall_level=2400.0,
            high=2401.0,
            low=2399.0,
            close=2400.0,
            next_bar_open=2400.5,
            buffer_points=2.0,
        )
    )

    assert result.accepted_beyond_wall is False
    assert result.wick_rejection is False
    assert result.confirmed_breakout is False
    assert result.failed_breakout is False
    assert result.direction == XauAcceptanceDirection.UNKNOWN


def test_classify_acceptance_handles_missing_next_bar_open_without_confirmation():
    result = classify_acceptance(
        XauAcceptanceInput(
            wall_level=2400.0,
            high=2405.0,
            low=2399.0,
            close=2403.0,
            buffer_points=2.0,
        )
    )

    assert result.accepted_beyond_wall is True
    assert result.confirmed_breakout is False
    assert result.failed_breakout is False
    assert any("next-bar hold is unavailable" in note for note in result.notes)


def test_classify_acceptance_supports_zero_buffer():
    result = classify_acceptance(
        XauAcceptanceInput(
            wall_level=2400.0,
            high=2402.0,
            low=2399.0,
            close=2401.0,
            next_bar_open=2401.5,
            buffer_points=0.0,
        )
    )

    assert result.accepted_beyond_wall is True
    assert result.confirmed_breakout is True


def test_acceptance_input_rejects_invalid_ohlc_order():
    with pytest.raises(ValidationError):
        XauAcceptanceInput(
            wall_level=2400.0,
            high=2398.0,
            low=2402.0,
            close=2400.0,
        )
