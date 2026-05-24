"""YouTube metadata recovery and timing reclassification.

This module is research-only. It discovers local YouTube metadata, prepares
user-controlled metadata fetch requests, normalizes timestamps, and re-runs the
same-day evidence classification without downloading videos or treating unknown
timing as same-session proof.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import polars as pl

from research_xau_vol_oi.config import ResearchConfig
from research_xau_vol_oi.transcript_timing_evidence import (
    build_same_day_filter_evidence,
    build_same_day_market_map_evidence,
    build_transcript_availability_classification,
    current_week_evidence_report_markdown,
)


FORBIDDEN_REPORT_PHRASES = (
    "profitable",
    "safe to trade",
    "live ready",
    "live-ready",
    "money-readiness",
)
HIGH_MEDIUM = {"HIGH", "MEDIUM"}
DEFAULT_METADATA_COMMAND = "yt-dlp --skip-download --write-info-json <video_url>"
MANUAL_TEMPLATE_COLUMNS = (
    "clean_transcript_id",
    "video_url",
    "video_id",
    "publish_time",
    "live_start_time",
    "live_end_time",
    "timezone",
    "source_notes",
    "reviewer_confidence",
)


@dataclass(frozen=True)
class YouTubeMetadataCandidate:
    """Recovered local metadata for one transcript candidate."""

    video_id: str = ""
    video_url: str = ""
    publish_time: str = ""
    live_start_time: str = ""
    live_end_time: str = ""
    raw_timezone: str = ""
    metadata_source: str = "NONE"
    timing_confidence: str = "UNKNOWN"
    redacted_metadata_path: str = ""
    notes: str = ""


@dataclass(frozen=True)
class YouTubeMetadataRecoveryResult:
    """Generated metadata recovery and timing reclassification artifacts."""

    youtube_metadata_local_discovery: pl.DataFrame
    youtube_metadata_fetch_requests: pl.DataFrame
    youtube_metadata_manual_entry_template: pl.DataFrame
    transcript_timezone_audit: pl.DataFrame
    transcript_availability_classification_after_metadata: pl.DataFrame
    same_day_filter_evidence_after_metadata: pl.DataFrame
    same_day_market_map_evidence_after_metadata: pl.DataFrame
    current_week_evidence_report_after_metadata_markdown: str
    final_recommendation: str
    fetch_commands_sh: str
    fetch_commands_ps1: str


def run_youtube_metadata_recovery_layer(
    *,
    output_dir: str | Path = "outputs",
    transcript_source_roots: Iterable[str | Path] | None = None,
    local_debug: bool = False,
) -> YouTubeMetadataRecoveryResult:
    """Run local metadata discovery, fetch planning, and reclassification."""

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    inputs = load_youtube_metadata_recovery_inputs(output_root)
    roots = resolve_transcript_source_roots(transcript_source_roots)
    local_index = build_local_metadata_index(roots=roots, output_root=output_root)
    manual_existing = _load_optional(output_root / "youtube_metadata_manual_entry_template.csv")
    result = build_youtube_metadata_recovery(
        inputs,
        local_metadata_index=local_index,
        manual_existing=manual_existing,
        local_debug=local_debug,
    )

    public_discovery = _public_discovery(result.youtube_metadata_local_discovery)
    _write_csv_and_md(
        output_root / "youtube_metadata_local_discovery.csv",
        output_root / "youtube_metadata_local_discovery.md",
        public_discovery,
        youtube_metadata_local_discovery_markdown,
    )
    result.youtube_metadata_fetch_requests.write_csv(
        output_root / "youtube_metadata_fetch_requests.csv"
    )
    (output_root / "youtube_metadata_fetch_plan.md").write_text(
        youtube_metadata_fetch_plan_markdown(result.youtube_metadata_fetch_requests),
        encoding="utf-8",
    )
    (output_root / "youtube_metadata_fetch_commands.sh").write_text(
        _safe_report(result.fetch_commands_sh),
        encoding="utf-8",
    )
    (output_root / "youtube_metadata_fetch_commands.ps1").write_text(
        _safe_report(result.fetch_commands_ps1),
        encoding="utf-8",
    )
    result.youtube_metadata_manual_entry_template.write_csv(
        output_root / "youtube_metadata_manual_entry_template.csv"
    )
    _write_csv_and_md(
        output_root / "transcript_timezone_audit.csv",
        output_root / "transcript_timezone_audit.md",
        result.transcript_timezone_audit,
        transcript_timezone_audit_markdown,
    )
    result.transcript_availability_classification_after_metadata.write_csv(
        output_root / "transcript_availability_classification_after_metadata.csv"
    )
    result.same_day_filter_evidence_after_metadata.write_csv(
        output_root / "same_day_filter_evidence_after_metadata.csv"
    )
    result.same_day_market_map_evidence_after_metadata.write_csv(
        output_root / "same_day_market_map_evidence_after_metadata.csv"
    )
    (output_root / "current_week_evidence_report_after_metadata.md").write_text(
        _safe_report(result.current_week_evidence_report_after_metadata_markdown),
        encoding="utf-8",
    )
    append_youtube_metadata_recovery_sections(output_root / "research_report.md", result)
    return result


def load_youtube_metadata_recovery_inputs(output_root: Path) -> dict[str, pl.DataFrame]:
    """Load optional artifacts needed by the recovery layer."""

    paths = {
        "transcript_timing_metadata_audit": output_root / "transcript_timing_metadata_audit.csv",
        "transcript_metadata_fetch_plan": output_root / "transcript_metadata_fetch_plan.csv",
        "clean_transcript_set": output_root / "clean_transcript_set.csv",
        "transcript_identity_audit": output_root / "transcript_identity_audit.csv",
        "transcript_corpus_manifest": output_root / "transcript_corpus_manifest.csv",
        "same_day_playbook_matches": output_root / "same_day_playbook_matches.csv",
        "current_week_replay_after_market_session_remap": (
            output_root / "current_week_replay_after_market_session_remap.csv"
        ),
        "current_week_cme_guru_replay": output_root / "current_week_cme_guru_replay.csv",
        "current_week_guru_filter_replay": output_root / "current_week_guru_filter_replay.csv",
        "current_week_cme_guru_playbook_replay": (
            output_root / "current_week_cme_guru_playbook_replay.csv"
        ),
        "transcript_availability_classification": (
            output_root / "transcript_availability_classification.csv"
        ),
        "same_day_filter_evidence": output_root / "same_day_filter_evidence.csv",
        "same_day_market_map_evidence": output_root / "same_day_market_map_evidence.csv",
    }
    return {name: _load_optional(path) for name, path in paths.items()}


def build_youtube_metadata_recovery(
    inputs: dict[str, pl.DataFrame],
    *,
    local_metadata_index: dict[str, YouTubeMetadataCandidate] | None = None,
    manual_existing: pl.DataFrame | None = None,
    local_debug: bool = False,
) -> YouTubeMetadataRecoveryResult:
    """Build all YouTube metadata recovery and reclassification artifacts."""

    local_metadata_index = local_metadata_index or {}
    timing = _frame(inputs, "transcript_timing_metadata_audit")
    fetch_plan = _frame(inputs, "transcript_metadata_fetch_plan")
    manual_template = build_manual_metadata_entry_template(fetch_plan, manual_existing)
    manual_candidates = manual_metadata_candidates(manual_template)
    discovery = build_youtube_metadata_local_discovery(
        timing_audit=timing,
        fetch_plan=fetch_plan,
        local_metadata_index=local_metadata_index,
        manual_candidates=manual_candidates,
        local_debug=local_debug,
    )
    fetch_requests = build_youtube_metadata_fetch_requests(discovery)
    fetch_commands_sh, fetch_commands_ps1 = generate_metadata_fetch_command_texts(
        discovery,
        local_debug=local_debug,
    )
    recovered_timing = build_timing_audit_after_metadata(
        timing_audit=timing,
        discovery=discovery,
        manual_candidates=manual_candidates,
    )
    timezone_audit = build_transcript_timezone_audit(recovered_timing)
    reclass_timing = apply_timezone_confidence_to_timing_audit(
        recovered_timing,
        timezone_audit,
    )
    availability = build_transcript_availability_classification(
        timing_audit=reclass_timing,
        remapped_replay=_frame(inputs, "current_week_replay_after_market_session_remap"),
        playbook_matches=_frame(inputs, "same_day_playbook_matches"),
    )
    filter_evidence = build_same_day_filter_evidence(
        remapped_replay=_frame(inputs, "current_week_replay_after_market_session_remap"),
        playbook_matches=_frame(inputs, "same_day_playbook_matches"),
        availability_classification=availability,
        filter_replay=_frame(inputs, "current_week_guru_filter_replay"),
        replay=_frame(inputs, "current_week_cme_guru_replay"),
        historical_playbook_replay=_frame(inputs, "current_week_cme_guru_playbook_replay"),
    )
    market_map = build_same_day_market_map_evidence(
        remapped_replay=_frame(inputs, "current_week_replay_after_market_session_remap"),
        playbook_matches=_frame(inputs, "same_day_playbook_matches"),
        availability_classification=availability,
        replay=_frame(inputs, "current_week_cme_guru_replay"),
    )
    scorecard = _scorecard_after_metadata(
        availability=availability,
        filter_evidence=filter_evidence,
        market_map=market_map,
        remapped_replay=_frame(inputs, "current_week_replay_after_market_session_remap"),
    )
    current_week_report = metadata_reclassification_report_markdown(
        before_availability=_frame(inputs, "transcript_availability_classification"),
        after_availability=availability,
        before_filter=_frame(inputs, "same_day_filter_evidence"),
        after_filter=filter_evidence,
        before_market_map=_frame(inputs, "same_day_market_map_evidence"),
        after_market_map=market_map,
    )
    current_week_report += "\n\n" + current_week_evidence_report_markdown(
        scorecard=scorecard,
        filter_evidence=filter_evidence,
        market_map_evidence=market_map,
        replay=_frame(inputs, "current_week_cme_guru_replay"),
    )
    final = choose_youtube_metadata_recovery_recommendation(
        discovery=discovery,
        fetch_requests=fetch_requests,
        availability=availability,
        filter_evidence=filter_evidence,
    )
    return YouTubeMetadataRecoveryResult(
        youtube_metadata_local_discovery=discovery,
        youtube_metadata_fetch_requests=fetch_requests,
        youtube_metadata_manual_entry_template=manual_template,
        transcript_timezone_audit=timezone_audit,
        transcript_availability_classification_after_metadata=availability,
        same_day_filter_evidence_after_metadata=filter_evidence,
        same_day_market_map_evidence_after_metadata=market_map,
        current_week_evidence_report_after_metadata_markdown=current_week_report,
        final_recommendation=final,
        fetch_commands_sh=fetch_commands_sh,
        fetch_commands_ps1=fetch_commands_ps1,
    )


def resolve_transcript_source_roots(
    roots: Iterable[str | Path] | None = None,
    *,
    config: ResearchConfig | None = None,
) -> tuple[Path, ...]:
    """Resolve transcript roots from config/env only."""

    cfg = config or ResearchConfig()
    configured = [Path(root) for root in (roots or ())]
    for env_name in ("GURU_TRANSCRIPT_SOURCE_ROOTS", "XAU_TRANSCRIPT_SOURCE_ROOTS"):
        value = os.getenv(env_name)
        if value:
            configured.extend(
                Path(item.strip()) for item in value.split(os.pathsep) if item.strip()
            )
    for data_root in cfg.data_roots:
        configured.append(Path(data_root) / "reports" / "youtube_transcripts")
    if os.getenv("XAU_ENABLE_CODEX_SESSION_METADATA_SCAN", "").lower() in {"1", "true", "yes"}:
        value = os.getenv("XAU_CODEX_SESSION_ROOTS", "")
        configured.extend(Path(item.strip()) for item in value.split(os.pathsep) if item.strip())
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


def build_local_metadata_index(
    *,
    roots: Iterable[Path],
    output_root: Path,
) -> dict[str, YouTubeMetadataCandidate]:
    """Build a content-hash keyed local metadata index from configured roots."""

    manifest_by_video = build_manifest_video_index([*roots, output_root])
    index: dict[str, YouTubeMetadataCandidate] = {}
    for root in roots:
        for path in _iter_transcript_files(root):
            text = _read_text(path)
            content_hash = _content_hash(text)
            if not content_hash or content_hash in index:
                continue
            video_id = extract_video_id(path.name) or extract_video_id(text[:500])
            manifest = manifest_by_video.get(video_id, YouTubeMetadataCandidate())
            metadata = parse_adjacent_info_json(path)
            header = parse_transcript_header_metadata(text)
            best = choose_metadata_candidate(
                metadata=metadata,
                manifest=manifest,
                header=header,
                filename_video_id=video_id,
                path=path,
            )
            index[content_hash] = best
    return index


def build_manifest_video_index(roots: Iterable[Path]) -> dict[str, YouTubeMetadataCandidate]:
    """Read local manifest CSV/JSONL files and map video id to safe metadata."""

    candidates: dict[str, YouTubeMetadataCandidate] = {}
    for root in roots:
        if not root.exists():
            continue
        for path in _iter_manifest_files(root):
            for row in _read_manifest_rows(path):
                video_id = _first_text(row, ("video_id", "id", "youtube_id"))
                if not video_id:
                    video_id = extract_video_id(_first_text(row, ("url", "webpage_url")))
                if not video_id or video_id in candidates:
                    continue
                url = _raw_first_text(row, ("url", "webpage_url"))
                timing = parse_info_json_metadata(row)
                candidates[video_id] = YouTubeMetadataCandidate(
                    video_id=video_id,
                    video_url=url or _youtube_url(video_id),
                    publish_time=timing.publish_time,
                    live_start_time=timing.live_start_time,
                    live_end_time=timing.live_end_time,
                    raw_timezone=timing.raw_timezone,
                    metadata_source="MANIFEST",
                    timing_confidence=timing.timing_confidence
                    if any((timing.publish_time, timing.live_start_time, timing.live_end_time))
                    else "UNKNOWN",
                    redacted_metadata_path=_redacted_metadata_path(path),
                    notes="Video identity recovered from local manifest.",
                )
    return candidates


def parse_info_json_metadata(payload: dict[str, Any]) -> YouTubeMetadataCandidate:
    """Parse yt-dlp/YouTube style metadata without fetching anything."""

    video_id = _first_text(payload, ("id", "video_id", "youtube_id"))
    url = _raw_first_text(payload, ("webpage_url", "original_url", "url"))
    publish_time, publish_tz = _first_timestamp(payload, ("timestamp", "release_timestamp"))
    if not publish_time:
        publish_time, publish_tz = _first_timestamp(
            payload,
            ("published_timestamp", "publish_timestamp", "upload_timestamp"),
        )
    if not publish_time:
        publish_time, publish_tz = _upload_date_timestamp(
            payload.get("upload_date") or payload.get("release_date")
        )
    live_start, live_start_tz = _first_timestamp(
        payload,
        ("live_start_time", "start_time", "actual_start_time"),
    )
    live_end, live_end_tz = _first_timestamp(
        payload,
        ("live_end_time", "end_time", "actual_end_time"),
    )
    raw_timezone = live_start_tz or publish_tz or live_end_tz
    confidence = "HIGH" if raw_timezone and (publish_time or live_start) else "UNKNOWN"
    if publish_time and not raw_timezone:
        confidence = "LOW"
    return YouTubeMetadataCandidate(
        video_id=video_id,
        video_url=url or (_youtube_url(video_id) if video_id else ""),
        publish_time=publish_time,
        live_start_time=live_start,
        live_end_time=live_end,
        raw_timezone=raw_timezone,
        metadata_source="INFO_JSON",
        timing_confidence=confidence,
        notes="Timing parsed from local metadata JSON." if publish_time or live_start else "",
    )


def parse_adjacent_info_json(path: Path) -> YouTubeMetadataCandidate:
    """Parse adjacent info JSON files for a transcript file."""

    candidates = [
        path.with_suffix(".info.json"),
        path.parent / f"{path.name}.info.json",
        path.parent / f"{path.stem}.info.json",
        path.parent / f"{path.stem}.metadata.json",
    ]
    for candidate in candidates:
        if not candidate.exists() or not candidate.is_file():
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8", errors="ignore"))
        except (OSError, json.JSONDecodeError):
            continue
        parsed = parse_info_json_metadata(payload)
        if parsed.video_id or parsed.publish_time or parsed.live_start_time:
            return YouTubeMetadataCandidate(
                **{
                    **parsed.__dict__,
                    "redacted_metadata_path": _redacted_metadata_path(candidate),
                }
            )
    return YouTubeMetadataCandidate()


def parse_transcript_header_metadata(text: str) -> YouTubeMetadataCandidate:
    """Look for URL/id hints in the first lines of a transcript."""

    header = "\n".join(text.splitlines()[:20])
    video_id = extract_video_id(header)
    if not video_id:
        return YouTubeMetadataCandidate()
    return YouTubeMetadataCandidate(
        video_id=video_id,
        video_url=_youtube_url(video_id),
        metadata_source="TRANSCRIPT_HEADER",
        timing_confidence="UNKNOWN",
        notes="Video identity recovered from transcript header.",
    )


def choose_metadata_candidate(
    *,
    metadata: YouTubeMetadataCandidate,
    manifest: YouTubeMetadataCandidate,
    header: YouTubeMetadataCandidate,
    filename_video_id: str,
    path: Path,
) -> YouTubeMetadataCandidate:
    """Choose the best local metadata candidate for one transcript file."""

    if metadata.metadata_source != "NONE":
        return _merge_candidates(metadata, manifest, header, filename_video_id, path)
    if manifest.metadata_source != "NONE":
        return _merge_candidates(manifest, header, YouTubeMetadataCandidate(), filename_video_id, path)
    if header.metadata_source != "NONE":
        return _merge_candidates(header, YouTubeMetadataCandidate(), YouTubeMetadataCandidate(), filename_video_id, path)
    if filename_video_id:
        return YouTubeMetadataCandidate(
            video_id=filename_video_id,
            video_url=_youtube_url(filename_video_id),
            metadata_source="FILENAME",
            timing_confidence="UNKNOWN",
            redacted_metadata_path=_redacted_metadata_path(path),
            notes="Video identity recovered from filename; publish/live timing still missing.",
        )
    return YouTubeMetadataCandidate(
        redacted_metadata_path=_redacted_metadata_path(path),
        notes="No local video identity or timing metadata found.",
    )


def build_youtube_metadata_local_discovery(
    *,
    timing_audit: pl.DataFrame,
    fetch_plan: pl.DataFrame,
    local_metadata_index: dict[str, YouTubeMetadataCandidate],
    manual_candidates: dict[str, YouTubeMetadataCandidate],
    local_debug: bool = False,
) -> pl.DataFrame:
    """Build local discovery rows for transcripts with missing timing metadata."""

    timing_by_id = _rows_by_key(timing_audit, "clean_transcript_id")
    rows = []
    for item in fetch_plan.to_dicts() if not fetch_plan.is_empty() else []:
        clean_id = _text(item.get("clean_transcript_id"))
        timing = timing_by_id.get(clean_id, {})
        content_hash = _text(timing.get("content_hash"))
        candidate = manual_candidates.get(clean_id) or local_metadata_index.get(
            content_hash,
            YouTubeMetadataCandidate(),
        )
        found = bool(candidate.video_id or candidate.video_url or candidate.publish_time)
        video_url_hash = _stable_hash(candidate.video_url) if candidate.video_url else ""
        rows.append(
            {
                "clean_transcript_id": clean_id,
                "transcript_date": _date_text(item.get("transcript_date"))
                or _date_text(timing.get("transcript_date")),
                "title_hash": _text(timing.get("title_hash")),
                "content_hash": content_hash,
                "local_metadata_found": found,
                "discovered_video_id_hash": _stable_hash(candidate.video_id)
                if candidate.video_id
                else "",
                "discovered_video_url_hash": video_url_hash,
                "metadata_source": candidate.metadata_source,
                "discovered_publish_time": candidate.publish_time,
                "discovered_live_start_time": candidate.live_start_time,
                "discovered_live_end_time": candidate.live_end_time,
                "timing_confidence": candidate.timing_confidence,
                "redacted_metadata_path": candidate.redacted_metadata_path,
                "notes": _discovery_notes(candidate, local_debug=local_debug),
                "_video_url": candidate.video_url if local_debug else "",
                "_raw_video_url": candidate.video_url,
                "_video_id": candidate.video_id,
                "_raw_timezone": candidate.raw_timezone,
            }
        )
    return _rows_frame(rows, _local_discovery_schema()).sort(
        ["transcript_date", "clean_transcript_id"]
    )


def build_youtube_metadata_fetch_requests(discovery: pl.DataFrame) -> pl.DataFrame:
    """Build user-controlled metadata fetch requests for unresolved rows."""

    rows = []
    for row in discovery.to_dicts() if not discovery.is_empty() else []:
        video_url_known = bool(str(row.get("_raw_video_url") or row.get("_video_url") or "").strip())
        video_id_known = bool(str(row.get("_video_id") or "").strip() or _text(row.get("discovered_video_id_hash")))
        missing_publish = not _text(row.get("discovered_publish_time"))
        missing_live_start = not _text(row.get("discovered_live_start_time"))
        missing_live_end = not _text(row.get("discovered_live_end_time"))
        if not any((missing_publish, missing_live_start, missing_live_end)) and video_url_known:
            action = "NO_ACTION_NEEDED"
        elif video_url_known:
            action = "RUN_YTDLP_METADATA_COMMAND"
        elif video_id_known:
            action = "PROVIDE_INFO_JSON"
        else:
            action = "PROVIDE_VIDEO_URL"
        rows.append(
            {
                "clean_transcript_id": row.get("clean_transcript_id"),
                "transcript_date": row.get("transcript_date"),
                "title_or_safe_label": (
                    f"{row.get('clean_transcript_id')}|title_hash:{row.get('title_hash')}"
                ),
                "missing_video_url": not video_url_known,
                "missing_video_id": not video_id_known,
                "missing_publish_time": missing_publish,
                "missing_live_start_time": missing_live_start,
                "missing_live_end_time": missing_live_end,
                "suggested_user_action": action,
                "command_template": DEFAULT_METADATA_COMMAND,
                "suggested_output_location": "configured transcript root beside transcript text",
                "rerun_command": "python -m research_xau_vol_oi.report",
            }
        )
    return _rows_frame(rows, _fetch_request_schema()).sort(
        ["transcript_date", "clean_transcript_id"]
    )


def generate_metadata_fetch_command_texts(
    discovery: pl.DataFrame,
    *,
    local_debug: bool = False,
) -> tuple[str, str]:
    """Generate reviewed-but-not-executed shell and PowerShell command files."""

    sh_lines = [
        "# Review before running. These commands fetch metadata only; they do not download videos.",
        "# The pipeline never executes this file automatically.",
        "set -euo pipefail",
        "",
    ]
    ps_lines = [
        "# Review before running. These commands fetch metadata only; they do not download videos.",
        "# The pipeline never executes this file automatically.",
        "$ErrorActionPreference = 'Stop'",
        "",
    ]
    for row in discovery.to_dicts() if not discovery.is_empty() else []:
        raw_url = str(row.get("_raw_video_url") or row.get("_video_url") or "").strip()
        url_hash = _text(row.get("discovered_video_url_hash"))
        if not raw_url and not url_hash:
            continue
        command_url = raw_url if local_debug else f"<video_url_for_hash_{url_hash}>"
        clean_id = _text(row.get("clean_transcript_id"))
        sh_lines.extend(
            [
                f"# {clean_id}",
                (
                    'yt-dlp --skip-download --write-info-json '
                    '--paths "configured_transcript_root" -o "%(id)s.%(ext)s" '
                    f'"{command_url}"'
                ),
                "",
            ]
        )
        ps_lines.extend(
            [
                f"# {clean_id}",
                (
                    'yt-dlp --skip-download --write-info-json '
                    '--paths "configured_transcript_root" -o "%(id)s.%(ext)s" '
                    f'"{command_url}"'
                ),
                "",
            ]
        )
    return "\n".join(sh_lines).rstrip() + "\n", "\n".join(ps_lines).rstrip() + "\n"


def build_manual_metadata_entry_template(
    fetch_plan: pl.DataFrame,
    existing: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Build or preserve a manual metadata entry template."""

    existing_by_id = _rows_by_key(existing if existing is not None else pl.DataFrame(), "clean_transcript_id")
    rows = []
    for item in fetch_plan.to_dicts() if not fetch_plan.is_empty() else []:
        clean_id = _text(item.get("clean_transcript_id"))
        saved = existing_by_id.get(clean_id, {})
        rows.append(
            {
                "clean_transcript_id": clean_id,
                "video_url": _text(saved.get("video_url")),
                "video_id": _text(saved.get("video_id")),
                "publish_time": _text(saved.get("publish_time")),
                "live_start_time": _text(saved.get("live_start_time")),
                "live_end_time": _text(saved.get("live_end_time")),
                "timezone": _text(saved.get("timezone")),
                "source_notes": _text(saved.get("source_notes")),
                "reviewer_confidence": _text(saved.get("reviewer_confidence")) or "MEDIUM",
            }
        )
    return _rows_frame(rows, _manual_template_schema()).sort("clean_transcript_id")


