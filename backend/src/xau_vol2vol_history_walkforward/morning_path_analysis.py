from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any

from src.models.xau_market_context import XauPriceBar
from src.models.xau_vol2vol_history_walkforward import (
    XauDailySdPathRecord,
    XauMarketOpportunity,
    XauSdEntryLevel,
    XauSdMeanReversionPlan,
    XauTradeSide,
    XauWalkforwardTradeOutcome,
    XauWalkforwardTradeStatus,
)
from src.xau_vol2vol_history_walkforward.planning import (
    XauPlanningSelection,
    planning_plan_metadata,
)

FILLED_STATUSES = {
    XauWalkforwardTradeStatus.TARGET_HIT,
    XauWalkforwardTradeStatus.STOP_HIT,
    XauWalkforwardTradeStatus.TIME_EXIT_PROFIT,
    XauWalkforwardTradeStatus.TIME_EXIT_LOSS,
    XauWalkforwardTradeStatus.EXPIRED,
    XauWalkforwardTradeStatus.AMBIGUOUS,
}
TIME_EXIT_STATUSES = {
    XauWalkforwardTradeStatus.TIME_EXIT_PROFIT,
    XauWalkforwardTradeStatus.TIME_EXIT_LOSS,
    XauWalkforwardTradeStatus.EXPIRED,
}


def build_daily_sd_paths(
    selections: list[XauPlanningSelection],
    bars: list[XauPriceBar],
) -> list[XauDailySdPathRecord]:
    records: list[XauDailySdPathRecord] = []
    for selection in selections:
        metadata = planning_plan_metadata(selection)
        required = (
            metadata["traded_reference_price"],
            metadata["future_reference_price"],
            metadata["basis_points"],
            metadata["mapped_lower_1sd"],
            metadata["mapped_lower_2sd"],
            metadata["mapped_lower_3sd"],
            metadata["mapped_upper_1sd"],
            metadata["mapped_upper_2sd"],
            metadata["mapped_upper_3sd"],
            selection.selected_xau_price_time,
            selection.basis_alignment_seconds,
        )
        if any(value is None for value in required):
            continue
        window = [
            bar
            for bar in bars
            if selection.simulation_window_start
            <= bar.timestamp.astimezone(selection.planning_at.tzinfo)
            <= selection.simulation_window_end
        ]
        if not window:
            continue
        lower_1 = float(metadata["mapped_lower_1sd"])
        lower_2 = float(metadata["mapped_lower_2sd"])
        lower_3 = float(metadata["mapped_lower_3sd"])
        upper_1 = float(metadata["mapped_upper_1sd"])
        upper_2 = float(metadata["mapped_upper_2sd"])
        upper_3 = float(metadata["mapped_upper_3sd"])
        center = float(metadata["traded_reference_price"])
        lower_1_5 = (lower_1 + lower_2) / 2
        lower_2_5 = (lower_2 + lower_3) / 2
        upper_1_5 = (upper_1 + upper_2) / 2
        upper_2_5 = (upper_2 + upper_3) / 2
        records.append(
            XauDailySdPathRecord(
                morning_plan_id=(
                    f"xau_morning_{selection.session_date:%Y%m%d}_"
                    f"{selection.planning_at:%H%M}"
                ),
                session_date=selection.session_date,
                cycle_label=selection.cycle_label,
                planning_at=selection.planning_at,
                simulation_window_start=selection.simulation_window_start,
                simulation_window_end=selection.simulation_window_end,
                selected_snapshot_time=selection.range_snapshot.observed_at,
                selected_xau_price_time=selection.selected_xau_price_time,
                selected_series=metadata["selected_series"],
                dte=metadata["selected_dte"],
                future_reference_price=float(metadata["future_reference_price"]),
                traded_reference_price=center,
                basis_points=float(metadata["basis_points"]),
                basis_alignment_seconds=float(selection.basis_alignment_seconds),
                expected_move=metadata["expected_move"],
                lower_1sd=lower_1,
                lower_1_5sd=lower_1_5,
                lower_2sd=lower_2,
                lower_2_5sd=lower_2_5,
                lower_3sd=lower_3,
                upper_1sd=upper_1,
                upper_1_5sd=upper_1_5,
                upper_2sd=upper_2,
                upper_2_5sd=upper_2_5,
                upper_3sd=upper_3,
                reached_lower_1sd=_reached_lower(window, lower_1),
                reached_lower_1_5sd=_reached_lower(window, lower_1_5),
                reached_lower_2sd=_reached_lower(window, lower_2),
                reached_lower_2_5sd=_reached_lower(window, lower_2_5),
                reached_lower_3sd=_reached_lower(window, lower_3),
                reached_upper_1sd=_reached_upper(window, upper_1),
                reached_upper_1_5sd=_reached_upper(window, upper_1_5),
                reached_upper_2sd=_reached_upper(window, upper_2),
                reached_upper_2_5sd=_reached_upper(window, upper_2_5),
                reached_upper_3sd=_reached_upper(window, upper_3),
                first_lower_2sd_touch_time=_first_lower_touch(window, lower_2),
                first_upper_2sd_touch_time=_first_upper_touch(window, upper_2),
                first_lower_3sd_touch_time=_first_lower_touch(window, lower_3),
                first_upper_3sd_touch_time=_first_upper_touch(window, upper_3),
                maximum_positive_sd=max(
                    (bar.high - center) / (upper_1 - center) for bar in window
                ),
                maximum_negative_sd=min(
                    (bar.low - center) / (center - lower_1) for bar in window
                ),
            )
        )
    return records


