"""Pine strategy baseline and CME/Guru overlay lab.

This module is research-only. It records the supplied TradingView strategy
tester summary, builds a canonical trade-candidate contract, and tests whether
available CME/guru evidence can act as conservative filters. When a TradingView
List of Trades CSV is unavailable, the overlay backtest is explicitly marked as
PROXY_ONLY and uses a Python approximation of the Pine grid/ladder candidate
logic over local OHLC research data.
"""

from __future__ import annotations

import argparse
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl


BASELINE_REPORT_VALUES: dict[str, Any] = {
    "strategy": "14-Indicator Status Dashboard Strategy",
    "date_start": "2025-01-02",
    "date_end": "2026-05-25",
    "initial_capital": 100000.0,
    "net_pnl": -2584.16,
    "gross_profit": None,
    "gross_loss": None,
    "commissions": 2774.14,
    "total_trades": 939,
    "win_rate": 0.5208,
    "avg_win": 12.47,
    "avg_loss": -19.29,
    "avg_pnl": -2.75,
    "profit_factor": 0.702,
    "long_pnl": 105.60,
    "short_pnl": -2689.76,
    "long_trade_count": None,
    "short_trade_count": None,
    "max_drawdown": None,
    "sharpe": -1.35,
    "buy_hold_return": 0.7249,
    "fee_burden_per_trade": 2774.14 / 939.0,
    "main_failure_modes": (
        "high trade count; fee drag; weak short side; outlier losses; "
        "average loss larger than average win"
    ),
}
FORBIDDEN_REPORT_PHRASES = (
    "profitable",
    "safe to trade",
    "live ready",
    "live-ready",
    "paper ready",
    "paper-ready",
    "broker integration ready",
)
FINAL_LABELS = (
    "DO_NOT_TRADE_BASELINE",
    "USE_AS_WATCHLIST_ONLY",
    "USE_AS_DISCRETIONARY_FILTER_ONLY",
    "PAPER_TEST_AFTER_MORE_FORWARD_EVIDENCE",
    "READY_FOR_SHADOW_REVIEW",
)
TRADE_LIST_CANDIDATES = (
    "pine_trades.csv",
    "pine_trade_list.csv",
    "tradingview_trades.csv",
    "tradingview_list_of_trades.csv",
    "TradingView_List_of_Trades.csv",
    "List of Trades.csv",
)
OHLC_CANDIDATES = (
    "xau_feature_table.parquet",
    "xau_spot_backfilled.parquet",
    "cme_canonical_xau_spot_price.parquet",
    "cme_canonical_futures_price.parquet",
)


@dataclass(frozen=True)
class PineProxyConfig:
    """Formation-period Pine proxy constants copied from the uploaded strategy."""

    grid_sd_len: int = 50
    entry_sd: float = 1.25
    stop_sd: float = 2.25
    no_trade_sd: float = 0.50
    don_len: int = 20
    sweep_lookback: int = 20
    ladder_enabled: bool = True
    pyramiding: int = 3
    target_offset_sd: float = 0.20
    soft_stop_sd: float = 3.15
    emergency_stop_sd: float = 3.60
    commission_rate: float = 0.0005
    slippage_points_per_side: float = 1.0
    fee_buffer_points: float = 0.0
    open_distance_limit_points: float = 25.0
    max_horizon_bars: int = 16
    min_warmup_bars: int = 102


@dataclass(frozen=True)
class PineOverlayLabResult:
    """All generated Pine overlay lab frames."""

    baseline_summary: pl.DataFrame
    trade_candidates: pl.DataFrame
    filter_plan: pl.DataFrame
    fee_outlier_audit: pl.DataFrame
    overlay_summary: pl.DataFrame
    formation_test: pl.DataFrame
    fast_start_decision: pl.DataFrame
    trade_list_available: bool
    data_mode: str


def run_pine_strategy_overlay_lab(
    *,
    output_dir: str | Path = "outputs",
    pine_path: str | Path | None = "Tradingview.pine",
    trade_list_path: str | Path | None = None,
    price_path: str | Path | None = None,
) -> PineOverlayLabResult:
    """Run the Pine baseline + CME/Guru overlay lab and write reports."""

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    pine_text = _read_optional_text(Path(pine_path)) if pine_path is not None else ""
    inputs = load_overlay_inputs(output_root)
    discovered_trade_list = discover_trade_list(output_root, trade_list_path=trade_list_path)
    trade_list_available = discovered_trade_list is not None

    baseline = build_baseline_summary(pine_text=pine_text)
    if trade_list_available:
        raw_trades = _load_optional(discovered_trade_list)
        candidates = normalize_pine_trade_list(raw_trades)
        data_mode = "ACTUAL_TRADE_LIST"
    else:
        selected_price = Path(price_path) if price_path is not None else discover_price_path(output_root)
        price = _load_optional(selected_price) if selected_price is not None else pl.DataFrame()
        candidates = build_proxy_trade_candidates(price, config=PineProxyConfig())
        data_mode = "PROXY_ONLY"
        write_trade_list_missing_request(output_root / "pine_trade_list_missing_request.md")

    candidates = enrich_trade_candidates_with_overlays(candidates, inputs)
    filter_plan = build_filter_overlay_plan(trade_list_available=trade_list_available, data_mode=data_mode)
    fee_audit = build_fee_outlier_audit(baseline, candidates)
    overlay_summary = run_overlay_backtest(candidates, data_mode=data_mode)
    sensitivity = build_sd_grid_sensitivity(
        _load_optional(discover_price_path(output_root)),
        inputs=inputs,
    )
    formation = build_formation_test(candidates, overlay_summary, sensitivity)
    decision = build_fast_start_decision(
        baseline,
        overlay_summary,
        formation,
        trade_list_available=trade_list_available,
    )

    write_lab_outputs(
        output_root=output_root,
        result=PineOverlayLabResult(
            baseline_summary=baseline,
            trade_candidates=candidates,
            filter_plan=filter_plan,
            fee_outlier_audit=fee_audit,
            overlay_summary=overlay_summary,
            formation_test=formation,
            fast_start_decision=decision,
            trade_list_available=trade_list_available,
            data_mode=data_mode,
        ),
    )
    return PineOverlayLabResult(
        baseline_summary=baseline,
        trade_candidates=candidates,
        filter_plan=filter_plan,
        fee_outlier_audit=fee_audit,
        overlay_summary=overlay_summary,
        formation_test=formation,
        fast_start_decision=decision,
        trade_list_available=trade_list_available,
        data_mode=data_mode,
    )


def load_overlay_inputs(output_root: Path) -> dict[str, pl.DataFrame]:
    """Load optional CME/guru overlay inputs with empty-frame fallbacks."""

    paths = {
        "guru_rule_library": output_root / "guru_rule_library.csv",
        "forward_rule_governance": output_root / "forward_rule_governance.csv",
        "next_rule_focus_list": output_root / "next_rule_focus_list.csv",
        "forward_event_level_outcomes": output_root / "forward_event_level_outcomes.csv",
        "forward_rule_event_evidence": output_root / "forward_rule_event_evidence.csv",
        "cme_canonical_option_oi_by_strike": output_root
        / "cme_canonical_option_oi_by_strike.parquet",
        "xau_basis_backfilled": output_root / "xau_basis_backfilled.parquet",
        "xau_spot_backfilled": output_root / "xau_spot_backfilled.parquet",
        "current_week_cme_guru_replay": output_root / "current_week_cme_guru_replay.csv",
        "same_day_filter_evidence_after_metadata": output_root
        / "same_day_filter_evidence_after_metadata.csv",
    }
    return {name: _load_optional(path) for name, path in paths.items()}


def discover_trade_list(
    output_root: Path,
    *,
    trade_list_path: str | Path | None = None,
) -> Path | None:
    """Find a TradingView List of Trades CSV if the user exported one."""

    if trade_list_path is not None:
        path = Path(trade_list_path)
        return path if path.exists() else None
    search_roots = [output_root, Path(".")]
    for root in search_roots:
        for name in TRADE_LIST_CANDIDATES:
            candidate = root / name
            if candidate.exists():
                return candidate
    for root in search_roots:
        if not root.exists():
            continue
        for candidate in root.glob("*trades*.csv"):
            lower = candidate.name.lower()
            if "pine" in lower or "tradingview" in lower or "list" in lower:
                return candidate
    return None


