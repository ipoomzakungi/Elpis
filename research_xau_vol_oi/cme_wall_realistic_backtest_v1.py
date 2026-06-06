"""Realistic CME wall entry/exit backtest v1.

This module rebuilds the previous CME wall strategy report as a conservative
entry/exit replay. It uses fixed levels known at setup time, waits for
post-snapshot confirmation, validates target/stop order against candles after
entry, and records at most one event row for a strategy/wall/session key.
"""

from __future__ import annotations

import bisect
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import polars as pl


STRATEGY_NAMES = (
    "WALL_REJECTION_CONFIRMED_FADE",
    "WALL_ACCEPTANCE_CONTINUATION",
    "AVOID_DIRECT_WALL_TRADE_FILTER",
    "SD_2_REJECTION_CONFIRMED_FADE",
    "COMBINED_CONSERVATIVE_REALISTIC",
)
FINAL_RECOMMENDATIONS = (
    "REALISTIC_BACKTEST_READY",
    "REALISTIC_BUT_SMALL_SAMPLE",
    "FILTER_CANDIDATE_ONLY",
    "NEED_MORE_CME_DAYS",
    "NOT_READY_FOR_MONEY",
)
RESEARCH_WARNING = (
    "Research-only realistic CME wall backtest v1. Entries require confirmed "
    "price reaction, targets and stops are fixed at entry, and path checks use "
    "candles after entry only."
)
PILOT_WARNING = "PILOT_ONLY / NEED_MORE_CME_DAYS / NOT_READY_FOR_MONEY"
MID_PRICE_PROXY = "MID_PRICE_PROXY_INTRADAY_PATH"
REALIZED_VOL_PROXY = "REALIZED_VOL_PROXY"
HALF_BLOCK = 12.5
FULL_BLOCK = 25.0
ENTRY_WINDOW = timedelta(hours=4)
EXIT_WINDOW = timedelta(hours=4)
MIN_SAMPLE_FOR_READY = 100


@dataclass(frozen=True)
class PriceCandle:
    """Normalized OHLC candle used by the path checker."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    spread: float


@dataclass(frozen=True)
class PathResult:
    """Result of an after-entry target/stop path check."""

    exit_timestamp: str
    exit_price: float
    exit_reason: str
    gross_pnl_points: float
    mfe: float
    mae: float
    bars_held: int
    ambiguous_same_candle: bool


@dataclass(frozen=True)
class CmeWallRealisticBacktestV1Result:
    """Generated realistic CME wall backtest artifacts."""

    definitions: pl.DataFrame
    trade_events: pl.DataFrame
    performance_summary: pl.DataFrame
    equity_curve: pl.DataFrame
    daily_pnl: pl.DataFrame
    bad_days: pl.DataFrame
    proxy_vs_realistic: pl.DataFrame
    quality_grade: pl.DataFrame
    final_recommendation: str
    paths: dict[str, Path]


def run_cme_wall_realistic_backtest_v1(
    *,
    output_dir: str | Path = "outputs",
    write_outputs: bool = True,
) -> CmeWallRealisticBacktestV1Result:
    """Run realistic CME wall entry/exit backtest v1."""

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "charts").mkdir(parents=True, exist_ok=True)
    paths = _output_paths(output_root)
    inputs = _load_inputs(output_root)
    definitions = build_realistic_strategy_definitions()
    trade_events = build_realistic_trade_events(inputs=inputs)
    performance = build_realistic_performance_summary(trade_events=trade_events)
    equity = build_realistic_equity_curve(trade_events=trade_events)
    daily_pnl, bad_days = build_realistic_daily_pnl(trade_events=trade_events)
    proxy_vs_realistic = build_proxy_vs_realistic_comparison(
        trade_events=trade_events,
        performance_summary=performance,
        inputs=inputs,
    )
    quality = build_realistic_quality_grade(performance_summary=performance)
    final = choose_final_recommendation(quality_grade=quality, trade_events=trade_events)
    result = CmeWallRealisticBacktestV1Result(
        definitions=definitions,
        trade_events=trade_events,
        performance_summary=performance,
        equity_curve=equity,
        daily_pnl=daily_pnl,
        bad_days=bad_days,
        proxy_vs_realistic=proxy_vs_realistic,
        quality_grade=quality,
        final_recommendation=final,
        paths=paths,
    )
    if write_outputs:
        write_cme_wall_realistic_backtest_v1_outputs(result)
    return result


def build_realistic_strategy_definitions() -> pl.DataFrame:
    """Define only confirmation-based research candidates."""

    rows = [
        {
            "strategy_name": "WALL_REJECTION_CONFIRMED_FADE",
            "entry_rule": "Enter after wall touch and close back inside; entry uses the next candle open.",
            "confirmation_required": "REJECTION_CONFIRMED",
            "target_rule": "Fixed midpoint/half-block/grid reference away from the wall.",
            "stop_rule": "Fixed half-block beyond the rejected wall.",
            "uses_direct_wall_touch": False,
            "uses_future_known_outcome": False,
            "allowed_label": "ALLOW_RESEARCH_CANDIDATE",
            "notes": "No entry is created without a rejection candle.",
        },
        {
            "strategy_name": "WALL_ACCEPTANCE_CONTINUATION",
            "entry_rule": "Enter after close beyond wall and one hold candle; entry uses the next candle open.",
            "confirmation_required": "ACCEPTANCE_CONFIRMED",
            "target_rule": "Fixed next wall from the snapshot map, or next full-block reference.",
            "stop_rule": "Fixed failed-acceptance close back inside the wall.",
            "uses_direct_wall_touch": False,
            "uses_future_known_outcome": False,
            "allowed_label": "ALLOW_RESEARCH_CANDIDATE",
            "notes": "No entry is created on first touch.",
        },
        {
            "strategy_name": "AVOID_DIRECT_WALL_TRADE_FILTER",
            "entry_rule": "Filter-only row when a wall is nearby without confirmation.",
            "confirmation_required": "FILTER_ONLY",
            "target_rule": "No target; no standalone trade.",
            "stop_rule": "No stop; filter-only.",
            "uses_direct_wall_touch": False,
            "uses_future_known_outcome": False,
            "allowed_label": "BLOCK",
            "notes": "Records context only and never receives fake PnL.",
        },
        {
            "strategy_name": "SD_2_REJECTION_CONFIRMED_FADE",
            "entry_rule": "Enter after 2SD touch and close back inside; entry uses next candle open.",
            "confirmation_required": "SD_REJECTION_CONFIRMED",
            "target_rule": "Fixed half-block/grid reference away from the SD boundary.",
            "stop_rule": "Fixed 3.5SD reference when available, otherwise half-block.",
            "uses_direct_wall_touch": False,
            "uses_future_known_outcome": False,
            "allowed_label": "ALLOW_RESEARCH_CANDIDATE",
            "notes": "Uses realized-vol proxy until timestamp-safe CME IV is available.",
        },
        {
            "strategy_name": "COMBINED_CONSERVATIVE_REALISTIC",
            "entry_rule": "Confirmed wall reaction plus context, cost, and data-quality checks.",
            "confirmation_required": "REJECTION_CONFIRMED_OR_ACCEPTANCE_CONFIRMED",
            "target_rule": "Same fixed target as the underlying confirmed wall reaction.",
            "stop_rule": "Same fixed stop as the underlying confirmed wall reaction.",
            "uses_direct_wall_touch": False,
            "uses_future_known_outcome": False,
            "allowed_label": "ALLOW_RESEARCH_CANDIDATE",
            "notes": "One combined row at most per wall/session; no blind SD/grid/wall entries.",
        },
    ]
    return _frame(rows, _definition_schema())


def build_realistic_trade_events(*, inputs: dict[str, pl.DataFrame]) -> pl.DataFrame:
    """Build one event row per independent setup and validated strategy."""

    price = _price_series(inputs)
    if not price:
        return _frame([], _trade_event_schema())
    rankings = _frame_input(inputs, "rankings")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    rows.extend(_wall_trade_rows(rankings=rankings, price=price, seen=seen))
    rows.extend(_sd_2_trade_rows(inputs=inputs, price=price, seen=seen))
    return _frame([_safe_row(row) for row in rows], _trade_event_schema())


def build_realistic_performance_summary(*, trade_events: pl.DataFrame) -> pl.DataFrame:
    """Compute TradingView-style metrics for realistic active trades."""

    rows = []
    for strategy in STRATEGY_NAMES:
        strategy_rows = _active_strategy_rows(trade_events, strategy)
        rows.append(_performance_row(strategy, strategy_rows))
    return _frame([_safe_row(row) for row in rows], _performance_schema())


def build_realistic_equity_curve(*, trade_events: pl.DataFrame) -> pl.DataFrame:
    """Build cumulative PnL and drawdown by active event."""

    rows: list[dict[str, Any]] = []
    if trade_events.is_empty():
        return _frame(rows, _equity_schema())
    active = [
        row
        for row in trade_events.to_dicts()
        if _text(row.get("direction")) in {"LONG", "SHORT"}
    ]
    active.sort(key=lambda row: (_text(row.get("exit_timestamp")), _text(row.get("event_id"))))
    cumulative_by_strategy: dict[str, float] = {}
    peak_by_strategy: dict[str, float] = {}
    for row in active:
        strategy = _text(row.get("strategy_name"))
        pnl = _float(row.get("net_pnl_points")) or 0.0
        cumulative = cumulative_by_strategy.get(strategy, 0.0) + pnl
        peak = max(peak_by_strategy.get(strategy, 0.0), cumulative)
        drawdown = cumulative - peak
        cumulative_by_strategy[strategy] = cumulative
        peak_by_strategy[strategy] = peak
        rows.append(
            {
                "timestamp": _text(row.get("exit_timestamp")),
                "strategy_name": strategy,
                "cumulative_pnl": cumulative,
                "drawdown": drawdown,
                "equity_curve_value": cumulative,
                "event_id": _text(row.get("event_id")),
            }
        )
    return _frame([_safe_row(row) for row in rows], _equity_schema())


def build_realistic_daily_pnl(*, trade_events: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Build daily PnL and bad-day diagnostics."""

    if trade_events.is_empty():
        return _frame([], _daily_pnl_schema()), _frame([], _bad_day_schema())
    active = [
        row
        for row in trade_events.to_dicts()
        if _text(row.get("direction")) in {"LONG", "SHORT"}
    ]
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in active:
        key = (_text(row.get("trade_date")), _text(row.get("strategy_name")))
        grouped.setdefault(key, []).append(row)
    daily_rows: list[dict[str, Any]] = []
    bad_rows: list[dict[str, Any]] = []
    for (trade_date, strategy), group in sorted(grouped.items()):
        gross = sum(_float(row.get("gross_pnl_points")) or 0.0 for row in group)
        net = sum(_float(row.get("net_pnl_points")) or 0.0 for row in group)
        fees = sum(
            (_float(row.get("spread_cost_points")) or 0.0)
            + (_float(row.get("slippage_points")) or 0.0)
            for row in group
        )
        drawdown = min(0.0, _max_drawdown([_float(row.get("net_pnl_points")) or 0.0 for row in group]))
        bad_day = net < 0.0
        reason = _bad_day_reason(group, net)
        daily_row = {
            "trade_date": trade_date,
            "strategy_name": strategy,
            "trades": len(group),
            "daily_gross_pnl": gross,
            "daily_net_pnl": net,
            "fees": fees,
            "max_intraday_drawdown": drawdown,
            "bad_day": bad_day,
            "bad_day_reason": reason if bad_day else "",
        }
        daily_rows.append(daily_row)
        if bad_day:
            bad_rows.append(daily_row)
    return (
        _frame([_safe_row(row) for row in daily_rows], _daily_pnl_schema()),
        _frame([_safe_row(row) for row in bad_rows], _bad_day_schema()),
    )


