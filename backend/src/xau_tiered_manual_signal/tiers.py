from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.models.xau_market_context import XauPriceBar
from src.xau_first_touch_study.events import evaluate_first_passage
from src.xau_first_touch_study.models import (
    CountingMode,
    EventOutcome,
    EventSide,
    FirstPassageStatus,
    FirstTouchEvent,
    MappedPlan,
)


@dataclass(frozen=True)
class OiConfluenceZone:
    boundary: float
    mapped_wall: float
    lower: float
    upper: float
    oi_total: float
    oi_percentile: float
    wall_distance_points: float
    source_snapshot_at: datetime
    selected_series: str


def extended_tier_levels(plan: MappedPlan) -> dict[float, tuple[float, float]]:
    lower_one, upper_one = plan.mapped_levels[1]
    lower_two, upper_two = plan.mapped_levels[2]
    return {
        1.0: (lower_one, upper_one),
        1.5: ((lower_one + lower_two) / 2, (upper_one + upper_two) / 2),
        2.0: plan.mapped_levels[2],
        3.0: plan.mapped_levels[3],
    }


def build_tier_events(
    plan: MappedPlan,
    bars: list[XauPriceBar],
    *,
    counting_mode: CountingMode,
) -> list[FirstTouchEvent]:
    session_bars = [
        item
        for item in sorted(bars, key=lambda row: row.timestamp)
        if item.timestamp >= plan.selection.activation_at
    ]
    events = []
    for tier, (lower, upper) in extended_tier_levels(plan).items():
        side_events = [
            item
            for item in (
                _first_touch(plan, session_bars, tier, EventSide.LOWER_LONG, lower),
                _first_touch(plan, session_bars, tier, EventSide.UPPER_SHORT, upper),
            )
            if item is not None
        ]
        if counting_mode == CountingMode.AGGREGATED and side_events:
            chosen = min(
                side_events,
                key=lambda item: (item.touch_timestamp, item.side.value),
            )
            events.append(
                FirstTouchEvent(
                    **{
                        **chosen.__dict__,
                        "event_id": chosen.event_id.replace(
                            CountingMode.SIDE_SPECIFIC.value,
                            CountingMode.AGGREGATED.value,
                        ),
                        "counting_mode": CountingMode.AGGREGATED,
                    }
                )
            )
        elif counting_mode == CountingMode.SIDE_SPECIFIC:
            events.extend(side_events)
    return sorted(events, key=lambda item: (item.touch_timestamp, item.tier))


def evaluate_tier_barrier(
    event: FirstTouchEvent,
    bars: list[XauPriceBar],
    *,
    tp_points: float,
    sl_points: float,
    cost_points: float,
    known_entry_at_bar_open: bool = False,
) -> Any:
    if known_entry_at_bar_open:
        return _evaluate_known_open_first_passage(
            event,
            bars,
            tp_points=tp_points,
            sl_points=sl_points,
            cost_points=cost_points,
        )
    return evaluate_first_passage(
        event,
        bars,
        tp_points=tp_points,
        sl_points=sl_points,
        cost_points=cost_points,
    )


def qualifying_lower_oi_zone(
    plan: MappedPlan,
    *,
    maximum_distance_points: float,
    minimum_percentile: float,
) -> OiConfluenceZone | None:
    boundary = extended_tier_levels(plan)[2.0][0]
    offset = plan.planning_xau_price - plan.selection.snapshot.future_reference
    rows = [
        {
            "mapped_strike": float(item["strike"]) + offset,
            "total": float(item.get("total") or 0),
        }
        for item in plan.selection.snapshot.strike_rows
        if item.get("strike") is not None
    ]
    if not rows:
        return None
    ranked = sorted(rows, key=lambda item: (-item["total"], item["mapped_strike"]))
    for index, item in enumerate(ranked, start=1):
        item["percentile"] = 1 - ((index - 1) / len(ranked))
    candidates = [
        item
        for item in rows
        if abs(item["mapped_strike"] - boundary) <= maximum_distance_points
        and item["percentile"] >= minimum_percentile
    ]
    if not candidates:
        return None
    wall = min(
        candidates,
        key=lambda item: (
            abs(item["mapped_strike"] - boundary),
            -item["total"],
        ),
    )
    return OiConfluenceZone(
        boundary=boundary,
        mapped_wall=wall["mapped_strike"],
        lower=min(boundary, wall["mapped_strike"]),
        upper=max(boundary, wall["mapped_strike"]),
        oi_total=wall["total"],
        oi_percentile=wall["percentile"],
        wall_distance_points=abs(wall["mapped_strike"] - boundary),
        source_snapshot_at=plan.selection.snapshot.observed_at,
        selected_series=plan.selection.snapshot.series,
    )


def executable_rejection_entry(
    zone: OiConfluenceZone,
    event: FirstTouchEvent,
    bars: list[XauPriceBar],
    *,
    rule: str,
) -> dict[str, Any] | None:
    ordered = sorted(bars, key=lambda item: item.timestamp)
    touch_index = next(
        (
            index
            for index, item in enumerate(ordered)
            if item.timestamp == event.touch_timestamp
        ),
        None,
    )
    if touch_index is None:
        return None
    threshold = zone.boundary if rule == "R1_BOUNDARY" else zone.upper
    for index in range(touch_index, len(ordered) - 1):
        confirmation = ordered[index]
        if confirmation.close <= threshold:
            continue
        entry_bar = ordered[index + 1]
        return {
            "rule": rule,
            "confirmation_timestamp": confirmation.timestamp,
            "confirmation_close": confirmation.close,
            "entry_timestamp": entry_bar.timestamp,
            "entry_price": entry_bar.open,
            "entry_bar_index": index + 1,
        }
    return None


