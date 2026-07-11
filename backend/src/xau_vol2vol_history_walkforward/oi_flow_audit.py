from __future__ import annotations

import csv
from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import mean, median
from typing import Any

from src.models.xau_market_context import XauPriceBar
from src.models.xau_vol2vol_history_walkforward import XauVol2VolStrikeSnapshot
from src.xau_vol2vol_history_walkforward.sd_zone_audit import EXIT_STRATEGIES


@dataclass(frozen=True)
class SnapshotGroup:
    observed_at: datetime
    rows: list[XauVol2VolStrikeSnapshot]


class StrikeSnapshotIndex:
    def __init__(self, rows: list[XauVol2VolStrikeSnapshot]) -> None:
        grouped: dict[tuple[str, str | None, str, datetime], list] = defaultdict(list)
        for row in rows:
            grouped[
                (row.session_date.isoformat(), row.series, row.snapshot_kind, row.observed_at)
            ].append(row)
        self._groups: dict[tuple[str, str | None, str], list[SnapshotGroup]] = defaultdict(list)
        for (session, series, kind, observed_at), items in grouped.items():
            self._groups[(session, series, kind)].append(SnapshotGroup(observed_at, items))
        for groups in self._groups.values():
            groups.sort(key=lambda item: item.observed_at)

    def latest(
        self,
        *,
        session_date: str,
        series: str | None,
        kind: str,
        at: datetime,
    ) -> tuple[SnapshotGroup | None, SnapshotGroup | None]:
        groups = self._groups.get((session_date, series, kind), [])
        times = [item.observed_at for item in groups]
        position = bisect_right(times, at) - 1
        if position < 0:
            return None, None
        previous = None
        if position > 0:
            previous_by_strike = {}
            for group in groups[:position]:
                for row in group.rows:
                    previous_by_strike[row.strike] = row
            previous = SnapshotGroup(
                groups[position - 1].observed_at,
                list(previous_by_strike.values()),
            )
        return groups[position], previous


