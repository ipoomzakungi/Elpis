"""Single-timeframe walk-forward validation for the Python Pine-like engine.

This module is research-only. It evaluates each symbol/interval separately,
applies train-only filter selection for walk-forward validation, and keeps GLD
and other proxy data clearly labeled. It does not combine timeframes into a
single strategy score and does not create execution readiness claims.
"""

from __future__ import annotations

import argparse
import html
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import polars as pl

from research_xau_vol_oi.pine_python_engine import (
    PinePythonEngineConfig,
    cme_wall_filter_allows,
    guru_filter_allows,
    price_filter_allows,
)
from research_xau_vol_oi.pine_python_engine import (
    _bool_value,
    _date_text,
    _float_or_none,
    _float_or_zero,
    _format_float,
    _frame_markdown,
    _load_optional,
    _rows_frame,
    _safe_report_text,
    _timestamp_text,
)
from research_xau_vol_oi.python_engine_expanded_backtest import (
    build_grid_sensitivity_preview,
    run_expanded_backtests,
)


FILTER_POLICIES = (
    "RAW",
    "PRICE_ONLY_FILTER",
    "FEE_HURDLE_FILTER",
    "OPEN_DISTANCE_FILTER",
    "NO_TRADE_MIDDLE_RANGE",
    "ACCEPTANCE_CONFIRMATION",
    "COMBINED_CONSERVATIVE",
)
DECISION_LABELS = (
    "DO_NOT_USE_RAW_SIGNALS",
    "WATCH_4H_FILTERED_CANDIDATE",
    "WATCH_1D_RESEARCH_ONLY",
    "AVOID_LOW_TIMEFRAME_RAW",
    "NEEDS_WALK_FORWARD_PASS",
    "NEEDS_MORE_FORWARD_EVIDENCE",
    "NOT_READY_FOR_MONEY",
)


@dataclass(frozen=True)
class SingleTimeframeValidationResult:
    """All generated single-timeframe validation frames."""

    timeframe_results: pl.DataFrame
    walk_forward: pl.DataFrame
    deep_dive: pl.DataFrame
    fee_drag: pl.DataFrame
    decision: pl.DataFrame


def run_single_timeframe_validation_lab(
    *,
    output_dir: str | Path = "outputs",
    config: PinePythonEngineConfig | None = None,
    local_frames: list[pl.DataFrame] | None = None,
    min_test_trades: int = 30,
) -> SingleTimeframeValidationResult:
    """Run single-timeframe validation and write requested artifacts."""

    output_root = Path(output_dir)
    charts_dir = output_root / "charts"
    output_root.mkdir(parents=True, exist_ok=True)
    charts_dir.mkdir(parents=True, exist_ok=True)

    cfg = config or PinePythonEngineConfig.from_env()
    expanded_summary, expanded_trades = run_expanded_backtests(
        output_root=output_root,
        local_frames=local_frames,
        base_config=cfg,
    )
    grid_preview = build_grid_sensitivity_preview(
        output_root=output_root,
        local_frames=local_frames,
        base_config=cfg,
    )
    timeframe_results = build_single_timeframe_results(expanded_summary)
    walk_forward = build_walk_forward_by_timeframe(
        expanded_trades,
        config=cfg,
        min_test_trades=min_test_trades,
    )
    deep_dive = build_4h_deep_dive(
        expanded_trades,
        output_root=output_root,
        config=cfg,
    )
    fee_drag = build_fee_drag_by_timeframe(
        expanded_summary,
        expanded_trades,
        grid_preview,
    )
    decision = build_timeframe_decision(timeframe_results, walk_forward, fee_drag)
    result = SingleTimeframeValidationResult(
        timeframe_results=timeframe_results,
        walk_forward=walk_forward,
        deep_dive=deep_dive,
        fee_drag=fee_drag,
        decision=decision,
    )
    write_single_timeframe_outputs(
        output_root=output_root,
        charts_dir=charts_dir,
        result=result,
    )
    return result


