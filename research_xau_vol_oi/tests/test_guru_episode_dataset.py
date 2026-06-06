from datetime import UTC, datetime, timedelta

import polars as pl

from research_xau_vol_oi.config import ResearchConfig, Signal
from research_xau_vol_oi.guru_episode_dataset import (
    build_guru_episode_review_decisions_template,
    build_guru_decision_episodes,
    build_guru_episode_outcomes,
    extract_guru_thesis,
    run_guru_episode_dataset_layer,
    summarize_guru_episode_performance,
)


def _review_queue() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "review_id": "r1",
                "transcript_id": "t1",
                "transcript_date": "2026-05-21",
                "availability_timestamp": datetime(2026, 5, 21, 9, 30, tzinfo=UTC),
                "source_excerpt": "If price rejects wall 2400 target 2385 invalid above 2410 short setup",
                "normalized_english_summary": "Rejecting a wall can support a short thesis.",
                "reviewer_decision": "",
                "reviewer_notes": "",
                "rule_tag": "REJECTION_AT_WALL",
                "rule_type": "ENTRY_CONDITION",
                "quality_label": "TESTABLE_AND_OBSERVABLE",
                "action_bias": "FADE",
                "condition": "Requires rejection before any fade thesis.",
                "observable_inputs": "wall_level|rejection_bar",
                "required_market_data": "asof_wall_level|future_ohlc_for_evaluation",
                "extracted_numeric_levels": "2400|2385|2410",
                "timestamp_like_numeric_levels": "",
                "confidence_score": 0.9,
                "testability_score": 0.9,
                "leakage_risk_score": 0.15,
                "suggested_review_priority": "HIGH",
                "review_priority_score": 190.0,
            },
            {
                "review_id": "r2",
                "transcript_id": "t2",
                "transcript_date": "2026-05-21",
                "availability_timestamp": datetime(2026, 5, 21, 9, 35, tzinfo=UTC),
                "source_excerpt": "No trade in middle one SD.",
                "normalized_english_summary": "Middle one SD should usually be no trade.",
                "reviewer_decision": "APPROVE",
                "reviewer_notes": "approved test fixture",
                "rule_tag": "NO_TRADE_DISCIPLINE",
                "rule_type": "NO_TRADE_FILTER",
                "quality_label": "TESTABLE_AND_OBSERVABLE",
                "action_bias": "NO_TRADE",
                "condition": "When price is in middle 1SD, stay out.",
                "observable_inputs": "sigma_position",
                "required_market_data": "asof_sigma_position",
                "extracted_numeric_levels": "",
                "timestamp_like_numeric_levels": "",
                "confidence_score": 0.8,
                "testability_score": 0.8,
                "leakage_risk_score": 0.1,
                "suggested_review_priority": "HIGH",
                "review_priority_score": 180.0,
            },
            {
                "review_id": "r3",
                "transcript_id": "t3",
                "transcript_date": "2026-05-21",
                "availability_timestamp": datetime(2026, 5, 21, 22, 0, tzinfo=UTC),
                "source_excerpt": "After the close, that rejection was obvious.",
                "normalized_english_summary": "Post-event comment.",
                "reviewer_decision": "",
                "reviewer_notes": "",
                "rule_tag": "REJECTION_AT_WALL",
                "rule_type": "POST_EVENT_COMMENTARY",
                "quality_label": "POST_EVENT_COMMENTARY",
                "action_bias": "FADE",
                "condition": "Commentary after the move.",
                "observable_inputs": "post_event_price",
                "required_market_data": "future_price",
                "extracted_numeric_levels": "",
                "timestamp_like_numeric_levels": "",
                "confidence_score": 0.4,
                "testability_score": 0.1,
                "leakage_risk_score": 0.9,
                "suggested_review_priority": "HIGH",
                "review_priority_score": 160.0,
            },
            {
                "review_id": "r4",
                "transcript_id": "t4",
                "transcript_date": "2026-05-21",
                "availability_timestamp": datetime(2026, 5, 21, 9, 40, tzinfo=UTC),
                "source_excerpt": "Context only wall note.",
                "normalized_english_summary": "Context only.",
                "reviewer_decision": "",
                "reviewer_notes": "",
                "rule_tag": "OI_WALL",
                "rule_type": "MARKET_MAP",
                "quality_label": "TESTABLE_BUT_NEEDS_DATA",
                "action_bias": "WATCH_ONLY",
                "condition": "Context.",
                "observable_inputs": "wall_level",
                "required_market_data": "asof_wall_level",
                "extracted_numeric_levels": "",
                "timestamp_like_numeric_levels": "",
                "confidence_score": 0.6,
                "testability_score": 0.5,
                "leakage_risk_score": 0.1,
                "suggested_review_priority": "MEDIUM",
                "review_priority_score": 90.0,
            },
        ]
    )


