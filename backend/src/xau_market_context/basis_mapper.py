from __future__ import annotations

from datetime import datetime

from src.models.xau_market_context import (
    XauBasisSnapshot,
    XauBasisStatus,
    XauMappedLevel,
    XauMappedLevelStatus,
)


def build_basis_snapshot(
    *,
    xauusd_spot_price: float | None,
    gc_futures_price: float | None,
    spot_timestamp: datetime | None = None,
    futures_timestamp: datetime | None = None,
    max_alignment_seconds: float = 120.0,
) -> XauBasisSnapshot:
    if xauusd_spot_price is None or gc_futures_price is None:
        return XauBasisSnapshot(
            xauusd_spot_price=xauusd_spot_price,
            gc_futures_price=gc_futures_price,
            basis_points=None,
            status=XauBasisStatus.UNAVAILABLE,
            timestamp_alignment_seconds=None,
            warnings=[
                "Basis unavailable because XAUUSD spot and GC futures prices were "
                "not both supplied."
            ],
        )

    alignment_seconds: float | None = None
    status = XauBasisStatus.ALIGNED
    warnings: list[str] = []
    if spot_timestamp is not None and futures_timestamp is not None:
        alignment_seconds = abs((spot_timestamp - futures_timestamp).total_seconds())
        if alignment_seconds > max_alignment_seconds:
            status = XauBasisStatus.STALE
            warnings.append(
                "Basis timestamps exceed max alignment tolerance; mapped levels are stale."
            )

    return XauBasisSnapshot(
        xauusd_spot_price=xauusd_spot_price,
        gc_futures_price=gc_futures_price,
        basis_points=gc_futures_price - xauusd_spot_price,
        status=status,
        timestamp_alignment_seconds=alignment_seconds,
        warnings=warnings,
    )


def map_futures_level(
    *,
    futures_level: float,
    basis: XauBasisSnapshot,
    source: str = "cme_futures_level",
) -> XauMappedLevel:
    if basis.status != XauBasisStatus.ALIGNED or basis.basis_points is None:
        return XauMappedLevel(
            source_level=futures_level,
            mapped_level=None,
            basis_points=basis.basis_points,
            mapping_status=XauMappedLevelStatus.UNAVAILABLE,
            source=source,
        )
    return XauMappedLevel(
        source_level=futures_level,
        mapped_level=futures_level - basis.basis_points,
        basis_points=basis.basis_points,
        mapping_status=XauMappedLevelStatus.AVAILABLE,
        source=source,
    )


def map_futures_levels(
    levels: list[float],
    *,
    basis: XauBasisSnapshot,
    source: str = "cme_futures_level",
) -> list[XauMappedLevel]:
    return [map_futures_level(futures_level=level, basis=basis, source=source) for level in levels]