def build_single_timeframe_results(expanded_summary: pl.DataFrame) -> pl.DataFrame:
    """Label each symbol/interval independently without aggregate scoring."""

    rows: list[dict[str, Any]] = []
    for raw in expanded_summary.to_dicts() if not expanded_summary.is_empty() else []:
        symbol = str(raw.get("symbol") or "")
        quality = str(raw.get("quality") or "")
        trade_count = int(raw.get("trade_count") or 0)
        rows_count = int(raw.get("rows") or 0)
        net = _float_or_zero(raw.get("net_pnl_after_cost"))
        sample_warning = bool(raw.get("sample_size_warning")) or trade_count < 30
        proxy_warning = symbol == "GLD" or quality == "PROXY_ONLY"
        label = _timeframe_label(
            symbol=symbol,
            quality=quality,
            rows=rows_count,
            trade_count=trade_count,
            net_pnl=net,
        )
        rows.append(
            {
                "symbol": symbol,
                "interval": raw.get("interval"),
                "rows": rows_count,
                "date_start": raw.get("date_start"),
                "date_end": raw.get("date_end"),
                "trade_count": trade_count,
                "net_pnl_after_cost": net,
                "avg_pnl": raw.get("avg_pnl"),
                "win_rate": raw.get("win_rate"),
                "avg_win": raw.get("avg_win"),
                "avg_loss": raw.get("avg_loss"),
                "profit_factor": raw.get("profit_factor"),
                "max_drawdown": raw.get("max_drawdown"),
                "commission_paid": raw.get("commission_paid"),
                "long_pnl": raw.get("long_pnl"),
                "short_pnl": raw.get("short_pnl"),
                "sample_size_warning": sample_warning,
                "proxy_warning": proxy_warning,
                "timeframe_label": label,
            }
        )
    return _rows_frame(rows, _timeframe_results_schema())


def build_walk_forward_by_timeframe(
    trades: pl.DataFrame,
    *,
    config: PinePythonEngineConfig | None = None,
    min_test_trades: int = 30,
) -> pl.DataFrame:
    """Choose policy on train trades and evaluate frozen policy on test trades."""

    cfg = config or PinePythonEngineConfig()
    if trades.is_empty():
        return _rows_frame([], _walk_forward_schema())
    rows: list[dict[str, Any]] = []
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for trade in trades.sort("entry_timestamp").to_dicts():
        grouped.setdefault((str(trade.get("run_symbol")), str(trade.get("run_interval"))), []).append(trade)
    for (symbol, interval), group_rows in sorted(grouped.items()):
        if not group_rows:
            continue
        splits = _walk_forward_splits(group_rows, min_test_trades=min_test_trades)
        for split_id, train_rows, test_rows in splits:
            selected_policy, train_summary = select_filter_policy_on_train(train_rows, config=cfg)
            test_allowed = _apply_policy(test_rows, selected_policy, config=cfg)
            test_summary = _trade_summary(test_allowed)
            sample_warning = len(test_allowed) < min_test_trades
            pass_flag = (
                not sample_warning
                and _float_or_zero(test_summary.get("net_pnl")) > 0
                and (_float_or_none(test_summary.get("profit_factor")) or 0.0) > 1.0
            )
            rows.append(
                {
                    "symbol": symbol,
                    "interval": interval,
                    "split_id": split_id,
                    "train_start": _timestamp_text(train_rows[0].get("entry_timestamp")),
                    "train_end": _timestamp_text(train_rows[-1].get("entry_timestamp")),
                    "test_start": _timestamp_text(test_rows[0].get("entry_timestamp")) if test_rows else None,
                    "test_end": _timestamp_text(test_rows[-1].get("entry_timestamp")) if test_rows else None,
                    "selected_filter_policy": selected_policy,
                    "train_net_pnl": train_summary["net_pnl"],
                    "test_net_pnl": test_summary["net_pnl"],
                    "test_trade_count": len(test_allowed),
                    "test_win_rate": test_summary["win_rate"],
                    "test_profit_factor": test_summary["profit_factor"],
                    "test_max_drawdown": test_summary["max_drawdown"],
                    "test_commission": test_summary["commission"],
                    "walk_forward_pass": pass_flag,
                    "sample_size_warning": sample_warning,
                    "reason": _walk_forward_reason(pass_flag, sample_warning, test_summary),
                }
            )
    return _rows_frame(rows, _walk_forward_schema())


def select_filter_policy_on_train(
    train_rows: list[dict[str, Any]],
    *,
    config: PinePythonEngineConfig,
) -> tuple[str, dict[str, Any]]:
    """Select the filter policy using train rows only."""

    summaries: list[tuple[str, dict[str, Any]]] = []
    for policy in FILTER_POLICIES:
        allowed = _apply_policy(train_rows, policy, config=config)
        summary = _trade_summary(allowed)
        summaries.append((policy, summary))
    selected_policy, selected_summary = max(
        summaries,
        key=lambda item: (
            _float_or_zero(item[1].get("net_pnl")),
            int(item[1].get("trade_count") or 0),
        ),
    )
    return selected_policy, selected_summary


