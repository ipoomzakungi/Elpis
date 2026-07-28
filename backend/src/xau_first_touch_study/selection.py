from __future__ import annotations

import json
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from src.models.xau_market_context import XauPriceBar
from src.xau_first_touch_study.models import (
    MappedPlan,
    MappingMode,
    SnapshotSelection,
    SourceSnapshot,
    TimeAnchor,
)


def load_source_snapshots(path: Path, expected_date: date) -> list[SourceSnapshot]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if str(payload.get("sessionDate") or "")[:10] != expected_date.isoformat():
        raise ValueError("Vol2Vol payload sessionDate does not match the requested date")
    rows = payload.get("snapshots")
    if not isinstance(rows, list):
        return []
    snapshots = []
    for row in rows:
        parsed = _source_snapshot(row, expected_date)
        if parsed is not None:
            snapshots.append(parsed)
    return snapshots


def select_snapshot(
    snapshots: list[SourceSnapshot],
    *,
    anchor: TimeAnchor,
    session_date: date,
    timezone: str = "Asia/Bangkok",
    target_dte: float = 0.8,
    dte_tolerance: float = 0.05,
) -> SnapshotSelection | None:
    exact = [
        item for item in snapshots if item.session_date == session_date and item.source_dte > 0
    ]
    if not exact:
        return None
    zone = ZoneInfo(timezone)
    target_at: datetime | None = None
    if anchor == TimeAnchor.T0_DTE_080:
        candidates = exact
        reason = "positive source DTE nearest 0.80, activity, earliest observation"
        activation = None
    elif anchor == TimeAnchor.T1_CME_SETTLEMENT:
        target_at = prior_cme_settlement(session_date).astimezone(zone)
        candidates = exact
        reason = "snapshot nearest prior applicable 13:30 America/New_York settlement"
        activation = None
    else:
        target_at = datetime.combine(session_date, time(7, 0), tzinfo=zone)
        candidates = [item for item in exact if item.observed_at.astimezone(zone) <= target_at]
        reason = "latest exact-session snapshot at or before 07:00 Asia/Bangkok"
        activation = target_at
        if not candidates:
            return None

    if anchor == TimeAnchor.T0_DTE_080:
        selected = min(
            candidates,
            key=lambda item: (
                abs(item.source_dte - target_dte),
                -item.activity_total,
                item.observed_at,
                item.series,
            ),
        )
    elif anchor == TimeAnchor.T1_CME_SETTLEMENT:
        selected = min(
            candidates,
            key=lambda item: (
                abs((item.observed_at.astimezone(zone) - target_at).total_seconds()),
                -item.activity_total,
                item.observed_at,
                item.series,
            ),
        )
    else:
        selected = min(
            candidates,
            key=lambda item: (
                -item.observed_at.timestamp(),
                -item.activity_total,
                item.series,
            ),
        )
    return SnapshotSelection(
        anchor=anchor,
        snapshot=selected,
        activation_at=activation or selected.observed_at.astimezone(zone),
        selection_reason=reason,
        target_at=target_at,
        dte_error=abs(selected.source_dte - target_dte),
        strict_dte_eligible=abs(selected.source_dte - target_dte) <= dte_tolerance,
    )


