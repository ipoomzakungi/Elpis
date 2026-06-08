from __future__ import annotations

from datetime import datetime

from src.models.xau_price_plan_tracker import (
    XauDukasPriceBar,
    XauReferenceAlignmentStatus,
)
from src.xau_price_plan_tracker.reference_price import extract_reference_price_at


def test_reference_price_prefers_exact_close() -> None:
    target = datetime.fromisoformat("2026-06-08T10:10:00")
    result = extract_reference_price_at([_bar(target, 4471)], target)

    assert result.alignment_status == XauReferenceAlignmentStatus.EXACT
    assert result.reference_price == 4471


def test_reference_price_uses_previous_bar_within_tolerance() -> None:
    target = datetime.fromisoformat("2026-06-08T10:10:00")
    previous = datetime.fromisoformat("2026-06-08T10:07:00")
    result = extract_reference_price_at([_bar(previous, 4469)], target)

    assert result.alignment_status == XauReferenceAlignmentStatus.WITHIN_TOLERANCE
    assert result.reference_price == 4469


def test_reference_price_marks_stale_when_too_far() -> None:
    target = datetime.fromisoformat("2026-06-08T10:10:00")
    previous = datetime.fromisoformat("2026-06-08T09:50:00")
    result = extract_reference_price_at([_bar(previous, 4469)], target)

    assert result.alignment_status == XauReferenceAlignmentStatus.STALE
    assert result.reference_price is None


def _bar(timestamp: datetime, close: float) -> XauDukasPriceBar:
    return XauDukasPriceBar(
        timestamp=timestamp,
        open=close,
        high=close + 1,
        low=close - 1,
        close=close,
    )