def build_proxy_vs_realistic_comparison(
    *,
    trade_events: pl.DataFrame,
    performance_summary: pl.DataFrame,
    inputs: dict[str, pl.DataFrame],
) -> pl.DataFrame:
    """Compare invalid proxy rows with realistic event counts."""

    proxy = _frame_input(inputs, "independent_event_performance")
    realism = _frame_input(inputs, "trade_realism_audit")
    perf_by_strategy = {
        _text(row.get("strategy_name")): row for row in performance_summary.to_dicts()
    }
    proxy_by_strategy = {_text(row.get("strategy_name")): row for row in proxy.to_dicts()} if not proxy.is_empty() else {}
    audit_by_strategy = {_text(row.get("strategy_name")): row for row in realism.to_dicts()} if not realism.is_empty() else {}
    rows: list[dict[str, Any]] = []
    mappings = [
        ("WALL_MAGNET_TO_NEAREST_WALL", "EXCLUDED_DIRECT_WALL_MAGNET"),
        ("WALL_REJECTION_FADE", "WALL_REJECTION_CONFIRMED_FADE"),
        ("WALL_ACCEPTANCE_CONTINUATION", "WALL_ACCEPTANCE_CONTINUATION"),
        ("AVOID_DIRECT_WALL_TRADE", "AVOID_DIRECT_WALL_TRADE_FILTER"),
        ("SD_GRID_REJECTION_2SD", "SD_2_REJECTION_CONFIRMED_FADE"),
        ("COMBINED_CONSERVATIVE", "COMBINED_CONSERVATIVE_REALISTIC"),
    ]
    for proxy_name, realistic_name in mappings:
        perf = perf_by_strategy.get(realistic_name, {})
        proxy_row = proxy_by_strategy.get(proxy_name, {})
        audit_row = audit_by_strategy.get(proxy_name, {})
        proxy_rows = _int(audit_row.get("trade_count"))
        if proxy_rows <= 0:
            proxy_rows = _int(proxy_row.get("independent_event_count"))
        realistic_count = _int(perf.get("realistic_trade_count"))
        overcount_ratio = proxy_rows / realistic_count if realistic_count > 0 else None
        rows.append(
            {
                "proxy_strategy_name": proxy_name,
                "realistic_strategy_name": realistic_name,
                "previous_proxy_pnl": _float(proxy_row.get("net_pnl_proxy")),
                "realistic_pnl": _float(perf.get("net_profit_points")),
                "proxy_row_count": proxy_rows,
                "realistic_trade_count": realistic_count,
                "overcount_ratio": overcount_ratio,
                "explanation": _proxy_comparison_explanation(proxy_name, realistic_name, overcount_ratio),
            }
        )
    return _frame([_safe_row(row) for row in rows], _proxy_comparison_schema())


def build_realistic_quality_grade(*, performance_summary: pl.DataFrame) -> pl.DataFrame:
    """Grade realistic strategy candidates conservatively."""

    rows: list[dict[str, Any]] = []
    for row in performance_summary.to_dicts():
        strategy = _text(row.get("strategy_name"))
        trades = _int(row.get("total_trades"))
        losses = _int(row.get("losing_trades"))
        net = _float(row.get("net_profit_points")) or 0.0
        if strategy == "AVOID_DIRECT_WALL_TRADE_FILTER":
            label = "FILTER_CANDIDATE_ONLY"
            reason = "Filter-only strategy does not create standalone PnL rows."
        elif trades == 0:
            label = "NEED_MORE_CME_DAYS"
            reason = "No confirmed realistic entries were available in the current sample."
        elif trades < MIN_SAMPLE_FOR_READY:
            label = "REALISTIC_BUT_SMALL_SAMPLE"
            reason = "Entry/exit logic is realistic, but the sample is too small for validation."
        elif losses == 0:
            label = "REALISTIC_BUT_SMALL_SAMPLE"
            reason = "No losing rows appeared; this is not proof and needs more days."
        elif net <= 0:
            label = "WEAK_OR_NEGATIVE"
            reason = "Realistic net proxy is weak or negative after costs."
        else:
            label = "REALISTIC_BUT_SMALL_SAMPLE"
            reason = "Positive-looking proxy remains research-only until larger CME coverage exists."
        rows.append(
            {
                "strategy_name": strategy,
                "quality_label": label,
                "realistic_trade_count": trades,
                "net_profit_points": net,
                "max_drawdown_points": _float(row.get("max_drawdown_points")) or 0.0,
                "profit_factor": _float(row.get("profit_factor")),
                "reason": reason,
                "final_recommendation": _grade_recommendation(label),
            }
        )
    return _frame([_safe_row(row) for row in rows], _quality_schema())


