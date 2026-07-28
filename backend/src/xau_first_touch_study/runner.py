from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from src.models.xau_market_context import XauPriceBar
from src.xau_first_touch_study.events import (
    attach_event_context,
    build_first_touch_events,
    evaluate_first_passage,
    evaluate_published_label,
)
from src.xau_first_touch_study.models import (
    CountingMode,
    EventOutcome,
    FirstTouchEvent,
    MappedPlan,
    MappingMode,
    SnapshotSelection,
    TimeAnchor,
    as_record,
)
from src.xau_first_touch_study.registry import load_registry
from src.xau_first_touch_study.selection import (
    load_source_snapshots,
    map_selection,
    select_snapshot,
)
from src.xau_first_touch_study.shadow import ShadowSession
from src.xau_first_touch_study.statistics import (
    benjamini_hochberg,
    binomial_upper_tail,
    chronological_split,
    external_prior_comparison,
    grouped_summaries,
    summarize_outcomes,
)
from src.xau_vol2vol_history_walkforward.data_lake import (
    daily_raw_path,
    evaluate_daily_session_eligibility,
)
from src.xau_vol2vol_history_walkforward.walkforward_simulator import (
    load_traded_bars_folder,
)


@dataclass(frozen=True)
class FirstTouchStudyConfig:
    vol2vol_root: Path
    price_bars_folder: Path
    registry_path: Path
    output_root: Path
    session_date_from: date
    session_date_to: date
    as_of_date: date
    timezone: str = "Asia/Bangkok"


