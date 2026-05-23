from datetime import UTC, datetime, timedelta

import polars as pl

from research_xau_vol_oi.config import ResearchConfig
from research_xau_vol_oi.gold_baseline_lab import (
    build_gold_lab_events,
    credible_uplift_stage,
    evaluate_gold_lab_scenarios,
    guru_uplift_decision,
    run_gold_baseline_lab,
)


def _feature_table() -> pl.DataFrame:
    start = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    rows = []
    for index in range(80):
        close = 2400.0 + index * 0.5 + (2.0 if index % 9 == 0 else 0.0)
        rows.append(
            {
                "timestamp": start + timedelta(minutes=15 * index),
                "open": close - 0.2,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 100 + index,
                "session_open": 2400.0,
                "sigma_position": (index % 12 - 6) / 4.0,
                "sigma_zone": "inside_1sd" if index % 12 < 8 else "between_1_2sd",
                "vol_regime": "IV_PREMIUM" if index % 2 == 0 else "BALANCED",
                "rv_percent": 10.0 + (index % 5),
                "vrp": 2.0,
                "wall_level": 2405.0,
                "wall_score": 0.3,
                "wall_score_bucket": "high",
                "distance_to_nearest_wall": 3.0,
                "freshness_weight": 1.2 if index % 2 == 0 else 0.8,
                "dte_weight": 1.0,
                "dte": 1 if index % 10 == 0 else 8,
                "dte_bucket": "0_3d" if index % 10 == 0 else "4_10d",
                "wall_side": "resistance" if index % 2 == 0 else "support",
                "basis": 10.0,
            }
        )
    return pl.DataFrame(rows)


def _signal_events(feature_table: pl.DataFrame) -> pl.DataFrame:
    rows = []
    for index, row in enumerate(feature_table.to_dicts()):
        if index % 6 != 0:
            continue
        signal = "FADE_WALL_SHORT" if index % 12 == 0 else "FADE_WALL_LONG"
        rows.append(
            {
                "event_timestamp": row["timestamp"],
                "source_bar_timestamp": row["timestamp"],
                "signal": signal,
                "close": row["close"],
                "sigma_position": row["sigma_position"],
                "sigma_zone": row["sigma_zone"],
                "vol_regime": row["vol_regime"],
                "wall_level": row["wall_level"],
                "wall_score": row["wall_score"],
                "wall_score_bucket": row["wall_score_bucket"],
                "distance_to_nearest_wall": row["distance_to_nearest_wall"],
                "freshness_weight": row["freshness_weight"],
                "dte_weight": row["dte_weight"],
                "dte": row["dte"],
                "dte_bucket": row["dte_bucket"],
                "wall_side": row["wall_side"],
            }
        )
    return pl.DataFrame(rows)


def _conditioned(signal_events: pl.DataFrame) -> pl.DataFrame:
    return signal_events.with_columns(
        pl.lit("OI_WALL|NO_TRADE_DISCIPLINE").alias("active_transcript_rule_tags"),
        pl.lit(2).alias("active_rule_count"),
    )


def test_gold_lab_builds_baseline_and_staged_events() -> None:
    features = _feature_table()
    signals = _signal_events(features)
    events = build_gold_lab_events(
        feature_table=features,
        signal_events=signals,
        transcript_conditioned_events=_conditioned(signals),
        guru_context_records=pl.DataFrame(
            [{"rule_tag": "OI_WALL", "suggested_decision": "SUGGEST_APPROVE_MARKET_MAP"}]
        ),
        config=ResearchConfig(walk_forward_train_bars=20, walk_forward_test_bars=10),
    )

    stages = set(events.get_column("stage").to_list())
    assert "BASELINE_TREND" in stages
    assert "BASELINE_IV_RANGE" in stages
    assert "BASELINE_WALL_REACTION" in stages
    assert "A_OI_FRESHNESS_VOLUME" in stages
    assert "D_GURU_CONTEXT_FILTER_MAP" in stages


def test_stage_e_requires_approved_trade_rules() -> None:
    features = _feature_table()
    signals = _signal_events(features)
    events = build_gold_lab_events(
        feature_table=features,
        signal_events=signals,
        transcript_conditioned_events=_conditioned(signals),
        approved_rule_records=pl.DataFrame(),
    )

    assert "E_GURU_TRADE_RULE" not in set(events.get_column("stage").to_list())


def test_metrics_include_walk_forward_placebo_and_cost_stress() -> None:
    features = _feature_table()
    signals = _signal_events(features)
    events = build_gold_lab_events(feature_table=features, signal_events=signals)
    metrics = evaluate_gold_lab_scenarios(
        features,
        events,
        config=ResearchConfig(walk_forward_train_bars=20, walk_forward_test_bars=10),
        permutation_iterations=10,
    )

    types = set(metrics.get_column("evaluation_type").to_list())
    assert {
        "full_sample",
        "walk_forward_split",
        "walk_forward_summary",
        "permutation_test",
        "matched_state_placebo",
        "cost_stress",
    }.issubset(types)
    assert {"stage", "scenario", "expectancy", "sample_size_warning"}.issubset(metrics.columns)
    walk_forward_rows = metrics.filter(pl.col("evaluation_type").str.starts_with("walk_forward"))
    assert walk_forward_rows.filter(pl.col("scenario").is_null() | (pl.col("scenario") == "")).is_empty()


def test_decision_helpers_return_conservative_labels() -> None:
    metrics = pl.DataFrame(
        [
            {
                "stage": "A_OI_FRESHNESS_VOLUME",
                "scenario": "A",
                "scenario_family": "cme_feature_stage",
                "edge_type": "map",
                "evaluation_type": "full_sample",
                "trade_count": 5,
                "expectancy": 1.0,
                "sample_size_warning": True,
                "uplift_vs_best_baseline": 1.0,
            }
        ]
    )

    assert credible_uplift_stage(metrics) == "NONE"
    assert guru_uplift_decision(metrics) == "GURU_NOT_TESTABLE"


def test_run_gold_lab_writes_outputs(tmp_path) -> None:
    features = _feature_table()
    signals = _signal_events(features)

    result = run_gold_baseline_lab(
        feature_table=features,
        signal_events=signals,
        output_dir=tmp_path,
        charts_dir=tmp_path / "charts",
        config=ResearchConfig(walk_forward_train_bars=20, walk_forward_test_bars=10),
    )

    assert result.metrics.height > 0
    assert (tmp_path / "gold_baseline_metrics.csv").exists()
    assert (tmp_path / "gold_ablation_report.md").exists()
    assert (tmp_path / "charts" / "gold_baseline_vs_uplift.svg").exists()
