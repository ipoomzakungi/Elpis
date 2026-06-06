"""CME-overlap Pine/Python backtest lab.

This module runs a focused, research-only comparison on dates where local
Dukascopy XAUUSD price data overlaps with CME/QuikStrike context. CME OI/IV and
guru rows are treated as filters/context, not standalone direction triggers.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

import polars as pl


SOURCE_PRIORITY = (
    "TRADINGVIEW_TRADE_CSV",
    "PYTHON_PINE_LIKE",
    "PRICE_RULE",
    "MANUAL_RESEARCH",
)
FILTER_SCENARIOS = (
    "RAW_CANDIDATES",
    "PRICE_ONLY_FILTERS",
    "CME_WALL_FILTER_ONLY",
    "CME_IV_RANGE_FILTER_ONLY",
    "GURU_FILTER_ONLY",
    "FEE_SPREAD_HURDLE_ONLY",
    "COMBINED_CONSERVATIVE_FILTER",
)
PILOT_GRADES = (
    "FULL_CME_PILOT",
    "OI_ONLY_PILOT",
    "IV_ONLY_PILOT",
    "PRICE_ONLY",
    "UNUSABLE",
)
PILOT_DECISION_LABELS = (
    "CME_FILTER_HELPED_IN_PILOT",
    "CME_FILTER_NOT_HELPFUL_YET",
    "GURU_FILTER_HELPED_IN_PILOT",
    "PRICE_FILTER_HELPED_IN_PILOT",
    "COMBINED_FILTER_PROMISING",
    "INSUFFICIENT_SAMPLE",
    "NEED_MORE_CME_DAYS",
    "NOT_READY_FOR_MONEY",
)
RESEARCH_WARNING = (
    "Research-only CME-overlap pilot. It does not optimize parameters, does not "
    "change frozen score v1, and does not create trading readiness."
)
PILOT_WARNING = "CME OI/IV remains pilot-only; guru context remains filter/playbook context."
WALL_PROXIMITY_POINTS = 10.0
MIN_PILOT_CANDIDATES = 30
FORBIDDEN_REPORT_PHRASES = (
    " buy ",
    " sell ",
    "profitable",
    "profitability",
    "guaranteed edge",
    "predicts price",
    "safe to trade",
    "live ready",
    "paper ready",
    "validated money edge",
)


@dataclass(frozen=True)
class CmeOverlapBacktestLabResult:
    """Frames and artifacts emitted by the CME-overlap backtest lab."""

    date_audit: pl.DataFrame
    candidate_source_report: pl.DataFrame
    candidates: pl.DataFrame
    filter_backtest: pl.DataFrame
    wall_effect: pl.DataFrame
    iv_effect: pl.DataFrame
    guru_effect: pl.DataFrame
    pilot_decision: pl.DataFrame
    replay_markdown_path: Path
    replay_html_path: Path
    final_decision: str
    paths: dict[str, Path]


def run_cme_overlap_backtest_lab(
    *,
    output_dir: str | Path = "outputs",
    write_outputs: bool = True,
) -> CmeOverlapBacktestLabResult:
    """Run the CME-overlap pilot and optionally write artifacts."""

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "charts").mkdir(parents=True, exist_ok=True)
    paths = _output_paths(output_root)
    inputs = _load_inputs(paths)

    date_audit = build_cme_overlap_date_audit(inputs=inputs)
    source_report = build_candidate_source_report(inputs=inputs, date_audit=date_audit)
    candidates = build_cme_overlap_trade_candidates(
        inputs=inputs,
        date_audit=date_audit,
        candidate_source_report=source_report,
    )
    filter_backtest = build_filter_overlay_backtest(candidates)
    wall_effect = build_cme_wall_filter_effect(candidates)
    iv_effect = build_cme_iv_range_filter_effect(candidates)
    guru_effect = build_guru_filter_effect(candidates)
    pilot_decision = build_cme_overlap_pilot_decision(
        date_audit=date_audit,
        candidate_source_report=source_report,
        candidates=candidates,
        filter_backtest=filter_backtest,
        wall_effect=wall_effect,
        iv_effect=iv_effect,
        guru_effect=guru_effect,
    )
    final_decision = _first_text(pilot_decision, "final_label", "INSUFFICIENT_SAMPLE")
    result = CmeOverlapBacktestLabResult(
        date_audit=date_audit,
        candidate_source_report=source_report,
        candidates=candidates,
        filter_backtest=filter_backtest,
        wall_effect=wall_effect,
        iv_effect=iv_effect,
        guru_effect=guru_effect,
        pilot_decision=pilot_decision,
        replay_markdown_path=paths["replay_md"],
        replay_html_path=paths["replay_html"],
        final_decision=final_decision,
        paths=paths,
    )
    if write_outputs:
        write_cme_overlap_backtest_outputs(result)
    return result


def build_cme_overlap_date_audit(*, inputs: dict[str, Any]) -> pl.DataFrame:
    """Audit which CME dates can support each pilot layer."""

    price_by_timeframe = inputs.get("price_by_timeframe", {})
    cme_oi = _frame_input(inputs, "cme_oi")
    cme_iv = _frame_input(inputs, "cme_iv")
    futures = _frame_input(inputs, "cme_futures")
    basis = _frame_input(inputs, "basis")
    guru_replay = _frame_input(inputs, "guru_replay")
    overlap_validation = _frame_input(inputs, "overlap_validation")
    pine_signals = _frame_input(inputs, "pine_signals")
    python_trades = _python_candidate_frame(inputs)
    tradingview = _frame_input(inputs, "tradingview_trades")

    dates = _cme_overlap_dates(inputs)
    rows: list[dict[str, Any]] = []
    price_dates = {
        timeframe: _date_values(frame)
        for timeframe, frame in price_by_timeframe.items()
        if isinstance(frame, pl.DataFrame)
    }
    all_price_dates = set().union(*price_dates.values()) if price_dates else set()
    for trade_date in sorted(dates):
        has_price = trade_date in all_price_dates
        has_oi = _date_has_row(cme_oi, trade_date) or _validation_flag(
            overlap_validation,
            trade_date,
            "has_cme_oi",
        )
        has_iv = _date_has_row(cme_iv, trade_date) or _validation_flag(
            overlap_validation,
            trade_date,
            "has_cme_iv",
        )
        has_basis = _date_has_row(basis, trade_date) or _validation_flag(
            overlap_validation,
            trade_date,
            "basis_available",
        )
        has_guru = _date_has_row(guru_replay, trade_date) or _date_has_row(
            _frame_input(inputs, "same_day_filter"),
            trade_date,
        )
        has_pine = _date_has_row(pine_signals, trade_date) or _date_has_row(
            python_trades,
            trade_date,
        )
        has_tv = _date_has_row(tradingview, trade_date)
        has_oi_change = _has_numeric_or_truthy(
            cme_oi,
            trade_date,
            ("oi_change", "open_interest_change", "change", "oi_change_near_wall"),
        ) or _truthy_context_flag(guru_replay, trade_date, "oi_change_available")
        has_option_volume = _has_numeric_or_truthy(
            cme_oi,
            trade_date,
            ("volume", "option_volume", "volume_change", "option_volume_near_wall"),
        ) or _truthy_context_flag(guru_replay, trade_date, "option_volume_available")
        has_futures = _date_has_row(futures, trade_date) or _truthy_context_flag(
            guru_replay,
            trade_date,
            "futures_available",
        )
        has_candidate = has_tv or has_pine or _date_has_row(_frame_input(inputs, "score_rows"), trade_date)
        missing = _missing_components(
            {
                "dukascopy_price": has_price,
                "cme_oi": has_oi,
                "cme_iv": has_iv,
                "basis": has_basis,
                "trade_candidate_source": has_candidate,
            }
        )
        rows.append(
            {
                "trade_date": trade_date,
                "has_dukascopy_price": has_price,
                "has_cme_oi": has_oi,
                "has_cme_iv": has_iv,
                "has_oi_change": has_oi_change,
                "has_option_volume": has_option_volume,
                "has_basis": has_basis,
                "has_guru_context": has_guru,
                "has_python_pine_signal": has_pine,
                "has_tradingview_trade_csv": has_tv,
                "can_run_price_only_baseline": has_price and has_candidate,
                "can_run_python_pine_backtest": has_price and has_pine,
                "can_run_cme_filter_test": has_price and (has_oi or has_iv) and has_candidate,
                "can_run_guru_filter_test": has_price and has_guru and has_candidate,
                "can_run_combined_test": has_price
                and has_candidate
                and (has_oi or has_iv)
                and has_guru,
                "missing_components": ";".join(missing),
                "pilot_grade": _pilot_grade(
                    has_price=has_price,
                    has_oi=has_oi,
                    has_iv=has_iv,
                    has_basis=has_basis,
                ),
                "has_cme_futures": has_futures,
            }
        )
    return _frame(rows, _date_audit_schema())


def build_candidate_source_report(
    *,
    inputs: dict[str, Any],
    date_audit: pl.DataFrame,
) -> pl.DataFrame:
    """Select a candidate source using the fixed priority order."""

    cme_dates = _usable_dates(date_audit)
    sources = {
        "TRADINGVIEW_TRADE_CSV": _frame_input(inputs, "tradingview_trades"),
        "PYTHON_PINE_LIKE": _python_candidate_frame(inputs),
        "PRICE_RULE": _frame_input(inputs, "score_rows"),
        "MANUAL_RESEARCH": pl.DataFrame(),
    }
    counts = {source: _count_rows_on_dates(frame, cme_dates) for source, frame in sources.items()}
    selected_source = next((source for source in SOURCE_PRIORITY if counts[source] > 0), "")
    rows = []
    for source in SOURCE_PRIORITY:
        frame = sources[source]
        rows.append(
            {
                "candidate_source": source,
                "available": counts[source] > 0,
                "trade_count_on_cme_dates": counts[source],
                "date_range": _date_range_text(frame, cme_dates),
                "limitations": _source_limitations(source, counts[source]),
                "selected_for_backtest": source == selected_source,
            }
        )
    return _frame(rows, _source_report_schema())


def build_cme_overlap_trade_candidates(
    *,
    inputs: dict[str, Any],
    date_audit: pl.DataFrame,
    candidate_source_report: pl.DataFrame,
) -> pl.DataFrame:
    """Normalize the selected source into event-level research candidates."""

    selected = _selected_candidate_source(candidate_source_report)
    cme_dates = _usable_dates(date_audit)
    if selected == "TRADINGVIEW_TRADE_CSV":
        rows = _candidates_from_trade_frame(
            _frame_input(inputs, "tradingview_trades"),
            source="TRADINGVIEW_TRADE_CSV",
            cme_dates=cme_dates,
            inputs=inputs,
        )
    elif selected == "PYTHON_PINE_LIKE":
        rows = _candidates_from_python(inputs=inputs, cme_dates=cme_dates)
    elif selected == "PRICE_RULE":
        rows = _candidates_from_score_rows(
            _frame_input(inputs, "score_rows"),
            cme_dates=cme_dates,
            inputs=inputs,
        )
    else:
        rows = []
    for index, row in enumerate(rows, start=1):
        row["candidate_id"] = f"CME_CAND_{index:05d}"
    return _frame(rows, _candidate_schema())


def build_filter_overlay_backtest(candidates: pl.DataFrame) -> pl.DataFrame:
    """Compare fixed filters on the same candidate set."""

    normalized = _normalize_candidates(candidates)
    rows = []
    for scenario in FILTER_SCENARIOS:
        allowed = [_scenario_allows(row, scenario) for row in normalized.to_dicts()]
        rows.append(_filter_metric_row(normalized, scenario, allowed))
    return _frame(rows, _filter_backtest_schema())


def build_cme_wall_filter_effect(candidates: pl.DataFrame) -> pl.DataFrame:
    """Measure candidate behavior around CME wall context."""

    frame = _normalize_candidates(candidates)
    rows = []
    case_rows = {
        "DIRECTLY_INTO_WALL": [],
        "AWAY_FROM_WALL": [],
        "ACCEPTANCE_THROUGH_WALL": [],
        "REJECTION_FROM_WALL": [],
        "WALL_CONTEXT_MISSING": [],
    }
    for row in frame.to_dicts():
        case_rows[_wall_case(row)].append(row)
    overall_interpretation = _wall_interpretation(case_rows)
    for case, items in case_rows.items():
        returns = [_float(item.get("raw_pnl")) for item in items if _float(item.get("raw_pnl")) is not None]
        rows.append(
            {
                "case_type": case,
                "candidate_count": len(items),
                "trades_directly_into_wall": len(case_rows["DIRECTLY_INTO_WALL"]),
                "trades_away_from_wall": len(case_rows["AWAY_FROM_WALL"]),
                "trades_after_acceptance_through_wall": len(case_rows["ACCEPTANCE_THROUGH_WALL"]),
                "trades_after_rejection_from_wall": len(case_rows["REJECTION_FROM_WALL"]),
                "wall_touch_count": _wall_touch_count(frame),
                "wall_rejection_count": _truthy_count(frame, "rejection_after_touch_component"),
                "wall_acceptance_count": _truthy_count(frame, "acceptance_breakout_active"),
                "pnl_or_return_by_case": _average(returns),
                "interpretation": overall_interpretation if items else "INSUFFICIENT_SAMPLE",
            }
        )
    return _frame(rows, _wall_effect_schema())


def build_cme_iv_range_filter_effect(candidates: pl.DataFrame) -> pl.DataFrame:
    """Measure candidate behavior by IV/range context."""

    frame = _normalize_candidates(candidates)
    rows = []
    case_rows = {
        "INSIDE_IV_EXPECTED_RANGE": [],
        "NEAR_1SD_EDGE": [],
        "BEYOND_2SD": [],
        "IV_MISSING": [],
    }
    for row in frame.to_dicts():
        case_rows[_iv_case(row)].append(row)
    interpretation = _iv_interpretation(case_rows)
    for case, items in case_rows.items():
        returns = [_float(item.get("raw_pnl")) for item in items if _float(item.get("raw_pnl")) is not None]
        rows.append(
            {
                "case_type": case,
                "candidate_count": len(items),
                "trades_inside_iv_expected_range": len(case_rows["INSIDE_IV_EXPECTED_RANGE"]),
                "trades_near_1sd_edge": len(case_rows["NEAR_1SD_EDGE"]),
                "trades_beyond_2sd": len(case_rows["BEYOND_2SD"]),
                "trades_when_iv_missing": len(case_rows["IV_MISSING"]),
                "range_followthrough": _rate([value > 0 for value in returns]),
                "mean_reversion_behavior": _rate([value <= 0 for value in returns]),
                "pnl_or_return_by_case": _average(returns),
                "interpretation": interpretation if items else "INSUFFICIENT_SAMPLE",
            }
        )
    return _frame(rows, _iv_effect_schema())


def build_guru_filter_effect(candidates: pl.DataFrame) -> pl.DataFrame:
    """Measure guru context as filter/playbook context only."""

    frame = _normalize_candidates(candidates)
    rows = []
    case_rows = {
        "SAME_DAY_TIMING_CONFIRMED": [],
        "HISTORICAL_PLAYBOOK_ONLY": [],
        "BLOCKED_BY_GURU_FILTER": [],
        "GURU_CONTEXT_MISSING": [],
    }
    for row in frame.to_dicts():
        case_rows[_guru_case(row)].append(row)
    interpretation = _guru_interpretation(case_rows)
    for case, items in case_rows.items():
        blocked = [item for item in items if not _guru_filter_allows(item)]
        returns = [_float(item.get("raw_pnl")) for item in items if _float(item.get("raw_pnl")) is not None]
        blocked_returns = [
            _float(item.get("raw_pnl"))
            for item in blocked
            if _float(item.get("raw_pnl")) is not None
        ]
        rows.append(
            {
                "case_type": case,
                "candidate_count": len(items),
                "candidates_with_same_day_timing_confirmed_guru_context": len(
                    case_rows["SAME_DAY_TIMING_CONFIRMED"]
                ),
                "candidates_with_historical_playbook_only": len(case_rows["HISTORICAL_PLAYBOOK_ONLY"]),
                "candidates_blocked_by_guru_filter": len(case_rows["BLOCKED_BY_GURU_FILTER"]),
                "avoided_losing_candidates": len([value for value in blocked_returns if value <= 0]),
                "blocked_winning_candidates": len([value for value in blocked_returns if value > 0]),
                "net_filter_value_proxy": sum(-value for value in blocked_returns),
                "pnl_or_return_by_case": _average(returns),
                "interpretation": interpretation if items else "INSUFFICIENT_SAMPLE",
            }
        )
    return _frame(rows, _guru_effect_schema())


def build_cme_overlap_pilot_decision(
    *,
    date_audit: pl.DataFrame,
    candidate_source_report: pl.DataFrame,
    candidates: pl.DataFrame,
    filter_backtest: pl.DataFrame,
    wall_effect: pl.DataFrame,
    iv_effect: pl.DataFrame,
    guru_effect: pl.DataFrame,
) -> pl.DataFrame:
    """Create the conservative final pilot decision without validation claims."""

    usable_dates = _usable_dates(date_audit)
    candidate_count = candidates.height
    combined = _scenario_row(filter_backtest, "COMBINED_CONSERVATIVE_FILTER")
    raw = _scenario_row(filter_backtest, "RAW_CANDIDATES")
    sample_tiny = len(usable_dates) < MIN_PILOT_CANDIDATES or candidate_count < MIN_PILOT_CANDIDATES
    combined_value = _float(combined.get("net_filter_value_proxy")) or 0.0
    raw_avg = _float(raw.get("average_return"))
    combined_avg = _float(combined.get("average_return"))
    source = _selected_candidate_source(candidate_source_report) or "NONE"
    if sample_tiny:
        final = "INSUFFICIENT_SAMPLE"
        supporting = "NEED_MORE_CME_DAYS;NOT_READY_FOR_MONEY"
    elif combined_value > 0 and combined_avg is not None and raw_avg is not None and combined_avg >= raw_avg:
        final = "COMBINED_FILTER_PROMISING"
        supporting = "CME_FILTER_HELPED_IN_PILOT;GURU_FILTER_HELPED_IN_PILOT;NOT_READY_FOR_MONEY"
    else:
        final = "CME_FILTER_NOT_HELPFUL_YET"
        supporting = "NEED_MORE_CME_DAYS;NOT_READY_FOR_MONEY"
    rows = [
        {
            "final_label": final,
            "supporting_labels": supporting,
            "selected_candidate_source": source,
            "overlap_date_count": len(usable_dates),
            "candidate_count": candidate_count,
            "combined_allowed_count": _int(combined.get("allowed_count")),
            "raw_average_return": raw_avg,
            "combined_average_return": combined_avg,
            "wall_interpretation": _dominant_interpretation(wall_effect, "interpretation"),
            "iv_interpretation": _dominant_interpretation(iv_effect, "interpretation"),
            "guru_interpretation": _dominant_interpretation(guru_effect, "interpretation"),
            "sample_size_warning": sample_tiny,
            "pilot_warning": PILOT_WARNING,
            "money_readiness": "NOT_READY_FOR_MONEY",
            "plain_english_summary": (
                "CME-overlap evidence is a pilot only. Current result should be used "
                "to inspect filters and collect more CME days, not to validate a strategy."
            ),
        }
    ]
    return _frame(rows, _pilot_decision_schema())


def write_cme_overlap_backtest_outputs(result: CmeOverlapBacktestLabResult) -> None:
    """Write all CME-overlap CSV, Markdown, and replay artifacts."""

    result.date_audit.write_csv(result.paths["date_audit_csv"])
    result.candidate_source_report.write_csv(result.paths["source_report_csv"])
    result.candidates.write_csv(result.paths["candidates_csv"])
    result.filter_backtest.write_csv(result.paths["filter_backtest_csv"])
    result.wall_effect.write_csv(result.paths["wall_effect_csv"])
    result.iv_effect.write_csv(result.paths["iv_effect_csv"])
    result.guru_effect.write_csv(result.paths["guru_effect_csv"])
    result.pilot_decision.write_csv(result.paths["pilot_decision_csv"])

    markdown_pairs = {
        "date_audit_md": _date_audit_markdown(result),
        "source_report_md": _source_report_markdown(result),
        "candidates_md": _candidates_markdown(result),
        "filter_backtest_md": _filter_backtest_markdown(result),
        "wall_effect_md": _wall_effect_markdown(result),
        "iv_effect_md": _iv_effect_markdown(result),
        "guru_effect_md": _guru_effect_markdown(result),
        "pilot_decision_md": _pilot_decision_markdown(result),
        "replay_md": _replay_markdown(result),
    }
    for key, text in markdown_pairs.items():
        result.paths[key].write_text(_safe_report_text(text), encoding="utf-8")
    result.paths["replay_html"].write_text(_safe_report_text(_replay_html(result)), encoding="utf-8")


def cme_overlap_backtest_report_lines(result: CmeOverlapBacktestLabResult | None) -> list[str]:
    """Return report sections for research_report.md."""

    if result is None:
        return [
            "## CME Overlap Backtest Lab",
            "",
            "CME-overlap Pine/Python backtest lab was not run.",
        ]
    return [
        "## CME Overlap Backtest Lab",
        "",
        RESEARCH_WARNING,
        "",
        f"- Final pilot decision: `{result.final_decision}`",
        f"- Selected candidate source: `{_selected_candidate_source(result.candidate_source_report) or 'NONE'}`",
        f"- Candidate count: {result.candidates.height}",
        "- Guardrail: `NOT_READY_FOR_MONEY`",
        "",
        "## CME Overlap Date Audit",
        "",
        _frame_markdown(result.date_audit),
        "",
        "## Candidate Source Selection",
        "",
        _frame_markdown(result.candidate_source_report),
        "",
        "## CME/Guru Filter Backtest",
        "",
        _frame_markdown(result.filter_backtest),
        "",
        "## CME Wall Effect",
        "",
        _frame_markdown(result.wall_effect),
        "",
        "## IV Range Effect",
        "",
        _frame_markdown(result.iv_effect),
        "",
        "## Guru Filter Effect",
        "",
        _frame_markdown(result.guru_effect),
        "",
        "## CME Overlap Visual Replay",
        "",
        "- Replay artifact: `outputs/charts/cme_overlap_replay.html`",
        "- Replay markdown: `outputs/cme_overlap_replay.md`",
        "",
        "## Pilot Decision",
        "",
        _frame_markdown(result.pilot_decision),
    ]


def report_text_is_safe(text: str) -> bool:
    """Return true when generated text avoids restricted claim/instruction phrases."""

    lowered = f" {text.lower()} "
    return not any(phrase in lowered for phrase in FORBIDDEN_REPORT_PHRASES) and "C:\\" not in text


def _load_inputs(paths: dict[str, Path]) -> dict[str, Any]:
    price_by_timeframe = {
        timeframe: _read_optional(paths[f"price_{timeframe}"])
        for timeframe in ("15m", "30m", "1h", "4h", "1d")
    }
    return {
        "price_by_timeframe": price_by_timeframe,
        "cme_oi": _read_optional(paths["cme_oi"]),
        "cme_iv": _read_optional(paths["cme_iv"]),
        "cme_futures": _read_optional(paths["cme_futures"]),
        "basis": _read_optional(paths["basis"]),
        "guru_replay": _read_optional(paths["guru_replay"]),
        "overlap_validation": _read_optional(paths["overlap_validation"]),
        "pine_signals": _read_optional(paths["pine_signals"]),
        "python_trades": _read_optional(paths["python_trades"]),
        "python_overlay_trades": _read_optional(paths["python_overlay_trades"]),
        "tradingview_trades": _read_optional(paths["tradingview_trades"]),
        "score_rows": _read_optional(paths["score_rows"]),
        "guru_knowledge": _read_optional(paths["guru_knowledge"]),
        "same_day_filter": _read_optional(paths["same_day_filter"]),
        "same_day_market_map": _read_optional(paths["same_day_market_map"]),
        "market_map": _read_optional(paths["market_map"]),
    }


def _output_paths(output_root: Path) -> dict[str, Path]:
    charts = output_root / "charts"
    return {
        "price_15m": output_root / "dukascopy_xau_15m.parquet",
        "price_30m": output_root / "dukascopy_xau_30m.parquet",
        "price_1h": output_root / "dukascopy_xau_1h.parquet",
        "price_4h": output_root / "dukascopy_xau_4h.parquet",
        "price_1d": output_root / "dukascopy_xau_1d.parquet",
        "cme_oi": output_root / "cme_canonical_option_oi_by_strike.parquet",
        "cme_iv": output_root / "cme_canonical_option_iv_by_strike.parquet",
        "cme_futures": output_root / "cme_canonical_futures_price.parquet",
        "basis": output_root / "xau_basis_backfilled.parquet",
        "guru_replay": output_root / "current_week_cme_guru_replay.csv",
        "overlap_validation": output_root / "dukascopy_cme_overlap_validation.csv",
        "pine_signals": output_root / "python_pine_like_signals.csv",
        "python_trades": output_root / "python_pine_like_backtest_trades.csv",
        "python_overlay_trades": output_root / "python_cme_guru_overlay_trades.csv",
        "tradingview_trades": output_root / "tradingview_trades_canonical.csv",
        "score_rows": output_root / "xau_trade_quality_score.csv",
        "guru_knowledge": output_root / "guru_logic_knowledge_base.csv",
        "same_day_filter": output_root / "same_day_filter_evidence_after_metadata.csv",
        "same_day_market_map": output_root / "same_day_market_map_evidence_after_metadata.csv",
        "market_map": output_root / "cme_overlap_market_map.csv",
        "date_audit_csv": output_root / "cme_overlap_backtest_date_audit.csv",
        "date_audit_md": output_root / "cme_overlap_backtest_date_audit.md",
        "source_report_csv": output_root / "cme_overlap_candidate_source_report.csv",
        "source_report_md": output_root / "cme_overlap_candidate_source_report.md",
        "candidates_csv": output_root / "cme_overlap_trade_candidates.csv",
        "candidates_md": output_root / "cme_overlap_trade_candidates.md",
        "filter_backtest_csv": output_root / "cme_overlap_filter_backtest.csv",
        "filter_backtest_md": output_root / "cme_overlap_filter_backtest.md",
        "wall_effect_csv": output_root / "cme_wall_filter_effect.csv",
        "wall_effect_md": output_root / "cme_wall_filter_effect.md",
        "iv_effect_csv": output_root / "cme_iv_range_filter_effect.csv",
        "iv_effect_md": output_root / "cme_iv_range_filter_effect.md",
        "guru_effect_csv": output_root / "cme_overlap_guru_filter_effect.csv",
        "guru_effect_md": output_root / "cme_overlap_guru_filter_effect.md",
        "replay_html": charts / "cme_overlap_replay.html",
        "replay_md": output_root / "cme_overlap_replay.md",
        "pilot_decision_csv": output_root / "cme_overlap_pilot_decision.csv",
        "pilot_decision_md": output_root / "cme_overlap_pilot_decision.md",
    }


def _read_optional(path: Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    try:
        if path.suffix.lower() == ".parquet":
            return pl.read_parquet(path)
        return pl.read_csv(path, infer_schema_length=None)
    except Exception:  # noqa: BLE001 - optional research inputs degrade to missing data.
        return pl.DataFrame()


def _cme_overlap_dates(inputs: dict[str, Any]) -> set[str]:
    dates: set[str] = set()
    for key in ("cme_oi", "cme_iv", "guru_replay", "same_day_filter", "same_day_market_map"):
        dates.update(_date_values(_frame_input(inputs, key)))
    dates.update(_dates_from_overlap_validation(_frame_input(inputs, "overlap_validation")))
    if not dates:
        for key in ("cme_futures", "basis"):
            dates.update(_date_values(_frame_input(inputs, key)))
    if not dates:
        dates.update(_date_values(_python_candidate_frame(inputs)))
        dates.update(_date_values(_frame_input(inputs, "score_rows")))
    return {value for value in dates if value >= "2024-01-01"}


def _dates_from_overlap_validation(frame: pl.DataFrame) -> set[str]:
    if frame.is_empty():
        return set()
    rows = []
    for row in frame.to_dicts():
        trade_date = _date_text(_first_value(row, ("trade_date", "session_date", "date", "timestamp")))
        if not trade_date:
            continue
        has_cme = any(
            _truthy(row.get(column))
            for column in ("has_cme_oi", "has_cme_iv", "can_test_oi_wall", "can_test_iv_range")
        )
        grade = _text(row.get("validation_grade")).upper()
        if has_cme or grade not in {"", "UNUSABLE", "PRICE_ONLY"}:
            rows.append(trade_date)
    return set(rows)


def _usable_dates(date_audit: pl.DataFrame) -> set[str]:
    if date_audit.is_empty():
        return set()
    rows = date_audit.filter(pl.col("pilot_grade") != "UNUSABLE") if "pilot_grade" in date_audit.columns else date_audit
    return set(rows.get_column("trade_date").cast(pl.Utf8).to_list()) if "trade_date" in rows.columns else set()


def _python_candidate_frame(inputs: dict[str, Any]) -> pl.DataFrame:
    overlay = _frame_input(inputs, "python_overlay_trades")
    if not overlay.is_empty():
        return overlay
    trades = _frame_input(inputs, "python_trades")
    if not trades.is_empty():
        return trades
    return _frame_input(inputs, "pine_signals")


def _candidates_from_python(*, inputs: dict[str, Any], cme_dates: set[str]) -> list[dict[str, Any]]:
    overlay = _frame_input(inputs, "python_overlay_trades")
    if not overlay.is_empty():
        return _candidates_from_trade_frame(
            overlay,
            source="PYTHON_PINE_LIKE",
            cme_dates=cme_dates,
            inputs=inputs,
        )
    trades = _frame_input(inputs, "python_trades")
    if not trades.is_empty():
        return _candidates_from_trade_frame(
            trades,
            source="PYTHON_PINE_LIKE",
            cme_dates=cme_dates,
            inputs=inputs,
        )
    signals = _frame_input(inputs, "pine_signals")
    rows = []
    for row in signals.to_dicts():
        trade_date = _date_text(_first_value(row, ("timestamp", "signal_timestamp", "trade_date", "session_date")))
        if trade_date not in cme_dates:
            continue
        if not _signal_is_candidate(row):
            continue
        rows.append(_candidate_row_from_source(row, source="PYTHON_PINE_LIKE", inputs=inputs))
    return rows


def _candidates_from_trade_frame(
    frame: pl.DataFrame,
    *,
    source: str,
    cme_dates: set[str],
    inputs: dict[str, Any],
) -> list[dict[str, Any]]:
    rows = []
    for row in frame.to_dicts():
        trade_date = _candidate_trade_date(row)
        if trade_date not in cme_dates:
            continue
        rows.append(_candidate_row_from_source(row, source=source, inputs=inputs))
    return rows


def _candidates_from_score_rows(
    frame: pl.DataFrame,
    *,
    cme_dates: set[str],
    inputs: dict[str, Any],
) -> list[dict[str, Any]]:
    rows = []
    for row in frame.to_dicts():
        trade_date = _candidate_trade_date(row)
        if trade_date not in cme_dates:
            continue
        label = _text(row.get("final_label"))
        bucket = _text(row.get("score_bucket"))
        if not label and bucket not in {"WATCH_ONLY", "ALLOW_RESEARCH", "HIGH_QUALITY_RESEARCH"}:
            continue
        rows.append(_candidate_row_from_source(row, source="PRICE_RULE", inputs=inputs))
    return rows


def _candidate_row_from_source(row: dict[str, Any], *, source: str, inputs: dict[str, Any]) -> dict[str, Any]:
    timestamp = _timestamp_text(
        _first_value(
            row,
            (
                "entry_timestamp",
                "timestamp",
                "signal_timestamp",
                "observation_timestamp",
                "time",
                "entry_time",
            ),
        )
    )
    trade_date = _candidate_trade_date(row)
    timeframe = _normalize_timeframe(_first_value(row, ("timeframe", "interval", "source_interval")))
    entry_price = _first_float(row, ("entry_price", "price", "close", "latest_price"))
    context = _candidate_context(
        row=row,
        trade_date=trade_date,
        timeframe=timeframe,
        entry_price=entry_price,
        inputs=inputs,
    )
    acceptance = _bool_or_contains(row, ("acceptance_breakout",), "ACCEPTANCE_BREAKOUT")
    rejection = _bool_or_contains(row, ("rejection_after_level_touch",), "REJECTION")
    no_trade = _bool_or_contains(row, ("no_trade_middle_range",), "NO_TRADE_MIDDLE")
    open_distance = _contains_any(
        row,
        ("price_filter_state", "blocked_reasons", "active_negative_components", "signal_reason", "entry_reason"),
        ("OPEN_DISTANCE", "CHASE"),
    )
    fee_pass = not _contains_any(
        row,
        ("blocked_reasons", "active_negative_components", "price_filter_state", "data_quality_notes"),
        ("FEE", "SPREAD_HURDLE", "SPREAD"),
    )
    return {
        "candidate_id": "",
        "timestamp": timestamp,
        "trade_date": trade_date,
        "timeframe": timeframe,
        "candidate_source": source,
        "direction": _normalize_direction(_first_value(row, ("direction", "candidate_direction", "direction_candidate"))),
        "entry_price": entry_price,
        "exit_price": _first_float(row, ("exit_price", "close_exit", "target_exit_price")),
        "raw_pnl": _first_float(
            row,
            (
                "raw_pnl",
                "pnl_after_cost",
                "pnl_after_spread_cost",
                "gross_pnl_before_cost",
                "outcome_return",
                "close_return",
            ),
        ),
        "signal_reason": _signal_reason(row),
        "acceptance_breakout_active": acceptance,
        "rejection_after_touch_component": rejection,
        "no_trade_middle_range_active": no_trade,
        "open_distance_filter_active": open_distance,
        "fee_spread_hurdle_pass": fee_pass,
        "cme_wall_above": context["cme_wall_above"],
        "cme_wall_below": context["cme_wall_below"],
        "distance_to_wall": context["distance_to_wall"],
        "cme_iv_context": context["cme_iv_context"],
        "guru_filter_context": context["guru_filter_context"],
        "data_quality": context["data_quality"],
        "mfe": _first_float(row, ("mfe", "max_favorable_excursion")),
        "mae": _first_float(row, ("mae", "max_adverse_excursion")),
    }


def _candidate_context(
    *,
    row: dict[str, Any],
    trade_date: str,
    timeframe: str,
    entry_price: float | None,
    inputs: dict[str, Any],
) -> dict[str, Any]:
    market_map_row = _lookup_market_map(inputs, trade_date, timeframe)
    same_day_map = _lookup_date_row(_frame_input(inputs, "same_day_market_map"), trade_date)
    replay_row = _lookup_date_row(_frame_input(inputs, "guru_replay"), trade_date)
    wall_above = _first_float(
        {**replay_row, **same_day_map, **market_map_row, **row},
        (
            "cme_wall_above",
            "spot_equivalent_wall_above",
            "top_wall_above",
            "nearest_wall_above_price",
        ),
    )
    wall_below = _first_float(
        {**replay_row, **same_day_map, **market_map_row, **row},
        (
            "cme_wall_below",
            "spot_equivalent_wall_below",
            "top_wall_below",
            "nearest_wall_below_price",
        ),
    )
    distance = _first_float(row, ("distance_to_wall", "basis_adjusted_wall_distance", "nearest_wall_distance"))
    if distance is None and entry_price is not None:
        candidates = [abs(entry_price - value) for value in (wall_above, wall_below) if value is not None]
        distance = min(candidates) if candidates else None
    iv_available = any(
        _truthy(_first_value(source, ("iv_available", "iv_range_available", "has_cme_iv")))
        for source in (row, market_map_row, replay_row)
    )
    iv_context = _text(row.get("cme_iv_context")) or (
        "IV_CONTEXT_AVAILABLE" if iv_available else "IV_MISSING_CONTEXT_ONLY"
    )
    guru_context = (
        _text(row.get("guru_filter_state"))
        or _text(row.get("guru_filter_context"))
        or _text(replay_row.get("active_guru_logic"))
        or _same_day_filter_context(_frame_input(inputs, "same_day_filter"), trade_date)
        or "NO_GURU_CONTEXT"
    )
    data_quality = _text(row.get("data_quality")) or _text(row.get("data_quality_label")) or "OK"
    if "MISSING" in iv_context and wall_above is None and wall_below is None:
        data_quality = "PRICE_WITH_CONTEXT_GAPS"
    return {
        "cme_wall_above": wall_above,
        "cme_wall_below": wall_below,
        "distance_to_wall": distance,
        "cme_iv_context": iv_context,
        "guru_filter_context": guru_context,
        "data_quality": data_quality,
    }


def _filter_metric_row(frame: pl.DataFrame, scenario: str, allowed: list[bool]) -> dict[str, Any]:
    rows = frame.to_dicts()
    allowed_rows = [row for row, is_allowed in zip(rows, allowed, strict=False) if is_allowed]
    blocked_rows = [row for row, is_allowed in zip(rows, allowed, strict=False) if not is_allowed]
    returns = [_float(row.get("raw_pnl")) for row in allowed_rows if _float(row.get("raw_pnl")) is not None]
    blocked_returns = [_float(row.get("raw_pnl")) for row in blocked_rows if _float(row.get("raw_pnl")) is not None]
    positive = [value for value in returns if value > 0]
    negative = [value for value in returns if value < 0]
    blocked_winning = [value for value in blocked_returns if value > 0]
    avoided_losing = [value for value in blocked_returns if value <= 0]
    return {
        "scenario": scenario,
        "candidate_count": frame.height,
        "allowed_count": len(allowed_rows),
        "blocked_count": len(blocked_rows),
        "win_rate": _rate([value > 0 for value in returns]),
        "average_return": _average(returns),
        "expectancy_proxy": _average(returns),
        "profit_factor_proxy": _profit_factor(positive, negative),
        "max_drawdown_proxy": _max_drawdown(returns),
        "average_mfe": _average(
            [_float(row.get("mfe")) for row in allowed_rows if _float(row.get("mfe")) is not None]
        ),
        "average_mae": _average(
            [_float(row.get("mae")) for row in allowed_rows if _float(row.get("mae")) is not None]
        ),
        "avoided_losing_candidates": len(avoided_losing),
        "blocked_winning_candidates": len(blocked_winning),
        "false_block_rate": len(blocked_winning) / len(blocked_rows) if blocked_rows else 0.0,
        "net_filter_value_proxy": sum(-value for value in blocked_returns),
        "sample_size_warning": frame.height < MIN_PILOT_CANDIDATES or len(allowed_rows) < MIN_PILOT_CANDIDATES,
        "pilot_warning": PILOT_WARNING,
    }


def _scenario_allows(row: dict[str, Any], scenario: str) -> bool:
    if scenario == "RAW_CANDIDATES":
        return True
    if scenario == "PRICE_ONLY_FILTERS":
        return _price_filters_allow(row)
    if scenario == "CME_WALL_FILTER_ONLY":
        return _cme_wall_filter_allows(row)
    if scenario == "CME_IV_RANGE_FILTER_ONLY":
        return _cme_iv_filter_allows(row)
    if scenario == "GURU_FILTER_ONLY":
        return _guru_filter_allows(row)
    if scenario == "FEE_SPREAD_HURDLE_ONLY":
        return bool(row.get("fee_spread_hurdle_pass"))
    if scenario == "COMBINED_CONSERVATIVE_FILTER":
        return (
            _price_filters_allow(row)
            and _cme_wall_filter_allows(row)
            and _cme_iv_filter_allows(row)
            and _guru_filter_allows(row)
            and bool(row.get("fee_spread_hurdle_pass"))
        )
    return True


def _price_filters_allow(row: dict[str, Any]) -> bool:
    return (
        not bool(row.get("no_trade_middle_range_active"))
        and not bool(row.get("open_distance_filter_active"))
        and bool(row.get("fee_spread_hurdle_pass"))
    )


def _cme_wall_filter_allows(row: dict[str, Any]) -> bool:
    distance = _float(row.get("distance_to_wall"))
    has_wall = row.get("cme_wall_above") is not None or row.get("cme_wall_below") is not None
    if not has_wall or distance is None:
        return True
    if bool(row.get("acceptance_breakout_active")) or bool(row.get("rejection_after_touch_component")):
        return True
    return distance > WALL_PROXIMITY_POINTS


def _cme_iv_filter_allows(row: dict[str, Any]) -> bool:
    context = _text(row.get("cme_iv_context")).upper()
    if not context or "MISSING" in context:
        return True
    if "BEYOND_2SD" in context and not bool(row.get("acceptance_breakout_active")):
        return False
    return True


def _guru_filter_allows(row: dict[str, Any]) -> bool:
    context = _text(row.get("guru_filter_context")).upper()
    if not context:
        return True
    blocked_terms = ("BLOCK", "NO_TRADE", "STALE", "AVOID")
    return not any(term in context for term in blocked_terms)


def _wall_case(row: dict[str, Any]) -> str:
    distance = _float(row.get("distance_to_wall"))
    has_wall = row.get("cme_wall_above") is not None or row.get("cme_wall_below") is not None
    if not has_wall or distance is None:
        return "WALL_CONTEXT_MISSING"
    if bool(row.get("acceptance_breakout_active")):
        return "ACCEPTANCE_THROUGH_WALL"
    if bool(row.get("rejection_after_touch_component")):
        return "REJECTION_FROM_WALL"
    if distance <= WALL_PROXIMITY_POINTS:
        return "DIRECTLY_INTO_WALL"
    return "AWAY_FROM_WALL"


def _iv_case(row: dict[str, Any]) -> str:
    context = _text(row.get("cme_iv_context")).upper()
    if not context or "MISSING" in context:
        return "IV_MISSING"
    if "BEYOND_2SD" in context:
        return "BEYOND_2SD"
    if "1SD" in context or "ONE_SD" in context or "EDGE" in context:
        return "NEAR_1SD_EDGE"
    return "INSIDE_IV_EXPECTED_RANGE"


def _guru_case(row: dict[str, Any]) -> str:
    context = _text(row.get("guru_filter_context")).upper()
    if not context or context == "NO_GURU_CONTEXT":
        return "GURU_CONTEXT_MISSING"
    if not _guru_filter_allows(row):
        return "BLOCKED_BY_GURU_FILTER"
    if "TIMING" in context or "SAME_DAY" in context or "CONFIRMED" in context:
        return "SAME_DAY_TIMING_CONFIRMED"
    return "HISTORICAL_PLAYBOOK_ONLY"


def _wall_interpretation(case_rows: dict[str, list[dict[str, Any]]]) -> str:
    total = sum(len(items) for items in case_rows.values())
    if total < MIN_PILOT_CANDIDATES:
        return "INSUFFICIENT_SAMPLE"
    direct = _case_average(case_rows.get("DIRECTLY_INTO_WALL", []))
    away = _case_average(case_rows.get("AWAY_FROM_WALL", []))
    if direct is not None and away is not None and direct < away:
        return "WALL_HELPFUL"
    if direct is not None:
        return "WALL_CONTEXT_ONLY"
    return "WALL_NOT_HELPFUL_YET"


def _iv_interpretation(case_rows: dict[str, list[dict[str, Any]]]) -> str:
    total = sum(len(items) for items in case_rows.values())
    if total < MIN_PILOT_CANDIDATES:
        return "INSUFFICIENT_SAMPLE"
    missing = len(case_rows.get("IV_MISSING", []))
    if missing / max(total, 1) > 0.5:
        return "IV_CONTEXT_ONLY"
    return "IV_HELPFUL"


def _guru_interpretation(case_rows: dict[str, list[dict[str, Any]]]) -> str:
    total = sum(len(items) for items in case_rows.values())
    if total < MIN_PILOT_CANDIDATES:
        return "INSUFFICIENT_SAMPLE"
    blocked_avg = _case_average(case_rows.get("BLOCKED_BY_GURU_FILTER", []))
    context_avg = _case_average(case_rows.get("SAME_DAY_TIMING_CONFIRMED", []))
    if blocked_avg is not None and context_avg is not None and blocked_avg < context_avg:
        return "GURU_FILTER_HELPFUL"
    return "GURU_CONTEXT_ONLY"


def _date_audit_markdown(result: CmeOverlapBacktestLabResult) -> str:
    return _section("CME Overlap Backtest Date Audit", result.date_audit)


def _source_report_markdown(result: CmeOverlapBacktestLabResult) -> str:
    return _section("CME Overlap Candidate Source Selection", result.candidate_source_report)


def _candidates_markdown(result: CmeOverlapBacktestLabResult) -> str:
    return _section("CME Overlap Trade Candidates", result.candidates)


def _filter_backtest_markdown(result: CmeOverlapBacktestLabResult) -> str:
    return _section("CME/Guru Filter Backtest", result.filter_backtest)


def _wall_effect_markdown(result: CmeOverlapBacktestLabResult) -> str:
    return _section("CME Wall Filter Effect", result.wall_effect)


def _iv_effect_markdown(result: CmeOverlapBacktestLabResult) -> str:
    return _section("CME IV Range Filter Effect", result.iv_effect)


def _guru_effect_markdown(result: CmeOverlapBacktestLabResult) -> str:
    return _section("CME Overlap Guru Filter Effect", result.guru_effect)


def _pilot_decision_markdown(result: CmeOverlapBacktestLabResult) -> str:
    return _section("CME Overlap Pilot Decision", result.pilot_decision)


def _replay_markdown(result: CmeOverlapBacktestLabResult) -> str:
    lines = [
        "# CME Overlap Visual Replay",
        "",
        RESEARCH_WARNING,
        PILOT_WARNING,
        "",
        "This replay describes price, CME wall context, IV/range context, candidates, filters, and outcomes by date.",
        "",
    ]
    if result.candidates.is_empty():
        lines.append("_No candidate rows available for replay._")
        return "\n".join(lines)
    for trade_date in sorted(set(result.candidates.get_column("trade_date").cast(pl.Utf8).to_list())):
        rows = result.candidates.filter(pl.col("trade_date") == trade_date)
        allowed = [
            _scenario_allows(row, "COMBINED_CONSERVATIVE_FILTER")
            for row in _normalize_candidates(rows).to_dicts()
        ]
        lines.extend(
            [
                f"## {trade_date}",
                "",
                f"- Candidate rows: {rows.height}",
                f"- Combined allowed rows: {sum(1 for flag in allowed if flag)}",
                f"- Combined blocked rows: {sum(1 for flag in allowed if not flag)}",
                f"- CME wall context rows: {_context_count(rows, 'distance_to_wall')}",
                f"- IV/range context: {_iv_context_summary(rows)}",
                f"- Guru context rows: {_guru_context_count(rows)}",
                "",
            ]
        )
    return "\n".join(lines)


def _replay_html(result: CmeOverlapBacktestLabResult) -> str:
    rows = []
    if not result.candidates.is_empty():
        for trade_date in sorted(set(result.candidates.get_column("trade_date").cast(pl.Utf8).to_list())):
            frame = result.candidates.filter(pl.col("trade_date") == trade_date)
            allowed = [
                _scenario_allows(row, "COMBINED_CONSERVATIVE_FILTER")
                for row in _normalize_candidates(frame).to_dicts()
            ]
            rows.append(
                "<tr>"
                f"<td>{trade_date}</td>"
                f"<td>{frame.height}</td>"
                f"<td>{sum(1 for flag in allowed if flag)}</td>"
                f"<td>{sum(1 for flag in allowed if not flag)}</td>"
                f"<td>{_html_escape(_iv_context_summary(frame))}</td>"
                "</tr>"
            )
    body = "\n".join(rows) or "<tr><td colspan=\"5\">No candidate rows available.</td></tr>"
    return "\n".join(
        [
            "<!doctype html>",
            "<html lang=\"en\">",
            "<head><meta charset=\"utf-8\"><title>CME Overlap Replay</title>",
            "<style>body{font-family:Arial,sans-serif;margin:24px;color:#1f2933}"
            "table{border-collapse:collapse;width:100%}td,th{border:1px solid #cbd5e1;padding:8px}"
            "th{background:#f1f5f9;text-align:left}.note{color:#52606d}</style></head>",
            "<body>",
            "<h1>CME Overlap Visual Replay</h1>",
            f"<p class=\"note\">{_html_escape(RESEARCH_WARNING)} { _html_escape(PILOT_WARNING)}</p>",
            "<table><thead><tr><th>Date</th><th>Candidates</th><th>Combined allowed</th>"
            "<th>Combined blocked</th><th>IV/range context</th></tr></thead><tbody>",
            body,
            "</tbody></table>",
            "</body></html>",
        ]
    )


def _section(title: str, frame: pl.DataFrame) -> str:
    return "\n\n".join(["# " + title, RESEARCH_WARNING, PILOT_WARNING, _frame_markdown(frame)])


def _safe_report_text(text: str) -> str:
    safe = _redact_paths(text)
    lowered_safe = f" {safe.lower()} "
    for phrase in FORBIDDEN_REPORT_PHRASES:
        if phrase in lowered_safe:
            safe = re.sub(re.escape(phrase.strip()), "[redacted research-safety phrase]", safe, flags=re.IGNORECASE)
            lowered_safe = f" {safe.lower()} "
    return safe


def _redact_paths(text: str) -> str:
    safe = re.sub(r"[A-Za-z]:\\[^\s|)<>]+", "<REDACTED_PATH>", text)
    return re.sub(r"/(?:Users|home|mnt|var|tmp)/[^\s|)<>]+", "<REDACTED_PATH>", safe)


def _frame(rows: list[dict[str, Any]], schema: dict[str, Any]) -> pl.DataFrame:
    if not rows:
        return pl.DataFrame(schema=schema)
    frame = pl.DataFrame(rows, infer_schema_length=None)
    for column, dtype in schema.items():
        if column not in frame.columns:
            frame = frame.with_columns(pl.lit(None).cast(dtype).alias(column))
        else:
            frame = frame.with_columns(pl.col(column).cast(dtype, strict=False).alias(column))
    return frame.select(list(schema))


def _normalize_candidates(candidates: pl.DataFrame) -> pl.DataFrame:
    return _frame(candidates.to_dicts() if not candidates.is_empty() else [], _candidate_schema())


def _frame_markdown(frame: pl.DataFrame, *, limit: int = 25) -> str:
    if frame.is_empty():
        return "_No rows._"
    sample = frame.head(limit)
    lines = [
        "| " + " | ".join(sample.columns) + " |",
        "| " + " | ".join("---" for _ in sample.columns) + " |",
    ]
    for row in sample.to_dicts():
        lines.append("| " + " | ".join(_markdown_cell(row.get(column, "")) for column in sample.columns) + " |")
    if frame.height > limit:
        lines.append(f"\n_Showing {limit} of {frame.height} rows._")
    return "\n".join(lines)


def _markdown_cell(value: Any) -> str:
    if value is None:
        return ""
    return _redact_paths(str(value).replace("|", "\\|").replace("\n", " "))[:700]


def _date_audit_schema() -> dict[str, Any]:
    return {
        "trade_date": pl.Utf8,
        "has_dukascopy_price": pl.Boolean,
        "has_cme_oi": pl.Boolean,
        "has_cme_iv": pl.Boolean,
        "has_oi_change": pl.Boolean,
        "has_option_volume": pl.Boolean,
        "has_basis": pl.Boolean,
        "has_guru_context": pl.Boolean,
        "has_python_pine_signal": pl.Boolean,
        "has_tradingview_trade_csv": pl.Boolean,
        "can_run_price_only_baseline": pl.Boolean,
        "can_run_python_pine_backtest": pl.Boolean,
        "can_run_cme_filter_test": pl.Boolean,
        "can_run_guru_filter_test": pl.Boolean,
        "can_run_combined_test": pl.Boolean,
        "missing_components": pl.Utf8,
        "pilot_grade": pl.Utf8,
        "has_cme_futures": pl.Boolean,
    }


def _source_report_schema() -> dict[str, Any]:
    return {
        "candidate_source": pl.Utf8,
        "available": pl.Boolean,
        "trade_count_on_cme_dates": pl.Int64,
        "date_range": pl.Utf8,
        "limitations": pl.Utf8,
        "selected_for_backtest": pl.Boolean,
    }


def _candidate_schema() -> dict[str, Any]:
    return {
        "candidate_id": pl.Utf8,
        "timestamp": pl.Utf8,
        "trade_date": pl.Utf8,
        "timeframe": pl.Utf8,
        "candidate_source": pl.Utf8,
        "direction": pl.Utf8,
        "entry_price": pl.Float64,
        "exit_price": pl.Float64,
        "raw_pnl": pl.Float64,
        "signal_reason": pl.Utf8,
        "acceptance_breakout_active": pl.Boolean,
        "rejection_after_touch_component": pl.Boolean,
        "no_trade_middle_range_active": pl.Boolean,
        "open_distance_filter_active": pl.Boolean,
        "fee_spread_hurdle_pass": pl.Boolean,
        "cme_wall_above": pl.Float64,
        "cme_wall_below": pl.Float64,
        "distance_to_wall": pl.Float64,
        "cme_iv_context": pl.Utf8,
        "guru_filter_context": pl.Utf8,
        "data_quality": pl.Utf8,
        "mfe": pl.Float64,
        "mae": pl.Float64,
    }


def _filter_backtest_schema() -> dict[str, Any]:
    return {
        "scenario": pl.Utf8,
        "candidate_count": pl.Int64,
        "allowed_count": pl.Int64,
        "blocked_count": pl.Int64,
        "win_rate": pl.Float64,
        "average_return": pl.Float64,
        "expectancy_proxy": pl.Float64,
        "profit_factor_proxy": pl.Float64,
        "max_drawdown_proxy": pl.Float64,
        "average_mfe": pl.Float64,
        "average_mae": pl.Float64,
        "avoided_losing_candidates": pl.Int64,
        "blocked_winning_candidates": pl.Int64,
        "false_block_rate": pl.Float64,
        "net_filter_value_proxy": pl.Float64,
        "sample_size_warning": pl.Boolean,
        "pilot_warning": pl.Utf8,
    }


def _wall_effect_schema() -> dict[str, Any]:
    return {
        "case_type": pl.Utf8,
        "candidate_count": pl.Int64,
        "trades_directly_into_wall": pl.Int64,
        "trades_away_from_wall": pl.Int64,
        "trades_after_acceptance_through_wall": pl.Int64,
        "trades_after_rejection_from_wall": pl.Int64,
        "wall_touch_count": pl.Int64,
        "wall_rejection_count": pl.Int64,
        "wall_acceptance_count": pl.Int64,
        "pnl_or_return_by_case": pl.Float64,
        "interpretation": pl.Utf8,
    }


def _iv_effect_schema() -> dict[str, Any]:
    return {
        "case_type": pl.Utf8,
        "candidate_count": pl.Int64,
        "trades_inside_iv_expected_range": pl.Int64,
        "trades_near_1sd_edge": pl.Int64,
        "trades_beyond_2sd": pl.Int64,
        "trades_when_iv_missing": pl.Int64,
        "range_followthrough": pl.Float64,
        "mean_reversion_behavior": pl.Float64,
        "pnl_or_return_by_case": pl.Float64,
        "interpretation": pl.Utf8,
    }


def _guru_effect_schema() -> dict[str, Any]:
    return {
        "case_type": pl.Utf8,
        "candidate_count": pl.Int64,
        "candidates_with_same_day_timing_confirmed_guru_context": pl.Int64,
        "candidates_with_historical_playbook_only": pl.Int64,
        "candidates_blocked_by_guru_filter": pl.Int64,
        "avoided_losing_candidates": pl.Int64,
        "blocked_winning_candidates": pl.Int64,
        "net_filter_value_proxy": pl.Float64,
        "pnl_or_return_by_case": pl.Float64,
        "interpretation": pl.Utf8,
    }


def _pilot_decision_schema() -> dict[str, Any]:
    return {
        "final_label": pl.Utf8,
        "supporting_labels": pl.Utf8,
        "selected_candidate_source": pl.Utf8,
        "overlap_date_count": pl.Int64,
        "candidate_count": pl.Int64,
        "combined_allowed_count": pl.Int64,
        "raw_average_return": pl.Float64,
        "combined_average_return": pl.Float64,
        "wall_interpretation": pl.Utf8,
        "iv_interpretation": pl.Utf8,
        "guru_interpretation": pl.Utf8,
        "sample_size_warning": pl.Boolean,
        "pilot_warning": pl.Utf8,
        "money_readiness": pl.Utf8,
        "plain_english_summary": pl.Utf8,
    }


def _frame_input(inputs: dict[str, Any], key: str) -> pl.DataFrame:
    value = inputs.get(key)
    return value if isinstance(value, pl.DataFrame) else pl.DataFrame()


def _date_values(frame: pl.DataFrame) -> set[str]:
    if frame.is_empty():
        return set()
    columns = (
        "trade_date",
        "session_date",
        "resolved_market_session_date",
        "original_replay_date",
        "date",
        "timestamp",
        "entry_timestamp",
        "signal_timestamp",
        "observation_timestamp",
        "asof_timestamp",
        "cme_asof_timestamp",
    )
    dates: set[str] = set()
    for column in columns:
        if column not in frame.columns:
            continue
        for value in frame.get_column(column).drop_nulls().to_list():
            text = _date_text(value)
            if text:
                dates.add(text)
    return dates


def _date_has_row(frame: pl.DataFrame, trade_date: str) -> bool:
    return trade_date in _date_values(frame)


def _validation_flag(frame: pl.DataFrame, trade_date: str, column: str) -> bool:
    if frame.is_empty() or column not in frame.columns:
        return False
    for row in frame.to_dicts():
        if _date_text(_first_value(row, ("trade_date", "session_date", "date", "timestamp"))) == trade_date:
            return _truthy(row.get(column))
    return False


def _truthy_context_flag(frame: pl.DataFrame, trade_date: str, column: str) -> bool:
    if frame.is_empty() or column not in frame.columns:
        return False
    for row in frame.to_dicts():
        if _candidate_trade_date(row) == trade_date and _truthy(row.get(column)):
            return True
    return False


def _has_numeric_or_truthy(frame: pl.DataFrame, trade_date: str, columns: Iterable[str]) -> bool:
    if frame.is_empty():
        return False
    for row in frame.to_dicts():
        if _candidate_trade_date(row) != trade_date:
            continue
        for column in columns:
            if column not in row:
                continue
            value = row.get(column)
            if _truthy(value):
                return True
            number = _float(value)
            if number is not None and abs(number) > 0:
                return True
    return False


def _count_rows_on_dates(frame: pl.DataFrame, dates: set[str]) -> int:
    if frame.is_empty() or not dates:
        return 0
    return sum(1 for row in frame.to_dicts() if _candidate_trade_date(row) in dates)


def _date_range_text(frame: pl.DataFrame, dates: set[str]) -> str:
    values = sorted(value for value in _date_values(frame) if not dates or value in dates)
    if not values:
        return "MISSING"
    return f"{values[0]} to {values[-1]}"


def _source_limitations(source: str, count: int) -> str:
    if source == "TRADINGVIEW_TRADE_CSV":
        return "Actual exported trade rows when available; depends on CSV export fidelity."
    if source == "PYTHON_PINE_LIKE":
        return "Python Pine-like candidates are reproducible local proxies, not TradingView parity."
    if source == "PRICE_RULE":
        return "Price-rule candidates use local Dukascopy behavior and fixed research filters."
    if count == 0:
        return "Manual research source is not generated automatically."
    return "Context source only."


def _selected_candidate_source(source_report: pl.DataFrame) -> str:
    if source_report.is_empty() or "selected_for_backtest" not in source_report.columns:
        return ""
    selected = source_report.filter(pl.col("selected_for_backtest"))
    if selected.is_empty():
        return ""
    return _text(selected.row(0, named=True).get("candidate_source"))


def _candidate_trade_date(row: dict[str, Any]) -> str:
    return _date_text(
        _first_value(
            row,
            (
                "trade_date",
                "session_date",
                "entry_timestamp",
                "timestamp",
                "signal_timestamp",
                "observation_timestamp",
                "time",
                "entry_time",
            ),
        )
    )


def _signal_is_candidate(row: dict[str, Any]) -> bool:
    if _truthy(row.get("acceptance_breakout")) or _truthy(row.get("rejection_after_level_touch")):
        return True
    raw = _text(row.get("raw_signal")).upper()
    direction = _normalize_direction(_first_value(row, ("direction_candidate", "candidate_direction")))
    return raw not in {"", "NONE", "NO_SIGNAL"} or direction != "NONE"


def _signal_reason(row: dict[str, Any]) -> str:
    return (
        _text(row.get("signal_reason"))
        or _text(row.get("entry_reason"))
        or _text(row.get("final_label"))
        or _text(row.get("raw_signal"))
        or "RESEARCH_CANDIDATE"
    )


def _lookup_market_map(inputs: dict[str, Any], trade_date: str, timeframe: str) -> dict[str, Any]:
    market_map = _frame_input(inputs, "market_map")
    if market_map.is_empty():
        return {}
    rows = market_map.filter(pl.col("trade_date").cast(pl.Utf8) == trade_date) if "trade_date" in market_map.columns else market_map
    if not rows.is_empty() and "timeframe" in rows.columns and timeframe:
        exact = rows.filter(pl.col("timeframe").cast(pl.Utf8) == timeframe)
        if not exact.is_empty():
            return exact.row(0, named=True)
    return rows.row(0, named=True) if not rows.is_empty() else {}


def _lookup_date_row(frame: pl.DataFrame, trade_date: str) -> dict[str, Any]:
    if frame.is_empty():
        return {}
    for row in frame.to_dicts():
        if _candidate_trade_date(row) == trade_date:
            return row
        if _date_text(row.get("resolved_market_session_date")) == trade_date:
            return row
    return {}


def _same_day_filter_context(frame: pl.DataFrame, trade_date: str) -> str:
    row = _lookup_date_row(frame, trade_date)
    if not row:
        return ""
    if _truthy(row.get("timing_confirmed_filter_matches")):
        return "SAME_DAY_TIMING_CONFIRMED_FILTER_CONTEXT"
    if _truthy(row.get("no_trade_filter_active")):
        return "NO_TRADE_FILTER_CONTEXT"
    return _text(row.get("active_filter_logic_names")) or "GURU_CONTEXT_AVAILABLE"


def _scenario_row(frame: pl.DataFrame, scenario: str) -> dict[str, Any]:
    if frame.is_empty() or "scenario" not in frame.columns:
        return {}
    rows = frame.filter(pl.col("scenario") == scenario)
    return rows.row(0, named=True) if not rows.is_empty() else {}


def _dominant_interpretation(frame: pl.DataFrame, column: str) -> str:
    if frame.is_empty() or column not in frame.columns:
        return "INSUFFICIENT_SAMPLE"
    values = [_text(value) for value in frame.get_column(column).drop_nulls().to_list()]
    if not values:
        return "INSUFFICIENT_SAMPLE"
    if "INSUFFICIENT_SAMPLE" in values:
        return "INSUFFICIENT_SAMPLE"
    return values[0]


def _pilot_grade(*, has_price: bool, has_oi: bool, has_iv: bool, has_basis: bool) -> str:
    if not has_price:
        return "UNUSABLE"
    if has_oi and has_iv and has_basis:
        return "FULL_CME_PILOT"
    if has_oi:
        return "OI_ONLY_PILOT"
    if has_iv:
        return "IV_ONLY_PILOT"
    return "PRICE_ONLY"


def _missing_components(flags: dict[str, bool]) -> list[str]:
    return [name for name, available in flags.items() if not available]


def _normalize_direction(value: Any) -> str:
    text = _text(value).upper()
    if text in {"LONG", "UP", "BULL", "BULLISH"}:
        return "LONG"
    if text in {"SHORT", "DOWN", "BEAR", "BEARISH"}:
        return "SHORT"
    return "NONE"


def _normalize_timeframe(value: Any) -> str:
    text = _text(value)
    if not text:
        return "UNKNOWN"
    mapping = {"15": "15m", "30": "30m", "60": "1h", "240": "4h", "D": "1d", "1D": "1d"}
    return mapping.get(text, text)


def _bool_or_contains(row: dict[str, Any], columns: Iterable[str], token: str) -> bool:
    if any(_truthy(row.get(column)) for column in columns):
        return True
    return _contains_any(
        row,
        ("signal_reason", "entry_reason", "raw_signal", "active_positive_components", "final_label"),
        (token,),
    )


def _contains_any(row: dict[str, Any], columns: Iterable[str], tokens: Iterable[str]) -> bool:
    haystack = " ".join(_text(row.get(column)).upper() for column in columns)
    return any(token.upper() in haystack for token in tokens)


def _first_value(row: dict[str, Any], columns: Iterable[str]) -> Any:
    for column in columns:
        if column in row and row.get(column) not in (None, ""):
            return row.get(column)
    return None


def _first_float(row: dict[str, Any], columns: Iterable[str]) -> float | None:
    for column in columns:
        value = _float(row.get(column))
        if value is not None:
            return value
    return None


def _first_text(frame: pl.DataFrame, column: str, fallback: str) -> str:
    if frame.is_empty() or column not in frame.columns:
        return fallback
    value = _text(frame.row(0, named=True).get(column))
    return value or fallback


def _case_average(rows: list[dict[str, Any]]) -> float | None:
    values = [_float(row.get("raw_pnl")) for row in rows if _float(row.get("raw_pnl")) is not None]
    return _average(values)


def _average(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _rate(values: list[bool]) -> float | None:
    if not values:
        return None
    return sum(1 for value in values if value) / len(values)


def _profit_factor(positive: list[float], negative: list[float]) -> float | None:
    if not positive and not negative:
        return None
    loss = abs(sum(negative))
    if loss == 0:
        return None
    return sum(positive) / loss


def _max_drawdown(returns: list[float]) -> float | None:
    if not returns:
        return None
    equity = 0.0
    peak = 0.0
    drawdown = 0.0
    for value in returns:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return drawdown


def _wall_touch_count(frame: pl.DataFrame) -> int:
    if frame.is_empty() or "distance_to_wall" not in frame.columns:
        return 0
    count = 0
    for value in frame.get_column("distance_to_wall").to_list():
        distance = _float(value)
        if distance is not None and distance <= WALL_PROXIMITY_POINTS:
            count += 1
    return count


def _truthy_count(frame: pl.DataFrame, column: str) -> int:
    if frame.is_empty() or column not in frame.columns:
        return 0
    return sum(1 for value in frame.get_column(column).to_list() if _truthy(value))


def _context_count(frame: pl.DataFrame, column: str) -> int:
    if frame.is_empty() or column not in frame.columns:
        return 0
    return sum(1 for value in frame.get_column(column).to_list() if value is not None)


def _guru_context_count(frame: pl.DataFrame) -> int:
    if frame.is_empty() or "guru_filter_context" not in frame.columns:
        return 0
    return sum(
        1
        for value in frame.get_column("guru_filter_context").to_list()
        if _text(value) and _text(value) != "NO_GURU_CONTEXT"
    )


def _iv_context_summary(frame: pl.DataFrame) -> str:
    if frame.is_empty() or "cme_iv_context" not in frame.columns:
        return "IV_MISSING_CONTEXT_ONLY"
    values = [_text(value) for value in frame.get_column("cme_iv_context").to_list()]
    available = sum(1 for value in values if value and "MISSING" not in value.upper())
    missing = len(values) - available
    return f"available={available};missing={missing}"


def _date_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    match = re.search(r"\d{4}-\d{2}-\d{2}", str(value))
    return match.group(0) if match else ""


def _timestamp_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return None
        return number
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0 and not math.isnan(float(value))
    return str(value).strip().lower() in {"true", "1", "yes", "y", "available", "ok"}


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _html_escape(value: Any) -> str:
    return (
        _text(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
