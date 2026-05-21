"""Score calibration, ablation, and signal-kill research layer.

This module evaluates whether the research-only ``signal_score`` has useful
ordering power. It deliberately keeps no-trade rows in the analysis and uses
walk-forward threshold selection so test windows cannot influence thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import polars as pl

from research_xau_vol_oi.backtest import (
    generate_bollinger_baseline_events,
    generate_oi_wall_only_baseline_events,
    generate_random_baseline_events,
    generate_sd_only_baseline_events,
    run_event_backtest,
)
from research_xau_vol_oi.config import ResearchConfig, Signal
from research_xau_vol_oi.signal_score import DIRECTIONAL_SIGNALS, SCORE_COMPONENTS, score_signal_events


THRESHOLDS = (50, 60, 70, 80, 90)
VOL_OI_SCENARIOS = {
    "ALL_DIRECTIONAL_VOL_OI": tuple(sorted(DIRECTIONAL_SIGNALS)),
    Signal.FADE_WALL_SHORT.value: (Signal.FADE_WALL_SHORT.value,),
    Signal.BREAK_WALL_SHORT.value: (Signal.BREAK_WALL_SHORT.value,),
    Signal.FADE_WALL_LONG.value: (Signal.FADE_WALL_LONG.value,),
    Signal.BREAK_WALL_LONG.value: (Signal.BREAK_WALL_LONG.value,),
}
BASELINE_SCENARIOS = (
    Signal.BOLLINGER_BASELINE.value,
    Signal.SD_ONLY_BASELINE.value,
    Signal.OI_WALL_ONLY_BASELINE.value,
    Signal.RANDOM_BASELINE.value,
)
MIN_SAMPLE_SIZE = 20


@dataclass(frozen=True)
class ScoreCalibrationResult:
    """Paths and summary state for generated calibration artifacts."""

    score_decile_performance: pl.DataFrame
    score_threshold_performance: pl.DataFrame
    walk_forward_score: pl.DataFrame
    ablation: pl.DataFrame
    kill_list: pl.DataFrame
    threshold_policy: pl.DataFrame
    monotonicity: dict[str, Any]
    final_decision: str


def run_score_research_layer(
    *,
    price_features: pl.DataFrame,
    signal_events: pl.DataFrame,
    signal_scores: pl.DataFrame,
    output_dir: Path,
    charts_dir: Path,
    config: ResearchConfig | None = None,
) -> ScoreCalibrationResult:
    """Run score calibration, write reports, and return generated frames."""

    cfg = config or ResearchConfig()
    output_dir.mkdir(parents=True, exist_ok=True)
    charts_dir.mkdir(parents=True, exist_ok=True)

    deciles = score_bucket_performance(price_features, signal_events, signal_scores, config=cfg)
    thresholds = score_threshold_performance(price_features, signal_events, signal_scores, config=cfg)
    walk_forward = walk_forward_score_calibration(price_features, signal_scores, config=cfg)
    monotonicity = classify_score_monotonicity(deciles)
    ablation = feature_ablation(price_features, signal_events, signal_scores, config=cfg)
    kill_list = build_signal_kill_list(
        deciles,
        thresholds,
        walk_forward,
        config=cfg,
    )
    threshold_policy = threshold_policy_recommendation(
        thresholds,
        walk_forward,
        monotonicity=monotonicity,
    )
    final_decision = final_research_decision(
        thresholds,
        walk_forward,
        threshold_policy,
        monotonicity=monotonicity,
    )

    deciles.write_csv(output_dir / "score_decile_performance.csv")
    thresholds.write_csv(output_dir / "score_threshold_performance.csv")
    walk_forward.write_csv(output_dir / "walk_forward_score_calibration.csv")
    ablation.write_csv(output_dir / "score_ablation_results.csv")
    kill_list.write_csv(output_dir / "signal_kill_list.csv")
    threshold_policy.write_csv(output_dir / "threshold_policy_recommendation.csv")

    write_score_calibration_report(
        output_dir / "score_calibration_report.md",
        deciles=deciles,
        thresholds=thresholds,
        walk_forward=walk_forward,
        kill_list=kill_list,
        threshold_policy=threshold_policy,
        monotonicity=monotonicity,
        final_decision=final_decision,
    )
    write_score_ablation_report(output_dir / "score_ablation_report.md", ablation)
    write_score_charts(
        charts_dir=charts_dir,
        deciles=deciles,
        thresholds=thresholds,
        scored_trades=_run_scored_backtest(price_features, _directional_score_rows(signal_scores), config=cfg),
    )

    return ScoreCalibrationResult(
        score_decile_performance=deciles,
        score_threshold_performance=thresholds,
        walk_forward_score=walk_forward,
        ablation=ablation,
        kill_list=kill_list,
        threshold_policy=threshold_policy,
        monotonicity=monotonicity,
        final_decision=final_decision,
    )


def score_bucket_performance(
    price_features: pl.DataFrame,
    signal_events: pl.DataFrame,
    signal_scores: pl.DataFrame,
    *,
    config: ResearchConfig | None = None,
    min_sample_size: int = MIN_SAMPLE_SIZE,
) -> pl.DataFrame:
    """Group score rows by decile and research context, keeping no-trade rows."""

    cfg = config or ResearchConfig()
    enriched = _enrich_scores(signal_scores, signal_events)
    if enriched.is_empty():
        return _empty_performance()
    scored_events = _directional_score_rows(enriched)
    trades = _run_scored_backtest(price_features, scored_events, config=cfg)
    groups = [
        ("score_decile", "score_decile"),
        ("signal_label", "signal_label"),
        ("trade_direction", "trade_direction"),
        ("sigma_zone", "sigma_zone"),
        ("wall_score_bucket", "wall_score_bucket"),
        ("dte_bucket", "dte_bucket"),
        ("iv_rv_vrp_regime", "vol_regime"),
    ]
    rows: list[dict[str, Any]] = []
    for group_type, key in groups:
        event_groups = _group_rows(enriched.to_dicts(), key)
        trade_groups = _group_rows(trades.to_dicts(), key)
        for bucket in sorted(event_groups):
            metrics = _performance_metrics(
                trade_groups.get(bucket, []),
                event_count=len(event_groups[bucket]),
                group_type=group_type,
                bucket=bucket,
                min_sample_size=min_sample_size,
            )
            rows.append(metrics)
    return pl.DataFrame(rows) if rows else _empty_performance()


def score_threshold_performance(
    price_features: pl.DataFrame,
    signal_events: pl.DataFrame,
    signal_scores: pl.DataFrame,
    *,
    config: ResearchConfig | None = None,
    thresholds: tuple[int, ...] = THRESHOLDS,
    cost_multipliers: tuple[int, ...] = (1, 2, 3, 5),
) -> pl.DataFrame:
    """Evaluate score thresholds, signal classes, baselines, and cost stress."""

    cfg = config or ResearchConfig()
    enriched = _enrich_scores(signal_scores, signal_events)
    baseline_events = _baseline_events(price_features, signal_events, config=cfg)
    rows: list[dict[str, Any]] = []
    for cost_multiplier in cost_multipliers:
        stressed_cfg = _cost_config(cfg, cost_multiplier)
        baseline_metrics = _baseline_metrics(price_features, baseline_events, config=stressed_cfg)
        for threshold in thresholds:
            for scenario, classes in VOL_OI_SCENARIOS.items():
                selected = _filter_score_rows(enriched, threshold=threshold, signal_classes=classes)
                trades = _run_scored_backtest(price_features, selected, config=stressed_cfg)
                rows.append(
                    {
                        **_performance_metrics(
                            trades.to_dicts(),
                            event_count=selected.height,
                            group_type="threshold",
                            bucket=scenario,
                            min_sample_size=MIN_SAMPLE_SIZE,
                        ),
                        "threshold": threshold,
                        "scenario": scenario,
                        "scenario_type": "vol_oi_score",
                        "cost_multiplier": cost_multiplier,
                        "cost_points_per_side": stressed_cfg.cost_points_per_side,
                        "slippage_points_per_side": stressed_cfg.slippage_points_per_side,
                    }
                )
            for scenario, metrics in baseline_metrics.items():
                rows.append(
                    {
                        **metrics,
                        "threshold": threshold,
                        "scenario": scenario,
                        "scenario_type": "baseline",
                        "cost_multiplier": cost_multiplier,
                        "cost_points_per_side": stressed_cfg.cost_points_per_side,
                        "slippage_points_per_side": stressed_cfg.slippage_points_per_side,
                    }
                )
    return pl.DataFrame(rows) if rows else _empty_threshold_performance()


def walk_forward_score_calibration(
    price_features: pl.DataFrame,
    signal_scores: pl.DataFrame,
    *,
    config: ResearchConfig | None = None,
    thresholds: tuple[int, ...] = THRESHOLDS,
    min_sample_size: int = MIN_SAMPLE_SIZE,
) -> pl.DataFrame:
    """Select score thresholds in train windows and freeze them in test windows."""

    cfg = config or ResearchConfig()
    if price_features.is_empty() or signal_scores.is_empty():
        return _empty_walk_forward()
    prices = price_features.sort("timestamp").to_dicts()
    enriched = _add_score_decile(signal_scores).sort("event_timestamp")
    rows: list[dict[str, Any]] = []
    start = 0
    split_id = 1
    while start + cfg.walk_forward_train_bars < len(prices):
        train_end = start + cfg.walk_forward_train_bars - 1
        test_start = train_end + 1
        test_end = min(test_start + cfg.walk_forward_test_bars - 1, len(prices) - 1)
        train_start_ts = prices[start]["timestamp"]
        train_end_ts = prices[train_end]["timestamp"]
        test_start_ts = prices[test_start]["timestamp"]
        test_end_ts = prices[test_end]["timestamp"]
        train_scores = _time_slice(enriched, train_start_ts, train_end_ts)
        test_scores = _time_slice(enriched, test_start_ts, test_end_ts)
        selected = _select_train_candidate(
            price_features,
            train_scores,
            train_end_ts=train_end_ts,
            config=cfg,
            thresholds=thresholds,
            min_sample_size=min_sample_size,
        )
        if selected is None:
            test_metrics = _performance_metrics(
                [],
                event_count=test_scores.height,
                group_type="walk_forward",
                bucket="no_selected_threshold",
                min_sample_size=min_sample_size,
            )
            rows.append(
                _walk_forward_row(
                    split_id=split_id,
                    train_start=train_start_ts,
                    train_end=train_end_ts,
                    test_start=test_start_ts,
                    test_end=test_end_ts,
                    selected_threshold=None,
                    selected_signal_classes="",
                    metrics=test_metrics,
                    pass_fail="FAIL",
                )
            )
        else:
            selected_threshold, selected_name, selected_classes = selected
            selected_test = _filter_score_rows(
                test_scores,
                threshold=selected_threshold,
                signal_classes=selected_classes,
            )
            test_trades = _run_scored_backtest(
                price_features,
                selected_test,
                config=cfg,
                max_exit_timestamp=test_end_ts,
            )
            test_metrics = _performance_metrics(
                test_trades.to_dicts(),
                event_count=selected_test.height,
                group_type="walk_forward",
                bucket=selected_name,
                min_sample_size=min_sample_size,
            )
            passed = (
                test_metrics["trade_count"] >= min_sample_size
                and (test_metrics["expectancy"] or 0.0) > 0
                and (test_metrics["profit_factor"] or 0.0) >= 1.2
            )
            rows.append(
                _walk_forward_row(
                    split_id=split_id,
                    train_start=train_start_ts,
                    train_end=train_end_ts,
                    test_start=test_start_ts,
                    test_end=test_end_ts,
                    selected_threshold=selected_threshold,
                    selected_signal_classes=",".join(selected_classes),
                    metrics=test_metrics,
                    pass_fail="PASS" if passed else "FAIL",
                )
            )
        split_id += 1
        start = test_end + 1
    return pl.DataFrame(rows) if rows else _empty_walk_forward()


def classify_score_monotonicity(deciles: pl.DataFrame) -> dict[str, Any]:
    """Classify whether higher score deciles improve expectancy."""

    rows = [
        row
        for row in deciles.filter(pl.col("group_type") == "score_decile").to_dicts()
        if row.get("trade_count") and row.get("expectancy") is not None
    ] if not deciles.is_empty() else []
    ordered = sorted(rows, key=lambda row: _decile_start(str(row["bucket"])))
    values = [float(row["expectancy"]) for row in ordered]
    if len(values) < 3:
        status = "monotonic_fail"
    elif all(values[index] <= values[index + 1] for index in range(len(values) - 1)):
        status = "monotonic_pass"
    else:
        low = [float(row["expectancy"]) for row in ordered if _decile_start(str(row["bucket"])) < 50]
        high = [float(row["expectancy"]) for row in ordered if _decile_start(str(row["bucket"])) >= 80]
        status = (
            "partial_monotonic_pass"
            if high and low and _average(high) > _average(low)
            else "monotonic_fail"
        )
    return {
        "monotonic_status": status,
        "monotonic_pass": status == "monotonic_pass",
        "partial_monotonic_pass": status == "partial_monotonic_pass",
        "monotonic_fail": status == "monotonic_fail",
        "decile_count": len(values),
    }


def feature_ablation(
    price_features: pl.DataFrame,
    signal_events: pl.DataFrame,
    baseline_scores: pl.DataFrame,
    *,
    config: ResearchConfig | None = None,
    threshold: int = 80,
) -> pl.DataFrame:
    """Re-score after removing each score component and compare threshold results."""

    cfg = config or ResearchConfig()
    baseline_metrics, baseline_no_trade = _ablation_metrics(
        price_features,
        signal_events,
        baseline_scores,
        threshold=threshold,
        config=cfg,
    )
    rows = []
    for component in sorted(SCORE_COMPONENTS):
        scores = score_signal_events(
            price_features,
            signal_events,
            config=cfg,
            disabled_components={component},
        )
        metrics, no_trade_count = _ablation_metrics(
            price_features,
            signal_events,
            scores,
            threshold=threshold,
            config=cfg,
        )
        expectancy_delta = _none_safe(metrics["expectancy"]) - _none_safe(baseline_metrics["expectancy"])
        pf_delta = _none_safe(metrics["profit_factor"]) - _none_safe(baseline_metrics["profit_factor"])
        trade_delta = metrics["trade_count"] - baseline_metrics["trade_count"]
        no_trade_delta = no_trade_count - baseline_no_trade
        rows.append(
            {
                "removed_component": component,
                "threshold": threshold,
                "baseline_expectancy": baseline_metrics["expectancy"],
                "ablated_expectancy": metrics["expectancy"],
                "change_in_expectancy": expectancy_delta,
                "baseline_profit_factor": baseline_metrics["profit_factor"],
                "ablated_profit_factor": metrics["profit_factor"],
                "change_in_profit_factor": pf_delta,
                "baseline_trade_count": baseline_metrics["trade_count"],
                "ablated_trade_count": metrics["trade_count"],
                "change_in_trade_count": trade_delta,
                "baseline_no_trade_count": baseline_no_trade,
                "ablated_no_trade_count": no_trade_count,
                "change_in_no_trade_count": no_trade_delta,
                "impact": "improves" if expectancy_delta > 0 else "worsens" if expectancy_delta < 0 else "unchanged",
            }
        )
    return pl.DataFrame(rows) if rows else _empty_ablation()


def build_signal_kill_list(
    deciles: pl.DataFrame,
    thresholds: pl.DataFrame,
    walk_forward: pl.DataFrame,
    *,
    config: ResearchConfig | None = None,
    min_sample_size: int = MIN_SAMPLE_SIZE,
) -> pl.DataFrame:
    """Recommend KEEP, quarantine, kill, or control-only by signal class."""

    _ = config or ResearchConfig()
    signal_rows = {
        row["bucket"]: row
        for row in deciles.filter(pl.col("group_type") == "signal_label").to_dicts()
    } if not deciles.is_empty() else {}
    baseline_rows = _threshold_baseline_rows(thresholds)
    all_labels = sorted(set(signal_rows) | set(baseline_rows) | {Signal.RANDOM_BASELINE.value})
    bollinger_expectancy = _none_safe(
        baseline_rows.get(Signal.BOLLINGER_BASELINE.value, {}).get("expectancy")
    )
    weak_baseline_expectancy = max(
        _none_safe(baseline_rows.get(Signal.SD_ONLY_BASELINE.value, {}).get("expectancy")),
        _none_safe(baseline_rows.get(Signal.OI_WALL_ONLY_BASELINE.value, {}).get("expectancy")),
        _none_safe(baseline_rows.get(Signal.RANDOM_BASELINE.value, {}).get("expectancy")),
    )
    wf_pass = _walk_forward_signal_passes(walk_forward)
    rows = []
    for label in all_labels:
        metrics = signal_rows.get(label) or baseline_rows.get(label) or {}
        trade_count = int(metrics.get("trade_count") or 0)
        expectancy = metrics.get("expectancy")
        profit_factor = metrics.get("profit_factor")
        walk_forward_pass = label in wf_pass
        recommendation, reason = _kill_recommendation(
            label=label,
            trade_count=trade_count,
            expectancy=expectancy,
            profit_factor=profit_factor,
            walk_forward_pass=walk_forward_pass,
            bollinger_expectancy=bollinger_expectancy,
            weak_baseline_expectancy=weak_baseline_expectancy,
            min_sample_size=min_sample_size,
        )
        rows.append(
            {
                "signal_label": label,
                "reason": reason,
                "trade_count": trade_count,
                "expectancy": expectancy,
                "profit_factor": profit_factor,
                "walk_forward_pass": walk_forward_pass,
                "recommendation": recommendation,
            }
        )
    return pl.DataFrame(rows) if rows else _empty_kill_list()


def threshold_policy_recommendation(
    thresholds: pl.DataFrame,
    walk_forward: pl.DataFrame,
    *,
    monotonicity: dict[str, Any],
    min_sample_size: int = MIN_SAMPLE_SIZE,
) -> pl.DataFrame:
    """Create the conservative threshold policy recommendation."""

    base_rows = [
        row
        for row in thresholds.filter(
            (pl.col("scenario_type") == "vol_oi_score")
            & (pl.col("scenario") == "ALL_DIRECTIONAL_VOL_OI")
            & (pl.col("cost_multiplier") == 1)
        ).to_dicts()
    ] if not thresholds.is_empty() else []
    candidates = [
        row
        for row in base_rows
        if int(row.get("trade_count") or 0) >= min_sample_size
        and (row.get("expectancy") is not None and float(row["expectancy"]) > 0)
    ]
    best = max(
        candidates,
        key=lambda row: (
            float(row.get("profit_factor") or 0.0),
            float(row.get("expectancy") or 0.0),
            int(row.get("threshold") or 0),
        ),
        default=None,
    )
    wf_any_pass = (
        walk_forward.filter(pl.col("pass_fail") == "PASS").height > 0
        if not walk_forward.is_empty()
        else False
    )
    if best is None or not wf_any_pass or monotonicity.get("monotonic_fail"):
        return pl.DataFrame(
            [
                {
                    "policy": "NO_DIRECTIONAL_SCORE_THRESHOLD",
                    "recommended_threshold": None,
                    "selected_signal_classes": "",
                    "in_sample_expectancy": best.get("expectancy") if best else None,
                    "in_sample_profit_factor": best.get("profit_factor") if best else None,
                    "walk_forward_pass": wf_any_pass,
                    "monotonic_status": monotonicity["monotonic_status"],
                    "recommendation": "Keep score as a research diagnostic; default to no-trade until walk-forward improves.",
                }
            ]
        )
    return pl.DataFrame(
        [
            {
                "policy": "FROZEN_SCORE_THRESHOLD_RESEARCH_ONLY",
                "recommended_threshold": best["threshold"],
                "selected_signal_classes": "ALL_DIRECTIONAL_VOL_OI",
                "in_sample_expectancy": best["expectancy"],
                "in_sample_profit_factor": best["profit_factor"],
                "walk_forward_pass": wf_any_pass,
                "monotonic_status": monotonicity["monotonic_status"],
                "recommendation": "Use only for continued research, not live trading.",
            }
        ]
    )


def final_research_decision(
    thresholds: pl.DataFrame,
    walk_forward: pl.DataFrame,
    threshold_policy: pl.DataFrame,
    *,
    monotonicity: dict[str, Any],
    min_sample_size: int = MIN_SAMPLE_SIZE,
) -> str:
    """Return the honest final research decision for score usefulness."""

    wf_rows = walk_forward.filter(pl.col("pass_fail") == "PASS") if not walk_forward.is_empty() else pl.DataFrame()
    if wf_rows.is_empty():
        return "NO_EDGE_PROVEN"
    best_wf = max(wf_rows.to_dicts(), key=lambda row: _none_safe(row.get("test_expectancy")))
    base_rows = thresholds.filter(
        (pl.col("scenario") == "BOLLINGER_BASELINE")
        & (pl.col("cost_multiplier") == 1)
    ) if not thresholds.is_empty() else pl.DataFrame()
    bollinger = _none_safe(base_rows.get_column("expectancy").max()) if not base_rows.is_empty() else 0.0
    sample_ok = int(best_wf.get("test_trade_count") or 0) >= min_sample_size
    pf_ok = _none_safe(best_wf.get("test_profit_factor")) >= 1.2
    expectancy_ok = _none_safe(best_wf.get("test_expectancy")) > 0
    monotonic_ok = not monotonicity.get("monotonic_fail")
    beats_bollinger = _none_safe(best_wf.get("test_expectancy")) > bollinger
    if sample_ok and pf_ok and expectancy_ok and monotonic_ok and beats_bollinger:
        return "VALIDATED_EDGE"
    if expectancy_ok and pf_ok and monotonic_ok:
        return "LIMITED_SHORT_SIDE_EDGE"
    policy = threshold_policy.to_dicts()[0] if not threshold_policy.is_empty() else {}
    if policy.get("recommended_threshold") is not None:
        return "PROMISING_BUT_UNVALIDATED"
    return "NO_EDGE_PROVEN"


def write_score_calibration_report(
    path: Path,
    *,
    deciles: pl.DataFrame,
    thresholds: pl.DataFrame,
    walk_forward: pl.DataFrame,
    kill_list: pl.DataFrame,
    threshold_policy: pl.DataFrame,
    monotonicity: dict[str, Any],
    final_decision: str,
) -> None:
    """Write the score calibration Markdown report."""

    lines = [
        "# XAU Vol-OI Score Calibration Report",
        "",
        "Research-only calibration. This report does not approve live trading.",
        "",
        f"- Final research decision: `{final_decision}`",
        f"- Monotonicity status: `{monotonicity['monotonic_status']}`",
        "",
        "## Score Decile Results",
        "",
        _frame_markdown(deciles.filter(pl.col("group_type") == "score_decile") if not deciles.is_empty() else deciles),
        "",
        "## Threshold Results",
        "",
        _frame_markdown(
            thresholds.filter(
                (pl.col("scenario_type") == "vol_oi_score")
                & (pl.col("cost_multiplier") == 1)
            )
            if not thresholds.is_empty()
            else thresholds
        ),
        "",
        "## Walk-Forward Score Results",
        "",
        _frame_markdown(walk_forward),
        "",
        "## Threshold Policy Recommendation",
        "",
        _frame_markdown(threshold_policy),
        "",
        "## Kill / Quarantine Recommendations",
        "",
        _frame_markdown(kill_list),
        "",
        "## Interpretation",
        "",
        "- `VALIDATED_EDGE` is blocked unless walk-forward expectancy is positive, "
        "profit factor clears 1.2 after costs, score buckets are at least partially "
        "monotonic, sample size is sufficient, and the score beats the Bollinger baseline.",
        "- No-trade and watch-only rows are included in event counts.",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_score_ablation_report(path: Path, ablation: pl.DataFrame) -> None:
    """Write the feature ablation Markdown report."""

    lines = [
        "# XAU Vol-OI Score Ablation Report",
        "",
        "Each row removes one scoring component and re-runs the score threshold research layer.",
        "",
        _frame_markdown(ablation),
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_score_charts(
    *,
    charts_dir: Path,
    deciles: pl.DataFrame,
    thresholds: pl.DataFrame,
    scored_trades: pl.DataFrame,
) -> None:
    """Write score calibration SVG chart artifacts."""

    decile_rows = (
        deciles.filter(pl.col("group_type") == "score_decile").sort("bucket").to_dicts()
        if not deciles.is_empty()
        else []
    )
    _write_bar_svg(
        charts_dir / "score_decile_expectancy.svg",
        title="Score decile expectancy",
        labels=[str(row["bucket"]) for row in decile_rows],
        values=[float(row.get("expectancy") or 0.0) for row in decile_rows],
    )
    threshold_rows = (
        thresholds.filter(
            (pl.col("scenario") == "ALL_DIRECTIONAL_VOL_OI")
            & (pl.col("cost_multiplier") == 1)
        ).sort("threshold").to_dicts()
        if not thresholds.is_empty()
        else []
    )
    _write_line_svg(
        charts_dir / "score_threshold_profit_factor.svg",
        title="Score threshold profit factor",
        labels=[str(row["threshold"]) for row in threshold_rows],
        values=[float(row.get("profit_factor") or 0.0) for row in threshold_rows],
    )
    _write_scatter_svg(
        charts_dir / "score_vs_forward_return.svg",
        title="Score vs forward return",
        rows=scored_trades.to_dicts(),
    )
    signal_rows = (
        deciles.filter(pl.col("group_type") == "signal_label").sort("bucket").to_dicts()
        if not deciles.is_empty()
        else []
    )
    _write_bar_svg(
        charts_dir / "signal_class_expectancy.svg",
        title="Signal class expectancy",
        labels=[str(row["bucket"]) for row in signal_rows],
        values=[float(row.get("expectancy") or 0.0) for row in signal_rows],
    )


def _enrich_scores(signal_scores: pl.DataFrame, signal_events: pl.DataFrame) -> pl.DataFrame:
    if signal_scores.is_empty():
        return _empty_scores_enriched()
    event_lookup = {
        (row.get("event_timestamp"), row.get("source_bar_timestamp")): row
        for row in signal_events.to_dicts()
    } if not signal_events.is_empty() else {}
    rows = []
    for score in signal_scores.to_dicts():
        event = event_lookup.get((score.get("event_timestamp"), score.get("source_bar_timestamp")), {})
        rows.append(
            {
                **score,
                "score_decile": score_decile(score.get("signal_score")),
                "sigma_zone": event.get("sigma_zone") or _sigma_zone(score.get("sigma_position")),
                "wall_score_bucket": event.get("wall_score_bucket") or _wall_score_bucket(score.get("wall_score")),
                "dte_bucket": event.get("dte_bucket") or "unknown",
                "dte": event.get("dte"),
                "wall_side": event.get("wall_side"),
                "next_wall_distance": event.get("next_wall_distance"),
                "signal": score.get("signal_label"),
            }
        )
    return pl.DataFrame(rows)


def score_decile(score: Any) -> str:
    """Return score decile label for a 0-100 score."""

    value = max(0, min(100, int(float(score or 0))))
    start = min((value // 10) * 10, 90)
    return f"{start}-{start + 10}"


def _directional_score_rows(scores: pl.DataFrame) -> pl.DataFrame:
    if scores.is_empty():
        return _empty_scores_enriched()
    enriched = _add_score_decile(scores)
    return enriched.filter(
        pl.col("signal_label").is_in(sorted(DIRECTIONAL_SIGNALS))
        & (pl.col("trade_direction") != "NONE")
    )


def _filter_score_rows(
    scores: pl.DataFrame,
    *,
    threshold: int,
    signal_classes: tuple[str, ...],
) -> pl.DataFrame:
    if scores.is_empty():
        return _empty_scores_enriched()
    enriched = _add_score_decile(scores)
    return enriched.filter(
        (pl.col("signal_score") >= threshold)
        & pl.col("signal_label").is_in(list(signal_classes))
        & (pl.col("trade_direction") != "NONE")
    )


def _run_scored_backtest(
    price: pl.DataFrame,
    score_rows: pl.DataFrame,
    *,
    config: ResearchConfig | None = None,
    max_exit_timestamp: Any | None = None,
) -> pl.DataFrame:
    cfg = config or ResearchConfig()
    if price.is_empty() or score_rows.is_empty():
        return _empty_score_trades()
    price_rows = price.sort("timestamp").to_dicts()
    trades: list[dict[str, Any]] = []
    for event in score_rows.sort("event_timestamp").to_dicts():
        direction = 1 if event.get("trade_direction") == "LONG" else -1 if event.get("trade_direction") == "SHORT" else 0
        if direction == 0:
            continue
        entry_index = _first_price_index_after(price_rows, event.get("event_timestamp"))
        if entry_index is None:
            continue
        exit_index = min(entry_index + cfg.backtest_horizon_bars, len(price_rows) - 1)
        if exit_index <= entry_index:
            continue
        exit_bar = price_rows[exit_index]
        if max_exit_timestamp is not None and exit_bar["timestamp"] > max_exit_timestamp:
            continue
        entry = price_rows[entry_index]
        path = price_rows[entry_index : exit_index + 1]
        entry_price = float(entry.get("open") or entry["close"])
        exit_price = float(exit_bar["close"])
        pnl = (exit_price - entry_price) * direction
        round_trip_cost = 2.0 * (cfg.cost_points_per_side + cfg.slippage_points_per_side)
        net_pnl = pnl - round_trip_cost
        mae, mfe = _mae_mfe(path, entry_price=entry_price, direction=direction)
        trades.append(
            {
                "event_timestamp": event.get("event_timestamp"),
                "entry_timestamp": entry["timestamp"],
                "exit_timestamp": exit_bar["timestamp"],
                "signal_label": event.get("signal_label"),
                "signal": event.get("signal_label"),
                "trade_direction": event.get("trade_direction"),
                "direction": direction,
                "signal_score": event.get("signal_score"),
                "score_decile": event.get("score_decile") or score_decile(event.get("signal_score")),
                "entry_price": entry_price,
                "exit_price": exit_price,
                "pnl_points": pnl,
                "round_trip_cost_points": round_trip_cost,
                "net_pnl_points": net_pnl,
                "mae_points": mae,
                "mfe_points": mfe,
                "time_in_trade_bars": exit_index - entry_index,
                "sigma_zone": event.get("sigma_zone"),
                "dte_bucket": event.get("dte_bucket"),
                "wall_score_bucket": event.get("wall_score_bucket"),
                "vol_regime": event.get("vol_regime"),
                "research_only": True,
            }
        )
    return pl.DataFrame(trades) if trades else _empty_score_trades()


def _select_train_candidate(
    price_features: pl.DataFrame,
    train_scores: pl.DataFrame,
    *,
    train_end_ts: Any,
    config: ResearchConfig,
    thresholds: tuple[int, ...],
    min_sample_size: int,
) -> tuple[int, str, tuple[str, ...]] | None:
    candidates = []
    for threshold in thresholds:
        for scenario, classes in VOL_OI_SCENARIOS.items():
            selected = _filter_score_rows(train_scores, threshold=threshold, signal_classes=classes)
            trades = _run_scored_backtest(
                price_features,
                selected,
                config=config,
                max_exit_timestamp=train_end_ts,
            )
            metrics = _performance_metrics(
                trades.to_dicts(),
                event_count=selected.height,
                group_type="train_candidate",
                bucket=scenario,
                min_sample_size=min_sample_size,
            )
            if (
                metrics["trade_count"] >= min_sample_size
                and (metrics["expectancy"] or 0.0) > 0
                and (metrics["profit_factor"] or 0.0) > 1.0
            ):
                candidates.append((threshold, scenario, classes, metrics))
    if not candidates:
        return None
    threshold, scenario, classes, _metrics = max(
        candidates,
        key=lambda item: (
            float(item[3].get("expectancy") or 0.0),
            float(item[3].get("profit_factor") or 0.0),
            item[0],
        ),
    )
    return threshold, scenario, classes


def _walk_forward_row(
    *,
    split_id: int,
    train_start: Any,
    train_end: Any,
    test_start: Any,
    test_end: Any,
    selected_threshold: int | None,
    selected_signal_classes: str,
    metrics: dict[str, Any],
    pass_fail: str,
) -> dict[str, Any]:
    return {
        "split_id": split_id,
        "train_start": train_start,
        "train_end": train_end,
        "test_start": test_start,
        "test_end": test_end,
        "selected_threshold": selected_threshold,
        "selected_signal_classes": selected_signal_classes,
        "test_event_count": metrics["event_count"],
        "test_trade_count": metrics["trade_count"],
        "test_expectancy": metrics["expectancy"],
        "test_profit_factor": metrics["profit_factor"],
        "test_max_drawdown": metrics["max_drawdown"],
        "pass_fail": pass_fail,
    }


def _baseline_events(
    price_features: pl.DataFrame,
    signal_events: pl.DataFrame,
    *,
    config: ResearchConfig,
) -> dict[str, pl.DataFrame]:
    return {
        Signal.BOLLINGER_BASELINE.value: generate_bollinger_baseline_events(price_features),
        Signal.SD_ONLY_BASELINE.value: generate_sd_only_baseline_events(price_features),
        Signal.OI_WALL_ONLY_BASELINE.value: generate_oi_wall_only_baseline_events(price_features),
        Signal.RANDOM_BASELINE.value: generate_random_baseline_events(signal_events, config=config),
    }


def _baseline_metrics(
    price_features: pl.DataFrame,
    baseline_events: dict[str, pl.DataFrame],
    *,
    config: ResearchConfig,
) -> dict[str, dict[str, Any]]:
    rows = {}
    for scenario, events in baseline_events.items():
        trades = run_event_backtest(price_features, events, config=config)
        rows[scenario] = _performance_metrics(
            trades.to_dicts(),
            event_count=events.height if not events.is_empty() else 0,
            group_type="threshold",
            bucket=scenario,
            min_sample_size=MIN_SAMPLE_SIZE,
        )
    return rows


def _ablation_metrics(
    price_features: pl.DataFrame,
    signal_events: pl.DataFrame,
    scores: pl.DataFrame,
    *,
    threshold: int,
    config: ResearchConfig,
) -> tuple[dict[str, Any], int]:
    enriched = _enrich_scores(scores, signal_events)
    selected = _filter_score_rows(
        enriched,
        threshold=threshold,
        signal_classes=VOL_OI_SCENARIOS["ALL_DIRECTIONAL_VOL_OI"],
    )
    trades = _run_scored_backtest(price_features, selected, config=config)
    no_trade_count = (
        enriched.filter(pl.col("signal_label").is_in([Signal.NO_TRADE.value, Signal.NO_TRADE_MIDDLE.value])).height
        if not enriched.is_empty()
        else 0
    )
    return (
        _performance_metrics(
            trades.to_dicts(),
            event_count=selected.height,
            group_type="ablation",
            bucket="ALL_DIRECTIONAL_VOL_OI",
            min_sample_size=MIN_SAMPLE_SIZE,
        ),
        no_trade_count,
    )


def _performance_metrics(
    rows: list[dict[str, Any]],
    *,
    event_count: int,
    group_type: str,
    bucket: str,
    min_sample_size: int,
) -> dict[str, Any]:
    pnl = [float(row.get("net_pnl_points", row.get("pnl_points", 0.0))) for row in rows]
    wins = [value for value in pnl if value > 0]
    losses = [value for value in pnl if value < 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    equity = []
    running = 0.0
    for value in pnl:
        running += value
        equity.append(running)
    trade_count = len(rows)
    return {
        "group_type": group_type,
        "bucket": bucket,
        "event_count": event_count,
        "trade_count": trade_count,
        "win_rate": len(wins) / trade_count if trade_count else None,
        "average_win": sum(wins) / len(wins) if wins else 0.0,
        "average_loss": sum(losses) / len(losses) if losses else 0.0,
        "expectancy": sum(pnl) / trade_count if trade_count else None,
        "profit_factor": gross_win / gross_loss if gross_loss > 0 else None,
        "max_drawdown": _max_drawdown(equity),
        "average_mae": _average([float(row.get("mae_points") or 0.0) for row in rows]),
        "average_mfe": _average([float(row.get("mfe_points") or 0.0) for row in rows]),
        "average_holding_time": _average([float(row.get("time_in_trade_bars") or 0.0) for row in rows]),
        "sample_size_warning": trade_count < min_sample_size,
    }


def _kill_recommendation(
    *,
    label: str,
    trade_count: int,
    expectancy: Any,
    profit_factor: Any,
    walk_forward_pass: bool,
    bollinger_expectancy: float,
    weak_baseline_expectancy: float,
    min_sample_size: int,
) -> tuple[str, str]:
    if label in {
        Signal.NO_TRADE.value,
        Signal.NO_TRADE_MIDDLE.value,
        Signal.RANDOM_BASELINE.value,
        Signal.BOLLINGER_BASELINE.value,
        Signal.SD_ONLY_BASELINE.value,
        Signal.OI_WALL_ONLY_BASELINE.value,
        Signal.WATCH_WALL.value,
        Signal.PIN_RISK.value,
        Signal.SQUEEZE_RISK.value,
    }:
        return "CONTROL_ONLY", "non-directional or baseline control"
    value = _none_safe(expectancy)
    pf = _none_safe(profit_factor)
    if trade_count < min_sample_size:
        return "QUARANTINE", "sample size below minimum"
    if value < 0:
        return "KILL", "negative expectancy with sufficient sample"
    if not walk_forward_pass:
        return "QUARANTINE", "positive in-sample but failed walk-forward"
    if value > bollinger_expectancy and pf >= 1.2:
        return "KEEP", "beats Bollinger and passed walk-forward"
    if value > weak_baseline_expectancy:
        return "KEEP_BUT_LIMIT_SIZE", "beats weak baselines but not Bollinger"
    return "QUARANTINE", "does not beat baseline stack"


def _threshold_baseline_rows(thresholds: pl.DataFrame) -> dict[str, dict[str, Any]]:
    if thresholds.is_empty():
        return {}
    rows = thresholds.filter(
        (pl.col("scenario_type") == "baseline")
        & (pl.col("threshold") == THRESHOLDS[0])
        & (pl.col("cost_multiplier") == 1)
    ).to_dicts()
    return {row["scenario"]: row for row in rows}


def _walk_forward_signal_passes(walk_forward: pl.DataFrame) -> set[str]:
    if walk_forward.is_empty():
        return set()
    passed = set()
    for row in walk_forward.filter(pl.col("pass_fail") == "PASS").to_dicts():
        for item in str(row.get("selected_signal_classes") or "").split(","):
            if item:
                passed.add(item)
    return passed


def _cost_config(config: ResearchConfig, multiplier: int) -> ResearchConfig:
    base_cost = config.cost_points_per_side
    base_slippage = config.slippage_points_per_side
    if base_cost + base_slippage <= 0:
        base_cost = 0.5
        base_slippage = 0.0
    return replace(
        config,
        cost_points_per_side=base_cost * multiplier,
        slippage_points_per_side=base_slippage * multiplier,
    )


def _time_slice(frame: pl.DataFrame, start: Any, end: Any) -> pl.DataFrame:
    if frame.is_empty():
        return frame
    return frame.filter((pl.col("event_timestamp") >= start) & (pl.col("event_timestamp") <= end))


def _group_rows(rows: list[dict[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get(key) or "unknown"), []).append(row)
    return grouped


def _add_score_decile(frame: pl.DataFrame) -> pl.DataFrame:
    if frame.is_empty() or "score_decile" in frame.columns:
        return frame
    rows = [{**row, "score_decile": score_decile(row.get("signal_score"))} for row in frame.to_dicts()]
    return pl.DataFrame(rows) if rows else frame


def _sigma_zone(value: Any) -> str:
    number = _float(value)
    if number is None:
        return "unknown"
    absolute = abs(number)
    if absolute <= 1:
        return "inside_1sd"
    if absolute <= 2:
        return "between_1_2sd"
    if absolute <= 3:
        return "between_2_3sd"
    return "outside_3sd"


def _wall_score_bucket(value: Any) -> str:
    number = _float(value)
    if number is None:
        return "unknown"
    if number >= 0.30:
        return "high"
    if number >= 0.15:
        return "medium"
    return "low"


def _first_price_index_after(rows: list[dict[str, Any]], timestamp: Any) -> int | None:
    for index, row in enumerate(rows):
        if row["timestamp"] > timestamp:
            return index
    return None


def _mae_mfe(
    path: list[dict[str, Any]],
    *,
    entry_price: float,
    direction: int,
) -> tuple[float, float]:
    lows = [float(row["low"]) for row in path]
    highs = [float(row["high"]) for row in path]
    if direction > 0:
        return min(low - entry_price for low in lows), max(high - entry_price for high in highs)
    return min(entry_price - high for high in highs), max(entry_price - low for low in lows)


def _max_drawdown(equity: list[float]) -> float:
    peak = 0.0
    max_dd = 0.0
    for value in equity:
        peak = max(peak, value)
        max_dd = min(max_dd, value - peak)
    return max_dd


def _average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _decile_start(label: str) -> int:
    try:
        return int(label.split("-")[0])
    except (ValueError, IndexError):
        return -1


def _none_safe(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _frame_markdown(frame: pl.DataFrame) -> str:
    if frame.is_empty():
        return "_No rows._"
    rows = ["| " + " | ".join(frame.columns) + " |", "|" + "|".join(["---"] * len(frame.columns)) + "|"]
    for raw in frame.head(25).to_dicts():
        rows.append("| " + " | ".join(str(raw.get(column, "")) for column in frame.columns) + " |")
    return "\n".join(rows)


def _write_bar_svg(path: Path, *, title: str, labels: list[str], values: list[float]) -> None:
    width, height = 900, 320
    if not values:
        path.write_text(_svg(title, '<text x="40" y="80">No data.</text>'), encoding="utf-8")
        return
    min_value = min(0.0, min(values))
    max_value = max(0.0, max(values))
    span = max(max_value - min_value, 1.0)
    bar_width = max(8.0, (width - 100) / max(len(values), 1) * 0.72)
    body = []
    zero_y = height - 45 - ((0.0 - min_value) / span) * (height - 90)
    body.append(f'<line x1="40" x2="{width - 40}" y1="{zero_y:.1f}" y2="{zero_y:.1f}" stroke="#9ca3af" />')
    for index, value in enumerate(values):
        x = 50 + index * (width - 100) / max(len(values), 1)
        y = height - 45 - ((max(value, 0.0) - min_value) / span) * (height - 90)
        base_y = height - 45 - ((min(value, 0.0) - min_value) / span) * (height - 90)
        top = min(y, base_y)
        bar_height = max(abs(base_y - y), 1.0)
        body.append(f'<rect x="{x:.1f}" y="{top:.1f}" width="{bar_width:.1f}" height="{bar_height:.1f}" fill="#2563eb" />')
        body.append(f'<text x="{x:.1f}" y="{height - 18}" font-size="10" transform="rotate(35 {x:.1f},{height - 18})">{labels[index]}</text>')
    path.write_text(_svg(title, "\n".join(body)), encoding="utf-8")


def _write_line_svg(path: Path, *, title: str, labels: list[str], values: list[float]) -> None:
    width, height = 900, 300
    if not values:
        path.write_text(_svg(title, '<text x="40" y="80">No data.</text>'), encoding="utf-8")
        return
    minimum, maximum = min(values), max(values)
    span = max(maximum - minimum, 1.0)
    points = []
    for index, value in enumerate(values):
        x = 50 + index * (width - 100) / max(len(values) - 1, 1)
        y = height - 45 - ((value - minimum) / span) * (height - 90)
        points.append(f"{x:.1f},{y:.1f}")
    body = [f'<polyline fill="none" stroke="#0f766e" stroke-width="2" points="{" ".join(points)}" />']
    for index, label in enumerate(labels):
        x = 50 + index * (width - 100) / max(len(values) - 1, 1)
        body.append(f'<text x="{x:.1f}" y="{height - 18}" font-size="11">{label}</text>')
    path.write_text(_svg(title, "\n".join(body)), encoding="utf-8")


def _write_scatter_svg(path: Path, *, title: str, rows: list[dict[str, Any]]) -> None:
    width, height = 900, 300
    if not rows:
        path.write_text(_svg(title, '<text x="40" y="80">No data.</text>'), encoding="utf-8")
        return
    x_values = [float(row.get("signal_score") or 0.0) for row in rows]
    y_values = [float(row.get("net_pnl_points") or 0.0) for row in rows]
    min_y, max_y = min(y_values), max(y_values)
    span_y = max(max_y - min_y, 1.0)
    body = []
    for x_value, y_value in zip(x_values, y_values, strict=False):
        x = 45 + (x_value / 100.0) * (width - 90)
        y = height - 45 - ((y_value - min_y) / span_y) * (height - 90)
        body.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="#dc2626" opacity="0.65" />')
    path.write_text(_svg(title, "\n".join(body)), encoding="utf-8")


def _svg(title: str, body: str) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="320" '
        'viewBox="0 0 900 320">'
        '<rect width="900" height="320" fill="#ffffff" />'
        f'<text x="40" y="30" font-size="18" font-family="Arial">{title}</text>'
        f"{body}</svg>"
    )


def _empty_performance() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "group_type": pl.String,
            "bucket": pl.String,
            "event_count": pl.Int64,
            "trade_count": pl.Int64,
            "win_rate": pl.Float64,
            "average_win": pl.Float64,
            "average_loss": pl.Float64,
            "expectancy": pl.Float64,
            "profit_factor": pl.Float64,
            "max_drawdown": pl.Float64,
            "average_mae": pl.Float64,
            "average_mfe": pl.Float64,
            "average_holding_time": pl.Float64,
            "sample_size_warning": pl.Boolean,
        }
    )


def _empty_threshold_performance() -> pl.DataFrame:
    return _empty_performance().with_columns(
        pl.lit(None).cast(pl.Int64).alias("threshold"),
        pl.lit(None).cast(pl.String).alias("scenario"),
        pl.lit(None).cast(pl.String).alias("scenario_type"),
        pl.lit(None).cast(pl.Int64).alias("cost_multiplier"),
        pl.lit(None).cast(pl.Float64).alias("cost_points_per_side"),
        pl.lit(None).cast(pl.Float64).alias("slippage_points_per_side"),
    )


def _empty_walk_forward() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "split_id": pl.Int64,
            "train_start": pl.Datetime(time_zone="UTC"),
            "train_end": pl.Datetime(time_zone="UTC"),
            "test_start": pl.Datetime(time_zone="UTC"),
            "test_end": pl.Datetime(time_zone="UTC"),
            "selected_threshold": pl.Int64,
            "selected_signal_classes": pl.String,
            "test_event_count": pl.Int64,
            "test_trade_count": pl.Int64,
            "test_expectancy": pl.Float64,
            "test_profit_factor": pl.Float64,
            "test_max_drawdown": pl.Float64,
            "pass_fail": pl.String,
        }
    )


def _empty_ablation() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "removed_component": pl.String,
            "threshold": pl.Int64,
            "baseline_expectancy": pl.Float64,
            "ablated_expectancy": pl.Float64,
            "change_in_expectancy": pl.Float64,
            "baseline_profit_factor": pl.Float64,
            "ablated_profit_factor": pl.Float64,
            "change_in_profit_factor": pl.Float64,
            "baseline_trade_count": pl.Int64,
            "ablated_trade_count": pl.Int64,
            "change_in_trade_count": pl.Int64,
            "baseline_no_trade_count": pl.Int64,
            "ablated_no_trade_count": pl.Int64,
            "change_in_no_trade_count": pl.Int64,
            "impact": pl.String,
        }
    )


def _empty_kill_list() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "signal_label": pl.String,
            "reason": pl.String,
            "trade_count": pl.Int64,
            "expectancy": pl.Float64,
            "profit_factor": pl.Float64,
            "walk_forward_pass": pl.Boolean,
            "recommendation": pl.String,
        }
    )


def _empty_score_trades() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "event_timestamp": pl.Datetime(time_zone="UTC"),
            "signal_label": pl.String,
            "signal": pl.String,
            "trade_direction": pl.String,
            "signal_score": pl.Int64,
            "score_decile": pl.String,
            "net_pnl_points": pl.Float64,
            "mae_points": pl.Float64,
            "mfe_points": pl.Float64,
            "time_in_trade_bars": pl.Int64,
        }
    )


def _empty_scores_enriched() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "event_timestamp": pl.Datetime(time_zone="UTC"),
            "source_bar_timestamp": pl.Datetime(time_zone="UTC"),
            "signal_label": pl.String,
            "signal_score": pl.Int64,
            "trade_direction": pl.String,
            "score_decile": pl.String,
            "sigma_zone": pl.String,
            "wall_score_bucket": pl.String,
            "dte_bucket": pl.String,
            "vol_regime": pl.String,
        }
    )