def discover_price_path(output_root: Path) -> Path | None:
    """Pick the best local OHLC proxy for the Python Pine-logic exploration."""

    for name in OHLC_CANDIDATES:
        candidate = output_root / name
        if candidate.exists():
            return candidate
    return None


def build_baseline_summary(*, pine_text: str = "") -> pl.DataFrame:
    """Build the supplied TradingView baseline summary frame."""

    values = dict(BASELINE_REPORT_VALUES)
    values["pine_script_present"] = bool(pine_text.strip())
    values["pine_script_features_detected"] = "|".join(detect_pine_features(pine_text))
    values["baseline_status_label"] = "DO_NOT_TRADE_BASELINE" if values["net_pnl"] < 0 else "RESEARCH_REVIEW_ONLY"
    values["research_only"] = True
    return _rows_frame([values], _baseline_schema())


def detect_pine_features(pine_text: str) -> list[str]:
    """Extract coarse feature names from the uploaded Pine script."""

    checks = {
        "14_indicator_status_dashboard": "GROUP_ADAPT",
        "dynamic_grid_range_engine": "GROUP_GRID",
        "three_level_sd_ladder_grid": "GROUP_LADDER",
        "fee_aware_filter": "useFeeAwareSizing",
        "asymmetric_bias_filter": "enableAsymBias",
        "sweep_confirmation": "useSweepConfirmation",
        "atr_donchian_env_exits": "exitMode",
    }
    return [feature for feature, token in checks.items() if token in pine_text]


def normalize_pine_trade_list(frame: pl.DataFrame) -> pl.DataFrame:
    """Normalize a TradingView trade export or canonical synthetic trade frame."""

    if frame.is_empty():
        return _empty_trade_candidates()
    rows: list[dict[str, Any]] = []
    columns = {_normal_column(column): column for column in frame.columns}
    for index, raw in enumerate(frame.to_dicts(), start=1):
        direction = _direction_from_raw(_get_first(raw, columns, ("direction", "type", "side")))
        if direction not in {"long", "short"}:
            continue
        entry = _float_or_none(
            _get_first(raw, columns, ("entry_price", "entry", "entryprice", "price"))
        )
        exit_price = _float_or_none(
            _get_first(raw, columns, ("exit_price", "exit", "exitprice", "exitpriceusd"))
        )
        pnl = _float_or_none(
            _get_first(raw, columns, ("pnl_after_cost", "net_profit", "profit", "pnl"))
        )
        if pnl is None:
            continue
        timestamp = _timestamp_text(
            _get_first(raw, columns, ("timestamp", "entry_time", "datetime", "date_time", "time"))
        )
        trade_id = str(_get_first(raw, columns, ("trade_id", "trade", "trade_no")) or index)
        fee_paid = _float_or_none(_get_first(raw, columns, ("fee_paid", "commission", "commissions")))
        rows.append(
            _candidate_row(
                timestamp=timestamp,
                trade_id=f"tv_{trade_id}",
                direction=direction,
                entry_price=entry,
                exit_price=exit_price,
                pnl=pnl + (fee_paid or 0.0),
                pnl_after_cost=pnl,
                bars_in_trade=int(_float_or_none(_get_first(raw, columns, ("bars_in_trade", "bars"))) or 0),
                entry_reason="TRADINGVIEW_EXPORTED_TRADE",
                exit_reason=str(_get_first(raw, columns, ("exit_reason", "exit_signal")) or ""),
                pine_signal_score=None,
                grid_state=str(_get_first(raw, columns, ("grid_state",)) or ""),
                ladder_state=str(_get_first(raw, columns, ("ladder_state",)) or ""),
                sd_position=_float_or_none(_get_first(raw, columns, ("sd_position", "sigma_position"))),
                regime_state=str(_get_first(raw, columns, ("regime_state",)) or ""),
                trend_filter_state=str(_get_first(raw, columns, ("trend_filter_state",)) or ""),
                sweep_confirmation=_bool_value(
                    _get_first(raw, columns, ("sweep_confirmation", "sweep"))
                ),
                fee_hurdle_passed=True,
                cme_filter_state="NOT_EVALUATED",
                guru_filter_state="NOT_EVALUATED",
                final_allow_trade=True,
                session_date=_date_text(timestamp),
                expected_move=None,
                round_trip_cost=fee_paid,
                source_mode="ACTUAL_TRADE_LIST",
            )
        )
    return _rows_frame(rows, _trade_candidate_schema())


def build_proxy_trade_candidates(
    price_frame: pl.DataFrame,
    *,
    config: PineProxyConfig,
) -> pl.DataFrame:
    """Approximate the Pine grid/ladder candidate logic over local OHLC data."""

    price_rows = _standardize_price_rows(price_frame)
    if len(price_rows) <= max(config.min_warmup_bars, config.grid_sd_len + 2):
        return _empty_trade_candidates()

    candidates: list[dict[str, Any]] = []
    last_trade_index = -10_000
    for index in range(len(price_rows) - 1):
        if index < max(config.min_warmup_bars, config.grid_sd_len + 2, config.don_len + 2):
            continue
        row = price_rows[index]
        window = price_rows[index - config.don_len + 1 : index + 1]
        close_window = [float(item["close"]) for item in price_rows[index - config.grid_sd_len + 1 : index + 1]]
        grid_dev = _stddev(close_window)
        if grid_dev <= 0:
            continue
        don_upper = max(float(item["high"]) for item in window)
        don_lower = min(float(item["low"]) for item in window)
        grid_mid = (don_upper + don_lower) * 0.5
        levels = _grid_levels(grid_mid=grid_mid, grid_dev=grid_dev, config=config)
        sigma = (float(row["close"]) - grid_mid) / grid_dev
        if levels["lower_no_trade"] <= float(row["close"]) <= levels["upper_no_trade"]:
            continue
        if index - last_trade_index < 5:
            continue
        low_trap, high_trap = _sweep_flags(price_rows, index, config=config)
        rows_to_add = _candidate_signals_for_row(
            row=row,
            price_rows=price_rows,
            index=index,
            levels=levels,
            sigma=sigma,
            low_trap=low_trap,
            high_trap=high_trap,
            config=config,
        )
        if rows_to_add:
            candidates.extend(rows_to_add)
            last_trade_index = index
    return _rows_frame(candidates, _trade_candidate_schema())


def enrich_trade_candidates_with_overlays(
    candidates: pl.DataFrame,
    inputs: dict[str, pl.DataFrame],
) -> pl.DataFrame:
    """Attach CME/guru filter states and final allow flags to candidates."""

    if candidates.is_empty():
        return candidates
    cme_by_date = _rows_by_date(inputs.get("current_week_cme_guru_replay", pl.DataFrame()), "trade_date")
    guru_by_date = _rows_by_date(
        inputs.get("same_day_filter_evidence_after_metadata", pl.DataFrame()),
        "resolved_market_session_date",
    )
    rows = []
    for raw in candidates.to_dicts():
        session_date = _date_text(raw.get("session_date") or raw.get("timestamp"))
        cme_row = cme_by_date.get(session_date, {})
        guru_row = guru_by_date.get(session_date, {})
        cme_allowed, cme_state = cme_wall_filter_allows(raw, cme_row, return_state=True)
        guru_allowed, guru_state = guru_no_trade_filter_allows(raw, guru_row, return_state=True)
        fee_allowed = fee_hurdle_allows(
            _float_or_none(raw.get("expected_move")),
            _float_or_none(raw.get("round_trip_cost")),
            buffer_points=0.25,
        )
        open_allowed = open_distance_filter_allows(raw)
        outlier_allowed = outlier_guard_allows(raw)
        final_allow = cme_allowed and guru_allowed and fee_allowed and open_allowed and outlier_allowed
        rows.append(
            {
                **raw,
                "fee_hurdle_passed": fee_allowed,
                "cme_filter_state": cme_state,
                "guru_filter_state": guru_state,
                "final_allow_trade": final_allow,
            }
        )
    return _rows_frame(rows, _trade_candidate_schema())


def fee_hurdle_allows(
    expected_move: float | None,
    round_trip_cost: float | None,
    *,
    buffer_points: float = 0.0,
) -> bool:
    """Allow only when expected movement clears costs plus buffer."""

    if expected_move is None or round_trip_cost is None:
        return False
    return expected_move > round_trip_cost + buffer_points


