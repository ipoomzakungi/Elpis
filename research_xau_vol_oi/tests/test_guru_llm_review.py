from datetime import UTC, datetime

import polars as pl
import pytest

from research_xau_vol_oi.guru_llm_review import (
    build_adversarial_review,
    build_blind_review_suggestions,
    build_final_review_suggestions,
    run_guru_llm_review_layer,
)


def _episodes() -> pl.DataFrame:
    base = {
        "transcript_date": "2026-05-21",
        "availability_timestamp": datetime(2026, 5, 21, 9, 30, tzinfo=UTC),
        "source_excerpt": "If price rejects wall 2400 invalid above 2410 short.",
        "normalized_english_summary": "Rejection at wall can support a short.",
        "rule_tag": "REJECTION_AT_WALL",
        "rule_type": "ENTRY_CONDITION",
        "action_bias": "FADE",
        "condition_text": "If price rejects wall, fade.",
        "mentioned_levels": "2400|2410",
        "spot_price": 2398.0,
        "session_open": 2390.0,
        "open_side": "ABOVE_OPEN",
        "annualized_iv": 18.0,
        "realized_vol": 12.0,
        "vrp": 6.0,
        "one_sd_level_upper": 2410.0,
        "one_sd_level_lower": 2380.0,
        "two_sd_level_upper": 2420.0,
        "two_sd_level_lower": 2370.0,
        "sigma_position": 0.5,
        "nearest_wall_above": 2400.0,
        "nearest_wall_below": None,
        "nearest_wall_above_score": 0.4,
        "nearest_wall_below_score": None,
        "basis": 2.0,
        "nearest_spot_equivalent_strike": 2400.0,
        "data_quality_status": "OK",
        "quality_label": "TESTABLE_AND_OBSERVABLE",
        "suggested_review_priority": "HIGH",
        "thesis_type": "REJECT_LEVEL",
        "expected_direction": "SHORT",
        "expected_from_level": 2400.0,
        "expected_to_level": None,
        "invalidation_level": 2410.0,
        "target_text": "",
        "invalidation_rule": "invalid above 2410",
        "mentioned_time_horizon": "1h",
        "missing_target": False,
        "missing_invalidation": False,
        "vague_logic": False,
        "post_event_risk": False,
        "numeric_artifact_risk": False,
        "no_market_data_match": False,
        "likely_context_only": False,
    }
    return pl.DataFrame(
        [
            {"episode_id": "approve_candidate", "transcript_id": "t1", **base},
            {
                "episode_id": "post_event",
                "transcript_id": "t2",
                **{
                    **base,
                    "source_excerpt": "After the move this rejection worked.",
                    "rule_type": "POST_EVENT_COMMENTARY",
                    "thesis_type": "POST_EVENT_COMMENTARY",
                    "post_event_risk": True,
                },
            },
            {
                "episode_id": "missing_levels",
                "transcript_id": "t3",
                **{
                    **base,
                    "source_excerpt": "Maybe wall matters.",
                    "condition_text": "Maybe wall matters.",
                    "expected_from_level": None,
                    "invalidation_level": None,
                    "missing_target": True,
                    "missing_invalidation": True,
                    "vague_logic": True,
                },
            },
            {
                "episode_id": "numeric_artifact",
                "transcript_id": "t4",
                **{
                    **base,
                    "source_excerpt": "00:00:00,169 --> 00:00:02,200 wall 2400",
                    "numeric_artifact_risk": True,
                },
            },
        ]
    )


def test_blind_review_rejects_future_outcome_columns() -> None:
    contaminated = _episodes().with_columns(pl.lit(True).alias("target_hit"))

    with pytest.raises(ValueError, match="forbidden future outcome"):
        build_blind_review_suggestions(contaminated)


def test_post_event_commentary_downgrade() -> None:
    suggestions = build_blind_review_suggestions(_episodes())
    row = suggestions.filter(pl.col("episode_id") == "post_event").row(0, named=True)

    assert row["suggested_review_decision"] == "SUGGEST_POST_EVENT_ONLY"
    assert row["corrected_thesis_type"] == "POST_EVENT_COMMENTARY"


def test_missing_target_invalidation_downgrade() -> None:
    suggestions = build_blind_review_suggestions(_episodes())
    row = suggestions.filter(pl.col("episode_id") == "missing_levels").row(0, named=True)

    assert row["suggested_review_decision"] == "SUGGEST_NEEDS_MORE_CONTEXT"
    assert row["corrected_thesis_type"] != "POST_EVENT_COMMENTARY"


def test_numeric_artifact_rejection() -> None:
    suggestions = build_blind_review_suggestions(_episodes())
    row = suggestions.filter(pl.col("episode_id") == "numeric_artifact").row(0, named=True)

    assert row["suggested_review_decision"] == "SUGGEST_REJECT"
    assert row["corrected_from_level"] is None
    assert row["corrected_invalidation_level"] is None


def test_adversarial_downgrade() -> None:
    suggestions = pl.DataFrame(
        [
            {
                "episode_id": "missing_levels",
                "suggested_review_decision": "SUGGEST_APPROVE",
                "corrected_thesis_type": "REJECT_LEVEL",
                "corrected_expected_direction": "SHORT",
                "corrected_from_level": 2400.0,
                "corrected_target_level": None,
                "corrected_invalidation_level": None,
                "corrected_time_horizon": "1h",
                "evidence_excerpt": "wall",
                "reason_for_decision": "test",
                "confidence_score": 0.8,
                "review_risk_flags": "",
                "requires_human_final_approval": True,
            }
        ]
    )
    adversarial = build_adversarial_review(suggestions, _episodes())
    final = build_final_review_suggestions(suggestions, adversarial)

    assert adversarial.row(0, named=True)["adversarial_decision"] == "DOWNGRADE_TO_CONTEXT"
    assert final.row(0, named=True)["suggested_review_decision"] == "SUGGEST_NEEDS_MORE_CONTEXT"
    assert final.row(0, named=True)["requires_human_final_approval"] is True


def test_run_llm_review_layer_writes_outputs(tmp_path) -> None:
    result = run_guru_llm_review_layer(episodes=_episodes(), output_dir=tmp_path)

    assert result.suggestions.height == 4
    assert (tmp_path / "guru_llm_review_suggestions.csv").exists()
    assert (tmp_path / "guru_llm_adversarial_review.csv").exists()
    assert (tmp_path / "guru_llm_review_final_suggestions.csv").exists()
    assert (tmp_path / "guru_llm_review_audit.md").exists()