def run_study(config: FirstTouchStudyConfig) -> Path:
    registry = load_registry(config.registry_path)
    run_id = f"xau_first_touch_study_{datetime.now().strftime('%Y%m%dT%H%M%S%f')}"
    run_dir = config.output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    price_result = load_traded_bars_folder(
        config.price_bars_folder,
        timezone=config.timezone,
    )
    bars_by_date = _bars_by_date(price_result.bars, config.timezone)

    eligibility_rows: list[dict[str, Any]] = []
    selections: list[SnapshotSelection] = []
    plans: list[MappedPlan] = []
    events: list[FirstTouchEvent] = []
    source_paths: list[Path] = []
    current = config.session_date_from
    while current <= config.session_date_to:
        eligibility = evaluate_daily_session_eligibility(
            root=config.vol2vol_root,
            session_date=current,
            current_date=config.as_of_date,
        )
        eligibility_rows.append(
            {
                "session_date": current.isoformat(),
                "source_session_status": eligibility.source_session_status,
                "backtest_eligible": eligibility.backtest_eligible,
                "reasons": eligibility.reasons,
                "payload_sha256": eligibility.payload_sha256,
            }
        )
        if not eligibility.backtest_eligible:
            current += timedelta(days=1)
            continue
        raw_path = daily_raw_path(config.vol2vol_root, current)
        source_paths.append(raw_path)
        snapshots = load_source_snapshots(raw_path, current)
        session_bars = bars_by_date.get(current, [])
        for anchor in TimeAnchor:
            selection = select_snapshot(
                snapshots,
                anchor=anchor,
                session_date=current,
                timezone=config.timezone,
                target_dte=registry["selection"]["primary_dte"],
                dte_tolerance=registry["selection"]["primary_dte_tolerance"],
            )
            if selection is None:
                continue
            selections.append(selection)
            for mapping_mode in MappingMode:
                plan = map_selection(
                    selection,
                    session_bars,
                    mapping_mode=mapping_mode,
                    maximum_gap_seconds=registry["mapping_modes"]["same_time_reference_basis"][
                        "maximum_timestamp_gap_seconds"
                    ],
                )
                if plan is None:
                    continue
                plans.append(plan)
                for counting_mode in CountingMode:
                    plan_events = build_first_touch_events(
                        plan,
                        session_bars,
                        counting_mode=counting_mode,
                    )
                    events.extend(
                        attach_event_context(item, plan, session_bars) for item in plan_events
                    )
        current += timedelta(days=1)

    plan_by_id = {item.plan_id: item for item in plans}
    primary_events = [
        item
        for item in events
        if item.counting_mode == CountingMode.AGGREGATED
        and item.anchor == TimeAnchor.T0_DTE_080
        and item.mapping_mode == MappingMode.DISTANCE_REANCHORED
        and plan_by_id[item.plan_id].selection.strict_dte_eligible
    ]
    published_outcomes = _published_outcomes(
        events,
        bars_by_date,
        favorable_points=registry["external_prior"]["significant_reversal_points"],
    )
    strict_outcomes = _strict_outcomes(
        events,
        bars_by_date,
        tp_points=25.0,
        sl_points=25.0,
        cost_points=0.0,
    )
    published_primary = _outcomes_for_events(published_outcomes, primary_events)
    strict_primary = _outcomes_for_events(strict_outcomes, primary_events)
    dte_events = [
        item
        for item in events
        if item.counting_mode == CountingMode.AGGREGATED
        and item.anchor == TimeAnchor.T0_DTE_080
        and item.mapping_mode == MappingMode.DISTANCE_REANCHORED
    ]
    time_anchor_events = [
        item
        for item in events
        if item.counting_mode == CountingMode.AGGREGATED
        and item.mapping_mode == MappingMode.DISTANCE_REANCHORED
    ]
    mapping_events = [
        item
        for item in events
        if item.counting_mode == CountingMode.AGGREGATED and item.anchor == TimeAnchor.T0_DTE_080
    ]
    side_events = [
        item
        for item in events
        if item.counting_mode == CountingMode.SIDE_SPECIFIC
        and item.anchor == TimeAnchor.T0_DTE_080
        and item.mapping_mode == MappingMode.DISTANCE_REANCHORED
    ]
    barrier = _barrier_sensitivity(
        events,
        bars_by_date,
        registry,
        primary_event_ids={item.event_id for item in primary_events},
    )
    dte = _dte_sensitivity(
        dte_events,
        _outcomes_for_events(strict_outcomes, dte_events),
        registry,
    )
    time_anchor = _group_outcome_report(
        _outcomes_for_events(strict_outcomes, time_anchor_events),
        "anchor",
    )
    mapping = _group_outcome_report(
        _outcomes_for_events(strict_outcomes, mapping_events),
        "mapping_mode",
    )
    side = _group_outcome_report(
        _outcomes_for_events(strict_outcomes, side_events),
        "side",
    )
    strict_report = _strict_report(strict_primary, events, bars_by_date, registry)
    published_report = _published_report(published_primary)
    external = external_prior_comparison(
        {tier: [item for item in published_primary if item.tier == tier] for tier in (1, 2, 3)},
        registry["external_prior"],
    )
    shadow = _build_shadow_plan(
        config=config,
        registry=registry,
        bars_by_date=bars_by_date,
    )
    integrity = _integrity_report(
        selections=selections,
        plans=plans,
        events=events,
        registry=registry,
    )
    promotion = _promotion_gates(strict_primary, integrity)

    manifest = {
        "run_id": run_id,
        "experiment_hash": registry["experiment_hash"],
        "registry_path": config.registry_path.as_posix(),
        "session_date_from": config.session_date_from.isoformat(),
        "session_date_to": config.session_date_to.isoformat(),
        "as_of_date": config.as_of_date.isoformat(),
        "source_paths": [_file_record(path) for path in source_paths],
        "price_paths": [_file_record(path) for path in price_result.source_paths],
        "external_source_status": "user_supplied_summary_not_independently_reproduced",
        "research_only": True,
        "signal_allowed": False,
        "order_submission_allowed": False,
    }
    selected_records = [
        {
            **as_record(item),
            "expiry": item.snapshot.expiry.isoformat() if item.snapshot.expiry else None,
            "calendar_dte": item.snapshot.calendar_dte,
            "trading_session_dte": item.snapshot.trading_session_dte,
        }
        for item in selections
    ]
    context = _context_report(events, strict_outcomes)
    metadata = {
        "run_id": run_id,
        "created_at": datetime.now(tz=ZoneInfo(config.timezone)).isoformat(),
        "eligible_session_count": sum(item["backtest_eligible"] for item in eligibility_rows),
        "selected_snapshot_count": len(selections),
        "mapped_plan_count": len(plans),
        "first_touch_event_count": len(events),
        "primary_event_count": len(primary_events),
        "promotion_gate_status": promotion["status"],
        "research_only": True,
        "signal_allowed": False,
        "order_submission_allowed": False,
    }
    artifacts = {
        "study_manifest.json": manifest,
        "session_eligibility.json": eligibility_rows,
        "selected_snapshots.json": selected_records,
        "first_touch_events.json": [as_record(item) for item in events],
        "published_label_results.json": published_report,
        "strict_first_passage_results.json": strict_report,
        "barrier_sensitivity.json": barrier,
        "dte_sensitivity.json": dte,
        "time_anchor_sensitivity.json": time_anchor,
        "mapping_sensitivity.json": mapping,
        "side_comparison.json": side,
        "oi_iv_flow_context.json": context,
        "external_prior_comparison.json": external,
        "shadow_plan.json": shadow,
        "integrity_report.json": integrity,
        "metadata.json": metadata,
    }
    for filename, payload in artifacts.items():
        _write_json(run_dir / filename, payload)
    (run_dir / "review_handoff.md").write_text(
        _review_handoff(
            run_dir=run_dir,
            registry=registry,
            metadata=metadata,
            selections=selections,
            events=primary_events,
            published=published_report,
            strict=strict_report,
            barrier=barrier,
            dte=dte,
            time_anchor=time_anchor,
            mapping=mapping,
            promotion=promotion,
            integrity=integrity,
            shadow=shadow,
        ),
        encoding="utf-8",
    )
    return run_dir