def cme_wall_filter_allows(
    trade: dict[str, Any],
    cme_row: dict[str, Any],
    *,
    strong_wall_threshold: float = 0.20,
    wall_proximity_points: float = 8.0,
    return_state: bool = False,
) -> bool | tuple[bool, str]:
    """Block candidates that point directly into a nearby strong CME wall."""

    if not cme_row:
        return (True, "NO_CME_CONTEXT") if return_state else True
    direction = str(trade.get("direction") or "")
    entry = _float_or_none(trade.get("entry_price"))
    wall_score = _float_or_none(cme_row.get("wall_score")) or 0.0
    if entry is None or wall_score < strong_wall_threshold:
        return (True, "CME_WEAK_OR_NO_NEAR_WALL") if return_state else True
    above = _float_or_none(cme_row.get("nearest_wall_above_price"))
    below = _float_or_none(cme_row.get("nearest_wall_below_price"))
    accepted = _bool_value(cme_row.get("accepted_wall"))
    rejected = _bool_value(cme_row.get("rejected_wall"))
    if direction == "long" and above is not None and 0 <= above - entry <= wall_proximity_points:
        allowed = accepted
        state = "ALLOW_ACCEPTED_WALL_BREAK_LONG" if allowed else "BLOCK_LONG_INTO_STRONG_WALL"
        return (allowed, state) if return_state else allowed
    if direction == "short" and below is not None and 0 <= entry - below <= wall_proximity_points:
        allowed = accepted
        state = "ALLOW_ACCEPTED_WALL_BREAK_SHORT" if allowed else "BLOCK_SHORT_INTO_STRONG_WALL"
        return (allowed, state) if return_state else allowed
    if rejected:
        return (True, "ALLOW_REJECTION_CONTEXT") if return_state else True
    return (True, "CME_NO_BLOCK") if return_state else True


def guru_no_trade_filter_allows(
    trade: dict[str, Any],
    guru_row: dict[str, Any],
    *,
    no_trade_sd: float = 0.50,
    return_state: bool = False,
) -> bool | tuple[bool, str]:
    """Block middle-range, same-day avoid, and stale-data contexts."""

    sigma = _float_or_none(trade.get("sd_position"))
    if sigma is not None and abs(sigma) <= no_trade_sd:
        return (False, "BLOCK_NO_TRADE_MIDDLE_RANGE") if return_state else False
    if not guru_row:
        return (True, "NO_GURU_CONTEXT") if return_state else True
    active = _bool_value(guru_row.get("no_trade_filter_active"))
    evidence = str(guru_row.get("evidence_status") or "")
    names = str(guru_row.get("active_filter_logic_names") or "")
    stale = "Stale Data" in names or "STALE" in names.upper()
    if active and evidence == "TIMING_CONFIRMED":
        return (False, "BLOCK_GURU_SAME_DAY_AVOID") if return_state else False
    if stale:
        return (False, "BLOCK_STALE_DATA_PERIOD") if return_state else False
    return (True, "GURU_NO_BLOCK") if return_state else True


def open_distance_filter_allows(
    trade: dict[str, Any],
    *,
    open_distance_limit_points: float = 25.0,
) -> bool:
    """Block chase candidates too far from the session open."""

    entry = _float_or_none(trade.get("entry_price"))
    session_open = _float_or_none(trade.get("session_open"))
    if entry is None or session_open is None:
        return True
    return abs(entry - session_open) <= open_distance_limit_points


def outlier_guard_allows(
    trade: dict[str, Any],
    *,
    max_abs_sd_position: float = 3.15,
) -> bool:
    """Block candidates already beyond the soft adverse grid threshold."""

    sigma = _float_or_none(trade.get("sd_position"))
    if sigma is None:
        return True
    return abs(sigma) <= max_abs_sd_position


def build_filter_overlay_plan(*, trade_list_available: bool, data_mode: str) -> pl.DataFrame:
    """Create the requested overlay test plan."""

    rows = [
        _plan_row("A", "direction_filter", "baseline all trades", data_mode, True),
        _plan_row("A", "direction_filter", "long-only", data_mode, True),
        _plan_row("A", "direction_filter", "short-only", data_mode, True),
        _plan_row("A", "direction_filter", "long with normal filter", data_mode, True),
        _plan_row("A", "direction_filter", "short with extra confirmation", data_mode, True),
        _plan_row("B", "fee_hurdle_filter", "expected range above cost plus buffer", data_mode, True),
        _plan_row("C", "guru_no_trade_filter", "middle range / same-day avoid / stale data", data_mode, True),
        _plan_row("D", "price_action_confirmation", "acceptance breakout / rejection after touch", data_mode, True),
        _plan_row("E", "cme_wall_filter", "block candidates directly into strong walls", data_mode, True),
        _plan_row("F", "open_distance_filter", "block chase candidates far from open", data_mode, True),
        _plan_row("G", "outlier_loss_guard", "pyramiding 3 vs 1 and ladder on/off", data_mode, True),
        _plan_row("H", "sd_grid_sensitivity", "formation/test gridSdLen-entrySd-noTradeSd", data_mode, True),
    ]
    if not trade_list_available:
        rows.append(
            _plan_row(
                "TRADE_LIST",
                "actual_trade_overlay",
                "requires TradingView List of Trades CSV for exact trade-level overlay",
                "MISSING_ACTUAL_TRADE_LIST",
                False,
            )
        )
    return _rows_frame(rows, _filter_plan_schema())


def build_fee_outlier_audit(baseline: pl.DataFrame, candidates: pl.DataFrame) -> pl.DataFrame:
    """Calculate fee burden and outlier diagnostics."""

    row = baseline.row(0, named=True)
    total_trades = int(row["total_trades"])
    net_pnl = float(row["net_pnl"])
    commissions = float(row["commissions"])
    commission_per_trade = commissions / total_trades if total_trades else 0.0
    gross_edge_before_cost = (net_pnl + commissions) / total_trades if total_trades else 0.0
    if candidates.is_empty():
        low_expectancy_count = 0
        outlier_count = _estimate_outlier_loss_count(row)
        contribution = abs(net_pnl)
        removing_worst = "hindsight_only_not_realistic"
    else:
        low_expectancy_count = candidates.filter(~pl.col("fee_hurdle_passed")).height
        pnl = [_float_or_zero(value) for value in candidates.get_column("pnl_after_cost").to_list()]
        threshold = _outlier_loss_threshold(pnl)
        outliers = [value for value in pnl if value <= threshold]
        outlier_count = len(outliers)
        contribution = abs(sum(outliers))
        removing_worst = (
            "would_be_positive_but_hindsight_only"
            if net_pnl + contribution > 0
            else "would_not_fully_repair_baseline"
        )
    rows = [
        {
            "commission_per_trade": commission_per_trade,
            "gross_edge_before_cost_estimate": gross_edge_before_cost,
            "fee_drag_ratio": commissions / max(abs(net_pnl) + commissions, 1.0),
            "low_expected_move_trade_count": low_expectancy_count,
            "outlier_loss_count": outlier_count,
            "outlier_loss_contribution": contribution,
            "removing_worst_outliers_effect": removing_worst,
            "realistic_removal_warning": "Worst-trade removal is a hindsight diagnostic, not a deployable rule.",
            "research_only": True,
        }
    ]
    return _rows_frame(rows, _fee_audit_schema())


