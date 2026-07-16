from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime
from statistics import mean, pstdev
from typing import Any
from zoneinfo import ZoneInfo

from src.models.xau_market_context import XauPriceBar
from src.models.xau_vol2vol_history_walkforward import (
    XauVol2VolRangeDeskSnapshot,
    XauVol2VolStrikeSnapshot,
)
from src.xau_vol2vol_history_walkforward.oi_flow_audit import StrikeSnapshotIndex
from src.xau_vol2vol_history_walkforward.planning import XauPlanningSelection


def build_checkpoint_rows(
    selections: list[XauPlanningSelection],
    bars: list[XauPriceBar],
    strike_index: StrikeSnapshotIndex,
    *,
    timezone: str,
    range_snapshots: list[XauVol2VolRangeDeskSnapshot] | None = None,
    monthly_strikes: list[XauVol2VolStrikeSnapshot] | None = None,
) -> list[dict[str, Any]]:
    zone = ZoneInfo(timezone)
    bars_by_date: dict[str, list[XauPriceBar]] = defaultdict(list)
    for bar in bars:
        bars_by_date[bar.timestamp.astimezone(zone).date().isoformat()].append(bar)
    for items in bars_by_date.values():
        items.sort(key=lambda item: item.timestamp)
    ordered = sorted(
        selections,
        key=lambda item: (
            item.session_date,
            item.planning_mode if hasattr(item, "planning_mode") else "",
            item.planning_at,
        ),
    )
    morning: dict[tuple[str, str], dict[str, float | None]] = {}
    range_snapshots = range_snapshots or []
    monthly_strikes = monthly_strikes or []
    rows = []
    for selection in ordered:
        mode = (
            "fixed_morning" if selection.cycle_label.startswith("fixed_morning") else "rolling_30m"
        )
        key = (selection.session_date.isoformat(), mode)
        snapshot = selection.range_snapshot
        if snapshot.diff is None or snapshot.future_open is None:
            continue
        session_bars = bars_by_date.get(selection.session_date.isoformat(), [])
        past_bars = [bar for bar in session_bars if bar.timestamp <= selection.planning_at]
        if not past_bars:
            continue
        current_bar = past_bars[-1]
        levels = _mapped_levels(snapshot)
        one_sd = _one_sd(levels, current_bar.close)
        if one_sd is None or one_sd <= 0:
            continue
        morning.setdefault(
            key,
            {
                "xau": current_bar.close,
                "basis": float(snapshot.diff),
                "one_sd": one_sd,
                "iv": float(snapshot.vol_now) if snapshot.vol_now is not None else None,
            },
        )
        anchor = morning[key]
        iv = float(snapshot.vol_now) if snapshot.vol_now is not None else None
        raw_iv_history = _raw_iv_history(
            range_snapshots,
            source_session=selection.source_session_date.isoformat(),
            series=snapshot.series,
            at=selection.planning_at,
        )
        previous_iv = raw_iv_history[-2][1] if len(raw_iv_history) > 1 else None
        oi, previous_oi = strike_index.latest(
            session_date=selection.source_session_date.isoformat(),
            series=snapshot.series,
            kind="open_interest",
            at=selection.planning_at,
        )
        volume, previous_volume = strike_index.latest(
            session_date=selection.source_session_date.isoformat(),
            series=snapshot.series,
            kind="intraday_volume",
            at=selection.planning_at,
        )
        oi_features = _strike_features(
            oi,
            previous_oi,
            price=current_bar.close,
            basis=float(snapshot.diff),
            one_sd=one_sd,
            prefix="oi",
        )
        volume_features = _strike_features(
            volume,
            previous_volume,
            price=current_bar.close,
            basis=float(snapshot.diff),
            one_sd=one_sd,
            prefix="volume",
        )
        iv_change = iv - previous_iv if iv is not None and previous_iv is not None else None
        morning_iv = anchor.get("iv")
        iv_since_morning = (
            iv - float(morning_iv)
            if iv is not None and morning_iv is not None
            else None
        )
        iv_slope_30m = _slope(raw_iv_history, selection.planning_at, 30)
        iv_slope_60m = _slope(raw_iv_history, selection.planning_at, 60)
        monthly_confluence = _monthly_confluence(
            monthly_strikes,
            at=selection.planning_at,
            price=current_bar.close,
            basis=float(snapshot.diff),
            one_sd=one_sd,
        )
        row = {
            "checkpoint_id": (
                f"{selection.session_date}:{mode}:{selection.planning_at.isoformat()}"
            ),
            "session_date": selection.session_date.isoformat(),
            "source_session_date": selection.source_session_date.isoformat(),
            "planning_mode": mode,
            "checkpoint_at": selection.planning_at.isoformat(),
            "source_snapshot_at": snapshot.observed_at.isoformat(),
            "source_snapshot_age_seconds": selection.snapshot_age_at_planning_seconds,
            "source_alignment_seconds": selection.source_alignment_seconds,
            "selected_series": snapshot.series,
            "dte": snapshot.dte,
            "current_xauusd": current_bar.close,
            "current_price_timestamp": current_bar.timestamp.isoformat(),
            "morning_xauusd": anchor["xau"],
            "morning_basis": anchor["basis"],
            "current_basis": float(snapshot.diff),
            "basis_drift": float(snapshot.diff) - anchor["basis"],
            "one_sd_points": one_sd,
            "price_z_from_morning": (current_bar.close - anchor["xau"]) / anchor["one_sd"],
            "price_z_from_current_snapshot": (current_bar.close - float(snapshot.cfd_open))
            / one_sd,
            "atr_5m": _atr(past_bars, 5),
            "atr_15m": _atr(past_bars, 15),
            "atr_1h": _atr(past_bars, 60),
            "realized_vol_30m": _realized_vol(past_bars, 30),
            "realized_vol_session": _realized_vol(past_bars, len(past_bars)),
            "atm_iv": iv,
            "atm_iv_change_since_morning": iv_since_morning,
            "atm_iv_change_previous": iv_change,
            "iv_slope_30m": iv_slope_30m,
            "iv_slope_60m": iv_slope_60m,
            "iv_state": _iv_state(iv_slope_30m),
            "minutes_since_0700": max(
                int((selection.planning_at.hour * 60 + selection.planning_at.minute) - 420),
                0,
            ),
            **levels,
            **oi_features,
            **volume_features,
            "monthly_oi_confluence": monthly_confluence,
            "future_feature_violation": any(
                timestamp is not None and timestamp > selection.planning_at
                for timestamp in (
                    oi.observed_at if oi else None,
                    volume.observed_at if volume else None,
                    current_bar.timestamp,
                )
            ),
            "research_only": True,
            "signal_allowed": False,
        }
        rows.append(row)
    return rows


