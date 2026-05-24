"""Transcript timing resolver and current-week same-day evidence reports.

This module is research-only. It resolves transcript timing metadata when local
metadata exists, classifies availability conservatively, and reports same-day
filter/market-map evidence without treating unknown or post-session text as a
same-session input.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import polars as pl

from research_xau_vol_oi.config import ResearchConfig


FORBIDDEN_REPORT_PHRASES = (
    "profitable",
    "safe to trade",
    "live ready",
    "live-ready",
    "money-readiness",
)
FINAL_RECOMMENDATIONS = (
    "SAME_DAY_FILTER_CONTEXT_READY",
    "SAME_DAY_FILTER_TIMING_CONFIRMED",
    "SAME_DAY_MARKET_MAP_CONTEXT_READY",
    "NEEDS_TRANSCRIPT_METADATA",
    "HISTORICAL_PLAYBOOK_ONLY",
    "POST_EVENT_ONLY",
    "CURRENT_WEEK_EVIDENCE_READY",
)
HIGH_MEDIUM = {"HIGH", "MEDIUM"}
FILTER_STATES = {"TIMING_CONFIRMED", "TIMING_UNKNOWN_CONTEXT_ONLY"}


@dataclass(frozen=True)
class TimingEvidenceResult:
    """Generated frames and recommendation for transcript timing evidence."""

    transcript_timing_metadata_audit: pl.DataFrame
    transcript_availability_classification: pl.DataFrame
    same_day_filter_evidence: pl.DataFrame
    same_day_market_map_evidence: pl.DataFrame
    current_week_evidence_scorecard: pl.DataFrame
    transcript_metadata_fetch_plan: pl.DataFrame
    current_week_evidence_report_markdown: str
    final_recommendation: str


@dataclass(frozen=True)
class TimingCandidate:
    """Resolved timing fields for one transcript file/content hash."""

    detected_publish_timestamp: str = ""
    detected_live_start_timestamp: str = ""
    detected_live_end_timestamp: str = ""
    detected_transcript_start_timestamp: str = ""
    detected_transcript_end_timestamp: str = ""
    timing_source: str = "UNKNOWN"
    timing_confidence: str = "UNKNOWN"
    timing_notes: str = ""


def run_transcript_timing_evidence_layer(
    *,
    output_dir: str | Path = "outputs",
    transcript_source_roots: Iterable[str | Path] | None = None,
) -> TimingEvidenceResult:
    """Run transcript timing and evidence reports."""

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    inputs = load_timing_evidence_inputs(output_root)
    timing_index = build_transcript_timing_index(
        resolve_transcript_source_roots(transcript_source_roots)
    )
    result = build_transcript_timing_evidence(inputs, timing_index=timing_index)

    result.transcript_timing_metadata_audit.write_csv(
        output_root / "transcript_timing_metadata_audit.csv"
    )
    (output_root / "transcript_timing_metadata_audit.md").write_text(
        transcript_timing_metadata_audit_markdown(result.transcript_timing_metadata_audit),
        encoding="utf-8",
    )
    result.transcript_availability_classification.write_csv(
        output_root / "transcript_availability_classification.csv"
    )
    (output_root / "transcript_availability_classification.md").write_text(
        transcript_availability_classification_markdown(
            result.transcript_availability_classification
        ),
        encoding="utf-8",
    )
    result.same_day_filter_evidence.write_csv(output_root / "same_day_filter_evidence.csv")
    (output_root / "same_day_filter_evidence.md").write_text(
        same_day_filter_evidence_markdown(result.same_day_filter_evidence),
        encoding="utf-8",
    )
    result.same_day_market_map_evidence.write_csv(
        output_root / "same_day_market_map_evidence.csv"
    )
    (output_root / "same_day_market_map_evidence.md").write_text(
        same_day_market_map_evidence_markdown(result.same_day_market_map_evidence),
        encoding="utf-8",
    )
    result.current_week_evidence_scorecard.write_csv(
        output_root / "current_week_evidence_scorecard.csv"
    )
    (output_root / "current_week_evidence_report.md").write_text(
        _safe_report(result.current_week_evidence_report_markdown),
        encoding="utf-8",
    )
    result.transcript_metadata_fetch_plan.write_csv(
        output_root / "transcript_metadata_fetch_plan.csv"
    )
    (output_root / "transcript_metadata_fetch_plan.md").write_text(
        transcript_metadata_fetch_plan_markdown(result.transcript_metadata_fetch_plan),
        encoding="utf-8",
    )
    append_transcript_timing_evidence_sections(output_root / "research_report.md", result)
    return result


def load_timing_evidence_inputs(output_root: Path) -> dict[str, pl.DataFrame]:
    """Load optional inputs with empty fallbacks."""

    names = {
        "current_week_same_day_guru_overlay": output_root / "current_week_same_day_guru_overlay.csv",
        "same_day_playbook_matches": output_root / "same_day_playbook_matches.csv",
        "same_day_transcript_interpretation_debug": (
            output_root / "same_day_transcript_interpretation_debug.csv"
        ),
        "current_week_replay_after_market_session_remap": (
            output_root / "current_week_replay_after_market_session_remap.csv"
        ),
        "current_week_cme_guru_replay": output_root / "current_week_cme_guru_replay.csv",
        "current_week_cme_guru_playbook_replay": (
            output_root / "current_week_cme_guru_playbook_replay.csv"
        ),
        "current_week_guru_filter_replay": output_root / "current_week_guru_filter_replay.csv",
        "current_cme_date_usability": output_root / "current_cme_date_usability.csv",
        "cme_validation_grade_days_after_backfill": (
            output_root / "cme_validation_grade_days_after_backfill.csv"
        ),
        "transcript_identity_audit": output_root / "transcript_identity_audit.csv",
        "clean_transcript_set": output_root / "clean_transcript_set.csv",
        "transcript_session_availability": output_root / "transcript_session_availability.csv",
        "guru_logic_knowledge_base": output_root / "guru_logic_knowledge_base.csv",
        "cme_canonical_option_oi_by_strike": output_root / "cme_canonical_option_oi_by_strike.parquet",
        "cme_canonical_option_iv_by_strike": output_root / "cme_canonical_option_iv_by_strike.parquet",
        "cme_canonical_futures_price": output_root / "cme_canonical_futures_price.parquet",
        "xau_spot_backfilled": output_root / "xau_spot_backfilled.parquet",
        "xau_basis_backfilled": output_root / "xau_basis_backfilled.parquet",
    }
    return {name: _load_optional(path) for name, path in names.items()}


def build_transcript_timing_evidence(
    inputs: dict[str, pl.DataFrame],
    *,
    timing_index: dict[str, TimingCandidate] | None = None,
) -> TimingEvidenceResult:
    """Build timing audit, classifications, evidence reports, and recommendation."""

    timing_index = timing_index or {}
    debug = _frame(inputs, "same_day_transcript_interpretation_debug")
    clean = _frame(inputs, "clean_transcript_set")
    remapped = _frame(inputs, "current_week_replay_after_market_session_remap")
    matches = _frame(inputs, "same_day_playbook_matches")
    replay = _frame(inputs, "current_week_cme_guru_replay")
    filter_replay = _frame(inputs, "current_week_guru_filter_replay")
    playbook = _frame(inputs, "current_week_cme_guru_playbook_replay")

    timing = build_transcript_timing_metadata_audit(
        same_day_debug=debug,
        clean_transcript_set=clean,
        timing_index=timing_index,
    )
    availability = build_transcript_availability_classification(
        timing_audit=timing,
        remapped_replay=remapped,
        playbook_matches=matches,
    )
    filter_evidence = build_same_day_filter_evidence(
        remapped_replay=remapped,
        playbook_matches=matches,
        availability_classification=availability,
        filter_replay=filter_replay,
        replay=replay,
        historical_playbook_replay=playbook,
    )
    market_map = build_same_day_market_map_evidence(
        remapped_replay=remapped,
        playbook_matches=matches,
        availability_classification=availability,
        replay=replay,
    )
    scorecard = build_current_week_evidence_scorecard(
        remapped_replay=remapped,
        filter_evidence=filter_evidence,
        market_map_evidence=market_map,
        replay=replay,
    )
    report = current_week_evidence_report_markdown(
        scorecard=scorecard,
        filter_evidence=filter_evidence,
        market_map_evidence=market_map,
        replay=replay,
    )
    fetch_plan = build_transcript_metadata_fetch_plan(timing)
    final = choose_timing_evidence_recommendation(
        availability=availability,
        filter_evidence=filter_evidence,
        market_map_evidence=market_map,
        fetch_plan=fetch_plan,
    )
    return TimingEvidenceResult(
        transcript_timing_metadata_audit=timing,
        transcript_availability_classification=availability,
        same_day_filter_evidence=filter_evidence,
        same_day_market_map_evidence=market_map,
        current_week_evidence_scorecard=scorecard,
        transcript_metadata_fetch_plan=fetch_plan,
        current_week_evidence_report_markdown=report,
        final_recommendation=final,
    )


def resolve_transcript_source_roots(
    roots: Iterable[str | Path] | None = None,
    *,
    config: ResearchConfig | None = None,
) -> tuple[Path, ...]:
    """Resolve transcript roots from local config/env only."""

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


def build_transcript_timing_index(roots: Iterable[Path]) -> dict[str, TimingCandidate]:
    """Scan configured transcript roots for local timing metadata keyed by content hash."""

    index: dict[str, TimingCandidate] = {}
    for root in roots:
        for path in _iter_transcript_files(root):
            text = _read_text(path)
            content_hash = _content_hash(text)
            if not content_hash or content_hash in index:
                continue
            index[content_hash] = resolve_timing_for_file(path=path, text=text)
    return index


def resolve_timing_for_file(path: Path, text: str) -> TimingCandidate:
    """Resolve timing for one local transcript file."""

    metadata = parse_adjacent_metadata(path)
    if metadata.timing_source != "UNKNOWN":
        return metadata
    filename = parse_filename_timing(path.name)
    if filename.timing_source != "UNKNOWN":
        return filename
    title = parse_title_timing(text)
    if title.timing_source != "UNKNOWN":
        return title
    srt = parse_srt_timecodes(text)
    if srt.timing_source != "UNKNOWN":
        return srt
    return file_modtime_timing(path)


def parse_filename_timing(filename: str) -> TimingCandidate:
    """Parse absolute publish/live time hints from a filename."""

    text = str(filename)
    patterns = (
        r"(20\d{2})[-_\.](\d{2})[-_\.](\d{2})[^\d]{1,5}([01]?\d|2[0-3])[-_:\.](\d{2})(?:[-_:\.](\d{2}))?",
        r"(20\d{2})(\d{2})(\d{2})[^\d]?([01]\d|2[0-3])(\d{2})(?:([0-5]\d))?",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        year, month, day, hour, minute, second = match.groups(default="00")
        timestamp = f"{year}-{month}-{day}T{int(hour):02d}:{int(minute):02d}:{int(second):02d}"
        return TimingCandidate(
            detected_publish_timestamp=timestamp,
            detected_live_start_timestamp=timestamp,
            timing_source="FILENAME",
            timing_confidence="MEDIUM",
            timing_notes="Timestamp parsed from transcript filename.",
        )
    return TimingCandidate()


def parse_metadata_json_timing(payload: dict[str, Any]) -> TimingCandidate:
    """Parse YouTube/yt-dlp style metadata JSON."""

    publish = _first_timestamp(
        payload,
        ("timestamp", "release_timestamp", "published_timestamp", "publish_timestamp"),
    )
    live_start = _first_timestamp(
        payload,
        ("live_start_time", "start_time", "actual_start_time", "release_timestamp"),
    )
    live_end = _first_timestamp(payload, ("live_end_time", "end_time", "actual_end_time"))
    upload_date = _upload_date_timestamp(payload.get("upload_date") or payload.get("release_date"))
    publish = publish or upload_date
    if not any((publish, live_start, live_end)):
        return TimingCandidate()
    confidence = "HIGH" if publish or live_start else "MEDIUM"
    return TimingCandidate(
        detected_publish_timestamp=publish,
        detected_live_start_timestamp=live_start,
        detected_live_end_timestamp=live_end,
        timing_source="YOUTUBE_METADATA_JSON",
        timing_confidence=confidence,
        timing_notes="Timing parsed from adjacent metadata JSON.",
    )


def parse_srt_timecodes(text: str) -> TimingCandidate:
    """Parse relative SRT timecodes without converting them to publish time."""

    matches = re.findall(
        r"(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})",
        text,
    )
    if not matches:
        return TimingCandidate()
    start = matches[0][0].replace(",", ".")
    end = matches[-1][1].replace(",", ".")
    return TimingCandidate(
        detected_transcript_start_timestamp=start,
        detected_transcript_end_timestamp=end,
        timing_source="SRT_TIMECODE",
        timing_confidence="LOW",
        timing_notes="SRT timecodes are relative offsets; they do not prove publish or live timing.",
    )


def parse_title_timing(text: str) -> TimingCandidate:
    """Parse title/body timestamp text when present."""

    for line in text.splitlines()[:12]:
        parsed = parse_filename_timing(line)
        if parsed.timing_source != "UNKNOWN":
            return TimingCandidate(
                detected_publish_timestamp=parsed.detected_publish_timestamp,
                detected_live_start_timestamp=parsed.detected_live_start_timestamp,
                timing_source="TITLE_TEXT",
                timing_confidence="MEDIUM",
                timing_notes="Timestamp parsed from transcript title text.",
            )
    return TimingCandidate()


def parse_adjacent_metadata(path: Path) -> TimingCandidate:
    """Parse adjacent metadata JSON if present."""

    candidates = [
        path.with_suffix(".info.json"),
        path.with_suffix(".json"),
        path.parent / f"{path.stem}.metadata.json",
    ]
    for candidate in candidates:
        if not candidate.exists() or not candidate.is_file():
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8", errors="ignore"))
        except (OSError, json.JSONDecodeError):
            continue
        parsed = parse_metadata_json_timing(payload)
        if parsed.timing_source != "UNKNOWN":
            return parsed
    return TimingCandidate()


def file_modtime_timing(path: Path) -> TimingCandidate:
    """Use file modified time only as a low-confidence audit fallback."""

    try:
        modified = datetime.fromtimestamp(path.stat().st_mtime).replace(microsecond=0)
    except OSError:
        return TimingCandidate()
    return TimingCandidate(
        detected_publish_timestamp=modified.isoformat(),
        timing_source="FILE_MODTIME_LOW_CONFIDENCE",
        timing_confidence="LOW",
        timing_notes="File modified time is an audit fallback only and is not same-session proof.",
    )


def build_transcript_timing_metadata_audit(
    *,
    same_day_debug: pl.DataFrame,
    clean_transcript_set: pl.DataFrame,
    timing_index: dict[str, TimingCandidate],
) -> pl.DataFrame:
    """Build one timing audit row per clean same-day transcript used in replay."""

    clean_by_id = {
        _text(row.get("clean_transcript_id")): row
        for row in clean_transcript_set.to_dicts()
        if _bool_value(row.get("included_in_clean_set"))
    }
    rows = []
    for debug in same_day_debug.to_dicts() if not same_day_debug.is_empty() else []:
        clean_id = _text(debug.get("clean_transcript_id"))
        clean = clean_by_id.get(clean_id, {})
        content_hash = _text(debug.get("content_hash")) or _text(clean.get("content_hash"))
        candidate = timing_index.get(content_hash, TimingCandidate())
        rows.append(
            {
                "clean_transcript_id": clean_id,
                "transcript_date": _date_text(debug.get("transcript_date"))
                or _date_text(clean.get("transcript_date")),
                "title_hash": _text(clean.get("title_hash")),
                "content_hash": content_hash,
                "detected_publish_timestamp": candidate.detected_publish_timestamp,
                "detected_live_start_timestamp": candidate.detected_live_start_timestamp,
                "detected_live_end_timestamp": candidate.detected_live_end_timestamp,
                "detected_transcript_start_timestamp": (
                    candidate.detected_transcript_start_timestamp
                ),
                "detected_transcript_end_timestamp": candidate.detected_transcript_end_timestamp,
                "timing_source": candidate.timing_source,
                "timing_confidence": candidate.timing_confidence,
                "timing_notes": candidate.timing_notes or "No absolute timing metadata found.",
            }
        )
    return _rows_frame(rows, _timing_audit_schema()).sort(
        ["transcript_date", "clean_transcript_id"]
    )


def build_transcript_availability_classification(
    *,
    timing_audit: pl.DataFrame,
    remapped_replay: pl.DataFrame,
    playbook_matches: pl.DataFrame,
) -> pl.DataFrame:
    """Classify transcript availability against resolved market sessions."""

    remapped_by_date = _rows_by_date(remapped_replay, "original_replay_date")
    match_counts = _match_counts_by_clean_id(playbook_matches)
    rows = []
    for timing in timing_audit.to_dicts() if not timing_audit.is_empty() else []:
        transcript_date = _date_text(timing.get("transcript_date"))
        remap = remapped_by_date.get(transcript_date, {})
        session_date = _date_text(remap.get("resolved_market_session_date")) or transcript_date
        publish = _text(timing.get("detected_publish_timestamp"))
        live_start = _text(timing.get("detected_live_start_timestamp"))
        confidence = _text(timing.get("timing_confidence"))
        timestamp = live_start or publish
        relation = classify_availability_relation(
            transcript_date=transcript_date,
            resolved_market_session_date=session_date,
            timestamp=timestamp,
            timing_confidence=confidence,
        )
        counts = match_counts.get(_text(timing.get("clean_transcript_id")), {})
        same_session_allowed = relation in {"PRE_SESSION", "DURING_SESSION"} and confidence in HIGH_MEDIUM
        rows.append(
            {
                "clean_transcript_id": timing.get("clean_transcript_id"),
                "transcript_date": transcript_date,
                "resolved_market_session_date": session_date,
                "detected_publish_timestamp": publish,
                "detected_live_start_timestamp": live_start,
                "session_open_timestamp": f"{session_date}T04:00:00",
                "session_close_timestamp": f"{session_date}T21:00:00",
                "availability_relation": relation,
                "can_use_as_same_session_context": bool(
                    same_session_allowed and int(counts.get("context", 0)) > 0
                ),
                "can_use_as_same_session_filter": bool(
                    same_session_allowed and int(counts.get("filter", 0)) > 0
                ),
                "can_use_as_same_session_market_map": bool(
                    same_session_allowed and int(counts.get("market_map", 0)) > 0
                ),
                "can_use_as_same_session_trade_rule": bool(
                    same_session_allowed and int(counts.get("trade_rule", 0)) > 0
                ),
                "reason_plain_english": _availability_reason(
                    relation=relation,
                    confidence=confidence,
                    transcript_date=transcript_date,
                    session_date=session_date,
                ),
            }
        )
    return _rows_frame(rows, _availability_schema()).sort(
        ["transcript_date", "clean_transcript_id"]
    )


def classify_availability_relation(
    *,
    transcript_date: str,
    resolved_market_session_date: str,
    timestamp: str,
    timing_confidence: str,
) -> str:
    """Classify transcript timing relative to a resolved market session."""

    transcript_day = _parse_date(transcript_date)
    session_day = _parse_date(resolved_market_session_date)
    if transcript_day is None or session_day is None:
        return "UNKNOWN"
    if transcript_day.weekday() >= 5:
        if _previous_trading_day(transcript_day) == session_day:
            return "WEEKEND_RECAP"
        if _next_trading_day(transcript_day) == session_day:
            return "NEXT_SESSION_PREP"
        return "HISTORICAL_PLAYBOOK_ONLY"
    if timing_confidence not in HIGH_MEDIUM:
        return "UNKNOWN"
    parsed = _parse_timestamp(timestamp)
    if parsed is None:
        return "UNKNOWN"
    if parsed.date() < session_day:
        return "NEXT_SESSION_PREP" if _next_trading_day(parsed.date()) == session_day else (
            "HISTORICAL_PLAYBOOK_ONLY"
        )
    if parsed.date() > session_day:
        return "POST_SESSION"
    if parsed.time() < time(4, 0):
        return "PRE_SESSION"
    if parsed.time() <= time(21, 0):
        return "DURING_SESSION"
    return "POST_SESSION"


def build_same_day_filter_evidence(
    *,
    remapped_replay: pl.DataFrame,
    playbook_matches: pl.DataFrame,
    availability_classification: pl.DataFrame,
    filter_replay: pl.DataFrame,
    replay: pl.DataFrame,
    historical_playbook_replay: pl.DataFrame,
) -> pl.DataFrame:
    """Build same-day filter evidence rows by replay date."""

    matches_by_date = _group_rows(playbook_matches, "replay_date")
    availability_by_clean = _availability_by_clean_id(availability_classification)
    filter_by_date = _rows_by_date(filter_replay, "trade_date")
    replay_by_date = _rows_by_date(replay, "trade_date")
    historical_by_date = _rows_by_date(historical_playbook_replay, "trade_date")
    rows = []
    for remap in remapped_replay.to_dicts() if not remapped_replay.is_empty() else []:
        original = _date_text(remap.get("original_replay_date"))
        date_matches = matches_by_date.get(original, [])
        filter_matches = [row for row in date_matches if _bool_value(row.get("usable_as_filter"))]
        timing_confirmed = [
            row
            for row in filter_matches
            if _bool_value(
                availability_by_clean.get(_text(row.get("clean_transcript_id")), {}).get(
                    "can_use_as_same_session_filter"
                )
            )
        ]
        unknown_timing = [
            row
            for row in filter_matches
            if _text(
                availability_by_clean.get(_text(row.get("clean_transcript_id")), {}).get(
                    "availability_relation"
                )
            )
            == "UNKNOWN"
        ]
        replay_row = replay_by_date.get(original, {})
        filter_row = filter_by_date.get(original, {})
        no_trade_active = _bool_value(filter_row.get("would_block_trade")) or _bool_value(
            replay_row.get("no_trade_filter_active")
        )
        base_candidates = 1 if _bool_value(replay_row.get("touched_wall")) else 0
        blocked = base_candidates if no_trade_active else 0
        evidence_status = _filter_evidence_status(
            filter_matches=len(filter_matches),
            timing_confirmed=len(timing_confirmed),
            historical=_historical_overlay_count(historical_by_date.get(original, {})),
        )
        rows.append(
            {
                "original_replay_date": original,
                "resolved_market_session_date": remap.get("resolved_market_session_date"),
                "same_day_filter_matches": len(filter_matches),
                "timing_confirmed_filter_matches": len(timing_confirmed),
                "unknown_timing_filter_matches": len(unknown_timing),
                "no_trade_filter_active": no_trade_active,
                "active_filter_logic_names": "|".join(_unique_names(filter_matches)),
                "base_trade_candidates_count": base_candidates,
                "blocked_trade_candidates_count": blocked,
                "known_bad_trades_blocked": 0,
                "known_good_trades_blocked": 0,
                "avoided_loss_proxy": 0.0,
                "opportunity_cost_proxy": 0.0,
                "net_filter_value_proxy": 0.0,
                "false_block_rate": None,
                "evidence_status": evidence_status,
                "plain_english_summary": _filter_summary(
                    original=original,
                    filter_matches=len(filter_matches),
                    timing_confirmed=len(timing_confirmed),
                    no_trade_active=no_trade_active,
                    status=evidence_status,
                ),
            }
        )
    return _rows_frame(rows, _filter_evidence_schema()).sort("original_replay_date")


def build_same_day_market_map_evidence(
    *,
    remapped_replay: pl.DataFrame,
    playbook_matches: pl.DataFrame,
    availability_classification: pl.DataFrame,
    replay: pl.DataFrame,
) -> pl.DataFrame:
    """Build same-day market-map evidence rows by replay date."""

    matches_by_date = _group_rows(playbook_matches, "replay_date")
    availability_by_clean = _availability_by_clean_id(availability_classification)
    replay_by_date = _rows_by_date(replay, "trade_date")
    rows = []
    for remap in remapped_replay.to_dicts() if not remapped_replay.is_empty() else []:
        original = _date_text(remap.get("original_replay_date"))
        replay_row = replay_by_date.get(original, {})
        date_matches = matches_by_date.get(original, [])
        map_matches = [row for row in date_matches if _bool_value(row.get("usable_as_market_map"))]
        timing_confirmed = [
            row
            for row in map_matches
            if _bool_value(
                availability_by_clean.get(_text(row.get("clean_transcript_id")), {}).get(
                    "can_use_as_same_session_market_map"
                )
            )
        ]
        basis = "AVAILABLE" in _text(remap.get("spot_basis_join_result")) or _bool_value(
            replay_row.get("basis_available")
        )
        spot_equiv = "SPOT_EQUIVALENT" in _text(remap.get("wall_mapping_result"))
        walls = _bool_value(replay_row.get("oi_available")) or _text(
            remap.get("cme_data_join_result")
        ).startswith("CME_JOIN")
        touched = _bool_value(replay_row.get("touched_wall"))
        rejected = _bool_value(replay_row.get("rejected_wall"))
        accepted = _bool_value(replay_row.get("accepted_wall"))
        confidence = _market_map_confidence(
            match_count=len(map_matches),
            timing_confirmed=len(timing_confirmed),
            basis=basis,
            walls=walls,
        )
        rows.append(
            {
                "original_replay_date": original,
                "resolved_market_session_date": remap.get("resolved_market_session_date"),
                "same_day_market_map_matches": len(map_matches),
                "timing_confirmed_market_map_matches": len(timing_confirmed),
                "active_market_map_logic_names": "|".join(_unique_names(map_matches)),
                "cme_oi_walls_available": walls,
                "basis_available": basis,
                "spot_equivalent_walls_available": bool(basis and spot_equiv),
                "top_wall_above": _number_or_none(replay_row.get("nearest_wall_above_price"))
                or _number_or_none(replay_row.get("top_oi_wall_1")),
                "top_wall_below": _number_or_none(replay_row.get("nearest_wall_below_price"))
                or _number_or_none(replay_row.get("top_oi_wall_2")),
                "price_touched_wall": touched,
                "price_rejected_wall": rejected,
                "price_accepted_wall": accepted,
                "map_hit_proxy": bool(walls and (touched or rejected or accepted)),
                "confidence": confidence,
                "plain_english_summary": _market_map_summary(
                    original=original,
                    map_matches=len(map_matches),
                    timing_confirmed=len(timing_confirmed),
                    basis=basis,
                    walls=walls,
                    confidence=confidence,
                ),
            }
        )
    return _rows_frame(rows, _market_map_schema()).sort("original_replay_date")


def build_current_week_evidence_scorecard(
    *,
    remapped_replay: pl.DataFrame,
    filter_evidence: pl.DataFrame,
    market_map_evidence: pl.DataFrame,
    replay: pl.DataFrame,
) -> pl.DataFrame:
    """Build a current-week evidence scorecard."""

    filter_by_date = _rows_by_date(filter_evidence, "original_replay_date")
    market_by_date = _rows_by_date(market_map_evidence, "original_replay_date")
    replay_by_date = _rows_by_date(replay, "trade_date")
    rows = []
    for remap in remapped_replay.to_dicts() if not remapped_replay.is_empty() else []:
        original = _date_text(remap.get("original_replay_date"))
        filter_row = filter_by_date.get(original, {})
        market_row = market_by_date.get(original, {})
        replay_row = replay_by_date.get(original, {})
        label = _date_label(filter_row, market_row)
        rows.append(
            {
                "date": original,
                "resolved_market_session_date": remap.get("resolved_market_session_date"),
                "cme_data_available": _text(remap.get("cme_data_join_result")),
                "oi_walls_visible": _bool_value(market_row.get("cme_oi_walls_available")),
                "basis_available": _bool_value(market_row.get("basis_available")),
                "same_day_guru_logic": _same_day_logic_summary(filter_row, market_row),
                "timing_status": _text(filter_row.get("evidence_status"))
                or _text(market_row.get("confidence")),
                "no_trade_filter_active": _bool_value(filter_row.get("no_trade_filter_active")),
                "market_map_aligned_with_oi_wall": _bool_value(market_row.get("map_hit_proxy")),
                "what_happened_after": _what_happened_after(replay_row),
                "what_can_we_learn": _what_can_we_learn(filter_row, market_row),
                "what_cannot_be_proven": _what_cannot_be_proven(filter_row),
                "final_per_date_label": label,
            }
        )
    return _rows_frame(rows, _scorecard_schema()).sort("date")


def build_transcript_metadata_fetch_plan(timing_audit: pl.DataFrame) -> pl.DataFrame:
    """Create a metadata fetch/update plan for unknown or low-confidence timing rows."""

    rows = []
    for row in timing_audit.to_dicts() if not timing_audit.is_empty() else []:
        confidence = _text(row.get("timing_confidence"))
        source = _text(row.get("timing_source"))
        if confidence in HIGH_MEDIUM and source not in {"SRT_TIMECODE"}:
            continue
        rows.append(
            {
                "clean_transcript_id": row.get("clean_transcript_id"),
                "transcript_date": row.get("transcript_date"),
                "required_metadata": "video_url|video_id|publish_time|live_start_time|live_end_time",
                "suggested_file_needed": ".info.json or manifest update with publish/live timestamps",
                "suggested_command_template": (
                    "yt-dlp --skip-download --write-info-json <video_url>"
                ),
                "where_to_place_file": "configured transcript root beside the transcript text",
                "rerun_command": "python -m research_xau_vol_oi.report",
            }
        )
    return _rows_frame(rows, _metadata_fetch_schema()).sort(
        ["transcript_date", "clean_transcript_id"]
    )


def choose_timing_evidence_recommendation(
    *,
    availability: pl.DataFrame,
    filter_evidence: pl.DataFrame,
    market_map_evidence: pl.DataFrame,
    fetch_plan: pl.DataFrame,
) -> str:
    """Choose final timing evidence recommendation."""

    confirmed_filters = _sum_int(filter_evidence, "timing_confirmed_filter_matches")
    unknown_filters = _sum_int(filter_evidence, "unknown_timing_filter_matches")
    if confirmed_filters > 0 and unknown_filters == 0 and fetch_plan.is_empty():
        return "SAME_DAY_FILTER_TIMING_CONFIRMED"
    if _sum_int(filter_evidence, "same_day_filter_matches") > 0 and not fetch_plan.is_empty():
        return "NEEDS_TRANSCRIPT_METADATA"
    if _sum_int(filter_evidence, "same_day_filter_matches") > 0:
        return "SAME_DAY_FILTER_CONTEXT_READY"
    if _sum_int(market_map_evidence, "same_day_market_map_matches") > 0:
        return "SAME_DAY_MARKET_MAP_CONTEXT_READY"
    if not availability.is_empty() and _any_state(availability, "availability_relation", "POST_SESSION"):
        return "POST_EVENT_ONLY"
    return "HISTORICAL_PLAYBOOK_ONLY"


def timing_evidence_report_lines(result: TimingEvidenceResult | None) -> list[str]:
    """Return Markdown lines for embedding in the main research report."""

    if result is None:
        return ["Transcript timing evidence layer was not run."]
    return [
        "## Transcript Timing Metadata Audit",
        "",
        f"- Final recommendation: `{result.final_recommendation}`",
        "",
        _frame_markdown(result.transcript_timing_metadata_audit),
        "",
        "## Availability Relation Classification",
        "",
        _frame_markdown(result.transcript_availability_classification),
        "",
        "## Same-Day Filter Evidence",
        "",
        _frame_markdown(result.same_day_filter_evidence),
        "",
        "## Same-Day Market-Map Evidence",
        "",
        _frame_markdown(result.same_day_market_map_evidence),
        "",
        "## Current-Week Evidence Report",
        "",
        _frame_markdown(result.current_week_evidence_scorecard),
        "",
        "## Transcript Metadata Fetch Plan",
        "",
        _frame_markdown(result.transcript_metadata_fetch_plan),
        "",
        "## What Can Be Used Now vs What Needs Timing Proof",
        "",
        *_use_now_vs_timing_lines(result),
    ]


def transcript_timing_metadata_audit_markdown(frame: pl.DataFrame) -> str:
    """Render timing metadata audit."""

    return _safe_report(
        "\n".join(
            [
                "# Transcript Timing Metadata Audit",
                "",
                "Only high/medium confidence absolute timestamps can support same-session use.",
                "",
                _frame_markdown(frame),
            ]
        )
    )


def transcript_availability_classification_markdown(frame: pl.DataFrame) -> str:
    """Render availability relation classification."""

    return _safe_report(
        "\n".join(
            [
                "# Transcript Availability Classification",
                "",
                "Unknown, post-session, and weekend recap text cannot be used as same-session input.",
                "",
                _frame_markdown(frame),
            ]
        )
    )


def same_day_filter_evidence_markdown(frame: pl.DataFrame) -> str:
    """Render same-day filter evidence."""

    return _safe_report(
        "\n".join(
            [
                "# Same-Day Filter Evidence",
                "",
                "Filter evidence is reported as context unless timing is confirmed.",
                "",
                _frame_markdown(frame),
            ]
        )
    )


def same_day_market_map_evidence_markdown(frame: pl.DataFrame) -> str:
    """Render same-day market-map evidence."""

    return _safe_report(
        "\n".join(
            [
                "# Same-Day Market-Map Evidence",
                "",
                "Spot-equivalent wall evidence requires basis availability.",
                "",
                _frame_markdown(frame),
            ]
        )
    )


def current_week_evidence_report_markdown(
    *,
    scorecard: pl.DataFrame,
    filter_evidence: pl.DataFrame,
    market_map_evidence: pl.DataFrame,
    replay: pl.DataFrame,
) -> str:
    """Render a narrative current-week evidence report."""

    filter_by_date = _rows_by_date(filter_evidence, "original_replay_date")
    market_by_date = _rows_by_date(market_map_evidence, "original_replay_date")
    replay_by_date = _rows_by_date(replay, "trade_date")
    lines = [
        "# Current-Week Evidence Report",
        "",
        "This is a research evidence summary. It is not a trading instruction or performance claim.",
        "",
    ]
    for row in scorecard.to_dicts() if not scorecard.is_empty() else []:
        day = _date_text(row.get("date"))
        filter_row = filter_by_date.get(day, {})
        market_row = market_by_date.get(day, {})
        replay_row = replay_by_date.get(day, {})
        lines.extend(
            [
                f"## {day}",
                "",
                f"- CME data available: {_text(row.get('cme_data_available'))}",
                f"- OI walls visible: {_yes_no(row.get('oi_walls_visible'))}",
                f"- Basis available: {_yes_no(row.get('basis_available'))}",
                f"- Same-day guru logic matched: {_same_day_logic_summary(filter_row, market_row)}",
                f"- Timing confirmed or unknown: {_text(row.get('timing_status'))}",
                f"- No-trade filter active: {_yes_no(row.get('no_trade_filter_active'))}",
                f"- Market-map aligned with OI wall: {_yes_no(row.get('market_map_aligned_with_oi_wall'))}",
                f"- What happened after: {_what_happened_after(replay_row)}",
                f"- What can we learn: {_what_can_we_learn(filter_row, market_row)}",
                f"- What cannot be proven: {_what_cannot_be_proven(filter_row)}",
                f"- Final per-date label: `{_text(row.get('final_per_date_label'))}`",
                "",
            ]
        )
    return _safe_report("\n".join(lines))


def transcript_metadata_fetch_plan_markdown(frame: pl.DataFrame) -> str:
    """Render metadata fetch plan."""

    return _safe_report(
        "\n".join(
            [
                "# Transcript Metadata Fetch Plan",
                "",
                "No network fetch is run here. Add local metadata files or update the manifest, then rerun the report.",
                "",
                _frame_markdown(frame),
            ]
        )
    )


def append_transcript_timing_evidence_sections(path: Path, result: TimingEvidenceResult) -> None:
    """Append or replace timing evidence sections in the main report."""

    marker = "\n## Transcript Timing Metadata Audit\n"
    section = _safe_report("\n".join(timing_evidence_report_lines(result)))
    existing = path.read_text(encoding="utf-8") if path.exists() else "# XAU/USD Vol-OI Research Report\n"
    if marker in existing:
        existing = existing.split(marker, 1)[0].rstrip()
    path.write_text(
        _redact_text(existing.rstrip()) + "\n\n" + section + "\n",
        encoding="utf-8",
    )


def _use_now_vs_timing_lines(result: TimingEvidenceResult) -> list[str]:
    filter_matches = _sum_int(result.same_day_filter_evidence, "same_day_filter_matches")
    confirmed = _sum_int(result.same_day_filter_evidence, "timing_confirmed_filter_matches")
    fetch_rows = result.transcript_metadata_fetch_plan.height
    return [
        f"- Same-day filter/context rows usable now as context-only: `{filter_matches}`",
        f"- Timing-confirmed same-session filter rows: `{confirmed}`",
        f"- Transcript metadata rows still needed: `{fetch_rows}`",
        "- Strict trade-rule use still requires explicit condition, level, direction, and target or invalidation.",
    ]


def _filter_evidence_status(*, filter_matches: int, timing_confirmed: int, historical: int) -> str:
    if timing_confirmed:
        return "TIMING_CONFIRMED"
    if filter_matches:
        return "TIMING_UNKNOWN_CONTEXT_ONLY"
    if historical:
        return "HISTORICAL_PLAYBOOK_ONLY"
    return "INSUFFICIENT_DATA"


def _market_map_confidence(
    *,
    match_count: int,
    timing_confirmed: int,
    basis: bool,
    walls: bool,
) -> str:
    if not match_count:
        return "LOW"
    if not timing_confirmed:
        return "CONTEXT_ONLY"
    if basis and walls:
        return "HIGH"
    if walls:
        return "MEDIUM"
    return "LOW"


def _date_label(filter_row: dict[str, Any], market_row: dict[str, Any]) -> str:
    filter_status = _text(filter_row.get("evidence_status"))
    if filter_status == "TIMING_CONFIRMED":
        return "USEFUL_PILOT_EVIDENCE"
    if filter_status == "TIMING_UNKNOWN_CONTEXT_ONLY":
        return "TIMING_UNKNOWN"
    if _text(market_row.get("confidence")) == "CONTEXT_ONLY":
        return "CONTEXT_ONLY"
    if filter_status == "HISTORICAL_PLAYBOOK_ONLY":
        return "CONTEXT_ONLY"
    return "NEEDS_MORE_DATA"


def _availability_reason(
    *,
    relation: str,
    confidence: str,
    transcript_date: str,
    session_date: str,
) -> str:
    if relation in {"PRE_SESSION", "DURING_SESSION"} and confidence in HIGH_MEDIUM:
        return f"{transcript_date} timing is {confidence}; it can be reviewed for same-session context/filter use against {session_date}."
    if relation == "POST_SESSION":
        return "Transcript appears after session close; keep it out of same-session input."
    if relation == "WEEKEND_RECAP":
        return "Weekend transcript is recap/post-event context, not Friday same-session input."
    if relation == "NEXT_SESSION_PREP":
        return "Transcript can be reviewed only for the next valid session."
    if relation == "HISTORICAL_PLAYBOOK_ONLY":
        return "Transcript timing is outside the resolved session; use as historical playbook context only."
    return "Absolute publish/live timing is missing or low confidence; use as context-only until metadata is added."


def _filter_summary(
    *,
    original: str,
    filter_matches: int,
    timing_confirmed: int,
    no_trade_active: bool,
    status: str,
) -> str:
    if timing_confirmed:
        return f"{original}: {filter_matches} same-day filter matches with timing confirmation; no-trade active={no_trade_active}."
    if filter_matches:
        return f"{original}: {filter_matches} same-day filter matches, but timing is not confirmed, so this is context-only."
    return f"{original}: no same-day filter match; status {status}."


def _market_map_summary(
    *,
    original: str,
    map_matches: int,
    timing_confirmed: int,
    basis: bool,
    walls: bool,
    confidence: str,
) -> str:
    return (
        f"{original}: market-map matches={map_matches}, timing_confirmed={timing_confirmed}, "
        f"basis={basis}, CME walls={walls}, confidence={confidence}."
    )


def _same_day_logic_summary(filter_row: dict[str, Any], market_row: dict[str, Any]) -> str:
    return (
        f"filters={int(_float_or_zero(filter_row.get('same_day_filter_matches')))}, "
        f"market_maps={int(_float_or_zero(market_row.get('same_day_market_map_matches')))}"
    )


def _what_happened_after(replay_row: dict[str, Any]) -> str:
    facts = []
    if _bool_value(replay_row.get("touched_wall")):
        facts.append("price touched an OI wall")
    if _bool_value(replay_row.get("rejected_wall")):
        facts.append("wall rejection was observed")
    if _bool_value(replay_row.get("accepted_wall")):
        facts.append("wall acceptance was observed")
    if _bool_value(replay_row.get("stayed_inside_range")):
        facts.append("price stayed inside the tracked range")
    if _bool_value(replay_row.get("broke_range")):
        facts.append("price broke the tracked range")
    return "; ".join(facts) if facts else "outcome labels are incomplete or unknown"


def _what_can_we_learn(filter_row: dict[str, Any], market_row: dict[str, Any]) -> str:
    if _text(filter_row.get("evidence_status")) == "TIMING_CONFIRMED":
        return "Same-day filter text and CME wall context can be compared as timing-confirmed research evidence."
    if _text(filter_row.get("evidence_status")) == "TIMING_UNKNOWN_CONTEXT_ONLY":
        return "Same-day text matches the filter playbook, but timing metadata is needed before same-session use."
    if _text(market_row.get("confidence")) == "CONTEXT_ONLY":
        return "Same-day market-map text aligns with CME context as context-only evidence."
    return "Historical playbook context is available, but same-day timing evidence is not established."


def _what_cannot_be_proven(filter_row: dict[str, Any]) -> str:
    if _text(filter_row.get("evidence_status")) == "TIMING_UNKNOWN_CONTEXT_ONLY":
        return "It cannot be proven that the same-day filter text was available before or during the relevant event."
    return "This report does not establish strict trade rules or performance claims."


def _match_counts_by_clean_id(matches: pl.DataFrame) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    for row in matches.to_dicts() if not matches.is_empty() else []:
        clean_id = _text(row.get("clean_transcript_id"))
        item = counts.setdefault(clean_id, {"context": 0, "filter": 0, "market_map": 0, "trade_rule": 0})
        if _bool_value(row.get("usable_as_context")):
            item["context"] += 1
        if _bool_value(row.get("usable_as_filter")):
            item["filter"] += 1
        if _bool_value(row.get("usable_as_market_map")):
            item["market_map"] += 1
        if _bool_value(row.get("usable_as_trade_rule")):
            item["trade_rule"] += 1
    return counts


def _availability_by_clean_id(frame: pl.DataFrame) -> dict[str, dict[str, Any]]:
    return {
        _text(row.get("clean_transcript_id")): row
        for row in frame.to_dicts()
        if _text(row.get("clean_transcript_id"))
    }


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


def _unique_names(rows: list[dict[str, Any]]) -> list[str]:
    names = []
    for row in rows:
        name = _text(row.get("logic_name"))
        if name and name not in names:
            names.append(name)
    return names


def _first_timestamp(payload: dict[str, Any], keys: Iterable[str]) -> str:
    for key in keys:
        value = payload.get(key)
        parsed = _timestamp_from_value(value)
        if parsed:
            return parsed
    return ""


def _timestamp_from_value(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc).replace(tzinfo=None).isoformat()
        except (OverflowError, OSError, ValueError):
            return ""
    text = str(value).strip()
    if re.fullmatch(r"\d{10}(?:\.\d+)?", text):
        return _timestamp_from_value(float(text))
    parsed = _parse_timestamp(text)
    return parsed.isoformat() if parsed else ""


def _upload_date_timestamp(value: Any) -> str:
    text = str(value or "").strip()
    match = re.fullmatch(r"(20\d{2})(\d{2})(\d{2})", text)
    if not match:
        return ""
    year, month, day = match.groups()
    return f"{year}-{month}-{day}T00:00:00"


def _parse_timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _iter_transcript_files(root: Path) -> Iterable[Path]:
    try:
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in {".txt", ".srt"} and path.stat().st_size <= 2_000_000:
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


def _number_or_none(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


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


def _count_state(frame: pl.DataFrame, column: str, value: str) -> int:
    if frame.is_empty() or column not in frame.columns:
        return 0
    return sum(1 for item in frame.get_column(column).to_list() if _text(item) == value)


def _any_state(frame: pl.DataFrame, column: str, value: str) -> bool:
    return _count_state(frame, column, value) > 0


def _float_or_zero(value: Any) -> float:
    try:
        if value in (None, ""):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _yes_no(value: Any) -> str:
    return "yes" if _bool_value(value) else "no"


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


def _timing_audit_schema() -> dict[str, Any]:
    return {
        "clean_transcript_id": pl.String,
        "transcript_date": pl.String,
        "title_hash": pl.String,
        "content_hash": pl.String,
        "detected_publish_timestamp": pl.String,
        "detected_live_start_timestamp": pl.String,
        "detected_live_end_timestamp": pl.String,
        "detected_transcript_start_timestamp": pl.String,
        "detected_transcript_end_timestamp": pl.String,
        "timing_source": pl.String,
        "timing_confidence": pl.String,
        "timing_notes": pl.String,
    }


def _availability_schema() -> dict[str, Any]:
    return {
        "clean_transcript_id": pl.String,
        "transcript_date": pl.String,
        "resolved_market_session_date": pl.String,
        "detected_publish_timestamp": pl.String,
        "detected_live_start_timestamp": pl.String,
        "session_open_timestamp": pl.String,
        "session_close_timestamp": pl.String,
        "availability_relation": pl.String,
        "can_use_as_same_session_context": pl.Boolean,
        "can_use_as_same_session_filter": pl.Boolean,
        "can_use_as_same_session_market_map": pl.Boolean,
        "can_use_as_same_session_trade_rule": pl.Boolean,
        "reason_plain_english": pl.String,
    }


def _filter_evidence_schema() -> dict[str, Any]:
    return {
        "original_replay_date": pl.String,
        "resolved_market_session_date": pl.String,
        "same_day_filter_matches": pl.Int64,
        "timing_confirmed_filter_matches": pl.Int64,
        "unknown_timing_filter_matches": pl.Int64,
        "no_trade_filter_active": pl.Boolean,
        "active_filter_logic_names": pl.String,
        "base_trade_candidates_count": pl.Int64,
        "blocked_trade_candidates_count": pl.Int64,
        "known_bad_trades_blocked": pl.Int64,
        "known_good_trades_blocked": pl.Int64,
        "avoided_loss_proxy": pl.Float64,
        "opportunity_cost_proxy": pl.Float64,
        "net_filter_value_proxy": pl.Float64,
        "false_block_rate": pl.Float64,
        "evidence_status": pl.String,
        "plain_english_summary": pl.String,
    }


def _market_map_schema() -> dict[str, Any]:
    return {
        "original_replay_date": pl.String,
        "resolved_market_session_date": pl.String,
        "same_day_market_map_matches": pl.Int64,
        "timing_confirmed_market_map_matches": pl.Int64,
        "active_market_map_logic_names": pl.String,
        "cme_oi_walls_available": pl.Boolean,
        "basis_available": pl.Boolean,
        "spot_equivalent_walls_available": pl.Boolean,
        "top_wall_above": pl.Float64,
        "top_wall_below": pl.Float64,
        "price_touched_wall": pl.Boolean,
        "price_rejected_wall": pl.Boolean,
        "price_accepted_wall": pl.Boolean,
        "map_hit_proxy": pl.Boolean,
        "confidence": pl.String,
        "plain_english_summary": pl.String,
    }


def _scorecard_schema() -> dict[str, Any]:
    return {
        "date": pl.String,
        "resolved_market_session_date": pl.String,
        "cme_data_available": pl.String,
        "oi_walls_visible": pl.Boolean,
        "basis_available": pl.Boolean,
        "same_day_guru_logic": pl.String,
        "timing_status": pl.String,
        "no_trade_filter_active": pl.Boolean,
        "market_map_aligned_with_oi_wall": pl.Boolean,
        "what_happened_after": pl.String,
        "what_can_we_learn": pl.String,
        "what_cannot_be_proven": pl.String,
        "final_per_date_label": pl.String,
    }


def _metadata_fetch_schema() -> dict[str, Any]:
    return {
        "clean_transcript_id": pl.String,
        "transcript_date": pl.String,
        "required_metadata": pl.String,
        "suggested_file_needed": pl.String,
        "suggested_command_template": pl.String,
        "where_to_place_file": pl.String,
        "rerun_command": pl.String,
    }


def main() -> None:
    """CLI entry point."""

    result = run_transcript_timing_evidence_layer()
    print(f"final_recommendation: {result.final_recommendation}")
    print(f"timing_rows: {result.transcript_timing_metadata_audit.height}")
    print(f"metadata_fetch_rows: {result.transcript_metadata_fetch_plan.height}")


if __name__ == "__main__":
    main()
