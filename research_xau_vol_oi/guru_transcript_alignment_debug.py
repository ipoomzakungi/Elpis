"""Guru transcript alignment debug and historical playbook overlay.

This module is research-only diagnostic tooling. It separates same-date
transcript availability from historical guru playbook context, and it keeps
transcript-derived text away from trade-rule status unless the extracted fields
are explicit enough for review.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable

import polars as pl

from research_xau_vol_oi.guru_logic_knowledge_base import RULE_TAG_TO_LOGIC_TYPE


PLAYBOOK_RULES = (
    "NO_TRADE_DISCIPLINE",
    "BASIS_MAPPING",
    "OI_WALL_ZONE",
    "VOLATILITY_RANGE",
    "OI_FRESHNESS",
    "REJECTION_CONFIRMATION",
    "ACCEPTANCE_CONFIRMATION",
    "SQUEEZE_RISK",
    "PIN_RISK",
    "STALE_DATA_WARNING",
    "NEWS_EVENT_WARNING",
)
OVERLAY_LABEL = "HISTORICAL_PLAYBOOK_OVERLAY"
NO_SAME_DATE_REASON = (
    "Transcript corpus exists, but no same-date transcript is available for this CME replay date."
)
FORBIDDEN_REPORT_PHRASES = (
    "profitable",
    "safe to trade",
    "live ready",
    "live-ready",
    "money-readiness",
)
FINAL_RECOMMENDATIONS = (
    "TRANSCRIPTS_EXIST_BUT_NO_SAME_DATE_CONTEXT",
    "TRANSCRIPTS_EXIST_PLAYBOOK_OVERLAY_READY",
    "SAME_DATE_TRANSCRIPT_ALIGNMENT_READY",
    "TEXT_INTERPRETATION_NEEDS_IMPROVEMENT",
    "FETCH_MISSING_XAU_SPOT_BASIS",
    "FETCH_MORE_TRANSCRIPTS_FOR_CURRENT_WEEK",
)


@dataclass(frozen=True)
class GuruTranscriptAlignmentDebugResult:
    """Generated frames and conservative recommendation for the debug layer."""

    transcript_alignment: pl.DataFrame
    text_interpretation_audit: pl.DataFrame
    playbook_overlay: pl.DataFrame
    playbook_replay: pl.DataFrame
    missing_spot_basis_fetch_plan: pl.DataFrame
    no_guru_context_explanation: str
    final_recommendation: str
    next_data_action: str
    transcript_corpus_exists: bool
    same_date_transcripts_exist_for_current_replay: bool


def run_guru_transcript_alignment_debug_layer(
    *,
    output_dir: str | Path = "outputs",
    transcript_source_roots: Iterable[str | Path] | None = None,
) -> GuruTranscriptAlignmentDebugResult:
    """Run transcript alignment diagnostics and write generated artifacts."""

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    _ = resolve_transcript_source_roots(transcript_source_roots)
    inputs = load_alignment_debug_inputs(output_root)
    result = build_guru_transcript_alignment_debug(inputs)

    result.transcript_alignment.write_csv(output_root / "guru_transcript_alignment_debug.csv")
    (output_root / "guru_transcript_alignment_debug.md").write_text(
        guru_transcript_alignment_debug_markdown(result.transcript_alignment),
        encoding="utf-8",
    )
    result.text_interpretation_audit.write_csv(output_root / "guru_text_interpretation_audit.csv")
    (output_root / "guru_text_interpretation_audit.md").write_text(
        guru_text_interpretation_audit_markdown(result.text_interpretation_audit),
        encoding="utf-8",
    )
    result.playbook_overlay.write_csv(output_root / "guru_playbook_overlay_for_current_week.csv")
    (output_root / "guru_playbook_overlay_for_current_week.md").write_text(
        guru_playbook_overlay_markdown(result.playbook_overlay, result.final_recommendation),
        encoding="utf-8",
    )
    (output_root / "no_guru_context_explanation.md").write_text(
        result.no_guru_context_explanation,
        encoding="utf-8",
    )
    result.playbook_replay.write_csv(output_root / "current_week_cme_guru_playbook_replay.csv")
    (output_root / "current_week_cme_guru_playbook_replay.md").write_text(
        current_week_playbook_replay_markdown(result.playbook_replay),
        encoding="utf-8",
    )
    result.missing_spot_basis_fetch_plan.write_csv(
        output_root / "missing_xau_spot_basis_fetch_plan.csv"
    )
    (output_root / "missing_xau_spot_basis_fetch_plan.md").write_text(
        missing_xau_spot_basis_fetch_plan_markdown(result.missing_spot_basis_fetch_plan),
        encoding="utf-8",
    )
    append_guru_transcript_alignment_sections(output_root / "research_report.md", result)
    return result


def resolve_transcript_source_roots(
    roots: Iterable[str | Path] | None = None,
) -> tuple[Path, ...]:
    """Resolve optional transcript roots from local config/env only.

    The resolved roots are intentionally not written to reports.
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


def load_alignment_debug_inputs(output_root: Path) -> dict[str, pl.DataFrame]:
    """Load optional inputs used by the alignment layer."""

    names = (
        "transcript_corpus_manifest",
        "guru_logic_knowledge_base",
        "guru_logic_priority_rank",
        "current_week_cme_guru_replay",
        "current_week_guru_filter_replay",
        "current_cme_date_usability",
        "cme_validation_grade_days_after_backfill",
        "guru_decision_episodes",
        "guru_full_context_review_suggestions",
    )
    inputs: dict[str, pl.DataFrame] = {}
    for name in names:
        inputs[name] = _load_optional_csv(output_root / f"{name}.csv")
    return inputs


def build_guru_transcript_alignment_debug(
    inputs: dict[str, pl.DataFrame],
) -> GuruTranscriptAlignmentDebugResult:
    """Build all Guru transcript alignment debug outputs from loaded frames."""

    manifest = _frame(inputs, "transcript_corpus_manifest")
    replay = _frame(inputs, "current_week_cme_guru_replay")
    usability = _frame(inputs, "current_cme_date_usability")
    kb = _frame(inputs, "guru_logic_knowledge_base")
    priority = _frame(inputs, "guru_logic_priority_rank")
    filter_replay = _frame(inputs, "current_week_guru_filter_replay")
    validation_after = _frame(inputs, "cme_validation_grade_days_after_backfill")
    episodes = _frame(inputs, "guru_decision_episodes")
    suggestions = _frame(inputs, "guru_full_context_review_suggestions")

    interpretation = build_guru_text_interpretation_audit(
        suggestions=suggestions,
        episodes=episodes,
        knowledge_base=kb,
    )
    alignment = build_transcript_coverage_by_cme_date(
        replay=replay,
        manifest=manifest,
        interpretation=interpretation,
        knowledge_base=kb,
    )
    overlay = build_historical_guru_playbook_overlay(
        replay=replay,
        knowledge_base=kb,
        priority_rank=priority,
        date_usability=usability,
    )
    playbook_replay = build_current_week_playbook_replay(
        replay=replay,
        alignment=alignment,
        overlay=overlay,
        interpretation=interpretation,
        filter_replay=filter_replay,
    )
    missing_plan = build_missing_xau_spot_basis_fetch_plan(replay)
    final_recommendation, next_data_action = choose_alignment_recommendation(
        alignment=alignment,
        manifest=manifest,
        interpretation=interpretation,
        replay=replay,
        missing_spot_basis_plan=missing_plan,
    )
    explanation = no_guru_context_explanation_markdown(
        alignment=alignment,
        manifest=manifest,
        interpretation=interpretation,
        overlay=overlay,
        replay=replay,
        validation_after=validation_after,
        final_recommendation=final_recommendation,
        next_data_action=next_data_action,
    )
    return GuruTranscriptAlignmentDebugResult(
        transcript_alignment=alignment,
        text_interpretation_audit=interpretation,
        playbook_overlay=overlay,
        playbook_replay=playbook_replay,
        missing_spot_basis_fetch_plan=missing_plan,
        no_guru_context_explanation=explanation,
        final_recommendation=final_recommendation,
        next_data_action=next_data_action,
        transcript_corpus_exists=not manifest.is_empty(),
        same_date_transcripts_exist_for_current_replay=_any_true(
            alignment,
            "same_date_transcript_available",
        ),
    )


