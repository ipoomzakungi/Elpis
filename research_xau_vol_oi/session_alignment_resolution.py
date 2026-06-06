"""Session calendar, transcript, and missing-data resolution diagnostics.

This module is research-only. It audits whether missing same-date guru text or
missing XAU spot/basis rows are true data gaps or calendar/session alignment
artifacts. It does not fetch data, create trading signals, or treat historical
playbook context as same-day transcript evidence.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable

import polars as pl


FINAL_RECOMMENDATIONS = (
    "REMAP_SESSION_DATES_FIRST",
    "FETCH_MISSING_SPOT_BASIS",
    "FETCH_MISSING_TRANSCRIPTS_ONLY",
    "PLAYBOOK_OVERLAY_READY",
    "SAME_DAY_CONTEXT_READY",
    "SAME_DAY_TRADE_RULE_NOT_READY",
)
FORBIDDEN_REPORT_PHRASES = (
    "profitable",
    "safe to trade",
    "live ready",
    "live-ready",
)
PLAYBOOK_ONLY = "PLAYBOOK_ONLY"


@dataclass(frozen=True)
class SessionAlignmentResolutionResult:
    """Generated frames and recommendations for the resolution layer."""

    session_calendar_audit: pl.DataFrame
    same_date_transcript_resolution: pl.DataFrame
    transcript_manifest_dedup_audit: pl.DataFrame
    same_day_guru_signal_readiness: pl.DataFrame
    refined_missing_data_action_plan: pl.DataFrame
    current_week_replay_resolved: pl.DataFrame
    final_recommendation: str
    secondary_recommendation: str


def run_session_alignment_resolution_layer(
    *,
    output_dir: str | Path = "outputs",
    transcript_source_roots: Iterable[str | Path] | None = None,
) -> SessionAlignmentResolutionResult:
    """Run session alignment resolution and write all requested artifacts."""

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    _ = resolve_transcript_source_roots(transcript_source_roots)
    inputs = load_session_alignment_inputs(output_root)
    result = build_session_alignment_resolution(inputs)

    result.session_calendar_audit.write_csv(output_root / "session_calendar_audit.csv")
    (output_root / "session_calendar_audit.md").write_text(
        session_calendar_audit_markdown(result.session_calendar_audit),
        encoding="utf-8",
    )
    result.same_date_transcript_resolution.write_csv(
        output_root / "same_date_transcript_resolution.csv"
    )
    (output_root / "same_date_transcript_resolution.md").write_text(
        same_date_transcript_resolution_markdown(result.same_date_transcript_resolution),
        encoding="utf-8",
    )
    result.transcript_manifest_dedup_audit.write_csv(
        output_root / "transcript_manifest_dedup_audit.csv"
    )
    (output_root / "transcript_manifest_dedup_audit.md").write_text(
        transcript_manifest_dedup_audit_markdown(result.transcript_manifest_dedup_audit),
        encoding="utf-8",
    )
    result.same_day_guru_signal_readiness.write_csv(
        output_root / "same_day_guru_signal_readiness.csv"
    )
    (output_root / "same_day_guru_signal_readiness.md").write_text(
        same_day_guru_signal_readiness_markdown(result.same_day_guru_signal_readiness),
        encoding="utf-8",
    )
    result.refined_missing_data_action_plan.write_csv(
        output_root / "refined_missing_data_action_plan.csv"
    )
    (output_root / "refined_missing_data_action_plan.md").write_text(
        refined_missing_data_action_plan_markdown(result.refined_missing_data_action_plan),
        encoding="utf-8",
    )
    result.current_week_replay_resolved.write_csv(output_root / "current_week_replay_resolved.csv")
    (output_root / "current_week_replay_resolved.md").write_text(
        current_week_replay_resolved_markdown(
            result.current_week_replay_resolved,
            final_recommendation=result.final_recommendation,
            secondary_recommendation=result.secondary_recommendation,
        ),
        encoding="utf-8",
    )
    append_session_alignment_resolution_sections(output_root / "research_report.md", result)
    return result


def resolve_transcript_source_roots(
    roots: Iterable[str | Path] | None = None,
) -> tuple[Path, ...]:
    """Resolve transcript roots from caller input or local environment only.

    Resolved paths are intentionally not written to any report.
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


def load_session_alignment_inputs(output_root: Path) -> dict[str, pl.DataFrame]:
    """Load optional input artifacts with empty-frame fallbacks."""

    names = {
        "current_week_cme_guru_replay": output_root / "current_week_cme_guru_replay.csv",
        "current_week_cme_guru_playbook_replay": (
            output_root / "current_week_cme_guru_playbook_replay.csv"
        ),
        "guru_transcript_alignment_debug": output_root / "guru_transcript_alignment_debug.csv",
        "guru_text_interpretation_audit": output_root / "guru_text_interpretation_audit.csv",
        "missing_xau_spot_basis_fetch_plan": (
            output_root / "missing_xau_spot_basis_fetch_plan.csv"
        ),
        "transcript_corpus_manifest": output_root / "transcript_corpus_manifest.csv",
        "cme_validation_grade_days_after_backfill": (
            output_root / "cme_validation_grade_days_after_backfill.csv"
        ),
        "current_cme_date_usability": output_root / "current_cme_date_usability.csv",
        "cme_canonical_futures_price": output_root / "cme_canonical_futures_price.parquet",
        "cme_canonical_option_oi_by_strike": (
            output_root / "cme_canonical_option_oi_by_strike.parquet"
        ),
        "xau_spot_backfilled": output_root / "xau_spot_backfilled.parquet",
        "xau_basis_backfilled": output_root / "xau_basis_backfilled.parquet",
        "guru_logic_knowledge_base": output_root / "guru_logic_knowledge_base.csv",
    }
    return {name: _load_optional(path) for name, path in names.items()}


