from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from src.models.xau_market_context import XauCandleReactionState, XauPriceBar
from src.xau_market_context.candle_state import classify_candle_state


def test_candle_rejected_below_after_wick_below_wall_and_close_above() -> None:
    state = classify_candle_state(
        level=4080,
        candle=_bar(high=4082, low=4076, close=4081),
        buffer=2,
    )

    assert state.state == XauCandleReactionState.REJECTED_BELOW
    assert "wicked below" in state.evidence[0]


def test_candle_accepted_above_after_close_above_wall_plus_buffer() -> None:
    state = classify_candle_state(
        level=4080,
        candle=_bar(high=4085, low=4079, close=4083),
        buffer=2,
    )

    assert state.state == XauCandleReactionState.ACCEPTED_ABOVE
    assert state.close == 4083


def _bar(*, high: float, low: float, close: float) -> XauPriceBar:
    return XauPriceBar(
        timestamp=datetime(2026, 6, 29, 14, 15, tzinfo=ZoneInfo("Asia/Bangkok")),
        open=4080,
        high=high,
        low=low,
        close=close,
        symbol="XAUUSD",
        timeframe="1m",
    )

