from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from src.models.xau_tiered_manual_signal import XauBrokerQuote
from src.xau_first_touch_study.models import (
    CountingMode,
    EventOutcome,
    EventSide,
    FirstTouchEvent,
    MappingMode,
    TimeAnchor,
    as_record,
)
from src.xau_first_touch_study.selection import (
    load_source_snapshots,
    map_selection,
    select_snapshot,
)
from src.xau_first_touch_study.statistics import (
    chronological_split,
    grouped_summaries,
    summarize_outcomes,
)
from src.xau_tiered_manual_signal.policy import load_policy
from src.xau_tiered_manual_signal.service import XauTieredManualSignalService
from src.xau_tiered_manual_signal.tiers import (
    build_tier_events,
    evaluate_tier_barrier,
    executable_rejection_entry,
    qualifying_lower_oi_zone,
)
from src.xau_vol2vol_history_walkforward.data_lake import (
    daily_raw_path,
    evaluate_daily_session_eligibility,
)
from src.xau_vol2vol_history_walkforward.walkforward_simulator import (
    load_traded_bars_folder,
)


@dataclass(frozen=True)
class TieredStudyConfig:
    vol2vol_root: Path
    price_bars_folder: Path
    policy_path: Path
    output_root: Path
    journal_root: Path
    session_date_from: date
    session_date_to: date
    as_of_date: date
    timezone: str = "Asia/Bangkok"
    broker_quote: XauBrokerQuote | None = None


def run_tiered_study(config: TieredStudyConfig) -> Path:
    policy = load_policy(config.policy_path)
    run_id = f"xau_tiered_first_touch_{datetime.now().strftime('%Y%m%dT%H%M%S%f')}"
    run_dir = config.output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    price_result = load_traded_bars_folder(
        config.price_bars_folder,
        timezone=config.timezone,
    )
    bars_by_date = _bars_by_date(price_result.bars, config.timezone)
    eligibility_rows: list[dict[str, Any]] = []
    strict_selections = []
    plans = []
    aggregated_events: list[FirstTouchEvent] = []
    side_events: list[FirstTouchEvent] = []
    source_paths: list[Path] = []

    current = config.session_date_from
    while current <= config.session_date_to:
        eligibility = evaluate_daily_session_eligibility(
            root=config.vol2vol_root,
            session_date=current,
            current_date=config.as_of_date,
        )
        row = {
            "session_date": current.isoformat(),
            "source_session_status": eligibility.source_session_status,
            "backtest_eligible": eligibility.backtest_eligible,
            "reasons": eligibility.reasons,
            "payload_sha256": eligibility.payload_sha256,
            "plan_created": False,
        }
        eligibility_rows.append(row)
        if not eligibility.backtest_eligible:
            current += timedelta(days=1)
            continue

        raw_path = daily_raw_path(config.vol2vol_root, current)
        source_paths.append(raw_path)
        selection = select_snapshot(
            load_source_snapshots(raw_path, current),
            anchor=TimeAnchor.T0_DTE_080,
            session_date=current,
            timezone=config.timezone,
            target_dte=policy["canonical_plan"]["target_source_dte"],
            dte_tolerance=(
                policy["canonical_plan"]["maximum_source_dte"]
                - policy["canonical_plan"]["target_source_dte"]
            ),
        )
        if selection is None or not _valid_selection(selection, policy):
            row["reasons"] = [*row["reasons"], "STRICT_T0_DTE_080_SELECTION_UNAVAILABLE"]
            current += timedelta(days=1)
            continue
        strict_selections.append(selection)
        session_bars = bars_by_date.get(current, [])
        plan = map_selection(
            selection,
            session_bars,
            mapping_mode=MappingMode.DISTANCE_REANCHORED,
        )
        if plan is None:
            row["reasons"] = [*row["reasons"], "DISTANCE_MAPPING_UNAVAILABLE"]
            current += timedelta(days=1)
            continue
        row["plan_created"] = True
        plans.append(plan)
        aggregated_events.extend(
            build_tier_events(plan, session_bars, counting_mode=CountingMode.AGGREGATED)
        )
        side_events.extend(
            build_tier_events(plan, session_bars, counting_mode=CountingMode.SIDE_SPECIFIC)
        )
        current += timedelta(days=1)

    matrix = _historical_matrix(aggregated_events, bars_by_date, policy)
    side_sensitivity = _side_sensitivity(side_events, bars_by_date, policy)
    executable = _executable_confluence(plans, side_events, bars_by_date, policy)
    integrity = _integrity_report(
        plans=plans,
        aggregated_events=aggregated_events,
        side_events=side_events,
        eligibility=eligibility_rows,
        policy=policy,
    )
    promotion = _promotion_report(
        matrix=matrix,
        events=aggregated_events,
        integrity=integrity,
        policy=policy,
    )
    current_plan = XauTieredManualSignalService(
        journal_root=config.journal_root,
        policy_path=config.policy_path,
        vol2vol_root=config.vol2vol_root,
        price_bars_folder=config.price_bars_folder,
        timezone=config.timezone,
    ).process_current(
        session_date=config.as_of_date,
        broker_quote=config.broker_quote,
    )
    plans_vs_events = _plans_vs_events(plans, aggregated_events)
    metadata = {
        "run_id": run_id,
        "policy_hash": policy["policy_hash"],
        "session_date_from": config.session_date_from.isoformat(),
        "session_date_to": config.session_date_to.isoformat(),
        "as_of_date": config.as_of_date.isoformat(),
        "eligible_source_session_count": sum(
            item["backtest_eligible"] for item in eligibility_rows
        ),
        "strict_t0_dte_selection_count": len(strict_selections),
        "planned_session_count": len(plans),
        "strict_selection_mapping_failure_count": len(strict_selections) - len(plans),
        "aggregated_event_count": len(aggregated_events),
        "side_specific_event_count": len(side_events),
        "source_paths": [_file_record(path) for path in source_paths],
        "price_paths": [_file_record(path) for path in price_result.source_paths],
        "research_only": True,
        "signal_allowed": False,
        "order_submission_allowed": False,
    }
    artifacts = {
        "metadata.json": metadata,
        "eligibility.json": eligibility_rows,
        "plans.json": [as_record(item) for item in plans],
        "events.json": [as_record(item) for item in aggregated_events],
        "historical_matrix.json": matrix,
        "side_sensitivity.json": side_sensitivity,
        "executable_confluence.json": executable,
        "plans_vs_events.json": plans_vs_events,
        "integrity_report.json": integrity,
        "promotion_gates.json": promotion,
        "current_plan.json": current_plan.model_dump(mode="json"),
    }
    for name, payload in artifacts.items():
        _write_json(run_dir / name, payload)
    (run_dir / "review_handoff.md").write_text(
        _review_handoff(
            metadata=metadata,
            matrix=matrix,
            executable=executable,
            plans_vs_events=plans_vs_events,
            integrity=integrity,
            promotion=promotion,
            current_plan=current_plan.model_dump(mode="json"),
        ),
        encoding="utf-8",
    )
    return run_dir


