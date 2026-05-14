from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from src.models.xau_forward_journal import (
    XauForwardJournalCreateRequest,
    XauForwardJournalEntry,
    XauForwardOutcomeLabel,
    XauForwardOutcomeResponse,
    XauForwardOutcomeStatus,
    XauForwardOutcomeUpdateRequest,
    XauForwardPriceCoverageRequest,
    XauForwardPriceCoverageResponse,
    XauForwardPriceDataUpdateRequest,
    XauForwardPriceOutcomeUpdateReport,
    XauForwardPriceOutcomeUpdateResponse,
)
from src.xau_forward_journal.entry_builder import (
    XauForwardJournalBuildError,
    build_journal_entry,
)
from src.xau_forward_journal.outcome import apply_outcome_update
from src.xau_forward_journal.price_data import load_price_candles
from src.xau_forward_journal.price_outcome import (
    OUTCOME_PRICE_UPDATE_LIMITATION,
    build_price_coverage_summary,
    build_price_outcome_observations,
)
from src.xau_forward_journal.report_store import XauForwardJournalReportStore


class XauForwardJournalConflictError(XauForwardJournalBuildError):
    def __init__(self, journal_id: str, snapshot_key: str) -> None:
        super().__init__(
            "A journal entry with this snapshot key already has non-pending outcomes",
            code="JOURNAL_ENTRY_CONFLICT",
            details=[
                {"field": "journal_id", "message": journal_id},
                {"field": "snapshot_key", "message": snapshot_key},
                {
                    "field": "resolution",
                    "message": (
                        "Create revision behavior is not implemented in this slice, "
                        "and immutable snapshots with completed outcomes are not overwritten."
                    ),
                },
            ],
        )


def create_xau_forward_journal_entry(
    request: XauForwardJournalCreateRequest,
    *,
    report_store: XauForwardJournalReportStore | None = None,
    reports_dir: Path | None = None,
) -> XauForwardJournalEntry:
    store = report_store or XauForwardJournalReportStore(reports_dir=reports_dir)
    entry = build_journal_entry(request, reports_dir=reports_dir or store.reports_dir)

    existing = store.find_entry_by_snapshot_key(entry.snapshot_key)
    if existing is not None:
        if _all_outcomes_pending(existing):
            return existing
        raise XauForwardJournalConflictError(existing.journal_id, existing.snapshot_key)

    if not request.persist_report:
        return entry
    return store.persist_entry(entry)


def update_xau_forward_journal_outcomes(
    journal_id: str,
    request: XauForwardOutcomeUpdateRequest,
    *,
    report_store: XauForwardJournalReportStore | None = None,
    reports_dir: Path | None = None,
) -> XauForwardOutcomeResponse:
    store = report_store or XauForwardJournalReportStore(reports_dir=reports_dir)
    entry = store.read_entry(journal_id)
    updated_entry = apply_outcome_update(entry, request)
    persisted_entry = store.persist_outcome_update(updated_entry)
    return store.read_outcome_response(persisted_entry.journal_id)


def get_xau_forward_journal_outcomes(
    journal_id: str,
    *,
    report_store: XauForwardJournalReportStore | None = None,
    reports_dir: Path | None = None,
) -> XauForwardOutcomeResponse:
    store = report_store or XauForwardJournalReportStore(reports_dir=reports_dir)
    return store.read_outcome_response(journal_id)


def get_xau_forward_journal_price_coverage(
    journal_id: str,
    request: XauForwardPriceCoverageRequest,
    *,
    report_store: XauForwardJournalReportStore | None = None,
    reports_dir: Path | None = None,
) -> XauForwardPriceCoverageResponse:
    store = report_store or XauForwardJournalReportStore(reports_dir=reports_dir)
    entry = store.read_entry(journal_id)
    candles, source = load_price_candles(request, base_dir=store.repo_root)
    coverage = build_price_coverage_summary(entry, candles, source)
    return XauForwardPriceCoverageResponse(
        journal_id=entry.journal_id,
        coverage=coverage,
        warnings=coverage.warnings,
        limitations=["Coverage checks do not update journal outcomes.", *coverage.limitations],
    )


def update_xau_forward_journal_outcomes_from_price_data(
    journal_id: str,
    request: XauForwardPriceDataUpdateRequest,
    *,
    report_store: XauForwardJournalReportStore | None = None,
    reports_dir: Path | None = None,
) -> XauForwardPriceOutcomeUpdateResponse:
    store = report_store or XauForwardJournalReportStore(reports_dir=reports_dir)
    entry = store.read_entry(journal_id)
    candles, source = load_price_candles(request, base_dir=store.repo_root)
    coverage = build_price_coverage_summary(entry, candles, source)
    price_update_id = _price_update_id()
    price_outcomes = build_price_outcome_observations(
        entry,
        candles,
        coverage,
        price_update_id=price_update_id,
    )
    updated_entry = apply_outcome_update(
        entry,
        XauForwardOutcomeUpdateRequest(
            outcomes=price_outcomes,
            update_note=request.update_note,
            research_only_acknowledged=True,
        ),
    )
    report = XauForwardPriceOutcomeUpdateReport(
        update_id=price_update_id,
        journal_id=entry.journal_id,
        source=source,
        coverage_summary=coverage,
        updated_outcomes=price_outcomes,
        missing_candle_checklist=coverage.missing_candle_checklist,
        proxy_limitations=coverage.proxy_limitations,
        warnings=coverage.warnings,
        limitations=[OUTCOME_PRICE_UPDATE_LIMITATION, *coverage.limitations],
    )
    if request.persist_report:
        persisted_entry, report = store.persist_price_update_report(updated_entry, report)
    else:
        persisted_entry = store.persist_outcome_update(updated_entry)

    return XauForwardPriceOutcomeUpdateResponse(
        journal_id=persisted_entry.journal_id,
        update_report=report,
        outcomes=persisted_entry.outcomes,
        coverage=coverage,
        artifacts=report.artifacts,
        warnings=report.warnings,
        limitations=report.limitations,
    )


def _all_outcomes_pending(entry: XauForwardJournalEntry) -> bool:
    return all(
        outcome.status == XauForwardOutcomeStatus.PENDING
        and outcome.label == XauForwardOutcomeLabel.PENDING
        for outcome in entry.outcomes
    )


def _price_update_id() -> str:
    return f"price_update_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S_%f')}"
