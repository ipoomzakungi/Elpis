"""Human-supervised review queue for guru transcript logic.

The queue keeps original transcript excerpts and blocks predictive claims until
rules are reviewed. LLM or keyword output remains a structured research feature;
it never becomes a direct trade signal.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import polars as pl

from research_xau_vol_oi.config import ResearchConfig
from research_xau_vol_oi.llm_transcript_extractor import (
    RuleQuality,
    RuleType,
    validate_rule_record,
)


REVIEW_DECISIONS = ("APPROVE", "REJECT", "NEEDS_MORE_CONTEXT", "POST_EVENT_ONLY", "DUPLICATE")
PRIORITY_RULE_TYPES = {
    RuleType.ENTRY_CONDITION.value,
    RuleType.INVALIDATION_RULE.value,
    RuleType.NO_TRADE_FILTER.value,
}
GURU_LOGIC_DECISIONS = (
    "GURU_LOGIC_REVIEW_REQUIRED",
    "GURU_LOGIC_APPROVED_CONTEXT_ONLY",
    "GURU_LOGIC_APPROVED_FILTER_CANDIDATE",
    "GURU_LOGIC_VALIDATED_FILTER",
)


@dataclass(frozen=True)
class GuruReviewQueueResult:
    """Review queue frames and conservative decision summary."""

    review_queue: pl.DataFrame
    review_sample: pl.DataFrame
    decisions_template: pl.DataFrame
    approved_rules: pl.DataFrame
    final_decision: str
    review_decisions_exist: bool


def run_guru_review_queue_layer(
    *,
    extracted_rules: pl.DataFrame,
    quality_audit: pl.DataFrame,
    signal_events: pl.DataFrame,
    feature_table: pl.DataFrame,
    output_dir: Path,
    config: ResearchConfig | None = None,
    external_llm_jsonl_path: str | Path = Path("inputs/external_llm_guru_rules.jsonl"),
    decisions_path: str | Path | None = None,
) -> GuruReviewQueueResult:
    """Build review artifacts and load any human approval decisions."""

    cfg = config or ResearchConfig()
    output_dir.mkdir(parents=True, exist_ok=True)
    external_records = import_external_llm_rules(
        external_llm_jsonl_path,
        transcript_lookup=_transcript_lookup(extracted_rules),
    )
    if external_records:
        extracted_rules = pl.concat(
            [extracted_rules, _rows_frame(external_records)],
            how="diagonal_relaxed",
        )

    review_queue = build_guru_review_queue(
        extracted_rules,
        quality_audit,
        signal_events,
        feature_table,
    )
    review_sample = review_queue.head(50)
    decisions_template = build_review_decisions_template(review_queue)
    actual_decisions_path = Path(decisions_path) if decisions_path is not None else cfg.guru_review_decisions_path
    approved_rules, decisions_exist = load_approved_review_rules(review_queue, actual_decisions_path)
    final_decision = guru_logic_final_decision(approved_rules, decisions_exist)

    review_queue.write_csv(output_dir / "guru_rule_review_queue.csv")
    review_sample.write_csv(output_dir / "guru_rule_review_sample.csv")
    decisions_template.write_csv(output_dir / "guru_rule_review_decisions_template.csv")
    write_guru_review_report(
        output_dir / "guru_rule_review_report.md",
        review_queue=review_queue,
        approved_rules=approved_rules,
        final_decision=final_decision,
        review_decisions_exist=decisions_exist,
        external_records_count=len(external_records),
    )
    return GuruReviewQueueResult(
        review_queue=review_queue,
        review_sample=review_sample,
        decisions_template=decisions_template,
        approved_rules=approved_rules,
        final_decision=final_decision,
        review_decisions_exist=decisions_exist,
    )


def build_guru_review_queue(
    extracted_rules: pl.DataFrame,
    quality_audit: pl.DataFrame,
    signal_events: pl.DataFrame,
    feature_table: pl.DataFrame,
) -> pl.DataFrame:
    """Create a deduplicated priority-sorted review queue."""

    if extracted_rules.is_empty():
        return _empty_review_queue()
    audit_lookup = {
        (row.get("transcript_id"), row.get("rule_tag")): row
        for row in quality_audit.to_dicts()
    } if not quality_audit.is_empty() else {}
    signal_timestamps = _event_timestamps(signal_events)
    repeated_counts = extracted_rules.group_by("rule_tag").len().to_dicts()
    repeat_lookup = {row["rule_tag"]: int(row["len"]) for row in repeated_counts}
    rows = []
    seen: set[tuple[str, str, str]] = set()
    duplicate_counts: dict[str, int] = {}
    for record in extracted_rules.to_dicts():
        excerpt = str(record.get("source_excerpt") or "")
        rule_tag = str(record.get("rule_tag") or "")
        fingerprint = excerpt_fingerprint(excerpt)
        duplicate_group_id = _duplicate_group_id(record.get("transcript_id"), rule_tag, fingerprint)
        duplicate_counts[duplicate_group_id] = duplicate_counts.get(duplicate_group_id, 0) + 1
        key = (str(record.get("transcript_id") or ""), rule_tag, fingerprint)
        if key in seen:
            continue
        seen.add(key)
        audit = audit_lookup.get((record.get("transcript_id"), rule_tag), {})
        quality_label = str(audit.get("rule_quality") or "CONTEXT_ONLY")
        numeric_levels = extract_numeric_levels(excerpt)
        timestamp_like = timestamp_like_numeric_levels(excerpt, numeric_levels)
        srt_artifact = likely_srt_timestamp_artifact(excerpt)
        near_signal = near_signal_event(record.get("availability_timestamp"), signal_timestamps)
        priority_score = review_priority_score(
            quality_label=quality_label,
            rule_type=str(record.get("rule_type") or ""),
            leakage_risk_score=_float(record.get("leakage_risk_score")),
            has_numeric=bool(numeric_levels),
            near_signal_event=near_signal,
            repeated_count=repeat_lookup.get(rule_tag, 0),
        )
        rows.append(
            {
                "review_id": _review_id(record, duplicate_group_id),
                "transcript_id": record.get("transcript_id"),
                "transcript_date": record.get("transcript_date"),
                "availability_timestamp": record.get("availability_timestamp"),
                "source_excerpt": excerpt,
                "normalized_english_summary": record.get("normalized_english_summary"),
                "rule_tag": rule_tag,
                "rule_type": record.get("rule_type"),
                "condition": record.get("condition"),
                "action_bias": record.get("action_bias"),
                "observable_inputs": record.get("observable_inputs"),
                "required_market_data": record.get("required_market_data"),
                "extracted_numeric_levels": "|".join(numeric_levels),
                "confidence_score": record.get("confidence_score"),
                "testability_score": record.get("testability_score"),
                "leakage_risk_score": record.get("leakage_risk_score"),
                "quality_label": quality_label,
                "suggested_review_priority": priority_label(priority_score),
                "review_priority_score": priority_score,
                "reviewer_decision": "",
                "reviewer_notes": "",
                "duplicate_group_id": duplicate_group_id,
                "duplicate_count": duplicate_counts.get(duplicate_group_id, 1),
                "near_signal_event": near_signal,
                "likely_srt_timestamp_artifact": srt_artifact,
                "timestamp_like_numeric_levels": "|".join(timestamp_like),
                "vague_context_only": quality_label == RuleQuality.CONTEXT_ONLY.value,
                "research_only": True,
            }
        )
    if not rows:
        return _empty_review_queue()
    for row in rows:
        row["duplicate_count"] = duplicate_counts.get(str(row["duplicate_group_id"]), 1)
    frame = _rows_frame(rows)
    return frame.sort(
        ["review_priority_score", "leakage_risk_score", "testability_score"],
        descending=[True, True, True],
    )


def build_review_decisions_template(review_queue: pl.DataFrame) -> pl.DataFrame:
    """Create a blank human decision template."""

    if review_queue.is_empty():
        return _empty_decisions_template()
    columns = [
        "review_id",
        "transcript_id",
        "rule_tag",
        "rule_type",
        "quality_label",
        "source_excerpt",
        "reviewer_decision",
        "reviewer_notes",
    ]
    return review_queue.select(columns)


def load_approved_review_rules(
    review_queue: pl.DataFrame,
    decisions_path: str | Path,
) -> tuple[pl.DataFrame, bool]:
    """Load approved human review decisions and return approved rule rows."""

    path = Path(decisions_path)
    if review_queue.is_empty() or not path.exists():
        return _empty_approved_rules(), False
    decisions = pl.read_csv(path)
    if decisions.is_empty() or "review_id" not in decisions.columns:
        return _empty_approved_rules(), True
    decision_lookup = {row["review_id"]: row for row in decisions.to_dicts()}
    approved = []
    for row in review_queue.to_dicts():
        decision = decision_lookup.get(row["review_id"], {})
        value = str(decision.get("reviewer_decision") or "").strip().upper()
        if value not in REVIEW_DECISIONS:
            continue
        if value == "APPROVE":
            approved.append(
                {
                    **row,
                    "reviewer_decision": value,
                    "reviewer_notes": decision.get("reviewer_notes") or "",
                    "approved_for_research_features": True,
                }
            )
    return (_rows_frame(approved) if approved else _empty_approved_rules()), True


def import_external_llm_rules(
    path: str | Path,
    *,
    transcript_lookup: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Import optional external JSONL rules after strict validation."""

    source = Path(path)
    if not source.exists():
        return []
    lookup = transcript_lookup or {}
    imported = []
    for line_no, line in enumerate(source.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line.strip():
            continue
        record = json.loads(line)
        imported.append(validate_external_llm_rule(record, transcript_lookup=lookup, line_no=line_no))
    return imported


def validate_external_llm_rule(
    record: dict[str, Any],
    *,
    transcript_lookup: dict[str, dict[str, Any]] | None = None,
    line_no: int = 0,
) -> dict[str, Any]:
    """Validate external LLM JSONL rule records and normalize to internal schema."""

    required = {
        "transcript_id",
        "source_excerpt",
        "normalized_english_summary",
        "rule_tag",
        "rule_type",
        "condition",
        "action_bias",
        "invalidation_rule",
        "required_market_data",
        "confidence_score",
        "testability_score",
        "leakage_risk_score",
    }
    missing = sorted(required - set(record))
    if missing:
        raise ValueError(f"external LLM rule line {line_no} missing fields: {', '.join(missing)}")
    if not str(record.get("source_excerpt") or "").strip():
        raise ValueError(f"external LLM rule line {line_no} missing source_excerpt")
    transcript_id = str(record["transcript_id"])
    lookup_row = (transcript_lookup or {}).get(transcript_id, {})
    availability = record.get("availability_timestamp") or lookup_row.get("availability_timestamp")
    if availability in (None, ""):
        raise ValueError(f"external LLM rule line {line_no} missing transcript availability timestamp")
    if _direct_instruction_without_condition(record):
        raise ValueError(f"external LLM rule line {line_no} contains direct BUY/SELL instruction")
    normalized = validate_rule_record(
        {
            "transcript_id": transcript_id,
            "transcript_date": record.get("transcript_date") or lookup_row.get("transcript_date"),
            "availability_timestamp": availability,
            "source_excerpt": record["source_excerpt"],
            "normalized_english_summary": record["normalized_english_summary"],
            "rule_tag": record["rule_tag"],
            "rule_type": record["rule_type"],
            "observable_inputs": record.get("observable_inputs") or "",
            "required_market_data": record["required_market_data"],
            "condition": record["condition"],
            "action_bias": record["action_bias"],
            "confidence_score": record["confidence_score"],
            "testability_score": record["testability_score"],
            "leakage_risk_score": record["leakage_risk_score"],
            "notes": f"external_llm_jsonl; invalidation_rule={record.get('invalidation_rule')}",
        }
    )
    return normalized


def guru_logic_final_decision(approved_rules: pl.DataFrame, decisions_exist: bool) -> str:
    """Return conservative guru logic review decision."""

    if not decisions_exist:
        return "GURU_LOGIC_REVIEW_REQUIRED"
    if approved_rules.is_empty():
        return "GURU_LOGIC_REVIEW_REQUIRED"
    has_filter_candidate = approved_rules.filter(
        pl.col("rule_type").is_in(list(PRIORITY_RULE_TYPES))
        & pl.col("quality_label").is_in([
            RuleQuality.TESTABLE_AND_OBSERVABLE.value,
            RuleQuality.TESTABLE_BUT_NEEDS_DATA.value,
        ])
    ).height > 0
    if has_filter_candidate:
        return "GURU_LOGIC_APPROVED_FILTER_CANDIDATE"
    return "GURU_LOGIC_APPROVED_CONTEXT_ONLY"


def write_guru_review_report(
    path: Path,
    *,
    review_queue: pl.DataFrame,
    approved_rules: pl.DataFrame,
    final_decision: str,
    review_decisions_exist: bool,
    external_records_count: int,
) -> None:
    """Write Markdown review report."""

    priority_counts = (
        review_queue.group_by("suggested_review_priority").len().sort("suggested_review_priority")
        if not review_queue.is_empty()
        else review_queue
    )
    top_priorities = review_queue.head(25) if not review_queue.is_empty() else review_queue
    quality_counts = (
        review_queue.group_by("quality_label").len().sort("quality_label")
        if not review_queue.is_empty()
        else review_queue
    )
    lines = [
        "# Guru Logic Review Queue",
        "",
        "Human-supervised review gate for extracted transcript rules. This is research-only.",
        "",
        f"- Final decision: `{final_decision}`",
        f"- Review queue rows: {review_queue.height}",
        f"- Approved rules available: {approved_rules.height}",
        f"- Review decisions file found: {review_decisions_exist}",
        f"- External LLM records imported: {external_records_count}",
        "- Unreviewed or rejected rules are not eligible for approved-only rule testing.",
        "",
        "## Reviewed vs Unreviewed Rule Status",
        "",
        _frame_markdown(priority_counts),
        "",
        "## Rule Quality Counts",
        "",
        _frame_markdown(quality_counts),
        "",
        "## Top Review Priorities",
        "",
        _frame_markdown(
            top_priorities.select([
                "review_id",
                "rule_tag",
                "rule_type",
                "quality_label",
                "suggested_review_priority",
                "leakage_risk_score",
                "extracted_numeric_levels",
                "likely_srt_timestamp_artifact",
                "timestamp_like_numeric_levels",
            ])
            if not top_priorities.is_empty()
            else top_priorities
        ),
        "",
        "## Approved Rules Available",
        "",
        _frame_markdown(approved_rules),
        "",
        "## Review Required Before Predictive Claim",
        "",
        "- `GURU_LOGIC_VALIDATED_FILTER` is blocked until rules are human-approved, "
        "walk-forward uplift is positive, placebo tests pass, sample size is sufficient, "
        "and no future transcript leakage exists.",
        "- LLM records are JSON features only. They never execute trades or create direct signals.",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def approved_rules_to_timeline(approved_rules: pl.DataFrame) -> pl.DataFrame:
    """Convert approved review rows to transcript-like rows for approved-only uplift."""

    if approved_rules.is_empty():
        return pl.DataFrame(
            schema={
                "transcript_id": pl.String,
                "transcript_date": pl.String,
                "availability_timestamp": pl.Datetime(time_zone="UTC"),
                "detected_rule_tags": pl.String,
                "confidence_score": pl.Float64,
            }
        )
    grouped: dict[tuple[Any, Any], dict[str, Any]] = {}
    for row in approved_rules.to_dicts():
        key = (row.get("transcript_id"), row.get("availability_timestamp"))
        item = grouped.setdefault(
            key,
            {
                "transcript_id": row.get("transcript_id"),
                "transcript_date": row.get("transcript_date"),
                "availability_timestamp": row.get("availability_timestamp"),
                "detected_rule_tags": set(),
                "confidence_scores": [],
            },
        )
        item["detected_rule_tags"].add(row.get("rule_tag"))
        item["confidence_scores"].append(_float(row.get("confidence_score")))
    rows = []
    for item in grouped.values():
        rows.append(
            {
                "transcript_id": item["transcript_id"],
                "transcript_date": item["transcript_date"],
                "availability_timestamp": item["availability_timestamp"],
                "detected_rule_tags": "|".join(sorted(tag for tag in item["detected_rule_tags"] if tag)),
                "confidence_score": sum(item["confidence_scores"]) / len(item["confidence_scores"])
                if item["confidence_scores"]
                else None,
            }
        )
    return _rows_frame(rows)


def review_priority_score(
    *,
    quality_label: str,
    rule_type: str,
    leakage_risk_score: float,
    has_numeric: bool,
    near_signal_event: bool,
    repeated_count: int,
) -> float:
    """Score queue priority; higher means review first."""

    score = 0.0
    if quality_label == RuleQuality.TESTABLE_AND_OBSERVABLE.value:
        score += 100
    elif quality_label == RuleQuality.TESTABLE_BUT_NEEDS_DATA.value:
        score += 55
    elif quality_label == RuleQuality.REJECT_LEAKAGE_RISK.value:
        score += 75
    if rule_type in PRIORITY_RULE_TYPES:
        score += 70
    if leakage_risk_score >= 0.70:
        score += 65
    if has_numeric:
        score += 25
    if near_signal_event:
        score += 20
    score += min(repeated_count, 20)
    return score


def priority_label(score: float) -> str:
    if score >= 150:
        return "HIGH"
    if score >= 80:
        return "MEDIUM"
    return "LOW"


def extract_numeric_levels(text: str) -> list[str]:
    values = []
    for match in re.finditer(r"(?<![\w])\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![\w])\d{3,5}(?:\.\d+)?", text):
        raw = match.group(0).replace(",", "")
        try:
            value = float(raw)
        except ValueError:
            continue
        if 100 <= value <= 10_000:
            values.append(raw)
    return _unique(values, limit=20)


def likely_srt_timestamp_artifact(text: str) -> bool:
    return bool(re.search(r"\d{2}:\d{2}:\d{2}[,.]\d{3}\s*-->", text))


def timestamp_like_numeric_levels(text: str, levels: list[str]) -> list[str]:
    if not levels:
        return []
    result = []
    has_srt = likely_srt_timestamp_artifact(text)
    for level in levels:
        try:
            value = float(level)
        except ValueError:
            continue
        normalized_level = level.lstrip("0") or "0"
        if has_srt and value < 1000:
            result.append(normalized_level)
        elif re.search(rf"\b\d{{2}}:\d{{2}}:\d{{2}}[,.]?{re.escape(level[-3:])}\b", text):
            result.append(level[-3:].lstrip("0") or "0")
    return _unique(result, limit=20)


def near_signal_event(availability: Any, event_timestamps: list[datetime]) -> bool:
    timestamp = _to_datetime(availability)
    if timestamp is None:
        return False
    end = timestamp + timedelta(hours=24)
    return any(timestamp <= event <= end for event in event_timestamps)


def excerpt_fingerprint(excerpt: str) -> str:
    normalized = re.sub(r"\d+", "#", re.sub(r"\s+", " ", excerpt.lower())).strip()
    return hashlib.sha1(normalized[:280].encode("utf-8")).hexdigest()[:16]


def _review_id(record: dict[str, Any], duplicate_group_id: str) -> str:
    raw = "|".join(
        [
            str(record.get("transcript_id") or ""),
            str(record.get("rule_tag") or ""),
            duplicate_group_id,
        ]
    )
    return "grq_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _duplicate_group_id(transcript_id: Any, rule_tag: str, fingerprint: str) -> str:
    raw = f"{transcript_id}|{rule_tag}|{fingerprint}"
    return "dup_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _direct_instruction_without_condition(record: dict[str, Any]) -> bool:
    text = " ".join(
        str(record.get(column) or "")
        for column in ("source_excerpt", "normalized_english_summary", "condition")
    ).lower()
    has_direct = bool(re.search(r"\b(buy|sell|long now|short now)\b|ซื้อเลย|ขายเลย", text))
    has_condition = bool(re.search(r"\b(if|when|only if|provided that)\b|ถ้า|เมื่อ|หาก", text))
    return has_direct and not has_condition


def _transcript_lookup(extracted_rules: pl.DataFrame) -> dict[str, dict[str, Any]]:
    if extracted_rules.is_empty():
        return {}
    lookup = {}
    for row in extracted_rules.to_dicts():
        lookup.setdefault(
            str(row.get("transcript_id") or ""),
            {
                "transcript_date": row.get("transcript_date"),
                "availability_timestamp": row.get("availability_timestamp"),
            },
        )
    return lookup


def _event_timestamps(signal_events: pl.DataFrame) -> list[datetime]:
    if signal_events.is_empty() or "event_timestamp" not in signal_events.columns:
        return []
    timestamps = [_to_datetime(value) for value in signal_events.get_column("event_timestamp").to_list()]
    return sorted(timestamp for timestamp in timestamps if timestamp is not None)


def _to_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value)
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    if len(text) >= 5 and text[-5] in {"+", "-"} and text[-2] != ":":
        text = f"{text[:-2]}:{text[-2:]}"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _unique(values: list[str], *, limit: int) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
        if len(result) >= limit:
            break
    return result


def _rows_frame(rows: list[dict[str, Any]]) -> pl.DataFrame:
    return pl.DataFrame(rows, infer_schema_length=None)


def _frame_markdown(frame: pl.DataFrame) -> str:
    if frame.is_empty():
        return "_No rows._"
    rows = ["| " + " | ".join(frame.columns) + " |", "|" + "|".join(["---"] * len(frame.columns)) + "|"]
    for raw in frame.head(25).to_dicts():
        rows.append("| " + " | ".join(str(raw.get(column, "")) for column in frame.columns) + " |")
    return "\n".join(rows)


def _empty_review_queue() -> pl.DataFrame:
    schema = {
        "review_id": pl.String,
        "transcript_id": pl.String,
        "transcript_date": pl.String,
        "availability_timestamp": pl.Datetime(time_zone="UTC"),
        "source_excerpt": pl.String,
        "normalized_english_summary": pl.String,
        "rule_tag": pl.String,
        "rule_type": pl.String,
        "condition": pl.String,
        "action_bias": pl.String,
        "observable_inputs": pl.String,
        "required_market_data": pl.String,
        "extracted_numeric_levels": pl.String,
        "confidence_score": pl.Float64,
        "testability_score": pl.Float64,
        "leakage_risk_score": pl.Float64,
        "quality_label": pl.String,
        "suggested_review_priority": pl.String,
        "review_priority_score": pl.Float64,
        "reviewer_decision": pl.String,
        "reviewer_notes": pl.String,
        "duplicate_group_id": pl.String,
        "duplicate_count": pl.Int64,
        "near_signal_event": pl.Boolean,
        "likely_srt_timestamp_artifact": pl.Boolean,
        "timestamp_like_numeric_levels": pl.String,
        "vague_context_only": pl.Boolean,
        "research_only": pl.Boolean,
    }
    return pl.DataFrame(schema=schema)


def _empty_decisions_template() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "review_id": pl.String,
            "transcript_id": pl.String,
            "rule_tag": pl.String,
            "rule_type": pl.String,
            "quality_label": pl.String,
            "source_excerpt": pl.String,
            "reviewer_decision": pl.String,
            "reviewer_notes": pl.String,
        }
    )


def _empty_approved_rules() -> pl.DataFrame:
    schema = dict(_empty_review_queue().schema)
    schema["approved_for_research_features"] = pl.Boolean
    return pl.DataFrame(schema=schema)
