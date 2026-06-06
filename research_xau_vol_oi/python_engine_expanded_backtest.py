"""Expanded Pine-to-Python parity and Yahoo backtest layer.

This module is research-only. It expands the first Python Pine-like engine
across available Yahoo-style OHLC intervals, documents TradingView parity gaps,
and compares conservative filters over a larger local sample where available.
It does not fetch data by default and does not create execution readiness
claims.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import polars as pl

from research_xau_vol_oi.pine_python_engine import (
    PinePythonEngineConfig,
    build_pine_like_signals,
    build_yahoo_ohlc_inventory,
    cme_wall_filter_allows,
    guru_filter_allows,
    load_local_yahoo_frames,
    price_filter_allows,
    run_python_backtest,
    select_ohlc_frame,
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


FORBIDDEN_DECISION_LABELS = (
    "READY_FOR_MONEY",
    "LIVE_READY",
    "PAPER_READY",
    "READY_FOR_LIVE",
)
EXPANDED_INTERVALS = ("15m", "30m", "1h", "4h", "1d")
PLAN_ROWS = (
    ("GC=F", "1m", "recent_intraday", "Yahoo-dependent short intraday window"),
    ("GC=F", "5m", "recent_intraday", "Yahoo-dependent intraday window"),
    ("GC=F", "15m", "recent_intraday", "Yahoo-dependent intraday window"),
    ("GC=F", "30m", "recent_intraday", "Yahoo-dependent intraday window"),
    ("GC=F", "60m", "recent_intraday", "Yahoo-dependent intraday window"),
    ("GC=F", "1h", "recent_intraday", "Yahoo-dependent intraday window"),
    ("GC=F", "1d", "long_history", "Yahoo daily history where available"),
    ("XAUUSD=X", "1h", "recent_intraday", "Yahoo-dependent spot-CFD availability"),
    ("XAUUSD=X", "1d", "long_history", "Yahoo-dependent spot-CFD availability"),
    ("GLD", "1d", "long_history", "Proxy-only ETF history"),
)


@dataclass(frozen=True)
class ExpandedEngineBacktestResult:
    """All generated expanded Python engine frames."""

    data_plan: pl.DataFrame
    expanded_summary: pl.DataFrame
    expanded_trades: pl.DataFrame
    overlay_summary: pl.DataFrame
    parity_gap: pl.DataFrame
    indicator_diagnostics: pl.DataFrame
    grid_sensitivity: pl.DataFrame
    fast_use_decision: pl.DataFrame


def run_python_engine_expanded_backtest_lab(
    *,
    output_dir: str | Path = "outputs",
    config: PinePythonEngineConfig | None = None,
) -> ExpandedEngineBacktestResult:
    """Run expanded Yahoo interval backtests and write all requested artifacts."""

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    cfg = config or PinePythonEngineConfig.from_env()
    inventory, _ = build_yahoo_ohlc_inventory(output_root=output_root, config=cfg)
    local_frames = load_local_yahoo_frames(output_root)

    data_plan = build_data_expansion_plan(inventory)
    expanded_summary, expanded_trades = run_expanded_backtests(
        output_root=output_root,
        local_frames=local_frames,
        base_config=cfg,
    )
    overlay_summary = build_expanded_overlay_summary(
        expanded_trades,
        output_root=output_root,
        config=cfg,
    )
    parity_gap = build_pine_parity_gap_report(output_root=output_root)
    indicator_diagnostics = build_indicator_diagnostics()
    grid_sensitivity = build_grid_sensitivity_preview(
        output_root=output_root,
        local_frames=local_frames,
        base_config=cfg,
    )
    fast_use_decision = build_expanded_fast_use_decision(
        data_plan=data_plan,
        expanded_summary=expanded_summary,
        overlay_summary=overlay_summary,
        parity_gap=parity_gap,
    )
    result = ExpandedEngineBacktestResult(
        data_plan=data_plan,
        expanded_summary=expanded_summary,
        expanded_trades=expanded_trades,
        overlay_summary=overlay_summary,
        parity_gap=parity_gap,
        indicator_diagnostics=indicator_diagnostics,
        grid_sensitivity=grid_sensitivity,
        fast_use_decision=fast_use_decision,
    )
    write_expanded_outputs(output_root=output_root, result=result)
    return result


def build_data_expansion_plan(inventory: pl.DataFrame) -> pl.DataFrame:
    """Build the requested Yahoo data expansion plan from current inventory."""

    current = _inventory_lookup(inventory)
    rows: list[dict[str, Any]] = []
    for symbol, interval, period, expected_limit in PLAN_ROWS:
        normalized_interval = "1h" if interval == "60m" else interval
        stats = current.get((symbol, normalized_interval), {})
        current_rows = int(stats.get("rows") or 0)
        useful_for = _useful_for(symbol, normalized_interval)
        rows.append(
            {
                "symbol": symbol,
                "interval": interval,
                "period": period,
                "expected_history_limit": expected_limit,
                "current_rows": current_rows,
                "current_date_start": stats.get("start"),
                "current_date_end": stats.get("end"),
                "fetch_needed": current_rows == 0,
                "useful_for": useful_for,
            }
        )
    return _rows_frame(rows, _data_plan_schema())


def run_expanded_backtests(
    *,
    output_root: Path,
    local_frames: list[pl.DataFrame] | None = None,
    base_config: PinePythonEngineConfig | None = None,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Run the Pine-like Python backtest over available Yahoo intervals."""

    cfg = base_config or PinePythonEngineConfig()
    frames = local_frames if local_frames is not None else load_local_yahoo_frames(output_root)
    rows: list[dict[str, Any]] = []
    all_trade_rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for symbol in _available_symbols(frames, preferred=cfg.symbol):
        for interval in EXPANDED_INTERVALS:
            key = (symbol, interval)
            if key in seen:
                continue
            seen.add(key)
            selected = select_ohlc_frame(
                frames,
                config=_config_for(base_config=cfg, symbol=symbol, interval=interval),
            )
            if selected.is_empty():
                continue
            selected_symbol = selected.get_column("symbol").drop_nulls().head(1).item()
            selected_interval = selected.get_column("interval").drop_nulls().head(1).item()
            if selected_symbol != symbol or selected_interval != interval:
                continue
            run_config = _config_for(base_config=cfg, symbol=symbol, interval=interval)
            signals = build_pine_like_signals(selected, config=run_config)
            trades, summary = run_python_backtest(selected, signals, config=run_config)
            summary_row = summary.row(0, named=True) if not summary.is_empty() else {}
            ohlc_stats = selected.select(
                pl.len().alias("rows"),
                pl.col("timestamp").min().alias("date_start"),
                pl.col("timestamp").max().alias("date_end"),
                pl.col("quality").first().alias("quality"),
            ).row(0, named=True)
            rows.append(
                {
                    "symbol": symbol,
                    "interval": interval,
                    "quality": ohlc_stats["quality"],
                    "rows": ohlc_stats["rows"],
                    "date_start": _timestamp_text(ohlc_stats["date_start"]),
                    "date_end": _timestamp_text(ohlc_stats["date_end"]),
                    "trade_count": summary_row.get("trade_count", 0),
                    "win_rate": summary_row.get("win_rate", 0.0),
                    "avg_win": summary_row.get("avg_win", 0.0),
                    "avg_loss": summary_row.get("avg_loss", 0.0),
                    "avg_pnl": summary_row.get("avg_pnl", 0.0),
                    "net_pnl_after_cost": _float_or_zero(summary_row.get("avg_pnl"))
                    * int(summary_row.get("trade_count") or 0),
                    "commission_paid": summary_row.get("commission_paid", 0.0),
                    "profit_factor": summary_row.get("profit_factor"),
                    "max_drawdown": summary_row.get("max_drawdown", 0.0),
                    "long_pnl": summary_row.get("long_pnl", 0.0),
                    "short_pnl": summary_row.get("short_pnl", 0.0),
                    "sample_size_warning": summary_row.get("sample_size_warning", True),
                }
            )
            signal_by_timestamp = {
                _timestamp_text(row.get("timestamp")): row for row in signals.to_dicts()
            }
            for trade in trades.to_dicts():
                signal = signal_by_timestamp.get(_timestamp_text(trade.get("signal_timestamp")), {})
                all_trade_rows.append(
                    {
                        **trade,
                        "run_symbol": symbol,
                        "run_interval": interval,
                        "data_quality": ohlc_stats["quality"],
                        "no_trade_middle_range": _bool_value(signal.get("no_trade_middle_range")),
                        "acceptance_breakout": _bool_value(signal.get("acceptance_breakout"))
                        or _bool_value(signal.get("acceptance_breakdown")),
                        "rejection_after_level_touch": _bool_value(
                            signal.get("rejection_after_level_touch")
                        ),
                        "session_open_distance": _float_or_none(signal.get("session_open_distance")),
                        "signal_atr": _float_or_none(signal.get("atr")),
                        "signal_sd_std": _float_or_none(signal.get("sd_std")),
                    }
                )
    return _rows_frame(rows, _expanded_summary_schema()), _rows_frame(
        all_trade_rows,
        _expanded_trade_schema(),
    )