def _historical_matrix(
    events: list[FirstTouchEvent],
    bars_by_date: dict[date, list[Any]],
    policy: dict[str, Any],
) -> dict[str, Any]:
    rows = []
    outcomes_by_profile: dict[tuple[float, str, float], list[EventOutcome]] = {}
    for tier in policy["tier_matrix"]:
        barrier_ids = [tier["primary_barrier"], *tier["comparison_barriers"]]
        tier_events = [item for item in events if float(item.tier) == float(tier["tier"])]
        for barrier_id in barrier_ids:
            barrier = policy["barriers"][barrier_id]
            for cost in policy["cost_scenarios_points"]:
                outcomes = [
                    evaluate_tier_barrier(
                        event,
                        bars_by_date.get(event.session_date, []),
                        tp_points=barrier["take_profit_points"],
                        sl_points=barrier["stop_loss_points"],
                        cost_points=cost,
                    )
                    for event in tier_events
                ]
                outcomes_by_profile[(float(tier["tier"]), barrier_id, float(cost))] = outcomes
                summary = _summary(outcomes)
                rows.append(
                    {
                        "tier": float(tier["tier"]),
                        "barrier_id": barrier_id,
                        "is_primary": barrier_id == tier["primary_barrier"],
                        "configured_state": tier["initial_state"],
                        "cost_points": cost,
                        **summary,
                        "development_holdout": chronological_split(outcomes),
                    }
                )
    one_sd = next(
        (
            item
            for item in rows
            if item["tier"] == 1.0
            and item["barrier_id"] == "TP12_5_SL12_5"
            and item["cost_points"] == 1.0
        ),
        None,
    )
    return {
        "counting_mode": CountingMode.AGGREGATED.value,
        "rows": rows,
        "one_sd_tp12_5_sl12_5_verdict": {
            "status": "SHADOW_ONLY",
            "summary_at_1_point_cost": one_sd,
            "reason": (
                "The frozen policy prohibits promotion; current local evidence "
                "must pass predefined event, holdout, side, expectancy, and integrity gates."
            ),
        },
        "research_only": True,
        "signal_allowed": False,
        "order_submission_allowed": False,
    }


