"""Open-interest wall scoring and wall table construction."""

from __future__ import annotations

from collections import defaultdict
from math import isfinite
from typing import Any

import polars as pl

from research_xau_vol_oi.config import ResearchConfig, WallSide


def dte_weight(dte: float | None, *, floor: float = 0.20) -> float:
    """Return a bounded weight that is higher for nearer expiries."""

    if dte is None:
        return 0.50
    if dte < 0:
        raise ValueError("dte must be greater than or equal to 0")
    return max(floor, min(1.0, 1.0 / (1.0 + dte / 30.0)))


def freshness_weight(
    *,
    oi_change: float | None,
    volume: float | None,
    max_abs_oi_change: float | None,
    max_volume: float | None,
) -> float:
    """Score recent OI change or intraday volume abnormality."""

    contribution = 0.0
    if oi_change is not None and max_abs_oi_change and max_abs_oi_change > 0:
        contribution += 0.35 * min(1.0, abs(oi_change) / max_abs_oi_change)
    if volume is not None and max_volume and max_volume > 0:
        contribution += 0.40 * min(1.0, volume / max_volume)
    return 1.0 + min(0.75, contribution)


def proximity_weight(
    *,
    wall_level: float | None,
    spot_price: float | None,
    one_sd_remaining: float | None,
    config: ResearchConfig | None = None,
) -> float:
    """Score proximity to spot and to current IV SD boundaries."""

    cfg = config or ResearchConfig()
    if wall_level is None or spot_price is None:
        return 1.0
    distance = abs(wall_level - spot_price)
    scale = max(cfg.proximity_points, (one_sd_remaining or cfg.proximity_points) * 0.5)
    base = max(0.20, 1.0 - distance / (scale * 4.0))
    if one_sd_remaining and one_sd_remaining > 0:
        boundary_distance = min(
            abs(wall_level - (spot_price + one_sd_remaining)),
            abs(wall_level - (spot_price - one_sd_remaining)),
        )
        if boundary_distance <= one_sd_remaining * cfg.sd_boundary_fraction:
            base += 0.15
    return min(1.25, base)


def compute_wall_score(
    *,
    normalized_total_oi: float,
    dte_component: float,
    freshness_component: float,
    proximity_component: float,
) -> float:
    """Compute the transparent wall score formula."""

    for name, value in {
        "normalized_total_oi": normalized_total_oi,
        "dte_component": dte_component,
        "freshness_component": freshness_component,
        "proximity_component": proximity_component,
    }.items():
        if value < 0 or not isfinite(value):
            raise ValueError(f"{name} must be finite and non-negative")
    return normalized_total_oi * dte_component * freshness_component * proximity_component


def build_oi_walls(
    options: pl.DataFrame,
    *,
    reference_price: float | None = None,
    one_sd_remaining: float | None = None,
    config: ResearchConfig | None = None,
) -> pl.DataFrame:
    """Group standardized option rows into basis-adjusted OI wall rows."""

    cfg = config or ResearchConfig()
    if options.is_empty():
        return _empty_wall_frame()

    grouped: dict[tuple[Any, Any, float], list[dict[str, Any]]] = defaultdict(list)
    for raw in options.to_dicts():
        grouped[(raw["timestamp"], raw["expiry"], float(raw["strike"]))].append(raw)

    max_total_by_timestamp: dict[Any, float] = defaultdict(float)
    max_change_by_timestamp: dict[Any, float] = defaultdict(float)
    max_volume_by_timestamp: dict[Any, float] = defaultdict(float)
    aggregate_rows: list[dict[str, Any]] = []
    for key, rows in grouped.items():
        timestamp, expiry, strike = key
        call_oi = sum(float(row.get("call_oi") or 0.0) for row in rows)
        put_oi = sum(float(row.get("put_oi") or 0.0) for row in rows)
        total_oi = call_oi + put_oi
        oi_change = _sum_optional(row.get("oi_change") for row in rows)
        volume = _sum_optional(row.get("volume") for row in rows)
        aggregate = {
            "timestamp": timestamp,
            "expiry": expiry,
            "strike": strike,
            "call_oi": call_oi,
            "put_oi": put_oi,
            "total_oi": total_oi,
            "oi_change": oi_change,
            "volume": volume,
            "dte": _min_optional(row.get("dte") for row in rows),
            "basis": _first_present(row.get("basis") for row in rows),
            "basis_source": _first_present(row.get("basis_source") for row in rows) or "missing",
            "spot_equivalent_strike": _first_present(
                row.get("spot_equivalent_strike") for row in rows
            ),
            "iv_percent": _first_present(row.get("iv_percent") for row in rows),
        }
        aggregate_rows.append(aggregate)
        max_total_by_timestamp[timestamp] = max(max_total_by_timestamp[timestamp], total_oi)
        if oi_change is not None:
            max_change_by_timestamp[timestamp] = max(
                max_change_by_timestamp[timestamp],
                abs(oi_change),
            )
        if volume is not None:
            max_volume_by_timestamp[timestamp] = max(max_volume_by_timestamp[timestamp], volume)

    wall_rows: list[dict[str, Any]] = []
    for row in aggregate_rows:
        max_total = max_total_by_timestamp[row["timestamp"]]
        normalized_total_oi = row["total_oi"] / max_total if max_total > 0 else 0.0
        dte_component = dte_weight(row["dte"])
        fresh_component = freshness_weight(
            oi_change=row["oi_change"],
            volume=row["volume"],
            max_abs_oi_change=max_change_by_timestamp.get(row["timestamp"]),
            max_volume=max_volume_by_timestamp.get(row["timestamp"]),
        )
        level = row["spot_equivalent_strike"]
        prox_component = proximity_weight(
            wall_level=level,
            spot_price=reference_price,
            one_sd_remaining=one_sd_remaining,
            config=cfg,
        )
        score = compute_wall_score(
            normalized_total_oi=normalized_total_oi,
            dte_component=dte_component,
            freshness_component=fresh_component,
            proximity_component=prox_component,
        )
        wall_rows.append(
            {
                **row,
                "wall_id": _wall_id(row["timestamp"], row["expiry"], row["strike"]),
                "wall_level": level,
                "normalized_total_oi": normalized_total_oi,
                "dte_weight": dte_component,
                "freshness_weight": fresh_component,
                "proximity_weight": prox_component,
                "wall_score": score,
                "wall_side": classify_wall_side(
                    call_oi=row["call_oi"],
                    put_oi=row["put_oi"],
                    wall_level=level,
                    spot_price=reference_price,
                ).value,
                "distance_to_spot": abs(level - reference_price)
                if level is not None and reference_price is not None
                else None,
                "largest_near_expiry_wall": False,
                "low_oi_gap_to_next_wall": False,
                "next_wall_distance": None,
            }
        )

    wall_rows = _mark_pin_and_gap_context(wall_rows, config=cfg)
    if not wall_rows:
        return _empty_wall_frame()
    return pl.DataFrame(wall_rows).sort(["timestamp", "wall_score"], descending=[False, True])


