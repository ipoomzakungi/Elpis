"""Codex-assisted blind review suggestions for guru episodes.

This module is deliberately deterministic. It imitates LLM-style review
reasoning from allowed pre-outcome fields only, writes suggestions for a human
reviewer, and never creates direct trading signals.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl


SUGGESTED_DECISIONS = (
    "SUGGEST_APPROVE",
    "SUGGEST_REJECT",
    "SUGGEST_NEEDS_MORE_CONTEXT",
    "SUGGEST_POST_EVENT_ONLY",
    "SUGGEST_DUPLICATE",
)
ADVERSARIAL_DECISIONS = ("PASS", "DOWNGRADE_TO_CONTEXT", "REJECT", "NEEDS_HUMAN")
THESIS_TYPES = (
    "REJECT_LEVEL",
    "BREAK_LEVEL",
    "RANGE_ROTATION",
    "PIN_OR_MAGNET",
    "SQUEEZE_CONTINUATION",
    "NO_TRADE",
    "WATCH_ONLY",
    "CONTEXT_ONLY",
    "POST_EVENT_COMMENTARY",
    "UNTESTABLE",
)
EXPECTED_DIRECTIONS = ("LONG", "SHORT", "RANGE", "NO_TRADE", "NONE")
ALLOWED_BLIND_REVIEW_COLUMNS = {
    "episode_id",
    "transcript_id",
    "transcript_date",
    "availability_timestamp",
    "source_excerpt",
    "normalized_english_summary",
    "rule_tag",
    "rule_type",
    "action_bias",
    "condition_text",
    "mentioned_levels",
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
    "spot_equivalent_strike",
    "nearest_spot_equivalent_strike",
    "data_quality_status",
    "missing_target",
    "missing_invalidation",
    "vague_logic",
    "post_event_risk",
    "numeric_artifact_risk",
    "no_market_data_match",
    "likely_context_only",
    "thesis_type",
    "expected_direction",
    "expected_from_level",
    "expected_to_level",
    "invalidation_level",
    "target_text",
    "invalidation_rule",
    "mentioned_time_horizon",
    "quality_label",
    "suggested_review_priority",
}
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


@dataclass(frozen=True)
class GuruLlmReviewResult:
    """Blind review suggestion outputs."""

    suggestions: pl.DataFrame
    adversarial: pl.DataFrame
    final_suggestions: pl.DataFrame


def run_guru_llm_review_layer(
    *,
    episodes: pl.DataFrame,
    output_dir: Path,
) -> GuruLlmReviewResult:
    """Write blind review suggestions, adversarial pass, final suggestions, and audit."""

    output_dir.mkdir(parents=True, exist_ok=True)
    suggestions = build_blind_review_suggestions(episodes)
    adversarial = build_adversarial_review(suggestions, episodes)
    final = build_final_review_suggestions(suggestions, adversarial)
    suggestions.write_csv(output_dir / "guru_llm_review_suggestions.csv")
    adversarial.write_csv(output_dir / "guru_llm_adversarial_review.csv")
    final.write_csv(output_dir / "guru_llm_review_final_suggestions.csv")
    write_guru_llm_review_audit(
        output_dir / "guru_llm_review_audit.md",
        suggestions=suggestions,
        adversarial=adversarial,
        final_suggestions=final,
    )
    return GuruLlmReviewResult(suggestions=suggestions, adversarial=adversarial, final_suggestions=final)


def build_blind_review_suggestions(episodes: pl.DataFrame) -> pl.DataFrame:
    """Suggest review decisions using only allowed pre-outcome episode fields."""

    validate_blind_review_input(episodes)
    if episodes.is_empty():
        return _empty_suggestions()
    rows = []
    for episode in episodes.to_dicts():
        suggestion = _suggest_episode(episode)
        rows.append(suggestion)
    return _rows_frame(rows) if rows else _empty_suggestions()


def validate_blind_review_input(frame: pl.DataFrame) -> None:
    """Reject accidental future-outcome columns before blind review."""

    forbidden = sorted(FORBIDDEN_REVIEW_COLUMNS.intersection({column.lower() for column in frame.columns}))
    if forbidden:
        raise ValueError(f"blind review input includes forbidden future outcome columns: {', '.join(forbidden)}")


def build_adversarial_review(suggestions: pl.DataFrame, episodes: pl.DataFrame) -> pl.DataFrame:
    """Challenge suggested approvals and flag weak extraction logic."""

    if suggestions.is_empty():
        return _empty_adversarial()
    episode_lookup = {row.get("episode_id"): row for row in episodes.to_dicts()}
    rows = []
    for suggestion in suggestions.to_dicts():
        episode = episode_lookup.get(suggestion.get("episode_id"), {})
        rows.append(_adversarial_row(suggestion, episode))
    return _rows_frame(rows) if rows else _empty_adversarial()


def build_final_review_suggestions(suggestions: pl.DataFrame, adversarial: pl.DataFrame) -> pl.DataFrame:
    """Combine blind and adversarial passes. Human approval is still required."""

    if suggestions.is_empty():
        return _empty_final_suggestions()
    adversarial_lookup = {row.get("episode_id"): row for row in adversarial.to_dicts()}
    rows = []
    for suggestion in suggestions.to_dicts():
        challenge = adversarial_lookup.get(suggestion.get("episode_id"), {})
        decision = str(suggestion.get("suggested_review_decision") or "")
        thesis_type = str(suggestion.get("corrected_thesis_type") or "")
        reason = str(suggestion.get("reason_for_decision") or "")
        adversarial_decision = str(challenge.get("adversarial_decision") or "PASS")
        if decision == "SUGGEST_APPROVE" and adversarial_decision != "PASS":
            if adversarial_decision == "REJECT":
                decision = "SUGGEST_REJECT"
            else:
                decision = "SUGGEST_NEEDS_MORE_CONTEXT"
                thesis_type = "CONTEXT_ONLY"
            reason = f"{reason} Adversarial review: {challenge.get('adversarial_reason')}"
        rows.append(
            {
                **suggestion,
                "suggested_review_decision": decision,
                "corrected_thesis_type": thesis_type,
                "adversarial_decision": adversarial_decision,
                "adversarial_reason": challenge.get("adversarial_reason") or "",
                "final_reason": reason,
                "requires_human_final_approval": True,
            }
        )
    return _rows_frame(rows) if rows else _empty_final_suggestions()


def write_guru_llm_review_audit(
    path: Path,
    *,
    suggestions: pl.DataFrame,
    adversarial: pl.DataFrame,
    final_suggestions: pl.DataFrame,
) -> None:
    """Write a short blind-review audit report."""

    lines = [
        "# Guru LLM-Style Blind Review Audit",
        "",
        "Deterministic Codex-assisted suggestions. This is not a human approval file and not a trading signal.",
        "",
        "## Anti-Leakage Guard",
        "",
        "- Blind review rejects future outcome columns before suggestion generation.",
        "- Allowed inputs are transcript excerpt, normalized summary, timestamp-visible market snapshot fields, and quality flags.",
        "- Future outcomes are not loaded or referenced during suggestion generation.",
        "",
        "## Suggestion Counts",
        "",
        _frame_markdown(_count_by(suggestions, "suggested_review_decision")),
        "",
        "## Adversarial Counts",
        "",
        _frame_markdown(_count_by(adversarial, "adversarial_decision")),
        "",
        "## Final Suggestion Counts",
        "",
        _frame_markdown(_count_by(final_suggestions, "suggested_review_decision")),
        "",
        "## Human Approval Required",
        "",
        "- `SUGGEST_APPROVE` means the logic may be eligible for human review; it is not an actual approval.",
        "- No predictive claim is allowed until human approval, walk-forward checks, placebo checks, and Monte Carlo validation pass.",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _suggest_episode(episode: dict[str, Any]) -> dict[str, Any]:
    text = " ".join(
        str(episode.get(column) or "")
        for column in ("source_excerpt", "normalized_english_summary", "condition_text")
    )
    current_thesis = _clean_choice(episode.get("thesis_type"), THESIS_TYPES, default="CONTEXT_ONLY")
    direction = _clean_choice(episode.get("expected_direction"), EXPECTED_DIRECTIONS, default="NONE")
    from_level = _clean_level(episode.get("expected_from_level"))
    target_level = _clean_level(episode.get("expected_to_level"))
    invalidation_level = _clean_level(episode.get("invalidation_level"))
    flags = _review_risk_flags(episode)
    if _bool(episode.get("numeric_artifact_risk")):
        from_level = None
        target_level = None
        invalidation_level = None
    if _bool(episode.get("post_event_risk")) or current_thesis == "POST_EVENT_COMMENTARY":
        decision = "SUGGEST_POST_EVENT_ONLY"
        thesis = "POST_EVENT_COMMENTARY"
        direction = "NONE"
        confidence = 0.9
        reason = "Excerpt or quality flags indicate post-event commentary; exclude from predictive review."
    elif _bool(episode.get("no_market_data_match")):
        decision = "SUGGEST_NEEDS_MORE_CONTEXT"
        thesis = current_thesis
        confidence = 0.55
        reason = "No timestamp-visible market snapshot matched the episode."
    elif _bool(episode.get("numeric_artifact_risk")):
        decision = "SUGGEST_REJECT"
        thesis = current_thesis
        confidence = 0.72
        reason = "Numeric level appears contaminated by SRT/timestamp artifacts; reject extracted levels."
    elif current_thesis in {"CONTEXT_ONLY", "WATCH_ONLY"} or _bool(episode.get("likely_context_only")):
        decision = "SUGGEST_NEEDS_MORE_CONTEXT"
        thesis = "WATCH_ONLY" if str(episode.get("action_bias") or "").upper() == "WATCH_ONLY" else "CONTEXT_ONLY"
        direction = "NONE"
        confidence = 0.68
        reason = "Rule appears to be market map/context, not a testable conditional trade thesis."
    elif current_thesis == "NO_TRADE":
        decision = "SUGGEST_NEEDS_MORE_CONTEXT" if _bool(episode.get("vague_logic")) else "SUGGEST_APPROVE"
        thesis = "NO_TRADE"
        direction = "NO_TRADE"
        confidence = 0.64
        reason = "No-trade rule can be reviewed as a filter, but current extraction is vague." if decision != "SUGGEST_APPROVE" else "No-trade rule has a clear conditional filter."
    elif _bool(episode.get("missing_target")) and _bool(episode.get("missing_invalidation")):
        decision = "SUGGEST_NEEDS_MORE_CONTEXT"
        thesis = current_thesis
        confidence = 0.52
        reason = "No target and no invalidation are present; do not suggest full approval."
    elif _bool(episode.get("vague_logic")):
        decision = "SUGGEST_NEEDS_MORE_CONTEXT"
        thesis = current_thesis
        confidence = 0.50
        reason = "Condition text is vague; human needs more transcript context."
    elif invalidation_level is not None and from_level is not None and _has_condition(text):
        decision = "SUGGEST_APPROVE"
        thesis = current_thesis
        confidence = 0.78
        reason = "Condition, level, invalidation, and observable inputs are present."
    else:
        decision = "SUGGEST_NEEDS_MORE_CONTEXT"
        thesis = current_thesis
        confidence = 0.55
        reason = "Rule has partial structure but is not specific enough for suggested approval."
    return {
        "episode_id": episode.get("episode_id"),
        "suggested_review_decision": decision,
        "corrected_thesis_type": thesis,
        "corrected_expected_direction": direction,
        "corrected_from_level": from_level,
        "corrected_target_level": target_level,
        "corrected_invalidation_level": invalidation_level,
        "corrected_time_horizon": episode.get("mentioned_time_horizon") or "",
        "evidence_excerpt": _excerpt(str(episode.get("source_excerpt") or "")),
        "reason_for_decision": reason,
        "confidence_score": confidence,
        "review_risk_flags": "|".join(flags),
        "requires_human_final_approval": True,
    }


def _adversarial_row(suggestion: dict[str, Any], episode: dict[str, Any]) -> dict[str, Any]:
    if suggestion.get("suggested_review_decision") != "SUGGEST_APPROVE":
        return {
            "episode_id": suggestion.get("episode_id"),
            "adversarial_decision": "PASS",
            "adversarial_reason": "No suggested approval to challenge.",
        }
    if _bool(episode.get("post_event_risk")):
        return {
            "episode_id": suggestion.get("episode_id"),
            "adversarial_decision": "REJECT",
            "adversarial_reason": "Possible post-event explanation, not a pre-event rule.",
        }
    if _bool(episode.get("numeric_artifact_risk")):
        return {
            "episode_id": suggestion.get("episode_id"),
            "adversarial_decision": "REJECT",
            "adversarial_reason": "Level may be contaminated by timestamp artifacts.",
        }
    if _clean_level(suggestion.get("corrected_invalidation_level")) is None and suggestion.get("corrected_thesis_type") not in {
        "NO_TRADE",
        "CONTEXT_ONLY",
        "WATCH_ONLY",
    }:
        return {
            "episode_id": suggestion.get("episode_id"),
            "adversarial_decision": "DOWNGRADE_TO_CONTEXT",
            "adversarial_reason": "No clear invalidation is present for a directional thesis.",
        }
    if _bool(episode.get("vague_logic")):
        return {
            "episode_id": suggestion.get("episode_id"),
            "adversarial_decision": "NEEDS_HUMAN",
            "adversarial_reason": "Condition is not specific enough; human should inspect full transcript.",
        }
    return {
        "episode_id": suggestion.get("episode_id"),
        "adversarial_decision": "PASS",
        "adversarial_reason": "Extracted rule appears specific enough for human approval review.",
    }


def _review_risk_flags(episode: dict[str, Any]) -> list[str]:
    flags = [
        "missing_target",
        "missing_invalidation",
        "vague_logic",
        "post_event_risk",
        "numeric_artifact_risk",
        "no_market_data_match",
        "likely_context_only",
    ]
    return [flag for flag in flags if _bool(episode.get(flag))]


def _has_condition(text: str) -> bool:
    return bool(re.search(r"\b(if|when|only if|provided that|requires|unless)\b|ถ้า|เมื่อ|หาก", text, flags=re.I))


def _clean_choice(value: Any, choices: tuple[str, ...], *, default: str) -> str:
    text = str(value or "").upper()
    return text if text in choices else default


def _clean_level(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if 100 <= parsed <= 10_000 else None


def _excerpt(text: str, limit: int = 260) -> str:
    normalized = " ".join(text.split())
    return normalized[:limit]


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() == "true"


def _count_by(frame: pl.DataFrame, column: str) -> pl.DataFrame:
    if frame.is_empty() or column not in frame.columns:
        return pl.DataFrame(schema={column: pl.String, "len": pl.Int64})
    return frame.group_by(column).len().sort(column)


def _frame_markdown(frame: pl.DataFrame) -> str:
    if frame.is_empty():
        return "_No rows._"
    columns = frame.columns
    rows = ["| " + " | ".join(columns) + " |", "|" + "|".join(["---"] * len(columns)) + "|"]
    for raw in frame.head(20).to_dicts():
        rows.append("| " + " | ".join(str(raw.get(column, "")) for column in columns) + " |")
    return "\n".join(rows)


def _rows_frame(rows: list[dict[str, Any]]) -> pl.DataFrame:
    return pl.DataFrame(rows, infer_schema_length=None)


def _empty_suggestions() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "episode_id": pl.String,
            "suggested_review_decision": pl.String,
            "corrected_thesis_type": pl.String,
            "corrected_expected_direction": pl.String,
            "corrected_from_level": pl.Float64,
            "corrected_target_level": pl.Float64,
            "corrected_invalidation_level": pl.Float64,
            "corrected_time_horizon": pl.String,
            "evidence_excerpt": pl.String,
            "reason_for_decision": pl.String,
            "confidence_score": pl.Float64,
            "review_risk_flags": pl.String,
            "requires_human_final_approval": pl.Boolean,
        }
    )


def _empty_adversarial() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "episode_id": pl.String,
            "adversarial_decision": pl.String,
            "adversarial_reason": pl.String,
        }
    )


def _empty_final_suggestions() -> pl.DataFrame:
    schema = dict(_empty_suggestions().schema)
    schema.update(
        {
            "adversarial_decision": pl.String,
            "adversarial_reason": pl.String,
            "final_reason": pl.String,
        }
    )
    return pl.DataFrame(schema=schema)
