"""Deterministic wall/range/no-trade signal classification."""

from __future__ import annotations

from typing import Any

import polars as pl

from research_xau_vol_oi.config import ResearchConfig, Signal, WallSide
from research_xau_vol_oi.oi_wall_engine import (
    classify_wall_side,
    compute_wall_score,
    proximity_weight,
)


def acceptance_confirmed(
    *,
    level: float,
    close: float,
    next_close: float | None,
    direction: str,
    buffer_points: float,
) -> bool:
    """Confirm breakout acceptance with close beyond level and next-bar hold."""

    if next_close is None:
        return False
    if direction == "long":
        return close > level + buffer_points and next_close > level + buffer_points
    if direction == "short":
        return close < level - buffer_points and next_close < level - buffer_points
    raise ValueError("direction must be 'long' or 'short'")


def classify_bar(
    bar: dict[str, Any],
    *,
    wall: dict[str, Any] | None,
    previous_bar: dict[str, Any] | None = None,
    next_bar: dict[str, Any] | None = None,
    config: ResearchConfig | None = None,
) -> dict[str, Any]:
    """Classify one bar against the best available wall as a research label."""

    cfg = config or ResearchConfig()
    close = _float(bar.get("close"))
    high = _float(bar.get("high"))
    low = _float(bar.get("low"))
    one_sd = _float(bar.get("one_sd_remaining"))
    sigma_position = _float(bar.get("sigma_position"))

    if _hard_no_trade(bar, wall, one_sd=one_sd):
        return _event(bar, wall, Signal.NO_TRADE, reason="data_quality_or_mapping_block")

    assert wall is not None
    wall_level = _float(wall.get("wall_level"))
    wall_score = _float(wall.get("wall_score")) or 0.0
    side = str(wall.get("wall_side") or WallSide.UNKNOWN.value)
    distance = abs(close - wall_level) if close is not None and wall_level is not None else None
    near_threshold = max(cfg.proximity_points, (one_sd or cfg.proximity_points) * cfg.proximity_sd_fraction)
    near_wall = distance is not None and distance <= near_threshold
    strong_wall = wall_score >= cfg.strong_wall_score
    next_close = _float(next_bar.get("close")) if next_bar else None

    if _is_resistance_rejection(side, high, close, wall_level, cfg):
        return _event(bar, wall, Signal.FADE_WALL_SHORT, reason="resistance_rejection")
    if _is_support_rejection(side, low, close, wall_level, cfg):
        return _event(bar, wall, Signal.FADE_WALL_LONG, reason="support_rejection")

    vol_expanded = _volatility_expanded(bar, previous_bar, config=cfg)
    if _break_long(close, next_close, wall_level, side, cfg) and (
        vol_expanded or not cfg.breakout_requires_vol_expansion
    ):
        return _event(bar, wall, Signal.BREAK_WALL_LONG, reason="accepted_above_resistance")
    if _break_short(close, next_close, wall_level, side, cfg) and (
        vol_expanded or not cfg.breakout_requires_vol_expansion
    ):
        return _event(bar, wall, Signal.BREAK_WALL_SHORT, reason="accepted_below_support")

    if _pin_risk(bar, wall, distance, config=cfg):
        return _event(bar, wall, Signal.PIN_RISK, reason="largest_near_expiry_wall_near_price")
    if _squeeze_risk(wall, near_wall, strong_wall):
        return _event(bar, wall, Signal.SQUEEZE_RISK, reason="low_oi_gap_toward_next_wall")
    if near_wall and strong_wall:
        return _event(bar, wall, Signal.WATCH_WALL, reason="price_near_strong_wall")
    if sigma_position is not None and abs(sigma_position) <= 1.0:
        return _event(bar, wall, Signal.NO_TRADE_MIDDLE, reason="inside_middle_1sd")
    return _event(bar, wall, Signal.NO_TRADE, reason="no_deterministic_gate")


