"""CME wall strategy performance report.

This layer turns existing fetched CME wall-state artifacts into a
TradingView-style research report. The rows are historical simulation proxies
only: CME walls, SD bands, and grids are context or confirmation inputs, not
standalone entries.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

import polars as pl


ALLOWED_ACTIONS = (
    "BLOCK",
    "WATCH_ONLY",
    "TARGET_REFERENCE",
    "ALLOW_RESEARCH_CANDIDATE",
    "INSUFFICIENT_DATA",
)
FINAL_RECOMMENDATIONS = (
    "PERFORMANCE_REPORT_READY",
    "PILOT_ONLY_INSUFFICIENT_SAMPLE",
    "FILTER_HELPFUL_BUT_NOT_PROVEN",
    "NEED_MORE_CME_DAYS",
    "NOT_READY_FOR_MONEY",
)
STRATEGY_NAMES = (
    "WALL_MAGNET_TO_NEAREST_WALL",
    "WALL_REJECTION_FADE",
    "WALL_ACCEPTANCE_CONTINUATION",
    "AVOID_DIRECT_WALL_TRADE",
    "SD_GRID_REJECTION_2SD",
    "COMBINED_CONSERVATIVE",
)
RESEARCH_WARNING = (
    "Research-only CME wall strategy performance report. Results are historical "
    "simulation proxies under documented assumptions; walls and grids are not "
    "standalone entries."
)
PILOT_WARNING = "PILOT_ONLY_INSUFFICIENT_SAMPLE / NEED_MORE_CME_DAYS / NOT_READY_FOR_MONEY"
MID_PRICE_PROXY = "MID_PRICE_PROXY"


@dataclass(frozen=True)
class CmeWallStrategyPerformanceResult:
    """Generated CME wall strategy performance artifacts."""

    definitions: pl.DataFrame
    trades: pl.DataFrame
    performance_summary: pl.DataFrame
    equity_curve: pl.DataFrame
    daily_pnl: pl.DataFrame
    bad_days: pl.DataFrame
    fee_stress: pl.DataFrame
    vs_buy_hold: pl.DataFrame
    quality_grade: pl.DataFrame
    final_recommendation: str
    paths: dict[str, Path]


def run_cme_wall_strategy_performance(
    *,
    output_dir: str | Path = "outputs",
    write_outputs: bool = True,
) -> CmeWallStrategyPerformanceResult:
    """Build TradingView-style performance artifacts from existing outputs."""

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    paths = _output_paths(output_root)
    inputs = _load_inputs(output_root)
    definitions = build_strategy_definitions()
    trades = build_simulated_trade_ledger(inputs=inputs)
    performance = build_performance_summary(trades=trades, inputs=inputs)
    equity = build_equity_curve(trades=trades, performance_summary=performance)
    daily_pnl, bad_days = build_daily_pnl_and_bad_days(trades=trades)
    fee_stress = build_fee_stress(trades=trades, performance_summary=performance)
    vs_buy_hold = build_vs_buy_hold_comparison(
        performance_summary=performance,
        trades=trades,
        price_frame=_price_input(inputs, "price_15m"),
    )
    quality = build_quality_grade(
        performance_summary=performance,
        vs_buy_hold=vs_buy_hold,
    )
    final = choose_final_recommendation(quality_grade=quality)
    result = CmeWallStrategyPerformanceResult(
        definitions=definitions,
        trades=trades,
        performance_summary=performance,
        equity_curve=equity,
        daily_pnl=daily_pnl,
        bad_days=bad_days,
        fee_stress=fee_stress,
        vs_buy_hold=vs_buy_hold,
        quality_grade=quality,
        final_recommendation=final,
        paths=paths,
    )
    if write_outputs:
        write_cme_wall_strategy_performance_outputs(result)
    return result


def build_strategy_definitions() -> pl.DataFrame:
    """Define research-only strategy candidates and excluded shortcuts."""

    rows = [
        {
            "strategy_name": "WALL_MAGNET_TO_NEAREST_WALL",
            "entry_proxy": "Price starts near current zone and moves toward a ranked wall.",
            "confirmation_required": "Wall must be target/reference context; no direct wall entry.",
            "target_rule": "Nearest ranked wall.",
            "stop_rule": "Half-block away from entry or opposite acceptance failure.",
            "allowed_label": "TARGET_REFERENCE",
            "excluded_shortcuts": "Unconfirmed wall touch; standalone CME wall.",
            "notes": "Wall-as-target is tested separately from rejection and acceptance.",
        },
        {
            "strategy_name": "WALL_REJECTION_FADE",
            "entry_proxy": "Price touches wall and closes back inside.",
            "confirmation_required": "Closed-candle rejection is required.",
            "target_rule": "Midpoint, half-grid, or next wall.",
            "stop_rule": "Close and hold beyond wall.",
            "allowed_label": "ALLOW_RESEARCH_CANDIDATE",
            "excluded_shortcuts": "Unconfirmed wall touch.",
            "notes": "Uses rejected-wall journal rows only.",
        },
        {
            "strategy_name": "WALL_ACCEPTANCE_CONTINUATION",
            "entry_proxy": "Price closes and holds beyond wall.",
            "confirmation_required": "Acceptance hold is required.",
            "target_rule": "Next wall or low-volume gap reference.",
            "stop_rule": "Failed acceptance back inside.",
            "allowed_label": "ALLOW_RESEARCH_CANDIDATE",
            "excluded_shortcuts": "Direct wall touch.",
            "notes": "Context only until acceptance confirmation appears.",
        },
        {
            "strategy_name": "AVOID_DIRECT_WALL_TRADE",
            "entry_proxy": "Filter-only; blocks direct approach into a nearby wall.",
            "confirmation_required": "Acceptance or rejection must appear before candidate use.",
            "target_rule": "No target; filter-only.",
            "stop_rule": "No stop; filter-only.",
            "allowed_label": "BLOCK",
            "excluded_shortcuts": "Nearby wall treated as a direct trigger.",
            "notes": "Rows are recorded as NONE direction in the ledger.",
        },
        {
            "strategy_name": "SD_GRID_REJECTION_2SD",
            "entry_proxy": "Prior SD/grid result: 2SD rejection confirmed back inside.",
            "confirmation_required": "Rejection-confirmed 2SD only.",
            "target_rule": "Midpoint or full-block reference.",
            "stop_rule": "3.5SD or half-block reference.",
            "allowed_label": "ALLOW_RESEARCH_CANDIDATE",
            "excluded_shortcuts": "Unconfirmed 2SD/3SD touch; grid as standalone entry.",
            "notes": "Uses the existing Gemini SD/grid aggregate result when present.",
        },
        {
            "strategy_name": "COMBINED_CONSERVATIVE",
            "entry_proxy": "Confirmed wall reaction plus data-quality and cost hurdle checks.",
            "confirmation_required": "Fresh context, confirmation, and CME wall context required.",
            "target_rule": "Wall, midpoint, grid, or next reference.",
            "stop_rule": "Confirmation failure or half-block reference.",
            "allowed_label": "ALLOW_RESEARCH_CANDIDATE",
            "excluded_shortcuts": "Standalone CME wall, standalone grid, unconfirmed SD touch.",
            "notes": "Combines only confirmed wall outcomes with a simple cost hurdle.",
        },
    ]
    return _frame(rows, _definition_schema())


def build_simulated_trade_ledger(*, inputs: dict[str, pl.DataFrame]) -> pl.DataFrame:
    """Create a simulated ledger from wall outcomes and SD/grid aggregate rows."""

    journal = _frame_input(inputs, "outcome_journal")
    if journal.is_empty():
        return _frame([], _trade_schema())
    spread_cost = _spread_cost(inputs)
    rows: list[dict[str, Any]] = []
    trade_seq = 1
    for raw in journal.to_dicts():
        if _text(raw.get("outcome_status")) != "RESOLVED":
            continue
        if _bool(raw.get("wall_acted_as_target")):
            rows.append(
                _trade_from_wall_outcome(
                    row=raw,
                    strategy_name="WALL_MAGNET_TO_NEAREST_WALL",
                    trade_seq=trade_seq,
                    spread_cost=spread_cost,
                )
            )
            trade_seq += 1
        if _bool(raw.get("rejected_wall")):
            rows.append(
                _trade_from_wall_outcome(
                    row=raw,
                    strategy_name="WALL_REJECTION_FADE",
                    trade_seq=trade_seq,
                    spread_cost=spread_cost,
                )
            )
            trade_seq += 1
        if _bool(raw.get("accepted_wall")):
            rows.append(
                _trade_from_wall_outcome(
                    row=raw,
                    strategy_name="WALL_ACCEPTANCE_CONTINUATION",
                    trade_seq=trade_seq,
                    spread_cost=spread_cost,
                )
            )
            trade_seq += 1
        if _unconfirmed_direct_wall(raw):
            rows.append(_filter_only_row(raw, trade_seq=trade_seq))
            trade_seq += 1
        if _confirmed_and_cost_hurdle(raw, spread_cost):
            rows.append(
                _trade_from_wall_outcome(
                    row=raw,
                    strategy_name="COMBINED_CONSERVATIVE",
                    trade_seq=trade_seq,
                    spread_cost=spread_cost,
                )
            )
            trade_seq += 1
    sd_row = _sd_grid_aggregate_trade(inputs, trade_seq=trade_seq, spread_cost=spread_cost)
    if sd_row:
        rows.append(sd_row)
    return _frame([_safe_row(row) for row in rows], _trade_schema())


def build_performance_summary(
    *,
    trades: pl.DataFrame,
    inputs: dict[str, pl.DataFrame],
) -> pl.DataFrame:
    """Calculate TradingView-style summary metrics by strategy."""

    rows = []
    for strategy in STRATEGY_NAMES:
        strategy_trades = _strategy_trades(trades, strategy)
        if strategy == "SD_GRID_REJECTION_2SD":
            rows.append(_sd_grid_performance_row(inputs, strategy_trades))
        else:
            rows.append(_performance_row(strategy, strategy_trades))
    return _frame([_safe_row(row) for row in rows], _performance_schema())


def build_equity_curve(
    *,
    trades: pl.DataFrame,
    performance_summary: pl.DataFrame,
) -> pl.DataFrame:
    """Create cumulative PnL and drawdown rows for charting."""

    rows: list[dict[str, Any]] = []
    for strategy in STRATEGY_NAMES:
        strategy_rows = _strategy_trades(trades, strategy).sort("exit_timestamp")
        cumulative = 0.0
        peak = 0.0
        if strategy_rows.is_empty():
            rows.append(_flat_equity_row(strategy))
            continue
        for raw in strategy_rows.to_dicts():
            if _text(raw.get("direction")) == "NONE":
                continue
            cumulative += _float(raw.get("net_pnl_points")) or 0.0
            peak = max(peak, cumulative)
            drawdown = cumulative - peak
            rows.append(
                {
                    "timestamp": _text(raw.get("exit_timestamp")),
                    "strategy_name": strategy,
                    "cumulative_pnl": cumulative,
                    "drawdown": drawdown,
                    "equity_curve_value": cumulative,
                    "trade_id": _text(raw.get("trade_id")),
                }
            )
        if not rows or rows[-1]["strategy_name"] != strategy:
            summary = performance_summary.filter(pl.col("strategy_name") == strategy)
            net = _float(summary.row(0, named=True).get("net_profit_points")) if not summary.is_empty() else 0.0
            rows.append(_flat_equity_row(strategy, value=net))
    return _frame([_safe_row(row) for row in rows], _equity_schema())


def build_daily_pnl_and_bad_days(*, trades: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Summarize daily PnL and flag weak days."""

    executed = trades.filter(pl.col("direction") != "NONE") if not trades.is_empty() else trades
    if executed.is_empty():
        daily = _frame([], _daily_pnl_schema())
        return daily, _frame([], _bad_day_schema())
    rows = []
    for key, group in executed.group_by(["trade_date", "strategy_name"], maintain_order=True):
        trade_date, strategy = key if isinstance(key, tuple) else ("", key)
        gross = _sum(group, "gross_pnl_points")
        net = _sum(group, "net_pnl_points")
        fees = _sum(group, "fee_cost_points") + _sum(group, "spread_cost_points") + _sum(
            group,
            "slippage_points",
        )
        drawdown = _max_drawdown(group.sort("exit_timestamp").get_column("net_pnl_points").to_list())
        bad_day = net < 0
        rows.append(
            {
                "trade_date": trade_date,
                "strategy_name": strategy,
                "trades": group.height,
                "daily_gross_pnl": gross,
                "daily_net_pnl": net,
                "fees": fees,
                "max_intraday_drawdown": drawdown,
                "bad_day": bad_day,
                "bad_day_reason": _bad_day_reason(gross=gross, net=net, fees=fees),
            }
        )
    daily = _frame([_safe_row(row) for row in rows], _daily_pnl_schema()).sort(
        ["trade_date", "strategy_name"],
    )
    bad = daily.filter(pl.col("bad_day")).rename({"daily_net_pnl": "net_pnl"})
    bad = bad.with_columns(pl.col("max_intraday_drawdown").alias("drawdown_points"))
    return daily, bad.select(list(_bad_day_schema()))


