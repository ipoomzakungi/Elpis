from src.models.xau_reaction import (
    XauConfidenceLabel,
    XauOpenFlipState,
    XauOpenRegimeInput,
    XauOpenRegimeResult,
    XauOpenSide,
    XauOpenSupportResistance,
)


def evaluate_open_regime(input_data: XauOpenRegimeInput) -> XauOpenRegimeResult:
    """Evaluate the session open as a research-only tactical boundary."""

    if input_data.session_open is None or input_data.current_price is None:
        return XauOpenRegimeResult(
            open_side=XauOpenSide.UNKNOWN,
            open_distance_points=None,
            open_flip_state=XauOpenFlipState.UNKNOWN,
            open_as_support_or_resistance=XauOpenSupportResistance.UNKNOWN,
            confidence_label=XauConfidenceLabel.UNKNOWN,
            notes=["Session open and current price are required for open-regime context."],
        )

    open_side = _open_side(input_data.current_price, input_data.session_open)
    open_distance = abs(input_data.current_price - input_data.session_open)
    flip_state = _flip_state(input_data)
    support_resistance = _support_resistance(open_side)
    notes = [
        "Session open is treated as a research context boundary, not a signal.",
        f"Current price is {open_side.value.replace('_', ' ')}.",
    ]
    if flip_state == XauOpenFlipState.CROSSED_WITHOUT_ACCEPTANCE:
        notes.append(
            "Price crossed the open after the initial move but has not accepted beyond it."
        )
    elif flip_state == XauOpenFlipState.ACCEPTED_FLIP:
        notes.append("Open flip requires acceptance beyond the open and is marked as accepted.")

    return XauOpenRegimeResult(
        open_side=open_side,
        open_distance_points=open_distance,
        open_flip_state=flip_state,
        open_as_support_or_resistance=support_resistance,
        confidence_label=XauConfidenceLabel.MEDIUM
        if flip_state == XauOpenFlipState.CROSSED_WITHOUT_ACCEPTANCE
        else XauConfidenceLabel.HIGH,
        notes=notes,
    )


def _open_side(current_price: float, session_open: float) -> XauOpenSide:
    if current_price > session_open:
        return XauOpenSide.ABOVE_OPEN
    if current_price < session_open:
        return XauOpenSide.BELOW_OPEN
    return XauOpenSide.AT_OPEN


def _flip_state(input_data: XauOpenRegimeInput) -> XauOpenFlipState:
    if input_data.crossed_open_after_initial_move is None:
        return XauOpenFlipState.UNKNOWN
    if not input_data.crossed_open_after_initial_move:
        return XauOpenFlipState.NO_FLIP
    if input_data.acceptance_beyond_open:
        return XauOpenFlipState.ACCEPTED_FLIP
    return XauOpenFlipState.CROSSED_WITHOUT_ACCEPTANCE


def _support_resistance(open_side: XauOpenSide) -> XauOpenSupportResistance:
    if open_side == XauOpenSide.ABOVE_OPEN:
        return XauOpenSupportResistance.SUPPORT_TEST
    if open_side == XauOpenSide.BELOW_OPEN:
        return XauOpenSupportResistance.RESISTANCE_TEST
    if open_side == XauOpenSide.AT_OPEN:
        return XauOpenSupportResistance.BOUNDARY
    return XauOpenSupportResistance.UNKNOWN
