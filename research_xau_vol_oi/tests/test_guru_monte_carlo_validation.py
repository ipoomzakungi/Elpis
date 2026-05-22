from datetime import UTC, datetime

import polars as pl

from research_xau_vol_oi.config import ResearchConfig, Signal
from research_xau_vol_oi.guru_monte_carlo_validation import (
    guru_monte_carlo_validation,
    markov_transition_matrix,
    run_guru_monte_carlo_validation_layer,
)


def _episodes() -> pl.DataFrame:
    rows = []
    for index in range(8):
        rows.append(
            {
                "episode_id": f"e{index}",
                "reviewer_decision": "APPROVE" if index < 2 else "",
                "rule_tag": "REJECTION_AT_WALL" if index < 4 else "NO_TRADE_DISCIPLINE",
                "thesis_type": "REJECT_LEVEL" if index < 4 else "NO_TRADE",
                "expected_direction": "SHORT" if index < 4 else "NO_TRADE",
                "sigma_position": 0.4 if index % 2 == 0 else 0.9,
                "wall_score_bucket": "high" if index < 4 else "low",
                "open_side": "ABOVE_OPEN" if index % 2 == 0 else "BELOW_OPEN",
                "vol_regime": "IV_PREMIUM",
            }
        )
    return pl.DataFrame(rows)


def _outcomes() -> pl.DataFrame:
    rows = []
    for index in range(8):
        supported = index in {0, 1, 2, 4, 6}
        rows.append(
            {
                "episode_id": f"e{index}",
                "outcome_window": "4h",
                "outcome_label": "THESIS_SUPPORTED" if supported else "THESIS_FAILED",
                "direction_correct": supported,
                "target_hit": None,
                "invalidation_hit": not supported if index < 4 else None,
                "signed_close_return": 5.0 if supported else -3.0,
                "wall_rejected": supported and index < 4,
                "wall_accepted": False,
                "stayed_inside_1sd": index >= 4,
                "broke_1sd": index < 4 and not supported,
            }
        )
    return pl.DataFrame(rows)


def _suggestions() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "episode_id": f"e{index}",
                "suggested_review_decision": "SUGGEST_APPROVE"
                if index < 3
                else "SUGGEST_NEEDS_MORE_CONTEXT"
                if index < 6
                else "SUGGEST_REJECT",
                "corrected_thesis_type": "REJECT_LEVEL" if index < 4 else "CONTEXT_ONLY",
                "corrected_expected_direction": "SHORT" if index < 4 else "NONE",
            }
            for index in range(8)
        ]
    )


def _full_context_suggestions() -> pl.DataFrame:
    decisions = [
        "SUGGEST_APPROVE_MARKET_MAP",
        "SUGGEST_APPROVE_FILTER",
        "SUGGEST_APPROVE_TRADE_RULE",
        "SUGGEST_APPROVE_CONTEXT",
        "SUGGEST_APPROVE_FILTER",
        "SUGGEST_NEEDS_MORE_CONTEXT",
        "SUGGEST_REJECT",
        "SUGGEST_POST_EVENT_ONLY",
    ]
    logic_types = [
        "OI_WALL_ZONE",
        "NO_TRADE_FILTER",
        "ENTRY_TRIGGER",
        "MARKET_MAP",
        "NO_TRADE_FILTER",
        "UNTESTABLE_OPINION",
        "UNTESTABLE_OPINION",
        "POST_EVENT_COMMENTARY",
    ]
    return pl.DataFrame(
        [
            {
                "episode_id": f"e{index}",
                "suggested_decision": decisions[index],
                "suggested_guru_logic_type": logic_types[index],
            }
            for index in range(8)
        ]
    )


def _signals() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {"event_timestamp": datetime(2026, 5, 21, 9, 0, tzinfo=UTC), "signal": Signal.NO_TRADE.value},
            {"event_timestamp": datetime(2026, 5, 21, 10, 0, tzinfo=UTC), "signal": Signal.FADE_WALL_SHORT.value},
        ]
    )