def build_transcript_coverage_by_cme_date(
    *,
    replay: pl.DataFrame,
    manifest: pl.DataFrame,
    interpretation: pl.DataFrame,
    knowledge_base: pl.DataFrame,
) -> pl.DataFrame:
    """Create one transcript coverage row per current CME replay date."""

    replay_rows = _sorted_replay_rows(replay)
    transcript_dates = _transcript_date_counts(manifest)
    unique_dates = sorted(transcript_dates)
    usable_context_dates = _usable_context_dates(interpretation)
    historical_overlay_available = not knowledge_base.is_empty()
    rows: list[dict[str, Any]] = []
    for replay_row in replay_rows:
        trade_date = str(replay_row.get("trade_date") or "")
        before, before_gap = _nearest_date(trade_date, unique_dates, before=True)
        after, after_gap = _nearest_date(trade_date, unique_dates, before=False)
        same_count = transcript_dates.get(trade_date, 0)
        same_available = same_count > 0
        usable_same_day = trade_date in usable_context_dates
        rows.append(
            {
                "trade_date": trade_date,
                "cme_data_available": _cme_data_available(replay_row),
                "spot_basis_available": _spot_basis_available(replay_row),
                "transcript_same_date_count": same_count,
                "transcript_nearest_before_date": before,
                "transcript_nearest_before_days_gap": before_gap,
                "transcript_nearest_after_date": after,
                "transcript_nearest_after_days_gap": after_gap,
                "same_date_transcript_available": same_available,
                "usable_same_day_guru_context": usable_same_day,
                "historical_playbook_overlay_available": historical_overlay_available,
                "reason_plain_english": _alignment_reason(
                    corpus_exists=not manifest.is_empty(),
                    same_available=same_available,
                    usable_same_day=usable_same_day,
                    historical_overlay_available=historical_overlay_available,
                ),
            }
        )
    return _rows_frame(rows, _alignment_schema()).sort("trade_date")


def build_guru_text_interpretation_audit(
    *,
    suggestions: pl.DataFrame,
    episodes: pl.DataFrame,
    knowledge_base: pl.DataFrame,
) -> pl.DataFrame:
    """Audit whether transcript text became context, filters, maps, or trade rules."""

    rows: list[dict[str, Any]] = []
    if not suggestions.is_empty():
        for row in suggestions.to_dicts():
            rows.append(_interpretation_row_from_suggestion(row))
    elif not episodes.is_empty():
        for row in episodes.to_dicts():
            rows.append(_interpretation_row_from_episode(row))
    elif not knowledge_base.is_empty():
        for row in knowledge_base.to_dicts():
            rows.append(_interpretation_row_from_knowledge_base(row))
    return _rows_frame(rows, _interpretation_schema()).sort(
        ["transcript_date", "transcript_id", "rule_tag"],
    )


def build_historical_guru_playbook_overlay(
    *,
    replay: pl.DataFrame,
    knowledge_base: pl.DataFrame,
    priority_rank: pl.DataFrame,
    date_usability: pl.DataFrame,
) -> pl.DataFrame:
    """Attach historical playbook rules to current-week CME replay dates."""

    replay_rows = _sorted_replay_rows(replay)
    usability_by_date = _rows_by_date(date_usability, "trade_date")
    kb_rows = knowledge_base.to_dicts() if not knowledge_base.is_empty() else []
    priority_rows = priority_rank.to_dicts() if not priority_rank.is_empty() else []
    rows: list[dict[str, Any]] = []
    for replay_row in replay_rows:
        trade_date = str(replay_row.get("trade_date") or "")
        usability = usability_by_date.get(trade_date, {})
        for rule_tag in PLAYBOOK_RULES:
            logic_type = _playbook_logic_type(rule_tag)
            logic_row = _find_playbook_logic_row(rule_tag, logic_type, kb_rows)
            priority_row = _find_playbook_logic_row(rule_tag, logic_type, priority_rows)
            missing = _missing_data_for_rule(rule_tag, replay_row, usability)
            required_available = not missing
            applies = _playbook_applies(rule_tag, replay_row, logic_row, missing)
            rows.append(
                {
                    "trade_date": trade_date,
                    "overlay_label": OVERLAY_LABEL,
                    "rule_tag": rule_tag,
                    "logic_type": logic_type,
                    "applies_to_current_data": applies,
                    "required_data_available": required_available,
                    "missing_data": "|".join(missing),
                    "playbook_interpretation": _playbook_interpretation(
                        rule_tag,
                        required_available=required_available,
                    ),
                    "confidence": _playbook_confidence(
                        logic_row=logic_row,
                        priority_row=priority_row,
                        required_available=required_available,
                    ),
                }
            )
    return _rows_frame(rows, _overlay_schema()).sort(["trade_date", "rule_tag"])


def build_current_week_playbook_replay(
    *,
    replay: pl.DataFrame,
    alignment: pl.DataFrame,
    overlay: pl.DataFrame,
    interpretation: pl.DataFrame,
    filter_replay: pl.DataFrame,
) -> pl.DataFrame:
    """Build one current-week replay row with playbook overlay state."""

    alignment_by_date = _rows_by_date(alignment, "trade_date")
    overlay_rows_by_date = _group_rows(overlay, "trade_date")
    trade_rule_dates = _same_day_trade_rule_dates(interpretation)
    filter_dates = _filter_replay_dates(filter_replay)
    rows: list[dict[str, Any]] = []
    for replay_row in _sorted_replay_rows(replay):
        trade_date = str(replay_row.get("trade_date") or "")
        alignment_row = alignment_by_date.get(trade_date, {})
        date_overlay = overlay_rows_by_date.get(trade_date, [])
        wall_state = _wall_map_state(replay_row)
        spot_state = _spot_basis_state(replay_row)
        same_day_state = _same_day_transcript_state(alignment_row)
        overlay_state = (
            "HISTORICAL_PLAYBOOK_OVERLAY_AVAILABLE"
            if date_overlay
            else "HISTORICAL_PLAYBOOK_OVERLAY_MISSING"
        )
        no_trade_active = _overlay_rule_active(
            date_overlay,
            {"NO_TRADE_DISCIPLINE", "STALE_DATA_WARNING", "NEWS_EVENT_WARNING"},
        ) or trade_date in filter_dates
        market_map_active = _overlay_rule_active(
            date_overlay,
            {
                "BASIS_MAPPING",
                "OI_WALL_ZONE",
                "VOLATILITY_RANGE",
                "OI_FRESHNESS",
                "SQUEEZE_RISK",
                "PIN_RISK",
            },
        )
        trade_rule_active = trade_date in trade_rule_dates
        rows.append(
            {
                "trade_date": trade_date,
                "cme_wall_map_state": wall_state,
                "spot_basis_state": spot_state,
                "iv_state": "IV_AVAILABLE" if _bool_value(replay_row.get("iv_available")) else "IV_MISSING",
                "guru_same_day_transcript_state": same_day_state,
                "historical_playbook_overlay_state": overlay_state,
                "no_trade_filter_playbook_active": no_trade_active,
                "market_map_playbook_active": market_map_active,
                "trade_rule_playbook_active": trade_rule_active,
                "plain_english_summary": _playbook_replay_summary(
                    trade_date=trade_date,
                    wall_state=wall_state,
                    spot_state=spot_state,
                    same_day_state=same_day_state,
                    overlay_state=overlay_state,
                    trade_rule_active=trade_rule_active,
                ),
            }
        )
    return _rows_frame(rows, _playbook_replay_schema()).sort("trade_date")