def build_signal_events(
    price_features: pl.DataFrame,
    walls: pl.DataFrame,
    *,
    config: ResearchConfig | None = None,
) -> pl.DataFrame:
    """Classify bars using only walls available at or before the bar timestamp."""

    cfg = config or ResearchConfig()
    price_rows = price_features.sort("timestamp").to_dicts()
    wall_rows = walls.sort("timestamp").to_dicts() if not walls.is_empty() else []
    events: list[dict[str, Any]] = []
    for index, bar in enumerate(price_rows):
        previous_bar = price_rows[index - 1] if index > 0 else None
        next_bar = price_rows[index + 1] if index < len(price_rows) - 1 else None
        wall = choose_wall_for_bar(bar, wall_rows, config=cfg)
        event = classify_bar(
            bar,
            wall=wall,
            previous_bar=previous_bar,
            next_bar=next_bar,
            config=cfg,
        )
        if event["signal"] in {Signal.BREAK_WALL_LONG.value, Signal.BREAK_WALL_SHORT.value}:
            if next_bar is None:
                continue
            event["event_timestamp"] = next_bar["timestamp"]
            event["confirmation_timestamp"] = next_bar["timestamp"]
        events.append(event)
    return pl.DataFrame(events) if events else _empty_events()


def choose_wall_for_bar(
    bar: dict[str, Any],
    walls: list[dict[str, Any]],
    *,
    config: ResearchConfig | None = None,
) -> dict[str, Any] | None:
    """Choose the nearest high-score wall with timestamp <= the bar timestamp."""

    cfg = config or ResearchConfig()
    timestamp = bar.get("timestamp")
    close = _float(bar.get("close"))
    if timestamp is None or close is None:
        return None
    candidates = [
        wall
        for wall in walls
        if wall.get("timestamp") <= timestamp
        and (_float(wall.get("wall_score")) or 0.0) >= cfg.min_wall_score
    ]
    if not candidates:
        return None
    dynamic_candidates = [_dynamic_wall_for_bar(wall, bar, config=cfg) for wall in candidates]
    return min(
        dynamic_candidates,
        key=lambda wall: (
            abs(close - (_float(wall.get("wall_level")) or close)),
            -(_float(wall.get("wall_score")) or 0.0),
        ),
    )


def _dynamic_wall_for_bar(
    wall: dict[str, Any],
    bar: dict[str, Any],
    *,
    config: ResearchConfig,
) -> dict[str, Any]:
    """Recompute proximity-sensitive wall fields as of the signal bar."""

    close = _float(bar.get("close"))
    level = _float(wall.get("wall_level"))
    dynamic = dict(wall)
    if close is None or level is None:
        return dynamic

    dynamic["distance_to_spot"] = abs(level - close)
    dynamic["wall_side"] = classify_wall_side(
        call_oi=_float(wall.get("call_oi")) or 0.0,
        put_oi=_float(wall.get("put_oi")) or 0.0,
        wall_level=level,
        spot_price=close,
    ).value
    if all(
        wall.get(column) is not None
        for column in (
            "normalized_total_oi",
            "dte_weight",
            "freshness_weight",
        )
    ):
        prox = proximity_weight(
            wall_level=level,
            spot_price=close,
            one_sd_remaining=_float(bar.get("one_sd_remaining")),
            config=config,
        )
        dynamic["proximity_weight"] = prox
        dynamic["wall_score"] = compute_wall_score(
            normalized_total_oi=float(wall["normalized_total_oi"]),
            dte_component=float(wall["dte_weight"]),
            freshness_component=float(wall["freshness_weight"]),
            proximity_component=prox,
        )
    return dynamic


def _hard_no_trade(
    bar: dict[str, Any],
    wall: dict[str, Any] | None,
    *,
    one_sd: float | None,
) -> bool:
    data_quality_state = str(bar.get("data_quality_state") or "VALID")
    if data_quality_state not in {"VALID", "valid"}:
        return True
    if one_sd is None or one_sd <= 0:
        return True
    if wall is None:
        return True
    if not wall.get("basis_available", wall.get("basis") is not None):
        return True
    return _float(wall.get("wall_level")) is None


def _event(
    bar: dict[str, Any],
    wall: dict[str, Any] | None,
    signal: Signal,
    *,
    reason: str,
) -> dict[str, Any]:
    wall = wall or {}
    return {
        "event_timestamp": bar.get("timestamp"),
        "source_bar_timestamp": bar.get("timestamp"),
        "available_wall_timestamp": wall.get("timestamp"),
        "signal": signal.value,
        "reason": reason,
        "close": bar.get("close"),
        "sigma_position": bar.get("sigma_position"),
        "sigma_zone": bar.get("sigma_zone"),
        "vol_regime": bar.get("vol_regime"),
        "wall_id": wall.get("wall_id"),
        "wall_level": wall.get("wall_level"),
        "wall_score": wall.get("wall_score"),
        "wall_score_bucket": _wall_score_bucket(_float(wall.get("wall_score"))),
        "distance_to_nearest_wall": wall.get("distance_to_spot"),
        "freshness_weight": wall.get("freshness_weight"),
        "dte_weight": wall.get("dte_weight"),
        "proximity_weight": wall.get("proximity_weight"),
        "dte": wall.get("dte"),
        "dte_bucket": _dte_bucket(_float(wall.get("dte"))),
        "wall_side": wall.get("wall_side"),
        "largest_near_expiry_wall": wall.get("largest_near_expiry_wall"),
        "low_oi_gap_to_next_wall": wall.get("low_oi_gap_to_next_wall"),
        "next_wall_distance": wall.get("next_wall_distance"),
        "research_only": True,
    }