def build_session_alignment_resolution(
    inputs: dict[str, pl.DataFrame],
) -> SessionAlignmentResolutionResult:
    """Build all session/transcript/data resolution frames."""

    replay = _frame(inputs, "current_week_cme_guru_replay")
    alignment = _frame(inputs, "guru_transcript_alignment_debug")
    manifest = _frame(inputs, "transcript_corpus_manifest")
    interpretation = _frame(inputs, "guru_text_interpretation_audit")
    playbook = _frame(inputs, "current_week_cme_guru_playbook_replay")
    missing_plan = _frame(inputs, "missing_xau_spot_basis_fetch_plan")
    knowledge_base = _frame(inputs, "guru_logic_knowledge_base")

    calendar = build_session_calendar_audit(
        replay=replay,
        date_usability=_frame(inputs, "current_cme_date_usability"),
        futures=_frame(inputs, "cme_canonical_futures_price"),
        option_oi=_frame(inputs, "cme_canonical_option_oi_by_strike"),
        spot=_frame(inputs, "xau_spot_backfilled"),
        basis=_frame(inputs, "xau_basis_backfilled"),
    )
    transcript_resolution = build_same_date_transcript_resolution(
        alignment=alignment,
        manifest=manifest,
        playbook_replay=playbook,
    )
    dedup = build_transcript_manifest_dedup_audit(manifest)
    readiness = build_same_day_guru_signal_readiness(
        alignment=alignment,
        interpretation=interpretation,
    )
    action_plan = build_refined_missing_data_action_plan(
        missing_spot_basis_plan=missing_plan,
        session_calendar=calendar,
        transcript_resolution=transcript_resolution,
    )
    resolved = build_current_week_replay_resolved(
        replay=replay,
        session_calendar=calendar,
        transcript_resolution=transcript_resolution,
        readiness=readiness,
        playbook_replay=playbook,
        knowledge_base=knowledge_base,
    )
    final, secondary = choose_session_alignment_recommendations(
        session_calendar=calendar,
        transcript_resolution=transcript_resolution,
        readiness=readiness,
        resolved=resolved,
        playbook_replay=playbook,
    )
    return SessionAlignmentResolutionResult(
        session_calendar_audit=calendar,
        same_date_transcript_resolution=transcript_resolution,
        transcript_manifest_dedup_audit=dedup,
        same_day_guru_signal_readiness=readiness,
        refined_missing_data_action_plan=action_plan,
        current_week_replay_resolved=resolved,
        final_recommendation=final,
        secondary_recommendation=secondary,
    )


def build_session_calendar_audit(
    *,
    replay: pl.DataFrame,
    date_usability: pl.DataFrame = pl.DataFrame(),
    futures: pl.DataFrame = pl.DataFrame(),
    option_oi: pl.DataFrame = pl.DataFrame(),
    spot: pl.DataFrame = pl.DataFrame(),
    basis: pl.DataFrame = pl.DataFrame(),
) -> pl.DataFrame:
    """Audit replay dates against weekday/session availability."""

    replay_rows = _rows_by_date(replay, "trade_date")
    usability_rows = _rows_by_date(date_usability, "trade_date")
    all_dates = _replay_dates(replay) or _replay_dates(date_usability)
    data_dates = {
        "futures": _date_set_from_frame(futures),
        "option_oi": _date_set_from_frame(option_oi),
        "spot": _date_set_from_frame(spot),
        "basis": _date_set_from_frame(basis),
    }
    rows: list[dict[str, Any]] = []
    for trade_date in all_dates:
        parsed = _parse_date(trade_date)
        if parsed is None:
            continue
        replay_row = replay_rows.get(trade_date, {})
        usability_row = usability_rows.get(trade_date, {})
        flags = _availability_flags(trade_date, replay_row, usability_row, data_dates)
        previous = _previous_trading_day(parsed).isoformat()
        next_day = _next_trading_day(parsed).isoformat()
        previous_available = _adjacent_date_available(previous, replay_rows, usability_rows, data_dates)
        next_available = _adjacent_date_available(next_day, replay_rows, usability_rows, data_dates)
        weekend = parsed.weekday() >= 5
        missing_core = not (flags["has_xau_spot_rows"] and flags["has_basis_rows"])
        likely_issue = bool(weekend and missing_core)
        mapping = _recommended_session_mapping(
            trade_date=trade_date,
            weekend=weekend,
            likely_issue=likely_issue,
            previous=previous,
            next_day=next_day,
            previous_available=previous_available,
            next_available=next_available,
            flags=flags,
        )
        likely_session = _mapped_session_date(mapping, trade_date)
        rows.append(
            {
                "replay_trade_date": trade_date,
                "day_of_week": parsed.strftime("%A"),
                "is_weekend": weekend,
                **flags,
                "likely_session_date": likely_session,
                "likely_calendar_date_issue": likely_issue,
                "possible_previous_trading_day": previous,
                "possible_next_trading_day": next_day,
                "recommended_session_mapping": mapping,
                "reason_plain_english": _calendar_reason(
                    trade_date=trade_date,
                    weekend=weekend,
                    likely_issue=likely_issue,
                    previous=previous,
                    next_day=next_day,
                    previous_available=previous_available,
                    next_available=next_available,
                    flags=flags,
                ),
            }
        )
    return _rows_frame(rows, _session_calendar_schema()).sort("replay_trade_date")