def build_missing_xau_spot_basis_fetch_plan(replay: pl.DataFrame) -> pl.DataFrame:
    """Build the specific missing XAU spot/basis fetch plan requested by date."""

    rows_by_date = _rows_by_date(replay, "trade_date")
    rows = []
    for trade_date in ("2026-05-16", "2026-05-23"):
        replay_row = rows_by_date.get(trade_date, {})
        missing = []
        if not _bool_value(replay_row.get("spot_available")):
            missing.append("xau_spot_price")
        if not _bool_value(replay_row.get("basis_available")):
            missing.append("basis")
        if not replay_row:
            missing = ["xau_spot_price", "basis"]
        rows.append(
            {
                "trade_date": trade_date,
                "missing_component": "|".join(missing) if missing else "none_detected",
                "suggested_file_needed": f"xauusd_spot_{trade_date}_intraday.csv or parquet",
                "required_columns": "timestamp,open,high,low,close",
                "preferred_granularity": "intraday <=15m preferred; same-session spot snapshot acceptable for debug",
                "where_to_place_file": "data/raw/xau/ or a root configured by XAU_SPOT_DATA_ROOTS",
                "rerun_command": "python -m research_xau_vol_oi.report",
            }
        )
    return _rows_frame(rows, _missing_plan_schema()).sort("trade_date")


def choose_alignment_recommendation(
    *,
    alignment: pl.DataFrame,
    manifest: pl.DataFrame,
    interpretation: pl.DataFrame,
    replay: pl.DataFrame,
    missing_spot_basis_plan: pl.DataFrame,
) -> tuple[str, str]:
    """Choose a conservative final recommendation and next data action."""

    if manifest.is_empty():
        return "FETCH_MORE_TRANSCRIPTS_FOR_CURRENT_WEEK", "FETCH_MORE_TRANSCRIPTS_FOR_CURRENT_WEEK"
    replay_dates = _date_values(replay, "trade_date")
    same_dates = {
        str(row.get("trade_date"))
        for row in alignment.to_dicts()
        if _bool_value(row.get("same_date_transcript_available"))
    }
    if replay_dates and not same_dates:
        return "TRANSCRIPTS_EXIST_PLAYBOOK_OVERLAY_READY", _spot_basis_next_action(
            missing_spot_basis_plan,
        )
    if _missing_after_corpus_end(replay_dates, same_dates, manifest):
        return "FETCH_MORE_TRANSCRIPTS_FOR_CURRENT_WEEK", _spot_basis_next_action(
            missing_spot_basis_plan,
        )
    if not interpretation.is_empty() and not _has_usable_interpretation(interpretation):
        return "TEXT_INTERPRETATION_NEEDS_IMPROVEMENT", _spot_basis_next_action(
            missing_spot_basis_plan,
        )
    if _has_missing_spot_basis(missing_spot_basis_plan):
        return "FETCH_MISSING_XAU_SPOT_BASIS", "FETCH_MISSING_XAU_SPOT_BASIS"
    if same_dates:
        return "SAME_DATE_TRANSCRIPT_ALIGNMENT_READY", "VERIFY_SAME_DAY_CONTEXT_ONLY"
    return "TRANSCRIPTS_EXIST_BUT_NO_SAME_DATE_CONTEXT", "FETCH_MORE_TRANSCRIPTS_FOR_CURRENT_WEEK"


def no_guru_context_explanation_markdown(
    *,
    alignment: pl.DataFrame,
    manifest: pl.DataFrame,
    interpretation: pl.DataFrame,
    overlay: pl.DataFrame,
    replay: pl.DataFrame,
    validation_after: pl.DataFrame,
    final_recommendation: str,
    next_data_action: str,
) -> str:
    """Explain no-guru-context cases in plain English."""

    same_date_count = _true_count(alignment, "same_date_transcript_available")
    missing_dates = [
        str(row.get("trade_date"))
        for row in alignment.to_dicts()
        if not _bool_value(row.get("same_date_transcript_available"))
    ]
    usable_same_day_count = _true_count(alignment, "usable_same_day_guru_context")
    corpus_dates = _date_values(manifest, "detected_date")
    corpus_end = max(corpus_dates) if corpus_dates else ""
    replay_dates = _date_values(replay, "trade_date")
    after_end_missing = [value for value in replay_dates if value > corpus_end and value in missing_dates]
    upgraded = _true_count(validation_after, "day_upgraded")
    lines = [
        "# No Guru Context Explanation",
        "",
        "Research-only diagnostic. Guru text is not converted into a buy/sell instruction.",
        "",
        "## 1. Are transcript files missing?",
        "",
        (
            "- No. The transcript corpus manifest exists and contains "
            f"{manifest.height} rows through {corpus_end}."
            if not manifest.is_empty()
            else "- Yes. No transcript corpus manifest was detected in the output folder."
        ),
        "",
        "## 2. Are same-date transcripts missing?",
        "",
        f"- Same-date transcripts exist for {same_date_count} current replay dates.",
        f"- Missing same-date replay dates: {', '.join(missing_dates) if missing_dates else 'none'}.",
        (
            f"- Dates after the detected corpus end that need a current-week fetch: {', '.join(after_end_missing)}."
            if after_end_missing
            else "- No missing replay date is after the detected corpus end."
        ),
        "",
        "## 3. Are transcripts available but not aligned to CME dates?",
        "",
        "- Yes for dates with nearest transcript before/after but no exact same-date row. "
        "Those dates can use historical playbook context only.",
        "",
        "## 4. Are transcripts available but only usable as historical playbook?",
        "",
        (
            f"- Yes. Historical playbook overlay rows: {overlay.height}. "
            f"Validation-grade dates upgraded after backfill: {upgraded}."
            if not overlay.is_empty()
            else "- No historical playbook overlay could be built from the available knowledge base."
        ),
        "",
        "## 5. Are transcripts available but not specific enough to become trade signals?",
        "",
        f"- Usable same-day guru context rows by date: {usable_same_day_count}.",
        "- A row is not treated as a trade rule unless condition, level, direction, target, "
        "and invalidation fields are clear and the text is not post-event commentary.",
        f"- Strict trade-rule rows detected: {_true_count(interpretation, 'usable_as_trade_rule')}.",
        "",
        "## 6. What exact data or transcript fetch is needed next?",
        "",
        "- Fetch same-date transcript(s) for current-week replay dates that are missing after the "
        "detected corpus end.",
        "- Supply XAU spot OHLC or dated spot snapshots for 2026-05-16 and 2026-05-23 so basis "
        "mapping can be rerun for those CME dates.",
        "- Re-run `python -m research_xau_vol_oi.report` after placing files under approved "
        "relative data roots.",
        "",
        f"Final recommendation: `{final_recommendation}`",
        f"Next data action: `{next_data_action}`",
    ]
    return _safe_report("\n".join(_redact_text(line) for line in lines))