def build_expanded_overlay_summary(
    expanded_trades: pl.DataFrame,
    *,
    output_root: Path,
    config: PinePythonEngineConfig | None = None,
) -> pl.DataFrame:
    """Compare overlay blockers over all expanded trade candidates."""

    cfg = config or PinePythonEngineConfig()
    rows = expanded_trades.to_dicts() if not expanded_trades.is_empty() else []
    cme_by_date = _rows_by_date(_load_optional(output_root / "current_week_cme_guru_replay.csv"), "trade_date")
    guru_by_date = _rows_by_date(
        _load_optional(output_root / "same_day_filter_evidence_after_metadata.csv"),
        "resolved_market_session_date",
    )

    def cme_allowed(row: dict[str, Any]) -> bool:
        session_date = _date_text(row.get("signal_timestamp") or row.get("entry_timestamp"))
        return bool(cme_wall_filter_allows(row, cme_by_date.get(session_date, {})))

    def guru_allowed(row: dict[str, Any]) -> bool:
        session_date = _date_text(row.get("signal_timestamp") or row.get("entry_timestamp"))
        return bool(guru_filter_allows(row, guru_by_date.get(session_date, {}), row))

    def fee_hurdle(row: dict[str, Any]) -> bool:
        expected = abs(_float_or_zero(row.get("signal_atr"))) + abs(_float_or_zero(row.get("signal_sd_std")))
        cost = abs(_float_or_zero(row.get("commission_paid"))) + abs(_float_or_zero(row.get("slippage_paid")))
        return expected > cost + cfg.fee_buffer_points

    def open_distance(row: dict[str, Any]) -> bool:
        distance = _float_or_none(row.get("session_open_distance"))
        return distance is None or abs(distance) <= cfg.open_distance_limit_points

    policies: dict[str, Callable[[dict[str, Any]], bool]] = {
        "raw_python_strategy": lambda row: True,
        "price_only_filter": lambda row: price_filter_allows(row, row, config=cfg)[0],
        "fee_hurdle_filter": fee_hurdle,
        "open_distance_filter": open_distance,
        "no_trade_middle_filter": lambda row: not _bool_value(row.get("no_trade_middle_range")),
        "acceptance_confirmation_only": lambda row: _bool_value(row.get("acceptance_breakout")),
        "rejection_confirmation_only": lambda row: _bool_value(row.get("rejection_after_level_touch")),
        "guru_timing_confirmed_filter": guru_allowed,
        "cme_wall_filter": cme_allowed,
        "combined_conservative_filter": lambda row: price_filter_allows(row, row, config=cfg)[0]
        and fee_hurdle(row)
        and open_distance(row)
        and not _bool_value(row.get("no_trade_middle_range"))
        and cme_allowed(row)
        and guru_allowed(row),
    }
    output: list[dict[str, Any]] = []
    for policy, predicate in policies.items():
        allowed = [row for row in rows if predicate(row)]
        blocked = [row for row in rows if not predicate(row)]
        output.append(_overlay_summary_row(policy, allowed, blocked))
    return _rows_frame(output, _expanded_overlay_schema())