def manual_metadata_candidates(frame: pl.DataFrame) -> dict[str, YouTubeMetadataCandidate]:
    """Convert filled manual rows into metadata candidates."""

    candidates: dict[str, YouTubeMetadataCandidate] = {}
    for row in frame.to_dicts() if not frame.is_empty() else []:
        if not any(
            _text(row.get(column))
            for column in ("video_url", "video_id", "publish_time", "live_start_time")
        ):
            continue
        confidence = _text(row.get("reviewer_confidence")).upper()
        if confidence not in {"HIGH", "MEDIUM", "LOW"}:
            confidence = "LOW"
        clean_id = _text(row.get("clean_transcript_id"))
        candidates[clean_id] = YouTubeMetadataCandidate(
            video_id=_text(row.get("video_id")),
            video_url=_text(row.get("video_url")),
            publish_time=_text(row.get("publish_time")),
            live_start_time=_text(row.get("live_start_time")),
            live_end_time=_text(row.get("live_end_time")),
            raw_timezone=_text(row.get("timezone")),
            metadata_source="MANUAL_METADATA_ENTRY",
            timing_confidence=confidence,
            redacted_metadata_path="manual metadata entry template",
            notes=_text(row.get("source_notes")) or "Manual metadata entry.",
        )
    return candidates


