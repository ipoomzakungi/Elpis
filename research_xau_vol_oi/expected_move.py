"""Implied-volatility expected move calculations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from math import sqrt
from typing import Any

import polars as pl

from research_xau_vol_oi.config import ResearchConfig


@dataclass(frozen=True)
class ExpectedMove:
    """IV-derived expected move snapshot."""

    reference_price: float
    annualized_iv_percent: float
    time_remaining_fraction: float
    one_sd_full_day: float
    one_sd_remaining: float
    two_sd_remaining: float
    three_sd_remaining: float
    sigma_position: float | None

    def as_dict(self) -> dict[str, float | None]:
        """Return a flat dictionary for DataFrame construction."""

        return {
            "reference_price": self.reference_price,
            "annualized_iv_percent": self.annualized_iv_percent,
            "time_remaining_fraction": self.time_remaining_fraction,
            "one_sd_full_day": self.one_sd_full_day,
            "one_sd_remaining": self.one_sd_remaining,
            "two_sd_remaining": self.two_sd_remaining,
            "three_sd_remaining": self.three_sd_remaining,
            "sigma_position": self.sigma_position,
        }


def compute_expected_move(
    *,
    reference_price: float,
    annualized_iv_percent: float,
    time_remaining_fraction: float,
    spot_price: float | None = None,
    session_open: float | None = None,
    trading_days: int = 252,
) -> ExpectedMove:
    """Implement the IV expected-move formula from the research brief."""

    if reference_price <= 0:
        raise ValueError("reference_price must be greater than 0")
    if annualized_iv_percent <= 0:
        raise ValueError("annualized_iv_percent must be greater than 0")
    if not 0 <= time_remaining_fraction <= 1:
        raise ValueError("time_remaining_fraction must be between 0 and 1")
    if trading_days <= 0:
        raise ValueError("trading_days must be greater than 0")

    one_sd_full_day = reference_price * (annualized_iv_percent / 100.0) / sqrt(trading_days)
    one_sd_remaining = one_sd_full_day * sqrt(time_remaining_fraction)
    sigma_position = None
    if spot_price is not None and session_open is not None and one_sd_remaining > 0:
        sigma_position = (spot_price - session_open) / one_sd_remaining
    return ExpectedMove(
        reference_price=reference_price,
        annualized_iv_percent=annualized_iv_percent,
        time_remaining_fraction=time_remaining_fraction,
        one_sd_full_day=one_sd_full_day,
        one_sd_remaining=one_sd_remaining,
        two_sd_remaining=2.0 * one_sd_remaining,
        three_sd_remaining=3.0 * one_sd_remaining,
        sigma_position=sigma_position,
    )


def add_expected_move_columns(
    price: pl.DataFrame,
    *,
    annualized_iv_percent: float,
    config: ResearchConfig | None = None,
) -> pl.DataFrame:
    """Add session-open, 1SD/2SD/3SD, and sigma-position columns to price bars."""

    cfg = config or ResearchConfig()
    if price.is_empty():
        return price

    session_open_by_date = _session_open_by_date(price)
    rows: list[dict[str, Any]] = []
    for raw in price.to_dicts():
        timestamp = raw["timestamp"]
        if not isinstance(timestamp, datetime):
            raise ValueError("price timestamp must be a datetime")
        session_open = session_open_by_date.get(raw["session_date"], raw["open"])
        fraction = time_remaining_fraction(timestamp, config=cfg)
        move = compute_expected_move(
            reference_price=float(raw["close"]),
            annualized_iv_percent=annualized_iv_percent,
            time_remaining_fraction=fraction,
            spot_price=float(raw["close"]),
            session_open=float(session_open),
            trading_days=cfg.annual_trading_days,
        )
        rows.append(
            {
                **raw,
                "session_open": float(session_open),
                **move.as_dict(),
                "sigma_zone": sigma_zone(move.sigma_position),
                "upper_1sd": float(session_open) + move.one_sd_remaining,
                "lower_1sd": float(session_open) - move.one_sd_remaining,
                "upper_2sd": float(session_open) + move.two_sd_remaining,
                "lower_2sd": float(session_open) - move.two_sd_remaining,
                "upper_3sd": float(session_open) + move.three_sd_remaining,
                "lower_3sd": float(session_open) - move.three_sd_remaining,
            }
        )
    return pl.DataFrame(rows)


def add_expected_move_columns_asof_options(
    price: pl.DataFrame,
    options: pl.DataFrame,
    *,
    config: ResearchConfig | None = None,
) -> pl.DataFrame:
    """Add IV bands using only the latest option IV snapshot known at each bar.

    Bars before the first usable option IV snapshot are retained and marked as
    ``MISSING_IV`` so no-trade periods remain visible instead of being dropped.
    """

    cfg = config or ResearchConfig()
    if price.is_empty():
        return price
    iv_snapshots = _iv_snapshots(options)
    session_open_by_date = _session_open_by_date(price)
    rows: list[dict[str, Any]] = []
    snapshot_index = -1
    for raw in price.sort("timestamp").to_dicts():
        timestamp = raw["timestamp"]
        if not isinstance(timestamp, datetime):
            raise ValueError("price timestamp must be a datetime")
        while (
            snapshot_index + 1 < len(iv_snapshots)
            and iv_snapshots[snapshot_index + 1]["timestamp"] <= timestamp
        ):
            snapshot_index += 1

        session_open = session_open_by_date.get(raw["session_date"], raw["open"])
        if snapshot_index < 0:
            rows.append(
                {
                    **raw,
                    "session_open": float(session_open),
                    "reference_price": float(raw["close"]),
                    "annualized_iv_percent": None,
                    "iv_available_timestamp": None,
                    "time_remaining_fraction": time_remaining_fraction(timestamp, config=cfg),
                    "one_sd_full_day": None,
                    "one_sd_remaining": None,
                    "two_sd_remaining": None,
                    "three_sd_remaining": None,
                    "sigma_position": None,
                    "sigma_zone": "unknown",
                    "upper_1sd": None,
                    "lower_1sd": None,
                    "upper_2sd": None,
                    "lower_2sd": None,
                    "upper_3sd": None,
                    "lower_3sd": None,
                    "data_quality_state": "MISSING_IV",
                }
            )
            continue

        snapshot = iv_snapshots[snapshot_index]
        fraction = time_remaining_fraction(timestamp, config=cfg)
        move = compute_expected_move(
            reference_price=float(raw["close"]),
            annualized_iv_percent=float(snapshot["iv_percent"]),
            time_remaining_fraction=fraction,
            spot_price=float(raw["close"]),
            session_open=float(session_open),
            trading_days=cfg.annual_trading_days,
        )
        rows.append(
            {
                **raw,
                "session_open": float(session_open),
                **move.as_dict(),
                "iv_available_timestamp": snapshot["timestamp"],
                "sigma_zone": sigma_zone(move.sigma_position),
                "upper_1sd": float(session_open) + move.one_sd_remaining,
                "lower_1sd": float(session_open) - move.one_sd_remaining,
                "upper_2sd": float(session_open) + move.two_sd_remaining,
                "lower_2sd": float(session_open) - move.two_sd_remaining,
                "upper_3sd": float(session_open) + move.three_sd_remaining,
                "lower_3sd": float(session_open) - move.three_sd_remaining,
                "data_quality_state": "VALID",
            }
        )
    return pl.DataFrame(rows)


def time_remaining_fraction(
    timestamp: datetime,
    *,
    config: ResearchConfig | None = None,
) -> float:
    """Estimate remaining research session fraction from UTC timestamp."""

    cfg = config or ResearchConfig()
    session_start = datetime.combine(
        timestamp.date(),
        time(hour=cfg.session_open_hour_utc),
        tzinfo=timestamp.tzinfo,
    )
    session_end = datetime.combine(
        timestamp.date(),
        time(hour=cfg.session_close_hour_utc),
        tzinfo=timestamp.tzinfo,
    )
    total_seconds = (session_end - session_start).total_seconds()
    if total_seconds <= 0:
        return 1.0
    remaining = (session_end - timestamp).total_seconds()
    return max(0.0, min(1.0, remaining / total_seconds))


def sigma_zone(sigma_position: float | None) -> str:
    """Bucket sigma position for reporting and grouped performance."""

    if sigma_position is None:
        return "unknown"
    absolute = abs(sigma_position)
    if absolute <= 1:
        return "inside_1sd"
    if absolute <= 2:
        return "between_1sd_2sd"
    if absolute <= 3:
        return "between_2sd_3sd"
    return "beyond_3sd"


def _session_open_by_date(price: pl.DataFrame) -> dict[str, float]:
    result: dict[str, float] = {}
    for raw in price.sort("timestamp").to_dicts():
        session_date = raw["session_date"]
        if session_date not in result:
            result[session_date] = float(raw["open"])
    return result


def _iv_snapshots(options: pl.DataFrame) -> list[dict[str, Any]]:
    if options.is_empty() or "iv_percent" not in options.columns:
        return []
    snapshots = (
        options.filter(pl.col("iv_percent").is_not_null())
        .group_by("timestamp")
        .agg(pl.col("iv_percent").mean().alias("iv_percent"))
        .sort("timestamp")
    )
    return snapshots.to_dicts()