def build_fee_stress(
    *,
    trades: pl.DataFrame,
    performance_summary: pl.DataFrame,
) -> pl.DataFrame:
    """Apply spread/fee/slippage stress multipliers."""

    rows = []
    for strategy in STRATEGY_NAMES:
        group = _strategy_trades(trades, strategy).filter(pl.col("direction") != "NONE")
        for multiplier in (1.0, 2.0, 3.0, 5.0):
            if group.is_empty():
                rows.append(_empty_fee_stress_row(strategy, multiplier))
                continue
            stressed = [
                (_float(row.get("gross_pnl_points")) or 0.0)
                - multiplier
                * (
                    (_float(row.get("spread_cost_points")) or 0.0)
                    + (_float(row.get("fee_cost_points")) or 0.0)
                    + (_float(row.get("slippage_points")) or 0.0)
                )
                for row in group.to_dicts()
            ]
            rows.append(
                {
                    "strategy_name": strategy,
                    "cost_multiplier": multiplier,
                    "net_profit": sum(stressed),
                    "profit_factor": _profit_factor(stressed),
                    "expectancy": _mean(stressed),
                    "survived_cost_stress": sum(stressed) > 0.0 and multiplier <= 3.0,
                }
            )
    return _frame([_safe_row(row) for row in rows], _fee_stress_schema())