def choose_final_recommendation(
    *,
    quality_grade: pl.DataFrame,
    trade_events: pl.DataFrame,
) -> str:
    """Choose a conservative overall recommendation."""

    active_count = _realistic_trade_count(trade_events)
    if active_count == 0:
        return "NEED_MORE_CME_DAYS"
    if quality_grade.is_empty():
        return "NEED_MORE_CME_DAYS"
    labels = {_text(value) for value in quality_grade.get_column("quality_label").to_list()}
    if "WEAK_OR_NEGATIVE" in labels:
        return "NOT_READY_FOR_MONEY"
    if active_count < MIN_SAMPLE_FOR_READY or "REALISTIC_BUT_SMALL_SAMPLE" in labels:
        return "REALISTIC_BUT_SMALL_SAMPLE"
    if labels == {"FILTER_CANDIDATE_ONLY"}:
        return "FILTER_CANDIDATE_ONLY"
    return "REALISTIC_BACKTEST_READY"


def write_cme_wall_realistic_backtest_v1_outputs(
    result: CmeWallRealisticBacktestV1Result,
) -> None:
    """Write CSV, Markdown, and SVG outputs."""

    result.definitions.write_csv(result.paths["definitions_csv"])
    result.trade_events.write_csv(result.paths["trade_events_csv"])
    result.performance_summary.write_csv(result.paths["performance_summary_csv"])
    result.equity_curve.write_csv(result.paths["equity_curve_csv"])
    result.daily_pnl.write_csv(result.paths["daily_pnl_csv"])
    result.bad_days.write_csv(result.paths["bad_days_csv"])
    result.proxy_vs_realistic.write_csv(result.paths["proxy_vs_realistic_csv"])
    result.quality_grade.write_csv(result.paths["quality_grade_csv"])
    _write_md(
        result.paths["definitions_md"],
        "CME Wall Realistic Strategy Definitions",
        result.definitions,
    )
    _write_md(
        result.paths["trade_events_md"],
        "CME Wall Realistic Trade Events",
        result.trade_events.head(80),
        intro=RESEARCH_WARNING,
    )
    _write_md(
        result.paths["performance_report_md"],
        "CME Wall Realistic Performance Summary",
        result.performance_summary,
        intro=f"Final recommendation: `{result.final_recommendation}`.",
    )
    _write_md(
        result.paths["equity_curve_md"],
        "CME Wall Realistic Equity Curve",
        result.equity_curve.tail(80),
    )
    _write_md(
        result.paths["daily_pnl_md"],
        "CME Wall Realistic Daily PnL",
        result.daily_pnl.tail(80),
    )
    _write_md(
        result.paths["bad_days_md"],
        "CME Wall Realistic Bad Days",
        result.bad_days.tail(80),
    )
    _write_md(
        result.paths["proxy_vs_realistic_md"],
        "CME Wall Proxy Vs Realistic Comparison",
        result.proxy_vs_realistic,
    )
    _write_md(
        result.paths["quality_grade_md"],
        "CME Wall Realistic Quality Grade",
        result.quality_grade,
    )
    _write_equity_svg(result.equity_curve, result.paths["equity_curve_svg"])


def cme_wall_realistic_backtest_v1_report_lines(
    result: CmeWallRealisticBacktestV1Result | None,
) -> list[str]:
    """Return research_report.md lines for the realistic backtest."""

    if result is None:
        return ["## Realistic CME Wall Entry/Exit Backtest v1", "", "Realistic backtest was not run."]
    active_count = _realistic_trade_count(result.trade_events)
    return [
        "## Realistic CME Wall Entry/Exit Backtest v1",
        "",
        RESEARCH_WARNING,
        "",
        f"- Final recommendation: `{result.final_recommendation}`",
        f"- Realistic active trade count: {active_count}",
        f"- Event rows including filter-only context: {result.trade_events.height}",
        "",
        "## Realistic Trade Events",
        "",
        _frame_markdown(result.trade_events.head(40)),
        "",
        "## Realistic Performance Summary",
        "",
        _frame_markdown(result.performance_summary),
        "",
        "## Equity Curve",
        "",
        _frame_markdown(result.equity_curve.tail(40)),
        "",
        "## Daily PnL",
        "",
        _frame_markdown(result.daily_pnl.tail(40)),
        "",
        "## Proxy vs Realistic Comparison",
        "",
        _frame_markdown(result.proxy_vs_realistic),
        "",
        "## Quality Grade",
        "",
        _frame_markdown(result.quality_grade),
        "",
        "- Links: `outputs/cme_wall_realistic_trade_events.csv`, "
        "`outputs/cme_wall_realistic_performance_summary.csv`, "
        "`outputs/cme_wall_proxy_vs_realistic_comparison.csv`, "
        "`outputs/cme_wall_realistic_quality_grade.csv`.",
    ]


def report_text_is_safe(text: str) -> bool:
    """Return true when text avoids restricted phrases and private paths."""

    safe = _safe_report_text(text)
    return not any(
        re.search(pattern, safe, flags=re.IGNORECASE)
        for pattern in (
            r"\bbuy\b",
            r"\bsell\b",
            r"profitable",
            r"profitability",
            r"guaranteed edge",
            r"predicts price",
            r"safe to trade",
            r"live[- ]ready",
            r"paper[- ]ready",
        )
    ) and not re.search(r"[A-Za-z]:\\Users\\|/Users/|/home/|/tmp/", safe)


def _wall_trade_rows(
    *,
    rankings: pl.DataFrame,
    price: list[PriceCandle],
    seen: set[str],
) -> list[dict[str, Any]]:
    if rankings.is_empty():
        return []
    rows: list[dict[str, Any]] = []
    ranking_rows = _context_ranking_rows(rankings)
    snapshot_levels = _snapshot_levels(ranking_rows)
    timestamps = [candle.timestamp for candle in price]
    spread_cost = _spread_cost_from_price(price)
    seq = 1
    for wall in ranking_rows:
        setup_dt = _parse_datetime(wall.get("snapshot_timestamp"))
        wall_level = _float(wall.get("strike")) or _float(wall.get("wall_level"))
        if setup_dt is None or wall_level is None:
            continue
        setup_price = _price_at_or_before(price, timestamps, setup_dt)
        if setup_price is None:
            setup_price = _float(wall.get("future_price"))
        side = _wall_side(wall, setup_price, wall_level)
        if side == "AT_PRICE" or setup_price is None:
            continue
        if _is_direct_wall_filter_context(wall):
            filter_row = _filter_only_row(
                wall=wall,
                setup_dt=setup_dt,
                setup_price=setup_price,
                wall_level=wall_level,
                seq=seq,
            )
            seq += 1
            key = _event_key(filter_row)
            if key not in seen:
                seen.add(key)
                rows.append(filter_row)
        rejection = _confirmed_wall_rejection_trade(
            wall=wall,
            price=price,
            timestamps=timestamps,
            setup_dt=setup_dt,
            setup_price=setup_price,
            wall_level=wall_level,
            side=side,
            seq=seq,
            spread_cost=spread_cost,
        )
        if rejection:
            seq += 1
            key = _event_key(rejection)
            if key not in seen:
                seen.add(key)
                rows.append(rejection)
        acceptance = _confirmed_wall_acceptance_trade(
            wall=wall,
            price=price,
            timestamps=timestamps,
            setup_dt=setup_dt,
            setup_price=setup_price,
            wall_level=wall_level,
            side=side,
            snapshot_levels=snapshot_levels,
            seq=seq,
            spread_cost=spread_cost,
        )
        if acceptance:
            seq += 1
            key = _event_key(acceptance)
            if key not in seen:
                seen.add(key)
                rows.append(acceptance)
        combined_source = _combined_source_trade(rejection, acceptance)
        if combined_source and _combined_context_pass(wall, spread_cost):
            combined = dict(combined_source)
            combined["event_id"] = f"CME_REAL_{seq:09d}"
            combined["strategy_name"] = "COMBINED_CONSERVATIVE_REALISTIC"
            combined["sample_warning"] = True
            seq += 1
            key = _event_key(combined)
            if key not in seen:
                seen.add(key)
                rows.append(combined)
    return rows


