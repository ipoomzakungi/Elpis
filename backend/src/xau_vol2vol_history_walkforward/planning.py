from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from src.models.xau_market_context import XauPriceBar
from src.models.xau_vol2vol_history_walkforward import (
    XauMappingMode,
    XauVol2VolRangeDeskSnapshot,
    XauVol2VolStrikeSnapshot,
)


@dataclass(frozen=True)
class XauPlanningSelection:
    session_date: date
    source_session_date: date
    cycle_label: str
    planning_at: datetime
    simulation_window_start: datetime
    simulation_window_end: datetime
    range_snapshot: XauVol2VolRangeDeskSnapshot
    strike_rows: list[XauVol2VolStrikeSnapshot] = field(default_factory=list)
    selected_xau_price_time: datetime | None = None
    basis_alignment_seconds: float | None = None
    mapping_mode: XauMappingMode = XauMappingMode.DISTANCE_REANCHORED
    source_alignment_seconds: float | None = None
    xau_price_age_at_planning_seconds: float | None = None
    snapshot_age_at_planning_seconds: float | None = None
    series_selection_reason: str | None = None
    candidate_series: list[dict] = field(default_factory=list)


def select_planning_cycles(
    *,
    range_snapshots: list[XauVol2VolRangeDeskSnapshot],
    strike_rows: list[XauVol2VolStrikeSnapshot],
    bars: list[XauPriceBar],
    session_date_from: date,
    session_date_to: date,
    planning_times: tuple[time, ...],
    timezone: str,
    basis_tolerance_seconds: int = 300,
    planning_mode: str = "scheduled_refresh",
    day_end_time: time = time(23, 59, 59),
    require_complete_window: bool = False,
    require_one_sd: bool = False,
    mapping_mode: XauMappingMode = XauMappingMode.DISTANCE_REANCHORED,
    source_alignment_tolerance_seconds: int = 300,
    snapshot_freshness_tolerance_seconds: int = 1800,
    bar_interval_minutes: int = 1,
    join_by_observed_trading_date: bool = False,
) -> tuple[list[XauPlanningSelection], dict[str, int]]:
    zone = ZoneInfo(timezone)
    selections: list[XauPlanningSelection] = []
    issues = {
        "future_snapshot_used_count": 0,
        "plans_missing_basis_count": 0,
        "plans_missing_sd_count": 0,
        "cycles_without_bars_count": 0,
        "cycles_without_snapshot_count": 0,
        "incomplete_candle_window_count": 0,
        "non_monotonic_sd_count": 0,
        "source_alignment_rejected_count": 0,
        "series_without_covering_dte_count": 0,
        "stale_snapshot_rejected_count": 0,
    }
    current = session_date_from
    trading_date_by_source_session = _trading_date_by_source_session(
        range_snapshots,
        zone,
    )
    strikes_by_session_series: dict[
        tuple[date, str | None], list[XauVol2VolStrikeSnapshot]
    ] = {}
    for row in strike_rows:
        strikes_by_session_series.setdefault((row.session_date, row.series), []).append(row)
    while current <= session_date_to:
        session_ranges = [
            item
            for item in range_snapshots
            if (
                trading_date_by_source_session.get(item.session_date) == current
                if join_by_observed_trading_date
                else item.session_date == current
            )
        ]
        session_bars = [
            item for item in bars if item.timestamp.astimezone(zone).date() == current
        ]
        for cycle_index, cycle in enumerate(planning_times):
            planning_at = datetime.combine(current, cycle, tzinfo=zone)
            window_start, window_end = _cycle_window(
                current,
                cycle,
                zone,
                planning_mode=planning_mode,
                day_end_time=day_end_time,
                next_cycle=(
                    planning_times[cycle_index + 1]
                    if cycle_index + 1 < len(planning_times)
                    else None
                ),
            )
            simulation_bars = [
                item
                for item in session_bars
                if window_start <= item.timestamp.astimezone(zone) <= window_end
            ]
            if not simulation_bars:
                issues["cycles_without_bars_count"] += 1
                continue
            if require_complete_window and not _window_is_complete(
                simulation_bars,
                window_start=window_start,
                window_end=window_end,
                zone=zone,
                bar_interval_minutes=bar_interval_minutes,
            ):
                issues["incomplete_candle_window_count"] += 1
                continue
            past_ranges = [
                item
                for item in session_ranges
                if item.observed_at.astimezone(zone) <= planning_at
            ]
            eligible = [
                item
                for item in past_ranges
                if _has_numeric_sd(item, require_one_sd=require_one_sd)
            ]
            if not eligible:
                if past_ranges:
                    issues["plans_missing_sd_count"] += 1
                else:
                    issues["cycles_without_snapshot_count"] += 1
                continue
            selected_range, candidates, selection_reason = _select_series_snapshot(
                eligible,
                required_horizon_days=max(
                    (window_end - planning_at).total_seconds() / 86_400,
                    0,
                ),
                planning_at=planning_at,
            )
            if selected_range is None:
                issues["series_without_covering_dte_count"] += 1
                continue
            snapshot_age_seconds = (
                planning_at - selected_range.observed_at.astimezone(zone)
            ).total_seconds()
            if snapshot_age_seconds > snapshot_freshness_tolerance_seconds:
                issues["stale_snapshot_rejected_count"] += 1
                continue
            if not _levels_are_monotonic(selected_range):
                issues["non_monotonic_sd_count"] += 1
                continue
            if selected_range.observed_at.astimezone(zone) > planning_at:
                issues["future_snapshot_used_count"] += 1
                continue
            eligible_bars = [
                item for item in session_bars if item.timestamp.astimezone(zone) <= planning_at
            ]
            if not eligible_bars:
                issues["cycles_without_bars_count"] += 1
                continue
            planning_bar = eligible_bars[-1]
            xau_age_seconds = (
                planning_at - planning_bar.timestamp.astimezone(zone)
            ).total_seconds()
            if xau_age_seconds > basis_tolerance_seconds:
                issues["plans_missing_basis_count"] += 1
                continue
            source_bars = [
                item
                for item in session_bars
                if item.timestamp.astimezone(zone)
                <= selected_range.observed_at.astimezone(zone)
            ]
            if not source_bars and mapping_mode == XauMappingMode.SAME_TIME_BASIS:
                issues["plans_missing_basis_count"] += 1
                continue
            source_bar = source_bars[-1] if source_bars else None
            source_alignment_seconds = (
                abs(
                    (
                        selected_range.observed_at.astimezone(zone)
                        - source_bar.timestamp.astimezone(zone)
                    ).total_seconds()
                )
                if source_bar is not None
                else None
            )
            if (
                mapping_mode == XauMappingMode.SAME_TIME_BASIS
                and source_alignment_seconds is not None
                and source_alignment_seconds > source_alignment_tolerance_seconds
            ):
                issues["source_alignment_rejected_count"] += 1
                continue
            if selected_range.future_open is None:
                issues["plans_missing_basis_count"] += 1
                continue
            mapping_bar = (
                source_bar
                if mapping_mode == XauMappingMode.SAME_TIME_BASIS
                else planning_bar
            )
            enriched = selected_range.model_copy(
                update={
                    "cfd_open": mapping_bar.close,
                    "diff": selected_range.future_open - mapping_bar.close,
                }
            )
            selected_strikes = _select_strikes(
                strikes_by_session_series.get(
                    (selected_range.session_date, selected_range.series), []
                ),
                session_date=selected_range.session_date,
                planning_at=planning_at,
                zone=zone,
                series=selected_range.series,
            )
            selections.append(
                XauPlanningSelection(
                    session_date=current,
                    source_session_date=selected_range.session_date,
                    cycle_label=(
                        f"fixed_morning_{cycle.strftime('%H%M')}"
                        if planning_mode == "fixed_morning"
                        else cycle.strftime("%H:%M")
                    ),
                    planning_at=planning_at,
                    simulation_window_start=window_start,
                    simulation_window_end=window_end,
                    range_snapshot=enriched,
                    strike_rows=selected_strikes,
                    selected_xau_price_time=mapping_bar.timestamp,
                    basis_alignment_seconds=source_alignment_seconds,
                    mapping_mode=mapping_mode,
                    source_alignment_seconds=source_alignment_seconds,
                    xau_price_age_at_planning_seconds=xau_age_seconds,
                    snapshot_age_at_planning_seconds=snapshot_age_seconds,
                    series_selection_reason=selection_reason,
                    candidate_series=candidates,
                )
            )
        current += timedelta(days=1)
    return selections, issues