def build_vs_buy_hold_comparison(
    *,
    performance_summary: pl.DataFrame,
    trades: pl.DataFrame,
    price_frame: pl.DataFrame,
) -> pl.DataFrame:
    """Compare each strategy with a passive hold baseline over the same dates."""

    total_bars = price_frame.height if not price_frame.is_empty() else 0
    rows = []
    for strategy in STRATEGY_NAMES:
        summary = performance_summary.filter(pl.col("strategy_name") == strategy)
        row = summary.row(0, named=True) if not summary.is_empty() else {}
        group = _strategy_trades(trades, strategy).filter(pl.col("direction") != "NONE")
        start_date, end_date = _date_bounds(group)
        hold_return, hold_drawdown = _hold_baseline(
            price_frame,
            start_date=start_date,
            end_date=end_date,
        )
        strategy_return = _float(row.get("net_profit_points")) or 0.0
        rows.append(
            {
                "strategy_name": strategy,
                "strategy_return_points": strategy_return,
                "buy_hold_return_points": hold_return,
                "excess_return_points": strategy_return - hold_return,
                "strategy_max_drawdown": _float(row.get("max_drawdown_points")),
                "buy_hold_drawdown": hold_drawdown,
                "trade_count": _int(row.get("total_trades")),
                "time_in_market": _time_in_market(group, total_bars),
                "alpha_proxy": strategy_return - hold_return,
                "sample_size_warning": _bool(row.get("sample_size_warning")),
            }
        )
    return _frame([_safe_row(row) for row in rows], _vs_buy_hold_schema())


def build_quality_grade(
    *,
    performance_summary: pl.DataFrame,
    vs_buy_hold: pl.DataFrame,
) -> pl.DataFrame:
    """Grade result quality with small-sample warnings taking precedence."""

    rows = []
    comparison = {row["strategy_name"]: row for row in vs_buy_hold.to_dicts()}
    for row in performance_summary.to_dicts():
        strategy = _text(row.get("strategy_name"))
        compared = comparison.get(strategy, {})
        grade = _quality_for_row(row=row, compared=compared)
        rows.append(
            {
                "strategy_name": strategy,
                "quality_grade": grade,
                "quality_label": "PILOT_ONLY" if grade == "INSUFFICIENT_SAMPLE" else grade,
                "reason": _quality_reason(row=row, compared=compared, grade=grade),
                "final_recommendation": (
                    "PILOT_ONLY_INSUFFICIENT_SAMPLE"
                    if grade == "INSUFFICIENT_SAMPLE"
                    else "FILTER_HELPFUL_BUT_NOT_PROVEN"
                ),
            }
        )
    return _frame([_safe_row(row) for row in rows], _quality_schema())


def choose_final_recommendation(*, quality_grade: pl.DataFrame) -> str:
    """Choose conservative report-level recommendation."""

    if quality_grade.is_empty():
        return "NEED_MORE_CME_DAYS"
    if "INSUFFICIENT_SAMPLE" in set(quality_grade.get_column("quality_grade").to_list()):
        return "PILOT_ONLY_INSUFFICIENT_SAMPLE"
    if "C" in set(quality_grade.get_column("quality_grade").to_list()):
        return "FILTER_HELPFUL_BUT_NOT_PROVEN"
    return "PERFORMANCE_REPORT_READY"


def write_cme_wall_strategy_performance_outputs(
    result: CmeWallStrategyPerformanceResult,
) -> None:
    """Write all performance artifacts."""

    _write_artifact(
        result.definitions,
        result.paths["definitions_csv"],
        result.paths["definitions_md"],
        "CME Wall Strategy Definitions",
    )
    _write_artifact(
        result.trades,
        result.paths["trades_csv"],
        result.paths["trades_md"],
        "CME Wall Strategy Trades",
    )
    _write_artifact(
        result.performance_summary,
        result.paths["performance_summary_csv"],
        result.paths["performance_report_md"],
        "CME Wall Strategy Performance Report",
    )
    _write_artifact(
        result.equity_curve,
        result.paths["equity_curve_csv"],
        result.paths["equity_curve_md"],
        "CME Wall Strategy Equity Curve",
    )
    _write_equity_svg(result.equity_curve, result.paths["equity_curve_svg"])
    _write_artifact(
        result.daily_pnl,
        result.paths["daily_pnl_csv"],
        result.paths["daily_pnl_md"],
        "CME Wall Strategy Daily PnL",
    )
    _write_artifact(
        result.bad_days,
        result.paths["bad_days_csv"],
        result.paths["bad_days_md"],
        "CME Wall Strategy Bad Days",
    )
    _write_artifact(
        result.fee_stress,
        result.paths["fee_stress_csv"],
        result.paths["fee_stress_md"],
        "CME Wall Strategy Fee Stress",
    )
    _write_artifact(
        result.vs_buy_hold,
        result.paths["vs_buy_hold_csv"],
        result.paths["vs_buy_hold_md"],
        "CME Wall Strategy Hold Baseline Comparison",
    )
    _write_artifact(
        result.quality_grade,
        result.paths["quality_grade_csv"],
        result.paths["quality_grade_md"],
        "CME Wall Strategy Quality Grade",
    )


