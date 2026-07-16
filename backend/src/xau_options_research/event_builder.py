from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from src.models.xau_market_context import XauPriceBar


def build_raw_events(
    checkpoints: list[dict[str, Any]],
    bars: list[XauPriceBar],
    *,
    timezone: str,
) -> list[dict[str, Any]]:
    zone = ZoneInfo(timezone)
    bars_by_date: dict[str, list[XauPriceBar]] = defaultdict(list)
    for bar in bars:
        bars_by_date[bar.timestamp.astimezone(zone).date().isoformat()].append(bar)
    for items in bars_by_date.values():
        items.sort(key=lambda item: item.timestamp)
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in checkpoints:
        grouped[(row["session_date"], row["planning_mode"])].append(row)
    events: list[dict[str, Any]] = []
    for (session_date, mode), rows in grouped.items():
        ordered = sorted(rows, key=lambda item: item["checkpoint_at"])
        session_bars = bars_by_date.get(session_date, [])
        for index, checkpoint in enumerate(ordered):
            start = datetime.fromisoformat(checkpoint["checkpoint_at"])
            end = (
                datetime.fromisoformat(ordered[index + 1]["checkpoint_at"])
                - timedelta(microseconds=1)
                if mode == "rolling_30m" and index + 1 < len(ordered)
                else start.replace(hour=23, minute=59, second=59)
            )
            window = [bar for bar in session_bars if start < bar.timestamp <= end]
            if not window:
                continue
            for label, level, side in _sd_boundaries(checkpoint):
                touch = next(
                    (bar for bar in window if bar.low <= level <= bar.high),
                    None,
                )
                if touch is not None:
                    events.append(_event(checkpoint, f"{label}_touch", side, touch, level))
                if label in {"lower_1_5sd", "lower_2sd"}:
                    breakout = next((bar for bar in window if bar.close < level), None)
                    if breakout is not None:
                        events.append(
                            _event(
                                checkpoint,
                                f"close_beyond_{label}",
                                "short_breakout",
                                breakout,
                                breakout.close,
                            )
                        )
                if label in {"upper_1_5sd", "upper_2sd"}:
                    breakout = next((bar for bar in window if bar.close > level), None)
                    if breakout is not None:
                        events.append(
                            _event(
                                checkpoint,
                                f"close_beyond_{label}",
                                "long_breakout",
                                breakout,
                                breakout.close,
                            )
                        )
            wall = checkpoint.get("oi_nearest_wall")
            if wall is not None:
                touch = next(
                    (bar for bar in window if bar.low <= wall <= bar.high),
                    None,
                )
                if touch is not None:
                    side = (
                        "long_reversion"
                        if wall < checkpoint["mapped_center"]
                        else "short_reversion"
                    )
                    events.append(_event(checkpoint, "oi_wall_touch", side, touch, wall))
                breakout = _first_wall_break(window, checkpoint, float(wall))
                if breakout is not None:
                    side = "long_breakout" if breakout.close > wall else "short_breakout"
                    events.append(
                        _event(
                            checkpoint,
                            "close_beyond_oi_wall",
                            side,
                            breakout,
                            breakout.close,
                        )
                    )
            z = abs(float(checkpoint["price_z_from_current_snapshot"]))
            oi_distance = checkpoint.get("oi_distance_sd")
            if z < 1 and oi_distance is not None and oi_distance <= 0.25:
                events.append(
                    _event(
                        checkpoint,
                        "pin_candidate",
                        "pin",
                        window[0],
                        float(checkpoint["current_xauusd"]),
                    )
                )
            if checkpoint.get("oi_low_activity_gap_above"):
                events.append(
                    _event(
                        checkpoint, "low_oi_gap_entry", "long_breakout", window[0], window[0].close
                    )
                )
            if checkpoint.get("oi_low_activity_gap_below"):
                events.append(
                    _event(
                        checkpoint, "low_oi_gap_entry", "short_breakout", window[0], window[0].close
                    )
                )
    events.sort(
        key=lambda item: (item["session_date"], item["event_timestamp"], item["event_type"])
    )
    return events


def _event(
    checkpoint: dict[str, Any],
    event_type: str,
    side: str,
    bar: XauPriceBar,
    entry_price: float,
) -> dict[str, Any]:
    event_id = f"{checkpoint['checkpoint_id']}:{event_type}:{side}:{bar.timestamp.isoformat()}"
    return {
        **checkpoint,
        "event_id": event_id,
        "episode_id": None,
        "event_type": event_type,
        "side": side,
        "event_timestamp": bar.timestamp.isoformat(),
        "entry_price": float(entry_price),
        "event_bar_open": bar.open,
        "event_bar_high": bar.high,
        "event_bar_low": bar.low,
        "event_bar_close": bar.close,
        "feature_timestamp": checkpoint["checkpoint_at"],
        "future_feature_violation": bool(checkpoint["future_feature_violation"]),
        "research_only": True,
        "signal_allowed": False,
    }


def _sd_boundaries(checkpoint: dict[str, Any]) -> list[tuple[str, float, str]]:
    definitions = []
    for label, key, side in (
        ("lower_1sd", "lower_1sd", "long_reversion"),
        ("lower_1_5sd", "lower_1_5sd", "long_reversion"),
        ("lower_2sd", "lower_2sd", "long_reversion"),
        ("upper_1sd", "upper_1sd", "short_reversion"),
        ("upper_1_5sd", "upper_1_5sd", "short_reversion"),
        ("upper_2sd", "upper_2sd", "short_reversion"),
    ):
        value = checkpoint.get(key)
        if value is not None:
            definitions.append((label, float(value), side))
    return definitions


def _first_wall_break(
    bars: list[XauPriceBar], checkpoint: dict[str, Any], wall: float
) -> XauPriceBar | None:
    center = float(checkpoint["mapped_center"])
    if wall >= center:
        return next((bar for bar in bars if bar.close > wall), None)
    return next((bar for bar in bars if bar.close < wall), None)
