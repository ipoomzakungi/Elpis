from src.models.xau_reaction import (
    XauAcceptanceDirection,
    XauAcceptanceInput,
    XauAcceptanceResult,
    XauConfidenceLabel,
)


def classify_acceptance(input_data: XauAcceptanceInput) -> XauAcceptanceResult:
    """Classify candle acceptance or rejection at a wall as research context."""

    _validate_ohlc_order(input_data.high, input_data.low, input_data.close)
    lower_buffer, upper_buffer = _wall_bounds(
        wall_level=input_data.wall_level,
        buffer_points=input_data.buffer_points,
    )

    close_above = input_data.close > upper_buffer
    close_below = input_data.close < lower_buffer
    wick_above = input_data.high > upper_buffer
    wick_below = input_data.low < lower_buffer
    next_holds_above = (
        input_data.next_bar_open is not None and input_data.next_bar_open > upper_buffer
    )
    next_holds_below = (
        input_data.next_bar_open is not None and input_data.next_bar_open < lower_buffer
    )

    accepted_beyond_wall = close_above or close_below
    confirmed_breakout = (close_above and next_holds_above) or (close_below and next_holds_below)
    wick_rejection = (wick_above and not close_above) or (wick_below and not close_below)
    failed_breakout = _failed_breakout(
        accepted_beyond_wall=accepted_beyond_wall,
        close_above=close_above,
        close_below=close_below,
        next_holds_above=next_holds_above,
        next_holds_below=next_holds_below,
        next_bar_open=input_data.next_bar_open,
    )
    direction = _direction(
        close_above=close_above,
        close_below=close_below,
        wick_above=wick_above,
        wick_below=wick_below,
    )
    notes = _notes(
        accepted_beyond_wall=accepted_beyond_wall,
        confirmed_breakout=confirmed_breakout,
        wick_rejection=wick_rejection,
        failed_breakout=failed_breakout,
        next_bar_open=input_data.next_bar_open,
    )

    return XauAcceptanceResult(
        wall_id=input_data.wall_id,
        zone_id=input_data.zone_id,
        accepted_beyond_wall=accepted_beyond_wall,
        wick_rejection=wick_rejection,
        failed_breakout=failed_breakout,
        confirmed_breakout=confirmed_breakout,
        direction=direction,
        confidence_label=XauConfidenceLabel.HIGH
        if confirmed_breakout or wick_rejection
        else XauConfidenceLabel.MEDIUM,
        notes=notes,
    )


def _validate_ohlc_order(high: float, low: float, close: float) -> None:
    if high < low:
        raise ValueError("high must be greater than or equal to low")
    if not low <= close <= high:
        raise ValueError("close must be inside the high-low range")


def _wall_bounds(*, wall_level: float, buffer_points: float) -> tuple[float, float]:
    if buffer_points < 0:
        raise ValueError("buffer_points must be greater than or equal to 0")
    return wall_level - buffer_points, wall_level + buffer_points


def _failed_breakout(
    *,
    accepted_beyond_wall: bool,
    close_above: bool,
    close_below: bool,
    next_holds_above: bool,
    next_holds_below: bool,
    next_bar_open: float | None,
) -> bool:
    if not accepted_beyond_wall or next_bar_open is None:
        return False
    return (close_above and not next_holds_above) or (close_below and not next_holds_below)


def _direction(
    *,
    close_above: bool,
    close_below: bool,
    wick_above: bool,
    wick_below: bool,
) -> XauAcceptanceDirection:
    if close_above or (wick_above and not wick_below):
        return XauAcceptanceDirection.ABOVE
    if close_below or (wick_below and not wick_above):
        return XauAcceptanceDirection.BELOW
    return XauAcceptanceDirection.UNKNOWN


def _notes(
    *,
    accepted_beyond_wall: bool,
    confirmed_breakout: bool,
    wick_rejection: bool,
    failed_breakout: bool,
    next_bar_open: float | None,
) -> list[str]:
    notes = ["Candle reaction is a research annotation only."]
    if confirmed_breakout:
        notes.append("Close beyond the wall plus next-bar hold confirms breakout context.")
    elif failed_breakout:
        notes.append("Close beyond the wall failed to hold on the next bar.")
    elif wick_rejection:
        notes.append("Wick through the wall did not close beyond the wall buffer.")
    elif accepted_beyond_wall and next_bar_open is None:
        notes.append("Close is beyond the wall, but next-bar hold is unavailable.")
    else:
        notes.append("No wall acceptance or rejection context is confirmed.")
    return notes