def build_same_date_transcript_resolution(
    *,
    alignment: pl.DataFrame,
    manifest: pl.DataFrame,
    playbook_replay: pl.DataFrame = pl.DataFrame(),
) -> pl.DataFrame:
    """Resolve missing same-date transcript cases before fetching new text."""

    transcript_counts = _transcript_date_counts(manifest)
    transcript_dates = sorted(transcript_counts)
    corpus_end = max(transcript_dates) if transcript_dates else ""
    playbook_rows = _rows_by_date(playbook_replay, "trade_date")
    rows: list[dict[str, Any]] = []
    for alignment_row in _sorted_rows(alignment, "trade_date"):
        trade_date = _date_text(alignment_row.get("trade_date"))
        if not trade_date:
            continue
        same_count = int(_float_or_zero(alignment_row.get("transcript_same_date_count")))
        if same_count > 0 or _bool_value(alignment_row.get("same_date_transcript_available")):
            continue
        parsed = _parse_date(trade_date)
        if parsed is None:
            continue
        previous = _previous_trading_day(parsed).isoformat()
        next_day = _next_trading_day(parsed).isoformat()
        previous_match = previous if transcript_counts.get(previous, 0) else ""
        next_match = next_day if transcript_counts.get(next_day, 0) else ""
        before, before_gap = _nearest_date(trade_date, transcript_dates, before=True)
        after, after_gap = _nearest_date(trade_date, transcript_dates, before=False)
        possible_shift = bool(previous_match or next_match)
        playbook_available = _playbook_available_for_date(playbook_rows.get(trade_date, {}))
        corpus_ended_before_date = bool(corpus_end and corpus_end < trade_date)
        should_fetch = _should_fetch_transcript(
            parsed=parsed,
            possible_shift=possible_shift,
            corpus_ended_before_date=corpus_ended_before_date,
            playbook_available=playbook_available,
        )
        rows.append(
            {
                "missing_replay_date": trade_date,
                "day_of_week": parsed.strftime("%A"),
                "same_date_transcript_count": same_count,
                "nearest_before_transcript_date": before,
                "nearest_before_gap_days": before_gap,
                "nearest_after_transcript_date": after,
                "nearest_after_gap_days": after_gap,
                "possible_session_shift_match": possible_shift,
                "possible_previous_trading_day_transcript": previous_match,
                "possible_next_trading_day_transcript": next_match,
                "should_fetch_transcript": should_fetch,
                "should_use_historical_playbook_overlay": playbook_available,
                "reason_plain_english": _transcript_resolution_reason(
                    trade_date=trade_date,
                    parsed=parsed,
                    possible_shift=possible_shift,
                    previous_match=previous_match,
                    next_match=next_match,
                    should_fetch=should_fetch,
                    playbook_available=playbook_available,
                    corpus_end=corpus_end,
                ),
            }
        )
    return _rows_frame(rows, _same_date_transcript_schema()).sort("missing_replay_date")


def build_transcript_manifest_dedup_audit(manifest: pl.DataFrame) -> pl.DataFrame:
    """Explain total manifest rows versus clean transcript-file rows."""

    if manifest.is_empty():
        row = {
            "total_manifest_rows": 0,
            "unique_file_hashes": 0,
            "unique_transcript_dates": 0,
            "unique_txt_files": 0,
            "zip_entry_rows": 0,
            "sidecar_or_duplicate_rows": 0,
            "duplicate_groups": 0,
            "clean_transcript_count": 0,
            "notes": "Transcript manifest is missing or empty.",
        }
        return _rows_frame([row], _manifest_dedup_schema())
    source_file_rows = _source_file_rows(manifest)
    zip_rows = _zip_entry_rows(manifest)
    clean_count = source_file_rows.height
    sidecar_or_duplicate = max(manifest.height - clean_count, 0)
    duplicate_groups = _unique_non_empty(manifest, "duplicate_group")
    row = {
        "total_manifest_rows": manifest.height,
        "unique_file_hashes": _unique_non_empty(manifest, "source_id_hash"),
        "unique_transcript_dates": _unique_non_empty(manifest, "detected_date"),
        "unique_txt_files": clean_count,
        "zip_entry_rows": zip_rows.height,
        "sidecar_or_duplicate_rows": sidecar_or_duplicate,
        "duplicate_groups": duplicate_groups,
        "clean_transcript_count": clean_count,
        "notes": (
            "Manifest rows include source text files plus zip-entry inventory rows. "
            "Clean transcript count is reported separately as source-file text rows; "
            "older clean counts can differ after newly downloaded transcript bundles are indexed."
        ),
    }
    return _rows_frame([row], _manifest_dedup_schema())


def build_same_day_guru_signal_readiness(
    *,
    alignment: pl.DataFrame,
    interpretation: pl.DataFrame,
) -> pl.DataFrame:
    """Count same-day text readiness without upgrading context into trade rules."""

    interpretation_by_date = _group_rows(interpretation, "transcript_date")
    rows: list[dict[str, Any]] = []
    for alignment_row in _sorted_rows(alignment, "trade_date"):
        trade_date = _date_text(alignment_row.get("trade_date"))
        same_count = int(_float_or_zero(alignment_row.get("transcript_same_date_count")))
        same_available = same_count > 0 or _bool_value(
            alignment_row.get("same_date_transcript_available")
        )
        if not trade_date or not same_available:
            continue
        text_rows = interpretation_by_date.get(trade_date, [])
        context_rows = _count_true(text_rows, "usable_as_context")
        filter_rows = _count_true(text_rows, "usable_as_filter")
        market_map_rows = _count_true(text_rows, "usable_as_market_map")
        trade_rule_rows = _count_true(text_rows, "usable_as_trade_rule")
        post_event_rows = sum(
            1
            for row in text_rows
            if "POST_EVENT" in _text(row.get("logic_type"))
            or "POST_EVENT" in _text(row.get("reason_not_trade_signal"))
        )
        insufficient_context_rows = sum(
            1
            for row in text_rows
            if not any(
                _bool_value(row.get(column))
                for column in (
                    "usable_as_context",
                    "usable_as_filter",
                    "usable_as_market_map",
                    "usable_as_trade_rule",
                )
            )
        )
        rows.append(
            {
                "trade_date": trade_date,
                "transcript_count": same_count,
                "context_rows": context_rows,
                "filter_rows": filter_rows,
                "market_map_rows": market_map_rows,
                "trade_rule_rows": trade_rule_rows,
                "post_event_rows": post_event_rows,
                "insufficient_context_rows": insufficient_context_rows,
                "can_use_as_same_day_context": context_rows > 0,
                "can_use_as_same_day_filter": filter_rows > 0,
                "can_use_as_same_day_trade_rule": trade_rule_rows > 0,
                "reason_not_trade_rule": _readiness_reason(
                    text_row_count=len(text_rows),
                    context_rows=context_rows,
                    filter_rows=filter_rows,
                    market_map_rows=market_map_rows,
                    trade_rule_rows=trade_rule_rows,
                    post_event_rows=post_event_rows,
                ),
            }
        )
    return _rows_frame(rows, _same_day_readiness_schema()).sort("trade_date")