def _sd_2_trade_rows(
    *,
    inputs: dict[str, pl.DataFrame],
    price: list[PriceCandle],
    seen: set[str],
) -> list[dict[str, Any]]:
    events = _frame_input(inputs, "sd_grid_events")
    if events.is_empty() or "event_type" not in events.columns:
        return []
    timestamps = [candle.timestamp for candle in price]
    spread_cost = _spread_cost_from_price(price)
    rows: list[dict[str, Any]] = []
    filtered = events.filter(
        (pl.col("event_type") == "REJECTION_BACK_INSIDE")
        & (pl.col("level_type") == "2SD")
    )
    seq = 1
    for event in filtered.to_dicts():
        setup_dt = _parse_datetime(event.get("timestamp"))
        if setup_dt is None:
            continue
        side = _text(event.get("side"))
        if side not in {"UPPER", "LOWER"}:
            continue
        entry_index = _next_candle_index(timestamps, setup_dt)
        if entry_index is None:
            continue
        entry = price[entry_index]
        direction = "SHORT" if side == "UPPER" else "LONG"
        target = _grid_target(entry.open, direction, HALF_BLOCK)
        one_sd = abs(_float(event.get("one_sd_value")) or 0.0)
        session_open = _float(event.get("session_open")) or entry.open
        if one_sd > 0:
            stop = session_open + (3.5 * one_sd) if direction == "SHORT" else session_open - (3.5 * one_sd)
        else:
            stop = _wall_stop(entry.open, direction, HALF_BLOCK)
        path = evaluate_after_entry_path(
            price=price,
            timestamps=timestamps,
            entry_index=entry_index,
            direction=direction,
            entry_price=entry.open,
            target_price=target,
            stop_price=stop,
            max_exit_time=entry.timestamp + EXIT_WINDOW,
            stop_mode="level",
        )
        if path is None:
            continue
        row = _trade_row(
            event_id=f"SD2_REAL_{seq:09d}",
            strategy_name="SD_2_REJECTION_CONFIRMED_FADE",
            trade_date=_date_text(entry.timestamp),
            setup_timestamp=setup_dt.isoformat(),
            entry_timestamp=entry.timestamp.isoformat(),
            exit_timestamp=path.exit_timestamp,
            direction=direction,
            entry_price=entry.open,
            target_price=target,
            stop_price=stop,
            exit_price=path.exit_price,
            wall_level=_float(event.get("trigger_price")),
            wall_type="SD_2_REALIZED_VOL_PROXY",
            entry_confirmation="SD_REJECTION_CONFIRMED",
            exit_reason=path.exit_reason,
            gross_pnl_points=path.gross_pnl_points,
            spread_cost_points=spread_cost,
            slippage_points=0.25,
            mfe=path.mfe,
            mae=path.mae,
            bars_held=path.bars_held,
            data_quality=REALIZED_VOL_PROXY,
            sample_warning=True,
        )
        key = _event_key(row)
        if key not in seen:
            seen.add(key)
            rows.append(row)
            seq += 1
    return rows


def _confirmed_wall_rejection_trade(
    *,
    wall: dict[str, Any],
    price: list[PriceCandle],
    timestamps: list[datetime],
    setup_dt: datetime,
    setup_price: float,
    wall_level: float,
    side: str,
    seq: int,
    spread_cost: float,
) -> dict[str, Any] | None:
    direction = "SHORT" if side == "ABOVE" else "LONG"
    end_dt = setup_dt + ENTRY_WINDOW
    start_index = bisect.bisect_right(timestamps, setup_dt)
    end_index = bisect.bisect_right(timestamps, end_dt)
    for index in range(start_index, max(start_index, end_index)):
        candle = price[index]
        if not _touches_level(candle, wall_level):
            continue
        closes_back_inside = candle.close < wall_level if side == "ABOVE" else candle.close > wall_level
        if not closes_back_inside:
            continue
        entry_index = index + 1
        if entry_index >= len(price):
            return None
        entry = price[entry_index]
        target = _grid_target(entry.open, direction, HALF_BLOCK)
        stop = wall_level + HALF_BLOCK if direction == "SHORT" else wall_level - HALF_BLOCK
        path = evaluate_after_entry_path(
            price=price,
            timestamps=timestamps,
            entry_index=entry_index,
            direction=direction,
            entry_price=entry.open,
            target_price=target,
            stop_price=stop,
            max_exit_time=entry.timestamp + EXIT_WINDOW,
            stop_mode="level",
        )
        if path is None:
            return None
        return _trade_row(
            event_id=f"CME_REAL_{seq:09d}",
            strategy_name="WALL_REJECTION_CONFIRMED_FADE",
            trade_date=_date_text(entry.timestamp),
            setup_timestamp=setup_dt.isoformat(),
            entry_timestamp=entry.timestamp.isoformat(),
            exit_timestamp=path.exit_timestamp,
            direction=direction,
            entry_price=entry.open,
            target_price=target,
            stop_price=stop,
            exit_price=path.exit_price,
            wall_level=wall_level,
            wall_type=_text(wall.get("wall_type")),
            entry_confirmation="REJECTION_CONFIRMED",
            exit_reason=path.exit_reason,
            gross_pnl_points=path.gross_pnl_points,
            spread_cost_points=spread_cost,
            slippage_points=0.25,
            mfe=path.mfe,
            mae=path.mae,
            bars_held=path.bars_held,
            data_quality=MID_PRICE_PROXY,
            sample_warning=True,
        )
    return None


