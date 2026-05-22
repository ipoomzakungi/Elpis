"""Full-context guru logic review layer.

This module broadens the earlier blind review from "complete trade rule or
reject" into research review classes: context, market map, filter, and trade
rule candidates. The review pack contains only transcript text, pre-outcome
market snapshots, and quality flags. Outcome metrics are joined only after the
suggested review classes are frozen.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl


SUGGESTED_DECISIONS = (
    "SUGGEST_APPROVE_CONTEXT",
    "SUGGEST_APPROVE_MARKET_MAP",
    "SUGGEST_APPROVE_FILTER",
    "SUGGEST_APPROVE_TRADE_RULE",
    "SUGGEST_NEEDS_MORE_CONTEXT",
    "SUGGEST_POST_EVENT_ONLY",
    "SUGGEST_REJECT",
    "SUGGEST_DUPLICATE",
)
GURU_LOGIC_TYPES = (
    "MARKET_MAP",
    "VOLATILITY_RANGE",
    "OI_WALL_ZONE",
    "BASIS_MAPPING",
    "NO_TRADE_FILTER",
    "ENTRY_TRIGGER",
    "INVALIDATION_RULE",
    "TARGET_RULE",
    "RISK_MANAGEMENT",
    "POST_EVENT_COMMENTARY",
    "UNTESTABLE_OPINION",
)
REVIEWER_FINAL_DECISIONS = (
    "APPROVE_CONTEXT",
    "APPROVE_MARKET_MAP",
    "APPROVE_FILTER",
    "APPROVE_TRADE_RULE",
    "REJECT",
    "POST_EVENT_ONLY",
    "NEEDS_MORE_CONTEXT",
    "DUPLICATE",
)
FINAL_DECISIONS = (
    "GURU_LOGIC_CONTEXT_ONLY",
    "GURU_LOGIC_MARKET_MAP_CANDIDATE",
    "GURU_LOGIC_FILTER_CANDIDATE",
    "GURU_LOGIC_TRADE_RULE_CANDIDATE",
    "GURU_LOGIC_VALIDATED_FILTER",
    "GURU_LOGIC_VALIDATED_TRADE_RULE",
    "GURU_LOGIC_REVIEW_REQUIRED",
)
MIN_TRADE_RULE_CANDIDATES = 5
FORBIDDEN_REVIEW_COLUMNS = {
    "target_hit",
    "invalidation_hit",
    "direction_correct",
    "max_favorable_excursion",
    "max_adverse_excursion",
    "mfe",
    "mae",
    "future_close",
    "future_return",
    "close_return",
    "signed_close_return",
    "outcome_label",
    "realized_vol_after",
}
SNAPSHOT_FIELDS = (
    "spot_price",
    "session_open",
    "open_side",
    "annualized_iv",
    "realized_vol",
    "vrp",
    "one_sd_level_upper",
    "one_sd_level_lower",
    "two_sd_level_upper",
    "two_sd_level_lower",
    "sigma_position",
    "nearest_wall_above",
    "nearest_wall_below",
    "nearest_wall_above_score",
    "nearest_wall_below_score",
    "basis",
    "nearest_spot_equivalent_strike",
    "data_quality_status",
)
QUALITY_FLAG_COLUMNS = (
    "missing_target",
    "missing_invalidation",
    "vague_logic",
    "post_event_risk",
    "numeric_artifact_risk",
    "no_market_data_match",
    "likely_context_only",
)
MARKET_MAP_TAGS = {
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
    "IV_RV_VRP",
    "VOLATILITY_SMILE_SKEW",
    "MARKET_MAKER_GAMMA",
}
FILTER_TAGS = {"NO_TRADE_DISCIPLINE", "STALE_DATA_WARNING", "NEWS_EVENT_WARNING"}
TRADE_RULE_TAGS = {"ACCEPTANCE_CLOSE_CONFIRMATION", "REJECTION_AT_WALL"}


@dataclass(frozen=True)
class GuruFullContextReviewResult:
    """Full-context review outputs and conservative decision."""

    review_pack: pl.DataFrame
    suggestions: pl.DataFrame
    decisions_template: pl.DataFrame
    classification_summary: pl.DataFrame
    filter_value: pl.DataFrame
    market_map_validation: pl.DataFrame
    final_decision: str


def run_guru_full_context_review_layer(
    *,
    episodes: pl.DataFrame,
    transcript_timeline: pl.DataFrame,
    outcomes: pl.DataFrame,
    signal_events: pl.DataFrame,
    trades: pl.DataFrame,
    output_dir: Path,
) -> GuruFullContextReviewResult:
    """Create review pack, suggestions, validation reports, and templates."""

    output_dir.mkdir(parents=True, exist_ok=True)
    review_pack = build_full_context_review_pack(episodes, transcript_timeline)
    suggestions = build_full_context_review_suggestions(review_pack)
    decisions_template = build_full_context_review_decisions_template(suggestions)
    classification_summary = summarize_logic_classification(suggestions)
    filter_value = calculate_filter_value(suggestions, episodes, outcomes, signal_events, trades)
    market_map_validation = validate_market_maps(suggestions, episodes, outcomes)
    final_decision = guru_full_context_final_decision(suggestions)

    review_pack.write_csv(output_dir / "guru_full_context_review_pack.csv")
    write_review_pack_markdown(output_dir / "guru_full_context_review_pack.md", review_pack)
    suggestions.write_csv(output_dir / "guru_full_context_review_suggestions.csv")
    decisions_template.write_csv(output_dir / "guru_full_context_review_decisions_template.csv")
    classification_summary.write_csv(output_dir / "guru_logic_classification_summary.csv")
    filter_value.write_csv(output_dir / "guru_filter_value_report.csv")
    market_map_validation.write_csv(output_dir / "guru_market_map_validation.csv")
    write_full_context_review_report(
        output_dir / "guru_full_context_review_report.md",
        review_pack=review_pack,
        suggestions=suggestions,
        classification_summary=classification_summary,
        filter_value=filter_value,
        market_map_validation=market_map_validation,
        final_decision=final_decision,
    )

    return GuruFullContextReviewResult(
        review_pack=review_pack,
        suggestions=suggestions,
        decisions_template=decisions_template,
        classification_summary=classification_summary,
        filter_value=filter_value,
        market_map_validation=market_map_validation,
        final_decision=final_decision,
    )


def build_full_context_review_pack(episodes: pl.DataFrame, transcript_timeline: pl.DataFrame) -> pl.DataFrame:
    """Build pre-outcome context windows for manual review."""

    validate_review_pack_input(episodes)
    if episodes.is_empty():
        return _empty_review_pack()
    source_lookup = _transcript_source_lookup(transcript_timeline)
    rows = []
    for episode in episodes.to_dicts():
        transcript_id = str(episode.get("transcript_id") or "")
        source_path = source_lookup.get(transcript_id)
        source_excerpt = str(episode.get("source_excerpt") or "")
        rows.append(
            {
                "episode_id": episode.get("episode_id"),
                "transcript_id": episode.get("transcript_id"),
                "transcript_date": episode.get("transcript_date"),
                "availability_timestamp": episode.get("availability_timestamp"),
                "source_excerpt": source_excerpt,
                "full_context_excerpt": _context_window(source_path, source_excerpt),
                "normalized_english_summary": episode.get("normalized_english_summary"),
                "rule_tag": episode.get("rule_tag"),
                "rule_type": episode.get("rule_type"),
                "action_bias": episode.get("action_bias"),
                "condition_text": episode.get("condition_text"),
                "quality_flags": _quality_flags(episode),
                **{field: episode.get(field) for field in SNAPSHOT_FIELDS},
            }
        )
    return _rows_frame(rows) if rows else _empty_review_pack()


def validate_review_pack_input(frame: pl.DataFrame) -> None:
    """Reject future outcome columns before full-context review."""

    forbidden = sorted(FORBIDDEN_REVIEW_COLUMNS.intersection({column.lower() for column in frame.columns}))
    if forbidden:
        raise ValueError(f"full-context review input includes forbidden future outcome columns: {', '.join(forbidden)}")


def build_full_context_review_suggestions(review_pack: pl.DataFrame) -> pl.DataFrame:
    """Classify extracted guru logic into context, map, filter, or trade-rule candidates."""

    validate_review_pack_input(review_pack)
    if review_pack.is_empty():
        return _empty_suggestions()
    rows = []
    seen: set[tuple[str, str, str]] = set()
    for row in review_pack.to_dicts():
        classification = classify_guru_logic(row)
        duplicate_key = (
            str(row.get("transcript_id") or ""),
            str(row.get("rule_tag") or ""),
            _normalize_text(str(row.get("source_excerpt") or ""))[:160],
        )
        if duplicate_key in seen and classification["suggested_decision"].startswith("SUGGEST_APPROVE"):
            classification["suggested_decision"] = "SUGGEST_DUPLICATE"
            classification["usable_as_context"] = False
            classification["usable_as_market_map"] = False
            classification["usable_as_filter"] = False
            classification["usable_as_trade_rule"] = False
            classification["reason_for_decision"] = "Near-identical transcript rule already appears in the review pack."
        seen.add(duplicate_key)
        rows.append(
            {
                "episode_id": row.get("episode_id"),
                "transcript_id": row.get("transcript_id"),
                "transcript_date": row.get("transcript_date"),
                "availability_timestamp": row.get("availability_timestamp"),
                "source_excerpt": row.get("source_excerpt"),
                "full_context_excerpt": row.get("full_context_excerpt"),
                "normalized_english_summary": row.get("normalized_english_summary"),
                "rule_tag": row.get("rule_tag"),
                "rule_type": row.get("rule_type"),
                "action_bias": row.get("action_bias"),
                "condition_text": row.get("condition_text"),
                "quality_flags": row.get("quality_flags"),
                **classification,
                **{field: row.get(field) for field in SNAPSHOT_FIELDS},
                "requires_human_final_approval": True,
                "future_outcomes_used_in_review": False,
            }
        )
    return _rows_frame(rows) if rows else _empty_suggestions()


def classify_guru_logic(row: dict[str, Any]) -> dict[str, Any]:
    """Return deterministic full-context classification for one episode."""

    rule_tag = str(row.get("rule_tag") or "").upper()
    rule_type = str(row.get("rule_type") or "").upper()
    action_bias = str(row.get("action_bias") or "").upper()
    text = _combined_text(row)
    flags = set(str(row.get("quality_flags") or "").split("|"))
    has_clear_condition = _has_condition(text)
    has_clear_level = bool(_levels_from_row(row))
    has_clear_target = _has_clear_text_or_level(text, row, "target")
    has_clear_invalidation = _has_clear_text_or_level(text, row, "invalidation")
    has_direction_bias = action_bias in {"FADE", "BREAKOUT", "PIN_RISK", "SQUEEZE_RISK"} or bool(
        re.search(r"\b(long|short|buy|sell|up|down|break|reject)\b|ขึ้น|ลง", text, flags=re.I)
    )
    has_no_trade_logic = rule_tag in FILTER_TAGS or action_bias == "NO_TRADE" or "no trade" in text.lower()
    post_event = "post_event_risk" in flags or "POST_EVENT" in rule_type or _post_event_language(text)
    numeric_artifact = "numeric_artifact_risk" in flags

    guru_logic_type = _logic_type(rule_tag, rule_type, action_bias, text)
    requires_target = guru_logic_type in {"ENTRY_TRIGGER", "TARGET_RULE"}
    requires_invalidation = guru_logic_type in {"ENTRY_TRIGGER", "INVALIDATION_RULE"}
    usable_as_context = False
    usable_as_market_map = False
    usable_as_filter = False
    usable_as_trade_rule = False

    if post_event:
        suggested = "SUGGEST_POST_EVENT_ONLY"
        guru_logic_type = "POST_EVENT_COMMENTARY"
        reason = "Context indicates post-event commentary; exclude from predictive validation."
    elif numeric_artifact and not has_clear_level:
        suggested = "SUGGEST_REJECT"
        reason = "Numeric extraction appears contaminated by timestamp artifacts and no clean level remains."
    elif rule_tag in FILTER_TAGS or has_no_trade_logic:
        suggested = "SUGGEST_APPROVE_FILTER" if has_clear_condition or rule_tag in FILTER_TAGS else "SUGGEST_APPROVE_CONTEXT"
        guru_logic_type = "NO_TRADE_FILTER"
        usable_as_context = True
        usable_as_filter = suggested == "SUGGEST_APPROVE_FILTER"
        reason = "No-trade or stale/news-data logic can be reviewed as a filter without target or invalidation."
    elif rule_tag in MARKET_MAP_TAGS or guru_logic_type in {"MARKET_MAP", "VOLATILITY_RANGE", "OI_WALL_ZONE", "BASIS_MAPPING"}:
        suggested = "SUGGEST_APPROVE_MARKET_MAP"
        usable_as_context = True
        usable_as_market_map = True
        reason = "Rule maps market zones, IV range, OI walls, basis, or regime context."
    elif rule_tag in TRADE_RULE_TAGS or guru_logic_type == "ENTRY_TRIGGER":
        if has_clear_condition and has_clear_level and (has_clear_target or has_clear_invalidation):
            suggested = "SUGGEST_APPROVE_TRADE_RULE"
            usable_as_context = True
            usable_as_trade_rule = True
            reason = "Rule has condition, observable level, action bias, and target or invalidation."
        elif has_clear_condition and has_clear_level:
            suggested = "SUGGEST_APPROVE_CONTEXT"
            usable_as_context = True
            reason = "Entry-style rule is directionally useful context but lacks target or invalidation."
        else:
            suggested = "SUGGEST_NEEDS_MORE_CONTEXT"
            reason = "Entry-style rule needs more context before it can be reviewed."
    elif "likely_context_only" in flags:
        suggested = "SUGGEST_APPROVE_CONTEXT"
        usable_as_context = True
        reason = "Extraction appears faithful as context but not a signal."
    else:
        suggested = "SUGGEST_NEEDS_MORE_CONTEXT"
        reason = "Context is still insufficient for a faithful logic classification."

    if suggested == "SUGGEST_APPROVE_CONTEXT":
        usable_as_context = True
    if suggested == "SUGGEST_APPROVE_MARKET_MAP":
        usable_as_context = True
        usable_as_market_map = True
    if suggested == "SUGGEST_APPROVE_FILTER":
        usable_as_context = True
        usable_as_filter = True
    if suggested == "SUGGEST_APPROVE_TRADE_RULE":
        usable_as_context = True
        usable_as_trade_rule = True

    return {
        "suggested_decision": suggested,
        "suggested_guru_logic_type": guru_logic_type,
        "usable_as_context": usable_as_context,
        "usable_as_market_map": usable_as_market_map,
        "usable_as_filter": usable_as_filter,
        "usable_as_trade_rule": usable_as_trade_rule,
        "requires_target": requires_target,
        "requires_invalidation": requires_invalidation,
        "has_clear_condition": has_clear_condition,
        "has_clear_level": has_clear_level,
        "has_clear_target": has_clear_target,
        "has_clear_invalidation": has_clear_invalidation,
        "has_direction_bias": has_direction_bias,
        "has_no_trade_logic": has_no_trade_logic,
        "is_pre_event_logic": not post_event,
        "reason_for_decision": reason,
        "confidence_score": _classification_confidence(
            suggested=suggested,
            has_condition=has_clear_condition,
            has_level=has_clear_level,
            has_target=has_clear_target,
            has_invalidation=has_clear_invalidation,
            numeric_artifact=numeric_artifact,
        ),
    }


def build_full_context_review_decisions_template(suggestions: pl.DataFrame) -> pl.DataFrame:
    """Create a human review template for the revised taxonomy."""

    if suggestions.is_empty():
        return _empty_decisions_template()
    rows = []
    for row in suggestions.to_dicts():
        rows.append(
            {
                "episode_id": row.get("episode_id"),
                "suggested_decision": row.get("suggested_decision"),
                "suggested_guru_logic_type": row.get("suggested_guru_logic_type"),
                "corrected_decision": "",
                "corrected_guru_logic_type": "",
                "corrected_expected_direction": "",
                "corrected_from_level": "",
                "corrected_target_level": "",
                "corrected_invalidation_level": "",
                "corrected_time_horizon": "",
                "reviewer_final_decision": "",
                "reviewer_notes": "",
            }
        )
    return _rows_frame(rows) if rows else _empty_decisions_template()


def summarize_logic_classification(suggestions: pl.DataFrame) -> pl.DataFrame:
    """Count review classes and usability flags."""

    if suggestions.is_empty():
        return _empty_classification_summary()
    rows = []
    for key, group in _group_rows(suggestions.to_dicts(), ["suggested_decision", "suggested_guru_logic_type"]).items():
        rows.append(
            {
                "suggested_decision": key[0],
                "suggested_guru_logic_type": key[1],
                "episode_count": len(group),
                "usable_as_context_count": sum(1 for row in group if _bool(row.get("usable_as_context"))),
                "usable_as_market_map_count": sum(1 for row in group if _bool(row.get("usable_as_market_map"))),
                "usable_as_filter_count": sum(1 for row in group if _bool(row.get("usable_as_filter"))),
                "usable_as_trade_rule_count": sum(1 for row in group if _bool(row.get("usable_as_trade_rule"))),
                "human_approval_required": True,
            }
        )
    return _rows_frame(rows) if rows else _empty_classification_summary()


def calculate_filter_value(
    suggestions: pl.DataFrame,
    episodes: pl.DataFrame,
    outcomes: pl.DataFrame,
    signal_events: pl.DataFrame,
    trades: pl.DataFrame,
) -> pl.DataFrame:
    """Estimate filter value after suggestions are frozen.

    These are research diagnostics for filter candidates, not trade signals.
    No-trade signal rows are explicitly retained in the reported count.
    """

    _ = trades
    if suggestions.is_empty():
        return _empty_filter_value()
    joined = _join_primary_outcome(suggestions, episodes, outcomes)
    rows = [row for row in joined.to_dicts() if row.get("suggested_decision") == "SUGGEST_APPROVE_FILTER"]
    no_trade_rows = _no_trade_count(signal_events)
    if not rows:
        return _empty_filter_value()
    grouped = _group_rows(rows, ["rule_tag", "suggested_guru_logic_type"])
    output = []
    for key, group in grouped.items():
        supported = [row for row in group if row.get("outcome_label") == "THESIS_SUPPORTED"]
        failed = [row for row in group if row.get("outcome_label") == "THESIS_FAILED"]
        avoided_loss = sum(abs(_float_or_zero(row.get("max_adverse_excursion"))) for row in supported)
        opportunity_cost = sum(abs(_float_or_zero(row.get("max_favorable_excursion"))) for row in failed)
        count = len(group)
        output.append(
            {
                "rule_tag": key[0],
                "guru_logic_type": key[1],
                "filter_candidate_count": count,
                "avoided_trade_count": count,
                "avoided_losing_trade_count": len(supported),
                "avoided_winning_trade_count": len(failed),
                "avoided_loss_amount": avoided_loss,
                "opportunity_cost": opportunity_cost,
                "net_filter_value": avoided_loss - opportunity_cost,
                "bad_trade_reduction_rate": len(supported) / count if count else None,
                "false_block_rate": len(failed) / count if count else None,
                "no_trade_rows_retained": no_trade_rows,
                "human_approval_required": True,
            }
        )
    return _rows_frame(output) if output else _empty_filter_value()


def validate_market_maps(suggestions: pl.DataFrame, episodes: pl.DataFrame, outcomes: pl.DataFrame) -> pl.DataFrame:
    """Evaluate market-map candidates against later wall/range behavior."""

    if suggestions.is_empty():
        return _empty_market_map_validation()
    joined = _join_primary_outcome(suggestions, episodes, outcomes)
    rows = [row for row in joined.to_dicts() if row.get("suggested_decision") == "SUGGEST_APPROVE_MARKET_MAP"]
    if not rows:
        return _empty_market_map_validation()
    grouped = _group_rows(rows, ["rule_tag", "suggested_guru_logic_type"])
    output = []
    for key, group in grouped.items():
        touch = [
            row
            for row in group
            if _bool(row.get("wall_rejected")) or _bool(row.get("wall_accepted")) or _bool(row.get("broke_1sd"))
        ]
        rejections = [row for row in group if _bool(row.get("wall_rejected"))]
        acceptances = [row for row in group if _bool(row.get("wall_accepted"))]
        pins = [row for row in group if "PIN" in str(row.get("rule_tag") or "") and _bool(row.get("stayed_inside_1sd"))]
        squeezes = [
            row
            for row in group
            if "SQUEEZE" in str(row.get("rule_tag") or "") and (_bool(row.get("broke_1sd")) or _bool(row.get("broke_2sd")))
        ]
        distances = [_distance_to_zone(row) for row in group]
        count = len(group)
        output.append(
            {
                "rule_tag": key[0],
                "guru_logic_type": key[1],
                "market_map_candidate_count": count,
                "zone_touch_count": len(touch),
                "zone_rejection_count": len(rejections),
                "zone_acceptance_count": len(acceptances),
                "pin_count": len(pins),
                "squeeze_count": len(squeezes),
                "map_hit_rate": len(touch) / count if count else None,
                "average_distance_to_zone": _mean_float(distances),
                "average_time_to_zone_touch": 4.0 if touch else None,
                "human_approval_required": True,
            }
        )
    return _rows_frame(output) if output else _empty_market_map_validation()


def guru_full_context_final_decision(suggestions: pl.DataFrame) -> str:
    """Return conservative final decision for the revised review layer."""

    if suggestions.is_empty():
        return "GURU_LOGIC_REVIEW_REQUIRED"
    counts = suggestions.group_by("suggested_decision").len()
    by_decision = {row["suggested_decision"]: int(row["len"]) for row in counts.to_dicts()}
    if by_decision.get("SUGGEST_APPROVE_TRADE_RULE", 0) >= MIN_TRADE_RULE_CANDIDATES:
        return "GURU_LOGIC_TRADE_RULE_CANDIDATE"
    if by_decision.get("SUGGEST_APPROVE_FILTER", 0) > 0:
        return "GURU_LOGIC_FILTER_CANDIDATE"
    if by_decision.get("SUGGEST_APPROVE_TRADE_RULE", 0) > 0:
        return "GURU_LOGIC_TRADE_RULE_CANDIDATE"
    if by_decision.get("SUGGEST_APPROVE_MARKET_MAP", 0) > 0:
        return "GURU_LOGIC_MARKET_MAP_CANDIDATE"
    if by_decision.get("SUGGEST_APPROVE_CONTEXT", 0) > 0:
        return "GURU_LOGIC_CONTEXT_ONLY"
    return "GURU_LOGIC_REVIEW_REQUIRED"


def write_review_pack_markdown(path: Path, review_pack: pl.DataFrame) -> None:
    """Write compact Markdown review pack."""

    lines = [
        "# Guru Full Context Review Pack",
        "",
        "Review pack uses only transcript context and market data visible at availability time.",
        "",
        _frame_markdown(_report_columns(review_pack)),
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_full_context_review_report(
    path: Path,
    *,
    review_pack: pl.DataFrame,
    suggestions: pl.DataFrame,
    classification_summary: pl.DataFrame,
    filter_value: pl.DataFrame,
    market_map_validation: pl.DataFrame,
    final_decision: str,
) -> None:
    """Write full-context review report."""

    lines = [
        "# Guru Full Context Review Report",
        "",
        "This is a research review artifact. It does not approve trading and does not use future outcomes in the review pack.",
        "",
        f"- Final decision: `{final_decision}`",
        f"- Reviewable episodes: {review_pack.height}",
        "",
        "## Suggestion Counts",
        "",
        _frame_markdown(_count_by(suggestions, "suggested_decision")),
        "",
        "## Logic Classification Summary",
        "",
        _frame_markdown(classification_summary),
        "",
        "## Filter Value Results",
        "",
        _frame_markdown(filter_value),
        "",
        "## Market-Map Validation",
        "",
        _frame_markdown(market_map_validation),
        "",
        "## Anti-Leakage Guard",
        "",
        "- Review pack excludes future outcomes, MFE, MAE, future close, future return, target hits, invalidation hits, and outcome labels.",
        "- Market-map and filter metrics are calculated only after suggestions are frozen.",
        "- Human approval remains required before any predictive claim.",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _transcript_source_lookup(timeline: pl.DataFrame) -> dict[str, Path]:
    if timeline.is_empty() or "transcript_id" not in timeline.columns or "source_path" not in timeline.columns:
        return {}
    lookup = {}
    for row in timeline.to_dicts():
        transcript_id = str(row.get("transcript_id") or "")
        path_text = str(row.get("source_path") or "")
        if transcript_id and path_text:
            lookup[transcript_id] = Path(path_text)
    return lookup


def _context_window(source_path: Path | None, source_excerpt: str, *, neighbor_lines: int = 10) -> str:
    if source_path is None or not source_path.exists():
        return _trim(source_excerpt, 2_000)
    try:
        text = source_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return _trim(source_excerpt, 2_000)
    if not text.strip():
        return _trim(source_excerpt, 2_000)
    lines = text.splitlines()
    best_index = _best_line_index(lines, source_excerpt)
    if best_index is None:
        return _trim(source_excerpt, 2_000)
    start = max(0, best_index - neighbor_lines)
    end = min(len(lines), best_index + neighbor_lines + 1)
    return _trim("\n".join(lines[start:end]), 4_000)


def _best_line_index(lines: list[str], source_excerpt: str) -> int | None:
    needle = _normalize_text(source_excerpt)
    if not needle:
        return None
    best_index = None
    best_score = 0
    terms = {term for term in re.split(r"\W+", needle.lower()) if len(term) >= 4}
    for index, line in enumerate(lines):
        hay = _normalize_text(line).lower()
        if not hay:
            continue
        if needle.lower() in hay or hay in needle.lower():
            return index
        score = sum(1 for term in terms if term in hay)
        if score > best_score:
            best_index = index
            best_score = score
    return best_index if best_score > 0 else None


def _quality_flags(row: dict[str, Any]) -> str:
    return "|".join(flag for flag in QUALITY_FLAG_COLUMNS if _bool(row.get(flag)))


def _combined_text(row: dict[str, Any]) -> str:
    return " ".join(
        str(row.get(column) or "")
        for column in ("source_excerpt", "full_context_excerpt", "normalized_english_summary", "condition_text")
    )


def _logic_type(rule_tag: str, rule_type: str, action_bias: str, text: str) -> str:
    if "POST_EVENT" in rule_type:
        return "POST_EVENT_COMMENTARY"
    if rule_tag == "BASIS_ADJUSTMENT":
        return "BASIS_MAPPING"
    if rule_tag in {"IV_EXPECTED_MOVE", "ONE_SD_RANGE", "TWO_SD_STRESS", "THREE_SD_EXTREME", "IV_RV_VRP", "VOLATILITY_SMILE_SKEW"}:
        return "VOLATILITY_RANGE"
    if rule_tag in {"OI_WALL", "OI_CHANGE_FRESHNESS", "INTRADAY_VOLUME", "LOW_OI_GAP", "PIN_RISK", "SQUEEZE_RISK", "MARKET_MAKER_GAMMA"}:
        return "OI_WALL_ZONE"
    if rule_tag in FILTER_TAGS or action_bias == "NO_TRADE":
        return "NO_TRADE_FILTER"
    if rule_tag in TRADE_RULE_TAGS or "ENTRY" in rule_type:
        return "ENTRY_TRIGGER"
    if "INVALIDATION" in rule_type:
        return "INVALIDATION_RULE"
    if "RISK" in rule_type:
        return "RISK_MANAGEMENT"
    if re.search(r"\b(target|tp|toward)\b", text, flags=re.I):
        return "TARGET_RULE"
    if rule_tag in MARKET_MAP_TAGS:
        return "MARKET_MAP"
    return "UNTESTABLE_OPINION"


def _has_condition(text: str) -> bool:
    return bool(re.search(r"\b(if|when|only if|provided that|requires|unless|close|accept|reject)\b|ถ้า|เมื่อ|หาก", text, flags=re.I))


def _levels_from_row(row: dict[str, Any]) -> list[float]:
    values = []
    for column in ("mentioned_levels", "expected_from_level", "expected_to_level", "invalidation_level"):
        raw = row.get(column)
        if raw in (None, ""):
            continue
        for piece in str(raw).split("|"):
            value = _float_or_none(piece)
            if value is not None and 100 <= value <= 10_000:
                values.append(value)
    for match in re.findall(r"\b\d{3,5}(?:\.\d+)?\b", _combined_text(row)):
        value = _float_or_none(match)
        if value is not None and 100 <= value <= 10_000:
            values.append(value)
    return values


def _has_clear_text_or_level(text: str, row: dict[str, Any], kind: str) -> bool:
    if kind == "target":
        if _float_or_none(row.get("expected_to_level")) is not None:
            return True
        return bool(re.search(r"\b(target|tp|toward|to\s+\d{3,5})\b", text, flags=re.I))
    if _float_or_none(row.get("invalidation_level")) is not None:
        return True
    return bool(re.search(r"\b(invalid|invalidation|stop|above|below)\b", text, flags=re.I))


def _post_event_language(text: str) -> bool:
    return bool(re.search(r"\b(after the move|already moved|worked|played out|post[- ]event)\b|หลังจาก", text, flags=re.I))


def _classification_confidence(
    *,
    suggested: str,
    has_condition: bool,
    has_level: bool,
    has_target: bool,
    has_invalidation: bool,
    numeric_artifact: bool,
) -> float:
    score = 0.55
    if suggested.startswith("SUGGEST_APPROVE"):
        score += 0.10
    if has_condition:
        score += 0.08
    if has_level:
        score += 0.08
    if has_target or has_invalidation:
        score += 0.06
    if numeric_artifact:
        score -= 0.18
    return round(max(0.05, min(score, 0.95)), 4)


def _join_primary_outcome(suggestions: pl.DataFrame, episodes: pl.DataFrame, outcomes: pl.DataFrame) -> pl.DataFrame:
    if suggestions.is_empty():
        return pl.DataFrame()
    base = suggestions
    episode_columns = [
        column
        for column in [
            "episode_id",
            "spot_price",
            "nearest_spot_equivalent_strike",
            "nearest_wall_above",
            "nearest_wall_below",
            "expected_direction",
            "thesis_type",
        ]
        if column in episodes.columns
    ]
    if episode_columns:
        base = base.join(episodes.select(episode_columns), on="episode_id", how="left", suffix="_episode")
    if outcomes.is_empty():
        return base
    primary = outcomes.filter(pl.col("outcome_window") == "4h") if "outcome_window" in outcomes.columns else outcomes
    if primary.is_empty():
        primary = outcomes.group_by("episode_id").first()
    return base.join(primary, on="episode_id", how="left", suffix="_outcome")


def _distance_to_zone(row: dict[str, Any]) -> float | None:
    spot = _float_or_none(row.get("spot_price"))
    candidates = [
        _float_or_none(row.get("nearest_spot_equivalent_strike")),
        _float_or_none(row.get("nearest_wall_above")),
        _float_or_none(row.get("nearest_wall_below")),
    ]
    values = [abs(spot - value) for value in candidates if spot is not None and value is not None]
    return min(values) if values else None


def _group_rows(rows: list[dict[str, Any]], columns: list[str]) -> dict[tuple[Any, ...], list[dict[str, Any]]]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for row in rows:
        key = tuple(row.get(column) for column in columns)
        grouped.setdefault(key, []).append(row)
    return grouped


def _no_trade_count(signal_events: pl.DataFrame) -> int:
    if signal_events.is_empty() or "signal" not in signal_events.columns:
        return 0
    return signal_events.filter(pl.col("signal").str.contains("NO_TRADE")).height


def _count_by(frame: pl.DataFrame, column: str) -> pl.DataFrame:
    if frame.is_empty() or column not in frame.columns:
        return pl.DataFrame(schema={column: pl.String, "len": pl.Int64})
    return frame.group_by(column).len().sort(column)


def _report_columns(frame: pl.DataFrame) -> pl.DataFrame:
    if frame.is_empty():
        return frame
    columns = [
        "episode_id",
        "transcript_id",
        "rule_tag",
        "rule_type",
        "action_bias",
        "source_excerpt",
        "full_context_excerpt",
        "quality_flags",
        "spot_price",
        "sigma_position",
        "nearest_spot_equivalent_strike",
        "data_quality_status",
    ]
    selected = [column for column in columns if column in frame.columns]
    return frame.select(selected) if selected else frame


def _frame_markdown(frame: pl.DataFrame) -> str:
    if frame.is_empty():
        return "_No rows._"
    columns = frame.columns
    rows = ["| " + " | ".join(columns) + " |", "|" + "|".join(["---"] * len(columns)) + "|"]
    for raw in frame.head(20).to_dicts():
        rows.append("| " + " | ".join(_markdown_cell(raw.get(column)) for column in columns) + " |")
    return "\n".join(rows)


def _markdown_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("\n", "<br>").replace("|", "\\|")[:600]


def _normalize_text(text: str) -> str:
    return " ".join(text.split())


def _trim(text: str, limit: int) -> str:
    normalized = text.strip()
    return normalized[:limit]


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() == "true"


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(parsed) else parsed


def _float_or_zero(value: Any) -> float:
    parsed = _float_or_none(value)
    return parsed if parsed is not None else 0.0


def _mean_float(values: list[float | None]) -> float | None:
    clean = [value for value in values if value is not None]
    return sum(clean) / len(clean) if clean else None


def _rows_frame(rows: list[dict[str, Any]]) -> pl.DataFrame:
    return pl.DataFrame(rows, infer_schema_length=None)


def _empty_review_pack() -> pl.DataFrame:
    schema: dict[str, pl.DataType] = {
        "episode_id": pl.String,
        "transcript_id": pl.String,
        "transcript_date": pl.String,
        "availability_timestamp": pl.Datetime(time_zone="UTC"),
        "source_excerpt": pl.String,
        "full_context_excerpt": pl.String,
        "normalized_english_summary": pl.String,
        "rule_tag": pl.String,
        "rule_type": pl.String,
        "action_bias": pl.String,
        "condition_text": pl.String,
        "quality_flags": pl.String,
    }
    schema.update({field: pl.String for field in SNAPSHOT_FIELDS})
    return pl.DataFrame(schema=schema)


def _empty_suggestions() -> pl.DataFrame:
    schema: dict[str, pl.DataType] = {
        "episode_id": pl.String,
        "transcript_id": pl.String,
        "transcript_date": pl.String,
        "availability_timestamp": pl.Datetime(time_zone="UTC"),
        "source_excerpt": pl.String,
        "full_context_excerpt": pl.String,
        "normalized_english_summary": pl.String,
        "rule_tag": pl.String,
        "rule_type": pl.String,
        "action_bias": pl.String,
        "condition_text": pl.String,
        "quality_flags": pl.String,
        "suggested_decision": pl.String,
        "suggested_guru_logic_type": pl.String,
        "usable_as_context": pl.Boolean,
        "usable_as_market_map": pl.Boolean,
        "usable_as_filter": pl.Boolean,
        "usable_as_trade_rule": pl.Boolean,
        "requires_target": pl.Boolean,
        "requires_invalidation": pl.Boolean,
        "has_clear_condition": pl.Boolean,
        "has_clear_level": pl.Boolean,
        "has_clear_target": pl.Boolean,
        "has_clear_invalidation": pl.Boolean,
        "has_direction_bias": pl.Boolean,
        "has_no_trade_logic": pl.Boolean,
        "is_pre_event_logic": pl.Boolean,
        "reason_for_decision": pl.String,
        "confidence_score": pl.Float64,
        "requires_human_final_approval": pl.Boolean,
        "future_outcomes_used_in_review": pl.Boolean,
    }
    schema.update({field: pl.String for field in SNAPSHOT_FIELDS})
    return pl.DataFrame(schema=schema)


def _empty_decisions_template() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "episode_id": pl.String,
            "suggested_decision": pl.String,
            "suggested_guru_logic_type": pl.String,
            "corrected_decision": pl.String,
            "corrected_guru_logic_type": pl.String,
            "corrected_expected_direction": pl.String,
            "corrected_from_level": pl.String,
            "corrected_target_level": pl.String,
            "corrected_invalidation_level": pl.String,
            "corrected_time_horizon": pl.String,
            "reviewer_final_decision": pl.String,
            "reviewer_notes": pl.String,
        }
    )


def _empty_classification_summary() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "suggested_decision": pl.String,
            "suggested_guru_logic_type": pl.String,
            "episode_count": pl.Int64,
            "usable_as_context_count": pl.Int64,
            "usable_as_market_map_count": pl.Int64,
            "usable_as_filter_count": pl.Int64,
            "usable_as_trade_rule_count": pl.Int64,
            "human_approval_required": pl.Boolean,
        }
    )


def _empty_filter_value() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "rule_tag": pl.String,
            "guru_logic_type": pl.String,
            "filter_candidate_count": pl.Int64,
            "avoided_trade_count": pl.Int64,
            "avoided_losing_trade_count": pl.Int64,
            "avoided_winning_trade_count": pl.Int64,
            "avoided_loss_amount": pl.Float64,
            "opportunity_cost": pl.Float64,
            "net_filter_value": pl.Float64,
            "bad_trade_reduction_rate": pl.Float64,
            "false_block_rate": pl.Float64,
            "no_trade_rows_retained": pl.Int64,
            "human_approval_required": pl.Boolean,
        }
    )


def _empty_market_map_validation() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "rule_tag": pl.String,
            "guru_logic_type": pl.String,
            "market_map_candidate_count": pl.Int64,
            "zone_touch_count": pl.Int64,
            "zone_rejection_count": pl.Int64,
            "zone_acceptance_count": pl.Int64,
            "pin_count": pl.Int64,
            "squeeze_count": pl.Int64,
            "map_hit_rate": pl.Float64,
            "average_distance_to_zone": pl.Float64,
            "average_time_to_zone_touch": pl.Float64,
            "human_approval_required": pl.Boolean,
        }
    )
