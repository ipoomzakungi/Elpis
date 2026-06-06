"""CME overlap date entry/TP pilot backtest lab.

This module is research-only. It runs a short-range pilot only on dates where
local XAU/USD bid/ask price data and CME OI/IV context overlap. CME data is
treated as an as-of market map, never as an automatic buy/sell signal.
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import polars as pl


TIMEFRAME_MINUTES = {
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "2h": 120,
}
RULE_TEMPLATE_IDS = (
    "WALL_REJECTION_FADE",
    "WALL_ACCEPTANCE_BREAKOUT",
    "LOW_OI_GAP_SQUEEZE",
    "NO_TRADE_MIDDLE_RANGE",
    "PINE_SIGNAL_WITH_CME_FILTER",
)
DECISION_LABELS = (
    "CME_OVERLAP_PILOT_READY",
    "CME_WALL_ENTRY_TP_CANDIDATE",
    "CME_WALL_CONTEXT_ONLY",
    "NEEDS_BASIS",
    "NEEDS_IV",
    "POST_EVENT_REPLAY_ONLY",
    "NOT_ENOUGH_FOR_VALIDATION",
    "NOT_READY_FOR_MONEY",
)
FORBIDDEN_REPORT_PHRASES = (
    "profitable",
    "safe to trade",
    "live ready",
    "live-ready",
    "paper ready",
    "paper-ready",
    "money ready",
    "ready for money",
    "money-readiness",
)
MIN_VALIDATION_DATES = 30
DEFAULT_START = "2026-05-15"
DEFAULT_END = "2026-05-15"


@dataclass(frozen=True)
class CmeOverlapEntryTpLabResult:
    """All generated CME overlap lab frames and chart references."""

    date_audit: pl.DataFrame
    market_map: pl.DataFrame
    rule_templates: pl.DataFrame
    trades: pl.DataFrame
    summary: pl.DataFrame
    timeframe_comparison: pl.DataFrame
    decision: pl.DataFrame
    chart_paths: tuple[Path, ...]
    final_decision: str


def run_cme_overlap_entry_tp_lab(
    *,
    output_dir: str | Path = "outputs",
    start: str | None = None,
    end: str | None = None,
    timeframes: str | list[str] | tuple[str, ...] | None = None,
    mode: str | None = None,
) -> CmeOverlapEntryTpLabResult:
    """Run the CME overlap pilot lab and write CSV/Markdown/HTML artifacts."""

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    charts_dir = output_root / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    start_text = start or os.getenv("XAU_CME_PILOT_START") or DEFAULT_START
    end_text = end or os.getenv("XAU_CME_PILOT_END") or DEFAULT_END
    selected_timeframes = _parse_timeframes(
        timeframes or os.getenv("XAU_CME_PILOT_TIMEFRAMES") or "15m,30m,1h,2h",
    )
    selected_mode = mode or os.getenv("XAU_CME_PILOT_MODE") or "OVERLAP_ONLY"
    start_date = _parse_date(start_text)
    end_date = _parse_date(end_text)

    price_by_timeframe = load_price_timeframes(
        output_root=output_root,
        start_date=start_date,
        end_date=end_date,
        timeframes=selected_timeframes,
    )
    cme_frames = load_cme_overlap_inputs(output_root)

    date_audit = build_overlap_date_audit(
        dates=_date_range(start_date, end_date),
        price_by_timeframe=price_by_timeframe,
        cme_oi=cme_frames["cme_oi"],
        cme_iv=cme_frames["cme_iv"],
        cme_futures=cme_frames["cme_futures"],
        basis=cme_frames["basis"],
        guru_context=_concat_or_empty(
            [cme_frames["guru_replay"], cme_frames["guru_overlay"]],
            _generic_schema(),
        ),
        pine_signals=cme_frames["pine_signals"],
        mode=selected_mode,
    )
    market_map = build_pilot_market_map(
        date_audit=date_audit,
        price_by_timeframe=price_by_timeframe,
        cme_oi=cme_frames["cme_oi"],
        cme_iv=cme_frames["cme_iv"],
        cme_futures=cme_frames["cme_futures"],
        basis=cme_frames["basis"],
        timeframes=selected_timeframes,
    )
    rule_templates = build_rule_templates()
    trades = run_entry_tp_pilot_backtest(
        market_map=market_map,
        price_by_timeframe=price_by_timeframe,
        pine_signals=cme_frames["pine_signals"],
        guru_context=cme_frames["guru_overlay"],
    )
    summary = summarize_entry_tp_trades(trades)
    timeframe_comparison = build_timeframe_comparison(summary, trades)
    decision = build_pilot_decision(
        date_audit=date_audit,
        market_map=market_map,
        trades=trades,
        summary=summary,
    )
    chart_paths = write_visual_replay_charts(
        charts_dir=charts_dir,
        market_map=market_map,
        price_by_timeframe=price_by_timeframe,
        trades=trades,
    )
    final_decision = _final_decision_label(decision)
    result = CmeOverlapEntryTpLabResult(
        date_audit=date_audit,
        market_map=market_map,
        rule_templates=rule_templates,
        trades=trades,
        summary=summary,
        timeframe_comparison=timeframe_comparison,
        decision=decision,
        chart_paths=chart_paths,
        final_decision=final_decision,
    )
    write_lab_outputs(output_root=output_root, result=result)
    append_research_report_sections(output_root / "research_report.md", result)
    return result


def load_cme_overlap_inputs(output_root: Path) -> dict[str, pl.DataFrame]:
    """Load optional CME/guru/Pine inputs with empty-frame fallbacks."""

    return {
        "cme_oi": _load_optional(output_root / "cme_canonical_option_oi_by_strike.parquet"),
        "cme_iv": _load_optional(output_root / "cme_canonical_option_iv_by_strike.parquet"),
        "cme_futures": _load_optional(output_root / "cme_canonical_futures_price.parquet"),
        "basis": _load_optional(output_root / "xau_basis_backfilled.parquet"),
        "guru_rule_library": _load_optional(output_root / "guru_rule_library.csv"),
        "guru_replay": _load_optional(output_root / "current_week_cme_guru_replay.csv"),
        "guru_overlay": _load_optional(output_root / "current_week_same_day_guru_overlay.csv"),
        "pine_signals": _load_optional(output_root / "python_pine_like_signals.csv"),
        "pine_overlay_trades": _load_optional(output_root / "python_cme_guru_overlay_trades.csv"),
    }


def load_price_timeframes(
    *,
    output_root: Path,
    start_date: date,
    end_date: date,
    timeframes: tuple[str, ...],
) -> dict[str, pl.DataFrame]:
    """Load exact Dukascopy frames where present, otherwise resample M1."""

    base_m1 = _load_best_price_source(
        "m1",
        output_root=output_root,
        start_date=start_date,
        end_date=end_date,
    )
    frames: dict[str, pl.DataFrame] = {}
    for timeframe in timeframes:
        exact = _load_best_price_source(
            timeframe,
            output_root=output_root,
            start_date=start_date,
            end_date=end_date,
        )
        if not exact.is_empty():
            frames[timeframe] = exact
        elif not base_m1.is_empty():
            frames[timeframe] = resample_price_bars(base_m1, timeframe)
        else:
            frames[timeframe] = _empty_price_frame()
    return frames


def build_overlap_date_audit(
    *,
    dates: list[date],
    price_by_timeframe: dict[str, pl.DataFrame],
    cme_oi: pl.DataFrame,
    cme_iv: pl.DataFrame,
    cme_futures: pl.DataFrame,
    basis: pl.DataFrame,
    guru_context: pl.DataFrame,
    pine_signals: pl.DataFrame,
    mode: str = "OVERLAP_ONLY",
) -> pl.DataFrame:
    """Build the selected-date CME/price overlap audit."""

    rows: list[dict[str, Any]] = []
    representative_price = _first_non_empty_frame(price_by_timeframe)
    for trade_day in dates:
        trade_date = trade_day.isoformat()
        price_rows = _date_rows(representative_price, trade_date)
        has_dukascopy_price = _has_dukascopy_price(price_rows)
        session_open, session_close = _session_bounds(trade_day, price_rows)
        has_oi = _has_date(cme_oi, trade_date)
        has_iv = _has_date(cme_iv, trade_date)
        has_futures = _has_date(cme_futures, trade_date)
        has_basis = _has_date(basis, trade_date)
        has_guru = _has_any_date(guru_context, trade_date)
        has_pine = _has_any_date(pine_signals, trade_date)
        cme_asof = select_cme_asof(
            cme_oi,
            trade_date=trade_date,
            session_open=session_open,
            session_close=session_close,
        )
        if cme_asof is None and has_iv:
            cme_asof = _earliest_datetime(_date_rows(cme_iv, trade_date), "asof_timestamp")
        before_session = cme_asof is not None and cme_asof <= session_open
        during_session = cme_asof is not None and cme_asof <= session_close
        post_event_only = cme_asof is not None and cme_asof > session_close
        missing = []
        if not has_dukascopy_price:
            missing.append("DUKASCOPY_BID_ASK_PRICE")
        if not has_oi:
            missing.append("CME_OI")
        if not has_iv:
            missing.append("NO_IV_RANGE")
        if not has_futures:
            missing.append("CME_FUTURES")
        if not has_basis:
            missing.append("NEEDS_BASIS")
        if cme_asof is None:
            missing.append("CME_ASOF_TIMESTAMP")
        usable = bool(has_dukascopy_price and has_oi and during_session and mode == "OVERLAP_ONLY")
        rows.append(
            {
                "trade_date": trade_date,
                "has_dukascopy_price": has_dukascopy_price,
                "has_cme_oi": has_oi,
                "has_cme_iv": has_iv,
                "has_cme_futures": has_futures,
                "has_basis": has_basis,
                "has_guru_context": has_guru,
                "has_pine_python_signals": has_pine,
                "cme_asof_timestamp": _timestamp_text(cme_asof),
                "can_use_cme_before_session": before_session,
                "can_use_cme_during_session": during_session,
                "can_use_cme_only_as_post_event_replay": post_event_only,
                "usable_for_entry_tp_pilot": usable,
                "missing_components": "|".join(missing),
                "reason_plain_english": _audit_reason(
                    has_price=has_dukascopy_price,
                    has_oi=has_oi,
                    has_iv=has_iv,
                    has_basis=has_basis,
                    cme_asof=cme_asof,
                    session_open=session_open,
                    session_close=session_close,
                    post_event_only=post_event_only,
                    usable=usable,
                ),
            }
        )
    return _rows_frame(rows, _date_audit_schema())


def select_cme_asof(
    cme_oi: pl.DataFrame,
    *,
    trade_date: str,
    session_open: datetime,
    session_close: datetime,
    min_dense_rows: int = 50,
) -> datetime | None:
    """Select the first usable CME OI as-of timestamp without looking ahead."""

    day = _date_rows(cme_oi, trade_date)
    if day.is_empty() or "asof_timestamp" not in day.columns:
        return None
    grouped = (
        day.group_by("asof_timestamp")
        .agg(
            pl.len().alias("row_count"),
            pl.sum("total_oi").alias("total_oi") if "total_oi" in day.columns else pl.lit(0.0).alias("total_oi"),
        )
        .sort("asof_timestamp")
    )
    rows = grouped.to_dicts()
    in_window = [row for row in rows if _as_utc(row["asof_timestamp"]) <= session_close]
    dense = [
        row
        for row in in_window
        if int(row.get("row_count") or 0) >= min_dense_rows
        and float(row.get("total_oi") or 0.0) > 0.0
    ]
    if dense:
        return _as_utc(dense[0]["asof_timestamp"])
    positive = [row for row in in_window if float(row.get("total_oi") or 0.0) > 0.0]
    if positive:
        return _as_utc(positive[0]["asof_timestamp"])
    if in_window:
        return _as_utc(in_window[0]["asof_timestamp"])
    return _as_utc(rows[0]["asof_timestamp"]) if rows else None


def build_pilot_market_map(
    *,
    date_audit: pl.DataFrame,
    price_by_timeframe: dict[str, pl.DataFrame],
    cme_oi: pl.DataFrame,
    cme_iv: pl.DataFrame,
    cme_futures: pl.DataFrame,
    basis: pl.DataFrame,
    timeframes: tuple[str, ...],
) -> pl.DataFrame:
    """Build basis-aware OI/IV market-map rows for usable overlap dates."""

    rows: list[dict[str, Any]] = []
    for audit in date_audit.to_dicts() if not date_audit.is_empty() else []:
        trade_date = str(audit["trade_date"])
        if not audit.get("has_dukascopy_price") or not audit.get("has_cme_oi"):
            continue
        cme_asof = _parse_datetime(audit.get("cme_asof_timestamp"))
        if cme_asof is None:
            continue
        for timeframe in timeframes:
            price = price_by_timeframe.get(timeframe, _empty_price_frame())
            bars = _date_rows(price, trade_date)
            if bars.is_empty():
                continue
            session = _session_ohlc(bars)
            reference_price = _reference_price_at_asof(bars, cme_asof)
            basis_reference = _basis_at_asof(basis, trade_date=trade_date, asof=cme_asof)
            wall_rows = _build_wall_rows(
                cme_oi,
                trade_date=trade_date,
                asof=cme_asof,
                basis_reference=basis_reference,
                reference_price=reference_price,
            )
            wall_above = _select_wall(wall_rows, reference_price=reference_price, side="above")
            wall_below = _select_wall(wall_rows, reference_price=reference_price, side="below")
            nearest_distance = _nearest_wall_distance(
                reference_price=reference_price,
                wall_above=wall_above,
                wall_below=wall_below,
            )
            iv_atm = _implied_vol_atm(
                cme_iv,
                trade_date=trade_date,
                asof=cme_asof,
                reference_strike=reference_price + (basis_reference or 0.0),
            )
            sd = _expected_move(reference_price, iv_atm)
            top_score = max(
                _float_or_zero(wall_above.get("wall_score") if wall_above else None),
                _float_or_zero(wall_below.get("wall_score") if wall_below else None),
            )
            quality = _wall_map_quality(
                usable=bool(audit.get("usable_for_entry_tp_pilot")),
                has_basis=basis_reference is not None,
                has_iv=iv_atm is not None,
                wall_rows=wall_rows,
            )
            rows.append(
                {
                    "trade_date": trade_date,
                    "timeframe": timeframe,
                    "session_open": session["open"],
                    "session_high": session["high"],
                    "session_low": session["low"],
                    "session_close": session["close"],
                    "basis_reference": basis_reference,
                    "top_oi_wall_above": _wall_value(wall_above, "strike"),
                    "top_oi_wall_below": _wall_value(wall_below, "strike"),
                    "top_oi_wall_score": top_score,
                    "spot_equivalent_wall_above": _wall_value(wall_above, "spot_level"),
                    "spot_equivalent_wall_below": _wall_value(wall_below, "spot_level"),
                    "nearest_wall_distance": nearest_distance,
                    "oi_change_near_wall": _wall_metric_sum(wall_above, wall_below, "oi_change"),
                    "option_volume_near_wall": _wall_metric_sum(wall_above, wall_below, "option_volume"),
                    "implied_vol_atm": iv_atm,
                    "one_sd_upper": reference_price + sd if sd is not None else None,
                    "one_sd_lower": reference_price - sd if sd is not None else None,
                    "two_sd_upper": reference_price + 2.0 * sd if sd is not None else None,
                    "two_sd_lower": reference_price - 2.0 * sd if sd is not None else None,
                    "iv_range_available": sd is not None,
                    "wall_map_quality": quality,
                    "cme_asof_timestamp": _timestamp_text(cme_asof),
                    "reference_price_at_asof": reference_price,
                    "level_basis": "SPOT_EQUIVALENT" if basis_reference is not None else "FUTURES_STRIKE",
                }
            )
    return _rows_frame(rows, _market_map_schema())


def build_rule_templates() -> pl.DataFrame:
    """Return the fixed entry/TP/SL templates under test."""

    rows = [
        {
            "rule_template": "WALL_REJECTION_FADE",
            "condition": "price touches or approaches an OI wall, then closes back away without acceptance beyond the wall",
            "direction": "short from resistance wall; long from support wall",
            "tp_options": "session open|midpoint of range|next wall|1SD middle",
            "sl_rule": "close and hold beyond wall, with ATR or spread-adjusted buffer",
            "research_only": True,
        },
        {
            "rule_template": "WALL_ACCEPTANCE_BREAKOUT",
            "condition": "price closes beyond an OI wall and the next candle holds beyond it",
            "direction": "continuation through wall",
            "tp_options": "next OI wall|1SD extension|2SD extension",
            "sl_rule": "close back inside wall",
            "research_only": True,
        },
        {
            "rule_template": "LOW_OI_GAP_SQUEEZE",
            "condition": "price breaks into a low-OI gap with little wall resistance until the next level",
            "direction": "continuation through the gap",
            "tp_options": "next strong wall",
            "sl_rule": "return back below or above breakout level",
            "research_only": True,
        },
        {
            "rule_template": "NO_TRADE_MIDDLE_RANGE",
            "condition": "price is inside middle range with no clear wall edge",
            "direction": "block trade candidates",
            "tp_options": "not applicable",
            "sl_rule": "not applicable",
            "research_only": True,
        },
        {
            "rule_template": "PINE_SIGNAL_WITH_CME_FILTER",
            "condition": "Pine/Python signal exists; CME map blocks trades into strong walls or allows wall-aligned acceptance/rejection",
            "direction": "signal direction after CME filter",
            "tp_options": "same wall-based TP rules",
            "sl_rule": "same wall-based SL rules",
            "research_only": True,
        },
    ]
    return _rows_frame(rows, _rule_template_schema())


def run_entry_tp_pilot_backtest(
    *,
    market_map: pl.DataFrame,
    price_by_timeframe: dict[str, pl.DataFrame],
    pine_signals: pl.DataFrame,
    guru_context: pl.DataFrame,
) -> pl.DataFrame:
    """Run deterministic pilot entries and spread-aware TP/SL replay."""

    trade_rows: list[dict[str, Any]] = []
    guru_dates = _date_set(guru_context)
    for market in market_map.to_dicts() if not market_map.is_empty() else []:
        trade_date = str(market["trade_date"])
        timeframe = str(market["timeframe"])
        bars_frame = _date_rows(price_by_timeframe.get(timeframe, _empty_price_frame()), trade_date)
        bars = bars_frame.sort("timestamp").to_dicts() if not bars_frame.is_empty() else []
        cme_asof = _parse_datetime(market.get("cme_asof_timestamp"))
        if not bars or cme_asof is None:
            continue
        wall_above = _market_level(market, "above")
        wall_below = _market_level(market, "below")
        common = {
            "trade_date": trade_date,
            "timeframe": timeframe,
            "iv_range_context": _iv_context(market),
            "guru_filter_state": "GURU_CONTEXT_AVAILABLE" if trade_date in guru_dates else "NO_GURU_CONTEXT",
            "data_quality_label": _data_quality_label(market, bars),
        }
        trade_rows.extend(
            _template_trade_rows(
                template="WALL_REJECTION_FADE",
                events=detect_wall_rejection_fade_entries(
                    bars,
                    wall_above=wall_above,
                    wall_below=wall_below,
                    asof=cme_asof,
                ),
                bars=bars,
                market=market,
                common=common,
            )
        )
        trade_rows.extend(
            _template_trade_rows(
                template="WALL_ACCEPTANCE_BREAKOUT",
                events=detect_wall_acceptance_breakout_entries(
                    bars,
                    wall_above=wall_above,
                    wall_below=wall_below,
                    asof=cme_asof,
                ),
                bars=bars,
                market=market,
                common=common,
            )
        )
        trade_rows.extend(
            _template_trade_rows(
                template="LOW_OI_GAP_SQUEEZE",
                events=detect_low_oi_gap_squeeze_entries(
                    bars,
                    wall_above=wall_above,
                    wall_below=wall_below,
                    asof=cme_asof,
                ),
                bars=bars,
                market=market,
                common=common,
            )
        )
        block_events = detect_no_trade_middle_range_blocks(
            bars,
            wall_above=wall_above,
            wall_below=wall_below,
            asof=cme_asof,
        )
        trade_rows.extend(
            _no_entry_rows(
                block_events,
                template="NO_TRADE_MIDDLE_RANGE",
                common=common,
                reason="NO_TRADE_MIDDLE_RANGE",
            )
        )
        pine_rows = run_pine_signal_with_cme_filter(
            bars=bars,
            market=market,
            pine_signals=pine_signals,
            cme_asof=cme_asof,
            common=common,
        )
        trade_rows.extend(pine_rows)
    return _rows_frame(trade_rows, _trade_schema())


def detect_wall_rejection_fade_entries(
    bars: list[dict[str, Any]],
    *,
    wall_above: float | None,
    wall_below: float | None,
    asof: datetime | None = None,
    max_entries: int = 5,
) -> list[dict[str, Any]]:
    """Detect wall rejection fade entries from candle action."""

    events: list[dict[str, Any]] = []
    tolerance = _touch_tolerance(bars)
    buffer = _execution_buffer(bars)
    for index in range(1, len(bars) - 1):
        if asof is not None and _as_utc(bars[index]["timestamp"]) < asof:
            continue
        close = _float_or_zero(bars[index].get("close"))
        high = _float_or_zero(bars[index].get("high"))
        low = _float_or_zero(bars[index].get("low"))
        if wall_above is not None and high >= wall_above - tolerance and close < wall_above - buffer:
            events.append(
                {
                    "direction": "short",
                    "signal_index": index,
                    "entry_index": index + 1,
                    "wall_used": wall_above,
                    "entry_pattern": "RESISTANCE_REJECTION",
                }
            )
        if wall_below is not None and low <= wall_below + tolerance and close > wall_below + buffer:
            events.append(
                {
                    "direction": "long",
                    "signal_index": index,
                    "entry_index": index + 1,
                    "wall_used": wall_below,
                    "entry_pattern": "SUPPORT_REJECTION",
                }
            )
        if len(events) >= max_entries:
            break
    return events


def detect_wall_acceptance_breakout_entries(
    bars: list[dict[str, Any]],
    *,
    wall_above: float | None,
    wall_below: float | None,
    asof: datetime | None = None,
    max_entries: int = 5,
) -> list[dict[str, Any]]:
    """Detect wall acceptance breakout entries."""

    events: list[dict[str, Any]] = []
    buffer = _execution_buffer(bars)
    for index in range(1, len(bars) - 2):
        if asof is not None and _as_utc(bars[index]["timestamp"]) < asof:
            continue
        close = _float_or_zero(bars[index].get("close"))
        hold_close = _float_or_zero(bars[index + 1].get("close"))
        if wall_above is not None and close > wall_above + buffer and hold_close > wall_above:
            events.append(
                {
                    "direction": "long",
                    "signal_index": index + 1,
                    "entry_index": index + 2,
                    "wall_used": wall_above,
                    "entry_pattern": "ACCEPTED_RESISTANCE_BREAK",
                }
            )
        if wall_below is not None and close < wall_below - buffer and hold_close < wall_below:
            events.append(
                {
                    "direction": "short",
                    "signal_index": index + 1,
                    "entry_index": index + 2,
                    "wall_used": wall_below,
                    "entry_pattern": "ACCEPTED_SUPPORT_BREAK",
                }
            )
        if len(events) >= max_entries:
            break
    return events


def detect_low_oi_gap_squeeze_entries(
    bars: list[dict[str, Any]],
    *,
    wall_above: float | None,
    wall_below: float | None,
    asof: datetime | None = None,
    max_entries: int = 5,
    min_gap_points: float = 12.0,
) -> list[dict[str, Any]]:
    """Detect continuation candidates through the gap between two OI walls."""

    if wall_above is None or wall_below is None or wall_above <= wall_below:
        return []
    if wall_above - wall_below < min_gap_points:
        return []
    events: list[dict[str, Any]] = []
    buffer = _execution_buffer(bars)
    for index in range(1, len(bars) - 1):
        if asof is not None and _as_utc(bars[index]["timestamp"]) < asof:
            continue
        previous_close = _float_or_zero(bars[index - 1].get("close"))
        close = _float_or_zero(bars[index].get("close"))
        if previous_close <= wall_below and close > wall_below + buffer:
            events.append(
                {
                    "direction": "long",
                    "signal_index": index,
                    "entry_index": index + 1,
                    "wall_used": wall_below,
                    "entry_pattern": "LOW_OI_GAP_BREAK_UP",
                }
            )
        if previous_close >= wall_above and close < wall_above - buffer:
            events.append(
                {
                    "direction": "short",
                    "signal_index": index,
                    "entry_index": index + 1,
                    "wall_used": wall_above,
                    "entry_pattern": "LOW_OI_GAP_BREAK_DOWN",
                }
            )
        if len(events) >= max_entries:
            break
    return events


def detect_no_trade_middle_range_blocks(
    bars: list[dict[str, Any]],
    *,
    wall_above: float | None,
    wall_below: float | None,
    asof: datetime | None = None,
    max_blocks: int = 5,
) -> list[dict[str, Any]]:
    """Detect no-trade middle-range blocks."""

    if wall_above is None or wall_below is None or wall_above <= wall_below:
        return []
    middle_low = wall_below + (wall_above - wall_below) * 0.30
    middle_high = wall_below + (wall_above - wall_below) * 0.70
    blocks: list[dict[str, Any]] = []
    for index, row in enumerate(bars):
        if asof is not None and _as_utc(row["timestamp"]) < asof:
            continue
        close = _float_or_zero(row.get("close"))
        if middle_low <= close <= middle_high:
            blocks.append(
                {
                    "signal_index": index,
                    "entry_index": index,
                    "direction": "none",
                    "wall_used": None,
                    "entry_pattern": "BLOCK_MIDDLE_RANGE",
                    "timestamp": _timestamp_text(row.get("timestamp")),
                }
            )
        if len(blocks) >= max_blocks:
            break
    return blocks


def run_pine_signal_with_cme_filter(
    *,
    bars: list[dict[str, Any]],
    market: dict[str, Any],
    pine_signals: pl.DataFrame,
    cme_asof: datetime,
    common: dict[str, Any],
    max_events: int = 5,
) -> list[dict[str, Any]]:
    """Replay Python/Pine signals through conservative CME wall filters."""

    trade_date = str(market["trade_date"])
    timeframe = str(market["timeframe"])
    signals = _pine_signal_rows(pine_signals, trade_date=trade_date, timeframe=timeframe)
    rows: list[dict[str, Any]] = []
    wall_above = _market_level(market, "above")
    wall_below = _market_level(market, "below")
    for signal in signals:
        signal_time = _parse_datetime(signal.get("timestamp"))
        if signal_time is None or signal_time < cme_asof:
            continue
        direction = _signal_direction(signal)
        if direction not in {"long", "short"}:
            continue
        entry_index = _first_bar_index_after(bars, signal_time)
        if entry_index is None:
            continue
        block_state = _pine_cme_block_state(
            direction=direction,
            entry_price=_float_or_zero(bars[entry_index].get("close")),
            wall_above=wall_above,
            wall_below=wall_below,
            signal=signal,
        )
        if block_state.startswith("BLOCK"):
            rows.append(
                _trade_row(
                    **common,
                    rule_template="PINE_SIGNAL_WITH_CME_FILTER",
                    entry_timestamp=_timestamp_text(bars[entry_index].get("timestamp")),
                    direction=direction,
                    entry_price=None,
                    tp_level=None,
                    sl_level=None,
                    exit_timestamp="",
                    exit_reason="NO_ENTRY",
                    pnl_points=None,
                    pnl_after_spread_cost=None,
                    mfe=None,
                    mae=None,
                    bars_held=0,
                    wall_used=_blocking_wall(direction, wall_above, wall_below),
                    wall_distance_at_entry=_wall_distance(
                        _float_or_zero(bars[entry_index].get("close")),
                        _blocking_wall(direction, wall_above, wall_below),
                    ),
                    pine_signal_state=block_state,
                )
            )
        else:
            event = {
                "direction": direction,
                "entry_index": entry_index,
                "signal_index": max(0, entry_index - 1),
                "wall_used": _blocking_wall(direction, wall_above, wall_below),
                "entry_pattern": block_state,
            }
            rows.extend(
                _template_trade_rows(
                    template="PINE_SIGNAL_WITH_CME_FILTER",
                    events=[event],
                    bars=bars,
                    market=market,
                    common={**common, "pine_signal_state": block_state},
                )
            )
        if len(rows) >= max_events:
            break
    if not rows:
        rows.append(
            _trade_row(
                **common,
                rule_template="PINE_SIGNAL_WITH_CME_FILTER",
                entry_timestamp="",
                direction="none",
                entry_price=None,
                tp_level=None,
                sl_level=None,
                exit_timestamp="",
                exit_reason="NO_ENTRY",
                pnl_points=None,
                pnl_after_spread_cost=None,
                mfe=None,
                mae=None,
                bars_held=0,
                wall_used=None,
                wall_distance_at_entry=None,
                pine_signal_state="NO_PINE_SIGNAL",
            )
        )
    return rows


def simulate_trade_exit(
    bars: list[dict[str, Any]],
    *,
    entry_index: int,
    direction: str,
    entry_price: float,
    tp_level: float,
    sl_level: float,
    timeout_bars: int = 16,
) -> dict[str, Any]:
    """Replay one trade with bid/ask-aware hit detection."""

    last_index = min(len(bars) - 1, entry_index + timeout_bars)
    mfe = 0.0
    mae = 0.0
    for index in range(entry_index, last_index + 1):
        row = bars[index]
        if direction == "long":
            high = _float_or_zero(row.get("bid_high"))
            low = _float_or_zero(row.get("bid_low"))
            mfe = max(mfe, high - entry_price)
            mae = min(mae, low - entry_price)
            tp_hit = high >= tp_level
            sl_hit = low <= sl_level
            if sl_hit or tp_hit:
                exit_reason = "SL_HIT" if sl_hit else "TP_HIT"
                exit_price = sl_level if sl_hit else tp_level
                return _exit_result(row, index, entry_index, direction, entry_price, exit_price, exit_reason, mfe, mae)
        else:
            high = _float_or_zero(row.get("ask_high"))
            low = _float_or_zero(row.get("ask_low"))
            mfe = max(mfe, entry_price - low)
            mae = min(mae, entry_price - high)
            tp_hit = low <= tp_level
            sl_hit = high >= sl_level
            if sl_hit or tp_hit:
                exit_reason = "SL_HIT" if sl_hit else "TP_HIT"
                exit_price = sl_level if sl_hit else tp_level
                return _exit_result(row, index, entry_index, direction, entry_price, exit_price, exit_reason, mfe, mae)
    last = bars[last_index]
    reason = "TIMEOUT" if last_index < len(bars) - 1 else "SESSION_CLOSE"
    exit_price = _float_or_zero(last.get("bid_close" if direction == "long" else "ask_close"))
    return _exit_result(last, last_index, entry_index, direction, entry_price, exit_price, reason, mfe, mae)


def resample_price_bars(price: pl.DataFrame, timeframe: str) -> pl.DataFrame:
    """Resample normalized price bars to a higher timeframe."""

    if price.is_empty():
        return _empty_price_frame()
    if timeframe not in TIMEFRAME_MINUTES:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    duration = _polars_duration(timeframe)
    frame = price.sort("timestamp").with_columns(
        pl.col("timestamp").dt.truncate(duration).alias("bar_timestamp")
    )
    grouped = (
        frame.group_by("bar_timestamp")
        .agg(
            pl.first("open").alias("open"),
            pl.max("high").alias("high"),
            pl.min("low").alias("low"),
            pl.last("close").alias("close"),
            pl.mean("spread_points").alias("spread_points"),
            pl.first("bid_open").alias("bid_open"),
            pl.max("bid_high").alias("bid_high"),
            pl.min("bid_low").alias("bid_low"),
            pl.last("bid_close").alias("bid_close"),
            pl.first("ask_open").alias("ask_open"),
            pl.max("ask_high").alias("ask_high"),
            pl.min("ask_low").alias("ask_low"),
            pl.last("ask_close").alias("ask_close"),
            pl.max("spread_available").alias("spread_available"),
            pl.first("price_source_label").alias("price_source_label"),
        )
        .rename({"bar_timestamp": "timestamp"})
        .with_columns(
            pl.col("timestamp").dt.date().cast(pl.String).alias("trade_date"),
            pl.lit(timeframe).alias("timeframe"),
        )
        .select(list(_price_schema()))
        .sort("timestamp")
    )
    return grouped


def basis_adjusted_wall_level(strike: float, basis: float) -> float:
    """Map a futures/options strike to a spot-equivalent level."""

    return strike - basis


def summarize_entry_tp_trades(trades: pl.DataFrame) -> pl.DataFrame:
    """Summarize pilot metrics by rule and timeframe."""

    rows: list[dict[str, Any]] = []
    if trades.is_empty():
        return _rows_frame(rows, _summary_schema())
    groups = _group_rows(trades, ("trade_date", "timeframe", "rule_template"))
    for (trade_date, timeframe, template), group_rows in groups.items():
        executed = [row for row in group_rows if row.get("exit_reason") != "NO_ENTRY"]
        pnl = [_float_or_zero(row.get("pnl_after_spread_cost")) for row in executed]
        wins = [value for value in pnl if value > 0]
        losses = [value for value in pnl if value < 0]
        rows.append(
            {
                "trade_date": trade_date,
                "timeframe": timeframe,
                "rule_template": template,
                "event_count": len(group_rows),
                "trade_count": len(executed),
                "win_rate": len(wins) / len(executed) if executed else None,
                "avg_win": _mean(wins),
                "avg_loss": _mean(losses),
                "expectancy": _mean(pnl) if pnl else None,
                "profit_factor": _profit_factor(pnl),
                "max_drawdown": _max_drawdown(pnl),
                "total_pnl_after_spread_cost": sum(pnl),
                "average_mfe": _mean([_float_or_zero(row.get("mfe")) for row in executed]),
                "average_mae": _mean([_float_or_zero(row.get("mae")) for row in executed]),
                "tp_hit_rate": _exit_rate(executed, "TP_HIT"),
                "sl_hit_rate": _exit_rate(executed, "SL_HIT"),
                "no_entry_count": len(group_rows) - len(executed),
                "sample_size_warning": len(executed) < MIN_VALIDATION_DATES,
            }
        )
    return _rows_frame(rows, _summary_schema()).sort(["trade_date", "timeframe", "rule_template"])


def build_timeframe_comparison(summary: pl.DataFrame, trades: pl.DataFrame) -> pl.DataFrame:
    """Compare pilot-only metrics across selected timeframes."""

    rows: list[dict[str, Any]] = []
    if summary.is_empty():
        return _rows_frame(rows, _timeframe_schema())
    for timeframe, groups in _group_rows(summary, ("timeframe",)).items():
        executed = [
            row
            for row in trades.to_dicts()
            if str(row.get("timeframe")) == timeframe[0] and row.get("exit_reason") != "NO_ENTRY"
        ]
        pnl = [_float_or_zero(row.get("pnl_after_spread_cost")) for row in executed]
        best, worst = _best_worst_templates_from_trades(executed)
        rows.append(
            {
                "timeframe": timeframe[0],
                "trade_count": len(executed),
                "total_pnl": sum(pnl),
                "expectancy": _mean(pnl) if pnl else None,
                "profit_factor": _profit_factor(pnl),
                "tp_hit_rate": _exit_rate(executed, "TP_HIT"),
                "sl_hit_rate": _exit_rate(executed, "SL_HIT"),
                "false_signal_rate": _false_signal_rate(groups),
                "average_hold_time": _mean([_float_or_zero(row.get("bars_held")) for row in executed]),
                "best_template": best,
                "worst_template": worst,
                "sample_warning": "PILOT_ONLY_ONE_OR_FEW_DATES",
            }
        )
    order = {name: index for index, name in enumerate(TIMEFRAME_MINUTES)}
    return (
        _rows_frame(rows, _timeframe_schema())
        .with_columns(pl.col("timeframe").replace_strict(order, default=999).alias("_sort_order"))
        .sort("_sort_order")
        .drop("_sort_order")
    )


def build_pilot_decision(
    *,
    date_audit: pl.DataFrame,
    market_map: pl.DataFrame,
    trades: pl.DataFrame,
    summary: pl.DataFrame,
) -> pl.DataFrame:
    """Build explicit pilot decision labels without money-readiness output."""

    usable_dates = _usable_dates(date_audit)
    few_dates = len(usable_dates) < MIN_VALIDATION_DATES
    trade_count = trades.filter(pl.col("exit_reason") != "NO_ENTRY").height if not trades.is_empty() else 0
    has_market_map = not market_map.is_empty()
    decision_scope = _decision_scope_rows(date_audit)
    needs_basis = _any_false(decision_scope, "has_basis")
    needs_iv = _any_false(decision_scope, "has_cme_iv")
    post_event = _any_true(decision_scope, "can_use_cme_only_as_post_event_replay")
    rows = []
    reasons = {
        "CME_OVERLAP_PILOT_READY": "At least one selected date has Dukascopy bid/ask price and CME OI available during the session.",
        "CME_WALL_ENTRY_TP_CANDIDATE": "At least one entry/TP/SL template could be replayed with spread-aware execution.",
        "CME_WALL_CONTEXT_ONLY": "CME walls were available but executable replay was limited or absent.",
        "NEEDS_BASIS": "Some selected dates lack basis, so futures strikes cannot always be converted to spot-equivalent wall levels.",
        "NEEDS_IV": "Some selected dates lack IV, so 1SD/2SD ranges are unavailable for those dates.",
        "POST_EVENT_REPLAY_ONLY": "Some CME as-of timestamps are after the tested decision window.",
        "NOT_ENOUGH_FOR_VALIDATION": "The selected overlap sample has fewer than 30 usable dates.",
        "NOT_READY_FOR_MONEY": "This artifact is research-only and not a live, paper, broker, or money-deployment gate.",
    }
    applies = {
        "CME_OVERLAP_PILOT_READY": bool(usable_dates),
        "CME_WALL_ENTRY_TP_CANDIDATE": trade_count > 0,
        "CME_WALL_CONTEXT_ONLY": has_market_map and trade_count == 0,
        "NEEDS_BASIS": needs_basis,
        "NEEDS_IV": needs_iv,
        "POST_EVENT_REPLAY_ONLY": post_event,
        "NOT_ENOUGH_FOR_VALIDATION": few_dates,
        "NOT_READY_FOR_MONEY": True,
    }
    for label in DECISION_LABELS:
        rows.append(
            {
                "decision_label": label,
                "applies": applies[label],
                "reason": reasons[label],
                "usable_overlap_dates": len(usable_dates),
                "trade_count": trade_count,
                "pilot_only": True,
            }
        )
    return _rows_frame(rows, _decision_schema())


def write_lab_outputs(*, output_root: Path, result: CmeOverlapEntryTpLabResult) -> None:
    """Write all requested lab outputs."""

    result.date_audit.write_csv(output_root / "cme_overlap_date_audit.csv")
    (output_root / "cme_overlap_date_audit.md").write_text(
        date_audit_markdown(result.date_audit),
        encoding="utf-8",
    )
    result.market_map.write_csv(output_root / "cme_overlap_market_map.csv")
    (output_root / "cme_overlap_market_map.md").write_text(
        market_map_markdown(result.market_map),
        encoding="utf-8",
    )
    result.rule_templates.write_csv(output_root / "cme_overlap_rule_templates.csv")
    (output_root / "cme_overlap_rule_templates.md").write_text(
        rule_templates_markdown(result.rule_templates),
        encoding="utf-8",
    )
    result.trades.write_csv(output_root / "cme_overlap_entry_tp_trades.csv")
    result.summary.write_csv(output_root / "cme_overlap_entry_tp_summary.csv")
    (output_root / "cme_overlap_entry_tp_report.md").write_text(
        entry_tp_report_markdown(result),
        encoding="utf-8",
    )
    result.timeframe_comparison.write_csv(output_root / "cme_overlap_timeframe_comparison.csv")
    (output_root / "cme_overlap_timeframe_comparison.md").write_text(
        timeframe_comparison_markdown(result.timeframe_comparison),
        encoding="utf-8",
    )
    result.decision.write_csv(output_root / "cme_overlap_pilot_decision.csv")
    (output_root / "cme_overlap_pilot_decision.md").write_text(
        decision_markdown(result.decision),
        encoding="utf-8",
    )


def write_visual_replay_charts(
    *,
    charts_dir: Path,
    market_map: pl.DataFrame,
    price_by_timeframe: dict[str, pl.DataFrame],
    trades: pl.DataFrame,
) -> tuple[Path, ...]:
    """Write compact HTML/SVG replay charts for available 2026-05-15 timeframes."""

    paths: list[Path] = []
    if market_map.is_empty():
        return tuple(paths)
    target = "2026-05-15"
    for row in market_map.filter(pl.col("trade_date") == target).to_dicts():
        timeframe = str(row["timeframe"])
        bars = _date_rows(price_by_timeframe.get(timeframe, _empty_price_frame()), target)
        if bars.is_empty():
            continue
        frame_trades = (
            trades.filter((pl.col("trade_date") == target) & (pl.col("timeframe") == timeframe))
            if not trades.is_empty()
            else trades
        )
        path = charts_dir / f"cme_overlap_2026_05_15_{timeframe}.html"
        path.write_text(
            _visual_replay_html(
                title=f"CME Overlap Replay {target} {timeframe}",
                bars=bars.sort("timestamp").to_dicts(),
                market=row,
                trades=frame_trades.to_dicts() if not frame_trades.is_empty() else [],
            ),
            encoding="utf-8",
        )
        paths.append(path)
    return tuple(paths)


def append_research_report_sections(path: Path, result: CmeOverlapEntryTpLabResult) -> None:
    """Append or replace the CME overlap lab sections in research_report.md."""

    block = "\n".join(
        [
            "<!-- CME_OVERLAP_ENTRY_TP_LAB_START -->",
            "## CME Overlap Date Audit",
            "",
            *_report_preview_lines(result.date_audit, "outputs/cme_overlap_date_audit.csv"),
            "",
            "## CME Market Map",
            "",
            *_report_preview_lines(result.market_map, "outputs/cme_overlap_market_map.csv"),
            "",
            "## Entry/TP/SL Rule Templates",
            "",
            *_report_preview_lines(result.rule_templates, "outputs/cme_overlap_rule_templates.csv"),
            "",
            "## CME Overlap Entry/TP Pilot Backtest",
            "",
            *_entry_tp_report_lines(result),
            "",
            "## Timeframe Comparison",
            "",
            *_report_preview_lines(
                result.timeframe_comparison,
                "outputs/cme_overlap_timeframe_comparison.csv",
            ),
            "",
            "## 2026-05-15 Visual Replay",
            "",
            *_visual_replay_lines(result.chart_paths),
            "",
            "## Pilot Decision",
            "",
            *_report_preview_lines(result.decision, "outputs/cme_overlap_pilot_decision.csv"),
            "<!-- CME_OVERLAP_ENTRY_TP_LAB_END -->",
            "",
        ]
    )
    block = _safe_report_text(block)
    existing = path.read_text(encoding="utf-8") if path.exists() else "# XAU/USD Vol-OI Research Report\n"
    pattern = re.compile(
        r"<!-- CME_OVERLAP_ENTRY_TP_LAB_START -->.*?<!-- CME_OVERLAP_ENTRY_TP_LAB_END -->\n?",
        re.DOTALL,
    )
    if pattern.search(existing):
        updated = pattern.sub(block, existing)
    else:
        updated = existing.rstrip() + "\n\n" + block
    path.write_text(_redact_text(updated), encoding="utf-8")


def date_audit_markdown(frame: pl.DataFrame) -> str:
    return _safe_report_text(
        "\n".join(
            [
                "# CME Overlap Date Audit",
                "",
                "Research-only audit of dates where Dukascopy XAU/USD bid/ask data overlaps CME OI/IV context.",
                "",
                _frame_markdown(frame),
            ]
        )
    )


def market_map_markdown(frame: pl.DataFrame) -> str:
    return _safe_report_text(
        "\n".join(
            [
                "# CME Overlap Market Map",
                "",
                "CME strikes are kept separate from spot-equivalent levels. Spot-equivalent levels use strike minus basis when basis exists.",
                "",
                _frame_markdown(frame),
            ]
        )
    )


def rule_templates_markdown(frame: pl.DataFrame) -> str:
    return _safe_report_text(
        "\n".join(
            [
                "# CME Overlap Entry/TP/SL Rule Templates",
                "",
                "Templates are fixed before replay. They are research definitions, not trade instructions.",
                "",
                _frame_markdown(frame),
            ]
        )
    )


def entry_tp_report_markdown(result: CmeOverlapEntryTpLabResult) -> str:
    return _safe_report_text(
        "\n".join(
            [
                "# CME Overlap Entry/TP Pilot Backtest",
                "",
                "Research-only spread-aware replay. One or a few overlap dates are not validation evidence.",
                "",
                "## Summary",
                "",
                _frame_markdown(result.summary),
                "",
                "## Trades",
                "",
                _frame_markdown(result.trades),
            ]
        )
    )


def timeframe_comparison_markdown(frame: pl.DataFrame) -> str:
    return _safe_report_text(
        "\n".join(
            [
                "# CME Overlap Timeframe Comparison",
                "",
                "All rows are labelled PILOT_ONLY through the sample warning. No timeframe is validated from this sample.",
                "",
                _frame_markdown(frame),
            ]
        )
    )


def decision_markdown(frame: pl.DataFrame) -> str:
    return _safe_report_text(
        "\n".join(
            [
                "# CME Overlap Pilot Decision",
                "",
                "The decision labels are research gates only and do not permit live, paper, broker, or money workflows.",
                "",
                _frame_markdown(frame),
            ]
        )
    )


def _load_best_price_source(
    timeframe: str,
    *,
    output_root: Path,
    start_date: date,
    end_date: date,
) -> pl.DataFrame:
    candidates = _price_candidates(timeframe, output_root)
    for path in candidates:
        if not path.exists():
            continue
        frame = _load_optional(path)
        normalized = normalize_price_frame(frame, timeframe=timeframe, source_label=_source_label_for_path(path))
        filtered = _filter_price_range(normalized, start_date=start_date, end_date=end_date)
        if not filtered.is_empty():
            return filtered
    return _empty_price_frame()


def normalize_price_frame(
    frame: pl.DataFrame,
    *,
    timeframe: str,
    source_label: str = "UNKNOWN_PRICE_SOURCE",
) -> pl.DataFrame:
    """Normalize a price frame to bid/ask-aware OHLC columns."""

    if frame.is_empty():
        return _empty_price_frame()
    columns = {_normal_column(column): column for column in frame.columns}
    timestamp_col = _first_column(columns, ("timestamp", "datetime", "time", "date_time", "opentime"))
    if timestamp_col is None:
        return _empty_price_frame()
    working = _normalize_timestamp_column(frame, timestamp_col)
    open_col = _first_column(columns, ("open", "midopen"))
    high_col = _first_column(columns, ("high", "midhigh"))
    low_col = _first_column(columns, ("low", "midlow"))
    close_col = _first_column(columns, ("close", "midclose"))
    if not all((open_col, high_col, low_col, close_col)):
        return _empty_price_frame()
    spread_col = _first_column(columns, ("spreadpoints", "spread", "spread_close"))
    bid_open = _first_column(columns, ("bidopen", "bid_open"))
    bid_high = _first_column(columns, ("bidhigh", "bid_high"))
    bid_low = _first_column(columns, ("bidlow", "bid_low"))
    bid_close = _first_column(columns, ("bidclose", "bid_close"))
    ask_open = _first_column(columns, ("askopen", "ask_open"))
    ask_high = _first_column(columns, ("askhigh", "ask_high"))
    ask_low = _first_column(columns, ("asklow", "ask_low"))
    ask_close = _first_column(columns, ("askclose", "ask_close"))
    has_bid_ask = all((bid_open, bid_high, bid_low, bid_close, ask_open, ask_high, ask_low, ask_close))

    base_exprs = [
        pl.col("timestamp"),
        pl.col(open_col).cast(pl.Float64, strict=False).alias("open"),
        pl.col(high_col).cast(pl.Float64, strict=False).alias("high"),
        pl.col(low_col).cast(pl.Float64, strict=False).alias("low"),
        pl.col(close_col).cast(pl.Float64, strict=False).alias("close"),
    ]
    if has_bid_ask:
        selected = working.select(
            [
                *base_exprs,
                pl.col(bid_open).cast(pl.Float64, strict=False).alias("bid_open"),
                pl.col(bid_high).cast(pl.Float64, strict=False).alias("bid_high"),
                pl.col(bid_low).cast(pl.Float64, strict=False).alias("bid_low"),
                pl.col(bid_close).cast(pl.Float64, strict=False).alias("bid_close"),
                pl.col(ask_open).cast(pl.Float64, strict=False).alias("ask_open"),
                pl.col(ask_high).cast(pl.Float64, strict=False).alias("ask_high"),
                pl.col(ask_low).cast(pl.Float64, strict=False).alias("ask_low"),
                pl.col(ask_close).cast(pl.Float64, strict=False).alias("ask_close"),
            ]
        ).with_columns(
            pl.lit(True).alias("spread_available"),
        )
    else:
        selected = working.select(
            [
                *base_exprs,
                (
                    pl.col(spread_col).cast(pl.Float64, strict=False)
                    if spread_col is not None
                    else pl.lit(0.0)
                ).alias("_source_spread"),
            ]
        )
        half = pl.col("_source_spread").fill_null(0.0) / 2.0
        selected = selected.with_columns(
            pl.lit(spread_col is not None).alias("spread_available"),
            (pl.col("open") - half).alias("bid_open"),
            (pl.col("high") - half).alias("bid_high"),
            (pl.col("low") - half).alias("bid_low"),
            (pl.col("close") - half).alias("bid_close"),
            (pl.col("open") + half).alias("ask_open"),
            (pl.col("high") + half).alias("ask_high"),
            (pl.col("low") + half).alias("ask_low"),
            (pl.col("close") + half).alias("ask_close"),
        )
    selected = selected.with_columns(
        (pl.col("ask_close") - pl.col("bid_close")).abs().alias("spread_points"),
        pl.col("timestamp").dt.date().cast(pl.String).alias("trade_date"),
        pl.lit(timeframe).alias("timeframe"),
        pl.lit(source_label).alias("price_source_label"),
    )
    return selected.select(list(_price_schema())).sort("timestamp")


def _template_trade_rows(
    *,
    template: str,
    events: list[dict[str, Any]],
    bars: list[dict[str, Any]],
    market: dict[str, Any],
    common: dict[str, Any],
) -> list[dict[str, Any]]:
    if not events:
        return _no_entry_rows([], template=template, common=common, reason="NO_ENTRY")
    rows = []
    base_common = {key: value for key, value in common.items() if key != "pine_signal_state"}
    pine_state = str(common.get("pine_signal_state") or "NOT_PINE_TEMPLATE")
    for event in events:
        entry_index = int(event["entry_index"])
        if entry_index >= len(bars):
            continue
        direction = str(event["direction"])
        entry_bar = bars[entry_index]
        entry_price = _float_or_zero(entry_bar.get("ask_open" if direction == "long" else "bid_open"))
        tp, sl = _tp_sl_levels(
            template=template,
            direction=direction,
            event=event,
            market=market,
            entry_price=entry_price,
            bars=bars,
        )
        exit_result = simulate_trade_exit(
            bars,
            entry_index=entry_index,
            direction=direction,
            entry_price=entry_price,
            tp_level=tp,
            sl_level=sl,
            timeout_bars=_timeout_bars(str(market["timeframe"])),
        )
        rows.append(
            _trade_row(
                **base_common,
                rule_template=template,
                entry_timestamp=_timestamp_text(entry_bar.get("timestamp")),
                direction=direction,
                entry_price=entry_price,
                tp_level=tp,
                sl_level=sl,
                exit_timestamp=exit_result["exit_timestamp"],
                exit_reason=exit_result["exit_reason"],
                pnl_points=exit_result["pnl_points"],
                pnl_after_spread_cost=exit_result["pnl_after_spread_cost"],
                mfe=exit_result["mfe"],
                mae=exit_result["mae"],
                bars_held=exit_result["bars_held"],
                wall_used=event.get("wall_used"),
                wall_distance_at_entry=_wall_distance(entry_price, event.get("wall_used")),
                pine_signal_state=pine_state,
            )
        )
    return rows or _no_entry_rows([], template=template, common=common, reason="NO_ENTRY")


def _tp_sl_levels(
    *,
    template: str,
    direction: str,
    event: dict[str, Any],
    market: dict[str, Any],
    entry_price: float,
    bars: list[dict[str, Any]],
) -> tuple[float, float]:
    buffer = max(_execution_buffer(bars), 1.0)
    wall = _float_or_none(event.get("wall_used"))
    above = _market_level(market, "above")
    below = _market_level(market, "below")
    one_sd_upper = _float_or_none(market.get("one_sd_upper"))
    one_sd_lower = _float_or_none(market.get("one_sd_lower"))
    if direction == "long":
        tp_candidates = [above, one_sd_upper, _float_or_none(market.get("session_open"))]
        tp = _first_profitable_level(tp_candidates, entry_price=entry_price, direction=direction) or (entry_price + buffer * 3.0)
        if template == "LOW_OI_GAP_SQUEEZE" and above is not None and above > entry_price:
            tp = above
        sl = (wall - buffer) if wall is not None else (below if below is not None else entry_price - buffer * 2.0)
        if sl >= entry_price:
            sl = entry_price - buffer * 2.0
    else:
        tp_candidates = [below, one_sd_lower, _float_or_none(market.get("session_open"))]
        tp = _first_profitable_level(tp_candidates, entry_price=entry_price, direction=direction) or (entry_price - buffer * 3.0)
        if template == "LOW_OI_GAP_SQUEEZE" and below is not None and below < entry_price:
            tp = below
        sl = (wall + buffer) if wall is not None else (above if above is not None else entry_price + buffer * 2.0)
        if sl <= entry_price:
            sl = entry_price + buffer * 2.0
    return float(tp), float(sl)


def _no_entry_rows(
    events: list[dict[str, Any]],
    *,
    template: str,
    common: dict[str, Any],
    reason: str,
) -> list[dict[str, Any]]:
    source = events or [{"timestamp": "", "direction": "none", "wall_used": None}]
    rows = []
    for event in source:
        rows.append(
            _trade_row(
                **common,
                rule_template=template,
                entry_timestamp=str(event.get("timestamp") or ""),
                direction=str(event.get("direction") or "none"),
                entry_price=None,
                tp_level=None,
                sl_level=None,
                exit_timestamp="",
                exit_reason="NO_ENTRY",
                pnl_points=None,
                pnl_after_spread_cost=None,
                mfe=None,
                mae=None,
                bars_held=0,
                wall_used=event.get("wall_used"),
                wall_distance_at_entry=None,
                pine_signal_state=reason,
            )
        )
    return rows


def _exit_result(
    row: dict[str, Any],
    index: int,
    entry_index: int,
    direction: str,
    entry_price: float,
    exit_price: float,
    reason: str,
    mfe: float,
    mae: float,
) -> dict[str, Any]:
    pnl = exit_price - entry_price if direction == "long" else entry_price - exit_price
    return {
        "exit_timestamp": _timestamp_text(row.get("timestamp")),
        "exit_reason": reason,
        "pnl_points": pnl,
        "pnl_after_spread_cost": pnl,
        "mfe": mfe,
        "mae": mae,
        "bars_held": index - entry_index + 1,
    }


def _trade_row(**kwargs: Any) -> dict[str, Any]:
    row = {
        "trade_date": "",
        "timeframe": "",
        "rule_template": "",
        "entry_timestamp": "",
        "direction": "",
        "entry_price": None,
        "tp_level": None,
        "sl_level": None,
        "exit_timestamp": "",
        "exit_reason": "",
        "pnl_points": None,
        "pnl_after_spread_cost": None,
        "mfe": None,
        "mae": None,
        "bars_held": 0,
        "wall_used": None,
        "wall_distance_at_entry": None,
        "iv_range_context": "",
        "guru_filter_state": "",
        "pine_signal_state": "",
        "data_quality_label": "",
    }
    row.update(kwargs)
    return row


def _build_wall_rows(
    cme_oi: pl.DataFrame,
    *,
    trade_date: str,
    asof: datetime,
    basis_reference: float | None,
    reference_price: float,
) -> list[dict[str, Any]]:
    day = _date_rows(cme_oi, trade_date)
    if day.is_empty() or "asof_timestamp" not in day.columns:
        return []
    exact = day.filter(pl.col("asof_timestamp") == asof)
    if exact.is_empty():
        available = day.filter(pl.col("asof_timestamp") <= asof).sort("asof_timestamp")
        if available.is_empty():
            return []
        selected_asof = available.tail(1).row(0, named=True)["asof_timestamp"]
        exact = day.filter(pl.col("asof_timestamp") == selected_asof)
    if exact.is_empty() or "strike" not in exact.columns:
        return []
    agg = exact.group_by("strike").agg(
        pl.sum("call_oi").alias("call_oi") if "call_oi" in exact.columns else pl.lit(0.0).alias("call_oi"),
        pl.sum("put_oi").alias("put_oi") if "put_oi" in exact.columns else pl.lit(0.0).alias("put_oi"),
        pl.sum("total_oi").alias("total_oi") if "total_oi" in exact.columns else pl.lit(0.0).alias("total_oi"),
        pl.sum("total_volume").alias("option_volume") if "total_volume" in exact.columns else pl.lit(0.0).alias("option_volume"),
        pl.sum("total_oi_change").alias("oi_change") if "total_oi_change" in exact.columns else pl.lit(0.0).alias("oi_change"),
    )
    rows = agg.to_dicts()
    max_oi = max((_float_or_zero(row.get("total_oi")) for row in rows), default=0.0)
    max_volume = max((_float_or_zero(row.get("option_volume")) for row in rows), default=0.0)
    max_change = max((abs(_float_or_zero(row.get("oi_change"))) for row in rows), default=0.0)
    wall_rows = []
    for row in rows:
        total_oi = _float_or_zero(row.get("total_oi"))
        if total_oi <= 0:
            continue
        strike = _float_or_zero(row.get("strike"))
        spot_level = basis_adjusted_wall_level(strike, basis_reference) if basis_reference is not None else None
        level = spot_level if spot_level is not None else strike
        score = (
            (total_oi / max_oi if max_oi > 0 else 0.0)
            + 0.15 * (_float_or_zero(row.get("option_volume")) / max_volume if max_volume > 0 else 0.0)
            + 0.15 * (abs(_float_or_zero(row.get("oi_change"))) / max_change if max_change > 0 else 0.0)
        )
        wall_rows.append(
            {
                "strike": strike,
                "spot_level": spot_level,
                "level": level,
                "wall_score": score,
                "total_oi": total_oi,
                "option_volume": _float_or_zero(row.get("option_volume")),
                "oi_change": _float_or_zero(row.get("oi_change")),
                "distance": abs(level - reference_price),
            }
        )
    return sorted(wall_rows, key=lambda item: item["wall_score"], reverse=True)


def _select_wall(
    wall_rows: list[dict[str, Any]],
    *,
    reference_price: float,
    side: str,
) -> dict[str, Any] | None:
    if side == "above":
        candidates = [row for row in wall_rows if row["level"] >= reference_price]
    else:
        candidates = [row for row in wall_rows if row["level"] <= reference_price]
    if not candidates:
        return None
    return sorted(candidates, key=lambda row: (-row["wall_score"], row["distance"]))[0]


def _basis_at_asof(basis: pl.DataFrame, *, trade_date: str, asof: datetime) -> float | None:
    day = _date_rows(basis, trade_date)
    if day.is_empty() or "basis" not in day.columns:
        return None
    if "timestamp" in day.columns:
        day = day.filter(pl.col("timestamp") <= asof)
    values = [_float_or_none(row.get("basis")) for row in day.to_dicts()]
    present = sorted(value for value in values if value is not None and math.isfinite(value))
    if not present:
        return None
    return present[len(present) // 2]


def _implied_vol_atm(
    cme_iv: pl.DataFrame,
    *,
    trade_date: str,
    asof: datetime,
    reference_strike: float,
) -> float | None:
    day = _date_rows(cme_iv, trade_date)
    if day.is_empty() or "implied_vol" not in day.columns or "strike" not in day.columns:
        return None
    if "asof_timestamp" in day.columns:
        day = day.filter(pl.col("asof_timestamp") <= asof)
        if day.is_empty():
            return None
        selected_asof = day.sort("asof_timestamp").tail(1).row(0, named=True)["asof_timestamp"]
        day = day.filter(pl.col("asof_timestamp") == selected_asof)
    rows = day.to_dicts()
    if not rows:
        return None
    nearest = min(rows, key=lambda row: abs(_float_or_zero(row.get("strike")) - reference_strike))
    iv = _float_or_none(nearest.get("implied_vol"))
    if iv is None or iv <= 0:
        return None
    return iv * 100.0 if iv <= 1.0 else iv


def _expected_move(reference_price: float, iv_percent: float | None) -> float | None:
    if iv_percent is None or iv_percent <= 0:
        return None
    return reference_price * (iv_percent / 100.0) / math.sqrt(252.0)


def _reference_price_at_asof(bars: pl.DataFrame, asof: datetime) -> float:
    before = bars.filter(pl.col("timestamp") <= asof).sort("timestamp")
    row = before.tail(1).row(0, named=True) if not before.is_empty() else bars.sort("timestamp").head(1).row(0, named=True)
    return float(row["close"])


def _session_ohlc(bars: pl.DataFrame) -> dict[str, float]:
    sorted_bars = bars.sort("timestamp")
    return {
        "open": float(sorted_bars.head(1).row(0, named=True)["open"]),
        "high": float(sorted_bars.select(pl.max("high")).item()),
        "low": float(sorted_bars.select(pl.min("low")).item()),
        "close": float(sorted_bars.tail(1).row(0, named=True)["close"]),
    }


def _session_bounds(trade_day: date, price_rows: pl.DataFrame) -> tuple[datetime, datetime]:
    if not price_rows.is_empty() and "timestamp" in price_rows.columns:
        sorted_rows = price_rows.sort("timestamp")
        return (
            _as_utc(sorted_rows.head(1).row(0, named=True)["timestamp"]),
            _as_utc(sorted_rows.tail(1).row(0, named=True)["timestamp"]),
        )
    return (
        datetime.combine(trade_day, time(0, 0), tzinfo=UTC),
        datetime.combine(trade_day, time(23, 59), tzinfo=UTC),
    )


def _visual_replay_html(
    *,
    title: str,
    bars: list[dict[str, Any]],
    market: dict[str, Any],
    trades: list[dict[str, Any]],
) -> str:
    width = 1100
    height = 520
    if not bars:
        return f"<html><body><h1>{_html(title)}</h1><p>No bars available.</p></body></html>"
    price_values = []
    for row in bars:
        price_values.extend([_float_or_zero(row.get("high")), _float_or_zero(row.get("low"))])
    levels = [
        _float_or_none(market.get("spot_equivalent_wall_above")),
        _float_or_none(market.get("spot_equivalent_wall_below")),
        _float_or_none(market.get("one_sd_upper")),
        _float_or_none(market.get("one_sd_lower")),
        _float_or_none(market.get("two_sd_upper")),
        _float_or_none(market.get("two_sd_lower")),
    ]
    price_values.extend(value for value in levels if value is not None)
    low = min(price_values)
    high = max(price_values)
    span = max(high - low, 1.0)

    def y(value: float) -> float:
        return 470 - ((value - low) / span) * 410

    candle_width = max(3.0, (width - 120) / max(len(bars), 1) * 0.65)
    parts = [
        "<html><body>",
        f"<h1>{_html(title)}</h1>",
        "<p>Research-only replay. CME wall levels are used as context, not automatic trade direction.</p>",
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
    ]
    for index, row in enumerate(bars):
        x = 60 + index * (width - 120) / max(len(bars) - 1, 1)
        open_price = _float_or_zero(row.get("open"))
        close_price = _float_or_zero(row.get("close"))
        high_price = _float_or_zero(row.get("high"))
        low_price = _float_or_zero(row.get("low"))
        color = "#047857" if close_price >= open_price else "#b91c1c"
        parts.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{y(high_price):.1f}" y2="{y(low_price):.1f}" stroke="{color}" stroke-width="1"/>')
        rect_y = min(y(open_price), y(close_price))
        rect_h = max(abs(y(open_price) - y(close_price)), 1.0)
        parts.append(f'<rect x="{x - candle_width / 2:.1f}" y="{rect_y:.1f}" width="{candle_width:.1f}" height="{rect_h:.1f}" fill="{color}" opacity="0.75"/>')
    _add_level(parts, y, width, market.get("spot_equivalent_wall_above"), "wall above", "#7c3aed")
    _add_level(parts, y, width, market.get("spot_equivalent_wall_below"), "wall below", "#7c3aed")
    _add_level(parts, y, width, market.get("one_sd_upper"), "1SD upper", "#2563eb")
    _add_level(parts, y, width, market.get("one_sd_lower"), "1SD lower", "#2563eb")
    _add_level(parts, y, width, market.get("two_sd_upper"), "2SD upper", "#64748b")
    _add_level(parts, y, width, market.get("two_sd_lower"), "2SD lower", "#64748b")
    timestamp_to_x = {_timestamp_text(row.get("timestamp")): 60 + index * (width - 120) / max(len(bars) - 1, 1) for index, row in enumerate(bars)}
    for trade in trades[:30]:
        entry_ts = str(trade.get("entry_timestamp") or "")
        x = timestamp_to_x.get(entry_ts)
        entry = _float_or_none(trade.get("entry_price"))
        if x is None or entry is None:
            continue
        parts.append(f'<circle cx="{x:.1f}" cy="{y(entry):.1f}" r="4" fill="#f59e0b"><title>{_html(str(trade.get("rule_template")))} { _html(str(trade.get("exit_reason")))} </title></circle>')
        _add_level(parts, y, width, trade.get("tp_level"), "TP", "#16a34a", dash="4 4", opacity="0.35")
        _add_level(parts, y, width, trade.get("sl_level"), "SL", "#dc2626", dash="4 4", opacity="0.35")
    parts.extend(["</svg>", _visual_table(market, trades), "</body></html>"])
    return "\n".join(parts)


def _add_level(
    parts: list[str],
    y_fn: Any,
    width: int,
    value: Any,
    label: str,
    color: str,
    *,
    dash: str = "",
    opacity: str = "0.85",
) -> None:
    parsed = _float_or_none(value)
    if parsed is None:
        return
    y_value = y_fn(parsed)
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    parts.append(f'<line x1="55" x2="{width - 45}" y1="{y_value:.1f}" y2="{y_value:.1f}" stroke="{color}" stroke-width="1.5" opacity="{opacity}"{dash_attr}/>')
    parts.append(f'<text x="{width - 180}" y="{y_value - 4:.1f}" font-size="11" fill="{color}">{_html(label)} {_format_float(parsed)}</text>')


def _visual_table(market: dict[str, Any], trades: list[dict[str, Any]]) -> str:
    rows = [
        ("CME as-of", market.get("cme_asof_timestamp")),
        ("Wall map quality", market.get("wall_map_quality")),
        ("Level basis", market.get("level_basis")),
        ("IV context", _iv_context(market)),
        ("Replay rows", len(trades)),
    ]
    cells = "".join(f"<tr><th>{_html(str(k))}</th><td>{_html(str(v))}</td></tr>" for k, v in rows)
    return f"<table>{cells}</table>"


def _report_preview_lines(frame: pl.DataFrame, link: str) -> list[str]:
    return [
        _frame_markdown(frame),
        "",
        f"- Link: `{link}`",
    ]


def _entry_tp_report_lines(result: CmeOverlapEntryTpLabResult) -> list[str]:
    return [
        f"- Final pilot decision: `{result.final_decision}`",
        f"- Trade rows: `{result.trades.height}`",
        f"- Summary rows: `{result.summary.height}`",
        "- Important: one/few overlap dates are not validation evidence.",
        "",
        _frame_markdown(result.summary),
        "",
        "- Links: `outputs/cme_overlap_entry_tp_trades.csv`, `outputs/cme_overlap_entry_tp_summary.csv`, `outputs/cme_overlap_entry_tp_report.md`.",
    ]


def _visual_replay_lines(paths: tuple[Path, ...]) -> list[str]:
    if not paths:
        return ["No visual replay files were written because no 2026-05-15 market-map rows were available."]
    return [f"- `{_redact_text(path.as_posix())}`" for path in paths]


def _frame_markdown(frame: pl.DataFrame, *, limit: int = 20) -> str:
    if frame.is_empty():
        return "_No rows._"
    rows = ["| " + " | ".join(frame.columns) + " |", "|" + "|".join(["---"] * len(frame.columns)) + "|"]
    for raw in frame.head(limit).to_dicts():
        rows.append("| " + " | ".join(_markdown_cell(raw.get(column, "")) for column in frame.columns) + " |")
    return "\n".join(rows)


def _markdown_cell(value: Any) -> str:
    return _redact_text(str(value).replace("|", "\\|").replace("\n", " "))[:700]


def _safe_report_text(text: str) -> str:
    safe = _redact_text(text)
    lowered = safe.lower()
    for phrase in FORBIDDEN_REPORT_PHRASES:
        if phrase in lowered:
            raise ValueError(f"Forbidden report phrase: {phrase}")
    if re.search(r"[A-Za-z]:[\\/]+Users[\\/]+", safe):
        raise ValueError("Report contains an unredacted local source path.")
    return safe


def _redact_text(text: str) -> str:
    text = re.sub(r"[A-Za-z]:[\\/]+Users[\\/]+[^`|\s,\"]+", "<REDACTED_PATH>", text)
    text = re.sub(r"[A-Za-z]:[\\/]+[^`|\s,\"]+", "<REDACTED_PATH>", text)
    text = re.sub(r"/Users/[^`|\s,\"]+", "<REDACTED_PATH>", text)
    return text


def _price_candidates(timeframe: str, output_root: Path) -> list[Path]:
    names = {
        "m1": [
            output_root / "dukascopy_xau_m1_mid.parquet",
            output_root / "xau_spot_dukascopy_m1.parquet",
            Path("data_pipeline/data/processed/xauusd_m1_2024_to_now.parquet"),
        ],
        "15m": [
            output_root / "dukascopy_xau_15m.parquet",
            output_root / "xau_spot_dukascopy_15m.parquet",
            Path("data_pipeline/data/processed/xauusd_m15_2024_to_now.parquet"),
        ],
        "30m": [
            output_root / "dukascopy_xau_30m.parquet",
            output_root / "xau_spot_dukascopy_30m.parquet",
        ],
        "1h": [
            output_root / "dukascopy_xau_1h.parquet",
            output_root / "xau_spot_dukascopy_1h.parquet",
        ],
        "2h": [],
        "4h": [
            output_root / "dukascopy_xau_4h.parquet",
            output_root / "xau_spot_dukascopy_4h.parquet",
        ],
    }
    return names.get(timeframe, [])


def _source_label_for_path(path: Path) -> str:
    text = path.as_posix().lower()
    if "dukascopy" in text or "xauusd_m" in text:
        return "DUKASCOPY_XAUUSD_BID_ASK"
    return "LOCAL_PRICE_SOURCE"


def _load_optional(path: Path | None) -> pl.DataFrame:
    if path is None or not path.exists():
        return pl.DataFrame()
    try:
        if path.suffix.lower() == ".parquet":
            return pl.read_parquet(path)
        if path.suffix.lower() == ".csv":
            return pl.read_csv(path, infer_schema_length=1000)
    except Exception:
        return pl.DataFrame()
    return pl.DataFrame()


def _normalize_timestamp_column(frame: pl.DataFrame, timestamp_col: str) -> pl.DataFrame:
    dtype = frame.schema.get(timestamp_col)
    if dtype in (pl.Datetime, pl.Datetime(time_zone="UTC")) or str(dtype).startswith("Datetime"):
        return frame.with_columns(pl.col(timestamp_col).dt.convert_time_zone("UTC").alias("timestamp"))
    return frame.with_columns(
        pl.col(timestamp_col)
        .cast(pl.String, strict=False)
        .str.replace(r"\+0000$", "+00:00")
        .str.to_datetime(strict=False, time_zone="UTC")
        .alias("timestamp")
    )


def _filter_price_range(frame: pl.DataFrame, *, start_date: date, end_date: date) -> pl.DataFrame:
    if frame.is_empty():
        return frame
    start_dt = datetime.combine(start_date, time(0, 0), tzinfo=UTC)
    end_dt = datetime.combine(end_date + timedelta(days=1), time(0, 0), tzinfo=UTC)
    return frame.filter((pl.col("timestamp") >= start_dt) & (pl.col("timestamp") < end_dt))


def _date_rows(frame: pl.DataFrame, trade_date: str) -> pl.DataFrame:
    if frame.is_empty():
        return frame
    if "trade_date" in frame.columns:
        return frame.filter(pl.col("trade_date").cast(pl.String) == trade_date)
    for column in ("timestamp", "asof_timestamp", "signal_timestamp", "entry_timestamp"):
        if column in frame.columns:
            return frame.filter(pl.col(column).cast(pl.String).str.contains(trade_date))
    return pl.DataFrame()


def _has_date(frame: pl.DataFrame, trade_date: str) -> bool:
    return not _date_rows(frame, trade_date).is_empty()


def _has_any_date(frame: pl.DataFrame, trade_date: str) -> bool:
    if frame.is_empty():
        return False
    if _has_date(frame, trade_date):
        return True
    return any(trade_date in str(value) for row in frame.head(2000).to_dicts() for value in row.values())


def _date_set(frame: pl.DataFrame) -> set[str]:
    dates = set()
    if frame.is_empty():
        return dates
    for row in frame.to_dicts():
        for value in row.values():
            text = _date_text(value)
            if text:
                dates.add(text)
                break
    return dates


def _has_dukascopy_price(frame: pl.DataFrame) -> bool:
    if frame.is_empty() or "price_source_label" not in frame.columns:
        return False
    return any("DUKASCOPY" in str(value).upper() for value in frame.get_column("price_source_label").to_list())


def _audit_reason(
    *,
    has_price: bool,
    has_oi: bool,
    has_iv: bool,
    has_basis: bool,
    cme_asof: datetime | None,
    session_open: datetime,
    session_close: datetime,
    post_event_only: bool,
    usable: bool,
) -> str:
    if not has_price:
        return "Missing Dukascopy bid/ask price rows for the selected date."
    if not has_oi:
        return "Missing CME OI rows for the selected date."
    if cme_asof is None:
        return "CME rows exist but no usable as-of timestamp was found."
    if post_event_only:
        return "POST_EVENT_REPLAY_ONLY: CME as-of timestamp is after the tested decision window."
    notes = []
    if cme_asof > session_open:
        notes.append("CME context is available only after the session has started.")
    if not has_basis:
        notes.append("NEEDS_BASIS: futures-strike pilot only unless basis is added.")
    if not has_iv:
        notes.append("NO_IV_RANGE: OI-wall pilot only because IV range is missing.")
    if usable:
        notes.append("Usable for overlap entry/TP pilot with as-of gating.")
    if not notes:
        notes.append("Usable for overlap entry/TP pilot before session decisions.")
    if cme_asof > session_close:
        notes.append("CME as-of is after session close.")
    return " ".join(notes)


def _wall_map_quality(
    *,
    usable: bool,
    has_basis: bool,
    has_iv: bool,
    wall_rows: list[dict[str, Any]],
) -> str:
    if not usable or not wall_rows:
        return "DEBUG_ONLY"
    if has_basis and has_iv:
        return "HIGH"
    if has_basis:
        return "MEDIUM"
    return "LOW"


def _market_level(market: dict[str, Any], side: str) -> float | None:
    key = "spot_equivalent_wall_above" if side == "above" else "spot_equivalent_wall_below"
    fallback = "top_oi_wall_above" if side == "above" else "top_oi_wall_below"
    return _float_or_none(market.get(key)) or _float_or_none(market.get(fallback))


def _wall_value(wall: dict[str, Any] | None, key: str) -> float | None:
    return _float_or_none(wall.get(key)) if wall else None


def _wall_metric_sum(
    wall_above: dict[str, Any] | None,
    wall_below: dict[str, Any] | None,
    key: str,
) -> float | None:
    values = [_wall_value(wall, key) for wall in (wall_above, wall_below)]
    present = [value for value in values if value is not None]
    return sum(present) if present else None


def _nearest_wall_distance(
    *,
    reference_price: float,
    wall_above: dict[str, Any] | None,
    wall_below: dict[str, Any] | None,
) -> float | None:
    distances = []
    for wall in (wall_above, wall_below):
        if wall is not None:
            distances.append(abs(_float_or_zero(wall.get("level")) - reference_price))
    return min(distances) if distances else None


def _data_quality_label(market: dict[str, Any], bars: list[dict[str, Any]]) -> str:
    spread_available = all(bool(row.get("spread_available")) for row in bars[: min(len(bars), 20)])
    label = str(market.get("wall_map_quality") or "DEBUG_ONLY")
    if not spread_available:
        return f"{label}|NO_BID_ASK_SPREAD"
    return label


def _iv_context(market: dict[str, Any]) -> str:
    if not _bool_value(market.get("iv_range_available")):
        return "NO_IV_RANGE"
    return (
        f"IV_ATM={_format_float(market.get('implied_vol_atm'))};"
        f"1SD={_format_float(market.get('one_sd_lower'))}-{_format_float(market.get('one_sd_upper'))};"
        f"2SD={_format_float(market.get('two_sd_lower'))}-{_format_float(market.get('two_sd_upper'))}"
    )


def _pine_signal_rows(pine_signals: pl.DataFrame, *, trade_date: str, timeframe: str) -> list[dict[str, Any]]:
    if pine_signals.is_empty() or "timestamp" not in pine_signals.columns:
        return []
    frame = pine_signals.filter(pl.col("timestamp").cast(pl.String).str.contains(trade_date))
    if "interval" in frame.columns:
        frame = frame.filter(pl.col("interval").cast(pl.String).str.to_lowercase() == timeframe.lower())
    return frame.sort("timestamp").to_dicts()


def _signal_direction(signal: dict[str, Any]) -> str:
    text = " ".join(
        str(signal.get(key) or "")
        for key in ("direction_candidate", "raw_signal", "reason")
    ).lower()
    if "short" in text or "sell" in text or "breakdown" in text:
        return "short"
    if "long" in text or "buy" in text or "breakout" in text:
        return "long"
    return ""


def _pine_cme_block_state(
    *,
    direction: str,
    entry_price: float,
    wall_above: float | None,
    wall_below: float | None,
    signal: dict[str, Any],
    proximity_points: float = 10.0,
) -> str:
    if _bool_value(signal.get("no_trade_middle_range")):
        return "BLOCK_NO_TRADE_MIDDLE_RANGE"
    if direction == "long" and wall_above is not None and 0 <= wall_above - entry_price <= proximity_points:
        return "ALLOW_ACCEPTANCE_BREAKOUT_LONG" if _bool_value(signal.get("acceptance_breakout")) else "BLOCK_LONG_INTO_STRONG_WALL"
    if direction == "short" and wall_below is not None and 0 <= entry_price - wall_below <= proximity_points:
        return "ALLOW_ACCEPTANCE_BREAKDOWN_SHORT" if _bool_value(signal.get("acceptance_breakdown")) else "BLOCK_SHORT_INTO_STRONG_WALL"
    if _bool_value(signal.get("rejection_after_level_touch")):
        return "ALLOW_REJECTION_CONTEXT"
    return "CME_NO_BLOCK"


def _blocking_wall(direction: str, wall_above: float | None, wall_below: float | None) -> float | None:
    return wall_above if direction == "long" else wall_below


def _first_bar_index_after(bars: list[dict[str, Any]], timestamp: datetime) -> int | None:
    for index, row in enumerate(bars):
        if _as_utc(row["timestamp"]) > timestamp:
            return index
    return None


def _first_profitable_level(
    levels: list[float | None],
    *,
    entry_price: float,
    direction: str,
) -> float | None:
    for level in levels:
        if level is None:
            continue
        if direction == "long" and level > entry_price:
            return level
        if direction == "short" and level < entry_price:
            return level
    return None


def _touch_tolerance(bars: list[dict[str, Any]]) -> float:
    ranges = [_float_or_zero(row.get("high")) - _float_or_zero(row.get("low")) for row in bars[:100]]
    return max(1.0, _mean(ranges) * 0.40)


def _execution_buffer(bars: list[dict[str, Any]]) -> float:
    spreads = [_float_or_zero(row.get("ask_close")) - _float_or_zero(row.get("bid_close")) for row in bars[:100]]
    ranges = [_float_or_zero(row.get("high")) - _float_or_zero(row.get("low")) for row in bars[:100]]
    return max(0.5, _mean(spreads) * 2.0, _mean(ranges) * 0.10)


def _timeout_bars(timeframe: str) -> int:
    minutes = TIMEFRAME_MINUTES.get(timeframe, 15)
    return max(2, int(240 / minutes))


def _wall_distance(entry_price: float, wall: Any) -> float | None:
    parsed = _float_or_none(wall)
    return abs(entry_price - parsed) if parsed is not None else None


def _exit_rate(rows: list[dict[str, Any]], reason: str) -> float | None:
    if not rows:
        return None
    return sum(1 for row in rows if row.get("exit_reason") == reason) / len(rows)


def _false_signal_rate(rows: list[dict[str, Any]]) -> float | None:
    events = sum(int(row.get("event_count") or 0) for row in rows)
    no_entries = sum(int(row.get("no_entry_count") or 0) for row in rows)
    return no_entries / events if events else None


def _best_worst_templates(rows: list[dict[str, Any]]) -> tuple[str, str]:
    eligible = [
        row
        for row in rows
        if int(row.get("trade_count") or 0) > 0 and row.get("expectancy") is not None
    ]
    if not eligible:
        return "", ""
    sorted_rows = sorted(eligible, key=lambda row: float(row.get("expectancy") or 0.0))
    return str(sorted_rows[-1].get("rule_template") or ""), str(sorted_rows[0].get("rule_template") or "")


def _best_worst_templates_from_trades(rows: list[dict[str, Any]]) -> tuple[str, str]:
    if not rows:
        return "", ""
    grouped: dict[str, list[float]] = {}
    for row in rows:
        template = str(row.get("rule_template") or "")
        if not template:
            continue
        grouped.setdefault(template, []).append(_float_or_zero(row.get("pnl_after_spread_cost")))
    if not grouped:
        return "", ""
    ranked = sorted((sum(values) / len(values), template) for template, values in grouped.items())
    return ranked[-1][1], ranked[0][1]


def _usable_dates(date_audit: pl.DataFrame) -> set[str]:
    if date_audit.is_empty() or "usable_for_entry_tp_pilot" not in date_audit.columns:
        return set()
    return set(
        row["trade_date"]
        for row in date_audit.filter(pl.col("usable_for_entry_tp_pilot")).to_dicts()
    )


def _decision_scope_rows(date_audit: pl.DataFrame) -> pl.DataFrame:
    if date_audit.is_empty():
        return date_audit
    if "has_cme_oi" not in date_audit.columns:
        return date_audit
    scoped = date_audit.filter(pl.col("has_cme_oi"))
    return scoped if not scoped.is_empty() else date_audit


def _any_false(frame: pl.DataFrame, column: str) -> bool:
    return not frame.is_empty() and column in frame.columns and frame.filter(~pl.col(column)).height > 0


def _any_true(frame: pl.DataFrame, column: str) -> bool:
    return not frame.is_empty() and column in frame.columns and frame.filter(pl.col(column)).height > 0


def _final_decision_label(decision: pl.DataFrame) -> str:
    if decision.is_empty():
        return "CME_WALL_CONTEXT_ONLY"
    applied = {
        row["decision_label"]
        for row in decision.to_dicts()
        if bool(row.get("applies"))
    }
    if "POST_EVENT_REPLAY_ONLY" in applied:
        return "POST_EVENT_REPLAY_ONLY"
    if "CME_WALL_ENTRY_TP_CANDIDATE" in applied:
        return "CME_WALL_ENTRY_TP_CANDIDATE"
    if "CME_OVERLAP_PILOT_READY" in applied:
        return "CME_OVERLAP_PILOT_READY"
    return "CME_WALL_CONTEXT_ONLY"


def _first_non_empty_frame(frames: dict[str, pl.DataFrame]) -> pl.DataFrame:
    for frame in frames.values():
        if not frame.is_empty():
            return frame
    return _empty_price_frame()


def _concat_or_empty(frames: list[pl.DataFrame], schema: dict[str, Any]) -> pl.DataFrame:
    present = [frame for frame in frames if not frame.is_empty()]
    if not present:
        return pl.DataFrame(schema=schema)
    try:
        return pl.concat(present, how="diagonal_relaxed")
    except Exception:
        return present[0]


def _group_rows(frame: pl.DataFrame, columns: tuple[str, ...]) -> dict[tuple[Any, ...], list[dict[str, Any]]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for row in frame.to_dicts() if not frame.is_empty() else []:
        key = tuple(row.get(column) for column in columns)
        groups.setdefault(key, []).append(row)
    return groups


def _date_range(start_date: date, end_date: date) -> list[date]:
    days = []
    current = start_date
    while current <= end_date:
        days.append(current)
        current += timedelta(days=1)
    return days


def _parse_timeframes(value: str | list[str] | tuple[str, ...]) -> tuple[str, ...]:
    items = value.split(",") if isinstance(value, str) else list(value)
    parsed = tuple(item.strip() for item in items if item.strip())
    unsupported = [item for item in parsed if item not in TIMEFRAME_MINUTES]
    if unsupported:
        raise ValueError(f"Unsupported pilot timeframe(s): {', '.join(unsupported)}")
    return parsed


def _parse_date(value: str) -> date:
    return date.fromisoformat(value[:10])


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return _as_utc(value)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return _as_utc(datetime.fromisoformat(text.replace("Z", "+00:00")))
    except ValueError:
        match = re.search(r"20\d{2}-\d{2}-\d{2}(?:[T ][0-9:.+-]+)?", text)
        if not match:
            return None
        try:
            return _as_utc(datetime.fromisoformat(match.group(0).replace("Z", "+00:00")))
        except ValueError:
            return None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _earliest_datetime(frame: pl.DataFrame, column: str) -> datetime | None:
    if frame.is_empty() or column not in frame.columns:
        return None
    value = frame.select(pl.min(column)).item()
    return _as_utc(value) if isinstance(value, datetime) else _parse_datetime(value)


def _timestamp_text(value: Any) -> str:
    parsed = _parse_datetime(value)
    if parsed is None:
        return _redact_text(str(value or ""))
    return parsed.isoformat().replace("+00:00", "Z")


def _date_text(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    match = re.search(r"20\d{2}-\d{2}-\d{2}", str(value or ""))
    return match.group(0) if match else ""


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(parsed) else parsed


def _float_or_zero(value: Any) -> float:
    parsed = _float_or_none(value)
    return parsed if parsed is not None else 0.0


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() not in {"", "0", "false", "no", "none", "null", "nan"}


def _mean(values: list[float]) -> float:
    present = [value for value in values if value is not None]
    return sum(present) / len(present) if present else 0.0


def _profit_factor(values: list[float]) -> float | None:
    wins = sum(value for value in values if value > 0)
    losses = abs(sum(value for value in values if value < 0))
    return wins / losses if losses > 0 else None


def _max_drawdown(values: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        drawdown = min(drawdown, equity - peak)
    return drawdown


def _format_float(value: Any) -> str:
    parsed = _float_or_none(value)
    return "n/a" if parsed is None else f"{parsed:.4f}"


def _html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _normal_column(column: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", column.lower())


def _first_column(columns: dict[str, str], names: tuple[str, ...]) -> str | None:
    for name in names:
        key = _normal_column(name)
        if key in columns:
            return columns[key]
    return None


def _polars_duration(timeframe: str) -> str:
    minutes = TIMEFRAME_MINUTES[timeframe]
    return f"{minutes}m" if minutes < 60 else f"{minutes // 60}h"


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


def _empty_price_frame() -> pl.DataFrame:
    return pl.DataFrame(schema=_price_schema())


def _price_schema() -> dict[str, Any]:
    return {
        "timestamp": pl.Datetime(time_zone="UTC"),
        "trade_date": pl.String,
        "timeframe": pl.String,
        "open": pl.Float64,
        "high": pl.Float64,
        "low": pl.Float64,
        "close": pl.Float64,
        "spread_points": pl.Float64,
        "bid_open": pl.Float64,
        "bid_high": pl.Float64,
        "bid_low": pl.Float64,
        "bid_close": pl.Float64,
        "ask_open": pl.Float64,
        "ask_high": pl.Float64,
        "ask_low": pl.Float64,
        "ask_close": pl.Float64,
        "spread_available": pl.Boolean,
        "price_source_label": pl.String,
    }


def _date_audit_schema() -> dict[str, Any]:
    return {
        "trade_date": pl.String,
        "has_dukascopy_price": pl.Boolean,
        "has_cme_oi": pl.Boolean,
        "has_cme_iv": pl.Boolean,
        "has_cme_futures": pl.Boolean,
        "has_basis": pl.Boolean,
        "has_guru_context": pl.Boolean,
        "has_pine_python_signals": pl.Boolean,
        "cme_asof_timestamp": pl.String,
        "can_use_cme_before_session": pl.Boolean,
        "can_use_cme_during_session": pl.Boolean,
        "can_use_cme_only_as_post_event_replay": pl.Boolean,
        "usable_for_entry_tp_pilot": pl.Boolean,
        "missing_components": pl.String,
        "reason_plain_english": pl.String,
    }


def _market_map_schema() -> dict[str, Any]:
    return {
        "trade_date": pl.String,
        "timeframe": pl.String,
        "session_open": pl.Float64,
        "session_high": pl.Float64,
        "session_low": pl.Float64,
        "session_close": pl.Float64,
        "basis_reference": pl.Float64,
        "top_oi_wall_above": pl.Float64,
        "top_oi_wall_below": pl.Float64,
        "top_oi_wall_score": pl.Float64,
        "spot_equivalent_wall_above": pl.Float64,
        "spot_equivalent_wall_below": pl.Float64,
        "nearest_wall_distance": pl.Float64,
        "oi_change_near_wall": pl.Float64,
        "option_volume_near_wall": pl.Float64,
        "implied_vol_atm": pl.Float64,
        "one_sd_upper": pl.Float64,
        "one_sd_lower": pl.Float64,
        "two_sd_upper": pl.Float64,
        "two_sd_lower": pl.Float64,
        "iv_range_available": pl.Boolean,
        "wall_map_quality": pl.String,
        "cme_asof_timestamp": pl.String,
        "reference_price_at_asof": pl.Float64,
        "level_basis": pl.String,
    }


def _rule_template_schema() -> dict[str, Any]:
    return {
        "rule_template": pl.String,
        "condition": pl.String,
        "direction": pl.String,
        "tp_options": pl.String,
        "sl_rule": pl.String,
        "research_only": pl.Boolean,
    }


def _trade_schema() -> dict[str, Any]:
    return {
        "trade_date": pl.String,
        "timeframe": pl.String,
        "rule_template": pl.String,
        "entry_timestamp": pl.String,
        "direction": pl.String,
        "entry_price": pl.Float64,
        "tp_level": pl.Float64,
        "sl_level": pl.Float64,
        "exit_timestamp": pl.String,
        "exit_reason": pl.String,
        "pnl_points": pl.Float64,
        "pnl_after_spread_cost": pl.Float64,
        "mfe": pl.Float64,
        "mae": pl.Float64,
        "bars_held": pl.Int64,
        "wall_used": pl.Float64,
        "wall_distance_at_entry": pl.Float64,
        "iv_range_context": pl.String,
        "guru_filter_state": pl.String,
        "pine_signal_state": pl.String,
        "data_quality_label": pl.String,
    }


def _summary_schema() -> dict[str, Any]:
    return {
        "trade_date": pl.String,
        "timeframe": pl.String,
        "rule_template": pl.String,
        "event_count": pl.Int64,
        "trade_count": pl.Int64,
        "win_rate": pl.Float64,
        "avg_win": pl.Float64,
        "avg_loss": pl.Float64,
        "expectancy": pl.Float64,
        "profit_factor": pl.Float64,
        "max_drawdown": pl.Float64,
        "total_pnl_after_spread_cost": pl.Float64,
        "average_mfe": pl.Float64,
        "average_mae": pl.Float64,
        "tp_hit_rate": pl.Float64,
        "sl_hit_rate": pl.Float64,
        "no_entry_count": pl.Int64,
        "sample_size_warning": pl.Boolean,
    }


def _timeframe_schema() -> dict[str, Any]:
    return {
        "timeframe": pl.String,
        "trade_count": pl.Int64,
        "total_pnl": pl.Float64,
        "expectancy": pl.Float64,
        "profit_factor": pl.Float64,
        "tp_hit_rate": pl.Float64,
        "sl_hit_rate": pl.Float64,
        "false_signal_rate": pl.Float64,
        "average_hold_time": pl.Float64,
        "best_template": pl.String,
        "worst_template": pl.String,
        "sample_warning": pl.String,
    }


def _decision_schema() -> dict[str, Any]:
    return {
        "decision_label": pl.String,
        "applies": pl.Boolean,
        "reason": pl.String,
        "usable_overlap_dates": pl.Int64,
        "trade_count": pl.Int64,
        "pilot_only": pl.Boolean,
    }


def _generic_schema() -> dict[str, Any]:
    return {"trade_date": pl.String}


def main() -> None:
    """CLI entry point."""

    result = run_cme_overlap_entry_tp_lab()
    print(f"final_decision: {result.final_decision}")
    print(f"overlap_dates: {result.date_audit.height}")
    print(f"trade_rows: {result.trades.height}")


if __name__ == "__main__":
    main()
