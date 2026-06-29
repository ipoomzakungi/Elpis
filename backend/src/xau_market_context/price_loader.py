from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from src.models.xau_market_context import XauPriceBar

_TIMESTAMP_COLUMNS = ("timestamp", "time", "datetime", "date")
_OPEN_COLUMNS = ("open", "bid_open", "ask_open")
_HIGH_COLUMNS = ("high", "bid_high", "ask_high")
_LOW_COLUMNS = ("low", "bid_low", "ask_low")
_CLOSE_COLUMNS = ("close", "bid_close", "ask_close")
_VOLUME_COLUMNS = ("volume", "tick_volume")


def load_price_bars(
    path: Path,
    *,
    default_symbol: str = "XAUUSD",
    default_timeframe: str = "1m",
    default_timezone: str = "Asia/Bangkok",
) -> list[XauPriceBar]:
    rows = _read_rows(path)
    bars = [
        _bar_from_mapping(
            row,
            default_symbol=default_symbol,
            default_timeframe=default_timeframe,
            default_timezone=default_timezone,
        )
        for row in rows
    ]
    return sorted(bars, key=lambda bar: bar.timestamp)


def latest_bar_at_or_before(
    bars: list[XauPriceBar],
    timestamp: datetime,
) -> XauPriceBar | None:
    timestamp = _ensure_aware(timestamp)
    candidates = [bar for bar in bars if bar.timestamp <= timestamp]
    return candidates[-1] if candidates else None


def _read_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload.get("bars", payload) if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            raise ValueError("JSON price bars must be a list or an object with a bars list")
        return [dict(row) for row in rows]
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _bar_from_mapping(
    row: dict[str, Any],
    *,
    default_symbol: str,
    default_timeframe: str,
    default_timezone: str,
) -> XauPriceBar:
    timestamp_value = _first(row, _TIMESTAMP_COLUMNS)
    if timestamp_value is None:
        raise ValueError("price bars require timestamp/time/date")
    return XauPriceBar(
        timestamp=_parse_datetime(timestamp_value, default_timezone),
        open=_required_float(row, _OPEN_COLUMNS, "open"),
        high=_required_float(row, _HIGH_COLUMNS, "high"),
        low=_required_float(row, _LOW_COLUMNS, "low"),
        close=_required_float(row, _CLOSE_COLUMNS, "close"),
        volume=_optional_float(_first(row, _VOLUME_COLUMNS)),
        symbol=str(_first(row, ("symbol",)) or default_symbol),
        timeframe=str(_first(row, ("timeframe", "interval")) or default_timeframe),
    )


def _first(row: dict[str, Any], names: tuple[str, ...]) -> Any:
    normalized = {str(key).strip().lower(): value for key, value in row.items()}
    for name in names:
        value = normalized.get(name)
        if value not in (None, ""):
            return value
    return None


def _required_float(row: dict[str, Any], names: tuple[str, ...], label: str) -> float:
    value = _first(row, names)
    if value is None:
        raise ValueError(f"price bars require {label}")
    return float(value)


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _parse_datetime(value: Any, default_timezone: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=ZoneInfo(default_timezone))
    return parsed.astimezone(ZoneInfo(default_timezone))


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value

