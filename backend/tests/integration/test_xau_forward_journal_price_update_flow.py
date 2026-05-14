from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl

from src.models.xau_forward_journal import (
    XauForwardJournalCreateRequest,
    XauForwardOutcomeStatus,
    XauForwardOutcomeWindow,
    XauForwardPriceCoverageStatus,
    XauForwardPriceDataUpdateRequest,
    XauForwardPriceSourceLabel,
)
from src.xau_forward_journal.orchestration import (
    create_xau_forward_journal_entry,
    get_xau_forward_journal_price_coverage,
    update_xau_forward_journal_outcomes_from_price_data,
)
from src.xau_forward_journal.report_store import XauForwardJournalReportStore
from tests.helpers.test_xau_forward_journal_data import (
    synthetic_forward_journal_create_payload,
    write_synthetic_source_reports,
)

SNAPSHOT_TIME = datetime(2026, 5, 14, 3, 8, 4, tzinfo=UTC)


def _create_request(**updates) -> XauForwardJournalCreateRequest:
    payload = synthetic_forward_journal_create_payload()
    payload.update(updates)
    return XauForwardJournalCreateRequest.model_validate(payload)


def _price_request(path: Path) -> XauForwardPriceDataUpdateRequest:
    return XauForwardPriceDataUpdateRequest(
        source_label=XauForwardPriceSourceLabel.LOCAL_PARQUET,
        source_symbol="XAUUSD local fixture",
        ohlc_path=str(path),
        update_note="Attach synthetic OHLC validation outcomes.",
        research_only_acknowledged=True,
    )


def _write_candles(path: Path, start: datetime, count: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(
        [
            {
                "timestamp": (start + timedelta(minutes=index)).isoformat(),
                "open": 4707.0 + index * 0.1,
                "high": 4708.0 + index * 0.1,
                "low": 4706.0 + index * 0.1,
                "close": 4707.5 + index * 0.1,
            }
            for index in range(count)
        ]
    ).write_parquet(path)
    return path


def test_price_update_flow_updates_synthetic_journal_from_synthetic_candles(tmp_path):
    reports_dir = tmp_path / "data" / "reports"
    write_synthetic_source_reports(reports_dir)
    store = XauForwardJournalReportStore(reports_dir=reports_dir)
    entry = create_xau_forward_journal_entry(_create_request(), report_store=store)
    original_snapshot = entry.snapshot.model_dump(mode="json")
    ohlc_path = _write_candles(tmp_path / "xau_complete.parquet", SNAPSHOT_TIME, 31)

    response = update_xau_forward_journal_outcomes_from_price_data(
        entry.journal_id,
        _price_request(ohlc_path),
        report_store=store,
    )
    loaded = store.read_entry(entry.journal_id)

    assert response.outcomes[0].status == XauForwardOutcomeStatus.COMPLETED
    assert response.outcomes[0].high == 4711.0
    assert response.outcomes[0].low == 4706.0
    assert response.outcomes[0].range == 5.0
    assert response.outcomes[0].price_source_label == XauForwardPriceSourceLabel.LOCAL_PARQUET
    assert response.outcomes[1].status == XauForwardOutcomeStatus.INCONCLUSIVE
    assert loaded.snapshot.model_dump(mode="json") == original_snapshot
    assert response.artifacts
    assert all(
        "data/reports/xau_forward_journal/" in artifact.path
        for artifact in response.artifacts
    )


def test_price_update_flow_keeps_missing_windows_pending(tmp_path):
    reports_dir = tmp_path / "data" / "reports"
    write_synthetic_source_reports(reports_dir)
    store = XauForwardJournalReportStore(reports_dir=reports_dir)
    entry = create_xau_forward_journal_entry(
        _create_request(capture_window="missing_price_snapshot"),
        report_store=store,
    )
    ohlc_path = _write_candles(
        tmp_path / "xau_late.parquet",
        SNAPSHOT_TIME + timedelta(minutes=45),
        16,
    )

    response = update_xau_forward_journal_outcomes_from_price_data(
        entry.journal_id,
        _price_request(ohlc_path),
        report_store=store,
    )
    coverage = get_xau_forward_journal_price_coverage(
        entry.journal_id,
        _price_request(ohlc_path),
        report_store=store,
    )

    assert response.coverage.windows[0].status == XauForwardPriceCoverageStatus.MISSING
    assert response.outcomes[0].status == XauForwardOutcomeStatus.PENDING
    assert response.outcomes[0].window == XauForwardOutcomeWindow.THIRTY_MINUTES
    assert XauForwardOutcomeWindow.THIRTY_MINUTES in coverage.coverage.missing_windows
