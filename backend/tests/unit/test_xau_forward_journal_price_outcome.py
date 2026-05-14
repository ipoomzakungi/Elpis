from datetime import UTC, datetime, timedelta

from src.models.xau_forward_journal import (
    XauForwardJournalEntry,
    XauForwardJournalEntryStatus,
    XauForwardJournalSourceType,
    XauForwardOhlcCandle,
    XauForwardOutcomeLabel,
    XauForwardOutcomeStatus,
    XauForwardOutcomeWindow,
    XauForwardPriceCoverageStatus,
    XauForwardPriceDirection,
    XauForwardPriceSource,
    XauForwardPriceSourceLabel,
    XauForwardSnapshotContext,
    XauForwardSourceReportRef,
)
from src.xau_forward_journal.price_outcome import (
    build_price_coverage_summary,
    build_price_outcome_observations,
    calculate_outcome_window_ranges,
    price_metrics_for_window,
)

SNAPSHOT_TIME = datetime(2026, 5, 14, 3, 8, 4, tzinfo=UTC)


def _entry(*, snapshot_price: float | None = 4707.2) -> XauForwardJournalEntry:
    return XauForwardJournalEntry(
        journal_id="journal_price_fixture",
        snapshot_key="20260514_daily_snapshot_g2rk6_price",
        status=XauForwardJournalEntryStatus.PARTIAL,
        snapshot=XauForwardSnapshotContext(
            snapshot_time=SNAPSHOT_TIME,
            capture_window="daily_snapshot",
            product="Gold (OG|GC)",
            expiration_code="G2RK6",
            futures_price_at_snapshot=snapshot_price,
        ),
        source_reports=[
            XauForwardSourceReportRef(
                source_type=XauForwardJournalSourceType.XAU_QUIKSTRIKE_FUSION,
                report_id="fusion_report",
                status="completed",
                product="Gold (OG|GC)",
                row_count=3,
            )
        ],
    )


def _source(label: XauForwardPriceSourceLabel = XauForwardPriceSourceLabel.LOCAL_PARQUET):
    return XauForwardPriceSource(
        source_label=label,
        source_symbol="XAUUSD local fixture",
        source_path="data/raw/xau_fixture.parquet",
        format="parquet",
        row_count=1,
        limitations=["Local Parquet fixture."],
    )


def _candles(start: datetime, count: int, *, step_minutes: int = 1) -> list[XauForwardOhlcCandle]:
    candles: list[XauForwardOhlcCandle] = []
    for index in range(count):
        open_price = 4707.0 + index * 0.1
        candles.append(
            XauForwardOhlcCandle(
                timestamp=start + timedelta(minutes=index * step_minutes),
                open=open_price,
                high=open_price + 1.0,
                low=open_price - 1.0,
                close=open_price + 0.5,
            )
        )
    return candles


def test_calculate_outcome_window_ranges_from_snapshot_time():
    ranges = calculate_outcome_window_ranges(_entry())
    by_window = {item.window: item for item in ranges}

    assert [item.window for item in ranges] == [
        XauForwardOutcomeWindow.THIRTY_MINUTES,
        XauForwardOutcomeWindow.ONE_HOUR,
        XauForwardOutcomeWindow.FOUR_HOURS,
        XauForwardOutcomeWindow.SESSION_CLOSE,
        XauForwardOutcomeWindow.NEXT_DAY,
    ]
    assert by_window[XauForwardOutcomeWindow.THIRTY_MINUTES].required_end == (
        SNAPSHOT_TIME + timedelta(minutes=30)
    )
    assert by_window[XauForwardOutcomeWindow.ONE_HOUR].required_end == (
        SNAPSHOT_TIME + timedelta(hours=1)
    )
    assert by_window[XauForwardOutcomeWindow.FOUR_HOURS].required_end == (
        SNAPSHOT_TIME + timedelta(hours=4)
    )
    assert by_window[XauForwardOutcomeWindow.SESSION_CLOSE].required_end == datetime(
        2026, 5, 14, 21, 0, tzinfo=UTC
    )
    assert by_window[XauForwardOutcomeWindow.NEXT_DAY].required_end == (
        SNAPSHOT_TIME + timedelta(days=1)
    )