def build_refined_missing_data_action_plan(
    *,
    missing_spot_basis_plan: pl.DataFrame,
    session_calendar: pl.DataFrame,
    transcript_resolution: pl.DataFrame,
) -> pl.DataFrame:
    """Refine missing spot/basis and transcript actions after calendar checks."""

    calendar_by_date = _rows_by_date(session_calendar, "replay_trade_date")
    rows: list[dict[str, Any]] = []
    for item in _sorted_rows(missing_spot_basis_plan, "trade_date"):
        trade_date = _date_text(item.get("trade_date"))
        if not trade_date:
            continue
        calendar = calendar_by_date.get(trade_date, {})
        calendar_issue = _bool_value(calendar.get("likely_calendar_date_issue"))
        adjacent_available = _calendar_adjacent_available(calendar)
        final_action = (
            "REMAP_SESSION_DATE"
            if calendar_issue and adjacent_available
            else "FETCH_XAU_SPOT"
        )
        if calendar_issue and not adjacent_available:
            final_action = "NEEDS_MANUAL_REVIEW"
        rows.append(
            {
                "data_item": "xau_spot_basis",
                "date": trade_date,
                "original_missing_reason": _text(item.get("missing_component")),
                "calendar_issue_possible": calendar_issue,
                "adjacent_date_available": adjacent_available,
                "final_action": final_action,
                "exact_file_needed": _exact_file_needed_for_action(final_action, item),
                "where_to_place_file": _where_to_place_for_action(final_action, item),
                "rerun_command": "python -m research_xau_vol_oi.report",
            }
        )
    for item in _sorted_rows(transcript_resolution, "missing_replay_date"):
        trade_date = _date_text(item.get("missing_replay_date"))
        if not trade_date:
            continue
        calendar = calendar_by_date.get(trade_date, {})
        calendar_issue = _bool_value(calendar.get("likely_calendar_date_issue"))
        adjacent_available = _bool_value(item.get("possible_session_shift_match"))
        final_action = _transcript_action(item, calendar_issue=calendar_issue)
        rows.append(
            {
                "data_item": "same_date_transcript",
                "date": trade_date,
                "original_missing_reason": "same-date transcript unavailable",
                "calendar_issue_possible": calendar_issue,
                "adjacent_date_available": adjacent_available,
                "final_action": final_action,
                "exact_file_needed": _transcript_file_needed(final_action),
                "where_to_place_file": "outputs/transcript_corpus_manifest.csv or configured transcript roots",
                "rerun_command": "python -m research_xau_vol_oi.report",
            }
        )
    return _rows_frame(rows, _missing_action_schema()).sort(["date", "data_item"])


def build_current_week_replay_resolved(
    *,
    replay: pl.DataFrame,
    session_calendar: pl.DataFrame,
    transcript_resolution: pl.DataFrame,
    readiness: pl.DataFrame,
    playbook_replay: pl.DataFrame,
    knowledge_base: pl.DataFrame = pl.DataFrame(),
) -> pl.DataFrame:
    """Resolve current replay labels after calendar and transcript checks."""

    calendar_by_date = _rows_by_date(session_calendar, "replay_trade_date")
    transcript_by_date = _rows_by_date(transcript_resolution, "missing_replay_date")
    readiness_by_date = _rows_by_date(readiness, "trade_date")
    playbook_by_date = _rows_by_date(playbook_replay, "trade_date")
    historical_playbook_default = not knowledge_base.is_empty()
    rows: list[dict[str, Any]] = []
    for replay_row in _sorted_rows(replay, "trade_date"):
        trade_date = _date_text(replay_row.get("trade_date"))
        if not trade_date:
            continue
        calendar = calendar_by_date.get(trade_date, {})
        transcript = transcript_by_date.get(trade_date, {})
        ready = readiness_by_date.get(trade_date, {})
        playbook = playbook_by_date.get(trade_date, {})
        resolved_date = str(calendar.get("likely_session_date") or trade_date)
        same_day_state = _same_day_transcript_state_for_resolved(ready, transcript, playbook)
        data_state = _data_state_for_resolved(replay_row, calendar)
        guru_state = _guru_state_for_resolved(
            ready,
            playbook,
            historical_playbook_default=historical_playbook_default,
        )
        rows.append(
            {
                "original_replay_date": trade_date,
                "resolved_session_date": resolved_date,
                "same_day_transcript_state": same_day_state,
                "data_state": data_state,
                "guru_state": guru_state,
                "plain_english_summary": _resolved_summary(
                    trade_date=trade_date,
                    resolved_date=resolved_date,
                    same_day_state=same_day_state,
                    data_state=data_state,
                    guru_state=guru_state,
                ),
            }
        )
    return _rows_frame(rows, _replay_resolved_schema()).sort("original_replay_date")


def choose_session_alignment_recommendations(
    *,
    session_calendar: pl.DataFrame,
    transcript_resolution: pl.DataFrame,
    readiness: pl.DataFrame,
    resolved: pl.DataFrame,
    playbook_replay: pl.DataFrame,
) -> tuple[str, str]:
    """Choose conservative primary and secondary recommendation labels."""

    if _any_true(session_calendar, "likely_calendar_date_issue"):
        primary = "REMAP_SESSION_DATES_FIRST"
    elif _any_state(resolved, "data_state", "NEEDS_SPOT_BASIS"):
        primary = "FETCH_MISSING_SPOT_BASIS"
    elif _any_true(transcript_resolution, "should_fetch_transcript"):
        primary = "FETCH_MISSING_TRANSCRIPTS_ONLY"
    elif _any_true(readiness, "can_use_as_same_day_trade_rule"):
        primary = "SAME_DAY_CONTEXT_READY"
    elif _any_same_day_context_or_filter(readiness):
        primary = "SAME_DAY_TRADE_RULE_NOT_READY"
    elif _playbook_all_replay_dates(playbook_replay, resolved):
        primary = "PLAYBOOK_OVERLAY_READY"
    else:
        primary = "FETCH_MISSING_TRANSCRIPTS_ONLY"

    secondary = "PLAYBOOK_OVERLAY_READY" if _playbook_all_replay_dates(playbook_replay, resolved) else ""
    if primary == "PLAYBOOK_OVERLAY_READY":
        secondary = "SAME_DAY_TRADE_RULE_NOT_READY"
    return primary, secondary