def guru_transcript_alignment_debug_markdown(frame: pl.DataFrame) -> str:
    """Render transcript coverage debug rows."""

    lines = [
        "# Guru Transcript Alignment Debug",
        "",
        "This separates same-date transcript availability from historical playbook context.",
        "",
        _frame_markdown(frame),
    ]
    return _safe_report("\n".join(lines))


def guru_text_interpretation_audit_markdown(frame: pl.DataFrame) -> str:
    """Render the interpretation audit."""

    lines = [
        "# Guru Text Interpretation Audit",
        "",
        "Transcript-derived text is classified as context, market map, filter, or strict trade-rule candidate.",
        "Strict trade-rule status requires clear condition, level, direction, target, and invalidation.",
        "",
        _frame_markdown(frame),
    ]
    return _safe_report("\n".join(lines))


def guru_playbook_overlay_markdown(frame: pl.DataFrame, final_recommendation: str) -> str:
    """Render historical playbook overlay rows."""

    lines = [
        "# Guru Playbook Overlay For Current Week",
        "",
        f"- Overlay label: `{OVERLAY_LABEL}`",
        f"- Final recommendation: `{final_recommendation}`",
        "- This is not a same-day guru signal.",
        "",
        _frame_markdown(frame),
    ]
    return _safe_report("\n".join(lines))


def current_week_playbook_replay_markdown(frame: pl.DataFrame) -> str:
    """Render current-week replay with historical playbook state."""

    lines = [
        "# Current-Week CME/Guru Playbook Replay",
        "",
        "Historical playbook overlay is shown separately from same-day transcript signal state.",
        "",
        _frame_markdown(frame),
    ]
    return _safe_report("\n".join(lines))


def missing_xau_spot_basis_fetch_plan_markdown(frame: pl.DataFrame) -> str:
    """Render missing XAU spot/basis fetch plan."""

    lines = [
        "# Missing XAU Spot/Basis Fetch Plan",
        "",
        "Place files under relative research data roots only; do not add private absolute paths.",
        "",
        _frame_markdown(frame),
    ]
    return _safe_report("\n".join(lines))


def guru_transcript_alignment_report_lines(
    result: GuruTranscriptAlignmentDebugResult | None,
) -> list[str]:
    """Return report sections for the main research report."""

    if result is None:
        return ["Guru transcript alignment debug layer was not run."]
    return [
        "## Guru Transcript Alignment Debug",
        "",
        f"- Transcript corpus exists: `{str(result.transcript_corpus_exists).lower()}`",
        "- Same-date transcripts exist for current replay dates: "
        f"`{str(result.same_date_transcripts_exist_for_current_replay).lower()}`",
        f"- Final recommendation: `{result.final_recommendation}`",
        f"- Next data action: `{result.next_data_action}`",
        "",
        _frame_markdown(result.transcript_alignment),
        "",
        "## Why Some Dates Show No Guru Context",
        "",
        *no_guru_context_summary_lines(result.transcript_alignment),
        "",
        "## Text Interpretation vs Trade Signal",
        "",
        _frame_markdown(_interpretation_summary(result.text_interpretation_audit)),
        "",
        "## Historical Guru Playbook Overlay",
        "",
        "- Overlay rows are labeled `HISTORICAL_PLAYBOOK_OVERLAY`; they are not same-day signals.",
        _frame_markdown(_overlay_summary(result.playbook_overlay)),
        "",
        "## Missing XAU Spot/Basis Fetch Plan",
        "",
        _frame_markdown(result.missing_spot_basis_fetch_plan),
        "",
        "## Current-Week Replay With Playbook Overlay",
        "",
        _frame_markdown(result.playbook_replay),
    ]


def no_guru_context_summary_lines(alignment: pl.DataFrame) -> list[str]:
    """Return short no-context summary lines for report embedding."""

    if alignment.is_empty():
        return ["No current replay dates were available for transcript alignment."]
    missing = [
        str(row.get("trade_date"))
        for row in alignment.to_dicts()
        if not _bool_value(row.get("same_date_transcript_available"))
    ]
    not_interpreted = [
        str(row.get("trade_date"))
        for row in alignment.to_dicts()
        if _bool_value(row.get("same_date_transcript_available"))
        and not _bool_value(row.get("usable_same_day_guru_context"))
    ]
    return [
        "- Dates with no same-date transcript: " + (", ".join(missing) if missing else "none"),
        "- Dates with transcript present but no usable same-day logic: "
        + (", ".join(not_interpreted) if not_interpreted else "none"),
        "- Historical playbook overlay remains available when the knowledge base has extracted rules.",
    ]


def append_guru_transcript_alignment_sections(
    path: Path,
    result: GuruTranscriptAlignmentDebugResult,
) -> None:
    """Append or replace alignment sections in a generated research report."""

    marker = "\n## Guru Transcript Alignment Debug\n"
    section = "\n".join(guru_transcript_alignment_report_lines(result))
    existing = path.read_text(encoding="utf-8") if path.exists() else "# XAU/USD Vol-OI Research Report\n"
    if marker in existing:
        existing = existing.split(marker, 1)[0].rstrip()
    _safe_report(section)
    path.write_text(existing.rstrip() + "\n\n" + section + "\n", encoding="utf-8")