def _published_outcomes(
    events: list[FirstTouchEvent],
    bars_by_date: dict[date, list[XauPriceBar]],
    *,
    favorable_points: float,
) -> list[EventOutcome]:
    return [
        evaluate_published_label(
            item,
            bars_by_date.get(item.session_date, []),
            favorable_points=favorable_points,
        )
        for item in events
    ]


def _strict_outcomes(
    events: list[FirstTouchEvent],
    bars_by_date: dict[date, list[XauPriceBar]],
    *,
    tp_points: float,
    sl_points: float,
    cost_points: float,
    conservative: bool = False,
) -> list[EventOutcome]:
    return [
        evaluate_first_passage(
            item,
            bars_by_date.get(item.session_date, []),
            tp_points=tp_points,
            sl_points=sl_points,
            cost_points=cost_points,
            conservative_ambiguous_loss=conservative,
        )
        for item in events
    ]


def _published_report(outcomes: list[EventOutcome]) -> dict[str, Any]:
    return {
        "label_definition": (
            "At least 25 points toward the mean after first touch before session end; "
            "no adverse barrier."
        ),
        "by_tier": grouped_summaries(outcomes, lambda item: str(item.tier)),
        "outcomes": [as_record(item) for item in outcomes],
        "warning": "This rate is not a tradable TP25/SL25 win rate.",
        "research_only": True,
        "signal_allowed": False,
        "order_submission_allowed": False,
    }