def session_alignment_resolution_report_lines(
    result: SessionAlignmentResolutionResult | None,
) -> list[str]:
    """Return Markdown lines for embedding in the main research report."""

    if result is None:
        return ["Session alignment resolution layer was not run."]
    return [
        "## Session Calendar Audit",
        "",
        f"- Final recommendation: `{result.final_recommendation}`",
        f"- Secondary recommendation: `{result.secondary_recommendation or 'none'}`",
        "",
        _frame_markdown(result.session_calendar_audit),
        "",
        "## Same-Date Transcript Resolution",
        "",
        _frame_markdown(result.same_date_transcript_resolution),
        "",
        "## Transcript Manifest Deduplication",
        "",
        _frame_markdown(result.transcript_manifest_dedup_audit),
        "",
        "## Same-Day Guru Signal Readiness",
        "",
        _frame_markdown(result.same_day_guru_signal_readiness),
        "",
        "## Refined Missing Data Action Plan",
        "",
        _frame_markdown(result.refined_missing_data_action_plan),
        "",
        "## Current-Week Replay Resolved",
        "",
        _frame_markdown(result.current_week_replay_resolved),
    ]


def session_calendar_audit_markdown(frame: pl.DataFrame) -> str:
    """Render session calendar audit rows."""

    return _safe_report(
        "\n".join(
            [
                "# Session Calendar Audit",
                "",
                "Weekend replay dates are checked against adjacent trading dates before data is called missing.",
                "",
                _frame_markdown(frame),
            ]
        )
    )


def same_date_transcript_resolution_markdown(frame: pl.DataFrame) -> str:
    """Render missing transcript resolution rows."""

    return _safe_report(
        "\n".join(
            [
                "# Same-Date Transcript Resolution",
                "",
                "Missing same-date transcripts are separated from session-shift candidates and playbook-only context.",
                "",
                _frame_markdown(frame),
            ]
        )
    )


def transcript_manifest_dedup_audit_markdown(frame: pl.DataFrame) -> str:
    """Render transcript manifest de-duplication audit."""

    return _safe_report(
        "\n".join(
            [
                "# Transcript Manifest Deduplication Audit",
                "",
                "Total manifest rows include zip entries and duplicate inventory rows; clean text-file count is separate.",
                "",
                _frame_markdown(frame),
            ]
        )
    )


def same_day_guru_signal_readiness_markdown(frame: pl.DataFrame) -> str:
    """Render same-day guru signal readiness."""

    return _safe_report(
        "\n".join(
            [
                "# Same-Day Guru Signal Readiness",
                "",
                "Context, filter, market-map, and strict trade-rule text are counted separately.",
                "",
                _frame_markdown(frame),
            ]
        )
    )


def refined_missing_data_action_plan_markdown(frame: pl.DataFrame) -> str:
    """Render refined missing data action plan."""

    return _safe_report(
        "\n".join(
            [
                "# Refined Missing Data Action Plan",
                "",
                "Calendar/session checks are applied before requesting new files.",
                "",
                _frame_markdown(frame),
            ]
        )
    )


def current_week_replay_resolved_markdown(
    frame: pl.DataFrame,
    *,
    final_recommendation: str,
    secondary_recommendation: str,
) -> str:
    """Render resolved current-week replay rows."""

    return _safe_report(
        "\n".join(
            [
                "# Current-Week Replay Resolved",
                "",
                f"- Final recommendation: `{final_recommendation}`",
                f"- Secondary recommendation: `{secondary_recommendation or 'none'}`",
                "- Historical playbook overlay remains separate from same-day transcript context.",
                "",
                _frame_markdown(frame),
            ]
        )
    )


def append_session_alignment_resolution_sections(
    path: Path,
    result: SessionAlignmentResolutionResult,
) -> None:
    """Append or replace resolution sections in a generated research report."""

    marker = "\n## Session Calendar Audit\n"
    section = "\n".join(session_alignment_resolution_report_lines(result))
    existing = path.read_text(encoding="utf-8") if path.exists() else "# XAU/USD Vol-OI Research Report\n"
    if marker in existing:
        existing = existing.split(marker, 1)[0].rstrip()
    path.write_text(_safe_report(existing.rstrip() + "\n\n" + section + "\n"), encoding="utf-8")


def _availability_flags(
    trade_date: str,
    replay_row: dict[str, Any],
    usability_row: dict[str, Any],
    data_dates: dict[str, set[str]],
) -> dict[str, bool]:
    replay_exists = bool(replay_row)
    return {
        "has_cme_futures_rows": _available(
            trade_date,
            replay_row.get("futures_available"),
            usability_row.get("has_gc_futures_price"),
            data_dates["futures"],
            replay_exists=replay_exists,
        ),
        "has_option_oi_rows": _available(
            trade_date,
            replay_row.get("oi_available"),
            usability_row.get("has_option_oi_by_strike"),
            data_dates["option_oi"],
            replay_exists=replay_exists,
        ),
        "has_xau_spot_rows": _available(
            trade_date,
            replay_row.get("spot_available"),
            usability_row.get("has_xau_spot_price"),
            data_dates["spot"],
            replay_exists=replay_exists,
        ),
        "has_basis_rows": _available(
            trade_date,
            replay_row.get("basis_available"),
            usability_row.get("has_basis"),
            data_dates["basis"],
            replay_exists=replay_exists,
        ),
    }


def _available(
    trade_date: str,
    replay_value: Any,
    usability_value: Any,
    observed_dates: set[str],
    *,
    replay_exists: bool,
) -> bool:
    if replay_exists:
        return _bool_value(replay_value) or trade_date in observed_dates
    return _bool_value(usability_value) or trade_date in observed_dates


def _adjacent_date_available(
    trade_date: str,
    replay_rows: dict[str, dict[str, Any]],
    usability_rows: dict[str, dict[str, Any]],
    data_dates: dict[str, set[str]],
) -> bool:
    flags = _availability_flags(
        trade_date,
        replay_rows.get(trade_date, {}),
        usability_rows.get(trade_date, {}),
        data_dates,
    )
    return bool(
        flags["has_cme_futures_rows"]
        and flags["has_xau_spot_rows"]
        and flags["has_basis_rows"]
    )