def run_overlay_backtest(candidates: pl.DataFrame, *, data_mode: str) -> pl.DataFrame:
    """Apply requested overlay policies to normalized candidates."""

    policies = {
        "baseline_all_trades": lambda row: True,
        "long_only": lambda row: row.get("direction") == "long",
        "short_only": lambda row: row.get("direction") == "short",
        "long_with_normal_filter": lambda row: row.get("direction") == "long"
        and _bool_value(row.get("fee_hurdle_passed")),
        "short_with_extra_confirmation": lambda row: row.get("direction") == "short"
        and _bool_value(row.get("fee_hurdle_passed"))
        and "BLOCK" not in str(row.get("cme_filter_state") or "")
        and "BLOCK" not in str(row.get("guru_filter_state") or ""),
        "fee_hurdle_filter": lambda row: _bool_value(row.get("fee_hurdle_passed")),
        "guru_no_trade_filter": lambda row: "BLOCK" not in str(row.get("guru_filter_state") or ""),
        "cme_wall_filter": lambda row: "BLOCK" not in str(row.get("cme_filter_state") or ""),
        "open_distance_filter": open_distance_filter_allows,
        "outlier_loss_guard": outlier_guard_allows,
        "all_filters": lambda row: _bool_value(row.get("final_allow_trade")),
    }
    rows = []
    raw_rows = candidates.to_dicts() if not candidates.is_empty() else []
    for policy, predicate in policies.items():
        allowed = [row for row in raw_rows if predicate(row)]
        blocked = [row for row in raw_rows if not predicate(row)]
        rows.append(_summary_for_policy(policy, allowed, blocked, all_rows=raw_rows, data_mode=data_mode))
    return _rows_frame(rows, _overlay_summary_schema())


def build_sd_grid_sensitivity(
    price_frame: pl.DataFrame,
    *,
    inputs: dict[str, pl.DataFrame] | None = None,
) -> pl.DataFrame:
    """Evaluate SD grid sensitivity with formation-only selection."""

    if price_frame.is_empty():
        return _empty_sensitivity()
    overlay_inputs = inputs or {}
    rows = []
    for grid_sd_len in (20, 30, 50, 80):
        for entry_sd in (1.0, 1.25, 1.5, 2.0):
            for no_trade_sd in (0.25, 0.50, 0.75):
                config = PineProxyConfig(
                    grid_sd_len=grid_sd_len,
                    entry_sd=entry_sd,
                    no_trade_sd=no_trade_sd,
                )
                candidates = enrich_trade_candidates_with_overlays(
                    build_proxy_trade_candidates(price_frame, config=config),
                    overlay_inputs,
                )
                row = _sensitivity_row(candidates, config)
                rows.append(row)
    frame = _rows_frame(rows, _sensitivity_schema())
    if frame.is_empty():
        return frame
    formation_best = (
        frame.sort(["formation_avg_pnl", "formation_trade_count"], descending=[True, True])
        .head(1)
        .row(0, named=True)
    )
    full_best = (
        frame.sort(["full_sample_avg_pnl", "full_sample_trade_count"], descending=[True, True])
        .head(1)
        .row(0, named=True)
    )
    return frame.with_columns(
        (
            (pl.col("grid_sd_len") == formation_best["grid_sd_len"])
            & (pl.col("entry_sd") == formation_best["entry_sd"])
            & (pl.col("no_trade_sd") == formation_best["no_trade_sd"])
        ).alias("selected_for_test"),
        (
            (pl.col("grid_sd_len") == full_best["grid_sd_len"])
            & (pl.col("entry_sd") == full_best["entry_sd"])
            & (pl.col("no_trade_sd") == full_best["no_trade_sd"])
        ).alias("is_full_sample_best"),
        pl.lit("formation_only").alias("selection_basis"),
    )


def build_formation_test(
    candidates: pl.DataFrame,
    overlay_summary: pl.DataFrame,
    sensitivity: pl.DataFrame,
) -> pl.DataFrame:
    """Build policy and SD-parameter formation/test diagnostics."""

    rows = []
    if not candidates.is_empty():
        formation_rows, test_rows = _split_candidate_rows(candidates.to_dicts())
        policy_names = [row["policy"] for row in overlay_summary.to_dicts()]
        policy_predicates = _policy_predicates()
        formation_scores = []
        for policy in policy_names:
            predicate = policy_predicates.get(policy, lambda row: True)
            formation_allowed = [row for row in formation_rows if predicate(row)]
            test_allowed = [row for row in test_rows if predicate(row)]
            formation_avg = _avg_pnl(formation_allowed)
            test_avg = _avg_pnl(test_allowed)
            formation_scores.append((policy, formation_avg))
            rows.append(
                {
                    "experiment_type": "overlay_policy",
                    "policy": policy,
                    "grid_sd_len": None,
                    "entry_sd": None,
                    "no_trade_sd": None,
                    "formation_trade_count": len(formation_allowed),
                    "test_trade_count": len(test_allowed),
                    "formation_avg_pnl": formation_avg,
                    "test_avg_pnl": test_avg,
                    "full_sample_trade_count": sum(1 for row in candidates.to_dicts() if predicate(row)),
                    "full_sample_avg_pnl": _avg_pnl([row for row in candidates.to_dicts() if predicate(row)]),
                    "selected_for_test": False,
                    "is_full_sample_best": False,
                    "selection_basis": "formation_only",
                    "sample_size_warning": len(test_allowed) < 30,
                    "leakage_warning": False,
                }
            )
        if formation_scores:
            best_policy = max(formation_scores, key=lambda item: item[1])[0]
            rows = [
                {**row, "selected_for_test": row["policy"] == best_policy}
                if row["experiment_type"] == "overlay_policy"
                else row
                for row in rows
            ]
    for row in sensitivity.to_dicts():
        rows.append({"experiment_type": "sd_grid_sensitivity", "policy": "pine_proxy_grid", **row})
    return _rows_frame(rows, _formation_schema())


def build_fast_start_decision(
    baseline: pl.DataFrame,
    overlay_summary: pl.DataFrame,
    formation: pl.DataFrame,
    *,
    trade_list_available: bool,
) -> pl.DataFrame:
    """Return conservative fast-start labels without execution readiness claims."""

    baseline_row = baseline.row(0, named=True)
    baseline_label = "DO_NOT_TRADE_BASELINE" if float(baseline_row["net_pnl"]) < 0 else "USE_AS_WATCHLIST_ONLY"
    best_test = _best_test_row(formation)
    overlay_improved = bool(best_test) and _float_or_zero(best_test.get("test_avg_pnl")) > 0.0
    sample_ok = bool(best_test) and int(best_test.get("test_trade_count") or 0) >= 100
    if not trade_list_available:
        final_label = "USE_AS_WATCHLIST_ONLY"
        reason = "Actual TradingView trade list is missing; proxy overlay cannot validate trade-level filtering."
    elif overlay_improved and not sample_ok:
        final_label = "USE_AS_DISCRETIONARY_FILTER_ONLY"
        reason = "Overlay improved the frozen test split, but sample size is not sufficient."
    elif overlay_improved and sample_ok:
        final_label = "READY_FOR_SHADOW_REVIEW"
        reason = "Out-of-sample filtered result cleared costs with sufficient sample in this research gate."
    else:
        final_label = "USE_AS_WATCHLIST_ONLY"
        reason = "Frozen test split did not clear the conservative after-cost gate."
    rows = [
        {
            "decision_scope": "baseline_direct",
            "decision_label": baseline_label,
            "reason": "Supplied baseline is negative after costs and cannot be used directly.",
            "trade_list_available": trade_list_available,
            "sample_size_warning": True,
            "research_only": True,
        },
        {
            "decision_scope": "overlay_lab",
            "decision_label": final_label,
            "reason": reason,
            "trade_list_available": trade_list_available,
            "sample_size_warning": not sample_ok,
            "research_only": True,
        },
    ]
    return _rows_frame(rows, _decision_schema())


def write_lab_outputs(*, output_root: Path, result: PineOverlayLabResult) -> None:
    """Write all requested Pine overlay output artifacts."""

    result.baseline_summary.write_csv(output_root / "pine_baseline_summary.csv")
    (output_root / "pine_baseline_summary.md").write_text(
        pine_baseline_summary_markdown(result.baseline_summary),
        encoding="utf-8",
    )
    (output_root / "pine_trade_candidate_schema.md").write_text(
        trade_candidate_schema_markdown(),
        encoding="utf-8",
    )
    result.filter_plan.write_csv(output_root / "pine_filter_overlay_plan.csv")
    (output_root / "pine_filter_overlay_plan.md").write_text(
        filter_overlay_plan_markdown(result.filter_plan),
        encoding="utf-8",
    )
    result.fee_outlier_audit.write_csv(output_root / "pine_fee_outlier_audit.csv")
    (output_root / "pine_fee_outlier_audit.md").write_text(
        fee_outlier_audit_markdown(result.fee_outlier_audit),
        encoding="utf-8",
    )
    result.overlay_summary.write_csv(output_root / "pine_overlay_backtest_summary.csv")
    (output_root / "pine_overlay_backtest_report.md").write_text(
        overlay_backtest_report_markdown(result),
        encoding="utf-8",
    )
    result.formation_test.write_csv(output_root / "pine_overlay_formation_test.csv")
    result.fast_start_decision.write_csv(output_root / "pine_fast_start_decision.csv")
    (output_root / "pine_fast_start_decision.md").write_text(
        fast_start_decision_markdown(result.fast_start_decision),
        encoding="utf-8",
    )
    append_pine_sections_to_research_report(output_root / "research_report.md", result)