def build_opportunity_map(
    paths: list[XauDailySdPathRecord],
    plans: list[XauSdMeanReversionPlan],
    outcomes: list[XauWalkforwardTradeOutcome],
) -> tuple[list[XauMarketOpportunity], dict[str, Any]]:
    plans_by_key: dict[tuple[date, str, XauTradeSide, XauSdEntryLevel], list] = defaultdict(
        list
    )
    for plan in plans:
        plans_by_key[(plan.session_date, plan.cycle_label, plan.side, plan.entry_sd)].append(plan)
    minimum_cost = min((item.cost_points for item in outcomes), default=0.0)
    base_by_plan = {
        item.plan_id: item for item in outcomes if item.cost_points == minimum_cost
    }
    all_by_plan: dict[str, list[XauWalkforwardTradeOutcome]] = defaultdict(list)
    for outcome in outcomes:
        all_by_plan[outcome.plan_id].append(outcome)

    opportunities: list[XauMarketOpportunity] = []
    for path in paths:
        touches = (
            (
                XauTradeSide.LONG_REVERSION,
                XauSdEntryLevel.TWO_SD,
                path.lower_2sd,
                path.first_lower_2sd_touch_time,
            ),
            (
                XauTradeSide.SHORT_REVERSION,
                XauSdEntryLevel.TWO_SD,
                path.upper_2sd,
                path.first_upper_2sd_touch_time,
            ),
            (
                XauTradeSide.LONG_REVERSION,
                XauSdEntryLevel.THREE_SD,
                path.lower_3sd,
                path.first_lower_3sd_touch_time,
            ),
            (
                XauTradeSide.SHORT_REVERSION,
                XauSdEntryLevel.THREE_SD,
                path.upper_3sd,
                path.first_upper_3sd_touch_time,
            ),
        )
        for side, entry_sd, entry_level, touched_at in touches:
            if touched_at is None:
                continue
            matched_plans = plans_by_key[(path.session_date, path.cycle_label, side, entry_sd)]
            plan_ids = sorted({plan.plan_id for plan in matched_plans})
            base_fills = [
                base_by_plan[plan_id]
                for plan_id in plan_ids
                if plan_id in base_by_plan and base_by_plan[plan_id].status in FILLED_STATUSES
            ]
            cost_fills = [
                item
                for plan_id in plan_ids
                for item in all_by_plan[plan_id]
                if item.status in FILLED_STATUSES
            ]
            opportunities.append(
                XauMarketOpportunity(
                    opportunity_id=(
                        f"{path.session_date.isoformat()}:{path.cycle_label}:"
                        f"{side.value}:{entry_sd.value}:{entry_level:.4f}"
                    ),
                    morning_plan_id=path.morning_plan_id,
                    session_date=path.session_date,
                    cycle_label=path.cycle_label,
                    side=side,
                    entry_sd=entry_sd,
                    entry_level=entry_level,
                    first_touch_time=touched_at,
                    configuration_plan_ids=plan_ids,
                    configuration_fill_count=len(base_fills),
                    cost_scenario_filled_row_count=len(cost_fills),
                    target_configuration_count=sum(
                        item.status == XauWalkforwardTradeStatus.TARGET_HIT
                        for item in base_fills
                    ),
                    stop_configuration_count=sum(
                        item.status == XauWalkforwardTradeStatus.STOP_HIT
                        for item in base_fills
                    ),
                    time_exit_configuration_count=sum(
                        item.status in TIME_EXIT_STATUSES for item in base_fills
                    ),
                )
            )
    return opportunities, summarize_opportunities(paths, opportunities)