def _recommended_session_mapping(
    *,
    trade_date: str,
    weekend: bool,
    likely_issue: bool,
    previous: str,
    next_day: str,
    previous_available: bool,
    next_available: bool,
    flags: dict[str, bool],
) -> str:
    if not weekend:
        return "KEEP_REPLAY_DATE"
    if all(flags.values()):
        return "KEEP_REPLAY_DATE_TRUE_WEEKEND_DATA"
    if likely_issue and previous_available:
        return f"REMAP_TO_{previous}"
    if likely_issue and next_available:
        return f"REMAP_TO_{next_day}"
    if likely_issue:
        return "NEEDS_MANUAL_REVIEW"
    return "IGNORE_WEEKEND_ARTIFACT"


def _mapped_session_date(mapping: str, fallback: str) -> str:
    match = re.search(r"REMAP_TO_(20\d{2}-\d{2}-\d{2})", mapping)
    return match.group(1) if match else fallback


def _calendar_reason(
    *,
    trade_date: str,
    weekend: bool,
    likely_issue: bool,
    previous: str,
    next_day: str,
    previous_available: bool,
    next_available: bool,
    flags: dict[str, bool],
) -> str:
    if weekend and all(flags.values()):
        return (
            f"{trade_date} is a weekend date, but true weekend-dated rows exist for the "
            "checked CME, spot, and basis fields; keep it separate for manual review."
        )
    if likely_issue and previous_available:
        return (
            f"{trade_date} is a weekend replay date with missing spot/basis rows. "
            f"The previous trading day {previous} has adjacent data, so review a session-date remap first."
        )
    if likely_issue and next_available:
        return (
            f"{trade_date} is a weekend replay date with missing spot/basis rows. "
            f"The next trading day {next_day} has adjacent data, so review a session-date remap first."
        )
    if likely_issue:
        return (
            f"{trade_date} is a weekend replay date with missing spot/basis rows, but adjacent "
            "trading-day coverage was not complete; manual review is needed before fetching."
        )
    if weekend:
        return f"{trade_date} is weekend-dated but no blocking missing-data artifact was detected."
    return f"{trade_date} is a weekday replay date; no weekend calendar artifact was detected."


def _should_fetch_transcript(
    *,
    parsed: date,
    possible_shift: bool,
    corpus_ended_before_date: bool,
    playbook_available: bool,
) -> bool:
    if parsed.weekday() >= 5 and possible_shift:
        return False
    if corpus_ended_before_date and not possible_shift:
        return True
    return bool(not possible_shift and not playbook_available)


def _transcript_resolution_reason(
    *,
    trade_date: str,
    parsed: date,
    possible_shift: bool,
    previous_match: str,
    next_match: str,
    should_fetch: bool,
    playbook_available: bool,
    corpus_end: str,
) -> str:
    if parsed.weekday() >= 5 and possible_shift:
        matches = ", ".join(item for item in (previous_match, next_match) if item)
        return (
            f"{trade_date} is weekend-dated and has transcript candidates on adjacent trading "
            f"date(s) {matches}; check session shift before fetching new transcripts."
        )
    if possible_shift:
        matches = ", ".join(item for item in (previous_match, next_match) if item)
        return (
            f"{trade_date} has no same-date transcript, but adjacent transcript date(s) {matches} "
            "exist; manual session-shift review is needed."
        )
    if should_fetch and corpus_end and corpus_end < trade_date:
        return (
            f"The transcript corpus ends on {corpus_end}, before {trade_date}; fetch the latest "
            "transcript only if the replay date remains after session mapping review."
        )
    if playbook_available:
        return f"{trade_date} has no same-date transcript; classify as {PLAYBOOK_ONLY}."
    return f"{trade_date} has no same-date or adjacent transcript candidate."


def _readiness_reason(
    *,
    text_row_count: int,
    context_rows: int,
    filter_rows: int,
    market_map_rows: int,
    trade_rule_rows: int,
    post_event_rows: int,
) -> str:
    if trade_rule_rows:
        return "STRICT_TRADE_RULE_CANDIDATE_PRESENT"
    if context_rows or filter_rows or market_map_rows:
        return "SAME_DAY_TEXT_IS_CONTEXT_FILTER_OR_MARKET_MAP_ONLY"
    if post_event_rows:
        return "POST_EVENT_COMMENTARY_ONLY"
    if text_row_count == 0:
        return "NO_REVIEWED_TEXT_ROWS_FOR_SAME_DATE_TRANSCRIPTS"
    return "INSUFFICIENT_STRICT_RULE_FIELDS"


def _exact_file_needed_for_action(action: str, item: dict[str, Any]) -> str:
    if action == "REMAP_SESSION_DATE":
        return "No new file until session-date remap is reviewed."
    return _text(item.get("suggested_file_needed")) or "xauusd_spot_<date>_intraday.csv or parquet"


def _where_to_place_for_action(action: str, item: dict[str, Any]) -> str:
    if action == "REMAP_SESSION_DATE":
        return "outputs/current_week_replay_resolved.csv"
    return _text(item.get("where_to_place_file")) or "data/raw/xau/"


def _transcript_action(item: dict[str, Any], *, calendar_issue: bool) -> str:
    if calendar_issue and _bool_value(item.get("possible_session_shift_match")):
        return "REMAP_SESSION_DATE"
    if _bool_value(item.get("should_fetch_transcript")):
        return "FETCH_TRANSCRIPT"
    if _bool_value(item.get("should_use_historical_playbook_overlay")):
        return "USE_PLAYBOOK_OVERLAY"
    if _bool_value(item.get("possible_session_shift_match")):
        return "NEEDS_MANUAL_REVIEW"
    return "FETCH_TRANSCRIPT"


def _transcript_file_needed(action: str) -> str:
    if action == "REMAP_SESSION_DATE":
        return "No new transcript until adjacent session-date match is reviewed."
    if action == "USE_PLAYBOOK_OVERLAY":
        return "No same-day file; use historical playbook overlay as separate context."
    return "same-date transcript text or updated transcript corpus manifest row"