def _confirmed_wall_acceptance_trade(
    *,
    wall: dict[str, Any],
    price: list[PriceCandle],
    timestamps: list[datetime],
    setup_dt: datetime,
    setup_price: float,
    wall_level: float,
    side: str,
    snapshot_levels: dict[str, list[float]],
    seq: int,
    spread_cost: float,
) -> dict[str, Any] | None:
    direction = "LONG" if side == "ABOVE" else "SHORT"
    end_dt = setup_dt + ENTRY_WINDOW
    start_index = bisect.bisect_right(timestamps, setup_dt)
    end_index = bisect.bisect_right(timestamps, end_dt)
    for index in range(start_index, max(start_index, end_index - 1)):
        first = price[index]
        second = price[index + 1]
        if side == "ABOVE":
            accepted = first.close > wall_level and second.close > wall_level
        else:
            accepted = first.close < wall_level and second.close < wall_level
        if not accepted:
            continue
        entry_index = index + 2
        if entry_index >= len(price):
            return None
        entry = price[entry_index]
        levels = snapshot_levels.get(_text(wall.get("snapshot_timestamp")), [])
        target = _next_snapshot_wall(levels, wall_level, direction)
        if target is None or not _target_is_beyond_entry(
            target_price=target,
            entry_price=entry.open,
            direction=direction,
        ):
            target = _grid_target(entry.open, direction, FULL_BLOCK)
        stop = wall_level
        path = evaluate_after_entry_path(
            price=price,
            timestamps=timestamps,
            entry_index=entry_index,
            direction=direction,
            entry_price=entry.open,
            target_price=target,
            stop_price=stop,
            max_exit_time=entry.timestamp + EXIT_WINDOW,
            stop_mode="close_inside",
        )
        if path is None:
            return None
        return _trade_row(
            event_id=f"CME_REAL_{seq:09d}",
            strategy_name="WALL_ACCEPTANCE_CONTINUATION",
            trade_date=_date_text(entry.timestamp),
            setup_timestamp=setup_dt.isoformat(),
            entry_timestamp=entry.timestamp.isoformat(),
            exit_timestamp=path.exit_timestamp,
            direction=direction,
            entry_price=entry.open,
            target_price=target,
            stop_price=stop,
            exit_price=path.exit_price,
            wall_level=wall_level,
            wall_type=_text(wall.get("wall_type")),
            entry_confirmation="ACCEPTANCE_CONFIRMED",
            exit_reason=path.exit_reason,
            gross_pnl_points=path.gross_pnl_points,
            spread_cost_points=spread_cost,
            slippage_points=0.25,
            mfe=path.mfe,
            mae=path.mae,
            bars_held=path.bars_held,
            data_quality=MID_PRICE_PROXY,
            sample_warning=True,
        )
    return None


def evaluate_after_entry_path(
    *,
    price: list[PriceCandle],
    timestamps: list[datetime],
    entry_index: int,
    direction: str,
    entry_price: float,
    target_price: float,
    stop_price: float,
    max_exit_time: datetime,
    stop_mode: str,
) -> PathResult | None:
    """Evaluate target/stop using candles after entry only."""

    if entry_index < 0 or entry_index >= len(price):
        return None
    end_index = bisect.bisect_right(timestamps, max_exit_time)
    if end_index <= entry_index:
        end_index = min(len(price), entry_index + 1)
    mfe = 0.0
    mae = 0.0
    last = price[entry_index]
    for bars_held, index in enumerate(range(entry_index, end_index), start=1):
        candle = price[index]
        last = candle
        if direction == "LONG":
            mfe = max(mfe, candle.high - entry_price)
            mae = min(mae, candle.low - entry_price)
            target_hit = candle.high >= target_price
            stop_hit = candle.low <= stop_price if stop_mode == "level" else candle.close <= stop_price
            if target_hit and stop_hit:
                return _path_result(
                    candle=candle,
                    entry_price=entry_price,
                    exit_price=stop_price,
                    direction=direction,
                    reason="STOP_HIT",
                    mfe=mfe,
                    mae=mae,
                    bars_held=bars_held,
                    ambiguous=True,
                )
            if stop_hit:
                return _path_result(
                    candle=candle,
                    entry_price=entry_price,
                    exit_price=stop_price,
                    direction=direction,
                    reason="STOP_HIT" if stop_mode == "level" else "INVALIDATION",
                    mfe=mfe,
                    mae=mae,
                    bars_held=bars_held,
                    ambiguous=False,
                )
            if target_hit:
                return _path_result(
                    candle=candle,
                    entry_price=entry_price,
                    exit_price=target_price,
                    direction=direction,
                    reason="TARGET_HIT",
                    mfe=mfe,
                    mae=mae,
                    bars_held=bars_held,
                    ambiguous=False,
                )
        else:
            mfe = max(mfe, entry_price - candle.low)
            mae = min(mae, entry_price - candle.high)
            target_hit = candle.low <= target_price
            stop_hit = candle.high >= stop_price if stop_mode == "level" else candle.close >= stop_price
            if target_hit and stop_hit:
                return _path_result(
                    candle=candle,
                    entry_price=entry_price,
                    exit_price=stop_price,
                    direction=direction,
                    reason="STOP_HIT",
                    mfe=mfe,
                    mae=mae,
                    bars_held=bars_held,
                    ambiguous=True,
                )
            if stop_hit:
                return _path_result(
                    candle=candle,
                    entry_price=entry_price,
                    exit_price=stop_price,
                    direction=direction,
                    reason="STOP_HIT" if stop_mode == "level" else "INVALIDATION",
                    mfe=mfe,
                    mae=mae,
                    bars_held=bars_held,
                    ambiguous=False,
                )
            if target_hit:
                return _path_result(
                    candle=candle,
                    entry_price=entry_price,
                    exit_price=target_price,
                    direction=direction,
                    reason="TARGET_HIT",
                    mfe=mfe,
                    mae=mae,
                    bars_held=bars_held,
                    ambiguous=False,
                )
    exit_price = last.close
    return _path_result(
        candle=last,
        entry_price=entry_price,
        exit_price=exit_price,
        direction=direction,
        reason="SESSION_CLOSE",
        mfe=mfe,
        mae=mae,
        bars_held=max(1, end_index - entry_index),
        ambiguous=False,
    )


def _path_result(
    *,
    candle: PriceCandle,
    entry_price: float,
    exit_price: float,
    direction: str,
    reason: str,
    mfe: float,
    mae: float,
    bars_held: int,
    ambiguous: bool,
) -> PathResult:
    gross = exit_price - entry_price if direction == "LONG" else entry_price - exit_price
    return PathResult(
        exit_timestamp=candle.timestamp.isoformat(),
        exit_price=exit_price,
        exit_reason=reason,
        gross_pnl_points=gross,
        mfe=mfe,
        mae=mae,
        bars_held=bars_held,
        ambiguous_same_candle=ambiguous,
    )


def _trade_row(
    *,
    event_id: str,
    strategy_name: str,
    trade_date: str,
    setup_timestamp: str,
    entry_timestamp: str,
    exit_timestamp: str,
    direction: str,
    entry_price: float,
    target_price: float | None,
    stop_price: float | None,
    exit_price: float | None,
    wall_level: float | None,
    wall_type: str,
    entry_confirmation: str,
    exit_reason: str,
    gross_pnl_points: float,
    spread_cost_points: float,
    slippage_points: float,
    mfe: float,
    mae: float,
    bars_held: int,
    data_quality: str,
    sample_warning: bool,
) -> dict[str, Any]:
    net = gross_pnl_points - spread_cost_points - slippage_points if direction != "NONE" else 0.0
    return {
        "event_id": event_id,
        "strategy_name": strategy_name,
        "trade_date": trade_date,
        "setup_timestamp": setup_timestamp,
        "entry_timestamp": entry_timestamp,
        "exit_timestamp": exit_timestamp,
        "direction": direction,
        "entry_price": entry_price,
        "target_price": target_price,
        "stop_price": stop_price,
        "exit_price": exit_price,
        "wall_level": wall_level,
        "wall_type": wall_type,
        "entry_confirmation": entry_confirmation,
        "exit_reason": exit_reason,
        "gross_pnl_points": gross_pnl_points,
        "spread_cost_points": spread_cost_points,
        "slippage_points": slippage_points,
        "net_pnl_points": net,
        "mfe": mfe,
        "mae": mae,
        "bars_held": bars_held,
        "data_quality": data_quality,
        "sample_warning": sample_warning,
    }