def _strict_report(
    primary: list[EventOutcome],
    events: list[FirstTouchEvent],
    bars_by_date: dict[date, list[XauPriceBar]],
    registry: dict[str, Any],
) -> dict[str, Any]:
    costs = {}
    primary_ids = {item.event_id for item in primary}
    primary_events = [item for item in events if item.event_id in primary_ids]
    for cost in registry["cost_scenarios_points"]:
        outcomes = _strict_outcomes(
            primary_events,
            bars_by_date,
            tp_points=25,
            sl_points=25,
            cost_points=cost,
        )
        costs[str(cost)] = grouped_summaries(outcomes, lambda item: str(item.tier))
    conservative = _strict_outcomes(
        primary_events,
        bars_by_date,
        tp_points=25,
        sl_points=25,
        cost_points=1.0,
        conservative=True,
    )
    return {
        "label_definition": "TP25 before SL25 from literal first touch.",
        "by_tier": grouped_summaries(primary, lambda item: str(item.tier)),
        "chronological_development_holdout_by_tier": {
            str(tier): chronological_split([item for item in primary if item.tier == tier])
            for tier in (1, 2, 3)
        },
        "cost_sensitivity": costs,
        "conservative_ambiguous_as_loss_at_1_point_cost": grouped_summaries(
            conservative,
            lambda item: str(item.tier),
        ),
        "outcomes": [as_record(item) for item in primary],
        "research_only": True,
        "signal_allowed": False,
        "order_submission_allowed": False,
    }


def _barrier_sensitivity(
    events: list[FirstTouchEvent],
    bars_by_date: dict[date, list[XauPriceBar]],
    registry: dict[str, Any],
    *,
    primary_event_ids: set[str],
) -> dict[str, Any]:
    primary_events = [item for item in events if item.event_id in primary_event_ids]
    trials = []
    p_values = []
    for trial in registry["barrier_trials"]:
        if "tp_points" in trial:
            tp = float(trial["tp_points"])
            sl = float(trial["sl_points"])
        else:
            fraction = float(trial["tp_sd_fraction"])
            outcomes = [
                evaluate_first_passage(
                    item,
                    bars_by_date.get(item.session_date, []),
                    tp_points=item.one_sd_points * fraction,
                    sl_points=item.one_sd_points * float(trial["sl_sd_fraction"]),
                )
                for item in primary_events
            ]
            trial_summary = grouped_summaries(outcomes, lambda item: str(item.tier))
            trials.append(
                {
                    "trial": trial,
                    "event_count": len(outcomes),
                    "by_tier": trial_summary,
                }
            )
            continue
        outcomes = _strict_outcomes(
            primary_events,
            bars_by_date,
            tp_points=tp,
            sl_points=sl,
            cost_points=0,
        )
        summaries = grouped_summaries(outcomes, lambda item: str(item.tier))
        trials.append({"trial": trial, "event_count": len(outcomes), "by_tier": summaries})
        for summary in summaries:
            resolved = summary["tp_first_count"] + summary["sl_first_count"]
            p_values.append(
                (
                    f"{trial['id']}:tier{summary['group']}",
                    binomial_upper_tail(
                        summary["tp_first_count"],
                        resolved,
                        sl / (tp + sl),
                    ),
                )
            )
    counts = {item["event_count"] for item in trials}
    return {
        "trials": trials,
        "event_count_invariant": len(counts) <= 1,
        "multiple_testing_adjustment": {
            "method": "benjamini_hochberg",
            "results": benjamini_hochberg(p_values),
        },
        "best_trial_selected": False,
        "research_only": True,
        "signal_allowed": False,
        "order_submission_allowed": False,
    }


def _dte_sensitivity(
    events: list[FirstTouchEvent],
    outcomes: list[EventOutcome],
    registry: dict[str, Any],
) -> dict[str, Any]:
    event_by_id = {item.event_id: item for item in events}
    rows = []
    for bucket in registry["dte_buckets"]:
        bucket_outcomes = [
            item
            for item in outcomes
            if bucket["minimum"] <= event_by_id[item.event_id].source_dte <= bucket["maximum"]
        ]
        rows.append(
            {
                "bucket": bucket,
                "by_tier": grouped_summaries(
                    bucket_outcomes,
                    lambda item: str(item.tier),
                ),
            }
        )
    return {
        "buckets": rows,
        "post_hoc_thresholds_added": False,
        "research_only": True,
        "signal_allowed": False,
        "order_submission_allowed": False,
    }


