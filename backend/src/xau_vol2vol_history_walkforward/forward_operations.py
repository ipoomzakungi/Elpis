from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from src.models.xau_market_context import XauPriceBar
from src.models.xau_vol2vol_history_walkforward import (
    XauVol2VolRangeDeskSnapshot,
    XauVol2VolStrikeSnapshot,
)

FORWARD_ENGINE_ERRATUM = "031N-forward-session-lifecycle-audit"
FORWARD_ENGINE_REVISION = hashlib.sha256(
    json.dumps(
        {
            "erratum": FORWARD_ENGINE_ERRATUM,
            "same_entry_bar_exit": "ambiguous_without_intrabar_sequence",
            "f0_entry_rule": "touch_entry",
            "f2_entry_rule": "confirmed_next_bar",
            "price_age_reference": "basis_source_bar",
            "incomplete_session_policy": "current_true_forward_prepare_only",
            "monitor_finalize_plan_source": "frozen_successful_prepare_journal",
        },
        sort_keys=True,
    ).encode("utf-8")
).hexdigest()


class ForwardOperationalState(StrEnum):
    PLAN_READY = "PLAN_READY"
    DATA_BLOCKED = "DATA_BLOCKED"
    STALE_SOURCE = "STALE_SOURCE"
    NO_VALID_SERIES = "NO_VALID_SERIES"
    NO_PRE_0700_SNAPSHOT = "NO_PRE_07:00_SNAPSHOT"
    SESSION_INCOMPLETE = "SESSION_INCOMPLETE"


@dataclass(frozen=True)
class ForwardReadinessResult:
    state: ForwardOperationalState
    reasons: list[str]
    plan: dict[str, Any] | None = None


