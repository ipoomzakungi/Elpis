from __future__ import annotations

from pathlib import Path

from src.models.xau_forward_journal import (
    XauForwardJournalCreateRequest,
    XauForwardJournalEntry,
    XauForwardOutcomeLabel,
    XauForwardOutcomeStatus,
)
from src.xau_forward_journal.entry_builder import (
    XauForwardJournalBuildError,
    build_journal_entry,
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


def _all_outcomes_pending(entry: XauForwardJournalEntry) -> bool:
    return all(
        outcome.status == XauForwardOutcomeStatus.PENDING
        and outcome.label == XauForwardOutcomeLabel.PENDING
        for outcome in entry.outcomes
    )
