from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from src.models.xau_market_context import XauPriceBar


def deduplicate_events(
    events: list[dict[str, Any]],
    bars: list[XauPriceBar],
    *,
    horizon_minutes: int = 120,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        family = _family(event["event_type"])
        grouped[
            (
                event["session_date"],
                event["planning_mode"],
                event["side"],
                family,
            )
        ].append(event)
    annotated: list[dict[str, Any]] = []
    anchors: list[dict[str, Any]] = []
    for key, rows in sorted(grouped.items()):
        ordered = sorted(rows, key=lambda item: item["event_timestamp"])
        episode_number = 0
        anchor: dict[str, Any] | None = None
        for event in ordered:
            reset_timestamp, reset_reason = _reset(anchor, event, bars, horizon_minutes)
            if anchor is None or reset_reason is not None:
                episode_number += 1
                episode_id = ":".join((*key, f"E{episode_number}"))
                anchor = {
                    **event,
                    "episode_id": episode_id,
                    "is_episode_anchor": True,
                    "reset_timestamp": (reset_timestamp.isoformat() if reset_timestamp else None),
                    "reset_reason": reset_reason,
                }
                anchors.append(anchor)
                annotated.append(anchor)
            else:
                annotated.append(
                    {
                        **event,
                        "episode_id": anchor["episode_id"],
                        "is_episode_anchor": False,
                        "reset_timestamp": None,
                        "reset_reason": None,
                    }
                )
    annotated.sort(key=lambda item: (item["session_date"], item["event_timestamp"]))
    anchors.sort(key=lambda item: (item["session_date"], item["event_timestamp"]))
    return annotated, anchors


def _reset(
    anchor: dict[str, Any] | None,
    event: dict[str, Any],
    bars: list[XauPriceBar],
    horizon_minutes: int,
) -> tuple[datetime | None, str | None]:
    if anchor is None:
        return None, "first_event"
    previous = datetime.fromisoformat(anchor["event_timestamp"])
    current = datetime.fromisoformat(event["event_timestamp"])
    if current >= previous + timedelta(minutes=horizon_minutes):
        return previous + timedelta(minutes=horizon_minutes), "prior_event_horizon_ended"
    center = float(anchor["mapped_center"])
    boundary = float(anchor["entry_price"])
    one_sd = float(anchor["one_sd_points"])
    between = [bar for bar in bars if previous < bar.timestamp < current]
    if any(
        (anchor["side"].startswith("long") and bar.close >= center)
        or (anchor["side"].startswith("short") and bar.close <= center)
        for bar in between
    ):
        bar = next(
            bar
            for bar in between
            if (anchor["side"].startswith("long") and bar.close >= center)
            or (anchor["side"].startswith("short") and bar.close <= center)
        )
        return bar.timestamp, "crossed_mapped_center"
    if any(
        (anchor["side"].startswith("long") and bar.close >= boundary + 0.5 * one_sd)
        or (anchor["side"].startswith("short") and bar.close <= boundary - 0.5 * one_sd)
        for bar in between
    ):
        bar = next(
            bar
            for bar in between
            if (anchor["side"].startswith("long") and bar.close >= boundary + 0.5 * one_sd)
            or (anchor["side"].startswith("short") and bar.close <= boundary - 0.5 * one_sd)
        )
        return bar.timestamp, "returned_0_5sd_inside"
    return None, None


def _family(event_type: str) -> str:
    if "sd_touch" in event_type:
        return event_type
    if "wall" in event_type:
        return "oi_wall"
    return event_type
