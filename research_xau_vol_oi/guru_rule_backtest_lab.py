"""Guru logic rule compiler and conservative range backtest lab.

This module is research-only. It compiles explicit rule candidates from the
guru playbook, runs price-only and current CME pilot checks where data exists,
and refuses same-day transcript modes unless transcript timing is confirmed.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import polars as pl

from research_xau_vol_oi.config import ResearchConfig


FORBIDDEN_REPORT_PHRASES = (
    "profitable",
    "safe to trade",
    "live ready",
    "live-ready",
    "money-readiness",
)
FINAL_RECOMMENDATIONS = (
    "START_PRICE_ONLY_RULE_BACKTEST",
    "START_CME_PILOT_RULE_BACKTEST",
    "WAIT_FOR_TRANSCRIPT_METADATA_FOR_SAME_DAY",
    "WAIT_FOR_MORE_CME_DATA_FOR_FULL_VALIDATION",
    "RULE_LIBRARY_READY",
    "RULE_BACKTEST_READY",
    "NOT_READY_FOR_MONEY",
)
RULE_MODES = (
    "PRICE_ONLY_RULES",
    "CME_PILOT_RULES",
    "SAME_DAY_CONFIRMED_GURU_RULES",
    "HISTORICAL_PLAYBOOK_RULES",
)


@dataclass(frozen=True)
class GuruRuleBacktestLabResult:
    """Generated rule library, backtest, ablation, and scorecard frames."""

    guru_rule_library: pl.DataFrame
    guru_rule_backtest_events: pl.DataFrame
    guru_rule_backtest_summary: pl.DataFrame
    guru_rule_backtest_by_period: pl.DataFrame
    guru_rule_formation_test_results: pl.DataFrame
    guru_rule_ablation: pl.DataFrame
    range_period_rule_scorecard: pl.DataFrame
    final_recommendation: str


def run_guru_rule_backtest_lab(
    *,
    output_dir: str | Path = "outputs",
    date_start: str | None = None,
    date_end: str | None = None,
    config: ResearchConfig | None = None,
) -> GuruRuleBacktestLabResult:
    """Run the rule compiler and conservative rule backtest lab."""

    cfg = config or ResearchConfig()
    output_root = Path(output_dir)
    charts_dir = output_root / cfg.chart_dir_name
    output_root.mkdir(parents=True, exist_ok=True)
    charts_dir.mkdir(parents=True, exist_ok=True)
    inputs = load_guru_rule_backtest_inputs(output_root)
    selected_start = date_start or os.getenv("GURU_RULE_BACKTEST_DATE_START") or os.getenv(
        "XAU_RULE_BACKTEST_DATE_START",
    )
    selected_end = date_end or os.getenv("GURU_RULE_BACKTEST_DATE_END") or os.getenv(
        "XAU_RULE_BACKTEST_DATE_END",
    )
    result = build_guru_rule_backtest_lab(
        inputs,
        date_start=selected_start,
        date_end=selected_end,
    )

    result.guru_rule_library.write_csv(output_root / "guru_rule_library.csv")
    (output_root / "guru_rule_library.md").write_text(
        guru_rule_library_markdown(result.guru_rule_library),
        encoding="utf-8",
    )
    (output_root / "guru_rule_definitions.yaml").write_text(
        guru_rule_definitions_yaml(result.guru_rule_library),
        encoding="utf-8",
    )
    result.guru_rule_backtest_events.write_csv(output_root / "guru_rule_backtest_events.csv")
    result.guru_rule_backtest_summary.write_csv(output_root / "guru_rule_backtest_summary.csv")
    result.guru_rule_backtest_by_period.write_csv(output_root / "guru_rule_backtest_by_period.csv")
    (output_root / "guru_rule_backtest_report.md").write_text(
        guru_rule_backtest_report_markdown(result),
        encoding="utf-8",
    )
    result.guru_rule_formation_test_results.write_csv(
        output_root / "guru_rule_formation_test_results.csv"
    )
    result.guru_rule_ablation.write_csv(output_root / "guru_rule_ablation.csv")
    (output_root / "guru_rule_ablation_report.md").write_text(
        guru_rule_ablation_report_markdown(result.guru_rule_ablation),
        encoding="utf-8",
    )
    result.range_period_rule_scorecard.write_csv(output_root / "range_period_rule_scorecard.csv")
    (output_root / "range_period_rule_backtest_report.md").write_text(
        range_period_rule_backtest_report_markdown(result.range_period_rule_scorecard),
        encoding="utf-8",
    )
    write_rule_backtest_charts(
        charts_dir=charts_dir,
        summary=result.guru_rule_backtest_summary,
        ablation=result.guru_rule_ablation,
    )
    append_guru_rule_backtest_lab_sections(output_root / "research_report.md", result)
    return result


def load_guru_rule_backtest_inputs(output_root: Path) -> dict[str, pl.DataFrame]:
    """Load optional inputs with empty-frame fallbacks."""

    paths = {
        "guru_logic_knowledge_base": output_root / "guru_logic_knowledge_base.csv",
        "guru_logic_priority_rank": output_root / "guru_logic_priority_rank.csv",
        "guru_logic_data_dependency_matrix": output_root / "guru_logic_data_dependency_matrix.csv",
        "same_day_playbook_matches": output_root / "same_day_playbook_matches.csv",
        "current_week_same_day_guru_overlay": output_root
        / "current_week_same_day_guru_overlay.csv",
        "transcript_availability_classification_after_metadata": output_root
        / "transcript_availability_classification_after_metadata.csv",
        "same_day_filter_evidence_after_metadata": output_root
        / "same_day_filter_evidence_after_metadata.csv",
        "same_day_market_map_evidence_after_metadata": output_root
        / "same_day_market_map_evidence_after_metadata.csv",
        "current_week_evidence_scorecard": output_root / "current_week_evidence_scorecard.csv",
        "current_week_replay_after_market_session_remap": output_root
        / "current_week_replay_after_market_session_remap.csv",
        "current_week_cme_guru_replay": output_root / "current_week_cme_guru_replay.csv",
        "xau_spot_backfilled": output_root / "xau_spot_backfilled.parquet",
        "xau_basis_backfilled": output_root / "xau_basis_backfilled.parquet",
        "cme_canonical_option_oi_by_strike": output_root
        / "cme_canonical_option_oi_by_strike.parquet",
        "cme_canonical_option_iv_by_strike": output_root
        / "cme_canonical_option_iv_by_strike.parquet",
        "cme_canonical_futures_price": output_root / "cme_canonical_futures_price.parquet",
        "signal_events": output_root / "signal_events.csv",
        "backtest_summary": output_root / "backtest_summary.csv",
        "xau_feature_table": output_root / "xau_feature_table.parquet",
    }
    return {name: _load_optional(path) for name, path in paths.items()}


def build_guru_rule_backtest_lab(
    inputs: dict[str, pl.DataFrame],
    *,
    date_start: str | None = None,
    date_end: str | None = None,
) -> GuruRuleBacktestLabResult:
    """Build rule library, events, summaries, split checks, ablation, and scorecard."""

    library = build_guru_rule_library(
        knowledge_base=_frame(inputs, "guru_logic_knowledge_base"),
        dependency_matrix=_frame(inputs, "guru_logic_data_dependency_matrix"),
        availability=_frame(inputs, "transcript_availability_classification_after_metadata"),
    )
    price = _filter_date_range(_frame(inputs, "xau_feature_table"), date_start, date_end)
    cme = _filter_date_range(_frame(inputs, "current_week_cme_guru_replay"), date_start, date_end)
    availability = _frame(inputs, "transcript_availability_classification_after_metadata")
    same_day_matches = _frame(inputs, "same_day_playbook_matches")
    events = build_rule_backtest_events(
        rule_library=library,
        price_features=price,
        cme_replay=cme,
        transcript_availability=availability,
        same_day_matches=same_day_matches,
    )
    summary = summarize_rule_backtest_events(events, rule_library=library)
    by_period = summarize_rule_backtest_by_period(events)
    formation = build_formation_test_results(
        rule_library=library,
        events=events,
        date_start=date_start,
        date_end=date_end,
    )
    ablation = build_rule_ablation(events, cme_replay=cme, transcript_availability=availability)
    scorecard = build_range_period_scorecard(
        rule_library=library,
        events=events,
        cme_replay=cme,
        price_features=price,
        availability=availability,
        date_start=date_start,
        date_end=date_end,
    )
    final = choose_rule_backtest_recommendation(
        rule_library=library,
        events=events,
        cme_replay=cme,
        availability=availability,
    )
    return GuruRuleBacktestLabResult(
        guru_rule_library=library,
        guru_rule_backtest_events=events,
        guru_rule_backtest_summary=summary,
        guru_rule_backtest_by_period=by_period,
        guru_rule_formation_test_results=formation,
        guru_rule_ablation=ablation,
        range_period_rule_scorecard=scorecard,
        final_recommendation=final,
    )


def build_guru_rule_library(
    *,
    knowledge_base: pl.DataFrame,
    dependency_matrix: pl.DataFrame,
    availability: pl.DataFrame,
) -> pl.DataFrame:
    """Compile the first explicit guru rule candidates."""

    kb_by_logic = _rows_by_key(knowledge_base, "logic_id")
    dep_by_logic = _rows_by_key(dependency_matrix, "logic_id")
    same_day_confirmed = _has_timing_confirmed_same_day(availability)
    rows = []
    for spec in _base_rule_specs():
        logic_id = spec.get("logic_id", "")
        kb = kb_by_logic.get(logic_id, {})
        dep = dep_by_logic.get(logic_id, {})
        first_seen = _date_text(kb.get("first_seen_date"))
        required_data = _required_data_for_rule(spec, dep)
        can_same_day = bool(
            spec["logic_source"] == "SAME_DAY_TIMING_CONFIRMED" and same_day_confirmed
        )
        validation = _validation_status_for_rule(
            spec=spec,
            required_data=required_data,
            can_same_day=can_same_day,
        )
        rows.append(
            {
                "rule_id": spec["rule_id"],
                "rule_name": spec["rule_name"],
                "rule_family": spec["rule_family"],
                "logic_source": spec["logic_source"],
                "rule_type": spec["rule_type"],
                "required_data": "|".join(required_data),
                "condition": spec["condition"],
                "action": spec["action"],
                "invalidation": spec["invalidation"],
                "target": spec["target"],
                "can_backtest_price_only": spec["rule_family"] == "PRICE_ONLY",
                "can_backtest_cme_pilot": spec["rule_family"] in {"CME_MARKET_MAP", "CME_FILTER"},
                "can_backtest_same_day_signal": can_same_day,
                "leakage_risk": spec["leakage_risk"],
                "validation_status": validation,
                "first_seen_date": first_seen,
                "source_logic_id": logic_id,
            }
        )
    return _rows_frame(rows, _rule_library_schema()).sort("rule_id")


def build_rule_backtest_events(
    *,
    rule_library: pl.DataFrame,
    price_features: pl.DataFrame,
    cme_replay: pl.DataFrame,
    transcript_availability: pl.DataFrame,
    same_day_matches: pl.DataFrame,
) -> pl.DataFrame:
    """Build deterministic rule events for available modes."""

    rows: list[dict[str, Any]] = []
    price_rows = price_features.sort("timestamp").to_dicts() if not price_features.is_empty() else []
    rows.extend(_price_only_events(price_rows))
    rows.extend(_cme_pilot_events(cme_replay))
    rows.extend(_same_day_confirmed_events(transcript_availability, same_day_matches))
    rows.extend(_historical_playbook_events(rule_library, price_rows))
    return _rows_frame(rows, _event_schema()).sort(["mode", "event_timestamp", "rule_id"])


def summarize_rule_backtest_events(
    events: pl.DataFrame,
    *,
    rule_library: pl.DataFrame,
) -> pl.DataFrame:
    """Summarize rule outcome metrics by rule and mode."""

    library_by_rule = _rows_by_key(rule_library, "rule_id")
    rows = []
    if events.is_empty():
        for rule in rule_library.to_dicts() if not rule_library.is_empty() else []:
            rows.append(_empty_summary_row(rule, mode=_mode_for_rule(rule)))
        return _rows_frame(rows, _summary_schema()).sort(["mode", "rule_id"])

    for (mode, rule_id), group_rows in _group_event_rows(events, ("mode", "rule_id")).items():
        rule = library_by_rule.get(rule_id, {})
        rows.append(_summarize_rule_group(rule_id=rule_id, mode=mode, rows=group_rows, rule=rule))

    observed = {(row["mode"], row["rule_id"]) for row in rows}
    for rule in rule_library.to_dicts() if not rule_library.is_empty() else []:
        mode = _mode_for_rule(rule)
        key = (mode, _text(rule.get("rule_id")))
        if key not in observed:
            rows.append(_empty_summary_row(rule, mode=mode))
    return _rows_frame(rows, _summary_schema()).sort(["mode", "rule_id"])


def summarize_rule_backtest_by_period(events: pl.DataFrame) -> pl.DataFrame:
    """Summarize rule events by calendar month and mode."""

    rows = []
    for (mode, period), group_rows in _group_event_rows(events, ("mode", "period")).items():
        returns = [_float_or_zero(row.get("future_return_points")) for row in group_rows]
        rows.append(
            {
                "period": period,
                "mode": mode,
                "event_count": len(group_rows),
                "trade_candidate_count": sum(1 for row in group_rows if _bool_value(row.get("trade_candidate"))),
                "blocked_trade_count": sum(1 for row in group_rows if _bool_value(row.get("blocked_trade"))),
                "average_return": _mean(returns),
                "expectancy_proxy": _mean(returns),
                "sample_size_warning": len(group_rows) < 30,
                "timing_warning": _any_truthy(group_rows, "timing_warning"),
                "leakage_warning": _any_truthy(group_rows, "leakage_warning"),
            }
        )
    return _rows_frame(rows, _by_period_schema()).sort(["period", "mode"])


def build_formation_test_results(
    *,
    rule_library: pl.DataFrame,
    events: pl.DataFrame,
    date_start: str | None = None,
    date_end: str | None = None,
) -> pl.DataFrame:
    """Create formation/test split diagnostics to avoid transcript lookahead."""

    event_dates = sorted(_date_text(row.get("event_date")) for row in events.to_dicts() if _date_text(row.get("event_date")))
    inferred_start = date_start or (event_dates[0] if event_dates else "")
    inferred_end = date_end or (event_dates[-1] if event_dates else "")
    split = _midpoint_date(event_dates)
    rows = []
    events_by_rule = _group_event_rows(events, ("rule_id",))
    for rule in rule_library.to_dicts() if not rule_library.is_empty() else []:
        rule_id = _text(rule.get("rule_id"))
        group = events_by_rule.get((rule_id,), [])
        first_seen = _date_text(rule.get("first_seen_date"))
        source = _text(rule.get("logic_source"))
        formation_count = sum(1 for row in group if _date_text(row.get("event_date")) <= split)
        test_count = sum(1 for row in group if _date_text(row.get("event_date")) > split)
        leakage = _formation_leakage_warning(rule, group)
        rows.append(
            {
                "rule_id": rule_id,
                "logic_source": source,
                "first_seen_date": first_seen,
                "date_start": inferred_start,
                "date_end": inferred_end,
                "formation_start": inferred_start,
                "formation_end": split,
                "test_start": _next_date_text(split),
                "test_end": inferred_end,
                "formation_event_count": formation_count,
                "test_event_count": test_count,
                "rules_frozen_before_test": True,
                "sample_size_warning": test_count < 30,
                "leakage_warning": leakage,
                "notes": _formation_notes(rule, leakage),
            }
        )
    return _rows_frame(rows, _formation_schema()).sort("rule_id")


def build_rule_ablation(
    events: pl.DataFrame,
    *,
    cme_replay: pl.DataFrame,
    transcript_availability: pl.DataFrame,
) -> pl.DataFrame:
    """Build conservative rule ablation rows."""

    scenarios = [
        ("base price-only baseline", {"PRICE_ONLY_RULES"}, set()),
        ("baseline + no-trade filter", {"PRICE_ONLY_RULES"}, {"NO_TRADE_MIDDLE_RANGE"}),
        (
            "baseline + rejection/acceptance confirmation",
            {"PRICE_ONLY_RULES"},
            {"REJECTION_AFTER_LEVEL_TOUCH", "ACCEPTANCE_BREAKOUT"},
        ),
        ("baseline + CME OI wall map", {"PRICE_ONLY_RULES", "CME_PILOT_RULES"}, {"OI_WALL_WATCH_ZONE"}),
        (
            "baseline + IV expected range",
            {"PRICE_ONLY_RULES", "CME_PILOT_RULES"},
            {"IV_EXPECTED_RANGE_FILTER"},
        ),
        (
            "baseline + same-day guru filter if timing confirmed",
            {"PRICE_ONLY_RULES", "SAME_DAY_CONFIRMED_GURU_RULES"},
            {"GURU_SAME_DAY_FILTER_CONFIRMED"},
        ),
        (
            "baseline + all available filters",
            {"PRICE_ONLY_RULES", "CME_PILOT_RULES", "SAME_DAY_CONFIRMED_GURU_RULES"},
            set(),
        ),
    ]
    has_cme = not cme_replay.is_empty()
    has_same_day = _has_timing_confirmed_same_day(transcript_availability)
    rows = []
    for scenario, modes, include_rules in scenarios:
        selected = [
            row
            for row in events.to_dicts()
            if _text(row.get("mode")) in modes
            and (not include_rules or _text(row.get("rule_id")) in include_rules)
        ]
        if "CME_PILOT_RULES" in modes and not has_cme:
            status = "WAIT_FOR_MORE_CME_DATA"
        elif "SAME_DAY_CONFIRMED_GURU_RULES" in modes and not has_same_day:
            status = "WAIT_FOR_TRANSCRIPT_METADATA"
        else:
            status = "READY_FOR_RESEARCH_REVIEW"
        returns = [_float_or_zero(row.get("future_return_points")) for row in selected]
        rows.append(
            {
                "scenario": scenario,
                "included_modes": "|".join(sorted(modes)),
                "included_rules": "|".join(sorted(include_rules)) if include_rules else "all_available",
                "event_count": len(selected),
                "blocked_trade_count": sum(1 for row in selected if _bool_value(row.get("blocked_trade"))),
                "average_return": _mean(returns),
                "expectancy_proxy": _mean(returns),
                "net_filter_value_proxy": _filter_value(selected),
                "status": status,
                "sample_size_warning": len(selected) < 30,
                "notes": _ablation_notes(status),
            }
        )
    return _rows_frame(rows, _ablation_schema())


def build_range_period_scorecard(
    *,
    rule_library: pl.DataFrame,
    events: pl.DataFrame,
    cme_replay: pl.DataFrame,
    price_features: pl.DataFrame,
    availability: pl.DataFrame,
    date_start: str | None = None,
    date_end: str | None = None,
) -> pl.DataFrame:
    """Build selected range scorecard."""

    dates = sorted(_date_text(row.get("event_date")) for row in events.to_dicts() if _date_text(row.get("event_date")))
    start = date_start or (dates[0] if dates else "")
    end = date_end or (dates[-1] if dates else "")
    mode_counts = _state_counts(events, "mode")
    summary = summarize_rule_backtest_events(events, rule_library=rule_library)
    best_rule, weak_rule = _best_and_weakest_rules(summary)
    missing = _blocked_rules(rule_library)
    rows = [
        {
            "date_start": start,
            "date_end": end,
            "data_available": f"price_rows={price_features.height};cme_rows={cme_replay.height};event_rows={events.height}",
            "rule_modes_available": "|".join(sorted(mode_counts)),
            "best_supported_rule": best_rule,
            "weakest_rule": weak_rule,
            "rules_blocked_by_missing_data": "|".join(missing),
            "whether_metadata_is_needed": not _has_timing_confirmed_same_day(availability),
            "whether_more_cme_is_needed": cme_replay.height < 60,
            "whether_result_is_pilot_only": True,
        }
    ]
    return _rows_frame(rows, _scorecard_schema())


def choose_rule_backtest_recommendation(
    *,
    rule_library: pl.DataFrame,
    events: pl.DataFrame,
    cme_replay: pl.DataFrame,
    availability: pl.DataFrame,
) -> str:
    """Choose final rule-lab recommendation."""

    price_events = events.filter(pl.col("mode") == "PRICE_ONLY_RULES") if not events.is_empty() else pl.DataFrame()
    if price_events.height > 0 and cme_replay.height > 0 and not _has_timing_confirmed_same_day(availability):
        return "WAIT_FOR_TRANSCRIPT_METADATA_FOR_SAME_DAY"
    if price_events.height > 0 and cme_replay.height > 0:
        return "RULE_BACKTEST_READY"
    if price_events.height > 0:
        return "START_PRICE_ONLY_RULE_BACKTEST"
    if rule_library.height > 0:
        return "RULE_LIBRARY_READY"
    return "NOT_READY_FOR_MONEY"


def guru_rule_backtest_lab_report_lines(
    result: GuruRuleBacktestLabResult | None,
) -> list[str]:
    """Return Markdown lines for embedding in the main research report."""

    if result is None:
        return ["Guru rule backtest lab was not run."]
    return [
        "## Guru Rule Library",
        "",
        f"- Final recommendation: `{result.final_recommendation}`",
        f"- Rules compiled: `{result.guru_rule_library.height}`",
        "",
        _frame_markdown(result.guru_rule_library),
        "",
        "## Rule Backtest Lab",
        "",
        _frame_markdown(result.guru_rule_backtest_summary),
        "",
        "## Price-Only Rule Backtest",
        "",
        _frame_markdown(_filter_mode(result.guru_rule_backtest_summary, "PRICE_ONLY_RULES")),
        "",
        "## CME Pilot Rule Backtest",
        "",
        _frame_markdown(_filter_mode(result.guru_rule_backtest_summary, "CME_PILOT_RULES")),
        "",
        "## Same-Day Confirmed Guru Rule Backtest",
        "",
        _frame_markdown(_filter_mode(result.guru_rule_backtest_summary, "SAME_DAY_CONFIRMED_GURU_RULES")),
        "",
        "## Historical Playbook Rule Warnings",
        "",
        _frame_markdown(
            result.guru_rule_formation_test_results.filter(pl.col("leakage_warning"))
            if not result.guru_rule_formation_test_results.is_empty()
            else pl.DataFrame()
        ),
        "",
        "## Formation/Test Split",
        "",
        _frame_markdown(result.guru_rule_formation_test_results),
        "",
        "## Rule Ablation",
        "",
        _frame_markdown(result.guru_rule_ablation),
        "",
        "## Range-Period Rule Scorecard",
        "",
        _frame_markdown(result.range_period_rule_scorecard),
        "",
        "## What Is Ready Now vs What Needs Metadata/CME",
        "",
        *_ready_now_lines(result),
    ]


def guru_rule_library_markdown(frame: pl.DataFrame) -> str:
    """Render rule library markdown."""

    return _safe_report(
        "\n".join(
            [
                "# Guru Rule Library",
                "",
                "Rules are research hypotheses. Same-day transcript rules require confirmed timing.",
                "",
                _frame_markdown(frame),
            ]
        )
    )


def guru_rule_definitions_yaml(frame: pl.DataFrame) -> str:
    """Render a simple YAML rule-definition file without extra dependencies."""

    lines = [
        "# Research-only guru rule definitions.",
        "# Same-day transcript rules require PRE_SESSION or DURING_SESSION timing before use.",
        "rules:",
    ]
    for row in frame.to_dicts() if not frame.is_empty() else []:
        lines.extend(
            [
                f"  - rule_id: {_yaml_quote(row.get('rule_id'))}",
                f"    rule_name: {_yaml_quote(row.get('rule_name'))}",
                f"    rule_family: {_yaml_quote(row.get('rule_family'))}",
                f"    logic_source: {_yaml_quote(row.get('logic_source'))}",
                f"    rule_type: {_yaml_quote(row.get('rule_type'))}",
                f"    required_data: {_yaml_quote(row.get('required_data'))}",
                f"    condition: {_yaml_quote(row.get('condition'))}",
                f"    action: {_yaml_quote(row.get('action'))}",
                f"    invalidation: {_yaml_quote(row.get('invalidation'))}",
                f"    target: {_yaml_quote(row.get('target'))}",
                f"    validation_status: {_yaml_quote(row.get('validation_status'))}",
            ]
        )
    return _safe_report("\n".join(lines) + "\n")


def guru_rule_backtest_report_markdown(result: GuruRuleBacktestLabResult) -> str:
    """Render backtest lab report."""

    return _safe_report(
        "\n".join(
            [
                "# Guru Rule Backtest Lab",
                "",
                "This report is a research event study and does not make performance claims.",
                "",
                "## Summary",
                "",
                _frame_markdown(result.guru_rule_backtest_summary),
                "",
                "## By Period",
                "",
                _frame_markdown(result.guru_rule_backtest_by_period),
                "",
                "## Formation/Test Split",
                "",
                _frame_markdown(result.guru_rule_formation_test_results),
            ]
        )
    )


def guru_rule_ablation_report_markdown(frame: pl.DataFrame) -> str:
    """Render ablation report."""

    return _safe_report(
        "\n".join(
            [
                "# Guru Rule Ablation",
                "",
                "Ablation rows are proxies for research triage; they are not deployment evidence.",
                "",
                _frame_markdown(frame),
            ]
        )
    )


def range_period_rule_backtest_report_markdown(frame: pl.DataFrame) -> str:
    """Render range-period scorecard."""

    return _safe_report(
        "\n".join(
            [
                "# Range-Period Rule Backtest Report",
                "",
                "The selected range scorecard labels pilot-only and missing-data limits explicitly.",
                "",
                _frame_markdown(frame),
            ]
        )
    )


def append_guru_rule_backtest_lab_sections(path: Path, result: GuruRuleBacktestLabResult) -> None:
    """Append or replace the rule lab section in the main report."""

    marker = "\n## Guru Rule Library\n"
    section = _safe_report("\n".join(guru_rule_backtest_lab_report_lines(result)))
    existing = path.read_text(encoding="utf-8") if path.exists() else "# XAU/USD Vol-OI Research Report\n"
    if marker in existing:
        existing = existing.split(marker, 1)[0].rstrip()
    path.write_text(_redact_text(existing.rstrip()) + "\n\n" + section + "\n", encoding="utf-8")


def write_rule_backtest_charts(
    *,
    charts_dir: Path,
    summary: pl.DataFrame,
    ablation: pl.DataFrame,
) -> None:
    """Write simple SVG charts for rule lab outputs."""

    labels = summary.get_column("rule_id").to_list() if not summary.is_empty() else []
    expectancy = summary.get_column("expectancy_proxy").to_list() if not summary.is_empty() else []
    filter_value = summary.get_column("net_filter_value_proxy").to_list() if not summary.is_empty() else []
    hit_rate = summary.get_column("wall_touch_rate").to_list() if not summary.is_empty() else []
    modes = _state_counts(summary, "mode")
    _write_bar_svg(
        charts_dir / "rule_backtest_expectancy.svg",
        title="Rule expectancy proxy",
        labels=[str(item) for item in labels],
        values=[float(value or 0.0) for value in expectancy],
    )
    _write_bar_svg(
        charts_dir / "rule_filter_value.svg",
        title="Rule filter value proxy",
        labels=[str(item) for item in labels],
        values=[float(value or 0.0) for value in filter_value],
    )
    _write_bar_svg(
        charts_dir / "rule_market_map_hit_rate.svg",
        title="Rule market-map hit rate",
        labels=[str(item) for item in labels],
        values=[float(value or 0.0) for value in hit_rate],
    )
    _write_bar_svg(
        charts_dir / "rule_mode_coverage.svg",
        title="Rule mode coverage",
        labels=list(modes),
        values=[float(value) for value in modes.values()],
    )
    _ = ablation


def _base_rule_specs() -> list[dict[str, str]]:
    return [
        {
            "rule_id": "NO_TRADE_MIDDLE_RANGE",
            "rule_name": "No trade in middle range",
            "rule_family": "PRICE_ONLY",
            "logic_source": "HISTORICAL_PLAYBOOK",
            "rule_type": "FILTER",
            "logic_id": "glkb_no_trade_discipline",
            "condition": "Price is inside the middle volatility/range zone.",
            "action": "Block directional chase trades.",
            "invalidation": "Price reaches an outer range edge or confirmed level interaction.",
            "target": "Reduced low-context directional candidates.",
            "leakage_risk": "MEDIUM",
        },
        {
            "rule_id": "OPEN_DISTANCE_FILTER",
            "rule_name": "Open distance chase filter",
            "rule_family": "PRICE_ONLY",
            "logic_source": "MANUAL_RESEARCH_HYPOTHESIS",
            "rule_type": "FILTER",
            "logic_id": "",
            "condition": "Price is far from the session open relative to current range.",
            "action": "Reduce chase trades.",
            "invalidation": "Price consolidates or retests a level.",
            "target": "Avoid overextended entries.",
            "leakage_risk": "LOW",
        },
        {
            "rule_id": "REJECTION_AFTER_LEVEL_TOUCH",
            "rule_name": "Rejection after level touch",
            "rule_family": "PRICE_ONLY",
            "logic_source": "MANUAL_RESEARCH_HYPOTHESIS",
            "rule_type": "ENTRY_TRIGGER",
            "logic_id": "glkb_rejection_confirmation",
            "condition": "Price touches a level and closes back inside.",
            "action": "Classify rejection.",
            "invalidation": "Next bar accepts beyond the level.",
            "target": "Rejection follow-through proxy.",
            "leakage_risk": "LOW",
        },
        {
            "rule_id": "ACCEPTANCE_BREAKOUT",
            "rule_name": "Acceptance breakout",
            "rule_family": "PRICE_ONLY",
            "logic_source": "MANUAL_RESEARCH_HYPOTHESIS",
            "rule_type": "ENTRY_TRIGGER",
            "logic_id": "glkb_acceptance_close_confirmation",
            "condition": "Price closes beyond a level and next bar holds.",
            "action": "Classify acceptance.",
            "invalidation": "Close returns inside the level.",
            "target": "Breakout follow-through proxy.",
            "leakage_risk": "LOW",
        },
        {
            "rule_id": "OI_WALL_WATCH_ZONE",
            "rule_name": "OI wall watch zone",
            "rule_family": "CME_MARKET_MAP",
            "logic_source": "HISTORICAL_PLAYBOOK",
            "rule_type": "MARKET_MAP",
            "logic_id": "glkb_oi_wall",
            "condition": "Price approaches a basis-adjusted OI wall.",
            "action": "Watch for rejection or acceptance.",
            "invalidation": "Basis or wall data missing/stale.",
            "target": "Wall touch/rejection/acceptance map.",
            "leakage_risk": "MEDIUM",
        },
        {
            "rule_id": "LOW_OI_GAP_SQUEEZE",
            "rule_name": "Low OI gap squeeze risk",
            "rule_family": "CME_MARKET_MAP",
            "logic_source": "HISTORICAL_PLAYBOOK",
            "rule_type": "MARKET_MAP",
            "logic_id": "glkb_squeeze_risk",
            "condition": "Price moves through a low-OI area toward the next wall.",
            "action": "Classify squeeze risk.",
            "invalidation": "No next-wall gap or OI data missing.",
            "target": "Low-OI continuation risk.",
            "leakage_risk": "MEDIUM",
        },
        {
            "rule_id": "PIN_RISK_NEAR_EXPIRY_WALL",
            "rule_name": "Pin risk near expiry wall",
            "rule_family": "CME_FILTER",
            "logic_source": "HISTORICAL_PLAYBOOK",
            "rule_type": "FILTER",
            "logic_id": "glkb_pin_risk",
            "condition": "Price is near a large near-expiry wall.",
            "action": "Reduce directional confidence.",
            "invalidation": "Expiry/wall data unavailable.",
            "target": "Pin-risk filter proxy.",
            "leakage_risk": "MEDIUM",
        },
        {
            "rule_id": "STALE_DATA_NO_TRADE",
            "rule_name": "Stale data no-trade",
            "rule_family": "CME_FILTER",
            "logic_source": "HISTORICAL_PLAYBOOK",
            "rule_type": "FILTER",
            "logic_id": "glkb_stale_data_warning",
            "condition": "CME data is stale or critical fields are missing.",
            "action": "No-trade.",
            "invalidation": "Fresh CME OI/basis/IV fields available.",
            "target": "Data-quality filter.",
            "leakage_risk": "MEDIUM",
        },
        {
            "rule_id": "IV_EXPECTED_RANGE_FILTER",
            "rule_name": "IV expected range filter",
            "rule_family": "CME_FILTER",
            "logic_source": "HISTORICAL_PLAYBOOK",
            "rule_type": "FILTER",
            "logic_id": "glkb_volatility_range",
            "condition": "Price is near a 1SD/2SD edge.",
            "action": "Require stronger confirmation.",
            "invalidation": "IV range unavailable or price returns to middle.",
            "target": "Expected-range filter proxy.",
            "leakage_risk": "MEDIUM",
        },
        {
            "rule_id": "GURU_SAME_DAY_FILTER_CONFIRMED",
            "rule_name": "Guru same-day filter confirmed",
            "rule_family": "GURU_SAME_DAY_FILTER",
            "logic_source": "SAME_DAY_TIMING_CONFIRMED",
            "rule_type": "FILTER",
            "logic_id": "glkb_no_trade_discipline",
            "condition": "Same-day transcript filter timing is PRE_SESSION or DURING_SESSION.",
            "action": "Allow same-day guru filter evidence.",
            "invalidation": "Transcript timing is UNKNOWN, POST_SESSION, or WEEKEND_RECAP.",
            "target": "Timing-confirmed same-day filter only.",
            "leakage_risk": "LOW",
        },
    ]


def _price_only_events(price_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(price_rows[:-2]):
        future = price_rows[index + 2]
        timestamp = row.get("timestamp")
        close = _float_or_none(row.get("close"))
        if close is None:
            continue
        event_date = _date_text(row.get("session_date")) or _date_text(timestamp)
        period = event_date[:7]
        future_return = _float_or_zero(future.get("close")) - close
        sigma = _float_or_none(row.get("sigma_position"))
        if sigma is not None and abs(sigma) < 0.5:
            rows.append(_event(row, "PRICE_ONLY_RULES", "NO_TRADE_MIDDLE_RANGE", timestamp, event_date, period, blocked=True, future_return=future_return, reason="middle_range"))
        open_distance = abs(close - _float_or_zero(row.get("session_open") or row.get("open")))
        one_sd = abs(_float_or_zero(row.get("one_sd_remaining"))) or max(abs(close) * 0.002, 1.0)
        if open_distance > one_sd:
            rows.append(_event(row, "PRICE_ONLY_RULES", "OPEN_DISTANCE_FILTER", timestamp, event_date, period, blocked=True, future_return=future_return, reason="far_from_open"))
        upper = _float_or_none(row.get("bb_upper") or row.get("upper_1sd"))
        lower = _float_or_none(row.get("bb_lower") or row.get("lower_1sd"))
        next_close = _float_or_zero(price_rows[index + 1].get("close"))
        if upper is not None and _float_or_zero(row.get("high")) >= upper and close < upper:
            rows.append(_event(row, "PRICE_ONLY_RULES", "REJECTION_AFTER_LEVEL_TOUCH", timestamp, event_date, period, trade=True, future_return=-future_return, reason="upper_level_rejection"))
        if lower is not None and _float_or_zero(row.get("low")) <= lower and close > lower:
            rows.append(_event(row, "PRICE_ONLY_RULES", "REJECTION_AFTER_LEVEL_TOUCH", timestamp, event_date, period, trade=True, future_return=future_return, reason="lower_level_rejection"))
        if upper is not None and close > upper and next_close > upper:
            rows.append(_event(row, "PRICE_ONLY_RULES", "ACCEPTANCE_BREAKOUT", timestamp, event_date, period, trade=True, future_return=future_return, reason="upper_acceptance"))
        if lower is not None and close < lower and next_close < lower:
            rows.append(_event(row, "PRICE_ONLY_RULES", "ACCEPTANCE_BREAKOUT", timestamp, event_date, period, trade=True, future_return=-future_return, reason="lower_acceptance"))
    return rows


def _cme_pilot_events(cme_replay: pl.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in cme_replay.to_dicts() if not cme_replay.is_empty() else []:
        day = _date_text(row.get("trade_date"))
        period = day[:7]
        if _bool_value(row.get("oi_available")) and _bool_value(row.get("basis_available")):
            rows.append(_event(row, "CME_PILOT_RULES", "OI_WALL_WATCH_ZONE", day, day, period, trade=_bool_value(row.get("touched_wall")), future_return=_cme_return_proxy(row), reason="basis_adjusted_wall_available"))
        if _bool_value(row.get("squeeze_or_pin_logic_active")):
            rows.append(_event(row, "CME_PILOT_RULES", "LOW_OI_GAP_SQUEEZE", day, day, period, trade=True, future_return=_cme_return_proxy(row), reason="squeeze_or_pin_logic_active"))
        if _bool_value(row.get("squeeze_or_pin_logic_active")) and _bool_value(row.get("oi_available")):
            rows.append(_event(row, "CME_PILOT_RULES", "PIN_RISK_NEAR_EXPIRY_WALL", day, day, period, blocked=True, future_return=_cme_return_proxy(row), reason="pin_risk_near_wall"))
        missing = not (_bool_value(row.get("oi_available")) and _bool_value(row.get("basis_available")))
        if missing:
            rows.append(_event(row, "CME_PILOT_RULES", "STALE_DATA_NO_TRADE", day, day, period, blocked=True, future_return=0.0, reason="critical_cme_fields_missing"))
        if _bool_value(row.get("iv_available")) and (_bool_value(row.get("broke_range")) or _bool_value(row.get("stayed_inside_range"))):
            rows.append(_event(row, "CME_PILOT_RULES", "IV_EXPECTED_RANGE_FILTER", day, day, period, blocked=_bool_value(row.get("stayed_inside_range")), future_return=_cme_return_proxy(row), reason="iv_range_context_available"))
    return rows


def _same_day_confirmed_events(
    transcript_availability: pl.DataFrame,
    same_day_matches: pl.DataFrame,
) -> list[dict[str, Any]]:
    if transcript_availability.is_empty() or same_day_matches.is_empty():
        return []
    confirmed_ids = {
        _text(row.get("clean_transcript_id"))
        for row in transcript_availability.to_dicts()
        if _bool_value(row.get("can_use_as_same_session_filter"))
        and _text(row.get("availability_relation")) in {"PRE_SESSION", "DURING_SESSION"}
    }
    rows = []
    for row in same_day_matches.to_dicts():
        clean_id = _text(row.get("clean_transcript_id"))
        if clean_id not in confirmed_ids or not _bool_value(row.get("usable_as_filter")):
            continue
        day = _date_text(row.get("replay_date")) or _date_text(row.get("transcript_date"))
        rows.append(
            _event(
                row,
                "SAME_DAY_CONFIRMED_GURU_RULES",
                "GURU_SAME_DAY_FILTER_CONFIRMED",
                day,
                day,
                day[:7],
                blocked=True,
                future_return=0.0,
                reason="timing_confirmed_same_day_filter",
            )
        )
    return rows


def _historical_playbook_events(
    rule_library: pl.DataFrame,
    price_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = []
    sample_rows = price_rows[:: max(len(price_rows) // 20, 1)] if price_rows else []
    playbook_rules = [
        row
        for row in rule_library.to_dicts()
        if _text(row.get("logic_source")) == "HISTORICAL_PLAYBOOK"
    ]
    for rule in playbook_rules:
        first_seen = _date_text(rule.get("first_seen_date"))
        for price in sample_rows:
            day = _date_text(price.get("session_date")) or _date_text(price.get("timestamp"))
            if first_seen and day < first_seen:
                continue
            rows.append(
                _event(
                    price,
                    "HISTORICAL_PLAYBOOK_RULES",
                    _text(rule.get("rule_id")),
                    price.get("timestamp"),
                    day,
                    day[:7],
                    blocked=_text(rule.get("rule_type")) == "FILTER",
                    future_return=0.0,
                    reason="historical_playbook_context_only",
                    leakage_warning=True,
                )
            )
    return rows


def _event(
    source: dict[str, Any],
    mode: str,
    rule_id: str,
    timestamp: Any,
    event_date: str,
    period: str,
    *,
    blocked: bool = False,
    trade: bool = False,
    future_return: float = 0.0,
    reason: str = "",
    leakage_warning: bool = False,
) -> dict[str, Any]:
    return {
        "event_timestamp": _timestamp_text(timestamp),
        "event_date": event_date,
        "period": period,
        "mode": mode,
        "rule_id": rule_id,
        "event_type": "BLOCK" if blocked else "TRADE_CANDIDATE" if trade else "CONTEXT",
        "trade_candidate": trade,
        "blocked_trade": blocked,
        "future_return_points": future_return,
        "favorable_followthrough": future_return > 0,
        "level_touched": _bool_value(source.get("touched_wall")) or "rejection" in reason or "acceptance" in reason,
        "level_rejected": _bool_value(source.get("rejected_wall")) or "rejection" in reason,
        "level_accepted": _bool_value(source.get("accepted_wall")) or "acceptance" in reason,
        "wall_touched": _bool_value(source.get("touched_wall")),
        "wall_rejected": _bool_value(source.get("rejected_wall")),
        "wall_accepted": _bool_value(source.get("accepted_wall")),
        "reason": reason,
        "leakage_warning": leakage_warning,
        "timing_warning": mode == "SAME_DAY_CONFIRMED_GURU_RULES" and reason != "timing_confirmed_same_day_filter",
        "sample_size_warning": False,
        "research_only": True,
    }


def _summarize_rule_group(
    *,
    rule_id: str,
    mode: str,
    rows: list[dict[str, Any]],
    rule: dict[str, Any],
) -> dict[str, Any]:
    returns = [_float_or_zero(row.get("future_return_points")) for row in rows]
    trade_rows = [row for row in rows if _bool_value(row.get("trade_candidate"))]
    blocked_rows = [row for row in rows if _bool_value(row.get("blocked_trade"))]
    wins = [value for value in returns if value > 0]
    avoided_losing = sum(1 for row in blocked_rows if _float_or_zero(row.get("future_return_points")) < 0)
    avoided_winning = sum(1 for row in blocked_rows if _float_or_zero(row.get("future_return_points")) > 0)
    event_count = len(rows)
    return {
        "rule_id": rule_id,
        "mode": mode,
        "rule_family": _text(rule.get("rule_family")),
        "rule_type": _text(rule.get("rule_type")),
        "event_count": event_count,
        "trade_candidate_count": len(trade_rows),
        "blocked_trade_count": len(blocked_rows),
        "win_rate": len(wins) / len(returns) if returns else None,
        "average_return": _mean(returns),
        "expectancy_proxy": _mean(returns),
        "profit_factor_proxy": _profit_factor_proxy(returns),
        "max_drawdown_proxy": _max_drawdown_proxy(returns),
        "avoided_losing_trade_count": avoided_losing,
        "avoided_winning_trade_count": avoided_winning,
        "net_filter_value_proxy": avoided_losing - avoided_winning,
        "false_block_rate": avoided_winning / len(blocked_rows) if blocked_rows else None,
        "breakout_followthrough_rate": _rate(rows, "level_accepted", "favorable_followthrough"),
        "rejection_followthrough_rate": _rate(rows, "level_rejected", "favorable_followthrough"),
        "wall_touch_rate": _bool_rate(rows, "wall_touched"),
        "wall_rejection_rate": _rate(rows, "wall_touched", "wall_rejected"),
        "wall_acceptance_rate": _rate(rows, "wall_touched", "wall_accepted"),
        "sample_size_warning": event_count < 30,
        "leakage_warning": _any_truthy(rows, "leakage_warning"),
        "timing_warning": _any_truthy(rows, "timing_warning"),
        "recommended_next_action": _next_action_for_summary(mode, event_count, rule),
    }


def _empty_summary_row(rule: dict[str, Any], *, mode: str) -> dict[str, Any]:
    return {
        "rule_id": _text(rule.get("rule_id")),
        "mode": mode,
        "rule_family": _text(rule.get("rule_family")),
        "rule_type": _text(rule.get("rule_type")),
        "event_count": 0,
        "trade_candidate_count": 0,
        "blocked_trade_count": 0,
        "win_rate": None,
        "average_return": 0.0,
        "expectancy_proxy": 0.0,
        "profit_factor_proxy": None,
        "max_drawdown_proxy": 0.0,
        "avoided_losing_trade_count": 0,
        "avoided_winning_trade_count": 0,
        "net_filter_value_proxy": 0.0,
        "false_block_rate": None,
        "breakout_followthrough_rate": None,
        "rejection_followthrough_rate": None,
        "wall_touch_rate": None,
        "wall_rejection_rate": None,
        "wall_acceptance_rate": None,
        "sample_size_warning": True,
        "leakage_warning": _text(rule.get("logic_source")) == "HISTORICAL_PLAYBOOK",
        "timing_warning": _text(rule.get("logic_source")) == "SAME_DAY_TIMING_CONFIRMED",
        "recommended_next_action": _next_action_for_summary(mode, 0, rule),
    }


def _validation_status_for_rule(
    *,
    spec: dict[str, str],
    required_data: list[str],
    can_same_day: bool,
) -> str:
    family = spec["rule_family"]
    if family == "PRICE_ONLY":
        return "READY_FOR_PRICE_ONLY_BACKTEST"
    if family in {"CME_MARKET_MAP", "CME_FILTER"}:
        if "cme_oi_by_strike" in required_data or "iv" in required_data:
            return "READY_FOR_CME_PILOT"
        return "WAIT_FOR_MORE_CME_DATA"
    if family == "GURU_SAME_DAY_FILTER":
        return "READY_FOR_CME_PILOT" if can_same_day else "WAIT_FOR_TRANSCRIPT_METADATA"
    return "CONTEXT_ONLY"


def _required_data_for_rule(spec: dict[str, str], dependency: dict[str, Any]) -> list[str]:
    family = spec["rule_family"]
    if family == "PRICE_ONLY":
        return ["ohlc"]
    if family == "GURU_SAME_DAY_FILTER":
        return ["transcript_timestamp", "same_day_playbook_matches"]
    data = ["ohlc"]
    if _bool_value(dependency.get("requires_basis")) or "WALL" in spec["rule_id"]:
        data.append("basis")
    if _bool_value(dependency.get("requires_cme_oi_by_strike")) or "OI" in spec["rule_id"]:
        data.append("cme_oi_by_strike")
    if _bool_value(dependency.get("requires_iv")) or "IV" in spec["rule_id"]:
        data.append("iv")
    return sorted(set(data))


def _mode_for_rule(rule: dict[str, Any]) -> str:
    family = _text(rule.get("rule_family"))
    if family == "PRICE_ONLY":
        return "PRICE_ONLY_RULES"
    if family in {"CME_MARKET_MAP", "CME_FILTER"}:
        return "CME_PILOT_RULES"
    if family == "GURU_SAME_DAY_FILTER":
        return "SAME_DAY_CONFIRMED_GURU_RULES"
    return "HISTORICAL_PLAYBOOK_RULES"


def _has_timing_confirmed_same_day(availability: pl.DataFrame) -> bool:
    if availability.is_empty():
        return False
    for row in availability.to_dicts():
        relation = _text(row.get("availability_relation"))
        if relation in {"PRE_SESSION", "DURING_SESSION"} and (
            _bool_value(row.get("can_use_as_same_session_filter"))
            or _bool_value(row.get("can_use_as_same_session_market_map"))
        ):
            return True
    return False


def _formation_leakage_warning(rule: dict[str, Any], rows: list[dict[str, Any]]) -> bool:
    source = _text(rule.get("logic_source"))
    first_seen = _date_text(rule.get("first_seen_date"))
    if source == "HISTORICAL_PLAYBOOK":
        return True
    if not first_seen or source == "MANUAL_RESEARCH_HYPOTHESIS":
        return False
    return any(_date_text(row.get("event_date")) < first_seen for row in rows)


def _formation_notes(rule: dict[str, Any], leakage: bool) -> str:
    source = _text(rule.get("logic_source"))
    if leakage and source == "HISTORICAL_PLAYBOOK":
        return "Historical playbook was extracted from the corpus; use only as retrospective context unless a clean later test period exists."
    if leakage:
        return "Rule has events before first_seen_date and must be excluded from predictive evidence."
    return "Rule is frozen before the test window in this diagnostic split."


def _filter_date_range(frame: pl.DataFrame, date_start: str | None, date_end: str | None) -> pl.DataFrame:
    if frame.is_empty() or not (date_start or date_end):
        return frame
    date_column = _date_column(frame)
    if not date_column:
        return frame
    filtered = frame
    if date_start:
        filtered = filtered.filter(pl.col(date_column).cast(pl.String).str.contains(r"\d{4}-\d{2}-\d{2}"))
        filtered = filtered.filter(pl.col(date_column).cast(pl.String).str.slice(0, 10) >= date_start)
    if date_end:
        filtered = filtered.filter(pl.col(date_column).cast(pl.String).str.slice(0, 10) <= date_end)
    return filtered


def _date_column(frame: pl.DataFrame) -> str:
    for column in ("timestamp", "trade_date", "event_timestamp", "date", "session_date"):
        if column in frame.columns:
            return column
    return ""


def _next_action_for_summary(mode: str, event_count: int, rule: dict[str, Any]) -> str:
    if mode == "SAME_DAY_CONFIRMED_GURU_RULES" and event_count == 0:
        return "WAIT_FOR_TRANSCRIPT_METADATA"
    if mode == "CME_PILOT_RULES" and event_count < 30:
        return "WAIT_FOR_MORE_CME_DATA_FOR_FULL_VALIDATION"
    if event_count < 30:
        return "EXTEND_SAMPLE_BEFORE_INTERPRETATION"
    if _text(rule.get("logic_source")) == "HISTORICAL_PLAYBOOK":
        return "USE_SEPARATE_TEST_PERIOD_BEFORE_PREDICTIVE_CLAIM"
    return "READY_FOR_RESEARCH_REVIEW"


def _ablation_notes(status: str) -> str:
    if status == "WAIT_FOR_TRANSCRIPT_METADATA":
        return "Same-day transcript timing is not confirmed, so this ablation stays inactive."
    if status == "WAIT_FOR_MORE_CME_DATA":
        return "CME sample is unavailable or too small for this ablation."
    return "Proxy comparison only; review sample size and leakage warnings."


def _best_and_weakest_rules(summary: pl.DataFrame) -> tuple[str, str]:
    if summary.is_empty():
        return "", ""
    eligible = summary.filter(pl.col("event_count") > 0)
    if eligible.is_empty():
        return "", ""
    sorted_rows = eligible.sort("expectancy_proxy").to_dicts()
    return _text(sorted_rows[-1].get("rule_id")), _text(sorted_rows[0].get("rule_id"))


def _blocked_rules(rule_library: pl.DataFrame) -> list[str]:
    blocked = []
    for row in rule_library.to_dicts() if not rule_library.is_empty() else []:
        status = _text(row.get("validation_status"))
        if status.startswith("WAIT_"):
            blocked.append(_text(row.get("rule_id")))
    return blocked


def _ready_now_lines(result: GuruRuleBacktestLabResult) -> list[str]:
    price_ready = result.guru_rule_library.filter(pl.col("can_backtest_price_only")).height
    cme_ready = result.guru_rule_library.filter(pl.col("can_backtest_cme_pilot")).height
    same_day_ready = result.guru_rule_library.filter(pl.col("can_backtest_same_day_signal")).height
    return [
        f"- Price-only rules ready now: `{price_ready}`",
        f"- CME pilot rules ready now: `{cme_ready}`",
        f"- Same-day transcript signal rules ready now: `{same_day_ready}`",
        "- Same-day transcript rules remain blocked unless timing is PRE_SESSION or DURING_SESSION.",
        "- Full validation needs more CME history and a clean formation/test split.",
    ]


def _cme_return_proxy(row: dict[str, Any]) -> float:
    if _bool_value(row.get("rejected_wall")):
        return 1.0
    if _bool_value(row.get("accepted_wall")):
        return 1.0
    if _bool_value(row.get("broke_range")):
        return 0.5
    if _bool_value(row.get("stayed_inside_range")):
        return -0.25
    return 0.0


def _filter_value(rows: list[dict[str, Any]]) -> float:
    avoided_losing = sum(1 for row in rows if _bool_value(row.get("blocked_trade")) and _float_or_zero(row.get("future_return_points")) < 0)
    avoided_winning = sum(1 for row in rows if _bool_value(row.get("blocked_trade")) and _float_or_zero(row.get("future_return_points")) > 0)
    return float(avoided_losing - avoided_winning)


def _rate(rows: list[dict[str, Any]], denominator_key: str, numerator_key: str) -> float | None:
    denom = [row for row in rows if _bool_value(row.get(denominator_key))]
    if not denom:
        return None
    return sum(1 for row in denom if _bool_value(row.get(numerator_key))) / len(denom)


def _bool_rate(rows: list[dict[str, Any]], key: str) -> float | None:
    if not rows:
        return None
    return sum(1 for row in rows if _bool_value(row.get(key))) / len(rows)


def _profit_factor_proxy(values: list[float]) -> float | None:
    gains = sum(value for value in values if value > 0)
    losses = abs(sum(value for value in values if value < 0))
    if losses == 0:
        return None
    return gains / losses


def _max_drawdown_proxy(values: list[float]) -> float:
    peak = 0.0
    equity = 0.0
    max_dd = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    return max_dd


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _any_truthy(rows: list[dict[str, Any]], key: str) -> bool:
    return any(_bool_value(row.get(key)) for row in rows)


def _midpoint_date(dates: list[str]) -> str:
    if not dates:
        return ""
    return dates[len(dates) // 2]


def _next_date_text(value: str) -> str:
    parsed = _parse_date(value)
    if parsed is None:
        return ""
    # Keep implementation simple and deterministic without business calendars.
    return date.fromordinal(parsed.toordinal() + 1).isoformat()


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _filter_mode(frame: pl.DataFrame, mode: str) -> pl.DataFrame:
    if frame.is_empty() or "mode" not in frame.columns:
        return pl.DataFrame()
    return frame.filter(pl.col("mode") == mode)


def _group_event_rows(frame: pl.DataFrame, columns: tuple[str, ...]) -> dict[tuple[Any, ...], list[dict[str, Any]]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    if frame.is_empty():
        return groups
    for row in frame.to_dicts():
        key = tuple(row.get(column) for column in columns)
        groups.setdefault(key, []).append(row)
    return groups


def _state_counts(frame: pl.DataFrame, column: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    if frame.is_empty() or column not in frame.columns:
        return counts
    for value in frame.get_column(column).to_list():
        key = _text(value)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _rows_by_key(frame: pl.DataFrame, column: str) -> dict[str, dict[str, Any]]:
    if frame.is_empty() or column not in frame.columns:
        return {}
    rows = {}
    for row in frame.to_dicts():
        key = _text(row.get(column))
        if key:
            rows[key] = row
    return rows


def _load_optional(path: Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    try:
        if path.suffix.lower() == ".parquet":
            return pl.read_parquet(path)
        return pl.read_csv(path, infer_schema_length=1000)
    except Exception:
        return pl.DataFrame()


def _frame(inputs: dict[str, pl.DataFrame], name: str) -> pl.DataFrame:
    value = inputs.get(name)
    return value if isinstance(value, pl.DataFrame) else pl.DataFrame()


def _timestamp_text(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""
    try:
        if isinstance(value, datetime):
            return value.isoformat()
    except TypeError:
        pass
    return _redact_text(text)


def _date_text(value: Any) -> str:
    match = re.search(r"20\d{2}-\d{2}-\d{2}", str(value or ""))
    return match.group(0) if match else ""


def _float_or_none(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _float_or_zero(value: Any) -> float:
    try:
        if value in (None, ""):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    return text not in {"", "0", "false", "f", "no", "n", "none", "null", "nan"}


def _text(value: Any) -> str:
    return _redact_text(str(value or "").strip())


def _redact_text(text: str) -> str:
    text = re.sub(r"[A-Za-z]:[\\/]+Users[\\/]+[^`|\s,\"]+", "<REDACTED_PATH>", text)
    text = re.sub(r"[A-Za-z]:[\\/]+[^`|\s,\"]+", "<REDACTED_PATH>", text)
    text = re.sub(r"/Users/[^`|\s,\"]+", "<REDACTED_PATH>", text)
    return text


def _rows_frame(rows: list[dict[str, Any]], schema: dict[str, Any]) -> pl.DataFrame:
    if not rows:
        return pl.DataFrame(schema=schema)
    frame = pl.DataFrame(rows, infer_schema_length=None)
    for column, dtype in schema.items():
        if column not in frame.columns:
            frame = frame.with_columns(pl.lit(None).cast(dtype).alias(column))
        else:
            frame = frame.with_columns(pl.col(column).cast(dtype, strict=False))
    return frame.select(list(schema))


def _frame_markdown(frame: pl.DataFrame, *, limit: int = 30) -> str:
    if frame.is_empty():
        return "_No rows._"
    columns = frame.columns
    rows = ["| " + " | ".join(columns) + " |", "|" + "|".join(["---"] * len(columns)) + "|"]
    for raw in frame.head(limit).to_dicts():
        rows.append("| " + " | ".join(_markdown_cell(raw.get(column, "")) for column in columns) + " |")
    return "\n".join(rows)


def _markdown_cell(value: Any) -> str:
    return _redact_text(str(value).replace("|", "\\|").replace("\n", " "))[:700]


def _safe_report(text: str) -> str:
    lowered = text.lower()
    for phrase in FORBIDDEN_REPORT_PHRASES:
        if phrase in lowered:
            raise ValueError(f"Forbidden report phrase: {phrase}")
    if re.search(r"[A-Za-z]:[\\/]+Users[\\/]+", text):
        raise ValueError("Report contains an unredacted local source path.")
    return _redact_text(text)


def _yaml_quote(value: Any) -> str:
    text = _redact_text(str(value or ""))
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _write_bar_svg(path: Path, *, title: str, labels: list[str], values: list[float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    width, height = 900, 300
    if not values:
        path.write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}"><text x="20" y="40">{title}: no data</text></svg>',
            encoding="utf-8",
        )
        return
    max_value = max(abs(value) for value in values) or 1.0
    bar_width = max(8, int((width - 80) / max(len(values), 1)))
    zero_y = height / 2
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
        f'<text x="20" y="24" font-size="16">{title}</text>',
        f'<line x1="50" x2="{width - 20}" y1="{zero_y}" y2="{zero_y}" stroke="#777"/>',
    ]
    for index, value in enumerate(values):
        x = 50 + index * bar_width
        h = abs(value) / max_value * (height / 2 - 50)
        y = zero_y - h if value >= 0 else zero_y
        fill = "#3b82f6" if value >= 0 else "#ef4444"
        parts.append(f'<rect x="{x}" y="{y}" width="{bar_width - 2}" height="{h}" fill="{fill}"/>')
        if index < 18:
            parts.append(
                f'<text x="{x}" y="{height - 10}" font-size="8" transform="rotate(45 {x},{height - 10})">{_redact_text(labels[index])[:18]}</text>'
            )
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def _rule_library_schema() -> dict[str, Any]:
    return {
        "rule_id": pl.String,
        "rule_name": pl.String,
        "rule_family": pl.String,
        "logic_source": pl.String,
        "rule_type": pl.String,
        "required_data": pl.String,
        "condition": pl.String,
        "action": pl.String,
        "invalidation": pl.String,
        "target": pl.String,
        "can_backtest_price_only": pl.Boolean,
        "can_backtest_cme_pilot": pl.Boolean,
        "can_backtest_same_day_signal": pl.Boolean,
        "leakage_risk": pl.String,
        "validation_status": pl.String,
        "first_seen_date": pl.String,
        "source_logic_id": pl.String,
    }


def _event_schema() -> dict[str, Any]:
    return {
        "event_timestamp": pl.String,
        "event_date": pl.String,
        "period": pl.String,
        "mode": pl.String,
        "rule_id": pl.String,
        "event_type": pl.String,
        "trade_candidate": pl.Boolean,
        "blocked_trade": pl.Boolean,
        "future_return_points": pl.Float64,
        "favorable_followthrough": pl.Boolean,
        "level_touched": pl.Boolean,
        "level_rejected": pl.Boolean,
        "level_accepted": pl.Boolean,
        "wall_touched": pl.Boolean,
        "wall_rejected": pl.Boolean,
        "wall_accepted": pl.Boolean,
        "reason": pl.String,
        "leakage_warning": pl.Boolean,
        "timing_warning": pl.Boolean,
        "sample_size_warning": pl.Boolean,
        "research_only": pl.Boolean,
    }


def _summary_schema() -> dict[str, Any]:
    return {
        "rule_id": pl.String,
        "mode": pl.String,
        "rule_family": pl.String,
        "rule_type": pl.String,
        "event_count": pl.Int64,
        "trade_candidate_count": pl.Int64,
        "blocked_trade_count": pl.Int64,
        "win_rate": pl.Float64,
        "average_return": pl.Float64,
        "expectancy_proxy": pl.Float64,
        "profit_factor_proxy": pl.Float64,
        "max_drawdown_proxy": pl.Float64,
        "avoided_losing_trade_count": pl.Int64,
        "avoided_winning_trade_count": pl.Int64,
        "net_filter_value_proxy": pl.Float64,
        "false_block_rate": pl.Float64,
        "breakout_followthrough_rate": pl.Float64,
        "rejection_followthrough_rate": pl.Float64,
        "wall_touch_rate": pl.Float64,
        "wall_rejection_rate": pl.Float64,
        "wall_acceptance_rate": pl.Float64,
        "sample_size_warning": pl.Boolean,
        "leakage_warning": pl.Boolean,
        "timing_warning": pl.Boolean,
        "recommended_next_action": pl.String,
    }


def _by_period_schema() -> dict[str, Any]:
    return {
        "period": pl.String,
        "mode": pl.String,
        "event_count": pl.Int64,
        "trade_candidate_count": pl.Int64,
        "blocked_trade_count": pl.Int64,
        "average_return": pl.Float64,
        "expectancy_proxy": pl.Float64,
        "sample_size_warning": pl.Boolean,
        "timing_warning": pl.Boolean,
        "leakage_warning": pl.Boolean,
    }


def _formation_schema() -> dict[str, Any]:
    return {
        "rule_id": pl.String,
        "logic_source": pl.String,
        "first_seen_date": pl.String,
        "date_start": pl.String,
        "date_end": pl.String,
        "formation_start": pl.String,
        "formation_end": pl.String,
        "test_start": pl.String,
        "test_end": pl.String,
        "formation_event_count": pl.Int64,
        "test_event_count": pl.Int64,
        "rules_frozen_before_test": pl.Boolean,
        "sample_size_warning": pl.Boolean,
        "leakage_warning": pl.Boolean,
        "notes": pl.String,
    }


def _ablation_schema() -> dict[str, Any]:
    return {
        "scenario": pl.String,
        "included_modes": pl.String,
        "included_rules": pl.String,
        "event_count": pl.Int64,
        "blocked_trade_count": pl.Int64,
        "average_return": pl.Float64,
        "expectancy_proxy": pl.Float64,
        "net_filter_value_proxy": pl.Float64,
        "status": pl.String,
        "sample_size_warning": pl.Boolean,
        "notes": pl.String,
    }


def _scorecard_schema() -> dict[str, Any]:
    return {
        "date_start": pl.String,
        "date_end": pl.String,
        "data_available": pl.String,
        "rule_modes_available": pl.String,
        "best_supported_rule": pl.String,
        "weakest_rule": pl.String,
        "rules_blocked_by_missing_data": pl.String,
        "whether_metadata_is_needed": pl.Boolean,
        "whether_more_cme_is_needed": pl.Boolean,
        "whether_result_is_pilot_only": pl.Boolean,
    }


def main() -> None:
    """CLI entry point."""

    result = run_guru_rule_backtest_lab()
    print(f"final_recommendation: {result.final_recommendation}")
    print(f"rules_compiled: {result.guru_rule_library.height}")
    print(f"events: {result.guru_rule_backtest_events.height}")


if __name__ == "__main__":
    main()