def _select_strikes(
    rows: list[XauVol2VolStrikeSnapshot],
    *,
    session_date: date,
    planning_at: datetime,
    zone: ZoneInfo,
    series: str | None,
) -> list[XauVol2VolStrikeSnapshot]:
    eligible = [
        item
        for item in rows
        if item.session_date == session_date and item.observed_at.astimezone(zone) <= planning_at
        and (series is None or item.series == series)
    ]
    latest_by_kind: dict[str, datetime] = {}
    for item in eligible:
        latest_by_kind[item.snapshot_kind] = max(
            latest_by_kind.get(item.snapshot_kind, item.observed_at),
            item.observed_at,
        )
    return [
        item
        for item in eligible
        if item.observed_at == latest_by_kind.get(item.snapshot_kind)
    ]


def _cycle_window(
    session_date: date,
    cycle: time,
    zone: ZoneInfo,
    *,
    planning_mode: str,
    day_end_time: time,
    next_cycle: time | None,
) -> tuple[datetime, datetime]:
    start = datetime.combine(session_date, cycle, tzinfo=zone) + timedelta(minutes=1)
    if planning_mode == "fixed_morning":
        end = datetime.combine(session_date, day_end_time, tzinfo=zone)
    elif planning_mode == "rolling_30m":
        end = (
            datetime.combine(session_date, next_cycle, tzinfo=zone)
            - timedelta(microseconds=1)
            if next_cycle is not None
            else datetime.combine(session_date, day_end_time, tzinfo=zone)
        )
    elif cycle < time(19, 0):
        end = datetime.combine(session_date, time(18, 59, 59, 999999), tzinfo=zone)
    else:
        end = datetime.combine(session_date, time(23, 59, 59, 999999), tzinfo=zone)
    return start, end