def build_timing_audit_after_metadata(
    *,
    timing_audit: pl.DataFrame,
    discovery: pl.DataFrame,
    manual_candidates: dict[str, YouTubeMetadataCandidate],
) -> pl.DataFrame:
    """Merge existing timing rows with recovered local or manual metadata."""

    discovery_by_id = _rows_by_key(discovery, "clean_transcript_id")
    rows = []
    for row in timing_audit.to_dicts() if not timing_audit.is_empty() else []:
        clean_id = _text(row.get("clean_transcript_id"))
        manual = manual_candidates.get(clean_id)
        discovered = discovery_by_id.get(clean_id, {})
        publish = _text(discovered.get("discovered_publish_time"))
        live_start = _text(discovered.get("discovered_live_start_time"))
        live_end = _text(discovered.get("discovered_live_end_time"))
        source = _text(discovered.get("metadata_source"))
        confidence = _text(discovered.get("timing_confidence"))
        notes = _text(discovered.get("notes"))
        if manual is not None:
            publish = manual.publish_time
            live_start = manual.live_start_time
            live_end = manual.live_end_time
            source = manual.metadata_source
            confidence = manual.timing_confidence
            notes = manual.notes
        if publish or live_start or live_end:
            rows.append(
                {
                    **row,
                    "detected_publish_timestamp": publish,
                    "detected_live_start_timestamp": live_start,
                    "detected_live_end_timestamp": live_end,
                    "timing_source": "YOUTUBE_METADATA_JSON"
                    if source in {"INFO_JSON", "MANIFEST"}
                    else source or row.get("timing_source"),
                    "timing_confidence": confidence or row.get("timing_confidence"),
                    "timing_notes": notes
                    or "Timing recovered from local YouTube metadata source.",
                }
            )
        else:
            rows.append(row)
    return _rows_frame(rows, _timing_audit_schema()).sort(
        ["transcript_date", "clean_transcript_id"]
    )