def _is_resistance_rejection(
    side: str,
    high: float | None,
    close: float | None,
    level: float | None,
    config: ResearchConfig,
) -> bool:
    return (
        side in {WallSide.RESISTANCE.value, WallSide.MIXED.value}
        and high is not None
        and close is not None
        and level is not None
        and high >= level
        and close < level - config.acceptance_buffer_points
    )


def _is_support_rejection(
    side: str,
    low: float | None,
    close: float | None,
    level: float | None,
    config: ResearchConfig,
) -> bool:
    return (
        side in {WallSide.SUPPORT.value, WallSide.MIXED.value}
        and low is not None
        and close is not None
        and level is not None
        and low <= level
        and close > level + config.acceptance_buffer_points
    )


def _break_long(
    close: float | None,
    next_close: float | None,
    level: float | None,
    side: str,
    config: ResearchConfig,
) -> bool:
    return side in {WallSide.RESISTANCE.value, WallSide.MIXED.value} and level is not None and (
        close is not None
        and acceptance_confirmed(
            level=level,
            close=close,
            next_close=next_close,
            direction="long",
            buffer_points=config.acceptance_buffer_points,
        )
    )


def _break_short(
    close: float | None,
    next_close: float | None,
    level: float | None,
    side: str,
    config: ResearchConfig,
) -> bool:
    return side in {WallSide.SUPPORT.value, WallSide.MIXED.value} and level is not None and (
        close is not None
        and acceptance_confirmed(
            level=level,
            close=close,
            next_close=next_close,
            direction="short",
            buffer_points=config.acceptance_buffer_points,
        )
    )


def _pin_risk(
    bar: dict[str, Any],
    wall: dict[str, Any],
    distance: float | None,
    *,
    config: ResearchConfig,
) -> bool:
    one_sd = _float(bar.get("one_sd_remaining")) or config.proximity_points
    return (
        bool(wall.get("largest_near_expiry_wall"))
        and (_float(wall.get("wall_score")) or 0.0) >= config.pin_wall_score
        and distance is not None
        and distance <= max(config.proximity_points, one_sd * config.proximity_sd_fraction)
    )


def _squeeze_risk(wall: dict[str, Any], near_wall: bool, strong_wall: bool) -> bool:
    return near_wall and strong_wall and bool(wall.get("low_oi_gap_to_next_wall"))


def _volatility_expanded(
    bar: dict[str, Any],
    previous_bar: dict[str, Any] | None,
    *,
    config: ResearchConfig,
) -> bool:
    if previous_bar is None:
        return False
    rv = _float(bar.get("rv_percent"))
    prior_rv = _float(previous_bar.get("rv_percent"))
    if rv is not None and prior_rv is not None and prior_rv > 0:
        return rv >= prior_rv * config.vol_expansion_multiple
    volume = _float(bar.get("volume"))
    prior_volume = _float(previous_bar.get("volume"))
    return volume is not None and prior_volume is not None and volume > prior_volume


def _wall_score_bucket(value: float | None) -> str:
    if value is None:
        return "unknown"
    if value >= 0.30:
        return "high"
    if value >= 0.15:
        return "medium"
    return "low"


def _dte_bucket(value: float | None) -> str:
    if value is None:
        return "unknown"
    if value <= 3:
        return "0_3d"
    if value <= 10:
        return "4_10d"
    if value <= 30:
        return "11_30d"
    return "over_30d"


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _empty_events() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "event_timestamp": pl.Datetime(time_zone="UTC"),
            "source_bar_timestamp": pl.Datetime(time_zone="UTC"),
            "available_wall_timestamp": pl.Datetime(time_zone="UTC"),
            "signal": pl.String,
            "reason": pl.String,
        }
    )
