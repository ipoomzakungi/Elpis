from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from src.models.xau_market_context import XauPriceBar
from src.models.xau_price_provider import (
    XauPriceProviderKind,
    XauPriceProviderQuality,
    XauResolvedPrice,
)
from src.xau_market_context.price_provider import unavailable_price

YFINANCE_RESEARCH_WARNING = (
    "Yahoo/yfinance data is research fallback only and not execution-grade."
)
YFINANCE_TERMS_WARNING = (
    "Yahoo/yfinance is not affiliated with Yahoo and data rights must follow Yahoo terms."
)


def fetch_yfinance_price(
    *,
    symbol: str,
    interval: str = "1m",
    period: str = "1d",
    timezone: str = "Asia/Bangkok",
) -> XauResolvedPrice:
    bars = fetch_yfinance_bars(
        symbol=symbol,
        interval=interval,
        period=period,
        timezone=timezone,
    )
    if not bars:
        return unavailable_price(
            symbol=symbol,
            provider=XauPriceProviderKind.YFINANCE,
            warning=f"No yfinance bars were available for {symbol}.",
            limitation=YFINANCE_RESEARCH_WARNING,
        )
    latest = bars[-1]
    return XauResolvedPrice(
        symbol=symbol,
        price=latest.close,
        timestamp=latest.timestamp,
        provider=XauPriceProviderKind.YFINANCE,
        provider_quality=XauPriceProviderQuality.RESEARCH_FALLBACK,
        warnings=[YFINANCE_RESEARCH_WARNING, YFINANCE_TERMS_WARNING],
        limitations=[
            "Yahoo/yfinance is a delayed/inconsistent research fallback, not a broker feed."
        ],
    )


def fetch_yfinance_bars(
    *,
    symbol: str,
    interval: str = "1m",
    period: str = "1d",
    timezone: str = "Asia/Bangkok",
) -> list[XauPriceBar]:
    try:
        import yfinance as yf
    except ImportError:
        return []

    ticker = yf.Ticker(symbol)
    frame = ticker.history(period=period, interval=interval)
    if frame is None or getattr(frame, "empty", True):
        return []
    target_tz = ZoneInfo(timezone)
    bars: list[XauPriceBar] = []
    for index, row in frame.iterrows():
        close = _float_from_row(row, "Close")
        open_price = _float_from_row(row, "Open") or close
        high = _float_from_row(row, "High") or close
        low = _float_from_row(row, "Low") or close
        if close is None or open_price is None or high is None or low is None:
            continue
        timestamp = _timestamp_from_index(index, target_tz)
        bars.append(
            XauPriceBar(
                timestamp=timestamp,
                open=open_price,
                high=max(high, open_price, close),
                low=min(low, open_price, close),
                close=close,
                volume=_float_from_row(row, "Volume"),
                symbol=symbol,
                timeframe=interval,
            )
        )
    return sorted(bars, key=lambda item: item.timestamp)


def save_yfinance_bars(
    *,
    bars: list[XauPriceBar],
    output_dir: Path,
    symbol: str,
    interval: str,
) -> Path | None:
    if not bars:
        return None
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_symbol = "".join(char for char in symbol if char.isalnum() or char in "-_")
    stamp = datetime.now(ZoneInfo("UTC")).strftime("%Y%m%dT%H%M%S")
    path = output_dir / f"yfinance_{safe_symbol}_{interval}_{stamp}.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "symbol",
                "timeframe",
            ],
        )
        writer.writeheader()
        for bar in bars:
            writer.writerow(
                {
                    "timestamp": bar.timestamp.isoformat(),
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                    "symbol": bar.symbol,
                    "timeframe": bar.timeframe,
                }
            )
    return path


def _timestamp_from_index(value: Any, timezone: ZoneInfo) -> datetime:
    if hasattr(value, "to_pydatetime"):
        parsed = value.to_pydatetime()
    elif isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone)
    return parsed.astimezone(timezone)


def _float_from_row(row: Any, key: str) -> float | None:
    try:
        value = row[key]
    except (KeyError, TypeError):
        return None
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None
