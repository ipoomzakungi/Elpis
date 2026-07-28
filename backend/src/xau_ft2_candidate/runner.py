from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from src.models.xau_ft2_candidate import XauFt2BrokerQuote
from src.xau_first_touch_study.models import (
    CountingMode,
    EventOutcome,
    EventSide,
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
    summarize_outcomes,
)
from src.xau_ft2_candidate.coverage_audit import (
    CoverageAuditConfig,
    run_coverage_audit,
    write_coverage_audit,
)
from src.xau_ft2_candidate.policy import load_candidate_policy
from src.xau_ft2_candidate.service import XauFt2CandidateService
from src.xau_tiered_manual_signal.tiers import (
    build_tier_events,
    evaluate_tier_barrier,
)
from src.xau_vol2vol_history_walkforward.data_lake import daily_raw_path
from src.xau_vol2vol_history_walkforward.walkforward_simulator import (
    load_traded_bars_folder,
)


@dataclass(frozen=True)
class Ft2CandidateRunConfig:
    vol2vol_root: Path
    price_bars_folder: Path
    policy_path: Path
    output_root: Path
    journal_root: Path
    session_date_from: date
    session_date_to: date
    as_of_date: date
    timezone: str = "Asia/Bangkok"
    broker_quote: XauFt2BrokerQuote | None = None


def run_candidate_study(config: Ft2CandidateRunConfig) -> Path:
    policy = load_candidate_policy(config.policy_path)
    run_id = f"xau_ft2_candidate_{datetime.now().strftime('%Y%m%dT%H%M%S%f')}"
    run_dir = config.output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    audit = run_coverage_audit(
        CoverageAuditConfig(
            vol2vol_root=config.vol2vol_root,
            price_bars_folder=config.price_bars_folder,
            session_date_from=config.session_date_from,
            session_date_to=config.session_date_to,
            as_of_date=config.as_of_date,
            target_dte=policy["canonical_plan"]["source_dte_target"],
            minimum_dte=policy["canonical_plan"]["source_dte_minimum"],
            maximum_dte=policy["canonical_plan"]["source_dte_maximum"],
            timezone=config.timezone,
        )
    )
    write_coverage_audit(run_dir, audit)

    price_result = load_traded_bars_folder(
        config.price_bars_folder,
        timezone=config.timezone,
    )
    bars_by_date = _bars_by_date(price_result.bars, config.timezone)
    plans = []
    events = []
    current = config.session_date_from
    while current <= config.session_date_to:
        audit_row = next(
            item for item in audit["rows"] if item["session_date"] == current.isoformat()
        )
        if not audit_row["final_plan_eligible"]:
            current += timedelta(days=1)
            continue
        selection = select_snapshot(
            load_source_snapshots(daily_raw_path(config.vol2vol_root, current), current),
            anchor=TimeAnchor.T0_DTE_080,
            session_date=current,
            timezone=config.timezone,
            target_dte=policy["canonical_plan"]["source_dte_target"],
            dte_tolerance=policy["canonical_plan"]["source_dte_tolerance"],
        )
        if selection is None:
            current += timedelta(days=1)
            continue
        plan = map_selection(
            selection,
            bars_by_date.get(current, []),
            mapping_mode=MappingMode.DISTANCE_REANCHORED,
        )
        if plan is None:
            current += timedelta(days=1)
            continue
        plans.append(plan)
        events.extend(
            item
            for item in build_tier_events(
                plan,
                bars_by_date.get(current, []),
                counting_mode=CountingMode.AGGREGATED,
            )
            if float(item.tier) == 2.0
        )
        current += timedelta(days=1)

    primary = _outcome_matrix(
        events,
        bars_by_date,
        costs=policy["cost_scenarios_points"],
        tp_points=policy["canonical_plan"]["take_profit_points"],
        sl_points=policy["canonical_plan"]["stop_loss_points"],
    )
    small = _outcome_matrix(
        events,
        bars_by_date,
        costs=policy["cost_scenarios_points"],
        tp_points=policy["challengers"]["FT2_SMALL_V1"]["take_profit_points"],
        sl_points=policy["challengers"]["FT2_SMALL_V1"]["stop_loss_points"],
    )
    integrity = _integrity(plans, events, audit, policy)
    sample = _sample_report(
        audit=audit,
        events=events,
        primary=primary,
        integrity=integrity,
        policy=policy,
    )
    current_plan = XauFt2CandidateService(
        journal_root=config.journal_root,
        policy_path=config.policy_path,
        vol2vol_root=config.vol2vol_root,
        price_bars_folder=config.price_bars_folder,
        timezone=config.timezone,
    ).process_session(
        session_date=config.as_of_date,
        broker_quote=config.broker_quote,
    )
    artifacts = {
        "metadata.json": {
            "run_id": run_id,
            "candidate_id": policy["candidate_id"],
            "candidate_hash": policy["candidate_hash"],
            "session_date_from": config.session_date_from.isoformat(),
            "session_date_to": config.session_date_to.isoformat(),
            "as_of_date": config.as_of_date.isoformat(),
            "research_only": True,
            "signal_allowed": False,
            "order_submission_allowed": False,
        },
        "frozen_plans.json": [as_record(item) for item in plans],
        "ft2_raw_events.json": [as_record(item) for item in events],
        "ft2_raw_outcomes.json": primary,
        "ft2_small_shadow_outcomes.json": small,
        "sample_report.json": sample,
        "promotion_gates.json": sample["promotion"],
        "integrity_report.json": integrity,
        "current_plan.json": current_plan.model_dump(mode="json"),
    }
    for name, payload in artifacts.items():
        _write_json(run_dir / name, payload)
    (run_dir / "sample_report.md").write_text(
        _sample_markdown(sample),
        encoding="utf-8",
    )
    (run_dir / "review_handoff.md").write_text(
        _review_handoff(audit, sample, current_plan.model_dump(mode="json")),
        encoding="utf-8",
    )
    return run_dir


