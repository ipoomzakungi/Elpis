from datetime import UTC, date, datetime

import pytest

from src.models.xau import (
    XauBasisSnapshot,
    XauBasisSource,
    XauFreshnessFactorStatus,
    XauOptionType,
    XauTimestampAlignmentStatus,
    XauWallType,
)
from src.xau.volatility import unavailable_expected_range
from src.xau.walls import (
    build_oi_walls,
    classify_wall_type,
    compute_expiry_weight,
    compute_freshness_factor,
)
from tests.helpers.test_xau_data import sample_xau_options_frame


def _rows():
    report = sample_xau_options_frame(include_optional=True)
    from src.xau.imports import validate_options_oi_frame

    return validate_options_oi_frame(report, file_path="memory.csv").rows


def _basis_snapshot() -> XauBasisSnapshot:
    return XauBasisSnapshot(
        basis=7.0,
        basis_source=XauBasisSource.COMPUTED,
        timestamp_alignment_status=XauTimestampAlignmentStatus.UNKNOWN,
        mapping_available=True,
    )


def test_build_oi_walls_computes_oi_share_expiry_weight_freshness_and_score():
    walls = build_oi_walls(_rows(), basis_snapshot=_basis_snapshot())

    assert len(walls) == 2
    call_wall = next(wall for wall in walls if wall.option_type == XauWallType.CALL)
    assert call_wall.total_expiry_open_interest == 20800.0
    assert call_wall.oi_share == pytest.approx(12500.0 / 20800.0)
    assert call_wall.expiry_weight == pytest.approx(compute_expiry_weight(7))
    assert call_wall.freshness_factor == 1.1
    assert call_wall.freshness_status == XauFreshnessFactorStatus.CONFIRMED
    assert call_wall.wall_score == pytest.approx(
        call_wall.oi_share * call_wall.expiry_weight * call_wall.freshness_factor
    )
    assert call_wall.spot_equivalent_level == 2393.0


def test_expiry_weight_is_bounded_and_higher_for_near_expiry():
    near = compute_expiry_weight(3)
    far = compute_expiry_weight(120)

    assert 0.25 <= far < near <= 1.0


def test_freshness_factor_uses_oi_change_and_volume_evidence():
    confirmed = compute_freshness_factor(oi_change=100.0, volume=10.0)
    stale = compute_freshness_factor(oi_change=-100.0, volume=0.0)
    unavailable = compute_freshness_factor(oi_change=None, volume=None)

    assert confirmed.factor == 1.1
    assert confirmed.status == XauFreshnessFactorStatus.CONFIRMED
    assert stale.factor == 0.9
    assert stale.status == XauFreshnessFactorStatus.STALE
    assert unavailable.factor == 1.0
    assert unavailable.status == XauFreshnessFactorStatus.UNAVAILABLE


def test_classify_wall_type_handles_call_put_mixed_and_unknown():
    assert classify_wall_type([XauOptionType.CALL]) == XauWallType.CALL
    assert classify_wall_type([XauOptionType.PUT]) == XauWallType.PUT
    assert classify_wall_type([XauOptionType.CALL, XauOptionType.PUT]) == XauWallType.MIXED
    assert classify_wall_type([XauOptionType.UNKNOWN]) == XauWallType.UNKNOWN


def test_build_oi_walls_adds_limitations_when_optional_inputs_are_missing():
    from src.models.xau import XauOptionsOiRow

    row = XauOptionsOiRow(
        source_row_id="row_1",
        timestamp=datetime(2026, 4, 30, 16, 0, tzinfo=UTC),
        expiry=date(2026, 5, 7),
        days_to_expiry=7,
        strike=2400.0,
        option_type=XauOptionType.UNKNOWN,
        open_interest=100.0,
    )

    walls = build_oi_walls(
        [row],
        basis_snapshot=None,
        expected_range=unavailable_expected_range("IV unavailable."),
    )

    wall = walls[0]
    assert wall.option_type == XauWallType.UNKNOWN
    assert wall.spot_equivalent_level is None
    assert wall.freshness_factor == 1.0
    assert any("basis" in item.lower() for item in wall.limitations)
    assert any("oi_change or volume" in item for item in wall.limitations)
    assert any("IV" in item for item in wall.limitations)
    assert wall.notes
    assert wall.wall_score == pytest.approx(wall.oi_share * wall.expiry_weight)