def build_4h_deep_dive(
    trades: pl.DataFrame,
    *,
    output_root: Path,
    config: PinePythonEngineConfig | None = None,
) -> pl.DataFrame:
    """Build the GC=F 4h trade-level deep dive with filter states."""

    cfg = config or PinePythonEngineConfig()
    cme_by_date = _rows_by_date(_load_optional(output_root / "current_week_cme_guru_replay.csv"), "trade_date")
    guru_by_date = _rows_by_date(
        _load_optional(output_root / "same_day_filter_evidence_after_metadata.csv"),
        "resolved_market_session_date",
    )
    rows: list[dict[str, Any]] = []
    source = trades.filter((pl.col("run_symbol") == "GC=F") & (pl.col("run_interval") == "4h"))
    for raw in source.sort("entry_timestamp").to_dicts() if not source.is_empty() else []:
        date_key = _date_text(raw.get("signal_timestamp") or raw.get("entry_timestamp"))
        cme_allowed, cme_state = cme_wall_filter_allows(
            raw,
            cme_by_date.get(date_key, {}),
            return_state=True,
        )
        guru_allowed, guru_state = guru_filter_allows(
            raw,
            guru_by_date.get(date_key, {}),
            raw,
            return_state=True,
        )
        fee_allowed = _fee_hurdle(raw, config=cfg)
        no_trade_block = _bool_value(raw.get("no_trade_middle_range"))
        acceptance = _bool_value(raw.get("acceptance_breakout"))
        rejection = _bool_value(raw.get("rejection_after_level_touch"))
        price_allowed = price_filter_allows(raw, raw, config=cfg)[0]
        allowed = bool(price_allowed and cme_allowed and guru_allowed)
        rows.append(
            {
                "trade_id": raw.get("trade_id"),
                "entry_time": raw.get("entry_timestamp"),
                "exit_time": raw.get("exit_timestamp"),
                "direction": raw.get("direction"),
                "entry_price": raw.get("entry_price"),
                "exit_price": raw.get("exit_price"),
                "pnl": raw.get("gross_pnl_before_cost"),
                "pnl_after_cost": raw.get("pnl_after_cost"),
                "fee_hurdle_state": "PASS" if fee_allowed else "BLOCK_FEE_HURDLE",
                "no_trade_middle_state": "BLOCK_NO_TRADE_MIDDLE" if no_trade_block else "PASS",
                "acceptance_rejection_state": _acceptance_rejection_state(acceptance, rejection),
                "cme_overlap_state": str(cme_state),
                "guru_overlap_state": str(guru_state),
                "reason_allowed_blocked": "ALLOW_FILTERED_RESEARCH" if allowed else "BLOCK_FILTERED_RESEARCH",
            }
        )
    return _rows_frame(rows, _deep_dive_schema())


def build_fee_drag_by_timeframe(
    timeframe_results: pl.DataFrame,
    trades: pl.DataFrame,
    grid_preview: pl.DataFrame,
) -> pl.DataFrame:
    """Calculate fee drag and grid-frequency warnings by symbol/interval."""

    effect = _lower_grid_effect(grid_preview)
    rows: list[dict[str, Any]] = []
    for raw in timeframe_results.to_dicts() if not timeframe_results.is_empty() else []:
        symbol = str(raw.get("symbol") or "")
        interval = str(raw.get("interval") or "")
        trade_rows = (
            trades.filter((pl.col("run_symbol") == symbol) & (pl.col("run_interval") == interval)).to_dicts()
            if not trades.is_empty()
            else []
        )
        days = max(_date_span_days(raw.get("date_start"), raw.get("date_end")), 1.0)
        trade_count = int(raw.get("trade_count") or 0)
        commission = _float_or_zero(raw.get("commission_paid"))
        gross = sum(_float_or_zero(row.get("gross_pnl_before_cost")) for row in trade_rows)
        net = _float_or_zero(raw.get("net_pnl_after_cost"))
        trades_per_day = trade_count / days
        high_frequency_issue = trades_per_day > 1.0 or interval in {"15m", "30m", "1h"}
        recommendation = _fee_recommendation(
            effect=effect,
            high_frequency_issue=high_frequency_issue,
            sample_warning=_bool_value(raw.get("sample_size_warning")),
        )
        rows.append(
            {
                "symbol": symbol,
                "interval": interval,
                "trades_per_day": trades_per_day,
                "commission_per_trade": commission / trade_count if trade_count else 0.0,
                "commission_total": commission,
                "gross_pnl_before_cost": gross,
                "net_pnl_after_cost": net,
                "fee_drag_ratio": commission / max(abs(gross), 1.0),
                "lowering_grid_sd_len_increases_trades_and_fees": effect == "INCREASED",
                "lowering_grid_sd_len_effect": effect,
                "recommendation": recommendation,
            }
        )
    return _rows_frame(rows, _fee_drag_schema())


