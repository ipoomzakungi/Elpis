"""Gold baseline and staged uplift lab for XAU Vol-OI research.

The lab asks whether CME/QuikStrike-derived and guru-derived features add
incremental value over simple gold baselines. It is research-only: generated
events are deterministic study labels, not orders or live/paper trading signals.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import polars as pl

from research_xau_vol_oi.config import ResearchConfig, Signal


MIN_SAMPLE_SIZE = 20
PERMUTATION_ITERATIONS = 300
DIRECTIONAL_SIGNALS = {
    Signal.FADE_WALL_LONG.value: 1,
    Signal.BREAK_WALL_LONG.value: 1,
    Signal.FADE_WALL_SHORT.value: -1,
    Signal.BREAK_WALL_SHORT.value: -1,
}
APPROVED_TRADE_RULE_DECISIONS = {"APPROVE_TRADE_RULE", "APPROVE"}
CONTEXT_FILTER_MAP_DECISIONS = {
    "SUGGEST_APPROVE_CONTEXT",
    "SUGGEST_APPROVE_MARKET_MAP",
    "SUGGEST_APPROVE_FILTER",
    "APPROVE_CONTEXT",
    "APPROVE_MARKET_MAP",
    "APPROVE_FILTER",
}


@dataclass(frozen=True)
class GoldBaselineLabResult:
    """Generated frames and conservative research conclusion."""

    metrics: pl.DataFrame
    scenario_events: pl.DataFrame
    final_decision: str
    credible_uplift_stage: str
    guru_uplift_decision: str
    best_edge_type: str


def run_gold_baseline_lab(
    *,
    feature_table: pl.DataFrame,
    signal_events: pl.DataFrame,
    output_dir: Path,
    charts_dir: Path,
    config: ResearchConfig | None = None,
    transcript_conditioned_events: pl.DataFrame | None = None,
    guru_context_records: pl.DataFrame | None = None,
    approved_rule_records: pl.DataFrame | None = None,
) -> GoldBaselineLabResult:
    """Run gold baselines, staged uplifts, reports, and chart outputs."""

    cfg = config or ResearchConfig()
    output_dir.mkdir(parents=True, exist_ok=True)
    charts_dir.mkdir(parents=True, exist_ok=True)

    scenario_events = build_gold_lab_events(
        feature_table=feature_table,
        signal_events=signal_events,
        transcript_conditioned_events=transcript_conditioned_events,
        guru_context_records=guru_context_records,
        approved_rule_records=approved_rule_records,
        config=cfg,
    )
    metrics = evaluate_gold_lab_scenarios(
        feature_table,
        scenario_events,
        config=cfg,
    )
    final_decision = gold_lab_final_decision(metrics)
    credible_stage = credible_uplift_stage(metrics)
    guru_decision = guru_uplift_decision(metrics)
    best_edge = best_edge_type(metrics)

    metrics.write_csv(output_dir / "gold_baseline_metrics.csv")
    write_gold_ablation_report(
        output_dir / "gold_ablation_report.md",
        metrics=metrics,
        final_decision=final_decision,
        credible_stage=credible_stage,
        guru_decision=guru_decision,
        best_edge=best_edge,
    )
    write_gold_baseline_chart(
        charts_dir / "gold_baseline_vs_uplift.svg",
        metrics=metrics,
    )
    return GoldBaselineLabResult(
        metrics=metrics,
        scenario_events=scenario_events,
        final_decision=final_decision,
        credible_uplift_stage=credible_stage,
        guru_uplift_decision=guru_decision,
        best_edge_type=best_edge,
    )


def build_gold_lab_events(
    *,
    feature_table: pl.DataFrame,
    signal_events: pl.DataFrame,
    transcript_conditioned_events: pl.DataFrame | None = None,
    guru_context_records: pl.DataFrame | None = None,
    approved_rule_records: pl.DataFrame | None = None,
    config: ResearchConfig | None = None,
) -> pl.DataFrame:
    """Create deterministic baseline and staged research events."""

    cfg = config or ResearchConfig()
    parts = [
        _gold_trend_events(feature_table, lookback=4, scenario="GOLD_TREND_4B"),
        _gold_trend_events(feature_table, lookback=16, scenario="GOLD_TREND_16B"),
        _gold_trend_events(
            feature_table,
            lookback=16,
            scenario="GOLD_TREND_16B_VOL_TARGET",
            vol_targeted=True,
        ),
        _iv_range_reentry_events(feature_table),
        _iv_range_breach_events(feature_table),
        _wall_reaction_events(signal_events, stage="BASELINE_WALL_REACTION", scenario="WALL_ACCEPT_REJECT"),
    ]
    wall = _wall_reaction_events(
        signal_events,
        stage="BASELINE_WALL_REACTION",
        scenario="WALL_ACCEPT_REJECT",
    )
    stage_a = _stage_a_oi_freshness_volume(wall, feature_table)
    stage_b = _stage_b_iv_rv_vrp(stage_a, feature_table)
    stage_c = _stage_c_open_context(stage_b, feature_table)
    stage_d = _stage_d_guru_context(
        stage_c,
        transcript_conditioned_events,
        guru_context_records,
        config=cfg,
    )
    stage_e = _stage_e_approved_trade_rules(
        stage_c,
        transcript_conditioned_events,
        approved_rule_records,
    )
    parts.extend([stage_a, stage_b, stage_c, stage_d, stage_e])
    frames = [part for part in parts if not part.is_empty()]
    if not frames:
        return _empty_lab_events()
    return pl.concat(frames, how="diagonal_relaxed").sort(["event_timestamp", "scenario"])


def evaluate_gold_lab_scenarios(
    feature_table: pl.DataFrame,
    scenario_events: pl.DataFrame,
    *,
    config: ResearchConfig | None = None,
    permutation_iterations: int = PERMUTATION_ITERATIONS,
) -> pl.DataFrame:
    """Evaluate every scenario with full sample, walk-forward, placebo, and stress rows."""

    cfg = config or ResearchConfig()
    if feature_table.is_empty() or scenario_events.is_empty():
        return _empty_metrics()
    rows: list[dict[str, Any]] = []
    scenario_names = sorted(set(scenario_events.get_column("scenario").to_list()))
    for scenario in scenario_names:
        events = scenario_events.filter(pl.col("scenario") == scenario)
        rows.append(_metrics_row(feature_table, events, cfg, evaluation_type="full_sample"))
        rows.extend(_event_stratified_rows(feature_table, events, cfg))
        rows.extend(_expiry_split_rows(feature_table, events, cfg))
        rows.extend(_cost_stress_rows(feature_table, events, cfg))
        rows.extend(_walk_forward_rows(feature_table, events, cfg))
        rows.append(
            _permutation_row(
                feature_table,
                scenario_events,
                events,
                cfg,
                iterations=permutation_iterations,
            )
        )
        rows.append(_matched_state_placebo_row(feature_table, scenario_events, events, cfg))
    metrics = pl.DataFrame(rows, infer_schema_length=None) if rows else _empty_metrics()
    summary = _walk_forward_summary(metrics)
    if not summary.is_empty():
        metrics = pl.concat([metrics, summary], how="diagonal_relaxed")
    return metrics


def gold_lab_final_decision(metrics: pl.DataFrame) -> str:
    """Return the conservative lab decision."""

    if metrics.is_empty():
        return "NO_EDGE_PROVEN"
    credible = credible_uplift_stage(metrics)
    if credible != "NONE":
        return "PROMISING_BUT_UNVALIDATED"
    return "NO_EDGE_PROVEN"


def credible_uplift_stage(metrics: pl.DataFrame) -> str:
    """Identify the first stage with statistically credible uplift, if any."""

    if metrics.is_empty():
        return "NONE"
    for stage in ["A_OI_FRESHNESS_VOLUME", "B_IV_RV_VRP", "C_OPEN_CONTEXT", "D_GURU_CONTEXT_FILTER_MAP", "E_GURU_TRADE_RULE"]:
        rows = _stage_rows(metrics, stage)
        if rows.is_empty():
            continue
        full = _best_full_row(rows)
        if not full:
            continue
        wf = _walk_forward_pass(rows)
        permutation = _test_pass(rows, "permutation_test")
        matched = _test_pass(rows, "matched_state_placebo")
        enough = not bool(full.get("sample_size_warning"))
        uplift = _none_safe(full.get("uplift_vs_best_baseline"))
        if enough and uplift > 0 and wf and permutation and matched:
            return stage
    return "NONE"


def guru_uplift_decision(metrics: pl.DataFrame) -> str:
    """State whether guru features help beyond non-guru CME baselines."""

    if metrics.is_empty():
        return "GURU_NO_UPLIFT_PROVEN"
    stage_d = _best_full_row(_stage_rows(metrics, "D_GURU_CONTEXT_FILTER_MAP"))
    stage_e = _best_full_row(_stage_rows(metrics, "E_GURU_TRADE_RULE"))
    best_non_guru = _best_non_guru_expectancy(metrics)
    guru_rows = [row for row in [stage_d, stage_e] if row]
    if not guru_rows:
        return "GURU_NOT_TESTABLE"
    best_guru = max(guru_rows, key=lambda row: _none_safe(row.get("expectancy")))
    if (
        _none_safe(best_guru.get("expectancy")) > best_non_guru
        and _walk_forward_pass(_stage_rows(metrics, str(best_guru.get("stage"))))
        and _test_pass(_stage_rows(metrics, str(best_guru.get("stage"))), "permutation_test")
        and _test_pass(_stage_rows(metrics, str(best_guru.get("stage"))), "matched_state_placebo")
        and not bool(best_guru.get("sample_size_warning"))
    ):
        return "GURU_PROMISING_UPLIFT"
    return "GURU_NO_CREDIBLE_UPLIFT"


def best_edge_type(metrics: pl.DataFrame) -> str:
    """Classify whether map, filter, or trade-rule edge is currently best."""

    if metrics.is_empty():
        return "NONE"
    credible = credible_uplift_stage(metrics)
    rows = [
        row
        for row in metrics.filter(pl.col("evaluation_type") == "full_sample").to_dicts()
        if row.get("edge_type") in {"map", "filter", "trade_rule"}
    ]
    if not rows:
        return "NONE"
    best = max(rows, key=lambda row: _none_safe(row.get("expectancy")))
    if credible == "NONE" or bool(best.get("sample_size_warning")):
        return f"{best['edge_type'].upper()}_UNVALIDATED"
    return str(best["edge_type"]).upper()


def write_gold_ablation_report(
    path: Path,
    *,
    metrics: pl.DataFrame,
    final_decision: str,
    credible_stage: str,
    guru_decision: str,
    best_edge: str,
) -> None:
    """Write the gold baseline and uplift Markdown report."""

    full = (
        metrics.filter(pl.col("evaluation_type") == "full_sample")
        .sort("expectancy", descending=True)
        if not metrics.is_empty()
        else metrics
    )
    wf = _walk_forward_summary(metrics)
    placebo = (
        metrics.filter(pl.col("evaluation_type").is_in(["permutation_test", "matched_state_placebo"]))
        if not metrics.is_empty()
        else metrics
    )
    lines = [
        "# Gold Baseline And Uplift Lab",
        "",
        "Research-only comparison of simple gold baselines against staged CME and guru-derived features.",
        "No live trading, paper trading, broker connection, or predictive claim is made.",
        "",
        f"- Final decision: `{final_decision}`",
        f"- Statistically credible uplift stage: `{credible_stage}`",
        f"- Guru uplift beyond non-guru CME baselines: `{guru_decision}`",
        f"- Best edge type: `{best_edge}`",
        "",
        "## Full-Sample Metrics",
        "",
        _frame_markdown(_report_columns(full)),
        "",
        "## Walk-Forward",
        "",
        _frame_markdown(_report_columns(wf)),
        "",
        "## Permutation And Matched-State Placebo",
        "",
        _frame_markdown(_report_columns(placebo)),
        "",
        "## Stage Interpretation",
        "",
        "- Stage A tests whether OI freshness and volume filters add value to wall reactions.",
        "- Stage B adds IV/RV/VRP regime context.",
        "- Stage C adds session-open side/open-flip context.",
        "- Stage D adds guru context/filter/map features as research-preview context unless human-approved.",
        "- Stage E is disabled unless human-approved/frozen trade-rule records exist.",
        "",
        "## Research Decision",
        "",
        "- Uplift is marked credible only when sample size is adequate, walk-forward test expectancy is positive, "
        "permutation and matched-state placebo tests pass, and the stage beats the best simple baseline.",
        "- If these gates fail, the correct conclusion is no credible incremental edge yet.",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_gold_baseline_chart(path: Path, *, metrics: pl.DataFrame) -> None:
    """Write a compact SVG comparing baseline and staged expectancy."""

    full = metrics.filter(pl.col("evaluation_type") == "full_sample") if not metrics.is_empty() else metrics
    if full.is_empty():
        path.write_text(_svg("Gold baseline vs uplift", '<text x="40" y="80">No data.</text>'), encoding="utf-8")
        return
    rows = sorted(full.to_dicts(), key=lambda row: str(row.get("scenario")))
    labels = [str(row.get("scenario"))[:18] for row in rows]
    values = [_none_safe(row.get("expectancy")) for row in rows]
    path.write_text(_bar_svg("Gold baseline vs staged uplift expectancy", labels, values), encoding="utf-8")


def _gold_trend_events(
    feature_table: pl.DataFrame,
    *,
    lookback: int,
    scenario: str,
    vol_targeted: bool = False,
) -> pl.DataFrame:
    rows = feature_table.sort("timestamp").to_dicts() if not feature_table.is_empty() else []
    if len(rows) <= lookback:
        return _empty_lab_events()
    rv_values = [float(row.get("rv_percent") or 0.0) for row in rows if row.get("rv_percent") is not None]
    target_rv = _median(rv_values) or 10.0
    events = []
    for index in range(lookback, len(rows)):
        current = rows[index]
        past = rows[index - lookback]
        close = _float(current.get("close"))
        past_close = _float(past.get("close"))
        if close is None or past_close is None or close == past_close:
            continue
        direction = 1 if close > past_close else -1
        rv = max(_float(current.get("rv_percent")) or target_rv, 1e-9)
        size = min(2.0, max(0.25, target_rv / rv)) if vol_targeted else 1.0
        events.append(
            _event_from_price_row(
                current,
                stage="BASELINE_TREND",
                scenario=scenario,
                family="gold_trend_baseline",
                edge_type="trend",
                direction=direction,
                reason=f"{lookback}_bar_time_series_momentum",
                position_size=size,
            )
        )
    return pl.DataFrame(events, infer_schema_length=None) if events else _empty_lab_events()


def _iv_range_reentry_events(feature_table: pl.DataFrame) -> pl.DataFrame:
    rows = feature_table.sort("timestamp").to_dicts() if not feature_table.is_empty() else []
    events = []
    for previous, current in zip(rows, rows[1:], strict=False):
        prior_sigma = _float(previous.get("sigma_position"))
        sigma = _float(current.get("sigma_position"))
        if prior_sigma is None or sigma is None:
            continue
        if prior_sigma > 1.0 and sigma <= 1.0:
            direction = -1
        elif prior_sigma < -1.0 and sigma >= -1.0:
            direction = 1
        else:
            continue
        events.append(
            _event_from_price_row(
                current,
                stage="BASELINE_IV_RANGE",
                scenario="IV_RANGE_REENTRY",
                family="iv_range_baseline",
                edge_type="range",
                direction=direction,
                reason="expected_move_breach_reentry",
            )
        )
    return pl.DataFrame(events, infer_schema_length=None) if events else _empty_lab_events()


def _iv_range_breach_events(feature_table: pl.DataFrame) -> pl.DataFrame:
    rows = feature_table.sort("timestamp").to_dicts() if not feature_table.is_empty() else []
    events = []
    for current in rows:
        sigma = _float(current.get("sigma_position"))
        if sigma is None or abs(sigma) < 1.5:
            continue
        events.append(
            _event_from_price_row(
                current,
                stage="BASELINE_IV_RANGE",
                scenario="IV_RANGE_BREACH",
                family="iv_range_baseline",
                edge_type="range",
                direction=1 if sigma > 0 else -1,
                reason="expected_move_breach_momentum_control",
            )
        )
    return pl.DataFrame(events, infer_schema_length=None) if events else _empty_lab_events()


def _wall_reaction_events(signal_events: pl.DataFrame, *, stage: str, scenario: str) -> pl.DataFrame:
    rows = []
    if signal_events.is_empty():
        return _empty_lab_events()
    for event in signal_events.to_dicts():
        signal = str(event.get("signal") or "")
        direction = DIRECTIONAL_SIGNALS.get(signal)
        if direction is None:
            continue
        rows.append(
            _event_from_signal_row(
                event,
                stage=stage,
                scenario=scenario,
                family="wall_reaction_baseline",
                edge_type="map",
                direction=direction,
                reason="basis_adjusted_wall_acceptance_rejection_no_guru",
            )
        )
    return pl.DataFrame(rows, infer_schema_length=None) if rows else _empty_lab_events()


def _stage_a_oi_freshness_volume(wall_events: pl.DataFrame, feature_table: pl.DataFrame) -> pl.DataFrame:
    if wall_events.is_empty():
        return _empty_lab_events()
    rows = []
    volume_median = _median([_float(row.get("volume")) or 0.0 for row in feature_table.to_dicts()])
    freshness_values = [_float(row.get("freshness_weight")) for row in wall_events.to_dicts()]
    freshness_cutoff = _median([value for value in freshness_values if value is not None]) or 0.0
    price_by_ts = _price_by_timestamp(feature_table)
    for row in wall_events.to_dicts():
        price = price_by_ts.get(row.get("event_timestamp"), {})
        volume = _float(price.get("volume")) or 0.0
        freshness = _float(row.get("freshness_weight")) or 0.0
        if freshness >= freshness_cutoff or volume >= volume_median:
            rows.append(
                {
                    **row,
                    "stage": "A_OI_FRESHNESS_VOLUME",
                    "scenario": "A_WALL_PLUS_FRESHNESS_VOLUME",
                    "scenario_family": "cme_feature_stage",
                    "edge_type": "map",
                    "reason": "wall_reaction_filtered_by_oi_freshness_or_volume",
                }
            )
    return pl.DataFrame(rows, infer_schema_length=None) if rows else _empty_lab_events()


def _stage_b_iv_rv_vrp(stage_a: pl.DataFrame, feature_table: pl.DataFrame) -> pl.DataFrame:
    if stage_a.is_empty():
        return _empty_lab_events()
    price_by_ts = _price_by_timestamp(feature_table)
    rows = []
    for row in stage_a.to_dicts():
        price = price_by_ts.get(row.get("event_timestamp"), {})
        vol_regime = str(price.get("vol_regime") or row.get("vol_regime") or "UNKNOWN")
        vrp = _float(price.get("vrp"))
        if vol_regime in {"IV_PREMIUM", "RV_PREMIUM", "STRESS"} or (vrp is not None and abs(vrp) > 0):
            rows.append(
                {
                    **row,
                    "stage": "B_IV_RV_VRP",
                    "scenario": "B_WALL_PLUS_IV_RV_VRP",
                    "scenario_family": "cme_feature_stage",
                    "edge_type": "map",
                    "vol_regime": vol_regime,
                    "reason": "stage_a_plus_iv_rv_vrp_regime",
                }
            )
    return pl.DataFrame(rows, infer_schema_length=None) if rows else _empty_lab_events()


def _stage_c_open_context(stage_b: pl.DataFrame, feature_table: pl.DataFrame) -> pl.DataFrame:
    if stage_b.is_empty():
        return _empty_lab_events()
    price_by_ts = _price_by_timestamp(feature_table)
    rows = []
    for row in stage_b.to_dicts():
        price = price_by_ts.get(row.get("event_timestamp"), {})
        direction = int(row.get("direction") or 0)
        close = _float(price.get("close"))
        session_open = _float(price.get("session_open"))
        if close is None or session_open is None:
            continue
        open_side = "ABOVE_OPEN" if close >= session_open else "BELOW_OPEN"
        if (direction > 0 and open_side == "ABOVE_OPEN") or (direction < 0 and open_side == "BELOW_OPEN"):
            rows.append(
                {
                    **row,
                    "stage": "C_OPEN_CONTEXT",
                    "scenario": "C_WALL_PLUS_OPEN_CONTEXT",
                    "scenario_family": "cme_feature_stage",
                    "edge_type": "filter",
                    "open_side": open_side,
                    "reason": "stage_b_plus_session_open_side_alignment",
                }
            )
    return pl.DataFrame(rows, infer_schema_length=None) if rows else _empty_lab_events()


def _stage_d_guru_context(
    stage_c: pl.DataFrame,
    transcript_conditioned_events: pl.DataFrame | None,
    guru_context_records: pl.DataFrame | None,
    *,
    config: ResearchConfig,
) -> pl.DataFrame:
    if stage_c.is_empty() or not config.research_preview_mode:
        return _empty_lab_events()
    conditioned = _conditioned_by_key(transcript_conditioned_events)
    context_tags = _guru_context_tags(guru_context_records)
    rows = []
    for row in stage_c.to_dicts():
        conditioned_row = conditioned.get(_event_key(row), {})
        active_tags = _split_tags(conditioned_row.get("active_transcript_rule_tags"))
        if not active_tags:
            continue
        if context_tags and not set(active_tags).intersection(context_tags):
            continue
        rows.append(
            {
                **row,
                "stage": "D_GURU_CONTEXT_FILTER_MAP",
                "scenario": "D_GURU_CONTEXT_FILTER_MAP",
                "scenario_family": "guru_feature_stage",
                "edge_type": "filter",
                "active_transcript_rule_tags": "|".join(active_tags),
                "uses_unapproved_guru_features": True,
                "reason": "stage_c_plus_asof_guru_context_filter_map_preview",
            }
        )
    return pl.DataFrame(rows, infer_schema_length=None) if rows else _empty_lab_events()


def _stage_e_approved_trade_rules(
    stage_c: pl.DataFrame,
    transcript_conditioned_events: pl.DataFrame | None,
    approved_rule_records: pl.DataFrame | None,
) -> pl.DataFrame:
    if stage_c.is_empty() or approved_rule_records is None or approved_rule_records.is_empty():
        return _empty_lab_events()
    approved_tags = _approved_trade_rule_tags(approved_rule_records)
    if not approved_tags:
        return _empty_lab_events()
    conditioned = _conditioned_by_key(transcript_conditioned_events)
    rows = []
    for row in stage_c.to_dicts():
        conditioned_row = conditioned.get(_event_key(row), {})
        active_tags = set(_split_tags(conditioned_row.get("active_transcript_rule_tags")))
        if not active_tags.intersection(approved_tags):
            continue
        rows.append(
            {
                **row,
                "stage": "E_GURU_TRADE_RULE",
                "scenario": "E_APPROVED_GURU_TRADE_RULE",
                "scenario_family": "guru_feature_stage",
                "edge_type": "trade_rule",
                "active_transcript_rule_tags": "|".join(sorted(active_tags.intersection(approved_tags))),
                "uses_unapproved_guru_features": False,
                "reason": "stage_c_plus_human_approved_frozen_guru_trade_rule",
            }
        )
    return pl.DataFrame(rows, infer_schema_length=None) if rows else _empty_lab_events()


def _run_lab_event_backtest(
    price: pl.DataFrame,
    events: pl.DataFrame,
    *,
    config: ResearchConfig,
    max_exit_timestamp: Any | None = None,
) -> pl.DataFrame:
    if price.is_empty() or events.is_empty():
        return _empty_trades()
    price_rows = price.sort("timestamp").to_dicts()
    event_rows = events.sort("event_timestamp").to_dicts()
    trades = []
    for event in event_rows:
        direction = int(event.get("direction") or 0)
        if direction == 0:
            continue
        entry_index = _first_price_index_after(price_rows, event.get("event_timestamp"))
        if entry_index is None:
            continue
        exit_index = min(entry_index + config.backtest_horizon_bars, len(price_rows) - 1)
        if exit_index <= entry_index:
            continue
        entry = price_rows[entry_index]
        exit_bar = price_rows[exit_index]
        if max_exit_timestamp is not None and exit_bar["timestamp"] > max_exit_timestamp:
            continue
        path = price_rows[entry_index : exit_index + 1]
        entry_price = float(entry.get("open") or entry["close"])
        exit_price = float(exit_bar["close"])
        position_size = float(event.get("position_size") or 1.0)
        pnl_points = (exit_price - entry_price) * direction * position_size
        round_trip_cost = 2.0 * (
            config.cost_points_per_side + config.slippage_points_per_side
        ) * position_size
        net_pnl = pnl_points - round_trip_cost
        mae, mfe = _mae_mfe(path, entry_price=entry_price, direction=direction, position_size=position_size)
        trades.append(
            {
                **event,
                "entry_timestamp": entry["timestamp"],
                "exit_timestamp": exit_bar["timestamp"],
                "entry_price": entry_price,
                "exit_price": exit_price,
                "pnl_points": pnl_points,
                "round_trip_cost_points": round_trip_cost,
                "net_pnl_points": net_pnl,
                "mae_points": mae,
                "mfe_points": mfe,
                "time_in_trade_bars": exit_index - entry_index,
                "research_only": True,
            }
        )
    return pl.DataFrame(trades, infer_schema_length=None) if trades else _empty_trades()


def _metrics_row(
    feature_table: pl.DataFrame,
    events: pl.DataFrame,
    config: ResearchConfig,
    *,
    evaluation_type: str,
    subgroup_type: str = "all",
    subgroup: str = "all",
    split_id: int | None = None,
    cost_multiplier: int = 1,
    placebo_expectancy: float | None = None,
    p_value: float | None = None,
) -> dict[str, Any]:
    trades = _run_lab_event_backtest(feature_table, events, config=config)
    event_rows = events.to_dicts()
    scenario = str(event_rows[0].get("scenario") if event_rows else "")
    stage = str(event_rows[0].get("stage") if event_rows else "")
    family = str(event_rows[0].get("scenario_family") if event_rows else "")
    edge_type = str(event_rows[0].get("edge_type") if event_rows else "")
    metrics = _trade_metrics(trades.to_dicts())
    baseline_expectancy = _best_baseline_expectancy_for_events(feature_table, events, config)
    return {
        "stage": stage,
        "scenario": scenario,
        "scenario_family": family,
        "edge_type": edge_type,
        "evaluation_type": evaluation_type,
        "split_id": split_id,
        "subgroup_type": subgroup_type,
        "subgroup": subgroup,
        "event_count": events.height if not events.is_empty() else 0,
        "trade_count": metrics["trade_count"],
        "no_trade_count": max(feature_table.height - (events.height if not events.is_empty() else 0), 0),
        "win_rate": metrics["win_rate"],
        "average_win": metrics["average_win"],
        "average_loss": metrics["average_loss"],
        "expectancy": metrics["expectancy"],
        "profit_factor": metrics["profit_factor"],
        "max_drawdown": metrics["max_drawdown"],
        "average_mae": metrics["average_mae"],
        "average_mfe": metrics["average_mfe"],
        "average_holding_time": metrics["average_holding_time"],
        "best_baseline_expectancy": baseline_expectancy,
        "uplift_vs_best_baseline": _delta(metrics["expectancy"], baseline_expectancy),
        "placebo_expectancy": placebo_expectancy,
        "uplift_vs_placebo": _delta(metrics["expectancy"], placebo_expectancy),
        "p_value": p_value,
        "cost_multiplier": cost_multiplier,
        "sample_size_warning": metrics["trade_count"] < MIN_SAMPLE_SIZE,
        "walk_forward_pass": None,
        "permutation_pass": None,
        "matched_placebo_pass": None,
        "notes": "",
    }


def _event_stratified_rows(
    feature_table: pl.DataFrame,
    events: pl.DataFrame,
    config: ResearchConfig,
) -> list[dict[str, Any]]:
    rows = []
    for key in ["sigma_zone", "wall_score_bucket", "dte_bucket", "vol_regime"]:
        if events.is_empty() or key not in events.columns:
            continue
        for value in sorted(set(str(item or "unknown") for item in events.get_column(key).to_list())):
            subset = events.filter(pl.col(key).cast(pl.Utf8).fill_null("unknown") == value)
            row = _metrics_row(
                feature_table,
                subset,
                config,
                evaluation_type="event_stratified",
                subgroup_type=key,
                subgroup=value,
            )
            rows.append(row)
    return rows


def _expiry_split_rows(
    feature_table: pl.DataFrame,
    events: pl.DataFrame,
    config: ResearchConfig,
) -> list[dict[str, Any]]:
    if events.is_empty() or "dte" not in events.columns:
        return []
    rows = []
    for label, subset in [
        ("expiry_day", events.filter(pl.col("dte").fill_null(9999) <= 1)),
        ("non_expiry_day", events.filter(pl.col("dte").fill_null(9999) > 1)),
    ]:
        rows.append(
            _metrics_row(
                feature_table,
                subset,
                config,
                evaluation_type="expiry_split",
                subgroup_type="expiry_day",
                subgroup=label,
            )
        )
    return rows


def _cost_stress_rows(
    feature_table: pl.DataFrame,
    events: pl.DataFrame,
    config: ResearchConfig,
) -> list[dict[str, Any]]:
    rows = []
    for multiplier in [1, 2, 3, 5]:
        stressed = _cost_config(config, multiplier)
        row = _metrics_row(
            feature_table,
            events,
            stressed,
            evaluation_type="cost_stress",
            subgroup_type="cost_multiplier",
            subgroup=f"{multiplier}x",
            cost_multiplier=multiplier,
        )
        rows.append(row)
    return rows


def _walk_forward_rows(
    feature_table: pl.DataFrame,
    events: pl.DataFrame,
    config: ResearchConfig,
) -> list[dict[str, Any]]:
    if feature_table.is_empty() or events.is_empty():
        return []
    prices = feature_table.sort("timestamp").to_dicts()
    meta = events.row(0, named=True)
    rows = []
    start = 0
    split_id = 1
    while start + config.walk_forward_train_bars < len(prices):
        train_end = start + config.walk_forward_train_bars - 1
        test_start = train_end + 1
        test_end = min(test_start + config.walk_forward_test_bars - 1, len(prices) - 1)
        test_start_ts = prices[test_start]["timestamp"]
        test_end_ts = prices[test_end]["timestamp"]
        test_events = events.filter(
            (pl.col("event_timestamp") >= test_start_ts)
            & (pl.col("event_timestamp") <= test_end_ts)
        )
        row = _metrics_row(
            feature_table,
            test_events,
            config,
            evaluation_type="walk_forward_split",
            subgroup_type="walk_forward",
            subgroup="test",
            split_id=split_id,
        )
        for key in ["stage", "scenario", "scenario_family", "edge_type"]:
            if not row.get(key):
                row[key] = meta.get(key)
        row["walk_forward_pass"] = (
            int(row["trade_count"] or 0) >= MIN_SAMPLE_SIZE
            and _none_safe(row.get("expectancy")) > 0
            and _none_safe(row.get("uplift_vs_best_baseline")) > 0
        )
        rows.append(row)
        split_id += 1
        start = test_end + 1
    return rows


def _permutation_row(
    feature_table: pl.DataFrame,
    all_events: pl.DataFrame,
    selected_events: pl.DataFrame,
    config: ResearchConfig,
    *,
    iterations: int,
) -> dict[str, Any]:
    observed = _metrics_row(feature_table, selected_events, config, evaluation_type="permutation_test")
    event_count = selected_events.height if not selected_events.is_empty() else 0
    if event_count == 0:
        observed.update({"p_value": None, "placebo_expectancy": None, "permutation_pass": False})
        return observed
    scenario = str(observed.get("scenario") or "")
    stable_seed_offset = sum((idx + 1) * ord(char) for idx, char in enumerate(scenario)) % 10_000
    rng = random.Random(config.random_seed + stable_seed_offset)
    universe = _price_universe_events(feature_table, all_events)
    if universe.is_empty():
        observed.update({"p_value": None, "placebo_expectancy": None, "permutation_pass": False})
        return observed
    placebo_values = []
    for _ in range(iterations):
        sampled = _sample_events(universe, event_count, rng)
        placebo_trades = _run_lab_event_backtest(feature_table, sampled, config=config)
        placebo_values.append(_trade_metrics(placebo_trades.to_dicts())["expectancy"] or 0.0)
    observed_expectancy = _none_safe(observed.get("expectancy"))
    placebo_mean = sum(placebo_values) / len(placebo_values) if placebo_values else None
    p_value = (
        sum(1 for value in placebo_values if value >= observed_expectancy) / len(placebo_values)
        if placebo_values
        else None
    )
    observed.update(
        {
            "placebo_expectancy": placebo_mean,
            "uplift_vs_placebo": _delta(observed.get("expectancy"), placebo_mean),
            "p_value": p_value,
            "permutation_pass": p_value is not None and p_value <= 0.05,
        }
    )
    return observed


def _matched_state_placebo_row(
    feature_table: pl.DataFrame,
    all_events: pl.DataFrame,
    selected_events: pl.DataFrame,
    config: ResearchConfig,
) -> dict[str, Any]:
    observed = _metrics_row(feature_table, selected_events, config, evaluation_type="matched_state_placebo")
    if selected_events.is_empty():
        observed.update({"placebo_expectancy": None, "matched_placebo_pass": False})
        return observed
    universe = _price_universe_events(feature_table, all_events)
    matched = _matched_placebo_events(selected_events, universe, config=config)
    matched_trades = _run_lab_event_backtest(feature_table, matched, config=config)
    placebo = _trade_metrics(matched_trades.to_dicts())
    placebo_expectancy = placebo["expectancy"]
    observed.update(
        {
            "placebo_expectancy": placebo_expectancy,
            "uplift_vs_placebo": _delta(observed.get("expectancy"), placebo_expectancy),
            "matched_placebo_pass": _delta(observed.get("expectancy"), placebo_expectancy) is not None
            and _delta(observed.get("expectancy"), placebo_expectancy) > 0,
        }
    )
    return observed


def _price_universe_events(feature_table: pl.DataFrame, all_events: pl.DataFrame) -> pl.DataFrame:
    if feature_table.is_empty():
        return _empty_lab_events()
    directions = [1, -1]
    rows = []
    for price in feature_table.to_dicts():
        for direction in directions:
            rows.append(
                _event_from_price_row(
                    price,
                    stage="PLACEBO",
                    scenario="MATCHED_RANDOM_PLACEBO",
                    family="placebo",
                    edge_type="placebo",
                    direction=direction,
                    reason="matched_state_control",
                )
            )
    if all_events.is_empty():
        return pl.DataFrame(rows, infer_schema_length=None) if rows else _empty_lab_events()
    return pl.DataFrame(rows, infer_schema_length=None)


def _matched_placebo_events(
    selected_events: pl.DataFrame,
    universe: pl.DataFrame,
    *,
    config: ResearchConfig,
) -> pl.DataFrame:
    rng = random.Random(config.random_seed + 31)
    universe_rows = universe.to_dicts()
    selected_timestamps = {row.get("event_timestamp") for row in selected_events.to_dicts()}
    rows = []
    for row in selected_events.to_dicts():
        state = _state_key(row)
        direction = int(row.get("direction") or 0)
        candidates = [
            item
            for item in universe_rows
            if item.get("event_timestamp") not in selected_timestamps
            and int(item.get("direction") or 0) == direction
            and _state_key(item) == state
        ]
        if not candidates:
            candidates = [
                item
                for item in universe_rows
                if item.get("event_timestamp") not in selected_timestamps
                and int(item.get("direction") or 0) == direction
            ]
        if candidates:
            chosen = rng.choice(candidates)
            rows.append(
                {
                    **chosen,
                    "stage": row.get("stage"),
                    "scenario": row.get("scenario"),
                    "scenario_family": row.get("scenario_family"),
                    "edge_type": row.get("edge_type"),
                }
            )
    return pl.DataFrame(rows, infer_schema_length=None) if rows else _empty_lab_events()


def _sample_events(universe: pl.DataFrame, count: int, rng: random.Random) -> pl.DataFrame:
    rows = universe.to_dicts()
    if not rows:
        return _empty_lab_events()
    if count <= len(rows):
        sample = rng.sample(rows, count)
    else:
        sample = [rng.choice(rows) for _ in range(count)]
    return pl.DataFrame(sample, infer_schema_length=None)


def _trade_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    pnl = [float(row.get("net_pnl_points") or 0.0) for row in rows]
    wins = [value for value in pnl if value > 0]
    losses = [value for value in pnl if value < 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    equity = []
    running = 0.0
    for value in pnl:
        running += value
        equity.append(running)
    return {
        "trade_count": len(rows),
        "win_rate": len(wins) / len(rows) if rows else None,
        "average_win": sum(wins) / len(wins) if wins else 0.0,
        "average_loss": sum(losses) / len(losses) if losses else 0.0,
        "expectancy": sum(pnl) / len(pnl) if pnl else None,
        "profit_factor": gross_win / gross_loss if gross_loss > 0 else None,
        "max_drawdown": _max_drawdown(equity),
        "average_mae": _average([float(row.get("mae_points") or 0.0) for row in rows]),
        "average_mfe": _average([float(row.get("mfe_points") or 0.0) for row in rows]),
        "average_holding_time": _average([float(row.get("time_in_trade_bars") or 0.0) for row in rows]),
    }


def _event_from_price_row(
    row: dict[str, Any],
    *,
    stage: str,
    scenario: str,
    family: str,
    edge_type: str,
    direction: int,
    reason: str,
    position_size: float = 1.0,
) -> dict[str, Any]:
    close = _float(row.get("close"))
    session_open = _float(row.get("session_open"))
    return {
        "event_timestamp": row.get("timestamp"),
        "stage": stage,
        "scenario": scenario,
        "scenario_family": family,
        "edge_type": edge_type,
        "direction": direction,
        "position_size": position_size,
        "reason": reason,
        "close": close,
        "sigma_position": row.get("sigma_position"),
        "sigma_zone": row.get("sigma_zone") or _sigma_zone(row.get("sigma_position")),
        "vol_regime": row.get("vol_regime"),
        "wall_level": row.get("wall_level"),
        "wall_score": row.get("wall_score"),
        "wall_score_bucket": row.get("wall_score_bucket"),
        "distance_to_nearest_wall": row.get("distance_to_nearest_wall"),
        "freshness_weight": row.get("freshness_weight"),
        "dte_weight": row.get("dte_weight"),
        "dte": row.get("dte"),
        "dte_bucket": row.get("dte_bucket"),
        "wall_side": row.get("wall_side"),
        "basis": row.get("basis"),
        "open_side": _open_side(close, session_open),
        "active_transcript_rule_tags": "",
        "uses_unapproved_guru_features": False,
        "research_only": True,
    }


def _event_from_signal_row(
    row: dict[str, Any],
    *,
    stage: str,
    scenario: str,
    family: str,
    edge_type: str,
    direction: int,
    reason: str,
) -> dict[str, Any]:
    return {
        "event_timestamp": row.get("event_timestamp"),
        "stage": stage,
        "scenario": scenario,
        "scenario_family": family,
        "edge_type": edge_type,
        "direction": direction,
        "position_size": 1.0,
        "reason": reason,
        "base_signal": row.get("signal"),
        "close": row.get("close"),
        "sigma_position": row.get("sigma_position"),
        "sigma_zone": row.get("sigma_zone"),
        "vol_regime": row.get("vol_regime"),
        "wall_level": row.get("wall_level"),
        "wall_score": row.get("wall_score"),
        "wall_score_bucket": row.get("wall_score_bucket"),
        "distance_to_nearest_wall": row.get("distance_to_nearest_wall"),
        "freshness_weight": row.get("freshness_weight"),
        "dte_weight": row.get("dte_weight"),
        "dte": row.get("dte"),
        "dte_bucket": row.get("dte_bucket"),
        "wall_side": row.get("wall_side"),
        "open_side": row.get("open_side"),
        "active_transcript_rule_tags": "",
        "uses_unapproved_guru_features": False,
        "research_only": True,
    }


def _price_by_timestamp(feature_table: pl.DataFrame) -> dict[Any, dict[str, Any]]:
    if feature_table.is_empty():
        return {}
    return {row.get("timestamp"): row for row in feature_table.to_dicts()}


def _conditioned_by_key(conditioned_events: pl.DataFrame | None) -> dict[str, dict[str, Any]]:
    if conditioned_events is None or conditioned_events.is_empty():
        return {}
    return {_event_key(row): row for row in conditioned_events.to_dicts()}


def _event_key(row: dict[str, Any]) -> str:
    return f"{row.get('event_timestamp')}::{row.get('base_signal') or row.get('signal') or ''}"


def _guru_context_tags(records: pl.DataFrame | None) -> set[str]:
    if records is None or records.is_empty():
        return set()
    rows = records.to_dicts()
    result = set()
    for row in rows:
        decision = str(row.get("suggested_decision") or row.get("reviewer_final_decision") or "")
        if decision not in CONTEXT_FILTER_MAP_DECISIONS:
            continue
        tag = str(row.get("rule_tag") or "")
        if tag:
            result.add(tag)
    return result


def _approved_trade_rule_tags(records: pl.DataFrame) -> set[str]:
    result = set()
    for row in records.to_dicts():
        decision = str(row.get("reviewer_final_decision") or row.get("reviewer_decision") or "").upper()
        if decision not in APPROVED_TRADE_RULE_DECISIONS:
            continue
        tag = str(row.get("rule_tag") or "")
        if tag:
            result.add(tag)
    return result


def _best_baseline_expectancy_for_events(
    feature_table: pl.DataFrame,
    events: pl.DataFrame,
    config: ResearchConfig,
) -> float | None:
    if events.is_empty():
        return None
    # Avoid recursive baseline comparison for baseline rows.
    stage = str(events.row(0, named=True).get("stage") or "")
    if stage.startswith("BASELINE"):
        return None
    baselines = [
        _gold_trend_events(feature_table, lookback=4, scenario="GOLD_TREND_4B"),
        _iv_range_reentry_events(feature_table),
    ]
    values = []
    for baseline in baselines:
        if baseline.is_empty():
            continue
        trades = _run_lab_event_backtest(feature_table, baseline, config=config)
        values.append(_trade_metrics(trades.to_dicts())["expectancy"])
    values = [value for value in values if value is not None]
    return max(values) if values else None


def _best_non_guru_expectancy(metrics: pl.DataFrame) -> float:
    if metrics.is_empty():
        return 0.0
    rows = metrics.filter(
        (pl.col("evaluation_type") == "full_sample")
        & ~pl.col("stage").str.starts_with("D_")
        & ~pl.col("stage").str.starts_with("E_")
    ).to_dicts()
    return max((_none_safe(row.get("expectancy")) for row in rows), default=0.0)


def _stage_rows(metrics: pl.DataFrame, stage: str) -> pl.DataFrame:
    if metrics.is_empty():
        return metrics
    return metrics.filter(pl.col("stage") == stage)


def _best_full_row(rows: pl.DataFrame) -> dict[str, Any]:
    if rows.is_empty():
        return {}
    full_rows = rows.filter(pl.col("evaluation_type") == "full_sample").to_dicts()
    if not full_rows:
        return {}
    return max(full_rows, key=lambda row: _none_safe(row.get("expectancy")))


def _walk_forward_pass(rows: pl.DataFrame) -> bool:
    if rows.is_empty():
        return False
    wf = rows.filter(pl.col("evaluation_type") == "walk_forward_split")
    if wf.is_empty():
        return False
    return any(bool(row.get("walk_forward_pass")) for row in wf.to_dicts())


def _test_pass(rows: pl.DataFrame, evaluation_type: str) -> bool:
    if rows.is_empty():
        return False
    subset = rows.filter(pl.col("evaluation_type") == evaluation_type)
    if subset.is_empty():
        return False
    if evaluation_type == "permutation_test":
        return any(bool(row.get("permutation_pass")) for row in subset.to_dicts())
    if evaluation_type == "matched_state_placebo":
        return any(bool(row.get("matched_placebo_pass")) for row in subset.to_dicts())
    return False


def _walk_forward_summary(metrics: pl.DataFrame) -> pl.DataFrame:
    if metrics.is_empty():
        return metrics
    rows = []
    for scenario in sorted(set(metrics.get_column("scenario").to_list())):
        subset = metrics.filter((pl.col("scenario") == scenario) & (pl.col("evaluation_type") == "walk_forward_split"))
        if subset.is_empty():
            continue
        pass_count = sum(1 for row in subset.to_dicts() if bool(row.get("walk_forward_pass")))
        rows.append(
            {
                "stage": subset.row(0, named=True).get("stage"),
                "scenario": scenario,
                "scenario_family": subset.row(0, named=True).get("scenario_family"),
                "edge_type": subset.row(0, named=True).get("edge_type"),
                "evaluation_type": "walk_forward_summary",
                "event_count": int(subset.get_column("event_count").sum()),
                "trade_count": int(subset.get_column("trade_count").sum()),
                "expectancy": float(subset.get_column("expectancy").drop_nulls().mean())
                if not subset.get_column("expectancy").drop_nulls().is_empty()
                else None,
                "profit_factor": float(subset.get_column("profit_factor").drop_nulls().mean())
                if not subset.get_column("profit_factor").drop_nulls().is_empty()
                else None,
                "walk_forward_pass": pass_count > 0,
                "pass_count": pass_count,
                "split_count": subset.height,
            }
        )
    return pl.DataFrame(rows, infer_schema_length=None) if rows else _empty_metrics()


def _report_columns(frame: pl.DataFrame) -> pl.DataFrame:
    if frame.is_empty():
        return frame
    columns = [
        "stage",
        "scenario",
        "scenario_family",
        "edge_type",
        "evaluation_type",
        "event_count",
        "trade_count",
        "expectancy",
        "profit_factor",
        "best_baseline_expectancy",
        "uplift_vs_best_baseline",
        "placebo_expectancy",
        "uplift_vs_placebo",
        "p_value",
        "sample_size_warning",
        "walk_forward_pass",
        "permutation_pass",
        "matched_placebo_pass",
    ]
    return frame.select([column for column in columns if column in frame.columns])


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
    position_size: float,
) -> tuple[float, float]:
    lows = [float(row["low"]) for row in path]
    highs = [float(row["high"]) for row in path]
    if direction > 0:
        return (
            min(low - entry_price for low in lows) * position_size,
            max(high - entry_price for high in highs) * position_size,
        )
    return (
        min(entry_price - high for high in highs) * position_size,
        max(entry_price - low for low in lows) * position_size,
    )


def _state_key(row: dict[str, Any]) -> str:
    return "|".join(
        [
            str(row.get("sigma_zone") or "unknown"),
            str(row.get("wall_score_bucket") or "unknown"),
            str(row.get("open_side") or "unknown"),
            str(row.get("vol_regime") or "unknown"),
        ]
    )


def _open_side(close: float | None, session_open: float | None) -> str:
    if close is None or session_open is None:
        return "unknown"
    return "ABOVE_OPEN" if close >= session_open else "BELOW_OPEN"


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


def _split_tags(value: Any) -> list[str]:
    if value is None:
        return []
    return [tag for tag in str(value).split("|") if tag]


def _max_drawdown(equity: list[float]) -> float:
    peak = 0.0
    drawdown = 0.0
    for value in equity:
        peak = max(peak, value)
        drawdown = min(drawdown, value - peak)
    return drawdown


def _average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _median(values: list[float]) -> float:
    clean = sorted(value for value in values if value is not None)
    if not clean:
        return 0.0
    middle = len(clean) // 2
    if len(clean) % 2:
        return clean[middle]
    return (clean[middle - 1] + clean[middle]) / 2.0


def _delta(left: Any, right: Any) -> float | None:
    if left is None or right is None:
        return None
    return _none_safe(left) - _none_safe(right)


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


def _bar_svg(title: str, labels: list[str], values: list[float]) -> str:
    width, height = 900, 340
    minimum = min(values + [0.0])
    maximum = max(values + [0.0])
    span = max(maximum - minimum, 1.0)
    count = max(len(values), 1)
    bar_width = max((width - 110) / count * 0.72, 4)
    zero_y = height - 55 - ((0.0 - minimum) / span) * (height - 110)
    body = [f'<line x1="45" x2="{width - 40}" y1="{zero_y:.1f}" y2="{zero_y:.1f}" stroke="#94a3b8" />']
    for index, value in enumerate(values):
        x = 55 + index * ((width - 110) / count)
        y = height - 55 - ((value - minimum) / span) * (height - 110)
        color = "#0f766e" if value >= 0 else "#b91c1c"
        body.append(
            f'<rect x="{x:.1f}" y="{min(y, zero_y):.1f}" width="{bar_width:.1f}" '
            f'height="{max(abs(zero_y - y), 1.0):.1f}" fill="{color}" />'
        )
        body.append(
            f'<text x="{x:.1f}" y="{height - 18}" font-size="9" font-family="Arial" '
            f'transform="rotate(35 {x:.1f},{height - 18})">{labels[index]}</text>'
        )
    return _svg(title, "\n".join(body))


def _svg(title: str, body: str) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="340" '
        'viewBox="0 0 900 340">'
        '<rect width="900" height="340" fill="#ffffff" />'
        f'<text x="40" y="30" font-size="18" font-family="Arial">{title}</text>'
        f"{body}</svg>"
    )


def _empty_lab_events() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "event_timestamp": pl.Datetime(time_zone="UTC"),
            "stage": pl.String,
            "scenario": pl.String,
            "scenario_family": pl.String,
            "edge_type": pl.String,
            "direction": pl.Int64,
            "position_size": pl.Float64,
            "reason": pl.String,
            "sigma_zone": pl.String,
            "wall_score_bucket": pl.String,
            "dte_bucket": pl.String,
            "vol_regime": pl.String,
        }
    )


def _empty_trades() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "event_timestamp": pl.Datetime(time_zone="UTC"),
            "stage": pl.String,
            "scenario": pl.String,
            "net_pnl_points": pl.Float64,
            "mae_points": pl.Float64,
            "mfe_points": pl.Float64,
            "time_in_trade_bars": pl.Int64,
        }
    )


def _empty_metrics() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "stage": pl.String,
            "scenario": pl.String,
            "scenario_family": pl.String,
            "edge_type": pl.String,
            "evaluation_type": pl.String,
            "split_id": pl.Int64,
            "subgroup_type": pl.String,
            "subgroup": pl.String,
            "event_count": pl.Int64,
            "trade_count": pl.Int64,
            "no_trade_count": pl.Int64,
            "win_rate": pl.Float64,
            "average_win": pl.Float64,
            "average_loss": pl.Float64,
            "expectancy": pl.Float64,
            "profit_factor": pl.Float64,
            "max_drawdown": pl.Float64,
            "average_mae": pl.Float64,
            "average_mfe": pl.Float64,
            "average_holding_time": pl.Float64,
            "best_baseline_expectancy": pl.Float64,
            "uplift_vs_best_baseline": pl.Float64,
            "placebo_expectancy": pl.Float64,
            "uplift_vs_placebo": pl.Float64,
            "p_value": pl.Float64,
            "cost_multiplier": pl.Int64,
            "sample_size_warning": pl.Boolean,
            "walk_forward_pass": pl.Boolean,
            "permutation_pass": pl.Boolean,
            "matched_placebo_pass": pl.Boolean,
            "notes": pl.String,
        }
    )
