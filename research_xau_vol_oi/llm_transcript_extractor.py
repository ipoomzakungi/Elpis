"""Optional offline transcript extraction audit layer.

This module does not call an LLM. It defines the strict JSON-record schema
and provides a deterministic offline extractor so the pipeline can audit
keyword extraction risk today. Externally produced LLM records can be loaded
later only as structured research features and must still pass validation,
backtest, walk-forward, and placebo checks before use.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import polars as pl

from research_xau_vol_oi.config import ResearchConfig
from research_xau_vol_oi.transcript_timeline import RULE_TAGS, TAG_KEYWORDS


class RuleType(StrEnum):
    """Allowed structured rule types."""

    MARKET_MAP = "MARKET_MAP"
    NO_TRADE_FILTER = "NO_TRADE_FILTER"
    ENTRY_CONDITION = "ENTRY_CONDITION"
    INVALIDATION_RULE = "INVALIDATION_RULE"
    RISK_RULE = "RISK_RULE"
    POST_EVENT_COMMENTARY = "POST_EVENT_COMMENTARY"
    UNTESTABLE_OPINION = "UNTESTABLE_OPINION"


class ActionBias(StrEnum):
    """Allowed non-execution action bias labels."""

    NO_TRADE = "NO_TRADE"
    WATCH_ONLY = "WATCH_ONLY"
    FADE = "FADE"
    BREAKOUT = "BREAKOUT"
    PIN_RISK = "PIN_RISK"
    SQUEEZE_RISK = "SQUEEZE_RISK"
    NONE = "NONE"


class RuleQuality(StrEnum):
    """Rule-quality rubric labels."""

    TESTABLE_AND_OBSERVABLE = "TESTABLE_AND_OBSERVABLE"
    TESTABLE_BUT_NEEDS_DATA = "TESTABLE_BUT_NEEDS_DATA"
    CONTEXT_ONLY = "CONTEXT_ONLY"
    POST_EVENT_COMMENTARY = "POST_EVENT_COMMENTARY"
    UNTESTABLE_OPINION = "UNTESTABLE_OPINION"
    REJECT_LEAKAGE_RISK = "REJECT_LEAKAGE_RISK"


RULE_DEFAULTS: dict[str, dict[str, Any]] = {
    "BASIS_ADJUSTMENT": {
        "summary": "Map CME futures or option strikes to XAU spot using basis.",
        "rule_type": RuleType.MARKET_MAP,
        "action_bias": ActionBias.WATCH_ONLY,
        "observable_inputs": ("futures_price", "spot_price", "option_strike"),
        "required_market_data": ("asof_futures_price", "asof_xau_spot_price"),
    },
    "IV_EXPECTED_MOVE": {
        "summary": "Use implied volatility to frame expected move.",
        "rule_type": RuleType.MARKET_MAP,
        "action_bias": ActionBias.WATCH_ONLY,
        "observable_inputs": ("annualized_iv_percent", "reference_price"),
        "required_market_data": ("asof_iv", "reference_price"),
    },
    "ONE_SD_RANGE": {
        "summary": "Treat the one standard deviation area as range context.",
        "rule_type": RuleType.MARKET_MAP,
        "action_bias": ActionBias.WATCH_ONLY,
        "observable_inputs": ("sigma_position", "one_sd_remaining"),
        "required_market_data": ("asof_iv", "session_open", "spot_price"),
    },
    "TWO_SD_STRESS": {
        "summary": "Treat two standard deviations as a stress zone.",
        "rule_type": RuleType.RISK_RULE,
        "action_bias": ActionBias.WATCH_ONLY,
        "observable_inputs": ("sigma_position", "two_sd_remaining"),
        "required_market_data": ("asof_iv", "spot_price"),
    },
    "THREE_SD_EXTREME": {
        "summary": "Treat three standard deviations as an extreme zone.",
        "rule_type": RuleType.RISK_RULE,
        "action_bias": ActionBias.WATCH_ONLY,
        "observable_inputs": ("sigma_position", "three_sd_remaining"),
        "required_market_data": ("asof_iv", "spot_price"),
    },
    "OI_WALL": {
        "summary": "Use open-interest concentration as wall context.",
        "rule_type": RuleType.MARKET_MAP,
        "action_bias": ActionBias.WATCH_ONLY,
        "observable_inputs": ("spot_adjusted_strike", "total_oi", "wall_score"),
        "required_market_data": ("asof_options_oi", "basis"),
    },
    "OI_CHANGE_FRESHNESS": {
        "summary": "Treat abnormal OI changes as freshness context.",
        "rule_type": RuleType.MARKET_MAP,
        "action_bias": ActionBias.WATCH_ONLY,
        "observable_inputs": ("oi_change", "freshness_weight"),
        "required_market_data": ("asof_oi_change",),
    },
    "INTRADAY_VOLUME": {
        "summary": "Use intraday volume as freshness or participation context.",
        "rule_type": RuleType.MARKET_MAP,
        "action_bias": ActionBias.WATCH_ONLY,
        "observable_inputs": ("intraday_volume", "volume_ratio"),
        "required_market_data": ("asof_volume",),
    },
    "LOW_OI_GAP": {
        "summary": "Low-OI gaps can create continuation risk toward the next wall.",
        "rule_type": RuleType.ENTRY_CONDITION,
        "action_bias": ActionBias.SQUEEZE_RISK,
        "observable_inputs": ("low_oi_gap_to_next_wall", "next_wall_distance"),
        "required_market_data": ("asof_oi_walls", "spot_price"),
    },
    "PIN_RISK": {
        "summary": "Near-expiry high-OI walls can create pin risk.",
        "rule_type": RuleType.RISK_RULE,
        "action_bias": ActionBias.PIN_RISK,
        "observable_inputs": ("largest_near_expiry_wall", "dte", "distance_to_wall"),
        "required_market_data": ("asof_oi_walls", "expiry_calendar"),
    },
    "SQUEEZE_RISK": {
        "summary": "A break through low-OI space can create squeeze risk.",
        "rule_type": RuleType.ENTRY_CONDITION,
        "action_bias": ActionBias.SQUEEZE_RISK,
        "observable_inputs": ("low_oi_gap_to_next_wall", "vol_expansion"),
        "required_market_data": ("asof_oi_walls", "realized_volatility"),
    },
    "OPEN_PRICE_THEORY": {
        "summary": "Use session open side as context.",
        "rule_type": RuleType.MARKET_MAP,
        "action_bias": ActionBias.WATCH_ONLY,
        "observable_inputs": ("session_open", "session_open_side"),
        "required_market_data": ("session_open", "spot_price"),
    },
    "ACCEPTANCE_CLOSE_CONFIRMATION": {
        "summary": "Breakout ideas require close acceptance or hold beyond a level.",
        "rule_type": RuleType.ENTRY_CONDITION,
        "action_bias": ActionBias.BREAKOUT,
        "observable_inputs": ("close_beyond_level", "next_bar_hold", "vol_expansion"),
        "required_market_data": ("confirmed_close", "next_bar_after_signal"),
    },
    "REJECTION_AT_WALL": {
        "summary": "Fade ideas require rejection at a support or resistance wall.",
        "rule_type": RuleType.ENTRY_CONDITION,
        "action_bias": ActionBias.FADE,
        "observable_inputs": ("wall_level", "rejection_bar", "close_back_inside"),
        "required_market_data": ("asof_wall_level", "close_confirmation"),
    },
    "NO_TRADE_DISCIPLINE": {
        "summary": "Avoid low-quality or unclear middle-zone setups.",
        "rule_type": RuleType.NO_TRADE_FILTER,
        "action_bias": ActionBias.NO_TRADE,
        "observable_inputs": ("data_quality", "sigma_zone", "wall_score"),
        "required_market_data": ("asof_features",),
    },
    "STALE_DATA_WARNING": {
        "summary": "Stale data should block research signals.",
        "rule_type": RuleType.RISK_RULE,
        "action_bias": ActionBias.NO_TRADE,
        "observable_inputs": ("data_age", "source_timestamp"),
        "required_market_data": ("source_availability_timestamp",),
    },
    "NEWS_EVENT_WARNING": {
        "summary": "News events can disable or quarantine signals.",
        "rule_type": RuleType.RISK_RULE,
        "action_bias": ActionBias.NO_TRADE,
        "observable_inputs": ("news_calendar", "event_window"),
        "required_market_data": ("known_news_calendar",),
    },
    "IV_RV_VRP": {
        "summary": "Compare implied and realized volatility regime.",
        "rule_type": RuleType.MARKET_MAP,
        "action_bias": ActionBias.WATCH_ONLY,
        "observable_inputs": ("iv", "rv", "vrp"),
        "required_market_data": ("asof_iv", "asof_realized_volatility"),
    },
    "VOLATILITY_SMILE_SKEW": {
        "summary": "Volatility smile or skew can describe options regime.",
        "rule_type": RuleType.MARKET_MAP,
        "action_bias": ActionBias.WATCH_ONLY,
        "observable_inputs": ("strike_iv", "skew", "smile_shape"),
        "required_market_data": ("options_chain_iv_by_strike",),
    },
    "MARKET_MAKER_GAMMA": {
        "summary": "Market-maker gamma is context, not directly observed here.",
        "rule_type": RuleType.MARKET_MAP,
        "action_bias": ActionBias.WATCH_ONLY,
        "observable_inputs": ("gamma_proxy", "dealer_positioning_proxy"),
        "required_market_data": ("options_chain", "gamma_model_or_proxy"),
    },
}

CONDITION_KEYWORDS = (
    "if",
    "when",
    "close",
    "break",
    "reject",
    "accept",
    "hold",
    "above",
    "below",
    "ถ้า",
    "หาก",
    "เมื่อ",
    "ปิดเหนือ",
    "ปิดใต้",
    "ยืนเหนือ",
    "ยืนใต้",
    "ทะลุ",
    "เด้ง",
    "หลุด",
)
INVALIDATION_KEYWORDS = (
    "invalid",
    "invalidation",
    "stop",
    "cancel",
    "fail",
    "close back",
    "ยกเลิก",
    "ผิดทาง",
    "หลุด",
    "กลับ",
    "ไม่เอา",
)
POST_EVENT_KEYWORDS = (
    "already",
    "happened",
    "after the move",
    "yesterday",
    "earlier",
    "ที่ผ่านมา",
    "เมื่อวาน",
    "หลังจาก",
    "เกิดขึ้นแล้ว",
    "ตอนเช้า",
    "ย้อน",
)
LEAKAGE_KEYWORDS = (
    "after session close",
    "after close",
    "after the event",
    "future close",
    "ย้อนหลัง",
    "หลังตลาดปิด",
)
OPINION_KEYWORDS = ("think", "believe", "guess", "น่าจะ", "คิดว่า", "มองว่า", "เดา")


@dataclass(frozen=True)
class LlmTranscriptExtractionResult:
    """Structured extraction frames and report decision."""

    extracted_rules: pl.DataFrame
    quality_audit: pl.DataFrame
    extraction_mode: str
    final_decision: str


def run_llm_transcript_extraction_layer(
    *,
    transcript_timeline: pl.DataFrame,
    output_dir: Path,
    config: ResearchConfig | None = None,
    offline_records_path: str | Path | None = None,
) -> LlmTranscriptExtractionResult:
    """Write optional LLM-style transcript extraction audit outputs."""

    _ = config or ResearchConfig()
    output_dir.mkdir(parents=True, exist_ok=True)
    if offline_records_path is not None:
        records = load_offline_llm_json_records(offline_records_path)
        extraction_mode = "offline_llm_json_records"
    else:
        records = extract_structured_rule_records(transcript_timeline)
        extraction_mode = "offline_deterministic_schema_extractor"
    extracted = records_to_frame(records)
    audit = build_rule_quality_audit(extracted)
    final_decision = final_extraction_decision(audit)

    extracted.write_csv(output_dir / "transcript_llm_extracted_rules.csv")
    audit.write_csv(output_dir / "transcript_rule_quality_audit.csv")
    write_extraction_audit_report(
        output_dir / "transcript_extraction_audit_report.md",
        extracted=extracted,
        audit=audit,
        extraction_mode=extraction_mode,
        final_decision=final_decision,
    )
    return LlmTranscriptExtractionResult(
        extracted_rules=extracted,
        quality_audit=audit,
        extraction_mode=extraction_mode,
        final_decision=final_decision,
    )


def extract_structured_rule_records(transcript_timeline: pl.DataFrame) -> list[dict[str, Any]]:
    """Extract strict JSON-serializable records from transcript timeline rows."""

    if transcript_timeline.is_empty():
        return []
    records = []
    seen: set[tuple[str, str, str]] = set()
    for row in transcript_timeline.to_dicts():
        text = _read_source_text(row.get("source_path"))
        title = str(row.get("title") or "")
        tags = _split_tags(row.get("detected_rule_tags"))
        for tag in tags:
            if tag not in RULE_TAGS:
                continue
            excerpt = find_source_excerpt(text=text, title=title, rule_tag=tag)
            key = (str(row.get("transcript_id") or ""), str(row.get("source_path") or ""), tag)
            if key in seen:
                continue
            seen.add(key)
            records.append(build_rule_record(row, tag, excerpt))
    return records


def build_rule_record(timeline_row: dict[str, Any], rule_tag: str, source_excerpt: str) -> dict[str, Any]:
    """Build one strict JSON-serializable extraction record."""

    defaults = RULE_DEFAULTS[rule_tag]
    rule_type, action_bias = _classify_rule_type_and_bias(rule_tag, source_excerpt)
    quality = classify_rule_quality(
        rule_tag=rule_tag,
        rule_type=rule_type,
        source_excerpt=source_excerpt,
    )
    condition = infer_condition(rule_tag, source_excerpt)
    notes = _record_notes(rule_tag, source_excerpt, quality)
    return {
        "transcript_id": str(timeline_row.get("transcript_id") or ""),
        "transcript_date": timeline_row.get("transcript_date"),
        "availability_timestamp": timeline_row.get("availability_timestamp"),
        "source_excerpt": source_excerpt,
        "normalized_english_summary": defaults["summary"],
        "rule_tag": rule_tag,
        "rule_type": rule_type.value,
        "observable_inputs": "|".join(defaults["observable_inputs"]),
        "required_market_data": "|".join(defaults["required_market_data"]),
        "condition": condition,
        "action_bias": action_bias.value,
        "confidence_score": _record_confidence(timeline_row, source_excerpt),
        "testability_score": _testability_score(quality),
        "leakage_risk_score": _leakage_risk_score(source_excerpt, rule_tag),
        "notes": notes,
    }


def find_source_excerpt(*, text: str, title: str, rule_tag: str, width: int = 360) -> str:
    """Return the original transcript excerpt that triggered a rule tag."""

    haystack = f"{title}\n{text}".strip()
    normalized = _normalize(haystack)
    best_index = None
    for keyword in TAG_KEYWORDS.get(rule_tag, ()):
        index = normalized.find(keyword.lower())
        if index >= 0:
            best_index = index
            break
    if best_index is None:
        return _clean_excerpt(title or haystack[:width], width=width)
    start = max(0, best_index - width // 2)
    end = min(len(haystack), best_index + width // 2)
    return _clean_excerpt(haystack[start:end], width=width)


def classify_rule_quality(
    *,
    rule_tag: str,
    rule_type: RuleType,
    source_excerpt: str,
) -> RuleQuality:
    """Apply rule-quality rubric to one extracted record."""

    text = _normalize(source_excerpt)
    post_event = _contains_any(text, POST_EVENT_KEYWORDS)
    leakage = _contains_any(text, LEAKAGE_KEYWORDS)
    has_condition = _contains_any(text, CONDITION_KEYWORDS)
    has_invalidation = _contains_any(text, INVALIDATION_KEYWORDS)
    has_level = bool(re.search(r"\d{3,5}(?:\.\d+)?", text))
    opinion = _contains_any(text, OPINION_KEYWORDS)

    if leakage:
        return RuleQuality.REJECT_LEAKAGE_RISK
    if post_event:
        return RuleQuality.POST_EVENT_COMMENTARY
    if opinion and not has_condition:
        return RuleQuality.UNTESTABLE_OPINION
    if rule_type in {RuleType.MARKET_MAP, RuleType.RISK_RULE, RuleType.NO_TRADE_FILTER}:
        return RuleQuality.TESTABLE_BUT_NEEDS_DATA if has_condition or has_level else RuleQuality.CONTEXT_ONLY
    if has_condition and has_invalidation:
        return RuleQuality.TESTABLE_AND_OBSERVABLE
    if has_condition or has_level:
        return RuleQuality.TESTABLE_BUT_NEEDS_DATA
    return RuleQuality.CONTEXT_ONLY


def infer_condition(rule_tag: str, source_excerpt: str) -> str:
    """Infer a non-execution research condition from a source excerpt."""

    text = _normalize(source_excerpt)
    if _contains_any(text, POST_EVENT_KEYWORDS):
        return "Post-event description; do not use as pre-event input."
    if _contains_any(text, CONDITION_KEYWORDS):
        return "Condition is present in excerpt; validate with as-of market data before use."
    if re.search(r"\d{3,5}(?:\.\d+)?", text):
        return "Level mentioned, but condition or invalidation may be incomplete."
    return f"Context-only mention of {rule_tag}; no explicit test condition found."


def build_rule_quality_audit(extracted_rules: pl.DataFrame) -> pl.DataFrame:
    """Create quality audit rows for extracted rule records."""

    if extracted_rules.is_empty():
        return _empty_quality_audit()
    rows = []
    for row in extracted_rules.to_dicts():
        rule_type = RuleType(str(row["rule_type"]))
        quality = classify_rule_quality(
            rule_tag=str(row["rule_tag"]),
            rule_type=rule_type,
            source_excerpt=str(row.get("source_excerpt") or ""),
        )
        notes = str(row.get("notes") or "")
        rows.append(
            {
                "transcript_id": row.get("transcript_id"),
                "rule_tag": row.get("rule_tag"),
                "rule_type": row.get("rule_type"),
                "action_bias": row.get("action_bias"),
                "rule_quality": quality.value,
                "confidence_score": row.get("confidence_score"),
                "testability_score": row.get("testability_score"),
                "leakage_risk_score": row.get("leakage_risk_score"),
                "has_source_excerpt": bool(row.get("source_excerpt")),
                "has_condition": "Condition is present" in str(row.get("condition") or ""),
                "has_invalidation": _contains_any(_normalize(str(row.get("source_excerpt") or "")), INVALIDATION_KEYWORDS),
                "incomplete_rule": "incomplete" in notes,
                "quality_reason": _quality_reason(quality, notes),
            }
        )
    return _rows_frame(rows)


def load_offline_llm_json_records(path: str | Path) -> list[dict[str, Any]]:
    """Load externally generated JSON or JSONL records and validate schema."""

    source = Path(path)
    text = source.read_text(encoding="utf-8-sig")
    if source.suffix.lower() == ".jsonl":
        raw = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        parsed = json.loads(text)
        raw = parsed if isinstance(parsed, list) else [parsed]
    return [validate_rule_record(record) for record in raw]


def validate_rule_record(record: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize one externally supplied JSON rule record."""

    required = {
        "transcript_id",
        "transcript_date",
        "availability_timestamp",
        "source_excerpt",
        "normalized_english_summary",
        "rule_tag",
        "rule_type",
        "observable_inputs",
        "required_market_data",
        "condition",
        "action_bias",
        "confidence_score",
        "testability_score",
        "leakage_risk_score",
        "notes",
    }
    missing = sorted(required - set(record))
    if missing:
        raise ValueError(f"missing rule record fields: {', '.join(missing)}")
    if record["rule_tag"] not in RULE_TAGS:
        raise ValueError(f"unsupported rule_tag: {record['rule_tag']}")
    RuleType(str(record["rule_type"]))
    ActionBias(str(record["action_bias"]))
    normalized = dict(record)
    for column in ("confidence_score", "testability_score", "leakage_risk_score"):
        normalized[column] = float(normalized[column])
    return normalized


