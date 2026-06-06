from datetime import UTC, datetime, timedelta

import polars as pl

from research_xau_vol_oi.backtest import backtest_all_scenarios
from research_xau_vol_oi.config import Signal
from research_xau_vol_oi.oi_wall_engine import (
    compute_wall_score,
    dte_weight,
    freshness_weight,
    proximity_weight,
)


def test_wall_score_increases_with_nearer_expiry() -> None:
    near = compute_wall_score(
        normalized_total_oi=0.8,
        dte_component=dte_weight(2),
        freshness_component=1.0,
        proximity_component=1.0,
    )
    far = compute_wall_score(
        normalized_total_oi=0.8,
        dte_component=dte_weight(60),
        freshness_component=1.0,
        proximity_component=1.0,
    )

    assert near > far


def test_wall_score_increases_with_freshness() -> None:
    neutral = freshness_weight(
        oi_change=None,
        volume=None,
        max_abs_oi_change=100.0,
        max_volume=1000.0,
    )
    fresh = freshness_weight(
        oi_change=100.0,
        volume=1000.0,
        max_abs_oi_change=100.0,
        max_volume=1000.0,
    )

    assert fresh > neutral


def test_wall_score_increases_with_proximity() -> None:
    near = proximity_weight(wall_level=2402.0, spot_price=2400.0, one_sd_remaining=25.0)
    far = proximity_weight(wall_level=2500.0, spot_price=2400.0, one_sd_remaining=25.0)

    assert near > far


def test_backtest_includes_oi_wall_and_bollinger_baselines() -> None:
    base = datetime(2026, 5, 21, 10, 0, tzinfo=UTC)
    price = pl.DataFrame(
        [
            {
                "timestamp": base + timedelta(minutes=index),
                "open": 100.0 + index,
                "high": 101.0 + index,
                "low": 99.0 + index,
                "close": 100.0 + index,
                "wall_level": 101.0 + index,
                "wall_score": 0.5,
                "wall_side": "resistance",
                "wall_score_bucket": "high",
                "dte_bucket": "0_3d",
                "sigma_position": 0.0,
                "sigma_zone": "inside_1sd",
                "vol_regime": "BALANCED",
                "bb_upper": 100.0,
                "bb_lower": 90.0,
            }
            for index in range(12)
        ]
    )
    events = pl.DataFrame(
        [
            {
                "event_timestamp": base,
                "signal": "NO_TRADE",
                "reason": "control",
            }
        ]
    )

    trades, summary = backtest_all_scenarios(price, events)
    signals = set(summary.filter(pl.col("group_type") == "signal").get_column("bucket"))

    assert Signal.OI_WALL_ONLY_BASELINE.value in signals
    assert Signal.BOLLINGER_BASELINE.value in signals
    assert not trades.is_empty()
