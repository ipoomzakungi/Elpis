from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from src.models.xau_market_context import XauPriceBar

HORIZONS = (5, 15, 30, 60, 120)


def label_events(
    events: list[dict[str, Any]],
    bars: list[XauPriceBar],
) -> list[dict[str, Any]]:
    labels = []
    for event in events:
        timestamp = datetime.fromisoformat(event["event_timestamp"])
        session_bars = [
            bar
            for bar in bars
            if bar.timestamp >= timestamp and bar.timestamp.date() == timestamp.date()
        ]
        if not session_bars:
            continue
        direction = _direction(event)
        entry = float(event["entry_price"])
        one_sd = float(event["one_sd_points"])
        row = {**event}
        for horizon in HORIZONS:
            window = [
                bar
                for bar in session_bars
                if bar.timestamp <= timestamp + timedelta(minutes=horizon)
            ]
            row.update(_window_labels(window, entry, direction, horizon))
        final = session_bars[-1]
        row["forward_return_eod"] = direction * (final.close - entry)
        favorable = entry + direction * 0.25 * one_sd
        adverse = entry - direction * 0.5 * one_sd
        first_favorable = _first_touch(session_bars, favorable, direction, favorable=True)
        first_adverse = _first_touch(session_bars, adverse, direction, favorable=False)
        row["reverted_0_25sd"] = first_favorable is not None
        row["reverted_0_50sd"] = (
            _first_touch(session_bars, entry + direction * 0.5 * one_sd, direction, favorable=True)
            is not None
        )
        row["continued_0_50sd"] = first_adverse is not None
        row["competing_outcome_first"] = _first_name(first_favorable, first_adverse)
        wall = event.get("oi_nearest_wall")
        row["reached_next_wall"] = (
            _touch_any(session_bars, float(wall)) if wall is not None else None
        )
        boundary = _event_boundary(event)
        row["returned_inside_boundary"] = _returned_inside(session_bars, boundary, event["side"])
        row["accepted_beyond_wall"] = event["event_type"] == "close_beyond_oi_wall"
        row["research_only"] = True
        row["signal_allowed"] = False
        labels.append(row)
    return labels


def _window_labels(
    bars: list[XauPriceBar], entry: float, direction: int, horizon: int
) -> dict[str, float | None]:
    if not bars:
        return {
            f"forward_return_{horizon}m": None,
            f"mfe_{horizon}m": None,
            f"mae_{horizon}m": None,
        }
    closes = direction * (bars[-1].close - entry)
    favorable = [
        direction * (bar.high - entry) if direction > 0 else direction * (bar.low - entry)
        for bar in bars
    ]
    adverse = [
        direction * (bar.low - entry) if direction > 0 else direction * (bar.high - entry)
        for bar in bars
    ]
    return {
        f"forward_return_{horizon}m": closes,
        f"mfe_{horizon}m": max(favorable),
        f"mae_{horizon}m": min(adverse),
    }


def _direction(event: dict[str, Any]) -> int:
    side = event["side"]
    if side == "pin":
        wall = event.get("oi_nearest_wall")
        return 1 if wall is not None and wall >= event["entry_price"] else -1
    return 1 if side in {"long_reversion", "long_breakout"} else -1


def _first_touch(
    bars: list[XauPriceBar], level: float, direction: int, *, favorable: bool
) -> datetime | None:
    for bar in bars:
        if favorable:
            touched = bar.high >= level if direction > 0 else bar.low <= level
        else:
            touched = bar.low <= level if direction > 0 else bar.high >= level
        if touched:
            return bar.timestamp
    return None


def _first_name(first: datetime | None, second: datetime | None) -> str | None:
    if first is None and second is None:
        return None
    if first is not None and second is not None and first == second:
        return "same_bar_ambiguous"
    return "favorable" if second is None or (first is not None and first < second) else "adverse"


def _touch_any(bars: list[XauPriceBar], level: float) -> bool:
    return any(bar.low <= level <= bar.high for bar in bars)


def _event_boundary(event: dict[str, Any]) -> float:
    return float(event["entry_price"])


def _returned_inside(bars: list[XauPriceBar], boundary: float, side: str) -> bool:
    if side in {"long_reversion", "short_breakout"}:
        return any(bar.close > boundary for bar in bars)
    if side in {"short_reversion", "long_breakout"}:
        return any(bar.close < boundary for bar in bars)
    return False
