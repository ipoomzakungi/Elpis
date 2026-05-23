"""Market-map and no-trade proof pack for XAU Vol-OI research.

The proof pack tests whether basis-adjusted OI walls and no-trade filters have
research value. It intentionally stops short of live, paper, or broker logic and
does not claim a tradable edge unless controls support it.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

import polars as pl

from research_xau_vol_oi.config import ResearchConfig, Signal


MIN_PROOF_SAMPLE = 20
NO_TRADE_SIGNALS = {
    Signal.NO_TRADE.value,
    Signal.NO_TRADE_MIDDLE.value,
    Signal.WATCH_WALL.value,
    Signal.PIN_RISK.value,
    Signal.SQUEEZE_RISK.value,
}
DIRECTIONAL_SIGNALS = {
    Signal.FADE_WALL_LONG.value,
    Signal.FADE_WALL_SHORT.value,
    Signal.BREAK_WALL_LONG.value,
    Signal.BREAK_WALL_SHORT.value,
}


@dataclass(frozen=True)
class MarketMapProofPackResult:
    """Generated proof-pack tables and conservative decision labels."""

    market_map_precision: pl.DataFrame
    filter_avoided_pnl: pl.DataFrame
    expiry_pin_test: pl.DataFrame
    final_decision: str
    map_decision: str
    filter_decision: str
    trade_rule_decision: str


def run_market_map_proof_pack(
    *,
    feature_table: pl.DataFrame,
    walls: pl.DataFrame,
    signal_events: pl.DataFrame,
    output_dir: str | Path,
    config: ResearchConfig | None = None,
) -> MarketMapProofPackResult:
    """Run the market-map/no-trade proof pack and write required outputs."""

    cfg = config or ResearchConfig()
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    wall_events = build_wall_level_events(feature_table, walls, config=cfg)
    market_map = build_market_map_precision_report(feature_table, wall_events, config=cfg)
    filter_report = build_filter_avoided_pnl_report(feature_table, signal_events, config=cfg)
    pin_report = build_expiry_pin_test_report(feature_table, wall_events, config=cfg)

    map_decision = decide_market_map_usefulness(market_map)
    filter_decision = decide_filter_usefulness(filter_report)
    trade_decision = decide_trade_rule_proof(market_map, filter_report)
    final_decision = decide_final_proof_pack(map_decision, filter_decision, trade_decision)

    market_map.write_csv(output_root / "market_map_precision_report.csv")
    filter_report.write_csv(output_root / "filter_avoided_pnl_report.csv")
    pin_report.write_csv(output_root / "expiry_pin_test_report.csv")
    (output_root / "proof_pack.md").write_text(
        proof_pack_markdown(
            market_map=market_map,
            filter_report=filter_report,
            pin_report=pin_report,
            final_decision=final_decision,
            map_decision=map_decision,
            filter_decision=filter_decision,
            trade_decision=trade_decision,
        ),
        encoding="utf-8",
    )
    return MarketMapProofPackResult(
        market_map_precision=market_map,
        filter_avoided_pnl=filter_report,
        expiry_pin_test=pin_report,
        final_decision=final_decision,
        map_decision=map_decision,
        filter_decision=filter_decision,
        trade_rule_decision=trade_decision,
    )


def build_wall_level_events(
    feature_table: pl.DataFrame,
    walls: pl.DataFrame,
    *,
    config: ResearchConfig | None = None,
) -> pl.DataFrame:
    """Create timestamp-safe wall and placebo level events."""

    cfg = config or ResearchConfig()
    if feature_table.is_empty() or walls.is_empty():
        return _empty_wall_events()
    price_rows = feature_table.sort("timestamp").to_dicts()
    wall_rows = _top_wall_rows(walls)
    rng = random.Random(cfg.random_seed + 1701)
    events: list[dict[str, Any]] = []
    for wall in wall_rows:
        start_index = _first_price_index_at_or_after(price_rows, wall.get("timestamp"))
        if start_index is None:
            continue
        start_bar = price_rows[start_index]
        close = _float(start_bar.get("close"))
        wall_level = _float(wall.get("wall_level") or wall.get("spot_equivalent_strike"))
        if close is None or wall_level is None:
            continue
        distance = abs(wall_level - close)
        side = _level_side(level=wall_level, close=close, explicit=wall.get("wall_side"))
        base = _wall_event_base(wall, start_bar, start_index, wall_level, side, distance)
        events.append({**base, "cohort": "actual_top_wall", "control_type": "actual_wall"})
        matched_sign = rng.choice([-1.0, 1.0])
        events.append(
            {
                **base,
                "level": close + matched_sign * max(distance, cfg.proximity_points),
                "side": "resistance" if matched_sign > 0 else "support",
                "cohort": "matched_random_strike",
                "control_type": "matched_distance_random_level",
            }
        )
        scale = max(distance * 1.5, _float(start_bar.get("one_sd_remaining")) or 0.0, cfg.proximity_points * 2.0)
        random_level = close + rng.uniform(-scale, scale)
        events.append(
            {
                **base,
                "level": random_level,
                "side": _level_side(level=random_level, close=close, explicit=None),
                "cohort": "random_level_placebo",
                "control_type": "random_level_placebo",
            }
        )
        matched_index = _matched_state_index(price_rows, start_bar, rng)
        if matched_index is not None:
            matched_bar = price_rows[matched_index]
            matched_close = _float(matched_bar.get("close"))
            if matched_close is not None:
                matched_sign = rng.choice([-1.0, 1.0])
                matched_level = matched_close + matched_sign * max(distance, cfg.proximity_points)
                events.append(
                    {
                        **base,
                        "event_timestamp": matched_bar.get("timestamp"),
                        "start_index": matched_index,
                        "start_close": matched_close,
                        "level": matched_level,
                        "side": "resistance" if matched_sign > 0 else "support",
                        "cohort": "matched_state_placebo",
                        "control_type": "matched_state_placebo",
                        "sigma_zone": matched_bar.get("sigma_zone"),
                        "vol_regime": matched_bar.get("vol_regime"),
                        "event_day_tag": _event_day_tag(matched_bar),
                    }
                )
    return pl.DataFrame(events, infer_schema_length=None) if events else _empty_wall_events()


def build_market_map_precision_report(
    feature_table: pl.DataFrame,
    wall_events: pl.DataFrame,
    *,
    config: ResearchConfig | None = None,
) -> pl.DataFrame:
    """Test wall touch, rejection/acceptance, low-OI gap, and acceptance quality."""

    cfg = config or ResearchConfig()
    if feature_table.is_empty() or wall_events.is_empty():
        return _empty_market_map_report()
    price_rows = feature_table.sort("timestamp").to_dicts()
    outcome_rows = [
        _wall_level_outcome(price_rows, event, config=cfg)
        for event in wall_events.to_dicts()
    ]
    rows: list[dict[str, Any]] = []
    for test_name, predicate in [
        ("market_map_touch", lambda row: True),
        ("wall_rejection_acceptance", lambda row: True),
        ("low_oi_gap_squeeze", lambda row: bool(row.get("low_oi_gap_to_next_wall"))),
        ("acceptance_close_hold_vs_wick_probe", lambda row: True),
    ]:
        subset = [row for row in outcome_rows if predicate(row)]
        rows.extend(_market_map_group_rows(test_name, subset))
    rows.extend(_market_map_control_comparison_rows(outcome_rows))
    return pl.DataFrame(rows, infer_schema_length=None) if rows else _empty_market_map_report()


def build_filter_avoided_pnl_report(
    feature_table: pl.DataFrame,
    signal_events: pl.DataFrame,
    *,
    config: ResearchConfig | None = None,
) -> pl.DataFrame:
    """Estimate avoided losses and opportunity cost from no-trade labels."""

    cfg = config or ResearchConfig()
    if feature_table.is_empty() or signal_events.is_empty():
        return _empty_filter_report()
    price_rows = feature_table.sort("timestamp").to_dicts()
    no_trade_rows = [
        row for row in signal_events.to_dicts() if str(row.get("signal")) in NO_TRADE_SIGNALS
    ]
    directional_rows = [
        row for row in signal_events.to_dicts() if str(row.get("signal")) in DIRECTIONAL_SIGNALS
    ]
    rng = random.Random(cfg.random_seed + 2603)
    rows = []
    true_items = _filter_candidate_items(price_rows, no_trade_rows, config=cfg)
    random_items = _filter_candidate_items(
        price_rows,
        _random_filter_control_events(signal_events.to_dicts(), len(no_trade_rows), rng),
        config=cfg,
    )
    matched_items = _filter_candidate_items(
        price_rows,
        _matched_filter_control_events(no_trade_rows, directional_rows, rng),
        config=cfg,
    )
    rows.append(
        _filter_summary_row(
            "NO_TRADE_FILTER",
            "actual_no_trade_labels",
            true_items,
            actual_items=true_items,
            comparison_items=matched_items,
        )
    )
    rows.append(
        _filter_summary_row(
            "RANDOM_LABEL_PLACEBO",
            "random_label_placebo",
            random_items,
            actual_items=true_items,
            comparison_items=random_items,
        )
    )
    rows.append(
        _filter_summary_row(
            "MATCHED_STATE_PLACEBO",
            "matched_state_placebo",
            matched_items,
            actual_items=true_items,
            comparison_items=matched_items,
        )
    )
    rows.extend(_filter_bucket_rows(true_items, bucket_key="dte_bucket", control_name="expiry_bucket_control"))
    rows.extend(_filter_bucket_rows(true_items, bucket_key="event_day_tag", control_name="event_day_control"))
    return pl.DataFrame(rows, infer_schema_length=None) if rows else _empty_filter_report()


def build_expiry_pin_test_report(
    feature_table: pl.DataFrame,
    wall_events: pl.DataFrame,
    *,
    config: ResearchConfig | None = None,
) -> pl.DataFrame:
    """Test near-expiry high-OI wall pin behavior versus controls."""

    cfg = config or ResearchConfig()
    if feature_table.is_empty() or wall_events.is_empty():
        return _empty_pin_report()
    price_rows = feature_table.sort("timestamp").to_dicts()
    events = [
        row
        for row in wall_events.to_dicts()
        if str(row.get("cohort")) in {"actual_top_wall", "matched_random_strike", "random_level_placebo"}
        and (_float(row.get("dte")) is None or (_float(row.get("dte")) or 999) <= cfg.near_expiry_days)
    ]
    outcome_rows = [_pin_outcome(price_rows, event, config=cfg) for event in events]
    rows = []
    rows.extend(_pin_group_rows(outcome_rows, "all", "all"))
    for bucket_key in ["expiry_bucket", "event_day_tag"]:
        for bucket in sorted({str(row.get(bucket_key) or "UNKNOWN") for row in outcome_rows}):
            rows.extend(
                _pin_group_rows(
                    [row for row in outcome_rows if str(row.get(bucket_key) or "UNKNOWN") == bucket],
                    bucket_key,
                    bucket,
                )
            )
    return pl.DataFrame(rows, infer_schema_length=None) if rows else _empty_pin_report()


def decide_market_map_usefulness(market_map: pl.DataFrame) -> str:
    """Return whether wall maps appear useful, without implying tradability."""

    if market_map.is_empty():
        return "NO_EDGE_FOUND"
    comparisons = market_map.filter(pl.col("row_type") == "comparison")
    if comparisons.is_empty():
        return "NO_EDGE_FOUND"
    positive = [
        row
        for row in comparisons.to_dicts()
        if not bool(row.get("sample_size_warning"))
        and (_float(row.get("touch_uplift_vs_control")) or 0.0) > 0
        and (_float(row.get("acceptance_uplift_vs_control")) or 0.0) >= 0
    ]
    return "MAP_USEFUL_NOT_TRADABLE" if positive else "NO_EDGE_FOUND"


def decide_filter_usefulness(filter_report: pl.DataFrame) -> str:
    """Return whether no-trade filters appear to have positive avoided value."""

    if filter_report.is_empty():
        return "NO_EDGE_FOUND"
    actual = filter_report.filter(
        (pl.col("control_type") == "actual_no_trade_labels") & (pl.col("row_type") == "summary")
    )
    if actual.is_empty():
        return "NO_EDGE_FOUND"
    row = actual.row(0, named=True)
    if (
        not bool(row.get("sample_size_warning"))
        and (_float(row.get("net_filter_value")) or 0.0) > 0
        and (_float(row.get("uplift_vs_matched_state_placebo")) or 0.0) > 0
    ):
        return "FILTER_USEFUL"
    return "NO_EDGE_FOUND"


def decide_trade_rule_proof(market_map: pl.DataFrame, filter_report: pl.DataFrame) -> str:
    """Trade rules require more than map/filter usefulness."""

    if market_map.is_empty() and filter_report.is_empty():
        return "NO_EDGE_FOUND"
    return "TRADE_RULE_NOT_PROVEN"


def decide_final_proof_pack(map_decision: str, filter_decision: str, trade_decision: str) -> str:
    """Combine map/filter/trade decisions into one conservative label."""

    if filter_decision == "FILTER_USEFUL":
        return "FILTER_USEFUL"
    if map_decision == "MAP_USEFUL_NOT_TRADABLE":
        return "MAP_USEFUL_NOT_TRADABLE"
    if trade_decision == "TRADE_RULE_NOT_PROVEN":
        return "TRADE_RULE_NOT_PROVEN"
    return "NO_EDGE_FOUND"


def proof_pack_markdown(
    *,
    market_map: pl.DataFrame,
    filter_report: pl.DataFrame,
    pin_report: pl.DataFrame,
    final_decision: str,
    map_decision: str,
    filter_decision: str,
    trade_decision: str,
) -> str:
    """Render the proof pack summary."""

    lines = [
        "# Market-Map And No-Trade Proof Pack",
        "",
        "Research-only proof pack. No live trading, paper trading, broker connection, or direct trade signal is created.",
        "",
        f"- Final decision: `{final_decision}`",
        f"- Market-map decision: `{map_decision}`",
        f"- No-trade filter decision: `{filter_decision}`",
        f"- Trade-rule decision: `{trade_decision}`",
        "",
        "## Required Outputs",
        "",
        "- `outputs/market_map_precision_report.csv`",
        "- `outputs/filter_avoided_pnl_report.csv`",
        "- `outputs/expiry_pin_test_report.csv`",
        "- `outputs/proof_pack.md`",
        "",
        "## Market-Map Precision",
        "",
        _frame_markdown(_report_head(market_map)),
        "",
        "## No-Trade Filter Avoided PnL",
        "",
        _frame_markdown(_report_head(filter_report)),
        "",
        "## Expiry Pin Test",
        "",
        _frame_markdown(_report_head(pin_report)),
        "",
        "## Interpretation",
        "",
        "- `MAP_USEFUL_NOT_TRADABLE` means wall locations behaved differently from controls, not that a trade rule works.",
        "- `FILTER_USEFUL` means avoided-loss value exceeded opportunity cost and matched placebo in this local sample.",
        "- `TRADE_RULE_NOT_PROVEN` means directional entries still need separate walk-forward, cost, and placebo validation.",
        "- `NO_EDGE_FOUND` means the current local sample did not beat the required controls.",
    ]
    return "\n".join(lines)


def _top_wall_rows(walls: pl.DataFrame) -> list[dict[str, Any]]:
    rows = []
    for _timestamp, group in _group_rows(walls.to_dicts(), "timestamp").items():
        sorted_group = sorted(group, key=lambda row: _float(row.get("wall_score")) or 0.0, reverse=True)
        keep_count = min(3, len(sorted_group))
        for rank, row in enumerate(sorted_group[:keep_count], start=1):
            rows.append({**row, "wall_rank": rank})
    return rows


def _wall_event_base(
    wall: dict[str, Any],
    start_bar: dict[str, Any],
    start_index: int,
    wall_level: float,
    side: str,
    distance: float,
) -> dict[str, Any]:
    dte = _float(wall.get("dte"))
    return {
        "event_timestamp": start_bar.get("timestamp"),
        "available_wall_timestamp": wall.get("timestamp"),
        "start_index": start_index,
        "start_close": _float(start_bar.get("close")),
        "level": wall_level,
        "side": side,
        "distance_from_start": distance,
        "wall_score": _float(wall.get("wall_score")),
        "wall_score_bucket": _score_bucket(_float(wall.get("wall_score"))),
        "dte": dte,
        "dte_bucket": _expiry_bucket(dte),
        "expiry_bucket": _expiry_bucket(dte),
        "sigma_zone": start_bar.get("sigma_zone"),
        "vol_regime": start_bar.get("vol_regime"),
        "event_day_tag": _event_day_tag(start_bar),
        "low_oi_gap_to_next_wall": bool(wall.get("low_oi_gap_to_next_wall")),
        "next_wall_distance": _float(wall.get("next_wall_distance")),
        "largest_near_expiry_wall": bool(wall.get("largest_near_expiry_wall")),
        "wall_rank": wall.get("wall_rank"),
    }


def _wall_level_outcome(
    price_rows: list[dict[str, Any]],
    event: dict[str, Any],
    *,
    config: ResearchConfig,
) -> dict[str, Any]:
    start_index = int(event.get("start_index") or 0)
    level = _float(event.get("level"))
    side = str(event.get("side") or "unknown")
    if level is None or start_index >= len(price_rows) - 1:
        return {**event, **_empty_level_outcome()}
    end_index = min(start_index + config.backtest_horizon_bars, len(price_rows) - 1)
    path = price_rows[start_index + 1 : end_index + 1]
    start_close = _float(event.get("start_close")) or _float(price_rows[start_index].get("close")) or level
    touched = any((_float(row.get("low")) or 0.0) <= level <= (_float(row.get("high")) or 0.0) for row in path)
    acceptance = _accepted_beyond(path, level=level, side=side, buffer_points=config.acceptance_buffer_points)
    wick_probe = touched and not acceptance
    rejection = _rejected_from_wall(path, level=level, side=side, buffer_points=config.acceptance_buffer_points)
    max_favorable = max(abs((_float(row.get("close")) or start_close) - start_close) for row in path) if path else 0.0
    squeeze_threshold = max(
        config.low_oi_gap_points * 0.5,
        (_float(event.get("next_wall_distance")) or config.low_oi_gap_points) * 0.35,
    )
    squeeze = bool(event.get("low_oi_gap_to_next_wall")) and touched and max_favorable >= squeeze_threshold
    continuation = acceptance and _continued_after_acceptance(path, level=level, side=side)
    return {
        **event,
        "touch": touched,
        "rejection": rejection,
        "acceptance": acceptance,
        "wick_only_probe": wick_probe,
        "squeeze": squeeze,
        "continuation": continuation,
        "max_abs_close_move": max_favorable,
    }


def _pin_outcome(
    price_rows: list[dict[str, Any]],
    event: dict[str, Any],
    *,
    config: ResearchConfig,
) -> dict[str, Any]:
    start_index = int(event.get("start_index") or 0)
    level = _float(event.get("level"))
    if level is None or start_index >= len(price_rows):
        return {**event, "pin_hit": False, "close_distance": None}
    start_timestamp = _coerce_timestamp(price_rows[start_index].get("timestamp"))
    if start_timestamp is None:
        return {**event, "pin_hit": False, "close_distance": None, "pin_threshold": None}
    start_date = start_timestamp.date()
    session_bars = []
    for row in price_rows[start_index:]:
        row_timestamp = _coerce_timestamp(row.get("timestamp"))
        if row_timestamp is not None and row_timestamp.date() == start_date:
            session_bars.append(row)
    exit_bar = session_bars[-1] if session_bars else price_rows[min(start_index + config.backtest_horizon_bars, len(price_rows) - 1)]
    close = _float(exit_bar.get("close"))
    one_sd = _float(price_rows[start_index].get("one_sd_remaining"))
    threshold = max(config.proximity_points, (one_sd or 0.0) * 0.20)
    distance = abs(close - level) if close is not None else None
    return {
        **event,
        "pin_hit": distance is not None and distance <= threshold,
        "close_distance": distance,
        "pin_threshold": threshold,
    }


def _market_map_group_rows(test_name: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for cohort in sorted({str(row.get("cohort")) for row in rows}):
        subset = [row for row in rows if str(row.get("cohort")) == cohort]
        output.append(_market_map_summary_row(test_name, cohort, "cohort", "all", subset))
        for bucket_key in ["expiry_bucket", "event_day_tag"]:
            for bucket in sorted({str(row.get(bucket_key) or "UNKNOWN") for row in subset}):
                output.append(
                    _market_map_summary_row(
                        test_name,
                        cohort,
                        bucket_key,
                        bucket,
                        [row for row in subset if str(row.get(bucket_key) or "UNKNOWN") == bucket],
                    )
                )
    return output


def _market_map_control_comparison_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actual = [row for row in rows if row.get("cohort") == "actual_top_wall"]
    output = []
    for control in ["matched_random_strike", "random_level_placebo", "matched_state_placebo"]:
        control_rows = [row for row in rows if row.get("cohort") == control]
        output.append(_market_map_comparison_row("top_wall_vs_control", actual, control_rows, control))
    gap_rows = [row for row in actual if bool(row.get("low_oi_gap_to_next_wall"))]
    no_gap_rows = [row for row in actual if not bool(row.get("low_oi_gap_to_next_wall"))]
    output.append(_market_map_comparison_row("low_oi_gap_vs_no_gap", gap_rows, no_gap_rows, "no_gap_actual_walls"))
    accepted = [row for row in actual if bool(row.get("acceptance"))]
    wick = [row for row in actual if bool(row.get("wick_only_probe"))]
    output.append(_market_map_comparison_row("acceptance_vs_wick_probe", accepted, wick, "wick_only_probe"))
    return output


def _market_map_summary_row(
    test_name: str,
    cohort: str,
    bucket_type: str,
    bucket: str,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    count = len(rows)
    return {
        "row_type": "summary",
        "test_name": test_name,
        "cohort": cohort,
        "control_type": rows[0].get("control_type") if rows else cohort,
        "bucket_type": bucket_type,
        "bucket": bucket,
        "event_count": count,
        "touch_rate": _rate(rows, "touch"),
        "rejection_rate": _rate(rows, "rejection"),
        "acceptance_rate": _rate(rows, "acceptance"),
        "wick_probe_rate": _rate(rows, "wick_only_probe"),
        "squeeze_rate": _rate(rows, "squeeze"),
        "continuation_rate": _rate(rows, "continuation"),
        "control_touch_rate": None,
        "touch_uplift_vs_control": None,
        "acceptance_uplift_vs_control": None,
        "sample_size_warning": count < MIN_PROOF_SAMPLE,
        "decision_label": "",
    }


def _market_map_comparison_row(
    test_name: str,
    actual: list[dict[str, Any]],
    control: list[dict[str, Any]],
    control_name: str,
) -> dict[str, Any]:
    touch_uplift = _rate(actual, "touch") - _rate(control, "touch")
    acceptance_uplift = _rate(actual, "acceptance") - _rate(control, "acceptance")
    warning = len(actual) < MIN_PROOF_SAMPLE or len(control) < MIN_PROOF_SAMPLE
    decision = "MAP_USEFUL_NOT_TRADABLE" if not warning and touch_uplift > 0 and acceptance_uplift >= 0 else "NO_EDGE_FOUND"
    return {
        "row_type": "comparison",
        "test_name": test_name,
        "cohort": "actual_top_wall",
        "control_type": control_name,
        "bucket_type": "all",
        "bucket": "all",
        "event_count": len(actual),
        "touch_rate": _rate(actual, "touch"),
        "rejection_rate": _rate(actual, "rejection"),
        "acceptance_rate": _rate(actual, "acceptance"),
        "wick_probe_rate": _rate(actual, "wick_only_probe"),
        "squeeze_rate": _rate(actual, "squeeze"),
        "continuation_rate": _rate(actual, "continuation"),
        "control_touch_rate": _rate(control, "touch"),
        "touch_uplift_vs_control": touch_uplift,
        "acceptance_uplift_vs_control": acceptance_uplift,
        "sample_size_warning": warning,
        "decision_label": decision,
    }


def _filter_candidate_items(
    price_rows: list[dict[str, Any]],
    events: list[dict[str, Any]],
    *,
    config: ResearchConfig,
) -> list[dict[str, Any]]:
    items = []
    for event in events:
        direction = _naive_wall_fade_direction(event)
        if direction == 0:
            continue
        entry_index = _first_price_index_after(price_rows, event.get("event_timestamp"))
        if entry_index is None:
            continue
        exit_index = min(entry_index + config.backtest_horizon_bars, len(price_rows) - 1)
        if exit_index <= entry_index:
            continue
        entry = price_rows[entry_index]
        exit_bar = price_rows[exit_index]
        entry_price = _float(entry.get("open")) or _float(entry.get("close"))
        exit_price = _float(exit_bar.get("close"))
        if entry_price is None or exit_price is None:
            continue
        gross = (exit_price - entry_price) * direction
        cost = 2.0 * (config.cost_points_per_side + config.slippage_points_per_side)
        pnl = gross - cost
        items.append(
            {
                "signal": event.get("signal"),
                "event_timestamp": event.get("event_timestamp"),
                "net_pnl_points": pnl,
                "avoided_loss": -pnl if pnl < 0 else 0.0,
                "opportunity_cost": pnl if pnl > 0 else 0.0,
                "dte_bucket": event.get("dte_bucket") or _expiry_bucket(_float(event.get("dte"))),
                "event_day_tag": _event_day_tag(event),
                "sigma_zone": event.get("sigma_zone"),
                "vol_regime": event.get("vol_regime"),
            }
        )
    return items


def _filter_summary_row(
    cohort: str,
    control_type: str,
    items: list[dict[str, Any]],
    *,
    actual_items: list[dict[str, Any]],
    comparison_items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    comparison_net = _net_filter_value(comparison_items or [])
    actual_net = _net_filter_value(actual_items)
    net_value = _net_filter_value(items)
    uplift = net_value - comparison_net if control_type == "actual_no_trade_labels" else actual_net - net_value
    return {
        "row_type": "summary",
        "cohort": cohort,
        "control_type": control_type,
        "bucket_type": "all",
        "bucket": "all",
        "no_trade_count": len(items),
        "avoided_trade_count": len(items),
        "avoided_losing_trade_count": sum(1 for item in items if item["net_pnl_points"] < 0),
        "avoided_winning_trade_count": sum(1 for item in items if item["net_pnl_points"] > 0),
        "avoided_loss_amount": sum(item["avoided_loss"] for item in items),
        "opportunity_cost": sum(item["opportunity_cost"] for item in items),
        "net_filter_value": net_value,
        "bad_trade_reduction_rate": _rate_by_value(items, lambda item: item["net_pnl_points"] < 0),
        "false_block_rate": _rate_by_value(items, lambda item: item["net_pnl_points"] > 0),
        "placebo_net_filter_value": comparison_net if comparison_items is not None else None,
        "uplift_vs_matched_state_placebo": uplift,
        "sample_size_warning": len(items) < MIN_PROOF_SAMPLE,
        "decision_label": "FILTER_USEFUL"
        if control_type == "actual_no_trade_labels" and len(items) >= MIN_PROOF_SAMPLE and net_value > 0 and uplift > 0
        else "NO_EDGE_FOUND",
    }


def _filter_bucket_rows(items: list[dict[str, Any]], *, bucket_key: str, control_name: str) -> list[dict[str, Any]]:
    rows = []
    for bucket in sorted({str(item.get(bucket_key) or "UNKNOWN") for item in items}):
        subset = [item for item in items if str(item.get(bucket_key) or "UNKNOWN") == bucket]
        rows.append(
            {
                **_filter_summary_row(
                    control_name.upper(),
                    control_name,
                    subset,
                    actual_items=items,
                    comparison_items=subset,
                ),
                "row_type": "bucket",
                "bucket_type": bucket_key,
                "bucket": bucket,
            }
        )
    return rows


def _pin_group_rows(rows: list[dict[str, Any]], bucket_type: str, bucket: str) -> list[dict[str, Any]]:
    output = []
    for cohort in sorted({str(row.get("cohort")) for row in rows}):
        subset = [row for row in rows if str(row.get("cohort")) == cohort]
        count = len(subset)
        output.append(
            {
                "test_name": "expiry_pin_test",
                "cohort": cohort,
                "control_type": subset[0].get("control_type") if subset else cohort,
                "bucket_type": bucket_type,
                "bucket": bucket,
                "event_count": count,
                "pin_rate": _rate(subset, "pin_hit"),
                "average_close_distance": _mean([_float(row.get("close_distance")) for row in subset]),
                "sample_size_warning": count < MIN_PROOF_SAMPLE,
                "decision_label": "",
            }
        )
    actual = [row for row in rows if row.get("cohort") == "actual_top_wall"]
    control = [row for row in rows if row.get("cohort") == "matched_random_strike"]
    warning = len(actual) < MIN_PROOF_SAMPLE or len(control) < MIN_PROOF_SAMPLE
    pin_uplift = _rate(actual, "pin_hit") - _rate(control, "pin_hit")
    output.append(
        {
            "test_name": "expiry_pin_vs_control",
            "cohort": "actual_top_wall",
            "control_type": "matched_random_strike",
            "bucket_type": bucket_type,
            "bucket": bucket,
            "event_count": len(actual),
            "pin_rate": _rate(actual, "pin_hit"),
            "average_close_distance": _mean([_float(row.get("close_distance")) for row in actual]),
            "control_pin_rate": _rate(control, "pin_hit"),
            "pin_uplift_vs_control": pin_uplift,
            "sample_size_warning": warning,
            "decision_label": "MAP_USEFUL_NOT_TRADABLE" if not warning and pin_uplift > 0 else "NO_EDGE_FOUND",
        }
    )
    return output


def _accepted_beyond(path: list[dict[str, Any]], *, level: float, side: str, buffer_points: float) -> bool:
    for index in range(len(path) - 1):
        close = _float(path[index].get("close"))
        next_close = _float(path[index + 1].get("close"))
        if close is None or next_close is None:
            continue
        if side == "resistance" and close > level + buffer_points and next_close > level + buffer_points:
            return True
        if side == "support" and close < level - buffer_points and next_close < level - buffer_points:
            return True
    return False


def _rejected_from_wall(path: list[dict[str, Any]], *, level: float, side: str, buffer_points: float) -> bool:
    if not path:
        return False
    if side == "resistance":
        return any((_float(row.get("high")) or 0.0) >= level for row in path) and (
            _float(path[-1].get("close")) or level
        ) < level - buffer_points
    if side == "support":
        return any((_float(row.get("low")) or 0.0) <= level for row in path) and (
            _float(path[-1].get("close")) or level
        ) > level + buffer_points
    return False


def _continued_after_acceptance(path: list[dict[str, Any]], *, level: float, side: str) -> bool:
    if len(path) < 3:
        return False
    final_close = _float(path[-1].get("close"))
    if final_close is None:
        return False
    if side == "resistance":
        return final_close > level
    if side == "support":
        return final_close < level
    return False


def _random_filter_control_events(
    events: list[dict[str, Any]],
    count: int,
    rng: random.Random,
) -> list[dict[str, Any]]:
    candidates = [event for event in events if str(event.get("signal")) not in NO_TRADE_SIGNALS]
    if not candidates:
        candidates = events
    if not candidates:
        return []
    return [dict(rng.choice(candidates)) for _ in range(count)]


def _matched_filter_control_events(
    no_trade_rows: list[dict[str, Any]],
    directional_rows: list[dict[str, Any]],
    rng: random.Random,
) -> list[dict[str, Any]]:
    if not directional_rows:
        return []
    matched = []
    for event in no_trade_rows:
        candidates = [
            row
            for row in directional_rows
            if row.get("sigma_zone") == event.get("sigma_zone")
            and row.get("vol_regime") == event.get("vol_regime")
            and (row.get("dte_bucket") == event.get("dte_bucket") or not event.get("dte_bucket"))
        ]
        matched.append(dict(rng.choice(candidates or directional_rows)))
    return matched


def _matched_state_index(
    price_rows: list[dict[str, Any]],
    start_bar: dict[str, Any],
    rng: random.Random,
) -> int | None:
    candidates = [
        index
        for index, row in enumerate(price_rows[:-1])
        if index != price_rows.index(start_bar)
        and row.get("sigma_zone") == start_bar.get("sigma_zone")
        and row.get("vol_regime") == start_bar.get("vol_regime")
    ]
    if not candidates:
        candidates = list(range(max(len(price_rows) - 1, 0)))
    return rng.choice(candidates) if candidates else None


def _naive_wall_fade_direction(event: dict[str, Any]) -> int:
    side = str(event.get("wall_side") or "").lower()
    if side == "resistance":
        return -1
    if side == "support":
        return 1
    wall_level = _float(event.get("wall_level"))
    close = _float(event.get("close"))
    if wall_level is not None and close is not None:
        return -1 if wall_level >= close else 1
    sigma = _float(event.get("sigma_position"))
    if sigma is not None and abs(sigma) > 1.0:
        return -1 if sigma > 0 else 1
    return 0


def _first_price_index_at_or_after(price_rows: list[dict[str, Any]], timestamp: Any) -> int | None:
    target = _coerce_timestamp(timestamp)
    for index, row in enumerate(price_rows):
        row_time = _coerce_timestamp(row.get("timestamp"))
        if row_time is not None and target is not None and row_time >= target:
            return index
    return None


def _first_price_index_after(price_rows: list[dict[str, Any]], timestamp: Any) -> int | None:
    target = _coerce_timestamp(timestamp)
    for index, row in enumerate(price_rows):
        row_time = _coerce_timestamp(row.get("timestamp"))
        if row_time is not None and target is not None and row_time > target:
            return index
    return None


def _coerce_timestamp(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _level_side(*, level: float, close: float, explicit: Any) -> str:
    explicit_text = str(explicit or "").lower()
    if explicit_text in {"support", "resistance"}:
        return explicit_text
    return "resistance" if level >= close else "support"


def _event_day_tag(row: dict[str, Any]) -> str:
    tags = str(row.get("event_tags") or row.get("event_day_tag") or "").strip()
    if tags:
        return tags
    if row.get("has_cpi"):
        return "CPI"
    if row.get("has_nfp"):
        return "NFP"
    if row.get("has_fomc"):
        return "FOMC"
    return "NO_EVENT_DATA"


def _score_bucket(value: float | None) -> str:
    if value is None:
        return "unknown"
    if value >= 0.30:
        return "very_high"
    if value >= 0.20:
        return "high"
    if value >= 0.10:
        return "medium"
    return "low"


def _expiry_bucket(dte: float | None) -> str:
    if dte is None:
        return "UNKNOWN"
    if dte <= 0:
        return "EXPIRY_DAY"
    if dte <= 3:
        return "0_3D"
    if dte <= 7:
        return "4_7D"
    if dte <= 30:
        return "8_30D"
    return "31D_PLUS"


def _rate(rows: list[dict[str, Any]], key: str) -> float:
    return sum(1 for row in rows if bool(row.get(key))) / len(rows) if rows else 0.0


def _rate_by_value(rows: list[dict[str, Any]], predicate: Any) -> float:
    return sum(1 for row in rows if predicate(row)) / len(rows) if rows else 0.0


def _mean(values: Iterable[float | None]) -> float | None:
    clean = [value for value in values if value is not None]
    return sum(clean) / len(clean) if clean else None


def _net_filter_value(items: list[dict[str, Any]]) -> float:
    return sum(item["avoided_loss"] for item in items) - sum(item["opportunity_cost"] for item in items)


def _empty_level_outcome() -> dict[str, Any]:
    return {
        "touch": False,
        "rejection": False,
        "acceptance": False,
        "wick_only_probe": False,
        "squeeze": False,
        "continuation": False,
        "max_abs_close_move": None,
    }


def _group_rows(rows: list[dict[str, Any]], key: str) -> dict[Any, list[dict[str, Any]]]:
    grouped: dict[Any, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(row.get(key), []).append(row)
    return grouped


def _float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _report_head(frame: pl.DataFrame, rows: int = 20) -> pl.DataFrame:
    return frame.head(rows) if not frame.is_empty() else frame


def _frame_markdown(frame: pl.DataFrame) -> str:
    if frame.is_empty():
        return "_No rows._"
    columns = frame.columns
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in frame.to_dicts():
        lines.append("| " + " | ".join(_markdown_cell(row.get(column, "")) for column in columns) + " |")
    return "\n".join(lines)


def _markdown_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _empty_wall_events() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "event_timestamp": pl.Datetime(time_zone="UTC"),
            "level": pl.Float64,
            "cohort": pl.String,
            "control_type": pl.String,
        }
    )


def _empty_market_map_report() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "row_type": pl.String,
            "test_name": pl.String,
            "cohort": pl.String,
            "control_type": pl.String,
            "event_count": pl.Int64,
            "touch_rate": pl.Float64,
            "rejection_rate": pl.Float64,
            "acceptance_rate": pl.Float64,
            "touch_uplift_vs_control": pl.Float64,
            "sample_size_warning": pl.Boolean,
            "decision_label": pl.String,
        }
    )


def _empty_filter_report() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "row_type": pl.String,
            "cohort": pl.String,
            "control_type": pl.String,
            "no_trade_count": pl.Int64,
            "avoided_losing_trade_count": pl.Int64,
            "avoided_winning_trade_count": pl.Int64,
            "avoided_loss_amount": pl.Float64,
            "opportunity_cost": pl.Float64,
            "net_filter_value": pl.Float64,
            "decision_label": pl.String,
        }
    )


def _empty_pin_report() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "test_name": pl.String,
            "cohort": pl.String,
            "control_type": pl.String,
            "event_count": pl.Int64,
            "pin_rate": pl.Float64,
            "average_close_distance": pl.Float64,
            "sample_size_warning": pl.Boolean,
            "decision_label": pl.String,
        }
    )
