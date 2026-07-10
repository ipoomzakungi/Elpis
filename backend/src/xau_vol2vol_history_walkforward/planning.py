from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from src.models.xau_market_context import XauPriceBar
from src.models.xau_vol2vol_history_walkforward import (
    XauVol2VolRangeDeskSnapshot,
    XauVol2VolStrikeSnapshot,
)


@dataclass(frozen=True)
class XauPlanningSelection:
    session_date: date
    cycle_label: str
    planning_at: datetime
    simulation_window_start: datetime
    simulation_window_end: datetime
    range_snapshot: XauVol2VolRangeDeskSnapshot
    strike_rows: list[XauVol2VolStrikeSnapshot] = field(default_factory=list)
    selected_xau_price_time: datetime | None = None
    basis_alignment_seconds: float | None = None


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
) -> tuple[list[XauPlanningSelection], dict[str, int]]:
    zone = ZoneInfo(timezone)
    selections: list[XauPlanningSelection] = []
    issues = {
        "future_snapshot_used_count": 0,
        "plans_missing_basis_count": 0,
        "plans_missing_sd_count": 0,
        "cycles_without_bars_count": 0,
        "cycles_without_snapshot_count": 0,
    }
    current = session_date_from
    while current <= session_date_to:
        session_ranges = [item for item in range_snapshots if item.session_date == current]
        session_bars = [
            item for item in bars if item.timestamp.astimezone(zone).date() == current
        ]
        for cycle in planning_times:
            planning_at = datetime.combine(current, cycle, tzinfo=zone)
            window_start, window_end = _cycle_window(current, cycle, zone)
            simulation_bars = [
                item
                for item in session_bars
                if window_start <= item.timestamp.astimezone(zone) <= window_end
            ]
            if not simulation_bars:
                issues["cycles_without_bars_count"] += 1
                continue
            past_ranges = [
                item
                for item in session_ranges
                if item.observed_at.astimezone(zone) <= planning_at
            ]
            eligible = [
                item
                for item in past_ranges
                if _has_numeric_sd(item)
            ]
            if not eligible:
                if past_ranges:
                    issues["plans_missing_sd_count"] += 1
                else:
                    issues["cycles_without_snapshot_count"] += 1
                continue
            selected_range = max(eligible, key=lambda item: item.observed_at)
            if selected_range.observed_at.astimezone(zone) > planning_at:
                issues["future_snapshot_used_count"] += 1
                continue
            eligible_bars = [
                item for item in session_bars if item.timestamp.astimezone(zone) <= planning_at
            ]
            if not eligible_bars:
                issues["cycles_without_bars_count"] += 1
                continue
            selected_bar = eligible_bars[-1]
            alignment_seconds = (
                planning_at - selected_bar.timestamp.astimezone(zone)
            ).total_seconds()
            if alignment_seconds > basis_tolerance_seconds:
                issues["plans_missing_basis_count"] += 1
                continue
            if selected_range.future_open is None:
                issues["plans_missing_basis_count"] += 1
                continue
            enriched = selected_range.model_copy(
                update={
                    "cfd_open": selected_bar.close,
                    "diff": selected_range.future_open - selected_bar.close,
                }
            )
            selected_strikes = _select_strikes(
                strike_rows,
                session_date=current,
                planning_at=planning_at,
                zone=zone,
            )
            selections.append(
                XauPlanningSelection(
                    session_date=current,
                    cycle_label=cycle.strftime("%H:%M"),
                    planning_at=planning_at,
                    simulation_window_start=window_start,
                    simulation_window_end=window_end,
                    range_snapshot=enriched,
                    strike_rows=selected_strikes,
                    selected_xau_price_time=selected_bar.timestamp,
                    basis_alignment_seconds=alignment_seconds,
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
) -> list[XauVol2VolStrikeSnapshot]:
    eligible = [
        item
        for item in rows
        if item.session_date == session_date and item.observed_at.astimezone(zone) <= planning_at
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


def _cycle_window(session_date: date, cycle: time, zone: ZoneInfo) -> tuple[datetime, datetime]:
    start = datetime.combine(session_date, cycle, tzinfo=zone) + timedelta(minutes=1)
    if cycle < time(19, 0):
        end = datetime.combine(session_date, time(18, 59, 59, 999999), tzinfo=zone)
    else:
        end = datetime.combine(session_date, time(23, 59, 59, 999999), tzinfo=zone)
    return start, end


def _has_numeric_sd(snapshot: XauVol2VolRangeDeskSnapshot) -> bool:
    return all(
        value is not None
        for value in (
            snapshot.future_buy_2sd,
            snapshot.future_buy_3sd,
            snapshot.future_sell_2sd,
            snapshot.future_sell_3sd,
        )
    )