def records_to_frame(records: list[dict[str, Any]]) -> pl.DataFrame:
    """Convert JSON records to the extraction frame."""

    if not records:
        return _empty_extracted_rules()
    return _rows_frame([validate_rule_record(record) for record in records])


def final_extraction_decision(audit: pl.DataFrame) -> str:
    """Return a conservative audit decision for the extraction layer."""

    if audit.is_empty():
        return "LLM_EXTRACTION_EMPTY"
    rejected = audit.filter(pl.col("rule_quality") == RuleQuality.REJECT_LEAKAGE_RISK.value).height
    testable = audit.filter(pl.col("rule_quality") == RuleQuality.TESTABLE_AND_OBSERVABLE.value).height
    needs_data = audit.filter(pl.col("rule_quality") == RuleQuality.TESTABLE_BUT_NEEDS_DATA.value).height
    if rejected:
        return "LLM_EXTRACTION_REQUIRES_REVIEW"
    if testable:
        return "LLM_EXTRACTION_HAS_TESTABLE_RULES"
    if needs_data:
        return "LLM_EXTRACTION_CONTEXT_NEEDS_DATA"
    return "LLM_EXTRACTION_CONTEXT_ONLY"


def write_extraction_audit_report(
    path: Path,
    *,
    extracted: pl.DataFrame,
    audit: pl.DataFrame,
    extraction_mode: str,
    final_decision: str,
) -> None:
    """Write Markdown audit of keyword vs optional structured extraction."""

    quality_counts = (
        audit.group_by("rule_quality").len().sort("rule_quality")
        if not audit.is_empty()
        else audit
    )
    testable = (
        audit.filter(pl.col("rule_quality").is_in([
            RuleQuality.TESTABLE_AND_OBSERVABLE.value,
            RuleQuality.TESTABLE_BUT_NEEDS_DATA.value,
        ]))
        if not audit.is_empty()
        else audit
    )
    rejected = (
        audit.filter(pl.col("rule_quality") == RuleQuality.REJECT_LEAKAGE_RISK.value)
        if not audit.is_empty()
        else audit
    )
    context = (
        audit.filter(pl.col("rule_quality").is_in([
            RuleQuality.CONTEXT_ONLY.value,
            RuleQuality.POST_EVENT_COMMENTARY.value,
            RuleQuality.UNTESTABLE_OPINION.value,
        ]))
        if not audit.is_empty()
        else audit
    )
    lines = [
        "# Transcript Extraction Audit",
        "",
        "Research-only extraction audit. Extracted records are structured features, not trade signals.",
        "",
        f"- Extraction mode: `{extraction_mode}`",
        f"- Final decision: `{final_decision}`",
        f"- Extracted rule records: {extracted.height}",
        "",
        "## Architecture Audit",
        "",
        "- Current timeline extraction is deterministic keyword/rule based, not semantic LLM extraction.",
        "- The optional LLM path accepts JSON/JSONL records only and validates the schema before use.",
        "- Source excerpts are stored with each extracted record for auditability.",
        "- Confidence scores are heuristic and must not be treated as model probabilities.",
        "",
        "## Guru Rule Testability",
        "",
        _frame_markdown(quality_counts),
        "",
        "## Which Guru Rules Are Testable",
        "",
        _frame_markdown(testable),
        "",
        "## Which Guru Rules Are Context Only",
        "",
        _frame_markdown(context),
        "",
        "## Which Guru Rules Are Rejected",
        "",
        _frame_markdown(rejected),
        "",
        "## Keyword vs LLM Extraction Risk",
        "",
        "- Thai ASR noise can split, omit, or distort key words such as IV/RV/VRP, skew, gamma, acceptance, and rejection.",
        "- Simple keyword matching can over-detect broad terms such as OI, volume, wait, open, news, and gamma.",
        "- Structured extraction separates rule type, condition, action bias, quality, and leakage risk, but it still needs validation.",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _classify_rule_type_and_bias(rule_tag: str, excerpt: str) -> tuple[RuleType, ActionBias]:
    text = _normalize(excerpt)
    if _contains_any(text, POST_EVENT_KEYWORDS):
        return RuleType.POST_EVENT_COMMENTARY, ActionBias.NONE
    if _contains_any(text, OPINION_KEYWORDS) and not _contains_any(text, CONDITION_KEYWORDS):
        return RuleType.UNTESTABLE_OPINION, ActionBias.NONE
    defaults = RULE_DEFAULTS[rule_tag]
    return defaults["rule_type"], defaults["action_bias"]


def _record_confidence(timeline_row: dict[str, Any], source_excerpt: str) -> float:
    base = _float(timeline_row.get("confidence_score"), default=0.35)
    excerpt_bonus = 0.10 if source_excerpt else -0.10
    condition_bonus = 0.05 if _contains_any(_normalize(source_excerpt), CONDITION_KEYWORDS) else 0.0
    return round(max(0.0, min(1.0, base * 0.85 + excerpt_bonus + condition_bonus)), 4)


def _testability_score(quality: RuleQuality) -> float:
    return {
        RuleQuality.TESTABLE_AND_OBSERVABLE: 0.90,
        RuleQuality.TESTABLE_BUT_NEEDS_DATA: 0.65,
        RuleQuality.CONTEXT_ONLY: 0.35,
        RuleQuality.POST_EVENT_COMMENTARY: 0.15,
        RuleQuality.UNTESTABLE_OPINION: 0.10,
        RuleQuality.REJECT_LEAKAGE_RISK: 0.0,
    }[quality]


def _leakage_risk_score(source_excerpt: str, rule_tag: str) -> float:
    text = _normalize(source_excerpt)
    if _contains_any(text, LEAKAGE_KEYWORDS):
        return 0.95
    if _contains_any(text, POST_EVENT_KEYWORDS):
        return 0.80
    if rule_tag == "ACCEPTANCE_CLOSE_CONFIRMATION":
        return 0.45
    if "next bar" in text or "แท่งถัด" in text:
        return 0.55
    return 0.15


def _record_notes(rule_tag: str, source_excerpt: str, quality: RuleQuality) -> str:
    text = _normalize(source_excerpt)
    notes = ["structured_research_feature_only", "no_trading_decision"]
    if quality == RuleQuality.POST_EVENT_COMMENTARY:
        notes.append("post_event_commentary_not_pre_event_input")
    if quality == RuleQuality.REJECT_LEAKAGE_RISK:
        notes.append("reject_required_data_not_available_before_signal")
    if RULE_DEFAULTS[rule_tag]["rule_type"] == RuleType.ENTRY_CONDITION and not _contains_any(text, INVALIDATION_KEYWORDS):
        notes.append("incomplete_rule_missing_explicit_invalidation")
    if not _contains_any(text, CONDITION_KEYWORDS):
        notes.append("condition_not_explicit_in_excerpt")
    return "; ".join(notes)


def _quality_reason(quality: RuleQuality, notes: str) -> str:
    if quality == RuleQuality.TESTABLE_AND_OBSERVABLE:
        return "condition, invalidation, and observable data are present"
    if quality == RuleQuality.TESTABLE_BUT_NEEDS_DATA:
        return f"testable context but extra data or completeness needed; {notes}"
    if quality == RuleQuality.POST_EVENT_COMMENTARY:
        return "statement appears to describe an event after it happened"
    if quality == RuleQuality.REJECT_LEAKAGE_RISK:
        return "required information appears unavailable before signal timestamp"
    if quality == RuleQuality.UNTESTABLE_OPINION:
        return "opinion or forecast without observable condition"
    return f"context only; {notes}"


def _read_source_text(path_value: Any) -> str:
    if not path_value:
        return ""
    path = Path(str(path_value))
    if not path.exists() or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8-sig", errors="replace")


def _split_tags(value: Any) -> list[str]:
    if value is None:
        return []
    return [tag for tag in str(value).split("|") if tag]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower())