def _interpretation_row_from_suggestion(row: dict[str, Any]) -> dict[str, Any]:
    rule_tag = _text(row.get("rule_tag")).upper()
    logic_type = _logic_type(row, rule_tag)
    has_condition = _bool_value(row.get("has_clear_condition")) or bool(
        _text(row.get("condition_text") or row.get("condition")),
    )
    has_level = _bool_value(row.get("has_clear_level")) or _has_numeric_level(row)
    has_direction = _bool_value(row.get("has_direction_bias")) or _has_direction(row)
    has_target = _bool_value(row.get("has_clear_target")) or bool(_text(row.get("target_text")))
    has_invalidation = _bool_value(row.get("has_clear_invalidation")) or bool(
        _text(row.get("invalidation_rule")),
    )
    usable_as_filter = _bool_value(row.get("usable_as_filter"))
    usable_as_market_map = _bool_value(row.get("usable_as_market_map"))
    usable_as_context = _bool_value(row.get("usable_as_context")) or usable_as_filter or usable_as_market_map
    post_event = not _bool_value(row.get("is_pre_event_logic")) or "POST_EVENT" in _text(
        row.get("rule_type"),
    ).upper()
    usable_as_trade_rule = (
        _bool_value(row.get("usable_as_trade_rule"))
        and has_condition
        and has_level
        and has_direction
        and has_target
        and has_invalidation
        and not post_event
    )
    return {
        "transcript_id": _text(row.get("transcript_id")),
        "transcript_date": _date_text(row.get("transcript_date")),
        "rule_tag": rule_tag or logic_type,
        "logic_type": logic_type,
        "suggested_decision": _text(row.get("suggested_decision")),
        "has_condition": has_condition,
        "has_level": has_level,
        "has_direction": has_direction,
        "has_target": has_target,
        "has_invalidation": has_invalidation,
        "usable_as_context": usable_as_context,
        "usable_as_market_map": usable_as_market_map,
        "usable_as_filter": usable_as_filter,
        "usable_as_trade_rule": usable_as_trade_rule,
        "reason_not_trade_signal": _reason_not_trade_signal(
            post_event=post_event,
            usable_as_filter=usable_as_filter,
            usable_as_market_map=usable_as_market_map,
            usable_as_context=usable_as_context,
            has_condition=has_condition,
            has_level=has_level,
            has_direction=has_direction,
            has_target=has_target,
            has_invalidation=has_invalidation,
            usable_as_trade_rule=usable_as_trade_rule,
            quality_text=_text(row.get("quality_flags")),
        ),
    }


def _interpretation_row_from_episode(row: dict[str, Any]) -> dict[str, Any]:
    rule_tag = _text(row.get("rule_tag")).upper()
    logic_type = _logic_type(row, rule_tag)
    thesis_type = _text(row.get("thesis_type")).upper()
    has_condition = bool(_text(row.get("condition_text")))
    has_level = bool(_text(row.get("mentioned_levels"))) or _float_or_none(
        row.get("expected_from_level"),
    ) is not None
    has_direction = _text(row.get("expected_direction")).upper() not in {"", "NONE"}
    has_target = _float_or_none(row.get("expected_to_level")) is not None or bool(
        _text(row.get("target_text")),
    )
    has_invalidation = _float_or_none(row.get("invalidation_level")) is not None or bool(
        _text(row.get("invalidation_rule")),
    )
    post_event = _bool_value(row.get("post_event_risk")) or thesis_type == "POST_EVENT_COMMENTARY"
    usable_as_filter = thesis_type in {"NO_TRADE", "WATCH_ONLY"} or logic_type == "NO_TRADE_FILTER"
    usable_as_market_map = thesis_type in {
        "CONTEXT_ONLY",
        "PIN_OR_MAGNET",
        "SQUEEZE_CONTINUATION",
        "RANGE_ROTATION",
    } or logic_type in {"MARKET_MAP", "OI_WALL_ZONE", "VOLATILITY_RANGE", "BASIS_MAPPING"}
    usable_as_context = usable_as_filter or usable_as_market_map or _bool_value(
        row.get("likely_context_only"),
    )
    usable_as_trade_rule = (
        not post_event
        and not usable_as_filter
        and has_condition
        and has_level
        and has_direction
        and has_target
        and has_invalidation
    )
    return {
        "transcript_id": _text(row.get("transcript_id")),
        "transcript_date": _date_text(row.get("transcript_date")),
        "rule_tag": rule_tag or logic_type,
        "logic_type": logic_type,
        "suggested_decision": _text(row.get("episode_review_status")) or "EPISODE_PREVIEW",
        "has_condition": has_condition,
        "has_level": has_level,
        "has_direction": has_direction,
        "has_target": has_target,
        "has_invalidation": has_invalidation,
        "usable_as_context": usable_as_context,
        "usable_as_market_map": usable_as_market_map,
        "usable_as_filter": usable_as_filter,
        "usable_as_trade_rule": usable_as_trade_rule,
        "reason_not_trade_signal": _reason_not_trade_signal(
            post_event=post_event,
            usable_as_filter=usable_as_filter,
            usable_as_market_map=usable_as_market_map,
            usable_as_context=usable_as_context,
            has_condition=has_condition,
            has_level=has_level,
            has_direction=has_direction,
            has_target=has_target,
            has_invalidation=has_invalidation,
            usable_as_trade_rule=usable_as_trade_rule,
            quality_text=_text(row.get("quality_label")),
        ),
    }


def _interpretation_row_from_knowledge_base(row: dict[str, Any]) -> dict[str, Any]:
    logic_type = _text(row.get("logic_type")).upper() or "UNTESTABLE"
    return {
        "transcript_id": _text(row.get("representative_transcript_ids")).split("|")[0],
        "transcript_date": _date_text(row.get("last_seen_date")),
        "rule_tag": _rule_tag_from_logic_type(logic_type),
        "logic_type": logic_type,
        "suggested_decision": _text(row.get("validation_status")),
        "has_condition": logic_type not in {"UNTESTABLE", "POST_EVENT_COMMENTARY"},
        "has_level": logic_type in {"BASIS_MAPPING", "OI_WALL_ZONE", "VOLATILITY_RANGE"},
        "has_direction": False,
        "has_target": False,
        "has_invalidation": False,
        "usable_as_context": logic_type not in {"UNTESTABLE", "POST_EVENT_COMMENTARY"},
        "usable_as_market_map": logic_type
        in {"BASIS_MAPPING", "OI_WALL_ZONE", "VOLATILITY_RANGE", "MARKET_MAP"},
        "usable_as_filter": logic_type == "NO_TRADE_FILTER",
        "usable_as_trade_rule": False,
        "reason_not_trade_signal": "FILTER_ONLY"
        if logic_type == "NO_TRADE_FILTER"
        else "MARKET_MAP_ONLY"
        if logic_type in {"BASIS_MAPPING", "OI_WALL_ZONE", "VOLATILITY_RANGE", "MARKET_MAP"}
        else "CONTEXT_ONLY",
    }


def _reason_not_trade_signal(
    *,
    post_event: bool,
    usable_as_filter: bool,
    usable_as_market_map: bool,
    usable_as_context: bool,
    has_condition: bool,
    has_level: bool,
    has_direction: bool,
    has_target: bool,
    has_invalidation: bool,
    usable_as_trade_rule: bool,
    quality_text: str,
) -> str:
    if usable_as_trade_rule:
        return ""
    if post_event:
        return "POST_EVENT_COMMENTARY"
    if usable_as_filter:
        return "FILTER_ONLY"
    if usable_as_market_map:
        return "MARKET_MAP_ONLY"
    if not has_condition:
        return "NO_CONDITION"
    if not has_level:
        return "NO_LEVEL"
    if not has_direction:
        return "CONTEXT_ONLY" if usable_as_context else "NEEDS_MORE_CONTEXT"
    if not has_target:
        return "NO_TARGET"
    if not has_invalidation:
        return "NO_INVALIDATION"
    if "WEAK" in quality_text.upper() or "ARTIFACT" in quality_text.upper():
        return "TEXT_EXTRACTION_WEAK"
    return "NEEDS_MORE_CONTEXT"