def evaluate_forward_readiness(
    *,
    session_date: date,
    planning_at: datetime,
    range_rows: list[XauVol2VolRangeDeskSnapshot],
    strike_rows: list[XauVol2VolStrikeSnapshot],
    bars: list[XauPriceBar],
    planning_mode: str,
    source_gap_limit_seconds: int = 300,
    snapshot_freshness_limit_seconds: int = 1800,
) -> ForwardReadinessResult:
    session_ranges = [row for row in range_rows if row.session_date == session_date]
    if not session_ranges:
        return ForwardReadinessResult(
            ForwardOperationalState.DATA_BLOCKED,
            ["Vol2Vol session payload is unavailable."],
        )
    eligible_bars = [bar for bar in bars if bar.timestamp <= planning_at]
    if not eligible_bars:
        return ForwardReadinessResult(
            ForwardOperationalState.DATA_BLOCKED,
            ["No XAUUSD bar exists at or before the planning checkpoint."],
        )
    past = [row for row in session_ranges if row.observed_at <= planning_at]
    if not past:
        return ForwardReadinessResult(
            ForwardOperationalState.NO_PRE_0700_SNAPSHOT,
            ["No Vol2Vol snapshot was observed before the planning checkpoint."],
        )
    complete = [row for row in past if _complete_sd(row) and row.dte is not None]
    if not complete:
        return ForwardReadinessResult(
            ForwardOperationalState.NO_VALID_SERIES,
            ["No pre-checkpoint series has a complete numeric SD ladder and DTE."],
        )
    latest_by_series = {}
    for row in complete:
        if (
            row.series not in latest_by_series
            or row.observed_at > latest_by_series[row.series].observed_at
        ):
            latest_by_series[row.series] = row
    monitoring_days = max(
        (
            planning_at.replace(hour=23, minute=59, second=59) - planning_at
        ).total_seconds()
        / 86_400,
        0,
    )
    covering = [row for row in latest_by_series.values() if float(row.dte) >= monitoring_days]
    if not covering:
        return ForwardReadinessResult(
            ForwardOperationalState.NO_VALID_SERIES,
            ["No deterministic series covers the remaining monitoring horizon."],
        )
    selected = min(covering, key=lambda row: (float(row.dte), row.series or ""))
    selected_snapshot_sha256 = hashlib.sha256(
        json.dumps(selected.model_dump(mode="json"), sort_keys=True).encode("utf-8")
    ).hexdigest()
    snapshot_age = (planning_at - selected.observed_at).total_seconds()
    source_bars = [bar for bar in bars if bar.timestamp <= selected.observed_at]
    if not source_bars:
        return ForwardReadinessResult(
            ForwardOperationalState.STALE_SOURCE,
            ["No synchronized XAUUSD bar exists at or before the Vol2Vol snapshot."],
        )
    source_bar = max(source_bars, key=lambda bar: bar.timestamp)
    source_gap = abs((selected.observed_at - source_bar.timestamp).total_seconds())
    xau_price_age = (planning_at - source_bar.timestamp).total_seconds()
    stale = []
    if snapshot_age > snapshot_freshness_limit_seconds:
        stale.append("Vol2Vol snapshot exceeds the protocol freshness limit.")
    if xau_price_age > source_gap_limit_seconds:
        stale.append("Planning XAUUSD price exceeds the freshness limit.")
    if source_gap > source_gap_limit_seconds:
        stale.append("Vol2Vol and XAUUSD source timestamps exceed alignment tolerance.")
    if stale:
        return ForwardReadinessResult(ForwardOperationalState.STALE_SOURCE, stale)
    diff = float(selected.future_open) - source_bar.close
    levels = _mapped_levels(selected, diff)
    selected_strikes = [
        row
        for row in strike_rows
        if row.session_date == session_date
        and row.series == selected.series
        and row.observed_at <= planning_at
    ]
    oi_snapshot = _latest_kind(selected_strikes, "open_interest")
    volume_snapshot = _latest_kind(selected_strikes, "intraday_volume")
    top_oi_walls = _top_mapped_walls(oi_snapshot, diff)
    return ForwardReadinessResult(
        ForwardOperationalState.PLAN_READY,
        [],
        {
            "session_date": session_date.isoformat(),
            "planning_mode": planning_mode,
            "planning_at": planning_at.isoformat(),
            "selected_series": selected.series,
            "dte": selected.dte,
            "future_reference": selected.future_open,
            "xau_reference": source_bar.close,
            "basis_points": diff,
            "mapping_mode": "same_time_basis",
            "vol2vol_snapshot_time": selected.observed_at.isoformat(),
            "selected_snapshot_sha256": selected_snapshot_sha256,
            "xau_source_time": source_bar.timestamp.isoformat(),
            "source_alignment_seconds": source_gap,
            "xau_price_age_at_planning_seconds": xau_price_age,
            "vol2vol_snapshot_age_at_planning_seconds": snapshot_age,
            "levels": levels,
            "plan_oi_snapshot_time": (
                oi_snapshot[0].observed_at.isoformat() if oi_snapshot else None
            ),
            "plan_volume_snapshot_time": (
                volume_snapshot[0].observed_at.isoformat() if volume_snapshot else None
            ),
            "top_oi_walls": top_oi_walls,
            "f0_status": "active_research_baseline",
            "f1_status": "context_label_only",
            "f2_status": "observe_not_required",
            "f3_status": "exploratory_only",
            "br_status": "monitor_only",
            "research_only": True,
            "signal_allowed": False,
        },
    )