def build_pine_parity_gap_report(*, output_root: Path) -> pl.DataFrame:
    """Explain why Python and TradingView results do not match yet."""

    trade_list_available = discover_tradingview_trade_list(output_root) is not None
    rows = [
        _gap_row(
            "different_date_range",
            "OPEN",
            "Current Python local intraday sample is narrower than the 2025-01-02 to 2026-05-25 TradingView baseline.",
            0,
            "Expand Yahoo/local OHLC coverage before comparing trade counts.",
        ),
        _gap_row(
            "different_symbol_source",
            "OPEN",
            "Yahoo GC=F/XAUUSD/GLD bars are not guaranteed to match the TradingView chart source.",
            0,
            "Lock the exact TradingView symbol/source and session calendar.",
        ),
        _gap_row(
            "missing_pine_trade_list",
            "RESOLVED" if trade_list_available else "OPEN",
            "TradingView List of Trades CSV is required for trade-level overlay and parity diagnostics.",
            1,
            "Import TradingView List of Trades CSV if the user provides it.",
        ),
        _gap_row(
            "partial_pine_logic_implementation",
            "OPEN",
            "Python currently recreates the Pine behavior as a simplified candidate engine.",
            2,
            "Implement ladder grid parity.",
        ),
        _gap_row(
            "pyramiding_not_exact",
            "OPEN",
            "Python starts with single-position simulation; TradingView baseline used pyramiding=3.",
            3,
            "Implement pyramiding parity.",
        ),
        _gap_row(
            "mtf_security_behavior_not_exact",
            "OPEN",
            "TradingView request.security and MTF alignment behavior is not fully reproduced.",
            4,
            "Implement MTF/security-style logic.",
        ),
        _gap_row(
            "session_timezone_alignment",
            "OPEN",
            "Yahoo timestamps and TradingView exchange sessions can differ.",
            5,
            "Align session/timezone.",
        ),
        _gap_row(
            "bar_by_bar_indicator_values",
            "OPEN",
            "Indicator values need direct bar-by-bar comparison against Pine exports.",
            6,
            "Compare indicator values bar-by-bar.",
        ),
        _gap_row(
            "fill_cost_assumptions",
            "OPEN",
            "Python uses bar-close fills; TradingView broker emulator assumptions can differ.",
            0,
            "Document and align commission, slippage, and fill assumptions.",
        ),
    ]
    return _rows_frame(rows, _parity_gap_schema())


def build_indicator_diagnostics() -> pl.DataFrame:
    """Document implementation status and parity risk for each indicator."""

    rows = [
        _indicator_row("ema", True, "ta.ema", "LOW", "synthetic known-value/no-lookahead", "MEDIUM"),
        _indicator_row("sma", True, "ta.sma", "LOW", "implicit in bands", "LOW"),
        _indicator_row("stdev", True, "ta.stdev", "MEDIUM", "no-lookahead SD band", "HIGH"),
        _indicator_row("zscore", True, "custom sigma", "MEDIUM", "no-trade middle tests", "HIGH"),
        _indicator_row("atr", True, "ta.atr", "MEDIUM", "backtest cost/stop tests", "HIGH"),
        _indicator_row("donchian", True, "ta.highest/ta.lowest", "MEDIUM", "no-lookahead test", "HIGH"),
        _indicator_row("rsi", True, "ta.rsi", "MEDIUM", "no-lookahead test", "HIGH"),
        _indicator_row("macd", True, "ta.macd", "MEDIUM", "no-lookahead test", "HIGH"),
        _indicator_row("stochastic", True, "ta.stoch", "MEDIUM", "engine smoke", "MEDIUM"),
        _indicator_row("cci", True, "ta.cci", "MEDIUM", "engine smoke", "MEDIUM"),
        _indicator_row("parabolic_sar", True, "ta.sar", "HIGH", "approximation only", "MEDIUM"),
        _indicator_row("envelope_bands", True, "custom ENV", "MEDIUM", "engine smoke", "MEDIUM"),
        _indicator_row("sd_bands", True, "custom SD bands", "HIGH", "no-lookahead test", "CRITICAL"),
        _indicator_row("range_regime", True, "custom regime", "HIGH", "engine smoke", "HIGH"),
        _indicator_row("vpi", False, "custom VPI", "HIGH", "not implemented", "CRITICAL"),
        _indicator_row("mtf", False, "request.security/MTF", "HIGH", "not implemented", "CRITICAL"),
        _indicator_row("sweep", True, "custom sweep/rejection proxy", "HIGH", "rejection test", "HIGH"),
        _indicator_row("adapt", False, "custom adapt", "HIGH", "not implemented", "HIGH"),
    ]
    return _rows_frame(rows, _indicator_diagnostic_schema())


