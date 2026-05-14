from __future__ import annotations

from datetime import UTC, datetime, time, timedelta

from src.models.xau_forward_journal import (
    XauForwardJournalEntry,
    XauForwardJournalNote,
    XauForwardMissingCandleItem,
    XauForwardOhlcCandle,
    XauForwardOutcomeLabel,
    XauForwardOutcomeObservation,
    XauForwardOutcomeStatus,
    XauForwardOutcomeWindow,
    XauForwardOutcomeWindowRange,
    XauForwardPriceCoverageStatus,
    XauForwardPriceCoverageSummary,
    XauForwardPriceCoverageWindow,
    XauForwardPriceDirection,
    XauForwardPriceOutcomeMetrics,
    XauForwardPriceSource,
)
from src.xau_forward_journal.outcome import OUTCOME_RESEARCH_LIMITATION

OUTCOME_PRICE_UPDATE_LIMITATION = (
    "Outcome price updates are local-only forward research annotations, not trading signals."
)
SESSION_CLOSE_UTC = time(hour=21, minute=0, tzinfo=UTC)


def calculate_outcome_window_ranges(
    entry: XauForwardJournalEntry,
) -> list[XauForwardOutcomeWindowRange]:
    snapshot_time = _utc(entry.snapshot.snapshot_time)
    session_close = datetime.combine(snapshot_time.date(), SESSION_CLOSE_UTC).astimezone(UTC)
    if session_close <= snapshot_time:
        session_close += timedelta(days=1)
    return [
        XauForwardOutcomeWindowRange(
            window=XauForwardOutcomeWindow.THIRTY_MINUTES,
            required_start=snapshot_time,
            required_end=snapshot_time + timedelta(minutes=30),
            boundary_basis="snapshot_plus_30m",
        ),
        XauForwardOutcomeWindowRange(
            window=XauForwardOutcomeWindow.ONE_HOUR,
            required_start=snapshot_time,
            required_end=snapshot_time + timedelta(hours=1),
            boundary_basis="snapshot_plus_1h",
        ),
        XauForwardOutcomeWindowRange(
            window=XauForwardOutcomeWindow.FOUR_HOURS,
            required_start=snapshot_time,
            required_end=snapshot_time + timedelta(hours=4),
            boundary_basis="snapshot_plus_4h",
        ),
        XauForwardOutcomeWindowRange(
            window=XauForwardOutcomeWindow.SESSION_CLOSE,
            required_start=snapshot_time,
            required_end=session_close,
            boundary_basis="xau_research_session_close_2100_utc",
        ),
        XauForwardOutcomeWindowRange(
            window=XauForwardOutcomeWindow.NEXT_DAY,
            required_start=snapshot_time,
            required_end=snapshot_time + timedelta(days=1),
            boundary_basis="snapshot_plus_24h",
        ),
    ]


def build_price_coverage_summary(
    entry: XauForwardJournalEntry,
    candles: list[XauForwardOhlcCandle],
    source: XauForwardPriceSource,
) -> XauForwardPriceCoverageSummary:
    windows = [
        evaluate_window_coverage(window_range, candles, source)
        for window_range in calculate_outcome_window_ranges(entry)
    ]
    complete = [
        window.window
        for window in windows
        if window.status == XauForwardPriceCoverageStatus.COMPLETE
    ]
    partial = [
        window.window
        for window in windows
        if window.status == XauForwardPriceCoverageStatus.PARTIAL
    ]
    missing = [
        window.window
        for window in windows
        if window.status == XauForwardPriceCoverageStatus.MISSING
    ]
    checklist = [
        missing_candle_item(window)
        for window in windows
        if window.status
        in {
            XauForwardPriceCoverageStatus.PARTIAL,
            XauForwardPriceCoverageStatus.MISSING,
            XauForwardPriceCoverageStatus.INVALID,
            XauForwardPriceCoverageStatus.BLOCKED,
        }
    ]
    return XauForwardPriceCoverageSummary(
        journal_id=entry.journal_id,
        snapshot_time=entry.snapshot.snapshot_time,
        source=source,
        windows=windows,
        complete_windows=complete,
        partial_windows=partial,
        missing_windows=missing,
        missing_candle_checklist=checklist,
        proxy_limitations=source.limitations,
        warnings=source.warnings,
        limitations=[
            "Coverage status is a data availability check, not a trading signal.",
            OUTCOME_PRICE_UPDATE_LIMITATION,
        ],
    )