def _window_is_complete(
    bars: list[XauPriceBar],
    *,
    window_start: datetime,
    window_end: datetime,
    zone: ZoneInfo,
    bar_interval_minutes: int,
) -> bool:
    interval_seconds = max(bar_interval_minutes, 1) * 60
    expected = max(int((window_end - window_start).total_seconds() // interval_seconds), 1)
    observed = {
        bar.timestamp.astimezone(zone).replace(second=0, microsecond=0)
        for bar in bars
    }
    if not observed:
        return False
    first = min(observed)
    last = max(observed)
    return (
        len(observed) >= max(expected - 1, 1)
        and first <= window_start + timedelta(seconds=interval_seconds)
        and last >= window_end - timedelta(seconds=interval_seconds)
    )


def _has_numeric_sd(
    snapshot: XauVol2VolRangeDeskSnapshot,
    *,
    require_one_sd: bool = False,
) -> bool:
    values = [
        snapshot.future_buy_2sd,
        snapshot.future_buy_3sd,
        snapshot.future_sell_2sd,
        snapshot.future_sell_3sd,
    ]
    if require_one_sd:
        values.extend([snapshot.future_buy_1sd, snapshot.future_sell_1sd])
    return all(value is not None for value in values)


def planning_plan_metadata(selection: XauPlanningSelection) -> dict:
    snapshot = selection.range_snapshot
    diff = snapshot.diff
    if diff is None:
        raise ValueError("planning selection requires basis")
    return {
        "selected_series": snapshot.series,
        "selected_dte": snapshot.dte,
        "future_reference_price": snapshot.future_open,
        "traded_reference_price": snapshot.cfd_open,
        "basis_points": diff,
        "expected_move": snapshot.expected_move,
        "mapping_mode": selection.mapping_mode,
        "source_alignment_seconds": selection.source_alignment_seconds,
        "xau_price_age_at_planning_seconds": (
            selection.xau_price_age_at_planning_seconds
        ),
        "snapshot_age_at_planning_seconds": selection.snapshot_age_at_planning_seconds,
        "series_selection_reason": selection.series_selection_reason,
        "candidate_series": selection.candidate_series,
        "mapped_lower_1sd": _mapped(snapshot.future_buy_1sd, diff),
        "mapped_lower_2sd": _mapped(snapshot.future_buy_2sd, diff),
        "mapped_lower_3sd": _mapped(snapshot.future_buy_3sd, diff),
        "mapped_upper_1sd": _mapped(snapshot.future_sell_1sd, diff),
        "mapped_upper_2sd": _mapped(snapshot.future_sell_2sd, diff),
        "mapped_upper_3sd": _mapped(snapshot.future_sell_3sd, diff),
    }


def _levels_are_monotonic(snapshot: XauVol2VolRangeDeskSnapshot) -> bool:
    lower = [snapshot.future_buy_3sd, snapshot.future_buy_2sd, snapshot.future_buy_1sd]
    upper = [snapshot.future_sell_1sd, snapshot.future_sell_2sd, snapshot.future_sell_3sd]
    center = snapshot.future_open
    if center is None:
        return False
    present_lower = [value for value in lower if value is not None]
    present_upper = [value for value in upper if value is not None]
    return (
        present_lower == sorted(present_lower)
        and all(value < center for value in present_lower)
        and present_upper == sorted(present_upper)
        and all(value > center for value in present_upper)
    )


def _mapped(value: float | None, diff: float) -> float | None:
    return value - diff if value is not None else None


def _select_series_snapshot(
    snapshots: list[XauVol2VolRangeDeskSnapshot],
    *,
    required_horizon_days: float,
    planning_at: datetime,
) -> tuple[XauVol2VolRangeDeskSnapshot | None, list[dict], str | None]:
    latest_by_series: dict[str, XauVol2VolRangeDeskSnapshot] = {}
    for snapshot in snapshots:
        key = snapshot.series or "unlabeled"
        current = latest_by_series.get(key)
        if current is None or snapshot.observed_at > current.observed_at:
            latest_by_series[key] = snapshot
    effective_dte = {
        key: (
            snapshot.dte
            - max(
                (
                    planning_at
                    - snapshot.observed_at.astimezone(planning_at.tzinfo)
                ).total_seconds()
                / 86_400,
                0,
            )
            if snapshot.dte is not None
            else None
        )
        for key, snapshot in latest_by_series.items()
    }
    candidates = []
    for key, snapshot in latest_by_series.items():
        remaining_dte = effective_dte[key]
        candidates.append(
            {
                "series": snapshot.series,
                "snapshot_dte": snapshot.dte,
                "effective_dte_at_planning": remaining_dte,
                "observed_at": snapshot.observed_at.isoformat(),
                "covers_monitoring_window": bool(
                    remaining_dte is not None
                    and remaining_dte > 0
                    and remaining_dte >= required_horizon_days
                ),
            }
        )
    covering = [
        snapshot
        for key, snapshot in latest_by_series.items()
        if effective_dte[key] is not None
        and effective_dte[key] > 0
        and effective_dte[key] >= required_horizon_days
    ]
    if not covering:
        return None, sorted(candidates, key=lambda item: str(item["series"])), None
    selected = min(
        covering,
        key=lambda item: (
            effective_dte[item.series or "unlabeled"] or float("inf"),
            -item.observed_at.timestamp(),
        ),
    )
    return (
        selected,
        sorted(candidates, key=lambda item: str(item["series"])),
        "nearest_positive_dte_covering_monitoring_window",
    )


def _trading_date_by_source_session(
    snapshots: list[XauVol2VolRangeDeskSnapshot],
    zone: ZoneInfo,
) -> dict[date, date]:
    first_observation: dict[date, datetime] = {}
    for snapshot in snapshots:
        observed = snapshot.observed_at.astimezone(zone)
        current = first_observation.get(snapshot.session_date)
        if current is None or observed < current:
            first_observation[snapshot.session_date] = observed
    return {
        source_session: observed.date()
        for source_session, observed in first_observation.items()
    }
