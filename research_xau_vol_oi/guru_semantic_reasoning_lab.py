"""Full-corpus semantic guru reasoning and SD/grid rule test lab.

The lab consumes the structured transcript-rule corpus plus raw source excerpts
where available, distills repeated reasoning claims, and runs deterministic
Dukascopy/CME pilot tests. Guru text is evidence for hypotheses only, not a
direct signal.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import polars as pl


SEMANTIC_CATEGORIES = (
    "CME_WALL",
    "SD_GRID",
    "MAGNET_TARGET",
    "REJECTION",
    "ACCEPTANCE",
    "PIN_RISK",
    "LOW_OI_GAP",
    "PUT_CALL_WALL",
    "NO_TRADE",
    "OPEN_PRICE",
    "RISK_MANAGEMENT",
    "POST_EVENT_REVIEW",
    "UNTESTABLE_COMMENT",
)
CLAIM_TYPES = (
    "WALL_AS_MAGNET",
    "WALL_AS_TARGET_TP",
    "WALL_AS_REJECTION",
    "WALL_AS_ACCEPTANCE_BREAK",
    "MAX_OI_PIN",
    "LOW_OI_GAP_SQUEEZE",
    "CALL_WALL_RESISTANCE",
    "PUT_WALL_SUPPORT",
    "PUT_CALL_IMBALANCE_BIAS",
    "SD_GRID_ENTRY",
    "SD_GRID_NO_TRADE",
    "THREE_SD_EXTREME_ENTRY",
    "THREE_POINT_FIVE_SD_STOP",
    "TWENTY_FIVE_DOLLAR_GRID",
    "IV_EXPECTED_MOVE",
    "REALIZED_RANGE_EXPECTATION",
    "OPEN_PRICE_REFERENCE",
    "NO_TRADE_MIDDLE_RANGE",
    "ACCEPTANCE_CONFIRMATION",
    "REJECTION_CONFIRMATION",
    "RISK_MANAGEMENT",
    "POST_EVENT_COMMENTARY",
    "UNTESTABLE",
)
FINAL_RECOMMENDATIONS = (
    "GURU_SEMANTIC_MAP_READY",
    "SD_GRID_TEST_READY",
    "WALL_MAGNET_PILOT_ONLY",
    "CME_ONLY_RULES_READY_FOR_WATCHLIST",
    "NEED_MORE_CME_DATA",
    "NOT_READY_FOR_MONEY",
)
SD_GRID_RULE_IDS = (
    "ENTRY_AT_1SD_FADE",
    "ENTRY_AT_2SD_FADE",
    "ENTRY_AT_3SD_FADE",
    "ENTRY_AT_3SD_WITH_3_5SD_STOP",
    "TP_AT_1SD",
    "TP_AT_MIDPOINT",
    "TP_AT_CME_WALL",
    "TP_AT_MAX_OI",
    "NO_TRADE_INSIDE_MIDDLE_RANGE",
    "ACCEPTANCE_BEYOND_3SD_CONTINUATION",
    "REJECTION_BACK_INSIDE_3SD_FADE",
    "$25_GRID_ROTATION",
    "$50_GRID_ROTATION",
)
TIMEFRAMES = ("15m", "30m", "1h", "4h", "1d")
RESEARCH_WARNING = (
    "Research-only full-corpus semantic reasoning lab. Guru text creates "
    "testable hypotheses only and is never a direct signal."
)
PILOT_WARNING = "CME wall and IV behavior remains pilot-only until more CME overlap days exist."
MIN_SAMPLE = 30
FORBIDDEN_REPORT_PHRASES = (
    " buy ",
    " sell ",
    "profitable",
    "profitability",
    "guaranteed edge",
    "predicts price",
    "safe to trade",
    "live ready",
    "paper ready",
    "validated money edge",
)


@dataclass(frozen=True)
class GuruSemanticReasoningLabResult:
    """Frames and labels emitted by the semantic reasoning lab."""

    segments: pl.DataFrame
    claims: pl.DataFrame
    frequency_map: pl.DataFrame
    sd_grid_rule_family: pl.DataFrame
    sd_grid_backtest: pl.DataFrame
    cme_wall_magnet_tp: pl.DataFrame
    guru_to_data_mapping: pl.DataFrame
    cme_only_rule_translation: pl.DataFrame
    final_recommendation: str
    paths: dict[str, Path]


def run_guru_semantic_reasoning_lab(
    *,
    output_dir: str | Path = "outputs",
    write_outputs: bool = True,
) -> GuruSemanticReasoningLabResult:
    """Run the full-corpus semantic reasoning lab."""

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    paths = _output_paths(output_root)
    inputs = _load_inputs(paths)
    segments = build_transcript_semantic_segments(inputs=inputs)
    claims = build_semantic_claims(segments=segments, inputs=inputs)
    frequency = build_reasoning_frequency_map(claims)
    rule_family = build_sd_grid_rule_family(claims)
    sd_grid = build_dukascopy_sd_grid_backtest(inputs=inputs, rule_family=rule_family)
    cme_wall = build_cme_wall_magnet_tp_backtest(inputs=inputs)
    mapping = build_guru_to_data_mapping_report(
        claims=claims,
        sd_grid_backtest=sd_grid,
        cme_wall_magnet_tp=cme_wall,
        inputs=inputs,
    )
    translation = build_cme_only_rule_translation_from_guru(claims=claims, cme_wall_magnet_tp=cme_wall)
    final = choose_final_recommendation(
        claims=claims,
        sd_grid_backtest=sd_grid,
        cme_wall_magnet_tp=cme_wall,
        translation=translation,
    )
    result = GuruSemanticReasoningLabResult(
        segments=segments,
        claims=claims,
        frequency_map=frequency,
        sd_grid_rule_family=rule_family,
        sd_grid_backtest=sd_grid,
        cme_wall_magnet_tp=cme_wall,
        guru_to_data_mapping=mapping,
        cme_only_rule_translation=translation,
        final_recommendation=final,
        paths=paths,
    )
    if write_outputs:
        write_guru_semantic_reasoning_lab_outputs(result)
    return result


def build_transcript_semantic_segments(*, inputs: dict[str, Any]) -> pl.DataFrame:
    """Build reasoning segments from structured transcript rules and excerpts."""

    rule_rows = _frame_input(inputs, "transcript_rules")
    clean = _frame_input(inputs, "clean_transcripts")
    debug = _frame_input(inputs, "same_day_debug")
    source_rows: list[dict[str, Any]] = []
    if not rule_rows.is_empty():
        for row in rule_rows.to_dicts():
            source_rows.append(_segment_from_rule_row(row, len(source_rows) + 1))
    if not debug.is_empty():
        for row in debug.to_dicts():
            source_rows.append(_segment_from_debug_row(row, len(source_rows) + 1))
    if not source_rows and not clean.is_empty():
        for row in clean.to_dicts():
            source_rows.append(_segment_from_clean_row(row, len(source_rows) + 1))
    return _frame(source_rows, _segment_schema())


def build_semantic_claims(*, segments: pl.DataFrame, inputs: dict[str, Any]) -> pl.DataFrame:
    """Extract testable semantic claims from evidence-backed segments."""

    rows: list[dict[str, Any]] = []
    for segment in segments.to_dicts():
        excerpt = _text(segment.get("source_excerpt"))
        if not excerpt:
            continue
        for claim_type in _claim_types_for_segment(segment):
            rows.append(_claim_from_segment(segment, claim_type, len(rows) + 1))
    rows.extend(_fallback_claims_from_hypotheses(_frame_input(inputs, "guru_wall_hypotheses"), len(rows)))
    return _frame(_dedupe_claim_rows(rows), _claim_schema())


def build_reasoning_frequency_map(claims: pl.DataFrame) -> pl.DataFrame:
    """Summarize repeated reasoning patterns by claim type."""

    rows = []
    for claim_type in CLAIM_TYPES:
        subset = claims.filter(pl.col("claim_type") == claim_type) if not claims.is_empty() else pl.DataFrame()
        dates = sorted(_date_text(row.get("transcript_date")) for row in subset.to_dicts() if _date_text(row.get("transcript_date")))
        transcripts = {
            _text(row.get("transcript_id"))
            for row in subset.to_dicts()
            if _text(row.get("transcript_id"))
        }
        rows.append(
            {
                "claim_type": claim_type,
                "claim_count": subset.height,
                "transcript_count": len(transcripts),
                "first_seen_date": dates[0] if dates else "",
                "last_seen_date": dates[-1] if dates else "",
                "representative_excerpts": _representative_excerpts(subset),
                "confidence_distribution": _distribution(subset, "confidence"),
                "testability_distribution": _distribution(subset, "testability"),
                "recommended_priority": _priority(subset.height, len(transcripts), claim_type),
            }
        )
    return _frame(rows, _frequency_schema())


def build_sd_grid_rule_family(claims: pl.DataFrame) -> pl.DataFrame:
    """Create testable SD/grid rule-family definitions."""

    rows = []
    for rule_id in SD_GRID_RULE_IDS:
        template = _sd_grid_rule_template(rule_id)
        rows.append(
            {
                **template,
                "rule_id": rule_id,
                "guru_claim_source": _claim_source_for_rule(claims, rule_id),
            }
        )
    return _frame(rows, _rule_family_schema())


def build_dukascopy_sd_grid_backtest(
    *,
    inputs: dict[str, Any],
    rule_family: pl.DataFrame,
) -> pl.DataFrame:
    """Run fixed SD/grid comparison on Dukascopy frames."""

    rows = []
    for timeframe in TIMEFRAMES:
        frame = _price_frame(inputs, timeframe)
        if frame.is_empty():
            for rule_id in SD_GRID_RULE_IDS:
                rows.append(_empty_backtest_row(rule_id, timeframe))
            continue
        daily_ranges = _daily_ranges(_price_frame(inputs, "1d"))
        sd_proxy = _range_proxy(daily_ranges)
        for rule_id in SD_GRID_RULE_IDS:
            rows.append(_sd_grid_backtest_row(rule_id, timeframe, frame, sd_proxy))
    return _frame(rows, _sd_backtest_schema())


def build_cme_wall_magnet_tp_backtest(*, inputs: dict[str, Any]) -> pl.DataFrame:
    """Run the CME wall magnet/TP pilot on current overlap only."""

    wall_map = _wall_map(inputs)
    price = _price_frame(inputs, "1h")
    if wall_map.is_empty() or price.is_empty():
        return _frame([], _cme_wall_tp_schema())
    rows = []
    for case_type in (
        "NEAREST_WALL",
        "STRONGEST_WALL",
        "MAX_OI_WALL",
        "PUT_WALL",
        "CALL_WALL",
        "TOTAL_OI_WALL",
        "REJECTION_AFTER_FAILED_ACCEPTANCE",
        "CONTINUATION_AFTER_ACCEPTANCE",
    ):
        events = _cme_case_events(case_type, wall_map=wall_map, price=price)
        rows.append(_cme_case_summary(case_type, events))
    return _frame(rows, _cme_wall_tp_schema())


def build_guru_to_data_mapping_report(
    *,
    claims: pl.DataFrame,
    sd_grid_backtest: pl.DataFrame,
    cme_wall_magnet_tp: pl.DataFrame,
    inputs: dict[str, Any],
) -> pl.DataFrame:
    """Map each semantic claim type to available data and current results."""

    rows = []
    for claim_type in CLAIM_TYPES:
        needed = _data_needed_for_claim(claim_type)
        available = _data_available_for_claim(claim_type, inputs)
        can_test = _can_test_now(claim_type, available)
        rows.append(
            {
                "claim_type": claim_type,
                "data_needed": needed,
                "data_available_now": ";".join(available) if available else "MISSING",
                "can_test_now": can_test,
                "test_result_available": _test_result_available(claim_type, sd_grid_backtest, cme_wall_magnet_tp),
                "current_result": _current_result_for_claim(claim_type, sd_grid_backtest, cme_wall_magnet_tp),
                "next_data_needed": _next_data_needed(claim_type, available),
            }
        )
    return _frame(rows, _mapping_schema())


def build_cme_only_rule_translation_from_guru(
    *,
    claims: pl.DataFrame,
    cme_wall_magnet_tp: pl.DataFrame,
) -> pl.DataFrame:
    """Translate semantic claims into watchlist-only CME rule candidates."""

    rows = []
    for template in _cme_translation_templates():
        rows.append(
            {
                **template,
                "guru_claim_source": _claim_source_for_translation(claims, template["rule_id"]),
                "current_evidence": _translation_evidence(template["rule_id"], cme_wall_magnet_tp),
                "validation_status": "NEED_MORE_CME_DATA"
                if template["rule_id"] not in {"3SD_EXTREME_WATCH", "3_5SD_INVALIDATION_REFERENCE"}
                else "TESTABLE_WITH_DUKASCOPY",
            }
        )
    return _frame(rows, _translation_schema())


def choose_final_recommendation(
    *,
    claims: pl.DataFrame,
    sd_grid_backtest: pl.DataFrame,
    cme_wall_magnet_tp: pl.DataFrame,
    translation: pl.DataFrame,
) -> str:
    """Choose a conservative recommendation label."""

    if claims.is_empty():
        return "NEED_MORE_CME_DATA"
    if _has_sd_grid_tests(sd_grid_backtest) and not translation.is_empty():
        return "CME_ONLY_RULES_READY_FOR_WATCHLIST"
    if _has_sd_grid_tests(sd_grid_backtest):
        return "SD_GRID_TEST_READY"
    if _cme_small_sample(cme_wall_magnet_tp):
        return "WALL_MAGNET_PILOT_ONLY"
    return "GURU_SEMANTIC_MAP_READY"


def write_guru_semantic_reasoning_lab_outputs(result: GuruSemanticReasoningLabResult) -> None:
    """Write CSV, JSONL, and Markdown artifacts."""

    result.segments.write_csv(result.paths["segments_csv"])
    result.paths["segments_md"].write_text(
        _safe_report_text(_artifact_markdown("Guru Transcript Semantic Segments", result.segments)),
        encoding="utf-8",
    )
    result.claims.write_csv(result.paths["claims_csv"])
    result.paths["claims_jsonl"].write_text(_claims_jsonl(result.claims), encoding="utf-8")
    result.paths["claims_md"].write_text(
        _safe_report_text(_artifact_markdown("Guru Semantic Claims", result.claims)),
        encoding="utf-8",
    )
    for key, frame in {
        "frequency": result.frequency_map,
        "rule_family": result.sd_grid_rule_family,
        "sd_backtest": result.sd_grid_backtest,
        "cme_wall_tp": result.cme_wall_magnet_tp,
        "mapping": result.guru_to_data_mapping,
        "translation": result.cme_only_rule_translation,
    }.items():
        frame.write_csv(result.paths[f"{key}_csv"])
        result.paths[f"{key}_md"].write_text(
            _safe_report_text(_artifact_markdown(_artifact_title(key), frame)),
            encoding="utf-8",
        )


def guru_semantic_reasoning_report_lines(result: GuruSemanticReasoningLabResult | None) -> list[str]:
    """Return research_report.md sections for this lab."""

    if result is None:
        return [
            "## Full-Corpus Guru Semantic Reasoning",
            "",
            "Full-corpus semantic reasoning lab was not run.",
        ]
    return [
        "## Full-Corpus Guru Semantic Reasoning",
        "",
        RESEARCH_WARNING,
        "",
        f"- Final recommendation: `{result.final_recommendation}`",
        f"- Semantic segments: {result.segments.height}",
        f"- Semantic claims: {result.claims.height}",
        "- Guardrail: `NOT_READY_FOR_MONEY`",
        "",
        "## Repeated Guru Claims",
        "",
        _frame_markdown(result.frequency_map.sort("claim_count", descending=True).head(15)),
        "",
        "## SD/Grid Rule Family",
        "",
        _frame_markdown(result.sd_grid_rule_family),
        "",
        "## Dukascopy SD/Grid Backtest",
        "",
        _frame_markdown(result.sd_grid_backtest.head(25)),
        "",
        "## CME Wall Magnet/TP Test",
        "",
        _frame_markdown(result.cme_wall_magnet_tp),
        "",
        "## Guru-to-Data Mapping",
        "",
        _frame_markdown(result.guru_to_data_mapping),
        "",
        "## CME-only Rule Translation",
        "",
        _frame_markdown(result.cme_only_rule_translation),
        "",
        "## What We Can Use Now",
        "",
        "- Full-corpus semantic map and claim frequency are ready for manual research review.",
        "- SD/grid and ATR range behavior can be tested broadly with Dukascopy.",
        "- CME-only translations can be used as watchlist labels only.",
        "",
        "## What Needs More CME Data",
        "",
        "- Wall magnet/TP behavior, put/call wall behavior, max-OI pin, and IV expected-move claims need more CME overlap days.",
    ]


def report_text_is_safe(text: str) -> bool:
    """Return true when generated reports avoid restricted phrases and local paths."""

    lowered = f" {text.lower()} "
    return not any(phrase in lowered for phrase in FORBIDDEN_REPORT_PHRASES) and "C:\\" not in text


def _segment_from_rule_row(row: dict[str, Any], index: int) -> dict[str, Any]:
    excerpt = _safe_cell(row.get("source_excerpt"))
    context = _safe_cell(
        " | ".join(
            value
            for value in (
                _text(row.get("normalized_english_summary")),
                _text(row.get("condition")),
                _text(row.get("observable_inputs")),
                _text(row.get("required_market_data")),
                _text(row.get("notes")),
            )
            if value
        )
    )
    category, confidence = _semantic_category(row=row, excerpt=excerpt, context=context)
    return {
        "segment_id": f"semseg_{index:06d}",
        "transcript_id": _text(row.get("transcript_id")),
        "transcript_date": _date_text(row.get("transcript_date")),
        "transcript_time": _time_text(row.get("availability_timestamp")),
        "source_excerpt": excerpt,
        "surrounding_context_excerpt": context,
        "language_detected": _language_detected(excerpt),
        "semantic_category": category,
        "confidence": confidence,
        "needs_human_review": _needs_human_review(excerpt, context, confidence),
        "rule_tag": _text(row.get("rule_tag")),
    }


def _segment_from_debug_row(row: dict[str, Any], index: int) -> dict[str, Any]:
    excerpt = _safe_cell(row.get("source_excerpt_sample"))
    context = _safe_cell(
        " | ".join(
            value
            for value in (
                _text(row.get("rule_keyword_hits")),
                _text(row.get("playbook_logic_matches")),
                _text(row.get("why_no_context_or_filter")),
            )
            if value
        )
    )
    category, confidence = _semantic_category(row=row, excerpt=excerpt, context=context)
    return {
        "segment_id": f"semseg_{index:06d}",
        "transcript_id": _text(row.get("clean_transcript_id")),
        "transcript_date": _date_text(row.get("transcript_date")),
        "transcript_time": _text(row.get("transcript_time")),
        "source_excerpt": excerpt,
        "surrounding_context_excerpt": context,
        "language_detected": _language_detected(excerpt),
        "semantic_category": category,
        "confidence": confidence,
        "needs_human_review": True,
        "rule_tag": _text(row.get("playbook_logic_matches")),
    }


def _segment_from_clean_row(row: dict[str, Any], index: int) -> dict[str, Any]:
    context = _safe_cell(_text(row.get("keep_reason")) or _text(row.get("collapse_reason")))
    return {
        "segment_id": f"semseg_{index:06d}",
        "transcript_id": _text(row.get("clean_transcript_id")),
        "transcript_date": _date_text(row.get("transcript_date")),
        "transcript_time": _text(row.get("transcript_time")),
        "source_excerpt": "",
        "surrounding_context_excerpt": context,
        "language_detected": "UNKNOWN",
        "semantic_category": "UNTESTABLE_COMMENT",
        "confidence": "LOW",
        "needs_human_review": True,
        "rule_tag": "",
    }


def _semantic_category(*, row: dict[str, Any], excerpt: str, context: str) -> tuple[str, str]:
    tag = _text(row.get("rule_tag")).upper()
    combined = f"{tag} {_text(row.get('normalized_english_summary'))} {_text(row.get('condition'))} {context}".upper()
    if "OI_WALL" in tag or "BASIS" in tag:
        return "CME_WALL", "HIGH"
    if "PIN_RISK" in tag:
        return "PIN_RISK", "HIGH"
    if "LOW_OI_GAP" in tag or "SQUEEZE" in tag:
        return "LOW_OI_GAP", "HIGH"
    if "REJECTION" in tag:
        return "REJECTION", "HIGH"
    if "ACCEPTANCE" in tag:
        return "ACCEPTANCE", "HIGH"
    if "NO_TRADE" in tag:
        return "NO_TRADE", "HIGH"
    if "OPEN_PRICE" in tag:
        return "OPEN_PRICE", "HIGH"
    if any(token in tag for token in ("ONE_SD", "TWO_SD", "THREE_SD", "IV_EXPECTED", "IV_RV")):
        return "SD_GRID", "HIGH"
    if "CALL" in combined or "PUT" in combined or "SKEW" in combined:
        return "PUT_CALL_WALL", "MEDIUM"
    if "TP" in combined or "TARGET" in combined or "MAGNET" in combined or "WALL" in combined:
        return "MAGNET_TARGET", "MEDIUM"
    if "STOP" in combined or "SL" in combined or "RISK" in combined or "RR" in combined:
        return "RISK_MANAGEMENT", "MEDIUM"
    if "POST" in combined or "REVIEW" in combined:
        return "POST_EVENT_REVIEW", "MEDIUM"
    return ("UNTESTABLE_COMMENT", "LOW") if excerpt or context else ("UNTESTABLE_COMMENT", "LOW")


def _needs_human_review(excerpt: str, context: str, confidence: str) -> bool:
    return confidence == "LOW" or len(excerpt) < 80 or len(context) < 20


def _claim_types_for_segment(segment: dict[str, Any]) -> list[str]:
    tag = _text(segment.get("rule_tag")).upper()
    context = f"{_text(segment.get('source_excerpt'))} {_text(segment.get('surrounding_context_excerpt'))}".upper()
    category = _text(segment.get("semantic_category"))
    out: list[str] = []
    if "OI_WALL" in tag or category == "CME_WALL":
        out.extend(["WALL_AS_MAGNET"])
        if "TP" in context or "TARGET" in context or "TAKE" in context:
            out.append("WALL_AS_TARGET_TP")
    if "REJECTION" in tag or category == "REJECTION":
        out.extend(["WALL_AS_REJECTION", "REJECTION_CONFIRMATION"])
    if "ACCEPTANCE" in tag or category == "ACCEPTANCE":
        out.extend(["WALL_AS_ACCEPTANCE_BREAK", "ACCEPTANCE_CONFIRMATION"])
    if "PIN_RISK" in tag or category == "PIN_RISK":
        out.append("MAX_OI_PIN")
    if "LOW_OI_GAP" in tag or "SQUEEZE" in tag or category == "LOW_OI_GAP":
        out.append("LOW_OI_GAP_SQUEEZE")
    if "VOLATILITY_SMILE" in tag or "SKEW" in tag:
        out.append("PUT_CALL_IMBALANCE_BIAS")
    if "CALL" in context and "WALL" in context:
        out.append("CALL_WALL_RESISTANCE")
    if "PUT" in context and "WALL" in context:
        out.append("PUT_WALL_SUPPORT")
    if "ONE_SD" in tag or "TWO_SD" in tag or "THREE_SD" in tag or category == "SD_GRID":
        out.append("SD_GRID_ENTRY")
    if "NO_TRADE" in tag and ("SD" in context or "RANGE" in context):
        out.append("SD_GRID_NO_TRADE")
    if "THREE_SD" in tag or "3 SD" in context or "3SD" in context:
        out.append("THREE_SD_EXTREME_ENTRY")
    if "3.5" in context or "3_5" in context or "3-5" in context:
        out.append("THREE_POINT_FIVE_SD_STOP")
    if "$25" in context or " 25 " in f" {context} " or "TWENTY FIVE" in context:
        out.append("TWENTY_FIVE_DOLLAR_GRID")
    if "IV_EXPECTED" in tag or "EXPECTED MOVE" in context:
        out.append("IV_EXPECTED_MOVE")
    if "IV_RV" in tag or "REALIZED" in context or "ATR" in context:
        out.append("REALIZED_RANGE_EXPECTATION")
    if "OPEN_PRICE" in tag or category == "OPEN_PRICE":
        out.append("OPEN_PRICE_REFERENCE")
    if "NO_TRADE" in tag:
        out.append("NO_TRADE_MIDDLE_RANGE")
    if category == "RISK_MANAGEMENT":
        out.append("RISK_MANAGEMENT")
    if category == "POST_EVENT_REVIEW":
        out.append("POST_EVENT_COMMENTARY")
    if not out:
        out.append("UNTESTABLE")
    return sorted(set(out), key=CLAIM_TYPES.index)


def _claim_from_segment(segment: dict[str, Any], claim_type: str, index: int) -> dict[str, Any]:
    template = _claim_template(claim_type)
    confidence = _claim_confidence(segment, claim_type)
    return {
        "claim_id": f"gclaim_{index:06d}",
        "transcript_id": _text(segment.get("transcript_id")),
        "transcript_date": _date_text(segment.get("transcript_date")),
        "source_excerpt": _safe_cell(segment.get("source_excerpt")),
        "normalized_reasoning_summary": template["summary"],
        "claim_type": claim_type,
        "expected_behavior": template["expected_behavior"],
        "condition": template["condition"],
        "entry_zone": template["entry_zone"],
        "target_zone": template["target_zone"],
        "stop_zone": template["stop_zone"],
        "invalidation_zone": template["invalidation_zone"],
        "required_data": template["required_data"],
        "testability": template["testability"],
        "confidence": confidence,
        "reason_for_confidence": _reason_for_confidence(segment, confidence),
    }


def _fallback_claims_from_hypotheses(hypotheses: pl.DataFrame, start_index: int) -> list[dict[str, Any]]:
    if hypotheses.is_empty():
        return []
    rows = []
    mapping = {
        "WALL_AS_TARGET": "WALL_AS_MAGNET",
        "WALL_AS_REJECTION": "WALL_AS_REJECTION",
        "WALL_AS_ACCEPTANCE": "WALL_AS_ACCEPTANCE_BREAK",
        "MAX_OI_PIN": "MAX_OI_PIN",
        "LOW_OI_GAP_SQUEEZE": "LOW_OI_GAP_SQUEEZE",
        "CALL_WALL_RESISTANCE": "CALL_WALL_RESISTANCE",
        "PUT_WALL_SUPPORT": "PUT_WALL_SUPPORT",
        "PUT_CALL_IMBALANCE_BIAS": "PUT_CALL_IMBALANCE_BIAS",
        "TWENTY_FIVE_DOLLAR_GRID": "TWENTY_FIVE_DOLLAR_GRID",
        "ONE_SD_RANGE": "SD_GRID_ENTRY",
        "TWO_SD_STRESS": "SD_GRID_ENTRY",
        "OPEN_PRICE_REFERENCE": "OPEN_PRICE_REFERENCE",
        "NO_TRADE_MIDDLE_RANGE": "NO_TRADE_MIDDLE_RANGE",
    }
    for row in hypotheses.to_dicts():
        claim_type = mapping.get(_text(row.get("hypothesis_id")))
        excerpt = _safe_cell(row.get("guru_evidence_excerpt"))
        if not claim_type or not excerpt:
            continue
        rows.append(
            {
                "claim_id": f"gclaim_{start_index + len(rows) + 1:06d}",
                "transcript_id": "guru_wall_logic_hypotheses",
                "transcript_date": "",
                "source_excerpt": excerpt,
                "normalized_reasoning_summary": _safe_cell(row.get("plain_english_logic")),
                "claim_type": claim_type,
                "expected_behavior": _safe_cell(row.get("expected_behavior")),
                "condition": _safe_cell(row.get("required_timing")),
                "entry_zone": "Context-defined level",
                "target_zone": "Context-defined level",
                "stop_zone": "Not specified in hypothesis row",
                "invalidation_zone": "Not specified in hypothesis row",
                "required_data": _safe_cell(row.get("required_cme_data")),
                "testability": _testability_from_status(row.get("current_validation_status")),
                "confidence": "MEDIUM",
                "reason_for_confidence": "Fallback from prior structured hypothesis with source excerpt.",
            }
        )
    return rows


def _dedupe_claim_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    out = []
    for row in rows:
        key = (_text(row.get("transcript_id")), _text(row.get("claim_type")), _text(row.get("source_excerpt"))[:120])
        if key in seen:
            continue
        seen.add(key)
        row["claim_id"] = f"gclaim_{len(out) + 1:06d}"
        out.append(row)
    return out


def _claim_template(claim_type: str) -> dict[str, str]:
    templates = {
        "WALL_AS_MAGNET": (
            "OI wall may act as magnet/reference.",
            "Price tends to move nearer to mapped OI wall.",
            "Price starts between walls with timestamp-safe wall map.",
            "Between walls",
            "Nearest or strongest wall",
            "No stop specified by claim",
            "Wall context stale or price rejects before target.",
            "CME OI walls, basis, Dukascopy price",
            "NEED_MORE_CME_DATA",
        ),
        "WALL_AS_TARGET_TP": (
            "OI wall may be target/TP reference.",
            "Candidate path reaches wall before invalidation.",
            "Separate price candidate exists and wall is ahead.",
            "Existing price candidate",
            "Mapped CME wall",
            "Candidate invalidation level",
            "Rejected before wall or wall stale.",
            "CME OI walls, candidate rows, basis",
            "NEED_MORE_CME_DATA",
        ),
        "WALL_AS_REJECTION": (
            "Wall touch can reject back inside.",
            "Touch then close back inside with followthrough away.",
            "Wall touched without accepted hold beyond.",
            "Wall boundary",
            "Midpoint or opposite wall",
            "Accepted hold beyond wall",
            "Two closes beyond wall.",
            "CME OI walls, intraday OHLC",
            "TESTABLE_WITH_CME_OVERLAP",
        ),
        "WALL_AS_ACCEPTANCE_BREAK": (
            "Close and hold beyond wall can imply acceptance context.",
            "Two closes beyond wall followed by continuation.",
            "Price closes beyond mapped wall.",
            "Accepted wall break",
            "Next wall or low-OI gap",
            "Failed hold back inside wall",
            "Close back inside accepted wall.",
            "CME OI walls, intraday OHLC",
            "TESTABLE_WITH_CME_OVERLAP",
        ),
        "MAX_OI_PIN": (
            "Max OI can act as pin/magnet risk.",
            "Price closes nearer max-OI strike into short DTE.",
            "Short-dated max-OI wall visible.",
            "Near max-OI band",
            "Max-OI level",
            "Acceptance away from pin",
            "Strong move away from max-OI.",
            "CME OI by strike, DTE, basis",
            "NEED_MORE_CME_DATA",
        ),
        "LOW_OI_GAP_SQUEEZE": (
            "Low-OI gaps may allow continuation.",
            "Accepted break into low-OI gap travels toward next wall.",
            "Low-OI gap between higher OI walls.",
            "Gap entry after acceptance",
            "Next high-OI wall",
            "Failed acceptance",
            "Close back inside prior wall.",
            "CME OI distribution, basis, OHLC",
            "NEED_MORE_CME_DATA",
        ),
        "CALL_WALL_RESISTANCE": (
            "Call wall may act as resistance/target context.",
            "Call wall touch has measurable rejection or acceptance.",
            "Call wall above/near price.",
            "Call wall boundary",
            "Call wall or next wall",
            "Accepted break beyond call wall",
            "No rejection evidence.",
            "Call OI/volume/change, basis, OHLC",
            "NEED_MORE_CME_DATA",
        ),
        "PUT_WALL_SUPPORT": (
            "Put wall may act as support/target context.",
            "Put wall touch has measurable rejection or acceptance.",
            "Put wall below/near price.",
            "Put wall boundary",
            "Put wall or next wall",
            "Accepted break beyond put wall",
            "No rejection evidence.",
            "Put OI/volume/change, basis, OHLC",
            "NEED_MORE_CME_DATA",
        ),
        "PUT_CALL_IMBALANCE_BIAS": (
            "Put/call imbalance may describe positioning bias.",
            "Followthrough differs by imbalance side.",
            "Measured put/call imbalance before outcome.",
            "No entry zone",
            "No target zone",
            "No stop zone",
            "Imbalance not timestamp-safe.",
            "Put/call OI and volume history",
            "NEED_MORE_CME_DATA",
        ),
        "SD_GRID_ENTRY": (
            "SD band can define entry/review zone.",
            "Price touches SD band and either rejects or accepts.",
            "Price reaches 1SD/2SD/3SD band.",
            "SD boundary",
            "Midpoint or opposite SD band",
            "Next outer band",
            "Acceptance through band.",
            "Dukascopy OHLC, realized-vol or IV bands",
            "TESTABLE_WITH_DUKASCOPY",
        ),
        "SD_GRID_NO_TRADE": (
            "Middle SD/range area can be no-trade context.",
            "Middle-zone rows have weaker followthrough.",
            "Price sits inside middle range.",
            "Middle range",
            "No target zone",
            "No stop zone",
            "Boundary behavior appears.",
            "Dukascopy OHLC, range bands",
            "TESTABLE_WITH_DUKASCOPY",
        ),
        "THREE_SD_EXTREME_ENTRY": (
            "3SD is treated as an extreme review zone.",
            "3SD touch either rejects back inside or accepts into continuation.",
            "Price reaches 3SD from session open/range proxy.",
            "3SD boundary",
            "2SD/1SD/midpoint",
            "3.5SD outer reference",
            "Acceptance beyond 3SD.",
            "Dukascopy OHLC, realized-vol proxy",
            "TESTABLE_WITH_DUKASCOPY",
        ),
        "THREE_POINT_FIVE_SD_STOP": (
            "3.5SD can be outer invalidation reference.",
            "3SD fade fails when price reaches 3.5SD outer band.",
            "3SD event exists.",
            "3SD boundary",
            "2SD/1SD/midpoint",
            "3.5SD band",
            "Hit 3.5SD before reverting.",
            "Dukascopy OHLC, realized-vol proxy",
            "TESTABLE_WITH_DUKASCOPY",
        ),
        "TWENTY_FIVE_DOLLAR_GRID": (
            "$25 grid can define practical XAU range references.",
            "Grid levels are touched, rejected, or accepted at measurable rates.",
            "Price near $25/$50 increment.",
            "$25/$50 boundary",
            "Next grid or midpoint",
            "Next outer grid",
            "Accepted break through grid.",
            "Dukascopy OHLC",
            "TESTABLE_WITH_DUKASCOPY",
        ),
        "IV_EXPECTED_MOVE": (
            "IV expected move frames the likely range.",
            "Price respects or breaks IV-derived bands.",
            "Timestamp-safe IV is available.",
            "IV band",
            "Opposite band or midpoint",
            "Outer IV band",
            "IV data stale or missing.",
            "CME IV, Dukascopy OHLC",
            "NEED_MORE_CME_DATA",
        ),
        "REALIZED_RANGE_EXPECTATION": (
            "Realized volatility/ATR can frame ranges.",
            "Price respects realized-vol or ATR bands.",
            "Enough recent OHLC history exists.",
            "ATR/realized-vol band",
            "Midpoint/opposite band",
            "Outer band",
            "Vol regime changes.",
            "Dukascopy OHLC",
            "TESTABLE_WITH_DUKASCOPY",
        ),
        "OPEN_PRICE_REFERENCE": (
            "Session open anchors distance and range logic.",
            "Open-distance bucket changes review state.",
            "Session open is known.",
            "Open-relative band",
            "Open/grid/wall reference",
            "Outer open-distance band",
            "Open reference unavailable.",
            "Dukascopy OHLC",
            "TESTABLE_WITH_DUKASCOPY",
        ),
        "NO_TRADE_MIDDLE_RANGE": (
            "Middle range is a blocker/watch context.",
            "Middle-zone events are lower quality than boundary events.",
            "Price is between relevant boundaries.",
            "Middle zone",
            "No target zone",
            "No stop zone",
            "Boundary touch or acceptance.",
            "Dukascopy OHLC, range/wall bands",
            "TESTABLE_WITH_DUKASCOPY",
        ),
        "ACCEPTANCE_CONFIRMATION": (
            "Acceptance requires close/hold behavior.",
            "Close and hold confirms continuation context.",
            "Level has been crossed.",
            "Accepted side of level",
            "Next level",
            "Back inside level",
            "Failed hold.",
            "Intraday OHLC",
            "TESTABLE_WITH_DUKASCOPY",
        ),
        "REJECTION_CONFIRMATION": (
            "Rejection requires touch then close back inside.",
            "Rejected level has followthrough away.",
            "Level touched.",
            "Touched boundary",
            "Midpoint/opposite boundary",
            "Accepted beyond level",
            "Close/hold beyond level.",
            "Intraday OHLC",
            "TESTABLE_WITH_DUKASCOPY",
        ),
        "RISK_MANAGEMENT": (
            "Risk management constrains use of setups.",
            "Defined stop/target relation changes outcome distribution.",
            "Entry/target/stop references are known.",
            "Defined entry reference",
            "Defined target reference",
            "Defined stop reference",
            "Stop hit or data stale.",
            "Dukascopy OHLC, spread/cost context",
            "TESTABLE_WITH_DUKASCOPY",
        ),
        "POST_EVENT_COMMENTARY": (
            "Post-event commentary is not usable as pre-event signal.",
            "Commentary only explains after-the-fact behavior.",
            "Text timestamp is after event or unclear.",
            "No entry zone",
            "No target zone",
            "No stop zone",
            "No as-of proof.",
            "Transcript timing metadata",
            "CONTEXT_ONLY",
        ),
        "UNTESTABLE": (
            "Claim lacks enough structure for testing.",
            "No measurable behavior specified.",
            "Unclear condition.",
            "N/A",
            "N/A",
            "N/A",
            "Unclear evidence.",
            "Human review required",
            "UNTESTABLE",
        ),
    }
    summary, behavior, condition, entry, target, stop, invalidation, data, testability = templates[claim_type]
    return {
        "summary": summary,
        "expected_behavior": behavior,
        "condition": condition,
        "entry_zone": entry,
        "target_zone": target,
        "stop_zone": stop,
        "invalidation_zone": invalidation,
        "required_data": data,
        "testability": testability,
    }


def _claim_confidence(segment: dict[str, Any], claim_type: str) -> str:
    if bool(segment.get("needs_human_review")):
        return "LOW"
    if claim_type == "UNTESTABLE":
        return "LOW"
    if _text(segment.get("confidence")) == "HIGH":
        return "HIGH"
    return "MEDIUM"


def _reason_for_confidence(segment: dict[str, Any], confidence: str) -> str:
    if confidence == "HIGH":
        return "Structured rule tag, source excerpt, and context fields all support the claim."
    if confidence == "MEDIUM":
        return "Source excerpt and context support the claim, but manual review is still useful."
    return "Segment has sparse context, uncertain category, or needs human review."


def _testability_from_status(status: Any) -> str:
    text = _text(status)
    if "PRICE_ONLY" in text:
        return "TESTABLE_WITH_DUKASCOPY"
    if "CME" in text:
        return "TESTABLE_WITH_CME_OVERLAP"
    if "CONTEXT" in text:
        return "CONTEXT_ONLY"
    return "NEED_MORE_CME_DATA"


def _sd_grid_rule_template(rule_id: str) -> dict[str, Any]:
    templates = {
        "ENTRY_AT_1SD_FADE": ("1SD touch then close back inside.", "Midpoint or open.", "Next outer band.", "Acceptance beyond 1SD.", True, False),
        "ENTRY_AT_2SD_FADE": ("2SD touch then close back inside.", "1SD or midpoint.", "3SD outer band.", "Acceptance beyond 2SD.", True, False),
        "ENTRY_AT_3SD_FADE": ("3SD extreme touch then close back inside.", "2SD/1SD/midpoint.", "3.5SD outer band.", "Acceptance beyond 3SD.", True, False),
        "ENTRY_AT_3SD_WITH_3_5SD_STOP": ("3SD extreme touch with 3.5SD invalidation.", "2SD/1SD/midpoint.", "3.5SD outer band.", "3.5SD hit before reversion.", True, False),
        "TP_AT_1SD": ("Existing candidate uses 1SD as target reference.", "1SD band.", "Candidate invalidation.", "1SD already stale or crossed.", True, False),
        "TP_AT_MIDPOINT": ("Existing candidate uses midpoint/open as target reference.", "Open/midpoint.", "Candidate invalidation.", "Midpoint not reachable in window.", True, False),
        "TP_AT_CME_WALL": ("Existing candidate uses CME wall as target reference.", "Mapped CME wall.", "Candidate invalidation.", "CME wall unavailable or stale.", False, True),
        "TP_AT_MAX_OI": ("Existing candidate uses max-OI wall as target reference.", "Max-OI spot-equivalent wall.", "Candidate invalidation.", "Max-OI wall stale or missing.", False, True),
        "NO_TRADE_INSIDE_MIDDLE_RANGE": ("Price inside middle range without boundary behavior.", "No target.", "No stop.", "Boundary touch/acceptance appears.", True, True),
        "ACCEPTANCE_BEYOND_3SD_CONTINUATION": ("Close and hold beyond 3SD.", "Next range band.", "Back inside 3SD.", "Failed hold beyond 3SD.", True, False),
        "REJECTION_BACK_INSIDE_3SD_FADE": ("3SD touch then close back inside.", "2SD/1SD/midpoint.", "3.5SD outer band.", "Close and hold beyond 3SD.", True, False),
        "$25_GRID_ROTATION": ("Touch/reject $25 grid increment.", "Adjacent grid or midpoint.", "Next outer grid.", "Accepted break through grid.", True, False),
        "$50_GRID_ROTATION": ("Touch/reject $50 grid increment.", "Adjacent grid or midpoint.", "Next outer grid.", "Accepted break through grid.", True, False),
    }
    entry, target, stop, invalidation, price_only, cme = templates[rule_id]
    return {
        "entry_logic": entry,
        "target_logic": target,
        "stop_logic": stop,
        "invalidation_logic": invalidation,
        "required_data": "Dukascopy OHLC" + ("; CME OI/IV/basis" if cme else ""),
        "can_test_price_only": price_only,
        "can_test_cme_overlap": cme,
        "risk_warning": "Research-only fixed comparison; do not tune on full sample.",
    }


def _claim_source_for_rule(claims: pl.DataFrame, rule_id: str) -> str:
    wanted = {
        "ENTRY_AT_1SD_FADE": ["SD_GRID_ENTRY"],
        "ENTRY_AT_2SD_FADE": ["SD_GRID_ENTRY"],
        "ENTRY_AT_3SD_FADE": ["THREE_SD_EXTREME_ENTRY"],
        "ENTRY_AT_3SD_WITH_3_5SD_STOP": ["THREE_POINT_FIVE_SD_STOP", "THREE_SD_EXTREME_ENTRY"],
        "TP_AT_1SD": ["SD_GRID_ENTRY"],
        "TP_AT_MIDPOINT": ["REALIZED_RANGE_EXPECTATION", "OPEN_PRICE_REFERENCE"],
        "TP_AT_CME_WALL": ["WALL_AS_TARGET_TP", "WALL_AS_MAGNET"],
        "TP_AT_MAX_OI": ["MAX_OI_PIN"],
        "NO_TRADE_INSIDE_MIDDLE_RANGE": ["NO_TRADE_MIDDLE_RANGE", "SD_GRID_NO_TRADE"],
        "ACCEPTANCE_BEYOND_3SD_CONTINUATION": ["THREE_SD_EXTREME_ENTRY", "ACCEPTANCE_CONFIRMATION"],
        "REJECTION_BACK_INSIDE_3SD_FADE": ["THREE_SD_EXTREME_ENTRY", "REJECTION_CONFIRMATION"],
        "$25_GRID_ROTATION": ["TWENTY_FIVE_DOLLAR_GRID"],
        "$50_GRID_ROTATION": ["TWENTY_FIVE_DOLLAR_GRID"],
    }[rule_id]
    subset = claims.filter(pl.col("claim_type").is_in(wanted)) if not claims.is_empty() else pl.DataFrame()
    return _representative_excerpts(subset, limit=1) or "No source excerpt available."


def _sd_grid_backtest_row(rule_id: str, timeframe: str, frame: pl.DataFrame, sd_proxy: float) -> dict[str, Any]:
    events = _sd_rule_events(rule_id, frame, sd_proxy)
    returns = [event["proxy_return"] for event in events]
    mfes = [event["mfe"] for event in events]
    maes = [event["mae"] for event in events]
    spread = _spread_estimate(frame)
    return {
        "rule_id": rule_id,
        "timeframe": timeframe,
        "event_count": len(events),
        "entry_count": len(events),
        "target_hit_rate": _rate([event["target_hit"] for event in events]),
        "stop_hit_rate": _rate([event["stop_hit"] for event in events]),
        "average_mfe": _average(mfes),
        "average_mae": _average(maes),
        "expectancy_proxy": _average([value - spread for value in returns]),
        "max_adverse_excursion": min(maes) if maes else None,
        "drawdown_proxy": _max_drawdown([value - spread for value in returns]),
        "spread_cost_estimate": spread,
        "sample_size_warning": len(events) < MIN_SAMPLE,
        "tail_risk_warning": _tail_risk_warning(rule_id, events),
    }


def _empty_backtest_row(rule_id: str, timeframe: str) -> dict[str, Any]:
    return {
        "rule_id": rule_id,
        "timeframe": timeframe,
        "event_count": 0,
        "entry_count": 0,
        "target_hit_rate": None,
        "stop_hit_rate": None,
        "average_mfe": None,
        "average_mae": None,
        "expectancy_proxy": None,
        "max_adverse_excursion": None,
        "drawdown_proxy": None,
        "spread_cost_estimate": None,
        "sample_size_warning": True,
        "tail_risk_warning": "NO_DATA",
    }


def _sd_rule_events(rule_id: str, frame: pl.DataFrame, sd_proxy: float) -> list[dict[str, Any]]:
    if frame.is_empty():
        return []
    events = []
    by_day = frame.group_by("trade_date", maintain_order=True)
    for _, group in by_day:
        bars = group.sort("timestamp").to_dicts()
        if not bars:
            continue
        open_price = _float(bars[0].get("open"))
        if open_price is None:
            continue
        if "$25" in rule_id:
            events.extend(_grid_events(bars, grid=25.0))
        elif "$50" in rule_id:
            events.extend(_grid_events(bars, grid=50.0))
        elif "1SD" in rule_id:
            events.extend(_sd_band_events(bars, open_price, sd_proxy, multiple=1.0, outer=2.0, continuation=False))
        elif "2SD" in rule_id:
            events.extend(_sd_band_events(bars, open_price, sd_proxy, multiple=2.0, outer=3.0, continuation=False))
        elif "ACCEPTANCE_BEYOND_3SD" in rule_id:
            events.extend(_sd_band_events(bars, open_price, sd_proxy, multiple=3.0, outer=3.5, continuation=True))
        elif "3SD" in rule_id:
            events.extend(_sd_band_events(bars, open_price, sd_proxy, multiple=3.0, outer=3.5, continuation=False))
        elif "TP_AT_MIDPOINT" in rule_id or "NO_TRADE" in rule_id:
            events.extend(_middle_range_events(bars, open_price, sd_proxy))
    return events


def _grid_events(bars: list[dict[str, Any]], *, grid: float) -> list[dict[str, Any]]:
    events = []
    for bar in bars:
        open_price = _float(bar.get("open"))
        high = _float(bar.get("high"))
        low = _float(bar.get("low"))
        close = _float(bar.get("close"))
        if None in (open_price, high, low, close):
            continue
        upper = math.ceil(open_price / grid) * grid
        lower = math.floor(open_price / grid) * grid
        if upper == lower:
            upper += grid
            lower -= grid
        touched_upper = high >= upper
        touched_lower = low <= lower
        if not (touched_upper or touched_lower):
            continue
        target_hit = lower <= close <= upper
        stop_hit = high >= upper + grid or low <= lower - grid
        mfe = max(high - open_price, open_price - low)
        mae = -max(open_price - low if touched_upper else 0.0, high - open_price if touched_lower else 0.0)
        events.append(
            {
                "target_hit": target_hit,
                "stop_hit": stop_hit,
                "mfe": mfe,
                "mae": mae,
                "proxy_return": (abs(close - open_price) if target_hit else -abs(close - open_price)),
            }
        )
    return events


def _sd_band_events(
    bars: list[dict[str, Any]],
    open_price: float,
    sd_proxy: float,
    *,
    multiple: float,
    outer: float,
    continuation: bool,
) -> list[dict[str, Any]]:
    events = []
    upper = open_price + sd_proxy * multiple
    lower = open_price - sd_proxy * multiple
    outer_upper = open_price + sd_proxy * outer
    outer_lower = open_price - sd_proxy * outer
    for index, bar in enumerate(bars):
        high = _float(bar.get("high"))
        low = _float(bar.get("low"))
        close = _float(bar.get("close"))
        if None in (high, low, close):
            continue
        touched_upper = high >= upper
        touched_lower = low <= lower
        if not (touched_upper or touched_lower):
            continue
        accepted = close > upper or close < lower
        target_hit = accepted if continuation else lower < close < upper
        stop_hit = high >= outer_upper or low <= outer_lower
        mfe = max(high - open_price, open_price - low)
        mae = -max(open_price - low if touched_upper else 0.0, high - open_price if touched_lower else 0.0)
        events.append(
            {
                "target_hit": target_hit,
                "stop_hit": stop_hit,
                "mfe": mfe,
                "mae": mae,
                "proxy_return": mfe if target_hit else mae,
                "bar_index": index,
            }
        )
    return events


def _middle_range_events(bars: list[dict[str, Any]], open_price: float, sd_proxy: float) -> list[dict[str, Any]]:
    events = []
    upper = open_price + sd_proxy
    lower = open_price - sd_proxy
    for bar in bars:
        close = _float(bar.get("close"))
        high = _float(bar.get("high"))
        low = _float(bar.get("low"))
        if None in (close, high, low):
            continue
        if lower <= close <= upper:
            events.append(
                {
                    "target_hit": False,
                    "stop_hit": False,
                    "mfe": max(high - close, close - low),
                    "mae": -max(high - close, close - low),
                    "proxy_return": 0.0,
                }
            )
    return events


def _cme_case_events(case_type: str, *, wall_map: pl.DataFrame, price: pl.DataFrame) -> list[dict[str, Any]]:
    events = []
    for trade_date in sorted(set(wall_map.get_column("trade_date").cast(pl.Utf8).to_list())):
        bars = _date_price_rows(price, trade_date)
        if not bars:
            continue
        walls = wall_map.filter(pl.col("trade_date") == trade_date)
        wall = _select_wall(case_type, walls, bars)
        if not wall:
            continue
        events.append(_wall_target_event(case_type, bars, wall))
    return events


def _select_wall(case_type: str, walls: pl.DataFrame, bars: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [row for row in walls.to_dicts() if _float(row.get("spot_equivalent_level")) is not None]
    if not rows:
        return {}
    start = _float(bars[0].get("open")) or _float(bars[0].get("close")) or 0.0
    if case_type == "NEAREST_WALL":
        return min(rows, key=lambda row: abs((_float(row.get("spot_equivalent_level")) or 0.0) - start))
    if case_type == "STRONGEST_WALL":
        return max(rows, key=lambda row: _float(row.get("wall_score")) or 0.0)
    if case_type == "MAX_OI_WALL":
        candidates = [row for row in rows if _text(row.get("wall_type")) == "MAX_OI_PIN"]
    elif case_type == "PUT_WALL":
        candidates = [row for row in rows if _text(row.get("wall_type")) == "PUT_WALL"]
    elif case_type == "CALL_WALL":
        candidates = [row for row in rows if _text(row.get("wall_type")) == "CALL_WALL"]
    elif case_type == "TOTAL_OI_WALL":
        candidates = [row for row in rows if _text(row.get("wall_type")) == "TOTAL_OI_WALL"]
    else:
        candidates = rows
    return max(candidates, key=lambda row: _float(row.get("wall_score")) or 0.0) if candidates else {}


def _wall_target_event(case_type: str, bars: list[dict[str, Any]], wall: dict[str, Any]) -> dict[str, Any]:
    level = _float(wall.get("spot_equivalent_level")) or _float(wall.get("strike")) or 0.0
    start = _float(bars[0].get("open")) or _float(bars[0].get("close")) or level
    close = _float(bars[-1].get("close")) or start
    direction = 1.0 if level >= start else -1.0
    touched = False
    rejected = False
    accepted_closes = 0
    toward = []
    against = []
    for bar in bars:
        high = _float(bar.get("high"))
        low = _float(bar.get("low"))
        bar_close = _float(bar.get("close"))
        if None in (high, low, bar_close):
            continue
        if low <= level <= high:
            touched = True
            if (direction > 0 and bar_close < level) or (direction < 0 and bar_close > level):
                rejected = True
        accepted = bar_close > level if direction > 0 else bar_close < level
        accepted_closes = accepted_closes + 1 if accepted else 0
        toward.append((high - start) if direction > 0 else (start - low))
        against.append((start - low) if direction > 0 else (high - start))
    accepted = accepted_closes >= 2
    return {
        "case_type": case_type,
        "target_hit": touched,
        "close_nearer": abs(close - level) < abs(start - level),
        "wall_touch": touched,
        "wall_rejection": rejected and not accepted,
        "wall_acceptance": accepted,
        "mfe_toward": max(toward) if toward else None,
        "mae_against": max(against) if against else None,
    }


def _cme_case_summary(case_type: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    sample_warning = len(events) < MIN_SAMPLE
    return {
        "case_type": case_type,
        "event_count": len(events),
        "target_hit_rate": _rate([bool(event.get("target_hit")) for event in events]),
        "close_nearer_rate": _rate([bool(event.get("close_nearer")) for event in events]),
        "wall_touch_rate": _rate([bool(event.get("wall_touch")) for event in events]),
        "wall_rejection_rate": _rate([bool(event.get("wall_rejection")) for event in events]),
        "wall_acceptance_rate": _rate([bool(event.get("wall_acceptance")) for event in events]),
        "average_mfe_toward_wall": _average([_float(event.get("mfe_toward")) for event in events]),
        "average_mae_against_wall": _average([_float(event.get("mae_against")) for event in events]),
        "sample_size_warning": sample_warning,
        "interpretation": _cme_case_interpretation(events, sample_warning),
    }


def _cme_case_interpretation(events: list[dict[str, Any]], sample_warning: bool) -> str:
    if sample_warning:
        return "INSUFFICIENT_SAMPLE"
    target = _rate([bool(event.get("target_hit")) for event in events]) or 0.0
    rejection = _rate([bool(event.get("wall_rejection")) for event in events]) or 0.0
    acceptance = _rate([bool(event.get("wall_acceptance")) for event in events]) or 0.0
    if target >= 0.55:
        return "MAGNET_CANDIDATE"
    if rejection > acceptance:
        return "REJECTION_CANDIDATE"
    if acceptance > rejection:
        return "ACCEPTANCE_CANDIDATE"
    return "MIXED"


def _data_needed_for_claim(claim_type: str) -> str:
    return _claim_template(claim_type)["required_data"]


def _data_available_for_claim(claim_type: str, inputs: dict[str, Any]) -> list[str]:
    available = []
    if not _price_frame(inputs, "1h").is_empty() or not _price_frame(inputs, "1d").is_empty():
        available.append("DUKASCOPY_PRICE")
    if not _frame_input(inputs, "cme_oi").is_empty():
        available.append("CME_OI")
    if not _frame_input(inputs, "cme_iv").is_empty():
        available.append("CME_IV")
    if not _frame_input(inputs, "basis").is_empty():
        available.append("BASIS")
    if claim_type in {"PUT_CALL_IMBALANCE_BIAS", "CALL_WALL_RESISTANCE", "PUT_WALL_SUPPORT"} and "CME_OI" not in available:
        return []
    return available


def _can_test_now(claim_type: str, available: list[str]) -> bool:
    if claim_type in {
        "SD_GRID_ENTRY",
        "SD_GRID_NO_TRADE",
        "THREE_SD_EXTREME_ENTRY",
        "THREE_POINT_FIVE_SD_STOP",
        "TWENTY_FIVE_DOLLAR_GRID",
        "REALIZED_RANGE_EXPECTATION",
        "OPEN_PRICE_REFERENCE",
        "NO_TRADE_MIDDLE_RANGE",
        "ACCEPTANCE_CONFIRMATION",
        "REJECTION_CONFIRMATION",
        "RISK_MANAGEMENT",
    }:
        return "DUKASCOPY_PRICE" in available
    if claim_type in {"UNTESTABLE", "POST_EVENT_COMMENTARY"}:
        return False
    return "DUKASCOPY_PRICE" in available and "CME_OI" in available and "BASIS" in available


def _test_result_available(claim_type: str, sd_grid: pl.DataFrame, cme_wall: pl.DataFrame) -> bool:
    if claim_type in {"TWENTY_FIVE_DOLLAR_GRID", "THREE_SD_EXTREME_ENTRY", "THREE_POINT_FIVE_SD_STOP", "SD_GRID_ENTRY"}:
        return not sd_grid.is_empty()
    if claim_type.startswith("WALL") or claim_type in {"MAX_OI_PIN", "LOW_OI_GAP_SQUEEZE", "CALL_WALL_RESISTANCE", "PUT_WALL_SUPPORT"}:
        return not cme_wall.is_empty()
    return not sd_grid.is_empty()


def _current_result_for_claim(claim_type: str, sd_grid: pl.DataFrame, cme_wall: pl.DataFrame) -> str:
    if claim_type == "TWENTY_FIVE_DOLLAR_GRID":
        rows = sd_grid.filter(pl.col("rule_id").str.contains("25", literal=True)) if not sd_grid.is_empty() else pl.DataFrame()
        return f"rows={rows.height}; comparison_only"
    if claim_type in {"THREE_SD_EXTREME_ENTRY", "THREE_POINT_FIVE_SD_STOP"}:
        rows = sd_grid.filter(pl.col("rule_id").str.contains("3SD", literal=True)) if not sd_grid.is_empty() else pl.DataFrame()
        tail = rows.select(pl.max("stop_hit_rate")).item() if not rows.is_empty() and "stop_hit_rate" in rows.columns else None
        return f"rows={rows.height}; max_stop_hit_rate={tail}"
    if claim_type.startswith("WALL") or claim_type in {"MAX_OI_PIN", "LOW_OI_GAP_SQUEEZE", "CALL_WALL_RESISTANCE", "PUT_WALL_SUPPORT"}:
        if cme_wall.is_empty():
            return "CME pilot missing"
        return "CME pilot only; " + ";".join(
            f"{row['case_type']}={row['interpretation']}" for row in cme_wall.head(3).to_dicts()
        )
    return "Mapped for review"


def _next_data_needed(claim_type: str, available: list[str]) -> str:
    if claim_type in {"UNTESTABLE", "POST_EVENT_COMMENTARY"}:
        return "Human review and as-of timing proof."
    missing = [item for item in ("DUKASCOPY_PRICE", "CME_OI", "CME_IV", "BASIS") if item not in available]
    if claim_type in {"TWENTY_FIVE_DOLLAR_GRID", "THREE_SD_EXTREME_ENTRY", "THREE_POINT_FIVE_SD_STOP"}:
        return "No extra data for price-only test; forward validation still required."
    return "More CME overlap dates." if not missing else "Missing: " + ";".join(missing)


def _cme_translation_templates() -> list[dict[str, str]]:
    return [
        _translation("WALL_AS_TP_REFERENCE", "Mapped wall is ahead of an independently generated research candidate.", "TARGET_REFERENCE"),
        _translation("MAX_OI_MAGNET_WATCH", "Short-dated max-OI wall is near current price.", "WATCH_ONLY"),
        _translation("FADE_ONLY_AFTER_WALL_REJECTION", "Wall touch closes back inside and does not hold beyond wall.", "ALLOW_RESEARCH_CANDIDATE"),
        _translation("FOLLOW_ONLY_AFTER_WALL_ACCEPTANCE", "Price closes and holds beyond mapped wall.", "ALLOW_RESEARCH_CANDIDATE"),
        _translation("NO_TRADE_MIDDLE_BETWEEN_WALLS", "Price is between major mapped walls without acceptance/rejection behavior.", "BLOCK"),
        _translation("AVOID_TRADE_DIRECTLY_INTO_WALL", "Candidate path points into nearby wall with no acceptance evidence.", "BLOCK"),
        _translation("LOW_OI_GAP_SQUEEZE_WATCH", "Accepted break enters low-OI gap toward next wall.", "WATCH_ONLY"),
        _translation("PIN_RISK_NO_CHASE", "Price is near max-OI/pin area after extended move.", "BLOCK"),
        _translation("3SD_EXTREME_WATCH", "Price reaches 3SD extreme from range proxy.", "WATCH_ONLY"),
        _translation("3_5SD_INVALIDATION_REFERENCE", "3.5SD acts as outer invalidation reference for 3SD review.", "TARGET_REFERENCE"),
    ]


def _translation(rule_id: str, condition: str, action: str) -> dict[str, str]:
    return {
        "rule_id": rule_id,
        "condition": condition,
        "action_label": action,
        "target_logic": "Use only as watchlist/target/reference context, never as a standalone direction trigger.",
        "invalidation_logic": "Invalidate when data is stale, missing, or price behavior contradicts the context.",
        "required_data": "Dukascopy OHLC plus CME OI/IV/basis where relevant.",
    }


def _claim_source_for_translation(claims: pl.DataFrame, rule_id: str) -> str:
    mapping = {
        "WALL_AS_TP_REFERENCE": ["WALL_AS_TARGET_TP", "WALL_AS_MAGNET"],
        "MAX_OI_MAGNET_WATCH": ["MAX_OI_PIN"],
        "FADE_ONLY_AFTER_WALL_REJECTION": ["WALL_AS_REJECTION", "REJECTION_CONFIRMATION"],
        "FOLLOW_ONLY_AFTER_WALL_ACCEPTANCE": ["WALL_AS_ACCEPTANCE_BREAK", "ACCEPTANCE_CONFIRMATION"],
        "NO_TRADE_MIDDLE_BETWEEN_WALLS": ["NO_TRADE_MIDDLE_RANGE"],
        "AVOID_TRADE_DIRECTLY_INTO_WALL": ["WALL_AS_REJECTION", "NO_TRADE_MIDDLE_RANGE"],
        "LOW_OI_GAP_SQUEEZE_WATCH": ["LOW_OI_GAP_SQUEEZE"],
        "PIN_RISK_NO_CHASE": ["MAX_OI_PIN"],
        "3SD_EXTREME_WATCH": ["THREE_SD_EXTREME_ENTRY"],
        "3_5SD_INVALIDATION_REFERENCE": ["THREE_POINT_FIVE_SD_STOP", "THREE_SD_EXTREME_ENTRY"],
    }
    subset = claims.filter(pl.col("claim_type").is_in(mapping[rule_id])) if not claims.is_empty() else pl.DataFrame()
    return _representative_excerpts(subset, limit=1) or "No source excerpt available."


def _translation_evidence(rule_id: str, cme_wall: pl.DataFrame) -> str:
    if cme_wall.is_empty():
        return "No CME wall test rows available."
    if "3" in rule_id:
        return "Dukascopy SD/grid test available; CME not required."
    return "CME wall test remains pilot-only: " + _dominant_cme_interpretation(cme_wall)


def _dominant_cme_interpretation(frame: pl.DataFrame) -> str:
    if frame.is_empty() or "interpretation" not in frame.columns:
        return "INSUFFICIENT_SAMPLE"
    values = [_text(value) for value in frame.get_column("interpretation").drop_nulls().to_list()]
    if "INSUFFICIENT_SAMPLE" in values:
        return "INSUFFICIENT_SAMPLE"
    return values[0] if values else "INSUFFICIENT_SAMPLE"


def _load_inputs(paths: dict[str, Path]) -> dict[str, Any]:
    return {
        "clean_transcripts": _read_optional(paths["clean_transcripts"]),
        "transcript_identity_audit": _read_optional(paths["transcript_identity_audit"]),
        "transcript_rules": _read_optional(paths["transcript_rules"]),
        "same_day_debug": _read_optional(paths["same_day_debug"]),
        "guru_logic_knowledge_base": _read_optional(paths["guru_logic_knowledge_base"]),
        "guru_wall_hypotheses": _read_optional(paths["guru_wall_hypotheses"]),
        "price_15m": _read_optional(paths["price_15m"]),
        "price_30m": _read_optional(paths["price_30m"]),
        "price_1h": _read_optional(paths["price_1h"]),
        "price_4h": _read_optional(paths["price_4h"]),
        "price_1d": _read_optional(paths["price_1d"]),
        "cme_oi": _read_optional(paths["cme_oi"]),
        "cme_iv": _read_optional(paths["cme_iv"]),
        "basis": _read_optional(paths["basis"]),
        "overlap_validation": _read_optional(paths["overlap_validation"]),
        "wall_map": _read_optional(paths["wall_map"]),
    }


def _output_paths(output_root: Path) -> dict[str, Path]:
    return {
        "clean_transcripts": output_root / "clean_transcript_set.csv",
        "transcript_identity_audit": output_root / "transcript_identity_audit.csv",
        "transcript_rules": output_root / "transcript_llm_extracted_rules.csv",
        "same_day_debug": output_root / "same_day_transcript_interpretation_debug.csv",
        "guru_logic_knowledge_base": output_root / "guru_logic_knowledge_base.csv",
        "guru_wall_hypotheses": output_root / "guru_wall_logic_hypotheses.csv",
        "price_15m": output_root / "dukascopy_xau_15m.parquet",
        "price_30m": output_root / "dukascopy_xau_30m.parquet",
        "price_1h": output_root / "dukascopy_xau_1h.parquet",
        "price_4h": output_root / "dukascopy_xau_4h.parquet",
        "price_1d": output_root / "dukascopy_xau_1d.parquet",
        "cme_oi": output_root / "cme_canonical_option_oi_by_strike.parquet",
        "cme_iv": output_root / "cme_canonical_option_iv_by_strike.parquet",
        "basis": output_root / "xau_basis_backfilled.parquet",
        "overlap_validation": output_root / "dukascopy_cme_overlap_validation.csv",
        "wall_map": output_root / "cme_wall_map_by_date.csv",
        "segments_csv": output_root / "guru_transcript_semantic_segments.csv",
        "segments_md": output_root / "guru_transcript_semantic_segments.md",
        "claims_jsonl": output_root / "guru_semantic_claims.jsonl",
        "claims_csv": output_root / "guru_semantic_claims.csv",
        "claims_md": output_root / "guru_semantic_claims.md",
        "frequency_csv": output_root / "guru_reasoning_frequency_map.csv",
        "frequency_md": output_root / "guru_reasoning_frequency_map.md",
        "rule_family_csv": output_root / "sd_grid_rule_family.csv",
        "rule_family_md": output_root / "sd_grid_rule_family.md",
        "sd_backtest_csv": output_root / "dukascopy_sd_grid_backtest.csv",
        "sd_backtest_md": output_root / "dukascopy_sd_grid_backtest.md",
        "cme_wall_tp_csv": output_root / "cme_wall_magnet_tp_backtest.csv",
        "cme_wall_tp_md": output_root / "cme_wall_magnet_tp_backtest.md",
        "mapping_csv": output_root / "guru_to_data_mapping_report.csv",
        "mapping_md": output_root / "guru_to_data_mapping_report.md",
        "translation_csv": output_root / "cme_only_rule_translation_from_guru.csv",
        "translation_md": output_root / "cme_only_rule_translation_from_guru.md",
    }


def _read_optional(path: Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    try:
        if path.suffix.lower() == ".parquet":
            return pl.read_parquet(path)
        return pl.read_csv(path, infer_schema_length=None)
    except Exception:  # noqa: BLE001 - optional research inputs degrade to empty.
        return pl.DataFrame()


def _price_frame(inputs: dict[str, Any], timeframe: str) -> pl.DataFrame:
    frame = _frame_input(inputs, f"price_{timeframe}")
    if frame.is_empty():
        return pl.DataFrame()
    normalized = frame
    if "trade_date" not in normalized.columns and "timestamp" in normalized.columns:
        normalized = normalized.with_columns(pl.col("timestamp").map_elements(_date_text, return_dtype=pl.Utf8).alias("trade_date"))
    for column in ("open", "high", "low", "close"):
        if column not in normalized.columns and f"mid_{column}" in normalized.columns:
            normalized = normalized.with_columns(pl.col(f"mid_{column}").alias(column))
        if column not in normalized.columns:
            normalized = normalized.with_columns(pl.lit(None).cast(pl.Float64).alias(column))
        else:
            normalized = normalized.with_columns(pl.col(column).cast(pl.Float64, strict=False).alias(column))
    if "spread_points" not in normalized.columns:
        normalized = normalized.with_columns(pl.lit(None).cast(pl.Float64).alias("spread_points"))
    if "timestamp" not in normalized.columns:
        normalized = normalized.with_columns(pl.col("trade_date").alias("timestamp"))
    return normalized.select(["timestamp", "trade_date", "open", "high", "low", "close", "spread_points"])


def _wall_map(inputs: dict[str, Any]) -> pl.DataFrame:
    frame = _frame_input(inputs, "wall_map")
    if frame.is_empty():
        return pl.DataFrame()
    return frame


def _date_price_rows(frame: pl.DataFrame, trade_date: str) -> list[dict[str, Any]]:
    if frame.is_empty() or "trade_date" not in frame.columns:
        return []
    return frame.filter(pl.col("trade_date").cast(pl.Utf8) == trade_date).sort("timestamp").to_dicts()


def _daily_ranges(daily: pl.DataFrame) -> list[float]:
    if daily.is_empty():
        return []
    ranges = []
    for row in daily.to_dicts():
        high = _float(row.get("high"))
        low = _float(row.get("low"))
        if high is not None and low is not None and high >= low:
            ranges.append(high - low)
    return ranges


def _range_proxy(ranges: list[float]) -> float:
    median = _percentile(ranges, 0.5)
    return max((median or 30.0) / 3.0, 1.0)


def _spread_estimate(frame: pl.DataFrame) -> float:
    if frame.is_empty() or "spread_points" not in frame.columns:
        return 0.0
    values = [_float(value) for value in frame.get_column("spread_points").drop_nulls().head(500).to_list()]
    clean = [value for value in values if value is not None]
    return _average(clean) or 0.0


def _tail_risk_warning(rule_id: str, events: list[dict[str, Any]]) -> str:
    if not events:
        return "NO_EVENTS"
    stop_rate = _rate([event["stop_hit"] for event in events]) or 0.0
    if "3SD" in rule_id and stop_rate > 0.25:
        return "TAIL_RISK_VISIBLE"
    return "COMPARISON_ONLY"


def _has_sd_grid_tests(frame: pl.DataFrame) -> bool:
    return not frame.is_empty() and frame.filter(pl.col("event_count") > 0).height > 0


def _cme_small_sample(frame: pl.DataFrame) -> bool:
    return frame.is_empty() or bool(frame.select(pl.max("sample_size_warning")).item())


def _claims_jsonl(claims: pl.DataFrame) -> str:
    lines = []
    for row in claims.to_dicts():
        safe = {key: _safe_cell(value) if isinstance(value, str) else value for key, value in row.items()}
        lines.append(json.dumps(safe, ensure_ascii=False, sort_keys=True))
    return "\n".join(lines) + ("\n" if lines else "")


def _artifact_markdown(title: str, frame: pl.DataFrame) -> str:
    return "\n\n".join(["# " + title, RESEARCH_WARNING, PILOT_WARNING, _frame_markdown(frame)])


def _artifact_title(key: str) -> str:
    return {
        "frequency": "Guru Reasoning Frequency Map",
        "rule_family": "SD/Grid Rule Family",
        "sd_backtest": "Dukascopy SD/Grid Backtest",
        "cme_wall_tp": "CME Wall Magnet/TP Backtest",
        "mapping": "Guru-to-Data Mapping Report",
        "translation": "CME-only Rule Translation From Guru",
    }[key]


def _safe_report_text(text: str) -> str:
    safe = _redact_paths(text)
    for phrase in FORBIDDEN_REPORT_PHRASES:
        safe = re.sub(re.escape(phrase.strip()), "[redacted research-safety phrase]", safe, flags=re.IGNORECASE)
    return safe


def _safe_cell(value: Any) -> str:
    return _safe_report_text(_text(value))


def _redact_paths(text: str) -> str:
    safe = re.sub(r"[A-Za-z]:\\[^\s|)<>]+", "<REDACTED_PATH>", text)
    return re.sub(r"/(?:Users|home|mnt|var|tmp)/[^\s|)<>]+", "<REDACTED_PATH>", safe)


def _frame(rows: list[dict[str, Any]], schema: dict[str, Any]) -> pl.DataFrame:
    if not rows:
        return pl.DataFrame(schema=schema)
    frame = pl.DataFrame(rows, infer_schema_length=None)
    for column, dtype in schema.items():
        if column not in frame.columns:
            frame = frame.with_columns(pl.lit(None).cast(dtype).alias(column))
        else:
            frame = frame.with_columns(pl.col(column).cast(dtype, strict=False).alias(column))
    return frame.select(list(schema))


def _frame_markdown(frame: pl.DataFrame, *, limit: int = 20) -> str:
    if frame.is_empty():
        return "_No rows._"
    sample = frame.head(limit)
    lines = [
        "| " + " | ".join(sample.columns) + " |",
        "| " + " | ".join("---" for _ in sample.columns) + " |",
    ]
    for row in sample.to_dicts():
        lines.append("| " + " | ".join(_markdown_cell(row.get(column, "")) for column in sample.columns) + " |")
    if frame.height > limit:
        lines.append(f"\n_Showing {limit} of {frame.height} rows._")
    return "\n".join(lines)


def _markdown_cell(value: Any) -> str:
    if value is None:
        return ""
    return _safe_cell(str(value).replace("|", "\\|").replace("\n", " "))[:700]


def _segment_schema() -> dict[str, Any]:
    return {
        "segment_id": pl.Utf8,
        "transcript_id": pl.Utf8,
        "transcript_date": pl.Utf8,
        "transcript_time": pl.Utf8,
        "source_excerpt": pl.Utf8,
        "surrounding_context_excerpt": pl.Utf8,
        "language_detected": pl.Utf8,
        "semantic_category": pl.Utf8,
        "confidence": pl.Utf8,
        "needs_human_review": pl.Boolean,
        "rule_tag": pl.Utf8,
    }


def _claim_schema() -> dict[str, Any]:
    return {
        "claim_id": pl.Utf8,
        "transcript_id": pl.Utf8,
        "transcript_date": pl.Utf8,
        "source_excerpt": pl.Utf8,
        "normalized_reasoning_summary": pl.Utf8,
        "claim_type": pl.Utf8,
        "expected_behavior": pl.Utf8,
        "condition": pl.Utf8,
        "entry_zone": pl.Utf8,
        "target_zone": pl.Utf8,
        "stop_zone": pl.Utf8,
        "invalidation_zone": pl.Utf8,
        "required_data": pl.Utf8,
        "testability": pl.Utf8,
        "confidence": pl.Utf8,
        "reason_for_confidence": pl.Utf8,
    }


def _frequency_schema() -> dict[str, Any]:
    return {
        "claim_type": pl.Utf8,
        "claim_count": pl.Int64,
        "transcript_count": pl.Int64,
        "first_seen_date": pl.Utf8,
        "last_seen_date": pl.Utf8,
        "representative_excerpts": pl.Utf8,
        "confidence_distribution": pl.Utf8,
        "testability_distribution": pl.Utf8,
        "recommended_priority": pl.Utf8,
    }


def _rule_family_schema() -> dict[str, Any]:
    return {
        "rule_id": pl.Utf8,
        "guru_claim_source": pl.Utf8,
        "entry_logic": pl.Utf8,
        "target_logic": pl.Utf8,
        "stop_logic": pl.Utf8,
        "invalidation_logic": pl.Utf8,
        "required_data": pl.Utf8,
        "can_test_price_only": pl.Boolean,
        "can_test_cme_overlap": pl.Boolean,
        "risk_warning": pl.Utf8,
    }


def _sd_backtest_schema() -> dict[str, Any]:
    return {
        "rule_id": pl.Utf8,
        "timeframe": pl.Utf8,
        "event_count": pl.Int64,
        "entry_count": pl.Int64,
        "target_hit_rate": pl.Float64,
        "stop_hit_rate": pl.Float64,
        "average_mfe": pl.Float64,
        "average_mae": pl.Float64,
        "expectancy_proxy": pl.Float64,
        "max_adverse_excursion": pl.Float64,
        "drawdown_proxy": pl.Float64,
        "spread_cost_estimate": pl.Float64,
        "sample_size_warning": pl.Boolean,
        "tail_risk_warning": pl.Utf8,
    }


def _cme_wall_tp_schema() -> dict[str, Any]:
    return {
        "case_type": pl.Utf8,
        "event_count": pl.Int64,
        "target_hit_rate": pl.Float64,
        "close_nearer_rate": pl.Float64,
        "wall_touch_rate": pl.Float64,
        "wall_rejection_rate": pl.Float64,
        "wall_acceptance_rate": pl.Float64,
        "average_mfe_toward_wall": pl.Float64,
        "average_mae_against_wall": pl.Float64,
        "sample_size_warning": pl.Boolean,
        "interpretation": pl.Utf8,
    }


def _mapping_schema() -> dict[str, Any]:
    return {
        "claim_type": pl.Utf8,
        "data_needed": pl.Utf8,
        "data_available_now": pl.Utf8,
        "can_test_now": pl.Boolean,
        "test_result_available": pl.Boolean,
        "current_result": pl.Utf8,
        "next_data_needed": pl.Utf8,
    }


def _translation_schema() -> dict[str, Any]:
    return {
        "rule_id": pl.Utf8,
        "condition": pl.Utf8,
        "action_label": pl.Utf8,
        "target_logic": pl.Utf8,
        "invalidation_logic": pl.Utf8,
        "required_data": pl.Utf8,
        "guru_claim_source": pl.Utf8,
        "current_evidence": pl.Utf8,
        "validation_status": pl.Utf8,
    }


def _frame_input(inputs: dict[str, Any], key: str) -> pl.DataFrame:
    value = inputs.get(key)
    return value if isinstance(value, pl.DataFrame) else pl.DataFrame()


def _representative_excerpts(frame: pl.DataFrame, *, limit: int = 3) -> str:
    if frame.is_empty() or "source_excerpt" not in frame.columns:
        return ""
    excerpts = []
    for value in frame.get_column("source_excerpt").drop_nulls().to_list():
        text = _safe_cell(value)
        if text and text not in excerpts:
            excerpts.append(text[:240])
        if len(excerpts) >= limit:
            break
    return " || ".join(excerpts)


def _distribution(frame: pl.DataFrame, column: str) -> str:
    if frame.is_empty() or column not in frame.columns:
        return ""
    counts: dict[str, int] = {}
    for value in frame.get_column(column).drop_nulls().to_list():
        key = _text(value)
        counts[key] = counts.get(key, 0) + 1
    return ";".join(f"{key}:{value}" for key, value in sorted(counts.items()))


def _priority(claim_count: int, transcript_count: int, claim_type: str) -> str:
    if claim_type in {"UNTESTABLE", "POST_EVENT_COMMENTARY"}:
        return "LOW"
    if claim_count >= 100 or transcript_count >= 50:
        return "HIGH"
    if claim_count >= 20 or transcript_count >= 10:
        return "MEDIUM"
    return "LOW"


def _language_detected(text: str) -> str:
    if re.search(r"[\u0E00-\u0E7F]", text):
        return "THAI_OR_MIXED"
    if text:
        return "ENGLISH_OR_MIXED"
    return "UNKNOWN"


def _time_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    match = re.search(r"T(\d{2}:\d{2}:\d{2})", text)
    return match.group(1) if match else ""


def _date_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    match = re.search(r"\d{4}-\d{2}-\d{2}", str(value))
    return match.group(0) if match else ""


def _float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return None
        return number
    except (TypeError, ValueError):
        return None


def _average(values: list[float | None]) -> float | None:
    clean = [value for value in values if value is not None]
    if not clean:
        return None
    return sum(clean) / len(clean)


def _rate(values: list[bool]) -> float | None:
    if not values:
        return None
    return sum(1 for value in values if value) / len(values)


def _percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(max(int(round((len(ordered) - 1) * quantile)), 0), len(ordered) - 1)
    return ordered[index]


def _max_drawdown(values: list[float]) -> float | None:
    if not values:
        return None
    equity = 0.0
    peak = 0.0
    drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return drawdown


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