def observe_forward_plan(
    plan: dict[str, Any],
    bars: list[XauPriceBar],
    *,
    finalize: bool,
) -> dict[str, list[dict[str, Any]]]:
    planning_at = datetime.fromisoformat(plan["planning_at"])
    local_date = planning_at.date()
    window = [
        bar
        for bar in bars
        if planning_at < bar.timestamp
        and bar.timestamp.astimezone(planning_at.tzinfo).date() == local_date
    ]
    opportunities = []
    confirmations = []
    outcomes = []
    levels = plan["levels"]
    center = float(plan["xau_reference"])
    one_sd = {
        "long_reversion": center - float(levels["lower_1sd"]),
        "short_reversion": float(levels["upper_1sd"]) - center,
    }
    for entry_definition, suffix in (
        ("zone_2_entry", "1sd"),
        ("zone_2_mid", "1_5sd"),
    ):
        for side in ("long_reversion", "short_reversion"):
            prefix = "lower" if side == "long_reversion" else "upper"
            entry = float(levels[f"{prefix}_{suffix}"])
            touch = _first_touch(window, side, entry)
            if touch is None:
                continue
            opportunity_id = (
                f"{plan['session_date']}:{plan['planning_mode']}:"
                f"{plan['planning_at']}:{side}:{entry_definition}"
            )
            nearest_wall = min(
                plan.get("top_oi_walls", []),
                key=lambda wall: abs(float(wall["mapped_strike"]) - entry),
                default=None,
            )
            f1_eligible = bool(
                nearest_wall
                and abs(float(nearest_wall["mapped_strike"]) - entry)
                / one_sd[side]
                <= 0.25
            )
            opportunities.append(
                {
                    "opportunity_id": opportunity_id,
                    "first_touch_time": touch.timestamp.isoformat(),
                    "side": side,
                    "entry_definition": entry_definition,
                    "entry_level": entry,
                    "f1_eligible": f1_eligible,
                    "nearest_top5_oi_wall": nearest_wall,
                }
            )
            confirmation = _confirmation(window, touch.timestamp, side, entry)
            if confirmation:
                confirmations.append(
                    {
                        "opportunity_id": opportunity_id,
                        **confirmation,
                        "execution_variant": "F2",
                        "entry_rule": "confirmed_next_bar",
                        "actual_entry_timestamp": confirmation[
                            "next_executable_entry_timestamp"
                        ],
                        "actual_entry_price": confirmation[
                            "next_executable_entry_price"
                        ],
                        "outcome_generated": False,
                        "f2_observed": True,
                        "f2_required_for_f0": False,
                    }
                )
            if finalize:
                outcomes.extend(
                    _final_outcomes(
                        opportunity_id,
                        side,
                        entry_definition,
                        entry,
                        one_sd[side],
                        levels,
                        touch.timestamp,
                        window,
                    )
                )
    return {
        "opportunities": opportunities,
        "confirmations": confirmations,
        "outcomes": outcomes,
    }


def _complete_sd(row):
    return row.future_open is not None and all(
        value is not None
        for value in (
            row.future_buy_1sd,
            row.future_buy_2sd,
            row.future_buy_3sd,
            row.future_sell_1sd,
            row.future_sell_2sd,
            row.future_sell_3sd,
        )
    )


def _mapped_levels(row, diff):
    lower_1 = float(row.future_buy_1sd) - diff
    lower_2 = float(row.future_buy_2sd) - diff
    lower_3 = float(row.future_buy_3sd) - diff
    upper_1 = float(row.future_sell_1sd) - diff
    upper_2 = float(row.future_sell_2sd) - diff
    upper_3 = float(row.future_sell_3sd) - diff
    return {
        "lower_1sd": lower_1,
        "lower_1_5sd": (lower_1 + lower_2) / 2,
        "lower_2sd": lower_2,
        "lower_2_5sd": (lower_2 + lower_3) / 2,
        "lower_3sd": lower_3,
        "upper_1sd": upper_1,
        "upper_1_5sd": (upper_1 + upper_2) / 2,
        "upper_2sd": upper_2,
        "upper_2_5sd": (upper_2 + upper_3) / 2,
        "upper_3sd": upper_3,
    }


def _latest_kind(rows, kind):
    matching = [row for row in rows if row.snapshot_kind == kind]
    if not matching:
        return []
    latest = max(row.observed_at for row in matching)
    return [row for row in matching if row.observed_at == latest]


def _top_mapped_walls(rows, diff):
    active = [row for row in rows if row.total is not None and row.total > 0]
    if len(active) < 5:
        return []
    return [
        {
            "futures_strike": row.strike,
            "mapped_strike": row.strike - diff,
            "total_oi": row.total,
            "rank": index,
        }
        for index, row in enumerate(
            sorted(active, key=lambda item: float(item.total), reverse=True)[:5],
            start=1,
        )
    ]


def _first_touch(bars, side, entry):
    if side == "long_reversion":
        return next((bar for bar in bars if bar.low <= entry), None)
    return next((bar for bar in bars if bar.high >= entry), None)