def build_grid_sensitivity_preview(
    *,
    output_root: Path,
    local_frames: list[pl.DataFrame] | None = None,
    base_config: PinePythonEngineConfig | None = None,
) -> pl.DataFrame:
    """Preview SD grid sensitivity with formation-only selection."""

    cfg = base_config or PinePythonEngineConfig()
    frames = local_frames if local_frames is not None else load_local_yahoo_frames(output_root)
    selected = select_ohlc_frame(
        frames,
        config=_config_for(base_config=cfg, symbol=cfg.symbol, interval=cfg.interval),
    )
    if selected.is_empty():
        return _rows_frame([], _grid_sensitivity_schema())
    rows: list[dict[str, Any]] = []
    for grid_sd_len in (20, 30, 50, 80):
        for entry_sd in (1.0, 1.25, 1.5, 2.0):
            for no_trade_sd in (0.25, 0.50, 0.75):
                run_config = PinePythonEngineConfig(
                    start=cfg.start,
                    end=cfg.end,
                    symbol=cfg.symbol,
                    interval=cfg.interval,
                    enable_yahoo_intraday_fetch=False,
                    grid_sd_len=grid_sd_len,
                    entry_sd=entry_sd,
                    stop_sd=cfg.stop_sd,
                    no_trade_sd=no_trade_sd,
                    donchian_len=cfg.donchian_len,
                    atr_len=cfg.atr_len,
                    ema_fast_len=cfg.ema_fast_len,
                    ema_slow_len=cfg.ema_slow_len,
                    cci_len=cfg.cci_len,
                    stochastic_len=cfg.stochastic_len,
                    max_hold_bars=cfg.max_hold_bars,
                    commission_rate=cfg.commission_rate,
                    slippage_points=cfg.slippage_points,
                    open_distance_limit_points=cfg.open_distance_limit_points,
                    fee_buffer_points=cfg.fee_buffer_points,
                    min_warmup_bars=cfg.min_warmup_bars,
                )
                signals = build_pine_like_signals(selected, config=run_config)
                trades, _ = run_python_backtest(selected, signals, config=run_config)
                rows.append(
                    _grid_row(
                        trades,
                        grid_sd_len=grid_sd_len,
                        entry_sd=entry_sd,
                        no_trade_sd=no_trade_sd,
                    )
                )
    frame = _rows_frame(rows, _grid_sensitivity_schema())
    if frame.is_empty():
        return frame
    formation_best = frame.sort(
        ["formation_avg_pnl", "formation_trade_count"],
        descending=[True, True],
    ).row(0, named=True)
    baseline_frequency = _mean_trade_count(frame.filter(pl.col("grid_sd_len") == 50))
    lower_frequency = _mean_trade_count(frame.filter(pl.col("grid_sd_len").is_in([20, 30])))
    effect = "NO_CHANGE"
    if lower_frequency > baseline_frequency:
        effect = "INCREASED"
    elif lower_frequency < baseline_frequency:
        effect = "DECREASED"
    return frame.with_columns(
        (
            (pl.col("grid_sd_len") == formation_best["grid_sd_len"])
            & (pl.col("entry_sd") == formation_best["entry_sd"])
            & (pl.col("no_trade_sd") == formation_best["no_trade_sd"])
        ).alias("selected_for_test"),
        pl.lit("formation_only").alias("selection_basis"),
        pl.lit(effect).alias("lower_grid_sd_len_frequency_effect"),
    )


def build_expanded_fast_use_decision(
    *,
    data_plan: pl.DataFrame,
    expanded_summary: pl.DataFrame,
    overlay_summary: pl.DataFrame,
    parity_gap: pl.DataFrame,
) -> pl.DataFrame:
    """Build conservative fast-use labels for the expanded layer."""

    raw = _policy_row(overlay_summary, "raw_python_strategy")
    combined = _policy_row(overlay_summary, "combined_conservative_filter")
    parity_open = not parity_gap.filter(pl.col("status") == "OPEN").is_empty()
    needs_more_history = data_plan.filter(pl.col("fetch_needed")).height > 0
    cme_overlap = _policy_row(overlay_summary, "cme_wall_filter").get("trades_blocked", 0) > 0
    labels = [
        (
            "DO_NOT_USE_RAW_SIGNALS",
            _float_or_zero(raw.get("avg_pnl")) <= 0 or parity_open or needs_more_history,
            "Raw expanded Python signals are not parity-validated and cannot be used directly.",
        ),
        (
            "USE_AS_WATCHLIST_ONLY",
            True,
            "Current evidence supports watchlist/research review only.",
        ),
        (
            "USE_FILTERED_SIGNALS_FOR_RESEARCH_ONLY",
            _float_or_zero(combined.get("net_filter_value")) > 0,
            "Filters may reduce bad candidates, but this remains sample-limited research.",
        ),
        (
            "NEEDS_PARITY_WITH_TRADINGVIEW",
            parity_open,
            "TradingView List of Trades and bar-by-bar indicator parity are still missing.",
        ),
        (
            "NEEDS_MORE_YAHOO_HISTORY",
            needs_more_history,
            "Local Yahoo-style coverage does not yet span the TradingView baseline.",
        ),
        (
            "NEEDS_CME_OVERLAP",
            not cme_overlap,
            "CME wall filter needs more overlapping trade candidates before evaluation.",
        ),
        (
            "NOT_READY_FOR_MONEY",
            True,
            "Research-only phase; no live, paper, broker, or account integration.",
        ),
    ]
    rows = [
        {
            "decision_rank": index + 1,
            "decision_label": label,
            "active": active,
            "reason": reason,
            "research_only": True,
        }
        for index, (label, active, reason) in enumerate(labels)
    ]
    for row in rows:
        if row["decision_label"] in FORBIDDEN_DECISION_LABELS:
            raise ValueError(f"Forbidden decision label: {row['decision_label']}")
    return _rows_frame(rows, _fast_use_schema())


