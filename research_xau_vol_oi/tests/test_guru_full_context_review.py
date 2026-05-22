from datetime import UTC, datetime

import polars as pl
import pytest

from research_xau_vol_oi.guru_full_context_review import (
    build_full_context_review_decisions_template,
    build_full_context_review_pack,
    build_full_context_review_suggestions,
    calculate_filter_value,
    classify_guru_logic,
    guru_full_context_final_decision,
    run_guru_full_context_review_layer,
    validate_market_maps,
)


def _episodes() -> pl.DataFrame:
    base = {
        "transcript_id": "t1",
        "transcript_date": "2026-05-21",
        "availability_timestamp": datetime(2026, 5, 21, 9, 30, tzinfo=UTC),
        "full_context_excerpt": "",
        "normalized_english_summary": "Wall and range logic.",
        "rule_type": "MARKET_MAP",
        "action_bias": "WATCH_ONLY",
        "condition_text": "When price approaches the wall, watch reaction.",
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
        "nearest_spot_equivalent_strike": 2400.0,
        "data_quality_status": "OK",
        "missing_target": True,
        "missing_invalidation": True,
        "vague_logic": False,
        "post_event_risk": False,
        "numeric_artifact_risk": False,
        "no_market_data_match": False,
        "likely_context_only": False,
    }
    return pl.DataFrame(
        [
            {
                "episode_id": "map",
                "source_excerpt": "OI wall 2400 is a key zone to watch.",
                "rule_tag": "OI_WALL",
                **base,
            },
            {
                "episode_id": "filter",
                "source_excerpt": "No trade in middle 1SD unless a strong wall confirms.",
                "rule_tag": "NO_TRADE_DISCIPLINE",
                "action_bias": "NO_TRADE",
                **{key: value for key, value in base.items() if key != "action_bias"},
            },
            {
                "episode_id": "trade",
                "source_excerpt": "If price rejects wall 2400, fade short invalid above 2410.",
                "rule_tag": "REJECTION_AT_WALL",
                "rule_type": "ENTRY_CONDITION",
                "action_bias": "FADE",
                "missing_target": True,
                "missing_invalidation": False,
                **{key: value for key, value in base.items() if key not in {"rule_type", "action_bias", "missing_target", "missing_invalidation"}},
            },
            {
                "episode_id": "post",
                "source_excerpt": "After the move this wall already worked.",
                "rule_tag": "OI_WALL",
                "rule_type": "POST_EVENT_COMMENTARY",
                "post_event_risk": True,
                **{key: value for key, value in base.items() if key not in {"rule_type", "post_event_risk"}},
            },
        ]
    )


def _outcomes() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "episode_id": "map",
                "outcome_window": "4h",
                "outcome_label": "THESIS_SUPPORTED",
                "wall_rejected": True,
                "wall_accepted": False,
                "stayed_inside_1sd": False,
                "broke_1sd": False,
                "broke_2sd": False,
                "max_favorable_excursion": 8.0,
                "max_adverse_excursion": -2.0,
            },
            {
                "episode_id": "filter",
                "outcome_window": "4h",
                "outcome_label": "THESIS_SUPPORTED",
                "wall_rejected": False,
                "wall_accepted": False,
                "stayed_inside_1sd": True,
                "broke_1sd": False,
                "broke_2sd": False,
                "max_favorable_excursion": 1.0,
                "max_adverse_excursion": -5.0,
            },
            {
                "episode_id": "trade",
                "outcome_window": "4h",
                "outcome_label": "THESIS_FAILED",
                "wall_rejected": False,
                "wall_accepted": True,
                "stayed_inside_1sd": False,
                "broke_1sd": True,
                "broke_2sd": False,
                "max_favorable_excursion": 2.0,
                "max_adverse_excursion": -7.0,
            },
        ]
    )


def _signals() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {"event_timestamp": datetime(2026, 5, 21, 9, 30, tzinfo=UTC), "signal": "NO_TRADE_MIDDLE"},
            {"event_timestamp": datetime(2026, 5, 21, 10, 0, tzinfo=UTC), "signal": "FADE_WALL_SHORT"},
        ]
    )