def _side_sensitivity(
    events: list[FirstTouchEvent],
    bars_by_date: dict[date, list[Any]],
    policy: dict[str, Any],
) -> dict[str, Any]:
    rows = []
    for tier in policy["tier_matrix"]:
        barrier_id = tier["primary_barrier"]
        barrier = policy["barriers"][barrier_id]
        outcomes = [
            evaluate_tier_barrier(
                event,
                bars_by_date.get(event.session_date, []),
                tp_points=barrier["take_profit_points"],
                sl_points=barrier["stop_loss_points"],
                cost_points=1.0,
            )
            for event in events
            if float(event.tier) == float(tier["tier"])
        ]
        rows.append(
            {
                "tier": float(tier["tier"]),
                "barrier_id": barrier_id,
                "by_side": grouped_summaries(outcomes, lambda item: item.side.value),
            }
        )
    return {
        "counting_mode": CountingMode.SIDE_SPECIFIC.value,
        "rows": rows,
        "warning": (
            "Side-specific rows are sensitivity evidence, "
            "not additional independent trades."
        ),
        "research_only": True,
        "signal_allowed": False,
        "order_submission_allowed": False,
    }


def _executable_confluence(
    plans: list[Any],
    side_events: list[FirstTouchEvent],
    bars_by_date: dict[date, list[Any]],
    policy: dict[str, Any],
) -> dict[str, Any]:
    plan_by_id = {item.plan_id: item for item in plans}
    candidates = [
        item
        for item in side_events
        if float(item.tier) == 2.0 and item.side == EventSide.LOWER_LONG
    ]
    records = []
    grouped: dict[tuple[str, str, float], list[EventOutcome]] = {}
    exclusion_counts: dict[str, int] = {}
    for event in candidates:
        plan = plan_by_id[event.plan_id]
        zone = qualifying_lower_oi_zone(
            plan,
            maximum_distance_points=policy["oi_zone"]["maximum_wall_distance_points"],
            minimum_percentile=policy["oi_zone"]["minimum_oi_percentile"],
        )
        if zone is None:
            _increment(exclusion_counts, "QUALIFYING_OI_ZONE_UNAVAILABLE")
            continue
        if zone.source_snapshot_at > event.touch_timestamp:
            _increment(exclusion_counts, "OI_SNAPSHOT_AFTER_FIRST_TOUCH")
            continue
        for rule in policy["rejection_rules"]:
            entry = executable_rejection_entry(
                zone,
                event,
                bars_by_date.get(event.session_date, []),
                rule=rule,
            )
            if entry is None:
                _increment(exclusion_counts, f"{rule}_NOT_CONFIRMED")
                continue
            executable_event = replace(
                event,
                event_id=f"{event.event_id}_{rule}_next_bar",
                boundary=entry["entry_price"],
                touch_timestamp=entry["entry_timestamp"],
                context={
                    **event.context,
                    "raw_boundary": event.boundary,
                    "mapped_oi_wall": zone.mapped_wall,
                    "oi_percentile": zone.oi_percentile,
                    "confirmation_close": entry["confirmation_close"],
                    "confirmation_timestamp": entry["confirmation_timestamp"].isoformat(),
                    "actual_entry_price": entry["entry_price"],
                },
            )
            record = {
                "session_date": event.session_date.isoformat(),
                "event_id": event.event_id,
                "rule": rule,
                "raw_boundary": event.boundary,
                "mapped_oi_wall": zone.mapped_wall,
                "zone_lower": zone.lower,
                "zone_upper": zone.upper,
                "oi_percentile": zone.oi_percentile,
                "confirmation_timestamp": entry["confirmation_timestamp"].isoformat(),
                "entry_timestamp": entry["entry_timestamp"].isoformat(),
                "actual_entry_price": entry["entry_price"],
                **_secondary_excursions(
                    bars_by_date.get(event.session_date, []),
                    entry_timestamp=entry["entry_timestamp"],
                    entry_price=entry["entry_price"],
                    one_sd_points=event.one_sd_points,
                    fractions=policy["secondary_excursions"],
                ),
            }
            records.append(record)
            for barrier_id in policy["executable_confluence_profiles"]:
                barrier = policy["barriers"][barrier_id]
                for cost in policy["cost_scenarios_points"]:
                    outcome = evaluate_tier_barrier(
                        executable_event,
                        bars_by_date.get(event.session_date, []),
                        tp_points=barrier["take_profit_points"],
                        sl_points=barrier["stop_loss_points"],
                        cost_points=cost,
                        known_entry_at_bar_open=True,
                    )
                    grouped.setdefault((rule, barrier_id, float(cost)), []).append(outcome)
    matrix = [
        {
            "rule": rule,
            "barrier_id": barrier,
            "cost_points": cost,
            **_summary(outcomes),
            "development_holdout": chronological_split(outcomes),
        }
        for (rule, barrier, cost), outcomes in sorted(grouped.items())
    ]
    return {
        "candidate_lower_2sd_first_touch_count": len(candidates),
        "qualified_entry_count": len(records),
        "qualified_independent_session_count": len(
            {item["session_date"] for item in records}
        ),
        "exclusion_counts": exclusion_counts,
        "entries": records,
        "matrix": matrix,
        "entry_definition": "Closed-bar rejection followed by actual next-bar open.",
        "research_only": True,
        "signal_allowed": False,
        "order_submission_allowed": False,
    }