def build_timeframe_decision(
    timeframe_results: pl.DataFrame,
    walk_forward: pl.DataFrame,
    fee_drag: pl.DataFrame,
) -> pl.DataFrame:
    """Build conservative timeframe decision labels."""

    row_4h = _timeframe_row(timeframe_results, "GC=F", "4h")
    row_1d = _timeframe_row(timeframe_results, "GC=F", "1d")
    low_rows = [
        _timeframe_row(timeframe_results, "GC=F", interval)
        for interval in ("15m", "30m", "1h")
    ]
    any_walk_pass = (
        not walk_forward.is_empty() and walk_forward.filter(pl.col("walk_forward_pass")).height > 0
    )
    high_fee_issue = (
        not fee_drag.is_empty()
        and fee_drag.filter(pl.col("recommendation") == "DO_NOT_LOWER_GRID").height > 0
    )
    rows = [
        _decision_row(
            "DO_NOT_USE_RAW_SIGNALS",
            True,
            "Raw signals are not parity-validated and are not a standalone research decision.",
        ),
        _decision_row(
            "WATCH_4H_FILTERED_CANDIDATE",
            row_4h.get("timeframe_label") == "PROMISING_DIAGNOSTIC",
            "GC=F 4h is a filtered research candidate, pending walk-forward and parity evidence.",
        ),
        _decision_row(
            "WATCH_1D_RESEARCH_ONLY",
            row_1d.get("timeframe_label") == "PROMISING_DIAGNOSTIC",
            "GC=F 1d is slower research-only context, not an execution label.",
        ),
        _decision_row(
            "AVOID_LOW_TIMEFRAME_RAW",
            any(row.get("timeframe_label") == "NEGATIVE" for row in low_rows) or high_fee_issue,
            "Low timeframes show weak raw behavior or fee-drag sensitivity.",
        ),
        _decision_row(
            "NEEDS_WALK_FORWARD_PASS",
            not any_walk_pass,
            "No timeframe has cleared the frozen walk-forward gate with sufficient test trades.",
        ),
        _decision_row(
            "NEEDS_MORE_FORWARD_EVIDENCE",
            True,
            "More forward evidence and TradingView parity are required.",
        ),
        _decision_row(
            "NOT_READY_FOR_MONEY",
            True,
            "Research-only phase; no live, paper, broker, or account integration.",
        ),
    ]
    for row in rows:
        if row["decision_label"] not in DECISION_LABELS:
            raise ValueError(f"Unknown decision label: {row['decision_label']}")
    return _rows_frame(rows, _decision_schema())


def write_single_timeframe_outputs(
    *,
    output_root: Path,
    charts_dir: Path,
    result: SingleTimeframeValidationResult,
) -> None:
    """Write CSV, Markdown, chart, and report artifacts."""

    result.timeframe_results.write_csv(output_root / "python_single_timeframe_results.csv")
    (output_root / "python_single_timeframe_results.md").write_text(
        single_timeframe_markdown(result.timeframe_results),
        encoding="utf-8",
    )
    result.walk_forward.write_csv(output_root / "python_walk_forward_by_timeframe.csv")
    (output_root / "python_walk_forward_by_timeframe.md").write_text(
        walk_forward_markdown(result.walk_forward),
        encoding="utf-8",
    )
    result.deep_dive.write_csv(output_root / "python_4h_candidate_deep_dive.csv")
    (output_root / "python_4h_candidate_deep_dive.md").write_text(
        deep_dive_markdown(result.deep_dive),
        encoding="utf-8",
    )
    charts_dir.mkdir(parents=True, exist_ok=True)
    (charts_dir / "python_4h_candidate_chart.html").write_text(
        deep_dive_chart_html(result.deep_dive),
        encoding="utf-8",
    )
    result.fee_drag.write_csv(output_root / "python_fee_drag_by_timeframe.csv")
    (output_root / "python_fee_drag_by_timeframe.md").write_text(
        fee_drag_markdown(result.fee_drag),
        encoding="utf-8",
    )
    result.decision.write_csv(output_root / "python_timeframe_decision.csv")
    (output_root / "python_timeframe_decision.md").write_text(
        timeframe_decision_markdown(result.decision),
        encoding="utf-8",
    )
    append_parity_single_timeframe_reminder(output_root / "python_pine_parity_gap_report.md")
    append_single_timeframe_sections_to_research_report(output_root / "research_report.md", result)


def single_timeframe_markdown(frame: pl.DataFrame) -> str:
    return _safe_report_text("# Python Single-Timeframe Results\n\n" + _frame_markdown(frame, limit=80))


def walk_forward_markdown(frame: pl.DataFrame) -> str:
    return _safe_report_text(
        "# Python Walk-Forward By Timeframe\n\n"
        "Policy is selected on train rows only and then frozen for the test rows.\n\n"
        + _frame_markdown(frame, limit=120)
    )