def write_trade_list_missing_request(path: Path) -> None:
    """Write a clear request for the TradingView List of Trades export."""

    lines = [
        "# Pine Trade List Missing",
        "",
        "The TradingView List of Trades CSV was not found, so this run uses PROXY_ONLY overlay tests.",
        "",
        "For accurate trade-level overlay, export the Strategy Tester List of Trades CSV from TradingView",
        "and save it as `outputs/pine_trade_list.csv` or pass it explicitly to the lab.",
        "",
        "Required columns are timestamp or entry time, direction, entry price, exit price, PnL,",
        "and optional bars in trade, commission, entry reason, and exit reason.",
    ]
    path.write_text(_safe_report_text("\n".join(lines)), encoding="utf-8")


def pine_baseline_summary_markdown(frame: pl.DataFrame) -> str:
    """Render baseline summary Markdown."""

    row = frame.row(0, named=True)
    lines = [
        "# Pine Baseline Summary",
        "",
        "Research-only summary of the supplied TradingView Strategy Tester result.",
        "",
        f"- Strategy: `{row['strategy']}`",
        f"- Date range: `{row['date_start']}` to `{row['date_end']}`",
        f"- Net PnL after reported costs: `{_format_float(row['net_pnl'])}`",
        f"- Total trades: `{row['total_trades']}`",
        f"- Win rate: `{_format_pct(row['win_rate'])}`",
        f"- Average PnL per trade: `{_format_float(row['avg_pnl'])}`",
        f"- Average win/loss: `{_format_float(row['avg_win'])}` / `{_format_float(row['avg_loss'])}`",
        f"- Reported commissions: `{_format_float(row['commissions'])}`",
        f"- Long/short PnL: `{_format_float(row['long_pnl'])}` / `{_format_float(row['short_pnl'])}`",
        f"- P/L ratio or profit factor: `{_format_float(row['profit_factor'])}`",
        f"- Sharpe: `{_format_float(row['sharpe'])}`",
        f"- Baseline label: `{row['baseline_status_label']}`",
        "",
        "## Main Failure Modes",
        "",
        "- High trade count creates cost drag.",
        "- Short side dominates the loss.",
        "- Average loss is larger than average win.",
        "- Outlier losses can overwhelm many small wins.",
    ]
    return _safe_report_text("\n".join(lines))


def trade_candidate_schema_markdown() -> str:
    """Render the canonical Pine trade candidate contract."""

    fields = [
        "timestamp",
        "trade_id",
        "direction",
        "entry_price",
        "exit_price",
        "pnl",
        "pnl_after_cost",
        "bars_in_trade",
        "entry_reason",
        "exit_reason",
        "pine_signal_score",
        "grid_state",
        "ladder_state",
        "sd_position",
        "regime_state",
        "trend_filter_state",
        "sweep_confirmation",
        "fee_hurdle_passed",
        "cme_filter_state",
        "guru_filter_state",
        "final_allow_trade",
    ]
    lines = [
        "# Pine Trade Candidate Schema",
        "",
        "Canonical row for overlay research. A row is a trade candidate, not an order instruction.",
        "",
        "| field | purpose |",
        "|---|---|",
    ]
    lines.extend(f"| `{field}` | Pine baseline or overlay attribute. |" for field in fields)
    lines.extend(
        [
            "",
            "The final field `final_allow_trade` is a research filter result only.",
            "It must not be used for live, paper, broker, wallet, or order execution.",
        ]
    )
    return _safe_report_text("\n".join(lines))


def filter_overlay_plan_markdown(frame: pl.DataFrame) -> str:
    """Render overlay plan Markdown."""

    lines = [
        "# Pine Filter Overlay Plan",
        "",
        "Research-only overlay tests. Parameters are evaluated with formation/test split where applicable.",
        "",
        _frame_markdown(frame),
    ]
    return _safe_report_text("\n".join(lines))


def fee_outlier_audit_markdown(frame: pl.DataFrame) -> str:
    """Render fee and outlier audit Markdown."""

    lines = [
        "# Pine Fee And Outlier Audit",
        "",
        _frame_markdown(frame),
        "",
        "Worst-trade removal is shown only as a hindsight diagnostic.",
    ]
    return _safe_report_text("\n".join(lines))


def overlay_backtest_report_markdown(result: PineOverlayLabResult) -> str:
    """Render overlay backtest Markdown."""

    lines = [
        "# Pine Overlay Backtest Report",
        "",
        f"- Data mode: `{result.data_mode}`",
        f"- TradingView trade list available: `{result.trade_list_available}`",
        "- The proxy mode ports the Pine grid/ladder candidate generator to local OHLC data.",
        "- TradingView fills, MTF requests, and Strategy Tester accounting are not exactly reproduced.",
        "",
        "## Overlay Summary",
        "",
        _frame_markdown(result.overlay_summary),
        "",
        "## Formation/Test Split",
        "",
        _frame_markdown(result.formation_test),
    ]
    return _safe_report_text("\n".join(lines))


def fast_start_decision_markdown(frame: pl.DataFrame) -> str:
    """Render fast-start decision Markdown."""

    lines = [
        "# Pine Fast-Start Decision",
        "",
        "Research-only decision labels. No execution workflow is included.",
        "",
        _frame_markdown(frame),
    ]
    return _safe_report_text("\n".join(lines))


def append_pine_sections_to_research_report(path: Path, result: PineOverlayLabResult) -> None:
    """Add or replace Pine overlay sections in the main research report."""

    start = "<!-- PINE OVERLAY LAB START -->"
    end = "<!-- PINE OVERLAY LAB END -->"
    section = "\n".join([start, *pine_research_report_lines(result), end])
    existing = path.read_text(encoding="utf-8") if path.exists() else "# XAU Vol-OI Research Report\n"
    pattern = re.compile(f"{re.escape(start)}.*?{re.escape(end)}", flags=re.DOTALL)
    if pattern.search(existing):
        updated = pattern.sub(section, existing)
    else:
        updated = existing.rstrip() + "\n\n" + section + "\n"
    path.write_text(_safe_report_text(updated), encoding="utf-8")


def pine_research_report_lines(result: PineOverlayLabResult) -> list[str]:
    """Return the requested main report sections."""

    baseline = result.baseline_summary.row(0, named=True)
    fee = result.fee_outlier_audit.row(0, named=True)
    direction = _direction_rows(result.overlay_summary)
    sensitivity = result.formation_test.filter(pl.col("experiment_type") == "sd_grid_sensitivity")
    formation = result.formation_test.filter(pl.col("experiment_type") == "overlay_policy")
    decision = result.fast_start_decision
    return [
        "## Pine Baseline Strategy",
        "",
        f"- Baseline label: `{baseline['baseline_status_label']}`",
        f"- Net PnL after reported costs: `{_format_float(baseline['net_pnl'])}`",
        f"- Total trades: `{baseline['total_trades']}`",
        f"- Average PnL per trade: `{_format_float(baseline['avg_pnl'])}`",
        "",
        "## Pine Failure Modes",
        "",
        f"- {baseline['main_failure_modes']}.",
        "- The baseline is retained as a watchlist/candidate generator only.",
        "",
        "## Fee and Outlier Audit",
        "",
        _frame_markdown(result.fee_outlier_audit),
        f"- Commission per trade estimate: `{_format_float(fee['commission_per_trade'])}`.",
        "",
        "## CME/Guru Filter Overlay",
        "",
        f"- Data mode: `{result.data_mode}`.",
        f"- Actual TradingView trade list available: `{result.trade_list_available}`.",
        "- CME walls are filters around candidate trades, not automatic direction signals.",
        "- Guru text is used only when timing and conditions are confirmed.",
        "",
        "## Direction Filter Results",
        "",
        _frame_markdown(direction),
        "",
        "## SD Grid Sensitivity",
        "",
        _frame_markdown(sensitivity),
        "",
        "## Formation/Test Overlay Results",
        "",
        _frame_markdown(formation),
        "",
        "## Fast-Start Decision",
        "",
        _frame_markdown(decision),
    ]


