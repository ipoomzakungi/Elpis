from datetime import UTC, datetime

import polars as pl
import pytest

from research_xau_vol_oi.config import Signal
from research_xau_vol_oi.guru_review_queue import (
    approved_rules_to_timeline,
    build_guru_review_queue,
    build_review_decisions_template,
    extract_numeric_levels,
    import_external_llm_rules,
    likely_srt_timestamp_artifact,
    load_approved_review_rules,
    timestamp_like_numeric_levels,
    validate_external_llm_rule,
)
from research_xau_vol_oi.llm_transcript_extractor import ActionBias, RuleType
from research_xau_vol_oi.transcript_uplift import build_transcript_conditioned_events


def _extracted_rules() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "transcript_id": "t1",
                "transcript_date": "2026-05-21",
                "availability_timestamp": datetime(2026, 5, 21, 9, 0, tzinfo=UTC),
                "source_excerpt": "00:00:00,654 --> 00:00:02,674 If price rejects OI wall 2400 invalid above 2410",
                "normalized_english_summary": "Fade ideas require rejection at a wall.",
                "rule_tag": "REJECTION_AT_WALL",
                "rule_type": RuleType.ENTRY_CONDITION.value,
                "observable_inputs": "wall_level|rejection_bar",
                "required_market_data": "asof_wall_level|close_confirmation",
                "condition": "Condition is present in excerpt.",
                "action_bias": ActionBias.FADE.value,
                "confidence_score": 0.9,
                "testability_score": 0.9,
                "leakage_risk_score": 0.2,
                "notes": "",
            },
            {
                "transcript_id": "t1",
                "transcript_date": "2026-05-21",
                "availability_timestamp": datetime(2026, 5, 21, 9, 0, tzinfo=UTC),
                "source_excerpt": "00:00:00,654 --> 00:00:02,674 If price rejects OI wall 2400 invalid above 2410",
                "normalized_english_summary": "Fade ideas require rejection at a wall.",
                "rule_tag": "REJECTION_AT_WALL",
                "rule_type": RuleType.ENTRY_CONDITION.value,
                "observable_inputs": "wall_level|rejection_bar",
                "required_market_data": "asof_wall_level|close_confirmation",
                "condition": "Condition is present in excerpt.",
                "action_bias": ActionBias.FADE.value,
                "confidence_score": 0.9,
                "testability_score": 0.9,
                "leakage_risk_score": 0.2,
                "notes": "",
            },
            {
                "transcript_id": "t2",
                "transcript_date": "2026-05-21",
                "availability_timestamp": datetime(2026, 5, 21, 10, 0, tzinfo=UTC),
                "source_excerpt": "Gamma is important today.",
                "normalized_english_summary": "Gamma context.",
                "rule_tag": "MARKET_MAKER_GAMMA",
                "rule_type": RuleType.MARKET_MAP.value,
                "observable_inputs": "gamma_proxy",
                "required_market_data": "options_chain",
                "condition": "Context-only mention.",
                "action_bias": ActionBias.WATCH_ONLY.value,
                "confidence_score": 0.5,
                "testability_score": 0.35,
                "leakage_risk_score": 0.1,
                "notes": "",
            },
        ]
    )


def _quality_audit() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "transcript_id": "t1",
                "rule_tag": "REJECTION_AT_WALL",
                "rule_type": RuleType.ENTRY_CONDITION.value,
                "action_bias": ActionBias.FADE.value,
                "rule_quality": "TESTABLE_AND_OBSERVABLE",
                "confidence_score": 0.9,
                "testability_score": 0.9,
                "leakage_risk_score": 0.2,
                "has_source_excerpt": True,
                "has_condition": True,
                "has_invalidation": True,
                "incomplete_rule": False,
                "quality_reason": "ok",
            },
            {
                "transcript_id": "t2",
                "rule_tag": "MARKET_MAKER_GAMMA",
                "rule_type": RuleType.MARKET_MAP.value,
                "action_bias": ActionBias.WATCH_ONLY.value,
                "rule_quality": "CONTEXT_ONLY",
                "confidence_score": 0.5,
                "testability_score": 0.35,
                "leakage_risk_score": 0.1,
                "has_source_excerpt": True,
                "has_condition": False,
                "has_invalidation": False,
                "incomplete_rule": False,
                "quality_reason": "context",
            },
        ]
    )


def _events() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "event_timestamp": datetime(2026, 5, 21, 9, 30, tzinfo=UTC),
                "source_bar_timestamp": datetime(2026, 5, 21, 9, 30, tzinfo=UTC),
                "signal": Signal.FADE_WALL_SHORT.value,
                "sigma_zone": "inside_1sd",
            }
        ]
    )


def test_review_queue_schema_priority_and_deduplication() -> None:
    queue = build_guru_review_queue(_extracted_rules(), _quality_audit(), _events(), pl.DataFrame())

    assert queue.height == 2
    top = queue.row(0, named=True)
    assert top["rule_tag"] == "REJECTION_AT_WALL"
    assert top["suggested_review_priority"] == "HIGH"
    assert top["reviewer_decision"] == ""
    assert top["reviewer_notes"] == ""
    assert top["duplicate_count"] == 2
    assert top["near_signal_event"] is True