def _same_day_transcript_state_for_resolved(
    readiness: dict[str, Any],
    transcript: dict[str, Any],
    playbook: dict[str, Any],
) -> str:
    if readiness:
        return "SAME_DATE_AVAILABLE"
    if _bool_value(transcript.get("possible_session_shift_match")):
        return "SESSION_SHIFT_MATCH"
    if _playbook_available_for_date(playbook) or _bool_value(
        transcript.get("should_use_historical_playbook_overlay")
    ):
        return PLAYBOOK_ONLY
    return "MISSING_TRANSCRIPT"


def _data_state_for_resolved(replay_row: dict[str, Any], calendar: dict[str, Any]) -> str:
    if _bool_value(calendar.get("likely_calendar_date_issue")):
        return "WEEKEND_ARTIFACT"
    spot = _bool_value(replay_row.get("spot_available")) or _bool_value(
        calendar.get("has_xau_spot_rows")
    )
    basis = _bool_value(replay_row.get("basis_available")) or _bool_value(
        calendar.get("has_basis_rows")
    )
    futures = _bool_value(replay_row.get("futures_available")) or _bool_value(
        calendar.get("has_cme_futures_rows")
    )
    oi = _bool_value(replay_row.get("oi_available")) or _bool_value(
        calendar.get("has_option_oi_rows")
    )
    if spot and basis and futures and oi:
        return "COMPLETE_FOR_PILOT"
    if futures and oi and (not spot or not basis):
        return "NEEDS_SPOT_BASIS"
    return "NEEDS_MANUAL_REVIEW"


def _guru_state_for_resolved(
    readiness: dict[str, Any],
    playbook: dict[str, Any],
    *,
    historical_playbook_default: bool,
) -> str:
    if _bool_value(readiness.get("can_use_as_same_day_filter")):
        return "SAME_DAY_FILTER"
    if _bool_value(readiness.get("can_use_as_same_day_context")):
        return "SAME_DAY_CONTEXT"
    if _playbook_available_for_date(playbook) or historical_playbook_default:
        return "HISTORICAL_PLAYBOOK_OVERLAY"
    return "NO_USABLE_GURU_CONTEXT"


def _resolved_summary(
    *,
    trade_date: str,
    resolved_date: str,
    same_day_state: str,
    data_state: str,
    guru_state: str,
) -> str:
    return (
        f"{trade_date} resolves to {resolved_date}. Data state: {data_state}; "
        f"same-day transcript state: {same_day_state}; guru state: {guru_state}. "
        "Historical playbook context is not a same-day trade rule."
    )


def _calendar_adjacent_available(calendar: dict[str, Any]) -> bool:
    mapping = _text(calendar.get("recommended_session_mapping"))
    return mapping.startswith("REMAP_TO_")


def _playbook_available_for_date(row: dict[str, Any]) -> bool:
    if not row:
        return False
    if "historical_playbook_overlay_state" in row:
        return "AVAILABLE" in _text(row.get("historical_playbook_overlay_state"))
    return any(_bool_value(row.get(column)) for column in row)


def _playbook_all_replay_dates(playbook: pl.DataFrame, resolved: pl.DataFrame) -> bool:
    if resolved.is_empty():
        return False
    if playbook.is_empty():
        return _any_state(resolved, "guru_state", "HISTORICAL_PLAYBOOK_OVERLAY")
    playbook_rows = _rows_by_date(playbook, "trade_date")
    return all(
        _playbook_available_for_date(playbook_rows.get(str(row.get("original_replay_date")), {}))
        for row in resolved.to_dicts()
    )


def _any_same_day_context_or_filter(readiness: pl.DataFrame) -> bool:
    return _any_true(readiness, "can_use_as_same_day_context") or _any_true(
        readiness,
        "can_use_as_same_day_filter",
    )


def _source_file_rows(manifest: pl.DataFrame) -> pl.DataFrame:
    if manifest.is_empty():
        return manifest
    if "notes" in manifest.columns:
        return manifest.filter(pl.col("notes").cast(pl.String).str.contains("source file"))
    return manifest


def _zip_entry_rows(manifest: pl.DataFrame) -> pl.DataFrame:
    if manifest.is_empty() or "notes" not in manifest.columns:
        return manifest.clear()
    return manifest.filter(pl.col("notes").cast(pl.String).str.contains("zip entry"))


def _transcript_date_counts(manifest: pl.DataFrame) -> dict[str, int]:
    counts: dict[str, int] = {}
    if manifest.is_empty():
        return counts
    date_col = _first_existing_column(manifest, ("detected_date", "transcript_date", "date"))
    if date_col is None:
        return counts
    for value in manifest.get_column(date_col).to_list():
        parsed = _date_text(value)
        if parsed:
            counts[parsed] = counts.get(parsed, 0) + 1
    return counts


def _replay_dates(*frames: pl.DataFrame) -> list[str]:
    dates: set[str] = set()
    for frame in frames:
        for column in ("trade_date", "replay_trade_date", "date"):
            if frame.is_empty() or column not in frame.columns:
                continue
            dates.update(_date_text(value) for value in frame.get_column(column).to_list())
    return sorted(date_value for date_value in dates if date_value)


def _date_set_from_frame(frame: pl.DataFrame) -> set[str]:
    dates: set[str] = set()
    if frame.is_empty():
        return dates
    for column in ("trade_date", "date", "timestamp", "asof_timestamp", "datetime"):
        if column not in frame.columns:
            continue
        for value in frame.get_column(column).to_list():
            parsed = _date_text(value)
            if parsed:
                dates.add(parsed)
    return dates


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


def _nearest_date(
    trade_date: str,
    available_dates: list[str],
    *,
    before: bool,
) -> tuple[str, int | None]:
    parsed = _parse_date(trade_date)
    if parsed is None:
        return "", None
    candidates: list[date] = []
    for value in available_dates:
        candidate = _parse_date(value)
        if candidate is None:
            continue
        if before and candidate < parsed:
            candidates.append(candidate)
        elif not before and candidate > parsed:
            candidates.append(candidate)
    if not candidates:
        return "", None
    selected = max(candidates) if before else min(candidates)
    return selected.isoformat(), abs((parsed - selected).days)