def deep_dive_markdown(frame: pl.DataFrame) -> str:
    rows = frame.to_dicts() if not frame.is_empty() else []
    pnl = [_float_or_zero(row.get("pnl_after_cost")) for row in rows]
    sorted_pnl = sorted(pnl)
    worst_count = min(3, len(sorted_pnl))
    best_count = min(3, len(sorted_pnl))
    worst_sum = sum(sorted_pnl[:worst_count]) if worst_count else 0.0
    best_sum = sum(sorted_pnl[-best_count:]) if best_count else 0.0
    long_pnl = sum(_float_or_zero(row.get("pnl_after_cost")) for row in rows if row.get("direction") == "LONG")
    short_pnl = sum(_float_or_zero(row.get("pnl_after_cost")) for row in rows if row.get("direction") == "SHORT")
    lines = [
        "# Python 4h Candidate Deep Dive",
        "",
        f"- Trades: `{len(rows)}`",
        f"- Best three contribution: `{_format_float(best_sum)}`",
        f"- Worst three contribution: `{_format_float(worst_sum)}`",
        f"- Long / short split: `{_format_float(long_pnl)}` / `{_format_float(short_pnl)}`",
        "- Fee hurdle and combined filters are diagnostics; CME/guru overlap remains limited.",
        "",
        _frame_markdown(frame, limit=80),
    ]
    return _safe_report_text("\n".join(lines))


def fee_drag_markdown(frame: pl.DataFrame) -> str:
    return _safe_report_text(
        "# Python Fee Drag By Timeframe\n\n"
        "Lower gridSdLen warning is inherited from the formation/test grid preview.\n\n"
        + _frame_markdown(frame, limit=80)
    )


def timeframe_decision_markdown(frame: pl.DataFrame) -> str:
    return _safe_report_text("# Python Timeframe Decision\n\n" + _frame_markdown(frame, limit=20))


def deep_dive_chart_html(frame: pl.DataFrame) -> str:
    rows = frame.to_dicts() if not frame.is_empty() else []
    cumulative = []
    total = 0.0
    for row in rows:
        total += _float_or_zero(row.get("pnl_after_cost"))
        cumulative.append(total)
    if cumulative:
        min_value = min(cumulative)
        max_value = max(cumulative)
        span = max(max_value - min_value, 1.0)
        points = []
        for index, value in enumerate(cumulative):
            x = 20 + index * (760 / max(len(cumulative) - 1, 1))
            y = 260 - ((value - min_value) / span) * 220
            points.append(f"{x:.1f},{y:.1f}")
        chart = (
            '<svg viewBox="0 0 820 300" width="100%" height="320">'
            '<rect width="100%" height="100%" fill="#ffffff" />'
            f'<polyline points="{" ".join(points)}" fill="none" stroke="#0f172a" stroke-width="2" />'
            "</svg>"
        )
    else:
        chart = "<p>No GC=F 4h candidate trades available.</p>"
    table_rows = "".join(
        "<tr>"
        f"<td>{html.escape(_timestamp_text(row.get('entry_time')))}</td>"
        f"<td>{html.escape(str(row.get('direction')))}</td>"
        f"<td>{_format_float(row.get('pnl_after_cost'))}</td>"
        f"<td>{html.escape(str(row.get('reason_allowed_blocked')))}</td>"
        "</tr>"
        for row in rows[:80]
    )
    return _safe_report_text(
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        "<title>Python 4h Candidate Chart</title>"
        "<style>body{font-family:Arial,sans-serif;margin:24px;color:#111827}"
        "table{border-collapse:collapse;width:100%;font-size:12px}"
        "td,th{border:1px solid #cbd5e1;padding:4px;text-align:left}</style></head><body>"
        "<h1>Python 4h Candidate Chart</h1>"
        "<p>Research-only cumulative after-cost trade path for GC=F 4h candidates.</p>"
        f"{chart}<table><thead><tr><th>Entry</th><th>Direction</th><th>After Cost PnL</th><th>State</th></tr></thead>"
        f"<tbody>{table_rows}</tbody></table></body></html>"
    )


def append_parity_single_timeframe_reminder(path: Path) -> None:
    """Append or replace single-timeframe parity reminder."""

    start = "<!-- SINGLE TIMEFRAME PARITY REMINDER START -->"
    end = "<!-- SINGLE TIMEFRAME PARITY REMINDER END -->"
    section = "\n".join(
        [
            start,
            "## Single-Timeframe Parity Reminder",
            "",
            "- Single-timeframe Python results are not TradingView parity.",
            "- TradingView List of Trades CSV is still needed.",
            "- Bar-by-bar indicator export is still needed for exact parity.",
            "- The Python engine can support independent research, but it is not Pine-equivalent yet.",
            end,
        ]
    )
    existing = path.read_text(encoding="utf-8") if path.exists() else "# Python Pine Parity Gap Report\n"
    pattern = re.compile(f"{re.escape(start)}.*?{re.escape(end)}", flags=re.DOTALL)
    updated = pattern.sub(section, existing) if pattern.search(existing) else existing.rstrip() + "\n\n" + section + "\n"
    path.write_text(_safe_report_text(updated), encoding="utf-8")


