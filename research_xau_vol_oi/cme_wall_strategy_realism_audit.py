"""Realism audit for the CME wall strategy proxy ledger.

The prior performance layer intentionally produced a TradingView-style report,
but its rows are proxy rows derived from wall outcome windows. This audit checks
whether those rows can be treated as realistic strategy trades. The conservative
answer is usually no until entry, stop, target, and path checks are rebuilt from
preselected levels.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

import polars as pl


STRATEGY_NAMES = (
    "WALL_MAGNET_TO_NEAREST_WALL",
    "WALL_REJECTION_FADE",
    "WALL_ACCEPTANCE_CONTINUATION",
    "AVOID_DIRECT_WALL_TRADE",
    "SD_GRID_REJECTION_2SD",
    "COMBINED_CONSERVATIVE",
)
FINAL_RECOMMENDATIONS = (
    "PERFORMANCE_REPORT_STRUCTURE_READY",
    "PNL_PROXY_NOT_TRUSTWORTHY_YET",
    "ENTRY_EXIT_REWRITE_REQUIRED",
    "NEED_MORE_CME_DAYS",
    "NOT_READY_FOR_MONEY",
)
RESEARCH_WARNING = (
    "Research-only CME wall strategy realism audit. Proxy ledger rows are not "
    "real trades; PnL-style fields are diagnostic until entry, exit, stop, and "
    "intraday path logic are rebuilt."
)


@dataclass(frozen=True)
class CmeWallStrategyRealismAuditResult:
    """Generated realism audit artifacts."""

    ledger_reconciliation: pl.DataFrame
    trade_realism_audit: pl.DataFrame
    gross_loss_sanity: pl.DataFrame
    independent_event_performance: pl.DataFrame
    corrected_quality_grade: pl.DataFrame
    entry_exit_rewrite_plan: pl.DataFrame
    final_recommendation: str
    paths: dict[str, Path]


def run_cme_wall_strategy_realism_audit(
    *,
    output_dir: str | Path = "outputs",
    write_outputs: bool = True,
) -> CmeWallStrategyRealismAuditResult:
    """Run the proxy-ledger realism audit and write outputs."""

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    paths = _output_paths(output_root)
    inputs = _load_inputs(output_root)
    trades = _frame_input(inputs, "trades")
    performance = _frame_input(inputs, "performance_summary")
    journal = _frame_input(inputs, "outcome_journal")

    reconciliation = build_ledger_reconciliation(trades=trades, outcome_journal=journal)
    realism = build_trade_realism_audit(
        trades=trades,
        performance_summary=performance,
        reconciliation=reconciliation,
    )
    sanity = build_gross_loss_sanity_check(
        trades=trades,
        performance_summary=performance,
        realism_audit=realism,
    )
    independent = build_independent_event_performance(trades=trades)
    quality = build_corrected_quality_grade(
        trade_realism_audit=realism,
        gross_loss_sanity=sanity,
        independent_event_performance=independent,
    )
    rewrite = build_entry_exit_rewrite_plan()
    final = choose_final_recommendation(corrected_quality_grade=quality)
    result = CmeWallStrategyRealismAuditResult(
        ledger_reconciliation=reconciliation,
        trade_realism_audit=realism,
        gross_loss_sanity=sanity,
        independent_event_performance=independent,
        corrected_quality_grade=quality,
        entry_exit_rewrite_plan=rewrite,
        final_recommendation=final,
        paths=paths,
    )
    if write_outputs:
        write_cme_wall_strategy_realism_audit_outputs(result)
    return result


def build_ledger_reconciliation(
    *,
    trades: pl.DataFrame,
    outcome_journal: pl.DataFrame,
) -> pl.DataFrame:
    """Reconcile proxy ledger rows against distinct wall/session events."""

    trade_rows = trades.to_dicts() if not trades.is_empty() else []
    journal_rows = outcome_journal.to_dicts() if not outcome_journal.is_empty() else []
    wall_events = {
        _wall_event_key_from_journal(row)
        for row in journal_rows
        if _wall_event_key_from_journal(row)
    }
    if not wall_events:
        wall_events = {
            _wall_event_key_from_trade(row)
            for row in trade_rows
            if _wall_event_key_from_trade(row)
        }
    market_sessions = {
        _market_session(row.get("entry_timestamp"), row.get("trade_date"))
        for row in trade_rows
        if _market_session(row.get("entry_timestamp"), row.get("trade_date"))
    }
    duplicate_trade_ids = _duplicate_count([_text(row.get("trade_id")) for row in trade_rows])
    duplicate_strategy_wall_window = _duplicate_count(
        [
            "|".join(
                [
                    _text(row.get("strategy_name")),
                    _text(row.get("entry_timestamp")),
                    _text(row.get("exit_timestamp")),
                    _level_text(row.get("wall_level")),
                    _text(row.get("wall_type")),
                ]
            )
            for row in trade_rows
        ]
    )
    ledger_rows = len(trade_rows)
    unique_wall_events = len(wall_events)
    unique_sessions = len(market_sessions)
    rows_per_wall_event = ledger_rows / unique_wall_events if unique_wall_events else 0.0
    rows_per_session = ledger_rows / unique_sessions if unique_sessions else 0.0
    risk = _overcount_risk(
        rows_per_wall_event=rows_per_wall_event,
        rows_per_session=rows_per_session,
        duplicate_trade_ids=duplicate_trade_ids,
        duplicate_strategy_wall_window=duplicate_strategy_wall_window,
    )
    row = {
        "ledger_rows": ledger_rows,
        "unique_strategy_names": len({_text(row.get("strategy_name")) for row in trade_rows if _text(row.get("strategy_name"))}),
        "unique_trade_ids": len({_text(row.get("trade_id")) for row in trade_rows if _text(row.get("trade_id"))}),
        "unique_wall_events": unique_wall_events,
        "unique_snapshot_timestamps": len({_text(row.get("entry_timestamp")) for row in trade_rows if _text(row.get("entry_timestamp"))}),
        "unique_wall_levels": len({_level_text(row.get("wall_level")) for row in trade_rows if _float(row.get("wall_level")) is not None}),
        "unique_trade_dates": len({_text(row.get("trade_date")) for row in trade_rows if _text(row.get("trade_date"))}),
        "unique_market_sessions": unique_sessions,
        "rows_per_wall_event_avg": rows_per_wall_event,
        "rows_per_session_avg": rows_per_session,
        "duplicate_trade_id_count": duplicate_trade_ids,
        "duplicate_strategy_wall_window_rows": duplicate_strategy_wall_window,
        "overcount_risk": risk,
        "explanation_plain_english": _reconciliation_explanation(risk),
    }
    return _frame([_safe_row(row)], _reconciliation_schema())


def build_trade_realism_audit(
    *,
    trades: pl.DataFrame,
    performance_summary: pl.DataFrame,
    reconciliation: pl.DataFrame,
) -> pl.DataFrame:
    """Audit whether proxy rows have realistic trade ingredients."""

    all_strategies = _strategy_order(trades)
    rows = []
    overcount_risk = (
        reconciliation.row(0, named=True).get("overcount_risk")
        if not reconciliation.is_empty()
        else "HIGH"
    )
    perf = {row["strategy_name"]: row for row in performance_summary.to_dicts()} if not performance_summary.is_empty() else {}
    for strategy in all_strategies:
        group = _strategy_rows(trades, strategy)
        active = [row for row in group if _text(row.get("direction")) != "NONE"]
        gross_values = [_float(row.get("gross_pnl_points")) or 0.0 for row in active]
        gross_loss_rows = sum(1 for value in gross_values if value < 0)
        gross_win_rows = sum(1 for value in gross_values if value > 0)
        independent_count = len({_independent_event_key(row) for row in active if _independent_event_key(row)})
        has_entry = bool(active) and all(_parse_datetime(row.get("entry_timestamp")) for row in active)
        has_exit = bool(active) and all(_parse_datetime(row.get("exit_timestamp")) for row in active)
        has_direction = bool(active) and all(_text(row.get("direction")) in {"LONG", "SHORT", "RANGE"} for row in active)
        has_target = bool(active) and all(_float(row.get("target_price")) is not None for row in active)
        has_stop = bool(active) and all(_float(row.get("stop_price")) is not None for row in active)
        has_path = any(_text(row.get("data_quality")) == "INTRADAY_PATH_VALIDATED" for row in active)
        pf_defined = _profit_factor_defined(perf.get(strategy, {}), gross_loss_rows, gross_win_rows)
        leakage_risk = _future_leakage_risk(
            strategy=strategy,
            active_rows=active,
            gross_loss_rows=gross_loss_rows,
            gross_win_rows=gross_win_rows,
            has_path_validation=has_path,
        )
        grade = _realism_grade(
            trade_count=len(active),
            independent_count=independent_count,
            has_entry=has_entry,
            has_exit=has_exit,
            has_target=has_target,
            has_stop=has_stop,
            has_path=has_path,
            gross_loss_rows=gross_loss_rows,
            gross_win_rows=gross_win_rows,
            overcount_risk=_text(overcount_risk),
        )
        rows.append(
            {
                "strategy_name": strategy,
                "trade_count": len(active),
                "unique_independent_event_count": independent_count,
                "has_real_entry_timestamp": has_entry,
                "has_real_exit_timestamp": has_exit,
                "has_defined_direction": has_direction,
                "has_defined_target": has_target,
                "has_defined_stop": has_stop,
                "has_intraday_path_validation": has_path,
                "gross_loss_rows": gross_loss_rows,
                "gross_win_rows": gross_win_rows,
                "profit_factor_defined": pf_defined,
                "future_leakage_risk": leakage_risk,
                "realism_grade": grade,
                "reason": _realism_reason(
                    strategy=strategy,
                    grade=grade,
                    has_path=has_path,
                    gross_loss_rows=gross_loss_rows,
                    gross_win_rows=gross_win_rows,
                    independent_count=independent_count,
                ),
            }
        )
    return _frame([_safe_row(row) for row in rows], _realism_schema())


def build_gross_loss_sanity_check(
    *,
    trades: pl.DataFrame,
    performance_summary: pl.DataFrame,
    realism_audit: pl.DataFrame,
) -> pl.DataFrame:
    """Flag suspicious gross-loss and profit-factor conditions."""

    perf = {row["strategy_name"]: row for row in performance_summary.to_dicts()} if not performance_summary.is_empty() else {}
    realism = {row["strategy_name"]: row for row in realism_audit.to_dicts()} if not realism_audit.is_empty() else {}
    rows = []
    for strategy in _strategy_order(trades):
        group = [row for row in _strategy_rows(trades, strategy) if _text(row.get("direction")) != "NONE"]
        gross_values = [_float(row.get("gross_pnl_points")) or 0.0 for row in group]
        net_values = [_float(row.get("net_pnl_points")) or 0.0 for row in group]
        gross_loss_rows = sum(1 for value in gross_values if value < 0)
        gross_win_rows = sum(1 for value in gross_values if value > 0)
        row_perf = perf.get(strategy, {})
        row_realism = realism.get(strategy, {})
        win_rate = _float(row_perf.get("win_rate"))
        no_losing_rows = gross_win_rows > 0 and gross_loss_rows == 0
        unrealistic_win_rate = win_rate is not None and win_rate >= 0.95 and len(group) >= 30
        mae_implies_loss = any((_float(row.get("mae")) or 0.0) < 0 for row in group) and gross_loss_rows == 0
        guaranteed = no_losing_rows and gross_win_rows > 0 and _text(row_realism.get("has_intraday_path_validation")).lower() != "true"
        target_after_outcome = _target_chosen_from_future_outcome(strategy=strategy, rows=group)
        labels = _sanity_labels(
            no_losing_rows=no_losing_rows,
            unrealistic_win_rate=unrealistic_win_rate,
            mae_implies_loss=mae_implies_loss,
            guaranteed=guaranteed,
            target_after_outcome=target_after_outcome,
            has_path=_bool(row_realism.get("has_intraday_path_validation")),
            active_rows=len(group),
        )
        rows.append(
            {
                "strategy_name": strategy,
                "trade_count": len(group),
                "gross_loss_rows": gross_loss_rows,
                "gross_win_rows": gross_win_rows,
                "net_loss_rows": sum(1 for value in net_values if value < 0),
                "win_rate": win_rate,
                "no_losing_rows": no_losing_rows,
                "unrealistic_win_rate": unrealistic_win_rate,
                "mae_implies_loss_possible": mae_implies_loss,
                "exit_logic_guarantees_favorable_outcome": guaranteed,
                "target_chosen_from_future_wall_touch_result": target_after_outcome,
                "sanity_label": ";".join(labels) if labels else "OK_FOR_STRUCTURE_ONLY",
                "recommended_fix": _sanity_fix(labels),
            }
        )
    return _frame([_safe_row(row) for row in rows], _gross_loss_schema())


def build_independent_event_performance(*, trades: pl.DataFrame) -> pl.DataFrame:
    """Collapse wall-window rows into one row per independent event."""

    rows = []
    for strategy in _strategy_order(trades):
        active = [row for row in _strategy_rows(trades, strategy) if _text(row.get("direction")) != "NONE"]
        selected = _primary_rows_by_independent_event(active)
        pnl = [_float(row.get("net_pnl_points")) or 0.0 for row in selected]
        wins = [value for value in pnl if value > 0]
        losses = [value for value in pnl if value < 0]
        rows.append(
            {
                "strategy_name": strategy,
                "independent_event_count": len(selected),
                "net_pnl_proxy": sum(pnl),
                "win_rate": len(wins) / len(pnl) if pnl else None,
                "average_return": _mean(pnl),
                "gross_profit": sum(wins),
                "gross_loss": sum(losses),
                "profit_factor": _profit_factor(pnl),
                "max_drawdown_proxy": _max_drawdown(pnl),
                "sample_size_warning": len(selected) < 30,
            }
        )
    return _frame([_safe_row(row) for row in rows], _independent_schema())


def build_corrected_quality_grade(
    *,
    trade_realism_audit: pl.DataFrame,
    gross_loss_sanity: pl.DataFrame,
    independent_event_performance: pl.DataFrame,
) -> pl.DataFrame:
    """Downgrade proxy PnL when ledger realism checks fail."""

    sanity = {row["strategy_name"]: row for row in gross_loss_sanity.to_dicts()} if not gross_loss_sanity.is_empty() else {}
    independent = {
        row["strategy_name"]: row for row in independent_event_performance.to_dicts()
    } if not independent_event_performance.is_empty() else {}
    rows = []
    for realism in trade_realism_audit.to_dicts():
        strategy = _text(realism.get("strategy_name"))
        sanity_row = sanity.get(strategy, {})
        independent_row = independent.get(strategy, {})
        label = _corrected_label(realism, sanity_row, independent_row)
        rows.append(
            {
                "strategy_name": strategy,
                "corrected_quality_label": label,
                "pnl_proxy_trustworthy": False,
                "reason": _corrected_reason(label, realism, sanity_row, independent_row),
                "final_recommendation": _grade_recommendation(label),
            }
        )
    return _frame([_safe_row(row) for row in rows], _corrected_quality_schema())


def build_entry_exit_rewrite_plan() -> pl.DataFrame:
    """Create the next-test plan required before realistic PnL work."""

    rows = [
        {
            "strategy_name": "WALL_MAGNET_TO_NEAREST_WALL",
            "current_issue": "Current ledger can know the wall target outcome before the proxy row is scored.",
            "required_realistic_entry": "Entry must occur before wall touch using only snapshot-time ranked walls.",
            "required_realistic_exit": "Target wall must be preselected from the snapshot, then checked only on later candles.",
            "required_stop": "Fixed stop from entry, such as half-block or failed approach level.",
            "required_intraday_path_check": "Replay 15m or lower candles after entry; do not use precomputed target flags.",
            "required_cost_model": "Apply spread, fee, and slippage at entry and exit.",
            "recommended_next_test": "Path-level target-to-preselected-wall test with one trade per snapshot/session.",
        },
        {
            "strategy_name": "WALL_REJECTION_FADE",
            "current_issue": "Current rows are generated from already-labeled rejection outcomes.",
            "required_realistic_entry": "Entry after the rejection candle closes back inside the wall.",
            "required_realistic_exit": "Target midpoint, half-grid, or next preselected wall after entry.",
            "required_stop": "Stop beyond the wall with closed-candle invalidation.",
            "required_intraday_path_check": "Replay bars after confirmation; reject same-window hindsight.",
            "required_cost_model": "Apply spread, fee, and slippage at confirmation and exit.",
            "recommended_next_test": "Confirmation-candle event builder with path-level TP/SL resolution.",
        },
        {
            "strategy_name": "WALL_ACCEPTANCE_CONTINUATION",
            "current_issue": "Current rows are generated from already-labeled acceptance outcomes.",
            "required_realistic_entry": "Entry after acceptance close and hold are confirmed.",
            "required_realistic_exit": "Target next wall or low-volume gap selected before entry.",
            "required_stop": "Failed acceptance back inside the wall.",
            "required_intraday_path_check": "Replay post-confirmation candles only.",
            "required_cost_model": "Apply spread, fee, and slippage at confirmation and exit.",
            "recommended_next_test": "Acceptance-hold continuation test against next preselected wall.",
        },
        {
            "strategy_name": "AVOID_DIRECT_WALL_TRADE",
            "current_issue": "Filter-only behavior has no standalone PnL ledger.",
            "required_realistic_entry": "No entry; compare blocked candidate set against unblocked baseline.",
            "required_realistic_exit": "Use the baseline candidate's original exit logic.",
            "required_stop": "Use the baseline candidate's original stop rule.",
            "required_intraday_path_check": "Audit avoided loss and blocked winner counts by candidate.",
            "required_cost_model": "Use the same cost model as the baseline candidate set.",
            "recommended_next_test": "Filter-effect report on pre-existing candidate trades only.",
        },
        {
            "strategy_name": "SD_GRID_REJECTION_2SD",
            "current_issue": "Current row is aggregate realized-vol proxy evidence, not a path-level trade ledger.",
            "required_realistic_entry": "Entry after 2SD rejection closes back inside using precomputed bands.",
            "required_realistic_exit": "Target midpoint or full block selected at entry.",
            "required_stop": "3.5SD or half-block invalidation selected at entry.",
            "required_intraday_path_check": "Replay candles after the rejection close; true IV needs timestamp-safe CME IV.",
            "required_cost_model": "Apply spread, fee, and slippage per event.",
            "recommended_next_test": "Event-level SD/grid confirmation replay, then repeat with CME IV when available.",
        },
        {
            "strategy_name": "COMBINED_CONSERVATIVE",
            "current_issue": "Current rows combine already-resolved wall outcomes and simple cost hurdle logic.",
            "required_realistic_entry": "Entry only after independent confirmation and data-quality checks pass.",
            "required_realistic_exit": "Target and invalidation must be selected before the entry bar.",
            "required_stop": "Use the stricter of wall failure, half-block, or SD invalidation.",
            "required_intraday_path_check": "Replay post-entry path once per snapshot/session.",
            "required_cost_model": "Apply spread, fee, slippage, and stale-data blocks before scoring.",
            "recommended_next_test": "One-trade-per-session conservative replay with preselected wall and SD context.",
        },
    ]
    return _frame([_safe_row(row) for row in rows], _rewrite_schema())


def choose_final_recommendation(*, corrected_quality_grade: pl.DataFrame) -> str:
    """Choose the audit-level final recommendation."""

    if corrected_quality_grade.is_empty():
        return "NEED_MORE_CME_DAYS"
    labels = set(corrected_quality_grade.get_column("corrected_quality_label").to_list())
    if "INVALID_FOR_PNL" in labels:
        return "ENTRY_EXIT_REWRITE_REQUIRED"
    if "OVERCOUNTED_PROXY" in labels or "PILOT_CONTEXT_ONLY" in labels:
        return "PNL_PROXY_NOT_TRUSTWORTHY_YET"
    if "NEED_MORE_CME_DAYS" in labels:
        return "NEED_MORE_CME_DAYS"
    return "PERFORMANCE_REPORT_STRUCTURE_READY"


def write_cme_wall_strategy_realism_audit_outputs(
    result: CmeWallStrategyRealismAuditResult,
) -> None:
    """Write all audit CSV and Markdown artifacts."""

    _write_artifact(
        result.ledger_reconciliation,
        result.paths["ledger_reconciliation_csv"],
        result.paths["ledger_reconciliation_md"],
        "CME Wall Strategy Ledger Reconciliation",
    )
    _write_artifact(
        result.trade_realism_audit,
        result.paths["trade_realism_audit_csv"],
        result.paths["trade_realism_audit_md"],
        "CME Wall Strategy Trade Realism Audit",
    )
    _write_artifact(
        result.gross_loss_sanity,
        result.paths["gross_loss_sanity_csv"],
        result.paths["gross_loss_sanity_md"],
        "CME Wall Strategy Gross Loss Sanity Check",
    )
    _write_artifact(
        result.independent_event_performance,
        result.paths["independent_event_performance_csv"],
        result.paths["independent_event_performance_md"],
        "CME Wall Strategy Independent Event Performance",
    )
    _write_artifact(
        result.corrected_quality_grade,
        result.paths["corrected_quality_grade_csv"],
        result.paths["corrected_quality_grade_md"],
        "CME Wall Strategy Corrected Quality Grade",
    )
    _write_artifact(
        result.entry_exit_rewrite_plan,
        result.paths["entry_exit_rewrite_plan_csv"],
        result.paths["entry_exit_rewrite_plan_md"],
        "CME Wall Strategy Entry Exit Rewrite Plan",
    )


def cme_wall_strategy_realism_audit_report_lines(
    result: CmeWallStrategyRealismAuditResult | None,
) -> list[str]:
    """Return research_report.md lines for the realism audit."""

    if result is None:
        return ["## CME Wall Strategy Realism Audit", "", "Realism audit was not run."]
    return [
        "## CME Wall Strategy Realism Audit",
        "",
        RESEARCH_WARNING,
        "",
        f"- Final recommendation: `{result.final_recommendation}`",
        "",
        "## Ledger Count Reconciliation",
        "",
        _frame_markdown(result.ledger_reconciliation),
        "",
        "## Trade Realism Audit",
        "",
        _frame_markdown(result.trade_realism_audit),
        "",
        "## Gross Loss Sanity Check",
        "",
        _frame_markdown(result.gross_loss_sanity),
        "",
        "## Independent Event Performance",
        "",
        _frame_markdown(result.independent_event_performance),
        "",
        "## Corrected Quality Grade",
        "",
        _frame_markdown(result.corrected_quality_grade),
        "",
        "## Entry/Exit Rewrite Plan",
        "",
        _frame_markdown(result.entry_exit_rewrite_plan),
        "",
        "- Links: `outputs/cme_wall_strategy_ledger_reconciliation.csv`, "
        "`outputs/cme_wall_strategy_trade_realism_audit.csv`, "
        "`outputs/cme_wall_strategy_independent_event_performance.csv`, "
        "`outputs/cme_wall_strategy_corrected_quality_grade.csv`.",
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


def _load_inputs(output_root: Path) -> dict[str, pl.DataFrame]:
    return {
        "trades": _read_optional(output_root / "cme_wall_strategy_trades.csv"),
        "performance_summary": _read_optional(output_root / "cme_wall_strategy_performance_summary.csv"),
        "equity_curve": _read_optional(output_root / "cme_wall_strategy_equity_curve.csv"),
        "daily_pnl": _read_optional(output_root / "cme_wall_strategy_daily_pnl.csv"),
        "bad_days": _read_optional(output_root / "cme_wall_strategy_bad_days.csv"),
        "fee_stress": _read_optional(output_root / "cme_wall_strategy_fee_stress.csv"),
        "vs_hold": _read_optional(output_root / "cme_wall_strategy_vs_buy_hold.csv"),
        "quality_grade": _read_optional(output_root / "cme_wall_strategy_quality_grade.csv"),
        "outcome_journal": _read_optional(output_root / "fetched_cme_wall_outcome_journal.csv"),
        "rankings": _read_optional(output_root / "fetched_cme_wall_rankings.csv"),
        "price_15m": _read_optional(output_root / "dukascopy_xau_15m.parquet"),
        "price_1h": _read_optional(output_root / "dukascopy_xau_1h.parquet"),
        "price_4h": _read_optional(output_root / "dukascopy_xau_4h.parquet"),
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


def _strategy_order(trades: pl.DataFrame) -> list[str]:
    names = list(STRATEGY_NAMES)
    if not trades.is_empty() and "strategy_name" in trades.columns:
        for name in trades.get_column("strategy_name").unique().to_list():
            if _text(name) and _text(name) not in names:
                names.append(_text(name))
    return names


def _strategy_rows(trades: pl.DataFrame, strategy: str) -> list[dict[str, Any]]:
    if trades.is_empty() or "strategy_name" not in trades.columns:
        return []
    return trades.filter(pl.col("strategy_name") == strategy).to_dicts()


def _primary_rows_by_independent_event(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = _independent_event_key(row)
        if not key:
            key = f"aggregate|{_text(row.get('strategy_name'))}|{_text(row.get('trade_id'))}"
        current = by_key.get(key)
        if current is None or _primary_sort_key(row) < _primary_sort_key(current):
            by_key[key] = row
    return list(by_key.values())


def _primary_sort_key(row: dict[str, Any]) -> tuple[int, str]:
    bars = _int(row.get("bars_held"))
    if bars <= 0:
        bars = 999999
    return bars, _text(row.get("exit_timestamp"))


def _independent_event_key(row: dict[str, Any]) -> str:
    timestamp = _text(row.get("entry_timestamp"))
    level = _level_text(row.get("wall_level"))
    strategy = _text(row.get("strategy_name"))
    if not timestamp or not level:
        return ""
    return "|".join([strategy, timestamp, level, _market_session(timestamp, row.get("trade_date"))])


def _wall_event_key_from_trade(row: dict[str, Any]) -> str:
    timestamp = _text(row.get("entry_timestamp"))
    level = _level_text(row.get("wall_level"))
    wall_type = _text(row.get("wall_type"))
    if not timestamp or not level:
        return ""
    return "|".join([timestamp, level, wall_type])


def _wall_event_key_from_journal(row: dict[str, Any]) -> str:
    timestamp = _text(row.get("snapshot_timestamp"))
    level = _level_text(row.get("wall_level"))
    wall_type = _text(row.get("wall_type"))
    if not timestamp or not level:
        return ""
    return "|".join([timestamp, level, wall_type])


def _market_session(timestamp: Any, trade_date: Any = "") -> str:
    parsed = _parse_datetime(timestamp)
    date_text = _date_text(timestamp) or _text(trade_date)
    if not date_text:
        return ""
    if parsed is None:
        return f"{date_text}:UNKNOWN"
    if parsed.hour < 8:
        bucket = "ASIA"
    elif parsed.hour < 16:
        bucket = "EUROPE_US"
    else:
        bucket = "LATE_US"
    return f"{date_text}:{bucket}"


def _duplicate_count(values: Iterable[str]) -> int:
    counts: dict[str, int] = {}
    for value in values:
        if not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    return sum(count - 1 for count in counts.values() if count > 1)


def _overcount_risk(
    *,
    rows_per_wall_event: float,
    rows_per_session: float,
    duplicate_trade_ids: int,
    duplicate_strategy_wall_window: int,
) -> str:
    if duplicate_trade_ids > 0 or duplicate_strategy_wall_window > 0:
        return "HIGH"
    if rows_per_wall_event > 2.0 or rows_per_session > 50.0:
        return "HIGH"
    if rows_per_wall_event > 1.2 or rows_per_session > 10.0:
        return "MEDIUM"
    return "LOW"


def _reconciliation_explanation(risk: str) -> str:
    if risk == "HIGH":
        return (
            "Ledger rows are likely overcounting wall-window proxy observations as "
            "strategy trades. Treat PnL-style totals as not trustworthy."
        )
    if risk == "MEDIUM":
        return "Ledger rows are close to independent events but still need path-level validation."
    return "Ledger row counts are close to independent event counts."


def _profit_factor_defined(perf_row: dict[str, Any], gross_loss_rows: int, gross_win_rows: int) -> bool:
    if _float(perf_row.get("profit_factor")) is not None:
        return True
    return not (gross_win_rows > 0 and gross_loss_rows == 0)


def _future_leakage_risk(
    *,
    strategy: str,
    active_rows: list[dict[str, Any]],
    gross_loss_rows: int,
    gross_win_rows: int,
    has_path_validation: bool,
) -> str:
    if not active_rows:
        return "LOW"
    if strategy in {"WALL_MAGNET_TO_NEAREST_WALL", "WALL_REJECTION_FADE", "WALL_ACCEPTANCE_CONTINUATION"}:
        return "HIGH"
    if gross_win_rows > 0 and gross_loss_rows == 0:
        return "HIGH"
    if not has_path_validation:
        return "MEDIUM"
    return "LOW"


def _realism_grade(
    *,
    trade_count: int,
    independent_count: int,
    has_entry: bool,
    has_exit: bool,
    has_target: bool,
    has_stop: bool,
    has_path: bool,
    gross_loss_rows: int,
    gross_win_rows: int,
    overcount_risk: str,
) -> str:
    if trade_count == 0:
        return "WINDOW_EVENT_PROXY"
    if not (has_entry and has_exit and has_target and has_stop):
        return "INVALID_FOR_PNL"
    if gross_win_rows > 0 and gross_loss_rows == 0:
        return "OVERCOUNTED_PROXY"
    if overcount_risk == "HIGH" and trade_count > independent_count:
        return "OVERCOUNTED_PROXY"
    if not has_path:
        return "WINDOW_EVENT_PROXY"
    return "REALISTIC_PROXY"


def _realism_reason(
    *,
    strategy: str,
    grade: str,
    has_path: bool,
    gross_loss_rows: int,
    gross_win_rows: int,
    independent_count: int,
) -> str:
    if grade == "INVALID_FOR_PNL":
        return "Missing realistic entry, exit, target, stop, or timestamp fields."
    if grade == "OVERCOUNTED_PROXY":
        return "Rows are derived from outcome windows and need one-event path replay before PnL use."
    if not has_path:
        return "No intraday entry-to-exit path validation is present."
    if gross_win_rows > 0 and gross_loss_rows == 0:
        return "Gross losses are absent despite active proxy rows."
    return f"{strategy} has {independent_count} independent events after collapse."


def _target_chosen_from_future_outcome(strategy: str, rows: list[dict[str, Any]]) -> bool:
    if strategy in {"WALL_MAGNET_TO_NEAREST_WALL", "WALL_REJECTION_FADE", "WALL_ACCEPTANCE_CONTINUATION"}:
        return bool(rows)
    return any(
        "journal outcome" in _text(row.get("entry_reason")).lower()
        or "follow-through" in _text(row.get("exit_reason")).lower()
        for row in rows
    )


def _sanity_labels(
    *,
    no_losing_rows: bool,
    unrealistic_win_rate: bool,
    mae_implies_loss: bool,
    guaranteed: bool,
    target_after_outcome: bool,
    has_path: bool,
    active_rows: int,
) -> list[str]:
    labels: list[str] = []
    if active_rows == 0:
        return ["NEEDS_PATH_LEVEL_BACKTEST"]
    if no_losing_rows or unrealistic_win_rate:
        labels.append("INVALID_FOR_PROFIT_FACTOR")
    if guaranteed or target_after_outcome:
        labels.append("NEEDS_ENTRY_EXIT_REWRITE")
    if mae_implies_loss or not has_path:
        labels.append("NEEDS_PATH_LEVEL_BACKTEST")
    return list(dict.fromkeys(labels))


def _sanity_fix(labels: list[str]) -> str:
    if not labels:
        return "No gross-loss blocker found, but keep research-only."
    if "NEEDS_ENTRY_EXIT_REWRITE" in labels:
        return "Rewrite entries/exits from preselected levels and replay candles after entry."
    if "NEEDS_PATH_LEVEL_BACKTEST" in labels:
        return "Add intraday path-level TP/SL validation."
    return "Do not use profit-factor style metrics until losing rows can occur."


def _corrected_label(
    realism: dict[str, Any],
    sanity: dict[str, Any],
    independent: dict[str, Any],
) -> str:
    strategy = _text(realism.get("strategy_name"))
    sanity_label = _text(sanity.get("sanity_label"))
    realism_grade = _text(realism.get("realism_grade"))
    independent_count = _int(independent.get("independent_event_count"))
    if strategy == "AVOID_DIRECT_WALL_TRADE":
        return "FILTER_CANDIDATE"
    if "INVALID_FOR_PROFIT_FACTOR" in sanity_label or "NEEDS_ENTRY_EXIT_REWRITE" in sanity_label:
        return "INVALID_FOR_PNL"
    if realism_grade == "OVERCOUNTED_PROXY":
        return "OVERCOUNTED_PROXY"
    if realism_grade == "WINDOW_EVENT_PROXY":
        return "PILOT_CONTEXT_ONLY"
    if independent_count < 30:
        return "NEED_MORE_CME_DAYS"
    return "REALISTIC_BUT_SMALL_SAMPLE"


def _corrected_reason(
    label: str,
    realism: dict[str, Any],
    sanity: dict[str, Any],
    independent: dict[str, Any],
) -> str:
    if label == "INVALID_FOR_PNL":
        return "Gross-loss and future-outcome sanity checks fail; PnL-style metrics are not trustworthy."
    if label == "OVERCOUNTED_PROXY":
        return "Multiple wall-window rows are counted from the same independent wall/session event."
    if label == "FILTER_CANDIDATE":
        return "Filter-only logic should be scored by avoided loss and blocked winner counts, not standalone PnL."
    if label == "PILOT_CONTEXT_ONLY":
        return "This is aggregate or window-level context, not a realistic trade ledger."
    if label == "NEED_MORE_CME_DAYS":
        return f"Only {_int(independent.get('independent_event_count'))} independent events after collapse."
    return f"{_text(realism.get('strategy_name'))} still needs more forward data before validation."


def _grade_recommendation(label: str) -> str:
    if label == "INVALID_FOR_PNL":
        return "ENTRY_EXIT_REWRITE_REQUIRED"
    if label in {"OVERCOUNTED_PROXY", "PILOT_CONTEXT_ONLY", "FILTER_CANDIDATE"}:
        return "PNL_PROXY_NOT_TRUSTWORTHY_YET"
    if label == "NEED_MORE_CME_DAYS":
        return "NEED_MORE_CME_DAYS"
    return "PERFORMANCE_REPORT_STRUCTURE_READY"


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


def _mean(values: Iterable[float | int | None]) -> float | None:
    clean = [_float(value) for value in values]
    clean = [value for value in clean if value is not None]
    if not clean:
        return None
    return sum(clean) / len(clean)


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


def _level_text(value: Any) -> str:
    number = _float(value)
    if number is None:
        return ""
    return f"{number:.2f}"


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


def _write_artifact(frame: pl.DataFrame, csv_path: Path, md_path: Path, title: str) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    frame.write_csv(csv_path)
    lines = [
        f"# {title}",
        "",
        RESEARCH_WARNING,
        "",
        _frame_markdown(frame.head(100)),
    ]
    md_path.write_text(_safe_report_text("\n".join(lines)), encoding="utf-8")


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
    return {
        "ledger_reconciliation_csv": output_root / "cme_wall_strategy_ledger_reconciliation.csv",
        "ledger_reconciliation_md": output_root / "cme_wall_strategy_ledger_reconciliation.md",
        "trade_realism_audit_csv": output_root / "cme_wall_strategy_trade_realism_audit.csv",
        "trade_realism_audit_md": output_root / "cme_wall_strategy_trade_realism_audit.md",
        "gross_loss_sanity_csv": output_root / "cme_wall_strategy_gross_loss_sanity.csv",
        "gross_loss_sanity_md": output_root / "cme_wall_strategy_gross_loss_sanity.md",
        "independent_event_performance_csv": output_root
        / "cme_wall_strategy_independent_event_performance.csv",
        "independent_event_performance_md": output_root
        / "cme_wall_strategy_independent_event_performance.md",
        "corrected_quality_grade_csv": output_root
        / "cme_wall_strategy_corrected_quality_grade.csv",
        "corrected_quality_grade_md": output_root
        / "cme_wall_strategy_corrected_quality_grade.md",
        "entry_exit_rewrite_plan_csv": output_root
        / "cme_wall_strategy_entry_exit_rewrite_plan.csv",
        "entry_exit_rewrite_plan_md": output_root
        / "cme_wall_strategy_entry_exit_rewrite_plan.md",
    }


def _reconciliation_schema() -> dict[str, Any]:
    return {
        "ledger_rows": pl.Int64,
        "unique_strategy_names": pl.Int64,
        "unique_trade_ids": pl.Int64,
        "unique_wall_events": pl.Int64,
        "unique_snapshot_timestamps": pl.Int64,
        "unique_wall_levels": pl.Int64,
        "unique_trade_dates": pl.Int64,
        "unique_market_sessions": pl.Int64,
        "rows_per_wall_event_avg": pl.Float64,
        "rows_per_session_avg": pl.Float64,
        "duplicate_trade_id_count": pl.Int64,
        "duplicate_strategy_wall_window_rows": pl.Int64,
        "overcount_risk": pl.Utf8,
        "explanation_plain_english": pl.Utf8,
    }


def _realism_schema() -> dict[str, Any]:
    return {
        "strategy_name": pl.Utf8,
        "trade_count": pl.Int64,
        "unique_independent_event_count": pl.Int64,
        "has_real_entry_timestamp": pl.Boolean,
        "has_real_exit_timestamp": pl.Boolean,
        "has_defined_direction": pl.Boolean,
        "has_defined_target": pl.Boolean,
        "has_defined_stop": pl.Boolean,
        "has_intraday_path_validation": pl.Boolean,
        "gross_loss_rows": pl.Int64,
        "gross_win_rows": pl.Int64,
        "profit_factor_defined": pl.Boolean,
        "future_leakage_risk": pl.Utf8,
        "realism_grade": pl.Utf8,
        "reason": pl.Utf8,
    }


def _gross_loss_schema() -> dict[str, Any]:
    return {
        "strategy_name": pl.Utf8,
        "trade_count": pl.Int64,
        "gross_loss_rows": pl.Int64,
        "gross_win_rows": pl.Int64,
        "net_loss_rows": pl.Int64,
        "win_rate": pl.Float64,
        "no_losing_rows": pl.Boolean,
        "unrealistic_win_rate": pl.Boolean,
        "mae_implies_loss_possible": pl.Boolean,
        "exit_logic_guarantees_favorable_outcome": pl.Boolean,
        "target_chosen_from_future_wall_touch_result": pl.Boolean,
        "sanity_label": pl.Utf8,
        "recommended_fix": pl.Utf8,
    }


def _independent_schema() -> dict[str, Any]:
    return {
        "strategy_name": pl.Utf8,
        "independent_event_count": pl.Int64,
        "net_pnl_proxy": pl.Float64,
        "win_rate": pl.Float64,
        "average_return": pl.Float64,
        "gross_profit": pl.Float64,
        "gross_loss": pl.Float64,
        "profit_factor": pl.Float64,
        "max_drawdown_proxy": pl.Float64,
        "sample_size_warning": pl.Boolean,
    }


def _corrected_quality_schema() -> dict[str, Any]:
    return {
        "strategy_name": pl.Utf8,
        "corrected_quality_label": pl.Utf8,
        "pnl_proxy_trustworthy": pl.Boolean,
        "reason": pl.Utf8,
        "final_recommendation": pl.Utf8,
    }


def _rewrite_schema() -> dict[str, Any]:
    return {
        "strategy_name": pl.Utf8,
        "current_issue": pl.Utf8,
        "required_realistic_entry": pl.Utf8,
        "required_realistic_exit": pl.Utf8,
        "required_stop": pl.Utf8,
        "required_intraday_path_check": pl.Utf8,
        "required_cost_model": pl.Utf8,
        "recommended_next_test": pl.Utf8,
    }
