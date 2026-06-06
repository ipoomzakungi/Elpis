"""Gemini SD/grid confirmation backtest layer.

This module compares blind SD/grid entries against confirmation-based variants
using Dukascopy OHLC only. Transcript support remains separate from market-data
validation, and SD levels are marked as realized-volatility proxies when true
CME IV is unavailable.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

import polars as pl


TIMEFRAMES = ("15m", "30m", "1h", "4h")
SD_PROXY_SOURCE = "REALIZED_VOL_PROXY"
FINAL_RECOMMENDATIONS = (
    "CONFIRMATION_REQUIRED",
    "GRID_AS_REFERENCE_ONLY",
    "NO_TRADE_FILTER_PROMISING",
    "NEEDS_CME_IV_FOR_TRUE_SD",
    "WATCHLIST_ONLY",
    "NOT_READY_FOR_MONEY",
)
RESEARCH_WARNING = (
    "Research-only SD/grid confirmation diagnostic. Transcript-supported rules "
    "are hypotheses only; realized-volatility proxy bands are not true CME-IV SD "
    "validation."
)
FORBIDDEN_PATTERNS = (
    r"\bbuy\b",
    r"\bsell\b",
    r"profitable",
    r"profitability",
    r"safe to trade",
    r"live[- ]ready",
)


@dataclass(frozen=True)
class GeminiSdGridConfirmationBacktestResult:
    """Generated confirmation-backtest artifacts."""

    events: pl.DataFrame
    entry_model_comparison: pl.DataFrame
    tp_sl_model_comparison: pl.DataFrame
    grid_clustering_test: pl.DataFrame
    rule_decision: pl.DataFrame
    final_recommendation: str
    paths: dict[str, Path]


def run_gemini_sd_grid_confirmation_backtest(
    *,
    output_dir: str | Path = "outputs",
    write_outputs: bool = True,
) -> GeminiSdGridConfirmationBacktestResult:
    """Run the Gemini SD/grid confirmation comparison and write artifacts."""

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    paths = _output_paths(output_root)
    inputs = _load_inputs(output_root)
    price_by_timeframe = _price_inputs(inputs)

    events = build_sd_grid_event_dataset(inputs=inputs)
    entry_models = build_entry_model_comparison(
        events=events,
        price_by_timeframe=price_by_timeframe,
    )
    tp_sl = build_tp_sl_model_comparison(
        events=events,
        price_by_timeframe=price_by_timeframe,
    )
    grid = build_grid_clustering_test(inputs=inputs)
    decision = build_sd_grid_rule_decision(
        entry_model_comparison=entry_models,
        tp_sl_model_comparison=tp_sl,
        grid_clustering_test=grid,
    )
    final = choose_final_recommendation(decision)
    result = GeminiSdGridConfirmationBacktestResult(
        events=events,
        entry_model_comparison=entry_models,
        tp_sl_model_comparison=tp_sl,
        grid_clustering_test=grid,
        rule_decision=decision,
        final_recommendation=final,
        paths=paths,
    )
    if write_outputs:
        write_gemini_sd_grid_confirmation_outputs(result)
    return result


def build_sd_grid_event_dataset(*, inputs: dict[str, Any]) -> pl.DataFrame:
    """Build SD/grid event rows for 15m, 30m, 1h, and 4h price frames."""

    daily = _normalize_price(_frame_input(inputs, "price_1d"), timeframe="1d")
    rows: list[dict[str, Any]] = []
    event_seq = 1
    for timeframe in TIMEFRAMES:
        frame = _normalize_price(_frame_input(inputs, f"price_{timeframe}"), timeframe=timeframe)
        if frame.is_empty():
            continue
        contexts = _contexts_for_frame(frame, daily)
        frame_rows = frame.sort("timestamp").to_dicts()
        context_by_date = {context["trade_date"]: context for context in contexts}
        for index, bar in enumerate(frame_rows):
            context = context_by_date.get(_date_text(bar.get("trade_date") or bar.get("timestamp")))
            if not context:
                continue
            generated = _events_for_bar(
                bar=bar,
                index=index,
                timeframe=timeframe,
                context=context,
                next_bar=frame_rows[index + 1] if index + 1 < len(frame_rows) else None,
            )
            for event in generated:
                event["event_id"] = f"SDGRID_{event_seq:09d}"
                rows.append(_safe_row(event))
                event_seq += 1
    return _frame(rows, _event_schema()).sort(["timeframe", "timestamp", "event_type", "level_type"])


def build_entry_model_comparison(
    *,
    events: pl.DataFrame,
    price_by_timeframe: dict[str, pl.DataFrame],
) -> pl.DataFrame:
    """Compare blind SD entries with rejection and acceptance confirmation."""

    price_cache = _price_cache(price_by_timeframe)
    specs = [
        ("BLIND_2SD_FADE", "REACH_2SD", "2SD", "FADE"),
        ("BLIND_3SD_FADE", "REACH_3SD", "3SD", "FADE"),
        ("REJECTION_CONFIRMED_2SD_FADE", "REJECTION_BACK_INSIDE", "2SD", "FADE"),
        ("REJECTION_CONFIRMED_3SD_FADE", "REJECTION_BACK_INSIDE", "3SD", "FADE"),
        ("ACCEPTANCE_CONTINUATION", "ACCEPTANCE_1H_CLOSE", "ANY", "CONTINUATION"),
        ("NO_TRADE_1SD_FILTER", "INSIDE_1SD", "1SD", "BLOCK"),
    ]
    rows = []
    for model_id, event_type, level_type, mode in specs:
        selected = _select_model_events(events, event_type=event_type, level_type=level_type)
        rows.append(
            _entry_summary_row(
                model_id=model_id,
                events=selected,
                price_cache=price_cache,
                mode=mode,
            )
        )
    return _frame([_safe_row(row) for row in rows], _entry_model_schema())


def build_tp_sl_model_comparison(
    *,
    events: pl.DataFrame,
    price_by_timeframe: dict[str, pl.DataFrame],
) -> pl.DataFrame:
    """Compare fixed half/full-block targets and stop models."""

    price_cache = _price_cache(price_by_timeframe)
    base_events = _select_model_events(
        events,
        event_type="REJECTION_BACK_INSIDE",
        level_type="ANY",
    )
    if not base_events:
        base_events = _select_model_events(events, event_type="REACH_2SD", level_type="ANY")
    specs = [
        ("TP_HALF_BLOCK_12_50_SL_HALF_BLOCK_12_50", "FIXED_12_50", "FIXED_12_50"),
        ("TP_FULL_BLOCK_25_SL_HALF_BLOCK_12_50", "FIXED_25", "FIXED_12_50"),
        ("TP_FULL_BLOCK_25_SL_3_5SD", "FIXED_25", "SD_3_5"),
        ("TP_AT_MIDPOINT_SL_3_5SD", "MIDPOINT_GRID", "SD_3_5"),
        ("TP_AT_OPPOSITE_GRID_SL_3_5SD", "OPPOSITE_GRID", "SD_3_5"),
    ]
    rows = []
    for model_id, target_model, stop_model in specs:
        measurements = [
            _simulate_event(
                event,
                price_cache,
                mode="FADE",
                target_model=target_model,
                stop_model=stop_model,
            )
            for event in base_events
        ]
        rows.append(
            _tp_sl_summary_row(
                model_id=model_id,
                target_model=target_model,
                stop_model=stop_model,
                measurements=[measurement for measurement in measurements if measurement],
            )
        )
    return _frame([_safe_row(row) for row in rows], _tp_sl_schema())


def build_grid_clustering_test(*, inputs: dict[str, Any]) -> pl.DataFrame:
    """Compare fixed grids against shifted grids and realized-vol dynamic bands."""

    daily = _normalize_price(_frame_input(inputs, "price_1d"), timeframe="1d")
    rows = []
    for timeframe in TIMEFRAMES:
        frame = _normalize_price(_frame_input(inputs, f"price_{timeframe}"), timeframe=timeframe)
        if frame.is_empty():
            continue
        contexts = _contexts_for_frame(frame, daily)
        for grid_size, grid_name in ((25.0, "$25_GRID_CLUSTERING"), (12.5, "$12_50_HALF_BLOCK_CLUSTERING")):
            rows.append(_grid_row(frame, contexts, timeframe=timeframe, grid_size=grid_size, grid_name=grid_name))
    return _frame([_safe_row(row) for row in rows], _grid_schema())


def build_sd_grid_rule_decision(
    *,
    entry_model_comparison: pl.DataFrame,
    tp_sl_model_comparison: pl.DataFrame,
    grid_clustering_test: pl.DataFrame,
) -> pl.DataFrame:
    """Build conservative rule decisions from the comparison artifacts."""

    entry = _rows_by_key(entry_model_comparison, "model_id")
    blind_3 = entry.get("BLIND_3SD_FADE", {})
    confirmed_3 = entry.get("REJECTION_CONFIRMED_3SD_FADE", {})
    confirmed_2 = entry.get("REJECTION_CONFIRMED_2SD_FADE", {})
    acceptance = entry.get("ACCEPTANCE_CONTINUATION", {})
    no_trade = entry.get("NO_TRADE_1SD_FILTER", {})
    best_entry = _best_entry_model(entry_model_comparison)
    dangerous = _dangerous_entry_model(entry_model_comparison)
    grid_label = _grid_decision_label(grid_clustering_test)
    rows = [
        {
            "rule_id": "BLIND_3SD_FADE",
            "decision_label": "BLIND_ENTRY_WEAK",
            "evidence_summary": _model_summary(blind_3),
            "limitation": "Blind 3SD behavior is evaluated with realized-vol proxy bands only.",
            "final_recommendation": "CONFIRMATION_REQUIRED",
        },
        {
            "rule_id": "REJECTION_CONFIRMED_2SD_FADE",
            "decision_label": "CONFIRMATION_REQUIRED",
            "evidence_summary": _model_summary(confirmed_2),
            "limitation": "Requires close-back-inside confirmation; not a standalone level touch.",
            "final_recommendation": "CONFIRMATION_REQUIRED",
        },
        {
            "rule_id": "REJECTION_CONFIRMED_3SD_FADE",
            "decision_label": "CONFIRMATION_REQUIRED",
            "evidence_summary": _model_summary(confirmed_3),
            "limitation": "Requires close-back-inside confirmation and tail-risk review.",
            "final_recommendation": "CONFIRMATION_REQUIRED",
        },
        {
            "rule_id": "ACCEPTANCE_CONTINUATION",
            "decision_label": "CONFIRMATION_REQUIRED",
            "evidence_summary": _model_summary(acceptance),
            "limitation": "Requires 1h hold beyond the SD level; price-only proxy only.",
            "final_recommendation": "CONFIRMATION_REQUIRED",
        },
        {
            "rule_id": "NO_TRADE_1SD_FILTER",
            "decision_label": "NO_TRADE_FILTER_PROMISING" if int(no_trade.get("event_count") or 0) else "WATCHLIST_ONLY",
            "evidence_summary": _model_summary(no_trade),
            "limitation": "Filter blocks middle-zone events; it is not an entry model.",
            "final_recommendation": "CONFIRMATION_REQUIRED",
        },
        {
            "rule_id": "GRID_CLUSTERING",
            "decision_label": grid_label,
            "evidence_summary": _grid_summary(grid_clustering_test),
            "limitation": "Grid levels are reference geometry; use random-shift baseline.",
            "final_recommendation": "CONFIRMATION_REQUIRED",
        },
        {
            "rule_id": "SD_PROXY_SOURCE",
            "decision_label": "NEEDS_CME_IV_FOR_TRUE_SD",
            "evidence_summary": "All SD bands in this layer use REALIZED_VOL_PROXY.",
            "limitation": "True SD validation needs timestamp-safe CME IV.",
            "final_recommendation": "CONFIRMATION_REQUIRED",
        },
        {
            "rule_id": "OVERALL",
            "decision_label": "CONFIRMATION_REQUIRED",
            "evidence_summary": f"Most promising={best_entry}; dangerous={dangerous}.",
            "limitation": "Use as watchlist research until CME-IV validation exists.",
            "final_recommendation": "CONFIRMATION_REQUIRED",
        },
    ]
    return _frame([_safe_row(row) for row in rows], _decision_schema())


def choose_final_recommendation(decision: pl.DataFrame) -> str:
    """Choose the final recommendation from decision rows."""

    if decision.is_empty():
        return "NOT_READY_FOR_MONEY"
    labels = set(decision.get_column("decision_label").to_list())
    if "CONFIRMATION_REQUIRED" in labels:
        return "CONFIRMATION_REQUIRED"
    if "GRID_AS_REFERENCE_ONLY" in labels:
        return "GRID_AS_REFERENCE_ONLY"
    if "NEEDS_CME_IV_FOR_TRUE_SD" in labels:
        return "NEEDS_CME_IV_FOR_TRUE_SD"
    return "WATCHLIST_ONLY"


def write_gemini_sd_grid_confirmation_outputs(
    result: GeminiSdGridConfirmationBacktestResult,
) -> None:
    """Write CSV and Markdown outputs."""

    frame_paths = {
        "events": (result.events, "events_csv", "events_md", "Gemini SD Grid Events"),
        "entry": (
            result.entry_model_comparison,
            "entry_comparison_csv",
            "entry_comparison_md",
            "Gemini SD Grid Entry Model Comparison",
        ),
        "tp_sl": (
            result.tp_sl_model_comparison,
            "tp_sl_comparison_csv",
            "tp_sl_comparison_md",
            "Gemini TP SL Model Comparison",
        ),
        "grid": (
            result.grid_clustering_test,
            "grid_clustering_csv",
            "grid_clustering_md",
            "Gemini Grid Clustering Test",
        ),
        "decision": (
            result.rule_decision,
            "rule_decision_csv",
            "rule_decision_md",
            "Gemini SD Grid Rule Decision",
        ),
    }
    for frame, csv_key, md_key, title in frame_paths.values():
        frame.write_csv(result.paths[csv_key])
        result.paths[md_key].write_text(
            _safe_report_text(_artifact_markdown(title, frame)),
            encoding="utf-8",
        )


def gemini_sd_grid_confirmation_report_lines(
    result: GeminiSdGridConfirmationBacktestResult | None,
) -> list[str]:
    """Return report lines for research_report.md."""

    if result is None:
        return ["## Gemini SD/Grid Confirmation Backtest", "", "Confirmation layer was not run."]
    return [
        "## Gemini SD/Grid Confirmation Backtest",
        "",
        RESEARCH_WARNING,
        "",
        f"- Final recommendation: `{result.final_recommendation}`",
        f"- Event rows: {result.events.height}",
        "- Guardrail: `NOT_READY_FOR_MONEY` remains active.",
        "",
        "## Blind vs Confirmed SD Entries",
        "",
        _frame_markdown(result.entry_model_comparison),
        "",
        "## TP/SL Model Comparison",
        "",
        _frame_markdown(result.tp_sl_model_comparison),
        "",
        "## Grid Clustering Test",
        "",
        _frame_markdown(result.grid_clustering_test),
        "",
        "## SD/Grid Rule Decision",
        "",
        _frame_markdown(result.rule_decision),
        "",
        "- Links: `outputs/gemini_sd_grid_events.csv`, "
        "`outputs/gemini_sd_grid_entry_model_comparison.csv`, "
        "`outputs/gemini_tp_sl_model_comparison.csv`, "
        "`outputs/gemini_grid_clustering_test.csv`, "
        "`outputs/gemini_sd_grid_rule_decision.csv`.",
    ]


def report_text_is_safe(text: str) -> bool:
    """Return true when generated text avoids restricted phrases and local paths."""

    safe = _safe_report_text(text)
    lowered = safe.lower()
    return safe == text and not any(re.search(pattern, lowered) for pattern in FORBIDDEN_PATTERNS)


def _events_for_bar(
    *,
    bar: dict[str, Any],
    index: int,
    timeframe: str,
    context: dict[str, Any],
    next_bar: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    high = _float(bar.get("high"))
    low = _float(bar.get("low"))
    close = _float(bar.get("close"))
    if high is None or low is None or close is None:
        return []
    open_price = float(context["session_open"])
    one_sd = float(context["one_sd"])
    sigma_high = (high - open_price) / one_sd
    sigma_low = (low - open_price) / one_sd
    sigma_close = (close - open_price) / one_sd
    common = {
        "timeframe": timeframe,
        "timestamp": _timestamp_text(bar.get("timestamp")),
        "trade_date": context["trade_date"],
        "bar_index": index,
        "open": _float(bar.get("open")),
        "high": high,
        "low": low,
        "close": close,
        "session_open": open_price,
        "one_sd_value": one_sd,
        "sd_proxy_source": SD_PROXY_SOURCE,
        "sigma_high": sigma_high,
        "sigma_low": sigma_low,
        "sigma_close": sigma_close,
        "grid_size": None,
        "grid_level": None,
        "close_back_inside": False,
        "hold_beyond_level": False,
        "continues_beyond_3_5sd": False,
    }
    rows: list[dict[str, Any]] = []
    if abs(sigma_close) <= 1.0:
        rows.append({**common, "event_type": "INSIDE_1SD", "level_type": "1SD", "side": "MIDDLE", "trigger_price": close})
    for threshold, event_type, level_type in ((2.0, "REACH_2SD", "2SD"), (3.0, "REACH_3SD", "3SD"), (3.5, "REACH_3_5SD", "3.5SD")):
        if sigma_high >= threshold:
            rows.append({**common, "event_type": event_type, "level_type": level_type, "side": "UPPER", "trigger_price": open_price + threshold * one_sd})
        if sigma_low <= -threshold:
            rows.append({**common, "event_type": event_type, "level_type": level_type, "side": "LOWER", "trigger_price": open_price - threshold * one_sd})
    for grid_size, event_type in ((25.0, "TOUCH_25_GRID"), (12.5, "TOUCH_12_50_HALF_GRID")):
        grid_level = _touched_grid_level(high, low, close, grid_size)
        if grid_level is not None:
            rows.append({**common, "event_type": event_type, "level_type": "GRID", "side": _grid_side(close, grid_level), "trigger_price": grid_level, "grid_size": grid_size, "grid_level": grid_level})
    for threshold, level_type in ((2.0, "2SD"), (3.0, "3SD")):
        if sigma_high >= threshold and sigma_close < threshold:
            rows.append({**common, "event_type": "REJECTION_BACK_INSIDE", "level_type": level_type, "side": "UPPER", "trigger_price": close, "close_back_inside": True})
        if sigma_low <= -threshold and sigma_close > -threshold:
            rows.append({**common, "event_type": "REJECTION_BACK_INSIDE", "level_type": level_type, "side": "LOWER", "trigger_price": close, "close_back_inside": True})
    if timeframe == "1h" and next_bar is not None:
        next_close = _float(next_bar.get("close"))
        next_timestamp = _timestamp_text(next_bar.get("timestamp"))
        if next_close is not None:
            next_sigma = (next_close - open_price) / one_sd
            for threshold, level_type in ((2.0, "2SD"), (3.0, "3SD")):
                if sigma_close >= threshold and next_sigma >= threshold:
                    rows.append({**common, "timestamp": next_timestamp, "bar_index": index + 1, "event_type": "ACCEPTANCE_1H_CLOSE", "level_type": level_type, "side": "UPPER", "trigger_price": next_close, "hold_beyond_level": True})
                if sigma_close <= -threshold and next_sigma <= -threshold:
                    rows.append({**common, "timestamp": next_timestamp, "bar_index": index + 1, "event_type": "ACCEPTANCE_1H_CLOSE", "level_type": level_type, "side": "LOWER", "trigger_price": next_close, "hold_beyond_level": True})
    if sigma_close >= 3.5:
        rows.append({**common, "event_type": "CONTINUE_BEYOND_3_5SD", "level_type": "3.5SD", "side": "UPPER", "trigger_price": close, "continues_beyond_3_5sd": True})
    if sigma_close <= -3.5:
        rows.append({**common, "event_type": "CONTINUE_BEYOND_3_5SD", "level_type": "3.5SD", "side": "LOWER", "trigger_price": close, "continues_beyond_3_5sd": True})
    return rows


def _entry_summary_row(
    *,
    model_id: str,
    events: list[dict[str, Any]],
    price_cache: dict[str, dict[str, Any]],
    mode: str,
) -> dict[str, Any]:
    if mode == "BLOCK":
        return {
            "model_id": model_id,
            "event_count": len(events),
            "entry_count": 0,
            "win_rate": None,
            "target_hit_rate": None,
            "stop_hit_rate": None,
            "expectancy_proxy": 0.0,
            "average_mfe": None,
            "average_mae": None,
            "max_adverse_excursion": None,
            "spread_cost_estimate": _spread_cost_for_events(events),
            "tail_risk_count": 0,
            "sample_size_warning": len(events) < 100,
        }
    measurements = [
            _simulate_event(
                event,
                price_cache,
                mode=mode,
                target_model="FIXED_12_50",
                stop_model="SD_3_5" if mode == "FADE" else "FIXED_12_50",
        )
        for event in events
    ]
    return _entry_metrics(model_id, [measurement for measurement in measurements if measurement], len(events))


def _simulate_event(
    event: dict[str, Any],
    price_cache: dict[str, dict[str, Any]],
    *,
    mode: str,
    target_model: str,
    stop_model: str,
) -> dict[str, Any] | None:
    timeframe = _text(event.get("timeframe"))
    cached = price_cache.get(timeframe)
    if not cached:
        return None
    rows = cached["rows"]
    index = int(event.get("bar_index") or 0)
    future = rows[index + 1 : index + 1 + _horizon_for_timeframe(timeframe)]
    if not future:
        return None
    side = _text(event.get("side"))
    entry = _float(event.get("trigger_price")) or _float(event.get("close"))
    if entry is None:
        return None
    direction = _direction_for_event(side=side, mode=mode)
    if direction == 0:
        return None
    one_sd = _float(event.get("one_sd_value")) or 1.0
    session_open = _float(event.get("session_open")) or entry
    target_points = _target_points(
        target_model,
        entry=entry,
        direction=direction,
        session_open=session_open,
    )
    stop_points = _stop_points(
        stop_model,
        entry=entry,
        direction=direction,
        session_open=session_open,
        one_sd=one_sd,
    )
    highs = [_float(row.get("high")) for row in future]
    lows = [_float(row.get("low")) for row in future]
    clean_highs = [value for value in highs if value is not None]
    clean_lows = [value for value in lows if value is not None]
    if direction > 0:
        mfe = max(0.0, max((value - entry for value in clean_highs), default=0.0))
        mae = min(0.0, min((value - entry for value in clean_lows), default=0.0))
    else:
        mfe = max(0.0, max((entry - value for value in clean_lows), default=0.0))
        mae = min(0.0, min((entry - value for value in clean_highs), default=0.0))
    target_hit = mfe >= target_points
    stop_hit = abs(mae) >= stop_points
    spread = float(cached["spread"])
    result = (target_points if target_hit else 0.0) - (stop_points if stop_hit else 0.0) - spread
    return {
        "target_hit": target_hit,
        "stop_hit": stop_hit,
        "win": target_hit and not stop_hit,
        "mfe": mfe,
        "mae": mae,
        "max_adverse": mae,
        "result": result,
        "spread_cost": spread,
        "target_points": target_points,
        "stop_points": stop_points,
        "tail_risk": stop_hit or abs(mae) >= max(25.0, one_sd),
    }


def _entry_metrics(
    model_id: str,
    measurements: list[dict[str, Any]],
    event_count: int,
) -> dict[str, Any]:
    entry_count = len(measurements)
    if not measurements:
        return {
            "model_id": model_id,
            "event_count": event_count,
            "entry_count": 0,
            "win_rate": None,
            "target_hit_rate": None,
            "stop_hit_rate": None,
            "expectancy_proxy": None,
            "average_mfe": None,
            "average_mae": None,
            "max_adverse_excursion": None,
            "spread_cost_estimate": None,
            "tail_risk_count": 0,
            "sample_size_warning": True,
        }
    return {
        "model_id": model_id,
        "event_count": event_count,
        "entry_count": entry_count,
        "win_rate": _bool_rate(measurements, "win"),
        "target_hit_rate": _bool_rate(measurements, "target_hit"),
        "stop_hit_rate": _bool_rate(measurements, "stop_hit"),
        "expectancy_proxy": _mean([float(row.get("result") or 0.0) for row in measurements]),
        "average_mfe": _mean([float(row.get("mfe") or 0.0) for row in measurements]),
        "average_mae": _mean([float(row.get("mae") or 0.0) for row in measurements]),
        "max_adverse_excursion": min(float(row.get("max_adverse") or 0.0) for row in measurements),
        "spread_cost_estimate": _mean([float(row.get("spread_cost") or 0.0) for row in measurements]),
        "tail_risk_count": sum(1 for row in measurements if bool(row.get("tail_risk"))),
        "sample_size_warning": entry_count < 100,
    }


def _tp_sl_summary_row(
    *,
    model_id: str,
    target_model: str,
    stop_model: str,
    measurements: list[dict[str, Any]],
) -> dict[str, Any]:
    if not measurements:
        return {
            "model_id": model_id,
            "target_model": target_model,
            "stop_model": stop_model,
            "event_count": 0,
            "target_hit_rate": None,
            "stop_hit_rate": None,
            "avg_win_proxy": None,
            "avg_loss_proxy": None,
            "expectancy_proxy": None,
            "max_drawdown_proxy": None,
            "tail_loss_warning": True,
        }
    wins = [float(row.get("target_points") or 0.0) for row in measurements if bool(row.get("target_hit"))]
    losses = [-float(row.get("stop_points") or 0.0) for row in measurements if bool(row.get("stop_hit"))]
    results = [float(row.get("result") or 0.0) for row in measurements]
    return {
        "model_id": model_id,
        "target_model": target_model,
        "stop_model": stop_model,
        "event_count": len(measurements),
        "target_hit_rate": _bool_rate(measurements, "target_hit"),
        "stop_hit_rate": _bool_rate(measurements, "stop_hit"),
        "avg_win_proxy": _mean(wins),
        "avg_loss_proxy": _mean(losses),
        "expectancy_proxy": _mean(results),
        "max_drawdown_proxy": _max_drawdown(results),
        "tail_loss_warning": _bool_rate(measurements, "stop_hit") > _bool_rate(measurements, "target_hit"),
    }


def _grid_row(
    frame: pl.DataFrame,
    contexts: list[dict[str, Any]],
    *,
    timeframe: str,
    grid_size: float,
    grid_name: str,
) -> dict[str, Any]:
    rows = frame.sort("timestamp").to_dicts()
    high_low_values: list[float] = []
    for row in rows:
        high = _float(row.get("high"))
        low = _float(row.get("low"))
        if high is not None:
            high_low_values.append(high)
        if low is not None:
            high_low_values.append(low)
    tolerance = 1.5
    touch_count = sum(1 for value in high_low_values if _distance_to_grid(value, grid_size) <= tolerance)
    high_low_rate = touch_count / len(high_low_values) if high_low_values else 0.0
    turning_values = _turning_point_values(rows)
    turning_rate = (
        sum(1 for value in turning_values if _distance_to_grid(value, grid_size) <= tolerance) / len(turning_values)
        if turning_values
        else 0.0
    )
    random_rates = [_shifted_grid_rate(high_low_values, grid_size, tolerance, shift) for shift in _random_shifts(grid_size)]
    random_baseline = _mean(random_rates)
    p_value_proxy = (sum(1 for rate in random_rates if rate >= high_low_rate) + 1) / (len(random_rates) + 1)
    dynamic_rate = _dynamic_band_rate(high_low_values, contexts, tolerance)
    uplift = high_low_rate - random_baseline
    if len(high_low_values) < 200:
        interpretation = "NEEDS_MORE_TESTING"
    elif uplift > 0.02 and p_value_proxy <= 0.25:
        interpretation = "GRID_CLUSTERING_PROMISING"
    elif uplift > 0.005:
        interpretation = "GRID_CLUSTERING_WEAK"
    else:
        interpretation = "GRID_CLUSTERING_RANDOM_LIKE"
    return {
        "grid_test_id": f"{timeframe}_{grid_name}",
        "timeframe": timeframe,
        "grid_type": grid_name,
        "touch_count": touch_count,
        "high_low_cluster_rate": high_low_rate,
        "turning_point_cluster_rate": turning_rate,
        "random_grid_baseline": random_baseline,
        "uplift_vs_random": uplift,
        "p_value_proxy": p_value_proxy,
        "dynamic_band_cluster_rate": dynamic_rate,
        "interpretation": interpretation,
    }


def _contexts_for_frame(frame: pl.DataFrame, daily: pl.DataFrame) -> list[dict[str, Any]]:
    frame_rows = frame.sort("timestamp").to_dicts()
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in frame_rows:
        trade_date = _date_text(row.get("trade_date") or row.get("timestamp"))
        if trade_date:
            grouped.setdefault(trade_date, []).append(row)
    ranges = _daily_ranges(daily)
    ordered_dates = sorted(grouped)
    contexts = []
    for trade_date in ordered_dates:
        bars = grouped[trade_date]
        session_open = _float(bars[0].get("open"))
        if session_open is None:
            continue
        one_sd = _one_sd_proxy(trade_date, session_open, ranges, ordered_dates)
        contexts.append(
            {
                "trade_date": trade_date,
                "session_open": session_open,
                "one_sd": one_sd,
                "sd_proxy_source": SD_PROXY_SOURCE,
            }
        )
    return contexts


def _one_sd_proxy(
    trade_date: str,
    session_open: float,
    daily_ranges: dict[str, float],
    ordered_dates: list[str],
) -> float:
    try:
        index = ordered_dates.index(trade_date)
    except ValueError:
        index = 0
    prior = [
        daily_ranges[day]
        for day in ordered_dates[max(0, index - 20) : index]
        if day in daily_ranges and daily_ranges[day] > 0
    ]
    if prior:
        return max(_median(prior) / 2.0, 1.0)
    current = daily_ranges.get(trade_date)
    if current and current > 0:
        return max(current / 2.0, 1.0)
    return max(session_open * 0.01, 1.0)


def _normalize_price(frame: pl.DataFrame, *, timeframe: str) -> pl.DataFrame:
    if frame.is_empty() or "timestamp" not in frame.columns:
        return pl.DataFrame(schema=_price_schema())
    out = frame
    for column in ("open", "high", "low", "close"):
        if column not in out.columns and f"mid_{column}" in out.columns:
            out = out.with_columns(pl.col(f"mid_{column}").alias(column))
        if column not in out.columns:
            out = out.with_columns(pl.lit(None).cast(pl.Float64).alias(column))
        else:
            out = out.with_columns(pl.col(column).cast(pl.Float64, strict=False).alias(column))
    if "trade_date" not in out.columns:
        out = out.with_columns(
            pl.col("timestamp").map_elements(_date_text, return_dtype=pl.Utf8).alias("trade_date")
        )
    if "spread_points" not in out.columns:
        out = out.with_columns(pl.lit(None).cast(pl.Float64).alias("spread_points"))
    out = out.with_columns(pl.lit(timeframe).alias("timeframe"))
    return out.select(["timestamp", "trade_date", "timeframe", "open", "high", "low", "close", "spread_points"])


def _price_inputs(inputs: dict[str, Any]) -> dict[str, pl.DataFrame]:
    return {
        timeframe: _normalize_price(_frame_input(inputs, f"price_{timeframe}"), timeframe=timeframe)
        for timeframe in TIMEFRAMES
    }


def _price_cache(price_by_timeframe: dict[str, pl.DataFrame]) -> dict[str, dict[str, Any]]:
    cache: dict[str, dict[str, Any]] = {}
    for timeframe, frame in price_by_timeframe.items():
        if frame.is_empty():
            continue
        cache[timeframe] = {
            "rows": frame.sort("timestamp").to_dicts(),
            "spread": _spread_estimate_for_timeframe(frame),
        }
    return cache


def _load_inputs(output_root: Path) -> dict[str, pl.DataFrame]:
    paths = {
        "claims": output_root / "gemini_guru_rulebook_claims.csv",
        "sd_grid_family": output_root / "gemini_sd_grid_rule_family.csv",
        "sd_grid_backtest": output_root / "gemini_sd_grid_backtest.csv",
        "caution_audit": output_root / "gemini_rulebook_caution_audit.csv",
        "price_15m": output_root / "dukascopy_xau_15m.parquet",
        "price_30m": output_root / "dukascopy_xau_30m.parquet",
        "price_1h": output_root / "dukascopy_xau_1h.parquet",
        "price_4h": output_root / "dukascopy_xau_4h.parquet",
        "price_1d": output_root / "dukascopy_xau_1d.parquet",
        "spread_report": output_root / "dukascopy_xau_spread_report.csv",
    }
    return {name: _read_optional(path) for name, path in paths.items()}


def _read_optional(path: Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    try:
        if path.suffix.lower() == ".parquet":
            return pl.read_parquet(path)
        return pl.read_csv(path, infer_schema_length=None)
    except Exception:
        return pl.DataFrame()


def _output_paths(output_root: Path) -> dict[str, Path]:
    return {
        "events_csv": output_root / "gemini_sd_grid_events.csv",
        "events_md": output_root / "gemini_sd_grid_events.md",
        "entry_comparison_csv": output_root / "gemini_sd_grid_entry_model_comparison.csv",
        "entry_comparison_md": output_root / "gemini_sd_grid_entry_model_comparison.md",
        "tp_sl_comparison_csv": output_root / "gemini_tp_sl_model_comparison.csv",
        "tp_sl_comparison_md": output_root / "gemini_tp_sl_model_comparison.md",
        "grid_clustering_csv": output_root / "gemini_grid_clustering_test.csv",
        "grid_clustering_md": output_root / "gemini_grid_clustering_test.md",
        "rule_decision_csv": output_root / "gemini_sd_grid_rule_decision.csv",
        "rule_decision_md": output_root / "gemini_sd_grid_rule_decision.md",
    }


def _select_model_events(
    events: pl.DataFrame,
    *,
    event_type: str,
    level_type: str,
) -> list[dict[str, Any]]:
    if events.is_empty():
        return []
    selected = events.filter(pl.col("event_type") == event_type)
    if level_type != "ANY":
        selected = selected.filter(pl.col("level_type") == level_type)
    if event_type == "REJECTION_BACK_INSIDE":
        selected = selected.filter(pl.col("close_back_inside"))
    if event_type == "ACCEPTANCE_1H_CLOSE":
        selected = selected.filter(pl.col("hold_beyond_level"))
    return selected.to_dicts()


def _direction_for_event(*, side: str, mode: str) -> int:
    if mode == "FADE":
        return -1 if side == "UPPER" else 1 if side == "LOWER" else 0
    if mode == "CONTINUATION":
        return 1 if side == "UPPER" else -1 if side == "LOWER" else 0
    return 0


def _target_points(
    target_model: str,
    *,
    entry: float,
    direction: int,
    session_open: float,
) -> float:
    if target_model == "FIXED_12_50":
        return 12.5
    if target_model == "FIXED_25":
        return 25.0
    if target_model == "MIDPOINT_GRID":
        return max(_distance_to_next_grid(entry, direction, grid=12.5), 1.0)
    if target_model == "OPPOSITE_GRID":
        return max(abs(entry - session_open), _distance_to_next_grid(entry, direction, grid=25.0), 1.0)
    return 12.5


def _stop_points(
    stop_model: str,
    *,
    entry: float,
    direction: int,
    session_open: float,
    one_sd: float,
) -> float:
    if stop_model == "FIXED_12_50":
        return 12.5
    if stop_model == "SD_3_5":
        stop_level = session_open - 3.5 * one_sd if direction > 0 else session_open + 3.5 * one_sd
        return max(abs(entry - stop_level), 12.5)
    return 12.5


def _distance_to_next_grid(value: float, direction: int, *, grid: float) -> float:
    if direction > 0:
        target = math.ceil((value + 0.000001) / grid) * grid
        if target <= value:
            target += grid
        return target - value
    target = math.floor((value - 0.000001) / grid) * grid
    if target >= value:
        target -= grid
    return value - target


def _horizon_for_timeframe(timeframe: str) -> int:
    return {"15m": 16, "30m": 8, "1h": 4, "4h": 2}.get(timeframe, 4)


def _spread_estimate_for_timeframe(frame: pl.DataFrame) -> float:
    if frame.is_empty() or "spread_points" not in frame.columns:
        return 0.5
    values = [_float(value) for value in frame.get_column("spread_points").drop_nulls().to_list()]
    clean = [value for value in values if value is not None and value >= 0]
    return _mean(clean) if clean else 0.5


def _spread_cost_for_events(events: list[dict[str, Any]]) -> float:
    values = [_float(row.get("spread_cost_estimate")) for row in events]
    clean = [value for value in values if value is not None]
    return _mean(clean) if clean else 0.5


def _daily_ranges(daily: pl.DataFrame) -> dict[str, float]:
    out: dict[str, float] = {}
    if daily.is_empty():
        return out
    for row in daily.to_dicts():
        high = _float(row.get("high"))
        low = _float(row.get("low"))
        trade_date = _date_text(row.get("trade_date") or row.get("timestamp"))
        if high is not None and low is not None and high >= low and trade_date:
            out[trade_date] = high - low
    return out


def _touched_grid_level(high: float, low: float, close: float, grid_size: float) -> float | None:
    tolerance = 1.5
    candidates = {
        round(high / grid_size) * grid_size,
        round(low / grid_size) * grid_size,
        round(close / grid_size) * grid_size,
        math.floor(low / grid_size) * grid_size,
        math.ceil(high / grid_size) * grid_size,
    }
    for level in sorted(candidates, key=lambda value: abs(close - value)):
        if low - tolerance <= level <= high + tolerance:
            return float(level)
    return None


def _grid_side(close: float, grid_level: float) -> str:
    if close > grid_level:
        return "ABOVE_GRID"
    if close < grid_level:
        return "BELOW_GRID"
    return "AT_GRID"


def _distance_to_grid(value: float, grid: float) -> float:
    remainder = abs(value) % grid
    return min(remainder, grid - remainder)


def _turning_point_values(rows: list[dict[str, Any]]) -> list[float]:
    values: list[float] = []
    for index in range(1, len(rows) - 1):
        prev, current, nxt = rows[index - 1], rows[index], rows[index + 1]
        high = _float(current.get("high"))
        low = _float(current.get("low"))
        if high is not None and high >= (_float(prev.get("high")) or high) and high >= (_float(nxt.get("high")) or high):
            values.append(high)
        if low is not None and low <= (_float(prev.get("low")) or low) and low <= (_float(nxt.get("low")) or low):
            values.append(low)
    return values


def _random_shifts(grid: float) -> list[float]:
    return [grid * fraction for fraction in (0.11, 0.23, 0.37, 0.49, 0.61, 0.73, 0.87)]


def _shifted_grid_rate(values: list[float], grid: float, tolerance: float, shift: float) -> float:
    if not values:
        return 0.0
    hits = 0
    for value in values:
        shifted = value - shift
        remainder = abs(shifted) % grid
        if min(remainder, grid - remainder) <= tolerance:
            hits += 1
    return hits / len(values)


def _dynamic_band_rate(values: list[float], contexts: list[dict[str, Any]], tolerance: float) -> float:
    if not values or not contexts:
        return 0.0
    levels: list[float] = []
    for context in contexts:
        session_open = float(context["session_open"])
        one_sd = float(context["one_sd"])
        for multiplier in (1.0, 2.0, 3.0):
            levels.append(session_open + multiplier * one_sd)
            levels.append(session_open - multiplier * one_sd)
    hits = sum(1 for value in values if min(abs(value - level) for level in levels) <= tolerance)
    return hits / len(values)


def _best_entry_model(frame: pl.DataFrame) -> str:
    if frame.is_empty():
        return ""
    eligible = frame.filter(pl.col("entry_count") > 0)
    if eligible.is_empty():
        return ""
    return _text(eligible.sort("expectancy_proxy", descending=True).row(0, named=True).get("model_id"))


def _dangerous_entry_model(frame: pl.DataFrame) -> str:
    if frame.is_empty():
        return ""
    eligible = frame.filter(pl.col("entry_count") > 0)
    if eligible.is_empty():
        return ""
    rows = eligible.to_dicts()
    rows.sort(
        key=lambda row: (
            (float(row.get("tail_risk_count") or 0.0) / max(float(row.get("entry_count") or 0.0), 1.0)),
            float(row.get("stop_hit_rate") or 0.0),
        ),
        reverse=True,
    )
    return _text(rows[0].get("model_id"))


def _grid_decision_label(grid: pl.DataFrame) -> str:
    if grid.is_empty():
        return "WATCHLIST_ONLY"
    interpretations = set(grid.get_column("interpretation").to_list())
    if "GRID_CLUSTERING_PROMISING" in interpretations or "GRID_CLUSTERING_WEAK" in interpretations:
        return "GRID_AS_REFERENCE_ONLY"
    return "WATCHLIST_ONLY"


def _model_summary(row: dict[str, Any]) -> str:
    if not row:
        return "No events."
    return (
        f"events={int(row.get('event_count') or 0)}; "
        f"entries={int(row.get('entry_count') or 0)}; "
        f"expectancy_proxy={_format_float(row.get('expectancy_proxy'))}; "
        f"tail_risk_count={int(row.get('tail_risk_count') or 0)}"
    )


def _grid_summary(frame: pl.DataFrame) -> str:
    if frame.is_empty():
        return "No grid rows."
    promising = frame.filter(pl.col("interpretation").is_in(["GRID_CLUSTERING_PROMISING", "GRID_CLUSTERING_WEAK"])).height
    return f"grid_reference_rows={promising}; total_rows={frame.height}"


def _artifact_markdown(title: str, frame: pl.DataFrame) -> str:
    return "\n\n".join(["# " + title, RESEARCH_WARNING, _frame_markdown(frame)])


def _frame_markdown(frame: pl.DataFrame, *, limit: int = 30) -> str:
    if frame.is_empty():
        return "_No rows._"
    sample = frame.head(limit)
    lines = [
        "| " + " | ".join(sample.columns) + " |",
        "| " + " | ".join("---" for _ in sample.columns) + " |",
    ]
    for row in sample.to_dicts():
        lines.append(
            "| "
            + " | ".join(_markdown_cell(row.get(column, "")) for column in sample.columns)
            + " |"
        )
    if frame.height > limit:
        lines.append(f"\n_Showing {limit} of {frame.height} rows._")
    return "\n".join(lines)


def _markdown_cell(value: Any) -> str:
    return _safe_text(str(value if value is not None else "")).replace("|", "\\|")[:700]


def _safe_report_text(text: str) -> str:
    safe = _safe_text(text)
    for pattern in FORBIDDEN_PATTERNS:
        safe = re.sub(pattern, _replacement_for(pattern), safe, flags=re.IGNORECASE)
    return safe


def _replacement_for(pattern: str) -> str:
    if "buy" in pattern or "sell" in pattern:
        return "direction"
    if "profit" in pattern:
        return "money-result"
    return "blocked phrase"


def _safe_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: _safe_text(value) if isinstance(value, str) else value for key, value in row.items()}


def _safe_text(value: Any) -> str:
    text = str(value or "")
    text = _redact_paths(text)
    text = re.sub(r"\bbuy\b", "direction", text, flags=re.IGNORECASE)
    text = re.sub(r"\bsell\b", "direction", text, flags=re.IGNORECASE)
    text = re.sub(r"profitable|profitability", "money-result", text, flags=re.IGNORECASE)
    text = re.sub(r"safe to trade|live[- ]ready", "blocked phrase", text, flags=re.IGNORECASE)
    return text.strip()


def _redact_paths(text: str) -> str:
    safe = re.sub(r"[A-Za-z]:\\Users\\[^\s|)<>\"']+", "<REDACTED_PATH>", text)
    safe = re.sub(r"[A-Za-z]:\\[^\s|)<>\"']+", "<REDACTED_PATH>", safe)
    return re.sub(r"/(?:Users|home|mnt|var|tmp)/[^\s|)<>\"']+", "<REDACTED_PATH>", safe)


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


def _frame_input(inputs: dict[str, Any], key: str) -> pl.DataFrame:
    value = inputs.get(key)
    return value if isinstance(value, pl.DataFrame) else pl.DataFrame()


def _rows_by_key(frame: pl.DataFrame, key: str) -> dict[str, dict[str, Any]]:
    if frame.is_empty() or key not in frame.columns:
        return {}
    return {_text(row.get(key)): row for row in frame.to_dicts()}


def _bool_rate(rows: list[dict[str, Any]], key: str) -> float:
    return sum(1 for row in rows if bool(row.get(key))) / len(rows) if rows else 0.0


def _mean(values: Iterable[float]) -> float:
    clean = [float(value) for value in values if value is not None and not math.isnan(float(value))]
    return sum(clean) / len(clean) if clean else 0.0


def _median(values: list[float]) -> float:
    clean = sorted(values)
    if not clean:
        return 0.0
    mid = len(clean) // 2
    if len(clean) % 2:
        return clean[mid]
    return (clean[mid - 1] + clean[mid]) / 2.0


def _max_drawdown(values: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        drawdown = min(drawdown, equity - peak)
    return drawdown


def _float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return None
        return number
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _timestamp_text(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return _text(value)


def _date_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    match = re.search(r"\d{4}-\d{2}-\d{2}", str(value))
    return match.group(0) if match else ""


def _format_float(value: Any) -> str:
    number = _float(value)
    return "n/a" if number is None else f"{number:.4f}"


def _event_schema() -> dict[str, Any]:
    return {
        "event_id": pl.Utf8,
        "timeframe": pl.Utf8,
        "timestamp": pl.Utf8,
        "trade_date": pl.Utf8,
        "bar_index": pl.Int64,
        "event_type": pl.Utf8,
        "level_type": pl.Utf8,
        "side": pl.Utf8,
        "trigger_price": pl.Float64,
        "open": pl.Float64,
        "high": pl.Float64,
        "low": pl.Float64,
        "close": pl.Float64,
        "session_open": pl.Float64,
        "one_sd_value": pl.Float64,
        "sd_proxy_source": pl.Utf8,
        "sigma_high": pl.Float64,
        "sigma_low": pl.Float64,
        "sigma_close": pl.Float64,
        "grid_size": pl.Float64,
        "grid_level": pl.Float64,
        "close_back_inside": pl.Boolean,
        "hold_beyond_level": pl.Boolean,
        "continues_beyond_3_5sd": pl.Boolean,
    }


def _entry_model_schema() -> dict[str, Any]:
    return {
        "model_id": pl.Utf8,
        "event_count": pl.Int64,
        "entry_count": pl.Int64,
        "win_rate": pl.Float64,
        "target_hit_rate": pl.Float64,
        "stop_hit_rate": pl.Float64,
        "expectancy_proxy": pl.Float64,
        "average_mfe": pl.Float64,
        "average_mae": pl.Float64,
        "max_adverse_excursion": pl.Float64,
        "spread_cost_estimate": pl.Float64,
        "tail_risk_count": pl.Int64,
        "sample_size_warning": pl.Boolean,
    }


def _tp_sl_schema() -> dict[str, Any]:
    return {
        "model_id": pl.Utf8,
        "target_model": pl.Utf8,
        "stop_model": pl.Utf8,
        "event_count": pl.Int64,
        "target_hit_rate": pl.Float64,
        "stop_hit_rate": pl.Float64,
        "avg_win_proxy": pl.Float64,
        "avg_loss_proxy": pl.Float64,
        "expectancy_proxy": pl.Float64,
        "max_drawdown_proxy": pl.Float64,
        "tail_loss_warning": pl.Boolean,
    }


def _grid_schema() -> dict[str, Any]:
    return {
        "grid_test_id": pl.Utf8,
        "timeframe": pl.Utf8,
        "grid_type": pl.Utf8,
        "touch_count": pl.Int64,
        "high_low_cluster_rate": pl.Float64,
        "turning_point_cluster_rate": pl.Float64,
        "random_grid_baseline": pl.Float64,
        "uplift_vs_random": pl.Float64,
        "p_value_proxy": pl.Float64,
        "dynamic_band_cluster_rate": pl.Float64,
        "interpretation": pl.Utf8,
    }


def _decision_schema() -> dict[str, Any]:
    return {
        "rule_id": pl.Utf8,
        "decision_label": pl.Utf8,
        "evidence_summary": pl.Utf8,
        "limitation": pl.Utf8,
        "final_recommendation": pl.Utf8,
    }


def _price_schema() -> dict[str, Any]:
    return {
        "timestamp": pl.Datetime,
        "trade_date": pl.Utf8,
        "timeframe": pl.Utf8,
        "open": pl.Float64,
        "high": pl.Float64,
        "low": pl.Float64,
        "close": pl.Float64,
        "spread_points": pl.Float64,
    }


def main() -> None:
    """CLI entry point."""

    result = run_gemini_sd_grid_confirmation_backtest()
    print(f"final_recommendation: {result.final_recommendation}")
    print(f"events: {result.events.height}")
    print(f"entry_models: {result.entry_model_comparison.height}")


if __name__ == "__main__":
    main()