def map_selection(
    selection: SnapshotSelection,
    bars: list[XauPriceBar],
    *,
    mapping_mode: MappingMode,
    maximum_gap_seconds: int = 300,
    bar_interval_minutes: int = 1,
) -> MappedPlan | None:
    activation_bar = latest_closed_bar(
        bars,
        selection.activation_at,
        bar_interval_minutes=bar_interval_minutes,
    )
    source_bar = latest_closed_bar(
        bars,
        selection.snapshot.observed_at,
        bar_interval_minutes=bar_interval_minutes,
    )
    if activation_bar is None or source_bar is None:
        return None
    source_close_at = source_bar.timestamp + timedelta(minutes=bar_interval_minutes)
    gap = (selection.snapshot.observed_at - source_close_at).total_seconds()
    if gap < 0:
        return None
    if mapping_mode == MappingMode.SAME_TIME_REFERENCE_BASIS and gap > maximum_gap_seconds:
        return None
    xau_reference = (
        activation_bar.close
        if mapping_mode == MappingMode.DISTANCE_REANCHORED
        else source_bar.close
    )
    future_reference = selection.snapshot.future_reference
    basis = (
        future_reference - source_bar.close
        if mapping_mode == MappingMode.SAME_TIME_REFERENCE_BASIS
        else None
    )
    mapped: dict[int, tuple[float, float]] = {}
    for tier, (future_lower, future_upper) in selection.snapshot.ranges.items():
        if mapping_mode == MappingMode.DISTANCE_REANCHORED:
            lower = xau_reference + (future_lower - future_reference)
            upper = xau_reference + (future_upper - future_reference)
        else:
            lower = future_lower - basis
            upper = future_upper - basis
        mapped[tier] = (lower, upper)
    lower_one, upper_one = mapped[1]
    one_sd = ((xau_reference - lower_one) + (upper_one - xau_reference)) / 2
    quality = (
        "distance_proxy_not_validated_basis"
        if mapping_mode == MappingMode.DISTANCE_REANCHORED
        else "same_time_reference_pass"
    )
    plan_key = (
        f"{selection.snapshot.session_date.isoformat()}_{selection.anchor.value}_"
        f"{mapping_mode.value}_{selection.snapshot.series}_"
        f"{selection.snapshot.observed_at.isoformat()}"
    )
    return MappedPlan(
        plan_id=plan_key,
        session_date=selection.snapshot.session_date,
        anchor=selection.anchor,
        mapping_mode=mapping_mode,
        selection=selection,
        planning_xau_timestamp=activation_bar.timestamp,
        planning_xau_price=activation_bar.close,
        source_xau_timestamp=source_bar.timestamp,
        source_xau_price=source_bar.close,
        source_gap_seconds=gap,
        mapping_quality=quality,
        closed_bar_status="closed",
        basis_points=basis,
        mapped_levels=mapped,
        one_sd_points=one_sd,
        oi_hard_feature_allowed=(
            mapping_mode == MappingMode.SAME_TIME_REFERENCE_BASIS and gap <= maximum_gap_seconds
        ),
    )


def latest_closed_bar(
    bars: list[XauPriceBar],
    at: datetime,
    *,
    bar_interval_minutes: int = 1,
) -> XauPriceBar | None:
    interval = timedelta(minutes=bar_interval_minutes)
    eligible = [item for item in bars if item.timestamp + interval <= at]
    return max(eligible, key=lambda item: item.timestamp) if eligible else None


def prior_cme_settlement(session_date: date) -> datetime:
    ny = ZoneInfo("America/New_York")
    candidate = session_date - timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return datetime.combine(candidate, time(13, 30), tzinfo=ny)


def _source_snapshot(row: dict[str, Any], expected_date: date) -> SourceSnapshot | None:
    try:
        observed = _parse_datetime(row.get("observedAt"))
        dte = float(row["dte"])
        reference = float(row["currentPrice"])
        series = str(row["series"])
    except (KeyError, TypeError, ValueError):
        return None
    if str(row.get("sessionDate") or "")[:10] != expected_date.isoformat():
        return None
    ranges: dict[int, tuple[float, float]] = {}
    for item in row.get("ranges") or []:
        try:
            tier = int(item["sd"])
            down_value = item.get("down")
            up_value = item.get("up")
            fallback = item.get("fix")
            down = float(down_value if down_value is not None else fallback)
            up = float(up_value if up_value is not None else fallback)
        except (KeyError, TypeError, ValueError):
            continue
        if tier in {1, 2, 3}:
            ranges[tier] = (reference - down, reference + up)
    if set(ranges) != {1, 2, 3}:
        return None
    totals = row.get("totals") or {}
    activity = _float_or_none(totals.get("total"))
    if activity is None:
        activity = sum(_float_or_none(item.get("total")) or 0 for item in row.get("rows") or [])
    return SourceSnapshot(
        snapshot_id=str(row.get("id") or f"{series}:{observed.isoformat()}"),
        session_date=expected_date,
        observed_at=observed,
        series=series,
        kind=str(row.get("kind") or "unknown"),
        source_dte=dte,
        future_reference=reference,
        atm_iv=_float_or_none(row.get("atmVol")),
        iv_change=_float_or_none(row.get("volChange")),
        future_change=_float_or_none(row.get("futureChange")),
        activity_total=activity,
        ranges=ranges,
        strike_rows=[dict(item) for item in row.get("rows") or []],
    )


def _parse_datetime(value: Any) -> datetime:
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None