def build_opportunity_features(
    result_sets: list[dict[str, Any]],
    daily_index: StrikeSnapshotIndex,
    *,
    monthly_index: StrikeSnapshotIndex | None = None,
    quikstrike_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    quikstrike_rows = quikstrike_rows or []
    for result in result_sets:
        diagnostics = {
            (item["session_date"], item["planning_at"]): item
            for item in result["diagnostics"]
        }
        touched = [
            item
            for item in result["opportunities"]
            if item["touched"]
            and item["entry_definition"] in {"zone_2_entry", "zone_2_mid"}
        ]
        for opportunity in _first_opportunities(touched):
            diagnostic = diagnostics[
                (opportunity["session_date"], opportunity["planning_at"])
            ]
            plan_at = datetime.fromisoformat(opportunity["planning_at"])
            touch_at = datetime.fromisoformat(opportunity["first_touch_time"])
            plan_state = build_feature_state(
                opportunity,
                diagnostic,
                plan_at,
                daily_index,
                monthly_index=monthly_index,
                quikstrike_rows=quikstrike_rows,
            )
            touch_state = build_feature_state(
                opportunity,
                diagnostic,
                touch_at,
                daily_index,
                monthly_index=monthly_index,
                quikstrike_rows=quikstrike_rows,
            )
            feature = {
                    **opportunity,
                    "source_session_date": diagnostic["source_session_date"],
                    "future_reference": diagnostic["future_reference"],
                    "xau_reference": diagnostic["xau_reference"],
                    "basis_diff_used": diagnostic["calculated_diff"],
                    "one_sd_points": _one_sd(diagnostic, opportunity["side"]),
                    "lower_2sd": diagnostic["lower_2sd"],
                    "lower_2_5sd": diagnostic["lower_2_5sd"],
                    "upper_2sd": diagnostic["upper_2sd"],
                    "upper_2_5sd": diagnostic["upper_2_5sd"],
                    "atm_vol": diagnostic.get("atm_vol"),
                    "atm_vol_change": diagnostic.get("atm_vol_change"),
                    "plan_state": plan_state,
                    "touch_state": touch_state,
                    "plan_oi_snapshot_time": plan_state["oi_snapshot_time"],
                    "plan_volume_snapshot_time": plan_state["volume_snapshot_time"],
                    "touch_oi_snapshot_time": touch_state["oi_snapshot_time"],
                    "touch_volume_snapshot_time": touch_state["volume_snapshot_time"],
                    "plan_feature_age_seconds": max(
                        value
                        for value in (
                            plan_state["oi_feature_age_seconds"],
                            plan_state["volume_feature_age_seconds"],
                        )
                        if value is not None
                    )
                    if plan_state["oi"] or plan_state["volume"]
                    else None,
                    "touch_feature_age_seconds": max(
                        value
                        for value in (
                            touch_state["oi_feature_age_seconds"],
                            touch_state["volume_feature_age_seconds"],
                        )
                        if value is not None
                    )
                    if touch_state["oi"] or touch_state["volume"]
                    else None,
                    "research_only": True,
                    "signal_allowed": False,
                }
            feature["descriptive_labels"] = _labels(feature)
            features.append(feature)
    return features


def build_feature_state(
    opportunity: dict[str, Any],
    diagnostic: dict[str, Any],
    state_at: datetime,
    daily_index: StrikeSnapshotIndex,
    *,
    monthly_index: StrikeSnapshotIndex | None = None,
    quikstrike_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    session = diagnostic["source_session_date"]
    series = opportunity["selected_series"]
    oi, previous_oi = daily_index.latest(
        session_date=session,
        series=series,
        kind="open_interest",
        at=state_at,
    )
    volume, previous_volume = daily_index.latest(
        session_date=session,
        series=series,
        kind="intraday_volume",
        at=state_at,
    )
    entry = float(opportunity["entry_level"])
    one_sd = _one_sd(diagnostic, opportunity["side"])
    oi_feature = _snapshot_feature(
        oi,
        previous_oi,
        entry=entry,
        one_sd=one_sd,
        diagnostic=diagnostic,
        mapping_mode=opportunity["mapping_mode"],
        value_kind="oi",
    )
    volume_feature = _snapshot_feature(
        volume,
        previous_volume,
        entry=entry,
        one_sd=one_sd,
        diagnostic=diagnostic,
        mapping_mode=opportunity["mapping_mode"],
        value_kind="volume",
    )
    monthly = _monthly_feature(
        monthly_index,
        state_at=state_at,
        entry=entry,
        one_sd=one_sd,
        diagnostic=diagnostic,
        mapping_mode=opportunity["mapping_mode"],
        daily_series=series,
    )
    quikstrike = _quikstrike_feature(
        quikstrike_rows or [],
        state_at=state_at,
        series=series,
        entry=entry,
        diagnostic=diagnostic,
        mapping_mode=opportunity["mapping_mode"],
    )
    missing = []
    if oi is None:
        missing.append("daily_open_interest")
    if volume is None:
        missing.append("intraday_volume")
    if monthly is None:
        missing.append("monthly_open_interest")
    if quikstrike is None:
        missing.append("quikstrike")
    return {
        "state_at": state_at.isoformat(),
        "oi_snapshot_time": oi.observed_at.isoformat() if oi else None,
        "volume_snapshot_time": volume.observed_at.isoformat() if volume else None,
        "oi_feature_age_seconds": (
            (state_at - oi.observed_at).total_seconds() if oi else None
        ),
        "volume_feature_age_seconds": (
            (state_at - volume.observed_at).total_seconds() if volume else None
        ),
        "oi": oi_feature,
        "volume": volume_feature,
        "monthly_oi": monthly,
        "quikstrike": quikstrike,
        "missing_feature_reasons": missing,
        "future_feature_violation": bool(
            (oi and oi.observed_at > state_at) or (volume and volume.observed_at > state_at)
        ),
        "research_only": True,
        "signal_allowed": False,
    }


def build_coverage(features: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in features:
        groups[(row["planning_mode"], row["mapping_mode"])].append(row)
    summaries = []
    for (planning_mode, mapping_mode), rows in sorted(groups.items()):
        count = len(rows)
        metrics = {
            "plan_time_oi": sum(row["plan_state"]["oi"] is not None for row in rows),
            "plan_time_volume": sum(
                row["plan_state"]["volume"] is not None for row in rows
            ),
            "touch_time_oi": sum(row["touch_state"]["oi"] is not None for row in rows),
            "touch_time_volume": sum(
                row["touch_state"]["volume"] is not None for row in rows
            ),
            "monthly_oi": sum(
                row["plan_state"]["monthly_oi"] is not None for row in rows
            ),
            "quikstrike_oi_change": sum(
                row["plan_state"]["quikstrike"] is not None
                and row["plan_state"]["quikstrike"].get("oi_change") is not None
                for row in rows
            ),
            "vol_settle": sum(
                row["plan_state"]["oi"] is not None
                and row["plan_state"]["oi"].get("vol_settle") is not None
                for row in rows
            ),
            "atm_vol": sum(row.get("atm_vol") is not None for row in rows),
            "same_series_match": sum(
                row["plan_state"]["oi"] is not None for row in rows
            ),
        }
        summaries.append(
            {
                "planning_mode": planning_mode,
                "mapping_mode": mapping_mode,
                "unique_opportunity_count": count,
                **{f"{key}_count": value for key, value in metrics.items()},
                **{
                    f"{key}_percentage": round(value / count * 100, 2) if count else 0.0
                    for key, value in metrics.items()
                },
                "stale_feature_count": sum(
                    (row["plan_state"]["oi_feature_age_seconds"] or 0) > 1800
                    for row in rows
                ),
                "future_feature_lookahead_count": sum(
                    row[state]["future_feature_violation"]
                    for row in rows
                    for state in ("plan_state", "touch_state")
                ),
                "missingness_by_field": {
                    key: count - value for key, value in metrics.items()
                },
                "research_only": True,
                "signal_allowed": False,
            }
        )
    return {
        "summaries": summaries,
        "research_only": True,
        "signal_allowed": False,
    }


def build_descriptive_stratification(
    features: list[dict[str, Any]],
    exit_backtest: dict[str, Any],
) -> dict[str, Any]:
    outcomes = _base_outcomes(exit_backtest)
    rows = []
    dimensions = (
        "top5_wall_near_entry",
        "wall_distance_bucket",
        "oi_confluence",
        "imbalance_label",
        "volume_direction",
        "oi_direction",
        "monthly_wall_confluence",
        "wormhole_label",
        "atm_vol_direction",
    )
    for feature in features:
        plan = feature["plan_state"]
        labels = _labels(feature)
        for outcome in outcomes.get(feature["opportunity_id"], []):
            common = {
                "planning_mode": feature["planning_mode"],
                "mapping_mode": feature["mapping_mode"],
                "strategy_id": outcome["strategy_id"],
                "side": feature["side"],
            }
            for dimension in dimensions:
                rows.append(
                    {
                        **common,
                        "dimension": dimension,
                        "label": labels[dimension],
                        "opportunity_id": feature["opportunity_id"],
                        "status": outcome["status"],
                        "mfe_points": outcome["mfe_points"],
                        "mae_points": outcome["mae_points"],
                        "net_points": outcome["net_points"],
                        "duration_minutes": _duration(outcome),
                        "feature_snapshot_time": plan["oi_snapshot_time"],
                    }
                )
    grouped: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[
            (
                row["planning_mode"],
                row["mapping_mode"],
                row["strategy_id"],
                row["side"],
                row["dimension"],
                row["label"],
            )
        ].append(row)
    summaries = []
    for key, items in sorted(grouped.items()):
        summaries.append(
            {
                "planning_mode": key[0],
                "mapping_mode": key[1],
                "strategy_id": key[2],
                "side": key[3],
                "dimension": key[4],
                "label": key[5],
                "unique_opportunity_count": len(
                    {item["opportunity_id"] for item in items}
                ),
                "fill_count": len(items),
                "target_hit_count": sum(item["status"] == "target_hit" for item in items),
                "stop_hit_count": sum(item["status"] == "stop_hit" for item in items),
                "time_exit_count": sum(
                    item["status"].startswith("time_exit") for item in items
                ),
                "average_mfe_points": _average(item["mfe_points"] for item in items),
                "average_mae_points": _average(item["mae_points"] for item in items),
                "net_expectancy_after_one_point": _average(
                    item["net_points"] for item in items
                ),
                "median_duration_minutes": _median(
                    item["duration_minutes"] for item in items
                ),
                "research_only": True,
                "signal_allowed": False,
            }
        )
    return {
        "summaries": summaries,
        "best_group_selection": "not_permitted",
        "research_only": True,
        "signal_allowed": False,
    }


def build_conditional_variants(
    features: list[dict[str, Any]],
    exit_backtest: dict[str, Any],
    *,
    bars: list[XauPriceBar] | None = None,
    daily_index: StrikeSnapshotIndex | None = None,
) -> dict[str, Any]:
    coverage = build_coverage(features)
    primary = [
        row
        for row in coverage["summaries"]
        if row["mapping_mode"] == "same_time_basis"
    ]
    gate_passed = all(
        row["unique_opportunity_count"] >= 10
        and row["plan_time_oi_percentage"] >= 70
        and row["plan_time_volume_percentage"] >= 70
        and row["touch_time_oi_percentage"] >= 70
        and row["touch_time_volume_percentage"] >= 70
        for row in primary
    )
    if not gate_passed:
        return {
            "coverage_gate_passed": False,
            "skip_reason": "Daily plan/touch OI and volume coverage gate failed.",
            "variants": [],
            "evidence_status": "insufficient_sample",
            "research_only": True,
            "signal_allowed": False,
        }
    base = _base_outcomes(exit_backtest)
    variants = []
    for variant in ("F0", "F1"):
        selected = []
        for feature in features:
            if feature["mapping_mode"] != "same_time_basis":
                continue
            labels = _labels(feature)
            if variant == "F1" and labels["top5_wall_near_entry"] != "yes":
                continue
            selected.extend(base.get(feature["opportunity_id"], []))
        variants.append(_variant_summary(variant, selected))
    confirmation_records = []
    if bars is None or daily_index is None:
        variants.extend(
            _unavailable_confirmation_variant(name) for name in ("F2", "F3", "BR")
        )
    else:
        feature_by_id = {
            row["opportunity_id"]: row
            for row in features
            if row["mapping_mode"] == "same_time_basis"
        }
        f2_rows = []
        f3_rows = []
        breakout_blocked = set()
        for feature in feature_by_id.values():
            labels = _labels(feature)
            plan_oi = feature["plan_state"]["oi"] or {}
            touch_volume = feature["touch_state"]["volume"] or {}
            wall = plan_oi.get("mapped_xauusd_strike")
            if (
                wall is not None
                and _accepted_beyond_wall(feature, bars, wall)
                and (touch_volume.get("change_percentile") or 0) >= 0.75
                and bool(plan_oi.get("low_activity_gap_toward_stop"))
            ):
                breakout_blocked.add(feature["opportunity_id"])
            if labels["top5_wall_near_entry"] != "yes":
                continue
            confirmation = _rejection_confirmation(feature, bars)
            if confirmation is None:
                continue
            confirmation_state = build_feature_state(
                feature,
                {
                    "source_session_date": feature["source_session_date"],
                    "calculated_diff": feature["basis_diff_used"],
                    "future_reference": feature["future_reference"],
                    "xau_reference": feature["xau_reference"],
                    "lower_1sd": feature["xau_reference"] - feature["one_sd_points"],
                    "upper_1sd": feature["xau_reference"] + feature["one_sd_points"],
                    "lower_2_5sd": feature["lower_2_5sd"],
                    "upper_2_5sd": feature["upper_2_5sd"],
                },
                confirmation["confirmation_at"],
                daily_index,
            )
            volume = confirmation_state["volume"] or {}
            accepted = wall is not None and _accepted_before_confirmation(
                feature,
                bars,
                wall,
                confirmation["confirmation_at"],
            )
            for strategy_id, strategy in EXIT_STRATEGIES.items():
                if strategy["entry_definition"] != feature["entry_definition"]:
                    continue
                outcome = _simulate_confirmed(
                    feature,
                    bars,
                    confirmation,
                    strategy_id=strategy_id,
                    target_sd=float(strategy["target_sd"]),
                    stop_sd=float(strategy["stop_sd"]),
                )
                f2_rows.append(outcome)
                volume_percentile = volume.get("change_percentile")
                if (
                    not accepted
                    and volume_percentile is not None
                    and volume_percentile < 0.75
                ):
                    f3_rows.append(outcome)
            confirmation_records.append(
                {
                    "opportunity_id": feature["opportunity_id"],
                    "confirmation_timestamp": confirmation["confirmation_at"].isoformat(),
                    "next_executable_entry_timestamp": confirmation["entry_at"].isoformat(),
                    "next_executable_entry_price": confirmation["entry_price"],
                    "confirmation_volume_change_percentile": volume.get(
                        "change_percentile"
                    ),
                    "accepted_beyond_wall_before_confirmation": accepted,
                }
            )
        variants.append(_variant_summary("F2", f2_rows))
        variants.append(_variant_summary("F3", f3_rows))
        br_rows = [
            outcome
            for opportunity_id, items in base.items()
            if opportunity_id in feature_by_id and opportunity_id not in breakout_blocked
            for outcome in items
        ]
        br_summary = _variant_summary("BR", br_rows)
        br_summary["blocked_opportunity_count"] = len(breakout_blocked)
        variants.append(br_summary)
    f0 = next((row for row in variants if row["variant"] == "F0"), None)
    if f0:
        for row in variants:
            row["opportunities_rejected_vs_f0"] = (
                f0["unique_opportunity_count"] - row["unique_opportunity_count"]
            )
            row["expectancy_change_vs_f0"] = (
                row.get("net_expectancy_after_one_point", 0)
                - f0.get("net_expectancy_after_one_point", 0)
            )
    return {
        "coverage_gate_passed": True,
        "variants": variants,
        "confirmation_records": confirmation_records if bars is not None else [],
        "evidence_status": "insufficient_sample",
        "research_only": True,
        "signal_allowed": False,
    }


def load_quikstrike_rows(folder: Path) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(folder.glob("*_xau_vol_oi_input.csv")):
        with path.open("r", encoding="utf-8", newline="") as handle:
            for raw in csv.DictReader(handle):
                timestamp = datetime.fromisoformat(raw["timestamp"].replace("Z", "+00:00"))
                rows.append(
                    {
                        "timestamp": timestamp,
                        "series": raw.get("expiry"),
                        "strike": _float(raw.get("strike")),
                        "oi_change": _float(raw.get("oi_change")),
                        "open_interest": _float(raw.get("open_interest")),
                        "volume": _float(raw.get("volume")),
                    }
                )
    return rows


def _snapshot_feature(
    group: SnapshotGroup | None,
    previous: SnapshotGroup | None,
    *,
    entry: float,
    one_sd: float,
    diagnostic: dict[str, Any],
    mapping_mode: str,
    value_kind: str,
) -> dict[str, Any] | None:
    if group is None:
        return None
    mapped = [
        (row, _map_strike(row.strike, diagnostic, mapping_mode)) for row in group.rows
    ]
    nearest, mapped_strike = min(mapped, key=lambda item: abs(item[1] - entry))
    values = [float(row.total) for row, _ in mapped if row.total is not None]
    ranked = sorted(values, reverse=True)
    value = float(nearest.total) if nearest.total is not None else None
    rank = ranked.index(value) + 1 if value is not None and value in ranked else None
    percentile = _percentile_rank(values, value)
    previous_row = None
    if previous:
        previous_row = next(
            (row for row in previous.rows if row.strike == nearest.strike), None
        )
    derived_change = (
        float(nearest.total) - float(previous_row.total)
        if nearest.total is not None
        and previous_row is not None
        and previous_row.total is not None
        else None
    )
    source_change = nearest.total_change
    changes = []
    if previous:
        previous_by_strike = {row.strike: row for row in previous.rows}
        for current_row in group.rows:
            prior = previous_by_strike.get(current_row.strike)
            if (
                current_row.total is not None
                and prior is not None
                and prior.total is not None
            ):
                changes.append(float(current_row.total) - float(prior.total))
    top = sorted(
        [(row, strike) for row, strike in mapped if row.total is not None],
        key=lambda item: float(item[0].total),
        reverse=True,
    )
    walls = sorted(strike for _, strike in top[:10])
    above = next((strike for strike in walls if strike > entry), None)
    below = next((strike for strike in reversed(walls) if strike < entry), None)
    imbalance = _imbalance(nearest.call, nearest.put)
    direction = _change_direction(derived_change)
    distance_sd = abs(mapped_strike - entry) / one_sd if one_sd else None
    return {
        "snapshot_time": group.observed_at.isoformat(),
        "original_futures_strike": nearest.strike,
        "mapped_xauusd_strike": mapped_strike,
        "mapping_mode": mapping_mode,
        "basis_diff_used": diagnostic["calculated_diff"],
        "selected_series": nearest.series,
        "distance_to_entry_points": abs(mapped_strike - entry),
        "distance_to_entry_sd": distance_sd,
        "rank": rank,
        "percentile": percentile,
        "top_5": rank is not None and rank <= 5,
        "top_10": rank is not None and rank <= 10,
        "call": nearest.call,
        "put": nearest.put,
        "total": nearest.total,
        "call_put_imbalance": imbalance[0],
        "imbalance_label": imbalance[1],
        "source_provided_change": source_change,
        "derived_change": derived_change,
        "change_discrepancy": (
            float(source_change) - derived_change
            if source_change is not None and derived_change is not None
            else None
        ),
        "change_direction": direction,
        "change_percentile": _percentile_rank(changes, derived_change),
        "vol_settle": nearest.vol_settle,
        "next_mapped_wall_above": above,
        "next_mapped_wall_below": below,
        "low_activity_gap_toward_target": _low_gap(mapped, entry, diagnostic["xau_reference"]),
        "low_activity_gap_toward_stop": _low_gap(
            mapped,
            entry,
            float(diagnostic["lower_2_5sd"])
            if entry < diagnostic["xau_reference"]
            else float(diagnostic["upper_2_5sd"]),
        ),
        "value_kind": value_kind,
    }


def _monthly_feature(
    index,
    *,
    state_at,
    entry,
    one_sd,
    diagnostic,
    mapping_mode,
    daily_series,
):
    if index is None:
        return None
    candidates = []
    for (session, series, kind), groups in index._groups.items():
        if kind != "monthly_open_interest":
            continue
        times = [item.observed_at for item in groups]
        position = bisect_right(times, state_at) - 1
        if position >= 0:
            candidates.append((groups[position], series, session))
    if not candidates:
        return None
    group, series, _ = max(candidates, key=lambda item: item[0].observed_at)
    mapped = [
        (row, _map_strike(row.strike, diagnostic, mapping_mode)) for row in group.rows
    ]
    nearest, strike = min(mapped, key=lambda item: abs(item[1] - entry))
    return {
        "snapshot_time": group.observed_at.isoformat(),
        "series": series,
        "daily_series_match": series == daily_series,
        "original_futures_strike": nearest.strike,
        "mapped_xauusd_strike": strike,
        "distance_points": abs(strike - entry),
        "distance_sd": abs(strike - entry) / one_sd if one_sd else None,
        "total": nearest.total,
    }


def _quikstrike_feature(rows, *, state_at, series, entry, diagnostic, mapping_mode):
    eligible = [row for row in rows if row["series"] == series and row["timestamp"] <= state_at]
    if not eligible:
        return None
    latest = max(row["timestamp"] for row in eligible)
    snapshot = [row for row in eligible if row["timestamp"] == latest]
    nearest = min(
        snapshot,
        key=lambda row: abs(_map_strike(row["strike"], diagnostic, mapping_mode) - entry),
    )
    same_strike = [row for row in snapshot if row["strike"] == nearest["strike"]]
    return {
        "snapshot_time": latest.isoformat(),
        "series": series,
        "strike": nearest["strike"],
        "mapped_xauusd_strike": _map_strike(nearest["strike"], diagnostic, mapping_mode),
        "oi_change": _sum_present(row["oi_change"] for row in same_strike),
        "open_interest": _sum_present(row["open_interest"] for row in same_strike),
        "volume": _sum_present(row["volume"] for row in same_strike),
    }


def _labels(feature):
    state = feature["plan_state"]
    oi = state["oi"] or {}
    volume = state["volume"] or {}
    monthly = state["monthly_oi"]
    distance = oi.get("distance_to_entry_sd")
    near_top5 = bool(oi.get("top_5") and distance is not None and distance <= 0.25)
    if distance is None:
        bucket = "unavailable"
    elif distance <= 0.10:
        bucket = "<=0.10sd"
    elif distance <= 0.25:
        bucket = "0.10-0.25sd"
    elif distance <= 0.50:
        bucket = "0.25-0.50sd"
    else:
        bucket = ">0.50sd"
    confluence = "strong" if near_top5 else "medium" if oi.get("top_10") else "weak"
    target_gap = bool(oi.get("low_activity_gap_toward_target"))
    stop_gap = bool(oi.get("low_activity_gap_toward_stop"))
    if target_gap and stop_gap:
        wormhole = "both"
    elif target_gap:
        wormhole = "toward_target"
    elif stop_gap:
        wormhole = "toward_stop"
    else:
        wormhole = "none"
    atm_change = feature.get("atm_vol_change")
    return {
        "top5_wall_near_entry": "yes" if near_top5 else "no",
        "wall_distance_bucket": bucket,
        "oi_confluence": confluence if oi else "unavailable",
        "imbalance_label": oi.get("imbalance_label", "unavailable"),
        "volume_direction": volume.get("change_direction", "unavailable"),
        "oi_direction": oi.get("change_direction", "unavailable"),
        "monthly_wall_confluence": (
            "yes"
            if monthly and monthly["distance_sd"] <= 0.25
            else "no"
            if monthly
            else "unavailable"
        ),
        "wormhole_label": wormhole,
        "atm_vol_direction": _change_direction(atm_change),
    }


def _first_opportunities(items):
    first = {}
    for item in sorted(items, key=lambda row: row["first_touch_time"]):
        key = (item["session_date"], item["side"], item["entry_definition"])
        first.setdefault(key, item)
    return list(first.values())


def _base_outcomes(exit_backtest):
    grouped = defaultdict(list)
    for experiment in exit_backtest["experiments"]:
        for row in experiment["outcomes"]:
            if row["cost_points"] == 1.0:
                grouped[row["opportunity_id"]].append(row)
    return grouped


def _variant_summary(name, rows):
    opportunities = sorted({row["opportunity_id"] for row in rows})
    sessions = sorted({row["session_date"] for row in rows if row.get("session_date")})
    split = max(int(len(sessions) * 0.7), 1) if sessions else 0
    development_sessions = set(sessions[:split])
    holdout_sessions = set(sessions[split:])
    result = {
        "variant": name,
        "status": "completed",
        "unique_opportunity_count": len(opportunities),
        "configuration_fill_count": len(rows),
        "target_hit_count": sum(row["status"] == "target_hit" for row in rows),
        "stop_hit_count": sum(row["status"] == "stop_hit" for row in rows),
        "time_exit_count": sum(row["status"].startswith("time_exit") for row in rows),
        "average_mfe_points": _average(row["mfe_points"] for row in rows),
        "average_mae_points": _average(row["mae_points"] for row in rows),
        "net_expectancy_after_one_point": _average(row["net_points"] for row in rows),
        "development_opportunity_count": len(
            {
                row["opportunity_id"]
                for row in rows
                if row.get("session_date") in development_sessions
            }
        ),
        "holdout_opportunity_count": len(
            {
                row["opportunity_id"]
                for row in rows
                if row.get("session_date") in holdout_sessions
            }
        ),
        "research_only": True,
        "signal_allowed": False,
    }
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row.get("planning_mode"), row["strategy_id"], row["side"])].append(row)
    result["groups"] = [
        {
            "planning_mode": key[0],
            "strategy_id": key[1],
            "side": key[2],
            "unique_opportunity_count": len(
                {item["opportunity_id"] for item in items}
            ),
            "target_hit_count": sum(item["status"] == "target_hit" for item in items),
            "stop_hit_count": sum(item["status"] == "stop_hit" for item in items),
            "time_exit_count": sum(
                item["status"].startswith("time_exit") for item in items
            ),
            "net_expectancy_after_one_point": _average(
                item["net_points"] for item in items
            ),
        }
        for key, items in sorted(grouped.items(), key=lambda value: str(value[0]))
    ]
    return result


def _map_strike(strike, diagnostic, mapping_mode):
    if mapping_mode == "same_time_basis":
        return float(strike) - float(diagnostic["calculated_diff"])
    return float(diagnostic["xau_reference"]) + (
        float(strike) - float(diagnostic["future_reference"])
    )


def _one_sd(diagnostic, side):
    center = float(diagnostic["xau_reference"])
    if side == "long_reversion":
        return center - float(diagnostic["lower_1sd"])
    return float(diagnostic["upper_1sd"]) - center


def _imbalance(call, put):
    if call is None or put is None or float(call) + float(put) == 0:
        return None, "unavailable"
    value = (float(call) - float(put)) / (float(call) + float(put))
    label = "call_heavy" if value >= 0.2 else "put_heavy" if value <= -0.2 else "balanced"
    return value, label


def _change_direction(value):
    if value is None:
        return "unavailable"
    if value > 0:
        return "increasing"
    if value < 0:
        return "decreasing"
    return "stable"


def _percentile_rank(values, value):
    if value is None or not values:
        return None
    return sum(item <= value for item in values) / len(values)


def _low_gap(mapped, start, end):
    between = [
        float(row.total)
        for row, strike in mapped
        if row.total is not None and min(start, end) < strike < max(start, end)
    ]
    all_values = [float(row.total) for row, _ in mapped if row.total is not None]
    if not between or not all_values:
        return None
    threshold = sorted(all_values)[max(int(len(all_values) * 0.25) - 1, 0)]
    return mean(between) <= threshold


def _duration(outcome):
    if not outcome.get("exited_at") or not outcome.get("triggered_at"):
        return None
    return (
        datetime.fromisoformat(outcome["exited_at"])
        - datetime.fromisoformat(outcome["triggered_at"])
    ).total_seconds() / 60


def _average(values):
    present = [float(value) for value in values if value is not None]
    return mean(present) if present else None


def _median(values):
    present = [float(value) for value in values if value is not None]
    return median(present) if present else None


def _sum_present(values):
    present = [float(value) for value in values if value is not None]
    return sum(present) if present else None


def _float(value):
    return float(value) if value not in (None, "") else None


def _unavailable_confirmation_variant(name):
    return {
        "variant": name,
        "status": "requires_confirmation_replay",
        "reason": "Price bars and the timestamp-safe daily index were not supplied.",
        "unique_opportunity_count": 0,
        "research_only": True,
        "signal_allowed": False,
    }


def _five_minute_candles(feature, bars, *, end_at=None):
    touch = datetime.fromisoformat(feature["first_touch_time"])
    end = end_at or touch.replace(hour=23, minute=59, second=59)
    selected = [bar for bar in bars if touch <= bar.timestamp <= end]
    grouped = defaultdict(list)
    for bar in selected:
        local = bar.timestamp.astimezone(touch.tzinfo)
        key = local.replace(minute=(local.minute // 5) * 5, second=0, microsecond=0)
        grouped[key].append(bar)
    candles = []
    for key, items in sorted(grouped.items()):
        items.sort(key=lambda row: row.timestamp)
        candles.append(
            {
                "start": key,
                "end": items[-1].timestamp,
                "open": items[0].open,
                "high": max(item.high for item in items),
                "low": min(item.low for item in items),
                "close": items[-1].close,
            }
        )
    return candles


def _rejection_confirmation(feature, bars):
    entry = float(feature["entry_level"])
    side = feature["side"]
    for candle in _five_minute_candles(feature, bars):
        touched = candle["low"] <= entry if side == "long_reversion" else candle["high"] >= entry
        inside = candle["close"] > entry if side == "long_reversion" else candle["close"] < entry
        if not touched or not inside:
            continue
        confirmation_date = candle["end"].astimezone(
            datetime.fromisoformat(feature["first_touch_time"]).tzinfo
        ).date()
        next_bar = next(
            (
                bar
                for bar in bars
                if bar.timestamp > candle["end"]
                and bar.timestamp.astimezone(
                    datetime.fromisoformat(feature["first_touch_time"]).tzinfo
                ).date()
                == confirmation_date
            ),
            None,
        )
        if next_bar is None:
            return None
        return {
            "confirmation_at": candle["end"],
            "entry_at": next_bar.timestamp,
            "entry_price": next_bar.open,
        }
    return None


def _accepted_beyond_wall(feature, bars, wall):
    side = feature["side"]
    return any(
        candle["close"] < wall if side == "long_reversion" else candle["close"] > wall
        for candle in _five_minute_candles(feature, bars)
    )


def _accepted_before_confirmation(feature, bars, wall, confirmation_at):
    side = feature["side"]
    return any(
        candle["close"] < wall if side == "long_reversion" else candle["close"] > wall
        for candle in _five_minute_candles(feature, bars, end_at=confirmation_at)
    )


def _simulate_confirmed(
    feature,
    bars,
    confirmation,
    *,
    strategy_id,
    target_sd,
    stop_sd,
):
    entry = float(confirmation["entry_price"])
    side = feature["side"]
    one_sd = float(feature["one_sd_points"])
    target = entry + target_sd * one_sd if side == "long_reversion" else entry - target_sd * one_sd
    suffix = "2sd" if stop_sd == 2.0 else "2_5sd"
    stop = float(feature[f"{'lower' if side == 'long_reversion' else 'upper'}_{suffix}"])
    end = confirmation["entry_at"].replace(hour=23, minute=59, second=59)
    window = [bar for bar in bars if confirmation["entry_at"] <= bar.timestamp <= end]
    status = "unavailable"
    exit_price = None
    exited_at = None
    mfe = None
    mae = None
    for bar in window:
        favorable = bar.high - entry if side == "long_reversion" else entry - bar.low
        adverse = bar.low - entry if side == "long_reversion" else entry - bar.high
        mfe = favorable if mfe is None else max(mfe, favorable)
        mae = adverse if mae is None else min(mae, adverse)
        target_hit = bar.high >= target if side == "long_reversion" else bar.low <= target
        stop_hit = bar.low <= stop if side == "long_reversion" else bar.high >= stop
        if stop_hit or target_hit:
            status = "stop_hit" if stop_hit else "target_hit"
            exit_price = stop if stop_hit else target
            exited_at = bar.timestamp
            break
    if status == "unavailable" and window:
        exit_price = window[-1].close
        exited_at = window[-1].timestamp
        gross_at_end = _gross(entry, exit_price, side)
        status = "time_exit_profit" if gross_at_end >= 0 else "time_exit_loss"
    gross = _gross(entry, exit_price, side) if exit_price is not None else None
    return {
        "opportunity_id": feature["opportunity_id"],
        "session_date": feature["session_date"],
        "planning_mode": feature["planning_mode"],
        "strategy_id": strategy_id,
        "side": side,
        "confirmation_timestamp": confirmation["confirmation_at"].isoformat(),
        "triggered_at": confirmation["entry_at"].isoformat(),
        "entry_price": entry,
        "exited_at": exited_at.isoformat() if exited_at else None,
        "status": status,
        "gross_points": gross,
        "cost_points": 1.0,
        "net_points": gross - 1.0 if gross is not None else None,
        "mfe_points": mfe,
        "mae_points": mae,
        "research_only": True,
        "signal_allowed": False,
    }


def _gross(entry, exit_price, side):
    return exit_price - entry if side == "long_reversion" else entry - exit_price
