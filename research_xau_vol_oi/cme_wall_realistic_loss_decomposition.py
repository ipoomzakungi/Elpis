"""Loss decomposition for realistic CME wall backtest v1.

This report-only layer explains where the realistic v1 replay loses points.
It does not alter strategy rules, tune thresholds, or create new entries.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
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
    "COST_DRAG_DOMINANT",
    "EXIT_REWRITE_NEEDED",
    "ENTRY_CONFIRMATION_WEAK",
    "WALL_SELECTION_WEAK",
    "ACCEPTANCE_CONTINUATION_QUARANTINE",
    "SD_2_REJECTION_COST_DRAG_REVIEW",
    "NEED_MORE_CME_DAYS",
    "NOT_READY_FOR_MONEY",
)
RESEARCH_WARNING = (
    "Research-only realistic CME wall loss decomposition. This audit explains "
    "loss drivers and fixability labels without changing strategy rules."
)


@dataclass(frozen=True)
class CmeWallRealisticLossDecompositionResult:
    """Generated realistic loss-decomposition artifacts."""

    loss_by_strategy: pl.DataFrame
    loss_by_exit_reason: pl.DataFrame
    cost_drag: pl.DataFrame
    loss_by_wall_type: pl.DataFrame
    loss_by_distance: pl.DataFrame
    loss_by_timeframe: pl.DataFrame
    loss_by_session: pl.DataFrame
    loss_by_direction: pl.DataFrame
    fixability_audit: pl.DataFrame
    next_action: pl.DataFrame
    conclusion_markdown: str
    final_recommendation: str
    paths: dict[str, Path]


def run_cme_wall_realistic_loss_decomposition(
    *,
    output_dir: str | Path = "outputs",
    write_outputs: bool = True,
) -> CmeWallRealisticLossDecompositionResult:
    """Run loss decomposition for the realistic CME wall backtest."""

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    paths = _output_paths(output_root)
    inputs = _load_inputs(output_root)
    trades = _prepared_trades(inputs)
    performance = _frame_input(inputs, "performance_summary")
    daily_pnl = _frame_input(inputs, "daily_pnl")
    loss_by_strategy = build_loss_by_strategy(trades=trades, performance=performance)
    loss_by_exit = build_loss_by_exit_reason(trades=trades)
    cost_drag = build_cost_drag_audit(trades=trades)
    loss_by_wall_type = build_group_loss_audit(
        trades=trades,
        group_column="wall_type_group",
        output_column="wall_type",
    )
    loss_by_distance = build_group_loss_audit(
        trades=trades,
        group_column="distance_bucket",
        output_column="distance_bucket",
    )
    loss_by_timeframe = build_timeframe_audit(trades=trades)
    loss_by_session = build_session_audit(trades=trades, daily_pnl=daily_pnl)
    loss_by_direction = build_group_loss_audit(
        trades=trades,
        group_column="direction",
        output_column="direction",
        schema=_direction_schema(),
    )
    fixability = build_fixability_audit(
        loss_by_strategy=loss_by_strategy,
        loss_by_exit_reason=loss_by_exit,
        cost_drag=cost_drag,
        loss_by_direction=loss_by_direction,
        loss_by_session=loss_by_session,
    )
    next_action = build_next_action_table(
        loss_by_strategy=loss_by_strategy,
        cost_drag=cost_drag,
        loss_by_wall_type=loss_by_wall_type,
        loss_by_distance=loss_by_distance,
        loss_by_direction=loss_by_direction,
        loss_by_session=loss_by_session,
        fixability=fixability,
    )
    final = choose_final_recommendation(fixability_audit=fixability, cost_drag=cost_drag)
    conclusion = build_loss_conclusion(
        next_action=next_action,
        fixability_audit=fixability,
        final_recommendation=final,
    )
    result = CmeWallRealisticLossDecompositionResult(
        loss_by_strategy=loss_by_strategy,
        loss_by_exit_reason=loss_by_exit,
        cost_drag=cost_drag,
        loss_by_wall_type=loss_by_wall_type,
        loss_by_distance=loss_by_distance,
        loss_by_timeframe=loss_by_timeframe,
        loss_by_session=loss_by_session,
        loss_by_direction=loss_by_direction,
        fixability_audit=fixability,
        next_action=next_action,
        conclusion_markdown=conclusion,
        final_recommendation=final,
        paths=paths,
    )
    if write_outputs:
        write_cme_wall_realistic_loss_decomposition_outputs(result)
    return result


def build_loss_by_strategy(*, trades: pl.DataFrame, performance: pl.DataFrame) -> pl.DataFrame:
    """Decompose losses by strategy."""

    rows: list[dict[str, Any]] = []
    perf = {_text(row.get("strategy_name")): row for row in performance.to_dicts()} if not performance.is_empty() else {}
    for strategy in STRATEGY_NAMES:
        group = _active_rows(trades, strategy_name=strategy)
        net_values = [_float(row.get("net_pnl_points")) or 0.0 for row in group]
        gross_values = [_float(row.get("gross_pnl_points")) or 0.0 for row in group]
        wins = [value for value in net_values if value > 0]
        losses = [value for value in net_values if value < 0]
        gross_profit = sum(value for value in gross_values if value > 0)
        gross_loss = sum(value for value in gross_values if value < 0)
        net_pnl = sum(net_values)
        top_losses = sorted((abs(value) for value in losses), reverse=True)
        loss_total_abs = sum(abs(value) for value in losses)
        top5 = sum(top_losses[:5]) / loss_total_abs if loss_total_abs else 0.0
        top10 = sum(top_losses[:10]) / loss_total_abs if loss_total_abs else 0.0
        drawdown = _float(perf.get(strategy, {}).get("max_drawdown_points"))
        if drawdown is None:
            drawdown = _max_drawdown(net_values)
        rows.append(
            {
                "strategy_name": strategy,
                "trades": len(group),
                "gross_profit": gross_profit,
                "gross_loss": gross_loss,
                "net_pnl": net_pnl,
                "win_rate": len(wins) / len(group) if group else None,
                "avg_win": sum(wins) / len(wins) if wins else None,
                "avg_loss": sum(losses) / len(losses) if losses else None,
                "largest_loss": min(losses) if losses else None,
                "largest_win": max(wins) if wins else None,
                "loss_concentration_top_5_trades": top5,
                "loss_concentration_top_10_trades": top10,
                "drawdown_contribution": drawdown,
                "profit_factor": gross_profit / abs(gross_loss) if gross_loss < 0 else None,
                "main_loss_driver": _main_loss_driver_for_strategy(strategy, group, net_pnl),
            }
        )
    return _frame([_safe_row(row) for row in rows], _loss_by_strategy_schema())


def build_loss_by_exit_reason(*, trades: pl.DataFrame) -> pl.DataFrame:
    """Group loss drivers by exit reason."""

    rows = []
    for reason in ("TARGET_HIT", "STOP_HIT", "SESSION_CLOSE", "INVALIDATION", "AMBIGUOUS_SAME_CANDLE", "NO_ENTRY"):
        group = [row for row in trades.to_dicts() if _exit_reason_group(row) == reason]
        rows.append(_group_metric_row(group=group, key_column="exit_reason", key_value=reason))
    return _frame([_safe_row(row) for row in rows], _exit_reason_schema())


def build_cost_drag_audit(*, trades: pl.DataFrame) -> pl.DataFrame:
    """Determine whether costs explain weak realistic results."""

    rows: list[dict[str, Any]] = []
    for strategy in STRATEGY_NAMES:
        group = _active_rows(trades, strategy_name=strategy)
        gross = sum(_float(row.get("gross_pnl_points")) or 0.0 for row in group)
        spread = sum(_float(row.get("spread_cost_points")) or 0.0 for row in group)
        slippage = sum(_float(row.get("slippage_points")) or 0.0 for row in group)
        total_cost = spread + slippage
        net = sum(_float(row.get("net_pnl_points")) or 0.0 for row in group)
        half_cost_net = sum(
            (_float(row.get("gross_pnl_points")) or 0.0)
            - 0.5
            * (
                (_float(row.get("spread_cost_points")) or 0.0)
                + (_float(row.get("slippage_points")) or 0.0)
            )
            for row in group
        )
        flips = sum(
            1
            for row in group
            if (_float(row.get("gross_pnl_points")) or 0.0) > 0
            and (_float(row.get("net_pnl_points")) or 0.0) < 0
        )
        rows.append(
            {
                "strategy_name": strategy,
                "gross_pnl_before_cost": gross,
                "spread_cost_total": spread,
                "slippage_total": slippage,
                "net_pnl_after_cost": net,
                "cost_drag_ratio": total_cost / abs(gross) if gross else None,
                "trades_flipped_from_win_to_loss_by_cost": flips,
                "strategies_survive_zero_cost": gross > 0,
                "strategies_survive_half_cost": half_cost_net > 0,
                "strategies_survive_base_cost": net > 0,
                "cost_explains_loss": gross > 0 and net < 0,
            }
        )
    return _frame([_safe_row(row) for row in rows], _cost_drag_schema())


def build_group_loss_audit(
    *,
    trades: pl.DataFrame,
    group_column: str,
    output_column: str,
    schema: dict[str, Any] | None = None,
) -> pl.DataFrame:
    """Build a generic group loss audit."""

    active = [row for row in trades.to_dicts() if _text(row.get("direction")) in {"LONG", "SHORT", "RANGE", "NONE"}]
    values = sorted({_text(row.get(group_column)) or "UNKNOWN" for row in active})
    rows = [
        _group_metric_row(
            group=[row for row in active if (_text(row.get(group_column)) or "UNKNOWN") == value],
            key_column=output_column,
            key_value=value,
        )
        for value in values
    ]
    return _frame([_safe_row(row) for row in rows], schema or _wall_distance_schema(output_column))


def build_timeframe_audit(*, trades: pl.DataFrame) -> pl.DataFrame:
    """Group losses by replay timeframe label."""

    return build_group_loss_audit(
        trades=trades,
        group_column="timeframe",
        output_column="timeframe",
        schema=_timeframe_schema(),
    )


def build_session_audit(*, trades: pl.DataFrame, daily_pnl: pl.DataFrame) -> pl.DataFrame:
    """Group losses by session/date and flag clustered loss days."""

    active = [row for row in trades.to_dicts() if _text(row.get("direction")) in {"LONG", "SHORT"}]
    total_loss_abs = abs(sum((_float(row.get("net_pnl_points")) or 0.0) for row in active if (_float(row.get("net_pnl_points")) or 0.0) < 0))
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in active:
        key = (_text(row.get("trade_date")), _text(row.get("session_bucket")))
        grouped.setdefault(key, []).append(row)
    bad_day_count = _bad_day_count_by_date(daily_pnl)
    rows: list[dict[str, Any]] = []
    for (trade_date, session), group in sorted(grouped.items()):
        net = sum(_float(row.get("net_pnl_points")) or 0.0 for row in group)
        rows.append(
            {
                "trade_date": trade_date,
                "session_date": f"{trade_date}:{session}",
                "trades": len(group),
                "net_pnl": net,
                "max_drawdown": _max_drawdown([_float(row.get("net_pnl_points")) or 0.0 for row in group]),
                "bad_day_count": bad_day_count.get(trade_date, 0),
                "clustered_loss_warning": bool(net < 0 and total_loss_abs and abs(net) / total_loss_abs >= 0.25),
            }
        )
    return _frame([_safe_row(row) for row in rows], _session_schema())


def build_fixability_audit(
    *,
    loss_by_strategy: pl.DataFrame,
    loss_by_exit_reason: pl.DataFrame,
    cost_drag: pl.DataFrame,
    loss_by_direction: pl.DataFrame,
    loss_by_session: pl.DataFrame,
) -> pl.DataFrame:
    """Classify whether each strategy is fixable, quarantined, or needs more data."""

    cost_by_strategy = {_text(row.get("strategy_name")): row for row in cost_drag.to_dicts()}
    rows: list[dict[str, Any]] = []
    for row in loss_by_strategy.to_dicts():
        strategy = _text(row.get("strategy_name"))
        trades = _int(row.get("trades"))
        net = _float(row.get("net_pnl")) or 0.0
        pf = _float(row.get("profit_factor"))
        cost = cost_by_strategy.get(strategy, {})
        main_failure = _fixability_failure_mode(
            strategy=strategy,
            trades=trades,
            net=net,
            profit_factor=pf,
            cost_row=cost,
            loss_by_exit_reason=loss_by_exit_reason,
            loss_by_direction=loss_by_direction,
            loss_by_session=loss_by_session,
        )
        fixability, action = _fixability_action(strategy, main_failure, trades, net, pf)
        rows.append(
            {
                "strategy_name": strategy,
                "main_failure_mode": main_failure,
                "fixability": fixability,
                "recommended_next_action": action,
                "reason": _fixability_reason(strategy, main_failure, cost, row),
            }
        )
    return _frame([_safe_row(row) for row in rows], _fixability_schema())


def build_next_action_table(
    *,
    loss_by_strategy: pl.DataFrame,
    cost_drag: pl.DataFrame,
    loss_by_wall_type: pl.DataFrame,
    loss_by_distance: pl.DataFrame,
    loss_by_direction: pl.DataFrame,
    loss_by_session: pl.DataFrame,
    fixability: pl.DataFrame,
) -> pl.DataFrame:
    """Answer the requested conclusion questions in structured form."""

    worst_strategy = _worst_row(loss_by_strategy, "net_pnl")
    worst_wall = _worst_row(loss_by_wall_type, "net_pnl")
    worst_distance = _worst_row(loss_by_distance, "net_pnl")
    worst_direction = _worst_row(loss_by_direction, "net_pnl")
    worst_session = _worst_row(loss_by_session, "net_pnl")
    cost_dominant = any(_bool(row.get("cost_explains_loss")) for row in cost_drag.to_dicts())
    keep = [
        _text(row.get("strategy_name"))
        for row in fixability.to_dicts()
        if _text(row.get("recommended_next_action")) in {"KEEP_RESEARCH", "TEST_AS_FILTER_ONLY", "NEED_MORE_CME_DAYS"}
    ]
    quarantine = [
        _text(row.get("strategy_name"))
        for row in fixability.to_dicts()
        if _text(row.get("recommended_next_action")) == "QUARANTINE"
    ]
    rows = [
        _answer("costs_explain_losses", "PARTIAL" if cost_dominant else "NO", _cost_summary(cost_drag)),
        _answer("exits_explain_losses", "YES", _exit_summary()),
        _answer("entries_explain_losses", "PARTIAL", _entry_summary(loss_by_strategy)),
        _answer("worst_direction", _text(worst_direction.get("direction")), _row_summary(worst_direction)),
        _answer("worst_wall_type", _text(worst_wall.get("wall_type")), _row_summary(worst_wall)),
        _answer("worst_distance_bucket", _text(worst_distance.get("distance_bucket")), _row_summary(worst_distance)),
        _answer("worst_session_day", _text(worst_session.get("session_date")), _row_summary(worst_session)),
        _answer("keep_under_research", ", ".join(keep), "Keep only as research/watchlist candidates until more CME days exist."),
        _answer("quarantine", ", ".join(quarantine), "Quarantine means no new rule tuning until the failure mode is reviewed."),
        _answer("next_best_test", "FORWARD_LOSS_JOURNAL", "Journal confirmed entries by failure mode before rewriting entries or exits."),
        _answer("worst_strategy", _text(worst_strategy.get("strategy_name")), _row_summary(worst_strategy)),
    ]
    return _frame([_safe_row(row) for row in rows], _next_action_schema())


def build_loss_conclusion(
    *,
    next_action: pl.DataFrame,
    fixability_audit: pl.DataFrame,
    final_recommendation: str,
) -> str:
    """Build the narrative conclusion markdown."""

    answers = {_text(row.get("question")): row for row in next_action.to_dicts()}
    lines = [
        "# CME Wall Realistic Loss Conclusion",
        "",
        RESEARCH_WARNING,
        "",
        f"- Final recommendation: `{final_recommendation}`",
        f"- Cost explanation: {_text(answers.get('costs_explain_losses', {}).get('answer'))}",
        f"- Exit explanation: {_text(answers.get('exits_explain_losses', {}).get('answer'))}",
        f"- Entry explanation: {_text(answers.get('entries_explain_losses', {}).get('answer'))}",
        f"- Worst direction: `{_text(answers.get('worst_direction', {}).get('answer'))}`",
        f"- Worst wall type: `{_text(answers.get('worst_wall_type', {}).get('answer'))}`",
        f"- Worst distance bucket: `{_text(answers.get('worst_distance_bucket', {}).get('answer'))}`",
        f"- Worst session/day: `{_text(answers.get('worst_session_day', {}).get('answer'))}`",
        f"- Keep under research: `{_text(answers.get('keep_under_research', {}).get('answer'))}`",
        f"- Quarantine: `{_text(answers.get('quarantine', {}).get('answer'))}`",
        f"- Next best test: `{_text(answers.get('next_best_test', {}).get('answer'))}`",
        "",
        "## Fixability",
        "",
        _frame_markdown(fixability_audit),
    ]
    return "\n".join(_safe_text(line) for line in lines) + "\n"


def choose_final_recommendation(*, fixability_audit: pl.DataFrame, cost_drag: pl.DataFrame) -> str:
    """Choose a conservative final recommendation."""

    actions = {_text(row.get("recommended_next_action")) for row in fixability_audit.to_dicts()}
    failures = {_text(row.get("main_failure_mode")) for row in fixability_audit.to_dicts()}
    if "QUARANTINE" in actions:
        return "ACCEPTANCE_CONTINUATION_QUARANTINE"
    if any(_bool(row.get("cost_explains_loss")) for row in cost_drag.to_dicts()):
        return "SD_2_REJECTION_COST_DRAG_REVIEW"
    if "EXIT_TOO_LATE" in failures or "STOP_TOO_WIDE" in failures:
        return "EXIT_REWRITE_NEEDED"
    if "FALSE_BREAKOUTS" in failures:
        return "ENTRY_CONFIRMATION_WEAK"
    if "BAD_WALL_SELECTION" in failures:
        return "WALL_SELECTION_WEAK"
    if "SAMPLE_TOO_SMALL" in failures:
        return "NEED_MORE_CME_DAYS"
    return "NOT_READY_FOR_MONEY"


def write_cme_wall_realistic_loss_decomposition_outputs(
    result: CmeWallRealisticLossDecompositionResult,
) -> None:
    """Write CSV and Markdown outputs."""

    result.loss_by_strategy.write_csv(result.paths["loss_by_strategy_csv"])
    result.loss_by_exit_reason.write_csv(result.paths["loss_by_exit_reason_csv"])
    result.cost_drag.write_csv(result.paths["cost_drag_csv"])
    result.loss_by_wall_type.write_csv(result.paths["loss_by_wall_type_csv"])
    result.loss_by_distance.write_csv(result.paths["loss_by_distance_csv"])
    result.loss_by_timeframe.write_csv(result.paths["loss_by_timeframe_csv"])
    result.loss_by_session.write_csv(result.paths["loss_by_session_csv"])
    result.loss_by_direction.write_csv(result.paths["loss_by_direction_csv"])
    result.fixability_audit.write_csv(result.paths["fixability_csv"])
    result.next_action.write_csv(result.paths["next_action_csv"])
    _write_md(result.paths["loss_by_strategy_md"], "CME Wall Realistic Loss By Strategy", result.loss_by_strategy)
    _write_md(result.paths["loss_by_exit_reason_md"], "CME Wall Realistic Loss By Exit Reason", result.loss_by_exit_reason)
    _write_md(result.paths["cost_drag_md"], "CME Wall Realistic Cost Drag", result.cost_drag)
    _write_md(result.paths["loss_by_wall_type_md"], "CME Wall Realistic Loss By Wall Type", result.loss_by_wall_type)
    _write_md(result.paths["loss_by_distance_md"], "CME Wall Realistic Loss By Distance", result.loss_by_distance)
    _write_md(result.paths["loss_by_timeframe_md"], "CME Wall Realistic Loss By Timeframe", result.loss_by_timeframe)
    _write_md(result.paths["loss_by_session_md"], "CME Wall Realistic Loss By Session", result.loss_by_session)
    _write_md(result.paths["loss_by_direction_md"], "CME Wall Realistic Loss By Direction", result.loss_by_direction)
    _write_md(result.paths["fixability_md"], "CME Wall Realistic Fixability Audit", result.fixability_audit)
    _write_md(result.paths["next_action_md"], "CME Wall Realistic Next Action", result.next_action)
    result.paths["loss_conclusion_md"].write_text(result.conclusion_markdown, encoding="utf-8")


def cme_wall_realistic_loss_decomposition_report_lines(
    result: CmeWallRealisticLossDecompositionResult | None,
) -> list[str]:
    """Return research_report.md lines for the loss decomposition."""

    if result is None:
        return ["## Realistic CME Wall Loss Decomposition", "", "Loss decomposition was not run."]
    return [
        "## Realistic CME Wall Loss Decomposition",
        "",
        RESEARCH_WARNING,
        "",
        f"- Final recommendation: `{result.final_recommendation}`",
        "",
        "## Cost Drag Audit",
        "",
        _frame_markdown(result.cost_drag),
        "",
        "## Wall Type / Distance Audit",
        "",
        _frame_markdown(result.loss_by_wall_type),
        "",
        _frame_markdown(result.loss_by_distance),
        "",
        "## Timeframe / Session Audit",
        "",
        _frame_markdown(result.loss_by_timeframe),
        "",
        _frame_markdown(result.loss_by_session.head(30)),
        "",
        "## Direction Audit",
        "",
        _frame_markdown(result.loss_by_direction),
        "",
        "## Fixability Audit",
        "",
        _frame_markdown(result.fixability_audit),
        "",
        "## Loss Conclusion",
        "",
        _frame_markdown(result.next_action),
        "",
        "- Links: `outputs/cme_wall_realistic_loss_by_strategy.csv`, "
        "`outputs/cme_wall_realistic_cost_drag.csv`, "
        "`outputs/cme_wall_realistic_fixability_audit.csv`, "
        "`outputs/cme_wall_realistic_loss_conclusion.md`.",
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


def _prepared_trades(inputs: dict[str, pl.DataFrame]) -> pl.DataFrame:
    trades = _frame_input(inputs, "trade_events")
    if trades.is_empty():
        return _frame([], _prepared_trade_schema())
    price_15m = _normalize_price_frame(_frame_input(inputs, "price_15m"))
    rows = []
    price_by_timestamp = {
        _parse_datetime(row.get("timestamp")): row
        for row in price_15m.to_dicts()
        if _parse_datetime(row.get("timestamp")) is not None
    }
    for raw in trades.to_dicts():
        row = dict(raw)
        row["exit_reason_group"] = _detect_exit_reason_group(row, price_by_timestamp)
        row["cost_points"] = (_float(row.get("spread_cost_points")) or 0.0) + (
            _float(row.get("slippage_points")) or 0.0
        )
        row["gross_minus_half_cost"] = (_float(row.get("gross_pnl_points")) or 0.0) - 0.5 * row["cost_points"]
        row["gross_minus_zero_cost"] = _float(row.get("gross_pnl_points")) or 0.0
        row["wall_type_group"] = _wall_type_group(row.get("wall_type"))
        row["distance_from_wall_at_entry"] = _distance_from_wall(row)
        row["distance_bucket"] = _distance_bucket(row["distance_from_wall_at_entry"])
        row["timeframe"] = _timeframe_label(row)
        row["session_bucket"] = _session_bucket(row.get("entry_timestamp") or row.get("setup_timestamp"))
        rows.append(row)
    return _frame([_safe_row(row) for row in rows], _prepared_trade_schema())


def _detect_exit_reason_group(
    row: dict[str, Any],
    price_by_timestamp: dict[datetime | None, dict[str, Any]],
) -> str:
    reason = _text(row.get("exit_reason")) or "NO_ENTRY"
    if reason == "NO_ENTRY" or _text(row.get("direction")) == "NONE":
        return "NO_ENTRY"
    timestamp = _parse_datetime(row.get("exit_timestamp"))
    candle = price_by_timestamp.get(timestamp)
    if candle and reason == "STOP_HIT" and _same_candle_target_stop(row, candle):
        return "AMBIGUOUS_SAME_CANDLE"
    return reason if reason in {"TARGET_HIT", "STOP_HIT", "SESSION_CLOSE", "INVALIDATION"} else reason


def _same_candle_target_stop(row: dict[str, Any], candle: dict[str, Any]) -> bool:
    direction = _text(row.get("direction"))
    target = _float(row.get("target_price"))
    stop = _float(row.get("stop_price"))
    high = _float(candle.get("high"))
    low = _float(candle.get("low"))
    if target is None or stop is None or high is None or low is None:
        return False
    if direction == "LONG":
        return high >= target and low <= stop
    if direction == "SHORT":
        return low <= target and high >= stop
    return False


def _group_metric_row(*, group: list[dict[str, Any]], key_column: str, key_value: str) -> dict[str, Any]:
    active = [row for row in group if _text(row.get("direction")) in {"LONG", "SHORT"}]
    pnl_values = [_float(row.get("net_pnl_points")) or 0.0 for row in active]
    wins = [value for value in pnl_values if value > 0]
    gross_values = [_float(row.get("gross_pnl_points")) or 0.0 for row in active]
    gross_profit = sum(value for value in gross_values if value > 0)
    gross_loss = sum(value for value in gross_values if value < 0)
    row = {
        key_column: key_value,
        "trade_count": len(active) if key_value != "NO_ENTRY" else len(group),
        "net_pnl": sum(pnl_values),
        "avg_pnl": sum(pnl_values) / len(active) if active else None,
        "win_rate": len(wins) / len(active) if active else None,
        "avg_mae": _average([_float(item.get("mae")) or 0.0 for item in active]),
        "avg_mfe": _average([_float(item.get("mfe")) or 0.0 for item in active]),
        "profit_factor": gross_profit / abs(gross_loss) if gross_loss < 0 else None,
        "max_drawdown": _max_drawdown(pnl_values),
        "interpretation": _group_interpretation(sum(pnl_values), len(active)),
        "notes": _group_notes(key_column, key_value, group),
    }
    return row


def _exit_reason_group(row: dict[str, Any]) -> str:
    return _text(row.get("exit_reason_group")) or _text(row.get("exit_reason")) or "NO_ENTRY"


def _main_loss_driver_for_strategy(strategy: str, group: list[dict[str, Any]], net_pnl: float) -> str:
    if strategy == "AVOID_DIRECT_WALL_TRADE_FILTER":
        return "FILTER_ONLY"
    if not group:
        return "SAMPLE_TOO_SMALL"
    if strategy == "WALL_ACCEPTANCE_CONTINUATION" and net_pnl < 0:
        return "FALSE_BREAKOUTS"
    gross = sum(_float(row.get("gross_pnl_points")) or 0.0 for row in group)
    if gross > 0 and net_pnl < 0:
        return "COST_DRAG"
    exit_groups = _net_by(group, "exit_reason_group")
    if exit_groups.get("SESSION_CLOSE", 0.0) < min(exit_groups.values(), default=0.0):
        return "EXIT_TOO_LATE"
    if exit_groups.get("STOP_HIT", 0.0) + exit_groups.get("AMBIGUOUS_SAME_CANDLE", 0.0) < 0:
        return "STOP_OR_AMBIGUITY"
    return "STRUCTURALLY_WEAK" if net_pnl < 0 else "MIXED"


def _fixability_failure_mode(
    *,
    strategy: str,
    trades: int,
    net: float,
    profit_factor: float | None,
    cost_row: dict[str, Any],
    loss_by_exit_reason: pl.DataFrame,
    loss_by_direction: pl.DataFrame,
    loss_by_session: pl.DataFrame,
) -> str:
    if strategy == "AVOID_DIRECT_WALL_TRADE_FILTER":
        return "SAMPLE_TOO_SMALL"
    if strategy == "WALL_ACCEPTANCE_CONTINUATION" and net < 0:
        return "FALSE_BREAKOUTS"
    if strategy == "SD_2_REJECTION_CONFIRMED_FADE" and net < 0 and profit_factor and profit_factor > 1:
        return "COST_DRAG"
    if trades < 30:
        return "SAMPLE_TOO_SMALL"
    if _bool(cost_row.get("cost_explains_loss")):
        return "COST_DRAG"
    if _clustered_loss_exists(loss_by_session):
        return "SESSION_CLUSTERED_LOSS"
    if _worst_direction_is_dominant(loss_by_direction):
        return "WRONG_DIRECTION"
    exit_loss = _worst_row(loss_by_exit_reason, "net_pnl")
    reason = _text(exit_loss.get("exit_reason"))
    if reason in {"SESSION_CLOSE", "INVALIDATION"}:
        return "EXIT_TOO_LATE"
    if reason in {"STOP_HIT", "AMBIGUOUS_SAME_CANDLE"}:
        return "STOP_TOO_WIDE"
    return "STRUCTURALLY_WEAK"


def _fixability_action(
    strategy: str,
    main_failure: str,
    trades: int,
    net: float,
    profit_factor: float | None,
) -> tuple[str, str]:
    if strategy == "WALL_ACCEPTANCE_CONTINUATION" and net < -1000:
        return "LIKELY_KILL", "QUARANTINE"
    if strategy == "AVOID_DIRECT_WALL_TRADE_FILTER":
        return "FIXABLE_WITH_FILTER", "TEST_AS_FILTER_ONLY"
    if main_failure == "COST_DRAG":
        return "FIXABLE_WITH_FILTER", "KEEP_RESEARCH"
    if trades < 30:
        return "NEED_MORE_DATA", "NEED_MORE_CME_DAYS"
    if main_failure in {"EXIT_TOO_LATE", "STOP_TOO_WIDE", "STOP_TOO_TIGHT"}:
        return "FIXABLE_WITH_EXIT_REWRITE", "REWRITE_EXIT"
    if main_failure in {"BAD_WALL_SELECTION", "WRONG_DIRECTION"}:
        return "FIXABLE_WITH_WALL_SELECTION", "REWRITE_ENTRY_CONFIRMATION"
    if main_failure == "FALSE_BREAKOUTS":
        return "FIXABLE_WITH_FILTER", "REWRITE_ENTRY_CONFIRMATION"
    if profit_factor and profit_factor > 0.8:
        return "NEED_MORE_DATA", "NEED_MORE_CME_DAYS"
    return "LIKELY_KILL", "KILL_LATER_IF_FORWARD_CONFIRMED"


def _fixability_reason(
    strategy: str,
    main_failure: str,
    cost_row: dict[str, Any],
    strategy_row: dict[str, Any],
) -> str:
    if strategy == "WALL_ACCEPTANCE_CONTINUATION":
        net = _float(strategy_row.get("net_pnl")) or 0.0
        if net < 0:
            return "Acceptance continuation has negative net and weak target follow-through in the realistic replay."
        return "Acceptance continuation no longer drives losses after favorable-target validation; keep it under forward research."
    if main_failure == "COST_DRAG":
        return "Gross replay survives zero-cost or half-cost assumptions but fails after base spread/slippage costs."
    if main_failure == "SAMPLE_TOO_SMALL":
        return "No active standalone rows or too few rows to assess as a standalone candidate."
    return f"Net={_float(strategy_row.get('net_pnl'))}; zero_cost_survives={_bool(cost_row.get('strategies_survive_zero_cost'))}."


def _answer(question: str, answer: str, evidence: str) -> dict[str, Any]:
    return {
        "question": question,
        "answer": answer,
        "evidence": evidence,
    }


def _cost_summary(cost_drag: pl.DataFrame) -> str:
    rows = [
        _text(row.get("strategy_name"))
        for row in cost_drag.to_dicts()
        if _bool(row.get("cost_explains_loss"))
    ]
    return "Cost-drag strategies: " + (", ".join(rows) if rows else "none")


def _exit_summary() -> str:
    return "Exit reason grouping separates target hits, stops, invalidation, session close, and ambiguous same-candle outcomes."


def _entry_summary(loss_by_strategy: pl.DataFrame) -> str:
    rows = {_text(row.get("strategy_name")): row for row in loss_by_strategy.to_dicts()}
    acceptance_net = _float(rows.get("WALL_ACCEPTANCE_CONTINUATION", {}).get("net_pnl")) or 0.0
    rejection_net = _float(rows.get("WALL_REJECTION_CONFIRMED_FADE", {}).get("net_pnl")) or 0.0
    if acceptance_net > 0 and rejection_net < 0:
        return "Acceptance continuation improved after favorable-target validation; rejection fade remains weak and needs entry-direction review."
    if acceptance_net < 0:
        return "Acceptance confirmation has weak follow-through; rejection variants are less severe but still negative after costs."
    return "Entry results are mixed; keep only research candidates with forward evidence."


def _row_summary(row: dict[str, Any]) -> str:
    if not row:
        return "No rows."
    pieces = []
    for key in ("trade_count", "trades", "net_pnl", "max_drawdown", "profit_factor"):
        if key in row:
            pieces.append(f"{key}={_text(row.get(key))}")
    return "; ".join(pieces)


def _active_rows(trades: pl.DataFrame, strategy_name: str | None = None) -> list[dict[str, Any]]:
    if trades.is_empty():
        return []
    rows = trades.to_dicts()
    if strategy_name:
        rows = [row for row in rows if _text(row.get("strategy_name")) == strategy_name]
    return [row for row in rows if _text(row.get("direction")) in {"LONG", "SHORT"}]


def _net_by(rows: list[dict[str, Any]], column: str) -> dict[str, float]:
    result: dict[str, float] = {}
    for row in rows:
        key = _text(row.get(column)) or "UNKNOWN"
        result[key] = result.get(key, 0.0) + (_float(row.get("net_pnl_points")) or 0.0)
    return result


def _worst_row(frame: pl.DataFrame, column: str) -> dict[str, Any]:
    if frame.is_empty() or column not in frame.columns:
        return {}
    sorted_frame = frame.sort(column)
    return sorted_frame.row(0, named=True) if sorted_frame.height else {}


def _clustered_loss_exists(loss_by_session: pl.DataFrame) -> bool:
    return bool(
        not loss_by_session.is_empty()
        and "clustered_loss_warning" in loss_by_session.columns
        and loss_by_session.get_column("clustered_loss_warning").any()
    )


def _worst_direction_is_dominant(loss_by_direction: pl.DataFrame) -> bool:
    if loss_by_direction.is_empty():
        return False
    rows = [row for row in loss_by_direction.to_dicts() if _text(row.get("direction")) in {"LONG", "SHORT"}]
    losses = [abs(_float(row.get("net_pnl")) or 0.0) for row in rows if (_float(row.get("net_pnl")) or 0.0) < 0]
    return bool(losses and max(losses) / max(sum(losses), 1.0) >= 0.7)


def _bad_day_count_by_date(daily_pnl: pl.DataFrame) -> dict[str, int]:
    if daily_pnl.is_empty() or "trade_date" not in daily_pnl.columns:
        return {}
    result: dict[str, int] = {}
    for row in daily_pnl.to_dicts():
        if _bool(row.get("bad_day")):
            date = _text(row.get("trade_date"))
            result[date] = result.get(date, 0) + 1
    return result


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
    if not {"timestamp", "high", "low", "close"}.issubset(set(frame.columns)):
        return pl.DataFrame()
    return (
        frame.with_columns(
            pl.col("timestamp").cast(pl.Datetime(time_zone="UTC"), strict=False),
            pl.col("high").cast(pl.Float64, strict=False),
            pl.col("low").cast(pl.Float64, strict=False),
            pl.col("close").cast(pl.Float64, strict=False),
        )
        .drop_nulls(["timestamp", "high", "low", "close"])
        .select([column for column in ("timestamp", "high", "low", "close") if column in frame.columns])
    )


def _wall_type_group(value: Any) -> str:
    text = _text(value)
    allowed = {
        "CALL_VOLUME_WALL",
        "PUT_VOLUME_WALL",
        "OI_WALL",
        "TOTAL_VOLUME_WALL",
        "LOW_VOLUME_GAP",
    }
    return text if text in allowed else text or "UNKNOWN"


def _distance_from_wall(row: dict[str, Any]) -> float | None:
    entry = _float(row.get("entry_price"))
    wall = _float(row.get("wall_level"))
    if entry is None or wall is None:
        return None
    return abs(entry - wall)


def _distance_bucket(distance: float | None) -> str:
    if distance is None:
        return "UNKNOWN"
    if distance < 10:
        return "0-10"
    if distance < 25:
        return "10-25"
    if distance < 50:
        return "25-50"
    if distance < 100:
        return "50-100"
    return "100+"


def _timeframe_label(row: dict[str, Any]) -> str:
    quality = _text(row.get("data_quality"))
    if "REALIZED_VOL" in quality:
        return "15m"
    if "INTRADAY_PATH" in quality:
        return "15m"
    if _text(row.get("direction")) == "NONE":
        return "NONE"
    return "UNKNOWN"


def _session_bucket(value: Any) -> str:
    parsed = _parse_datetime(value)
    if parsed is None:
        return "UNKNOWN"
    if parsed.hour < 8:
        return "ASIA"
    if parsed.hour < 16:
        return "EUROPE_US"
    return "LATE_US"


def _group_interpretation(net_pnl: float, count: int) -> str:
    if count == 0:
        return "CONTEXT_ONLY"
    if net_pnl < 0:
        return "LOSS_DRIVER"
    if net_pnl > 0:
        return "OFFSETTING_WINNER"
    return "NEUTRAL"


def _group_notes(key_column: str, key_value: str, group: list[dict[str, Any]]) -> str:
    if key_column == "exit_reason" and key_value == "AMBIGUOUS_SAME_CANDLE":
        return "Conservative assumption used when target and stop can occur in one candle."
    if key_column == "wall_type" and key_value == "SD_2_REALIZED_VOL_PROXY":
        return "SD proxy row, not a CME wall type."
    if not group:
        return "No active rows."
    return "Research-only diagnostic grouping."


def _average(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _max_drawdown(values: list[float]) -> float:
    cumulative = 0.0
    peak = 0.0
    max_dd = 0.0
    for value in values:
        cumulative += value
        peak = max(peak, cumulative)
        max_dd = min(max_dd, cumulative - peak)
    return max_dd


def _load_inputs(output_root: Path) -> dict[str, pl.DataFrame]:
    return {
        "trade_events": _read_optional(output_root / "cme_wall_realistic_trade_events.csv"),
        "performance_summary": _read_optional(output_root / "cme_wall_realistic_performance_summary.csv"),
        "equity_curve": _read_optional(output_root / "cme_wall_realistic_equity_curve.csv"),
        "daily_pnl": _read_optional(output_root / "cme_wall_realistic_daily_pnl.csv"),
        "bad_days": _read_optional(output_root / "cme_wall_realistic_bad_days.csv"),
        "quality_grade": _read_optional(output_root / "cme_wall_realistic_quality_grade.csv"),
        "proxy_vs_realistic": _read_optional(output_root / "cme_wall_proxy_vs_realistic_comparison.csv"),
        "rankings": _read_optional(output_root / "fetched_cme_wall_rankings.csv"),
        "daily_wall_state": _read_optional(output_root / "fetched_cme_daily_wall_state.csv"),
        "price_15m": _read_optional(output_root / "dukascopy_xau_15m.parquet"),
        "price_30m": _read_optional(output_root / "dukascopy_xau_30m.parquet"),
        "price_1h": _read_optional(output_root / "dukascopy_xau_1h.parquet"),
        "price_4h": _read_optional(output_root / "dukascopy_xau_4h.parquet"),
        "spread_report": _read_optional(output_root / "dukascopy_xau_spread_report.csv"),
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


def _write_md(path: Path, title: str, frame: pl.DataFrame) -> None:
    lines = [f"# {_safe_text(title)}", "", RESEARCH_WARNING, "", _frame_markdown(frame)]
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


def _output_paths(output_root: Path) -> dict[str, Path]:
    return {
        "loss_by_strategy_csv": output_root / "cme_wall_realistic_loss_by_strategy.csv",
        "loss_by_strategy_md": output_root / "cme_wall_realistic_loss_by_strategy.md",
        "loss_by_exit_reason_csv": output_root / "cme_wall_realistic_loss_by_exit_reason.csv",
        "loss_by_exit_reason_md": output_root / "cme_wall_realistic_loss_by_exit_reason.md",
        "cost_drag_csv": output_root / "cme_wall_realistic_cost_drag.csv",
        "cost_drag_md": output_root / "cme_wall_realistic_cost_drag.md",
        "loss_by_wall_type_csv": output_root / "cme_wall_realistic_loss_by_wall_type.csv",
        "loss_by_wall_type_md": output_root / "cme_wall_realistic_loss_by_wall_type.md",
        "loss_by_distance_csv": output_root / "cme_wall_realistic_loss_by_distance.csv",
        "loss_by_distance_md": output_root / "cme_wall_realistic_loss_by_distance.md",
        "loss_by_timeframe_csv": output_root / "cme_wall_realistic_loss_by_timeframe.csv",
        "loss_by_timeframe_md": output_root / "cme_wall_realistic_loss_by_timeframe.md",
        "loss_by_session_csv": output_root / "cme_wall_realistic_loss_by_session.csv",
        "loss_by_session_md": output_root / "cme_wall_realistic_loss_by_session.md",
        "loss_by_direction_csv": output_root / "cme_wall_realistic_loss_by_direction.csv",
        "loss_by_direction_md": output_root / "cme_wall_realistic_loss_by_direction.md",
        "fixability_csv": output_root / "cme_wall_realistic_fixability_audit.csv",
        "fixability_md": output_root / "cme_wall_realistic_fixability_audit.md",
        "loss_conclusion_md": output_root / "cme_wall_realistic_loss_conclusion.md",
        "next_action_csv": output_root / "cme_wall_realistic_next_action.csv",
        "next_action_md": output_root / "cme_wall_realistic_next_action.md",
    }


def _prepared_trade_schema() -> dict[str, Any]:
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
        "exit_reason_group": pl.Utf8,
        "cost_points": pl.Float64,
        "gross_minus_half_cost": pl.Float64,
        "gross_minus_zero_cost": pl.Float64,
        "wall_type_group": pl.Utf8,
        "distance_from_wall_at_entry": pl.Float64,
        "distance_bucket": pl.Utf8,
        "timeframe": pl.Utf8,
        "session_bucket": pl.Utf8,
    }


def _loss_by_strategy_schema() -> dict[str, Any]:
    return {
        "strategy_name": pl.Utf8,
        "trades": pl.Int64,
        "gross_profit": pl.Float64,
        "gross_loss": pl.Float64,
        "net_pnl": pl.Float64,
        "win_rate": pl.Float64,
        "avg_win": pl.Float64,
        "avg_loss": pl.Float64,
        "largest_loss": pl.Float64,
        "largest_win": pl.Float64,
        "loss_concentration_top_5_trades": pl.Float64,
        "loss_concentration_top_10_trades": pl.Float64,
        "drawdown_contribution": pl.Float64,
        "profit_factor": pl.Float64,
        "main_loss_driver": pl.Utf8,
    }


def _exit_reason_schema() -> dict[str, Any]:
    return {
        "exit_reason": pl.Utf8,
        "trade_count": pl.Int64,
        "net_pnl": pl.Float64,
        "avg_pnl": pl.Float64,
        "win_rate": pl.Float64,
        "avg_mae": pl.Float64,
        "avg_mfe": pl.Float64,
        "profit_factor": pl.Float64,
        "max_drawdown": pl.Float64,
        "interpretation": pl.Utf8,
        "notes": pl.Utf8,
    }


def _cost_drag_schema() -> dict[str, Any]:
    return {
        "strategy_name": pl.Utf8,
        "gross_pnl_before_cost": pl.Float64,
        "spread_cost_total": pl.Float64,
        "slippage_total": pl.Float64,
        "net_pnl_after_cost": pl.Float64,
        "cost_drag_ratio": pl.Float64,
        "trades_flipped_from_win_to_loss_by_cost": pl.Int64,
        "strategies_survive_zero_cost": pl.Boolean,
        "strategies_survive_half_cost": pl.Boolean,
        "strategies_survive_base_cost": pl.Boolean,
        "cost_explains_loss": pl.Boolean,
    }


def _wall_distance_schema(column: str) -> dict[str, Any]:
    return {
        column: pl.Utf8,
        "trade_count": pl.Int64,
        "net_pnl": pl.Float64,
        "avg_pnl": pl.Float64,
        "win_rate": pl.Float64,
        "avg_mae": pl.Float64,
        "avg_mfe": pl.Float64,
        "profit_factor": pl.Float64,
        "max_drawdown": pl.Float64,
        "interpretation": pl.Utf8,
        "notes": pl.Utf8,
    }


def _timeframe_schema() -> dict[str, Any]:
    return _wall_distance_schema("timeframe")


def _direction_schema() -> dict[str, Any]:
    return _wall_distance_schema("direction")


def _session_schema() -> dict[str, Any]:
    return {
        "trade_date": pl.Utf8,
        "session_date": pl.Utf8,
        "trades": pl.Int64,
        "net_pnl": pl.Float64,
        "max_drawdown": pl.Float64,
        "bad_day_count": pl.Int64,
        "clustered_loss_warning": pl.Boolean,
    }


def _fixability_schema() -> dict[str, Any]:
    return {
        "strategy_name": pl.Utf8,
        "main_failure_mode": pl.Utf8,
        "fixability": pl.Utf8,
        "recommended_next_action": pl.Utf8,
        "reason": pl.Utf8,
    }


def _next_action_schema() -> dict[str, Any]:
    return {
        "question": pl.Utf8,
        "answer": pl.Utf8,
        "evidence": pl.Utf8,
    }
