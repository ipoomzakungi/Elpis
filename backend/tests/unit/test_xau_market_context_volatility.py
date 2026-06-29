from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from src.models.xau_market_context import XauPriceBar
from src.xau_market_context.volatility import calculate_atr, realized_volatility


def test_atr_calculation_from_simple_ohlc_bars() -> None:
    bars = [
        _bar(0, 100, 105, 95, 102),
        _bar(1, 102, 108, 101, 107),
        _bar(2, 107, 110, 106, 108),
    ]

    assert calculate_atr(bars, period=3) == pytest.approx((10 + 7 + 4) / 3)


def test_realized_vol_returns_null_for_insufficient_data() -> None:
    bars = [_bar(0, 100, 101, 99, 100), _bar(1, 100, 101, 99, 100.5)]

    assert realized_volatility(
        bars,
        start_time=bars[0].timestamp,
        end_time=bars[-1].timestamp,
    ) is None


def _bar(
    minute: int,
    open_price: float,
    high: float,
    low: float,
    close: float,
) -> XauPriceBar:
    return XauPriceBar(
        timestamp=datetime(2026, 6, 29, 14, 0, tzinfo=ZoneInfo("Asia/Bangkok"))
        + timedelta(minutes=minute),
        open=open_price,
        high=high,
        low=low,
        close=close,
        symbol="XAUUSD",
        timeframe="1m",
    )

