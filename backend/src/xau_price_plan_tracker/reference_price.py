from __future__ import annotations

from datetime import datetime, timedelta

from src.models.xau_price_plan_tracker import (
    XauDukasPriceBar,
    XauReferenceAlignmentStatus,
    XauReferencePriceResult,
)


def extract_reference_price_at(
    bars: list[XauDukasPriceBar],
    timestamp: datetime,
    *,
    tolerance_minutes: int = 5,
) -> XauReferencePriceResult:
    if not bars:
        return XauReferencePriceResult(
            requested_timestamp=timestamp,
            alignment_status=XauReferenceAlignmentStatus.UNAVAILABLE,
            limitations=["No XAU price bars were available."],
        )
    sorted_bars = sorted(bars, key=lambda item: item.timestamp)
    for bar in sorted_bars:
        if bar.timestamp == timestamp:
            return XauReferencePriceResult(
                requested_timestamp=timestamp,
                reference_price=bar.close,
                matched_timestamp=bar.timestamp,
                alignment_status=XauReferenceAlignmentStatus.EXACT,
            )
    candidates = [bar for bar in sorted_bars if bar.timestamp <= timestamp]
    if not candidates:
        return XauReferencePriceResult(
            requested_timestamp=timestamp,
            alignment_status=XauReferenceAlignmentStatus.UNAVAILABLE,
            limitations=["No bar exists at or before the requested reference timestamp."],
        )
    latest = candidates[-1]
    if timestamp - latest.timestamp <= timedelta(minutes=tolerance_minutes):
        return XauReferencePriceResult(
            requested_timestamp=timestamp,
            reference_price=latest.close,
            matched_timestamp=latest.timestamp,
            alignment_status=XauReferenceAlignmentStatus.WITHIN_TOLERANCE,
            limitations=["Reference used latest prior close within tolerance."],
        )
    return XauReferencePriceResult(
        requested_timestamp=timestamp,
        alignment_status=XauReferenceAlignmentStatus.STALE,
        limitations=["Latest prior bar is outside the allowed tolerance."],
    )


__all__ = ["extract_reference_price_at"]