def build_transcript_timezone_audit(timing_audit: pl.DataFrame) -> pl.DataFrame:
    """Normalize timestamps to UTC, Bangkok, and CME exchange time."""

    rows = []
    for row in timing_audit.to_dicts() if not timing_audit.is_empty() else []:
        clean_id = _text(row.get("clean_transcript_id"))
        timestamp = (
            _text(row.get("detected_live_start_timestamp"))
            or _text(row.get("detected_publish_timestamp"))
            or _text(row.get("detected_live_end_timestamp"))
        )
        if not timestamp:
            continue
        raw_timezone = infer_raw_timezone(timestamp)
        normalized = normalize_timestamp(timestamp, raw_timezone=raw_timezone)
        source = _text(row.get("timing_source"))
        confidence = normalized["timezone_confidence"]
        notes = normalized["notes"]
        if source in {"FILENAME", "FILE_MODTIME_LOW_CONFIDENCE", "SRT_TIMECODE"} and not raw_timezone:
            confidence = "UNKNOWN"
            notes = (
                "Timestamp has no explicit timezone; this source cannot prove "
                "same-session availability."
            )
        rows.append(
            {
                "clean_transcript_id": clean_id,
                "raw_timestamp": timestamp,
                "raw_timezone": raw_timezone,
                "inferred_timezone": normalized["inferred_timezone"],
                "normalized_utc_timestamp": normalized["normalized_utc_timestamp"],
                "normalized_bangkok_timestamp": normalized["normalized_bangkok_timestamp"],
                "normalized_cme_exchange_timestamp": (
                    normalized["normalized_cme_exchange_timestamp"]
                ),
                "timezone_confidence": confidence,
                "notes": notes,
            }
        )
    return _rows_frame(rows, _timezone_schema()).sort("clean_transcript_id")