def write_expanded_outputs(*, output_root: Path, result: ExpandedEngineBacktestResult) -> None:
    """Write all expanded layer CSV/Markdown artifacts."""

    result.data_plan.write_csv(output_root / "python_engine_data_expansion_plan.csv")
    (output_root / "python_engine_data_expansion_plan.md").write_text(
        data_plan_markdown(result.data_plan),
        encoding="utf-8",
    )
    result.expanded_summary.write_csv(output_root / "python_expanded_backtest_summary.csv")
    (output_root / "python_expanded_backtest_report.md").write_text(
        expanded_backtest_markdown(result.expanded_summary),
        encoding="utf-8",
    )
    result.overlay_summary.write_csv(output_root / "python_expanded_overlay_summary.csv")
    (output_root / "python_expanded_overlay_report.md").write_text(
        expanded_overlay_markdown(result.overlay_summary),
        encoding="utf-8",
    )
    result.parity_gap.write_csv(output_root / "python_pine_parity_gap_report.csv")
    (output_root / "python_pine_parity_gap_report.md").write_text(
        parity_gap_markdown(result.parity_gap),
        encoding="utf-8",
    )
    result.indicator_diagnostics.write_csv(output_root / "python_indicator_diagnostics.csv")
    (output_root / "python_indicator_diagnostics.md").write_text(
        indicator_diagnostics_markdown(result.indicator_diagnostics),
        encoding="utf-8",
    )
    result.grid_sensitivity.write_csv(output_root / "python_grid_sensitivity_preview.csv")
    (output_root / "python_grid_sensitivity_preview.md").write_text(
        grid_sensitivity_markdown(result.grid_sensitivity),
        encoding="utf-8",
    )
    result.fast_use_decision.write_csv(output_root / "python_engine_fast_use_decision.csv")
    (output_root / "python_engine_fast_use_decision.md").write_text(
        fast_use_markdown(result.fast_use_decision),
        encoding="utf-8",
    )
    append_expanded_sections_to_research_report(output_root / "research_report.md", result)


def data_plan_markdown(frame: pl.DataFrame) -> str:
    return _safe_report_text("# Python Engine Data Expansion Plan\n\n" + _frame_markdown(frame, limit=80))


def expanded_backtest_markdown(frame: pl.DataFrame) -> str:
    return _safe_report_text(
        "# Python Expanded Backtest Report\n\n"
        "Runs use bar-close research simulation over available Yahoo-style OHLC intervals.\n\n"
        + _frame_markdown(frame, limit=80)
    )


def expanded_overlay_markdown(frame: pl.DataFrame) -> str:
    return _safe_report_text(
        "# Python Expanded Overlay Report\n\n"
        "Filters are blockers only; small positive subsets are not proof of readiness.\n\n"
        + _frame_markdown(frame, limit=80)
    )


def parity_gap_markdown(frame: pl.DataFrame) -> str:
    return _safe_report_text("# Python Pine Parity Gap Report\n\n" + _frame_markdown(frame, limit=80))


def indicator_diagnostics_markdown(frame: pl.DataFrame) -> str:
    return _safe_report_text("# Python Indicator Diagnostics\n\n" + _frame_markdown(frame, limit=80))


def grid_sensitivity_markdown(frame: pl.DataFrame) -> str:
    return _safe_report_text(
        "# Python Grid Sensitivity Preview\n\n"
        "Formation/test split is used. This is a preview, not full-sample parameter selection.\n\n"
        + _frame_markdown(frame, limit=80)
    )


def fast_use_markdown(frame: pl.DataFrame) -> str:
    return _safe_report_text("# Python Engine Fast-Use Decision\n\n" + _frame_markdown(frame, limit=20))


def append_expanded_sections_to_research_report(
    path: Path,
    result: ExpandedEngineBacktestResult,
) -> None:
    """Add or replace expanded Python engine sections in the main report."""

    start = "<!-- PYTHON ENGINE EXPANDED BACKTEST START -->"
    end = "<!-- PYTHON ENGINE EXPANDED BACKTEST END -->"
    section = "\n".join([start, *expanded_report_lines(result), end])
    existing = path.read_text(encoding="utf-8") if path.exists() else "# XAU Vol-OI Research Report\n"
    pattern = re.compile(f"{re.escape(start)}.*?{re.escape(end)}", flags=re.DOTALL)
    updated = pattern.sub(section, existing) if pattern.search(existing) else existing.rstrip() + "\n\n" + section + "\n"
    path.write_text(_safe_report_text(updated), encoding="utf-8")


