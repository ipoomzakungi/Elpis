"""Research decision gates for XAU Vol-OI money-readiness.

This module reads generated research outputs and converts them into explicit
gate decisions, a 0-100 readiness score, ranked next tasks, and a Markdown
money-readiness report. It is research-only and never enables live, paper,
broker, or order workflows.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl


MIN_VALIDATION_DATES = 60
SERIOUS_VALIDATION_DATES = 120
ROBUST_VALIDATION_DATES = 250
MIN_SAMPLE_SIZE = 20
MAX_ACCEPTABLE_FALSE_BLOCK_RATE = 0.45
READY_LABELS = {
    "READY_FOR_SHADOW_MODE",
    "READY_FOR_PAPER_TRADING",
    "READY_FOR_SMALL_CAPITAL_TEST",
}


@dataclass(frozen=True)
class ResearchDecisionGateResult:
    """Decision-gate outputs and summary state."""

    gate_report: pl.DataFrame
    scorecard: pl.DataFrame
    next_tasks: pl.DataFrame
    final_label: str
    readiness_score: float
    passed_gates: tuple[str, ...]
    failed_gates: tuple[str, ...]
    blocking_issues: tuple[str, ...]


def run_research_decision_gate(
    *,
    output_dir: str | Path,
    charts_dir: str | Path | None = None,
    inputs: dict[str, pl.DataFrame | str] | None = None,
    min_validation_dates: int = MIN_VALIDATION_DATES,
) -> ResearchDecisionGateResult:
    """Read generated outputs, evaluate gates, and write decision artifacts."""

    output_root = Path(output_dir)
    chart_root = Path(charts_dir) if charts_dir is not None else output_root / "charts"
    output_root.mkdir(parents=True, exist_ok=True)
    chart_root.mkdir(parents=True, exist_ok=True)

    loaded = inputs or load_decision_gate_inputs(output_root)
    result = evaluate_research_decision_gates(
        loaded,
        min_validation_dates=min_validation_dates,
    )
    result.gate_report.write_csv(output_root / "research_decision_gate.csv")
    result.scorecard.write_csv(output_root / "research_readiness_scorecard.csv")
    result.next_tasks.write_csv(output_root / "next_research_tasks_ranked.csv")
    (output_root / "money_readiness_report.md").write_text(
        money_readiness_markdown(result),
        encoding="utf-8",
    )
    write_research_gate_status_svg(chart_root / "research_gate_status.svg", result.gate_report)
    return result


def load_decision_gate_inputs(output_dir: str | Path) -> dict[str, pl.DataFrame | str]:
    """Load all known optional outputs if they exist."""

    root = Path(output_dir)
    csv_names = [
        "gold_baseline_metrics",
        "guru_filter_value_report",
        "guru_market_map_validation",
        "guru_monte_carlo_validation",
        "guru_logic_classification_summary",
        "transcript_rule_uplift",
        "transcript_walk_forward_uplift",
        "score_decile_performance",
        "score_threshold_performance",
        "signal_kill_list",
        "backtest_summary",
        "market_data_coverage_manifest",
        "transcript_market_coverage_alignment",
        "source_gap_audit",
        "no_trade_filter_avoided_pnl",
        "filter_avoided_pnl_report",
        "market_map_precision_report",
        "expiry_pin_test_report",
        "cme_history_coverage_report",
        "cme_validation_grade_days",
        "cme_validation_grade_uplift",
        "cme_data_requirements_checklist",
        "basis_adjustment_precision_report",
    ]
    md_names = [
        "gold_ablation_report",
        "score_calibration_report",
        "proof_pack",
        "guru_monte_carlo_report",
        "leakage_audit_report",
    ]
    loaded: dict[str, pl.DataFrame | str] = {}
    for name in csv_names:
        path = root / f"{name}.csv"
        if path.exists():
            try:
                loaded[name] = pl.read_csv(path, infer_schema_length=1000)
            except Exception as exc:  # pragma: no cover - corrupted local artifact
                loaded[name] = pl.DataFrame({"load_error": [str(exc)]})
    for name in md_names:
        path = root / f"{name}.md"
        if path.exists():
            loaded[name] = path.read_text(encoding="utf-8", errors="replace")
    return loaded


def evaluate_research_decision_gates(
    inputs: dict[str, pl.DataFrame | str],
    *,
    min_validation_dates: int = MIN_VALIDATION_DATES,
) -> ResearchDecisionGateResult:
    """Evaluate all decision gates from loaded output artifacts."""

    gate_rows = [
        _data_coverage_gate(inputs, min_validation_dates=min_validation_dates),
        _baseline_gate(inputs),
        _cme_uplift_gate(inputs),
        _guru_context_gate(inputs),
        _guru_filter_gate(inputs),
        _market_map_gate(inputs),
        _trade_rule_gate(inputs),
        _robustness_gate(inputs),
    ]
    money_gate = _money_readiness_gate(gate_rows)
    gate_rows.append(money_gate)
    gate_report = pl.DataFrame(gate_rows, infer_schema_length=None)
    scorecard = _build_scorecard(gate_rows, inputs)
    readiness_score = min(100.0, max(0.0, sum(float(row["points_awarded"]) for row in scorecard.to_dicts())))
    final_label = _final_readiness_label(gate_rows)
    passed = tuple(row["gate_name"] for row in gate_rows if row["status"] == "PASS")
    failed = tuple(row["gate_name"] for row in gate_rows if row["status"] != "PASS")
    blocking = tuple(
        issue
        for row in gate_rows
        if row["status"] != "PASS"
        for issue in str(row.get("blocking_issues") or "").split("; ")
        if issue
    )
    tasks = build_next_research_tasks(gate_rows, final_label)
    return ResearchDecisionGateResult(
        gate_report=gate_report,
        scorecard=scorecard,
        next_tasks=tasks,
        final_label=final_label,
        readiness_score=readiness_score,
        passed_gates=passed,
        failed_gates=failed,
        blocking_issues=blocking,
    )


def build_next_research_tasks(gate_rows: list[dict[str, Any]], final_label: str) -> pl.DataFrame:
    """Rank next tasks based on failed gates and current candidate state."""

    failed = {row["gate_name"] for row in gate_rows if row["status"] != "PASS"}
    task_specs = [
        (
            "Import more CME/QuikStrike history by strike/expiry",
            "DATA",
            "DATA_COVERAGE_GATE" in failed,
            "Current CME validation window is too small for proof.",
            "CRITICAL",
            "Blocking for CME uplift, market-map, and money-readiness gates.",
            "Build/import a longer local CME options panel with OI, OI change, volume, IV, futures, spot/proxy, and basis.",
        ),
        (
            "Resolve duplicate/conflicting CME snapshots",
            "DATA",
            "DATA_COVERAGE_GATE" in failed,
            "Duplicate snapshot conflicts block validation-grade daily panels.",
            "HIGH",
            "Blocking for clean daily wall maps.",
            "Review cme_history_duplicate_conflict_report.csv and define deterministic latest/as-of snapshot policy.",
        ),
        (
            "Improve no-trade filter avoided-PnL calculation",
            "VALIDATION",
            True,
            "The filter candidate is promising but needs purged walk-forward and stricter controls.",
            "HIGH",
            "Required before treating filters as validated.",
            "Add purged walk-forward avoided-PnL and compare NO_TRADE filters to matched random filters by event day and expiry bucket.",
        ),
        (
            "Improve market-map precision testing",
            "VALIDATION",
            "MARKET_MAP_GATE" in failed,
            "Market-map sample size is too small and random-zone controls are not beaten.",
            "HIGH",
            "Blocking for MAP_USEFUL_NOT_TRADABLE validation.",
            "Increase wall-event sample and run matched random strike, random-level, expiry-bucket, and event-day controls.",
        ),
        (
            "Compare basis-adjusted vs non-basis-adjusted OI walls",
            "FEATURE",
            "MARKET_MAP_GATE" in failed or "DATA_COVERAGE_GATE" in failed,
            "Basis adjustment is central to the thesis but needs direct precision comparison.",
            "HIGH",
            "Required for basis-adjustment proof.",
            "Add side-by-side map precision report for raw futures strikes vs spot-equivalent strikes.",
        ),
        (
            "Add macro event calendar filters",
            "DATA",
            "DATA_COVERAGE_GATE" in failed,
            "Event-day controls are incomplete when CPI/NFP/FOMC tags are missing.",
            "HIGH",
            "Blocks event-day controls and news-disable validation.",
            "Import local CPI/NFP/FOMC calendar and join by session date before proof-pack evaluation.",
        ),
        (
            "Add IV skew and call-put IV spread features",
            "FEATURE",
            True,
            "Current IV context is incomplete for wall-quality and volatility-regime tests.",
            "MEDIUM",
            "Useful for CME feature refinement after data coverage improves.",
            "Normalize call/put IV by strike-expiry and add skew, smile, and call-put spread regime columns.",
        ),
        (
            "Add purged walk-forward validation",
            "VALIDATION",
            "CME_UPLIFT_GATE" in failed or "GURU_FILTER_GATE" in failed,
            "Current promising effects do not pass strict out-of-sample gates.",
            "HIGH",
            "Required before paper/shadow readiness.",
            "Implement purged and embargoed walk-forward splits for CME and filter proof-pack outputs.",
        ),
        (
            "Add White Reality Check or SPA-style multiple-testing correction",
            "VALIDATION",
            "ROBUSTNESS_GATE" in failed,
            "Multiple signal families and thresholds can create false discovery.",
            "MEDIUM",
            "Required before any edge claim across many tested rules.",
            "Add bootstrap multiple-testing correction over signal families, score thresholds, and rule tags.",
        ),
        (
            "Produce shadow-mode checklist only after validation passes",
            "RISK",
            final_label in READY_LABELS,
            "Shadow mode should start only after gates support it.",
            "LOW",
            "Not currently allowed unless readiness label changes.",
            "Generate a non-execution observation checklist after DATA, CME_UPLIFT, ROBUSTNESS, and filter/map gates pass.",
        ),
    ]
    active = [task for task in task_specs if task[2]]
    rows = []
    for rank, task in enumerate(active, start=1):
        rows.append(
            {
                "rank": rank,
                "task_name": task[0],
                "category": task[1],
                "why_it_matters": task[3],
                "expected_impact": task[4],
                "blocking_status": task[5],
                "codex_prompt_hint": task[6],
            }
        )
    return pl.DataFrame(rows, infer_schema_length=None)


def money_readiness_markdown(result: ResearchDecisionGateResult) -> str:
    """Render the money-readiness report."""

    passed = [row for row in result.gate_report.to_dicts() if row["status"] == "PASS"]
    failed = [row for row in result.gate_report.to_dicts() if row["status"] != "PASS"]
    lines = [
        "# XAU Vol-OI Research Decision Gate",
        "",
        "Research-only report. This is not live trading, paper trading, broker integration, or approval to trade real money.",
        "",
        f"- Final readiness label: `{result.final_label}`",
        f"- Money-readiness score: `{result.readiness_score:.1f}/100`",
        f"- Minimum preliminary complete validation-grade days: `{MIN_VALIDATION_DATES}`",
        f"- Serious validation target: `{SERIOUS_VALIDATION_DATES}`",
        f"- Robust validation target: `{ROBUST_VALIDATION_DATES}`",
        f"- Ready for shadow mode: `{result.final_label in READY_LABELS}`",
        f"- Ready for paper trading: `{result.final_label in {'READY_FOR_PAPER_TRADING', 'READY_FOR_SMALL_CAPITAL_TEST'}}`",
        f"- Ready for real money: `{result.final_label == 'READY_FOR_SMALL_CAPITAL_TEST'}`",
        "",
        "## Passed Gates",
        "",
        *[f"- `{row['gate_name']}`: {row['evidence']}" for row in passed],
        "",
        "## Failed Gates",
        "",
        *[f"- `{row['gate_name']}`: {row['blocking_issues']}" for row in failed],
        "",
        "## Gate Table",
        "",
        _frame_markdown(result.gate_report),
        "",
        "## Readiness Scorecard",
        "",
        _frame_markdown(result.scorecard),
        "",
        "## Ranked Next Research Tasks",
        "",
        _frame_markdown(result.next_tasks),
        "",
        "## Final Decision",
        "",
        _final_decision_text(result),
    ]
    return "\n".join(lines)


def write_research_gate_status_svg(path: str | Path, gate_report: pl.DataFrame) -> None:
    """Write a compact SVG showing pass/fail gate status."""

    path = Path(path)
    rows = gate_report.to_dicts() if not gate_report.is_empty() else []
    width = 920
    row_height = 28
    height = 70 + row_height * max(len(rows), 1)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<text x="24" y="34" font-family="Arial" font-size="20" font-weight="700">Research Gate Status</text>',
    ]
    for index, row in enumerate(rows):
        y = 58 + index * row_height
        passed = row.get("status") == "PASS"
        color = "#148a4f" if passed else "#c2410c"
        parts.append(f'<rect x="24" y="{y}" width="18" height="18" rx="3" fill="{color}"/>')
        parts.append(
            f'<text x="52" y="{y + 14}" font-family="Arial" font-size="13" fill="#111827">'
            f"{_escape_xml(row.get('gate_name'))}: {_escape_xml(row.get('status'))}</text>"
        )
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def _data_coverage_gate(
    inputs: dict[str, pl.DataFrame | str],
    *,
    min_validation_dates: int,
) -> dict[str, Any]:
    validation_days = _frame(inputs, "cme_validation_grade_days")
    alignment = _frame(inputs, "transcript_market_coverage_alignment")
    market = _frame(inputs, "market_data_coverage_manifest")
    cme_coverage = _frame(inputs, "cme_history_coverage_report")
    complete_validation_grade_days = _true_count(validation_days, "complete_validation_grade")
    full_validation_dates = _true_count(alignment, "can_run_full_vol_oi_validation")
    complete_cme_days = _true_count(cme_coverage, "complete_validation_day")
    primary_complete_days = (
        complete_validation_grade_days
        if not validation_days.is_empty()
        else max(full_validation_dates, complete_cme_days)
    )
    enough_dates = primary_complete_days >= min_validation_dates
    xau_align = (
        _any_true(validation_days, "has_xau_spot_price")
        or _any_true(alignment, "has_xau_price_data")
        or _any_true(cme_coverage, "has_xau_spot_or_proxy_price")
    )
    futures = _any_true(validation_days, "has_gc_futures_price") or _any_true(
        cme_coverage,
        "has_futures_reference_price",
    )
    basis = (
        _any_true(validation_days, "has_basis")
        or _any_true(alignment, "has_basis_data")
        or _any_true(cme_coverage, "has_basis")
    )
    iv = (
        _any_true(validation_days, "has_option_iv")
        or _any_true(alignment, "has_cme_iv_data")
        or _any_true(cme_coverage, "has_iv_context")
    )
    oi = (
        _any_true(validation_days, "has_option_oi_by_strike")
        or _any_true(alignment, "has_cme_options_oi_data")
        or _any_true(cme_coverage, "has_cme_options_oi")
    )
    oi_change_volume = (
        _any_true(validation_days, "has_option_oi_change")
        or _any_true(validation_days, "has_option_volume")
        or
        _any_true(cme_coverage, "has_oi_change")
        or _any_true(cme_coverage, "has_intraday_volume")
        or _market_has_any(market, ["oi_change", "volume"])
    )
    conditions = {
        "enough_cme_validation_dates": enough_dates,
        "xau_price_aligns_with_cme": xau_align,
        "gc_futures_price_exists": futures,
        "basis_data_exists": basis,
        "iv_data_exists": iv,
        "oi_by_strike_expiry_exists": oi,
        "oi_change_or_intraday_volume_exists": oi_change_volume,
    }
    return _gate_row(
        "DATA_COVERAGE_GATE",
        conditions,
        20,
        evidence=(
            f"full_validation_dates={full_validation_dates}; "
            f"complete_cme_days={complete_cme_days}; "
            f"complete_validation_grade_days={complete_validation_grade_days}; "
            f"market_files={market.height}"
        ),
    )


def _baseline_gate(inputs: dict[str, pl.DataFrame | str]) -> dict[str, Any]:
    gold = _frame(inputs, "gold_baseline_metrics")
    stages = set(gold.get_column("stage").to_list()) if not gold.is_empty() and "stage" in gold.columns else set()
    scenario_families = (
        set(gold.get_column("scenario_family").to_list())
        if not gold.is_empty() and "scenario_family" in gold.columns
        else set()
    )
    conditions = {
        "simple_gold_baselines_implemented": {
            "BASELINE_TREND",
            "BASELINE_IV_RANGE",
            "BASELINE_WALL_REACTION",
        }.issubset(stages),
        "cme_only_compared_to_price_baseline": (
            "cme_feature_stage" in scenario_families
            and "gold_trend_baseline" in scenario_families
        ),
        "cost_aware_results_exist": _any_equals(gold, "evaluation_type", "cost_stress") or "cost_multiplier" in gold.columns,
    }
    return _gate_row("BASELINE_GATE", conditions, 15, evidence=f"gold_metric_rows={gold.height}")


def _cme_uplift_gate(inputs: dict[str, pl.DataFrame | str]) -> dict[str, Any]:
    validation_uplift = _frame(inputs, "cme_validation_grade_uplift")
    if not validation_uplift.is_empty():
        full = validation_uplift.filter(pl.col("stage") == "FULL_CME_VOL_OI")
        cme_rows = validation_uplift.filter(pl.col("stage").is_in(["CME_OI_ONLY", "CME_IV_ONLY", "FULL_CME_VOL_OI"]))
        conditions = {
            "validation_grade_uplift_rows_exist": not cme_rows.is_empty(),
            "beats_price_baseline_out_of_sample": _any_positive(cme_rows, "uplift_vs_price_only")
            and _any_true(cme_rows, "walk_forward_pass"),
            "walk_forward_passes": _any_true(cme_rows, "walk_forward_pass"),
            "permutation_or_placebo_not_explained": _any_true(cme_rows, "placebo_pass"),
            "sample_size_sufficient": _max_numeric(full, "event_count") >= MIN_SAMPLE_SIZE
            and _any_false(full, "sample_size_warning"),
            "cost_stress_survives": _any_true(cme_rows, "cost_stress_survival"),
        }
        return _gate_row(
            "CME_UPLIFT_GATE",
            conditions,
            20,
            evidence=(
                f"validation_grade_uplift_rows={validation_uplift.height}; "
                f"full_cme_vol_oi_events={_max_numeric(full, 'event_count')}"
            ),
        )
    gold = _frame(inputs, "gold_baseline_metrics")
    cme = gold.filter(pl.col("scenario_family") == "cme_feature_stage") if _has_columns(gold, ["scenario_family"]) else pl.DataFrame()
    full = cme.filter(pl.col("evaluation_type") == "full_sample") if _has_columns(cme, ["evaluation_type"]) else pl.DataFrame()
    wf = cme.filter(pl.col("evaluation_type").str.contains("walk_forward")) if _has_columns(cme, ["evaluation_type"]) else pl.DataFrame()
    conditions = {
        "beats_price_baseline_out_of_sample": (
            _any_positive(wf, "uplift_vs_best_baseline")
            and _any_true(wf, "walk_forward_pass")
        ),
        "walk_forward_passes": _any_true(wf, "walk_forward_pass"),
        "permutation_or_placebo_not_explained": _any_true(cme, "permutation_pass") or _any_true(cme, "matched_placebo_pass"),
        "sample_size_sufficient": _any_false(full, "sample_size_warning") and _max_numeric(full, "trade_count") >= MIN_SAMPLE_SIZE,
    }
    return _gate_row(
        "CME_UPLIFT_GATE",
        conditions,
        20,
        evidence=f"cme_stage_rows={cme.height}; best_full_uplift={_max_numeric(full, 'uplift_vs_best_baseline')}",
    )


def _guru_context_gate(inputs: dict[str, pl.DataFrame | str]) -> dict[str, Any]:
    classification = _frame(inputs, "guru_logic_classification_summary")
    wf = _frame(inputs, "transcript_walk_forward_uplift")
    usable_context = (
        _sum_numeric(classification, "usable_as_context_count")
        + _sum_numeric(classification, "usable_as_market_map_count")
        + _sum_numeric(classification, "usable_as_filter_count")
    )
    no_future = _all_true_or_missing(wf, "no_lookahead")
    conditions = {
        "guru_context_classified": classification.height > 0 and usable_context > 0,
        "no_future_outcomes_used": no_future,
        "context_not_direct_trade_signal": _sum_numeric(classification, "usable_as_trade_rule_count") <= usable_context + 1,
    }
    return _gate_row("GURU_CONTEXT_GATE", conditions, 5, evidence=f"classified_rows={classification.height}; usable_context_count={usable_context}")


def _guru_filter_gate(inputs: dict[str, pl.DataFrame | str]) -> dict[str, Any]:
    filter_report = _frame(inputs, "filter_avoided_pnl_report")
    if filter_report.is_empty():
        filter_report = _frame(inputs, "no_trade_filter_avoided_pnl")
    actual = (
        filter_report.filter(pl.col("control_type") == "actual_no_trade_labels")
        if _has_columns(filter_report, ["control_type"])
        else pl.DataFrame()
    )
    proxy = _frame(inputs, "guru_filter_value_report")
    monte = _frame(inputs, "guru_monte_carlo_validation")
    wf = _frame(inputs, "transcript_walk_forward_uplift")
    conditions = {
        "filters_reduce_bad_trades": (
            _max_numeric(actual, "avoided_losing_trade_count")
            > _max_numeric(actual, "avoided_winning_trade_count")
        ),
        "net_filter_value_positive_after_opportunity_cost": (
            _max_numeric(actual, "net_filter_value") > 0
            and _max_numeric(actual, "avoided_loss_amount") > 0
        ),
        "false_block_rate_acceptable": 0 < _max_numeric(actual, "false_block_rate") <= MAX_ACCEPTABLE_FALSE_BLOCK_RATE,
        "walk_forward_passes": _any_equals(wf, "pass_fail", "PASS"),
        "placebo_passes": _any_true(monte, "monte_carlo_pass") or _max_numeric(actual, "uplift_vs_matched_state_placebo") > 0,
        "not_proxy_only": not actual.is_empty() or proxy.is_empty(),
    }
    return _gate_row(
        "GURU_FILTER_GATE",
        conditions,
        8,
        evidence=(
            f"net_filter_value={_max_numeric(actual, 'net_filter_value')}; "
            f"proxy_rows={proxy.height}; actual_rows={actual.height}"
        ),
        candidate_label="GURU_FILTER_CANDIDATE" if _max_numeric(actual, "net_filter_value") > 0 else "",
    )


def _market_map_gate(inputs: dict[str, pl.DataFrame | str]) -> dict[str, Any]:
    market_map = _frame(inputs, "market_map_precision_report")
    comparisons = (
        market_map.filter(pl.col("row_type") == "comparison")
        if _has_columns(market_map, ["row_type"])
        else pl.DataFrame()
    )
    guru_map = _frame(inputs, "guru_market_map_validation")
    conditions = {
        "walls_beat_random_zones": _any_equals(comparisons, "decision_label", "MAP_USEFUL_NOT_TRADABLE"),
        "basis_adjustment_improves_precision": _has_basis_adjustment_comparison(market_map),
        "sample_size_sufficient": _max_numeric(comparisons, "event_count") >= MIN_SAMPLE_SIZE and _any_false(comparisons, "sample_size_warning"),
        "guru_map_not_approval_only": guru_map.is_empty() or not _any_true(guru_map, "human_approval_required"),
    }
    return _gate_row(
        "MARKET_MAP_GATE",
        conditions,
        7,
        evidence=f"comparison_rows={comparisons.height}; guru_map_rows={guru_map.height}",
        candidate_label="MARKET_MAP_CANDIDATE" if _any_positive(comparisons, "touch_uplift_vs_control") else "",
    )


def _trade_rule_gate(inputs: dict[str, pl.DataFrame | str]) -> dict[str, Any]:
    kills = _frame(inputs, "signal_kill_list")
    classification = _frame(inputs, "guru_logic_classification_summary")
    thresholds = _frame(inputs, "score_threshold_performance")
    trade_candidates = (
        thresholds.filter(pl.col("scenario_type") == "vol_oi_score")
        if _has_columns(thresholds, ["scenario_type"])
        else pl.DataFrame()
    )
    complete_rules = (
        _sum_numeric(classification, "usable_as_trade_rule_count") > 0
        and not _any_true(classification, "human_approval_required")
    )
    passing = [
        row
        for row in trade_candidates.to_dicts()
        if _float(row.get("expectancy")) is not None
        and (_float(row.get("expectancy")) or 0.0) > 0
        and (_float(row.get("profit_factor")) or 0.0) >= 1.2
        and not bool(row.get("sample_size_warning"))
    ]
    conditions = {
        "complete_trade_rules_exist": complete_rules,
        "positive_expectancy_after_costs": bool(passing),
        "profit_factor_above_1_2": bool(passing),
        "max_drawdown_acceptable": bool(passing) and min(_float(row.get("max_drawdown")) or 0.0 for row in passing) > -500,
        "walk_forward_placebo_bootstrap_pass": _any_true(kills, "walk_forward_pass") and _any_true(_frame(inputs, "guru_monte_carlo_validation"), "monte_carlo_pass"),
    }
    return _gate_row(
        "TRADE_RULE_GATE",
        conditions,
        0,
        evidence=f"approved_complete_trade_rules={complete_rules}; passing_threshold_rows={len(passing)}",
    )


def _robustness_gate(inputs: dict[str, pl.DataFrame | str]) -> dict[str, Any]:
    thresholds = _frame(inputs, "score_threshold_performance")
    backtest = _frame(inputs, "backtest_summary")
    score_text = str(inputs.get("score_calibration_report", ""))
    leakage_text = str(inputs.get("leakage_audit_report", ""))
    cme_rows = (
        thresholds.filter(pl.col("scenario_type") == "vol_oi_score")
        if _has_columns(thresholds, ["scenario_type"])
        else pl.DataFrame()
    )
    cost_pass = _cost_stress_survives(cme_rows)
    random_expectancy = _bucket_expectancy(backtest, "RANDOM_BASELINE")
    bollinger_expectancy = _bucket_expectancy(backtest, "BOLLINGER_BASELINE")
    best_vol_oi = _best_directional_expectancy(backtest)
    conditions = {
        "cost_2x_3x_5x_survives": cost_pass,
        "random_baseline_beaten": best_vol_oi is not None and random_expectancy is not None and best_vol_oi > random_expectancy,
        "bollinger_or_sd_baseline_beaten_or_explained": best_vol_oi is not None and bollinger_expectancy is not None and best_vol_oi > bollinger_expectancy,
        "score_not_false_monotonic": "monotonic_fail" not in score_text,
        "no_leakage_audit_failures": _leakage_audit_passes(leakage_text),
    }
    return _gate_row(
        "ROBUSTNESS_GATE",
        conditions,
        15,
        evidence=f"best_vol_oi={best_vol_oi}; random={random_expectancy}; bollinger={bollinger_expectancy}",
    )


def _money_readiness_gate(gate_rows: list[dict[str, Any]]) -> dict[str, Any]:
    status_by_gate = {row["gate_name"]: row["status"] == "PASS" for row in gate_rows}
    conditions = {
        "data_gate_passes": status_by_gate.get("DATA_COVERAGE_GATE", False),
        "cme_uplift_gate_passes": status_by_gate.get("CME_UPLIFT_GATE", False),
        "filter_or_market_or_trade_gate_passes": any(
            [
                status_by_gate.get("GURU_FILTER_GATE", False),
                status_by_gate.get("MARKET_MAP_GATE", False),
                status_by_gate.get("TRADE_RULE_GATE", False),
            ]
        ),
        "robustness_gate_passes": status_by_gate.get("ROBUSTNESS_GATE", False),
        "trade_rule_or_risk_gate_passes": status_by_gate.get("TRADE_RULE_GATE", False),
    }
    return _gate_row("MONEY_READINESS_GATE", conditions, 0, evidence="Real-money readiness requires data, uplift, robustness, and risk gates.")


def _build_scorecard(gate_rows: list[dict[str, Any]], inputs: dict[str, pl.DataFrame | str]) -> pl.DataFrame:
    by_name = {row["gate_name"]: row for row in gate_rows}
    guru_points = min(
        15.0,
        float(by_name["GURU_CONTEXT_GATE"]["score_awarded"])
        + float(by_name["GURU_FILTER_GATE"]["score_awarded"])
        + float(by_name["MARKET_MAP_GATE"]["score_awarded"]),
    )
    risk_points = 4.0 if _frame(inputs, "score_threshold_performance").height > 0 else 0.0
    if by_name["ROBUSTNESS_GATE"]["status"] == "PASS":
        risk_points = 10.0
    reporting_points = 5.0 if by_name["BASELINE_GATE"]["status"] == "PASS" and _frame(inputs, "backtest_summary").height > 0 else 2.0
    rows = [
        _score_row("Data coverage", by_name["DATA_COVERAGE_GATE"]["score_awarded"], 20),
        _score_row("Baseline comparison", by_name["BASELINE_GATE"]["score_awarded"], 15),
        _score_row("CME uplift", by_name["CME_UPLIFT_GATE"]["score_awarded"], 20),
        _score_row("Guru filter/market-map uplift", guru_points, 15),
        _score_row("Robustness / placebo / bootstrap", by_name["ROBUSTNESS_GATE"]["score_awarded"], 15),
        _score_row("Risk and cost realism", risk_points, 10),
        _score_row("Reporting and reproducibility", reporting_points, 5),
    ]
    return pl.DataFrame(rows, infer_schema_length=None)


def _final_readiness_label(gate_rows: list[dict[str, Any]]) -> str:
    by_name = {row["gate_name"]: row for row in gate_rows}
    data_pass = by_name["DATA_COVERAGE_GATE"]["status"] == "PASS"
    cme_pass = by_name["CME_UPLIFT_GATE"]["status"] == "PASS"
    robust_pass = by_name["ROBUSTNESS_GATE"]["status"] == "PASS"
    trade_pass = by_name["TRADE_RULE_GATE"]["status"] == "PASS"
    filter_candidate = by_name["GURU_FILTER_GATE"].get("candidate_label") == "GURU_FILTER_CANDIDATE"
    map_candidate = by_name["MARKET_MAP_GATE"].get("candidate_label") == "MARKET_MAP_CANDIDATE"
    if data_pass and cme_pass and robust_pass and trade_pass and by_name["MONEY_READINESS_GATE"]["status"] == "PASS":
        return "READY_FOR_PAPER_TRADING"
    if not data_pass:
        return "NOT_READY_DATA_INSUFFICIENT"
    if filter_candidate and by_name["GURU_FILTER_GATE"]["status"] != "PASS":
        return "GURU_FILTER_CANDIDATE"
    if map_candidate and by_name["MARKET_MAP_GATE"]["status"] != "PASS":
        return "MARKET_MAP_CANDIDATE"
    if trade_pass:
        return "TRADE_RULE_CANDIDATE"
    if cme_pass:
        return "CME_FEATURES_PROMISING"
    return "RESEARCH_READY_NOT_VALIDATED"


def _gate_row(
    gate_name: str,
    conditions: dict[str, bool],
    max_score: float,
    *,
    evidence: str,
    candidate_label: str = "",
) -> dict[str, Any]:
    passed = all(conditions.values())
    failed_conditions = [name for name, ok in conditions.items() if not ok]
    awarded = max_score if passed else max_score * (sum(conditions.values()) / len(conditions) if conditions else 0.0)
    return {
        "gate_name": gate_name,
        "status": "PASS" if passed else "FAIL",
        "score_awarded": round(awarded, 2),
        "max_score": max_score,
        "evidence": evidence,
        "blocking_issues": "; ".join(failed_conditions),
        "required_before_money": not passed,
        "candidate_label": candidate_label,
    }


def _score_row(category: str, points: float, max_points: float) -> dict[str, Any]:
    ratio = points / max_points if max_points else 0.0
    status = "PASS" if ratio >= 1.0 else "PARTIAL" if points > 0 else "FAIL"
    return {
        "score_category": category,
        "points_awarded": round(float(points), 2),
        "max_points": max_points,
        "status": status,
        "evidence": f"{points:.2f}/{max_points:.2f}",
    }


def _final_decision_text(result: ResearchDecisionGateResult) -> str:
    if result.final_label == "NOT_READY_DATA_INSUFFICIENT":
        return "The project is not ready for shadow mode, paper trading, or real money. The first blocker is validation-grade CME/XAU data coverage."
    if result.final_label == "GURU_FILTER_CANDIDATE":
        return "No-trade/filter logic is promising, but it is not validated for trading until walk-forward, placebo, and data coverage gates pass."
    if result.final_label == "MARKET_MAP_CANDIDATE":
        return "Market maps may help interpretation, but they are not trade rules and need more controlled validation."
    return "The current evidence remains research-only until every money-readiness gate passes."


def _frame(inputs: dict[str, pl.DataFrame | str], name: str) -> pl.DataFrame:
    value = inputs.get(name)
    return value if isinstance(value, pl.DataFrame) else pl.DataFrame()


def _has_columns(frame: pl.DataFrame, columns: list[str]) -> bool:
    return not frame.is_empty() and all(column in frame.columns for column in columns)


def _true_count(frame: pl.DataFrame, column: str) -> int:
    if frame.is_empty() or column not in frame.columns:
        return 0
    return sum(1 for value in frame.get_column(column).to_list() if _bool_value(value))


def _any_true(frame: pl.DataFrame, column: str) -> bool:
    return _true_count(frame, column) > 0


def _any_false(frame: pl.DataFrame, column: str) -> bool:
    if frame.is_empty() or column not in frame.columns:
        return False
    return any(not _bool_value(value) for value in frame.get_column(column).to_list())


def _all_true_or_missing(frame: pl.DataFrame, column: str) -> bool:
    if frame.is_empty() or column not in frame.columns:
        return True
    return all(_bool_value(value) for value in frame.get_column(column).to_list())


def _bool_value(value: Any) -> bool:
    """Parse bool-like CSV values without treating the string 'false' as true."""

    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"", "0", "false", "f", "no", "n", "none", "null", "nan"}:
        return False
    if text in {"1", "true", "t", "yes", "y"}:
        return True
    return bool(text)


def _any_equals(frame: pl.DataFrame, column: str, value: Any) -> bool:
    if frame.is_empty() or column not in frame.columns:
        return False
    return any(str(item) == str(value) for item in frame.get_column(column).to_list())


def _any_positive(frame: pl.DataFrame, column: str) -> bool:
    return _max_numeric(frame, column) > 0


def _max_numeric(frame: pl.DataFrame, column: str) -> float:
    if frame.is_empty() or column not in frame.columns:
        return 0.0
    values = [_float(value) for value in frame.get_column(column).to_list()]
    clean = [value for value in values if value is not None]
    return max(clean) if clean else 0.0


def _sum_numeric(frame: pl.DataFrame, column: str) -> float:
    if frame.is_empty() or column not in frame.columns:
        return 0.0
    return sum(_float(value) or 0.0 for value in frame.get_column(column).to_list())


def _float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _market_has_any(market: pl.DataFrame, terms: list[str]) -> bool:
    if market.is_empty() or "key_columns_detected" not in market.columns:
        return False
    text = " ".join(str(value).lower() for value in market.get_column("key_columns_detected").to_list())
    return any(term.lower() in text for term in terms)


def _has_basis_adjustment_comparison(market_map: pl.DataFrame) -> bool:
    if market_map.is_empty():
        return False
    text = " ".join(str(value).lower() for row in market_map.to_dicts() for value in row.values())
    return "basis_adjusted" in text and "non_basis" in text


def _cost_stress_survives(frame: pl.DataFrame) -> bool:
    if frame.is_empty() or "cost_multiplier" not in frame.columns:
        return False
    needed = {2, 3, 5}
    surviving = set()
    for row in frame.to_dicts():
        multiplier = int(_float(row.get("cost_multiplier")) or 0)
        expectancy = _float(row.get("expectancy"))
        profit_factor = _float(row.get("profit_factor"))
        if (
            multiplier in needed
            and expectancy is not None
            and expectancy > 0
            and profit_factor is not None
            and profit_factor >= 1.2
        ):
            surviving.add(multiplier)
    return needed.issubset(surviving)


def _bucket_expectancy(backtest: pl.DataFrame, bucket: str) -> float | None:
    if not _has_columns(backtest, ["bucket", "expectancy"]):
        return None
    rows = backtest.filter(pl.col("bucket") == bucket)
    return _max_numeric(rows, "expectancy") if not rows.is_empty() else None


def _best_directional_expectancy(backtest: pl.DataFrame) -> float | None:
    if not _has_columns(backtest, ["bucket", "expectancy"]):
        return None
    excluded = {"BOLLINGER_BASELINE", "RANDOM_BASELINE", "SD_ONLY_BASELINE", "OI_WALL_ONLY_BASELINE"}
    rows = backtest.filter(~pl.col("bucket").is_in(list(excluded)))
    return _max_numeric(rows, "expectancy") if not rows.is_empty() else None


def _leakage_audit_passes(text: str) -> bool:
    """Return false only for explicit leakage failures or nonzero future-use counts."""

    if not text:
        return False
    lowered = text.lower()
    if "leakage failure" in lowered or "future leak" in lowered:
        return False
    count_patterns = [
        r"future iv used before availability:\s*(\d+)",
        r"future oi/wall used before event timestamp:\s*(\d+)",
    ]
    for pattern in count_patterns:
        match = re.search(pattern, lowered)
        if match and int(match.group(1)) > 0:
            return False
    return True


def _frame_markdown(frame: pl.DataFrame) -> str:
    if frame.is_empty():
        return "_No rows._"
    columns = frame.columns
    rows = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for raw in frame.head(40).to_dicts():
        rows.append("| " + " | ".join(_markdown_cell(raw.get(column, "")) for column in columns) + " |")
    return "\n".join(rows)


def _markdown_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _escape_xml(value: Any) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
