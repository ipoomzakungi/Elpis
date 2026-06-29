from __future__ import annotations

from datetime import datetime, timedelta
from math import log, sqrt

from src.models.xau_market_context import (
    XauPriceBar,
    XauSessionOpen,
    XauVolatilitySnapshot,
    XauVolatilityStatus,
)


def calculate_atr(bars: list[XauPriceBar], *, period: int = 14) -> float | None:
    if period <= 0:
        raise ValueError("period must be positive")
    ordered = sorted(bars, key=lambda item: item.timestamp)
    if len(ordered) < period:
        return None
    ranges: list[float] = []
    previous_close: float | None = None
    for bar in ordered:
        if previous_close is None:
            true_range = bar.high - bar.low
        else:
            true_range = max(
                bar.high - bar.low,
                abs(bar.high - previous_close),
                abs(bar.low - previous_close),
            )
        ranges.append(true_range)
        previous_close = bar.close
    return sum(ranges[-period:]) / period


def realized_volatility(
    bars: list[XauPriceBar],
    *,
    start_time: datetime,
    end_time: datetime,
) -> float | None:
    selected = [
        bar
        for bar in sorted(bars, key=lambda item: item.timestamp)
        if start_time <= bar.timestamp <= end_time
    ]
    if len(selected) < 3:
        return None
    returns = [
        log(current.close / previous.close)
        for previous, current in zip(selected, selected[1:], strict=False)
        if previous.close > 0 and current.close > 0
    ]
    if len(returns) < 2:
        return None
    return sqrt(sum(value * value for value in returns))


def build_volatility_snapshot(
    *,
    bars: list[XauPriceBar],
    current_timestamp: datetime,
    active_session: XauSessionOpen | None = None,
    period: int = 14,
) -> XauVolatilitySnapshot:
    bars_until_now = [bar for bar in bars if bar.timestamp <= current_timestamp]
    atr_5m = calculate_atr(_resample_bars(bars_until_now, minutes=5), period=period)
    atr_15m = calculate_atr(_resample_bars(bars_until_now, minutes=15), period=period)
    atr_1h = calculate_atr(_resample_bars(bars_until_now, minutes=60), period=period)
    rv_30m = realized_volatility(
        bars_until_now,
        start_time=current_timestamp - timedelta(minutes=30),
        end_time=current_timestamp,
    )
    rv_session = None
    if active_session is not None and active_session.open_time <= current_timestamp:
        rv_session = realized_volatility(
            bars_until_now,
            start_time=active_session.open_time,
            end_time=current_timestamp,
        )

    warnings: list[str] = []
    values = [atr_5m, atr_15m, atr_1h, rv_30m, rv_session]
    if all(value is None for value in values):
        status = XauVolatilityStatus.UNAVAILABLE
        warnings.append("Insufficient traded-side bars for ATR and realized volatility.")
    elif any(value is None for value in values):
        status = XauVolatilityStatus.PARTIAL
        warnings.append("Some ATR/RV fields are unavailable because bar coverage is insufficient.")
    else:
        status = XauVolatilityStatus.AVAILABLE

    return XauVolatilitySnapshot(
        atr_5m=atr_5m,
        atr_15m=atr_15m,
        atr_1h=atr_1h,
        realized_vol_30m=rv_30m,
        realized_vol_session=rv_session,
        status=status,
        warnings=warnings,
    )


def _resample_bars(bars: list[XauPriceBar], *, minutes: int) -> list[XauPriceBar]:
    if not bars:
        return []
    buckets: dict[datetime, list[XauPriceBar]] = {}
    for bar in sorted(bars, key=lambda item: item.timestamp):
        bucket_minute = (bar.timestamp.minute // minutes) * minutes
        bucket_time = bar.timestamp.replace(minute=bucket_minute, second=0, microsecond=0)
        buckets.setdefault(bucket_time, []).append(bar)
    resampled: list[XauPriceBar] = []
    for bucket_time, bucket_bars in sorted(buckets.items(), key=lambda item: item[0]):
        first = bucket_bars[0]
        last = bucket_bars[-1]
        volume_values = [bar.volume for bar in bucket_bars if bar.volume is not None]
        resampled.append(
            XauPriceBar(
                timestamp=bucket_time,
                open=first.open,
                high=max(bar.high for bar in bucket_bars),
                low=min(bar.low for bar in bucket_bars),
                close=last.close,
                volume=sum(volume_values) if volume_values else None,
                symbol=first.symbol,
                timeframe=f"{minutes}m" if minutes < 60 else "1h",
            )
        )
    return resampled