def _rows_by_date(frame: pl.DataFrame, column: str) -> dict[str, dict[str, Any]]:
    if frame.is_empty() or column not in frame.columns:
        return {}
    rows: dict[str, dict[str, Any]] = {}
    for row in frame.to_dicts():
        parsed = _date_text(row.get(column))
        if parsed:
            rows[parsed] = row
    return rows


def _group_rows(frame: pl.DataFrame, column: str) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    if frame.is_empty() or column not in frame.columns:
        return groups
    for row in frame.to_dicts():
        parsed = _date_text(row.get(column))
        if parsed:
            groups.setdefault(parsed, []).append(row)
    return groups


def _sorted_rows(frame: pl.DataFrame, column: str) -> list[dict[str, Any]]:
    if frame.is_empty() or column not in frame.columns:
        return []
    return sorted(
        [row for row in frame.to_dicts() if _date_text(row.get(column))],
        key=lambda row: _date_text(row.get(column)),
    )


def _count_true(rows: list[dict[str, Any]], column: str) -> int:
    return sum(1 for row in rows if _bool_value(row.get(column)))


def _any_true(frame: pl.DataFrame, column: str) -> bool:
    if frame.is_empty() or column not in frame.columns:
        return False
    return any(_bool_value(value) for value in frame.get_column(column).to_list())


def _any_state(frame: pl.DataFrame, column: str, state: str) -> bool:
    if frame.is_empty() or column not in frame.columns:
        return False
    return any(_text(value) == state for value in frame.get_column(column).to_list())


def _unique_non_empty(frame: pl.DataFrame, column: str) -> int:
    if frame.is_empty() or column not in frame.columns:
        return 0
    return len({_text(value) for value in frame.get_column(column).to_list() if _text(value)})


def _first_existing_column(frame: pl.DataFrame, candidates: Iterable[str]) -> str | None:
    lookup = {column.lower(): column for column in frame.columns}
    for candidate in candidates:
        if candidate.lower() in lookup:
            return lookup[candidate.lower()]
    return None


def _float_or_zero(value: Any) -> float:
    try:
        if value in (None, ""):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


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


def _date_text(value: Any) -> str:
    text = str(value or "")
    match = re.search(r"20\d{2}-\d{2}-\d{2}", text)
    return match.group(0) if match else ""


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


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
        if path.suffix.lower() == ".parquet":
            return pl.read_parquet(path)
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


def _session_calendar_schema() -> dict[str, Any]:
    return {
        "replay_trade_date": pl.String,
        "day_of_week": pl.String,
        "is_weekend": pl.Boolean,
        "has_cme_futures_rows": pl.Boolean,
        "has_option_oi_rows": pl.Boolean,
        "has_xau_spot_rows": pl.Boolean,
        "has_basis_rows": pl.Boolean,
        "likely_session_date": pl.String,
        "likely_calendar_date_issue": pl.Boolean,
        "possible_previous_trading_day": pl.String,
        "possible_next_trading_day": pl.String,
        "recommended_session_mapping": pl.String,
        "reason_plain_english": pl.String,
    }


def _same_date_transcript_schema() -> dict[str, Any]:
    return {
        "missing_replay_date": pl.String,
        "day_of_week": pl.String,
        "same_date_transcript_count": pl.Int64,
        "nearest_before_transcript_date": pl.String,
        "nearest_before_gap_days": pl.Int64,
        "nearest_after_transcript_date": pl.String,
        "nearest_after_gap_days": pl.Int64,
        "possible_session_shift_match": pl.Boolean,
        "possible_previous_trading_day_transcript": pl.String,
        "possible_next_trading_day_transcript": pl.String,
        "should_fetch_transcript": pl.Boolean,
        "should_use_historical_playbook_overlay": pl.Boolean,
        "reason_plain_english": pl.String,
    }


def _manifest_dedup_schema() -> dict[str, Any]:
    return {
        "total_manifest_rows": pl.Int64,
        "unique_file_hashes": pl.Int64,
        "unique_transcript_dates": pl.Int64,
        "unique_txt_files": pl.Int64,
        "zip_entry_rows": pl.Int64,
        "sidecar_or_duplicate_rows": pl.Int64,
        "duplicate_groups": pl.Int64,
        "clean_transcript_count": pl.Int64,
        "notes": pl.String,
    }


def _same_day_readiness_schema() -> dict[str, Any]:
    return {
        "trade_date": pl.String,
        "transcript_count": pl.Int64,
        "context_rows": pl.Int64,
        "filter_rows": pl.Int64,
        "market_map_rows": pl.Int64,
        "trade_rule_rows": pl.Int64,
        "post_event_rows": pl.Int64,
        "insufficient_context_rows": pl.Int64,
        "can_use_as_same_day_context": pl.Boolean,
        "can_use_as_same_day_filter": pl.Boolean,
        "can_use_as_same_day_trade_rule": pl.Boolean,
        "reason_not_trade_rule": pl.String,
    }


def _missing_action_schema() -> dict[str, Any]:
    return {
        "data_item": pl.String,
        "date": pl.String,
        "original_missing_reason": pl.String,
        "calendar_issue_possible": pl.Boolean,
        "adjacent_date_available": pl.Boolean,
        "final_action": pl.String,
        "exact_file_needed": pl.String,
        "where_to_place_file": pl.String,
        "rerun_command": pl.String,
    }


def _replay_resolved_schema() -> dict[str, Any]:
    return {
        "original_replay_date": pl.String,
        "resolved_session_date": pl.String,
        "same_day_transcript_state": pl.String,
        "data_state": pl.String,
        "guru_state": pl.String,
        "plain_english_summary": pl.String,
    }


def main() -> None:
    """CLI entry point."""

    result = run_session_alignment_resolution_layer()
    print(f"final_recommendation: {result.final_recommendation}")
    print(f"secondary_recommendation: {result.secondary_recommendation}")
    print(f"calendar_rows: {result.session_calendar_audit.height}")
    print(f"action_rows: {result.refined_missing_data_action_plan.height}")


if __name__ == "__main__":
    main()
