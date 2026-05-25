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
from research_xau_vol_oi.cme_history_normalizer import (
    CmeHistoryNormalizerResult,
    run_cme_history_normalizer,
)
from research_xau_vol_oi.cme_history_importer import (
    CmeHistoryImporterResult,
    run_cme_history_importer,
)
from research_xau_vol_oi.config import ResearchConfig
from research_xau_vol_oi.approved_session_remap_interpretation import (
    ApprovedSessionRemapInterpretationResult,
    approved_session_remap_report_lines,
    run_approved_session_remap_interpretation_layer,
)
from research_xau_vol_oi.current_data_usability_audit import (
    CurrentDataUsabilityAuditResult,
    current_data_usability_report_lines,
    run_current_data_usability_audit,
)
from research_xau_vol_oi.current_week_replay import (
    CurrentWeekReplayResult,
    current_week_replay_report_lines,
    run_current_week_replay_layer,
)
from research_xau_vol_oi.daily_forward_data_gate import (
    DailyForwardDataGateResult,
    daily_forward_data_gate_report_lines,
    run_daily_forward_data_gate,
)
from research_xau_vol_oi.yahoo_intraday_outcome_resolver import (
    YahooIntradayOutcomeResolverResult,
    run_yahoo_intraday_outcome_resolver,
    yahoo_intraday_outcome_report_lines,
)
from research_xau_vol_oi.forward_outcome_review import (
    ForwardOutcomeReviewResult,
    forward_outcome_review_report_lines,
    run_forward_outcome_review,
)
from research_xau_vol_oi.forward_event_evidence_aggregator import (
    ForwardEventEvidenceAggregatorResult,
    forward_event_evidence_report_lines,
    run_forward_event_evidence_aggregator,
)
from research_xau_vol_oi.forward_evidence_integrity_audit import (
    ForwardEvidenceIntegrityAuditResult,
    forward_evidence_integrity_report_lines,
    run_forward_evidence_integrity_audit,
)
from research_xau_vol_oi.data_recovery_audit import (
    DataRecoveryAuditResult,
    run_data_recovery_audit_layer,
)
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
from research_xau_vol_oi.guru_full_context_review import (
    GuruFullContextReviewResult,
    run_guru_full_context_review_layer,
)
from research_xau_vol_oi.guru_logic_knowledge_base import (
    GuruLogicKnowledgeBaseResult,
    run_guru_logic_knowledge_base_layer,
)
from research_xau_vol_oi.guru_transcript_alignment_debug import (
    GuruTranscriptAlignmentDebugResult,
    guru_transcript_alignment_report_lines,
    run_guru_transcript_alignment_debug_layer,
)
from research_xau_vol_oi.session_alignment_resolution import (
    SessionAlignmentResolutionResult,
    run_session_alignment_resolution_layer,
    session_alignment_resolution_report_lines,
)
from research_xau_vol_oi.transcript_identity_session_remap import (
    TranscriptIdentitySessionRemapResult,
    run_transcript_identity_session_remap_layer,
    transcript_identity_session_remap_report_lines,
)
from research_xau_vol_oi.transcript_timing_evidence import (
    TimingEvidenceResult,
    run_transcript_timing_evidence_layer,
    timing_evidence_report_lines,
)
from research_xau_vol_oi.youtube_metadata_recovery import (
    YouTubeMetadataRecoveryResult,
    run_youtube_metadata_recovery_layer,
    youtube_metadata_recovery_report_lines,
)
from research_xau_vol_oi.guru_rule_backtest_lab import (
    GuruRuleBacktestLabResult,
    guru_rule_backtest_lab_report_lines,
    run_guru_rule_backtest_lab,
)
from research_xau_vol_oi.gold_baseline_lab import (
    GoldBaselineLabResult,
    run_gold_baseline_lab,
)
from research_xau_vol_oi.guru_llm_review import (
    GuruLlmReviewResult,
    run_guru_llm_review_layer,
)
from research_xau_vol_oi.guru_monte_carlo_validation import (
    GuruMonteCarloValidationResult,
    run_guru_monte_carlo_validation_layer,
)
from research_xau_vol_oi.guru_review_queue import (
    GuruReviewQueueResult,
    run_guru_review_queue_layer,
)
from research_xau_vol_oi.llm_transcript_extractor import (
    LlmTranscriptExtractionResult,
    run_llm_transcript_extraction_layer,
)
from research_xau_vol_oi.market_map_proof_pack import (
    MarketMapProofPackResult,
    run_market_map_proof_pack,
)
from research_xau_vol_oi.pine_python_engine import run_pine_python_engine_lab
from research_xau_vol_oi.pine_strategy_overlay_lab import run_pine_strategy_overlay_lab
from research_xau_vol_oi.python_engine_expanded_backtest import (
    run_python_engine_expanded_backtest_lab,
)
from research_xau_vol_oi.python_single_timeframe_validation import (
    run_single_timeframe_validation_lab,
)
from research_xau_vol_oi.research_decision_gate import (
    ResearchDecisionGateResult,
    run_research_decision_gate,
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
    guru_llm_review = run_guru_llm_review_layer(
        episodes=guru_episode_dataset.review_sample,
        output_dir=output_root,
    )
    guru_full_context_review = run_guru_full_context_review_layer(
        episodes=guru_episode_dataset.review_sample,
        transcript_timeline=transcript_timeline.timeline,
        outcomes=guru_episode_dataset.outcomes,
        signal_events=signal_events,
        trades=trades,
        output_dir=output_root,
    )
    guru_monte_carlo = run_guru_monte_carlo_validation_layer(
        episodes=guru_episode_dataset.episodes,
        outcomes=guru_episode_dataset.outcomes,
        final_suggestions=guru_full_context_review.suggestions,
        signal_events=signal_events,
        output_dir=output_root,
        charts_dir=charts_dir,
        config=cfg,
    )
    gold_baseline_lab = run_gold_baseline_lab(
        feature_table=feature_table,
        signal_events=signal_events,
        transcript_conditioned_events=transcript_uplift.conditioned_events,
        guru_context_records=guru_full_context_review.suggestions,
        approved_rule_records=guru_review.approved_rules,
        output_dir=output_root,
        charts_dir=charts_dir,
        config=cfg,
    )
    cme_history_normalizer = run_cme_history_normalizer(
        output_dir=output_root,
        config=cfg,
    )
    cme_history_importer = run_cme_history_importer(
        output_dir=output_root,
    )
    market_map_proof_pack = run_market_map_proof_pack(
        feature_table=feature_table,
        walls=walls,
        signal_events=signal_events,
        output_dir=output_root,
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
    data_recovery = run_data_recovery_audit_layer(output_dir=output_root, config=cfg)
    audit_path = output_root / "leakage_audit_report.md"
    write_leakage_audit_report(
        audit_path,
        feature_table=feature_table,
        events=signal_events,
        summary=summary,
        walk_forward=walk_forward,
        cost_stress=cost_stress,
    )
    research_decision_gate = run_research_decision_gate(
        output_dir=output_root,
        charts_dir=charts_dir,
    )
    guru_logic_knowledge_base = run_guru_logic_knowledge_base_layer(
        output_dir=output_root,
    )
    current_data_usability = run_current_data_usability_audit(
        output_dir=output_root,
    )
    current_week_replay = run_current_week_replay_layer(
        output_dir=output_root,
    )
    guru_transcript_alignment_debug = run_guru_transcript_alignment_debug_layer(
        output_dir=output_root,
    )
    session_alignment_resolution = run_session_alignment_resolution_layer(
        output_dir=output_root,
    )
    transcript_identity_session_remap = run_transcript_identity_session_remap_layer(
        output_dir=output_root,
    )
    approved_session_remap_interpretation = run_approved_session_remap_interpretation_layer(
        output_dir=output_root,
    )
    transcript_timing_evidence = run_transcript_timing_evidence_layer(
        output_dir=output_root,
    )
    youtube_metadata_recovery = run_youtube_metadata_recovery_layer(
        output_dir=output_root,
    )
    guru_rule_backtest_lab = run_guru_rule_backtest_lab(
        output_dir=output_root,
    )
    daily_forward_data_gate = run_daily_forward_data_gate(
        output_dir=output_root,
    )
    yahoo_intraday_outcome = run_yahoo_intraday_outcome_resolver(
        output_dir=output_root,
    )
    forward_outcome_review = run_forward_outcome_review(
        output_dir=output_root,
    )
    forward_event_evidence = run_forward_event_evidence_aggregator(
        output_dir=output_root,
    )
    forward_evidence_integrity = run_forward_evidence_integrity_audit(
        output_dir=output_root,
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
        guru_llm_review=guru_llm_review,
        guru_full_context_review=guru_full_context_review,
        guru_monte_carlo=guru_monte_carlo,
        gold_baseline_lab=gold_baseline_lab,
        cme_history_normalizer=cme_history_normalizer,
        cme_history_importer=cme_history_importer,
        market_map_proof_pack=market_map_proof_pack,
        data_recovery=data_recovery,
        research_decision_gate=research_decision_gate,
        guru_logic_knowledge_base=guru_logic_knowledge_base,
        current_data_usability=current_data_usability,
        current_week_replay=current_week_replay,
        guru_transcript_alignment_debug=guru_transcript_alignment_debug,
        session_alignment_resolution=session_alignment_resolution,
        transcript_identity_session_remap=transcript_identity_session_remap,
        approved_session_remap_interpretation=approved_session_remap_interpretation,
        transcript_timing_evidence=transcript_timing_evidence,
        youtube_metadata_recovery=youtube_metadata_recovery,
        guru_rule_backtest_lab=guru_rule_backtest_lab,
        daily_forward_data_gate=daily_forward_data_gate,
        yahoo_intraday_outcome=yahoo_intraday_outcome,
        forward_outcome_review=forward_outcome_review,
        forward_event_evidence=forward_event_evidence,
        forward_evidence_integrity=forward_evidence_integrity,
        charts_dir=charts_dir,
    )
    run_pine_strategy_overlay_lab(output_dir=output_root)
    run_pine_python_engine_lab(output_dir=output_root)
    run_python_engine_expanded_backtest_lab(output_dir=output_root)
    run_single_timeframe_validation_lab(output_dir=output_root)
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
        "guru_llm_review_suggestions": output_root / "guru_llm_review_suggestions.csv",
        "guru_llm_adversarial_review": output_root / "guru_llm_adversarial_review.csv",
        "guru_llm_review_final_suggestions": output_root / "guru_llm_review_final_suggestions.csv",
        "guru_llm_review_audit": output_root / "guru_llm_review_audit.md",
        "guru_full_context_review_pack": output_root / "guru_full_context_review_pack.csv",
        "guru_full_context_review_suggestions": output_root / "guru_full_context_review_suggestions.csv",
        "guru_full_context_review_decisions_template": output_root / "guru_full_context_review_decisions_template.csv",
        "guru_logic_classification_summary": output_root / "guru_logic_classification_summary.csv",
        "guru_filter_value_report": output_root / "guru_filter_value_report.csv",
        "guru_market_map_validation": output_root / "guru_market_map_validation.csv",
        "guru_full_context_review_report": output_root / "guru_full_context_review_report.md",
        "guru_monte_carlo_validation": output_root / "guru_monte_carlo_validation.csv",
        "guru_monte_carlo_report": output_root / "guru_monte_carlo_report.md",
        "gold_baseline_metrics": output_root / "gold_baseline_metrics.csv",
        "gold_ablation_report": output_root / "gold_ablation_report.md",
        "gold_baseline_vs_uplift_chart": charts_dir / "gold_baseline_vs_uplift.svg",
        "cme_daily_strike_expiry_panel": output_root / "cme_daily_strike_expiry_panel.parquet",
        "cme_session_regime_panel": output_root / "cme_session_regime_panel.parquet",
        "cme_history_coverage_report": output_root / "cme_history_coverage_report.csv",
        "cme_history_coverage_markdown": output_root / "cme_history_coverage_report.md",
        "cme_history_missing_field_report": output_root / "cme_history_missing_field_report.csv",
        "cme_history_duplicate_conflict_report": output_root / "cme_history_duplicate_conflict_report.csv",
        "cme_history_source_inventory": output_root / "cme_history_source_inventory.csv",
        "cme_import_file_detection": output_root / "cme_import_file_detection.csv",
        "cme_validation_grade_days": output_root / "cme_validation_grade_days.csv",
        "cme_validation_grade_report": output_root / "cme_validation_grade_report.md",
        "cme_validation_grade_uplift": output_root / "cme_validation_grade_uplift.csv",
        "cme_validation_grade_uplift_report": output_root / "cme_validation_grade_uplift_report.md",
        "cme_data_requirements_checklist": output_root / "cme_data_requirements_checklist.csv",
        "cme_data_requirements_checklist_report": output_root / "cme_data_requirements_checklist.md",
        "basis_adjustment_precision_report": output_root / "basis_adjustment_precision_report.csv",
        "basis_adjustment_precision_markdown": output_root / "basis_adjustment_precision_report.md",
        "xau_vol_oi_validation_dataset": output_root / "xau_vol_oi_validation_dataset.parquet",
        "orchestrator_gpt_context": output_root / "orchestrator_gpt_context.md",
        "market_map_precision_report": output_root / "market_map_precision_report.csv",
        "filter_avoided_pnl_report": output_root / "filter_avoided_pnl_report.csv",
        "expiry_pin_test_report": output_root / "expiry_pin_test_report.csv",
        "proof_pack": output_root / "proof_pack.md",
        "research_decision_gate": output_root / "research_decision_gate.csv",
        "research_readiness_scorecard": output_root / "research_readiness_scorecard.csv",
        "money_readiness_report": output_root / "money_readiness_report.md",
        "next_research_tasks_ranked": output_root / "next_research_tasks_ranked.csv",
        "guru_logic_knowledge_base": output_root / "guru_logic_knowledge_base.csv",
        "guru_logic_knowledge_base_report": output_root / "guru_logic_knowledge_base.md",
        "guru_logic_data_dependency_matrix": output_root / "guru_logic_data_dependency_matrix.csv",
        "guru_logic_data_dependency_matrix_report": output_root
        / "guru_logic_data_dependency_matrix.md",
        "guru_logic_priority_rank": output_root / "guru_logic_priority_rank.csv",
        "cme_collection_plan_for_guru_logic": output_root
        / "cme_collection_plan_for_guru_logic.csv",
        "cme_collection_plan_for_guru_logic_report": output_root
        / "cme_collection_plan_for_guru_logic.md",
        "guru_logic_validation_path": output_root / "guru_logic_validation_path.csv",
        "guru_logic_validation_path_report": output_root / "guru_logic_validation_path.md",
        "current_cme_date_usability": output_root / "current_cme_date_usability.csv",
        "iv_field_mapping_audit": output_root / "iv_field_mapping_audit.csv",
        "spot_basis_join_audit": output_root / "spot_basis_join_audit.csv",
        "one_week_cme_pilot_summary": output_root / "one_week_cme_pilot_summary.csv",
        "ohlc_guru_price_only_pilot": output_root / "ohlc_guru_price_only_pilot.csv",
        "cme_fetch_tool_gap_audit": output_root / "cme_fetch_tool_gap_audit.csv",
        "spot_basis_backfill_audit": output_root / "spot_basis_backfill_audit.csv",
        "spot_basis_backfill_report": output_root / "spot_basis_backfill_report.md",
        "xau_spot_backfilled": output_root / "xau_spot_backfilled.parquet",
        "xau_basis_backfilled": output_root / "xau_basis_backfilled.parquet",
        "spot_basis_join_preview": output_root / "spot_basis_join_preview.csv",
        "current_week_cme_guru_replay": output_root / "current_week_cme_guru_replay.csv",
        "current_week_cme_guru_replay_report": output_root / "current_week_cme_guru_replay.md",
        "current_week_guru_filter_replay": output_root / "current_week_guru_filter_replay.csv",
        "current_week_guru_filter_replay_report": output_root / "current_week_guru_filter_replay.md",
        "cme_validation_grade_days_after_backfill": output_root
        / "cme_validation_grade_days_after_backfill.csv",
        "cme_validation_upgrade_report": output_root / "cme_validation_upgrade_report.md",
        "fetch_tool_next_changes": output_root / "fetch_tool_next_changes.md",
        "current_week_wall_replay_chart": charts_dir / "current_week_wall_replay.svg",
        "current_week_basis_replay_chart": charts_dir / "current_week_basis_replay.svg",
        "current_week_guru_filter_overlay_chart": charts_dir
        / "current_week_guru_filter_overlay.svg",
        "guru_transcript_alignment_debug": output_root / "guru_transcript_alignment_debug.csv",
        "guru_transcript_alignment_debug_report": output_root / "guru_transcript_alignment_debug.md",
        "guru_text_interpretation_audit": output_root / "guru_text_interpretation_audit.csv",
        "guru_text_interpretation_audit_report": output_root / "guru_text_interpretation_audit.md",
        "guru_playbook_overlay_for_current_week": output_root
        / "guru_playbook_overlay_for_current_week.csv",
        "guru_playbook_overlay_for_current_week_report": output_root
        / "guru_playbook_overlay_for_current_week.md",
        "no_guru_context_explanation": output_root / "no_guru_context_explanation.md",
        "current_week_cme_guru_playbook_replay": output_root
        / "current_week_cme_guru_playbook_replay.csv",
        "current_week_cme_guru_playbook_replay_report": output_root
        / "current_week_cme_guru_playbook_replay.md",
        "missing_xau_spot_basis_fetch_plan": output_root / "missing_xau_spot_basis_fetch_plan.csv",
        "missing_xau_spot_basis_fetch_plan_report": output_root
        / "missing_xau_spot_basis_fetch_plan.md",
        "session_calendar_audit": output_root / "session_calendar_audit.csv",
        "session_calendar_audit_report": output_root / "session_calendar_audit.md",
        "same_date_transcript_resolution": output_root / "same_date_transcript_resolution.csv",
        "same_date_transcript_resolution_report": output_root
        / "same_date_transcript_resolution.md",
        "transcript_manifest_dedup_audit": output_root / "transcript_manifest_dedup_audit.csv",
        "transcript_manifest_dedup_audit_report": output_root
        / "transcript_manifest_dedup_audit.md",
        "same_day_guru_signal_readiness": output_root / "same_day_guru_signal_readiness.csv",
        "same_day_guru_signal_readiness_report": output_root
        / "same_day_guru_signal_readiness.md",
        "refined_missing_data_action_plan": output_root / "refined_missing_data_action_plan.csv",
        "refined_missing_data_action_plan_report": output_root
        / "refined_missing_data_action_plan.md",
        "current_week_replay_resolved": output_root / "current_week_replay_resolved.csv",
        "current_week_replay_resolved_report": output_root / "current_week_replay_resolved.md",
        "transcript_identity_audit": output_root / "transcript_identity_audit.csv",
        "transcript_identity_audit_report": output_root / "transcript_identity_audit.md",
        "clean_transcript_set": output_root / "clean_transcript_set.csv",
        "clean_transcript_set_report": output_root / "clean_transcript_set.md",
        "transcript_session_availability": output_root / "transcript_session_availability.csv",
        "transcript_session_availability_report": output_root / "transcript_session_availability.md",
        "session_remap_suggestions": output_root / "session_remap_suggestions.csv",
        "session_remap_decisions_template": output_root / "session_remap_decisions_template.csv",
        "session_remap_policy": output_root / "session_remap_policy.md",
        "current_week_replay_after_approved_remap": output_root
        / "current_week_replay_after_approved_remap.csv",
        "current_week_replay_after_approved_remap_report": output_root
        / "current_week_replay_after_approved_remap.md",
        "same_day_guru_reinterpretation_after_identity": output_root
        / "same_day_guru_reinterpretation_after_identity.csv",
        "same_day_guru_reinterpretation_after_identity_report": output_root
        / "same_day_guru_reinterpretation_after_identity.md",
        "session_remap_decisions_applied": output_root / "session_remap_decisions_applied.csv",
        "current_week_replay_after_market_session_remap": output_root
        / "current_week_replay_after_market_session_remap.csv",
        "current_week_replay_after_market_session_remap_report": output_root
        / "current_week_replay_after_market_session_remap.md",
        "same_day_transcript_interpretation_debug": output_root
        / "same_day_transcript_interpretation_debug.csv",
        "same_day_transcript_interpretation_debug_report": output_root
        / "same_day_transcript_interpretation_debug.md",
        "same_day_playbook_matches": output_root / "same_day_playbook_matches.csv",
        "same_day_playbook_matches_report": output_root / "same_day_playbook_matches.md",
        "current_week_same_day_guru_overlay": output_root
        / "current_week_same_day_guru_overlay.csv",
        "current_week_same_day_guru_overlay_report": output_root
        / "current_week_same_day_guru_overlay.md",
        "transcript_timing_metadata_audit": output_root / "transcript_timing_metadata_audit.csv",
        "transcript_timing_metadata_audit_report": output_root
        / "transcript_timing_metadata_audit.md",
        "transcript_availability_classification": output_root
        / "transcript_availability_classification.csv",
        "transcript_availability_classification_report": output_root
        / "transcript_availability_classification.md",
        "same_day_filter_evidence": output_root / "same_day_filter_evidence.csv",
        "same_day_filter_evidence_report": output_root / "same_day_filter_evidence.md",
        "same_day_market_map_evidence": output_root / "same_day_market_map_evidence.csv",
        "same_day_market_map_evidence_report": output_root
        / "same_day_market_map_evidence.md",
        "current_week_evidence_report": output_root / "current_week_evidence_report.md",
        "current_week_evidence_scorecard": output_root / "current_week_evidence_scorecard.csv",
        "transcript_metadata_fetch_plan": output_root / "transcript_metadata_fetch_plan.csv",
        "transcript_metadata_fetch_plan_report": output_root
        / "transcript_metadata_fetch_plan.md",
        "youtube_metadata_local_discovery": output_root
        / "youtube_metadata_local_discovery.csv",
        "youtube_metadata_local_discovery_report": output_root
        / "youtube_metadata_local_discovery.md",
        "youtube_metadata_fetch_requests": output_root / "youtube_metadata_fetch_requests.csv",
        "youtube_metadata_fetch_plan": output_root / "youtube_metadata_fetch_plan.md",
        "youtube_metadata_fetch_commands_sh": output_root / "youtube_metadata_fetch_commands.sh",
        "youtube_metadata_fetch_commands_ps1": output_root / "youtube_metadata_fetch_commands.ps1",
        "youtube_metadata_manual_entry_template": output_root
        / "youtube_metadata_manual_entry_template.csv",
        "transcript_timezone_audit": output_root / "transcript_timezone_audit.csv",
        "transcript_timezone_audit_report": output_root / "transcript_timezone_audit.md",
        "transcript_availability_classification_after_metadata": output_root
        / "transcript_availability_classification_after_metadata.csv",
        "same_day_filter_evidence_after_metadata": output_root
        / "same_day_filter_evidence_after_metadata.csv",
        "same_day_market_map_evidence_after_metadata": output_root
        / "same_day_market_map_evidence_after_metadata.csv",
        "current_week_evidence_report_after_metadata": output_root
        / "current_week_evidence_report_after_metadata.md",
        "guru_rule_library": output_root / "guru_rule_library.csv",
        "guru_rule_library_report": output_root / "guru_rule_library.md",
        "guru_rule_definitions": output_root / "guru_rule_definitions.yaml",
        "guru_rule_backtest_events": output_root / "guru_rule_backtest_events.csv",
        "guru_rule_backtest_summary": output_root / "guru_rule_backtest_summary.csv",
        "guru_rule_backtest_by_period": output_root / "guru_rule_backtest_by_period.csv",
        "guru_rule_backtest_report": output_root / "guru_rule_backtest_report.md",
        "guru_rule_formation_test_results": output_root
        / "guru_rule_formation_test_results.csv",
        "guru_rule_ablation": output_root / "guru_rule_ablation.csv",
        "guru_rule_ablation_report": output_root / "guru_rule_ablation_report.md",
        "range_period_rule_backtest_report": output_root
        / "range_period_rule_backtest_report.md",
        "range_period_rule_scorecard": output_root / "range_period_rule_scorecard.csv",
        "daily_forward_data_gate": output_root / "daily_forward_data_gate.csv",
        "daily_forward_data_gate_report": output_root / "daily_forward_data_gate.md",
        "outcome_coverage_check": output_root / "outcome_coverage_check.csv",
        "outcome_coverage_check_report": output_root / "outcome_coverage_check.md",
        "forward_data_provider_audit": output_root / "forward_data_provider_audit.csv",
        "forward_data_provider_audit_report": output_root
        / "forward_data_provider_audit.md",
        "daily_forward_run_decision": output_root / "daily_forward_run_decision.csv",
        "daily_forward_run_decision_report": output_root / "daily_forward_run_decision.md",
        "yahoo_intraday_fetch_plan": output_root / "yahoo_intraday_fetch_plan.csv",
        "yahoo_intraday_fetch_plan_report": output_root / "yahoo_intraday_fetch_plan.md",
        "intraday_resample_coverage": output_root / "intraday_resample_coverage.csv",
        "intraday_resample_coverage_report": output_root / "intraday_resample_coverage.md",
        "partial_outcome_resolution": output_root / "partial_outcome_resolution.csv",
        "partial_outcome_resolution_report": output_root / "partial_outcome_resolution.md",
        "forward_evidence_outcomes_preview": output_root
        / "forward_evidence_outcomes_preview.csv",
        "forward_journal_status_report": output_root / "forward_journal_status_report.md",
        "forward_journal_scorecard": output_root / "forward_journal_scorecard.csv",
        "useful_evidence_so_far": output_root / "useful_evidence_so_far.csv",
        "useful_evidence_so_far_report": output_root / "useful_evidence_so_far.md",
        "forward_outcome_preview_audit": output_root
        / "forward_outcome_preview_audit.csv",
        "forward_outcome_preview_audit_report": output_root
        / "forward_outcome_preview_audit.md",
        "forward_evidence_outcomes": output_root / "forward_evidence_outcomes.csv",
        "forward_evidence_outcomes_promoted": output_root
        / "forward_evidence_outcomes_promoted.csv",
        "forward_outcome_promotion_report": output_root
        / "forward_outcome_promotion_report.md",
        "forward_rule_evidence_summary": output_root
        / "forward_rule_evidence_summary.csv",
        "forward_rule_evidence_summary_report": output_root
        / "forward_rule_evidence_summary.md",
        "forward_filter_evidence": output_root / "forward_filter_evidence.csv",
        "forward_filter_evidence_report": output_root / "forward_filter_evidence.md",
        "forward_market_map_evidence": output_root / "forward_market_map_evidence.csv",
        "forward_market_map_evidence_report": output_root
        / "forward_market_map_evidence.md",
        "forward_pending_outcome_summary": output_root
        / "forward_pending_outcome_summary.csv",
        "forward_pending_outcome_summary_report": output_root
        / "forward_pending_outcome_summary.md",
        "forward_evidence_scorecard": output_root / "forward_evidence_scorecard.csv",
        "forward_evidence_scorecard_report": output_root
        / "forward_evidence_scorecard.md",
        "forward_event_level_outcomes": output_root
        / "forward_event_level_outcomes.csv",
        "forward_event_level_outcomes_report": output_root
        / "forward_event_level_outcomes.md",
        "forward_rule_event_evidence": output_root / "forward_rule_event_evidence.csv",
        "forward_rule_event_evidence_report": output_root
        / "forward_rule_event_evidence.md",
        "forward_rule_governance": output_root / "forward_rule_governance.csv",
        "forward_rule_governance_report": output_root / "forward_rule_governance.md",
        "next_rule_focus_list": output_root / "next_rule_focus_list.csv",
        "next_rule_focus_list_report": output_root / "next_rule_focus_list.md",
        "forward_event_scorecard": output_root / "forward_event_scorecard.csv",
        "forward_event_scorecard_report": output_root / "forward_event_scorecard.md",
        "forward_evidence_count_reconciliation": output_root
        / "forward_evidence_count_reconciliation.csv",
        "forward_evidence_count_reconciliation_report": output_root
        / "forward_evidence_count_reconciliation.md",
        "forward_event_duplication_audit": output_root / "forward_event_duplication_audit.csv",
        "forward_event_duplication_audit_report": output_root
        / "forward_event_duplication_audit.md",
        "forward_sample_size_by_definition": output_root
        / "forward_sample_size_by_definition.csv",
        "forward_sample_size_by_definition_report": output_root
        / "forward_sample_size_by_definition.md",
        "speckit_prereq_warning": output_root / "speckit_prereq_warning.md",
        "rule_backtest_expectancy_chart": charts_dir / "rule_backtest_expectancy.svg",
        "rule_filter_value_chart": charts_dir / "rule_filter_value.svg",
        "rule_market_map_hit_rate_chart": charts_dir / "rule_market_map_hit_rate.svg",
        "rule_mode_coverage_chart": charts_dir / "rule_mode_coverage.svg",
        "research_gate_status_chart": charts_dir / "research_gate_status.svg",
        "transcript_corpus_manifest": output_root / "transcript_corpus_manifest.csv",
        "transcript_corpus_manifest_report": output_root / "transcript_corpus_manifest.md",
        "market_data_coverage_manifest": output_root / "market_data_coverage_manifest.csv",
        "market_data_coverage_report": output_root / "market_data_coverage_report.md",
        "transcript_market_coverage_alignment": output_root
        / "transcript_market_coverage_alignment.csv",
        "transcript_market_coverage_alignment_report": output_root
        / "transcript_market_coverage_alignment.md",
        "codex_session_search_report": output_root / "codex_session_search_report.md",
        "source_recovery_action_plan": output_root / "source_recovery_action_plan.md",
        "privacy_path_audit_report": output_root / "privacy_path_audit_report.md",
        "pine_baseline_summary": output_root / "pine_baseline_summary.csv",
        "pine_overlay_backtest_summary": output_root / "pine_overlay_backtest_summary.csv",
        "pine_overlay_formation_test": output_root / "pine_overlay_formation_test.csv",
        "pine_fast_start_decision": output_root / "pine_fast_start_decision.csv",
        "yahoo_ohlc_inventory": output_root / "yahoo_ohlc_inventory.csv",
        "python_indicator_snapshot": output_root / "python_indicator_snapshot.csv",
        "python_pine_like_signals": output_root / "python_pine_like_signals.csv",
        "python_pine_like_backtest_summary": output_root
        / "python_pine_like_backtest_summary.csv",
        "python_cme_guru_overlay_summary": output_root / "python_cme_guru_overlay_summary.csv",
        "python_vs_tradingview_parity": output_root / "python_vs_tradingview_parity.csv",
        "python_fast_use_decision": output_root / "python_fast_use_decision.csv",
        "python_engine_data_expansion_plan": output_root / "python_engine_data_expansion_plan.csv",
        "python_expanded_backtest_summary": output_root / "python_expanded_backtest_summary.csv",
        "python_expanded_overlay_summary": output_root / "python_expanded_overlay_summary.csv",
        "python_pine_parity_gap_report": output_root / "python_pine_parity_gap_report.csv",
        "python_indicator_diagnostics": output_root / "python_indicator_diagnostics.csv",
        "python_grid_sensitivity_preview": output_root / "python_grid_sensitivity_preview.csv",
        "python_engine_fast_use_decision": output_root / "python_engine_fast_use_decision.csv",
        "python_single_timeframe_results": output_root / "python_single_timeframe_results.csv",
        "python_walk_forward_by_timeframe": output_root / "python_walk_forward_by_timeframe.csv",
        "python_4h_candidate_deep_dive": output_root / "python_4h_candidate_deep_dive.csv",
        "python_fee_drag_by_timeframe": output_root / "python_fee_drag_by_timeframe.csv",
        "python_timeframe_decision": output_root / "python_timeframe_decision.csv",
        "python_4h_candidate_chart": charts_dir / "python_4h_candidate_chart.html",
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
    guru_llm_review: GuruLlmReviewResult | None = None,
    guru_full_context_review: GuruFullContextReviewResult | None = None,
    guru_monte_carlo: GuruMonteCarloValidationResult | None = None,
    gold_baseline_lab: GoldBaselineLabResult | None = None,
    cme_history_normalizer: CmeHistoryNormalizerResult | None = None,
    cme_history_importer: CmeHistoryImporterResult | None = None,
    market_map_proof_pack: MarketMapProofPackResult | None = None,
    data_recovery: DataRecoveryAuditResult | None = None,
    research_decision_gate: ResearchDecisionGateResult | None = None,
    guru_logic_knowledge_base: GuruLogicKnowledgeBaseResult | None = None,
    current_data_usability: CurrentDataUsabilityAuditResult | None = None,
    current_week_replay: CurrentWeekReplayResult | None = None,
    guru_transcript_alignment_debug: GuruTranscriptAlignmentDebugResult | None = None,
    session_alignment_resolution: SessionAlignmentResolutionResult | None = None,
    transcript_identity_session_remap: TranscriptIdentitySessionRemapResult | None = None,
    approved_session_remap_interpretation: ApprovedSessionRemapInterpretationResult | None = None,
    transcript_timing_evidence: TimingEvidenceResult | None = None,
    youtube_metadata_recovery: YouTubeMetadataRecoveryResult | None = None,
    guru_rule_backtest_lab: GuruRuleBacktestLabResult | None = None,
    daily_forward_data_gate: DailyForwardDataGateResult | None = None,
    yahoo_intraday_outcome: YahooIntradayOutcomeResolverResult | None = None,
    forward_outcome_review: ForwardOutcomeReviewResult | None = None,
    forward_event_evidence: ForwardEventEvidenceAggregatorResult | None = None,
    forward_evidence_integrity: ForwardEvidenceIntegrityAuditResult | None = None,
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
        "## Data Recovery and Coverage Audit",
        "",
        *_data_recovery_lines(data_recovery),
        "",
        "## Validation-Grade CME History Normalizer",
        "",
        *_cme_history_normalizer_lines(cme_history_normalizer),
        "",
        "## CME Historical Data Import",
        "",
        *_cme_history_importer_lines(cme_history_importer),
        "",
        *current_data_usability_report_lines(current_data_usability),
        "",
        *current_week_replay_report_lines(current_week_replay),
        "",
        *guru_transcript_alignment_report_lines(guru_transcript_alignment_debug),
        "",
        *session_alignment_resolution_report_lines(session_alignment_resolution),
        "",
        *transcript_identity_session_remap_report_lines(transcript_identity_session_remap),
        "",
        *approved_session_remap_report_lines(approved_session_remap_interpretation),
        "",
        *timing_evidence_report_lines(transcript_timing_evidence),
        "",
        *youtube_metadata_recovery_report_lines(youtube_metadata_recovery),
        "",
        *guru_rule_backtest_lab_report_lines(guru_rule_backtest_lab),
        "",
        *daily_forward_data_gate_report_lines(daily_forward_data_gate),
        "",
        *yahoo_intraday_outcome_report_lines(yahoo_intraday_outcome),
        "",
        *forward_outcome_review_report_lines(forward_outcome_review),
        "",
        *forward_event_evidence_report_lines(forward_event_evidence),
        "",
        *forward_evidence_integrity_report_lines(forward_evidence_integrity),
        "",
        "## Market-Map And No-Trade Proof Pack",
        "",
        *_market_map_proof_pack_lines(market_map_proof_pack),
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
        "## Blind Guru Logic Review",
        "",
        *_guru_llm_review_lines(guru_llm_review),
        "",
        "## Full-Context Guru Logic Review",
        "",
        *_guru_full_context_review_lines(guru_full_context_review),
        "",
        "## Guru Logic Knowledge Base",
        "",
        *_guru_logic_knowledge_base_lines(guru_logic_knowledge_base),
        "",
        "## What Can Be Extracted Now",
        "",
        *_guru_logic_extractable_now_lines(guru_logic_knowledge_base),
        "",
        "## What Cannot Be Proven Yet",
        "",
        *_guru_logic_not_proven_lines(guru_logic_knowledge_base),
        "",
        "## CME Data Dependency Matrix",
        "",
        *_guru_logic_dependency_matrix_lines(guru_logic_knowledge_base),
        "",
        "## Guru Logic Priority Ranking",
        "",
        *_guru_logic_priority_lines(guru_logic_knowledge_base),
        "",
        "## CME Collection Plan",
        "",
        *_guru_logic_collection_plan_lines(guru_logic_knowledge_base),
        "",
        "## Validation Path by Logic Type",
        "",
        *_guru_logic_validation_path_lines(guru_logic_knowledge_base),
        "",
        "## Guru Logic Recommendation",
        "",
        *_guru_logic_final_recommendation_lines(guru_logic_knowledge_base),
        "",
        "## Monte Carlo Validation",
        "",
        *_guru_monte_carlo_lines(guru_monte_carlo),
        "",
        "## Gold Baseline And Uplift Lab",
        "",
        *_gold_baseline_lab_lines(gold_baseline_lab),
        "",
        "## Research Decision Gate",
        "",
        *_research_decision_gate_lines(research_decision_gate),
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


def _data_recovery_lines(data_recovery: DataRecoveryAuditResult | None) -> list[str]:
    if data_recovery is None:
        return ["Data recovery audit was not run."]
    manifest = data_recovery.transcript_manifest
    alignment = data_recovery.alignment
    market = data_recovery.market_coverage
    source_counts = (
        manifest.group_by("source_type").len().sort("source_type")
        if not manifest.is_empty()
        else manifest
    )
    extracted_full_txt = (
        manifest.filter(
            (pl.col("source_type") == "FULL_CORPUS")
            & ~pl.col("notes").str.contains("zip")
            & pl.col("file_name").str.to_lowercase().str.ends_with(".txt")
        ).height
        if not manifest.is_empty()
        else 0
    )
    full_extracted = (
        manifest.filter(
            (pl.col("source_type") == "FULL_CORPUS")
            & ~pl.col("notes").str.contains("zip")
            & pl.col("file_name").str.to_lowercase().str.ends_with(".txt")
        )
        if not manifest.is_empty()
        else manifest
    )
    full_start = full_extracted.get_column("detected_date").min() if not full_extracted.is_empty() else None
    full_end = full_extracted.get_column("detected_date").max() if not full_extracted.is_empty() else None
    source_zip_counts = (
        manifest.with_columns(
            pl.col("notes").str.contains("zip").alias("is_zip_entry")
        )
        .group_by(["source_type", "is_zip_entry"])
        .len()
        .sort(["source_type", "is_zip_entry"])
        if not manifest.is_empty()
        else manifest
    )
    validation_dates = (
        alignment.filter(pl.col("can_run_full_vol_oi_validation"))
        .select(["transcript_date", "transcript_count"])
        .head(20)
        if not alignment.is_empty()
        else alignment
    )
    logic_only = (
        alignment.filter(~pl.col("can_run_full_vol_oi_validation")).height
        if not alignment.is_empty()
        else 0
    )
    return [
        "### Transcript Corpus Status",
        "",
        f"- Large external transcript corpus found: {data_recovery.full_corpus_found}",
        f"- Full corpus path: `{data_recovery.full_corpus_path or 'not found'}`",
        f"- Full corpus archive: `{data_recovery.full_corpus_zip_path or 'not found'}`",
        f"- Extracted full-corpus `.txt` files found: {extracted_full_txt}",
        f"- Extracted full-corpus date range: {full_start or 'n/a'} to {full_end or 'n/a'}",
        f"- Likely session log: `{data_recovery.likely_session_path or 'not found'}`",
        "- Manifest row counts include extracted `.txt` files plus zip entries; "
        "the extracted full-corpus text-file count is the clean corpus count.",
        "- Default mode redacts source paths, session IDs, and private source names.",
        "",
        _frame_markdown(source_counts),
        "",
        _frame_markdown(source_zip_counts),
        "",
        "### CME/Yahoo Data Coverage",
        "",
        f"- Market data range detected: {data_recovery.market_date_start or 'n/a'} "
        f"to {data_recovery.market_date_end or 'n/a'}",
        f"- Market coverage files: {market.height}",
        f"- Full CME validation transcript dates: {data_recovery.full_validation_dates}",
        f"- Logic-only transcript dates: {logic_only}",
        "",
        "### Full Validation Dates",
        "",
        _frame_markdown(validation_dates),
        "",
        "### Logic-Only Transcript Dates",
        "",
        "- Transcript dates without matched CME OI, IV, and futures/basis are retained "
        "for logic extraction only. They should not be used to claim Vol-OI validation.",
        "",
        "### Recommended Next Action",
        "",
        "- Do not refetch transcripts when the full corpus path and zip are present.",
        "- Fetch or import more CME/QuikStrike history before expanding validation claims.",
        "- Treat the one-week CME/Yahoo window as pilot alignment coverage.",
        "",
        "- Recovery outputs: `outputs/transcript_corpus_manifest.csv`, "
        "`outputs/market_data_coverage_manifest.csv`, "
        "`outputs/transcript_market_coverage_alignment.csv`, "
        "`outputs/codex_session_search_report.md`, "
        "`outputs/source_recovery_action_plan.md`, "
        "`outputs/privacy_path_audit_report.md`.",
    ]


def _cme_history_normalizer_lines(cme_history: CmeHistoryNormalizerResult | None) -> list[str]:
    if cme_history is None:
        return ["CME history normalizer was not run."]
    coverage = cme_history.coverage_report
    missing_counts = (
        cme_history.missing_field_report.group_by("missing_field").len().sort("missing_field")
        if not cme_history.missing_field_report.is_empty()
        else cme_history.missing_field_report
    )
    coverage_view = (
        coverage.select(
            [
                column
                for column in [
                    "session_date",
                    "complete_validation_day",
                    "strike_expiry_rows",
                    "expiry_count",
                    "strike_count",
                    "missing_fields",
                    "reason_if_not_complete",
                ]
                if column in coverage.columns
            ]
        )
        if not coverage.is_empty()
        else coverage
    )
    return [
        "- Canonical daily strike-expiry panel: `outputs/cme_daily_strike_expiry_panel.parquet`",
        "- Canonical session-level regime panel: `outputs/cme_session_regime_panel.parquet`",
        "- Coverage report: `outputs/cme_history_coverage_report.csv` and "
        "`outputs/cme_history_coverage_report.md`",
        "- Missing-field report: `outputs/cme_history_missing_field_report.csv`",
        "- Duplicate/conflict report: `outputs/cme_history_duplicate_conflict_report.csv`",
        f"- First validation-grade date: `{cme_history.first_validation_grade_date or 'n/a'}`",
        f"- Last validation-grade date: `{cme_history.last_validation_grade_date or 'n/a'}`",
        f"- Complete validation-grade days: {cme_history.complete_validation_days}",
        f"- Daily strike-expiry rows: {cme_history.daily_panel.height}",
        f"- Session rows: {cme_history.session_panel.height}",
        f"- Source files inspected: {cme_history.source_inventory.height}",
        "",
        "### Fields Still Missing For Full Proof",
        "",
        *[f"- `{field}`" for field in cme_history.missing_fields_for_full_proof],
        "",
        "### Coverage By Session",
        "",
        _frame_markdown(coverage_view),
        "",
        "### Missing Field Counts",
        "",
        _frame_markdown(missing_counts),
    ]


def _cme_history_importer_lines(importer: CmeHistoryImporterResult | None) -> list[str]:
    if importer is None:
        return ["CME history importer was not run."]
    detection_counts = (
        importer.file_detection.group_by("detected_type").len().sort("detected_type")
        if not importer.file_detection.is_empty()
        else importer.file_detection
    )
    grade_counts = (
        importer.validation_grade_days.group_by("validation_grade").len().sort("validation_grade")
        if not importer.validation_grade_days.is_empty()
        else importer.validation_grade_days
    )
    complete_days = (
        importer.validation_grade_days.filter(pl.col("complete_validation_grade")).height
        if not importer.validation_grade_days.is_empty()
        else 0
    )
    missing_critical = (
        importer.data_requirements_checklist.filter(
            (pl.col("priority") == "CRITICAL") & (pl.col("current_status") != "AVAILABLE")
        )
        if not importer.data_requirements_checklist.is_empty()
        else importer.data_requirements_checklist
    )
    canonical_counts = pl.DataFrame(
        [
            {"table": "cme_option_oi_by_strike", "rows": importer.option_oi_by_strike.height},
            {"table": "cme_option_iv_by_strike", "rows": importer.option_iv_by_strike.height},
            {"table": "cme_futures_price", "rows": importer.futures_price.height},
            {"table": "xau_spot_price", "rows": importer.xau_spot_price.height},
            {"table": "xau_basis", "rows": importer.basis.height},
            {"table": "macro_event_calendar", "rows": importer.macro_event_calendar.height},
            {"table": "xau_vol_oi_validation_dataset", "rows": importer.validation_dataset.height},
        ]
    )
    return [
        "- Importer output is local-file only; it does not fetch protected CME data.",
        "- Source paths are redacted and source hashes are used for reproducibility.",
        f"- Files detected: {importer.file_detection.height}",
        f"- Complete validation-grade days: {complete_days}",
        "- Preliminary validation target: `60` complete validation-grade days.",
        "- Serious validation target: `120` complete validation-grade days.",
        "- Robust validation target: `250` complete validation-grade days.",
        "- Orchestrator GPT context pack: `outputs/orchestrator_gpt_context.md`",
        "",
        "### Files Detected By CME Type",
        "",
        _frame_markdown(detection_counts),
        "",
        "### Canonical CME Schema Row Counts",
        "",
        _frame_markdown(canonical_counts),
        "",
        "### Validation-Grade Days",
        "",
        _frame_markdown(grade_counts),
        "",
        "### Missing Critical CME Components",
        "",
        _frame_markdown(missing_critical),
        "",
        "### Basis Adjustment Precision",
        "",
        _frame_markdown(importer.basis_precision_report.head(12)),
        "",
        "### CME Validation-Grade Uplift",
        "",
        _frame_markdown(importer.validation_grade_uplift),
        "",
        "### Data Requirements Checklist",
        "",
        _frame_markdown(importer.data_requirements_checklist),
        "",
        "- Links: `outputs/cme_import_file_detection.csv`, "
        "`outputs/cme_validation_grade_days.csv`, "
        "`outputs/cme_validation_grade_report.md`, "
        "`outputs/basis_adjustment_precision_report.csv`, "
        "`outputs/cme_validation_grade_uplift.csv`, "
        "`outputs/cme_data_requirements_checklist.csv`, "
        "`outputs/orchestrator_gpt_context.md`.",
    ]


def _market_map_proof_pack_lines(proof_pack: MarketMapProofPackResult | None) -> list[str]:
    if proof_pack is None:
        return ["Market-map proof pack was not run."]
    market_map = proof_pack.market_map_precision
    filters = proof_pack.filter_avoided_pnl
    pins = proof_pack.expiry_pin_test
    market_view = (
        market_map.select(
            [
                column
                for column in [
                    "row_type",
                    "test_name",
                    "cohort",
                    "control_type",
                    "event_count",
                    "touch_rate",
                    "acceptance_rate",
                    "touch_uplift_vs_control",
                    "decision_label",
                ]
                if column in market_map.columns
            ]
        ).head(12)
        if not market_map.is_empty()
        else market_map
    )
    filter_view = (
        filters.select(
            [
                column
                for column in [
                    "row_type",
                    "cohort",
                    "control_type",
                    "no_trade_count",
                    "avoided_losing_trade_count",
                    "avoided_winning_trade_count",
                    "net_filter_value",
                    "uplift_vs_matched_state_placebo",
                    "decision_label",
                ]
                if column in filters.columns
            ]
        ).head(12)
        if not filters.is_empty()
        else filters
    )
    pin_view = (
        pins.select(
            [
                column
                for column in [
                    "test_name",
                    "cohort",
                    "control_type",
                    "event_count",
                    "pin_rate",
                    "control_pin_rate",
                    "pin_uplift_vs_control",
                    "decision_label",
                ]
                if column in pins.columns
            ]
        ).head(12)
        if not pins.is_empty()
        else pins
    )
    return [
        f"- Final decision: `{proof_pack.final_decision}`",
        f"- Market-map decision: `{proof_pack.map_decision}`",
        f"- No-trade filter decision: `{proof_pack.filter_decision}`",
        f"- Trade-rule decision: `{proof_pack.trade_rule_decision}`",
        "- Outputs: `outputs/market_map_precision_report.csv`, "
        "`outputs/filter_avoided_pnl_report.csv`, "
        "`outputs/expiry_pin_test_report.csv`, `outputs/proof_pack.md`.",
        "",
        "### Market-Map Precision Snapshot",
        "",
        _frame_markdown(market_view),
        "",
        "### Filter Avoided PnL Snapshot",
        "",
        _frame_markdown(filter_view),
        "",
        "### Expiry Pin Snapshot",
        "",
        _frame_markdown(pin_view),
    ]


def _research_decision_gate_lines(
    decision_gate: ResearchDecisionGateResult | None,
) -> list[str]:
    if decision_gate is None:
        return ["Research decision gate was not run."]
    gate_rows = decision_gate.gate_report
    scorecard = decision_gate.scorecard
    tasks = decision_gate.next_tasks
    failed = gate_rows.filter(pl.col("status") != "PASS") if not gate_rows.is_empty() else gate_rows
    passed = gate_rows.filter(pl.col("status") == "PASS") if not gate_rows.is_empty() else gate_rows
    shadow_ready = decision_gate.final_label in {
        "READY_FOR_SHADOW_MODE",
        "READY_FOR_PAPER_TRADING",
        "READY_FOR_SMALL_CAPITAL_TEST",
    }
    paper_ready = decision_gate.final_label in {"READY_FOR_PAPER_TRADING", "READY_FOR_SMALL_CAPITAL_TEST"}
    return [
        f"- Final decision: `{decision_gate.final_label}`",
        f"- Money-readiness score: `{decision_gate.readiness_score:.1f}/100`",
        f"- Ready for shadow mode: `{shadow_ready}`",
        f"- Ready for paper trading: `{paper_ready}`",
        f"- Ready for real money: `{decision_gate.final_label == 'READY_FOR_SMALL_CAPITAL_TEST'}`",
        "- This gate is intentionally conservative: a promising no-trade filter or market map "
        "does not become a trade rule without data coverage, walk-forward, placebo, and cost gates.",
        "",
        "### Passed Gates",
        "",
        _frame_markdown(passed.select(["gate_name", "status", "evidence"]) if not passed.is_empty() else passed),
        "",
        "### Failed Gates And Blocking Issues",
        "",
        _frame_markdown(
            failed.select(["gate_name", "status", "blocking_issues", "evidence"])
            if not failed.is_empty()
            else failed
        ),
        "",
        "### Money Readiness Score",
        "",
        _frame_markdown(scorecard),
        "",
        "### Top Next Research Tasks",
        "",
        _frame_markdown(tasks.head(10) if not tasks.is_empty() else tasks),
        "",
        "- Links: `outputs/research_decision_gate.csv`, "
        "`outputs/research_readiness_scorecard.csv`, "
        "`outputs/money_readiness_report.md`, "
        "`outputs/next_research_tasks_ranked.csv`, "
        "`outputs/charts/research_gate_status.svg`.",
    ]


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


def _guru_llm_review_lines(guru_llm_review: GuruLlmReviewResult | None) -> list[str]:
    if guru_llm_review is None:
        return ["Blind guru logic review was not run."]
    suggestion_counts = (
        guru_llm_review.suggestions.group_by("suggested_review_decision").len().sort("suggested_review_decision")
        if not guru_llm_review.suggestions.is_empty()
        else guru_llm_review.suggestions
    )
    adversarial_counts = (
        guru_llm_review.adversarial.group_by("adversarial_decision").len().sort("adversarial_decision")
        if not guru_llm_review.adversarial.is_empty()
        else guru_llm_review.adversarial
    )
    final_counts = (
        guru_llm_review.final_suggestions.group_by("suggested_review_decision").len().sort("suggested_review_decision")
        if not guru_llm_review.final_suggestions.is_empty()
        else guru_llm_review.final_suggestions
    )
    final_preview = (
        guru_llm_review.final_suggestions.select([
            "episode_id",
            "suggested_review_decision",
            "corrected_thesis_type",
            "corrected_expected_direction",
            "adversarial_decision",
            "confidence_score",
            "review_risk_flags",
        ]).head(20)
        if not guru_llm_review.final_suggestions.is_empty()
        else guru_llm_review.final_suggestions
    )
    return [
        "- Blind review used only transcript text, timestamp-visible market snapshots, and quality flags.",
        "- Future outcome fields are rejected before suggestion generation.",
        "- Suggestions still require human final approval.",
        "",
        "### Suggested Rules vs Human Approval",
        "",
        _frame_markdown(suggestion_counts),
        "",
        "### Adversarial Review",
        "",
        _frame_markdown(adversarial_counts),
        "",
        "### Final Suggestions",
        "",
        _frame_markdown(final_counts),
        "",
        _frame_markdown(final_preview),
        "",
        "- Links: `outputs/guru_llm_review_suggestions.csv`, "
        "`outputs/guru_llm_review_final_suggestions.csv`, `outputs/guru_llm_review_audit.md`.",
    ]


def _guru_full_context_review_lines(guru_review: GuruFullContextReviewResult | None) -> list[str]:
    if guru_review is None:
        return ["Full-context guru logic review was not run."]
    suggestions = guru_review.suggestions
    suggestion_counts = (
        suggestions.group_by("suggested_decision").len().sort("suggested_decision")
        if not suggestions.is_empty()
        else suggestions
    )
    logic_counts = (
        suggestions.group_by("suggested_guru_logic_type").len().sort("suggested_guru_logic_type")
        if not suggestions.is_empty()
        else suggestions
    )
    review_preview = (
        suggestions.select([
            "episode_id",
            "rule_tag",
            "suggested_decision",
            "suggested_guru_logic_type",
            "usable_as_context",
            "usable_as_market_map",
            "usable_as_filter",
            "usable_as_trade_rule",
            "reason_for_decision",
        ]).head(20)
        if not suggestions.is_empty()
        else suggestions
    )
    return [
        f"- Revised Guru Logic Decision: `{guru_review.final_decision}`",
        f"- Full-context review pack rows: {guru_review.review_pack.height}",
        f"- Human review template rows: {guru_review.decisions_template.height}",
        "- This layer separates faithful extraction from later quantitative usefulness.",
        "- Future outcomes are excluded from the review pack and joined only for post-review metrics.",
        "",
        "### Review Taxonomy Counts",
        "",
        _frame_markdown(suggestion_counts),
        "",
        "### Logic Type Counts",
        "",
        _frame_markdown(logic_counts),
        "",
        "### Classification Preview",
        "",
        _frame_markdown(review_preview),
        "",
        "### Filter Value Results",
        "",
        _frame_markdown(guru_review.filter_value),
        "",
        "### Market-Map Validation Results",
        "",
        _frame_markdown(guru_review.market_map_validation),
        "",
        "- Links: `outputs/guru_full_context_review_pack.csv`, "
        "`outputs/guru_full_context_review_suggestions.csv`, "
        "`outputs/guru_full_context_review_decisions_template.csv`, "
        "`outputs/guru_full_context_review_report.md`.",
    ]


def _guru_logic_knowledge_base_lines(result: GuruLogicKnowledgeBaseResult | None) -> list[str]:
    if result is None:
        return ["Guru Logic Knowledge Base was not run."]
    top = _priority_preview(result, 10)
    return [
        "Research-only extraction layer. Logic can be extracted from transcripts now, "
        "while CME validation remains gated by data coverage.",
        "",
        f"- Repeated guru logic concepts extracted: {result.knowledge_base.height}",
        f"- Current validation-grade CME days: {result.current_available_validation_days}",
        f"- Preliminary validation threshold: {result.minimum_validation_days}",
        f"- Guru logic recommendation: `{result.final_recommendation}`",
        "",
        "### Top Concepts",
        "",
        _frame_markdown(top),
        "",
        "- Links: `outputs/guru_logic_knowledge_base.csv`, "
        "`outputs/guru_logic_knowledge_base.md`.",
    ]


def _guru_logic_extractable_now_lines(result: GuruLogicKnowledgeBaseResult | None) -> list[str]:
    if result is None:
        return ["Guru Logic Knowledge Base was not run."]
    context = _priority_actions(result, {"USE_AS_PLAYBOOK_CONTEXT_NOW", "TEST_PRICE_ONLY_NOW"})
    return [
        "- Repeated wording, market-map context, no-trade/filter language, and required "
        "data dependencies can be extracted without CME validation data.",
        "- Extracted logic remains research context until later validation controls pass.",
        "",
        _frame_markdown(context),
    ]


def _guru_logic_not_proven_lines(result: GuruLogicKnowledgeBaseResult | None) -> list[str]:
    if result is None:
        return ["Guru Logic Knowledge Base was not run."]
    blocked = _priority_actions(
        result,
        {"WAIT_FOR_MORE_CME_DATA", "COLLECT_REQUIRED_DATA_FIRST", "IGNORE_OR_REJECT"},
    )
    return [
        "- The extracted logic is not validated for performance.",
        "- Full CME validation cannot be claimed while aligned validation-grade days remain "
        f"below {result.minimum_validation_days}.",
        "- Direct trade-rule use, live trading, paper trading, and broker integration remain "
        "out of scope.",
        "",
        _frame_markdown(blocked),
    ]


def _guru_logic_dependency_matrix_lines(result: GuruLogicKnowledgeBaseResult | None) -> list[str]:
    if result is None:
        return ["Guru Logic Knowledge Base was not run."]
    columns = [
        "logic_id",
        "logic_name",
        "requires_xau_spot",
        "requires_gc_futures",
        "requires_basis",
        "requires_cme_oi_by_strike",
        "requires_oi_change",
        "requires_option_volume",
        "requires_iv",
        "current_available_validation_days",
        "validation_blocker",
    ]
    frame = result.dependency_matrix
    selected = frame.select([column for column in columns if column in frame.columns]).head(20)
    return [
        _frame_markdown(selected),
        "",
        "- Links: `outputs/guru_logic_data_dependency_matrix.csv`, "
        "`outputs/guru_logic_data_dependency_matrix.md`.",
    ]


def _guru_logic_priority_lines(result: GuruLogicKnowledgeBaseResult | None) -> list[str]:
    if result is None:
        return ["Guru Logic Knowledge Base was not run."]
    return [
        _frame_markdown(_priority_preview(result, 20)),
        "",
        "- Link: `outputs/guru_logic_priority_rank.csv`.",
    ]


def _guru_logic_collection_plan_lines(result: GuruLogicKnowledgeBaseResult | None) -> list[str]:
    if result is None:
        return ["Guru Logic Knowledge Base was not run."]
    columns = [
        "source_name",
        "priority",
        "current_status",
        "user_action_required",
    ]
    frame = result.collection_plan
    selected = frame.select([column for column in columns if column in frame.columns])
    return [
        _frame_markdown(selected),
        "",
        "- Links: `outputs/cme_collection_plan_for_guru_logic.csv`, "
        "`outputs/cme_collection_plan_for_guru_logic.md`.",
    ]


def _guru_logic_validation_path_lines(result: GuruLogicKnowledgeBaseResult | None) -> list[str]:
    if result is None:
        return ["Guru Logic Knowledge Base was not run."]
    columns = [
        "logic_type",
        "what_can_be_done_now",
        "what_cannot_be_proven_yet",
        "validation_method",
        "pass_criteria",
    ]
    frame = result.validation_path
    selected = frame.select([column for column in columns if column in frame.columns])
    return [
        _frame_markdown(selected),
        "",
        "- Links: `outputs/guru_logic_validation_path.csv`, "
        "`outputs/guru_logic_validation_path.md`.",
    ]


def _guru_logic_final_recommendation_lines(result: GuruLogicKnowledgeBaseResult | None) -> list[str]:
    if result is None:
        return ["Guru Logic Knowledge Base was not run."]
    return [
        f"`{result.final_recommendation}`",
        "",
        "The practical path is to keep extracting repeated guru concepts now, use the best "
        "filter/map candidates only as research context or price-only pilots, and collect "
        "more aligned CME data before validation claims.",
    ]


def _priority_preview(result: GuruLogicKnowledgeBaseResult, limit: int) -> pl.DataFrame:
    if result.priority_rank.is_empty():
        return result.priority_rank
    columns = [
        "rank",
        "logic_id",
        "logic_name",
        "logic_type",
        "transcript_count",
        "priority_score",
        "recommended_action",
    ]
    return result.priority_rank.select([column for column in columns if column in result.priority_rank.columns]).head(limit)


def _priority_actions(result: GuruLogicKnowledgeBaseResult, actions: set[str]) -> pl.DataFrame:
    if result.priority_rank.is_empty() or "recommended_action" not in result.priority_rank.columns:
        return result.priority_rank
    return _priority_preview(
        GuruLogicKnowledgeBaseResult(
            knowledge_base=result.knowledge_base,
            dependency_matrix=result.dependency_matrix,
            priority_rank=result.priority_rank.filter(pl.col("recommended_action").is_in(sorted(actions))),
            collection_plan=result.collection_plan,
            validation_path=result.validation_path,
            final_recommendation=result.final_recommendation,
            current_available_validation_days=result.current_available_validation_days,
            minimum_validation_days=result.minimum_validation_days,
        ),
        20,
    )


def _guru_monte_carlo_lines(guru_monte_carlo: GuruMonteCarloValidationResult | None) -> list[str]:
    if guru_monte_carlo is None:
        return ["Guru Monte Carlo validation was not run."]
    validation = guru_monte_carlo.validation
    return [
        f"- Final Guru Logic Decision: `{guru_monte_carlo.final_decision}`",
        f"- Validation rows: {validation.height}",
        f"- Markov transition rows: {guru_monte_carlo.markov_transitions.height}",
        "",
        "### Permutation Test",
        "",
        _frame_markdown(_method_rows(validation, "PERMUTATION")),
        "",
        "### Date-Shift Placebo",
        "",
        _frame_markdown(_method_rows(validation, "DATE_SHIFT_PLACEBO")),
        "",
        "### Matched Market-State Placebo",
        "",
        _frame_markdown(_method_rows(validation, "MATCHED_MARKET_STATE_PLACEBO")),
        "",
        "### Markov Transition Test",
        "",
        _frame_markdown(guru_monte_carlo.markov_transitions),
        "",
        "- Links: `outputs/guru_monte_carlo_validation.csv`, `outputs/guru_monte_carlo_report.md`.",
    ]


def _gold_baseline_lab_lines(gold_lab: GoldBaselineLabResult | None) -> list[str]:
    if gold_lab is None:
        return ["Gold baseline lab was not run."]
    metrics = gold_lab.metrics
    full = (
        metrics.filter(pl.col("evaluation_type") == "full_sample")
        .sort("expectancy", descending=True)
        if not metrics.is_empty()
        else metrics
    )
    placebo = (
        metrics.filter(pl.col("evaluation_type").is_in(["permutation_test", "matched_state_placebo"]))
        if not metrics.is_empty()
        else metrics
    )
    columns = [
        "stage",
        "scenario",
        "scenario_family",
        "edge_type",
        "event_count",
        "trade_count",
        "expectancy",
        "profit_factor",
        "uplift_vs_best_baseline",
        "sample_size_warning",
    ]
    placebo_columns = [
        "stage",
        "scenario",
        "evaluation_type",
        "trade_count",
        "expectancy",
        "placebo_expectancy",
        "uplift_vs_placebo",
        "p_value",
        "permutation_pass",
        "matched_placebo_pass",
    ]
    return [
        f"- Final decision: `{gold_lab.final_decision}`",
        f"- Statistically credible uplift stage: `{gold_lab.credible_uplift_stage}`",
        f"- Guru uplift beyond non-guru CME baselines: `{gold_lab.guru_uplift_decision}`",
        f"- Best edge type: `{gold_lab.best_edge_type}`",
        "",
        "### Full-Sample Gold Baselines And Stages",
        "",
        _frame_markdown(full.select([column for column in columns if column in full.columns]) if not full.is_empty() else full),
        "",
        "### Placebo / Permutation Checks",
        "",
        _frame_markdown(
            placebo.select([column for column in placebo_columns if column in placebo.columns])
            if not placebo.is_empty()
            else placebo
        ),
        "",
        "- Links: `outputs/gold_baseline_metrics.csv`, `outputs/gold_ablation_report.md`, "
        "`outputs/charts/gold_baseline_vs_uplift.svg`.",
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
        rows.append("| " + " | ".join(_markdown_cell(raw.get(column, "")) for column in columns) + " |")
    return "\n".join(rows)


def _markdown_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _method_rows(frame: pl.DataFrame, method: str) -> pl.DataFrame:
    if frame.is_empty() or "method" not in frame.columns:
        return frame
    return frame.filter(pl.col("method") == method)


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