def _logic_type(row: dict[str, Any], rule_tag: str) -> str:
    explicit = _text(row.get("suggested_guru_logic_type") or row.get("logic_type")).upper()
    if explicit and explicit != "UNTESTABLE_OPINION":
        return explicit
    if rule_tag in RULE_TAG_TO_LOGIC_TYPE:
        return RULE_TAG_TO_LOGIC_TYPE[rule_tag]
    rule_type = _text(row.get("rule_type")).upper()
    action_bias = _text(row.get("action_bias")).upper()
    if "POST_EVENT" in rule_type:
        return "POST_EVENT_COMMENTARY"
    if "NO_TRADE" in action_bias or "NO_TRADE" in rule_tag:
        return "NO_TRADE_FILTER"
    if "REJECTION" in rule_tag:
        return "REJECTION_CONFIRMATION"
    if "ACCEPTANCE" in rule_tag:
        return "ACCEPTANCE_CONFIRMATION"
    return "MARKET_MAP" if action_bias in {"WATCH_ONLY", "NONE", ""} else "ENTRY_TRIGGER"


def _playbook_logic_type(rule_tag: str) -> str:
    mapping = {
        "NO_TRADE_DISCIPLINE": "NO_TRADE_FILTER",
        "BASIS_MAPPING": "BASIS_MAPPING",
        "OI_WALL_ZONE": "OI_WALL_ZONE",
        "VOLATILITY_RANGE": "VOLATILITY_RANGE",
        "OI_FRESHNESS": "OI_FRESHNESS",
        "REJECTION_CONFIRMATION": "REJECTION_CONFIRMATION",
        "ACCEPTANCE_CONFIRMATION": "ACCEPTANCE_CONFIRMATION",
        "SQUEEZE_RISK": "SQUEEZE_RISK",
        "PIN_RISK": "PIN_RISK",
        "STALE_DATA_WARNING": "NO_TRADE_FILTER",
        "NEWS_EVENT_WARNING": "NO_TRADE_FILTER",
    }
    return mapping[rule_tag]


