import polars as pl

from research_xau_vol_oi.research_decision_gate import (
    evaluate_research_decision_gates,
    run_research_decision_gate,
)


def _gate_status(result, gate_name: str) -> str:
    rows = result.gate_report.filter(pl.col("gate_name") == gate_name).to_dicts()
    assert rows
    return str(rows[0]["status"])


def _gate_blockers(result, gate_name: str) -> str:
    rows = result.gate_report.filter(pl.col("gate_name") == gate_name).to_dicts()
    assert rows
    return str(rows[0]["blocking_issues"])


def _passing_data_inputs(rows: int = 3) -> dict[str, pl.DataFrame | str]:
    dates = [f"2026-05-{10 + index:02d}" for index in range(rows)]
    return {
        "transcript_market_coverage_alignment": pl.DataFrame(
            {
                "transcript_date": dates,
                "can_run_full_vol_oi_validation": [True] * rows,
                "has_xau_price_data": [True] * rows,
                "has_cme_options_oi_data": [True] * rows,
                "has_cme_iv_data": [True] * rows,
                "has_basis_data": [True] * rows,
            }
        ),
        "cme_history_coverage_report": pl.DataFrame(
            {
                "complete_validation_day": [True] * rows,
                "has_xau_spot_or_proxy_price": [True] * rows,
                "has_basis": [True] * rows,
                "has_iv_context": [True] * rows,
                "has_cme_options_oi": [True] * rows,
                "has_oi_change": [True] * rows,
                "has_intraday_volume": [True] * rows,
            }
        ),
        "market_data_coverage_manifest": pl.DataFrame(
            {
                "source_name": ["local"],
                "key_columns_detected": ["oi_change volume"],
            }
        ),
    }


def _baseline_inputs() -> dict[str, pl.DataFrame | str]:
    return {
        "gold_baseline_metrics": pl.DataFrame(
            [
                {
                    "stage": "BASELINE_TREND",
                    "scenario_family": "gold_trend_baseline",
                    "evaluation_type": "full_sample",
                    "trade_count": 50,
                    "sample_size_warning": False,
                },
                {
                    "stage": "BASELINE_IV_RANGE",
                    "scenario_family": "iv_range_baseline",
                    "evaluation_type": "full_sample",
                    "trade_count": 50,
                    "sample_size_warning": False,
                },
                {
                    "stage": "BASELINE_WALL_REACTION",
                    "scenario_family": "wall_reaction_baseline",
                    "evaluation_type": "full_sample",
                    "trade_count": 50,
                    "sample_size_warning": False,
                },
                {
                    "stage": "A_OI_FRESHNESS_VOLUME",
                    "scenario_family": "cme_feature_stage",
                    "evaluation_type": "full_sample",
                    "trade_count": 50,
                    "uplift_vs_best_baseline": 1.0,
                    "sample_size_warning": False,
                    "permutation_pass": False,
                    "matched_placebo_pass": False,
                },
                {
                    "stage": "A_OI_FRESHNESS_VOLUME",
                    "scenario_family": "cme_feature_stage",
                    "evaluation_type": "cost_stress",
                    "trade_count": 50,
                    "cost_multiplier": 2,
                },
            ]
        )
    }


def test_data_insufficient_blocks_money_readiness() -> None:
    inputs = _baseline_inputs()
    inputs.update(
        {
            "transcript_market_coverage_alignment": pl.DataFrame(
                {
                    "can_run_full_vol_oi_validation": [True],
                    "has_xau_price_data": [True],
                    "has_cme_options_oi_data": [True],
                    "has_cme_iv_data": [True],
                    "has_basis_data": [True],
                }
            ),
            "cme_history_coverage_report": pl.DataFrame(
                {
                    "complete_validation_day": [False],
                    "has_xau_spot_or_proxy_price": [True],
                    "has_basis": [True],
                    "has_iv_context": [True],
                    "has_cme_options_oi": [True],
                    "has_oi_change": [True],
                    "has_intraday_volume": [True],
                }
            ),
        }
    )

    result = evaluate_research_decision_gates(inputs, min_validation_dates=5)

    assert result.final_label == "NOT_READY_DATA_INSUFFICIENT"
    assert _gate_status(result, "MONEY_READINESS_GATE") == "FAIL"
    assert "enough_cme_validation_dates" in _gate_blockers(result, "DATA_COVERAGE_GATE")


def test_small_sample_blocks_validated_market_map_label() -> None:
    inputs = _passing_data_inputs()
    inputs.update(_baseline_inputs())
    inputs["market_map_precision_report"] = pl.DataFrame(
        [
            {
                "row_type": "comparison",
                "decision_label": "MAP_USEFUL_NOT_TRADABLE",
                "event_count": 3,
                "sample_size_warning": True,
                "touch_uplift_vs_control": 0.2,
            }
        ]
    )

    result = evaluate_research_decision_gates(inputs, min_validation_dates=2)

    assert _gate_status(result, "MARKET_MAP_GATE") == "FAIL"
    assert "sample_size_sufficient" in _gate_blockers(result, "MARKET_MAP_GATE")
    assert result.final_label != "READY_FOR_PAPER_TRADING"


