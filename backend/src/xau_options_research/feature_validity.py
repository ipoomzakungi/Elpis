from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from statistics import median, pstdev
from typing import Any

from src.models.xau_vol2vol_history_walkforward import (
    XauVol2VolRangeDeskSnapshot,
    XauVol2VolStrikeSnapshot,
)

CHECKPOINT_FEATURES = (
    "atm_iv",
    "atm_iv_change_previous",
    "iv_slope_30m",
    "iv_slope_60m",
    "oi_total",
    "oi_change",
    "volume_total",
    "volume_change",
    "basis_drift",
    "monthly_oi_confluence",
)


def build_feature_semantics_audit(
    checkpoints: list[dict[str, Any]],
    ranges: list[XauVol2VolRangeDeskSnapshot],
    strikes: list[XauVol2VolStrikeSnapshot],
) -> dict[str, Any]:
    summaries = {
        field: _audit_checkpoint_field(checkpoints, field) for field in CHECKPOINT_FEATURES
    }
    source_oi = [
        float(row.total_change)
        for row in strikes
        if row.snapshot_kind == "open_interest" and row.total_change is not None
    ]
    derived_oi = _derived_strike_changes(strikes, "open_interest")
    volume = _volume_semantics(strikes)
    iv = _iv_semantics(ranges)
    source_oi_updates = _strike_change_semantics(strikes, "open_interest")
    oi_status = (
        "non_informative"
        if _information_status(source_oi) == "non_informative"
        else "variable_structural_not_directionally_validated"
    )
    summaries["source_oi_change"] = _audit_values(source_oi)
    summaries["derived_oi_change"] = _audit_values(derived_oi)
    return {
        "feature_summaries": summaries,
        "oi_change_status": oi_status,
        "oi_change_reason": (
            "Source OI Change has insufficient non-zero or unique values. OI is treated "
            "as a settled structural stock, not an intraday directional flow."
            if oi_status == "non_informative"
            else "Source OI Change varies, but is a structural field with no validated "
            "directional relationship."
        ),
        "source_oi_change_update_semantics": source_oi_updates,
        "multi_session_oi_features": _multi_session_oi_features(strikes),
        "intraday_volume": volume,
        "iv_update_semantics": iv,
        "derived_feature_policy": {
            "prior_session_oi_change": "same strike, prior completed session",
            "multi_session_oi_change_3d": "same strike, three completed sessions",
            "multi_session_oi_change_5d": "same strike, five completed sessions",
            "wall_persistence_days": "consecutive completed sessions in top-five OI",
            "iv_slopes": "actual source value changes only; repeated values are not updates",
            "interval_volume": "non-negative cumulative-volume delta within session/series/strike",
        },
        "informative_feature_count": sum(
            row["information_status"] == "informative" for row in summaries.values()
        ),
        "research_only": True,
        "signal_allowed": False,
    }


def derive_interval_volume(
    current: float | None,
    previous: float | None,
    *,
    same_session_and_series: bool,
) -> float | None:
    if current is None:
        return None
    if previous is None or not same_session_and_series:
        return None
    difference = current - previous
    return difference if difference >= 0 else None


def actual_value_updates(
    observations: list[tuple[datetime, float]],
) -> list[tuple[datetime, float]]:
    updates: list[tuple[datetime, float]] = []
    for timestamp, value in sorted(observations):
        if not updates or value != updates[-1][1]:
            updates.append((timestamp, value))
    return updates


def _audit_checkpoint_field(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["session_date"]].append(row)
    session_rows = []
    all_values: list[Any] = []
    for session, items in sorted(grouped.items()):
        ordered = sorted(items, key=lambda item: item["checkpoint_at"])
        values = [item.get(field) for item in ordered if item.get(field) is not None]
        all_values.extend(values)
        updates = _update_times(ordered, field)
        intervals = [
            (current - previous).total_seconds() / 60
            for previous, current in zip(updates, updates[1:], strict=False)
        ]
        session_rows.append(
            {
                "session_date": session,
                "non_null_count": len(values),
                "non_zero_count": sum(_non_zero(value) for value in values),
                "unique_value_count": len({_hashable(value) for value in values}),
                "actual_update_count": max(len(updates) - 1, 0),
                "median_update_interval_minutes": median(intervals) if intervals else None,
                "maximum_stale_run_minutes": max(intervals) if intervals else None,
                "repeated_snapshot_percentage": (
                    1 - len(updates) / len(values) if values else None
                ),
                "first_update_time": updates[0].isoformat() if updates else None,
                "last_update_time": updates[-1].isoformat() if updates else None,
                "within_session_variation": _numeric_variation(values),
            }
        )
    result = _audit_values(all_values)
    result.update(
        {
            "sessions": session_rows,
            "cross_session_variation": _session_variation(session_rows),
        }
    )
    return result