def test_complete_window_metrics_and_outcome_observation_are_computed():
    entry = _entry()
    candles = _candles(SNAPSHOT_TIME, 31)
    coverage = build_price_coverage_summary(entry, candles, _source())
    outcomes = build_price_outcome_observations(
        entry,
        candles,
        coverage,
        price_update_id="price_update_fixture",
    )

    thirty_min = outcomes[0]
    assert coverage.windows[0].status == XauForwardPriceCoverageStatus.COMPLETE
    assert coverage.windows[0].candle_count == 31
    assert thirty_min.status == XauForwardOutcomeStatus.COMPLETED
    assert thirty_min.label == XauForwardOutcomeLabel.STAYED_INSIDE_RANGE
    assert thirty_min.observation_start == SNAPSHOT_TIME
    assert thirty_min.observation_end == SNAPSHOT_TIME + timedelta(minutes=30)
    assert thirty_min.high == 4711.0
    assert thirty_min.low == 4706.0
    assert thirty_min.close == 4710.5
    assert thirty_min.range == 5.0
    assert thirty_min.direction == XauForwardPriceDirection.UP_FROM_SNAPSHOT
    assert thirty_min.price_source_label == XauForwardPriceSourceLabel.LOCAL_PARQUET


def test_direction_calculation_handles_up_down_flat_and_unavailable():
    window = build_price_coverage_summary(
        _entry(),
        _candles(SNAPSHOT_TIME, 31),
        _source(),
    ).windows[0]
    up = price_metrics_for_window(
        window,
        _candles(SNAPSHOT_TIME, 31),
        snapshot_price=4707.2,
        price_update_id="price_update_up",
    )
    down = price_metrics_for_window(
        window,
        [
            XauForwardOhlcCandle(
                timestamp=SNAPSHOT_TIME,
                open=4707.2,
                high=4708.0,
                low=4700.0,
                close=4701.0,
            ),
            XauForwardOhlcCandle(
                timestamp=SNAPSHOT_TIME + timedelta(minutes=30),
                open=4701.0,
                high=4702.0,
                low=4700.0,
                close=4701.0,
            ),
        ],
        snapshot_price=4707.2,
        price_update_id="price_update_down",
    )
    flat = price_metrics_for_window(
        window,
        [
            XauForwardOhlcCandle(
                timestamp=SNAPSHOT_TIME,
                open=4707.2,
                high=4708.0,
                low=4707.0,
                close=4707.2,
            ),
            XauForwardOhlcCandle(
                timestamp=SNAPSHOT_TIME + timedelta(minutes=30),
                open=4707.2,
                high=4708.0,
                low=4707.0,
                close=4707.2,
            ),
        ],
        snapshot_price=4707.2,
        price_update_id="price_update_flat",
    )
    unavailable = price_metrics_for_window(
        window,
        _candles(SNAPSHOT_TIME, 31),
        snapshot_price=None,
        price_update_id="price_update_unavailable",
    )

    assert up.direction == XauForwardPriceDirection.UP_FROM_SNAPSHOT
    assert down.direction == XauForwardPriceDirection.DOWN_FROM_SNAPSHOT
    assert flat.direction == XauForwardPriceDirection.FLAT_FROM_SNAPSHOT
    assert unavailable.direction == XauForwardPriceDirection.UNAVAILABLE


def test_partial_and_missing_coverage_map_to_inconclusive_and_pending_outcomes():
    entry = _entry()
    candles = _candles(SNAPSHOT_TIME + timedelta(minutes=45), 16)
    coverage = build_price_coverage_summary(entry, candles, _source())
    outcomes = build_price_outcome_observations(
        entry,
        candles,
        coverage,
        price_update_id="price_update_partial",
    )

    assert coverage.windows[0].status == XauForwardPriceCoverageStatus.MISSING
    assert outcomes[0].status == XauForwardOutcomeStatus.PENDING
    assert outcomes[0].label == XauForwardOutcomeLabel.PENDING
    assert coverage.windows[1].status == XauForwardPriceCoverageStatus.PARTIAL
    assert outcomes[1].status == XauForwardOutcomeStatus.INCONCLUSIVE
    assert outcomes[1].label == XauForwardOutcomeLabel.INCONCLUSIVE
    assert coverage.missing_candle_checklist[0].window == XauForwardOutcomeWindow.THIRTY_MINUTES


def test_gap_detection_prevents_complete_coverage():
    entry = _entry()
    candles = [
        *_candles(SNAPSHOT_TIME, 2),
        *_candles(SNAPSHOT_TIME + timedelta(minutes=30), 1),
    ]
    coverage = build_price_coverage_summary(entry, candles, _source())

    assert coverage.windows[0].status == XauForwardPriceCoverageStatus.PARTIAL
    assert coverage.windows[0].gap_count == 1
    assert coverage.windows[0].partial_reason