def test_failed_placebo_blocks_filter_gate() -> None:
    inputs = _passing_data_inputs()
    inputs.update(_baseline_inputs())
    inputs["filter_avoided_pnl_report"] = pl.DataFrame(
        [
            {
                "control_type": "actual_no_trade_labels",
                "avoided_losing_trade_count": 30,
                "avoided_winning_trade_count": 10,
                "avoided_loss_amount": 100.0,
                "net_filter_value": 50.0,
                "false_block_rate": 0.25,
                "uplift_vs_matched_state_placebo": -1.0,
                "sample_size_warning": False,
            }
        ]
    )
    inputs["transcript_walk_forward_uplift"] = pl.DataFrame({"pass_fail": ["FAIL"]})
    inputs["guru_monte_carlo_validation"] = pl.DataFrame({"monte_carlo_pass": [False]})

    result = evaluate_research_decision_gates(inputs, min_validation_dates=2)

    assert _gate_status(result, "GURU_FILTER_GATE") == "FAIL"
    assert "walk_forward_passes" in _gate_blockers(result, "GURU_FILTER_GATE")
    assert "placebo_passes" in _gate_blockers(result, "GURU_FILTER_GATE")


def test_positive_filter_proxy_without_real_pnl_does_not_pass_filter_gate() -> None:
    inputs = _passing_data_inputs()
    inputs.update(_baseline_inputs())
    inputs["guru_filter_value_report"] = pl.DataFrame(
        [
            {
                "rule_tag": "NO_TRADE_DISCIPLINE",
                "net_filter_value": 100.0,
                "avoided_loss_amount": 0.0,
                "human_approval_required": True,
            }
        ]
    )

    result = evaluate_research_decision_gates(inputs, min_validation_dates=2)

    assert _gate_status(result, "GURU_FILTER_GATE") == "FAIL"
    assert "not_proxy_only" in _gate_blockers(result, "GURU_FILTER_GATE")


def test_trade_rule_without_target_invalidation_cannot_pass_trade_gate() -> None:
    inputs = _passing_data_inputs()
    inputs.update(_baseline_inputs())
    inputs["guru_logic_classification_summary"] = pl.DataFrame(
        [
            {
                "usable_as_context_count": 1,
                "usable_as_market_map_count": 0,
                "usable_as_filter_count": 0,
                "usable_as_trade_rule_count": 1,
                "human_approval_required": True,
            }
        ]
    )
    inputs["score_threshold_performance"] = pl.DataFrame(
        [
            {
                "scenario_type": "vol_oi_score",
                "expectancy": 10.0,
                "profit_factor": 2.0,
                "sample_size_warning": False,
                "max_drawdown": -10.0,
            }
        ]
    )

    result = evaluate_research_decision_gates(inputs, min_validation_dates=2)

    assert _gate_status(result, "TRADE_RULE_GATE") == "FAIL"
    assert "complete_trade_rules_exist" in _gate_blockers(result, "TRADE_RULE_GATE")


def test_readiness_score_range() -> None:
    result = evaluate_research_decision_gates({}, min_validation_dates=2)

    assert 0.0 <= result.readiness_score <= 100.0
    assert result.final_label == "NOT_READY_DATA_INSUFFICIENT"


def test_final_labels_follow_gate_rules_when_data_missing() -> None:
    inputs = _baseline_inputs()
    inputs["filter_avoided_pnl_report"] = pl.DataFrame(
        [
            {
                "control_type": "actual_no_trade_labels",
                "avoided_losing_trade_count": 40,
                "avoided_winning_trade_count": 5,
                "avoided_loss_amount": 500.0,
                "net_filter_value": 300.0,
                "false_block_rate": 0.1,
                "uplift_vs_matched_state_placebo": 250.0,
            }
        ]
    )
    inputs["transcript_walk_forward_uplift"] = pl.DataFrame({"pass_fail": ["PASS"]})

    result = evaluate_research_decision_gates(inputs, min_validation_dates=2)

    assert result.final_label == "NOT_READY_DATA_INSUFFICIENT"
    assert _gate_status(result, "DATA_COVERAGE_GATE") == "FAIL"


def test_missing_optional_outputs_handled_gracefully(tmp_path) -> None:
    result = run_research_decision_gate(output_dir=tmp_path, charts_dir=tmp_path / "charts")

    assert result.gate_report.height == 9
    assert result.final_label == "NOT_READY_DATA_INSUFFICIENT"
    assert (tmp_path / "research_decision_gate.csv").exists()
    assert (tmp_path / "research_readiness_scorecard.csv").exists()
    assert (tmp_path / "money_readiness_report.md").exists()
    assert (tmp_path / "next_research_tasks_ranked.csv").exists()
    assert (tmp_path / "charts" / "research_gate_status.svg").exists()