def _filter_only_row(
    *,
    wall: dict[str, Any],
    setup_dt: datetime,
    setup_price: float,
    wall_level: float,
    seq: int,
) -> dict[str, Any]:
    return _trade_row(
        event_id=f"CME_FILTER_{seq:09d}",
        strategy_name="AVOID_DIRECT_WALL_TRADE_FILTER",
        trade_date=_date_text(setup_dt),
        setup_timestamp=setup_dt.isoformat(),
        entry_timestamp="",
        exit_timestamp="",
        direction="NONE",
        entry_price=setup_price,
        target_price=None,
        stop_price=None,
        exit_price=None,
        wall_level=wall_level,
        wall_type=_text(wall.get("wall_type")),
        entry_confirmation="FILTER_ONLY",
        exit_reason="NO_ENTRY",
        gross_pnl_points=0.0,
        spread_cost_points=0.0,
        slippage_points=0.0,
        mfe=0.0,
        mae=0.0,
        bars_held=0,
        data_quality="FILTER_ONLY_NO_PNL",
        sample_warning=True,
    )


def _performance_row(strategy: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    gross_values = [_float(row.get("gross_pnl_points")) or 0.0 for row in rows]
    net_values = [_float(row.get("net_pnl_points")) or 0.0 for row in rows]
    wins = [value for value in net_values if value > 0]
    losses = [value for value in net_values if value < 0]
    gross_profit = sum(value for value in gross_values if value > 0)
    gross_loss = sum(value for value in gross_values if value < 0)
    net = sum(net_values)
    total = len(net_values)
    profit_factor = gross_profit / abs(gross_loss) if gross_loss < 0 else None
    avg_win = sum(wins) / len(wins) if wins else None
    avg_loss = sum(losses) / len(losses) if losses else None
    max_drawdown = _max_drawdown(net_values)
    return {
        "strategy_name": strategy,
        "total_trades": total,
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "win_rate": len(wins) / total if total else None,
        "net_profit_points": net,
        "gross_profit_points": gross_profit,
        "gross_loss_points": gross_loss,
        "profit_factor": profit_factor,
        "average_trade": net / total if total else None,
        "average_win": avg_win,
        "average_loss": avg_loss,
        "max_drawdown_points": max_drawdown,
        "largest_win": max(wins) if wins else None,
        "largest_loss": min(losses) if losses else None,
        "commission_or_fee_total": 0.0,
        "spread_cost_total": sum(_float(row.get("spread_cost_points")) or 0.0 for row in rows),
        "slippage_total": sum(_float(row.get("slippage_points")) or 0.0 for row in rows),
        "expectancy": net / total if total else None,
        "sample_size_warning": total < MIN_SAMPLE_FOR_READY,
        "realistic_trade_count": total,
    }


def _active_strategy_rows(trade_events: pl.DataFrame, strategy: str) -> list[dict[str, Any]]:
    if trade_events.is_empty() or "strategy_name" not in trade_events.columns:
        return []
    return [
        row
        for row in trade_events.filter(pl.col("strategy_name") == strategy).to_dicts()
        if _text(row.get("direction")) in {"LONG", "SHORT"}
    ]


def _context_ranking_rows(rankings: pl.DataFrame) -> list[dict[str, Any]]:
    if rankings.is_empty():
        return []
    frame = rankings
    if "context_threshold_passed" in frame.columns:
        passed = frame.filter(pl.col("context_threshold_passed").cast(pl.Boolean, strict=False) == True)  # noqa: E712
        if not passed.is_empty():
            frame = passed
    if "snapshot_timestamp" in frame.columns:
        frame = frame.sort(["snapshot_timestamp", "rank_overall"], nulls_last=True)
    return frame.to_dicts()


def _snapshot_levels(rows: list[dict[str, Any]]) -> dict[str, list[float]]:
    result: dict[str, set[float]] = {}
    for row in rows:
        timestamp = _text(row.get("snapshot_timestamp"))
        level = _float(row.get("strike")) or _float(row.get("wall_level"))
        if timestamp and level is not None:
            result.setdefault(timestamp, set()).add(level)
    return {key: sorted(values) for key, values in result.items()}


def _combined_source_trade(
    rejection: dict[str, Any] | None,
    acceptance: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if rejection is None:
        return acceptance
    if acceptance is None:
        return rejection
    return rejection if _text(rejection.get("entry_timestamp")) <= _text(acceptance.get("entry_timestamp")) else acceptance


def _combined_context_pass(row: dict[str, Any], spread_cost: float) -> bool:
    if "context_threshold_passed" in row and not _bool(row.get("context_threshold_passed")):
        return False
    distance = abs(_float(row.get("distance_from_price")) or 0.0)
    return distance >= max(HALF_BLOCK, spread_cost * 3.0)


def _is_direct_wall_filter_context(row: dict[str, Any]) -> bool:
    bucket = _text(row.get("distance_bucket"))
    if bucket == "0_25":
        return True
    distance = abs(_float(row.get("distance_from_price")) or 999999.0)
    return distance <= FULL_BLOCK


def _wall_side(row: dict[str, Any], setup_price: float | None, wall_level: float) -> str:
    side = _text(row.get("side_relative_to_price"))
    if side in {"ABOVE", "BELOW", "AT_PRICE"}:
        return side
    if setup_price is None:
        return "AT_PRICE"
    if wall_level > setup_price:
        return "ABOVE"
    if wall_level < setup_price:
        return "BELOW"
    return "AT_PRICE"


def _touches_level(candle: PriceCandle, level: float) -> bool:
    return candle.low <= level <= candle.high


def _grid_target(entry_price: float, direction: str, grid_size: float) -> float:
    if direction == "LONG":
        target = math.ceil(entry_price / grid_size) * grid_size
        if target <= entry_price:
            target += grid_size
        return target
    target = math.floor(entry_price / grid_size) * grid_size
    if target >= entry_price:
        target -= grid_size
    return target


def _wall_stop(entry_price: float, direction: str, block_size: float) -> float:
    return entry_price - block_size if direction == "LONG" else entry_price + block_size


def _next_snapshot_wall(levels: list[float], wall_level: float, direction: str) -> float | None:
    if direction == "LONG":
        candidates = [level for level in levels if level > wall_level]
        return min(candidates) if candidates else None
    candidates = [level for level in levels if level < wall_level]
    return max(candidates) if candidates else None


def _target_is_beyond_entry(*, target_price: float, entry_price: float, direction: str) -> bool:
    if direction == "LONG":
        return target_price > entry_price
    if direction == "SHORT":
        return target_price < entry_price
    return False


def _price_series(inputs: dict[str, pl.DataFrame]) -> list[PriceCandle]:
    for key in ("price_15m", "price_30m", "price_1h", "price_4h"):
        frame = _normalize_price_frame(_frame_input(inputs, key))
        if not frame.is_empty():
            rows = []
            for row in frame.to_dicts():
                timestamp = _parse_datetime(row.get("timestamp"))
                open_ = _float(row.get("open"))
                high = _float(row.get("high"))
                low = _float(row.get("low"))
                close = _float(row.get("close"))
                if timestamp and open_ is not None and high is not None and low is not None and close is not None:
                    rows.append(
                        PriceCandle(
                            timestamp=timestamp,
                            open=open_,
                            high=high,
                            low=low,
                            close=close,
                            spread=_float(row.get("spread_points")) or _float(row.get("spread_close")) or 0.5,
                        )
                    )
            return sorted(rows, key=lambda candle: candle.timestamp)
    return []


def _normalize_price_frame(frame: pl.DataFrame) -> pl.DataFrame:
    if frame.is_empty():
        return frame
    rename: dict[str, str] = {}
    if "time" in frame.columns and "timestamp" not in frame.columns:
        rename["time"] = "timestamp"
    if rename:
        frame = frame.rename(rename)
    for target, candidates in {
        "open": ("mid_open", "bid_open", "ask_open"),
        "high": ("mid_high", "bid_high", "ask_high"),
        "low": ("mid_low", "bid_low", "ask_low"),
        "close": ("mid_close", "bid_close", "ask_close"),
    }.items():
        if target not in frame.columns:
            for candidate in candidates:
                if candidate in frame.columns:
                    frame = frame.with_columns(pl.col(candidate).alias(target))
                    break
    required = {"timestamp", "open", "high", "low", "close"}
    if not required.issubset(set(frame.columns)):
        return pl.DataFrame()
    return (
        frame.with_columns(
            pl.col("timestamp").cast(pl.Datetime(time_zone="UTC"), strict=False),
            pl.col("open").cast(pl.Float64, strict=False),
            pl.col("high").cast(pl.Float64, strict=False),
            pl.col("low").cast(pl.Float64, strict=False),
            pl.col("close").cast(pl.Float64, strict=False),
        )
        .drop_nulls(["timestamp", "open", "high", "low", "close"])
        .sort("timestamp")
    )


def _price_at_or_before(
    price: list[PriceCandle],
    timestamps: list[datetime],
    timestamp: datetime,
) -> float | None:
    index = bisect.bisect_right(timestamps, timestamp) - 1
    if index < 0 or index >= len(price):
        return None
    return price[index].close


def _next_candle_index(timestamps: list[datetime], timestamp: datetime) -> int | None:
    index = bisect.bisect_right(timestamps, timestamp)
    return index if index < len(timestamps) else None


def _spread_cost_from_price(price: list[PriceCandle]) -> float:
    spreads = [candle.spread for candle in price if candle.spread and candle.spread > 0]
    if not spreads:
        return 0.5
    return sorted(spreads)[len(spreads) // 2]


def _max_drawdown(values: list[float]) -> float:
    cumulative = 0.0
    peak = 0.0
    max_dd = 0.0
    for value in values:
        cumulative += value
        peak = max(peak, cumulative)
        max_dd = min(max_dd, cumulative - peak)
    return max_dd


def _realistic_trade_count(trade_events: pl.DataFrame) -> int:
    if trade_events.is_empty() or "direction" not in trade_events.columns:
        return 0
    return trade_events.filter(pl.col("direction").is_in(["LONG", "SHORT"])).height


def _bad_day_reason(group: list[dict[str, Any]], net: float) -> str:
    if net >= 0:
        return ""
    if any(_text(row.get("exit_reason")) in {"STOP_HIT", "INVALIDATION"} for row in group):
        return "wall_failed"
    if sum((_float(row.get("spread_cost_points")) or 0.0) for row in group) > abs(net):
        return "fee_drag"
    return "false_breakout"


def _proxy_comparison_explanation(proxy_name: str, realistic_name: str, ratio: float | None) -> str:
    if realistic_name == "EXCLUDED_DIRECT_WALL_MAGNET":
        return "Direct wall-magnet trade is excluded in v1 because entry would need to be preselected before touch."
    if ratio is None:
        return "Proxy rows did not map to confirmed realistic entries in this sample."
    if ratio > 3:
        return "Proxy report likely overcounted outcome windows compared with one-entry realistic events."
    return "Realistic replay materially reduces proxy row count."


def _grade_recommendation(label: str) -> str:
    return {
        "REALISTIC_BACKTEST_READY": "REALISTIC_BACKTEST_READY",
        "REALISTIC_BUT_SMALL_SAMPLE": "REALISTIC_BUT_SMALL_SAMPLE",
        "FILTER_CANDIDATE_ONLY": "FILTER_CANDIDATE_ONLY",
        "WEAK_OR_NEGATIVE": "NOT_READY_FOR_MONEY",
        "NEED_MORE_CME_DAYS": "NEED_MORE_CME_DAYS",
        "NOT_READY_FOR_MONEY": "NOT_READY_FOR_MONEY",
    }.get(label, "NEED_MORE_CME_DAYS")


def _event_key(row: dict[str, Any]) -> str:
    return "|".join(
        [
            _text(row.get("strategy_name")),
            _text(row.get("setup_timestamp")),
            _level_text(row.get("wall_level")),
            _text(row.get("wall_type")),
            _market_session(row.get("setup_timestamp"), row.get("trade_date")),
        ]
    )


def _market_session(timestamp: Any, trade_date: Any = "") -> str:
    parsed = _parse_datetime(timestamp)
    date_text = _date_text(timestamp) or _text(trade_date)
    if not date_text:
        return "UNKNOWN"
    if parsed is None:
        return f"{date_text}:UNKNOWN"
    if parsed.hour < 8:
        bucket = "ASIA"
    elif parsed.hour < 16:
        bucket = "EUROPE_US"
    else:
        bucket = "LATE_US"
    return f"{date_text}:{bucket}"


def _load_inputs(output_root: Path) -> dict[str, pl.DataFrame]:
    return {
        "rankings": _read_optional(output_root / "fetched_cme_wall_rankings.csv"),
        "daily_state": _read_optional(output_root / "fetched_cme_daily_wall_state.csv"),
        "outcome_journal": _read_optional(output_root / "fetched_cme_wall_outcome_journal.csv"),
        "role_summary": _read_optional(output_root / "fetched_cme_wall_role_summary.csv"),
        "rewrite_plan": _read_optional(output_root / "cme_wall_strategy_entry_exit_rewrite_plan.csv"),
        "independent_event_performance": _read_optional(
            output_root / "cme_wall_strategy_independent_event_performance.csv",
        ),
        "trade_realism_audit": _read_optional(output_root / "cme_wall_strategy_trade_realism_audit.csv"),
        "price_15m": _read_optional(output_root / "dukascopy_xau_15m.parquet"),
        "price_30m": _read_optional(output_root / "dukascopy_xau_30m.parquet"),
        "price_1h": _read_optional(output_root / "dukascopy_xau_1h.parquet"),
        "price_4h": _read_optional(output_root / "dukascopy_xau_4h.parquet"),
        "latest_ranked_state": _read_optional(
            output_root / "xau_indicator_latest_state_with_ranked_cme_walls.csv",
        ),
        "sd_decision": _read_optional(output_root / "sd_grid_confirmation_decision_summary.csv"),
        "sd_entry_comparison": _read_optional(output_root / "gemini_sd_grid_entry_model_comparison.csv"),
        "tp_sl_comparison": _read_optional(output_root / "gemini_tp_sl_model_comparison.csv"),
        "sd_grid_events": _read_optional(output_root / "gemini_sd_grid_events.csv"),
    }


def _read_optional(path: Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    try:
        if path.suffix.lower() == ".parquet":
            return pl.read_parquet(path)
        return pl.read_csv(path, infer_schema_length=1000)
    except Exception:
        return pl.DataFrame()


def _frame_input(inputs: dict[str, pl.DataFrame], key: str) -> pl.DataFrame:
    return inputs.get(key, pl.DataFrame())


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = _text(value)
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _date_text(value: Any) -> str:
    parsed = _parse_datetime(value)
    if parsed is not None:
        return parsed.date().isoformat()
    text = _text(value)
    return text[:10] if len(text) >= 10 else ""


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value).strip()


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(result) else result


def _int(value: Any) -> int:
    number = _float(value)
    return int(number) if number is not None else 0


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"true", "1", "yes", "y"}


def _level_text(value: Any) -> str:
    number = _float(value)
    return f"{number:.2f}" if number is not None else ""


def _safe_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: _safe_text(value) if isinstance(value, str) else value for key, value in row.items()}


def _safe_report_text(text: str) -> str:
    return _safe_text(text)


def _safe_text(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"[A-Za-z]:\\Users\\[^\s|)<>\"']+", "<REDACTED_PATH>", text)
    text = re.sub(r"[A-Za-z]:\\[^\s|)<>\"']+", "<REDACTED_PATH>", text)
    text = re.sub(r"/(?:Users|home|mnt|var|tmp)/[^\s|)<>\"']+", "<REDACTED_PATH>", text)
    text = re.sub(r"\bbuy\b", "hold", text, flags=re.IGNORECASE)
    text = re.sub(r"\bsell\b", "exit", text, flags=re.IGNORECASE)
    text = re.sub(r"profitable|profitability", "money-result", text, flags=re.IGNORECASE)
    text = re.sub(
        r"predicts price|guaranteed edge|safe to trade",
        "blocked phrase",
        text,
        flags=re.IGNORECASE,
    )
    return text.strip()


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


def _write_md(path: Path, title: str, frame: pl.DataFrame, intro: str = "") -> None:
    lines = [f"# {_safe_text(title)}", ""]
    if intro:
        lines.extend([_safe_text(intro), ""])
    lines.append(_frame_markdown(frame))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _frame_markdown(frame: pl.DataFrame) -> str:
    if frame.is_empty():
        return "_No rows._"
    columns = frame.columns
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in frame.to_dicts():
        lines.append("| " + " | ".join(_markdown_cell(row.get(column)) for column in columns) + " |")
    return "\n".join(lines)


def _markdown_cell(value: Any) -> str:
    if isinstance(value, float):
        if math.isnan(value):
            return ""
        return f"{value:.6g}"
    return _safe_text(value).replace("|", "\\|").replace("\n", " ")[:700]


def _write_equity_svg(equity: pl.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if equity.is_empty():
        path.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="240">'
            '<text x="24" y="120">No realistic equity rows.</text></svg>',
            encoding="utf-8",
        )
        return
    rows = equity.to_dicts()
    values = [_float(row.get("cumulative_pnl")) or 0.0 for row in rows]
    if not values:
        return
    min_value = min(values)
    max_value = max(values)
    span = max(max_value - min_value, 1.0)
    width = 720
    height = 260
    points = []
    for index, value in enumerate(values):
        x = 30 + (index / max(len(values) - 1, 1)) * (width - 60)
        y = height - 30 - ((value - min_value) / span) * (height - 60)
        points.append(f"{x:.2f},{y:.2f}")
    svg = "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
            '<rect width="100%" height="100%" fill="white"/>',
            '<text x="30" y="24" font-family="Arial" font-size="14">Realistic CME wall equity proxy</text>',
            f'<polyline fill="none" stroke="#2563eb" stroke-width="2" points="{" ".join(points)}"/>',
            "</svg>",
        ]
    )
    path.write_text(svg, encoding="utf-8")