def _summary(outcomes: list[EventOutcome]) -> dict[str, Any]:
    summary = summarize_outcomes(outcomes)
    gains = sum(
        item.net_points
        for item in outcomes
        if item.include_in_expectancy
        and item.net_points is not None
        and item.net_points > 0
    )
    losses = -sum(
        item.net_points
        for item in outcomes
        if item.include_in_expectancy
        and item.net_points is not None
        and item.net_points < 0
    )
    summary["profit_factor"] = (
        gains / losses if losses > 0 else (None if gains == 0 else "infinite")
    )
    return summary


def _integrity_report(
    *,
    plans: list[Any],
    aggregated_events: list[FirstTouchEvent],
    side_events: list[FirstTouchEvent],
    eligibility: list[dict[str, Any]],
    policy: dict[str, Any],
) -> dict[str, Any]:
    checks = {
        "one_plan_per_session": len(plans) == len({item.session_date for item in plans}),
        "no_future_snapshot": all(
            item.selection.snapshot.observed_at <= item.selection.activation_at
            for item in plans
        ),
        "source_dte_in_frozen_range": all(
            policy["canonical_plan"]["minimum_source_dte"]
            <= item.selection.snapshot.source_dte
            <= policy["canonical_plan"]["maximum_source_dte"]
            for item in plans
        ),
        "one_aggregated_event_per_tier_session": len(aggregated_events)
        == len({(item.session_date, float(item.tier)) for item in aggregated_events}),
        "one_side_event_per_tier_session_side": len(side_events)
        == len(
            {
                (item.session_date, float(item.tier), item.side.value)
                for item in side_events
            }
        ),
        "all_rows_research_only": all(
            item.research_only
            and not item.signal_allowed
            and not item.order_submission_allowed
            for item in [*aggregated_events, *side_events]
        ),
        "ineligible_sessions_did_not_create_plans": all(
            not item["plan_created"] for item in eligibility if not item["backtest_eligible"]
        ),
    }
    return {
        "checks": checks,
        "violation_count": sum(not value for value in checks.values()),
        "research_only": True,
        "signal_allowed": False,
        "order_submission_allowed": False,
    }


def _plans_vs_events(plans: list[Any], events: list[FirstTouchEvent]) -> dict[str, Any]:
    planned = len(plans)
    by_tier = []
    for tier in (1.0, 1.5, 2.0, 3.0):
        count = sum(float(item.tier) == tier for item in events)
        by_tier.append(
            {
                "tier": tier,
                "planned_sessions": planned,
                "first_touch_events": count,
                "touch_rate": count / planned if planned else None,
                "projected_events_per_40_eligible_plans": (
                    40 * count / planned if planned else None
                ),
            }
        )
    return {
        "planned_sessions": planned,
        "plans_are_not_trade_events": True,
        "by_tier": by_tier,
        "projection_warning": "Projection is descriptive and not a guaranteed occurrence rate.",
    }