def _candidate_signals_for_row(
    *,
    row: dict[str, Any],
    price_rows: list[dict[str, Any]],
    index: int,
    levels: dict[str, float],
    sigma: float,
    low_trap: bool,
    high_trap: bool,
    config: PineProxyConfig,
) -> list[dict[str, Any]]:
    """Create per-rung proxy candidates for one bar."""

    output: list[dict[str, Any]] = []
    if config.ladder_enabled:
        rung_levels = [
            ("L1", 2.0, 1),
            ("L2", 2.5, 2),
            ("L3", 3.0, 3),
        ][: max(1, min(config.pyramiding, 3))]
    else:
        rung_levels = [("GRID", config.entry_sd, 1)]
    close = float(row["close"])
    low = float(row["low"])
    high = float(row["high"])
    open_price = float(row["open"])
    for rung_name, rung_sd, _rung_index in rung_levels:
        long_level = levels["grid_mid"] - rung_sd * levels["grid_dev"]
        short_level = levels["grid_mid"] + rung_sd * levels["grid_dev"]
        long_reject = low <= long_level and close > long_level and (close > open_price or low_trap)
        short_reject = high >= short_level and close < short_level and (close < open_price or high_trap)
        if long_reject:
            output.append(
                _proxy_candidate_from_signal(
                    row=row,
                    price_rows=price_rows,
                    index=index,
                    direction="long",
                    rung_name=rung_name,
                    rung_sd=rung_sd,
                    entry_level=long_level,
                    target=levels["long_target"],
                    stop=levels["long_emergency_stop"],
                    sigma=sigma,
                    config=config,
                )
            )
        if short_reject:
            output.append(
                _proxy_candidate_from_signal(
                    row=row,
                    price_rows=price_rows,
                    index=index,
                    direction="short",
                    rung_name=rung_name,
                    rung_sd=rung_sd,
                    entry_level=short_level,
                    target=levels["short_target"],
                    stop=levels["short_emergency_stop"],
                    sigma=sigma,
                    config=config,
                )
            )
    return output


def _proxy_candidate_from_signal(
    *,
    row: dict[str, Any],
    price_rows: list[dict[str, Any]],
    index: int,
    direction: str,
    rung_name: str,
    rung_sd: float,
    entry_level: float,
    target: float,
    stop: float,
    sigma: float,
    config: PineProxyConfig,
) -> dict[str, Any]:
    entry = float(row["close"])
    exit_price, exit_reason, bars = _simulate_proxy_exit(
        price_rows,
        index=index,
        direction=direction,
        target=target,
        stop=stop,
        config=config,
    )
    sign = 1.0 if direction == "long" else -1.0
    pnl = (exit_price - entry) * sign
    cost = (entry + exit_price) * config.commission_rate + 2.0 * config.slippage_points_per_side
    pnl_after_cost = pnl - cost
    expected_move = abs(target - entry)
    timestamp = _timestamp_text(row.get("timestamp"))
    return _candidate_row(
        timestamp=timestamp,
        trade_id=f"proxy_{index}_{direction}_{rung_name}",
        direction=direction,
        entry_price=entry,
        exit_price=exit_price,
        pnl=pnl,
        pnl_after_cost=pnl_after_cost,
        bars_in_trade=bars,
        entry_reason=f"PINE_PROXY_REJECTION_{rung_name}_{rung_sd:g}SD",
        exit_reason=exit_reason,
        pine_signal_score=min(abs(sigma) / max(rung_sd, 0.1), 3.0),
        grid_state="LOWER_ENTRY" if direction == "long" else "UPPER_ENTRY",
        ladder_state=rung_name if config.ladder_enabled else "DISABLED",
        sd_position=sigma,
        regime_state="GRID_MEAN_REVERSION_PROXY",
        trend_filter_state="NOT_PORTED_PROXY",
        sweep_confirmation=False,
        fee_hurdle_passed=fee_hurdle_allows(
            expected_move,
            cost,
            buffer_points=config.fee_buffer_points,
        ),
        cme_filter_state="PENDING",
        guru_filter_state="PENDING",
        final_allow_trade=True,
        session_date=_date_text(row.get("session_date") or timestamp),
        expected_move=expected_move,
        round_trip_cost=cost,
        source_mode="PROXY_ONLY",
        session_open=_float_or_none(row.get("session_open")),
    )


def _simulate_proxy_exit(
    price_rows: list[dict[str, Any]],
    *,
    index: int,
    direction: str,
    target: float,
    stop: float,
    config: PineProxyConfig,
) -> tuple[float, str, int]:
    """Conservative next-bar path simulation for proxy candidates."""

    last_exit = float(price_rows[min(index + config.max_horizon_bars, len(price_rows) - 1)]["close"])
    for offset in range(1, config.max_horizon_bars + 1):
        next_index = index + offset
        if next_index >= len(price_rows):
            break
        row = price_rows[next_index]
        high = float(row["high"])
        low = float(row["low"])
        if direction == "long":
            stop_hit = low <= stop
            target_hit = high >= target
            if stop_hit:
                return stop, "PINE_PROXY_EMERGENCY_STOP", offset
            if target_hit:
                return target, "PINE_PROXY_MID_TARGET", offset
        else:
            stop_hit = high >= stop
            target_hit = low <= target
            if stop_hit:
                return stop, "PINE_PROXY_EMERGENCY_STOP", offset
            if target_hit:
                return target, "PINE_PROXY_MID_TARGET", offset
        last_exit = float(row["close"])
    return last_exit, "PINE_PROXY_TIME_EXIT", min(config.max_horizon_bars, len(price_rows) - index - 1)


def _grid_levels(*, grid_mid: float, grid_dev: float, config: PineProxyConfig) -> dict[str, float]:
    return {
        "grid_mid": grid_mid,
        "grid_dev": grid_dev,
        "upper_no_trade": grid_mid + grid_dev * config.no_trade_sd,
        "lower_no_trade": grid_mid - grid_dev * config.no_trade_sd,
        "long_target": grid_mid + grid_dev * config.target_offset_sd,
        "short_target": grid_mid - grid_dev * config.target_offset_sd,
        "long_emergency_stop": grid_mid - grid_dev * config.emergency_stop_sd,
        "short_emergency_stop": grid_mid + grid_dev * config.emergency_stop_sd,
    }


def _sweep_flags(
    rows: list[dict[str, Any]],
    index: int,
    *,
    config: PineProxyConfig,
) -> tuple[bool, bool]:
    if index < config.sweep_lookback:
        return False, False
    prior = rows[index - config.sweep_lookback + 1 : index]
    prior_high = max(float(item["high"]) for item in prior)
    prior_low = min(float(item["low"]) for item in prior)
    row = rows[index]
    high_trap = float(row["high"]) > prior_high and float(row["close"]) < prior_high
    low_trap = float(row["low"]) < prior_low and float(row["close"]) > prior_low
    return low_trap, high_trap


def _standardize_price_rows(frame: pl.DataFrame) -> list[dict[str, Any]]:
    if frame.is_empty():
        return []
    columns = {_normal_column(column): column for column in frame.columns}
    required = ("timestamp", "open", "high", "low", "close")
    if any(name not in columns for name in required):
        return []
    rows = []
    sorted_frame = frame.sort(columns["timestamp"])
    for raw in sorted_frame.to_dicts():
        timestamp = _parse_datetime(raw.get(columns["timestamp"]))
        open_price = _float_or_none(raw.get(columns["open"]))
        high = _float_or_none(raw.get(columns["high"]))
        low = _float_or_none(raw.get(columns["low"]))
        close = _float_or_none(raw.get(columns["close"]))
        if timestamp is None or None in {open_price, high, low, close}:
            continue
        if high < low or open_price < low or open_price > high or close < low or close > high:
            continue
        session_open = _float_or_none(raw.get(columns.get("session_open", "")))
        rows.append(
            {
                "timestamp": timestamp,
                "session_date": _date_text(raw.get(columns.get("session_date", "")) or timestamp),
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "session_open": session_open if session_open is not None else open_price,
            }
        )
    return rows