def test_full_context_window_excludes_future_outcome_columns() -> None:
    contaminated = _episodes().with_columns(pl.lit(True).alias("target_hit"))

    with pytest.raises(ValueError, match="forbidden future outcome"):
        build_full_context_review_pack(contaminated, pl.DataFrame())


def test_market_map_approval_does_not_require_target_invalidation() -> None:
    row = build_full_context_review_pack(_episodes(), pl.DataFrame()).filter(pl.col("episode_id") == "map").row(0, named=True)
    decision = classify_guru_logic(row)

    assert decision["suggested_decision"] == "SUGGEST_APPROVE_MARKET_MAP"
    assert decision["usable_as_market_map"] is True
    assert decision["requires_target"] is False


def test_no_trade_filter_approval_does_not_require_direction_or_target() -> None:
    row = build_full_context_review_pack(_episodes(), pl.DataFrame()).filter(pl.col("episode_id") == "filter").row(0, named=True)
    decision = classify_guru_logic(row)

    assert decision["suggested_decision"] == "SUGGEST_APPROVE_FILTER"
    assert decision["usable_as_filter"] is True
    assert decision["has_no_trade_logic"] is True


def test_trade_rule_approval_requires_condition_plus_target_or_invalidation() -> None:
    suggestions = build_full_context_review_suggestions(build_full_context_review_pack(_episodes(), pl.DataFrame()))
    row = suggestions.filter(pl.col("episode_id") == "trade").row(0, named=True)

    assert row["suggested_decision"] == "SUGGEST_APPROVE_TRADE_RULE"
    assert row["has_clear_condition"] is True
    assert row["has_clear_invalidation"] is True


def test_post_event_commentary_excluded_from_predictive_validation() -> None:
    suggestions = build_full_context_review_suggestions(build_full_context_review_pack(_episodes(), pl.DataFrame()))
    row = suggestions.filter(pl.col("episode_id") == "post").row(0, named=True)

    assert row["suggested_decision"] == "SUGGEST_POST_EVENT_ONLY"
    assert row["is_pre_event_logic"] is False


def test_filter_value_calculation_retains_no_trade_rows() -> None:
    suggestions = build_full_context_review_suggestions(build_full_context_review_pack(_episodes(), pl.DataFrame()))
    result = calculate_filter_value(suggestions, _episodes(), _outcomes(), _signals(), pl.DataFrame())

    assert result.height == 1
    assert result.row(0, named=True)["no_trade_rows_retained"] == 1
    assert {"avoided_trade_count", "net_filter_value", "false_block_rate"}.issubset(result.columns)


def test_market_map_validation_schema() -> None:
    suggestions = build_full_context_review_suggestions(build_full_context_review_pack(_episodes(), pl.DataFrame()))
    result = validate_market_maps(suggestions, _episodes(), _outcomes())

    assert result.height == 1
    assert {"zone_touch_count", "map_hit_rate", "average_distance_to_zone"}.issubset(result.columns)


def test_decision_template_and_final_decision() -> None:
    suggestions = build_full_context_review_suggestions(build_full_context_review_pack(_episodes(), pl.DataFrame()))
    template = build_full_context_review_decisions_template(suggestions)

    assert "reviewer_final_decision" in template.columns
    assert guru_full_context_final_decision(suggestions) == "GURU_LOGIC_FILTER_CANDIDATE"


def test_run_full_context_review_layer_writes_outputs(tmp_path) -> None:
    result = run_guru_full_context_review_layer(
        episodes=_episodes(),
        transcript_timeline=pl.DataFrame(),
        outcomes=_outcomes(),
        signal_events=_signals(),
        trades=pl.DataFrame(),
        output_dir=tmp_path,
    )

    assert result.review_pack.height == 4
    assert (tmp_path / "guru_full_context_review_pack.csv").exists()
    assert (tmp_path / "guru_full_context_review_suggestions.csv").exists()
    assert (tmp_path / "guru_filter_value_report.csv").exists()