def classify_wall_side(
    *,
    call_oi: float,
    put_oi: float,
    wall_level: float | None,
    spot_price: float | None,
) -> WallSide:
    """Classify a wall as support, resistance, mixed, or unknown."""

    if wall_level is None or spot_price is None:
        return WallSide.UNKNOWN
    if put_oi > call_oi * 1.2 and wall_level <= spot_price:
        return WallSide.SUPPORT
    if call_oi > put_oi * 1.2 and wall_level >= spot_price:
        return WallSide.RESISTANCE
    if call_oi > 0 and put_oi > 0:
        return WallSide.MIXED
    return WallSide.UNKNOWN


def _mark_pin_and_gap_context(
    rows: list[dict[str, Any]],
    *,
    config: ResearchConfig,
) -> list[dict[str, Any]]:
    by_timestamp: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_timestamp[row["timestamp"]].append(row)

    marked: list[dict[str, Any]] = []
    for timestamp_rows in by_timestamp.values():
        near_expiry_rows = [
            row
            for row in timestamp_rows
            if row.get("dte") is not None and row["dte"] <= config.near_expiry_days
        ]
        largest = max(near_expiry_rows or timestamp_rows, key=lambda row: row["total_oi"])
        sorted_by_level = sorted(
            [row for row in timestamp_rows if row.get("wall_level") is not None],
            key=lambda row: row["wall_level"],
        )
        distance_by_id: dict[str, float | None] = {}
        for index, row in enumerate(sorted_by_level):
            next_distances = []
            if index > 0:
                next_distances.append(abs(row["wall_level"] - sorted_by_level[index - 1]["wall_level"]))
            if index < len(sorted_by_level) - 1:
                next_distances.append(abs(row["wall_level"] - sorted_by_level[index + 1]["wall_level"]))
            distance_by_id[row["wall_id"]] = min(next_distances) if next_distances else None

        for row in timestamp_rows:
            next_distance = distance_by_id.get(row["wall_id"])
            marked.append(
                {
                    **row,
                    "largest_near_expiry_wall": row["wall_id"] == largest["wall_id"],
                    "next_wall_distance": next_distance,
                    "low_oi_gap_to_next_wall": (
                        next_distance is not None and next_distance >= config.low_oi_gap_points
                    ),
                }
            )
    return marked


def _sum_optional(values: Any) -> float | None:
    present = [float(value) for value in values if value is not None]
    return sum(present) if present else None


def _min_optional(values: Any) -> float | None:
    present = [float(value) for value in values if value is not None]
    return min(present) if present else None


def _first_present(values: Any) -> Any | None:
    for value in values:
        if value is not None:
            return value
    return None


def _wall_id(timestamp: Any, expiry: Any, strike: float) -> str:
    stamp = str(timestamp).replace(":", "").replace("+", "").replace(" ", "T")
    expiry_text = str(expiry).replace(":", "").replace(" ", "_")
    strike_text = f"{strike:g}".replace(".", "_")
    return f"wall_{stamp}_{expiry_text}_{strike_text}"


def _empty_wall_frame() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "timestamp": pl.Datetime(time_zone="UTC"),
            "expiry": pl.String,
            "strike": pl.Float64,
            "wall_id": pl.String,
            "wall_level": pl.Float64,
            "wall_score": pl.Float64,
        }
    )