def append_single_timeframe_sections_to_research_report(
    path: Path,
    result: SingleTimeframeValidationResult,
) -> None:
    """Append or replace the requested main report sections."""

    start = "<!-- PYTHON SINGLE TIMEFRAME VALIDATION START -->"
    end = "<!-- PYTHON SINGLE TIMEFRAME VALIDATION END -->"
    section = "\n".join([start, *single_timeframe_report_lines(result), end])
    existing = path.read_text(encoding="utf-8") if path.exists() else "# XAU Vol-OI Research Report\n"
    pattern = re.compile(f"{re.escape(start)}.*?{re.escape(end)}", flags=re.DOTALL)
    updated = pattern.sub(section, existing) if pattern.search(existing) else existing.rstrip() + "\n\n" + section + "\n"
    path.write_text(_safe_report_text(updated), encoding="utf-8")


def single_timeframe_report_lines(result: SingleTimeframeValidationResult) -> list[str]:
    row_4h = _timeframe_row(result.timeframe_results, "GC=F", "4h")
    low_negative = [
        row
        for row in (
            _timeframe_row(result.timeframe_results, "GC=F", "15m"),
            _timeframe_row(result.timeframe_results, "GC=F", "30m"),
            _timeframe_row(result.timeframe_results, "GC=F", "1h"),
        )
        if row.get("timeframe_label") == "NEGATIVE"
    ]
    wf_4h = result.walk_forward.filter(
        (pl.col("symbol") == "GC=F") & (pl.col("interval") == "4h")
    ) if not result.walk_forward.is_empty() else pl.DataFrame()
    fee_4h = _fee_row(result.fee_drag, "GC=F", "4h")
    active = [
        row["decision_label"]
        for row in result.decision.to_dicts()
        if _bool_value(row.get("active"))
    ]
    return [
        "## Single-Timeframe Python Results",
        "",
        f"- Timeframes evaluated separately: `{result.timeframe_results.height}`.",
        f"- GC=F 4h label: `{row_4h.get('timeframe_label', 'n/a')}`.",
        f"- Low-timeframe negative count: `{len(low_negative)}`.",
        "- GLD remains `PROXY_ONLY`; XAUUSD rows with insufficient coverage are marked `INSUFFICIENT_DATA`.",
        "",
        "## Walk-Forward by Timeframe",
        "",
        f"- Walk-forward rows: `{result.walk_forward.height}`.",
        f"- GC=F 4h walk-forward rows: `{wf_4h.height}`.",
        f"- Any pass: `{not result.walk_forward.filter(pl.col('walk_forward_pass')).is_empty() if not result.walk_forward.is_empty() else False}`.",
        "- Filter policy is selected on train data only and frozen for test data.",
        "",
        "## 4h Candidate Deep Dive",
        "",
        f"- GC=F 4h trade rows: `{result.deep_dive.height}`.",
        f"- GC=F 4h net after cost: `{_format_float(row_4h.get('net_pnl_after_cost'))}`.",
        "- The 4h candidate remains diagnostic until walk-forward and parity gates are stronger.",
        "",
        "## Fee Drag by Timeframe",
        "",
        f"- GC=F 4h trades per day: `{_format_float(fee_4h.get('trades_per_day'))}`.",
        f"- Lower gridSdLen effect: `{fee_4h.get('lowering_grid_sd_len_effect', 'n/a')}`.",
        f"- GC=F 4h fee recommendation: `{fee_4h.get('recommendation', 'n/a')}`.",
        "",
        "## Timeframe Decision",
        "",
        f"- Active labels: `{', '.join(active)}`.",
        "- Final operating stance: `NOT_READY_FOR_MONEY`.",
    ]


def _apply_policy(
    rows: list[dict[str, Any]],
    policy: str,
    *,
    config: PinePythonEngineConfig,
) -> list[dict[str, Any]]:
    predicates: dict[str, Callable[[dict[str, Any]], bool]] = {
        "RAW": lambda row: True,
        "PRICE_ONLY_FILTER": lambda row: price_filter_allows(row, row, config=config)[0],
        "FEE_HURDLE_FILTER": lambda row: _fee_hurdle(row, config=config),
        "OPEN_DISTANCE_FILTER": lambda row: _open_distance(row, config=config),
        "NO_TRADE_MIDDLE_RANGE": lambda row: not _bool_value(row.get("no_trade_middle_range")),
        "ACCEPTANCE_CONFIRMATION": lambda row: _bool_value(row.get("acceptance_breakout")),
        "COMBINED_CONSERVATIVE": lambda row: price_filter_allows(row, row, config=config)[0]
        and _fee_hurdle(row, config=config)
        and _open_distance(row, config=config)
        and not _bool_value(row.get("no_trade_middle_range")),
    }
    predicate = predicates[policy]
    return [row for row in rows if predicate(row)]


def _fee_hurdle(row: dict[str, Any], *, config: PinePythonEngineConfig) -> bool:
    expected = abs(_float_or_zero(row.get("signal_atr"))) + abs(_float_or_zero(row.get("signal_sd_std")))
    cost = abs(_float_or_zero(row.get("commission_paid"))) + abs(_float_or_zero(row.get("slippage_paid")))
    return expected > cost + config.fee_buffer_points


