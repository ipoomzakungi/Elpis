from __future__ import annotations

from typing import Any

from src.models.xau_market_context import XauPriceBar
from src.xau_first_touch_study.models import (
    CountingMode,
    EventOutcome,
    EventSide,
    FirstPassageStatus,
    FirstTouchEvent,
    MappedPlan,
)


def build_first_touch_events(
    plan: MappedPlan,
    bars: list[XauPriceBar],
    *,
    counting_mode: CountingMode,
) -> list[FirstTouchEvent]:
    session_bars = [
        item
        for item in sorted(bars, key=lambda bar: bar.timestamp)
        if item.timestamp >= plan.selection.activation_at
    ]
    events: list[FirstTouchEvent] = []
    for tier in (1, 2, 3):
        lower, upper = plan.mapped_levels[tier]
        side_events = [
            event
            for event in (
                _first_side_touch(plan, session_bars, tier, EventSide.LOWER_LONG, lower),
                _first_side_touch(plan, session_bars, tier, EventSide.UPPER_SHORT, upper),
            )
            if event is not None
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
    return sorted(events, key=lambda item: (item.touch_timestamp, item.tier, item.side.value))


def evaluate_published_label(
    event: FirstTouchEvent,
    bars: list[XauPriceBar],
    *,
    favorable_points: float = 25.0,
    cost_points: float = 0.0,
) -> EventOutcome:
    window = _post_touch_bars(event, bars)
    if not window:
        return _unavailable(event, "LABEL_A_PUBLISHED_EVENTUAL_REVERSAL", cost_points)
    direction = _direction(event.side)
    maximum_favorable = 0.0
    maximum_adverse = 0.0
    resolved_at = None
    adverse_before = 0.0
    for bar in window:
        favorable, adverse = _bar_excursions(bar, event.boundary, direction)
        maximum_favorable = max(maximum_favorable, favorable)
        maximum_adverse = min(maximum_adverse, adverse)
        if favorable >= favorable_points:
            resolved_at = bar.timestamp
            adverse_before = abs(maximum_adverse)
            break
    success = resolved_at is not None
    gross = favorable_points if success else None
    return EventOutcome(
        event_id=event.event_id,
        session_date=event.session_date,
        tier=event.tier,
        side=event.side,
        anchor=event.anchor,
        mapping_mode=event.mapping_mode,
        label="LABEL_A_PUBLISHED_EVENTUAL_REVERSAL",
        status="eventual_reversal" if success else "not_observed_before_session_end",
        success=success,
        tp_points=favorable_points,
        sl_points=None,
        cost_points=cost_points,
        gross_points=gross,
        net_points=gross - cost_points if gross is not None else None,
        mfe_points=maximum_favorable,
        mae_points=maximum_adverse,
        maximum_adverse_before_reversal=adverse_before if success else abs(maximum_adverse),
        resolved_at=resolved_at,
        minutes_to_resolution=_minutes(event, resolved_at),
        same_bar_ambiguous=False,
        include_in_expectancy=False,
    )


def evaluate_first_passage(
    event: FirstTouchEvent,
    bars: list[XauPriceBar],
    *,
    tp_points: float,
    sl_points: float,
    cost_points: float = 0.0,
    conservative_ambiguous_loss: bool = False,
) -> EventOutcome:
    window = _bars_from_touch(event, bars)
    if not window:
        return _unavailable(event, "LABEL_B_TRADABLE_FIRST_PASSAGE", cost_points)
    direction = _direction(event.side)
    maximum_favorable = 0.0
    maximum_adverse = 0.0
    status = FirstPassageStatus.SESSION_END_UNRESOLVED
    resolved_at = None
    gross: float | None = None
    for index, bar in enumerate(window):
        favorable, adverse = _bar_excursions(bar, event.boundary, direction)
        maximum_favorable = max(maximum_favorable, favorable)
        maximum_adverse = min(maximum_adverse, adverse)
        tp_hit = favorable >= tp_points
        sl_hit = adverse <= -sl_points
        touch_bar_unknown = index == 0 and (tp_hit or sl_hit)
        if (tp_hit and sl_hit) or touch_bar_unknown:
            status = FirstPassageStatus.SAME_BAR_AMBIGUOUS
            resolved_at = bar.timestamp
            gross = -sl_points if conservative_ambiguous_loss else None
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
        final = window[-1].close
        gross = direction * (final - event.boundary)
    include = (
        status
        not in {
            FirstPassageStatus.SAME_BAR_AMBIGUOUS,
            FirstPassageStatus.UNAVAILABLE,
        }
        or conservative_ambiguous_loss
    )
    return EventOutcome(
        event_id=event.event_id,
        session_date=event.session_date,
        tier=event.tier,
        side=event.side,
        anchor=event.anchor,
        mapping_mode=event.mapping_mode,
        label="LABEL_B_TRADABLE_FIRST_PASSAGE",
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
        minutes_to_resolution=_minutes(event, resolved_at),
        same_bar_ambiguous=status == FirstPassageStatus.SAME_BAR_AMBIGUOUS,
        include_in_expectancy=include,
    )


def attach_event_context(
    event: FirstTouchEvent,
    plan: MappedPlan,
    bars: list[XauPriceBar],
) -> FirstTouchEvent:
    rows = plan.selection.snapshot.strike_rows
    totals = [
        (float(row["strike"]), float(row.get("total") or 0))
        for row in rows
        if row.get("strike") is not None
    ]
    ranked = sorted(totals, key=lambda item: (-item[1], item[0]))
    nearest = min(totals, key=lambda item: abs(item[0] - event.boundary)) if totals else None
    rank = (
        next(
            (
                index
                for index, item in enumerate(ranked, start=1)
                if nearest is not None and item[0] == nearest[0]
            ),
            None,
        )
        if nearest
        else None
    )
    touch_bar = next(
        (item for item in bars if item.timestamp == event.touch_timestamp),
        None,
    )
    context: dict[str, Any] = {
        "nearest_oi_wall": nearest[0] if nearest else None,
        "nearest_oi_total": nearest[1] if nearest else None,
        "oi_rank": rank,
        "oi_percentile": (1 - ((rank - 1) / max(len(ranked), 1)) if rank is not None else None),
        "wall_distance_points": (abs(nearest[0] - event.boundary) if nearest is not None else None),
        "atm_iv": plan.selection.snapshot.atm_iv,
        "iv_change_since_plan": plan.selection.snapshot.iv_change,
        "intraday_interval_volume": plan.selection.snapshot.activity_total,
        "volume_acceleration": None,
        "acceptance_rejection_state": _acceptance_state(event, touch_bar),
        "next_wall": _next_wall(event, ranked),
        "low_oi_gap": _low_oi_gap(event, totals),
        "selected_series_matches": True,
        "strike_timestamp_not_later_than_event": (
            plan.selection.snapshot.observed_at <= event.touch_timestamp
        ),
        "oi_hard_feature_allowed": plan.oi_hard_feature_allowed,
        "descriptive_only": True,
    }
    return FirstTouchEvent(**{**event.__dict__, "context": context})


def _first_side_touch(
    plan: MappedPlan,
    bars: list[XauPriceBar],
    tier: int,
    side: EventSide,
    boundary: float,
) -> FirstTouchEvent | None:
    for index, bar in enumerate(bars):
        touched = bar.low <= boundary if side == EventSide.LOWER_LONG else bar.high >= boundary
        if not touched:
            continue
        repeats = sum(
            (item.low <= boundary if side == EventSide.LOWER_LONG else item.high >= boundary)
            for item in bars[index + 1 :]
        )
        event_id = (
            f"{plan.plan_id}_{CountingMode.SIDE_SPECIFIC.value}_{tier}_"
            f"{side.value}_{bar.timestamp.isoformat()}"
        )
        return FirstTouchEvent(
            event_id=event_id,
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


def _post_touch_bars(
    event: FirstTouchEvent,
    bars: list[XauPriceBar],
) -> list[XauPriceBar]:
    return [
        item
        for item in sorted(bars, key=lambda bar: bar.timestamp)
        if item.timestamp > event.touch_timestamp
    ]


def _bars_from_touch(
    event: FirstTouchEvent,
    bars: list[XauPriceBar],
) -> list[XauPriceBar]:
    return [
        item
        for item in sorted(bars, key=lambda bar: bar.timestamp)
        if item.timestamp >= event.touch_timestamp
    ]


def _direction(side: EventSide) -> int:
    return 1 if side == EventSide.LOWER_LONG else -1


def _bar_excursions(
    bar: XauPriceBar,
    boundary: float,
    direction: int,
) -> tuple[float, float]:
    if direction > 0:
        return bar.high - boundary, bar.low - boundary
    return boundary - bar.low, boundary - bar.high


def _minutes(event: FirstTouchEvent, resolved_at: Any) -> float | None:
    if resolved_at is None:
        return None
    return (resolved_at - event.touch_timestamp).total_seconds() / 60


def _unavailable(
    event: FirstTouchEvent,
    label: str,
    cost_points: float,
) -> EventOutcome:
    return EventOutcome(
        event_id=event.event_id,
        session_date=event.session_date,
        tier=event.tier,
        side=event.side,
        anchor=event.anchor,
        mapping_mode=event.mapping_mode,
        label=label,
        status=FirstPassageStatus.UNAVAILABLE.value,
        success=None,
        tp_points=None,
        sl_points=None,
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


def _acceptance_state(
    event: FirstTouchEvent,
    bar: XauPriceBar | None,
) -> str:
    if bar is None:
        return "unavailable"
    if event.side == EventSide.LOWER_LONG:
        return "closed_inside" if bar.close > event.boundary else "accepted_beyond"
    return "closed_inside" if bar.close < event.boundary else "accepted_beyond"


def _next_wall(
    event: FirstTouchEvent,
    ranked: list[tuple[float, float]],
) -> float | None:
    candidates = (
        [item[0] for item in ranked if item[0] > event.boundary]
        if event.side == EventSide.LOWER_LONG
        else [item[0] for item in ranked if item[0] < event.boundary]
    )
    if not candidates:
        return None
    return min(candidates) if event.side == EventSide.LOWER_LONG else max(candidates)


def _low_oi_gap(
    event: FirstTouchEvent,
    totals: list[tuple[float, float]],
) -> bool | None:
    between = [
        total
        for strike, total in totals
        if (
            event.boundary <= strike <= event.boundary + event.one_sd_points
            if event.side == EventSide.LOWER_LONG
            else event.boundary - event.one_sd_points <= strike <= event.boundary
        )
    ]
    if not between:
        return None
    return max(between) <= 5