def expanded_report_lines(result: ExpandedEngineBacktestResult) -> list[str]:
    """Return requested research_report.md sections."""

    raw = _policy_row(result.overlay_summary, "raw_python_strategy")
    combined = _policy_row(result.overlay_summary, "combined_conservative_filter")
    best_interval = _best_backtest_row(result.expanded_summary)
    active_labels = [
        row["decision_label"]
        for row in result.fast_use_decision.to_dicts()
        if _bool_value(row.get("active"))
    ]
    return [
        "## Expanded Yahoo Backtest",
        "",
        f"- Expanded runs: `{result.expanded_summary.height}` symbol/interval combinations.",
        f"- Best interval by avg PnL in this diagnostic: `{best_interval.get('symbol', 'n/a')} {best_interval.get('interval', 'n/a')}`.",
        f"- Total expanded candidate trades: `{int(raw.get('trades_allowed') or 0)}`.",
        f"- Raw expanded after-cost PnL: `{_format_float(raw.get('net_pnl_after_cost'))}`.",
        "",
        "## Overlay Comparison",
        "",
        f"- Combined conservative allowed trades: `{combined.get('trades_allowed', 0)}`.",
        f"- Combined conservative blocked trades: `{combined.get('trades_blocked', 0)}`.",
        f"- Combined net filter value: `{_format_float(combined.get('net_filter_value'))}`.",
        "- Small positive subsets remain sample-limited and are not proof of readiness.",
        "",
        "## Pine Parity Gap",
        "",
        f"- Open parity gaps: `{result.parity_gap.filter(pl.col('status') == 'OPEN').height}`.",
        "- Top priority: import a TradingView List of Trades CSV, then compare indicator values bar-by-bar.",
        "",
        "## Indicator Diagnostics",
        "",
        f"- Critical diagnostics: `{result.indicator_diagnostics.filter(pl.col('priority') == 'CRITICAL').height}`.",
        "- Highest-risk gaps remain VPI, MTF/security behavior, SD grid parity, and full ladder/pyramiding behavior.",
        "",
        "## Grid Sensitivity Preview",
        "",
        f"- Preview rows: `{result.grid_sensitivity.height}`.",
        f"- Lower gridSdLen frequency effect: `{_grid_effect(result.grid_sensitivity)}`.",
        "- Selection basis: `formation_only`; no full-sample parameter is selected.",
        "",
        "## Fast-Use Decision",
        "",
        f"- Active labels: `{', '.join(active_labels)}`.",
        "- Final operating stance: `NOT_READY_FOR_MONEY`.",
    ]


def discover_tradingview_trade_list(output_root: Path) -> Path | None:
    """Find a TradingView List of Trades CSV if present."""

    names = (
        "pine_trades.csv",
        "pine_trade_list.csv",
        "tradingview_trades.csv",
        "tradingview_list_of_trades.csv",
        "TradingView_List_of_Trades.csv",
        "List of Trades.csv",
    )
    for root in (output_root, Path(".")):
        for name in names:
            candidate = root / name
            if candidate.exists():
                return candidate
    return None


def _overlay_summary_row(
    policy: str,
    allowed: list[dict[str, Any]],
    blocked: list[dict[str, Any]],
) -> dict[str, Any]:
    pnl = [_float_or_zero(row.get("pnl_after_cost")) for row in allowed]
    blocked_pnl = [_float_or_zero(row.get("pnl_after_cost")) for row in blocked]
    wins = [value for value in pnl if value > 0]
    losses = [value for value in pnl if value < 0]
    gross_wins = sum(wins)
    gross_losses = abs(sum(losses))
    avoided_loss = abs(sum(value for value in blocked_pnl if value < 0))
    opportunity_cost = sum(value for value in blocked_pnl if value > 0)
    return {
        "policy": policy,
        "trades_allowed": len(allowed),
        "trades_blocked": len(blocked),
        "net_pnl_after_cost": sum(pnl),
        "avg_pnl": sum(pnl) / len(pnl) if pnl else 0.0,
        "win_rate": len(wins) / len(allowed) if allowed else 0.0,
        "profit_factor": gross_wins / gross_losses if gross_losses else None,
        "avoided_loss": avoided_loss,
        "opportunity_cost": opportunity_cost,
        "net_filter_value": avoided_loss - opportunity_cost,
        "false_block_rate": opportunity_cost / max(abs(sum(blocked_pnl)), 1.0),
        "sample_size_warning": len(allowed) < 30,
        "research_only": True,
    }


def _grid_row(
    trades: pl.DataFrame,
    *,
    grid_sd_len: int,
    entry_sd: float,
    no_trade_sd: float,
) -> dict[str, Any]:
    rows = trades.to_dicts() if not trades.is_empty() else []
    split_index = len(rows) // 2
    formation = rows[:split_index]
    test = rows[split_index:]
    full_pnl = [_float_or_zero(row.get("pnl_after_cost")) for row in rows]
    formation_pnl = [_float_or_zero(row.get("pnl_after_cost")) for row in formation]
    test_pnl = [_float_or_zero(row.get("pnl_after_cost")) for row in test]
    return {
        "grid_sd_len": grid_sd_len,
        "entry_sd": entry_sd,
        "no_trade_sd": no_trade_sd,
        "formation_trade_count": len(formation),
        "test_trade_count": len(test),
        "full_sample_trade_count": len(rows),
        "formation_avg_pnl": sum(formation_pnl) / len(formation_pnl) if formation_pnl else 0.0,
        "test_avg_pnl": sum(test_pnl) / len(test_pnl) if test_pnl else 0.0,
        "full_sample_avg_pnl": sum(full_pnl) / len(full_pnl) if full_pnl else 0.0,
        "formation_commission_paid": sum(_float_or_zero(row.get("commission_paid")) for row in formation),
        "full_sample_commission_paid": sum(_float_or_zero(row.get("commission_paid")) for row in rows),
        "selected_for_test": False,
        "selection_basis": "formation_only",
        "lower_grid_sd_len_frequency_effect": "NO_CHANGE",
        "sample_size_warning": len(test) < 30,
    }


