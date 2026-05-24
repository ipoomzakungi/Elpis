"""Approved market-session remap and same-day transcript interpretation debug.

This module is research-only. It applies approved market-session remaps only to
market-data alignment, keeps transcript availability dates unchanged, and adds a
same-day playbook matcher so context/filter/market-map evidence is separated
from strict trade-rule evidence.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable

import polars as pl

from research_xau_vol_oi.config import ResearchConfig


APPROVED_MARKET_SESSION_ONLY = "APPROVED_MARKET_SESSION_ONLY"
FINAL_RECOMMENDATIONS = (
    "SAME_DAY_CONTEXT_READY",
    "SAME_DAY_FILTER_READY",
    "SAME_DAY_MARKET_MAP_READY",
    "HISTORICAL_PLAYBOOK_ONLY",
    "POST_EVENT_ONLY",
    "EXTRACTOR_FIX_REQUIRED",
    "NEEDS_TRANSCRIPT_TIME_METADATA",
    "NEEDS_MANUAL_REVIEW",
)
FORBIDDEN_REPORT_PHRASES = (
    "profitable",
    "safe to trade",
    "live ready",
    "live-ready",
)
PLAYBOOK_TAGS = (
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
LOGIC_TYPE_BY_TAG = {
    "NO_TRADE_DISCIPLINE": "NO_TRADE_FILTER",
    "BASIS_MAPPING": "BASIS_MAPPING",
    "OI_WALL_ZONE": "OI_WALL_ZONE",
    "VOLATILITY_RANGE": "VOLATILITY_RANGE",
    "OI_FRESHNESS": "OI_FRESHNESS",
    "REJECTION_CONFIRMATION": "REJECTION_CONFIRMATION",
    "ACCEPTANCE_CONFIRMATION": "ACCEPTANCE_CONFIRMATION",
    "SQUEEZE_RISK": "SQUEEZE_RISK",
    "PIN_RISK": "PIN_RISK",
    "STALE_DATA_WARNING": "STALE_DATA_WARNING",
    "NEWS_EVENT_WARNING": "NEWS_EVENT_WARNING",
}
KEYWORDS_BY_TAG = {
    "NO_TRADE_DISCIPLINE": (
        "no trade",
        "not trade",
        "filter",
        "wait",
        "ไม่เทรด",
        "อย่าเทรด",
        "รอ",
        "กรอง",
    ),
    "BASIS_MAPPING": (
        "basis",
        "spot",
        "future",
        "futures",
        "gc=f",
        "yahoo",
        "ฟิวเจอร์",
        "สปอต",
        "ห่าง",
        "เทียบ",
    ),
    "OI_WALL_ZONE": (
        "oi",
        "open interest",
        "strike",
        "wall",
        "zone",
        "วอล",
        "กำแพง",
        "โซน",
    ),
    "VOLATILITY_RANGE": (
        "volatility",
        "iv",
        "range",
        "1sd",
        "2sd",
        "3sd",
        "sd",
        "กรอบ",
        "distribution",
    ),
    "OI_FRESHNESS": (
        "oi change",
        "volume",
        "fresh",
        "stale",
        "volume profile",
        "เปลี่ยน",
        "ปริมาณ",
        "วอลุ่ม",
    ),
    "REJECTION_CONFIRMATION": (
        "reject",
        "rejection",
        "rejected",
        "เด้ง",
        "สวน",
        "ปฏิเสธ",
    ),
    "ACCEPTANCE_CONFIRMATION": (
        "accept",
        "acceptance",
        "break",
        "breakout",
        "ผ่าน",
        "ยืน",
    ),
    "SQUEEZE_RISK": (
        "squeeze",
        "low oi",
        "gap",
        "ช่องว่าง",
    ),
    "PIN_RISK": (
        "pin",
        "expiry",
        "expiration",
        "หมดอายุ",
    ),
    "STALE_DATA_WARNING": (
        "stale",
        "old data",
        "outdated",
        "yesterday",
        "ย้อนหลัง",
        "เก่า",
    ),
    "NEWS_EVENT_WARNING": (
        "news",
        "fomc",
        "cpi",
        "fed",
        "ข่าว",
    ),
}
FILTER_TAGS = {"NO_TRADE_DISCIPLINE", "STALE_DATA_WARNING", "NEWS_EVENT_WARNING"}
MARKET_MAP_TAGS = {
    "BASIS_MAPPING",
    "OI_WALL_ZONE",
    "VOLATILITY_RANGE",
    "OI_FRESHNESS",
    "SQUEEZE_RISK",
    "PIN_RISK",
}


@dataclass(frozen=True)
class ApprovedSessionRemapInterpretationResult:
    """Generated frames for approved remap and same-day interpretation debug."""

    session_remap_decisions_template: pl.DataFrame
    session_remap_decisions_applied: pl.DataFrame
    current_week_replay_after_market_session_remap: pl.DataFrame
    same_day_transcript_interpretation_debug: pl.DataFrame
    same_day_playbook_matches: pl.DataFrame
    current_week_same_day_guru_overlay: pl.DataFrame
    final_recommendation: str


def run_approved_session_remap_interpretation_layer(
    *,
    output_dir: str | Path = "outputs",
    transcript_source_roots: Iterable[str | Path] | None = None,
) -> ApprovedSessionRemapInterpretationResult:
    """Run approved market-session remap and same-day interpretation debug."""

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    inputs = load_approved_remap_inputs(output_root)
    text_index = build_transcript_text_index(
        resolve_transcript_source_roots(transcript_source_roots)
    )
    result = build_approved_session_remap_interpretation(inputs, text_index=text_index)

    result.session_remap_decisions_template.write_csv(
        output_root / "session_remap_decisions_template.csv"
    )
    result.session_remap_decisions_applied.write_csv(
        output_root / "session_remap_decisions_applied.csv"
    )
    result.current_week_replay_after_market_session_remap.write_csv(
        output_root / "current_week_replay_after_market_session_remap.csv"
    )
    (output_root / "current_week_replay_after_market_session_remap.md").write_text(
        current_week_replay_after_market_session_remap_markdown(
            result.current_week_replay_after_market_session_remap,
            final_recommendation=result.final_recommendation,
        ),
        encoding="utf-8",
    )
    result.same_day_transcript_interpretation_debug.write_csv(
        output_root / "same_day_transcript_interpretation_debug.csv"
    )
    (output_root / "same_day_transcript_interpretation_debug.md").write_text(
        same_day_transcript_interpretation_debug_markdown(
            result.same_day_transcript_interpretation_debug
        ),
        encoding="utf-8",
    )
    result.same_day_playbook_matches.write_csv(output_root / "same_day_playbook_matches.csv")
    (output_root / "same_day_playbook_matches.md").write_text(
        same_day_playbook_matches_markdown(result.same_day_playbook_matches),
        encoding="utf-8",
    )
    result.current_week_same_day_guru_overlay.write_csv(
        output_root / "current_week_same_day_guru_overlay.csv"
    )
    (output_root / "current_week_same_day_guru_overlay.md").write_text(
        current_week_same_day_guru_overlay_markdown(
            result.current_week_same_day_guru_overlay,
            final_recommendation=result.final_recommendation,
        ),
        encoding="utf-8",
    )
    append_approved_session_remap_sections(output_root / "research_report.md", result)
    return result


def load_approved_remap_inputs(output_root: Path) -> dict[str, pl.DataFrame]:
    """Load optional input artifacts with empty-frame fallbacks."""

    names = {
        "session_remap_suggestions": output_root / "session_remap_suggestions.csv",
        "session_calendar_audit": output_root / "session_calendar_audit.csv",
        "current_week_replay_resolved": output_root / "current_week_replay_resolved.csv",
        "current_week_cme_guru_replay": output_root / "current_week_cme_guru_replay.csv",
        "current_week_cme_guru_playbook_replay": (
            output_root / "current_week_cme_guru_playbook_replay.csv"
        ),
        "clean_transcript_set": output_root / "clean_transcript_set.csv",
        "transcript_identity_audit": output_root / "transcript_identity_audit.csv",
        "transcript_session_availability": output_root / "transcript_session_availability.csv",
        "same_day_guru_signal_readiness": output_root / "same_day_guru_signal_readiness.csv",
        "guru_logic_knowledge_base": output_root / "guru_logic_knowledge_base.csv",
    }
    return {name: _load_optional(path) for name, path in names.items()}


def build_approved_session_remap_interpretation(
    inputs: dict[str, pl.DataFrame],
    *,
    text_index: dict[str, dict[str, Any]] | None = None,
) -> ApprovedSessionRemapInterpretationResult:
    """Build all approved remap and same-day debug frames."""

    suggestions = _frame(inputs, "session_remap_suggestions")
    calendar = _frame(inputs, "session_calendar_audit")
    resolved = _frame(inputs, "current_week_replay_resolved")
    replay = _frame(inputs, "current_week_cme_guru_replay")
    clean = _frame(inputs, "clean_transcript_set")
    availability = _frame(inputs, "transcript_session_availability")
    readiness = _frame(inputs, "same_day_guru_signal_readiness")
    knowledge_base = _frame(inputs, "guru_logic_knowledge_base")
    playbook = _frame(inputs, "current_week_cme_guru_playbook_replay")

    decisions_template = build_market_session_remap_decisions(suggestions)
    decisions_applied = build_market_session_remap_decisions(suggestions)
    remapped = build_current_week_replay_after_market_session_remap(
        decisions=decisions_applied,
        current_week_resolved=resolved,
        replay=replay,
        session_calendar=calendar,
    )
    debug = build_same_day_transcript_interpretation_debug(
        clean_transcript_set=clean,
        current_week_replay_after_remap=remapped,
        transcript_availability=availability,
        readiness=readiness,
        knowledge_base=knowledge_base,
        text_index=text_index or {},
    )
    matches = build_same_day_playbook_matches(
        interpretation_debug=debug,
        knowledge_base=knowledge_base,
        text_index=text_index or {},
    )
    overlay = build_current_week_same_day_guru_overlay(
        current_week_replay_after_remap=remapped,
        interpretation_debug=debug,
        playbook_matches=matches,
        historical_playbook_replay=playbook,
    )
    final = choose_approved_remap_recommendation(overlay=overlay, debug=debug)
    return ApprovedSessionRemapInterpretationResult(
        session_remap_decisions_template=decisions_template,
        session_remap_decisions_applied=decisions_applied,
        current_week_replay_after_market_session_remap=remapped,
        same_day_transcript_interpretation_debug=debug,
        same_day_playbook_matches=matches,
        current_week_same_day_guru_overlay=overlay,
        final_recommendation=final,
    )


def resolve_transcript_source_roots(
    roots: Iterable[str | Path] | None = None,
    *,
    config: ResearchConfig | None = None,
) -> tuple[Path, ...]:
    """Resolve local transcript roots from caller input, environment, or config roots."""

    cfg = config or ResearchConfig()
    configured = [Path(root) for root in (roots or ())]
    for env_name in ("GURU_TRANSCRIPT_SOURCE_ROOTS", "XAU_TRANSCRIPT_SOURCE_ROOTS"):
        env_value = os.getenv(env_name)
        if env_value:
            configured.extend(
                Path(item.strip()) for item in env_value.split(os.pathsep) if item.strip()
            )
    for data_root in cfg.data_roots:
        configured.append(Path(data_root) / "reports" / "youtube_transcripts")
    deduped: list[Path] = []
    seen: set[str] = set()
    for root in configured:
        if not root.exists():
            continue
        key = root.resolve().as_posix().lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(root)
    return tuple(deduped)


def build_transcript_text_index(roots: Iterable[Path]) -> dict[str, dict[str, Any]]:
    """Build a content-hash keyed text index without exposing local paths."""

    index: dict[str, dict[str, Any]] = {}
    for root in roots:
        for path in _iter_transcript_text_files(root):
            text = _read_text(path)
            if not text.strip():
                continue
            content_hash = _content_hash(text)
            if not content_hash or content_hash in index:
                continue
            index[content_hash] = {
                "text": text,
                "text_length": len(text),
                "thai_text_detected": bool(re.search(r"[\u0E00-\u0E7F]", text)),
            }
    return index


def build_market_session_remap_decisions(suggestions: pl.DataFrame) -> pl.DataFrame:
    """Create market-session-only approved decisions from explicit suggestions."""

    rows = []
    for row in suggestions.to_dicts() if not suggestions.is_empty() else []:
        original = _date_text(row.get("original_replay_date"))
        target = _date_text(row.get("suggested_market_session_date"))
        if not original or not target:
            continue
        rows.append(
            {
                "original_replay_date": original,
                "suggested_market_session_date": target,
                "approval_status": APPROVED_MARKET_SESSION_ONLY,
                "approval_scope": "MARKET_SESSION_ONLY",
                "transcript_remap_approved": False,
                "reason": _text(row.get("reason"))
                or "Approved for market-session date alignment only.",
                "reviewer_notes": (
                    "Approved for CME/OHLC/spot-basis session alignment only; transcript "
                    "availability date is unchanged."
                ),
            }
        )
    return _rows_frame(rows, _remap_decision_schema()).sort("original_replay_date")


def build_current_week_replay_after_market_session_remap(
    *,
    decisions: pl.DataFrame,
    current_week_resolved: pl.DataFrame,
    replay: pl.DataFrame,
    session_calendar: pl.DataFrame,
) -> pl.DataFrame:
    """Apply approved remaps to market session dates only."""

    decisions_by_date = _rows_by_date(decisions, "original_replay_date")
    resolved_by_date = _rows_by_date(current_week_resolved, "original_replay_date")
    replay_by_date = _rows_by_date(replay, "trade_date")
    calendar_by_date = _rows_by_date(session_calendar, "replay_trade_date")
    dates = sorted(
        _date_values(current_week_resolved, "original_replay_date")
        | _date_values(replay, "trade_date")
        | _date_values(session_calendar, "replay_trade_date")
    )
    rows = []
    for original in dates:
        decision = decisions_by_date.get(original, {})
        target = _date_text(decision.get("suggested_market_session_date"))
        applied = _text(decision.get("approval_status")) == APPROVED_MARKET_SESSION_ONLY
        resolved_market = target if applied and target else original
        replay_row = replay_by_date.get(original, {})
        resolved_row = resolved_by_date.get(original, {})
        calendar_row = calendar_by_date.get(original, {})
        rows.append(
            {
                "original_replay_date": original,
                "resolved_market_session_date": resolved_market,
                "remap_status": "APPLIED_MARKET_SESSION_ONLY" if applied else "NO_REMAP_NEEDED",
                "transcript_availability_date_unchanged": True,
                "cme_data_join_result": _cme_join_result(replay_row, calendar_row, applied),
                "spot_basis_join_result": _spot_basis_join_result(
                    replay_row,
                    resolved_row,
                    calendar_row,
                    applied,
                ),
                "wall_mapping_result": _wall_mapping_result(replay_row, resolved_row, applied),
                "plain_english_summary": _market_remap_summary(
                    original=original,
                    resolved_market=resolved_market,
                    applied=applied,
                ),
            }
        )
    return _rows_frame(rows, _market_remap_schema()).sort("original_replay_date")


def build_same_day_transcript_interpretation_debug(
    *,
    clean_transcript_set: pl.DataFrame,
    current_week_replay_after_remap: pl.DataFrame,
    transcript_availability: pl.DataFrame,
    readiness: pl.DataFrame,
    knowledge_base: pl.DataFrame,
    text_index: dict[str, dict[str, Any]],
) -> pl.DataFrame:
    """Debug why clean same-day transcripts did or did not produce same-day logic."""

    replay_dates = _date_values(current_week_replay_after_remap, "original_replay_date")
    remap_by_date = _rows_by_date(current_week_replay_after_remap, "original_replay_date")
    readiness_by_date = _rows_by_date(readiness, "trade_date")
    availability_by_pair = _availability_by_pair(transcript_availability)
    rows = []
    for clean in _included_clean_rows(clean_transcript_set):
        transcript_date = _date_text(clean.get("transcript_date"))
        if transcript_date not in replay_dates:
            continue
        content_hash = _text(clean.get("content_hash"))
        text_record = text_index.get(content_hash, {})
        text = _text_content(text_record)
        matches = _match_playbook_text(text, knowledge_base)
        counts = _counts_from_matches(matches)
        readiness_row = readiness_by_date.get(transcript_date, {})
        post_event_reason = _post_event_reason(readiness_row)
        availability_relation = _availability_for_pair(
            availability_by_pair,
            replay_date=transcript_date,
            transcript_date=transcript_date,
        )
        rows.append(
            {
                "clean_transcript_id": clean.get("clean_transcript_id"),
                "content_hash": content_hash,
                "transcript_date": transcript_date,
                "transcript_time": _text(clean.get("transcript_time")),
                "replay_date": transcript_date,
                "resolved_market_session_date": _date_text(
                    remap_by_date.get(transcript_date, {}).get("resolved_market_session_date")
                )
                or transcript_date,
                "availability_relation": availability_relation,
                "source_excerpt_sample": _sample_excerpt(text, matches),
                "text_length": int(text_record.get("text_length") or 0),
                "thai_text_detected": bool(text_record.get("thai_text_detected")),
                "rule_keyword_hits": "|".join(_keyword_hits(matches)),
                "playbook_logic_matches": "|".join(match["logic_id"] for match in matches),
                "extracted_context_count": counts["context"],
                "extracted_filter_count": counts["filter"],
                "extracted_market_map_count": counts["market_map"],
                "extracted_trade_rule_count": 0,
                "post_event_reason": post_event_reason,
                "why_no_context_or_filter": _why_no_context_or_filter(
                    text=text,
                    counts=counts,
                    post_event_reason=post_event_reason,
                ),
                "recommended_fix": _recommended_interpretation_fix(text=text, counts=counts),
            }
        )
    return _rows_frame(rows, _interpretation_debug_schema()).sort(
        ["replay_date", "clean_transcript_id"]
    )


def build_same_day_playbook_matches(
    *,
    interpretation_debug: pl.DataFrame,
    knowledge_base: pl.DataFrame,
    text_index: dict[str, dict[str, Any]],
) -> pl.DataFrame:
    """Build one row per same-day playbook match."""

    kb_by_logic = _knowledge_by_logic(knowledge_base)
    rows = []
    for debug in interpretation_debug.to_dicts() if not interpretation_debug.is_empty() else []:
        content_hash = _debug_content_hash(debug, interpretation_debug)
        text = _text_content(text_index.get(content_hash, {}))
        matches = _match_playbook_text(text, knowledge_base)
        for match in matches:
            logic = kb_by_logic.get(match["logic_type"], {})
            rows.append(
                {
                    "clean_transcript_id": debug.get("clean_transcript_id"),
                    "transcript_date": debug.get("transcript_date"),
                    "replay_date": debug.get("replay_date"),
                    "logic_id": _text(logic.get("logic_id")) or match["logic_id"],
                    "logic_name": _text(logic.get("logic_name")) or match["logic_name"],
                    "matched_text_excerpt": _match_excerpt(text, match["keyword"]),
                    "match_method": "KEYWORD",
                    "usable_as_context": True,
                    "usable_as_filter": match["tag"] in FILTER_TAGS,
                    "usable_as_market_map": match["tag"] in MARKET_MAP_TAGS,
                    "usable_as_trade_rule": False,
                    "confidence": _match_confidence(match),
                    "reason": _match_reason(match),
                }
            )
    return _rows_frame(rows, _same_day_playbook_match_schema()).sort(
        ["replay_date", "clean_transcript_id", "logic_id"]
    )


def build_current_week_same_day_guru_overlay(
    *,
    current_week_replay_after_remap: pl.DataFrame,
    interpretation_debug: pl.DataFrame,
    playbook_matches: pl.DataFrame,
    historical_playbook_replay: pl.DataFrame,
) -> pl.DataFrame:
    """Create one same-day guru overlay row per current-week replay date."""

    debug_by_date = _group_rows(interpretation_debug, "replay_date")
    matches_by_date = _group_rows(playbook_matches, "replay_date")
    historical_by_date = _rows_by_date(historical_playbook_replay, "trade_date")
    rows = []
    for replay_row in (
        current_week_replay_after_remap.to_dicts()
        if not current_week_replay_after_remap.is_empty()
        else []
    ):
        original = _date_text(replay_row.get("original_replay_date"))
        debug_rows = debug_by_date.get(original, [])
        match_rows = matches_by_date.get(original, [])
        context = _count_true(match_rows, "usable_as_context")
        filters = _count_true(match_rows, "usable_as_filter")
        market_maps = _count_true(match_rows, "usable_as_market_map")
        trade_rules = _count_true(match_rows, "usable_as_trade_rule")
        historical = _historical_overlay_count(historical_by_date.get(original, {}))
        state = _final_overlay_state(
            transcript_count=len(debug_rows),
            context=context,
            filters=filters,
            market_maps=market_maps,
            trade_rules=trade_rules,
            historical=historical,
        )
        rows.append(
            {
                "original_replay_date": original,
                "resolved_market_session_date": replay_row.get("resolved_market_session_date"),
                "same_day_transcript_count": len(debug_rows),
                "same_day_context_matches": context,
                "same_day_filter_matches": filters,
                "same_day_market_map_matches": market_maps,
                "same_day_trade_rule_matches": trade_rules,
                "historical_playbook_overlay_matches": historical,
                "final_guru_overlay_state": state,
                "plain_english_summary": _overlay_summary(
                    original=original,
                    state=state,
                    context=context,
                    filters=filters,
                    market_maps=market_maps,
                    trade_rules=trade_rules,
                    historical=historical,
                ),
            }
        )
    return _rows_frame(rows, _same_day_overlay_schema()).sort("original_replay_date")


def choose_approved_remap_recommendation(
    *,
    overlay: pl.DataFrame,
    debug: pl.DataFrame,
) -> str:
    """Choose a conservative recommendation after approved remap and debug."""

    states = set(overlay.get_column("final_guru_overlay_state").to_list()) if not overlay.is_empty() else set()
    if "SAME_DAY_FILTER_READY" in states:
        return "SAME_DAY_FILTER_READY"
    if "SAME_DAY_MARKET_MAP_READY" in states:
        return "SAME_DAY_MARKET_MAP_READY"
    if "SAME_DAY_CONTEXT_READY" in states:
        return "SAME_DAY_CONTEXT_READY"
    if not debug.is_empty() and _any_state(debug, "why_no_context_or_filter", "NOT_PASSED_TO_EXTRACTOR"):
        return "EXTRACTOR_FIX_REQUIRED"
    if not debug.is_empty() and _any_state(debug, "availability_relation", "UNKNOWN"):
        return "NEEDS_TRANSCRIPT_TIME_METADATA"
    if "POST_EVENT_ONLY" in states:
        return "POST_EVENT_ONLY"
    if "HISTORICAL_PLAYBOOK_ONLY" in states:
        return "HISTORICAL_PLAYBOOK_ONLY"
    return "NEEDS_MANUAL_REVIEW"


def approved_session_remap_report_lines(
    result: ApprovedSessionRemapInterpretationResult | None,
) -> list[str]:
    """Return Markdown lines for embedding in the main research report."""

    if result is None:
        return ["Approved market-session remap layer was not run."]
    return [
        "## Approved Market-Session Remap",
        "",
        f"- Final recommendation: `{result.final_recommendation}`",
        "- Scope: market-session date only; transcript availability dates are unchanged.",
        "",
        _frame_markdown(result.current_week_replay_after_market_session_remap),
        "",
        "## Same-Day Transcript Interpretation Debug",
        "",
        _frame_markdown(result.same_day_transcript_interpretation_debug),
        "",
        "## Same-Day Playbook Matches",
        "",
        _frame_markdown(_playbook_match_summary(result.same_day_playbook_matches)),
        "",
        "## Current-Week Same-Day Guru Overlay",
        "",
        _frame_markdown(result.current_week_same_day_guru_overlay),
        "",
        "## What Changed After Remap",
        "",
        *_what_changed_after_remap_lines(result.current_week_replay_after_market_session_remap),
        "",
        "## Remaining Issues",
        "",
        *_remaining_issue_lines(result),
    ]


def current_week_replay_after_market_session_remap_markdown(
    frame: pl.DataFrame,
    *,
    final_recommendation: str,
) -> str:
    """Render approved market-session remap output."""

    return _safe_report(
        "\n".join(
            [
                "# Current-Week Replay After Market-Session Remap",
                "",
                f"- Final recommendation: `{final_recommendation}`",
                *_what_changed_after_remap_lines(frame),
                "",
                _frame_markdown(frame),
            ]
        )
    )


def same_day_transcript_interpretation_debug_markdown(frame: pl.DataFrame) -> str:
    """Render same-day transcript interpretation debug output."""

    return _safe_report(
        "\n".join(
            [
                "# Same-Day Transcript Interpretation Debug",
                "",
                "Clean same-date transcript text is checked against playbook concepts before strict trade-rule review.",
                "",
                _frame_markdown(frame),
            ]
        )
    )


def same_day_playbook_matches_markdown(frame: pl.DataFrame) -> str:
    """Render same-day playbook matches."""

    return _safe_report(
        "\n".join(
            [
                "# Same-Day Playbook Matches",
                "",
                "Context/filter/market-map matches are reported separately from strict trade-rule matches.",
                "",
                _frame_markdown(_playbook_match_summary(frame)),
                "",
                _frame_markdown(frame),
            ]
        )
    )


def current_week_same_day_guru_overlay_markdown(
    frame: pl.DataFrame,
    *,
    final_recommendation: str,
) -> str:
    """Render current-week same-day guru overlay output."""

    return _safe_report(
        "\n".join(
            [
                "# Current-Week Same-Day Guru Overlay",
                "",
                f"- Final recommendation: `{final_recommendation}`",
                "- Same-day overlay and historical playbook overlay are separate fields.",
                "",
                _frame_markdown(frame),
            ]
        )
    )


def append_approved_session_remap_sections(
    path: Path,
    result: ApprovedSessionRemapInterpretationResult,
) -> None:
    """Append or replace approved remap sections in a generated research report."""

    marker = "\n## Approved Market-Session Remap\n"
    section = "\n".join(approved_session_remap_report_lines(result))
    existing = path.read_text(encoding="utf-8") if path.exists() else "# XAU/USD Vol-OI Research Report\n"
    if marker in existing:
        existing = existing.split(marker, 1)[0].rstrip()
    path.write_text(_safe_report(existing.rstrip() + "\n\n" + section + "\n"), encoding="utf-8")


def _iter_transcript_text_files(root: Path) -> Iterable[Path]:
    suffixes = {".txt", ".srt"}
    try:
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in suffixes and path.stat().st_size <= 2_000_000:
                yield path
    except OSError:
        return


def _read_text(path: Path) -> str:
    for encoding in ("utf-8", "utf-8-sig", "cp874", "cp1252"):
        try:
            return path.read_text(encoding=encoding, errors="ignore")
        except OSError:
            return ""
        except UnicodeError:
            continue
    return ""


def _content_hash(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text.strip())
    if not normalized:
        return ""
    return hashlib.sha1(normalized.encode("utf-8", errors="ignore")).hexdigest()[:12]


def _included_clean_rows(frame: pl.DataFrame) -> list[dict[str, Any]]:
    if frame.is_empty():
        return []
    return [row for row in frame.to_dicts() if _bool_value(row.get("included_in_clean_set"))]


def _match_playbook_text(text: str, knowledge_base: pl.DataFrame) -> list[dict[str, str]]:
    if not text.strip():
        return []
    lowered = text.lower()
    kb_by_logic = _knowledge_by_logic(knowledge_base)
    matches = []
    for tag in PLAYBOOK_TAGS:
        keywords = KEYWORDS_BY_TAG[tag]
        hits = [keyword for keyword in keywords if keyword.lower() in lowered]
        if not hits:
            continue
        logic_type = LOGIC_TYPE_BY_TAG[tag]
        kb = kb_by_logic.get(logic_type, {})
        matches.append(
            {
                "tag": tag,
                "logic_type": logic_type,
                "logic_id": _text(kb.get("logic_id")) or tag.lower(),
                "logic_name": _text(kb.get("logic_name")) or tag.replace("_", " ").title(),
                "keyword": hits[0],
                "hit_count": str(len(hits)),
            }
        )
    return matches


def _counts_from_matches(matches: list[dict[str, str]]) -> dict[str, int]:
    return {
        "context": len(matches),
        "filter": sum(1 for match in matches if match["tag"] in FILTER_TAGS),
        "market_map": sum(1 for match in matches if match["tag"] in MARKET_MAP_TAGS),
    }


def _keyword_hits(matches: list[dict[str, str]]) -> list[str]:
    return [f"{match['tag']}:{match['keyword']}" for match in matches]


def _sample_excerpt(text: str, matches: list[dict[str, str]]) -> str:
    if not text:
        return ""
    keyword = matches[0]["keyword"] if matches else ""
    return _match_excerpt(text, keyword) if keyword else _short_excerpt(text)


def _match_excerpt(text: str, keyword: str) -> str:
    if not text:
        return ""
    if not keyword:
        return _short_excerpt(text)
    lowered = text.lower()
    index = lowered.find(keyword.lower())
    if index < 0:
        return _short_excerpt(text)
    start = max(index - 60, 0)
    end = min(index + len(keyword) + 60, len(text))
    return _short_excerpt(text[start:end])


def _short_excerpt(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    words = cleaned.split()
    if len(words) >= 12:
        return " ".join(words[:12])
    return cleaned[:120]


def _post_event_reason(readiness_row: dict[str, Any]) -> str:
    post_event_rows = int(_float_or_zero(readiness_row.get("post_event_rows")))
    if post_event_rows:
        return f"POST_EVENT_ROWS_ALREADY_REVIEWED:{post_event_rows}"
    return ""


def _why_no_context_or_filter(
    *,
    text: str,
    counts: dict[str, int],
    post_event_reason: str,
) -> str:
    if not text.strip():
        return "NOT_PASSED_TO_EXTRACTOR"
    if counts["context"] or counts["filter"] or counts["market_map"]:
        return "EXTRACTOR_ONLY_USES_REVIEW_EPISODES"
    if len(text.strip()) < 100:
        return "TEXT_TOO_SHORT"
    if post_event_reason:
        return "CLASSIFIED_POST_EVENT"
    return "RULE_KEYWORDS_NOT_MATCHED"


def _recommended_interpretation_fix(*, text: str, counts: dict[str, int]) -> str:
    if not text.strip():
        return "Resolve local transcript text for the clean transcript content hash."
    if counts["context"] or counts["filter"] or counts["market_map"]:
        return "Pass clean same-day transcript text through the same-day playbook matcher before strict trade-rule review."
    return "Add language-specific playbook keywords or route transcript text to manual review."


def _debug_content_hash(debug: dict[str, Any], interpretation_debug: pl.DataFrame) -> str:
    # The debug frame intentionally omits raw paths. Recover content hash by clean id
    # when tests construct a debug frame with content_hash, otherwise return empty.
    if "content_hash" in debug:
        return _text(debug.get("content_hash"))
    if "content_hash" in interpretation_debug.columns:
        rows = interpretation_debug.filter(
            pl.col("clean_transcript_id") == debug.get("clean_transcript_id")
        ).to_dicts()
        if rows:
            return _text(rows[0].get("content_hash"))
    return ""


def _availability_by_pair(frame: pl.DataFrame) -> dict[tuple[str, str], str]:
    values: dict[tuple[str, str], str] = {}
    for row in frame.to_dicts() if not frame.is_empty() else []:
        replay = _date_text(row.get("replay_trade_date"))
        transcript = _date_text(row.get("transcript_date"))
        relation = _text(row.get("availability_relation"))
        if replay and transcript and (replay, transcript) not in values:
            values[(replay, transcript)] = relation
    return values


def _availability_for_pair(
    values: dict[tuple[str, str], str],
    *,
    replay_date: str,
    transcript_date: str,
) -> str:
    return values.get((replay_date, transcript_date), "UNKNOWN")


def _knowledge_by_logic(frame: pl.DataFrame) -> dict[str, dict[str, Any]]:
    rows = {}
    for row in frame.to_dicts() if not frame.is_empty() else []:
        logic_type = _text(row.get("logic_type"))
        if logic_type and logic_type not in rows:
            rows[logic_type] = row
    return rows


def _match_confidence(match: dict[str, str]) -> str:
    hit_count = int(match.get("hit_count") or 0)
    if hit_count >= 3:
        return "HIGH"
    if hit_count == 2:
        return "MEDIUM"
    return "LOW"


def _match_reason(match: dict[str, str]) -> str:
    if match["tag"] in FILTER_TAGS:
        return "Same-day text matched filter/warning playbook keywords; use as context/filter only."
    if match["tag"] in MARKET_MAP_TAGS:
        return "Same-day text matched market-map playbook keywords; use as context/market-map only."
    return "Same-day text matched confirmation keywords but lacks strict reviewed trade-rule fields."


def _final_overlay_state(
    *,
    transcript_count: int,
    context: int,
    filters: int,
    market_maps: int,
    trade_rules: int,
    historical: int,
) -> str:
    if trade_rules:
        return "SAME_DAY_CONTEXT_READY"
    if filters:
        return "SAME_DAY_FILTER_READY"
    if market_maps:
        return "SAME_DAY_MARKET_MAP_READY"
    if context:
        return "SAME_DAY_CONTEXT_READY"
    if transcript_count:
        return "POST_EVENT_ONLY"
    if historical:
        return "HISTORICAL_PLAYBOOK_ONLY"
    return "NO_USABLE_GURU_CONTEXT"


def _historical_overlay_count(row: dict[str, Any]) -> int:
    if not row:
        return 0
    return sum(
        1
        for column in (
            "no_trade_filter_playbook_active",
            "market_map_playbook_active",
            "trade_rule_playbook_active",
        )
        if _bool_value(row.get(column))
    )


def _overlay_summary(
    *,
    original: str,
    state: str,
    context: int,
    filters: int,
    market_maps: int,
    trade_rules: int,
    historical: int,
) -> str:
    return (
        f"{original}: {state}. Same-day matches context={context}, filter={filters}, "
        f"market_map={market_maps}, strict_trade_rule={trade_rules}; historical overlay "
        f"matches={historical}."
    )


def _cme_join_result(
    replay_row: dict[str, Any],
    calendar_row: dict[str, Any],
    applied: bool,
) -> str:
    if applied:
        return "CME_JOINED_ON_APPROVED_MARKET_SESSION"
    if _bool_value(replay_row.get("futures_available")) or _bool_value(
        calendar_row.get("has_cme_futures_rows")
    ):
        return "CME_JOIN_AVAILABLE"
    return "CME_JOIN_MISSING"


def _spot_basis_join_result(
    replay_row: dict[str, Any],
    resolved_row: dict[str, Any],
    calendar_row: dict[str, Any],
    applied: bool,
) -> str:
    if applied:
        return "SPOT_BASIS_AVAILABLE_AFTER_MARKET_SESSION_REMAP"
    if _bool_value(replay_row.get("spot_available")) and _bool_value(replay_row.get("basis_available")):
        return "SPOT_BASIS_AVAILABLE"
    if _bool_value(calendar_row.get("has_xau_spot_rows")) and _bool_value(calendar_row.get("has_basis_rows")):
        return "SPOT_BASIS_AVAILABLE"
    if _text(resolved_row.get("data_state")) == "WEEKEND_ARTIFACT":
        return "WEEKEND_ARTIFACT_PENDING_REMAP"
    return "SPOT_BASIS_MISSING"


def _wall_mapping_result(
    replay_row: dict[str, Any],
    resolved_row: dict[str, Any],
    applied: bool,
) -> str:
    if applied:
        return "SPOT_EQUIVALENT_WALL_MAP_AFTER_MARKET_SESSION_REMAP"
    wall_type = _text(replay_row.get("wall_type"))
    if wall_type == "SPOT_EQUIVALENT_LEVEL":
        return "SPOT_EQUIVALENT_WALL_MAP"
    if _text(resolved_row.get("data_state")) == "WEEKEND_ARTIFACT":
        return "FUTURES_STRIKE_WALL_MAP_PENDING_REMAP"
    return "WALL_MAP_AVAILABLE"


def _market_remap_summary(*, original: str, resolved_market: str, applied: bool) -> str:
    if applied:
        return (
            f"{original} market data is aligned to {resolved_market}; transcript availability "
            "date remains unchanged."
        )
    return f"{original} keeps its original market session date; no remap is needed."


def _what_changed_after_remap_lines(frame: pl.DataFrame) -> list[str]:
    upgraded = _rows_upgraded_after_remap(frame)
    basis_improved = _count_state(frame, "spot_basis_join_result", "SPOT_BASIS_AVAILABLE_AFTER_MARKET_SESSION_REMAP")
    wall_improved = _count_state(
        frame,
        "wall_mapping_result",
        "SPOT_EQUIVALENT_WALL_MAP_AFTER_MARKET_SESSION_REMAP",
    )
    missing = _remaining_missing_dates(frame)
    return [
        f"- Rows upgraded: `{upgraded}`",
        f"- Basis availability improvements: `{basis_improved}`",
        f"- Spot-equivalent wall improvements: `{wall_improved}`",
        f"- Remaining missing market-data dates: `{', '.join(missing) if missing else 'none'}`",
    ]


def _remaining_issue_lines(result: ApprovedSessionRemapInterpretationResult) -> list[str]:
    debug = result.same_day_transcript_interpretation_debug
    no_text = _count_state(debug, "why_no_context_or_filter", "NOT_PASSED_TO_EXTRACTOR")
    unknown_time = _count_state(debug, "availability_relation", "UNKNOWN")
    trade_rules = _sum_int(result.current_week_same_day_guru_overlay, "same_day_trade_rule_matches")
    return [
        f"- Same-day transcripts without resolved text: `{no_text}`",
        f"- Same-day transcripts needing time metadata review: `{unknown_time}`",
        f"- Strict same-day trade-rule matches: `{trade_rules}`",
        "- Strict trade-rule count can remain zero while context/filter/market-map rows are used separately.",
    ]


def _playbook_match_summary(frame: pl.DataFrame) -> pl.DataFrame:
    if frame.is_empty():
        return _rows_frame([], _playbook_match_summary_schema())
    rows = []
    for logic_name, group in _group_rows(frame, "logic_name").items():
        rows.append(
            {
                "logic_name": logic_name,
                "match_rows": len(group),
                "context_rows": sum(1 for row in group if _bool_value(row.get("usable_as_context"))),
                "filter_rows": sum(1 for row in group if _bool_value(row.get("usable_as_filter"))),
                "market_map_rows": sum(
                    1 for row in group if _bool_value(row.get("usable_as_market_map"))
                ),
                "trade_rule_rows": sum(
                    1 for row in group if _bool_value(row.get("usable_as_trade_rule"))
                ),
            }
        )
    return _rows_frame(rows, _playbook_match_summary_schema()).sort("logic_name")


def _rows_upgraded_after_remap(frame: pl.DataFrame) -> int:
    return _count_state(frame, "remap_status", "APPLIED_MARKET_SESSION_ONLY")


def _remaining_missing_dates(frame: pl.DataFrame) -> list[str]:
    rows = []
    for row in frame.to_dicts() if not frame.is_empty() else []:
        if _text(row.get("spot_basis_join_result")) in {
            "SPOT_BASIS_MISSING",
            "WEEKEND_ARTIFACT_PENDING_REMAP",
        }:
            rows.append(_date_text(row.get("original_replay_date")))
    return [row for row in rows if row]


def _count_state(frame: pl.DataFrame, column: str, value: str) -> int:
    if frame.is_empty() or column not in frame.columns:
        return 0
    return sum(1 for item in frame.get_column(column).to_list() if _text(item) == value)


def _any_state(frame: pl.DataFrame, column: str, value: str) -> bool:
    return _count_state(frame, column, value) > 0


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


def _text_content(record: dict[str, Any]) -> str:
    return str(record.get("text") or "")


def _float_or_zero(value: Any) -> float:
    try:
        if value in (None, ""):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


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
        key = _text(row.get(column))
        if key:
            groups.setdefault(key, []).append(row)
    return groups


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


def _date_text(value: Any) -> str:
    text = str(value or "")
    match = re.search(r"20\d{2}-\d{2}-\d{2}", text)
    return match.group(0) if match else ""


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _previous_trading_day(value: date) -> date:
    candidate = value - timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate


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


def _remap_decision_schema() -> dict[str, Any]:
    return {
        "original_replay_date": pl.String,
        "suggested_market_session_date": pl.String,
        "approval_status": pl.String,
        "approval_scope": pl.String,
        "transcript_remap_approved": pl.Boolean,
        "reason": pl.String,
        "reviewer_notes": pl.String,
    }


def _market_remap_schema() -> dict[str, Any]:
    return {
        "original_replay_date": pl.String,
        "resolved_market_session_date": pl.String,
        "remap_status": pl.String,
        "transcript_availability_date_unchanged": pl.Boolean,
        "cme_data_join_result": pl.String,
        "spot_basis_join_result": pl.String,
        "wall_mapping_result": pl.String,
        "plain_english_summary": pl.String,
    }


def _interpretation_debug_schema() -> dict[str, Any]:
    return {
        "clean_transcript_id": pl.String,
        "content_hash": pl.String,
        "transcript_date": pl.String,
        "transcript_time": pl.String,
        "replay_date": pl.String,
        "resolved_market_session_date": pl.String,
        "availability_relation": pl.String,
        "source_excerpt_sample": pl.String,
        "text_length": pl.Int64,
        "thai_text_detected": pl.Boolean,
        "rule_keyword_hits": pl.String,
        "playbook_logic_matches": pl.String,
        "extracted_context_count": pl.Int64,
        "extracted_filter_count": pl.Int64,
        "extracted_market_map_count": pl.Int64,
        "extracted_trade_rule_count": pl.Int64,
        "post_event_reason": pl.String,
        "why_no_context_or_filter": pl.String,
        "recommended_fix": pl.String,
    }


def _same_day_playbook_match_schema() -> dict[str, Any]:
    return {
        "clean_transcript_id": pl.String,
        "transcript_date": pl.String,
        "replay_date": pl.String,
        "logic_id": pl.String,
        "logic_name": pl.String,
        "matched_text_excerpt": pl.String,
        "match_method": pl.String,
        "usable_as_context": pl.Boolean,
        "usable_as_filter": pl.Boolean,
        "usable_as_market_map": pl.Boolean,
        "usable_as_trade_rule": pl.Boolean,
        "confidence": pl.String,
        "reason": pl.String,
    }


def _same_day_overlay_schema() -> dict[str, Any]:
    return {
        "original_replay_date": pl.String,
        "resolved_market_session_date": pl.String,
        "same_day_transcript_count": pl.Int64,
        "same_day_context_matches": pl.Int64,
        "same_day_filter_matches": pl.Int64,
        "same_day_market_map_matches": pl.Int64,
        "same_day_trade_rule_matches": pl.Int64,
        "historical_playbook_overlay_matches": pl.Int64,
        "final_guru_overlay_state": pl.String,
        "plain_english_summary": pl.String,
    }


def _playbook_match_summary_schema() -> dict[str, Any]:
    return {
        "logic_name": pl.String,
        "match_rows": pl.Int64,
        "context_rows": pl.Int64,
        "filter_rows": pl.Int64,
        "market_map_rows": pl.Int64,
        "trade_rule_rows": pl.Int64,
    }


def main() -> None:
    """CLI entry point."""

    result = run_approved_session_remap_interpretation_layer()
    print(f"final_recommendation: {result.final_recommendation}")
    print(
        "rows_upgraded: "
        f"{_rows_upgraded_after_remap(result.current_week_replay_after_market_session_remap)}"
    )
    print(f"same_day_debug_rows: {result.same_day_transcript_interpretation_debug.height}")
    print(f"same_day_match_rows: {result.same_day_playbook_matches.height}")


if __name__ == "__main__":
    main()
