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