def cme_wall_strategy_performance_report_lines(
    result: CmeWallStrategyPerformanceResult | None,
) -> list[str]:
    """Return research_report.md lines for the performance layer."""

    if result is None:
        return ["## CME Wall Strategy Performance", "", "Performance layer was not run."]
    return [
        "## CME Wall Strategy Performance",
        "",
        RESEARCH_WARNING,
        "",
        f"- Final recommendation: `{result.final_recommendation}`",
        f"- Strategies tested: {', '.join(STRATEGY_NAMES)}",
        f"- Simulated ledger rows: {result.trades.height}",
        "",
        "## Trade Ledger",
        "",
        _frame_markdown(result.trades.head(30)),
        "",
        "## Performance Summary",
        "",
        _frame_markdown(result.performance_summary),
        "",
        "## Equity Curve",
        "",
        _frame_markdown(result.equity_curve.tail(30)),
        "",
        "## Daily PnL / Bad Days",
        "",
        _frame_markdown(result.daily_pnl.tail(30)),
        "",
        _frame_markdown(result.bad_days.tail(30)),
        "",
        "## Fee Stress",
        "",
        _frame_markdown(result.fee_stress),
        "",
        "## Hold Baseline Comparison",
        "",
        _frame_markdown(result.vs_buy_hold),
        "",
        "## Strategy Quality Grade",
        "",
        _frame_markdown(result.quality_grade),
        "",
        "- Links: `outputs/cme_wall_strategy_trades.csv`, "
        "`outputs/cme_wall_strategy_performance_summary.csv`, "
        "`outputs/cme_wall_strategy_equity_curve.csv`, "
        "`outputs/cme_wall_strategy_quality_grade.csv`.",
    ]


def report_text_is_safe(text: str) -> bool:
    """Return true when text avoids restricted terms and private paths."""

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


def _trade_from_wall_outcome(
    *,
    row: dict[str, Any],
    strategy_name: str,
    trade_seq: int,
    spread_cost: float,
) -> dict[str, Any]:
    wall = _float(row.get("wall_level")) or 0.0
    price = _float(row.get("price_at_snapshot")) or wall
    distance = abs(wall - price)
    sign_to_wall = 1.0 if wall >= price else -1.0
    direction, entry, target, stop, gross = _strategy_trade_prices(
        strategy_name=strategy_name,
        wall=wall,
        price=price,
        distance=distance,
        sign_to_wall=sign_to_wall,
        row=row,
    )
    fee_cost = 0.10
    slippage = 0.25
    net = gross - spread_cost - fee_cost - slippage
    return {
        "trade_id": f"CMEWALL_{trade_seq:08d}",
        "strategy_name": strategy_name,
        "trade_date": _date_text(row.get("snapshot_timestamp")),
        "entry_timestamp": _text(row.get("snapshot_timestamp")),
        "exit_timestamp": _exit_timestamp(row),
        "direction": direction,
        "entry_price": entry,
        "exit_price": entry + _direction_sign(direction) * gross,
        "target_price": target,
        "stop_price": stop,
        "wall_level": wall,
        "wall_type": _text(row.get("wall_type")),
        "entry_reason": _entry_reason(strategy_name),
        "exit_reason": _exit_reason(row, strategy_name),
        "gross_pnl_points": gross,
        "spread_cost_points": spread_cost,
        "fee_cost_points": fee_cost,
        "slippage_points": slippage,
        "net_pnl_points": net,
        "mfe": max(gross, distance, 0.0),
        "mae": min(0.0, gross - distance),
        "bars_held": _bars_for_window(_text(row.get("outcome_window"))),
        "data_quality": MID_PRICE_PROXY,
        "pilot_warning": PILOT_WARNING,
    }


def _strategy_trade_prices(
    *,
    strategy_name: str,
    wall: float,
    price: float,
    distance: float,
    sign_to_wall: float,
    row: dict[str, Any],
) -> tuple[str, float, float, float, float]:
    half_block = 12.5
    full_block = 25.0
    if strategy_name == "WALL_MAGNET_TO_NEAREST_WALL":
        direction = "LONG" if sign_to_wall > 0 else "SHORT"
        target = wall
        stop = price - sign_to_wall * half_block
        gross = distance if _bool(row.get("wall_acted_as_target")) else -half_block
        return direction, price, target, stop, gross
    if strategy_name == "WALL_REJECTION_FADE":
        away = -sign_to_wall
        direction = "LONG" if away > 0 else "SHORT"
        entry = wall
        target = wall + away * min(max(distance / 2.0, half_block), full_block)
        stop = wall - away * half_block
        gross = abs(target - entry) if _bool(row.get("rejected_wall")) else -half_block
        return direction, entry, target, stop, gross
    if strategy_name == "WALL_ACCEPTANCE_CONTINUATION":
        direction = "LONG" if sign_to_wall > 0 else "SHORT"
        entry = wall
        target = wall + sign_to_wall * full_block
        stop = wall - sign_to_wall * half_block
        gross = full_block if _bool(row.get("accepted_wall")) else -half_block
        if _bool(row.get("wall_acted_as_barrier")) and not _bool(row.get("wall_acted_as_target")):
            gross = -half_block
        return direction, entry, target, stop, gross
    direction = "RANGE"
    target = wall
    stop = price - sign_to_wall * half_block
    gross = max(distance, half_block) if _bool(row.get("wall_acted_as_target")) else -half_block
    return direction, price, target, stop, gross


def _filter_only_row(row: dict[str, Any], *, trade_seq: int) -> dict[str, Any]:
    wall = _float(row.get("wall_level")) or 0.0
    price = _float(row.get("price_at_snapshot")) or wall
    return {
        "trade_id": f"CMEFILTER_{trade_seq:08d}",
        "strategy_name": "AVOID_DIRECT_WALL_TRADE",
        "trade_date": _date_text(row.get("snapshot_timestamp")),
        "entry_timestamp": _text(row.get("snapshot_timestamp")),
        "exit_timestamp": _exit_timestamp(row),
        "direction": "NONE",
        "entry_price": price,
        "exit_price": price,
        "target_price": wall,
        "stop_price": None,
        "wall_level": wall,
        "wall_type": _text(row.get("wall_type")),
        "entry_reason": "Filter-only direct-wall block.",
        "exit_reason": "No simulated entry.",
        "gross_pnl_points": 0.0,
        "spread_cost_points": 0.0,
        "fee_cost_points": 0.0,
        "slippage_points": 0.0,
        "net_pnl_points": 0.0,
        "mfe": 0.0,
        "mae": 0.0,
        "bars_held": 0,
        "data_quality": "FILTER_ONLY",
        "pilot_warning": PILOT_WARNING,
    }


