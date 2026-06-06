"""Transcript identity, multi-live audit, and approved session remap diagnostics.

This module is research-only. It distinguishes exact duplicate transcript
inventory rows from separate same-day live streams, and it keeps market-session
date remaps behind an explicit approval file. It does not fetch data, execute
orders, or turn historical playbook context into same-day guru signal evidence.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Iterable

import polars as pl


FINAL_RECOMMENDATIONS = (
    "APPROVE_SESSION_REMAP_FIRST",
    "MULTI_LIVE_TRANSCRIPTS_CONFIRMED",
    "CLEAN_TRANSCRIPT_SET_READY",
    "REMAP_PENDING_APPROVAL",
    "SAME_DAY_CONTEXT_READY",
    "SAME_DAY_TRADE_RULE_NOT_READY",
    "FETCH_MORE_TRANSCRIPTS_CURRENT_WEEK",
    "FETCH_MISSING_XAU_SPOT_BASIS",
)
FORBIDDEN_REPORT_PHRASES = (
    "profitable",
    "safe to trade",
    "live ready",
    "live-ready",
)
REMAP_OUTPUTS = (
    "current_week_replay_after_approved_remap.csv",
    "transcript_session_availability.csv",
    "same_day_guru_reinterpretation_after_identity.csv",
)


@dataclass(frozen=True)
class TranscriptIdentitySessionRemapResult:
    """Generated frames and recommendation for transcript identity/remap review."""

    transcript_identity_audit: pl.DataFrame
    clean_transcript_set: pl.DataFrame
    transcript_session_availability: pl.DataFrame
    session_remap_suggestions: pl.DataFrame
    session_remap_decisions_template: pl.DataFrame
    current_week_replay_after_approved_remap: pl.DataFrame
    same_day_guru_reinterpretation_after_identity: pl.DataFrame
    final_recommendation: str
    allow_auto_session_remap: bool


def run_transcript_identity_session_remap_layer(
    *,
    output_dir: str | Path = "outputs",
    transcript_source_roots: Iterable[str | Path] | None = None,
    allow_auto_session_remap: bool = False,
) -> TranscriptIdentitySessionRemapResult:
    """Run transcript identity and approved-remap diagnostics."""

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    _ = resolve_transcript_source_roots(transcript_source_roots)
    inputs = load_transcript_identity_inputs(output_root)
    result = build_transcript_identity_session_remap(
        inputs,
        allow_auto_session_remap=allow_auto_session_remap,
    )

    result.transcript_identity_audit.write_csv(output_root / "transcript_identity_audit.csv")
    (output_root / "transcript_identity_audit.md").write_text(
        transcript_identity_audit_markdown(result.transcript_identity_audit),
        encoding="utf-8",
    )
    result.clean_transcript_set.write_csv(output_root / "clean_transcript_set.csv")
    (output_root / "clean_transcript_set.md").write_text(
        clean_transcript_set_markdown(result.clean_transcript_set),
        encoding="utf-8",
    )
    result.transcript_session_availability.write_csv(
        output_root / "transcript_session_availability.csv"
    )
    (output_root / "transcript_session_availability.md").write_text(
        transcript_session_availability_markdown(result.transcript_session_availability),
        encoding="utf-8",
    )
    result.session_remap_suggestions.write_csv(output_root / "session_remap_suggestions.csv")
    result.session_remap_decisions_template.write_csv(
        output_root / "session_remap_decisions_template.csv"
    )
    (output_root / "session_remap_policy.md").write_text(
        session_remap_policy_markdown(
            result.session_remap_suggestions,
            allow_auto_session_remap=allow_auto_session_remap,
        ),
        encoding="utf-8",
    )
    result.current_week_replay_after_approved_remap.write_csv(
        output_root / "current_week_replay_after_approved_remap.csv"
    )
    (output_root / "current_week_replay_after_approved_remap.md").write_text(
        current_week_replay_after_approved_remap_markdown(
            result.current_week_replay_after_approved_remap,
            final_recommendation=result.final_recommendation,
        ),
        encoding="utf-8",
    )
    result.same_day_guru_reinterpretation_after_identity.write_csv(
        output_root / "same_day_guru_reinterpretation_after_identity.csv"
    )
    (output_root / "same_day_guru_reinterpretation_after_identity.md").write_text(
        same_day_guru_reinterpretation_after_identity_markdown(
            result.same_day_guru_reinterpretation_after_identity,
            final_recommendation=result.final_recommendation,
        ),
        encoding="utf-8",
    )
    append_transcript_identity_session_remap_sections(output_root / "research_report.md", result)
    return result


def resolve_transcript_source_roots(
    roots: Iterable[str | Path] | None = None,
) -> tuple[Path, ...]:
    """Resolve transcript roots from caller input or local environment only.

    Resolved paths are intentionally not written to reports.
    """

    configured = [Path(root) for root in (roots or ())]
    for env_name in ("GURU_TRANSCRIPT_SOURCE_ROOTS", "XAU_TRANSCRIPT_SOURCE_ROOTS"):
        env_value = os.getenv(env_name)
        if env_value:
            configured.extend(
                Path(item.strip()) for item in env_value.split(os.pathsep) if item.strip()
            )
    deduped: list[Path] = []
    seen: set[str] = set()
    for root in configured:
        key = root.as_posix().lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(root)
    return tuple(deduped)


def load_transcript_identity_inputs(output_root: Path) -> dict[str, pl.DataFrame]:
    """Load optional input artifacts with empty-frame fallbacks."""

    names = {
        "transcript_corpus_manifest": output_root / "transcript_corpus_manifest.csv",
        "session_calendar_audit": output_root / "session_calendar_audit.csv",
        "same_date_transcript_resolution": output_root / "same_date_transcript_resolution.csv",
        "transcript_manifest_dedup_audit": output_root / "transcript_manifest_dedup_audit.csv",
        "same_day_guru_signal_readiness": output_root / "same_day_guru_signal_readiness.csv",
        "refined_missing_data_action_plan": output_root / "refined_missing_data_action_plan.csv",
        "current_week_replay_resolved": output_root / "current_week_replay_resolved.csv",
        "current_week_cme_guru_replay": output_root / "current_week_cme_guru_replay.csv",
        "current_week_cme_guru_playbook_replay": (
            output_root / "current_week_cme_guru_playbook_replay.csv"
        ),
        "guru_transcript_alignment_debug": output_root / "guru_transcript_alignment_debug.csv",
        "guru_text_interpretation_audit": output_root / "guru_text_interpretation_audit.csv",
        "session_remap_decisions": output_root / "session_remap_decisions.csv",
    }
    return {name: _load_optional(path) for name, path in names.items()}


def build_transcript_identity_session_remap(
    inputs: dict[str, pl.DataFrame],
    *,
    allow_auto_session_remap: bool = False,
) -> TranscriptIdentitySessionRemapResult:
    """Build all transcript identity and approval-gated remap frames."""

    manifest = _frame(inputs, "transcript_corpus_manifest")
    replay = _frame(inputs, "current_week_cme_guru_replay")
    calendar = _frame(inputs, "session_calendar_audit")
    resolved = _frame(inputs, "current_week_replay_resolved")
    readiness = _frame(inputs, "same_day_guru_signal_readiness")
    playbook = _frame(inputs, "current_week_cme_guru_playbook_replay")
    interpretation = _frame(inputs, "guru_text_interpretation_audit")
    decisions = _frame(inputs, "session_remap_decisions")

    identity = build_transcript_identity_audit(manifest)
    clean_set = build_clean_transcript_set(identity)
    availability = build_transcript_session_availability(
        clean_transcript_set=clean_set,
        replay=replay,
        session_calendar=calendar,
        current_week_resolved=resolved,
        playbook_replay=playbook,
    )
    suggestions = build_session_remap_suggestions(
        session_calendar=calendar,
        decisions=decisions,
        allow_auto_session_remap=allow_auto_session_remap,
    )
    decisions_template = build_session_remap_decisions_template(suggestions)
    replay_after = build_current_week_replay_after_approved_remap(
        current_week_resolved=resolved,
        replay=replay,
        suggestions=suggestions,
        transcript_availability=availability,
        playbook_replay=playbook,
    )
    reinterpretation = build_same_day_guru_reinterpretation_after_identity(
        clean_transcript_set=clean_set,
        transcript_availability=availability,
        readiness=readiness,
        interpretation=interpretation,
        playbook_replay=playbook,
        replay=replay,
    )
    final_recommendation = choose_transcript_identity_recommendation(
        suggestions=suggestions,
        clean_transcript_set=clean_set,
        identity=identity,
        reinterpretation=reinterpretation,
    )
    return TranscriptIdentitySessionRemapResult(
        transcript_identity_audit=identity,
        clean_transcript_set=clean_set,
        transcript_session_availability=availability,
        session_remap_suggestions=suggestions,
        session_remap_decisions_template=decisions_template,
        current_week_replay_after_approved_remap=replay_after,
        same_day_guru_reinterpretation_after_identity=reinterpretation,
        final_recommendation=final_recommendation,
        allow_auto_session_remap=allow_auto_session_remap,
    )


def build_transcript_identity_audit(manifest: pl.DataFrame) -> pl.DataFrame:
    """Classify transcript rows without deduplicating by date alone."""

    records: list[dict[str, Any]] = []
    for index, row in enumerate(manifest.to_dicts() if not manifest.is_empty() else []):
        record = _identity_record_from_manifest(row, index)
        records.append(record)
    content_groups = _group_dicts(records, "content_hash")
    day_groups = _group_dicts(records, "detected_transcript_date")
    video_groups = _group_dicts(records, "same_video_group_id")
    classified = [
        _classify_identity_record(record, content_groups, day_groups, video_groups)
        for record in records
    ]
    return _rows_frame(classified, _transcript_identity_schema()).sort("transcript_record_id")


def build_clean_transcript_set(identity: pl.DataFrame) -> pl.DataFrame:
    """Build a clean transcript set while preserving same-day unique live streams."""

    rows = identity.to_dicts() if not identity.is_empty() else []
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = _clean_group_key(row)
        grouped.setdefault(key, []).append(row)
    clean_rows: list[dict[str, Any]] = []
    for index, key in enumerate(sorted(grouped)):
        members = sorted(grouped[key], key=_selection_sort_key)
        selected = members[0]
        clean_id = f"clean_{index + 1:05d}"
        included = "|".join(str(member.get("transcript_record_id")) for member in members)
        for member in members:
            is_selected = member.get("transcript_record_id") == selected.get("transcript_record_id")
            clean_rows.append(
                {
                    "clean_transcript_id": clean_id,
                    "transcript_record_ids_included": included,
                    "selected_record_id": selected.get("transcript_record_id"),
                    "transcript_date": member.get("detected_transcript_date"),
                    "transcript_time": member.get("detected_transcript_start_time")
                    or member.get("detected_publish_time"),
                    "title_hash": member.get("normalized_title_hash"),
                    "content_hash": member.get("content_hash"),
                    "identity_class": member.get("identity_class"),
                    "included_in_clean_set": is_selected,
                    "collapse_reason": "" if is_selected else _collapse_reason(member),
                    "keep_reason": _keep_reason(selected) if is_selected else "",
                }
            )
    return _rows_frame(clean_rows, _clean_transcript_schema()).sort(
        ["clean_transcript_id", "included_in_clean_set"],
        descending=[False, True],
    )


def build_transcript_session_availability(
    *,
    clean_transcript_set: pl.DataFrame,
    replay: pl.DataFrame,
    session_calendar: pl.DataFrame = pl.DataFrame(),
    current_week_resolved: pl.DataFrame = pl.DataFrame(),
    playbook_replay: pl.DataFrame = pl.DataFrame(),
) -> pl.DataFrame:
    """Classify clean transcript availability against current replay dates."""

    clean_rows = [
        row for row in clean_transcript_set.to_dicts() if _bool_value(row.get("included_in_clean_set"))
    ]
    replay_rows = _replay_rows(replay, current_week_resolved, session_calendar)
    playbook_rows = _rows_by_date(playbook_replay, "trade_date")
    market_dates = sorted(
        {
            _date_text(row.get("market_session_date"))
            for row in replay_rows
            if _date_text(row.get("market_session_date"))
        }
    )
    rows: list[dict[str, Any]] = []
    for clean in clean_rows:
        transcript_date = _date_text(clean.get("transcript_date"))
        transcript_time = _time_text(clean.get("transcript_time"))
        publish_timestamp = _timestamp_text(transcript_date, transcript_time)
        for replay_row in replay_rows:
            replay_date = _date_text(replay_row.get("replay_trade_date"))
            market_date = _date_text(replay_row.get("market_session_date")) or replay_date
            relation = _availability_relation(
                transcript_date=transcript_date,
                transcript_time=transcript_time,
                market_session_date=market_date,
                replay_trade_date=replay_date,
            )
            parsed_transcript = _parse_date(transcript_date)
            parsed_market = _parse_date(market_date)
            playbook_available = _playbook_available_for_date(playbook_rows.get(replay_date, {}))
            rows.append(
                {
                    "transcript_date": transcript_date,
                    "transcript_time": transcript_time,
                    "publish_timestamp": publish_timestamp,
                    "market_session_date": market_date,
                    "replay_trade_date": replay_date,
                    "day_of_week": parsed_market.strftime("%A") if parsed_market else "",
                    "is_weekend_transcript": bool(
                        parsed_transcript and parsed_transcript.weekday() >= 5
                    ),
                    "is_weekend_market_date": bool(parsed_market and parsed_market.weekday() >= 5),
                    "nearest_market_session_before": _nearest_market_date(
                        market_date,
                        market_dates,
                        before=True,
                    ),
                    "nearest_market_session_after": _nearest_market_date(
                        market_date,
                        market_dates,
                        before=False,
                    ),
                    "availability_relation": relation,
                    "can_use_as_same_session_input": relation in {"PRE_SESSION", "DURING_SESSION"},
                    "can_use_as_next_session_input": relation == "NEXT_SESSION_PREP",
                    "can_use_as_playbook_context": playbook_available
                    or relation
                    in {
                        "POST_SESSION",
                        "WEEKEND_RECAP",
                        "NEXT_SESSION_PREP",
                        "HISTORICAL_PLAYBOOK_ONLY",
                    },
                    "reason_plain_english": _availability_reason(
                        transcript_date=transcript_date,
                        market_session_date=market_date,
                        relation=relation,
                    ),
                }
            )
    return _rows_frame(rows, _transcript_session_availability_schema()).sort(
        ["replay_trade_date", "transcript_date", "transcript_time"]
    )


def build_session_remap_suggestions(
    *,
    session_calendar: pl.DataFrame,
    decisions: pl.DataFrame = pl.DataFrame(),
    allow_auto_session_remap: bool = False,
) -> pl.DataFrame:
    """Create remap suggestions, pending unless an approval file approves them."""

    decision_status = _remap_decision_status(decisions)
    rows: list[dict[str, Any]] = []
    for row in session_calendar.to_dicts() if not session_calendar.is_empty() else []:
        original = _date_text(row.get("replay_trade_date"))
        target = _suggested_target(row)
        if not original or not target or target == original:
            continue
        status = decision_status.get((original, target), "PENDING")
        if allow_auto_session_remap and status == "PENDING":
            status = "APPROVED"
        confidence = (
            "HIGH"
            if _bool_value(row.get("likely_calendar_date_issue"))
            and _text(row.get("recommended_session_mapping")).startswith("REMAP_TO_")
            else "MEDIUM"
        )
        rows.append(
            {
                "original_replay_date": original,
                "suggested_market_session_date": target,
                "reason": _text(row.get("reason_plain_english"))
                or "Weekend/session calendar diagnostic suggests a remap.",
                "confidence": confidence,
                "affected_outputs": "|".join(REMAP_OUTPUTS),
                "approval_status": status,
                "reviewer_notes": _remap_reviewer_notes(decisions, original, target),
            }
        )
    return _rows_frame(rows, _session_remap_suggestion_schema()).sort("original_replay_date")


def build_session_remap_decisions_template(suggestions: pl.DataFrame) -> pl.DataFrame:
    """Build a reviewer template; it is not treated as approval input."""

    rows = []
    for row in suggestions.to_dicts() if not suggestions.is_empty() else []:
        rows.append(
            {
                "original_replay_date": row.get("original_replay_date"),
                "suggested_market_session_date": row.get("suggested_market_session_date"),
                "reason": row.get("reason"),
                "confidence": row.get("confidence"),
                "affected_outputs": row.get("affected_outputs"),
                "approval_status": "PENDING",
                "reviewer_notes": "",
            }
        )
    return _rows_frame(rows, _session_remap_suggestion_schema()).sort("original_replay_date")


def build_current_week_replay_after_approved_remap(
    *,
    current_week_resolved: pl.DataFrame,
    replay: pl.DataFrame,
    suggestions: pl.DataFrame,
    transcript_availability: pl.DataFrame,
    playbook_replay: pl.DataFrame = pl.DataFrame(),
) -> pl.DataFrame:
    """Apply approved market-session remaps without remapping transcript availability."""

    replay_rows = _replay_rows(replay, current_week_resolved, pl.DataFrame())
    if not replay_rows:
        replay_rows = [
            {
                "replay_trade_date": _date_text(row.get("original_replay_date")),
                "market_session_date": _date_text(row.get("resolved_session_date"))
                or _date_text(row.get("original_replay_date")),
            }
            for row in current_week_resolved.to_dicts()
        ]
    suggestions_by_date = {
        _date_text(row.get("original_replay_date")): row
        for row in suggestions.to_dicts()
        if _date_text(row.get("original_replay_date"))
    }
    resolved_by_date = _rows_by_date(current_week_resolved, "original_replay_date")
    playbook_by_date = _rows_by_date(playbook_replay, "trade_date")
    rows = []
    for replay_row in replay_rows:
        original = _date_text(replay_row.get("replay_trade_date"))
        suggestion = suggestions_by_date.get(original, {})
        approved = _text(suggestion.get("approval_status")).upper() == "APPROVED"
        proposed = _date_text(suggestion.get("suggested_market_session_date"))
        market_date = proposed if approved and proposed else original
        remap_status = (
            "REMAP_APPROVED"
            if approved
            else "REMAP_PENDING_APPROVAL"
            if suggestion
            else "NO_REMAP_SUGGESTED"
        )
        transcript_state = _transcript_state_after_remap(
            transcript_availability=transcript_availability,
            replay_trade_date=original,
            playbook_row=playbook_by_date.get(original, {}),
        )
        previous = resolved_by_date.get(original, {})
        data_state = _data_state_after_remap(previous, remap_status)
        rows.append(
            {
                "original_replay_date": original,
                "market_session_date": market_date,
                "proposed_market_session_date": proposed,
                "approval_status": remap_status,
                "remap_applied": approved,
                "transcript_state": transcript_state,
                "data_state_after_approved_remap": data_state,
                "guru_state": _text(previous.get("guru_state")) or "HISTORICAL_PLAYBOOK_OVERLAY",
                "what_would_change_if_approved": _what_would_change_if_approved(
                    original=original,
                    proposed=proposed,
                    approved=approved,
                ),
                "plain_english_summary": _approved_remap_summary(
                    original=original,
                    market_date=market_date,
                    remap_status=remap_status,
                    transcript_state=transcript_state,
                ),
            }
        )
    return _rows_frame(rows, _replay_after_remap_schema()).sort("original_replay_date")


def build_same_day_guru_reinterpretation_after_identity(
    *,
    clean_transcript_set: pl.DataFrame,
    transcript_availability: pl.DataFrame,
    readiness: pl.DataFrame,
    interpretation: pl.DataFrame = pl.DataFrame(),
    playbook_replay: pl.DataFrame = pl.DataFrame(),
    replay: pl.DataFrame = pl.DataFrame(),
) -> pl.DataFrame:
    """Recount same-day text after identity cleanup without upgrading trade rules."""

    replay_dates = _replay_date_set(replay)
    if not replay_dates and not readiness.is_empty():
        replay_dates = _date_values(readiness, "trade_date")
    clean_rows = [
        row for row in clean_transcript_set.to_dicts() if _bool_value(row.get("included_in_clean_set"))
    ]
    same_day_clean_count = sum(
        1 for row in clean_rows if _date_text(row.get("transcript_date")) in replay_dates
    )
    if not readiness.is_empty():
        context_rows = _sum_int(readiness, "context_rows")
        filter_rows = _sum_int(readiness, "filter_rows")
        market_map_rows = _sum_int(readiness, "market_map_rows")
        trade_rule_rows = _sum_int(readiness, "trade_rule_rows")
        post_event_rows = _sum_int(readiness, "post_event_rows")
    else:
        current_interpretation = [
            row
            for row in interpretation.to_dicts()
            if _date_text(row.get("transcript_date")) in replay_dates
        ]
        context_rows = _count_true(current_interpretation, "usable_as_context")
        filter_rows = _count_true(current_interpretation, "usable_as_filter")
        market_map_rows = _count_true(current_interpretation, "usable_as_market_map")
        trade_rule_rows = _count_true(current_interpretation, "usable_as_trade_rule")
        post_event_rows = _post_event_count(current_interpretation)
    weekend_recap_rows = _availability_relation_count(
        transcript_availability,
        "WEEKEND_RECAP",
    )
    next_session_prep_rows = _availability_relation_count(
        transcript_availability,
        "NEXT_SESSION_PREP",
    )
    playbook_available = (
        not playbook_replay.is_empty()
        and any(_playbook_available_for_date(row) for row in playbook_replay.to_dicts())
    )
    row = {
        "scope": "CURRENT_WEEK_CLEAN_TRANSCRIPTS",
        "clean_transcript_count": sum(1 for row in clean_rows),
        "same_day_clean_transcript_count": same_day_clean_count,
        "context_rows": context_rows,
        "filter_rows": filter_rows,
        "market_map_rows": market_map_rows,
        "trade_rule_rows": trade_rule_rows,
        "post_event_rows": post_event_rows,
        "weekend_recap_rows": weekend_recap_rows,
        "next_session_prep_rows": next_session_prep_rows,
        "historical_playbook_overlay_available": playbook_available,
        "strict_trade_rule_explanation": _strict_trade_rule_explanation(
            context_rows=context_rows,
            filter_rows=filter_rows,
            market_map_rows=market_map_rows,
            trade_rule_rows=trade_rule_rows,
            post_event_rows=post_event_rows,
        ),
    }
    return _rows_frame([row], _same_day_reinterpretation_schema())


def choose_transcript_identity_recommendation(
    *,
    suggestions: pl.DataFrame,
    clean_transcript_set: pl.DataFrame,
    identity: pl.DataFrame,
    reinterpretation: pl.DataFrame,
) -> str:
    """Choose a conservative final recommendation."""

    if _any_status(suggestions, "PENDING"):
        return "APPROVE_SESSION_REMAP_FIRST"
    if _any_status(suggestions, "REJECTED"):
        return "REMAP_PENDING_APPROVAL"
    row = reinterpretation.row(0, named=True) if not reinterpretation.is_empty() else {}
    if int(row.get("trade_rule_rows") or 0) == 0 and any(
        int(row.get(column) or 0) > 0 for column in ("context_rows", "filter_rows", "market_map_rows")
    ):
        return "SAME_DAY_TRADE_RULE_NOT_READY"
    if _any_identity_class(identity, "SAME_DAY_DIFFERENT_LIVE"):
        return "MULTI_LIVE_TRANSCRIPTS_CONFIRMED"
    if not clean_transcript_set.is_empty():
        return "CLEAN_TRANSCRIPT_SET_READY"
    return "FETCH_MORE_TRANSCRIPTS_CURRENT_WEEK"


def transcript_identity_session_remap_report_lines(
    result: TranscriptIdentitySessionRemapResult | None,
) -> list[str]:
    """Return Markdown lines for embedding in the main research report."""

    if result is None:
        return ["Transcript identity/session remap layer was not run."]
    return [
        "## Transcript Identity Audit",
        "",
        f"- Final recommendation: `{result.final_recommendation}`",
        f"- allow_auto_session_remap: `{str(result.allow_auto_session_remap).lower()}`",
        "",
        _frame_markdown(result.transcript_identity_audit),
        "",
        "## Multi-Live vs Duplicate Classification",
        "",
        _frame_markdown(_identity_summary(result.transcript_identity_audit)),
        "",
        "## Clean Transcript Set",
        "",
        _frame_markdown(_clean_set_summary(result.clean_transcript_set)),
        "",
        "## Transcript Availability vs Market Session",
        "",
        _frame_markdown(_availability_summary(result.transcript_session_availability)),
        "",
        "## Session Remap Approval Workflow",
        "",
        _frame_markdown(result.session_remap_suggestions),
        "",
        "## Current-Week Replay After Approved Remap",
        "",
        _frame_markdown(result.current_week_replay_after_approved_remap),
        "",
        "## Same-Day Guru Reinterpretation After Identity Cleanup",
        "",
        _frame_markdown(result.same_day_guru_reinterpretation_after_identity),
    ]


def transcript_identity_audit_markdown(frame: pl.DataFrame) -> str:
    """Render transcript identity audit rows."""

    return _safe_report(
        "\n".join(
            [
                "# Transcript Identity Audit",
                "",
                "Same-date transcript rows are classified by content, video identity, and format; date alone is never used as a duplicate key.",
                "",
                "## Summary",
                "",
                _frame_markdown(_identity_summary(frame)),
                "",
                "## Sample Rows",
                "",
                _frame_markdown(frame),
            ]
        )
    )


def clean_transcript_set_markdown(frame: pl.DataFrame) -> str:
    """Render clean transcript set rows."""

    return _safe_report(
        "\n".join(
            [
                "# Clean Transcript Set",
                "",
                "Exact content duplicates and sidecar formats are collapsed; separate same-day live streams remain separate.",
                "",
                _frame_markdown(_clean_set_summary(frame)),
                "",
                _frame_markdown(frame),
            ]
        )
    )


def transcript_session_availability_markdown(frame: pl.DataFrame) -> str:
    """Render transcript availability classifications."""

    return _safe_report(
        "\n".join(
            [
                "# Transcript Availability vs Market Session",
                "",
                "Weekend transcripts are not treated as Friday predictive inputs unless timestamps prove prior availability.",
                "",
                _frame_markdown(_availability_summary(frame)),
                "",
                _frame_markdown(frame),
            ]
        )
    )


def session_remap_policy_markdown(
    suggestions: pl.DataFrame,
    *,
    allow_auto_session_remap: bool,
) -> str:
    """Render session remap approval policy."""

    return _safe_report(
        "\n".join(
            [
                "# Session Remap Policy",
                "",
                f"- `allow_auto_session_remap`: `{str(allow_auto_session_remap).lower()}`",
                "- Remap suggestions are diagnostic until a reviewed approval file is provided.",
                "- Approved remaps change market-session date only; transcript availability remains separately classified.",
                "- Historical playbook overlay remains separate from same-day transcript evidence.",
                "",
                _frame_markdown(suggestions),
            ]
        )
    )


def current_week_replay_after_approved_remap_markdown(
    frame: pl.DataFrame,
    *,
    final_recommendation: str,
) -> str:
    """Render replay rows after approval-gated remap application."""

    return _safe_report(
        "\n".join(
            [
                "# Current-Week Replay After Approved Remap",
                "",
                f"- Final recommendation: `{final_recommendation}`",
                "- Pending remaps are shown as what-if diagnostics, not applied validation changes.",
                "",
                _frame_markdown(frame),
            ]
        )
    )


def same_day_guru_reinterpretation_after_identity_markdown(
    frame: pl.DataFrame,
    *,
    final_recommendation: str,
) -> str:
    """Render same-day reinterpretation after identity cleanup."""

    return _safe_report(
        "\n".join(
            [
                "# Same-Day Guru Reinterpretation After Identity Cleanup",
                "",
                f"- Final recommendation: `{final_recommendation}`",
                "- Context, filter, market-map, post-event, and strict trade-rule rows are counted separately.",
                "",
                _frame_markdown(frame),
            ]
        )
    )


def append_transcript_identity_session_remap_sections(
    path: Path,
    result: TranscriptIdentitySessionRemapResult,
) -> None:
    """Append or replace identity/remap sections in a generated research report."""

    marker = "\n## Transcript Identity Audit\n"
    section = "\n".join(transcript_identity_session_remap_report_lines(result))
    existing = path.read_text(encoding="utf-8") if path.exists() else "# XAU/USD Vol-OI Research Report\n"
    if marker in existing:
        existing = existing.split(marker, 1)[0].rstrip()
    path.write_text(_safe_report(existing.rstrip() + "\n\n" + section + "\n"), encoding="utf-8")


def _identity_record_from_manifest(row: dict[str, Any], index: int) -> dict[str, Any]:
    transcript_date = _date_text(_first_value(row, ("detected_date", "transcript_date", "date")))
    file_type = _file_type(row)
    source_hash = _hashed_or_existing(_first_value(row, ("source_id_hash", "source_id", "path_hash")))
    file_hash = _hashed_or_existing(_first_value(row, ("file_hash", "source_id_hash", "path_hash")))
    content_hash = _content_hash(row)
    title_hash = _title_hash(row)
    video_hash = _hashed_or_existing(
        _first_value(row, ("detected_video_id", "video_id", "youtube_id", "id"))
    )
    url_hash = _hashed_or_existing(_first_value(row, ("detected_url", "url", "webpage_url")))
    same_video = video_hash or url_hash
    return {
        "transcript_record_id": f"tr_{index + 1:06d}",
        "source_id_hash": source_hash,
        "file_hash": file_hash,
        "content_hash": content_hash,
        "normalized_title_hash": title_hash,
        "detected_video_id_hash": video_hash,
        "detected_url_hash": url_hash,
        "detected_publish_date": _date_text(_first_value(row, ("detected_publish_date", "publish_date"))),
        "detected_publish_time": _time_text(_first_value(row, ("detected_publish_time", "publish_time"))),
        "detected_live_start_time": _time_text(
            _first_value(row, ("detected_live_start_time", "live_start_time", "start_time"))
        ),
        "detected_transcript_date": transcript_date,
        "detected_transcript_start_time": _time_text(
            _first_value(row, ("detected_transcript_start_time", "transcript_start_time"))
        ),
        "detected_transcript_end_time": _time_text(
            _first_value(row, ("detected_transcript_end_time", "transcript_end_time"))
        ),
        "file_type": file_type,
        "same_day_group_id": _stable_hash(transcript_date) if transcript_date else "",
        "same_content_group_id": content_hash,
        "same_video_group_id": same_video,
        "identity_class": "UNKNOWN_NEEDS_REVIEW",
        "duplicate_safe_to_collapse": False,
        "notes": _identity_notes(row),
    }


def _classify_identity_record(
    record: dict[str, Any],
    content_groups: dict[str, list[dict[str, Any]]],
    day_groups: dict[str, list[dict[str, Any]]],
    video_groups: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    row = dict(record)
    content_group = _non_empty_group(content_groups, row.get("content_hash"))
    day_group = _non_empty_group(day_groups, row.get("detected_transcript_date"))
    video_group = _non_empty_group(video_groups, row.get("same_video_group_id"))
    same_video_formats = _is_same_video_multiformat(row, video_group)
    same_day_distinct = _same_day_distinct_content(day_group)
    if row.get("file_type") == "ZIP_ENTRY" and _has_non_zip_same_content(row, content_group):
        identity_class = "ZIP_ENTRY_DUPLICATE"
        collapsible = True
        note = "Zip inventory row has the same content group as an extracted/source transcript."
    elif same_video_formats and row.get("file_type") != _preferred_video_file_type(video_group):
        identity_class = "SIDECAR_FILE"
        collapsible = True
        note = "Same video is represented in another preferred transcript format."
    elif same_video_formats:
        identity_class = "SAME_VIDEO_MULTIPLE_FORMATS"
        collapsible = True
        note = "Same video appears in multiple transcript formats; keep one clean transcript."
    elif _same_content_source_duplicate(row, content_group):
        identity_class = "SAME_CONTENT_DUPLICATE"
        collapsible = True
        note = "Same content hash appears across more than one source transcript row."
    elif same_day_distinct:
        identity_class = "SAME_DAY_DIFFERENT_LIVE"
        collapsible = False
        note = "Same transcript date has multiple distinct content/title/time identities."
    elif not row.get("content_hash") and not row.get("detected_transcript_date"):
        identity_class = "UNKNOWN_NEEDS_REVIEW"
        collapsible = False
        note = "Insufficient identity fields for automatic classification."
    else:
        identity_class = "UNIQUE_TRANSCRIPT"
        collapsible = False
        note = "No duplicate identity evidence beyond date."
    row["identity_class"] = identity_class
    row["duplicate_safe_to_collapse"] = collapsible
    row["notes"] = _join_notes(row.get("notes"), note)
    return row


def _clean_group_key(row: dict[str, Any]) -> str:
    video_group = _text(row.get("same_video_group_id"))
    identity_class = _text(row.get("identity_class"))
    if video_group and identity_class in {"SAME_VIDEO_MULTIPLE_FORMATS", "SIDECAR_FILE"}:
        return f"video:{video_group}"
    content_hash = _text(row.get("content_hash"))
    if content_hash:
        return f"content:{content_hash}"
    return f"record:{row.get('transcript_record_id')}"


def _selection_sort_key(row: dict[str, Any]) -> tuple[int, int, str]:
    file_type_rank = {
        "TXT": 0,
        "JSON": 1,
        "SRT": 2,
        "UNKNOWN": 3,
        "ZIP_ENTRY": 4,
    }.get(_text(row.get("file_type")), 9)
    source_rank = 0 if "source file" in _text(row.get("notes")).lower() else 1
    return (file_type_rank, source_rank, _text(row.get("transcript_record_id")))


def _collapse_reason(row: dict[str, Any]) -> str:
    identity_class = _text(row.get("identity_class"))
    if identity_class == "ZIP_ENTRY_DUPLICATE":
        return "ZIP_ENTRY_DUPLICATE_COLLAPSED"
    if identity_class in {"SAME_VIDEO_MULTIPLE_FORMATS", "SIDECAR_FILE"}:
        return "SAME_VIDEO_MULTIPLE_FORMATS_COLLAPSED"
    if identity_class == "SAME_CONTENT_DUPLICATE":
        return "EXACT_CONTENT_DUPLICATE_COLLAPSED"
    return "DUPLICATE_GROUP_COLLAPSED"


def _keep_reason(row: dict[str, Any]) -> str:
    identity_class = _text(row.get("identity_class"))
    if identity_class == "SAME_DAY_DIFFERENT_LIVE":
        return "Different same-day content is kept as a separate live transcript."
    if identity_class in {"SAME_VIDEO_MULTIPLE_FORMATS", "SIDECAR_FILE"}:
        return "Preferred transcript format selected for the same video."
    if identity_class in {"SAME_CONTENT_DUPLICATE", "ZIP_ENTRY_DUPLICATE"}:
        return "Preferred source transcript selected for duplicate content."
    return "Unique transcript retained."


def _replay_rows(
    replay: pl.DataFrame,
    current_week_resolved: pl.DataFrame,
    session_calendar: pl.DataFrame,
) -> list[dict[str, Any]]:
    dates = _date_values(replay, "trade_date")
    dates.update(_date_values(current_week_resolved, "original_replay_date"))
    dates.update(_date_values(session_calendar, "replay_trade_date"))
    resolved_by_date = _rows_by_date(current_week_resolved, "original_replay_date")
    calendar_by_date = _rows_by_date(session_calendar, "replay_trade_date")
    rows = []
    for trade_date in sorted(dates):
        resolved = resolved_by_date.get(trade_date, {})
        calendar = calendar_by_date.get(trade_date, {})
        market_session_date = (
            _date_text(resolved.get("resolved_session_date"))
            or _date_text(calendar.get("likely_session_date"))
            or trade_date
        )
        rows.append(
            {
                "replay_trade_date": trade_date,
                "market_session_date": market_session_date,
            }
        )
    return rows


def _availability_relation(
    *,
    transcript_date: str,
    transcript_time: str,
    market_session_date: str,
    replay_trade_date: str,
) -> str:
    transcript = _parse_date(transcript_date)
    market = _parse_date(market_session_date)
    replay = _parse_date(replay_trade_date)
    if transcript is None or market is None:
        return "UNKNOWN"
    if transcript.weekday() >= 5:
        previous = _previous_trading_day(transcript)
        next_day = _next_trading_day(transcript)
        if market == previous:
            return "WEEKEND_RECAP"
        if market == next_day:
            return "NEXT_SESSION_PREP"
        if replay and replay.weekday() >= 5 and transcript == replay:
            return "WEEKEND_RECAP"
        return "HISTORICAL_PLAYBOOK_ONLY"
    if transcript < market:
        return "NEXT_SESSION_PREP" if _next_trading_day(transcript) == market else (
            "HISTORICAL_PLAYBOOK_ONLY"
        )
    if transcript > market:
        return "POST_SESSION"
    parsed_time = _parse_time(transcript_time)
    if parsed_time is None:
        return "UNKNOWN"
    if parsed_time < time(4, 0):
        return "PRE_SESSION"
    if parsed_time <= time(21, 0):
        return "DURING_SESSION"
    return "POST_SESSION"


def _availability_reason(
    *,
    transcript_date: str,
    market_session_date: str,
    relation: str,
) -> str:
    if relation == "WEEKEND_RECAP":
        return (
            f"{transcript_date} is after the {market_session_date} market session; treat it as "
            "weekend recap or post-event commentary, not prior same-session input."
        )
    if relation == "NEXT_SESSION_PREP":
        return (
            f"{transcript_date} is before the next market session {market_session_date}; it can "
            "be reviewed as next-session preparation only."
        )
    if relation == "POST_SESSION":
        return (
            f"{transcript_date} is after market session {market_session_date}; it is not a "
            "same-session predictive input."
        )
    if relation in {"PRE_SESSION", "DURING_SESSION"}:
        return (
            f"{transcript_date} appears available during or before market session "
            f"{market_session_date}; review timestamp detail before same-session use."
        )
    if relation == "HISTORICAL_PLAYBOOK_ONLY":
        return (
            f"{transcript_date} is not same-session timing for {market_session_date}; use only "
            "as historical playbook context."
        )
    return "Transcript timing is unknown; do not use as same-session input without manual review."


def _remap_decision_status(decisions: pl.DataFrame) -> dict[tuple[str, str], str]:
    statuses: dict[tuple[str, str], str] = {}
    for row in decisions.to_dicts() if not decisions.is_empty() else []:
        original = _date_text(row.get("original_replay_date"))
        target = _date_text(row.get("suggested_market_session_date"))
        status = _text(row.get("approval_status")).upper()
        if original and target and status in {"APPROVED", "REJECTED", "PENDING"}:
            statuses[(original, target)] = status
    return statuses


def _remap_reviewer_notes(decisions: pl.DataFrame, original: str, target: str) -> str:
    for row in decisions.to_dicts() if not decisions.is_empty() else []:
        if (
            _date_text(row.get("original_replay_date")) == original
            and _date_text(row.get("suggested_market_session_date")) == target
        ):
            return _text(row.get("reviewer_notes"))
    return ""


def _suggested_target(row: dict[str, Any]) -> str:
    mapping = _text(row.get("recommended_session_mapping"))
    match = re.search(r"REMAP_TO_(20\d{2}-\d{2}-\d{2})", mapping)
    if match:
        return match.group(1)
    return _date_text(row.get("likely_session_date"))


def _transcript_state_after_remap(
    *,
    transcript_availability: pl.DataFrame,
    replay_trade_date: str,
    playbook_row: dict[str, Any],
) -> str:
    rows = [
        row
        for row in transcript_availability.to_dicts()
        if _date_text(row.get("replay_trade_date")) == replay_trade_date
    ]
    relations = {_text(row.get("availability_relation")) for row in rows}
    if any(_bool_value(row.get("can_use_as_same_session_input")) for row in rows):
        return "SAME_SESSION_TRANSCRIPT"
    if relations & {"POST_SESSION", "WEEKEND_RECAP"}:
        return "POST_EVENT_TRANSCRIPT"
    if "NEXT_SESSION_PREP" in relations:
        return "NEXT_SESSION_PREP"
    if _playbook_available_for_date(playbook_row):
        return "PLAYBOOK_OVERLAY"
    return "PLAYBOOK_OVERLAY"


def _data_state_after_remap(previous: dict[str, Any], remap_status: str) -> str:
    if remap_status == "REMAP_PENDING_APPROVAL":
        return "REMAP_PENDING_APPROVAL"
    if remap_status == "REMAP_APPROVED":
        return "COMPLETE_FOR_PILOT_AFTER_APPROVED_REMAP"
    return _text(previous.get("data_state")) or "NEEDS_MANUAL_REVIEW"


def _what_would_change_if_approved(*, original: str, proposed: str, approved: bool) -> str:
    if not proposed:
        return "No market-session remap is proposed."
    if approved:
        return f"Market data session date is remapped from {original} to {proposed}."
    return f"Approval would remap market data session date from {original} to {proposed}."


def _approved_remap_summary(
    *,
    original: str,
    market_date: str,
    remap_status: str,
    transcript_state: str,
) -> str:
    return (
        f"{original} uses market session {market_date} with status {remap_status}. "
        f"Transcript state remains separately classified as {transcript_state}."
    )


def _strict_trade_rule_explanation(
    *,
    context_rows: int,
    filter_rows: int,
    market_map_rows: int,
    trade_rule_rows: int,
    post_event_rows: int,
) -> str:
    if trade_rule_rows:
        return "Strict same-day trade-rule candidate rows exist after identity cleanup."
    if context_rows or filter_rows or market_map_rows:
        return "Same-day text remains context/filter/market-map only after identity cleanup."
    if post_event_rows:
        return "Reviewed same-day text is post-event commentary only after identity cleanup."
    return "No reviewed same-day context/filter/market-map/trade-rule rows are available."


def _identity_summary(frame: pl.DataFrame) -> pl.DataFrame:
    if frame.is_empty():
        return _rows_frame([], _identity_summary_schema())
    rows = []
    for identity_class, group in _group_dicts(frame.to_dicts(), "identity_class").items():
        rows.append(
            {
                "identity_class": identity_class,
                "row_count": len(group),
                "safe_to_collapse_rows": sum(
                    1 for row in group if _bool_value(row.get("duplicate_safe_to_collapse"))
                ),
            }
        )
    return _rows_frame(rows, _identity_summary_schema()).sort("identity_class")


def _clean_set_summary(frame: pl.DataFrame) -> pl.DataFrame:
    if frame.is_empty():
        return _rows_frame([], _clean_set_summary_schema())
    rows = [
        {
            "total_rows": frame.height,
            "included_clean_transcripts": _true_count(frame, "included_in_clean_set"),
            "collapsed_rows": frame.height - _true_count(frame, "included_in_clean_set"),
            "unique_transcript_dates": _unique_non_empty(frame, "transcript_date"),
        }
    ]
    return _rows_frame(rows, _clean_set_summary_schema())


def _availability_summary(frame: pl.DataFrame) -> pl.DataFrame:
    if frame.is_empty():
        return _rows_frame([], _availability_summary_schema())
    rows = []
    for relation, group in _group_dicts(frame.to_dicts(), "availability_relation").items():
        rows.append(
            {
                "availability_relation": relation,
                "row_count": len(group),
                "same_session_input_rows": sum(
                    1 for row in group if _bool_value(row.get("can_use_as_same_session_input"))
                ),
                "next_session_input_rows": sum(
                    1 for row in group if _bool_value(row.get("can_use_as_next_session_input"))
                ),
            }
        )
    return _rows_frame(rows, _availability_summary_schema()).sort("availability_relation")


def _content_hash(row: dict[str, Any]) -> str:
    for column in ("content_hash", "duplicate_group", "normalized_content_hash"):
        value = _text(row.get(column))
        if value:
            return _hashed_or_existing(value)
    text = _text(_first_value(row, ("clean_text", "transcript_text", "content")))
    if text:
        return _stable_hash(text)
    return _hashed_or_existing(_first_value(row, ("source_id_hash", "file_hash")))


def _title_hash(row: dict[str, Any]) -> str:
    title = _text(_first_value(row, ("normalized_title", "detected_title", "title", "file_name")))
    if not title:
        return ""
    return _stable_hash(re.sub(r"\s+", " ", title.lower()).strip())


def _file_type(row: dict[str, Any]) -> str:
    notes = _text(row.get("notes")).lower()
    file_text = " ".join(_text(row.get(column)).lower() for column in ("file_path", "file_name"))
    if "zip entry" in notes or ".zip" in file_text:
        return "ZIP_ENTRY"
    suffix = Path(_text(row.get("file_name"))).suffix.lower()
    if suffix == ".txt":
        return "TXT"
    if suffix == ".srt" or _bool_value(row.get("has_srt_timestamps")):
        return "SRT"
    if suffix in {".json", ".jsonl"}:
        return "JSON"
    return "UNKNOWN"


def _identity_notes(row: dict[str, Any]) -> str:
    notes = _text(row.get("notes"))
    if _bool_value(row.get("path_redacted")):
        return _join_notes(notes, "source path redacted")
    return notes


def _same_day_distinct_content(day_group: list[dict[str, Any]]) -> bool:
    distinct = {
        (
            _text(row.get("content_hash")),
            _text(row.get("normalized_title_hash")),
            _text(row.get("detected_transcript_start_time")) or _text(row.get("detected_publish_time")),
        )
        for row in day_group
        if _text(row.get("content_hash"))
    }
    return len(distinct) > 1


def _has_non_zip_same_content(row: dict[str, Any], content_group: list[dict[str, Any]]) -> bool:
    return any(
        other.get("transcript_record_id") != row.get("transcript_record_id")
        and other.get("file_type") != "ZIP_ENTRY"
        for other in content_group
    )


def _same_content_source_duplicate(row: dict[str, Any], content_group: list[dict[str, Any]]) -> bool:
    non_zip = [item for item in content_group if item.get("file_type") != "ZIP_ENTRY"]
    return len(non_zip) > 1 and row.get("file_type") != "ZIP_ENTRY"


def _is_same_video_multiformat(
    row: dict[str, Any],
    video_group: list[dict[str, Any]],
) -> bool:
    if not row.get("same_video_group_id") or len(video_group) <= 1:
        return False
    file_types = {_text(item.get("file_type")) for item in video_group}
    return bool(file_types & {"TXT", "SRT", "JSON"}) and len(file_types) > 1


def _preferred_video_file_type(video_group: list[dict[str, Any]]) -> str:
    order = ("TXT", "JSON", "SRT", "UNKNOWN", "ZIP_ENTRY")
    file_types = {_text(row.get("file_type")) for row in video_group}
    for file_type in order:
        if file_type in file_types:
            return file_type
    return ""


def _post_event_count(rows: list[dict[str, Any]]) -> int:
    return sum(
        1
        for row in rows
        if "POST_EVENT" in _text(row.get("logic_type"))
        or "POST_EVENT" in _text(row.get("reason_not_trade_signal"))
    )


def _availability_relation_count(frame: pl.DataFrame, relation: str) -> int:
    if frame.is_empty() or "availability_relation" not in frame.columns:
        return 0
    return sum(1 for value in frame.get_column("availability_relation").to_list() if value == relation)


def _replay_date_set(frame: pl.DataFrame) -> set[str]:
    return _date_values(frame, "trade_date")


def _sum_int(frame: pl.DataFrame, column: str) -> int:
    if frame.is_empty() or column not in frame.columns:
        return 0
    total = 0
    for value in frame.get_column(column).to_list():
        try:
            total += int(value or 0)
        except (TypeError, ValueError):
            continue
    return total


def _any_status(frame: pl.DataFrame, status: str) -> bool:
    if frame.is_empty() or "approval_status" not in frame.columns:
        return False
    return any(_text(value).upper() == status for value in frame.get_column("approval_status").to_list())


def _any_identity_class(frame: pl.DataFrame, identity_class: str) -> bool:
    if frame.is_empty() or "identity_class" not in frame.columns:
        return False
    return any(_text(value) == identity_class for value in frame.get_column("identity_class").to_list())


def _playbook_available_for_date(row: dict[str, Any]) -> bool:
    if not row:
        return False
    if "historical_playbook_overlay_state" in row:
        return "AVAILABLE" in _text(row.get("historical_playbook_overlay_state"))
    return any(_bool_value(row.get(column)) for column in row)


def _nearest_market_date(value: str, market_dates: list[str], *, before: bool) -> str:
    parsed = _parse_date(value)
    if parsed is None:
        return ""
    candidates: list[date] = []
    for market_date in market_dates:
        candidate = _parse_date(market_date)
        if candidate is None:
            continue
        if before and candidate < parsed:
            candidates.append(candidate)
        elif not before and candidate > parsed:
            candidates.append(candidate)
    if not candidates:
        return ""
    return (max(candidates) if before else min(candidates)).isoformat()


def _previous_trading_day(value: date) -> date:
    candidate = value - timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate


def _next_trading_day(value: date) -> date:
    candidate = value + timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate


def _first_value(row: dict[str, Any], columns: Iterable[str]) -> Any:
    lower = {key.lower(): key for key in row}
    for column in columns:
        key = lower.get(column.lower())
        if key is not None and row.get(key) not in (None, ""):
            return row.get(key)
    return ""


def _hashed_or_existing(value: Any) -> str:
    text = _text(value)
    if not text:
        return ""
    if re.fullmatch(r"[a-fA-F0-9]{8,64}", text):
        return text[:16].lower()
    return _stable_hash(text)


def _stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _join_notes(*notes: Any) -> str:
    parts = []
    for note in notes:
        text = _text(note)
        if text and text not in parts:
            parts.append(text)
    return "; ".join(parts)


def _non_empty_group(groups: dict[str, list[dict[str, Any]]], key: Any) -> list[dict[str, Any]]:
    text = _text(key)
    return groups.get(text, []) if text else []


def _group_dicts(rows: list[dict[str, Any]], column: str) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = _text(row.get(column))
        if not key:
            continue
        groups.setdefault(key, []).append(row)
    return groups


def _rows_by_date(frame: pl.DataFrame, column: str) -> dict[str, dict[str, Any]]:
    if frame.is_empty() or column not in frame.columns:
        return {}
    rows: dict[str, dict[str, Any]] = {}
    for row in frame.to_dicts():
        parsed = _date_text(row.get(column))
        if parsed:
            rows[parsed] = row
    return rows


def _date_values(frame: pl.DataFrame, column: str) -> set[str]:
    if frame.is_empty() or column not in frame.columns:
        return set()
    return {
        parsed
        for value in frame.get_column(column).to_list()
        if (parsed := _date_text(value))
    }


def _count_true(rows: list[dict[str, Any]], column: str) -> int:
    return sum(1 for row in rows if _bool_value(row.get(column)))


def _true_count(frame: pl.DataFrame, column: str) -> int:
    if frame.is_empty() or column not in frame.columns:
        return 0
    return sum(1 for value in frame.get_column(column).to_list() if _bool_value(value))


def _unique_non_empty(frame: pl.DataFrame, column: str) -> int:
    if frame.is_empty() or column not in frame.columns:
        return 0
    return len({_text(value) for value in frame.get_column(column).to_list() if _text(value)})


def _time_text(value: Any) -> str:
    text = _text(value)
    if not text:
        return ""
    match = re.search(r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?", text)
    if not match:
        return ""
    hour = int(match.group(1))
    minute = int(match.group(2))
    second = int(match.group(3) or 0)
    return f"{hour:02d}:{minute:02d}:{second:02d}"


def _timestamp_text(day: str, clock: str) -> str:
    if not day:
        return ""
    return f"{day}T{clock or '00:00:00'}"


def _parse_time(value: str) -> time | None:
    try:
        return datetime.strptime(value, "%H:%M:%S").time()
    except ValueError:
        return None


def _date_text(value: Any) -> str:
    text = str(value or "")
    match = re.search(r"20\d{2}-\d{2}-\d{2}", text)
    return match.group(0) if match else ""


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"", "0", "false", "f", "no", "n", "none", "null", "nan"}:
        return False
    if text in {"1", "true", "t", "yes", "y"}:
        return True
    return bool(text)


def _text(value: Any) -> str:
    return _redact_text(str(value or "").strip())


def _redact_text(text: str) -> str:
    text = re.sub(r"[A-Za-z]:[\\/]+Users[\\/]+[^`|\s,\"]+", "<REDACTED_PATH>", text)
    text = re.sub(r"[A-Za-z]:[\\/]+[^`|\s,\"]+", "<REDACTED_PATH>", text)
    text = re.sub(r"/Users/[^`|\s,\"]+", "<REDACTED_PATH>", text)
    return text


def _load_optional(path: Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    try:
        return pl.read_csv(path, infer_schema_length=1000)
    except Exception:
        return pl.DataFrame()


def _frame(inputs: dict[str, pl.DataFrame], name: str) -> pl.DataFrame:
    value = inputs.get(name)
    return value if isinstance(value, pl.DataFrame) else pl.DataFrame()


def _rows_frame(rows: list[dict[str, Any]], schema: dict[str, Any]) -> pl.DataFrame:
    if not rows:
        return pl.DataFrame(schema=schema)
    frame = pl.DataFrame(rows, infer_schema_length=None)
    for column, dtype in schema.items():
        if column not in frame.columns:
            frame = frame.with_columns(pl.lit(None).cast(dtype).alias(column))
        else:
            frame = frame.with_columns(pl.col(column).cast(dtype, strict=False))
    return frame.select(list(schema))


def _frame_markdown(frame: pl.DataFrame, *, limit: int = 30) -> str:
    if frame.is_empty():
        return "_No rows._"
    columns = frame.columns
    rows = ["| " + " | ".join(columns) + " |", "|" + "|".join(["---"] * len(columns)) + "|"]
    for raw in frame.head(limit).to_dicts():
        rows.append("| " + " | ".join(_markdown_cell(raw.get(column, "")) for column in columns) + " |")
    return "\n".join(rows)


def _markdown_cell(value: Any) -> str:
    return _redact_text(str(value).replace("|", "\\|").replace("\n", " "))[:700]


def _safe_report(text: str) -> str:
    lowered = text.lower()
    for phrase in FORBIDDEN_REPORT_PHRASES:
        if phrase in lowered:
            raise ValueError(f"Forbidden report phrase: {phrase}")
    if re.search(r"[A-Za-z]:[\\/]+Users[\\/]+", text):
        raise ValueError("Report contains an unredacted local source path.")
    return _redact_text(text)


def _transcript_identity_schema() -> dict[str, Any]:
    return {
        "transcript_record_id": pl.String,
        "source_id_hash": pl.String,
        "file_hash": pl.String,
        "content_hash": pl.String,
        "normalized_title_hash": pl.String,
        "detected_video_id_hash": pl.String,
        "detected_url_hash": pl.String,
        "detected_publish_date": pl.String,
        "detected_publish_time": pl.String,
        "detected_live_start_time": pl.String,
        "detected_transcript_date": pl.String,
        "detected_transcript_start_time": pl.String,
        "detected_transcript_end_time": pl.String,
        "file_type": pl.String,
        "same_day_group_id": pl.String,
        "same_content_group_id": pl.String,
        "same_video_group_id": pl.String,
        "identity_class": pl.String,
        "duplicate_safe_to_collapse": pl.Boolean,
        "notes": pl.String,
    }


def _clean_transcript_schema() -> dict[str, Any]:
    return {
        "clean_transcript_id": pl.String,
        "transcript_record_ids_included": pl.String,
        "selected_record_id": pl.String,
        "transcript_date": pl.String,
        "transcript_time": pl.String,
        "title_hash": pl.String,
        "content_hash": pl.String,
        "identity_class": pl.String,
        "included_in_clean_set": pl.Boolean,
        "collapse_reason": pl.String,
        "keep_reason": pl.String,
    }


def _transcript_session_availability_schema() -> dict[str, Any]:
    return {
        "transcript_date": pl.String,
        "transcript_time": pl.String,
        "publish_timestamp": pl.String,
        "market_session_date": pl.String,
        "replay_trade_date": pl.String,
        "day_of_week": pl.String,
        "is_weekend_transcript": pl.Boolean,
        "is_weekend_market_date": pl.Boolean,
        "nearest_market_session_before": pl.String,
        "nearest_market_session_after": pl.String,
        "availability_relation": pl.String,
        "can_use_as_same_session_input": pl.Boolean,
        "can_use_as_next_session_input": pl.Boolean,
        "can_use_as_playbook_context": pl.Boolean,
        "reason_plain_english": pl.String,
    }


def _session_remap_suggestion_schema() -> dict[str, Any]:
    return {
        "original_replay_date": pl.String,
        "suggested_market_session_date": pl.String,
        "reason": pl.String,
        "confidence": pl.String,
        "affected_outputs": pl.String,
        "approval_status": pl.String,
        "reviewer_notes": pl.String,
    }


def _replay_after_remap_schema() -> dict[str, Any]:
    return {
        "original_replay_date": pl.String,
        "market_session_date": pl.String,
        "proposed_market_session_date": pl.String,
        "approval_status": pl.String,
        "remap_applied": pl.Boolean,
        "transcript_state": pl.String,
        "data_state_after_approved_remap": pl.String,
        "guru_state": pl.String,
        "what_would_change_if_approved": pl.String,
        "plain_english_summary": pl.String,
    }


def _same_day_reinterpretation_schema() -> dict[str, Any]:
    return {
        "scope": pl.String,
        "clean_transcript_count": pl.Int64,
        "same_day_clean_transcript_count": pl.Int64,
        "context_rows": pl.Int64,
        "filter_rows": pl.Int64,
        "market_map_rows": pl.Int64,
        "trade_rule_rows": pl.Int64,
        "post_event_rows": pl.Int64,
        "weekend_recap_rows": pl.Int64,
        "next_session_prep_rows": pl.Int64,
        "historical_playbook_overlay_available": pl.Boolean,
        "strict_trade_rule_explanation": pl.String,
    }


def _identity_summary_schema() -> dict[str, Any]:
    return {
        "identity_class": pl.String,
        "row_count": pl.Int64,
        "safe_to_collapse_rows": pl.Int64,
    }


def _clean_set_summary_schema() -> dict[str, Any]:
    return {
        "total_rows": pl.Int64,
        "included_clean_transcripts": pl.Int64,
        "collapsed_rows": pl.Int64,
        "unique_transcript_dates": pl.Int64,
    }


def _availability_summary_schema() -> dict[str, Any]:
    return {
        "availability_relation": pl.String,
        "row_count": pl.Int64,
        "same_session_input_rows": pl.Int64,
        "next_session_input_rows": pl.Int64,
    }


def main() -> None:
    """CLI entry point."""

    result = run_transcript_identity_session_remap_layer()
    print(f"final_recommendation: {result.final_recommendation}")
    print(f"identity_rows: {result.transcript_identity_audit.height}")
    print(f"clean_rows: {_true_count(result.clean_transcript_set, 'included_in_clean_set')}")
    print(f"remap_suggestions: {result.session_remap_suggestions.height}")


if __name__ == "__main__":
    main()