def _inventory_lookup(inventory: pl.DataFrame) -> dict[tuple[str, str], dict[str, Any]]:
    lookup: dict[tuple[str, str], dict[str, Any]] = {}
    if inventory.is_empty():
        return lookup
    for raw in inventory.to_dicts():
        if not _bool_value(raw.get("available")):
            continue
        key = (str(raw.get("symbol")), "1h" if raw.get("interval") == "60m" else str(raw.get("interval")))
        existing = lookup.get(key)
        if existing is None or int(raw.get("rows") or 0) > int(existing.get("rows") or 0):
            lookup[key] = raw
    return lookup


def _available_symbols(frames: list[pl.DataFrame], *, preferred: str) -> list[str]:
    symbols: list[str] = []
    for symbol in (preferred, "GC=F", "XAUUSD=X", "GLD"):
        if symbol not in symbols:
            symbols.append(symbol)
    available = set()
    for frame in frames:
        if frame.is_empty() or "symbol" not in frame.columns:
            continue
        available.update(str(value) for value in frame.get_column("symbol").drop_nulls().unique().to_list())
    return [symbol for symbol in symbols if symbol in available]


def _config_for(
    *,
    base_config: PinePythonEngineConfig,
    symbol: str,
    interval: str,
) -> PinePythonEngineConfig:
    return PinePythonEngineConfig(
        start=base_config.start,
        end=base_config.end,
        symbol=symbol,
        interval=interval,
        enable_yahoo_intraday_fetch=False,
        grid_sd_len=base_config.grid_sd_len,
        entry_sd=base_config.entry_sd,
        stop_sd=base_config.stop_sd,
        no_trade_sd=base_config.no_trade_sd,
        donchian_len=base_config.donchian_len,
        atr_len=base_config.atr_len,
        ema_fast_len=base_config.ema_fast_len,
        ema_slow_len=base_config.ema_slow_len,
        cci_len=base_config.cci_len,
        stochastic_len=base_config.stochastic_len,
        max_hold_bars=base_config.max_hold_bars,
        commission_rate=base_config.commission_rate,
        slippage_points=base_config.slippage_points,
        open_distance_limit_points=base_config.open_distance_limit_points,
        fee_buffer_points=base_config.fee_buffer_points,
        min_warmup_bars=base_config.min_warmup_bars,
    )


def _useful_for(symbol: str, interval: str) -> str:
    if symbol == "GLD":
        return "proxy_only|daily_baseline"
    if interval == "1d":
        return "daily_baseline|indicator_parity"
    if interval in {"1m", "5m", "15m", "30m", "1h"}:
        return "indicator_parity|intraday_backtest"
    return "indicator_parity"


def _rows_by_date(frame: pl.DataFrame, date_column: str) -> dict[str, dict[str, Any]]:
    if frame.is_empty() or date_column not in frame.columns:
        return {}
    rows: dict[str, dict[str, Any]] = {}
    for raw in frame.to_dicts():
        key = _date_text(raw.get(date_column))
        if key:
            rows[key] = raw
    return rows


def _gap_row(
    gap: str,
    status: str,
    explanation: str,
    priority_fix_rank: int,
    priority_fix: str,
) -> dict[str, Any]:
    return {
        "gap": gap,
        "status": status,
        "explanation": explanation,
        "priority_fix_rank": priority_fix_rank,
        "priority_fix": priority_fix,
        "research_only": True,
    }


def _indicator_row(
    indicator: str,
    implemented: bool,
    pine_equivalent: str,
    known_parity_risk: str,
    test_coverage: str,
    priority: str,
) -> dict[str, Any]:
    return {
        "indicator": indicator,
        "implemented": implemented,
        "pine_equivalent": pine_equivalent,
        "known_parity_risk": known_parity_risk,
        "test_coverage": test_coverage,
        "priority": priority,
    }


def _mean_trade_count(frame: pl.DataFrame) -> float:
    if frame.is_empty():
        return 0.0
    return sum(frame.get_column("full_sample_trade_count").to_list()) / frame.height


def _policy_row(frame: pl.DataFrame, policy: str) -> dict[str, Any]:
    if frame.is_empty() or "policy" not in frame.columns:
        return {}
    rows = frame.filter(pl.col("policy") == policy).to_dicts()
    return rows[0] if rows else {}


def _best_backtest_row(frame: pl.DataFrame) -> dict[str, Any]:
    if frame.is_empty():
        return {}
    return frame.sort(["avg_pnl", "trade_count"], descending=[True, True]).row(0, named=True)


def _grid_effect(frame: pl.DataFrame) -> str:
    if frame.is_empty() or "lower_grid_sd_len_frequency_effect" not in frame.columns:
        return "NO_DATA"
    return str(frame.get_column("lower_grid_sd_len_frequency_effect").drop_nulls().head(1).item())