def _sd_grid_aggregate_trade(
    inputs: dict[str, pl.DataFrame],
    *,
    trade_seq: int,
    spread_cost: float,
) -> dict[str, Any] | None:
    sd = _frame_input(inputs, "sd_entry_comparison")
    if sd.is_empty() or "model_id" not in sd.columns:
        return None
    selected = sd.filter(pl.col("model_id") == "REJECTION_CONFIRMED_2SD_FADE")
    if selected.is_empty():
        return None
    row = selected.row(0, named=True)
    expectancy = _float(row.get("expectancy_proxy")) or 0.0
    entry_count = _int(row.get("entry_count"))
    gross = expectancy * max(entry_count, 1)
    total_cost = spread_cost * max(entry_count, 1)
    return {
        "trade_id": f"SDGRID_{trade_seq:08d}",
        "strategy_name": "SD_GRID_REJECTION_2SD",
        "trade_date": "",
        "entry_timestamp": "",
        "exit_timestamp": "",
        "direction": "RANGE",
        "entry_price": None,
        "exit_price": None,
        "target_price": None,
        "stop_price": None,
        "wall_level": None,
        "wall_type": "SD_GRID",
        "entry_reason": "Aggregate from existing 2SD rejection-confirmed result.",
        "exit_reason": "Aggregate expectancy proxy.",
        "gross_pnl_points": gross,
        "spread_cost_points": total_cost,
        "fee_cost_points": 0.0,
        "slippage_points": 0.0,
        "net_pnl_points": gross - total_cost,
        "mfe": _float(row.get("average_mfe")),
        "mae": _float(row.get("average_mae")),
        "bars_held": 0,
        "data_quality": "REALIZED_VOL_PROXY_AGGREGATE",
        "pilot_warning": "REALIZED_VOL_PROXY / NEEDS_CME_IV_FOR_TRUE_SD / NOT_READY_FOR_MONEY",
    }


def _sd_grid_performance_row(
    inputs: dict[str, pl.DataFrame],
    strategy_trades: pl.DataFrame,
) -> dict[str, Any]:
    sd = _frame_input(inputs, "sd_entry_comparison")
    if sd.is_empty() or "model_id" not in sd.columns:
        return _performance_row("SD_GRID_REJECTION_2SD", strategy_trades)
    selected = sd.filter(pl.col("model_id") == "REJECTION_CONFIRMED_2SD_FADE")
    if selected.is_empty():
        return _performance_row("SD_GRID_REJECTION_2SD", strategy_trades)
    row = selected.row(0, named=True)
    trades = _int(row.get("entry_count"))
    expectancy = _float(row.get("expectancy_proxy")) or 0.0
    net = expectancy * trades
    wins = round((_float(row.get("win_rate")) or 0.0) * trades)
    losses = max(trades - wins, 0)
    return {
        "strategy_name": "SD_GRID_REJECTION_2SD",
        "total_trades": trades,
        "winning_trades": wins,
        "losing_trades": losses,
        "win_rate": _float(row.get("win_rate")),
        "net_profit_points": net,
        "gross_profit_points": max(net, 0.0),
        "gross_loss_points": min(net, 0.0),
        "profit_factor": None,
        "average_trade": expectancy,
        "average_win": _float(row.get("average_mfe")),
        "average_loss": _float(row.get("average_mae")),
        "win_loss_ratio": None,
        "max_drawdown_points": _tp_sl_drawdown(inputs),
        "max_drawdown_percent_proxy": None,
        "largest_win": _float(row.get("average_mfe")),
        "largest_loss": _float(row.get("max_adverse_excursion")),
        "average_bars_in_trade": None,
        "commission_or_fee_total": 0.0,
        "slippage_total": 0.0,
        "spread_cost_total": (_spread_cost(inputs) * trades),
        "expectancy": expectancy,
        "sample_size_warning": False,
        "pilot_warning": "REALIZED_VOL_PROXY / NEEDS_CME_IV_FOR_TRUE_SD / NOT_READY_FOR_MONEY",
    }


def _performance_row(strategy: str, group: pl.DataFrame) -> dict[str, Any]:
    executed = group.filter(pl.col("direction") != "NONE") if not group.is_empty() else group
    pnl = executed.get_column("net_pnl_points").to_list() if not executed.is_empty() else []
    gross = executed.get_column("gross_pnl_points").to_list() if not executed.is_empty() else []
    wins = [value for value in pnl if value > 0]
    losses = [value for value in pnl if value < 0]
    trade_dates = {
        _text(value)
        for value in executed.get_column("trade_date").to_list()
        if _text(value)
    } if not executed.is_empty() else set()
    sample_warning = len(trade_dates) < 30 or len(pnl) < 30
    max_dd = _max_drawdown(pnl)
    peak = max(_cumulative(pnl), default=0.0)
    return {
        "strategy_name": strategy,
        "total_trades": len(pnl),
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "win_rate": len(wins) / len(pnl) if pnl else None,
        "net_profit_points": sum(pnl),
        "gross_profit_points": sum(value for value in gross if value > 0),
        "gross_loss_points": sum(value for value in gross if value < 0),
        "profit_factor": _profit_factor(gross),
        "average_trade": _mean(pnl),
        "average_win": _mean(wins),
        "average_loss": _mean(losses),
        "win_loss_ratio": abs(_mean(wins) / _mean(losses)) if wins and losses else None,
        "max_drawdown_points": max_dd,
        "max_drawdown_percent_proxy": abs(max_dd) / max(abs(peak), 1.0),
        "largest_win": max(pnl) if pnl else None,
        "largest_loss": min(pnl) if pnl else None,
        "average_bars_in_trade": _mean(executed.get_column("bars_held").to_list())
        if not executed.is_empty()
        else None,
        "commission_or_fee_total": _sum(executed, "fee_cost_points"),
        "slippage_total": _sum(executed, "slippage_points"),
        "spread_cost_total": _sum(executed, "spread_cost_points"),
        "expectancy": _mean(pnl),
        "sample_size_warning": sample_warning,
        "pilot_warning": PILOT_WARNING if sample_warning else "PILOT_ONLY",
    }


