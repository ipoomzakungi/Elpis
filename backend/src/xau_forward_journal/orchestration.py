from __future__ import annotations

from pathlib import Path

from src.models.xau_forward_journal import (
    XauForwardJournalCreateRequest,
    XauForwardJournalEntry,
    XauForwardOutcomeLabel,
    XauForwardOutcomeResponse,
    XauForwardOutcomeStatus,
    XauForwardOutcomeUpdateRequest,
)
from src.xau_forward_journal.entry_builder import (
    XauForwardJournalBuildError,
    build_journal_entry,
)
from src.xau_forward_journal.outcome import apply_outcome_update
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


def _all_outcomes_pending(entry: XauForwardJournalEntry) -> bool:
    return all(
        outcome.status == XauForwardOutcomeStatus.PENDING
        and outcome.label == XauForwardOutcomeLabel.PENDING
        for outcome in entry.outcomes
    )
