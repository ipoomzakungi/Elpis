from datetime import UTC, datetime

from src.models.xau import (
    XauBasisSource,
    XauReferencePrice,
    XauReferenceType,
    XauTimestampAlignmentStatus,
)
from src.xau.basis import (
    build_basis_snapshot,
    compute_futures_spot_basis,
    map_strike_to_spot_equivalent,
)


def reference_price(
    symbol: str,
    price: float,
    reference_type: XauReferenceType,
    timestamp: datetime | None = None,
) -> XauReferencePrice:
    return XauReferencePrice(
        source="manual",
        symbol=symbol,
        price=price,
        timestamp=timestamp,
        reference_type=reference_type,
    )


def test_compute_basis_and_spot_equivalent_level():
    basis = compute_futures_spot_basis(futures_price=2410.0, spot_price=2403.0)

    assert basis == 7.0
    assert map_strike_to_spot_equivalent(2400.0, basis) == 2393.0


def test_build_computed_basis_snapshot_with_aligned_references():
    timestamp = datetime(2026, 4, 30, 16, 0, tzinfo=UTC)
    spot = reference_price("XAUUSD", 2403.0, XauReferenceType.SPOT, timestamp)
    futures = reference_price("GC", 2410.0, XauReferenceType.FUTURES, timestamp)

    snapshot = build_basis_snapshot(spot_reference=spot, futures_reference=futures)

    assert snapshot.basis == 7.0
    assert snapshot.basis_source == XauBasisSource.COMPUTED
    assert snapshot.mapping_available is True
    assert snapshot.timestamp_alignment_status == XauTimestampAlignmentStatus.ALIGNED


def test_build_manual_basis_snapshot_without_requiring_prices():
    snapshot = build_basis_snapshot(manual_basis=-2.5)

    assert snapshot.basis == -2.5
    assert snapshot.basis_source == XauBasisSource.MANUAL
    assert snapshot.mapping_available is True
    assert "Manual basis" in snapshot.notes[0]


def test_build_unavailable_basis_snapshot_when_references_missing():
    snapshot = build_basis_snapshot()

    assert snapshot.basis is None
    assert snapshot.basis_source == XauBasisSource.UNAVAILABLE
    assert snapshot.mapping_available is False
    assert "requires a manual basis" in snapshot.notes[0]