def _group_outcome_report(
    outcomes: list[EventOutcome],
    field: str,
) -> dict[str, Any]:
    return {
        "groups": grouped_summaries(
            outcomes,
            lambda item: f"{getattr(item, field).value}:tier{item.tier}",
        ),
        "pooled_strategy_rate": None,
        "research_only": True,
        "signal_allowed": False,
        "order_submission_allowed": False,
    }


def _build_shadow_plan(
    *,
    config: FirstTouchStudyConfig,
    registry: dict[str, Any],
    bars_by_date: dict[date, list[XauPriceBar]],
) -> dict[str, Any]:
    shadow = ShadowSession()
    raw_path = daily_raw_path(config.vol2vol_root, config.as_of_date)
    eligibility = evaluate_daily_session_eligibility(
        root=config.vol2vol_root,
        session_date=config.as_of_date,
        current_date=config.as_of_date,
    )
    if not raw_path.exists() or not eligibility.forward_plan_eligible:
        shadow.load_plan(None)
        return {
            "session_date": config.as_of_date.isoformat(),
            "reason": eligibility.reasons or ["Current Vol2Vol payload is unavailable."],
            "session": shadow.as_record(),
            "shadow_candidates": [],
        }
    snapshots = load_source_snapshots(raw_path, config.as_of_date)
    selection = select_snapshot(
        snapshots,
        anchor=TimeAnchor.T0_DTE_080,
        session_date=config.as_of_date,
        timezone=config.timezone,
        target_dte=registry["selection"]["primary_dte"],
        dte_tolerance=registry["selection"]["primary_dte_tolerance"],
    )
    plan = (
        map_selection(
            selection,
            bars_by_date.get(config.as_of_date, []),
            mapping_mode=MappingMode.DISTANCE_REANCHORED,
        )
        if selection
        else None
    )
    shadow.load_plan(plan)
    return {
        "session_date": config.as_of_date.isoformat(),
        "reason": "Plan ready; waiting for literal first touch." if plan else "Mapping blocked.",
        "plan": as_record(plan) if plan else None,
        "session": shadow.as_record(),
        "shadow_candidates": [],
    }


def _integrity_report(
    *,
    selections: list[SnapshotSelection],
    plans: list[MappedPlan],
    events: list[FirstTouchEvent],
    registry: dict[str, Any],
) -> dict[str, Any]:
    violations = {
        "future_snapshot_used_count": sum(
            item.snapshot.observed_at > item.activation_at for item in selections
        ),
        "mixed_series_plan_count": 0,
        "non_closed_bar_count": sum(item.closed_bar_status != "closed" for item in plans),
        "same_time_gap_violation_count": sum(
            item.mapping_mode == MappingMode.SAME_TIME_REFERENCE_BASIS
            and item.source_gap_seconds
            > registry["mapping_modes"]["same_time_reference_basis"][
                "maximum_timestamp_gap_seconds"
            ]
            for item in plans
        ),
        "event_before_snapshot_count": sum(
            item.touch_timestamp < item.selected_snapshot_at for item in events
        ),
        "non_first_touch_flag_count": sum(not item.first_touch for item in events),
        "signal_enabled_count": sum(item.signal_allowed for item in events),
        "order_submission_enabled_count": sum(item.order_submission_allowed for item in events),
    }
    return {
        "violations": violations,
        "integrity_pass": all(value == 0 for value in violations.values()),
        "candidate_validation_v2_modified": False,
        "protocol_v1_modified": False,
        "feature_032_reports_modified": False,
        "exact_contract_basis_available": False,
        "research_only": True,
        "signal_allowed": False,
        "order_submission_allowed": False,
    }