def _audit_values(values: list[Any]) -> dict[str, Any]:
    numeric = [float(value) for value in values if isinstance(value, (int, float, bool))]
    unique = {_hashable(value) for value in values}
    return {
        "non_null_count": len(values),
        "non_zero_count": sum(_non_zero(value) for value in values),
        "unique_value_count": len(unique),
        "information_status": _information_status(values),
        "variation": pstdev(numeric) if len(numeric) > 1 else 0.0 if numeric else None,
    }


def _information_status(values: list[Any]) -> str:
    non_zero = sum(_non_zero(value) for value in values)
    unique = len({_hashable(value) for value in values})
    return "informative" if non_zero > 1 and unique > 2 else "non_informative"


def _derived_strike_changes(rows: list[XauVol2VolStrikeSnapshot], kind: str) -> list[float]:
    grouped: dict[tuple[str, str | None, float], list[XauVol2VolStrikeSnapshot]] = defaultdict(list)
    for row in rows:
        if row.snapshot_kind == kind and row.total is not None:
            grouped[(row.session_date.isoformat(), row.series, row.strike)].append(row)
    changes = []
    for items in grouped.values():
        ordered = sorted(items, key=lambda item: item.observed_at)
        for previous, current in zip(ordered, ordered[1:], strict=False):
            changes.append(float(current.total) - float(previous.total))
    return changes


def _volume_semantics(rows: list[XauVol2VolStrikeSnapshot]) -> dict[str, Any]:
    grouped: dict[tuple[str, str | None, float], list[XauVol2VolStrikeSnapshot]] = defaultdict(list)
    for row in rows:
        if row.snapshot_kind == "intraday_volume" and row.total is not None:
            grouped[(row.session_date.isoformat(), row.series, row.strike)].append(row)
    transitions = 0
    nondecreasing = 0
    intervals = []
    negative_resets = 0
    for items in grouped.values():
        ordered = sorted(items, key=lambda item: item.observed_at)
        for previous, current in zip(ordered, ordered[1:], strict=False):
            transitions += 1
            interval = derive_interval_volume(
                float(current.total),
                float(previous.total),
                same_session_and_series=True,
            )
            if interval is None:
                negative_resets += 1
            else:
                nondecreasing += 1
                intervals.append(interval)
    ratio = nondecreasing / transitions if transitions else None
    derived = _aggregate_volume_intervals(rows)
    return {
        "semantics": "cumulative" if ratio is not None and ratio >= 0.9 else "unresolved",
        "transition_count": transitions,
        "nondecreasing_transition_percentage": ratio,
        "negative_reset_count": negative_resets,
        "interval_volume_non_zero_count": sum(value != 0 for value in intervals),
        "interval_volume_unique_count": len(set(intervals)),
        "negative_reset_policy": "null unless session or series boundary",
        "derived_interval_features": derived,
    }


def _iv_semantics(rows: list[XauVol2VolRangeDeskSnapshot]) -> dict[str, Any]:
    grouped: dict[tuple[str, str | None], list[tuple[datetime, float]]] = defaultdict(list)
    for row in rows:
        if row.vol_now is not None:
            grouped[(row.session_date.isoformat(), row.series)].append(
                (row.observed_at, float(row.vol_now))
            )
    update_intervals = []
    raw_count = 0
    update_count = 0
    for observations in grouped.values():
        raw_count += len(observations)
        updates = actual_value_updates(observations)
        update_count += len(updates)
        update_intervals.extend(
            (current[0] - previous[0]).total_seconds() / 60
            for previous, current in zip(updates, updates[1:], strict=False)
        )
    return {
        "raw_snapshot_count": raw_count,
        "actual_value_update_count": update_count,
        "repeated_value_count": raw_count - update_count,
        "median_actual_update_interval_minutes": (
            median(update_intervals) if update_intervals else None
        ),
        "slope_policy": "actual value updates only",
    }


def _strike_change_semantics(
    rows: list[XauVol2VolStrikeSnapshot], kind: str
) -> dict[str, Any]:
    grouped: dict[tuple[str, str | None, float], list[tuple[datetime, float]]] = defaultdict(list)
    for row in rows:
        if row.snapshot_kind == kind and row.total_change is not None:
            grouped[(row.session_date.isoformat(), row.series, row.strike)].append(
                (row.observed_at, float(row.total_change))
            )
    raw_count = 0
    actual_count = 0
    intervals = []
    for observations in grouped.values():
        raw_count += len(observations)
        updates = actual_value_updates(observations)
        actual_count += len(updates)
        intervals.extend(
            (current[0] - previous[0]).total_seconds() / 60
            for previous, current in zip(updates, updates[1:], strict=False)
        )
    return {
        "raw_value_count": raw_count,
        "actual_value_update_count": actual_count,
        "repeated_value_count": raw_count - actual_count,
        "repeated_value_percentage": (
            (raw_count - actual_count) / raw_count if raw_count else None
        ),
        "median_actual_update_interval_minutes": median(intervals) if intervals else None,
    }