def _mapped_levels(snapshot: Any) -> dict[str, float | None]:
    diff = float(snapshot.diff)

    def mapped(value: float | None) -> float | None:
        return float(value) - diff if value is not None else None
    lower_1 = mapped(snapshot.future_buy_1sd)
    lower_2 = mapped(snapshot.future_buy_2sd)
    lower_3 = mapped(snapshot.future_buy_3sd)
    upper_1 = mapped(snapshot.future_sell_1sd)
    upper_2 = mapped(snapshot.future_sell_2sd)
    upper_3 = mapped(snapshot.future_sell_3sd)
    return {
        "mapped_center": mapped(snapshot.future_open),
        "lower_1sd": lower_1,
        "lower_1_5sd": _mid(lower_1, lower_2),
        "lower_2sd": lower_2,
        "lower_3sd": lower_3,
        "upper_1sd": upper_1,
        "upper_1_5sd": _mid(upper_1, upper_2),
        "upper_2sd": upper_2,
        "upper_3sd": upper_3,
    }


def _one_sd(levels: dict[str, float | None], fallback_center: float) -> float | None:
    center = levels["mapped_center"] or fallback_center
    distances = [
        abs(center - value)
        for value in (levels["lower_1sd"], levels["upper_1sd"])
        if value is not None
    ]
    return mean(distances) if distances else None