def _clean_excerpt(text: str, *, width: int) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= width:
        return cleaned
    return cleaned[: width - 3].rstrip() + "..."


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword.lower() in text for keyword in keywords)


def _float(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _rows_frame(rows: list[dict[str, Any]]) -> pl.DataFrame:
    return pl.DataFrame(rows, infer_schema_length=None)


def _empty_extracted_rules() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "transcript_id": pl.String,
            "transcript_date": pl.String,
            "availability_timestamp": pl.Datetime(time_zone="UTC"),
            "source_excerpt": pl.String,
            "normalized_english_summary": pl.String,
            "rule_tag": pl.String,
            "rule_type": pl.String,
            "observable_inputs": pl.String,
            "required_market_data": pl.String,
            "condition": pl.String,
            "action_bias": pl.String,
            "confidence_score": pl.Float64,
            "testability_score": pl.Float64,
            "leakage_risk_score": pl.Float64,
            "notes": pl.String,
        }
    )


def _empty_quality_audit() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "transcript_id": pl.String,
            "rule_tag": pl.String,
            "rule_type": pl.String,
            "action_bias": pl.String,
            "rule_quality": pl.String,
            "confidence_score": pl.Float64,
            "testability_score": pl.Float64,
            "leakage_risk_score": pl.Float64,
            "has_source_excerpt": pl.Boolean,
            "has_condition": pl.Boolean,
            "has_invalidation": pl.Boolean,
            "incomplete_rule": pl.Boolean,
            "quality_reason": pl.String,
        }
    )


def _frame_markdown(frame: pl.DataFrame) -> str:
    if frame.is_empty():
        return "_No rows._"
    rows = ["| " + " | ".join(frame.columns) + " |", "|" + "|".join(["---"] * len(frame.columns)) + "|"]
    for raw in frame.head(25).to_dicts():
        rows.append("| " + " | ".join(str(raw.get(column, "")) for column in frame.columns) + " |")
    return "\n".join(rows)