def _open_distance(row: dict[str, Any], *, config: PinePythonEngineConfig) -> bool:
    distance = _float_or_none(row.get("session_open_distance"))
    return distance is None or abs(distance) <= config.open_distance_limit_points


def _walk_forward_splits(
    rows: list[dict[str, Any]],
    *,
    min_test_trades: int,
) -> list[tuple[str, list[dict[str, Any]], list[dict[str, Any]]]]:
    if len(rows) < 2:
        return []
    if len(rows) >= min_test_trades * 3:
        splits = []
        for index, train_fraction in enumerate((0.5, 0.65), start=1):
            split = max(1, int(len(rows) * train_fraction))
            if len(rows) - split <= 0:
                continue
            splits.append((f"WF{index}", rows[:split], rows[split:]))
        return splits
    split = max(1, int(len(rows) * 0.6))
    if split >= len(rows):
        split = len(rows) - 1
    return [("WF1", rows[:split], rows[split:])]


def _trade_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    pnl = [_float_or_zero(row.get("pnl_after_cost")) for row in rows]
    wins = [value for value in pnl if value > 0]
    losses = [value for value in pnl if value < 0]
    gross_wins = sum(wins)
    gross_losses = abs(sum(losses))
    return {
        "trade_count": len(rows),
        "net_pnl": sum(pnl),
        "win_rate": len(wins) / len(rows) if rows else 0.0,
        "profit_factor": gross_wins / gross_losses if gross_losses else None,
        "max_drawdown": _max_drawdown(_cumulative(pnl)),
        "commission": sum(_float_or_zero(row.get("commission_paid")) for row in rows),
    }


def _walk_forward_reason(
    passed: bool,
    sample_warning: bool,
    test_summary: dict[str, Any],
) -> str:
    if passed:
        return "PASS_DIAGNOSTIC"
    if sample_warning:
        return "SAMPLE_TOO_SMALL"
    if _float_or_zero(test_summary.get("net_pnl")) <= 0:
        return "TEST_NET_NON_POSITIVE"
    return "TEST_FILTER_GATE_NOT_MET"


def _timeframe_label(
    *,
    symbol: str,
    quality: str,
    rows: int,
    trade_count: int,
    net_pnl: float,
) -> str:
    if symbol == "GLD" or quality == "PROXY_ONLY":
        return "PROXY_ONLY"
    if rows < 100 or trade_count < 10:
        return "INSUFFICIENT_DATA"
    if net_pnl > 0 and trade_count >= 30:
        return "PROMISING_DIAGNOSTIC"
    return "NEGATIVE"


def _acceptance_rejection_state(acceptance: bool, rejection: bool) -> str:
    if acceptance and rejection:
        return "ACCEPTANCE_AND_REJECTION"
    if acceptance:
        return "ACCEPTANCE_CONFIRMATION"
    if rejection:
        return "REJECTION_AFTER_TOUCH"
    return "NO_CONFIRMATION"


def _fee_recommendation(
    *,
    effect: str,
    high_frequency_issue: bool,
    sample_warning: bool,
) -> str:
    if effect == "INCREASED" and high_frequency_issue:
        return "DO_NOT_LOWER_GRID"
    if sample_warning:
        return "GRID_SENSITIVITY_NEEDS_MORE_DATA"
    return "TEST_GRID_WITH_FILTERS_ONLY"


def _lower_grid_effect(grid_preview: pl.DataFrame) -> str:
    if grid_preview.is_empty() or "lower_grid_sd_len_frequency_effect" not in grid_preview.columns:
        return "NO_DATA"
    values = grid_preview.get_column("lower_grid_sd_len_frequency_effect").drop_nulls().to_list()
    return str(values[0]) if values else "NO_DATA"


def _date_span_days(start: Any, end: Any) -> float:
    start_text = _timestamp_text(start)
    end_text = _timestamp_text(end)
    if not start_text or not end_text:
        return 1.0
    start_dt = _timestamp_value_local(start_text)
    end_dt = _timestamp_value_local(end_text)
    if start_dt is None or end_dt is None:
        return 1.0
    return max((end_dt - start_dt).total_seconds() / 86400.0, 1.0)


def _timestamp_value_local(value: Any):
    from research_xau_vol_oi.pine_python_engine import _timestamp_value

    return _timestamp_value(value)


def _rows_by_date(frame: pl.DataFrame, date_column: str) -> dict[str, dict[str, Any]]:
    if frame.is_empty() or date_column not in frame.columns:
        return {}
    rows: dict[str, dict[str, Any]] = {}
    for raw in frame.to_dicts():
        key = _date_text(raw.get(date_column))
        if key:
            rows[key] = raw
    return rows