def _features() -> pl.DataFrame:
    base = datetime(2026, 5, 21, 9, 0, tzinfo=UTC)
    rows = []
    for index, close in enumerate([2398.0, 2399.0, 2397.0, 2386.0, 2378.0, 2382.0]):
        timestamp = base + timedelta(minutes=30 * index)
        rows.append(
            {
                "timestamp": timestamp,
                "open": close - 1,
                "high": close + (20 if timestamp == datetime(2026, 5, 21, 9, 30, tzinfo=UTC) else 3),
                "low": close - 4,
                "close": close,
                "volume": 100 + index,
                "session_open": 2398.0,
                "annualized_iv_percent": 18.0,
                "rv_percent": 12.0,
                "vrp": 6.0,
                "upper_1sd": 2410.0,
                "lower_1sd": 2385.0,
                "upper_2sd": 2422.0,
                "lower_2sd": 2370.0,
                "sigma_position": (close - 2398.0) / 12.0,
                "sigma_zone": "inside_1sd",
                "data_quality_state": "OK",
                "vol_regime": "IV_PREMIUM",
                "wall_level": 2400.0,
                "wall_score": 0.35,
                "wall_score_bucket": "high",
                "wall_side": "resistance",
                "basis": 4.0,
            }
        )
    return pl.DataFrame(rows)


def _signals() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "event_timestamp": datetime(2026, 5, 21, 9, 45, tzinfo=UTC),
                "signal": Signal.NO_TRADE.value,
            },
            {
                "event_timestamp": datetime(2026, 5, 21, 10, 0, tzinfo=UTC),
                "signal": Signal.FADE_WALL_SHORT.value,
            },
        ]
    )


def test_market_snapshot_uses_only_rows_at_or_before_availability() -> None:
    episodes = build_guru_decision_episodes(
        review_queue=_review_queue(),
        feature_table=_features(),
        signal_events=_signals(),
    )
    row = episodes.filter(pl.col("transcript_id") == "t1").row(0, named=True)

    assert row["data_available_timestamp"] == datetime(2026, 5, 21, 9, 30, tzinfo=UTC)
    assert row["spot_price"] == 2399.0
    assert row["no_trade_signal_rows_retained"] == 1


def test_future_outcomes_exclude_availability_bar() -> None:
    episodes = build_guru_decision_episodes(
        review_queue=_review_queue(),
        feature_table=_features(),
        signal_events=_signals(),
    )
    outcomes = build_guru_episode_outcomes(episodes, _features())
    one_hour = outcomes.filter(
        (pl.col("transcript_id") == "t1") & (pl.col("outcome_window") == "1h")
    ).row(0, named=True)

    assert one_hour["evaluation_data_start"] == datetime(2026, 5, 21, 10, 0, tzinfo=UTC)
    assert one_hour["target_hit"] is True
    assert one_hour["invalidation_hit"] is False
    assert one_hour["outcome_label"] == "THESIS_SUPPORTED"


def test_review_required_sample_and_outputs(tmp_path) -> None:
    queue = _review_queue().with_columns(pl.lit("").alias("reviewer_decision"))
    result = run_guru_episode_dataset_layer(
        review_queue=queue,
        feature_table=_features(),
        signal_events=_signals(),
        trades=pl.DataFrame(),
        output_dir=tmp_path,
        charts_dir=tmp_path / "charts",
        config=ResearchConfig(),
    )

    assert result.episodes.height == 3
    assert result.review_sample.height == 3
    assert result.final_decision == "GURU_EPISODE_REVIEW_REQUIRED"
    assert result.approved_only_can_run is False
    assert result.review_decisions_template.height == 3
    assert (tmp_path / "guru_decision_episodes.csv").exists()
    assert (tmp_path / "guru_episode_review_dashboard.html").exists()
    assert (tmp_path / "guru_episode_review_decisions_template.csv").exists()
    assert (tmp_path / "guru_episode_review_guide.md").exists()
    assert (tmp_path / "charts" / "guru_episode_target_hit_rate.svg").exists()