def normalize_timestamp(raw_timestamp: str, *, raw_timezone: str = "") -> dict[str, str]:
    """Normalize a timestamp when timezone evidence is explicit."""

    parsed, detected_tz = _parse_timestamp_with_timezone(raw_timestamp)
    inferred = raw_timezone or detected_tz
    if parsed is None:
        return {
            "inferred_timezone": "",
            "normalized_utc_timestamp": "",
            "normalized_bangkok_timestamp": "",
            "normalized_cme_exchange_timestamp": "",
            "timezone_confidence": "UNKNOWN",
            "notes": "Timestamp could not be parsed.",
        }
    if parsed.tzinfo is None:
        if not raw_timezone:
            return {
                "inferred_timezone": "",
                "normalized_utc_timestamp": "",
                "normalized_bangkok_timestamp": "",
                "normalized_cme_exchange_timestamp": "",
                "timezone_confidence": "UNKNOWN",
                "notes": "Timezone is missing; timestamp is not same-session proof.",
            }
        try:
            parsed = parsed.replace(tzinfo=ZoneInfo(raw_timezone))
        except ZoneInfoNotFoundError:
            if raw_timezone.upper() != "UTC":
                return {
                    "inferred_timezone": raw_timezone,
                    "normalized_utc_timestamp": "",
                    "normalized_bangkok_timestamp": "",
                    "normalized_cme_exchange_timestamp": "",
                    "timezone_confidence": "UNKNOWN",
                    "notes": "Configured timezone could not be loaded.",
                }
            parsed = parsed.replace(tzinfo=timezone.utc)
    utc_dt = parsed.astimezone(timezone.utc)
    bangkok = utc_dt.astimezone(ZoneInfo("Asia/Bangkok"))
    cme = utc_dt.astimezone(ZoneInfo("America/Chicago"))
    return {
        "inferred_timezone": inferred or "UTC_OFFSET",
        "normalized_utc_timestamp": utc_dt.isoformat(),
        "normalized_bangkok_timestamp": bangkok.isoformat(),
        "normalized_cme_exchange_timestamp": cme.isoformat(),
        "timezone_confidence": "HIGH",
        "notes": "Timezone was explicit and normalization is available.",
    }


def apply_timezone_confidence_to_timing_audit(
    timing_audit: pl.DataFrame,
    timezone_audit: pl.DataFrame,
) -> pl.DataFrame:
    """Downgrade timing rows that lack explicit timezone proof."""

    tz_by_id = _rows_by_key(timezone_audit, "clean_transcript_id")
    rows = []
    for row in timing_audit.to_dicts() if not timing_audit.is_empty() else []:
        clean_id = _text(row.get("clean_transcript_id"))
        tz_row = tz_by_id.get(clean_id, {})
        tz_confidence = _text(tz_row.get("timezone_confidence"))
        if tz_confidence not in HIGH_MEDIUM:
            updated = {
                **row,
                "timing_confidence": "LOW"
                if _text(row.get("detected_publish_timestamp"))
                or _text(row.get("detected_live_start_timestamp"))
                else "UNKNOWN",
                "timing_notes": (
                    "Timing exists but timezone is not explicit, so same-session "
                    "classification remains unavailable."
                ),
            }
            rows.append(updated)
            continue
        timestamp = _strip_timezone_for_session(_text(tz_row.get("normalized_bangkok_timestamp")))
        updated = {
            **row,
            "detected_publish_timestamp": timestamp,
            "detected_live_start_timestamp": timestamp
            if _text(row.get("detected_live_start_timestamp"))
            else "",
            "timing_confidence": "HIGH",
            "timing_notes": "Timing normalized with explicit timezone metadata.",
        }
        rows.append(updated)
    return _rows_frame(rows, _timing_audit_schema()).sort(
        ["transcript_date", "clean_transcript_id"]
    )


def choose_youtube_metadata_recovery_recommendation(
    *,
    discovery: pl.DataFrame,
    fetch_requests: pl.DataFrame,
    availability: pl.DataFrame,
    filter_evidence: pl.DataFrame,
) -> str:
    """Choose the final metadata recovery recommendation."""

    if _sum_int(filter_evidence, "timing_confirmed_filter_matches") > 0:
        unresolved = _count_bool(fetch_requests, "missing_publish_time") + _count_bool(
            fetch_requests,
            "missing_live_start_time",
        )
        if unresolved == 0:
            return "SAME_DAY_FILTER_TIMING_CONFIRMED"
    if not availability.is_empty() and not _any_state(availability, "availability_relation", "UNKNOWN"):
        return "TIMING_RECLASSIFICATION_READY"
    if _any_state(fetch_requests, "suggested_user_action", "RUN_YTDLP_METADATA_COMMAND"):
        return "RUN_METADATA_FETCH_COMMANDS"
    if _any_state(fetch_requests, "suggested_user_action", "PROVIDE_VIDEO_URL"):
        return "USER_PROVIDE_VIDEO_URLS"
    if _any_state(fetch_requests, "suggested_user_action", "PROVIDE_INFO_JSON"):
        return "NEEDS_MANUAL_METADATA_ENTRY"
    if _count_bool(discovery, "local_metadata_found"):
        return "METADATA_RECOVERY_READY"
    return "SAME_DAY_CONTEXT_ONLY"