def _timeframe_row(frame: pl.DataFrame, symbol: str, interval: str) -> dict[str, Any]:
    if frame.is_empty():
        return {}
    rows = frame.filter((pl.col("symbol") == symbol) & (pl.col("interval") == interval)).to_dicts()
    return rows[0] if rows else {}


def _fee_row(frame: pl.DataFrame, symbol: str, interval: str) -> dict[str, Any]:
    if frame.is_empty():
        return {}
    rows = frame.filter((pl.col("symbol") == symbol) & (pl.col("interval") == interval)).to_dicts()
    return rows[0] if rows else {}


def _decision_row(label: str, active: bool, reason: str) -> dict[str, Any]:
    return {
        "decision_label": label,
        "active": active,
        "reason": reason,
        "research_only": True,
    }


def _cumulative(values: list[float]) -> list[float]:
    output = []
    total = 0.0
    for value in values:
        total += value
        output.append(total)
    return output


def _max_drawdown(cumulative: list[float]) -> float:
    peak = 0.0
    max_drawdown = 0.0
    for value in cumulative:
        peak = max(peak, value)
        max_drawdown = min(max_drawdown, value - peak)
    return max_drawdown


def _timeframe_results_schema() -> dict[str, Any]:
    return {
        "symbol": pl.Utf8,
        "interval": pl.Utf8,
        "rows": pl.Int64,
        "date_start": pl.Utf8,
        "date_end": pl.Utf8,
        "trade_count": pl.Int64,
        "net_pnl_after_cost": pl.Float64,
        "avg_pnl": pl.Float64,
        "win_rate": pl.Float64,
        "avg_win": pl.Float64,
        "avg_loss": pl.Float64,
        "profit_factor": pl.Float64,
        "max_drawdown": pl.Float64,
        "commission_paid": pl.Float64,
        "long_pnl": pl.Float64,
        "short_pnl": pl.Float64,
        "sample_size_warning": pl.Boolean,
        "proxy_warning": pl.Boolean,
        "timeframe_label": pl.Utf8,
    }


def _walk_forward_schema() -> dict[str, Any]:
    return {
        "symbol": pl.Utf8,
        "interval": pl.Utf8,
        "split_id": pl.Utf8,
        "train_start": pl.Utf8,
        "train_end": pl.Utf8,
        "test_start": pl.Utf8,
        "test_end": pl.Utf8,
        "selected_filter_policy": pl.Utf8,
        "train_net_pnl": pl.Float64,
        "test_net_pnl": pl.Float64,
        "test_trade_count": pl.Int64,
        "test_win_rate": pl.Float64,
        "test_profit_factor": pl.Float64,
        "test_max_drawdown": pl.Float64,
        "test_commission": pl.Float64,
        "walk_forward_pass": pl.Boolean,
        "sample_size_warning": pl.Boolean,
        "reason": pl.Utf8,
    }


def _deep_dive_schema() -> dict[str, Any]:
    return {
        "trade_id": pl.Utf8,
        "entry_time": pl.Datetime(time_zone="UTC"),
        "exit_time": pl.Datetime(time_zone="UTC"),
        "direction": pl.Utf8,
        "entry_price": pl.Float64,
        "exit_price": pl.Float64,
        "pnl": pl.Float64,
        "pnl_after_cost": pl.Float64,
        "fee_hurdle_state": pl.Utf8,
        "no_trade_middle_state": pl.Utf8,
        "acceptance_rejection_state": pl.Utf8,
        "cme_overlap_state": pl.Utf8,
        "guru_overlap_state": pl.Utf8,
        "reason_allowed_blocked": pl.Utf8,
    }


def _fee_drag_schema() -> dict[str, Any]:
    return {
        "symbol": pl.Utf8,
        "interval": pl.Utf8,
        "trades_per_day": pl.Float64,
        "commission_per_trade": pl.Float64,
        "commission_total": pl.Float64,
        "gross_pnl_before_cost": pl.Float64,
        "net_pnl_after_cost": pl.Float64,
        "fee_drag_ratio": pl.Float64,
        "lowering_grid_sd_len_increases_trades_and_fees": pl.Boolean,
        "lowering_grid_sd_len_effect": pl.Utf8,
        "recommendation": pl.Utf8,
    }


def _decision_schema() -> dict[str, Any]:
    return {
        "decision_label": pl.Utf8,
        "active": pl.Boolean,
        "reason": pl.Utf8,
        "research_only": pl.Boolean,
    }


def main() -> None:
    """CLI entry point."""

    parser = argparse.ArgumentParser(description="Run single-timeframe Python validation.")
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    args = parser.parse_args()
    result = run_single_timeframe_validation_lab(output_dir=args.output_dir)
    row_4h = _timeframe_row(result.timeframe_results, "GC=F", "4h")
    print(f"timeframes: {result.timeframe_results.height}")
    print(f"gc_4h_label: {row_4h.get('timeframe_label', 'n/a')}")


if __name__ == "__main__":
    main()