def evaluate_window_coverage(
    window_range: XauForwardOutcomeWindowRange,
    candles: list[XauForwardOhlcCandle],
    source: XauForwardPriceSource,
) -> XauForwardPriceCoverageWindow:
    overlap = [
        candle
        for candle in candles
        if window_range.required_start <= candle.timestamp <= window_range.required_end
    ]
    if not overlap:
        missing_reason = (
            f"No usable candles overlap the required {window_range.window.value} window."
        )
        return XauForwardPriceCoverageWindow(
            window=window_range.window,
            status=XauForwardPriceCoverageStatus.MISSING,
            required_start=window_range.required_start,
            required_end=window_range.required_end,
            missing_reason=missing_reason,
            source_label=source.source_label,
            source_symbol=source.source_symbol,
            limitations=window_range.limitations,
        )

    observed_start = overlap[0].timestamp
    observed_end = overlap[-1].timestamp
    gap_count = _gap_count(overlap)
    complete = (
        observed_start <= window_range.required_start
        and observed_end >= window_range.required_end
        and len(overlap) >= 2
        and gap_count == 0
        and not window_range.limitations
    )
    if complete:
        status = XauForwardPriceCoverageStatus.COMPLETE
        partial_reason = None
    else:
        status = XauForwardPriceCoverageStatus.PARTIAL
        partial_reason = "Candles overlap the window but do not fully cover the required interval."
        if gap_count:
            partial_reason = "Candles include timestamp gaps inside the required interval."
        if window_range.limitations:
            partial_reason = "Window boundary limitations prevent completed coverage."
    return XauForwardPriceCoverageWindow(
        window=window_range.window,
        status=status,
        required_start=window_range.required_start,
        required_end=window_range.required_end,
        observed_start=observed_start,
        observed_end=observed_end,
        candle_count=len(overlap),
        gap_count=gap_count,
        partial_reason=partial_reason,
        source_label=source.source_label,
        source_symbol=source.source_symbol,
        limitations=window_range.limitations,
    )


def build_price_outcome_observations(
    entry: XauForwardJournalEntry,
    candles: list[XauForwardOhlcCandle],
    coverage: XauForwardPriceCoverageSummary,
    *,
    price_update_id: str,
) -> list[XauForwardOutcomeObservation]:
    observations: list[XauForwardOutcomeObservation] = []
    snapshot_price = _snapshot_price(entry)
    for window in coverage.windows:
        overlap = [
            candle
            for candle in candles
            if window.required_start <= candle.timestamp <= window.required_end
        ]
        metrics = price_metrics_for_window(
            window,
            overlap,
            snapshot_price=snapshot_price,
            price_update_id=price_update_id,
        )
        observations.append(
            XauForwardOutcomeObservation(
                window=metrics.window,
                status=metrics.status,
                label=metrics.label,
                observation_start=metrics.observation_start,
                observation_end=metrics.observation_end,
                open=metrics.open,
                high=metrics.high,
                low=metrics.low,
                close=metrics.close,
                range=metrics.range,
                direction=metrics.direction,
                price_source_label=metrics.source_label,
                price_source_symbol=metrics.source_symbol,
                coverage_status=window.status,
                coverage_reason=window.partial_reason or window.missing_reason,
                price_update_id=price_update_id,
                notes=metrics.notes,
                limitations=metrics.limitations,
            )
        )
    return observations