def _promotion_gates(
    strict_primary: list[EventOutcome],
    integrity: dict[str, Any],
) -> dict[str, Any]:
    tier2 = [item for item in strict_primary if item.tier == 2]
    tier2_after_cost = [
        replace(
            item,
            cost_points=1.0,
            net_points=item.gross_points - 1.0 if item.gross_points is not None else None,
        )
        for item in tier2
    ]
    split = chronological_split(tier2)
    summary = summarize_outcomes(tier2_after_cost)
    side_groups = grouped_summaries(tier2_after_cost, lambda item: item.side.value)
    checks = {
        "at_least_30_local_events": len(tier2) >= 30,
        "at_least_10_holdout_events": (split["holdout"]["event_count"] >= 10),
        "at_least_10_independent_sessions": (summary["independent_session_count"] >= 10),
        "zero_integrity_violations": integrity["integrity_pass"],
        "positive_median_after_costs": (
            summary["median_net_points"] is not None and summary["median_net_points"] > 0
        ),
        "favorable_confidence_evidence": (
            summary["session_clustered_expectancy_ci95"] is not None
            and summary["session_clustered_expectancy_ci95"][0] > 0
        ),
        "stable_upper_and_lower_sides": (
            len(side_groups) == 2
            and all(
                item["net_expectancy_points"] is not None and item["net_expectancy_points"] > 0
                for item in side_groups
            )
        ),
    }
    return {
        "status": "shadow_only" if not all(checks.values()) else "shadow_review_eligible",
        "checks": checks,
        "tier2_summary": summary,
        "live_execution_allowed": False,
        "paper_order_submission_allowed": False,
    }


def _context_report(
    events: list[FirstTouchEvent],
    outcomes: list[EventOutcome],
) -> dict[str, Any]:
    outcome_by_id = {
        item.event_id: item for item in outcomes if item.label == "LABEL_B_TRADABLE_FIRST_PASSAGE"
    }
    rows = [
        {
            "event_id": item.event_id,
            "session_date": item.session_date.isoformat(),
            "tier": item.tier,
            "side": item.side.value,
            "anchor": item.anchor.value,
            "mapping_mode": item.mapping_mode.value,
            **item.context,
        }
        for item in events
    ]
    filters = {
        "strict_first_touch_baseline": lambda event: True,
        "oi_confluence": lambda event: bool(
            event.context.get("oi_hard_feature_allowed")
            and event.context.get("oi_percentile") is not None
            and event.context["oi_percentile"] >= 0.8
            and event.context.get("wall_distance_points") is not None
            and event.context["wall_distance_points"] <= event.one_sd_points * 0.25
        ),
        "iv_non_expansion": lambda event: (
            event.context.get("iv_change_since_plan") is not None
            and event.context["iv_change_since_plan"] <= 0
        ),
        "rejection_confirmation": lambda event: (
            event.context.get("acceptance_rejection_state") == "closed_inside"
        ),
        "flow_through_exclusion": lambda event: (
            event.context.get("acceptance_rejection_state") != "accepted_beyond"
        ),
    }
    comparisons = []
    for name, predicate in filters.items():
        selected = [
            outcome_by_id[item.event_id]
            for item in events
            if predicate(item) and item.event_id in outcome_by_id
        ]
        comparisons.append(
            {
                "variant": name,
                "mandatory_in_shadow_v1": False,
                "summary": summarize_outcomes(selected),
            }
        )
    return {
        "events": rows,
        "descriptive_matched_comparisons": comparisons,
        "confirmation_entry_rule": (
            "Any future executable confirmation variant must enter on the next "
            "closed bar; this v1 report does not simulate a confirmation entry."
        ),
        "hard_filter_promoted": False,
        "research_only": True,
        "signal_allowed": False,
        "order_submission_allowed": False,
    }


def _outcomes_for_events(
    outcomes: list[EventOutcome],
    events: list[FirstTouchEvent],
) -> list[EventOutcome]:
    event_ids = {item.event_id for item in events}
    return [item for item in outcomes if item.event_id in event_ids]