def test_permutation_p_value_schema() -> None:
    validation, _ = guru_monte_carlo_validation(
        episodes=_episodes(),
        outcomes=_outcomes(),
        final_suggestions=_suggestions(),
        signal_events=_signals(),
        config=ResearchConfig(random_seed=11),
        iterations=40,
    )
    row = validation.filter(pl.col("method") == "PERMUTATION").row(0, named=True)

    assert {"p_value", "observed_metric", "placebo_mean", "monte_carlo_pass"}.issubset(validation.columns)
    assert row["p_value"] is None or 0 <= row["p_value"] <= 1


def test_bootstrap_ci_schema() -> None:
    validation, _ = guru_monte_carlo_validation(
        episodes=_episodes(),
        outcomes=_outcomes(),
        final_suggestions=_suggestions(),
        signal_events=_signals(),
        config=ResearchConfig(random_seed=12),
        iterations=40,
    )
    rows = validation.filter(pl.col("method") == "BOOTSTRAP_CI")

    assert {"bootstrap_ci_low", "bootstrap_ci_high"}.issubset(rows.columns)
    assert rows.height > 0


def test_matched_placebo_retains_no_trade_rows() -> None:
    validation, _ = guru_monte_carlo_validation(
        episodes=_episodes(),
        outcomes=_outcomes(),
        final_suggestions=_suggestions(),
        signal_events=_signals(),
        config=ResearchConfig(random_seed=13),
        iterations=40,
    )
    matched = validation.filter(pl.col("method") == "MATCHED_MARKET_STATE_PLACEBO")

    assert matched.get_column("no_trade_rows_retained").min() == 1


def test_markov_transition_matrix_schema() -> None:
    joined = _episodes().join(_outcomes(), on="episode_id").join(_suggestions(), on="episode_id")
    markov = markov_transition_matrix(joined)

    assert {"group", "from_state", "to_state", "count", "probability"}.issubset(markov.columns)
    assert markov.height > 0


def test_monte_carlo_separates_context_filter_market_map_trade_rules() -> None:
    validation, _ = guru_monte_carlo_validation(
        episodes=_episodes(),
        outcomes=_outcomes(),
        final_suggestions=_full_context_suggestions(),
        signal_events=_signals(),
        config=ResearchConfig(random_seed=22),
        iterations=40,
    )

    rule_sets = set(validation.get_column("rule_set").to_list())
    assert "MARKET_MAP_APPROVED_PREVIEW" in rule_sets
    assert "FILTER_APPROVED_PREVIEW" in rule_sets
    assert "TRADE_RULE_APPROVED_PREVIEW" in rule_sets
    assert {"avoided_trade_count", "zone_touch_count", "map_hit_rate"}.issubset(validation.columns)


def test_monte_carlo_reproducibility_with_fixed_seed() -> None:
    args = {
        "episodes": _episodes(),
        "outcomes": _outcomes(),
        "final_suggestions": _suggestions(),
        "signal_events": _signals(),
        "config": ResearchConfig(random_seed=99),
        "iterations": 50,
    }
    first, _ = guru_monte_carlo_validation(**args)
    second, _ = guru_monte_carlo_validation(**args)

    assert first.to_dicts() == second.to_dicts()


def test_run_monte_carlo_layer_writes_outputs(tmp_path) -> None:
    result = run_guru_monte_carlo_validation_layer(
        episodes=_episodes(),
        outcomes=_outcomes(),
        final_suggestions=_suggestions(),
        signal_events=_signals(),
        output_dir=tmp_path,
        charts_dir=tmp_path / "charts",
        config=ResearchConfig(random_seed=7),
        iterations=30,
    )

    assert result.validation.height > 0
    assert (tmp_path / "guru_monte_carlo_validation.csv").exists()
    assert (tmp_path / "guru_monte_carlo_report.md").exists()
    assert (tmp_path / "charts" / "guru_monte_carlo_supported_rate.svg").exists()