def _find_playbook_logic_row(
    rule_tag: str,
    logic_type: str,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    rule_term = rule_tag.lower().replace("_", " ")
    for row in rows:
        row_logic = _text(row.get("logic_type")).upper()
        row_id = _text(row.get("logic_id")).lower()
        row_name = _text(row.get("logic_name")).lower()
        if rule_tag.lower() in row_id or rule_term in row_name:
            return row
        if rule_tag == "BASIS_MAPPING" and "basis" in row_name:
            return row
        if rule_tag == "OI_WALL_ZONE" and ("oi_wall" in row_id or "open-interest" in row_name):
            return row
        if rule_tag == "VOLATILITY_RANGE" and row_logic == "VOLATILITY_RANGE":
            return row
        if rule_tag == "NO_TRADE_DISCIPLINE" and "no_trade" in row_id:
            return row
        if rule_tag == "STALE_DATA_WARNING" and "stale" in row_name:
            return row
        if rule_tag == "NEWS_EVENT_WARNING" and ("news" in row_name or "macro" in row_name):
            return row
        if row_logic == logic_type and rule_tag not in {"STALE_DATA_WARNING", "NEWS_EVENT_WARNING"}:
            return row
    return {}


def _missing_data_for_rule(
    rule_tag: str,
    replay_row: dict[str, Any],
    usability_row: dict[str, Any],
) -> list[str]:
    missing = []
    if rule_tag == "BASIS_MAPPING":
        if not _bool_value(replay_row.get("spot_available")):
            missing.append("xau_spot_price")
        if not _bool_value(replay_row.get("futures_available")):
            missing.append("gc_futures_price")
        if not _bool_value(replay_row.get("basis_available")):
            missing.append("basis")
    elif rule_tag == "OI_WALL_ZONE":
        if not _bool_value(replay_row.get("oi_available")):
            missing.append("option_oi_by_strike")
        if not _spot_basis_available(replay_row):
            missing.append("spot_basis_mapping")
    elif rule_tag == "VOLATILITY_RANGE":
        if not _bool_value(replay_row.get("iv_available")):
            missing.append("option_iv")
        if not _bool_value(replay_row.get("spot_available")):
            missing.append("xau_spot_price")
    elif rule_tag == "OI_FRESHNESS":
        if not (
            _bool_value(replay_row.get("oi_change_available"))
            or _bool_value(replay_row.get("option_volume_available"))
        ):
            missing.append("oi_change_or_option_volume")
    elif rule_tag in {"REJECTION_CONFIRMATION", "ACCEPTANCE_CONFIRMATION"}:
        if not _bool_value(replay_row.get("oi_available")):
            missing.append("option_oi_by_strike")
        if not _spot_basis_available(replay_row):
            missing.append("spot_basis_mapping")
    elif rule_tag in {"SQUEEZE_RISK", "PIN_RISK"}:
        if not _bool_value(replay_row.get("oi_available")):
            missing.append("option_oi_by_strike")
    elif rule_tag == "NEWS_EVENT_WARNING":
        if not _bool_value(usability_row.get("has_macro_event_flag")):
            missing.append("macro_event_flag")
    return missing


def _playbook_applies(
    rule_tag: str,
    replay_row: dict[str, Any],
    logic_row: dict[str, Any],
    missing: list[str],
) -> bool:
    if not logic_row:
        return False
    if rule_tag in {"STALE_DATA_WARNING", "NEWS_EVENT_WARNING"}:
        return bool(missing)
    if rule_tag == "NO_TRADE_DISCIPLINE":
        return True
    if rule_tag == "OI_FRESHNESS":
        return not missing or _bool_value(replay_row.get("no_trade_filter_active"))
    return not missing


def _playbook_interpretation(rule_tag: str, *, required_available: bool) -> str:
    interpretations = {
        "NO_TRADE_DISCIPLINE": "Use as a historical filter/playbook reminder when context is unclear.",
        "BASIS_MAPPING": "Map futures strike levels into spot-equivalent levels only when basis is available.",
        "OI_WALL_ZONE": "Treat high open-interest strikes as market-map zones, not orders.",
        "VOLATILITY_RANGE": "Use IV/range context to frame stretch and containment.",
        "OI_FRESHNESS": "Check OI change or option volume before trusting a wall as fresh.",
        "REJECTION_CONFIRMATION": "A rejection idea needs observed rejection at a level before review.",
        "ACCEPTANCE_CONFIRMATION": "An acceptance idea needs observed acceptance beyond a level before review.",
        "SQUEEZE_RISK": "Low-OI gaps can be tracked as squeeze-risk context.",
        "PIN_RISK": "Near-expiry concentration can be tracked as pin-risk context.",
        "STALE_DATA_WARNING": "Missing freshness fields should keep the rule in warning/filter mode.",
        "NEWS_EVENT_WARNING": "Missing macro flags should keep the rule in warning/filter mode.",
    }
    suffix = " Required data is available." if required_available else " Required data is missing."
    return interpretations[rule_tag] + suffix


def _playbook_confidence(
    *,
    logic_row: dict[str, Any],
    priority_row: dict[str, Any],
    required_available: bool,
) -> str:
    if not logic_row:
        return "DEBUG_ONLY"
    count = int(_float_or_none(logic_row.get("transcript_count")) or 0)
    score = _float_or_none(priority_row.get("priority_score"))
    if required_available and (count >= 20 or (score is not None and score >= 0.35)):
        return "HIGH"
    if count >= 2:
        return "MEDIUM" if required_available else "LOW"
    return "DEBUG_ONLY"


def _alignment_reason(
    *,
    corpus_exists: bool,
    same_available: bool,
    usable_same_day: bool,
    historical_overlay_available: bool,
) -> str:
    if not corpus_exists:
        return "Transcript corpus manifest is missing; fetch or rebuild the corpus manifest."
    if not same_available:
        return NO_SAME_DATE_REASON
    if usable_same_day:
        return "Same-date transcript and interpreted guru context are available for this CME replay date."
    if historical_overlay_available:
        return "Same-date transcript exists, but active logic is only available as historical playbook context."
    return "Same-date transcript exists, but text interpretation did not produce usable guru context."


def _cme_data_available(row: dict[str, Any]) -> bool:
    return any(
        _bool_value(row.get(column))
        for column in ("oi_available", "iv_available", "futures_available")
    )


def _spot_basis_available(row: dict[str, Any]) -> bool:
    return _bool_value(row.get("spot_available")) and _bool_value(row.get("basis_available"))


def _transcript_date_counts(manifest: pl.DataFrame) -> dict[str, int]:
    counts: dict[str, int] = {}
    if manifest.is_empty():
        return counts
    date_column = _first_existing_column(manifest, ("detected_date", "transcript_date", "date"))
    if not date_column:
        return counts
    for value in manifest.get_column(date_column).to_list():
        parsed = _date_text(value)
        if parsed:
            counts[parsed] = counts.get(parsed, 0) + 1
    return counts


def _usable_context_dates(interpretation: pl.DataFrame) -> set[str]:
    dates = set()
    if interpretation.is_empty():
        return dates
    for row in interpretation.to_dicts():
        if any(
            _bool_value(row.get(column))
            for column in (
                "usable_as_context",
                "usable_as_market_map",
                "usable_as_filter",
                "usable_as_trade_rule",
            )
        ):
            date_text = _date_text(row.get("transcript_date"))
            if date_text:
                dates.add(date_text)
    return dates


def _same_day_trade_rule_dates(interpretation: pl.DataFrame) -> set[str]:
    return {
        _date_text(row.get("transcript_date"))
        for row in interpretation.to_dicts()
        if _bool_value(row.get("usable_as_trade_rule")) and _date_text(row.get("transcript_date"))
    }


def _nearest_date(
    trade_date: str,
    available_dates: list[str],
    *,
    before: bool,
) -> tuple[str, int | None]:
    parsed = _parse_date(trade_date)
    if parsed is None:
        return "", None
    candidates = []
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


def _wall_map_state(row: dict[str, Any]) -> str:
    if not _bool_value(row.get("oi_available")):
        return "NO_CME_WALL_MAP"
    wall_type = _text(row.get("wall_type")).upper()
    if wall_type == "SPOT_EQUIVALENT_LEVEL":
        return "SPOT_EQUIVALENT_WALL_MAP"
    if wall_type == "FUTURES_STRIKE_LEVEL":
        return "FUTURES_STRIKE_WALL_MAP"
    return "CME_WALL_MAP_UNKNOWN"


def _spot_basis_state(row: dict[str, Any]) -> str:
    if _spot_basis_available(row):
        return "SPOT_BASIS_AVAILABLE"
    if _bool_value(row.get("spot_available")) and not _bool_value(row.get("basis_available")):
        return "SPOT_AVAILABLE_BASIS_MISSING"
    if not _bool_value(row.get("spot_available")) and _bool_value(row.get("basis_available")):
        return "BASIS_AVAILABLE_SPOT_MISSING"
    return "SPOT_BASIS_MISSING"


def _same_day_transcript_state(alignment_row: dict[str, Any]) -> str:
    if not _bool_value(alignment_row.get("same_date_transcript_available")):
        return "NO_SAME_DAY_TRANSCRIPT"
    if _bool_value(alignment_row.get("usable_same_day_guru_context")):
        return "SAME_DAY_CONTEXT_AVAILABLE"
    return "SAME_DAY_TRANSCRIPT_NOT_INTERPRETED"


def _playbook_replay_summary(
    *,
    trade_date: str,
    wall_state: str,
    spot_state: str,
    same_day_state: str,
    overlay_state: str,
    trade_rule_active: bool,
) -> str:
    trade_text = "a strict same-day trade-rule candidate is present" if trade_rule_active else (
        "no strict trade-rule signal is active"
    )
    return (
        f"{trade_date}: {wall_state}; {spot_state}; {same_day_state}; "
        f"{overlay_state}. Historical rules are context/filter overlays only; {trade_text}."
    )


def _overlay_rule_active(rows: list[dict[str, Any]], tags: set[str]) -> bool:
    return any(
        _text(row.get("rule_tag")).upper() in tags
        and _bool_value(row.get("applies_to_current_data"))
        for row in rows
    )


def _filter_replay_dates(frame: pl.DataFrame) -> set[str]:
    if frame.is_empty():
        return set()
    return {
        _date_text(row.get("trade_date"))
        for row in frame.to_dicts()
        if _bool_value(row.get("would_block_trade")) and _date_text(row.get("trade_date"))
    }


def _missing_after_corpus_end(
    replay_dates: set[str],
    same_dates: set[str],
    manifest: pl.DataFrame,
) -> bool:
    corpus_dates = _date_values(manifest, "detected_date")
    if not corpus_dates:
        return False
    corpus_end = max(corpus_dates)
    return any(replay_date > corpus_end and replay_date not in same_dates for replay_date in replay_dates)


def _has_usable_interpretation(frame: pl.DataFrame) -> bool:
    return any(
        _bool_value(row.get(column))
        for row in frame.to_dicts()
        for column in (
            "usable_as_context",
            "usable_as_market_map",
            "usable_as_filter",
            "usable_as_trade_rule",
        )
    )


def _has_missing_spot_basis(plan: pl.DataFrame) -> bool:
    if plan.is_empty():
        return False
    return any(
        _text(row.get("missing_component")) not in {"", "none_detected"}
        for row in plan.to_dicts()
    )


def _spot_basis_next_action(plan: pl.DataFrame) -> str:
    return "FETCH_MISSING_XAU_SPOT_BASIS" if _has_missing_spot_basis(plan) else (
        "VERIFY_TRANSCRIPT_ALIGNMENT"
    )


def _interpretation_summary(frame: pl.DataFrame) -> pl.DataFrame:
    if frame.is_empty():
        return frame
    rows = []
    for reason, group in _group_rows(frame, "reason_not_trade_signal").items():
        rows.append(
            {
                "reason_not_trade_signal": reason or "STRICT_TRADE_RULE",
                "row_count": len(group),
                "usable_as_context_count": sum(
                    1 for row in group if _bool_value(row.get("usable_as_context"))
                ),
                "usable_as_filter_count": sum(
                    1 for row in group if _bool_value(row.get("usable_as_filter"))
                ),
                "usable_as_trade_rule_count": sum(
                    1 for row in group if _bool_value(row.get("usable_as_trade_rule"))
                ),
            }
        )
    return _rows_frame(
        rows,
        {
            "reason_not_trade_signal": pl.String,
            "row_count": pl.Int64,
            "usable_as_context_count": pl.Int64,
            "usable_as_filter_count": pl.Int64,
            "usable_as_trade_rule_count": pl.Int64,
        },
    ).sort("reason_not_trade_signal")


def _overlay_summary(frame: pl.DataFrame) -> pl.DataFrame:
    if frame.is_empty():
        return frame
    rows = []
    for rule_tag, group in _group_rows(frame, "rule_tag").items():
        rows.append(
            {
                "rule_tag": rule_tag,
                "dates_applied": sum(
                    1 for row in group if _bool_value(row.get("applies_to_current_data"))
                ),
                "dates_missing_required_data": sum(
                    1 for row in group if not _bool_value(row.get("required_data_available"))
                ),
                "highest_confidence": _highest_confidence(row.get("confidence") for row in group),
            }
        )
    return _rows_frame(
        rows,
        {
            "rule_tag": pl.String,
            "dates_applied": pl.Int64,
            "dates_missing_required_data": pl.Int64,
            "highest_confidence": pl.String,
        },
    ).sort("rule_tag")


def _highest_confidence(values: Iterable[Any]) -> str:
    order = {"DEBUG_ONLY": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}
    best = "DEBUG_ONLY"
    for value in values:
        text = _text(value).upper()
        if order.get(text, -1) > order[best]:
            best = text
    return best


def _sorted_replay_rows(replay: pl.DataFrame) -> list[dict[str, Any]]:
    if replay.is_empty():
        return []
    rows = [row for row in replay.to_dicts() if row.get("trade_date")]
    return sorted(rows, key=lambda row: str(row.get("trade_date")))


def _rows_by_date(frame: pl.DataFrame, column: str) -> dict[str, dict[str, Any]]:
    if frame.is_empty() or column not in frame.columns:
        return {}
    return {str(row.get(column)): row for row in frame.to_dicts() if row.get(column)}


def _group_rows(frame: pl.DataFrame, column: str) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    if frame.is_empty() or column not in frame.columns:
        return groups
    for row in frame.to_dicts():
        groups.setdefault(str(row.get(column) or ""), []).append(row)
    return groups


def _date_values(frame: pl.DataFrame, column: str) -> set[str]:
    if frame.is_empty() or column not in frame.columns:
        return set()
    return {
        parsed
        for value in frame.get_column(column).to_list()
        if (parsed := _date_text(value))
    }


def _first_existing_column(frame: pl.DataFrame, candidates: Iterable[str]) -> str | None:
    lower_lookup = {column.lower(): column for column in frame.columns}
    for candidate in candidates:
        if candidate.lower() in lower_lookup:
            return lower_lookup[candidate.lower()]
    return None


def _has_numeric_level(row: dict[str, Any]) -> bool:
    text = " ".join(
        _text(row.get(column))
        for column in (
            "mentioned_levels",
            "extracted_numeric_levels",
            "source_excerpt",
            "normalized_english_summary",
        )
    )
    return bool(re.search(r"\b[12]?\d{3}(?:\.\d+)?\b", text))


def _has_direction(row: dict[str, Any]) -> bool:
    text = " ".join(
        _text(row.get(column))
        for column in (
            "action_bias",
            "mentioned_direction",
            "expected_direction",
            "normalized_english_summary",
        )
    ).upper()
    return any(token in text for token in ("LONG", "SHORT", "BUY", "SELL", "FADE", "BREAK"))


def _rule_tag_from_logic_type(logic_type: str) -> str:
    for rule_tag, mapped in RULE_TAG_TO_LOGIC_TYPE.items():
        if mapped == logic_type:
            return rule_tag
    return logic_type


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed else None


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


def _true_count(frame: pl.DataFrame, column: str) -> int:
    if frame.is_empty() or column not in frame.columns:
        return 0
    return sum(1 for value in frame.get_column(column).to_list() if _bool_value(value))


def _any_true(frame: pl.DataFrame, column: str) -> bool:
    return _true_count(frame, column) > 0


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


def _load_optional_csv(path: Path) -> pl.DataFrame:
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
    return text


def _alignment_schema() -> dict[str, Any]:
    return {
        "trade_date": pl.String,
        "cme_data_available": pl.Boolean,
        "spot_basis_available": pl.Boolean,
        "transcript_same_date_count": pl.Int64,
        "transcript_nearest_before_date": pl.String,
        "transcript_nearest_before_days_gap": pl.Int64,
        "transcript_nearest_after_date": pl.String,
        "transcript_nearest_after_days_gap": pl.Int64,
        "same_date_transcript_available": pl.Boolean,
        "usable_same_day_guru_context": pl.Boolean,
        "historical_playbook_overlay_available": pl.Boolean,
        "reason_plain_english": pl.String,
    }


def _interpretation_schema() -> dict[str, Any]:
    return {
        "transcript_id": pl.String,
        "transcript_date": pl.String,
        "rule_tag": pl.String,
        "logic_type": pl.String,
        "suggested_decision": pl.String,
        "has_condition": pl.Boolean,
        "has_level": pl.Boolean,
        "has_direction": pl.Boolean,
        "has_target": pl.Boolean,
        "has_invalidation": pl.Boolean,
        "usable_as_context": pl.Boolean,
        "usable_as_market_map": pl.Boolean,
        "usable_as_filter": pl.Boolean,
        "usable_as_trade_rule": pl.Boolean,
        "reason_not_trade_signal": pl.String,
    }


def _overlay_schema() -> dict[str, Any]:
    return {
        "trade_date": pl.String,
        "overlay_label": pl.String,
        "rule_tag": pl.String,
        "logic_type": pl.String,
        "applies_to_current_data": pl.Boolean,
        "required_data_available": pl.Boolean,
        "missing_data": pl.String,
        "playbook_interpretation": pl.String,
        "confidence": pl.String,
    }


def _playbook_replay_schema() -> dict[str, Any]:
    return {
        "trade_date": pl.String,
        "cme_wall_map_state": pl.String,
        "spot_basis_state": pl.String,
        "iv_state": pl.String,
        "guru_same_day_transcript_state": pl.String,
        "historical_playbook_overlay_state": pl.String,
        "no_trade_filter_playbook_active": pl.Boolean,
        "market_map_playbook_active": pl.Boolean,
        "trade_rule_playbook_active": pl.Boolean,
        "plain_english_summary": pl.String,
    }


def _missing_plan_schema() -> dict[str, Any]:
    return {
        "trade_date": pl.String,
        "missing_component": pl.String,
        "suggested_file_needed": pl.String,
        "required_columns": pl.String,
        "preferred_granularity": pl.String,
        "where_to_place_file": pl.String,
        "rerun_command": pl.String,
    }


def main() -> None:
    """CLI entry point."""

    result = run_guru_transcript_alignment_debug_layer()
    print(f"final_recommendation: {result.final_recommendation}")
    print(f"next_data_action: {result.next_data_action}")
    print(f"transcript_corpus_exists: {result.transcript_corpus_exists}")
    print(
        "same_date_transcripts_exist_for_current_replay: "
        f"{result.same_date_transcripts_exist_for_current_replay}"
    )


if __name__ == "__main__":
    main()