def _bars_by_date(
    bars: list[XauPriceBar],
    timezone: str,
) -> dict[date, list[XauPriceBar]]:
    zone = ZoneInfo(timezone)
    grouped: dict[date, list[XauPriceBar]] = defaultdict(list)
    for item in bars:
        grouped[item.timestamp.astimezone(zone).date()].append(item)
    return grouped


def _file_record(path: Path) -> dict[str, Any]:
    body = path.read_bytes()
    return {
        "path": path.as_posix(),
        "bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
    }


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )


def _review_handoff(
    *,
    run_dir: Path,
    registry: dict[str, Any],
    metadata: dict[str, Any],
    selections: list[SnapshotSelection],
    events: list[FirstTouchEvent],
    published: dict[str, Any],
    strict: dict[str, Any],
    barrier: dict[str, Any],
    dte: dict[str, Any],
    time_anchor: dict[str, Any],
    mapping: dict[str, Any],
    promotion: dict[str, Any],
    integrity: dict[str, Any],
    shadow: dict[str, Any],
) -> str:
    dte_values = [
        item.snapshot.source_dte
        for item in selections
        if item.anchor == TimeAnchor.T0_DTE_080 and item.strict_dte_eligible
    ]
    lines = [
        "# XAU Vol2Vol First-Touch Replication Review",
        "",
        "Research-only replication. No signal or order submission is allowed.",
        "",
        "## External Prior",
        "",
    ]
    for tier, prior in registry["external_prior"]["tiers"].items():
        lines.append(
            f"- {tier}SD: {prior['reversals']}/{prior['touches']} "
            f"reported reversals ({prior['reported_rate']:.2%})."
        )
    lines.extend(
        [
            "",
            "## Local Coverage",
            "",
            f"- Eligible completed sessions: {metadata['eligible_session_count']}",
            f"- Strict primary first-touch events: {metadata['primary_event_count']}",
            f"- Selected DTE count: {len(dte_values)}",
            f"- Selected DTE minimum/median/maximum: {_distribution(dte_values)}",
            "",
            "## Primary T0 Distance-Reanchored Results",
            "",
            "| Tier | Touches | Published Label A rate | Strict TP25/SL25 rate | Difference |",
            "|---:|---:|---:|---:|---:|",
        ]
    )
    published_by_tier = {item["group"]: item for item in published["by_tier"]}
    strict_by_tier = {item["group"]: item for item in strict["by_tier"]}
    for tier in ("1", "2", "3"):
        label_a = published_by_tier.get(tier, {})
        label_b = strict_by_tier.get(tier, {})
        a_rate = label_a.get("event_success_rate")
        b_rate = label_b.get("event_success_rate")
        difference = a_rate - b_rate if a_rate is not None and b_rate is not None else None
        lines.append(
            f"| {tier} | {label_a.get('event_count', 0)} | {_percent(a_rate)} | "
            f"{_percent(b_rate)} | {_percent(difference)} |"
        )
    tier2 = strict_by_tier.get("2", {})
    lines.extend(
        [
            "",
            "## Risk And Validation",
            "",
            f"- Strict tier-2 maximum drawdown: "
            f"{tier2.get('maximum_drawdown_points', 'n/a')} points.",
            f"- Strict tier-2 maximum consecutive losses: "
            f"{tier2.get('maximum_consecutive_losses', 'n/a')}.",
            f"- Holdout tier-2 events: "
            f"{strict['chronological_development_holdout_by_tier']['2']['holdout']['event_count']}.",
            f"- Integrity pass: {integrity['integrity_pass']}.",
            f"- Promotion status: **{promotion['status']}**.",
            "- Published Label A is not described as a tradable win rate.",
            "- Calendar DTE, trading-session DTE, and expiry remain null when the "
            "retained source does not expose them; raw source DTE is the primary field.",
            "",
            "## Sensitivities",
            "",
            f"- Barrier trials: {len(barrier['trials'])}; automatic best selection: no.",
            f"- DTE buckets: {len(dte['buckets'])}; post-hoc thresholds: no.",
            f"- Time-anchor groups: {len(time_anchor['groups'])}; results are not pooled.",
            f"- Mapping groups: {len(mapping['groups'])}; distance mapping is not a "
            "validated exact-contract basis.",
            "",
            "### Tier-2 Barrier Sensitivity",
            "",
            "| Trial | Events | TP-first rate | Net expectancy |",
            "|---|---:|---:|---:|",
        ]
    )
    for trial in barrier["trials"]:
        tier2_trial = next(
            (item for item in trial["by_tier"] if item["group"] == "2"),
            None,
        )
        if tier2_trial:
            lines.append(
                f"| {trial['trial']['id']} | {tier2_trial['event_count']} | "
                f"{_percent(tier2_trial['event_success_rate'])} | "
                f"{_number(tier2_trial['net_expectancy_points'])} |"
            )
    lines.extend(
        [
            "",
            "### Tier-2 DTE Sensitivity",
            "",
            "| DTE bucket | Events | TP-first rate | Net expectancy |",
            "|---|---:|---:|---:|",
        ]
    )
    for bucket in dte["buckets"]:
        tier2_bucket = next(
            (item for item in bucket["by_tier"] if item["group"] == "2"),
            None,
        )
        if tier2_bucket:
            lines.append(
                f"| {bucket['bucket']['id']} | {tier2_bucket['event_count']} | "
                f"{_percent(tier2_bucket['event_success_rate'])} | "
                f"{_number(tier2_bucket['net_expectancy_points'])} |"
            )
    lines.extend(
        [
            "",
            "### Tier-2 Time And Mapping Sensitivity",
            "",
            "| Dimension | Group | Events | TP-first rate | Net expectancy |",
            "|---|---|---:|---:|---:|",
        ]
    )
    for dimension, report in (("anchor", time_anchor), ("mapping", mapping)):
        for item in report["groups"]:
            if item["group"].endswith(":tier2"):
                lines.append(
                    f"| {dimension} | {item['group']} | {item['event_count']} | "
                    f"{_percent(item['event_success_rate'])} | "
                    f"{_number(item['net_expectancy_points'])} |"
                )
    lines.extend(
        [
            "",
            "### Tier-2 Cost Sensitivity",
            "",
            "| Cost points | Events | Net expectancy |",
            "|---:|---:|---:|",
        ]
    )
    for cost, summaries in strict["cost_sensitivity"].items():
        tier2_cost = next(
            (item for item in summaries if item["group"] == "2"),
            None,
        )
        if tier2_cost:
            lines.append(
                f"| {cost} | {tier2_cost['event_count']} | "
                f"{_number(tier2_cost['net_expectancy_points'])} |"
            )
    lines.extend(
        [
            "",
            "## Current Shadow Plan",
            "",
            f"- Session date: {shadow['session_date']}",
            f"- State: {shadow['session']['state']}",
            f"- Reason: {shadow['reason']}",
            "- Broker orders: none.",
            "",
            "## Promotion Gates",
            "",
        ]
    )
    for check, passed in promotion["checks"].items():
        lines.append(f"- {check}: `{passed}`")
    lines.extend(
        [
            "",
            "## Artifacts",
            "",
        ]
    )
    for path in sorted(run_dir.iterdir()):
        lines.append(f"- `{path.as_posix()}`")
    return "\n".join(lines) + "\n"


def _distribution(values: list[float]) -> str:
    if not values:
        return "n/a"
    ordered = sorted(values)
    middle = ordered[len(ordered) // 2]
    return f"{ordered[0]:.3f} / {middle:.3f} / {ordered[-1]:.3f}"


def _percent(value: float | None) -> str:
    return f"{value:.2%}" if value is not None else "n/a"


def _number(value: float | None) -> str:
    return f"{value:.3f}" if value is not None else "n/a"