def _confirmation(bars, touched_at, side, entry):
    grouped = {}
    for bar in bars:
        if bar.timestamp < touched_at:
            continue
        local = bar.timestamp.astimezone(touched_at.tzinfo)
        key = local.replace(minute=(local.minute // 5) * 5, second=0, microsecond=0)
        grouped.setdefault(key, []).append(bar)
    for items in grouped.values():
        items.sort(key=lambda bar: bar.timestamp)
        high = max(bar.high for bar in items)
        low = min(bar.low for bar in items)
        close = items[-1].close
        touched = low <= entry if side == "long_reversion" else high >= entry
        rejected = close > entry if side == "long_reversion" else close < entry
        if touched and rejected:
            next_bar = next((bar for bar in bars if bar.timestamp > items[-1].timestamp), None)
            if next_bar:
                return {
                    "confirmation_timestamp": items[-1].timestamp.isoformat(),
                    "next_executable_entry_timestamp": next_bar.timestamp.isoformat(),
                    "next_executable_entry_price": next_bar.open,
                }
    return None


def _final_outcomes(
    opportunity_id,
    side,
    entry_definition,
    entry,
    one_sd,
    levels,
    touched_at,
    bars,
):
    strategies = (
        (("A", 0.25, "2sd"), ("B", 0.5, "2sd"))
        if entry_definition == "zone_2_entry"
        else (("C", 0.25, "2_5sd"), ("D", 0.5, "2_5sd"))
    )
    outcomes = []
    entry_bar = next((bar for bar in bars if bar.timestamp == touched_at), None)
    if entry_bar is None:
        return outcomes
    for strategy, target_sd, stop_suffix in strategies:
        target = (
            entry + target_sd * one_sd
            if side == "long_reversion"
            else entry - target_sd * one_sd
        )
        stop = float(levels[f"{'lower' if side == 'long_reversion' else 'upper'}_{stop_suffix}"])
        status = "unavailable"
        exit_price = None
        exited_at = None
        mfe = None
        mae = None
        target_touched_same_bar = False
        stop_touched_same_bar = False
        ambiguity_reason = None
        for bar in bars:
            if bar.timestamp < touched_at:
                continue
            favorable = bar.high - entry if side == "long_reversion" else entry - bar.low
            adverse = bar.low - entry if side == "long_reversion" else entry - bar.high
            mfe = favorable if mfe is None else max(mfe, favorable)
            mae = adverse if mae is None else min(mae, adverse)
            target_hit = bar.high >= target if side == "long_reversion" else bar.low <= target
            stop_hit = bar.low <= stop if side == "long_reversion" else bar.high >= stop
            if bar.timestamp == touched_at and (target_hit or stop_hit):
                target_touched_same_bar = target_hit
                stop_touched_same_bar = stop_hit
                status = "same_bar_ambiguous"
                ambiguity_reason = _same_bar_ambiguity_reason(target_hit, stop_hit)
                break
            if stop_hit or target_hit:
                status = "stop_hit" if stop_hit else "target_hit"
                exit_price = stop if stop_hit else target
                exited_at = bar.timestamp
                break
        if status == "unavailable" and bars:
            exit_price = bars[-1].close
            exited_at = bars[-1].timestamp
            gross = exit_price - entry if side == "long_reversion" else entry - exit_price
            status = "time_exit_profit" if gross >= 0 else "time_exit_loss"
        gross = (
            exit_price - entry
            if side == "long_reversion" and exit_price is not None
            else entry - exit_price
            if exit_price is not None
            else None
        )
        outcomes.append(
            {
                "record_key": f"{opportunity_id}:{strategy}",
                "opportunity_id": opportunity_id,
                "strategy_id": strategy,
                "side": side,
                "status": status,
                "execution_variant": "F0",
                "entry_rule": "touch_entry",
                "entry_price": entry,
                "actual_entry_price": entry,
                "actual_entry_timestamp": touched_at.isoformat(),
                "entry_bar_timestamp": entry_bar.timestamp.isoformat(),
                "entry_bar_open": entry_bar.open,
                "entry_bar_high": entry_bar.high,
                "entry_bar_low": entry_bar.low,
                "entry_bar_close": entry_bar.close,
                "target_touched_same_bar": target_touched_same_bar,
                "stop_touched_same_bar": stop_touched_same_bar,
                "intrabar_sequence_available": False,
                "ambiguity_reason": ambiguity_reason,
                "exit_price": exit_price,
                "exited_at": exited_at.isoformat() if exited_at else None,
                "gross_points": gross,
                "cost_points": 1.0,
                "net_points": gross - 1.0 if gross is not None else None,
                "mfe_points": mfe,
                "mae_points": mae,
            }
        )
    return outcomes


def _same_bar_ambiguity_reason(target_hit: bool, stop_hit: bool) -> str:
    if target_hit and stop_hit:
        return "entry_target_and_stop_touched_in_same_m1_bar_without_sequence"
    if target_hit:
        return "entry_and_target_touched_in_same_m1_bar_without_sequence"
    return "entry_and_stop_touched_in_same_m1_bar_without_sequence"