def youtube_metadata_recovery_report_lines(
    result: YouTubeMetadataRecoveryResult | None,
) -> list[str]:
    """Return Markdown lines for the main report."""

    if result is None:
        return ["YouTube metadata recovery layer was not run."]
    availability_counts = _state_counts(
        result.transcript_availability_classification_after_metadata,
        "availability_relation",
    )
    return [
        "## YouTube Metadata Recovery",
        "",
        f"- Final recommendation: `{result.final_recommendation}`",
        f"- Local metadata rows found: `{_count_bool(result.youtube_metadata_local_discovery, 'local_metadata_found')}`",
        f"- Metadata fetch request rows: `{result.youtube_metadata_fetch_requests.height}`",
        "",
        "## Metadata Local Discovery",
        "",
        _frame_markdown(_public_discovery(result.youtube_metadata_local_discovery)),
        "",
        "## Metadata Fetch Requests",
        "",
        _frame_markdown(result.youtube_metadata_fetch_requests),
        "",
        "## Timezone Normalization",
        "",
        _frame_markdown(result.transcript_timezone_audit),
        "",
        "## Timing Reclassification After Metadata",
        "",
        f"- PRE_SESSION: `{availability_counts.get('PRE_SESSION', 0)}`",
        f"- DURING_SESSION: `{availability_counts.get('DURING_SESSION', 0)}`",
        f"- POST_SESSION: `{availability_counts.get('POST_SESSION', 0)}`",
        f"- WEEKEND_RECAP: `{availability_counts.get('WEEKEND_RECAP', 0)}`",
        f"- NEXT_SESSION_PREP: `{availability_counts.get('NEXT_SESSION_PREP', 0)}`",
        f"- UNKNOWN: `{availability_counts.get('UNKNOWN', 0)}`",
        "",
        _frame_markdown(result.transcript_availability_classification_after_metadata),
        "",
        "## Remaining Unknown Timing",
        "",
        _frame_markdown(
            result.transcript_availability_classification_after_metadata.filter(
                pl.col("availability_relation") == "UNKNOWN"
            )
            if not result.transcript_availability_classification_after_metadata.is_empty()
            else pl.DataFrame()
        ),
        "",
        "## Next User Action",
        "",
        *_next_action_lines(result),
    ]


def youtube_metadata_local_discovery_markdown(frame: pl.DataFrame) -> str:
    """Render local discovery report."""

    return _safe_report(
        "\n".join(
            [
                "# YouTube Metadata Local Discovery",
                "",
                "URLs and paths are hashed or redacted. Local discovery does not fetch network data.",
                "",
                _frame_markdown(_public_discovery(frame)),
            ]
        )
    )


def youtube_metadata_fetch_plan_markdown(frame: pl.DataFrame) -> str:
    """Render metadata fetch request plan."""

    return _safe_report(
        "\n".join(
            [
                "# YouTube Metadata Fetch Plan",
                "",
                "Metadata fetch is user-controlled. Generated command files are not executed by the pipeline.",
                "",
                _frame_markdown(frame),
            ]
        )
    )


def transcript_timezone_audit_markdown(frame: pl.DataFrame) -> str:
    """Render timezone audit."""

    return _safe_report(
        "\n".join(
            [
                "# Transcript Timezone Audit",
                "",
                "Unknown timezone rows do not unlock same-session classification.",
                "",
                _frame_markdown(frame),
            ]
        )
    )


def metadata_reclassification_report_markdown(
    *,
    before_availability: pl.DataFrame,
    after_availability: pl.DataFrame,
    before_filter: pl.DataFrame,
    after_filter: pl.DataFrame,
    before_market_map: pl.DataFrame,
    after_market_map: pl.DataFrame,
) -> str:
    """Render before/after timing reclassification summary."""

    counts = _state_counts(after_availability, "availability_relation")
    upgraded = _upgraded_dates(before_filter, after_filter, before_market_map, after_market_map)
    downgraded = _downgraded_dates(before_filter, after_filter, before_market_map, after_market_map)
    before_counts = _state_counts(before_availability, "availability_relation")
    return _safe_report(
        "\n".join(
            [
                "# Timing Reclassification After Metadata",
                "",
                f"- PRE_SESSION: `{counts.get('PRE_SESSION', 0)}`",
                f"- DURING_SESSION: `{counts.get('DURING_SESSION', 0)}`",
                f"- POST_SESSION: `{counts.get('POST_SESSION', 0)}`",
                f"- WEEKEND_RECAP: `{counts.get('WEEKEND_RECAP', 0)}`",
                f"- NEXT_SESSION_PREP: `{counts.get('NEXT_SESSION_PREP', 0)}`",
                f"- UNKNOWN: `{counts.get('UNKNOWN', 0)}`",
                f"- Timing-confirmed filter matches: `{_sum_int(after_filter, 'timing_confirmed_filter_matches')}`",
                f"- Timing-confirmed market-map matches: `{_sum_int(after_market_map, 'timing_confirmed_market_map_matches')}`",
                f"- Dates upgraded from context-only to timing-confirmed: `{_join_or_none(upgraded)}`",
                f"- Dates downgraded due timezone uncertainty: `{_join_or_none(downgraded)}`",
                f"- Prior UNKNOWN count: `{before_counts.get('UNKNOWN', 0)}`",
            ]
        )
    )


def append_youtube_metadata_recovery_sections(
    path: Path,
    result: YouTubeMetadataRecoveryResult,
) -> None:
    """Append or replace YouTube metadata recovery sections in the main report."""

    marker = "\n## YouTube Metadata Recovery\n"
    section = _safe_report("\n".join(youtube_metadata_recovery_report_lines(result)))
    existing = path.read_text(encoding="utf-8") if path.exists() else "# XAU/USD Vol-OI Research Report\n"
    if marker in existing:
        existing = existing.split(marker, 1)[0].rstrip()
    path.write_text(_redact_text(existing.rstrip()) + "\n\n" + section + "\n", encoding="utf-8")


def extract_video_id(text: str) -> str:
    """Extract a likely YouTube video id from filenames, URLs, or text."""

    patterns = (
        r"\[([A-Za-z0-9_-]{8,16})\]",
        r"(?:v=|youtu\.be/|shorts/|embed/)([A-Za-z0-9_-]{8,16})",
    )
    for pattern in patterns:
        match = re.search(pattern, text or "")
        if match:
            return match.group(1)
    return ""


def _merge_candidates(
    primary: YouTubeMetadataCandidate,
    secondary: YouTubeMetadataCandidate,
    tertiary: YouTubeMetadataCandidate,
    filename_video_id: str,
    path: Path,
) -> YouTubeMetadataCandidate:
    video_id = primary.video_id or secondary.video_id or tertiary.video_id or filename_video_id
    video_url = primary.video_url or secondary.video_url or tertiary.video_url or _youtube_url(video_id)
    return YouTubeMetadataCandidate(
        video_id=video_id,
        video_url=video_url,
        publish_time=primary.publish_time or secondary.publish_time or tertiary.publish_time,
        live_start_time=primary.live_start_time
        or secondary.live_start_time
        or tertiary.live_start_time,
        live_end_time=primary.live_end_time or secondary.live_end_time or tertiary.live_end_time,
        raw_timezone=primary.raw_timezone or secondary.raw_timezone or tertiary.raw_timezone,
        metadata_source=primary.metadata_source,
        timing_confidence=primary.timing_confidence,
        redacted_metadata_path=primary.redacted_metadata_path
        or secondary.redacted_metadata_path
        or _redacted_metadata_path(path),
        notes=primary.notes
        or secondary.notes
        or "Video identity recovered locally; publish/live timing still missing.",
    )