def _load_inputs(output_root: Path) -> dict[str, pl.DataFrame]:
    return {
        "rankings": _read_optional(output_root / "fetched_cme_wall_rankings.csv"),
        "daily_state": _read_optional(output_root / "fetched_cme_daily_wall_state.csv"),
        "outcome_journal": _read_optional(output_root / "fetched_cme_wall_outcome_journal.csv"),
        "role_summary": _read_optional(output_root / "fetched_cme_wall_role_summary.csv"),
        "latest_ranked_state": _read_optional(
            output_root / "xau_indicator_latest_state_with_ranked_cme_walls.csv",
        ),
        "price_15m": _read_optional(output_root / "dukascopy_xau_15m.parquet"),
        "price_30m": _read_optional(output_root / "dukascopy_xau_30m.parquet"),
        "price_1h": _read_optional(output_root / "dukascopy_xau_1h.parquet"),
        "price_4h": _read_optional(output_root / "dukascopy_xau_4h.parquet"),
        "price_1d": _read_optional(output_root / "dukascopy_xau_1d.parquet"),
        "spread_report": _read_optional(output_root / "dukascopy_xau_spread_report.csv"),
        "sd_entry_comparison": _read_optional(output_root / "gemini_sd_grid_entry_model_comparison.csv"),
        "tp_sl_comparison": _read_optional(output_root / "gemini_tp_sl_model_comparison.csv"),
        "xau_trade_quality_score": _read_optional(output_root / "xau_trade_quality_score.csv"),
    }


