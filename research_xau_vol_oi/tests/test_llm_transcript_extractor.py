from datetime import UTC, datetime

import polars as pl
import pytest

from research_xau_vol_oi.llm_transcript_extractor import (
    ActionBias,
    RuleQuality,
    RuleType,
    build_rule_quality_audit,
    classify_rule_quality,
    extract_structured_rule_records,
    find_source_excerpt,
    records_to_frame,
    validate_rule_record,
)


def _timeline(tmp_path, text: str, tags: str = "OI_WALL|REJECTION_AT_WALL") -> pl.DataFrame:
    path = tmp_path / "2026-05-21 - transcript [abc123].txt"
    path.write_text(text, encoding="utf-8")
    return pl.DataFrame(
        [
            {
                "transcript_id": "abc123",
                "source_path": str(path),
                "transcript_date": "2026-05-21",
                "availability_timestamp": datetime(2026, 5, 21, 21, 1, tzinfo=UTC),
                "title": "XAU OI Wall",
                "detected_rule_tags": tags,
                "confidence_score": 0.8,
                "extracted_numeric_levels": "",
                "extracted_basis_values": "",
                "extracted_iv_values": "",
                "extracted_sd_values": "",
                "extracted_oi_strikes": "",
                "notes": "",
            }
        ]
    )


def test_extractor_outputs_schema_and_source_excerpt(tmp_path) -> None:
    timeline = _timeline(
        tmp_path,
        "If price rejects the OI wall at 2400 and close back below, invalid if it breaks above.",
    )

    records = extract_structured_rule_records(timeline)
    frame = records_to_frame(records)

    assert {
        "transcript_id",
        "source_excerpt",
        "normalized_english_summary",
        "rule_tag",
        "rule_type",
        "action_bias",
        "confidence_score",
        "testability_score",
        "leakage_risk_score",
    }.issubset(frame.columns)
    assert frame.filter(pl.col("rule_tag") == "OI_WALL").height == 1
    assert "OI wall" in frame.row(0, named=True)["source_excerpt"]


def test_testable_condition_with_invalidation() -> None:
    quality = classify_rule_quality(
        rule_tag="REJECTION_AT_WALL",
        rule_type=RuleType.ENTRY_CONDITION,
        source_excerpt="If price rejects 2400 and close back below, invalid if it breaks above.",
    )

    assert quality == RuleQuality.TESTABLE_AND_OBSERVABLE


def test_level_without_invalidation_is_incomplete(tmp_path) -> None:
    timeline = _timeline(
        tmp_path,
        "If price rejects OI wall 2400 then watch fade setup.",
        tags="REJECTION_AT_WALL",
    )
    audit = build_rule_quality_audit(records_to_frame(extract_structured_rule_records(timeline)))
    row = audit.row(0, named=True)

    assert row["rule_quality"] == RuleQuality.TESTABLE_BUT_NEEDS_DATA.value
    assert row["incomplete_rule"] is True


def test_vague_statement_context_only() -> None:
    quality = classify_rule_quality(
        rule_tag="MARKET_MAKER_GAMMA",
        rule_type=RuleType.MARKET_MAP,
        source_excerpt="Gamma is important today.",
    )

    assert quality == RuleQuality.CONTEXT_ONLY


def test_post_event_commentary_classified() -> None:
    quality = classify_rule_quality(
        rule_tag="OI_WALL",
        rule_type=RuleType.MARKET_MAP,
        source_excerpt="Yesterday price already rejected the OI wall after the move happened.",
    )

    assert quality == RuleQuality.POST_EVENT_COMMENTARY


def test_leakage_risk_rejected() -> None:
    quality = classify_rule_quality(
        rule_tag="ACCEPTANCE_CLOSE_CONFIRMATION",
        rule_type=RuleType.ENTRY_CONDITION,
        source_excerpt="Use the future close after the event to decide the breakout.",
    )

    assert quality == RuleQuality.REJECT_LEAKAGE_RISK


def test_validate_json_record_rejects_trade_like_unknown_tag() -> None:
    record = {
        "transcript_id": "abc",
        "transcript_date": "2026-05-21",
        "availability_timestamp": "2026-05-21T21:01:00+00:00",
        "source_excerpt": "buy now",
        "normalized_english_summary": "bad",
        "rule_tag": "BUY_SIGNAL",
        "rule_type": RuleType.ENTRY_CONDITION.value,
        "observable_inputs": "price",
        "required_market_data": "price",
        "condition": "buy now",
        "action_bias": ActionBias.BREAKOUT.value,
        "confidence_score": 0.9,
        "testability_score": 0.9,
        "leakage_risk_score": 0.1,
        "notes": "",
    }

    with pytest.raises(ValueError, match="unsupported rule_tag"):
        validate_rule_record(record)


def test_find_source_excerpt_uses_original_text() -> None:
    excerpt = find_source_excerpt(
        text="noise before. ปิดเหนือ OI wall 2400 แล้วค่อยดู. noise after.",
        title="",
        rule_tag="ACCEPTANCE_CLOSE_CONFIRMATION",
        width=80,
    )

    assert "ปิดเหนือ" in excerpt
