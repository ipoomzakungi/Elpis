from src.models.xau_reaction import (
    XauOpenFlipState,
    XauOpenRegimeInput,
    XauOpenSide,
    XauOpenSupportResistance,
)
from src.xau_reaction.open_regime import evaluate_open_regime


def test_evaluate_open_regime_computes_open_side_and_distance():
    result = evaluate_open_regime(
        XauOpenRegimeInput(
            session_open=2400.0,
            current_price=2412.5,
            crossed_open_after_initial_move=False,
        )
    )

    assert result.open_side == XauOpenSide.ABOVE_OPEN
    assert result.open_distance_points == 12.5
    assert result.open_flip_state == XauOpenFlipState.NO_FLIP
    assert result.open_as_support_or_resistance == XauOpenSupportResistance.SUPPORT_TEST


def test_evaluate_open_regime_does_not_mark_full_flip_without_acceptance():
    result = evaluate_open_regime(
        XauOpenRegimeInput(
            session_open=2400.0,
            current_price=2394.0,
            crossed_open_after_initial_move=True,
            acceptance_beyond_open=False,
        )
    )

    assert result.open_side == XauOpenSide.BELOW_OPEN
    assert result.open_flip_state == XauOpenFlipState.CROSSED_WITHOUT_ACCEPTANCE
    assert result.open_as_support_or_resistance == XauOpenSupportResistance.RESISTANCE_TEST


def test_evaluate_open_regime_marks_accepted_flip_only_with_acceptance():
    result = evaluate_open_regime(
        XauOpenRegimeInput(
            session_open=2400.0,
            current_price=2408.0,
            crossed_open_after_initial_move=True,
            acceptance_beyond_open=True,
        )
    )

    assert result.open_flip_state == XauOpenFlipState.ACCEPTED_FLIP


def test_evaluate_open_regime_returns_unknown_when_open_or_price_is_missing():
    result = evaluate_open_regime(XauOpenRegimeInput(session_open=None, current_price=2400.0))

    assert result.open_side == XauOpenSide.UNKNOWN
    assert result.open_distance_points is None
    assert result.open_flip_state == XauOpenFlipState.UNKNOWN
    assert result.open_as_support_or_resistance == XauOpenSupportResistance.UNKNOWN