def _output_paths(output_root: Path) -> dict[str, Path]:
    return {
        "definitions_csv": output_root / "cme_wall_realistic_strategy_definitions.csv",
        "definitions_md": output_root / "cme_wall_realistic_strategy_definitions.md",
        "trade_events_csv": output_root / "cme_wall_realistic_trade_events.csv",
        "trade_events_md": output_root / "cme_wall_realistic_trade_events.md",
        "performance_summary_csv": output_root / "cme_wall_realistic_performance_summary.csv",
        "performance_report_md": output_root / "cme_wall_realistic_performance_report.md",
        "equity_curve_csv": output_root / "cme_wall_realistic_equity_curve.csv",
        "equity_curve_md": output_root / "cme_wall_realistic_equity_curve.md",
        "equity_curve_svg": output_root / "charts" / "cme_wall_realistic_equity_curve.svg",
        "daily_pnl_csv": output_root / "cme_wall_realistic_daily_pnl.csv",
        "daily_pnl_md": output_root / "cme_wall_realistic_daily_pnl.md",
        "bad_days_csv": output_root / "cme_wall_realistic_bad_days.csv",
        "bad_days_md": output_root / "cme_wall_realistic_bad_days.md",
        "proxy_vs_realistic_csv": output_root / "cme_wall_proxy_vs_realistic_comparison.csv",
        "proxy_vs_realistic_md": output_root / "cme_wall_proxy_vs_realistic_comparison.md",
        "quality_grade_csv": output_root / "cme_wall_realistic_quality_grade.csv",
        "quality_grade_md": output_root / "cme_wall_realistic_quality_grade.md",
    }