def test_review_dashboard_separates_transcript_snapshot_and_evaluation(tmp_path) -> None:
    result = run_guru_episode_dataset_layer(
        review_queue=_review_queue(),
        feature_table=_features(),
        signal_events=_signals(),
        trades=pl.DataFrame(),
        output_dir=tmp_path,
        charts_dir=tmp_path / "charts",
    )
    dashboard = (tmp_path / "guru_episode_review_dashboard.html").read_text(encoding="utf-8")
    guide = (tmp_path / "guru_episode_review_guide.md").read_text(encoding="utf-8")

    assert "1. Transcript Section" in dashboard
    assert "2. Market Snapshot Section" in dashboard
    assert "3. Outcome Section · EVALUATION ONLY" in dashboard
    assert "4. Reviewer Fields" in dashboard
    assert "reviewer_decision" in dashboard
    assert "do not use future outcomes" in guide.lower()
    assert result.review_decisions_template.height == result.review_sample.height


def test_review_decisions_template_schema_and_quality_flags() -> None:
    episodes = build_guru_decision_episodes(
        review_queue=_review_queue(),
        feature_table=_features(),
        signal_events=_signals(),
    )
    template = build_guru_episode_review_decisions_template(episodes)

    assert {
        "episode_id",
        "reviewer_decision",
        "corrected_thesis_type",
        "corrected_expected_direction",
        "corrected_from_level",
        "corrected_target_level",
        "corrected_invalidation_level",
        "corrected_time_horizon",
        "reviewer_notes",
        "missing_target",
        "missing_invalidation",
        "post_event_risk",
        "numeric_artifact_risk",
        "likely_context_only",
    }.issubset(template.columns)
    post = template.filter(pl.col("transcript_id") == "t3").row(0, named=True)
    assert post["post_event_risk"] is True
    assert post["reviewer_decision"] == ""


def test_approved_only_mode_uses_only_approved_records(tmp_path) -> None:
    result = run_guru_episode_dataset_layer(
        review_queue=_review_queue(),
        feature_table=_features(),
        signal_events=_signals(),
        trades=pl.DataFrame(),
        output_dir=tmp_path,
        charts_dir=tmp_path / "charts",
        approved_only=True,
    )

    assert result.episodes.height == 1
    assert result.episodes.row(0, named=True)["reviewer_decision"] == "APPROVE"
    assert result.approved_only_can_run is True


def test_thesis_extraction_parses_levels_direction_and_invalidation() -> None:
    row = {
        **_review_queue().row(0, named=True),
        "extracted_numeric_levels": "169|2400|2385|2410",
        "timestamp_like_numeric_levels": "169",
    }
    thesis = extract_guru_thesis(row, {"wall_level": 2400.0})

    assert thesis["thesis_type"] == "REJECT_LEVEL"
    assert thesis["expected_direction"] == "SHORT"
    assert thesis["expected_from_level"] == 2400.0
    assert thesis["expected_to_level"] == 2385.0
    assert thesis["invalidation_level"] == 2410.0


def test_post_session_same_session_outcome_is_untestable() -> None:
    episodes = build_guru_decision_episodes(
        review_queue=_review_queue(),
        feature_table=_features(),
        signal_events=_signals(),
        config=ResearchConfig(session_close_hour_utc=21),
    )
    post = episodes.filter(pl.col("transcript_id") == "t3").row(0, named=True)
    outcomes = build_guru_episode_outcomes(episodes, _features(), config=ResearchConfig(session_close_hour_utc=21))
    session_close = outcomes.filter(
        (pl.col("transcript_id") == "t3") & (pl.col("outcome_window") == "session_close")
    ).row(0, named=True)

    assert post["published_after_session_close"] is True
    assert post["predictive_claim_allowed"] is False
    assert session_close["outcome_label"] == "UNTESTABLE"


def test_performance_summary_schema_and_recommendation() -> None:
    episodes = build_guru_decision_episodes(
        review_queue=_review_queue(),
        feature_table=_features(),
        signal_events=_signals(),
    )
    outcomes = build_guru_episode_outcomes(episodes, _features())
    performance = summarize_guru_episode_performance(episodes, outcomes)

    assert {
        "rule_tag",
        "thesis_type",
        "episode_count",
        "approved_count",
        "target_hit_rate",
        "invalidation_hit_rate",
        "direction_accuracy",
        "recommendation",
    }.issubset(performance.columns)
    assert "REVIEW_REQUIRED" in set(performance.get_column("recommendation").to_list())