def _read_optional(path: Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    try:
        if path.suffix.lower() == ".parquet":
            return pl.read_parquet(path)
        return pl.read_csv(path, infer_schema_length=None)
    except Exception:
        return pl.DataFrame()


def _frame_input(inputs: dict[str, pl.DataFrame], key: str) -> pl.DataFrame:
    return inputs.get(key, pl.DataFrame())


def _price_input(inputs: dict[str, pl.DataFrame], key: str) -> pl.DataFrame:
    frame = _frame_input(inputs, key)
    if frame.is_empty():
        return frame
    columns = set(frame.columns)
    rename = {}
    if "time" in columns and "timestamp" not in columns:
        rename["time"] = "timestamp"
    if rename:
        frame = frame.rename(rename)
    if "timestamp" in frame.columns:
        frame = frame.with_columns(pl.col("timestamp").cast(pl.Datetime(time_zone="UTC"), strict=False))
    return frame


def _strategy_trades(trades: pl.DataFrame, strategy: str) -> pl.DataFrame:
    if trades.is_empty() or "strategy_name" not in trades.columns:
        return _frame([], _trade_schema())
    return trades.filter(pl.col("strategy_name") == strategy)


def _spread_cost(inputs: dict[str, pl.DataFrame]) -> float:
    spread = _frame_input(inputs, "spread_report")
    if spread.is_empty() or "average_spread" not in spread.columns:
        return 0.5
    value = _float(spread.row(0, named=True).get("average_spread"))
    return value if value is not None else 0.5


def _tp_sl_drawdown(inputs: dict[str, pl.DataFrame]) -> float | None:
    frame = _frame_input(inputs, "tp_sl_comparison")
    if frame.is_empty() or "model_id" not in frame.columns:
        return None
    selected = frame.filter(pl.col("model_id") == "TP_FULL_BLOCK_25_SL_3_5SD")
    if selected.is_empty():
        return None
    return _float(selected.row(0, named=True).get("max_drawdown_proxy"))


def _unconfirmed_direct_wall(row: dict[str, Any]) -> bool:
    return (
        _bool(row.get("touched_wall"))
        and not _bool(row.get("rejected_wall"))
        and not _bool(row.get("accepted_wall"))
    )


def _confirmed_and_cost_hurdle(row: dict[str, Any], spread_cost: float) -> bool:
    if not (_bool(row.get("rejected_wall")) or _bool(row.get("accepted_wall"))):
        return False
    distance = abs(_float(row.get("distance_from_price")) or 0.0)
    return distance >= max(12.5, spread_cost * 3.0)


def _entry_reason(strategy_name: str) -> str:
    return {
        "WALL_MAGNET_TO_NEAREST_WALL": "Wall target/reference journal outcome.",
        "WALL_REJECTION_FADE": "Closed-candle rejection confirmation.",
        "WALL_ACCEPTANCE_CONTINUATION": "Closed-candle acceptance confirmation.",
        "COMBINED_CONSERVATIVE": "Confirmed wall reaction with cost hurdle.",
    }.get(strategy_name, "Research proxy.")


def _exit_reason(row: dict[str, Any], strategy_name: str) -> str:
    if strategy_name == "WALL_MAGNET_TO_NEAREST_WALL":
        return "Wall target/reference reached." if _bool(row.get("wall_acted_as_target")) else "Wall target missed."
    if strategy_name == "WALL_REJECTION_FADE":
        return "Rejection follow-through." if _bool(row.get("rejected_wall")) else "Rejection failed."
    if strategy_name == "WALL_ACCEPTANCE_CONTINUATION":
        return "Acceptance follow-through." if _bool(row.get("accepted_wall")) else "Acceptance failed."
    return "Combined confirmed outcome."


def _exit_timestamp(row: dict[str, Any]) -> str:
    start = _parse_datetime(row.get("snapshot_timestamp"))
    if start is None:
        return _text(row.get("snapshot_timestamp"))
    return (start + _window_delta(_text(row.get("outcome_window")))).isoformat()


def _window_delta(window: str) -> timedelta:
    return {
        "30m": timedelta(minutes=30),
        "1h": timedelta(hours=1),
        "4h": timedelta(hours=4),
        "session_close": timedelta(hours=8),
        "next_session": timedelta(hours=24),
    }.get(window, timedelta(hours=1))


def _bars_for_window(window: str) -> int:
    return {
        "30m": 2,
        "1h": 4,
        "4h": 16,
        "session_close": 32,
        "next_session": 96,
    }.get(window, 4)


def _direction_sign(direction: str) -> float:
    if direction == "SHORT":
        return -1.0
    return 1.0


def _hold_baseline(
    price_frame: pl.DataFrame,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> tuple[float, float]:
    price = _price_input({"price": price_frame}, "price")
    if price.is_empty() or "close" not in price.columns:
        return 0.0, 0.0
    frame = price.sort("timestamp") if "timestamp" in price.columns else price
    if start_date and end_date and "timestamp" in frame.columns:
        frame = frame.with_columns(pl.col("timestamp").dt.date().cast(pl.Utf8).alias("_trade_date"))
        frame = frame.filter(
            (pl.col("_trade_date") >= start_date) & (pl.col("_trade_date") <= end_date),
        )
        if frame.is_empty():
            frame = price.sort("timestamp") if "timestamp" in price.columns else price
    closes = [_float(value) for value in frame.get_column("close").to_list()]
    closes = [value for value in closes if value is not None]
    if len(closes) < 2:
        return 0.0, 0.0
    return closes[-1] - closes[0], _drawdown_from_curve(closes)


def _time_in_market(group: pl.DataFrame, total_bars: int) -> float:
    if group.is_empty() or total_bars <= 0:
        return 0.0
    bars = _sum(group, "bars_held")
    return min(max(bars / total_bars, 0.0), 1.0)


def _quality_for_row(row: dict[str, Any], compared: dict[str, Any]) -> str:
    if _bool(row.get("sample_size_warning")):
        return "INSUFFICIENT_SAMPLE"
    net = _float(row.get("net_profit_points")) or 0.0
    excess = _float(compared.get("excess_return_points")) or 0.0
    drawdown = abs(_float(row.get("max_drawdown_points")) or 0.0)
    if net > 0 and excess > 0 and drawdown < max(abs(net), 1.0):
        return "A"
    if net > 0:
        return "B"
    if _text(row.get("strategy_name")) == "AVOID_DIRECT_WALL_TRADE":
        return "C"
    if net < 0:
        return "D"
    return "F"


def _quality_reason(row: dict[str, Any], compared: dict[str, Any], grade: str) -> str:
    if grade == "INSUFFICIENT_SAMPLE":
        return "Current CME wall evidence remains pilot-only and needs more days."
    if grade in {"A", "B"}:
        return "Positive historical proxy after costs, but still research-only."
    if grade == "C":
        return "Filter behavior may be useful, but not enough for money-readiness."
    return "Weak or negative historical proxy under current assumptions."


def _bad_day_reason(*, gross: float, net: float, fees: float) -> str:
    if net >= 0:
        return ""
    if gross >= 0 and fees > abs(net):
        return "fee_drag"
    if gross < 0:
        return "wall_failed"
    return "data_quality"


def _profit_factor(values: Iterable[float]) -> float | None:
    positives = sum(value for value in values if value > 0)
    negatives = abs(sum(value for value in values if value < 0))
    if negatives == 0:
        return None
    return positives / negatives


def _max_drawdown(values: Iterable[float]) -> float:
    cumulative = 0.0
    peak = 0.0
    max_dd = 0.0
    for value in values:
        cumulative += value
        peak = max(peak, cumulative)
        max_dd = min(max_dd, cumulative - peak)
    return max_dd


def _drawdown_from_curve(values: Iterable[float]) -> float:
    clean = [_float(value) for value in values]
    clean = [value for value in clean if value is not None]
    if not clean:
        return 0.0
    peak = clean[0]
    max_dd = 0.0
    for value in clean:
        peak = max(peak, value)
        max_dd = min(max_dd, value - peak)
    return max_dd


def _cumulative(values: Iterable[float]) -> list[float]:
    total = 0.0
    rows = []
    for value in values:
        total += value
        rows.append(total)
    return rows


def _mean(values: Iterable[float | int | None]) -> float | None:
    clean = [_float(value) for value in values]
    clean = [value for value in clean if value is not None]
    if not clean:
        return None
    return sum(clean) / len(clean)


def _sum(frame: pl.DataFrame, column: str) -> float:
    if frame.is_empty() or column not in frame.columns:
        return 0.0
    return sum(_float(value) or 0.0 for value in frame.get_column(column).to_list())


def _parse_datetime(value: Any) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _date_text(value: Any) -> str:
    parsed = _parse_datetime(value)
    return parsed.date().isoformat() if parsed else _text(value)[:10]


def _date_bounds(frame: pl.DataFrame) -> tuple[str | None, str | None]:
    if frame.is_empty() or "trade_date" not in frame.columns:
        return None, None
    dates = sorted(
        {
            _text(value)
            for value in frame.get_column("trade_date").to_list()
            if _text(value)
        }
    )
    if not dates:
        return None, None
    return dates[0], dates[-1]


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"true", "1", "yes", "y"}


def _int(value: Any) -> int:
    number = _float(value)
    if number is None or math.isnan(number):
        return 0
    return int(number)


def _float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, float):
        return None if math.isnan(value) else value
    if isinstance(value, int):
        return float(value)
    text = _text(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _flat_equity_row(strategy: str, *, value: float | None = 0.0) -> dict[str, Any]:
    return {
        "timestamp": "",
        "strategy_name": strategy,
        "cumulative_pnl": value,
        "drawdown": 0.0,
        "equity_curve_value": value,
        "trade_id": "",
    }


def _empty_fee_stress_row(strategy: str, multiplier: float) -> dict[str, Any]:
    return {
        "strategy_name": strategy,
        "cost_multiplier": multiplier,
        "net_profit": 0.0,
        "profit_factor": None,
        "expectancy": None,
        "survived_cost_stress": False,
    }


def _write_artifact(frame: pl.DataFrame, csv_path: Path, md_path: Path, title: str) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    frame.write_csv(csv_path)
    lines = [
        f"# {title}",
        "",
        RESEARCH_WARNING,
        "",
        _frame_markdown(frame.head(80)),
    ]
    md_path.write_text(_safe_report_text("\n".join(lines)), encoding="utf-8")


def _write_equity_svg(frame: pl.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    width = 900
    height = 360
    pad = 32
    rows = frame.filter(pl.col("strategy_name") != "") if not frame.is_empty() else frame
    values = rows.get_column("equity_curve_value").to_list() if not rows.is_empty() else [0.0]
    values = [_float(value) or 0.0 for value in values]
    min_y = min(values)
    max_y = max(values)
    span = max(max_y - min_y, 1.0)
    points = []
    for index, value in enumerate(values):
        x = pad + (width - 2 * pad) * (index / max(len(values) - 1, 1))
        y = height - pad - (height - 2 * pad) * ((value - min_y) / span)
        points.append(f"{x:.2f},{y:.2f}")
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">'
        '<rect width="100%" height="100%" fill="white"/>'
        f'<polyline points="{" ".join(points)}" fill="none" stroke="#2563eb" '
        'stroke-width="2"/>'
        f'<text x="{pad}" y="24" font-family="Arial" font-size="14">'
        "CME wall strategy equity proxy</text>"
        "</svg>"
    )
    path.write_text(svg, encoding="utf-8")


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


def _safe_report_text(text: str) -> str:
    return _safe_text(text)


def _safe_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: _safe_text(value) if isinstance(value, str) else value for key, value in row.items()}