def _scorecard_after_metadata(
    *,
    availability: pl.DataFrame,
    filter_evidence: pl.DataFrame,
    market_map: pl.DataFrame,
    remapped_replay: pl.DataFrame,
) -> pl.DataFrame:
    filter_by_date = _rows_by_key(filter_evidence, "original_replay_date")
    market_by_date = _rows_by_key(market_map, "original_replay_date")
    rows = []
    for remap in remapped_replay.to_dicts() if not remapped_replay.is_empty() else []:
        day = _date_text(remap.get("original_replay_date"))
        filter_row = filter_by_date.get(day, {})
        market_row = market_by_date.get(day, {})
        timing_status = _text(filter_row.get("evidence_status")) or _text(
            market_row.get("confidence")
        )
        rows.append(
            {
                "date": day,
                "resolved_market_session_date": _text(remap.get("resolved_market_session_date")),
                "cme_data_available": _text(remap.get("cme_data_join_result")),
                "oi_walls_visible": _bool_value(market_row.get("cme_oi_walls_available")),
                "basis_available": _bool_value(market_row.get("basis_available")),
                "same_day_guru_logic": (
                    f"filters={int(_float_or_zero(filter_row.get('same_day_filter_matches')))}, "
                    f"market_maps={int(_float_or_zero(market_row.get('same_day_market_map_matches')))}"
                ),
                "timing_status": timing_status,
                "no_trade_filter_active": _bool_value(filter_row.get("no_trade_filter_active")),
                "market_map_aligned_with_oi_wall": _bool_value(market_row.get("map_hit_proxy")),
                "what_happened_after": "outcome labels are incomplete or unknown",
                "what_can_we_learn": _learn_after_metadata(filter_row, market_row),
                "what_cannot_be_proven": _cannot_prove_after_metadata(filter_row),
                "final_per_date_label": _date_label_after_metadata(filter_row, market_row),
            }
        )
    return _rows_frame(rows, _scorecard_schema()).sort("date")


def _learn_after_metadata(filter_row: dict[str, Any], market_row: dict[str, Any]) -> str:
    if _text(filter_row.get("evidence_status")) == "TIMING_CONFIRMED":
        return "Recovered metadata allows same-day filter evidence to be reviewed with timing proof."
    if _text(market_row.get("confidence")) == "HIGH":
        return "Recovered metadata allows same-day market-map evidence to be reviewed with timing proof."
    return "Metadata is still missing or timezone-uncertain, so evidence remains context-only."


def _cannot_prove_after_metadata(filter_row: dict[str, Any]) -> str:
    if _text(filter_row.get("evidence_status")) == "TIMING_UNKNOWN_CONTEXT_ONLY":
        return "The same-day text timing is still not proven before or during the relevant session."
    return "This report does not establish strict trade rules or performance claims."


def _date_label_after_metadata(filter_row: dict[str, Any], market_row: dict[str, Any]) -> str:
    if _text(filter_row.get("evidence_status")) == "TIMING_CONFIRMED":
        return "USEFUL_PILOT_EVIDENCE"
    if _text(filter_row.get("evidence_status")) == "TIMING_UNKNOWN_CONTEXT_ONLY":
        return "TIMING_UNKNOWN"
    if _text(market_row.get("confidence")) == "CONTEXT_ONLY":
        return "CONTEXT_ONLY"
    return "NEEDS_MORE_DATA"


def _next_action_lines(result: YouTubeMetadataRecoveryResult) -> list[str]:
    if _any_state(
        result.youtube_metadata_fetch_requests,
        "suggested_user_action",
        "RUN_YTDLP_METADATA_COMMAND",
    ):
        return [
            "- Review `outputs/youtube_metadata_fetch_commands.ps1` or `.sh`.",
            "- Run only the metadata commands you approve, then rerun `python -m research_xau_vol_oi.report`.",
        ]
    if _any_state(
        result.youtube_metadata_fetch_requests,
        "suggested_user_action",
        "PROVIDE_VIDEO_URL",
    ):
        return [
            "- Add video URLs or `.info.json` files for remaining rows.",
            "- Use `outputs/youtube_metadata_manual_entry_template.csv` if URL recovery is not possible.",
        ]
    return ["- Rerun `python -m research_xau_vol_oi.report` after metadata files are added."]


def _upgraded_dates(
    before_filter: pl.DataFrame,
    after_filter: pl.DataFrame,
    before_market_map: pl.DataFrame,
    after_market_map: pl.DataFrame,
) -> list[str]:
    before_confirmed = _confirmed_dates(before_filter, before_market_map)
    after_confirmed = _confirmed_dates(after_filter, after_market_map)
    return sorted(after_confirmed - before_confirmed)


def _downgraded_dates(
    before_filter: pl.DataFrame,
    after_filter: pl.DataFrame,
    before_market_map: pl.DataFrame,
    after_market_map: pl.DataFrame,
) -> list[str]:
    before_confirmed = _confirmed_dates(before_filter, before_market_map)
    after_confirmed = _confirmed_dates(after_filter, after_market_map)
    return sorted(before_confirmed - after_confirmed)


def _confirmed_dates(filter_frame: pl.DataFrame, market_map_frame: pl.DataFrame) -> set[str]:
    dates: set[str] = set()
    if not filter_frame.is_empty() and "timing_confirmed_filter_matches" in filter_frame.columns:
        for row in filter_frame.to_dicts():
            if int(_float_or_zero(row.get("timing_confirmed_filter_matches"))) > 0:
                dates.add(_date_text(row.get("original_replay_date")))
    if not market_map_frame.is_empty() and "timing_confirmed_market_map_matches" in market_map_frame.columns:
        for row in market_map_frame.to_dicts():
            if int(_float_or_zero(row.get("timing_confirmed_market_map_matches"))) > 0:
                dates.add(_date_text(row.get("original_replay_date")))
    return {date for date in dates if date}


def _join_or_none(values: list[str]) -> str:
    return "|".join(values) if values else "none"


def _public_discovery(frame: pl.DataFrame) -> pl.DataFrame:
    private_columns = {"_video_url", "_raw_video_url", "_video_id", "_raw_timezone"}
    if frame.is_empty():
        return pl.DataFrame(schema={k: v for k, v in _local_discovery_schema().items() if k not in private_columns})
    return frame.select([column for column in frame.columns if column not in private_columns])


def _discovery_notes(candidate: YouTubeMetadataCandidate, *, local_debug: bool) -> str:
    notes = candidate.notes or "No local metadata found."
    if candidate.video_url and not local_debug:
        notes = f"{notes} Raw URL suppressed; use hash or enable local debug for command expansion."
    return notes


def _first_timestamp(payload: dict[str, Any], keys: Iterable[str]) -> tuple[str, str]:
    for key in keys:
        timestamp, tz_name = _timestamp_from_value(payload.get(key))
        if timestamp:
            return timestamp, tz_name
    return "", ""


def _timestamp_from_value(value: Any) -> tuple[str, str]:
    if value in (None, ""):
        return "", ""
    if isinstance(value, (int, float)):
        try:
            parsed = datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return "", ""
        return parsed.isoformat(), "UTC"
    text = str(value).strip()
    if re.fullmatch(r"\d{10}(?:\.\d+)?", text):
        return _timestamp_from_value(float(text))
    parsed, tz_name = _parse_timestamp_with_timezone(text)
    if parsed is None:
        return "", ""
    return parsed.isoformat(), tz_name


