from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.models.xau_market_context import XauPriceBar


@dataclass(frozen=True)
class ExecutableEvent:
    event_id: str
    side: str
    entry: float
    touch_timestamp: datetime


def evaluate_executable_fill(
    event: ExecutableEvent,
    bid_bars: list[XauPriceBar],
    *,
    spread_points: float,
    tp_points: float,
    sl_points: float,
) -> dict[str, Any]:
    bars = [
        bar
        for bar in sorted(bid_bars, key=lambda item: item.timestamp)
        if bar.timestamp >= event.touch_timestamp
    ]
    is_long = event.side == "lower_long"
    fill_index = next(
        (
            index
            for index, bar in enumerate(bars)
            if (bar.low + spread_points <= event.entry if is_long else bar.high >= event.entry)
        ),
        None,
    )
    base = {
        "event_id": event.event_id,
        "side": event.side,
        "reference_entry": event.entry,
        "reference_boundary_touched": True,
        "spread_points": spread_points,
        "entry_price_side": "ask" if is_long else "bid",
        "exit_price_side": "bid" if is_long else "ask",
        "research_only": True,
        "signal_allowed": False,
        "order_submission_allowed": False,
    }
    if fill_index is None:
        return {
            **base,
            "status": "not_filled_due_to_spread",
            "executable_entry_filled": False,
            "filled_at": None,
            "resolved_at": None,
        }

    fill_bar = bars[fill_index]
    target = event.entry + tp_points if is_long else event.entry - tp_points
    stop = event.entry - sl_points if is_long else event.entry + sl_points
    for index, bar in enumerate(bars[fill_index:], start=fill_index):
        if is_long:
            tp_hit = bar.high >= target
            sl_hit = bar.low <= stop
        else:
            ask_low = bar.low + spread_points
            ask_high = bar.high + spread_points
            tp_hit = ask_low <= target
            sl_hit = ask_high >= stop
        if not (tp_hit or sl_hit):
            continue
        if index == fill_index or (tp_hit and sl_hit):
            status = "same_bar_ambiguous"
        elif tp_hit:
            status = "tp_first"
        else:
            status = "sl_first"
        return {
            **base,
            "status": status,
            "executable_entry_filled": True,
            "filled_at": fill_bar.timestamp.isoformat(),
            "resolved_at": bar.timestamp.isoformat(),
            "target": target,
            "stop": stop,
        }
    return {
        **base,
        "status": "session_end_unresolved",
        "executable_entry_filled": True,
        "filled_at": fill_bar.timestamp.isoformat(),
        "resolved_at": None,
        "target": target,
        "stop": stop,
    }


def summarize_fill_sensitivity(
    events: list[ExecutableEvent],
    bars_by_trading_date: dict[str, list[XauPriceBar]],
    event_trading_dates: dict[str, str],
    *,
    spreads: list[float],
    tp_points: float,
    sl_points: float,
) -> dict[str, Any]:
    rows = []
    details: dict[str, list[dict[str, Any]]] = {}
    for spread in spreads:
        outcomes = [
            evaluate_executable_fill(
                event,
                bars_by_trading_date.get(event_trading_dates[event.event_id], []),
                spread_points=spread,
                tp_points=tp_points,
                sl_points=sl_points,
            )
            for event in events
        ]
        details[str(spread)] = outcomes
        rows.append(
            {
                "spread_points": spread,
                "reference_touch_count": len(events),
                "executable_fill_count": sum(item["executable_entry_filled"] for item in outcomes),
                "not_filled_due_to_spread": sum(
                    item["status"] == "not_filled_due_to_spread" for item in outcomes
                ),
                "tp_first": sum(item["status"] == "tp_first" for item in outcomes),
                "sl_first": sum(item["status"] == "sl_first" for item in outcomes),
                "same_bar_ambiguous": sum(
                    item["status"] == "same_bar_ambiguous" for item in outcomes
                ),
                "session_end_unresolved": sum(
                    item["status"] == "session_end_unresolved" for item in outcomes
                ),
            }
        )
    return {
        "price_source_side": "bid",
        "synthetic_ask": "bid_plus_configured_spread",
        "cost_subtraction_does_not_create_a_fill": True,
        "rows": rows,
        "outcomes_by_spread": details,
        "research_only": True,
        "signal_allowed": False,
        "order_submission_allowed": False,
    }