def _evaluate_known_open_first_passage(
    event: FirstTouchEvent,
    bars: list[XauPriceBar],
    *,
    tp_points: float,
    sl_points: float,
    cost_points: float,
) -> EventOutcome:
    window = [
        item
        for item in sorted(bars, key=lambda row: row.timestamp)
        if item.timestamp >= event.touch_timestamp
    ]
    if not window:
        return EventOutcome(
            event_id=event.event_id,
            session_date=event.session_date,
            tier=event.tier,
            side=event.side,
            anchor=event.anchor,
            mapping_mode=event.mapping_mode,
            label="LABEL_B_EXECUTABLE_NEXT_BAR_OPEN",
            status=FirstPassageStatus.UNAVAILABLE.value,
            success=None,
            tp_points=tp_points,
            sl_points=sl_points,
            cost_points=cost_points,
            gross_points=None,
            net_points=None,
            mfe_points=None,
            mae_points=None,
            maximum_adverse_before_reversal=None,
            resolved_at=None,
            minutes_to_resolution=None,
            same_bar_ambiguous=False,
            include_in_expectancy=False,
        )
    direction = 1 if event.side == EventSide.LOWER_LONG else -1
    maximum_favorable = 0.0
    maximum_adverse = 0.0
    status = FirstPassageStatus.SESSION_END_UNRESOLVED
    resolved_at = None
    gross: float | None = None
    for bar in window:
        if direction > 0:
            favorable = bar.high - event.boundary
            adverse = bar.low - event.boundary
        else:
            favorable = event.boundary - bar.low
            adverse = event.boundary - bar.high
        maximum_favorable = max(maximum_favorable, favorable)
        maximum_adverse = min(maximum_adverse, adverse)
        tp_hit = favorable >= tp_points
        sl_hit = adverse <= -sl_points
        if tp_hit and sl_hit:
            status = FirstPassageStatus.SAME_BAR_AMBIGUOUS
            resolved_at = bar.timestamp
            break
        if tp_hit:
            status = FirstPassageStatus.TP_FIRST
            resolved_at = bar.timestamp
            gross = tp_points
            break
        if sl_hit:
            status = FirstPassageStatus.SL_FIRST
            resolved_at = bar.timestamp
            gross = -sl_points
            break
    if status == FirstPassageStatus.SESSION_END_UNRESOLVED:
        gross = direction * (window[-1].close - event.boundary)
    return EventOutcome(
        event_id=event.event_id,
        session_date=event.session_date,
        tier=event.tier,
        side=event.side,
        anchor=event.anchor,
        mapping_mode=event.mapping_mode,
        label="LABEL_B_EXECUTABLE_NEXT_BAR_OPEN",
        status=status.value,
        success=status == FirstPassageStatus.TP_FIRST,
        tp_points=tp_points,
        sl_points=sl_points,
        cost_points=cost_points,
        gross_points=gross,
        net_points=gross - cost_points if gross is not None else None,
        mfe_points=maximum_favorable,
        mae_points=maximum_adverse,
        maximum_adverse_before_reversal=abs(maximum_adverse),
        resolved_at=resolved_at,
        minutes_to_resolution=(
            (resolved_at - event.touch_timestamp).total_seconds() / 60
            if resolved_at is not None
            else None
        ),
        same_bar_ambiguous=status == FirstPassageStatus.SAME_BAR_AMBIGUOUS,
        include_in_expectancy=status != FirstPassageStatus.SAME_BAR_AMBIGUOUS,
    )


def _first_touch(
    plan: MappedPlan,
    bars: list[XauPriceBar],
    tier: float,
    side: EventSide,
    boundary: float,
) -> FirstTouchEvent | None:
    for index, bar in enumerate(bars):
        touched = bar.low <= boundary if side == EventSide.LOWER_LONG else bar.high >= boundary
        if not touched:
            continue
        repeats = sum(
            (
                item.low <= boundary
                if side == EventSide.LOWER_LONG
                else item.high >= boundary
            )
            for item in bars[index + 1 :]
        )
        return FirstTouchEvent(
            event_id=(
                f"{plan.plan_id}_{CountingMode.SIDE_SPECIFIC.value}_{tier:g}_"
                f"{side.value}_{bar.timestamp.isoformat()}"
            ),
            plan_id=plan.plan_id,
            session_date=plan.session_date,
            anchor=plan.anchor,
            mapping_mode=plan.mapping_mode,
            counting_mode=CountingMode.SIDE_SPECIFIC,
            tier=tier,
            side=side,
            boundary=boundary,
            touch_timestamp=bar.timestamp,
            touch_bar_index=index,
            source_series=plan.selection.snapshot.series,
            source_dte=plan.selection.snapshot.source_dte,
            selected_snapshot_at=plan.selection.snapshot.observed_at,
            repeated_touch_count=repeats,
            one_sd_points=plan.one_sd_points,
        )
    return None