def _upload_date_timestamp(value: Any) -> tuple[str, str]:
    text = str(value or "").strip()
    match = re.fullmatch(r"(20\d{2})(\d{2})(\d{2})", text)
    if not match:
        return "", ""
    year, month, day = match.groups()
    return f"{year}-{month}-{day}T00:00:00", ""


def _parse_timestamp_with_timezone(value: str) -> tuple[datetime | None, str]:
    text = str(value or "").strip()
    if not text:
        return None, ""
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None, ""
    if parsed.tzinfo is None:
        return parsed, ""
    return parsed, "UTC_OFFSET"


def _strip_timezone_for_session(value: str) -> str:
    parsed, _ = _parse_timestamp_with_timezone(value)
    if parsed is None:
        return value
    return parsed.replace(tzinfo=None).isoformat()


def infer_raw_timezone(timestamp: str) -> str:
    _, tz_name = _parse_timestamp_with_timezone(timestamp)
    return tz_name


def _iter_transcript_files(root: Path) -> Iterable[Path]:
    try:
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in {".txt", ".srt"} and path.stat().st_size <= 2_000_000:
                yield path
    except OSError:
        return


def _iter_manifest_files(root: Path) -> Iterable[Path]:
    try:
        for path in root.rglob("*"):
            name = path.name.lower()
            if path.is_file() and "manifest" in name and path.suffix.lower() in {".csv", ".jsonl", ".json"}:
                yield path
            elif path.is_file() and "archive" in name and path.suffix.lower() in {".txt", ".csv"}:
                yield path
    except OSError:
        return


def _read_manifest_rows(path: Path) -> list[dict[str, Any]]:
    try:
        if path.suffix.lower() == ".jsonl":
            return [
                json.loads(line)
                for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()
                if line.strip().startswith("{")
            ]
        if path.suffix.lower() == ".json":
            payload = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
            if isinstance(payload, list):
                return [item for item in payload if isinstance(item, dict)]
            if isinstance(payload, dict):
                entries = payload.get("entries")
                if isinstance(entries, list):
                    return [item for item in entries if isinstance(item, dict)]
                return [payload]
        with path.open("r", encoding="utf-8", errors="ignore", newline="") as handle:
            return list(csv.DictReader(handle))
    except (OSError, json.JSONDecodeError, csv.Error):
        return []


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


def _stable_hash(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()[:16]


def _youtube_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}" if video_id else ""


def _redacted_metadata_path(path: Path) -> str:
    suffix = path.suffix or ".metadata"
    return f"<REDACTED_PATH>/<METADATA_FILE>{suffix}"


def _write_csv_and_md(
    csv_path: Path,
    md_path: Path,
    frame: pl.DataFrame,
    renderer: Any,
) -> None:
    frame.write_csv(csv_path)
    md_path.write_text(renderer(frame), encoding="utf-8")


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


def _rows_by_key(frame: pl.DataFrame, column: str) -> dict[str, dict[str, Any]]:
    if frame is None or frame.is_empty() or column not in frame.columns:
        return {}
    rows = {}
    for row in frame.to_dicts():
        key = _text(row.get(column))
        if key:
            rows[key] = row
    return rows


def _first_text(row: dict[str, Any], keys: Iterable[str]) -> str:
    for key in keys:
        value = _text(row.get(key))
        if value:
            return value
    return ""


def _raw_first_text(row: dict[str, Any], keys: Iterable[str]) -> str:
    for key in keys:
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def _date_text(value: Any) -> str:
    match = re.search(r"20\d{2}-\d{2}-\d{2}", str(value or ""))
    return match.group(0) if match else ""


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    return text not in {"", "0", "false", "f", "no", "n", "none", "null", "nan"}


def _text(value: Any) -> str:
    return _redact_text(str(value or "").strip())


def _redact_text(text: str) -> str:
    text = re.sub(r"https?://(?:www\.)?(?:youtube\.com|youtu\.be)/[^`|\s,\"]+", "<REDACTED_URL>", text)
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
    if re.search(r"https?://(?:www\.)?(?:youtube\.com|youtu\.be)/", text):
        raise ValueError("Report contains an unredacted YouTube URL.")
    return _redact_text(text)


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


def _count_bool(frame: pl.DataFrame, column: str) -> int:
    if frame.is_empty() or column not in frame.columns:
        return 0
    return sum(1 for value in frame.get_column(column).to_list() if _bool_value(value))


def _any_state(frame: pl.DataFrame, column: str, value: str) -> bool:
    if frame.is_empty() or column not in frame.columns:
        return False
    return any(_text(item) == value for item in frame.get_column(column).to_list())


def _state_counts(frame: pl.DataFrame, column: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    if frame.is_empty() or column not in frame.columns:
        return counts
    for item in frame.get_column(column).to_list():
        key = _text(item)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _float_or_zero(value: Any) -> float:
    try:
        if value in (None, ""):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _local_discovery_schema() -> dict[str, Any]:
    return {
        "clean_transcript_id": pl.String,
        "transcript_date": pl.String,
        "title_hash": pl.String,
        "content_hash": pl.String,
        "local_metadata_found": pl.Boolean,
        "discovered_video_id_hash": pl.String,
        "discovered_video_url_hash": pl.String,
        "metadata_source": pl.String,
        "discovered_publish_time": pl.String,
        "discovered_live_start_time": pl.String,
        "discovered_live_end_time": pl.String,
        "timing_confidence": pl.String,
        "redacted_metadata_path": pl.String,
        "notes": pl.String,
        "_video_url": pl.String,
        "_raw_video_url": pl.String,
        "_video_id": pl.String,
        "_raw_timezone": pl.String,
    }


def _fetch_request_schema() -> dict[str, Any]:
    return {
        "clean_transcript_id": pl.String,
        "transcript_date": pl.String,
        "title_or_safe_label": pl.String,
        "missing_video_url": pl.Boolean,
        "missing_video_id": pl.Boolean,
        "missing_publish_time": pl.Boolean,
        "missing_live_start_time": pl.Boolean,
        "missing_live_end_time": pl.Boolean,
        "suggested_user_action": pl.String,
        "command_template": pl.String,
        "suggested_output_location": pl.String,
        "rerun_command": pl.String,
    }


def _manual_template_schema() -> dict[str, Any]:
    return {column: pl.String for column in MANUAL_TEMPLATE_COLUMNS}


def _timezone_schema() -> dict[str, Any]:
    return {
        "clean_transcript_id": pl.String,
        "raw_timestamp": pl.String,
        "raw_timezone": pl.String,
        "inferred_timezone": pl.String,
        "normalized_utc_timestamp": pl.String,
        "normalized_bangkok_timestamp": pl.String,
        "normalized_cme_exchange_timestamp": pl.String,
        "timezone_confidence": pl.String,
        "notes": pl.String,
    }


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


def main() -> None:
    """CLI entry point."""

    result = run_youtube_metadata_recovery_layer()
    print(f"final_recommendation: {result.final_recommendation}")
    print(f"local_metadata_found: {_count_bool(result.youtube_metadata_local_discovery, 'local_metadata_found')}")
    print(f"fetch_requests: {result.youtube_metadata_fetch_requests.height}")


if __name__ == "__main__":
    main()