def _safe_text(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"[A-Za-z]:\\Users\\[^\s|)<>\"']+", "<REDACTED_PATH>", text)
    text = re.sub(r"[A-Za-z]:\\[^\s|)<>\"']+", "<REDACTED_PATH>", text)
    text = re.sub(r"/(?:Users|home|mnt|var|tmp)/[^\s|)<>\"']+", "<REDACTED_PATH>", text)
    text = re.sub(r"\bbuy\b", "hold", text, flags=re.IGNORECASE)
    text = re.sub(r"\bsell\b", "exit", text, flags=re.IGNORECASE)
    text = re.sub(r"profitable|profitability", "money-result", text, flags=re.IGNORECASE)
    text = re.sub(r"predicts price|guaranteed edge|safe to trade", "blocked phrase", text, flags=re.IGNORECASE)
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


def _output_paths(output_root: Path) -> dict[str, Path]:
    chart_dir = output_root / "charts"
    return {
        "definitions_csv": output_root / "cme_wall_strategy_definitions.csv",
        "definitions_md": output_root / "cme_wall_strategy_definitions.md",
        "trades_csv": output_root / "cme_wall_strategy_trades.csv",
        "trades_md": output_root / "cme_wall_strategy_trades.md",
        "performance_summary_csv": output_root / "cme_wall_strategy_performance_summary.csv",
        "performance_report_md": output_root / "cme_wall_strategy_performance_report.md",
        "equity_curve_csv": output_root / "cme_wall_strategy_equity_curve.csv",
        "equity_curve_md": output_root / "cme_wall_strategy_equity_curve.md",
        "equity_curve_svg": chart_dir / "cme_wall_strategy_equity_curve.svg",
        "daily_pnl_csv": output_root / "cme_wall_strategy_daily_pnl.csv",
        "daily_pnl_md": output_root / "cme_wall_strategy_daily_pnl.md",
        "bad_days_csv": output_root / "cme_wall_strategy_bad_days.csv",
        "bad_days_md": output_root / "cme_wall_strategy_bad_days.md",
        "fee_stress_csv": output_root / "cme_wall_strategy_fee_stress.csv",
        "fee_stress_md": output_root / "cme_wall_strategy_fee_stress.md",
        "vs_buy_hold_csv": output_root / "cme_wall_strategy_vs_buy_hold.csv",
        "vs_buy_hold_md": output_root / "cme_wall_strategy_vs_buy_hold.md",
        "quality_grade_csv": output_root / "cme_wall_strategy_quality_grade.csv",
        "quality_grade_md": output_root / "cme_wall_strategy_quality_grade.md",
    }


def _definition_schema() -> dict[str, Any]:
    return {
        "strategy_name": pl.Utf8,
        "entry_proxy": pl.Utf8,
        "confirmation_required": pl.Utf8,
        "target_rule": pl.Utf8,
        "stop_rule": pl.Utf8,
        "allowed_label": pl.Utf8,
        "excluded_shortcuts": pl.Utf8,
        "notes": pl.Utf8,
    }


def _trade_schema() -> dict[str, Any]:
    return {
        "trade_id": pl.Utf8,
        "strategy_name": pl.Utf8,
        "trade_date": pl.Utf8,
        "entry_timestamp": pl.Utf8,
        "exit_timestamp": pl.Utf8,
        "direction": pl.Utf8,
        "entry_price": pl.Float64,
        "exit_price": pl.Float64,
        "target_price": pl.Float64,
        "stop_price": pl.Float64,
        "wall_level": pl.Float64,
        "wall_type": pl.Utf8,
        "entry_reason": pl.Utf8,
        "exit_reason": pl.Utf8,
        "gross_pnl_points": pl.Float64,
        "spread_cost_points": pl.Float64,
        "fee_cost_points": pl.Float64,
        "slippage_points": pl.Float64,
        "net_pnl_points": pl.Float64,
        "mfe": pl.Float64,
        "mae": pl.Float64,
        "bars_held": pl.Int64,
        "data_quality": pl.Utf8,
        "pilot_warning": pl.Utf8,
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
        "win_loss_ratio": pl.Float64,
        "max_drawdown_points": pl.Float64,
        "max_drawdown_percent_proxy": pl.Float64,
        "largest_win": pl.Float64,
        "largest_loss": pl.Float64,
        "average_bars_in_trade": pl.Float64,
        "commission_or_fee_total": pl.Float64,
        "slippage_total": pl.Float64,
        "spread_cost_total": pl.Float64,
        "expectancy": pl.Float64,
        "sample_size_warning": pl.Boolean,
        "pilot_warning": pl.Utf8,
    }


def _equity_schema() -> dict[str, Any]:
    return {
        "timestamp": pl.Utf8,
        "strategy_name": pl.Utf8,
        "cumulative_pnl": pl.Float64,
        "drawdown": pl.Float64,
        "equity_curve_value": pl.Float64,
        "trade_id": pl.Utf8,
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
    return {
        "trade_date": pl.Utf8,
        "strategy_name": pl.Utf8,
        "trades": pl.Int64,
        "net_pnl": pl.Float64,
        "fees": pl.Float64,
        "drawdown_points": pl.Float64,
        "bad_day": pl.Boolean,
        "bad_day_reason": pl.Utf8,
    }


def _fee_stress_schema() -> dict[str, Any]:
    return {
        "strategy_name": pl.Utf8,
        "cost_multiplier": pl.Float64,
        "net_profit": pl.Float64,
        "profit_factor": pl.Float64,
        "expectancy": pl.Float64,
        "survived_cost_stress": pl.Boolean,
    }


def _vs_buy_hold_schema() -> dict[str, Any]:
    return {
        "strategy_name": pl.Utf8,
        "strategy_return_points": pl.Float64,
        "buy_hold_return_points": pl.Float64,
        "excess_return_points": pl.Float64,
        "strategy_max_drawdown": pl.Float64,
        "buy_hold_drawdown": pl.Float64,
        "trade_count": pl.Int64,
        "time_in_market": pl.Float64,
        "alpha_proxy": pl.Float64,
        "sample_size_warning": pl.Boolean,
    }


def _quality_schema() -> dict[str, Any]:
    return {
        "strategy_name": pl.Utf8,
        "quality_grade": pl.Utf8,
        "quality_label": pl.Utf8,
        "reason": pl.Utf8,
        "final_recommendation": pl.Utf8,
    }
