from datetime import UTC, datetime, timedelta

import polars as pl

from research_xau_vol_oi.zone_classifier import build_signal_events


def test_signal_events_use_only_available_wall_timestamps() -> None:
    base = datetime(2026, 5, 21, 10, 0, tzinfo=UTC)
    price = pl.DataFrame(
        [
            {
                "timestamp": base + timedelta(minutes=15 * index),
                "open": 2400.0 + index,
                "high": 2404.0 + index,
                "low": 2398.0 + index,
                "close": 2401.0 + index,
                "volume": 100.0,
                "one_sd_remaining": 20.0,
                "sigma_position": 0.5,
                "sigma_zone": "inside_1sd",
                "data_quality_state": "VALID",
            }
            for index in range(5)
        ]
    )
    walls = pl.DataFrame(
        [
            {
                "timestamp": base + timedelta(minutes=30),
                "wall_id": "wall_available_later",
                "wall_level": 2405.0,
                "wall_score": 0.4,
                "wall_side": "resistance",
                "basis": 7.0,
                "basis_available": True,
                "dte": 2.0,
            }
        ]
    )

    events = build_signal_events(price, walls)
    violations = events.filter(
        pl.col("available_wall_timestamp").is_not_null()
        & (pl.col("available_wall_timestamp") > pl.col("event_timestamp"))
    )

    assert violations.is_empty()