def summarize_opportunities(
    paths: list[XauDailySdPathRecord],
    opportunities: list[XauMarketOpportunity],
) -> dict[str, Any]:
    dates = sorted({path.session_date for path in paths})
    split_index = min(max(int(len(dates) * 0.7), 1), max(len(dates) - 1, 1))
    holdout_dates = set(dates[split_index:]) if len(dates) > 1 else set()
    filled = [item for item in opportunities if item.configuration_fill_count > 0]
    holdout_filled = [item for item in filled if item.session_date in holdout_dates]
    filled_sessions = {item.session_date for item in filled}
    evidence_status = (
        "provisional"
        if len(filled) >= 30 and len(holdout_filled) >= 10 and len(filled_sessions) >= 5
        else "insufficient_sample"
    )
    return {
        "testable_morning_sessions": len(paths),
        "sessions_reaching_either_2sd": sum(
            path.reached_lower_2sd or path.reached_upper_2sd for path in paths
        ),
        "sessions_reaching_either_3sd": sum(
            path.reached_lower_3sd or path.reached_upper_3sd for path in paths
        ),
        "unique_market_opportunity_count": len(opportunities),
        "unique_2sd_opportunity_count": sum(
            item.entry_sd == XauSdEntryLevel.TWO_SD for item in opportunities
        ),
        "unique_3sd_opportunity_count": sum(
            item.entry_sd == XauSdEntryLevel.THREE_SD for item in opportunities
        ),
        "filled_opportunity_count": len(filled),
        "configuration_fill_count": sum(
            item.configuration_fill_count for item in opportunities
        ),
        "cost_scenario_filled_row_count": sum(
            item.cost_scenario_filled_row_count for item in opportunities
        ),
        "unique_filled_sessions": len(filled_sessions),
        "unique_filled_cycles": len({item.cycle_label for item in filled}),
        "holdout_filled_opportunity_count": len(holdout_filled),
        "opportunity_target_count": sum(
            item.target_configuration_count > 0 for item in filled
        ),
        "opportunity_stop_count": sum(item.stop_configuration_count > 0 for item in filled),
        "opportunity_time_exit_count": sum(
            item.time_exit_configuration_count > 0 for item in filled
        ),
        "evidence_status": evidence_status,
        "research_only": True,
        "signal_allowed": False,
    }


def _reached_lower(bars: list[XauPriceBar], level: float) -> bool:
    return any(bar.low <= level for bar in bars)


def _reached_upper(bars: list[XauPriceBar], level: float) -> bool:
    return any(bar.high >= level for bar in bars)


def _first_lower_touch(bars: list[XauPriceBar], level: float) -> datetime | None:
    return next((bar.timestamp for bar in bars if bar.low <= level), None)


def _first_upper_touch(bars: list[XauPriceBar], level: float) -> datetime | None:
    return next((bar.timestamp for bar in bars if bar.high >= level), None)