def _outcome_matrix(
    events: list[Any],
    bars_by_date: dict[date, list[Any]],
    *,
    costs: list[float],
    tp_points: float,
    sl_points: float,
) -> dict[str, Any]:
    rows = []
    details = {}
    for cost in costs:
        outcomes = [
            evaluate_tier_barrier(
                event,
                bars_by_date.get(event.session_date, []),
                tp_points=tp_points,
                sl_points=sl_points,
                cost_points=cost,
            )
            for event in events
        ]
        summary = _summary(outcomes)
        rows.append(
            {
                "cost_points": cost,
                **summary,
                "development_holdout": chronological_split(outcomes),
            }
        )
        details[str(cost)] = [as_record(item) for item in outcomes]
    return {
        "take_profit_points": tp_points,
        "stop_loss_points": sl_points,
        "rows": rows,
        "outcomes_by_cost": details,
        "event_count_is_not_multiplied_by_costs": True,
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
        gains / losses if losses else ("infinite" if gains else None)
    )
    return summary


def _sample_report(
    *,
    audit: dict[str, Any],
    events: list[Any],
    primary: dict[str, Any],
    integrity: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    realistic = next(item for item in primary["rows"] if item["cost_points"] == 1.0)
    plan_count = audit["mapped_plans"]
    lower = sum(item.side == EventSide.LOWER_LONG for item in events)
    upper = sum(item.side == EventSide.UPPER_SHORT for item in events)
    resolved_sessions = realistic["tp_first_count"] + realistic["sl_first_count"]
    gate_config = policy["promotion_gates"]
    checks = {
        "minimum_30_local_events": len(events)
        >= gate_config["minimum_local_first_touch_events"],
        "minimum_10_holdout_events": realistic["development_holdout"]["holdout"][
            "event_count"
        ]
        >= gate_config["minimum_holdout_events"],
        "minimum_10_resolved_independent_sessions": resolved_sessions
        >= gate_config["minimum_resolved_independent_sessions"],
        "minimum_5_upper_events": upper >= gate_config["minimum_upper_events"],
        "minimum_5_lower_events": lower >= gate_config["minimum_lower_events"],
        "zero_mapping_timing_violations": integrity["violation_count"] == 0,
        "positive_median_after_1_point_cost": (
            realistic["median_net_points"] is not None
            and realistic["median_net_points"] > 0
        ),
        "confidence_evidence_reported": (
            realistic["wilson_interval_95"] is not None
            and realistic["session_clustered_expectancy_ci95"] is not None
        ),
        "drawdown_threshold_configured": (
            gate_config["maximum_drawdown_points"] is not None
        ),
    }
    return {
        "candidate_id": policy["candidate_id"],
        "candidate_hash": policy["candidate_hash"],
        "completed_source_sessions": audit["completed_sessions"],
        "eligible_strict_plans": plan_count,
        "eligible_plan_rate": (
            plan_count / audit["completed_sessions"]
            if audit["completed_sessions"]
            else None
        ),
        "first_touch_event_count": len(events),
        "touch_rate": len(events) / plan_count if plan_count else None,
        "projected_events": {
            str(plans): plans * len(events) / plan_count if plan_count else None
            for plans in (40, 100, 200)
        },
        "lower_long_events": lower,
        "upper_short_events": upper,
        "tp_first": realistic["tp_first_count"],
        "sl_first": realistic["sl_first_count"],
        "ambiguous": realistic["ambiguous_count"],
        "unresolved": realistic["unresolved_count"],
        "cost_adjusted_result_at_1_point": realistic,
        "holdout_event_count": realistic["development_holdout"]["holdout"][
            "event_count"
        ],
        "promotion": {
            "checks": checks,
            "all_standard_gates_passed": all(checks.values()),
            "status": "PROVISIONAL_RESEARCH_ALERTS_ONLY",
            "external_prior_bypass_used": False,
            "warning": (
                "Forty eligible plans are an operational test, not a "
                "profitability-validation sample."
            ),
        },
        "research_only": True,
        "signal_allowed": False,
        "order_submission_allowed": False,
    }


def _integrity(
    plans: list[Any],
    events: list[Any],
    audit: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    checks = {
        "one_plan_per_session": len(plans) == len({item.session_date for item in plans}),
        "one_ft2_event_per_session": len(events)
        == len({item.session_date for item in events}),
        "all_events_literal_2sd": all(float(item.tier) == 2.0 for item in events),
        "all_events_aggregated": all(
            item.counting_mode == CountingMode.AGGREGATED for item in events
        ),
        "all_plans_strict_dte": all(
            policy["canonical_plan"]["source_dte_minimum"]
            <= item.selection.snapshot.source_dte
            <= policy["canonical_plan"]["source_dte_maximum"]
            for item in plans
        ),
        "audit_plan_count_matches": len(plans) == audit["mapped_plans"],
        "no_future_snapshots": all(
            item.selection.snapshot.observed_at <= item.selection.activation_at
            for item in plans
        ),
        "research_only": all(
            item.research_only
            and not item.signal_allowed
            and not item.order_submission_allowed
            for item in events
        ),
    }
    return {
        "checks": checks,
        "violation_count": sum(not value for value in checks.values()),
        "research_only": True,
        "signal_allowed": False,
        "order_submission_allowed": False,
    }


def _bars_by_date(bars: list[Any], timezone: str) -> dict[date, list[Any]]:
    zone = ZoneInfo(timezone)
    grouped: dict[date, list[Any]] = {}
    for bar in bars:
        grouped.setdefault(bar.timestamp.astimezone(zone).date(), []).append(bar)
    return grouped


def _sample_markdown(sample: dict[str, Any]) -> str:
    result = sample["cost_adjusted_result_at_1_point"]
    return "\n".join(
        [
            "# FT2_RAW_V1 Sample Report",
            "",
            f"- Completed source sessions: {sample['completed_source_sessions']}",
            f"- Eligible strict plans: {sample['eligible_strict_plans']}",
            f"- Literal 2SD first touches: {sample['first_touch_event_count']}",
            f"- Touch rate: {_percent(sample['touch_rate'])}",
            f"- Lower/upper events: {sample['lower_long_events']}/{sample['upper_short_events']}",
            f"- TP/SL/ambiguous: {sample['tp_first']}/{sample['sl_first']}/{sample['ambiguous']}",
            f"- Net expectancy at 1 point cost: {_number(result['net_expectancy_points'])}",
            f"- Promotion: {sample['promotion']['status']}",
            "",
            "Forty eligible plans are an operational test, not a "
            "profitability-validation sample.",
            "",
        ]
    )


def _review_handoff(
    audit: dict[str, Any],
    sample: dict[str, Any],
    current: dict[str, Any],
) -> str:
    return "\n".join(
        [
            "# FT2_RAW_V1 Review Handoff",
            "",
            "## Coverage",
            "",
            f"- Completed sessions: {audit['completed_sessions']}",
            f"- Raw DTE-qualified sessions: {audit['source_qualified_sessions']}",
            f"- Parser-qualified sessions: {audit['parser_qualified_sessions']}",
            f"- CFD-mapped plans: {audit['mapped_plans']}",
            f"- Recoverable exclusions: {audit['recoverable_exclusions']}",
            f"- Irrecoverable exclusions: {audit['irrecoverable_exclusions']}",
            "",
            "The four raw-DTE-qualified parser exclusions contain no complete "
            "literal 1/2/3SD ranges. No parser bug was demonstrated.",
            "",
            "## Frozen Candidate",
            "",
            f"- Candidate: {sample['candidate_id']}",
            f"- Hash: `{sample['candidate_hash']}`",
            "- Trigger: first aggregated literal-2SD touch.",
            "- Entry model: touch-reference.",
            "- Exit: TP25/SL25.",
            "- OI, IV, volume, and rejection are descriptive and do not gate the alert.",
            "",
            "## Local Sample",
            "",
            f"- Events: {sample['first_touch_event_count']}",
            f"- Touch rate: {_percent(sample['touch_rate'])}",
            f"- Lower/upper: {sample['lower_long_events']}/{sample['upper_short_events']}",
            f"- TP/SL/ambiguous: {sample['tp_first']}/{sample['sl_first']}/{sample['ambiguous']}",
            f"- Holdout events: {sample['holdout_event_count']}",
            "",
            "## Promotion",
            "",
            f"- Status: `{sample['promotion']['status']}`",
            "- External prior bypass: `False`",
            "- Drawdown threshold is unset, so promotion is blocked.",
            "",
            "## Current Session",
            "",
            f"- Plan status: {(current.get('plan') or {}).get('status', 'unavailable')}",
            f"- Alert status: {(current.get('alert') or {}).get('status', 'none')}",
            "",
            "All outputs remain research-only and cannot submit orders.",
            "",
        ]
    )


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _percent(value: float | None) -> str:
    return f"{value:.2%}" if value is not None else "n/a"


def _number(value: float | None) -> str:
    return f"{value:.3f}" if value is not None else "n/a"
