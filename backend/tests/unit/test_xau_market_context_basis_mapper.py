from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from src.models.xau_market_context import XauBasisStatus
from src.xau_market_context.basis_mapper import build_basis_snapshot, map_futures_level


def test_basis_mapping_positive_basis_maps_futures_to_spot_equivalent() -> None:
    basis = build_basis_snapshot(xauusd_spot_price=4050, gc_futures_price=4070)
    mapped = map_futures_level(futures_level=4100, basis=basis)

    assert basis.basis_points == pytest.approx(20)
    assert basis.status == XauBasisStatus.ALIGNED
    assert mapped.mapped_level == pytest.approx(4080)


def test_basis_mapping_negative_basis() -> None:
    basis = build_basis_snapshot(xauusd_spot_price=4070, gc_futures_price=4050)
    mapped = map_futures_level(futures_level=4100, basis=basis)

    assert basis.basis_points == pytest.approx(-20)
    assert mapped.mapped_level == pytest.approx(4120)


def test_missing_basis_blocks_mapped_levels() -> None:
    basis = build_basis_snapshot(xauusd_spot_price=4050, gc_futures_price=None)
    mapped = map_futures_level(futures_level=4100, basis=basis)

    assert basis.status == XauBasisStatus.UNAVAILABLE
    assert basis.basis_points is None
    assert mapped.mapped_level is None
    assert mapped.mapping_status == "unavailable"


def test_timestamp_alignment_stale() -> None:
    tz = ZoneInfo("Asia/Bangkok")
    basis = build_basis_snapshot(
        xauusd_spot_price=4050,
        gc_futures_price=4070,
        spot_timestamp=datetime(2026, 6, 29, 14, 15, tzinfo=tz),
        futures_timestamp=datetime(2026, 6, 29, 14, 10, tzinfo=tz),
        max_alignment_seconds=120,
    )

    assert basis.status == XauBasisStatus.STALE
    assert basis.timestamp_alignment_seconds == timedelta(minutes=5).total_seconds()


def test_unavailable_values_are_not_coerced_to_zero() -> None:
    with pytest.raises(ValidationError):
        build_basis_snapshot(xauusd_spot_price=0, gc_futures_price=4070)

