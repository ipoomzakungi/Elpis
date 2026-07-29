from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from src.models.xau_ft2_candidate import XauFt2AcknowledgementRequest
from src.xau_first_touch_study.models import (
    CountingMode,
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
from src.xau_ft2_candidate.coverage_audit import (
    CoverageAuditConfig,
    run_coverage_audit,
)
from src.xau_ft2_candidate.executable_fill import (
    ExecutableEvent,
    summarize_fill_sensitivity,
)
from src.xau_ft2_candidate.integrity_policy import (
    load_integrity_policy,
    synchronized_reference_accepted,
)
from src.xau_ft2_candidate.policy import load_candidate_policy
from src.xau_tiered_manual_signal.tiers import (
    build_tier_events,
    evaluate_tier_barrier,
)
from src.xau_vol2vol_history_walkforward.data_lake import daily_raw_path
from src.xau_vol2vol_history_walkforward.walkforward_simulator import (
    load_traded_bars_folder,
)


@dataclass(frozen=True)
class Ft2IntegrityRunConfig:
    vol2vol_root: Path
    price_bars_folder: Path
    candidate_policy_path: Path
    integrity_policy_path: Path
    output_root: Path
    supersedes_run_dir: Path
    session_date_from: date
    session_date_to: date
    as_of_date: date
    timezone: str = "Asia/Bangkok"


def run_integrity_study(config: Ft2IntegrityRunConfig) -> Path:
    candidate = load_candidate_policy(config.candidate_policy_path)
    engine = load_integrity_policy(
        config.integrity_policy_path,
        candidate_policy_path=config.candidate_policy_path,
    )
    prior = _load_prior(config.supersedes_run_dir)
    run_id = f"xau_ft2_integrity_{datetime.now().strftime('%Y%m%dT%H%M%S%f')}"
    run_dir = config.output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    audit = run_coverage_audit(
        CoverageAuditConfig(
            vol2vol_root=config.vol2vol_root,
            price_bars_folder=config.price_bars_folder,
            session_date_from=config.session_date_from,
            session_date_to=config.session_date_to,
            as_of_date=config.as_of_date,
            target_dte=candidate["canonical_plan"]["source_dte_target"],
            minimum_dte=candidate["canonical_plan"]["source_dte_minimum"],
            maximum_dte=candidate["canonical_plan"]["source_dte_maximum"],
            timezone=config.timezone,
        )
    )
    all_bars = load_traded_bars_folder(
        config.price_bars_folder,
        timezone=config.timezone,
    ).bars
    bars_by_date = _bars_by_date(all_bars, config.timezone)
    maximum_gap = engine["mapping"]["maximum_source_gap_seconds"]
    audit_by_date = {item["session_date"]: item for item in audit["rows"]}
    corrected_plans = []
    events = []
    rejected = []
    current = config.session_date_from
    while current <= config.session_date_to:
        if not audit_by_date[current.isoformat()]["parser_dte_qualified"]:
            current += timedelta(days=1)
            continue
        raw_path = daily_raw_path(config.vol2vol_root, current)
        if not raw_path.exists():
            current += timedelta(days=1)
            continue
        try:
            selection = select_snapshot(
                load_source_snapshots(raw_path, current),
                anchor=TimeAnchor.T0_DTE_080,
                session_date=current,
                timezone=config.timezone,
                target_dte=candidate["canonical_plan"]["source_dte_target"],
                dte_tolerance=candidate["canonical_plan"]["source_dte_tolerance"],
            )
        except ValueError as exc:
            rejected.append(
                {
                    "source_session_date": current.isoformat(),
                    "reason": str(exc),
                }
            )
            current += timedelta(days=1)
            continue
        if selection is None or not selection.strict_dte_eligible:
            current += timedelta(days=1)
            continue
        plan = map_selection(
            selection,
            all_bars,
            mapping_mode=MappingMode.DISTANCE_REANCHORED,
            maximum_gap_seconds=maximum_gap,
            bar_interval_minutes=engine["mapping"]["bar_interval_minutes"],
        )
        if plan is None:
            rejected.append(
                {
                    "source_session_date": current.isoformat(),
                    "reason": "XAU_REFERENCE_UNAVAILABLE",
                }
            )
            current += timedelta(days=1)
            continue
        if not synchronized_reference_accepted(
            plan,
            maximum_gap_seconds=maximum_gap,
        ):
            rejected.append(
                {
                    "source_session_date": current.isoformat(),
                    "plan_id": plan.plan_id,
                    "selected_xau_timestamp": plan.planning_xau_timestamp.isoformat(),
                    "source_gap_seconds": plan.source_gap_seconds,
                    "reason": "XAU_REFERENCE_UNAVAILABLE_STALE",
                }
            )
            current += timedelta(days=1)
            continue
        trading_date = selection.activation_at.astimezone(ZoneInfo(config.timezone)).date()
        plan_record = {
            **as_record(plan),
            "plan_id": f"{plan.plan_id}_{engine['engine_revision']}",
            "source_plan_key": plan.plan_id,
            "source_session_date": current.isoformat(),
            "snapshot_timestamp_utc": selection.snapshot.observed_at.isoformat(),
            "activation_timestamp_bangkok": selection.activation_at.astimezone(
                ZoneInfo(config.timezone)
            ).isoformat(),
            "trading_date_bangkok": trading_date.isoformat(),
            "selected_xau_timestamp": plan.planning_xau_timestamp.isoformat(),
            "source_gap_seconds": plan.source_gap_seconds,
            "engine_revision": engine["engine_revision"],
            "engine_hash": engine["engine_hash"],
            "candidate_hash": candidate["candidate_hash"],
            "reference_trade_levels": _reference_trade_levels(
                plan.mapped_levels[2][0],
                plan.mapped_levels[2][1],
                candidate["canonical_plan"]["take_profit_points"],
                candidate["canonical_plan"]["stop_loss_points"],
            ),
        }
        corrected_plans.append(plan_record)
        events.extend(
            item
            for item in build_tier_events(
                plan,
                bars_by_date.get(trading_date.isoformat(), []),
                counting_mode=CountingMode.AGGREGATED,
            )
            if float(item.tier) == 2.0
        )
        current += timedelta(days=1)

    plan_by_source_key = {item["source_plan_key"]: item for item in corrected_plans}
    corrected_events = [
        {
            **as_record(event),
            "plan_id": plan_by_source_key[event.plan_id]["plan_id"],
            "source_plan_key": event.plan_id,
            "source_session_date": event.session_date.isoformat(),
            "trading_date_bangkok": plan_by_source_key[event.plan_id]["trading_date_bangkok"],
            "engine_revision": engine["engine_revision"],
            "candidate_hash": candidate["candidate_hash"],
        }
        for event in events
    ]
    outcomes = [
        as_record(
            evaluate_tier_barrier(
                event,
                bars_by_date.get(
                    plan_by_source_key[event.plan_id]["trading_date_bangkok"],
                    [],
                ),
                tp_points=candidate["canonical_plan"]["take_profit_points"],
                sl_points=candidate["canonical_plan"]["stop_loss_points"],
                cost_points=0,
            )
        )
        for event in events
    ]
    executable = summarize_fill_sensitivity(
        [
            ExecutableEvent(
                event_id=event.event_id,
                side=event.side.value,
                entry=event.boundary,
                touch_timestamp=event.touch_timestamp,
            )
            for event in events
        ],
        bars_by_date,
        {
            event.event_id: plan_by_source_key[event.plan_id]["trading_date_bangkok"]
            for event in events
        },
        spreads=engine["execution"]["synthetic_spread_points"],
        tp_points=candidate["canonical_plan"]["take_profit_points"],
        sl_points=candidate["canonical_plan"]["stop_loss_points"],
    )
    comparison = _comparison(prior, corrected_plans, corrected_events, outcomes)
    stale = _stale_audit(prior, corrected_plans, maximum_gap)
    sample = _sample_report(
        audit=audit,
        plans=corrected_plans,
        events=corrected_events,
        outcomes=outcomes,
        comparison=comparison,
        candidate=candidate,
    )
    integrity = _integrity_report(
        corrected_plans,
        corrected_events,
        rejected,
        stale,
        candidate,
        engine,
    )
    alignment = _alignment_audit(
        corrected_plans,
        rejected,
        stale,
        comparison,
        maximum_gap,
    )
    metadata = {
        "run_id": run_id,
        "engine_revision": engine["engine_revision"],
        "engine_hash": engine["engine_hash"],
        "candidate_id": candidate["candidate_id"],
        "candidate_hash": candidate["candidate_hash"],
        "supersedes_run_id": prior["metadata"]["run_id"],
        "historical_result_changed": comparison["historical_result_changed"],
        "invalidated_plan_ids": stale["invalidated_plan_ids"],
        "corrected_plan_ids": comparison["corrected_plan_ids"],
        "session_date_from": config.session_date_from.isoformat(),
        "session_date_to": config.session_date_to.isoformat(),
        "as_of_date": config.as_of_date.isoformat(),
        "research_only": True,
        "signal_allowed": False,
        "order_submission_allowed": False,
    }
    artifacts = {
        "metadata.json": metadata,
        "trading_date_alignment_audit.json": alignment,
        "stale_plan_audit.json": stale,
        "corrected_frozen_plans.json": corrected_plans,
        "corrected_events.json": corrected_events,
        "corrected_outcomes.json": outcomes,
        "executable_fill_sensitivity.json": executable,
        "manual_execution_schema.json": {
            "schema": XauFt2AcknowledgementRequest.model_json_schema(),
            "reference_entry_and_actual_fill_are_distinct": True,
            "manual_outcome_requires_actual_fill": True,
            "research_only": True,
            "signal_allowed": False,
            "order_submission_allowed": False,
        },
        "sample_report.json": sample,
        "integrity_report.json": integrity,
    }
    for name, payload in artifacts.items():
        _write_json(run_dir / name, payload)
    (run_dir / "trading_date_alignment_audit.md").write_text(
        _alignment_markdown(alignment),
        encoding="utf-8",
    )
    (run_dir / "review_handoff.md").write_text(
        _review_handoff(metadata, sample, stale, executable, integrity),
        encoding="utf-8",
    )
    return run_dir


def _load_prior(run_dir: Path) -> dict[str, Any]:
    required = {
        "metadata": "metadata.json",
        "plans": "frozen_plans.json",
        "events": "ft2_raw_events.json",
        "outcomes": "ft2_raw_outcomes.json",
        "sample": "sample_report.json",
    }
    result = {}
    for key, name in required.items():
        path = run_dir / name
        if not path.exists():
            raise FileNotFoundError(f"Superseded evidence is missing {name}: {run_dir}")
        result[key] = json.loads(path.read_text(encoding="utf-8"))
    return result


def _stale_audit(
    prior: dict[str, Any],
    corrected: list[dict[str, Any]],
    maximum_gap: float,
) -> dict[str, Any]:
    stale = [
        item for item in prior["plans"] if float(item.get("source_gap_seconds") or 0) > maximum_gap
    ]
    corrected_by_source = {item["source_session_date"]: item for item in corrected}
    return {
        "maximum_source_gap_seconds": maximum_gap,
        "stale_plan_count": len(stale),
        "invalidated_plan_ids": [item["plan_id"] for item in stale],
        "stale_plans": [
            {
                "plan_id": item["plan_id"],
                "source_session_date": item["session_date"],
                "prior_selected_xau_timestamp": item["planning_xau_timestamp"],
                "prior_source_gap_seconds": item["source_gap_seconds"],
                "corrected_plan_id": (
                    corrected_by_source[item["session_date"]]["plan_id"]
                    if item["session_date"] in corrected_by_source
                    else None
                ),
            }
            for item in stale
        ],
        "stale_plans_enter_corrected_denominator": False,
        "research_only": True,
        "signal_allowed": False,
        "order_submission_allowed": False,
    }


def _comparison(
    prior: dict[str, Any],
    plans: list[dict[str, Any]],
    events: list[dict[str, Any]],
    outcomes: list[dict[str, Any]],
) -> dict[str, Any]:
    prior_plan_by_source = {item["session_date"]: item for item in prior["plans"]}
    corrected_ids = [
        item["plan_id"]
        for item in plans
        if (
            item["source_session_date"] not in prior_plan_by_source
            or item["selected_xau_timestamp"]
            != prior_plan_by_source[item["source_session_date"]]["planning_xau_timestamp"]
        )
    ]
    counts = _outcome_counts(outcomes)
    old = prior["sample"]
    july5 = next(
        (item for item in plans if item["source_session_date"] == "2026-07-05"),
        None,
    )
    changed = (
        len(plans) != old["eligible_strict_plans"]
        or len(events) != old["first_touch_event_count"]
        or counts["tp_first"] != old["tp_first"]
        or counts["sl_first"] != old["sl_first"]
        or counts["same_bar_ambiguous"] != old["ambiguous"]
    )
    return {
        "prior_mapped_plans": old["eligible_strict_plans"],
        "corrected_mapped_plans": len(plans),
        "prior_events": old["first_touch_event_count"],
        "corrected_events": len(events),
        "prior_tp_first": old["tp_first"],
        "corrected_tp_first": counts["tp_first"],
        "prior_sl_first": old["sl_first"],
        "corrected_sl_first": counts["sl_first"],
        "prior_ambiguous": old["ambiguous"],
        "corrected_ambiguous": counts["same_bar_ambiguous"],
        "prior_touch_rate": old["touch_rate"],
        "corrected_touch_rate": len(events) / len(plans) if plans else None,
        "july_5_recovered": july5 is not None,
        "july_5_trading_date_bangkok": (july5["trading_date_bangkok"] if july5 else None),
        "corrected_plan_ids": corrected_ids,
        "historical_result_changed": changed,
        "original_three_events_remain_valid": {
            "2026-06-23",
            "2026-06-24",
            "2026-06-29",
        }.issubset({item["source_session_date"] for item in events}),
    }


def _sample_report(
    *,
    audit: dict[str, Any],
    plans: list[dict[str, Any]],
    events: list[dict[str, Any]],
    outcomes: list[dict[str, Any]],
    comparison: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    counts = _outcome_counts(outcomes)
    lower = sum(item["side"] == EventSide.LOWER_LONG.value for item in events)
    upper = sum(item["side"] == EventSide.UPPER_SHORT.value for item in events)
    return {
        "candidate_id": candidate["candidate_id"],
        "candidate_hash": candidate["candidate_hash"],
        "completed_source_sessions": audit["completed_sessions"],
        "eligible_strict_plans": len(plans),
        "first_touch_event_count": len(events),
        "touch_rate": len(events) / len(plans) if plans else None,
        "lower_long_events": lower,
        "upper_short_events": upper,
        **counts,
        "comparison": comparison,
        "promotion_status": "BLOCKED_INSUFFICIENT_EVIDENCE",
        "research_only": True,
        "signal_allowed": False,
        "order_submission_allowed": False,
    }


def _integrity_report(
    plans: list[dict[str, Any]],
    events: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
    stale: dict[str, Any],
    candidate: dict[str, Any],
    engine: dict[str, Any],
) -> dict[str, Any]:
    maximum_gap = engine["mapping"]["maximum_source_gap_seconds"]
    checks = {
        "candidate_hash_unchanged": engine["candidate_hash"] == candidate["candidate_hash"],
        "source_and_trading_dates_persisted": all(
            item.get("source_session_date") and item.get("trading_date_bangkok") for item in plans
        ),
        "all_xau_references_fully_closed": all(
            item["closed_bar_status"] == "closed" for item in plans
        ),
        "all_accepted_source_gaps_within_limit": all(
            item["source_gap_seconds"] <= maximum_gap for item in plans
        ),
        "no_stale_plan_in_denominator": not stale["stale_plans_enter_corrected_denominator"],
        "one_plan_per_source_session": len(plans)
        == len({item["source_session_date"] for item in plans}),
        "one_event_per_source_session": len(events)
        == len({item["source_session_date"] for item in events}),
        "all_events_literal_2sd": all(item["tier"] == 2 for item in events),
        "research_only": all(
            item["research_only"]
            and not item["signal_allowed"]
            and not item["order_submission_allowed"]
            for item in plans + events
        ),
        "no_execution_features_enabled": all(
            not engine["guardrails"][key]
            for key in (
                "position_sizing_allowed",
                "averaging_allowed",
                "recovery_allowed",
                "martingale_allowed",
                "automatic_execution_allowed",
                "signal_allowed",
                "order_submission_allowed",
            )
        ),
    }
    return {
        "engine_revision": engine["engine_revision"],
        "engine_hash": engine["engine_hash"],
        "candidate_hash": candidate["candidate_hash"],
        "checks": checks,
        "violation_count": sum(not item for item in checks.values()),
        "rejected_reference_count": len(rejected),
        "rejected_references": rejected,
        "research_only": True,
        "signal_allowed": False,
        "order_submission_allowed": False,
    }


def _alignment_audit(
    plans: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
    stale: dict[str, Any],
    comparison: dict[str, Any],
    maximum_gap: float,
) -> dict[str, Any]:
    gaps = [float(item["source_gap_seconds"]) for item in plans]
    next_day = [
        item for item in plans if item["source_session_date"] != item["trading_date_bangkok"]
    ]
    return {
        "definition": (
            "trading_date_bangkok is the Bangkok date containing the activation "
            "and monitoring window; source_session_date remains immutable metadata"
        ),
        "maximum_allowed_source_gap_seconds": maximum_gap,
        "maximum_accepted_source_gap_seconds": max(gaps) if gaps else None,
        "maximum_mapping_error_seconds": max(gaps) if gaps else None,
        "next_calendar_day_plan_count": len(next_day),
        "next_calendar_day_plans": [
            {
                "plan_id": item["plan_id"],
                "source_session_date": item["source_session_date"],
                "activation_timestamp_bangkok": item["activation_timestamp_bangkok"],
                "trading_date_bangkok": item["trading_date_bangkok"],
                "selected_xau_timestamp": item["selected_xau_timestamp"],
                "source_gap_seconds": item["source_gap_seconds"],
            }
            for item in next_day
        ],
        "stale_plan_count": stale["stale_plan_count"],
        "rejected_references": rejected,
        "comparison": comparison,
        "research_only": True,
        "signal_allowed": False,
        "order_submission_allowed": False,
    }


def _outcome_counts(outcomes: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "tp_first": sum(item["status"] == "tp_first" for item in outcomes),
        "sl_first": sum(item["status"] == "sl_first" for item in outcomes),
        "same_bar_ambiguous": sum(item["status"] == "same_bar_ambiguous" for item in outcomes),
        "session_end_unresolved": sum(
            item["status"] == "session_end_unresolved" for item in outcomes
        ),
    }


def _reference_trade_levels(
    lower: float,
    upper: float,
    take_profit_points: float,
    stop_loss_points: float,
) -> dict[str, dict[str, float]]:
    return {
        "lower_long": {
            "entry": lower,
            "take_profit": lower + take_profit_points,
            "stop_loss": lower - stop_loss_points,
        },
        "upper_short": {
            "entry": upper,
            "take_profit": upper - take_profit_points,
            "stop_loss": upper + stop_loss_points,
        },
    }


def _bars_by_date(bars: list[Any], timezone: str) -> dict[str, list[Any]]:
    zone = ZoneInfo(timezone)
    grouped: dict[str, list[Any]] = {}
    for bar in bars:
        key = bar.timestamp.astimezone(zone).date().isoformat()
        grouped.setdefault(key, []).append(bar)
    return grouped


def _alignment_markdown(report: dict[str, Any]) -> str:
    comparison = report["comparison"]
    return "\n".join(
        [
            "# FT2 Trading-Date Alignment Audit",
            "",
            f"- Prior mapped plans: {comparison['prior_mapped_plans']}",
            f"- Corrected mapped plans: {comparison['corrected_mapped_plans']}",
            f"- Invalidated stale plans: {report['stale_plan_count']}",
            f"- July 5 recovered: {comparison['july_5_recovered']}",
            (
                "- Maximum accepted source gap: "
                f"{report['maximum_accepted_source_gap_seconds']} seconds"
            ),
            "",
            "Source-session labels remain immutable. XAU references and monitoring "
            "windows now follow the actual Bangkok activation timestamp.",
            "",
        ]
    )


def _review_handoff(
    metadata: dict[str, Any],
    sample: dict[str, Any],
    stale: dict[str, Any],
    executable: dict[str, Any],
    integrity: dict[str, Any],
) -> str:
    comparison = sample["comparison"]
    lines = [
        "# FT2_RAW_V1 034D Integrity Review Handoff",
        "",
        "## Frozen Candidate",
        "",
        f"- Candidate hash: `{metadata['candidate_hash']}`",
        f"- Integrity engine: `{metadata['engine_revision']}`",
        "- Candidate rules, DTE band, literal 2SD trigger, TP25/SL25, and "
        "promotion gates are unchanged.",
        "",
        "## Corrected Historical Result",
        "",
        f"- Mapped plans: {comparison['prior_mapped_plans']} -> "
        f"{comparison['corrected_mapped_plans']}",
        f"- Stale plans invalidated: {stale['stale_plan_count']}",
        f"- July 5 recovered: {comparison['july_5_recovered']}",
        f"- Events: {comparison['prior_events']} -> {comparison['corrected_events']}",
        f"- TP/SL/ambiguous: {sample['tp_first']}/{sample['sl_first']}/"
        f"{sample['same_bar_ambiguous']}",
        f"- Touch rate: {_percent(sample['touch_rate'])}",
        f"- Lower/upper: {sample['lower_long_events']}/{sample['upper_short_events']}",
        f"- Original three events remain valid: {comparison['original_three_events_remain_valid']}",
        "",
        "## Executable Fill Sensitivity",
        "",
    ]
    lines.extend(
        (
            f"- Spread {row['spread_points']}: fills "
            f"{row['executable_fill_count']}, TP/SL/ambiguous "
            f"{row['tp_first']}/{row['sl_first']}/"
            f"{row['same_bar_ambiguous']}, not filled "
            f"{row['not_filled_due_to_spread']}"
        )
        for row in executable["rows"]
    )
    lines.extend(
        [
            "",
            "Dukascopy bars are treated as bid. Long entries require synthetic "
            "ask to reach the limit; short entries use bid. Cost subtraction "
            "never creates a fill.",
            "",
            "## Operational Boundary",
            "",
            "- PLAN_READY publishes reference boundaries.",
            "- REFERENCE_ALERT does not create an assumed manual outcome.",
            "- PROVISIONAL_MANUAL_ALERT requires synchronized broker bid/ask.",
            "- Manual outcomes require an acknowledged actual fill.",
            "- No order submission, sizing, recovery, averaging, or martingale path exists.",
            "",
            f"Integrity violations: {integrity['violation_count']}.",
            "Promotion remains blocked because the evidence sample is insufficient.",
            "",
        ]
    )
    return "\n".join(lines)


def _percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2%}"


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
