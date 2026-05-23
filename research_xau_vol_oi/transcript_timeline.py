"""Guru transcript timeline alignment for XAU Vol-OI research.

Transcript-derived rules are treated as dated research evidence. A rule can
only be joined to market events after its availability timestamp.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import polars as pl

from research_xau_vol_oi.config import ResearchConfig, Signal


RULE_TAGS = (
    "BASIS_ADJUSTMENT",
    "IV_EXPECTED_MOVE",
    "ONE_SD_RANGE",
    "TWO_SD_STRESS",
    "THREE_SD_EXTREME",
    "OI_WALL",
    "OI_CHANGE_FRESHNESS",
    "INTRADAY_VOLUME",
    "LOW_OI_GAP",
    "PIN_RISK",
    "SQUEEZE_RISK",
    "OPEN_PRICE_THEORY",
    "ACCEPTANCE_CLOSE_CONFIRMATION",
    "REJECTION_AT_WALL",
    "NO_TRADE_DISCIPLINE",
    "STALE_DATA_WARNING",
    "NEWS_EVENT_WARNING",
    "IV_RV_VRP",
    "VOLATILITY_SMILE_SKEW",
    "MARKET_MAKER_GAMMA",
)

TAG_KEYWORDS = {
    "BASIS_ADJUSTMENT": ("basis", "spot", "futures", "future", "สปอต", "ฟิวเจอร์", "ส่วนต่าง"),
    "IV_EXPECTED_MOVE": ("iv", "implied", "expected move", "คาด", "อิมพลาย", "volatility"),
    "ONE_SD_RANGE": ("1 sd", "one sd", "1sd", "หนึ่ง sd", "โซนสีส้ม"),
    "TWO_SD_STRESS": ("2 sd", "two sd", "2sd"),
    "THREE_SD_EXTREME": ("3 sd", "three sd", "3sd"),
    "OI_WALL": ("oi", "openinterest", "open interest", "strike", "wall", "แนวรับ", "แนวต้าน", "กำแพง", "วอล"),
    "OI_CHANGE_FRESHNESS": ("oi change", "change oi", "fresh", "เพิ่ม oi", "ลด oi", "เปลี่ยน"),
    "INTRADAY_VOLUME": ("intraday", "volume", "วอลุ่ม", "ปริมาณ"),
    "LOW_OI_GAP": ("low oi", "gap", "ช่องว่าง", "หลุดไหล", "ไหลไป"),
    "PIN_RISK": ("pin", "pin risk", "ปัก", "ตรึง"),
    "SQUEEZE_RISK": ("squeeze", "บีบ", "ไล่ราคา", "หลุดไหล"),
    "OPEN_PRICE_THEORY": ("open price", "session open", "ราคาเปิด", "เปิดตลาด", "ราคา open"),
    "ACCEPTANCE_CLOSE_CONFIRMATION": (
        "acceptance",
        "close confirm",
        "ปิดเหนือ",
        "ปิดใต้",
        "ยืนเหนือ",
        "ยืนใต้",
        "แท่งเทียน",
    ),
    "REJECTION_AT_WALL": ("rejection", "reject", "เด้ง", "ทะลุไม่ได้", "รับอยู่", "โดนต้าน", "ปฏิเสธ"),
    "NO_TRADE_DISCIPLINE": ("no trade", "ไม่เทรด", "ไม่ควรเทรด", "รอ", "เก็บตังค์", "พัก"),
    "STALE_DATA_WARNING": ("stale", "ข้อมูลเก่า", "เก่า", "delay", "ดีเลย์"),
    "NEWS_EVENT_WARNING": ("news", "ข่าว", "ตัวเลข", "cpi", "fomc", "nfp", "fed"),
    "IV_RV_VRP": ("iv/rv", "iv rv", "vrp", "realized", "rv", "variance risk"),
    "VOLATILITY_SMILE_SKEW": ("smile", "skew", "สกิว", "vol smile", "vol skew"),
    "MARKET_MAKER_GAMMA": ("market maker", "gamma", "dealer", "mm", "แกมมา"),
}

DECISIONS = (
    "TRANSCRIPT_RULE_SUPPORTED",
    "TRANSCRIPT_RULE_PROMISING",
    "TRANSCRIPT_RULE_UNVALIDATED",
    "TRANSCRIPT_RULE_FAILED",
)
WINDOWS = ("same_day", "next_session", "3_session", "5_session")
MIN_RULE_SAMPLE = 10


@dataclass(frozen=True)
class TranscriptTimelineResult:
    """Generated transcript timeline frames and decision summary."""

    timeline: pl.DataFrame
    coverage: pl.DataFrame
    alignment: pl.DataFrame
    performance: pl.DataFrame
    ablation: pl.DataFrame
    final_decision: str


def run_transcript_timeline_layer(
    *,
    feature_table: pl.DataFrame,
    signal_events: pl.DataFrame,
    trades: pl.DataFrame,
    output_dir: Path,
    charts_dir: Path,
    transcript_paths: list[Path] | None = None,
    config: ResearchConfig | None = None,
) -> TranscriptTimelineResult:
    """Parse transcripts, align dated rules to market events, and write outputs."""

    cfg = config or ResearchConfig()
    output_dir.mkdir(parents=True, exist_ok=True)
    charts_dir.mkdir(parents=True, exist_ok=True)

    timeline = build_transcript_rule_timeline(transcript_paths=transcript_paths, config=cfg)
    alignment = align_transcripts_to_market(
        timeline,
        feature_table,
        signal_events,
        trades,
        config=cfg,
    )
    performance = transcript_rule_performance(alignment, trades)
    coverage = transcript_rule_coverage(timeline, alignment)
    ablation = transcript_rule_ablation(alignment, trades, signal_events)
    final_decision = transcript_final_decision(performance)

    timeline.write_csv(output_dir / "transcript_rule_timeline.csv")
    coverage.write_csv(output_dir / "transcript_rule_coverage.csv")
    alignment.write_csv(output_dir / "transcript_market_alignment.csv")
    performance.write_csv(output_dir / "transcript_rule_performance.csv")
    ablation.write_csv(output_dir / "transcript_rule_ablation.csv")
    write_transcript_alignment_report(
        output_dir / "transcript_alignment_report.md",
        timeline=timeline,
        coverage=coverage,
        alignment=alignment,
        performance=performance,
        ablation=ablation,
        final_decision=final_decision,
    )
    write_transcript_charts(charts_dir=charts_dir, coverage=coverage, performance=performance)

    return TranscriptTimelineResult(
        timeline=timeline,
        coverage=coverage,
        alignment=alignment,
        performance=performance,
        ablation=ablation,
        final_decision=final_decision,
    )


def discover_transcript_files(
    *,
    config: ResearchConfig | None = None,
    roots: tuple[Path, ...] | None = None,
) -> list[Path]:
    """Find local transcript text files, preferring individual files over combined exports."""

    cfg = config or ResearchConfig()
    search_roots = roots or cfg.data_roots
    candidates: list[Path] = []
    for root in search_roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".txt", ".md", ".srt"}:
                continue
            lower = str(path).lower()
            if "transcript" not in lower:
                continue
            if any(part in lower for part in ("manifest", "missing_or_gap", "report.")):
                continue
            candidates.append(path)
    individual = [
        path
        for path in candidates
        if "[" in path.name and "]" in path.name and "combined" not in path.name.lower()
    ]
    if individual:
        return sorted(individual)
    return sorted(path for path in candidates if "combined" in path.name.lower()) or sorted(candidates)


def build_transcript_rule_timeline(
    *,
    transcript_paths: list[Path] | None = None,
    config: ResearchConfig | None = None,
) -> pl.DataFrame:
    """Parse transcript files into one timeline row per transcript/video."""

    paths = transcript_paths if transcript_paths is not None else discover_transcript_files(config=config)
    rows = []
    for path in paths:
        for record in parse_transcript_file(path, config=config):
            rows.append(record)
    if not rows:
        return _empty_timeline()
    return _rows_frame(rows).sort("availability_timestamp")


def parse_transcript_file(
    path: Path,
    *,
    config: ResearchConfig | None = None,
) -> list[dict[str, Any]]:
    """Parse a transcript file into one or more dated transcript records."""

    cfg = config or ResearchConfig()
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    if _looks_combined(text):
        sections = _split_combined_transcript(text)
        return [_parse_transcript_text(path, section, config=cfg) for section in sections]
    return [_parse_transcript_text(path, text, config=cfg)]


def align_transcripts_to_market(
    timeline: pl.DataFrame,
    feature_table: pl.DataFrame,
    signal_events: pl.DataFrame,
    trades: pl.DataFrame,
    *,
    config: ResearchConfig | None = None,
) -> pl.DataFrame:
    """Align transcript tags to events only after transcript availability."""

    cfg = config or ResearchConfig()
    if timeline.is_empty() or signal_events.is_empty():
        return _empty_alignment()
    session_lookup = _session_lookup(feature_table, signal_events, config=cfg)
    events = _event_rows(signal_events, session_lookup, config=cfg)
    trade_lookup = _trade_lookup(trades)
    rows = []
    for transcript in timeline.to_dicts():
        tags = _split_tags(transcript.get("detected_rule_tags"))
        availability = transcript.get("availability_timestamp")
        if availability is None:
            continue
        transcript_session = _session_date(availability, config=cfg)
        transcript_index = session_lookup.get(transcript_session)
        for tag in tags:
            for window in WINDOWS:
                aligned_events = [
                    event
                    for event in events
                    if event["event_timestamp"] >= availability
                    and _in_window(
                        event_session_index=event["session_index"],
                        transcript_session_index=transcript_index,
                        window=window,
                    )
                ]
                event_keys = {
                    _event_key(event.get("event_timestamp"), event.get("signal"))
                    for event in aligned_events
                }
                event_key_values = sorted(
                    _serialize_event_key(event.get("event_timestamp"), event.get("signal"))
                    for event in aligned_events
                )
                trade_rows = [trade for key, trade in trade_lookup.items() if key in event_keys]
                metrics = _metrics(trade_rows)
                no_trade_count = sum(
                    1
                    for event in aligned_events
                    if str(event.get("signal") or "").startswith("NO_TRADE")
                )
                rows.append(
                    {
                        "transcript_id": transcript["transcript_id"],
                        "rule_tag": tag,
                        "window_label": window,
                        "availability_timestamp": availability,
                        "transcript_session_date": transcript_session,
                        "event_count": len(aligned_events),
                        "no_trade_event_count": no_trade_count,
                        "trade_count": metrics["trade_count"],
                        "win_rate": metrics["win_rate"],
                        "expectancy": metrics["expectancy"],
                        "profit_factor": metrics["profit_factor"],
                        "max_drawdown": metrics["max_drawdown"],
                        "event_keys": "|".join(event_key_values),
                        "first_event_timestamp": min(
                            (event["event_timestamp"] for event in aligned_events),
                            default=None,
                        ),
                        "last_event_timestamp": max(
                            (event["event_timestamp"] for event in aligned_events),
                            default=None,
                        ),
                        "no_lookahead_violations": sum(
                            1 for event in aligned_events if event["event_timestamp"] < availability
                        ),
                    }
                )
    return _rows_frame(rows) if rows else _empty_alignment()


def transcript_rule_coverage(timeline: pl.DataFrame, alignment: pl.DataFrame) -> pl.DataFrame:
    """Summarize rule tag frequency and market overlap."""

    if timeline.is_empty():
        return _empty_coverage()
    rows = []
    alignment_rows = alignment.to_dicts() if not alignment.is_empty() else []
    for tag in RULE_TAGS:
        transcript_rows = [
            row for row in timeline.to_dicts() if tag in _split_tags(row.get("detected_rule_tags"))
        ]
        tag_alignments = [row for row in alignment_rows if row.get("rule_tag") == tag]
        by_window = {
            window: len(
                {
                    key
                    for row in tag_alignments
                    if row["window_label"] == window
                    for key in _alignment_event_keys(row)
                }
            )
            for window in WINDOWS
        }
        rows.append(
            {
                "rule_tag": tag,
                "transcript_count": len(transcript_rows),
                "first_availability_timestamp": min(
                    (row["availability_timestamp"] for row in transcript_rows),
                    default=None,
                ),
                "last_availability_timestamp": max(
                    (row["availability_timestamp"] for row in transcript_rows),
                    default=None,
                ),
                "average_confidence_score": _average(
                    [float(row.get("confidence_score") or 0.0) for row in transcript_rows]
                ),
                "same_day_event_count": by_window["same_day"],
                "next_session_event_count": by_window["next_session"],
                "three_session_event_count": by_window["3_session"],
                "five_session_event_count": by_window["5_session"],
            }
        )
    return _rows_frame(rows)


def transcript_rule_performance(alignment: pl.DataFrame, trades: pl.DataFrame) -> pl.DataFrame:
    """Aggregate aligned transcript rule performance by rule and window."""

    if alignment.is_empty():
        return _empty_rule_performance()
    trade_lookup = {
        _serialize_event_key(row.get("event_timestamp"), row.get("signal")): row
        for row in _directional_trade_rows(trades)
    }
    rows = []
    for tag in RULE_TAGS:
        for window in WINDOWS:
            matches = [
                row
                for row in alignment.to_dicts()
                if row.get("rule_tag") == tag and row.get("window_label") == window
            ]
            event_keys = sorted({key for row in matches for key in _alignment_event_keys(row)})
            trade_rows = [
                trade_lookup[key]
                for key in event_keys
                if key in trade_lookup
            ]
            trade_rows = sorted(trade_rows, key=lambda row: row.get("event_timestamp"))
            trade_count = len(trade_rows)
            event_count = len(event_keys)
            no_trade_count = sum(
                1 for key in event_keys if _signal_from_serialized_event_key(key).startswith("NO_TRADE")
            )
            metrics = _metrics(trade_rows)
            rows.append(
                {
                    "rule_tag": tag,
                    "window_label": window,
                    "event_count": event_count,
                    "no_trade_event_count": no_trade_count,
                    "trade_count": trade_count,
                    "win_rate": metrics["win_rate"],
                    "expectancy": metrics["expectancy"],
                    "profit_factor": metrics["profit_factor"],
                    "max_drawdown": metrics["max_drawdown"],
                    "decision_label": _rule_decision(
                        trade_count=trade_count,
                        expectancy=metrics["expectancy"],
                        profit_factor=metrics["profit_factor"],
                    ),
                    "sample_size_warning": trade_count < MIN_RULE_SAMPLE,
                }
            )
    _ = trades
    return _rows_frame(rows)


def transcript_rule_ablation(
    alignment: pl.DataFrame,
    trades: pl.DataFrame,
    signal_events: pl.DataFrame,
) -> pl.DataFrame:
    """Compare all trades to removing events associated with each transcript rule."""

    trade_rows = _directional_trade_rows(trades)
    base_metrics = _metrics(trade_rows)
    rows = []
    all_events = signal_events.to_dicts() if not signal_events.is_empty() else []
    for tag in RULE_TAGS:
        tag_alignments = (
            alignment.filter((pl.col("rule_tag") == tag) & (pl.col("window_label") == "5_session")).to_dicts()
            if not alignment.is_empty()
            else []
        )
        covered_keys = _covered_trade_keys(tag_alignments, all_events)
        without_rule = [
            trade
            for trade in trade_rows
            if _event_key(trade.get("event_timestamp"), trade.get("signal")) not in covered_keys
        ]
        without_metrics = _metrics(without_rule)
        rows.append(
            {
                "rule_tag": tag,
                "base_trade_count": base_metrics["trade_count"],
                "without_rule_trade_count": without_metrics["trade_count"],
                "change_in_trade_count": without_metrics["trade_count"] - base_metrics["trade_count"],
                "base_expectancy": base_metrics["expectancy"],
                "without_rule_expectancy": without_metrics["expectancy"],
                "change_in_expectancy": _none_safe(without_metrics["expectancy"])
                - _none_safe(base_metrics["expectancy"]),
                "base_profit_factor": base_metrics["profit_factor"],
                "without_rule_profit_factor": without_metrics["profit_factor"],
                "change_in_profit_factor": _none_safe(without_metrics["profit_factor"])
                - _none_safe(base_metrics["profit_factor"]),
                "covered_event_count": len(covered_keys),
                "decision_label": _rule_decision(
                    trade_count=base_metrics["trade_count"] - without_metrics["trade_count"],
                    expectancy=base_metrics["expectancy"],
                    profit_factor=base_metrics["profit_factor"],
                ),
            }
        )
    return _rows_frame(rows)


def transcript_final_decision(performance: pl.DataFrame) -> str:
    """Return a conservative final decision for transcript-derived rules."""

    if performance.is_empty():
        return "TRANSCRIPT_RULE_UNVALIDATED"
    decisions = set(performance.get_column("decision_label").to_list())
    if decisions.intersection({"TRANSCRIPT_RULE_SUPPORTED", "TRANSCRIPT_RULE_PROMISING"}):
        # Rule-level support only means the dated rule overlapped favorable
        # outcomes after it was available. It does not prove that transcript
        # availability improves the signal layer out of sample.
        return "TRANSCRIPT_RULE_PROMISING"
    if decisions == {"TRANSCRIPT_RULE_FAILED"}:
        return "TRANSCRIPT_RULE_FAILED"
    return "TRANSCRIPT_RULE_UNVALIDATED"


def write_transcript_alignment_report(
    path: Path,
    *,
    timeline: pl.DataFrame,
    coverage: pl.DataFrame,
    alignment: pl.DataFrame,
    performance: pl.DataFrame,
    ablation: pl.DataFrame,
    final_decision: str,
) -> None:
    """Write Markdown report for transcript timeline alignment."""

    supported = (
        performance.filter(pl.col("decision_label") == "TRANSCRIPT_RULE_SUPPORTED")
        if not performance.is_empty()
        else performance
    )
    failed = (
        performance.filter(pl.col("decision_label") == "TRANSCRIPT_RULE_FAILED")
        if not performance.is_empty()
        else performance
    )
    leakage_violations = (
        int(alignment.get_column("no_lookahead_violations").sum())
        if not alignment.is_empty()
        else 0
    )
    lines = [
        "# Guru Transcript Timeline Alignment",
        "",
        "Research-only transcript evidence layer. Transcript rules are not trading instructions.",
        "",
        f"- Final decision: `{final_decision}`",
        f"- Parsed transcripts: {timeline.height}",
        f"- Alignment no-lookahead violations: {leakage_violations}",
        "- Rule performance uses unique post-availability market events, so overlapping transcript "
        "windows do not multiply-count the same trade.",
        "- Current results show dated overlap with existing signals, not independent proof that "
        "transcript timing improves signal quality.",
        "",
        "## Rule Tag Coverage",
        "",
        _frame_markdown(coverage.sort("transcript_count", descending=True) if not coverage.is_empty() else coverage),
        "",
        "## Rule-by-Rule Performance",
        "",
        _frame_markdown(
            performance.filter(pl.col("window_label") == "5_session")
            if not performance.is_empty()
            else performance
        ),
        "",
        "## Transcript Rule Ablation",
        "",
        _frame_markdown(ablation),
        "",
        "## Supported Guru Rules",
        "",
        _frame_markdown(supported),
        "",
        "## Failed Guru Rules",
        "",
        _frame_markdown(failed),
        "",
        "## Research Questions",
        "",
        *_research_question_lines(coverage, performance, ablation),
        "",
        "## Anti-Leakage Checks",
        "",
        "- Transcript availability timestamp is required for every parsed record.",
        "- Market joins require `availability_timestamp <= event_timestamp`.",
        "- Same-day windows are empty when a transcript is only available after session close.",
        "- No-trade rows are retained in alignment event counts.",
        "- Rule performance and coverage deduplicate event keys across overlapping transcript windows.",
        "- Rule extraction reads transcript text only; it does not inspect future price.",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_transcript_charts(
    *,
    charts_dir: Path,
    coverage: pl.DataFrame,
    performance: pl.DataFrame,
) -> None:
    """Write transcript rule SVG charts."""

    charts_dir.mkdir(parents=True, exist_ok=True)
    coverage_rows = (
        coverage.sort("transcript_count", descending=True).head(20).to_dicts()
        if not coverage.is_empty()
        else []
    )
    _write_bar_svg(
        charts_dir / "transcript_rule_frequency.svg",
        title="Transcript rule frequency",
        labels=[row["rule_tag"] for row in coverage_rows],
        values=[float(row.get("transcript_count") or 0.0) for row in coverage_rows],
    )
    perf_rows = (
        performance.filter(pl.col("window_label") == "5_session").sort("rule_tag").to_dicts()
        if not performance.is_empty()
        else []
    )
    _write_bar_svg(
        charts_dir / "transcript_rule_expectancy.svg",
        title="Transcript rule expectancy",
        labels=[row["rule_tag"] for row in perf_rows],
        values=[float(row.get("expectancy") or 0.0) for row in perf_rows],
    )
    _write_bar_svg(
        charts_dir / "transcript_rule_walk_forward.svg",
        title="Transcript rule support flags",
        labels=[row["rule_tag"] for row in perf_rows],
        values=[
            1.0
            if row.get("decision_label")
            in {"TRANSCRIPT_RULE_SUPPORTED", "TRANSCRIPT_RULE_PROMISING"}
            else 0.0
            for row in perf_rows
        ],
    )


def _parse_transcript_text(path: Path, text: str, *, config: ResearchConfig) -> dict[str, Any]:
    transcript_date, date_note = _parse_transcript_date(path, text)
    availability, availability_note = _availability_timestamp(
        transcript_date,
        path=path,
        text=text,
        config=config,
    )
    title = _parse_title(path, text)
    tag_hits = _tag_hits(text, title)
    tags = [tag for tag, count in tag_hits.items() if count > 0]
    notes = [note for note in (date_note, availability_note) if note]
    if not tags:
        notes.append("no_rule_tags_detected")
    return {
        "transcript_id": _transcript_id(path, text),
        "source_path": str(path),
        "transcript_date": transcript_date.isoformat() if transcript_date else None,
        "availability_timestamp": availability,
        "title": title,
        "detected_rule_tags": "|".join(tags),
        "confidence_score": _confidence_score(tag_hits, text),
        "extracted_numeric_levels": "|".join(_extract_numeric_levels(text)),
        "extracted_basis_values": "|".join(_extract_near_keywords(text, ("basis", "ส่วนต่าง"))),
        "extracted_iv_values": "|".join(_extract_near_keywords(text, ("iv", "implied", "อิมพลาย"))),
        "extracted_sd_values": "|".join(_extract_sd_values(text)),
        "extracted_oi_strikes": "|".join(_extract_near_keywords(text, ("oi", "openinterest", "แนวรับ", "แนวต้าน", "strike"))),
        "notes": "; ".join(notes),
    }


def _looks_combined(text: str) -> bool:
    return text.count("Date: ") > 1 and text.count("Video ID: ") > 1


def _split_combined_transcript(text: str) -> list[str]:
    parts = re.split(r"\n={20,}\n", text)
    return [part.strip() for part in parts if "Date:" in part and "Title:" in part]


def _parse_transcript_date(path: Path, text: str) -> tuple[date | None, str]:
    patterns = [
        r"Date:\s*(\d{4}-\d{2}-\d{2})",
        r"\b(\d{4}-\d{2}-\d{2})\b",
        r"\b(\d{4})(\d{2})(\d{2})\b",
        r"\b(\d{1,2})[/-](\d{1,2})[/-](20\d{2})\b",
    ]
    haystack = f"{path.name}\n{text[:2000]}"
    for pattern in patterns:
        match = re.search(pattern, haystack)
        if not match:
            continue
        try:
            if len(match.groups()) == 1:
                return datetime.strptime(match.group(1), "%Y-%m-%d").date(), "date_from_iso_metadata"
            if pattern.startswith(r"\b(\d{4})"):
                return date(int(match.group(1)), int(match.group(2)), int(match.group(3))), "date_from_yyyymmdd"
            return date(int(match.group(3)), int(match.group(2)), int(match.group(1))), "date_from_title"
        except ValueError:
            continue
    return None, "date_missing_used_file_mtime"


def _availability_timestamp(
    transcript_date: date | None,
    *,
    path: Path,
    text: str,
    config: ResearchConfig,
) -> tuple[datetime, str]:
    explicit = _parse_explicit_timestamp(text)
    if explicit is not None:
        return explicit, "availability_from_explicit_timestamp"
    if transcript_date is None:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC), "availability_from_file_mtime"
    close_time = time(config.session_close_hour_utc, 1, tzinfo=UTC)
    return datetime.combine(transcript_date, close_time), "availability_default_after_session_close"


def _parse_explicit_timestamp(text: str) -> datetime | None:
    match = re.search(
        r"(?:Published|Availability|Available|เผยแพร่)[:\s]+"
        r"(\d{4}-\d{2}-\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?",
        text[:3000],
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    second = int(match.group(4) or 0)
    return datetime.fromisoformat(
        f"{match.group(1)}T{match.group(2)}:{match.group(3)}:{second:02d}+00:00"
    )


def _parse_title(path: Path, text: str) -> str:
    match = re.search(r"Title:\s*(.+)", text[:3000])
    if match:
        return match.group(1).strip()
    title = re.sub(r"\[[^\]]+\]", "", path.stem)
    title = re.sub(r"^\d{4}-\d{2}-\d{2}\s*-\s*", "", title)
    title = title.replace(".th-orig", "")
    return title.strip()


def _tag_hits(text: str, title: str) -> dict[str, int]:
    normalized = _normalize_text(f"{title}\n{text}")
    hits: dict[str, int] = {}
    for tag, keywords in TAG_KEYWORDS.items():
        count = 0
        for keyword in keywords:
            count += normalized.count(keyword.lower())
        hits[tag] = count
    return hits


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower())


def _confidence_score(tag_hits: dict[str, int], text: str) -> float:
    detected = sum(1 for value in tag_hits.values() if value > 0)
    total_hits = sum(tag_hits.values())
    length_factor = min(0.20, len(text) / 100_000)
    return round(min(1.0, 0.10 + detected * 0.045 + min(total_hits, 80) * 0.006 + length_factor), 4)


def _extract_numeric_levels(text: str) -> list[str]:
    values = []
    for match in re.finditer(r"(?<![\w])\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![\w])\d{3,5}(?:\.\d+)?", text):
        raw = match.group(0).replace(",", "")
        try:
            value = float(raw)
        except ValueError:
            continue
        if 100 <= value <= 10_000:
            values.append(raw)
    return _unique_limited(values, limit=30)


def _extract_near_keywords(text: str, keywords: tuple[str, ...]) -> list[str]:
    normalized = _normalize_text(text)
    values = []
    for match in re.finditer(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d{1,5}(?:\.\d+)?", normalized):
        start, end = match.span()
        window = normalized[max(0, start - 60) : min(len(normalized), end + 60)]
        if any(keyword.lower() in window for keyword in keywords):
            values.append(match.group(0).replace(",", ""))
    return _unique_limited(values, limit=20)


def _extract_sd_values(text: str) -> list[str]:
    normalized = _normalize_text(text)
    values = []
    for match in re.finditer(r"(\d+(?:\.\d+)?)\s*sd|sd\s*(\d+(?:\.\d+)?)", normalized):
        values.append(match.group(1) or match.group(2))
    return _unique_limited(values, limit=20)


def _unique_limited(values: list[str], *, limit: int) -> list[str]:
    result = []
    seen = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
        if len(result) >= limit:
            break
    return result


def _transcript_id(path: Path, text: str) -> str:
    video_match = re.search(r"Video ID:\s*([A-Za-z0-9_-]+)", text[:2000])
    if video_match:
        return video_match.group(1)
    bracket_match = re.search(r"\[([A-Za-z0-9_-]{6,})\]", path.name)
    if bracket_match:
        return bracket_match.group(1)
    return re.sub(r"[^A-Za-z0-9_-]+", "_", path.stem)[:80]


def _session_lookup(
    feature_table: pl.DataFrame,
    signal_events: pl.DataFrame,
    *,
    config: ResearchConfig,
) -> dict[str, int]:
    dates = set()
    if not feature_table.is_empty() and "session_date" in feature_table.columns:
        dates.update(str(value) for value in feature_table.get_column("session_date").drop_nulls().to_list())
    if not signal_events.is_empty():
        for row in signal_events.to_dicts():
            timestamp = row.get("event_timestamp")
            if isinstance(timestamp, datetime):
                dates.add(_session_date(timestamp, config=config))
    return {value: index for index, value in enumerate(sorted(dates))}


def _event_rows(
    signal_events: pl.DataFrame,
    session_lookup: dict[str, int],
    *,
    config: ResearchConfig,
) -> list[dict[str, Any]]:
    rows = []
    for row in signal_events.to_dicts():
        timestamp = row.get("event_timestamp")
        if not isinstance(timestamp, datetime):
            continue
        session = _session_date(timestamp, config=config)
        rows.append({**row, "session_date": session, "session_index": session_lookup.get(session)})
    return rows


def _trade_lookup(trades: pl.DataFrame) -> dict[tuple[Any, str], dict[str, Any]]:
    if trades.is_empty():
        return {}
    return {
        _event_key(row.get("event_timestamp"), row.get("signal")): row
        for row in _directional_trade_rows(trades)
    }


def _directional_trade_rows(trades: pl.DataFrame) -> list[dict[str, Any]]:
    if trades.is_empty():
        return []
    directional = {
        Signal.FADE_WALL_LONG.value,
        Signal.FADE_WALL_SHORT.value,
        Signal.BREAK_WALL_LONG.value,
        Signal.BREAK_WALL_SHORT.value,
    }
    return [row for row in trades.to_dicts() if row.get("signal") in directional]


def _covered_trade_keys(tag_alignments: list[dict[str, Any]], events: list[dict[str, Any]]) -> set[tuple[Any, str]]:
    if not tag_alignments:
        return set()
    keys = set()
    event_map = {
        _serialize_event_key(event.get("event_timestamp"), event.get("signal")): _event_key(
            event.get("event_timestamp"),
            event.get("signal"),
        )
        for event in events
    }
    for alignment in tag_alignments:
        serialized_keys = _alignment_event_keys(alignment)
        if serialized_keys:
            keys.update(event_map[key] for key in serialized_keys if key in event_map)
            continue
        availability = alignment.get("availability_timestamp")
        last_event = alignment.get("last_event_timestamp")
        if availability is None or last_event is None:
            continue
        for event in events:
            timestamp = event.get("event_timestamp")
            if isinstance(timestamp, datetime) and availability <= timestamp <= last_event:
                keys.add(_event_key(timestamp, event.get("signal")))
    return keys


def _in_window(
    *,
    event_session_index: int | None,
    transcript_session_index: int | None,
    window: str,
) -> bool:
    if event_session_index is None or transcript_session_index is None:
        return False
    delta = event_session_index - transcript_session_index
    if window == "same_day":
        return delta == 0
    if window == "next_session":
        return delta == 1
    if window == "3_session":
        return 1 <= delta <= 3
    if window == "5_session":
        return 1 <= delta <= 5
    raise ValueError(f"unknown window: {window}")


def _session_date(timestamp: datetime, *, config: ResearchConfig) -> str:
    ts = timestamp.astimezone(UTC)
    session_day = ts.date()
    if ts.hour < config.session_open_hour_utc:
        session_day -= timedelta(days=1)
    return session_day.isoformat()


def _event_key(timestamp: Any, signal: Any) -> tuple[Any, str]:
    return timestamp, str(signal or "")


def _serialize_event_key(timestamp: Any, signal: Any) -> str:
    timestamp_value = timestamp.isoformat() if isinstance(timestamp, datetime) else str(timestamp or "")
    return f"{timestamp_value}::{str(signal or '')}"


def _alignment_event_keys(row: dict[str, Any]) -> list[str]:
    value = row.get("event_keys")
    if value is None:
        return []
    return [part for part in str(value).split("|") if part]


def _signal_from_serialized_event_key(key: str) -> str:
    return key.rsplit("::", 1)[-1] if "::" in key else ""


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    pnl = [float(row.get("net_pnl_points", row.get("pnl_points", 0.0))) for row in rows]
    wins = [value for value in pnl if value > 0]
    losses = [value for value in pnl if value < 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    equity = []
    running = 0.0
    for value in pnl:
        running += value
        equity.append(running)
    return {
        "trade_count": len(rows),
        "win_rate": len(wins) / len(rows) if rows else None,
        "expectancy": sum(pnl) / len(pnl) if pnl else None,
        "profit_factor": gross_win / gross_loss if gross_loss > 0 else None,
        "max_drawdown": _max_drawdown(equity),
    }


def _combine_alignment_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    trade_count = sum(int(row.get("trade_count") or 0) for row in rows)
    if trade_count == 0:
        return {"win_rate": None, "expectancy": None, "profit_factor": None, "max_drawdown": 0.0}
    expectancy = sum(
        float(row.get("expectancy") or 0.0) * int(row.get("trade_count") or 0)
        for row in rows
    ) / trade_count
    win_rate = sum(
        float(row.get("win_rate") or 0.0) * int(row.get("trade_count") or 0)
        for row in rows
    ) / trade_count
    gross_pf_numerators = []
    profit_factors = []
    for row in rows:
        if row.get("profit_factor") is not None and int(row.get("trade_count") or 0) > 0:
            profit_factors.append(float(row["profit_factor"]))
            gross_pf_numerators.append(int(row.get("trade_count") or 0))
    profit_factor = (
        sum(pf * weight for pf, weight in zip(profit_factors, gross_pf_numerators, strict=False))
        / sum(gross_pf_numerators)
        if gross_pf_numerators
        else None
    )
    max_drawdown = min((float(row.get("max_drawdown") or 0.0) for row in rows), default=0.0)
    return {
        "win_rate": win_rate,
        "expectancy": expectancy,
        "profit_factor": profit_factor,
        "max_drawdown": max_drawdown,
    }


def _rule_decision(
    *,
    trade_count: int,
    expectancy: Any,
    profit_factor: Any,
) -> str:
    value = _none_safe(expectancy)
    pf = _none_safe(profit_factor)
    if trade_count >= MIN_RULE_SAMPLE and value > 0 and pf >= 1.2:
        return "TRANSCRIPT_RULE_SUPPORTED"
    if trade_count >= max(3, MIN_RULE_SAMPLE // 2) and value > 0:
        return "TRANSCRIPT_RULE_PROMISING"
    if trade_count >= MIN_RULE_SAMPLE and value < 0:
        return "TRANSCRIPT_RULE_FAILED"
    return "TRANSCRIPT_RULE_UNVALIDATED"


def _research_question_lines(
    coverage: pl.DataFrame,
    performance: pl.DataFrame,
    ablation: pl.DataFrame,
) -> list[str]:
    most_common = []
    if not coverage.is_empty():
        most_common = [
            row["rule_tag"]
            for row in coverage.sort("transcript_count", descending=True).head(5).to_dicts()
            if int(row.get("transcript_count") or 0) > 0
        ]
    supported = []
    if not performance.is_empty():
        supported = [
            row["rule_tag"]
            for row in performance.filter(pl.col("decision_label") == "TRANSCRIPT_RULE_SUPPORTED")
            .select("rule_tag")
            .unique()
            .to_dicts()
        ]
    failed = []
    if not performance.is_empty():
        failed = [
            row["rule_tag"]
            for row in performance.filter(pl.col("decision_label") == "TRANSCRIPT_RULE_FAILED")
            .select("rule_tag")
            .unique()
            .to_dicts()
        ]
    _ = ablation
    return [
        f"- Most common rule tags: {', '.join(most_common) if most_common else 'none detected'}.",
        f"- Rule tags overlapping with supported windows: {', '.join(supported) if supported else 'none yet'}.",
        "- BASIS_ADJUSTMENT wall accuracy: unvalidated here without an unadjusted transcript-specific wall ablation.",
        "- OPEN_PRICE_THEORY open-flip test: unvalidated until explicit open-flip outcome columns are added.",
        "- NO_TRADE_DISCIPLINE: tracked through no-trade event counts; not enough evidence to claim improvement.",
        "- ACCEPTANCE_CLOSE_CONFIRMATION: evaluated through breakout-aligned trades; no profitability claim is made.",
        "- REJECTION_AT_WALL: evaluated through fade-aligned trades; support requires sufficient aligned samples.",
        "- IV_RV_VRP: tracked as a rule tag and market regime overlap; current support depends on aligned samples.",
        "- LOW_OI_GAP / SQUEEZE_RISK: tracked through continuation windows; no validated continuation edge is claimed.",
        f"- Failed rule tags: {', '.join(failed) if failed else 'none with sufficient negative sample yet'}.",
    ]


def _split_tags(value: Any) -> list[str]:
    if value is None:
        return []
    return [tag for tag in str(value).split("|") if tag]


def _average(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _max_drawdown(equity: list[float]) -> float:
    peak = 0.0
    max_dd = 0.0
    for value in equity:
        peak = max(peak, value)
        max_dd = min(max_dd, value - peak)
    return max_dd


def _none_safe(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _frame_markdown(frame: pl.DataFrame) -> str:
    if frame.is_empty():
        return "_No rows._"
    rows = ["| " + " | ".join(frame.columns) + " |", "|" + "|".join(["---"] * len(frame.columns)) + "|"]
    for raw in frame.head(25).to_dicts():
        rows.append("| " + " | ".join(str(raw.get(column, "")) for column in frame.columns) + " |")
    return "\n".join(rows)


def _write_bar_svg(path: Path, *, title: str, labels: list[str], values: list[float]) -> None:
    width, height = 900, 340
    if not values:
        path.write_text(_svg(title, '<text x="40" y="80">No data.</text>'), encoding="utf-8")
        return
    minimum = min(0.0, min(values))
    maximum = max(0.0, max(values))
    span = max(maximum - minimum, 1.0)
    bar_step = (width - 120) / max(len(values), 1)
    bar_width = max(6.0, bar_step * 0.65)
    zero_y = height - 55 - ((0 - minimum) / span) * (height - 105)
    body = [f'<line x1="45" x2="{width - 35}" y1="{zero_y:.1f}" y2="{zero_y:.1f}" stroke="#9ca3af" />']
    for index, value in enumerate(values):
        x = 55 + index * bar_step
        y = height - 55 - ((max(value, 0.0) - minimum) / span) * (height - 105)
        base_y = height - 55 - ((min(value, 0.0) - minimum) / span) * (height - 105)
        body.append(
            f'<rect x="{x:.1f}" y="{min(y, base_y):.1f}" width="{bar_width:.1f}" '
            f'height="{max(abs(base_y - y), 1.0):.1f}" fill="#2563eb" />'
        )
        label = labels[index][:18]
        body.append(
            f'<text x="{x:.1f}" y="{height - 28}" font-size="9" '
            f'transform="rotate(35 {x:.1f},{height - 28})">{label}</text>'
        )
    path.write_text(_svg(title, "\n".join(body)), encoding="utf-8")


def _svg(title: str, body: str) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="340" '
        'viewBox="0 0 900 340">'
        '<rect width="900" height="340" fill="#ffffff" />'
        f'<text x="40" y="30" font-size="18" font-family="Arial">{title}</text>'
        f"{body}</svg>"
    )


def _rows_frame(rows: list[dict[str, Any]]) -> pl.DataFrame:
    return pl.DataFrame(rows, infer_schema_length=None)


def _empty_timeline() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "transcript_id": pl.String,
            "source_path": pl.String,
            "transcript_date": pl.String,
            "availability_timestamp": pl.Datetime(time_zone="UTC"),
            "title": pl.String,
            "detected_rule_tags": pl.String,
            "confidence_score": pl.Float64,
            "extracted_numeric_levels": pl.String,
            "extracted_basis_values": pl.String,
            "extracted_iv_values": pl.String,
            "extracted_sd_values": pl.String,
            "extracted_oi_strikes": pl.String,
            "notes": pl.String,
        }
    )


def _empty_coverage() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "rule_tag": pl.String,
            "transcript_count": pl.Int64,
            "first_availability_timestamp": pl.Datetime(time_zone="UTC"),
            "last_availability_timestamp": pl.Datetime(time_zone="UTC"),
            "average_confidence_score": pl.Float64,
            "same_day_event_count": pl.Int64,
            "next_session_event_count": pl.Int64,
            "three_session_event_count": pl.Int64,
            "five_session_event_count": pl.Int64,
        }
    )


def _empty_alignment() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "transcript_id": pl.String,
            "rule_tag": pl.String,
            "window_label": pl.String,
            "availability_timestamp": pl.Datetime(time_zone="UTC"),
            "transcript_session_date": pl.String,
            "event_count": pl.Int64,
            "no_trade_event_count": pl.Int64,
            "trade_count": pl.Int64,
            "win_rate": pl.Float64,
            "expectancy": pl.Float64,
            "profit_factor": pl.Float64,
            "max_drawdown": pl.Float64,
            "event_keys": pl.String,
            "first_event_timestamp": pl.Datetime(time_zone="UTC"),
            "last_event_timestamp": pl.Datetime(time_zone="UTC"),
            "no_lookahead_violations": pl.Int64,
        }
    )


def _empty_rule_performance() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "rule_tag": pl.String,
            "window_label": pl.String,
            "event_count": pl.Int64,
            "no_trade_event_count": pl.Int64,
            "trade_count": pl.Int64,
            "win_rate": pl.Float64,
            "expectancy": pl.Float64,
            "profit_factor": pl.Float64,
            "max_drawdown": pl.Float64,
            "decision_label": pl.String,
            "sample_size_warning": pl.Boolean,
        }
    )