def _strike_features(
    group: Any,
    previous: Any,
    *,
    price: float,
    basis: float,
    one_sd: float,
    prefix: str,
) -> dict[str, Any]:
    empty = {
        f"{prefix}_snapshot_at": None,
        f"{prefix}_nearest_wall": None,
        f"{prefix}_distance_points": None,
        f"{prefix}_distance_sd": None,
        f"{prefix}_rank": None,
        f"{prefix}_percentile": None,
        f"{prefix}_call": None,
        f"{prefix}_put": None,
        f"{prefix}_total": None,
        f"{prefix}_imbalance": None,
        f"{prefix}_change": None,
        f"{prefix}_change_percentile": None,
        f"{prefix}_wall_persistence": None,
        f"{prefix}_vol_settle": None,
        f"{prefix}_next_wall_above": None,
        f"{prefix}_next_wall_below": None,
        f"{prefix}_low_activity_gap_above": None,
        f"{prefix}_low_activity_gap_below": None,
    }
    if group is None or not group.rows:
        return empty
    rows = [row for row in group.rows if row.total is not None]
    if not rows:
        return empty
    mapped = [(row, row.strike - basis) for row in rows]
    nearest, mapped_strike = min(mapped, key=lambda item: abs(item[1] - price))
    ranked = sorted(rows, key=lambda row: float(row.total or 0), reverse=True)
    rank = ranked.index(nearest) + 1
    totals = sorted(float(row.total or 0) for row in rows)
    percentile = sum(value <= float(nearest.total or 0) for value in totals) / len(totals)
    previous_by_strike = {
        row.strike: row for row in (previous.rows if previous is not None else [])
    }
    prior = previous_by_strike.get(nearest.strike)
    change = (
        float(nearest.total) - float(prior.total)
        if prior is not None and prior.total is not None and nearest.total is not None
        else nearest.total_change
    )
    changes = sorted(float(row.total_change) for row in rows if row.total_change is not None)
    change_percentile = (
        sum(value <= float(change) for value in changes) / len(changes)
        if change is not None and changes
        else None
    )
    previous_top = {
        row.strike
        for row in sorted(
            previous.rows if previous is not None else [],
            key=lambda row: float(row.total or 0),
            reverse=True,
        )[:5]
    }
    above = sorted(value for _, value in mapped if value > price)
    below = sorted((value for _, value in mapped if value < price), reverse=True)
    nonzero = [float(row.total or 0) for row in rows if float(row.total or 0) > 0]
    low_cutoff = _quantile(nonzero, 0.25) if nonzero else None
    return {
        f"{prefix}_snapshot_at": group.observed_at.isoformat(),
        f"{prefix}_nearest_wall": mapped_strike,
        f"{prefix}_distance_points": abs(mapped_strike - price),
        f"{prefix}_distance_sd": abs(mapped_strike - price) / one_sd,
        f"{prefix}_rank": rank,
        f"{prefix}_percentile": percentile,
        f"{prefix}_call": nearest.call,
        f"{prefix}_put": nearest.put,
        f"{prefix}_total": nearest.total,
        f"{prefix}_imbalance": _imbalance(nearest.call, nearest.put),
        f"{prefix}_change": change,
        f"{prefix}_change_percentile": change_percentile,
        f"{prefix}_wall_persistence": nearest.strike in previous_top if previous else None,
        f"{prefix}_vol_settle": nearest.vol_settle,
        f"{prefix}_next_wall_above": above[0] if above else None,
        f"{prefix}_next_wall_below": below[0] if below else None,
        f"{prefix}_low_activity_gap_above": _low_gap(
            mapped, price, above[0] if above else None, low_cutoff
        ),
        f"{prefix}_low_activity_gap_below": _low_gap(
            mapped, below[0] if below else None, price, low_cutoff
        ),
    }


def _atr(bars: list[XauPriceBar], count: int) -> float | None:
    selected = bars[-count:]
    return mean(bar.high - bar.low for bar in selected) if selected else None


def _realized_vol(bars: list[XauPriceBar], count: int) -> float | None:
    selected = bars[-max(count, 2) :]
    returns = [
        math.log(current.close / previous.close)
        for previous, current in zip(selected, selected[1:], strict=False)
        if previous.close > 0 and current.close > 0
    ]
    return pstdev(returns) if len(returns) > 1 else None


def _slope(history: list[tuple[datetime, float]], at: datetime, minutes: int) -> float | None:
    eligible = [
        (timestamp, value)
        for timestamp, value in history
        if (at - timestamp).total_seconds() <= minutes * 60
    ]
    if len(eligible) < 2:
        return None
    elapsed = (eligible[-1][0] - eligible[0][0]).total_seconds() / 60
    return (eligible[-1][1] - eligible[0][1]) / elapsed if elapsed else None


def _raw_iv_history(
    snapshots: list[XauVol2VolRangeDeskSnapshot],
    *,
    source_session: str,
    series: str | None,
    at: datetime,
) -> list[tuple[datetime, float]]:
    by_time = {
        row.observed_at: float(row.vol_now)
        for row in snapshots
        if row.session_date.isoformat() == source_session
        and row.series == series
        and row.observed_at <= at
        and row.vol_now is not None
    }
    return sorted(by_time.items())


def _monthly_confluence(
    rows: list[XauVol2VolStrikeSnapshot],
    *,
    at: datetime,
    price: float,
    basis: float,
    one_sd: float,
) -> bool | None:
    eligible = [row for row in rows if row.observed_at <= at and row.total is not None]
    if not eligible:
        return None
    latest = max(row.observed_at for row in eligible)
    snapshot = [row for row in eligible if row.observed_at == latest]
    top = sorted(snapshot, key=lambda row: float(row.total or 0), reverse=True)[:5]
    return any(abs((row.strike - basis) - price) / one_sd <= 0.25 for row in top)


def _iv_state(slope: float | None) -> str | None:
    if slope is None:
        return None
    if slope > 0.002:
        return "expanding"
    if slope < -0.002:
        return "compressing"
    return "stable"


def _imbalance(call: float | None, put: float | None) -> float | None:
    if call is None or put is None or call + put == 0:
        return None
    return (call - put) / (call + put)


def _low_gap(
    mapped: list[tuple[Any, float]], lower: float | None, upper: float | None, cutoff: float | None
) -> bool | None:
    if lower is None or upper is None or cutoff is None:
        return None
    between = [float(row.total or 0) for row, value in mapped if lower < value < upper]
    return bool(between) and max(between) <= cutoff


def _quantile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[int((len(ordered) - 1) * q)]


def _mid(first: float | None, second: float | None) -> float | None:
    return (first + second) / 2 if first is not None and second is not None else None