def _aggregate_volume_intervals(
    rows: list[XauVol2VolStrikeSnapshot],
) -> list[dict[str, Any]]:
    totals: dict[tuple[str, str | None, datetime], float] = defaultdict(float)
    for row in rows:
        if row.snapshot_kind == "intraday_volume" and row.total is not None:
            totals[(row.session_date.isoformat(), row.series, row.observed_at)] += float(row.total)
    grouped: dict[tuple[str, str | None], list[tuple[datetime, float]]] = defaultdict(list)
    for (session, series, observed_at), total in totals.items():
        grouped[(session, series)].append((observed_at, total))
    result = []
    for (session, series), observations in sorted(grouped.items()):
        ordered = sorted(observations)
        interval_rows = []
        for index, (observed_at, total) in enumerate(ordered):
            previous = ordered[index - 1][1] if index else None
            interval = derive_interval_volume(
                total, previous, same_session_and_series=index > 0
            )
            interval_rows.append((observed_at, total, interval))
        for observed_at, total, interval in interval_rows:
            result.append(
                {
                    "session_date": session,
                    "series": series,
                    "observed_at": observed_at.isoformat(),
                    "cumulative_volume": total,
                    "interval_volume": interval,
                    "volume_acceleration_30m": _rolling_acceleration(
                        interval_rows, observed_at, 30
                    ),
                    "volume_acceleration_60m": _rolling_acceleration(
                        interval_rows, observed_at, 60
                    ),
                }
            )
    return result


def _rolling_acceleration(
    rows: list[tuple[datetime, float, float | None]],
    at: datetime,
    minutes: int,
) -> float | None:
    recent = [
        interval
        for timestamp, _, interval in rows
        if interval is not None and 0 <= (at - timestamp).total_seconds() < minutes * 60
    ]
    prior = [
        interval
        for timestamp, _, interval in rows
        if interval is not None
        and minutes * 60 <= (at - timestamp).total_seconds() < 2 * minutes * 60
    ]
    return sum(recent) - sum(prior) if recent and prior else None


def _multi_session_oi_features(
    rows: list[XauVol2VolStrikeSnapshot],
) -> list[dict[str, Any]]:
    latest: dict[tuple[str, float], XauVol2VolStrikeSnapshot] = {}
    for row in rows:
        if row.snapshot_kind != "open_interest" or row.total is None:
            continue
        key = (row.session_date.isoformat(), row.strike)
        if key not in latest or row.observed_at > latest[key].observed_at:
            latest[key] = row
    by_session: dict[str, list[XauVol2VolStrikeSnapshot]] = defaultdict(list)
    for (session, _), row in latest.items():
        by_session[session].append(row)
    sessions = sorted(by_session)
    top_five = {
        session: {
            row.strike
            for row in sorted(
                by_session[session], key=lambda item: float(item.total or 0), reverse=True
            )[:5]
        }
        for session in sessions
    }
    records = []
    for session_index, session in enumerate(sessions):
        for row in by_session[session]:
            history = [
                next(
                    (
                        item
                        for item in by_session[prior_session]
                        if item.strike == row.strike
                    ),
                    None,
                )
                for prior_session in sessions[:session_index]
            ]
            available = [item for item in history if item is not None]
            persistence = 0
            for prior_session in reversed(sessions[: session_index + 1]):
                if row.strike not in top_five[prior_session]:
                    break
                persistence += 1
            records.append(
                {
                    "session_date": session,
                    "strike": row.strike,
                    "prior_session_oi_change": _lag_change(row, available, 1),
                    "multi_session_oi_change_3d": _lag_change(row, available, 3),
                    "multi_session_oi_change_5d": _lag_change(row, available, 5),
                    "wall_persistence_days": persistence,
                }
            )
    return records


def _lag_change(
    current: XauVol2VolStrikeSnapshot,
    history: list[XauVol2VolStrikeSnapshot],
    lag: int,
) -> float | None:
    if len(history) < lag or current.total is None or history[-lag].total is None:
        return None
    return float(current.total) - float(history[-lag].total)


def _update_times(rows: list[dict[str, Any]], field: str) -> list[datetime]:
    observations = [
        (datetime.fromisoformat(row["checkpoint_at"]), row.get(field))
        for row in rows
        if row.get(field) is not None
    ]
    updates = []
    previous: Any = object()
    for timestamp, value in observations:
        if not updates or value != previous:
            updates.append(timestamp)
            previous = value
    return updates


def _numeric_variation(values: list[Any]) -> float | None:
    numeric = [float(value) for value in values if isinstance(value, (int, float, bool))]
    return pstdev(numeric) if len(numeric) > 1 else 0.0 if numeric else None


def _session_variation(rows: list[dict[str, Any]]) -> float | None:
    values = [row["within_session_variation"] for row in rows]
    numeric = [float(value) for value in values if value is not None]
    return pstdev(numeric) if len(numeric) > 1 else 0.0 if numeric else None


def _non_zero(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return isinstance(value, (int, float)) and value != 0


def _hashable(value: Any) -> Any:
    return value if isinstance(value, (str, int, float, bool, type(None))) else repr(value)
