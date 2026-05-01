from src.models.xau import (
    XauBasisSnapshot,
    XauBasisSource,
    XauReferencePrice,
    XauTimestampAlignmentStatus,
)


def compute_futures_spot_basis(futures_price: float, spot_price: float) -> float:
    """Return gold futures minus XAU spot/proxy reference."""

    if futures_price <= 0:
        raise ValueError("futures_price must be greater than 0")
    if spot_price <= 0:
        raise ValueError("spot_price must be greater than 0")
    return futures_price - spot_price


def map_strike_to_spot_equivalent(futures_strike: float, futures_spot_basis: float) -> float:
    """Map a futures/options strike into a spot-equivalent XAU level."""

    if futures_strike <= 0:
        raise ValueError("futures_strike must be greater than 0")
    return futures_strike - futures_spot_basis


def build_basis_snapshot(
    *,
    spot_reference: XauReferencePrice | None = None,
    futures_reference: XauReferencePrice | None = None,
    manual_basis: float | None = None,
) -> XauBasisSnapshot:
    """Create an auditable basis snapshot for spot-equivalent wall mapping."""

    notes: list[str] = []
    if manual_basis is not None:
        notes.append(
            "Manual basis supplied by researcher; verify against futures and spot context."
        )
        return XauBasisSnapshot(
            basis=manual_basis,
            basis_source=XauBasisSource.MANUAL,
            futures_reference=futures_reference,
            spot_reference=spot_reference,
            timestamp_alignment_status=_timestamp_alignment(spot_reference, futures_reference),
            mapping_available=True,
            notes=notes,
        )

    if spot_reference is None or futures_reference is None:
        return XauBasisSnapshot(
            basis=None,
            basis_source=XauBasisSource.UNAVAILABLE,
            futures_reference=futures_reference,
            spot_reference=spot_reference,
            timestamp_alignment_status=XauTimestampAlignmentStatus.UNKNOWN,
            mapping_available=False,
            notes=[
                "Spot-equivalent mapping requires a manual basis or both futures "
                "and spot references."
            ],
        )

    basis = compute_futures_spot_basis(futures_reference.price, spot_reference.price)
    return XauBasisSnapshot(
        basis=basis,
        basis_source=XauBasisSource.COMPUTED,
        futures_reference=futures_reference,
        spot_reference=spot_reference,
        timestamp_alignment_status=_timestamp_alignment(spot_reference, futures_reference),
        mapping_available=True,
        notes=notes,
    )


def _timestamp_alignment(
    spot_reference: XauReferencePrice | None,
    futures_reference: XauReferencePrice | None,
) -> XauTimestampAlignmentStatus:
    if spot_reference is None or futures_reference is None:
        return XauTimestampAlignmentStatus.UNKNOWN
    if spot_reference.timestamp is None or futures_reference.timestamp is None:
        return XauTimestampAlignmentStatus.UNKNOWN
    if spot_reference.timestamp == futures_reference.timestamp:
        return XauTimestampAlignmentStatus.ALIGNED
    return XauTimestampAlignmentStatus.MISMATCHED