def _promotion_report(
    *,
    matrix: dict[str, Any],
    events: list[FirstTouchEvent],
    integrity: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    rows = []
    realistic_rows = {
        (item["tier"], item["barrier_id"]): item
        for item in matrix["rows"]
        if item["cost_points"] == 1.0
    }
    for tier_policy in policy["tier_matrix"]:
        tier = float(tier_policy["tier"])
        for barrier_id in [
            tier_policy["primary_barrier"],
            *tier_policy["comparison_barriers"],
        ]:
            summary = realistic_rows[(tier, barrier_id)]
            sides = {
                item.side.value for item in events if float(item.tier) == tier
            }
            checks = {
                "minimum_20_local_events": summary["event_count"]
                >= policy["promotion_gates"]["experimental_manual_event_count"],
                "minimum_10_holdout_events": summary["development_holdout"]["holdout"][
                    "event_count"
                ]
                >= policy["promotion_gates"]["minimum_holdout_events"],
                "positive_median_after_1_point_cost": (
                    summary["median_net_points"] is not None
                    and summary["median_net_points"] > 0
                ),
                "both_sides_represented": sides
                == {EventSide.LOWER_LONG.value, EventSide.UPPER_SHORT.value},
                "zero_integrity_violations": integrity["violation_count"] == 0,
                "acceptable_drawdown_threshold_frozen": False,
            }
            provisional_exception = (
                tier == 2.0
                and barrier_id == "TP25_SL25"
                and tier_policy.get("evidence_status")
                == "external_prior_plus_small_local_sample"
            )
            rows.append(
                {
                    "tier": tier,
                    "barrier_id": barrier_id,
                    "checks": checks,
                    "all_standard_gates_passed": all(checks.values()),
                    "provisional_external_prior_exception": provisional_exception,
                    "result": (
                        "PROVISIONAL_MANUAL_CANDIDATE_WITH_LIVE_DATA_GATES"
                        if provisional_exception
                        else "SHADOW_ONLY"
                    ),
                    "warning": (
                        "No numerical drawdown threshold was supplied, so standard "
                        "promotion cannot pass automatically."
                    ),
                }
            )
    return {
        "rows": rows,
        "research_only": True,
        "signal_allowed": False,
        "order_submission_allowed": False,
    }


def _review_handoff(
    *,
    metadata: dict[str, Any],
    matrix: dict[str, Any],
    executable: dict[str, Any],
    plans_vs_events: dict[str, Any],
    integrity: dict[str, Any],
    promotion: dict[str, Any],
    current_plan: dict[str, Any],
) -> str:
    lines = [
        "# XAU Tiered First-Touch Manual-Signal Research Handoff",
        "",
        "## Scope",
        "",
        "- Canonical plan: T0, source DTE nearest 0.80, fixed levels.",
        "- Mapping: futures distances reanchored to retained Dukascopy XAUUSD.",
        "- Primary count: one aggregated first touch per tier and session.",
        "- Execution study: lower-long 2SD plus mapped OI zone, rejection close, next-bar open.",
        "- All outputs are research-only. No signal or order submission is allowed.",
        "",
        "## Coverage",
        "",
        f"- Retained date range: {metadata['session_date_from']} to {metadata['session_date_to']}",
        f"- Completed eligible source sessions: {metadata['eligible_source_session_count']}",
        f"- Strict T0 DTE-0.80 source selections: {metadata['strict_t0_dte_selection_count']}",
        f"- CFD-mapped daily plans: {metadata['planned_session_count']}",
        "- Strict selections without a mappable retained XAUUSD bar: "
        f"{metadata['strict_selection_mapping_failure_count']}",
        f"- Aggregated tier events: {metadata['aggregated_event_count']}",
        "",
        "## Plans Versus Events",
        "",
        "| Tier | Plans | First touches | Touch rate | Projected per 40 plans |",
        "|---:|---:|---:|---:|---:|",
    ]
    for item in plans_vs_events["by_tier"]:
        lines.append(
            f"| {item['tier']:g}SD | {item['planned_sessions']} | "
            f"{item['first_touch_events']} | {_percent(item['touch_rate'])} | "
            f"{_number(item['projected_events_per_40_eligible_plans'])} |"
        )
    lines.extend(
        [
            "",
            "## Tier Matrix At 1 Point Cost",
            "",
            "| Tier | Barrier | Events | TP | SL | Ambiguous | Unresolved | "
            "Expectancy | Profit factor |",
            "|---:|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in matrix["rows"]:
        if row["cost_points"] != 1.0:
            continue
        lines.append(
            f"| {row['tier']:g}SD | {row['barrier_id']} | {row['event_count']} | "
            f"{row['tp_first_count']} | {row['sl_first_count']} | "
            f"{row['ambiguous_count']} | {row['unresolved_count']} | "
            f"{_number(row['net_expectancy_points'])} | {_number(row['profit_factor'])} |"
        )
    lines.extend(
        [
            "",
            "The 1SD TP12.5/SL12.5 arm remains `SHADOW_ONLY`; it is not promoted from this run.",
            "",
            "## Executable 2SD OI-Rejection Test",
            "",
            "- Raw lower-long 2SD candidates: "
            f"{executable['candidate_lower_2sd_first_touch_count']}",
            f"- Qualified rule entries: {executable['qualified_entry_count']}",
            "- Independent qualified sessions: "
            f"{executable['qualified_independent_session_count']}",
            "- Entry is measured at the actual next-bar open after a closed-bar "
            "R1/R2 confirmation.",
            "",
            "| Rule | Barrier | Cost | Events | TP | SL | Ambiguous | Expectancy |",
            "|---|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in executable["matrix"]:
        if row["cost_points"] != 1.0:
            continue
        lines.append(
            f"| {row['rule']} | {row['barrier_id']} | {row['cost_points']} | "
            f"{row['event_count']} | {row['tp_first_count']} | {row['sl_first_count']} | "
            f"{row['ambiguous_count']} | {_number(row['net_expectancy_points'])} |"
        )
    lines.extend(
        [
            "",
            "## Current Session",
            "",
            f"- Plan status: {(current_plan.get('plan') or {}).get('status', 'unavailable')}",
            f"- Signal status: {(current_plan.get('signal') or {}).get('status', 'none')}",
            "- Without a synchronized valid broker bid/ask, an eligible setup is "
            "a `REFERENCE_ALERT`.",
            "",
            "## Integrity",
            "",
            f"- Violations: {integrity['violation_count']}",
        ]
    )
    for name, passed in integrity["checks"].items():
        lines.append(f"- {name}: `{passed}`")
    lines.extend(["", "## Promotion Gates", ""])
    for item in promotion["rows"]:
        if not (
            item["barrier_id"] in {"TP12_5_SL12_5", "TP25_SL25"}
            and item["tier"] in {1.0, 1.5, 2.0, 3.0}
        ):
            continue
        lines.append(
            f"- {item['tier']:g}SD {item['barrier_id']}: `{item['result']}`; "
            f"standard gates passed=`{item['all_standard_gates_passed']}`."
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "This report measures retained local evidence only. Small event counts, one-sided "
            "coverage, and empty holdout groups prevent a profitability or live-readiness claim.",
            "CFD execution adds sizing flexibility, not statistical edge; broker basis, spread, "
            "and wick differences remain execution risks.",
            "",
        ]
    )
    return "\n".join(lines)


def _valid_selection(selection: Any, policy: dict[str, Any]) -> bool:
    return (
        selection.strict_dte_eligible
        and selection.snapshot.observed_at <= selection.activation_at
        and policy["canonical_plan"]["minimum_source_dte"]
        <= selection.snapshot.source_dte
        <= policy["canonical_plan"]["maximum_source_dte"]
    )


def _bars_by_date(bars: list[Any], timezone: str) -> dict[date, list[Any]]:
    zone = ZoneInfo(timezone)
    grouped: dict[date, list[Any]] = {}
    for bar in bars:
        grouped.setdefault(bar.timestamp.astimezone(zone).date(), []).append(bar)
    return grouped


def _file_record(path: Path) -> dict[str, Any]:
    return {
        "path": path.as_posix(),
        "exists": path.exists(),
        "size_bytes": path.stat().st_size if path.exists() else None,
    }


def _increment(counts: dict[str, int], key: str) -> None:
    counts[key] = counts.get(key, 0) + 1


def _secondary_excursions(
    bars: list[Any],
    *,
    entry_timestamp: datetime,
    entry_price: float,
    one_sd_points: float,
    fractions: list[float],
) -> dict[str, Any]:
    later = [item for item in bars if item.timestamp >= entry_timestamp]
    maximum_favorable = max(
        (item.high - entry_price for item in later),
        default=None,
    )
    return {
        "maximum_favorable_excursion_points": maximum_favorable,
        "sd_excursions": {
            f"{fraction:g}SD": (
                maximum_favorable >= fraction * one_sd_points
                if maximum_favorable is not None
                else None
            )
            for fraction in fractions
        },
    }


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _percent(value: float | None) -> str:
    return f"{value:.2%}" if value is not None else "n/a"


def _number(value: Any) -> str:
    return f"{value:.3f}" if isinstance(value, int | float) else str(value or "n/a")
