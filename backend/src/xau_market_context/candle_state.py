from __future__ import annotations

from src.models.xau_market_context import (
    XauCandleReactionState,
    XauCandleState,
    XauPriceBar,
)


def buffer_points(
    *,
    configured_min_buffer: float,
    atr_5m: float | None = None,
    buffer_atr_fraction: float = 0.25,
    spread_buffer: float | None = None,
) -> float:
    candidates = [configured_min_buffer]
    if atr_5m is not None:
        candidates.append(atr_5m * buffer_atr_fraction)
    if spread_buffer is not None:
        candidates.append(spread_buffer)
    return max(candidates)


def classify_candle_state(
    *,
    level: float | None,
    candle: XauPriceBar | None,
    next_bar: XauPriceBar | None = None,
    buffer: float,
) -> XauCandleState:
    if level is None or candle is None:
        return XauCandleState(
            level=level or 1.0,
            timeframe=candle.timeframe if candle else "unavailable",
            state=XauCandleReactionState.UNAVAILABLE,
            close=candle.close if candle else None,
            high=candle.high if candle else None,
            low=candle.low if candle else None,
            buffer_points=buffer,
            evidence=["Mapped level or last closed candle is unavailable."],
        )

    upper = level + buffer
    lower = level - buffer
    close_above = candle.close > upper
    close_below = candle.close < lower
    next_holds_above = next_bar is None or next_bar.open > upper
    next_holds_below = next_bar is None or next_bar.open < lower

    if close_above and not next_holds_above:
        state = XauCandleReactionState.FAILED_BREAKOUT
        evidence = ["Candle closed above the wall buffer but the next bar did not hold above."]
    elif close_below and not next_holds_below:
        state = XauCandleReactionState.FAILED_BREAKOUT
        evidence = ["Candle closed below the wall buffer but the next bar did not hold below."]
    elif close_above:
        state = XauCandleReactionState.ACCEPTED_ABOVE
        evidence = ["Candle closed above the wall buffer."]
    elif close_below:
        state = XauCandleReactionState.ACCEPTED_BELOW
        evidence = ["Candle closed below the wall buffer."]
    elif candle.high > upper and candle.close < level:
        state = XauCandleReactionState.REJECTED_ABOVE
        evidence = ["Candle wicked above the wall buffer and closed back below the wall."]
    elif candle.low < lower and candle.close > level:
        state = XauCandleReactionState.REJECTED_BELOW
        evidence = ["Candle wicked below the wall buffer and closed back above the wall."]
    elif candle.low <= level <= candle.high:
        state = XauCandleReactionState.CLOSE_BACK_INSIDE
        evidence = ["Candle traded through the wall but closed inside the buffer."]
    else:
        state = XauCandleReactionState.NEUTRAL
        evidence = ["No acceptance or rejection context was confirmed."]

    return XauCandleState(
        level=level,
        timeframe=candle.timeframe,
        state=state,
        close=candle.close,
        high=candle.high,
        low=candle.low,
        buffer_points=buffer,
        evidence=evidence,
    )