def _definition_schema() -> dict[str, Any]:
    return {
        "strategy_name": pl.Utf8,
        "entry_rule": pl.Utf8,
        "confirmation_required": pl.Utf8,
        "target_rule": pl.Utf8,
        "stop_rule": pl.Utf8,
        "uses_direct_wall_touch": pl.Boolean,
        "uses_future_known_outcome": pl.Boolean,
        "allowed_label": pl.Utf8,
        "notes": pl.Utf8,
    }


def _trade_event_schema() -> dict[str, Any]:
    return {
        "event_id": pl.Utf8,
        "strategy_name": pl.Utf8,
        "trade_date": pl.Utf8,
        "setup_timestamp": pl.Utf8,
        "entry_timestamp": pl.Utf8,
        "exit_timestamp": pl.Utf8,
        "direction": pl.Utf8,
        "entry_price": pl.Float64,
        "target_price": pl.Float64,
        "stop_price": pl.Float64,
        "exit_price": pl.Float64,
        "wall_level": pl.Float64,
        "wall_type": pl.Utf8,
        "entry_confirmation": pl.Utf8,
        "exit_reason": pl.Utf8,
        "gross_pnl_points": pl.Float64,
        "spread_cost_points": pl.Float64,
        "slippage_points": pl.Float64,
        "net_pnl_points": pl.Float64,
        "mfe": pl.Float64,
        "mae": pl.Float64,
        "bars_held": pl.Int64,
        "data_quality": pl.Utf8,
        "sample_warning": pl.Boolean,
    }


def _performance_schema() -> dict[str, Any]:
    return {
        "strategy_name": pl.Utf8,
        "total_trades": pl.Int64,
        "winning_trades": pl.Int64,
        "losing_trades": pl.Int64,
        "win_rate": pl.Float64,
        "net_profit_points": pl.Float64,
        "gross_profit_points": pl.Float64,
        "gross_loss_points": pl.Float64,
        "profit_factor": pl.Float64,
        "average_trade": pl.Float64,
        "average_win": pl.Float64,
        "average_loss": pl.Float64,
        "max_drawdown_points": pl.Float64,
        "largest_win": pl.Float64,
        "largest_loss": pl.Float64,
        "commission_or_fee_total": pl.Float64,
        "spread_cost_total": pl.Float64,
        "slippage_total": pl.Float64,
        "expectancy": pl.Float64,
        "sample_size_warning": pl.Boolean,
        "realistic_trade_count": pl.Int64,
    }


def _equity_schema() -> dict[str, Any]:
    return {
        "timestamp": pl.Utf8,
        "strategy_name": pl.Utf8,
        "cumulative_pnl": pl.Float64,
        "drawdown": pl.Float64,
        "equity_curve_value": pl.Float64,
        "event_id": pl.Utf8,
    }


def _daily_pnl_schema() -> dict[str, Any]:
    return {
        "trade_date": pl.Utf8,
        "strategy_name": pl.Utf8,
        "trades": pl.Int64,
        "daily_gross_pnl": pl.Float64,
        "daily_net_pnl": pl.Float64,
        "fees": pl.Float64,
        "max_intraday_drawdown": pl.Float64,
        "bad_day": pl.Boolean,
        "bad_day_reason": pl.Utf8,
    }


def _bad_day_schema() -> dict[str, Any]:
    return _daily_pnl_schema()


def _proxy_comparison_schema() -> dict[str, Any]:
    return {
        "proxy_strategy_name": pl.Utf8,
        "realistic_strategy_name": pl.Utf8,
        "previous_proxy_pnl": pl.Float64,
        "realistic_pnl": pl.Float64,
        "proxy_row_count": pl.Int64,
        "realistic_trade_count": pl.Int64,
        "overcount_ratio": pl.Float64,
        "explanation": pl.Utf8,
    }


def _quality_schema() -> dict[str, Any]:
    return {
        "strategy_name": pl.Utf8,
        "quality_label": pl.Utf8,
        "realistic_trade_count": pl.Int64,
        "net_profit_points": pl.Float64,
        "max_drawdown_points": pl.Float64,
        "profit_factor": pl.Float64,
        "reason": pl.Utf8,
        "final_recommendation": pl.Utf8,
    }