def test_srt_timestamp_and_numeric_artifact_flags() -> None:
    excerpt = "00:00:00,654 --> 00:00:02,674 wall 2400"
    levels = extract_numeric_levels(excerpt)

    assert likely_srt_timestamp_artifact(excerpt)
    assert "2400" in levels
    assert {"654", "674"}.issubset(set(timestamp_like_numeric_levels(excerpt, levels)))


def test_review_decisions_template_and_approved_rules(tmp_path) -> None:
    queue = build_guru_review_queue(_extracted_rules(), _quality_audit(), _events(), pl.DataFrame())
    template = build_review_decisions_template(queue)
    decisions_path = tmp_path / "decisions.csv"
    template.with_columns(
        pl.when(pl.col("rule_tag") == "REJECTION_AT_WALL")
        .then(pl.lit("APPROVE"))
        .otherwise(pl.lit("REJECT"))
        .alias("reviewer_decision")
    ).write_csv(decisions_path)

    approved, exists = load_approved_review_rules(queue, decisions_path)

    assert exists is True
    assert approved.height == 1
    assert approved.row(0, named=True)["approved_for_research_features"] is True


def test_approved_rules_can_gate_conditioned_events(tmp_path) -> None:
    queue = build_guru_review_queue(_extracted_rules(), _quality_audit(), _events(), pl.DataFrame())
    decisions_path = tmp_path / "decisions.csv"
    build_review_decisions_template(queue).with_columns(
        pl.when(pl.col("rule_tag") == "REJECTION_AT_WALL")
        .then(pl.lit("APPROVE"))
        .otherwise(pl.lit("REJECT"))
        .alias("reviewer_decision")
    ).write_csv(decisions_path)
    approved, _ = load_approved_review_rules(queue, decisions_path)
    approved_timeline = approved_rules_to_timeline(approved)
    conditioned = build_transcript_conditioned_events(
        _events(),
        approved_timeline,
        approved_only=True,
        approved_rule_records=approved,
    )

    row = conditioned.row(0, named=True)
    assert row["active_transcript_rule_tags"] == "REJECTION_AT_WALL"
    assert row["has_rejection_at_wall_tag"] is True


def test_external_llm_import_rejects_missing_excerpt() -> None:
    with pytest.raises(ValueError, match="missing source_excerpt"):
        validate_external_llm_rule(
            {
                "transcript_id": "t1",
                "source_excerpt": "",
                "normalized_english_summary": "summary",
                "rule_tag": "OI_WALL",
                "rule_type": RuleType.MARKET_MAP.value,
                "condition": "context",
                "action_bias": ActionBias.WATCH_ONLY.value,
                "invalidation_rule": "",
                "required_market_data": "oi",
                "confidence_score": 0.8,
                "testability_score": 0.5,
                "leakage_risk_score": 0.1,
            },
            transcript_lookup={"t1": {"availability_timestamp": datetime(2026, 5, 21, tzinfo=UTC)}},
        )


def test_external_llm_import_rejects_missing_availability() -> None:
    with pytest.raises(ValueError, match="availability"):
        validate_external_llm_rule(
            {
                "transcript_id": "t1",
                "source_excerpt": "OI wall context",
                "normalized_english_summary": "summary",
                "rule_tag": "OI_WALL",
                "rule_type": RuleType.MARKET_MAP.value,
                "condition": "context",
                "action_bias": ActionBias.WATCH_ONLY.value,
                "invalidation_rule": "",
                "required_market_data": "oi",
                "confidence_score": 0.8,
                "testability_score": 0.5,
                "leakage_risk_score": 0.1,
            }
        )


def test_external_llm_import_rejects_direct_buy_sell() -> None:
    with pytest.raises(ValueError, match="direct BUY/SELL"):
        validate_external_llm_rule(
            {
                "transcript_id": "t1",
                "source_excerpt": "buy now",
                "normalized_english_summary": "buy now",
                "rule_tag": "OI_WALL",
                "rule_type": RuleType.ENTRY_CONDITION.value,
                "condition": "buy now",
                "action_bias": ActionBias.BREAKOUT.value,
                "invalidation_rule": "",
                "required_market_data": "oi",
                "confidence_score": 0.8,
                "testability_score": 0.5,
                "leakage_risk_score": 0.1,
                "availability_timestamp": datetime(2026, 5, 21, tzinfo=UTC),
            }
        )


def test_external_jsonl_import_accepts_conditional_research_logic(tmp_path) -> None:
    path = tmp_path / "external.jsonl"
    path.write_text(
        '{"transcript_id":"t1","source_excerpt":"if price rejects wall then watch",'
        '"normalized_english_summary":"conditional watch","rule_tag":"OI_WALL",'
        '"rule_type":"MARKET_MAP","condition":"if price rejects wall then watch",'
        '"action_bias":"WATCH_ONLY","invalidation_rule":"none","required_market_data":"oi",'
        '"confidence_score":0.8,"testability_score":0.5,"leakage_risk_score":0.1}\n',
        encoding="utf-8",
    )

    rows = import_external_llm_rules(
        path,
        transcript_lookup={"t1": {"availability_timestamp": datetime(2026, 5, 21, tzinfo=UTC)}},
    )

    assert len(rows) == 1
    assert rows[0]["rule_tag"] == "OI_WALL"