def _data_plan_schema() -> dict[str, Any]:
    return {
        "symbol": pl.Utf8,
        "interval": pl.Utf8,
        "period": pl.Utf8,
        "expected_history_limit": pl.Utf8,
        "current_rows": pl.Int64,
        "current_date_start": pl.Utf8,
        "current_date_end": pl.Utf8,
        "fetch_needed": pl.Boolean,
        "useful_for": pl.Utf8,
    }


def _expanded_summary_schema() -> dict[str, Any]:
    return {
        "symbol": pl.Utf8,
        "interval": pl.Utf8,
        "quality": pl.Utf8,
        "rows": pl.Int64,
        "date_start": pl.Utf8,
        "date_end": pl.Utf8,
        "trade_count": pl.Int64,
        "win_rate": pl.Float64,
        "avg_win": pl.Float64,
        "avg_loss": pl.Float64,
        "avg_pnl": pl.Float64,
        "net_pnl_after_cost": pl.Float64,
        "commission_paid": pl.Float64,
        "profit_factor": pl.Float64,
        "max_drawdown": pl.Float64,
        "long_pnl": pl.Float64,
        "short_pnl": pl.Float64,
        "sample_size_warning": pl.Boolean,
    }


def _expanded_trade_schema() -> dict[str, Any]:
    return {
        "trade_id": pl.Utf8,
        "symbol": pl.Utf8,
        "interval": pl.Utf8,
        "direction": pl.Utf8,
        "signal_timestamp": pl.Datetime(time_zone="UTC"),
        "entry_timestamp": pl.Datetime(time_zone="UTC"),
        "exit_timestamp": pl.Datetime(time_zone="UTC"),
        "signal_bar_index": pl.Int64,
        "entry_bar_index": pl.Int64,
        "exit_bar_index": pl.Int64,
        "entry_price": pl.Float64,
        "exit_price": pl.Float64,
        "gross_pnl_before_cost": pl.Float64,
        "pnl_after_cost": pl.Float64,
        "commission_paid": pl.Float64,
        "slippage_paid": pl.Float64,
        "bars_in_trade": pl.Int64,
        "entry_reason": pl.Utf8,
        "exit_reason": pl.Utf8,
        "pine_like_score": pl.Float64,
        "sd_position": pl.Float64,
        "atr": pl.Float64,
        "stop_price": pl.Float64,
        "target_price": pl.Float64,
        "research_only": pl.Boolean,
        "run_symbol": pl.Utf8,
        "run_interval": pl.Utf8,
        "data_quality": pl.Utf8,
        "no_trade_middle_range": pl.Boolean,
        "acceptance_breakout": pl.Boolean,
        "rejection_after_level_touch": pl.Boolean,
        "session_open_distance": pl.Float64,
        "signal_atr": pl.Float64,
        "signal_sd_std": pl.Float64,
    }


def _expanded_overlay_schema() -> dict[str, Any]:
    return {
        "policy": pl.Utf8,
        "trades_allowed": pl.Int64,
        "trades_blocked": pl.Int64,
        "net_pnl_after_cost": pl.Float64,
        "avg_pnl": pl.Float64,
        "win_rate": pl.Float64,
        "profit_factor": pl.Float64,
        "avoided_loss": pl.Float64,
        "opportunity_cost": pl.Float64,
        "net_filter_value": pl.Float64,
        "false_block_rate": pl.Float64,
        "sample_size_warning": pl.Boolean,
        "research_only": pl.Boolean,
    }


def _parity_gap_schema() -> dict[str, Any]:
    return {
        "gap": pl.Utf8,
        "status": pl.Utf8,
        "explanation": pl.Utf8,
        "priority_fix_rank": pl.Int64,
        "priority_fix": pl.Utf8,
        "research_only": pl.Boolean,
    }


def _indicator_diagnostic_schema() -> dict[str, Any]:
    return {
        "indicator": pl.Utf8,
        "implemented": pl.Boolean,
        "pine_equivalent": pl.Utf8,
        "known_parity_risk": pl.Utf8,
        "test_coverage": pl.Utf8,
        "priority": pl.Utf8,
    }


def _grid_sensitivity_schema() -> dict[str, Any]:
    return {
        "grid_sd_len": pl.Int64,
        "entry_sd": pl.Float64,
        "no_trade_sd": pl.Float64,
        "formation_trade_count": pl.Int64,
        "test_trade_count": pl.Int64,
        "full_sample_trade_count": pl.Int64,
        "formation_avg_pnl": pl.Float64,
        "test_avg_pnl": pl.Float64,
        "full_sample_avg_pnl": pl.Float64,
        "formation_commission_paid": pl.Float64,
        "full_sample_commission_paid": pl.Float64,
        "selected_for_test": pl.Boolean,
        "selection_basis": pl.Utf8,
        "lower_grid_sd_len_frequency_effect": pl.Utf8,
        "sample_size_warning": pl.Boolean,
    }


def _fast_use_schema() -> dict[str, Any]:
    return {
        "decision_rank": pl.Int64,
        "decision_label": pl.Utf8,
        "active": pl.Boolean,
        "reason": pl.Utf8,
        "research_only": pl.Boolean,
    }


def main() -> None:
    """CLI entry point."""

    parser = argparse.ArgumentParser(description="Run expanded Python Pine engine backtest lab.")
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    args = parser.parse_args()
    result = run_python_engine_expanded_backtest_lab(output_dir=args.output_dir)
    raw = _policy_row(result.overlay_summary, "raw_python_strategy")
    print(f"expanded_runs: {result.expanded_summary.height}")
    print(f"raw_trades: {raw.get('trades_allowed', 0)}")


if __name__ == "__main__":
    main()