def price_metrics_for_window(
    window: XauForwardPriceCoverageWindow,
    candles: list[XauForwardOhlcCandle],
    *,
    snapshot_price: float | None,
    price_update_id: str,
) -> XauForwardPriceOutcomeMetrics:
    if window.status == XauForwardPriceCoverageStatus.MISSING:
        return XauForwardPriceOutcomeMetrics(
            window=window.window,
            status=XauForwardOutcomeStatus.PENDING,
            label=XauForwardOutcomeLabel.PENDING,
            direction=XauForwardPriceDirection.UNAVAILABLE,
            source_label=window.source_label,
            source_symbol=window.source_symbol,
            notes=[
                XauForwardJournalNote(
                    text="No usable price candles were available for this outcome window.",
                    source="price_update",
                )
            ],
            limitations=[OUTCOME_RESEARCH_LIMITATION, OUTCOME_PRICE_UPDATE_LIMITATION],
        )
    if window.status != XauForwardPriceCoverageStatus.COMPLETE:
        return XauForwardPriceOutcomeMetrics(
            window=window.window,
            status=XauForwardOutcomeStatus.INCONCLUSIVE,
            label=XauForwardOutcomeLabel.INCONCLUSIVE,
            observation_start=window.observed_start,
            observation_end=window.observed_end,
            direction=XauForwardPriceDirection.UNAVAILABLE,
            source_label=window.source_label,
            source_symbol=window.source_symbol,
            notes=[
                XauForwardJournalNote(
                    text=window.partial_reason
                    or "Price candles were insufficient for a completed outcome.",
                    source="price_update",
                )
            ],
            limitations=[OUTCOME_RESEARCH_LIMITATION, OUTCOME_PRICE_UPDATE_LIMITATION],
        )

    high = max(candle.high for candle in candles)
    low = min(candle.low for candle in candles)
    first = candles[0]
    last = candles[-1]
    direction = _direction(last.close, snapshot_price)
    limitations = [OUTCOME_RESEARCH_LIMITATION, OUTCOME_PRICE_UPDATE_LIMITATION]
    if snapshot_price is None:
        limitations.append(
            "Snapshot price is unavailable; direction from snapshot was not computed."
        )
    return XauForwardPriceOutcomeMetrics(
        window=window.window,
        status=XauForwardOutcomeStatus.COMPLETED,
        label=XauForwardOutcomeLabel.STAYED_INSIDE_RANGE,
        observation_start=window.observed_start,
        observation_end=window.observed_end,
        open=first.open,
        high=high,
        low=low,
        close=last.close,
        range=high - low,
        snapshot_price=snapshot_price,
        direction=direction,
        source_label=window.source_label,
        source_symbol=window.source_symbol,
        notes=[
            XauForwardJournalNote(
                text="Outcome metrics were computed from local research OHLC candles.",
                source="price_update",
            )
        ],
        limitations=limitations,
    )


def missing_candle_item(window: XauForwardPriceCoverageWindow) -> XauForwardMissingCandleItem:
    message = (
        window.missing_reason
        or window.partial_reason
        or "Window does not have sufficient candle coverage."
    )
    return XauForwardMissingCandleItem(
        window=window.window,
        required_start=window.required_start,
        required_end=window.required_end,
        status=window.status,
        message=message,
        action=f"Import or generate candles that cover the {window.window.value} window.",
    )


def _snapshot_price(entry: XauForwardJournalEntry) -> float | None:
    return (
        entry.snapshot.spot_price_at_snapshot
        or entry.snapshot.futures_price_at_snapshot
        or entry.snapshot.session_open_price
    )


def _direction(close: float, snapshot_price: float | None) -> XauForwardPriceDirection:
    if snapshot_price is None:
        return XauForwardPriceDirection.UNAVAILABLE
    if close > snapshot_price:
        return XauForwardPriceDirection.UP_FROM_SNAPSHOT
    if close < snapshot_price:
        return XauForwardPriceDirection.DOWN_FROM_SNAPSHOT
    return XauForwardPriceDirection.FLAT_FROM_SNAPSHOT


def _gap_count(candles: list[XauForwardOhlcCandle]) -> int:
    if len(candles) < 3:
        return 0
    deltas = [
        (right.timestamp - left.timestamp).total_seconds()
        for left, right in zip(candles, candles[1:])
    ]
    positive_deltas = [delta for delta in deltas if delta > 0]
    if not positive_deltas:
        return 0
    expected = min(positive_deltas)
    return sum(1 for delta in positive_deltas if delta > expected * 1.5)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
