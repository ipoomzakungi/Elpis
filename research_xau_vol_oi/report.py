"""Pipeline orchestration, output writing, charts, and Markdown report creation."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import polars as pl

from research_xau_vol_oi.backtest import (
    backtest_all_scenarios,
    run_cost_stress,
    walk_forward_validate,
)
from research_xau_vol_oi.basis_mapper import add_basis_columns
from research_xau_vol_oi.config import ResearchConfig
from research_xau_vol_oi.data_loader import (
    DataLoadError,
    discover_data_files,
    load_table,
    standardize_options_frame,
    standardize_price_frame,
)
from research_xau_vol_oi.expected_move import add_expected_move_columns_asof_options
from research_xau_vol_oi.guru_episode_dataset import (
    GuruEpisodeDatasetResult,
    run_guru_episode_dataset_layer,
)
from research_xau_vol_oi.guru_review_queue import (
    GuruReviewQueueResult,
    run_guru_review_queue_layer,
)
from research_xau_vol_oi.llm_transcript_extractor import (
    LlmTranscriptExtractionResult,
    run_llm_transcript_extraction_layer,
)
from research_xau_vol_oi.oi_wall_engine import build_oi_walls
from research_xau_vol_oi.score_calibration import (
    ScoreCalibrationResult,
    run_score_research_layer,
)
from research_xau_vol_oi.signal_score import score_signal_events, write_signal_dashboard
from research_xau_vol_oi.transcript_timeline import (
    TranscriptTimelineResult,
    run_transcript_timeline_layer,
)
from research_xau_vol_oi.transcript_uplift import (
    TranscriptUpliftResult,
    run_transcript_uplift_layer,
)
from research_xau_vol_oi.volatility_engine import (
    add_bollinger_baseline,
    add_realized_volatility,
    add_volatility_regime,
)
from research_xau_vol_oi.zone_classifier import build_signal_events, choose_wall_for_bar


def run_pipeline(
    *,
    price_path: str | Path | None = None,
    options_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    config: ResearchConfig | None = None,
) -> dict[str, Path]:
    """Run the local research pipeline and write requested outputs."""

    cfg = config or ResearchConfig()
    if output_dir is not None:
        cfg = ResearchConfig(output_dir=Path(output_dir))

    selected_price, selected_options = select_default_inputs(
        price_path=price_path,
        options_path=options_path,
    )
    output_root = cfg.output_dir
    charts_dir = output_root / cfg.chart_dir_name
    output_root.mkdir(parents=True, exist_ok=True)
    charts_dir.mkdir(parents=True, exist_ok=True)

    inventory = discover_data_files(config=cfg)
    inventory.write_csv(output_root / "data_inventory.csv")

    price_raw = load_table(selected_price)
    options_raw = load_table(selected_options)
    price = standardize_price_frame(price_raw, source_path=selected_price, config=cfg)
    options = standardize_options_frame(options_raw, source_path=selected_options, config=cfg)
    options = add_basis_columns(options)
    reference_price = _reference_price(price, options)
    price_features = add_expected_move_columns_asof_options(price, options, config=cfg)
    price_features = add_realized_volatility(price_features)
    price_features = add_volatility_regime(price_features)
    price_features = add_bollinger_baseline(price_features)

    latest_one_sd = _first_non_null(price_features, "one_sd_remaining")
    walls = build_oi_walls(
        options,
        reference_price=reference_price,
        one_sd_remaining=latest_one_sd,
        config=cfg,
    )
    feature_table = attach_wall_context(price_features, walls, config=cfg)
    signal_events = build_signal_events(feature_table, walls, config=cfg)
    signal_scores = score_signal_events(feature_table, signal_events, config=cfg)
    trades, summary = backtest_all_scenarios(feature_table, signal_events, config=cfg)
    walk_forward = walk_forward_validate(feature_table, signal_events, config=cfg)
    cost_stress = run_cost_stress(feature_table, signal_events, config=cfg)
    score_calibration = run_score_research_layer(
        price_features=feature_table,
        signal_events=signal_events,
        signal_scores=signal_scores,
        output_dir=output_root,
        charts_dir=charts_dir,
        config=cfg,
    )
    transcript_timeline = run_transcript_timeline_layer(
        feature_table=feature_table,
        signal_events=signal_events,
        trades=trades,
        output_dir=output_root,
        charts_dir=charts_dir,
        config=cfg,
    )
    llm_transcript_extraction = run_llm_transcript_extraction_layer(
        transcript_timeline=transcript_timeline.timeline,
        output_dir=output_root,
        config=cfg,
    )
    guru_review = run_guru_review_queue_layer(
        extracted_rules=llm_transcript_extraction.extracted_rules,
        quality_audit=llm_transcript_extraction.quality_audit,
        signal_events=signal_events,
        feature_table=feature_table,
        output_dir=output_root,
        config=cfg,
    )
    transcript_uplift = run_transcript_uplift_layer(
        feature_table=feature_table,
        signal_events=signal_events,
        trades=trades,
        transcript_timeline=transcript_timeline.timeline,
        output_dir=output_root,
        charts_dir=charts_dir,
        config=cfg,
        approved_rule_records=guru_review.approved_rules,
        review_decisions_exist=guru_review.review_decisions_exist,
    )
    guru_episode_dataset = run_guru_episode_dataset_layer(
        review_queue=guru_review.review_queue,
        feature_table=feature_table,
        signal_events=signal_events,
        trades=trades,
        output_dir=output_root,
        charts_dir=charts_dir,
        config=cfg,
    )

    feature_path = output_root / "xau_feature_table.parquet"
    events_path = output_root / "signal_events.csv"
    summary_path = output_root / "backtest_summary.csv"
    feature_table.write_parquet(feature_path)
    signal_events.write_csv(events_path)
    summary.write_csv(summary_path)
    signal_scores.write_csv(output_root / "signal_score_examples.csv")
    trades.write_csv(output_root / "backtest_trades.csv")
    walk_forward.write_csv(output_root / "walk_forward_validation.csv")
    cost_stress.write_csv(output_root / "transaction_cost_stress.csv")
    walls.write_csv(output_root / "oi_walls.csv")
    write_signal_dashboard(output_root / "signal_dashboard.html", signal_scores)

    write_charts(
        feature_table=feature_table,
        walls=walls,
        events=signal_events,
        trades=trades,
        summary=summary,
        chart_dir=charts_dir,
    )
    report_path = output_root / "research_report.md"
    write_research_report(
        report_path,
        price_path=selected_price,
        options_path=selected_options,
        inventory=inventory,
        feature_table=feature_table,
        events=signal_events,
        trades=trades,
        summary=summary,
        walk_forward=walk_forward,
        cost_stress=cost_stress,
        score_calibration=score_calibration,
        transcript_timeline=transcript_timeline,
        transcript_uplift=transcript_uplift,
        llm_transcript_extraction=llm_transcript_extraction,
        guru_review=guru_review,
        guru_episode_dataset=guru_episode_dataset,
        charts_dir=charts_dir,
    )
    audit_path = output_root / "leakage_audit_report.md"
    write_leakage_audit_report(
        audit_path,
        feature_table=feature_table,
        events=signal_events,
        summary=summary,
        walk_forward=walk_forward,
        cost_stress=cost_stress,
    )
    return {
        "feature_table": feature_path,
        "signal_events": events_path,
        "signal_score_examples": output_root / "signal_score_examples.csv",
        "score_decile_performance": output_root / "score_decile_performance.csv",
        "score_threshold_performance": output_root / "score_threshold_performance.csv",
        "score_calibration_report": output_root / "score_calibration_report.md",
        "score_ablation_report": output_root / "score_ablation_report.md",
        "signal_kill_list": output_root / "signal_kill_list.csv",
        "threshold_policy_recommendation": output_root / "threshold_policy_recommendation.csv",
        "transcript_rule_timeline": output_root / "transcript_rule_timeline.csv",
        "transcript_rule_coverage": output_root / "transcript_rule_coverage.csv",
        "transcript_market_alignment": output_root / "transcript_market_alignment.csv",
        "transcript_rule_performance": output_root / "transcript_rule_performance.csv",
        "transcript_rule_ablation": output_root / "transcript_rule_ablation.csv",
        "transcript_alignment_report": output_root / "transcript_alignment_report.md",
        "transcript_conditioned_events": output_root / "transcript_conditioned_events.csv",
        "transcript_rule_uplift": output_root / "transcript_rule_uplift.csv",
        "transcript_rule_combination_uplift": output_root / "transcript_rule_combination_uplift.csv",
        "transcript_walk_forward_uplift": output_root / "transcript_walk_forward_uplift.csv",
        "transcript_placebo_tests": output_root / "transcript_placebo_tests.csv",
        "transcript_rule_keep_kill": output_root / "transcript_rule_keep_kill.csv",
        "transcript_uplift_report": output_root / "transcript_uplift_report.md",
        "transcript_approved_rule_uplift": output_root / "transcript_approved_rule_uplift.csv",
        "transcript_approved_walk_forward_uplift": output_root / "transcript_approved_walk_forward_uplift.csv",
        "transcript_llm_extracted_rules": output_root / "transcript_llm_extracted_rules.csv",
        "transcript_rule_quality_audit": output_root / "transcript_rule_quality_audit.csv",
        "transcript_extraction_audit_report": output_root / "transcript_extraction_audit_report.md",
        "guru_rule_review_queue": output_root / "guru_rule_review_queue.csv",
        "guru_rule_review_sample": output_root / "guru_rule_review_sample.csv",
        "guru_rule_review_decisions_template": output_root / "guru_rule_review_decisions_template.csv",
        "guru_rule_review_report": output_root / "guru_rule_review_report.md",
        "guru_decision_episodes": output_root / "guru_decision_episodes.csv",
        "guru_episode_outcomes": output_root / "guru_episode_outcomes.csv",
        "guru_episode_rule_performance": output_root / "guru_episode_rule_performance.csv",
        "guru_episode_review_sample": output_root / "guru_episode_review_sample.csv",
        "guru_episode_review_dashboard": output_root / "guru_episode_review_dashboard.html",
        "guru_episode_review_decisions_template": output_root / "guru_episode_review_decisions_template.csv",
        "guru_episode_review_guide": output_root / "guru_episode_review_guide.md",
        "guru_episode_report": output_root / "guru_episode_report.md",
        "backtest_summary": summary_path,
        "research_report": report_path,
        "leakage_audit_report": audit_path,
        "signal_dashboard": output_root / "signal_dashboard.html",
        "charts": charts_dir,
    }


def select_default_inputs(
    *,
    price_path: str | Path | None,
    options_path: str | Path | None,
) -> tuple[Path, Path]:
    """Select local defaults when explicit paths are not supplied."""

    if price_path is not None and options_path is not None:
        return Path(price_path), Path(options_path)

    default_price = Path("data/raw/yahoo/gc=f_15m_ohlcv_20260513_20260521.parquet")
    default_options = Path("backend/data/raw/xau/quikstrike_20260513_101537_xau_vol_oi_input.csv")
    if price_path is None and not default_price.exists():
        candidates = sorted(Path("data/raw/yahoo").glob("*ohlcv*.parquet"))
        if not candidates:
            raise DataLoadError("No default Yahoo/price OHLCV parquet file was found.")
        default_price = candidates[-1]
    if options_path is None and not default_options.exists():
        candidates = sorted(Path("backend/data/raw/xau").glob("*xau*oi*.csv"))
        if not candidates:
            raise DataLoadError("No default XAU options OI CSV file was found.")
        default_options = candidates[-1]
    return Path(price_path or default_price), Path(options_path or default_options)


def attach_wall_context(
    price_features: pl.DataFrame,
    walls: pl.DataFrame,
    *,
    config: ResearchConfig | None = None,
) -> pl.DataFrame:
    """Attach nearest available wall fields to every price feature row."""

    cfg = config or ResearchConfig()
    wall_rows = walls.to_dicts() if not walls.is_empty() else []
    rows: list[dict[str, Any]] = []
    for row in price_features.to_dicts():
        wall = choose_wall_for_bar(row, wall_rows, config=cfg)
        rows.append(
            {
                **row,
                "wall_id": wall.get("wall_id") if wall else None,
                "wall_level": wall.get("wall_level") if wall else None,
                "wall_score": wall.get("wall_score") if wall else None,
                "wall_score_bucket": _wall_score_bucket(wall.get("wall_score") if wall else None),
                "distance_to_nearest_wall": wall.get("distance_to_spot") if wall else None,
                "freshness_weight": wall.get("freshness_weight") if wall else None,
                "dte_weight": wall.get("dte_weight") if wall else None,
                "proximity_weight": wall.get("proximity_weight") if wall else None,
                "wall_side": wall.get("wall_side") if wall else None,
                "dte": wall.get("dte") if wall else None,
                "dte_bucket": _dte_bucket(wall.get("dte") if wall else None),
                "basis": wall.get("basis") if wall else None,
                "basis_source": wall.get("basis_source") if wall else None,
                "basis_available": wall.get("basis_available", wall.get("basis") is not None)
                if wall
                else False,
                "largest_near_expiry_wall": wall.get("largest_near_expiry_wall") if wall else False,
                "low_oi_gap_to_next_wall": wall.get("low_oi_gap_to_next_wall") if wall else False,
                "next_wall_distance": wall.get("next_wall_distance") if wall else None,
            }
        )
    return pl.DataFrame(rows) if rows else price_features


def write_charts(
    *,
    feature_table: pl.DataFrame,
    walls: pl.DataFrame,
    events: pl.DataFrame,
    trades: pl.DataFrame,
    summary: pl.DataFrame,
    chart_dir: Path,
) -> None:
    """Write lightweight SVG chart artifacts without adding plotting dependencies."""

    prices = [(row["timestamp"], row["close"]) for row in feature_table.to_dicts()]
    _write_line_svg(
        chart_dir / "xau_price_sd_bands.svg",
        title="XAU price with IV 1SD/2SD/3SD bands",
        series=[float(row["close"]) for row in feature_table.to_dicts()],
    )
    _write_bar_svg(
        chart_dir / "spot_adjusted_oi_walls.svg",
        title="Spot-adjusted OI walls",
        labels=[str(row.get("strike")) for row in walls.to_dicts()],
        values=[float(row.get("wall_level") or 0.0) for row in walls.to_dicts()],
    )
    _write_bar_svg(
        chart_dir / "wall_score_heatmap.svg",
        title="Wall score heatmap",
        labels=[str(row.get("strike")) for row in walls.to_dicts()],
        values=[float(row.get("wall_score") or 0.0) for row in walls.to_dicts()],
    )
    _write_marker_svg(
        chart_dir / "signal_markers.svg",
        title="Signal markers",
        count=len(events),
        labels=[str(row.get("signal")) for row in events.head(20).to_dicts()],
    )
    _write_line_svg(
        chart_dir / "equity_curve_by_signal_type.svg",
        title="Equity curve by signal type",
        series=_equity_curve(trades),
    )
    _write_bar_svg(
        chart_dir / "expectancy_by_sigma_zone.svg",
        title="Expectancy by sigma zone",
        labels=_summary_labels(summary, "sigma_zone"),
        values=_summary_values(summary, "sigma_zone"),
    )
    _write_bar_svg(
        chart_dir / "expectancy_by_wall_score_bucket.svg",
        title="Expectancy by wall_score bucket",
        labels=_summary_labels(summary, "wall_score_bucket"),
        values=_summary_values(summary, "wall_score_bucket"),
    )
    _write_marker_svg(
        chart_dir / "confusion_wall_reject_vs_break.svg",
        title="Confusion table: wall reject vs wall break",
        count=len(prices),
        labels=_confusion_labels(events),
    )


def write_research_report(
    path: Path,
    *,
    price_path: Path,
    options_path: Path,
    inventory: pl.DataFrame,
    feature_table: pl.DataFrame,
    events: pl.DataFrame,
    trades: pl.DataFrame,
    summary: pl.DataFrame,
    walk_forward: pl.DataFrame,
    cost_stress: pl.DataFrame,
    score_calibration: ScoreCalibrationResult | None = None,
    transcript_timeline: TranscriptTimelineResult | None = None,
    transcript_uplift: TranscriptUpliftResult | None = None,
    llm_transcript_extraction: LlmTranscriptExtractionResult | None = None,
    guru_review: GuruReviewQueueResult | None = None,
    guru_episode_dataset: GuruEpisodeDatasetResult | None = None,
    charts_dir: Path,
) -> None:
    """Write a research report that answers the requested evaluation questions."""

    signal_counts = events.group_by("signal").len().sort("signal") if not events.is_empty() else pl.DataFrame()
    directional = summary.filter(pl.col("group_type") == "signal") if not summary.is_empty() else pl.DataFrame()
    answers = _answer_questions(directional)
    text = [
        "# XAU/USD Vol-OI Research Report",
        "",
        "This report is a local research artifact. It is not a live trading bot, "
        "not an order system, and not evidence of live readiness.",
        "",
        "## Inputs",
        "",
        f"- Price data: `{price_path}`",
        f"- CME/options data: `{options_path}`",
        f"- Inventory files found: {inventory.height}",
        f"- Feature rows: {feature_table.height}",
        f"- Signal events: {events.height}",
        f"- Backtest trades/control observations: {trades.height}",
        f"- Walk-forward splits: {walk_forward.height}",
        f"- Cost-stress rows: {cost_stress.height}",
        "",
        "## Available Data Inventory",
        "",
        *_inventory_lines(inventory),
        "",
        "## Signal Counts",
        "",
        _frame_markdown(signal_counts),
        "",
        "## Backtest Summary",
        "",
        _frame_markdown(directional),
        "",
        "## No-Trade Coverage",
        "",
        _frame_markdown(
            summary.filter(pl.col("group_type") == "signal_coverage")
            if not summary.is_empty()
            else pl.DataFrame()
        ),
        "",
        "## Transaction Cost Stress",
        "",
        _frame_markdown(cost_stress),
        "",
        "## Signal Score Calibration",
        "",
        *_score_calibration_lines(score_calibration),
        "",
        "## Guru Transcript Timeline Alignment",
        "",
        *_transcript_timeline_lines(transcript_timeline),
        "",
        "## Transcript-Conditioned Uplift Test",
        "",
        *_transcript_uplift_lines(transcript_uplift),
        "",
        "## LLM Transcript Extraction Audit",
        "",
        *_llm_transcript_extraction_lines(llm_transcript_extraction),
        "",
        "## Guru Logic Review Queue",
        "",
        *_guru_review_lines(guru_review, transcript_uplift),
        "",
        "## Guru Decision Episode Dataset",
        "",
        *_guru_episode_lines(guru_episode_dataset),
        "",
        "## Required Questions",
        "",
        *answers,
        "",
        "## Charts",
        "",
        *[f"- `{path.name}`" for path in sorted(charts_dir.glob('*.svg'))],
        "",
        "## Limitations",
        "",
        "- Yahoo GC=F is a futures OHLCV proxy and is not true XAUUSD spot.",
        "- OI wall data quality depends on imported CME/QuikStrike-style files.",
        "- The current pipeline uses deterministic thresholds and walk-forward splits; "
        "thresholds should be selected in formation periods only.",
        "- No result here should be read as a profitability, prediction, safety, or "
        "live-readiness claim.",
        "",
        "## Next Tests",
        "",
        "- Add longer CME options history with verified timestamp availability.",
        "- Compare basis-adjusted walls against unadjusted walls on the same windows.",
        "- Separate news-disabled windows and session-specific behavior.",
        "- Validate transcript-derived rules one rule at a time before combining them.",
    ]
    path.write_text("\n".join(text), encoding="utf-8")


def write_leakage_audit_report(
    path: Path,
    *,
    feature_table: pl.DataFrame,
    events: pl.DataFrame,
    summary: pl.DataFrame,
    walk_forward: pl.DataFrame,
    cost_stress: pl.DataFrame,
) -> None:
    """Write a direct leakage, assumptions, and false-edge audit."""

    future_iv = _count_future_timestamp(
        feature_table,
        known_col="iv_available_timestamp",
        event_col="timestamp",
    )
    future_wall = _count_future_timestamp(
        events,
        known_col="available_wall_timestamp",
        event_col="event_timestamp",
    )
    no_trade_rows = (
        events.filter(pl.col("signal").str.starts_with("NO_TRADE")).height
        if not events.is_empty()
        else 0
    )
    killed = _kill_candidates(summary)
    threshold_risks = [
        "`strong_wall_score`, `pin_wall_score`, and `min_wall_score` need formation-period selection.",
        "`acceptance_buffer_points` can overfit bar size and instrument volatility.",
        "`proximity_points` and `proximity_sd_fraction` can overfit how close a wall must be.",
        "`backtest_horizon_bars` can overfit exit timing.",
        "`walk_forward_train_bars` and `walk_forward_test_bars` define validation granularity.",
    ]
    lines = [
        "# XAU Vol-OI Leakage Audit Report",
        "",
        "This audit checks whether the local research pipeline is using information before "
        "it would be known. It does not certify a trading edge.",
        "",
        "## Findings",
        "",
        f"- Future IV used before availability: {future_iv}",
        f"- Future OI/wall used before event timestamp: {future_wall}",
        "- Futures strike mapping: implemented as `spot_equivalent_strike = strike - basis`; "
        "basis is row/session sourced when futures and spot are present, otherwise missing.",
        "- IV bands: patched to use only the latest option IV timestamp at or before each bar; "
        "pre-IV bars are retained as `NO_TRADE` via `MISSING_IV`.",
        "- Break labels: close-plus-next-bar-hold is resolved at the confirmation bar timestamp.",
        f"- No-trade rows retained in signal events: {no_trade_rows}",
        "",
        "## Baselines",
        "",
        _frame_markdown(
            summary.filter(pl.col("group_type") == "signal")
            if not summary.is_empty()
            else pl.DataFrame()
        ),
        "",
        "## Walk-Forward",
        "",
        _frame_markdown(walk_forward),
        "",
        "## Transaction Cost And Slippage Stress",
        "",
        _frame_markdown(cost_stress),
        "",
        "## Overfit Thresholds",
        "",
        *[f"- {item}" for item in threshold_risks],
        "",
        "## Signal Classes To Kill Or Quarantine",
        "",
        *[f"- {item}" for item in killed],
        "",
        "## Required Code Changes Made",
        "",
        "- IV expected-move bands now use as-of option IV snapshots.",
        "- Bars before IV availability are kept and marked `MISSING_IV`, producing no-trade labels.",
        "- Wall proximity, wall side, and event wall score are recomputed at the signal bar.",
        "- Added OI-wall-only and Bollinger baselines.",
        "- Added net PnL after configurable transaction cost and slippage.",
        "- Added walk-forward performance fields and transaction cost stress output.",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _score_calibration_lines(score_calibration: ScoreCalibrationResult | None) -> list[str]:
    if score_calibration is None:
        return ["Score calibration was not run."]
    policy = (
        score_calibration.threshold_policy.to_dicts()[0]
        if not score_calibration.threshold_policy.is_empty()
        else {}
    )
    kill_rows = (
        score_calibration.kill_list.select(
            ["signal_label", "recommendation", "reason", "trade_count", "expectancy", "profit_factor"]
        )
        if not score_calibration.kill_list.is_empty()
        else score_calibration.kill_list
    )
    threshold_rows = (
        score_calibration.score_threshold_performance.filter(
            (pl.col("scenario_type") == "vol_oi_score")
            & (pl.col("cost_multiplier") == 1)
        )
        if not score_calibration.score_threshold_performance.is_empty()
        else score_calibration.score_threshold_performance
    )
    decile_rows = (
        score_calibration.score_decile_performance.filter(pl.col("group_type") == "score_decile")
        if not score_calibration.score_decile_performance.is_empty()
        else score_calibration.score_decile_performance
    )
    ablation_rows = score_calibration.ablation.select(
        [
            "removed_component",
            "change_in_expectancy",
            "change_in_profit_factor",
            "change_in_trade_count",
            "change_in_no_trade_count",
            "impact",
        ]
    ) if not score_calibration.ablation.is_empty() else score_calibration.ablation
    return [
        f"- Final Research Decision: `{score_calibration.final_decision}`",
        f"- Score monotonicity: `{score_calibration.monotonicity['monotonic_status']}`",
        f"- Threshold policy: `{policy.get('policy', 'unknown')}`",
        f"- Policy recommendation: {policy.get('recommendation', 'n/a')}",
        "",
        "### Score Decile Results",
        "",
        _frame_markdown(decile_rows),
        "",
        "### Threshold Results",
        "",
        _frame_markdown(threshold_rows),
        "",
        "### Walk-Forward Score Results",
        "",
        _frame_markdown(score_calibration.walk_forward_score),
        "",
        "### Feature Ablation Results",
        "",
        _frame_markdown(ablation_rows),
        "",
        "### Kill / Quarantine Recommendations",
        "",
        _frame_markdown(kill_rows),
    ]


def _transcript_timeline_lines(transcript_timeline: TranscriptTimelineResult | None) -> list[str]:
    if transcript_timeline is None:
        return ["Transcript timeline alignment was not run."]
    supported = (
        transcript_timeline.performance.filter(
            pl.col("decision_label") == "TRANSCRIPT_RULE_SUPPORTED"
        )
        if not transcript_timeline.performance.is_empty()
        else transcript_timeline.performance
    )
    failed = (
        transcript_timeline.performance.filter(pl.col("decision_label") == "TRANSCRIPT_RULE_FAILED")
        if not transcript_timeline.performance.is_empty()
        else transcript_timeline.performance
    )
    coverage = (
        transcript_timeline.coverage.sort("transcript_count", descending=True)
        if not transcript_timeline.coverage.is_empty()
        else transcript_timeline.coverage
    )
    performance = (
        transcript_timeline.performance.filter(pl.col("window_label") == "5_session")
        if not transcript_timeline.performance.is_empty()
        else transcript_timeline.performance
    )
    ablation = (
        transcript_timeline.ablation.select(
            [
                "rule_tag",
                "change_in_expectancy",
                "change_in_profit_factor",
                "covered_event_count",
                "decision_label",
            ]
        )
        if not transcript_timeline.ablation.is_empty()
        else transcript_timeline.ablation
    )
    leakage_violations = (
        int(transcript_timeline.alignment.get_column("no_lookahead_violations").sum())
        if not transcript_timeline.alignment.is_empty()
        else 0
    )
    return [
        f"- Final Decision: `{transcript_timeline.final_decision}`",
        f"- Parsed transcripts: {transcript_timeline.timeline.height}",
        f"- Transcript alignment no-lookahead violations: {leakage_violations}",
        "- Rule performance uses unique post-availability event keys to avoid counting the same "
        "trade multiple times across overlapping transcript windows.",
        "- The transcript layer improves dated rule traceability; it has not proven independent "
        "signal-quality improvement.",
        "",
        "### Rule Tag Coverage",
        "",
        _frame_markdown(coverage),
        "",
        "### Rule-by-Rule Performance",
        "",
        _frame_markdown(performance),
        "",
        "### Transcript Rule Ablation",
        "",
        _frame_markdown(ablation),
        "",
        "### Supported Guru Rules",
        "",
        _frame_markdown(supported),
        "",
        "### Failed Guru Rules",
        "",
        _frame_markdown(failed),
        "",
        "### Final Decision",
        "",
        "Transcript rules are treated as dated evidence only. They are not allowed to explain "
        "events before their availability timestamp, no-trade rows are retained, and no "
        "profitability claim is made from this alignment layer.",
    ]


def _transcript_uplift_lines(transcript_uplift: TranscriptUpliftResult | None) -> list[str]:
    if transcript_uplift is None:
        return ["Transcript-conditioned uplift testing was not run."]
    rule_rows = (
        transcript_uplift.rule_uplift.select(
            [
                "rule_id",
                "rule_type",
                "event_count",
                "directional_trade_count",
                "no_trade_count",
                "expectancy",
                "profit_factor",
                "sample_size_warning",
                "uplift_vs_no_tag",
                "uplift_vs_base_score",
                "uplift_vs_bollinger_baseline",
                "uplift_vs_random_baseline",
            ]
        )
        if not transcript_uplift.rule_uplift.is_empty()
        else transcript_uplift.rule_uplift
    )
    combination_rows = (
        transcript_uplift.combination_uplift.select(
            [
                "rule_id",
                "rule_type",
                "event_count",
                "directional_trade_count",
                "no_trade_count",
                "expectancy",
                "profit_factor",
                "sample_size_warning",
                "uplift_vs_no_tag",
                "uplift_vs_base_score",
            ]
        )
        if not transcript_uplift.combination_uplift.is_empty()
        else transcript_uplift.combination_uplift
    )
    no_trade_count = (
        transcript_uplift.conditioned_events.filter(pl.col("no_trade_row_retained")).height
        if not transcript_uplift.conditioned_events.is_empty()
        else 0
    )
    return [
        f"- Final Decision: `{transcript_uplift.final_decision}`",
        f"- Conditioned signal events: {transcript_uplift.conditioned_events.height}",
        f"- No-trade rows retained: {no_trade_count}",
        "- Same market events are deduplicated before uplift metrics are calculated.",
        "- Placebo and walk-forward checks must pass before transcript rules can become filters.",
        "",
        "### Rule Tag Uplift",
        "",
        _frame_markdown(rule_rows),
        "",
        "### Rule Combination Uplift",
        "",
        _frame_markdown(combination_rows),
        "",
        "### Walk-Forward Transcript Uplift",
        "",
        _frame_markdown(transcript_uplift.walk_forward_uplift),
        "",
        "### Placebo Tests",
        "",
        _frame_markdown(transcript_uplift.placebo_tests),
        "",
        "### Transcript Rule Keep/Kill Decision",
        "",
        _frame_markdown(transcript_uplift.keep_kill),
        "",
        "### Final Decision",
        "",
        "Transcript-conditioned uplift is treated as a filter-validation problem, not a "
        "profitability claim. `LEAKAGE_PLACEBO` is an intentionally invalid negative control.",
    ]


def _llm_transcript_extraction_lines(
    extraction: LlmTranscriptExtractionResult | None,
) -> list[str]:
    if extraction is None:
        return ["LLM transcript extraction audit was not run."]
    quality_counts = (
        extraction.quality_audit.group_by("rule_quality").len().sort("rule_quality")
        if not extraction.quality_audit.is_empty()
        else extraction.quality_audit
    )
    testable = (
        extraction.quality_audit.filter(
            pl.col("rule_quality").is_in(
                ["TESTABLE_AND_OBSERVABLE", "TESTABLE_BUT_NEEDS_DATA"]
            )
        )
        if not extraction.quality_audit.is_empty()
        else extraction.quality_audit
    )
    context = (
        extraction.quality_audit.filter(
            pl.col("rule_quality").is_in(
                ["CONTEXT_ONLY", "POST_EVENT_COMMENTARY", "UNTESTABLE_OPINION"]
            )
        )
        if not extraction.quality_audit.is_empty()
        else extraction.quality_audit
    )
    rejected = (
        extraction.quality_audit.filter(pl.col("rule_quality") == "REJECT_LEAKAGE_RISK")
        if not extraction.quality_audit.is_empty()
        else extraction.quality_audit
    )
    return [
        f"- Final Decision: `{extraction.final_decision}`",
        f"- Extraction mode: `{extraction.extraction_mode}`",
        f"- Extracted structured records: {extraction.extracted_rules.height}",
        "- Current production transcript tagging is deterministic keyword/rule based, not semantic LLM extraction.",
        "- The optional LLM-style path accepts JSON/JSONL records only and treats them as research features.",
        "- LLM output is not allowed to create direct trade signals; it must pass backtest, walk-forward, and placebo validation.",
        "",
        "### Guru Rule Testability",
        "",
        _frame_markdown(quality_counts),
        "",
        "### Keyword vs LLM Extraction Risk",
        "",
        "- Thai ASR noise can miss distorted forms of IV/RV/VRP, skew, gamma, acceptance, rejection, and basis language.",
        "- Simple keywords can falsely trigger broad tags such as OI wall, volume, no-trade, open-price, news, and gamma.",
        "- Source excerpts are now stored with each structured record for audit review.",
        "",
        "### Which Guru Rules Are Testable",
        "",
        _frame_markdown(testable),
        "",
        "### Which Guru Rules Are Context Only",
        "",
        _frame_markdown(context),
        "",
        "### Which Guru Rules Are Rejected",
        "",
        _frame_markdown(rejected),
    ]


def _guru_review_lines(
    guru_review: GuruReviewQueueResult | None,
    transcript_uplift: TranscriptUpliftResult | None,
) -> list[str]:
    if guru_review is None:
        return ["Guru logic review queue was not run."]
    priority_counts = (
        guru_review.review_queue.group_by("suggested_review_priority").len().sort("suggested_review_priority")
        if not guru_review.review_queue.is_empty()
        else guru_review.review_queue
    )
    approved_count = guru_review.approved_rules.height
    approved_status = transcript_uplift.approved_only_status if transcript_uplift is not None else "UNKNOWN"
    top_priorities = (
        guru_review.review_queue.select(
            [
                "review_id",
                "rule_tag",
                "rule_type",
                "quality_label",
                "suggested_review_priority",
                "leakage_risk_score",
                "extracted_numeric_levels",
                "likely_srt_timestamp_artifact",
                "timestamp_like_numeric_levels",
            ]
        ).head(25)
        if not guru_review.review_queue.is_empty()
        else guru_review.review_queue
    )
    return [
        f"- Final Decision: `{guru_review.final_decision}`",
        f"- Review queue rows: {guru_review.review_queue.height}",
        f"- Approved rules available: {approved_count}",
        f"- Review decisions exist: {guru_review.review_decisions_exist}",
        f"- Approved-only uplift status: `{approved_status}`",
        "- Human approval is required before transcript rules can be used for predictive claims.",
        "",
        "### Reviewed vs Unreviewed Rule Status",
        "",
        _frame_markdown(priority_counts),
        "",
        "### Approved Rules Available",
        "",
        _frame_markdown(guru_review.approved_rules),
        "",
        "### Review Required Before Predictive Claim",
        "",
        _frame_markdown(top_priorities),
    ]


def _guru_episode_lines(guru_episode: GuruEpisodeDatasetResult | None) -> list[str]:
    if guru_episode is None:
        return ["Guru decision episode dataset was not run."]
    snapshot_fields = [
        "spot_price",
        "session_open",
        "open_side",
        "distance_from_open",
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
        "nearest_spot_equivalent_strike",
        "intraday_volume_near_level",
        "oi_change_near_level",
        "data_quality_status",
    ]
    approval_counts = (
        guru_episode.episodes.group_by("episode_review_status").len().sort("episode_review_status")
        if not guru_episode.episodes.is_empty()
        else guru_episode.episodes
    )
    episode_preview = (
        guru_episode.episodes.select([
            "episode_id",
            "transcript_id",
            "rule_tag",
            "thesis_type",
            "expected_direction",
            "episode_review_status",
            "spot_price",
            "expected_from_level",
            "expected_to_level",
            "invalidation_level",
        ]).head(20)
        if not guru_episode.episodes.is_empty()
        else guru_episode.episodes
    )
    outcome_preview = (
        guru_episode.outcomes.select([
            "episode_id",
            "rule_tag",
            "outcome_window",
            "target_hit",
            "invalidation_hit",
            "direction_correct",
            "max_favorable_excursion",
            "max_adverse_excursion",
            "outcome_label",
        ]).head(20)
        if not guru_episode.outcomes.is_empty()
        else guru_episode.outcomes
    )
    return [
        f"- Final Guru Logic Decision: `{guru_episode.final_decision}`",
        f"- Episode count: {guru_episode.episodes.height}",
        f"- Outcome rows: {guru_episode.outcomes.height}",
        f"- High-priority review sample count: {guru_episode.review_sample.height}",
        f"- Episode review decision template rows: {guru_episode.review_decisions_template.height}",
        f"- Approved-only episode validation can run: {guru_episode.approved_only_can_run}",
        f"- No-trade signal rows retained: {guru_episode.no_trade_rows_retained}",
        "",
        "### What Data Guru Could See",
        "",
        "- Snapshot fields created: " + ", ".join(f"`{field}`" for field in snapshot_fields),
        "- Snapshots are built from rows with `timestamp <= availability_timestamp`; outcomes use later rows only.",
        "",
        "### Guru Thesis vs Market Outcome",
        "",
        _frame_markdown(episode_preview),
        "",
        "### Target / Invalidation Accuracy",
        "",
        _frame_markdown(outcome_preview),
        "",
        "### Approved vs Preview Episodes",
        "",
        _frame_markdown(approval_counts),
        "",
        "### Episode-Level Rule Performance",
        "",
        _frame_markdown(guru_episode.performance),
        "",
        "### Final Guru Logic Decision",
        "",
        "- `GURU_EPISODE_VALIDATED_FILTER` remains blocked unless human-approved records, enough samples, "
        "walk-forward pass, placebo pass, clear target/invalidation logic, zero future transcript leakage, "
        "and retained no-trade rows are all present.",
        "- Review dashboard: `outputs/guru_episode_review_dashboard.html`",
        "- Review decisions template: `outputs/guru_episode_review_decisions_template.csv`",
        "- Review guide: `outputs/guru_episode_review_guide.md`",
    ]


def _reference_price(price: pl.DataFrame, options: pl.DataFrame) -> float:
    spot_values = [value for value in options.get_column("spot_price").to_list() if value is not None]
    if spot_values:
        return float(spot_values[-1])
    return float(price.get_column("close").head(1).item())


def _first_non_null(frame: pl.DataFrame, column: str) -> float | None:
    if column not in frame.columns:
        return None
    for value in frame.get_column(column).to_list():
        if value is not None:
            return float(value)
    return None


def _count_future_timestamp(frame: pl.DataFrame, *, known_col: str, event_col: str) -> int:
    if frame.is_empty() or known_col not in frame.columns or event_col not in frame.columns:
        return 0
    return frame.filter(
        pl.col(known_col).is_not_null() & (pl.col(known_col) > pl.col(event_col))
    ).height


def _kill_candidates(summary: pl.DataFrame) -> list[str]:
    if summary.is_empty():
        return ["No signal classes can be evaluated yet."]
    rows = summary.filter(pl.col("group_type") == "signal").to_dicts()
    candidates = []
    for row in rows:
        signal = row.get("bucket")
        trade_count = int(row.get("trade_count") or 0)
        expectancy = row.get("expectancy")
        if trade_count < 5:
            candidates.append(f"{signal}: quarantine, sample size below 5.")
        elif expectancy is not None and float(expectancy) <= 0:
            candidates.append(f"{signal}: kill or quarantine, non-positive net expectancy.")
    return candidates or ["No signal class met the automatic kill/quarantine rule."]


def _wall_score_bucket(value: Any) -> str:
    if value is None:
        return "unknown"
    value = float(value)
    if value >= 0.30:
        return "high"
    if value >= 0.15:
        return "medium"
    return "low"


def _dte_bucket(value: Any) -> str:
    if value is None:
        return "unknown"
    value = float(value)
    if value <= 3:
        return "0_3d"
    if value <= 10:
        return "4_10d"
    if value <= 30:
        return "11_30d"
    return "over_30d"


def _inventory_lines(inventory: pl.DataFrame) -> list[str]:
    if inventory.is_empty():
        return ["No local research data files found."]
    grouped = inventory.group_by(["category", "extension"]).len().sort(["category", "extension"])
    lines = ["| category | extension | count |", "|---|---:|---:|"]
    for row in grouped.to_dicts():
        lines.append(f"| {row['category']} | {row['extension']} | {row['len']} |")
    return lines


def _answer_questions(summary: pl.DataFrame) -> list[str]:
    if summary.is_empty():
        return [
            "- Does 1SD/2SD range logic work by itself? Not established; no completed "
            "control observations were available.",
            "- Does adding CME OI wall data improve it? Not established without paired "
            "control and wall-signal samples.",
            "- Does basis-adjusted OI wall mapping improve it? Not established here; "
            "compare against an unadjusted-wall ablation next.",
            "- Which signal works better: fade wall or break wall? Not established.",
            "- Which zones should be no-trade zones? Bad data, stale data, missing IV, "
            "missing basis, no nearby wall, and middle 1SD without wall evidence.",
            "- Which transcript-derived rules are supported by data? The formulas and "
            "classification gates are implemented; statistical support requires more data.",
            "- Which rules fail? No deterministic rule is marked failed until it has "
            "adequate sample coverage.",
            "- What should be tested next? Longer CME history, basis ablations, and "
            "session/news segmentation.",
        ]
    sd_only = _summary_signal(summary, "SD_ONLY_BASELINE")
    oi_only = _summary_signal(summary, "OI_WALL_ONLY_BASELINE")
    random = _summary_signal(summary, "RANDOM_BASELINE")
    bollinger = _summary_signal(summary, "BOLLINGER_BASELINE")
    fade = _weighted_signal_expectancy(summary, ["FADE_WALL_LONG", "FADE_WALL_SHORT"])
    break_wall = _weighted_signal_expectancy(summary, ["BREAK_WALL_LONG", "BREAK_WALL_SHORT"])
    return [
        "- Does 1SD/2SD range logic work by itself? In this run, `SD_ONLY_BASELINE` "
        f"expectancy is {_metric(sd_only, 'expectancy')} with profit factor "
        f"{_metric(sd_only, 'profit_factor')}; it does not stand alone.",
        "- Does adding CME OI wall data improve it? Not broadly. `OI_WALL_ONLY_BASELINE` "
        f"expectancy is {_metric(oi_only, 'expectancy')}, while random is "
        f"{_metric(random, 'expectancy')} and Bollinger is "
        f"{_metric(bollinger, 'expectancy')}. The positive wall results are limited "
        "to specific short-side fade/break classes and need more walk-forward evidence.",
        "- Does basis-adjusted OI wall mapping improve it? The pipeline maps strikes "
        "with basis; add an unadjusted ablation before making that claim.",
        "- Which signal works better: fade wall or break wall? Aggregate fade-wall "
        f"expectancy is {_format_float(fade)}; aggregate break-wall expectancy is "
        f"{_format_float(break_wall)}. Direction matters more than the family: "
        "`FADE_WALL_SHORT` and `BREAK_WALL_SHORT` survive in-sample, while the long "
        "classes do not.",
        "- Which zones should be no-trade zones? Bad quality, stale, missing IV, "
        "missing basis, no nearby wall, and middle 1SD without high-score walls.",
        "- Which transcript-derived guru rules are supported by data? Basis mapping, "
        "IV expected move, acceptance confirmation, no-trade gates, and wall scoring "
        "are implemented as testable rules. Only the short-side wall reactions show "
        "positive in-sample evidence in this small run.",
        "- Which rules fail? `SD_ONLY_BASELINE`, `OI_WALL_ONLY_BASELINE`, "
        "`FADE_WALL_LONG`, and `BREAK_WALL_LONG` should be killed or quarantined "
        "until they survive fresh walk-forward data.",
        "- What should be tested next? Add unadjusted-wall and no-basis ablations, "
        "news-disabled labels, and separate near-expiry pin tests.",
    ]


def _summary_signal(summary: pl.DataFrame, signal: str) -> dict[str, Any]:
    if summary.is_empty():
        return {}
    rows = summary.filter(
        (pl.col("group_type") == "signal") & (pl.col("bucket") == signal)
    ).to_dicts()
    return rows[0] if rows else {}


def _weighted_signal_expectancy(summary: pl.DataFrame, signals: list[str]) -> float | None:
    if summary.is_empty():
        return None
    rows = summary.filter(
        (pl.col("group_type") == "signal") & pl.col("bucket").is_in(signals)
    ).to_dicts()
    numerator = 0.0
    denominator = 0
    for row in rows:
        trade_count = int(row.get("trade_count") or 0)
        expectancy = row.get("expectancy")
        if trade_count > 0 and expectancy is not None:
            numerator += trade_count * float(expectancy)
            denominator += trade_count
    if denominator == 0:
        return None
    return numerator / denominator


def _metric(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    return _format_float(float(value)) if value is not None else "n/a"


def _format_float(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.4f}"


def _frame_markdown(frame: pl.DataFrame) -> str:
    if frame.is_empty():
        return "_No rows._"
    columns = frame.columns
    rows = ["| " + " | ".join(columns) + " |", "|" + "|".join(["---"] * len(columns)) + "|"]
    for raw in frame.head(20).to_dicts():
        rows.append("| " + " | ".join(str(raw.get(column, "")) for column in columns) + " |")
    return "\n".join(rows)


def _write_line_svg(path: Path, *, title: str, series: list[float]) -> None:
    width, height = 900, 260
    if not series:
        _write_empty_svg(path, title)
        return
    minimum, maximum = min(series), max(series)
    span = max(maximum - minimum, 1.0)
    points = []
    for index, value in enumerate(series):
        x = 40 + index * (width - 80) / max(len(series) - 1, 1)
        y = height - 40 - ((value - minimum) / span) * (height - 80)
        points.append(f"{x:.1f},{y:.1f}")
    path.write_text(
        _svg(title, f'<polyline fill="none" stroke="#2563eb" stroke-width="2" points="{" ".join(points)}" />'),
        encoding="utf-8",
    )


def _write_bar_svg(path: Path, *, title: str, labels: list[str], values: list[float]) -> None:
    width, height = 900, 300
    if not values:
        _write_empty_svg(path, title)
        return
    maximum = max(max(abs(value) for value in values), 1.0)
    bar_width = max(4, (width - 80) / max(len(values), 1))
    bars = []
    for index, value in enumerate(values):
        x = 40 + index * bar_width
        bar_height = abs(value) / maximum * (height - 90)
        y = height - 40 - bar_height
        bars.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width * 0.8:.1f}" '
            f'height="{bar_height:.1f}" fill="#0f766e"><title>{labels[index]}</title></rect>'
        )
    path.write_text(_svg(title, "\n".join(bars)), encoding="utf-8")


def _write_marker_svg(path: Path, *, title: str, count: int, labels: list[str]) -> None:
    body = [f'<text x="40" y="70" font-size="16">count: {count}</text>']
    for index, label in enumerate(labels[:20]):
        y = 105 + index * 18
        body.append(f'<circle cx="50" cy="{y}" r="4" fill="#dc2626" />')
        body.append(f'<text x="65" y="{y + 4}" font-size="12">{label}</text>')
    path.write_text(_svg(title, "\n".join(body)), encoding="utf-8")


def _write_empty_svg(path: Path, title: str) -> None:
    path.write_text(_svg(title, '<text x="40" y="80">No data available.</text>'), encoding="utf-8")


def _svg(title: str, body: str) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="300" '
        'viewBox="0 0 900 300">'
        f'<rect width="900" height="300" fill="#ffffff" />'
        f'<text x="40" y="30" font-size="18" font-family="Arial">{title}</text>'
        f"{body}</svg>"
    )


def _equity_curve(trades: pl.DataFrame) -> list[float]:
    running = 0.0
    curve = [0.0]
    for row in trades.to_dicts():
        running += float(row.get("pnl_points") or 0.0)
        curve.append(running)
    return curve


def _summary_labels(summary: pl.DataFrame, group_type: str) -> list[str]:
    if summary.is_empty():
        return []
    return [
        str(row["bucket"])
        for row in summary.filter(pl.col("group_type") == group_type).to_dicts()
    ]


def _summary_values(summary: pl.DataFrame, group_type: str) -> list[float]:
    if summary.is_empty():
        return []
    return [
        float(row.get("expectancy") or 0.0)
        for row in summary.filter(pl.col("group_type") == group_type).to_dicts()
    ]


def _confusion_labels(events: pl.DataFrame) -> list[str]:
    if events.is_empty():
        return []
    labels = []
    for signal in ["FADE_WALL_LONG", "FADE_WALL_SHORT", "BREAK_WALL_LONG", "BREAK_WALL_SHORT"]:
        count = events.filter(pl.col("signal") == signal).height
        labels.append(f"{signal}: {count}")
    return labels


def main() -> None:
    """CLI entry point."""

    parser = argparse.ArgumentParser(description="Run XAU Vol-OI research pipeline.")
    parser.add_argument("--price", type=Path, default=None)
    parser.add_argument("--options", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    args = parser.parse_args()
    paths = run_pipeline(price_path=args.price, options_path=args.options, output_dir=args.output_dir)
    for name, path in paths.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