def _summary_for_policy(
    policy: str,
    allowed: list[dict[str, Any]],
    blocked: list[dict[str, Any]],
    *,
    all_rows: list[dict[str, Any]],
    data_mode: str,
) -> dict[str, Any]:
    pnl = [_float_or_zero(row.get("pnl_after_cost")) for row in allowed]
    wins = [value for value in pnl if value > 0]
    losses = [value for value in pnl if value < 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    blocked_pnl = [_float_or_zero(row.get("pnl_after_cost")) for row in blocked]
    avoided_loss = abs(sum(value for value in blocked_pnl if value < 0))
    opportunity_cost = sum(value for value in blocked_pnl if value > 0)
    return {
        "policy": policy,
        "data_mode": data_mode,
        "trade_count": len(allowed),
        "blocked_trade_count": len(blocked),
        "win_rate": len(wins) / len(allowed) if allowed else None,
        "net_pnl_after_cost": sum(pnl),
        "avg_win": sum(wins) / len(wins) if wins else 0.0,
        "avg_loss": sum(losses) / len(losses) if losses else 0.0,
        "avg_pnl": sum(pnl) / len(pnl) if pnl else None,
        "profit_factor": gross_win / gross_loss if gross_loss > 0 else None,
        "max_drawdown": _max_drawdown(pnl),
        "sharpe_proxy": _sharpe_proxy(pnl),
        "fee_paid": sum(_float_or_zero(row.get("round_trip_cost")) for row in allowed),
        "outlier_loss_count": len([value for value in pnl if value <= _outlier_loss_threshold(pnl)]),
        "false_block_rate": _false_block_rate(blocked, all_rows),
        "avoided_loss": avoided_loss,
        "opportunity_cost": opportunity_cost,
        "net_filter_value": avoided_loss - opportunity_cost,
        "sample_size_warning": len(allowed) < 30,
        "leakage_warning": data_mode == "PROXY_ONLY",
    }


def _sensitivity_row(candidates: pl.DataFrame, config: PineProxyConfig) -> dict[str, Any]:
    rows = candidates.to_dicts() if not candidates.is_empty() else []
    formation, test = _split_candidate_rows(rows)
    return {
        "grid_sd_len": config.grid_sd_len,
        "entry_sd": config.entry_sd,
        "no_trade_sd": config.no_trade_sd,
        "formation_trade_count": len(formation),
        "test_trade_count": len(test),
        "formation_avg_pnl": _avg_pnl(formation),
        "test_avg_pnl": _avg_pnl(test),
        "full_sample_trade_count": len(rows),
        "full_sample_avg_pnl": _avg_pnl(rows),
        "selected_for_test": False,
        "is_full_sample_best": False,
        "selection_basis": "formation_only",
        "sample_size_warning": len(test) < 30,
        "leakage_warning": True,
    }


def _split_candidate_rows(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not rows:
        return [], []
    sorted_rows = sorted(rows, key=lambda row: str(row.get("timestamp") or ""))
    split_index = max(1, len(sorted_rows) // 2)
    return sorted_rows[:split_index], sorted_rows[split_index:]


def _policy_predicates() -> dict[str, Any]:
    return {
        "baseline_all_trades": lambda row: True,
        "long_only": lambda row: row.get("direction") == "long",
        "short_only": lambda row: row.get("direction") == "short",
        "long_with_normal_filter": lambda row: row.get("direction") == "long"
        and _bool_value(row.get("fee_hurdle_passed")),
        "short_with_extra_confirmation": lambda row: row.get("direction") == "short"
        and _bool_value(row.get("fee_hurdle_passed"))
        and "BLOCK" not in str(row.get("cme_filter_state") or "")
        and "BLOCK" not in str(row.get("guru_filter_state") or ""),
        "fee_hurdle_filter": lambda row: _bool_value(row.get("fee_hurdle_passed")),
        "guru_no_trade_filter": lambda row: "BLOCK" not in str(row.get("guru_filter_state") or ""),
        "cme_wall_filter": lambda row: "BLOCK" not in str(row.get("cme_filter_state") or ""),
        "open_distance_filter": open_distance_filter_allows,
        "outlier_loss_guard": outlier_guard_allows,
        "all_filters": lambda row: _bool_value(row.get("final_allow_trade")),
    }


def _direction_rows(summary: pl.DataFrame) -> pl.DataFrame:
    if summary.is_empty():
        return summary
    return summary.filter(pl.col("policy").is_in(["baseline_all_trades", "long_only", "short_only"]))


def _best_test_row(formation: pl.DataFrame) -> dict[str, Any]:
    if formation.is_empty() or "selected_for_test" not in formation.columns:
        return {}
    selected = formation.filter(pl.col("selected_for_test"))
    if selected.is_empty():
        return {}
    return selected.head(1).row(0, named=True)


def _plan_row(
    part: str,
    overlay: str,
    scenario: str,
    data_mode: str,
    enabled: bool,
) -> dict[str, Any]:
    return {
        "part": part,
        "overlay": overlay,
        "scenario": scenario,
        "data_mode": data_mode,
        "enabled": enabled,
        "formation_test_required": overlay in {"sd_grid_sensitivity", "actual_trade_overlay"},
        "notes": "Use formation/test split; no full-sample parameter selection.",
    }


def _candidate_row(**kwargs: Any) -> dict[str, Any]:
    row = {
        "timestamp": "",
        "trade_id": "",
        "direction": "",
        "entry_price": None,
        "exit_price": None,
        "pnl": None,
        "pnl_after_cost": None,
        "bars_in_trade": 0,
        "entry_reason": "",
        "exit_reason": "",
        "pine_signal_score": None,
        "grid_state": "",
        "ladder_state": "",
        "sd_position": None,
        "regime_state": "",
        "trend_filter_state": "",
        "sweep_confirmation": False,
        "fee_hurdle_passed": False,
        "cme_filter_state": "",
        "guru_filter_state": "",
        "final_allow_trade": False,
        "session_date": "",
        "expected_move": None,
        "round_trip_cost": None,
        "source_mode": "",
        "session_open": None,
    }
    row.update(kwargs)
    return row


def _baseline_schema() -> dict[str, Any]:
    return {
        "strategy": pl.String,
        "date_start": pl.String,
        "date_end": pl.String,
        "initial_capital": pl.Float64,
        "net_pnl": pl.Float64,
        "gross_profit": pl.Float64,
        "gross_loss": pl.Float64,
        "commissions": pl.Float64,
        "total_trades": pl.Int64,
        "win_rate": pl.Float64,
        "avg_win": pl.Float64,
        "avg_loss": pl.Float64,
        "avg_pnl": pl.Float64,
        "profit_factor": pl.Float64,
        "long_pnl": pl.Float64,
        "short_pnl": pl.Float64,
        "long_trade_count": pl.Int64,
        "short_trade_count": pl.Int64,
        "max_drawdown": pl.Float64,
        "sharpe": pl.Float64,
        "buy_hold_return": pl.Float64,
        "fee_burden_per_trade": pl.Float64,
        "main_failure_modes": pl.String,
        "pine_script_present": pl.Boolean,
        "pine_script_features_detected": pl.String,
        "baseline_status_label": pl.String,
        "research_only": pl.Boolean,
    }


def _trade_candidate_schema() -> dict[str, Any]:
    return {
        "timestamp": pl.String,
        "trade_id": pl.String,
        "direction": pl.String,
        "entry_price": pl.Float64,
        "exit_price": pl.Float64,
        "pnl": pl.Float64,
        "pnl_after_cost": pl.Float64,
        "bars_in_trade": pl.Int64,
        "entry_reason": pl.String,
        "exit_reason": pl.String,
        "pine_signal_score": pl.Float64,
        "grid_state": pl.String,
        "ladder_state": pl.String,
        "sd_position": pl.Float64,
        "regime_state": pl.String,
        "trend_filter_state": pl.String,
        "sweep_confirmation": pl.Boolean,
        "fee_hurdle_passed": pl.Boolean,
        "cme_filter_state": pl.String,
        "guru_filter_state": pl.String,
        "final_allow_trade": pl.Boolean,
        "session_date": pl.String,
        "expected_move": pl.Float64,
        "round_trip_cost": pl.Float64,
        "source_mode": pl.String,
        "session_open": pl.Float64,
    }


def _filter_plan_schema() -> dict[str, Any]:
    return {
        "part": pl.String,
        "overlay": pl.String,
        "scenario": pl.String,
        "data_mode": pl.String,
        "enabled": pl.Boolean,
        "formation_test_required": pl.Boolean,
        "notes": pl.String,
    }


def _fee_audit_schema() -> dict[str, Any]:
    return {
        "commission_per_trade": pl.Float64,
        "gross_edge_before_cost_estimate": pl.Float64,
        "fee_drag_ratio": pl.Float64,
        "low_expected_move_trade_count": pl.Int64,
        "outlier_loss_count": pl.Int64,
        "outlier_loss_contribution": pl.Float64,
        "removing_worst_outliers_effect": pl.String,
        "realistic_removal_warning": pl.String,
        "research_only": pl.Boolean,
    }


def _overlay_summary_schema() -> dict[str, Any]:
    return {
        "policy": pl.String,
        "data_mode": pl.String,
        "trade_count": pl.Int64,
        "blocked_trade_count": pl.Int64,
        "win_rate": pl.Float64,
        "net_pnl_after_cost": pl.Float64,
        "avg_win": pl.Float64,
        "avg_loss": pl.Float64,
        "avg_pnl": pl.Float64,
        "profit_factor": pl.Float64,
        "max_drawdown": pl.Float64,
        "sharpe_proxy": pl.Float64,
        "fee_paid": pl.Float64,
        "outlier_loss_count": pl.Int64,
        "false_block_rate": pl.Float64,
        "avoided_loss": pl.Float64,
        "opportunity_cost": pl.Float64,
        "net_filter_value": pl.Float64,
        "sample_size_warning": pl.Boolean,
        "leakage_warning": pl.Boolean,
    }


def _sensitivity_schema() -> dict[str, Any]:
    return {
        "grid_sd_len": pl.Int64,
        "entry_sd": pl.Float64,
        "no_trade_sd": pl.Float64,
        "formation_trade_count": pl.Int64,
        "test_trade_count": pl.Int64,
        "formation_avg_pnl": pl.Float64,
        "test_avg_pnl": pl.Float64,
        "full_sample_trade_count": pl.Int64,
        "full_sample_avg_pnl": pl.Float64,
        "selected_for_test": pl.Boolean,
        "is_full_sample_best": pl.Boolean,
        "selection_basis": pl.String,
        "sample_size_warning": pl.Boolean,
        "leakage_warning": pl.Boolean,
    }


def _formation_schema() -> dict[str, Any]:
    return {
        "experiment_type": pl.String,
        "policy": pl.String,
        "grid_sd_len": pl.Int64,
        "entry_sd": pl.Float64,
        "no_trade_sd": pl.Float64,
        "formation_trade_count": pl.Int64,
        "test_trade_count": pl.Int64,
        "formation_avg_pnl": pl.Float64,
        "test_avg_pnl": pl.Float64,
        "full_sample_trade_count": pl.Int64,
        "full_sample_avg_pnl": pl.Float64,
        "selected_for_test": pl.Boolean,
        "is_full_sample_best": pl.Boolean,
        "selection_basis": pl.String,
        "sample_size_warning": pl.Boolean,
        "leakage_warning": pl.Boolean,
    }


def _decision_schema() -> dict[str, Any]:
    return {
        "decision_scope": pl.String,
        "decision_label": pl.String,
        "reason": pl.String,
        "trade_list_available": pl.Boolean,
        "sample_size_warning": pl.Boolean,
        "research_only": pl.Boolean,
    }


def _empty_trade_candidates() -> pl.DataFrame:
    return pl.DataFrame(schema=_trade_candidate_schema())


def _empty_sensitivity() -> pl.DataFrame:
    return pl.DataFrame(schema=_sensitivity_schema())


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


def _read_optional_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _normal_column(column: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", column.lower())


def _get_first(raw: dict[str, Any], columns: dict[str, str], names: tuple[str, ...]) -> Any:
    for name in names:
        column = columns.get(_normal_column(name))
        if column is not None:
            return raw.get(column)
    return None


def _direction_from_raw(value: Any) -> str:
    text = str(value or "").lower()
    if "short" in text or "sell" in text:
        return "short"
    if "long" in text or "buy" in text:
        return "long"
    return ""


def _rows_by_date(frame: pl.DataFrame, column: str) -> dict[str, dict[str, Any]]:
    if frame.is_empty() or column not in frame.columns:
        return {}
    rows = {}
    for row in frame.to_dicts():
        date_key = _date_text(row.get(column))
        if date_key:
            rows[date_key] = row
    return rows


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            match = re.search(r"20\d{2}-\d{2}-\d{2}", text)
            if not match:
                return None
            parsed = datetime.fromisoformat(match.group(0))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _timestamp_text(value: Any) -> str:
    if isinstance(value, datetime):
        parsed = value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return parsed.isoformat().replace("+00:00", "Z")
    parsed = _parse_datetime(value)
    if parsed is not None:
        return parsed.isoformat().replace("+00:00", "Z")
    return _redact_text(str(value or ""))


def _date_text(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    match = re.search(r"20\d{2}-\d{2}-\d{2}", str(value or ""))
    return match.group(0) if match else ""


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        if math.isnan(float(value)):
            return None
        return float(value)
    text = re.sub(r"[$,%\s]", "", str(value))
    if text in {"", "-", "nan", "None"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


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


def _stddev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return math.sqrt(variance)


def _avg_pnl(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    return sum(_float_or_zero(row.get("pnl_after_cost")) for row in rows) / len(rows)


def _max_drawdown(pnl: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    drawdown = 0.0
    for value in pnl:
        equity += value
        peak = max(peak, equity)
        drawdown = min(drawdown, equity - peak)
    return drawdown


def _sharpe_proxy(pnl: list[float]) -> float | None:
    if len(pnl) < 2:
        return None
    mean = sum(pnl) / len(pnl)
    std = _stddev(pnl)
    if std == 0:
        return None
    return mean / std * math.sqrt(len(pnl))


def _outlier_loss_threshold(pnl: list[float]) -> float:
    losses = [value for value in pnl if value < 0]
    if not losses:
        return -math.inf
    mean_loss = sum(losses) / len(losses)
    return min(mean_loss * 2.0, mean_loss - _stddev(losses))


def _estimate_outlier_loss_count(row: dict[str, Any]) -> int:
    total = int(row.get("total_trades") or 0)
    win_rate = _float_or_zero(row.get("win_rate"))
    losing_count = max(0, int(round(total * (1.0 - win_rate))))
    return max(1, int(round(losing_count * 0.05)))


def _false_block_rate(blocked: list[dict[str, Any]], all_rows: list[dict[str, Any]]) -> float | None:
    if not blocked:
        return None
    winning_blocked = sum(1 for row in blocked if _float_or_zero(row.get("pnl_after_cost")) > 0)
    winning_total = sum(1 for row in all_rows if _float_or_zero(row.get("pnl_after_cost")) > 0)
    if winning_total == 0:
        return None
    return winning_blocked / winning_total


def _format_float(value: Any) -> str:
    parsed = _float_or_none(value)
    return "n/a" if parsed is None else f"{parsed:.4f}"


def _format_pct(value: Any) -> str:
    parsed = _float_or_none(value)
    return "n/a" if parsed is None else f"{parsed * 100:.2f}%"


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


def main() -> None:
    """CLI entry point."""

    parser = argparse.ArgumentParser(description="Run Pine strategy overlay lab.")
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    parser.add_argument("--pine", type=Path, default=Path("Tradingview.pine"))
    parser.add_argument("--trade-list", type=Path, default=None)
    parser.add_argument("--price", type=Path, default=None)
    args = parser.parse_args()
    result = run_pine_strategy_overlay_lab(
        output_dir=args.output_dir,
        pine_path=args.pine,
        trade_list_path=args.trade_list,
        price_path=args.price,
    )
    decision = result.fast_start_decision.filter(pl.col("decision_scope") == "overlay_lab")
    label = decision.row(0, named=True)["decision_label"] if not decision.is_empty() else "n/a"
    print(f"data_mode: {result.data_mode}")
    print(f"trade_list_available: {result.trade_list_available}")
    print(f"fast_start_decision: {label}")


if __name__ == "__main__":
    main()
