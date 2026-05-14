from fastapi import APIRouter, Depends, status

from src.api.validation import api_error
from src.models.xau_forward_journal import (
    XAU_FORWARD_JOURNAL_FORWARD_ONLY_LIMITATION,
    XAU_FORWARD_JOURNAL_RESEARCH_ONLY_WARNING,
    XauForwardJournalCreateRequest,
    XauForwardJournalEntry,
    XauForwardJournalListResponse,
    XauForwardOutcomeResponse,
    XauForwardOutcomeUpdateRequest,
    validate_xau_forward_journal_safe_id,
)
from src.xau_forward_journal.entry_builder import (
    XauForwardIncompatibleSourceReportError,
    XauForwardJournalBuildError,
    XauForwardSourceReportNotFoundError,
)
from src.xau_forward_journal.orchestration import (
    XauForwardJournalConflictError,
)
from src.xau_forward_journal.orchestration import (
    create_xau_forward_journal_entry as orchestrate_xau_forward_journal_entry,
)
from src.xau_forward_journal.report_store import XauForwardJournalReportStore

router = APIRouter()


def get_xau_forward_journal_report_store() -> XauForwardJournalReportStore:
    return XauForwardJournalReportStore()


@router.post(
    "/xau/forward-journal/entries",
    response_model=XauForwardJournalEntry,
    status_code=status.HTTP_201_CREATED,
)
async def create_xau_forward_journal_entry(
    request: XauForwardJournalCreateRequest,
    store: XauForwardJournalReportStore = Depends(get_xau_forward_journal_report_store),
) -> XauForwardJournalEntry:
    """Create a local-only XAU forward journal entry from saved report ids."""

    try:
        return orchestrate_xau_forward_journal_entry(request, report_store=store)
    except XauForwardSourceReportNotFoundError as exc:
        api_error(404, exc.code, str(exc), exc.details)
    except XauForwardIncompatibleSourceReportError as exc:
        api_error(400, exc.code, str(exc), exc.details)
    except XauForwardJournalConflictError as exc:
        api_error(409, exc.code, str(exc), exc.details)
    except XauForwardJournalBuildError as exc:
        api_error(400, exc.code, str(exc), exc.details)
    except ValueError as exc:
        api_error(400, "VALIDATION_ERROR", str(exc))

    raise RuntimeError("unreachable")


@router.get(
    "/xau/forward-journal/entries",
    response_model=XauForwardJournalListResponse,
)
async def list_xau_forward_journal_entries() -> XauForwardJournalListResponse:
    """List saved local-only XAU forward journal entries."""

    return XauForwardJournalListResponse(entries=[])


@router.get(
    "/xau/forward-journal/entries/{journal_id}",
    response_model=XauForwardJournalEntry,
)
async def get_xau_forward_journal_entry(journal_id: str) -> XauForwardJournalEntry:
    """Read one saved local-only XAU forward journal entry."""

    _validate_journal_id(journal_id)
    _foundation_not_implemented(
        "XAU forward journal detail reads are not implemented in this foundation slice.",
        [{"field": "journal_id", "message": journal_id}],
    )
    raise RuntimeError("unreachable")


@router.post(
    "/xau/forward-journal/entries/{journal_id}/outcomes",
    response_model=XauForwardOutcomeResponse,
)
async def update_xau_forward_journal_outcomes(
    journal_id: str,
    request: XauForwardOutcomeUpdateRequest,
) -> XauForwardOutcomeResponse:
    """Attach later local-only outcome windows to a saved journal entry."""

    _validate_journal_id(journal_id)
    _foundation_not_implemented(
        "XAU forward journal outcome updates are not implemented in this foundation slice.",
        [
            {"field": "journal_id", "message": journal_id},
            {"field": "outcomes", "message": str(len(request.outcomes))},
        ],
    )
    raise RuntimeError("unreachable")


@router.get(
    "/xau/forward-journal/entries/{journal_id}/outcomes",
    response_model=XauForwardOutcomeResponse,
)
async def get_xau_forward_journal_outcomes(journal_id: str) -> XauForwardOutcomeResponse:
    """Read later local-only outcome windows for a saved journal entry."""

    _validate_journal_id(journal_id)
    _foundation_not_implemented(
        "XAU forward journal outcome reads are not implemented in this foundation slice.",
        [{"field": "journal_id", "message": journal_id}],
    )
    raise RuntimeError("unreachable")


def _validate_journal_id(journal_id: str) -> None:
    try:
        validate_xau_forward_journal_safe_id(journal_id, "journal_id")
    except ValueError as exc:
        api_error(400, "VALIDATION_ERROR", str(exc))


def _foundation_not_implemented(
    message: str,
    details: list[dict[str, str]] | None = None,
) -> None:
    api_error(
        501,
        "NOT_IMPLEMENTED",
        message,
        [
            {
                "field": "scope",
                "message": (
                    "Forward journal routes are local-only and research-only placeholders; "
                    "they do not create entries, label outcomes, or access browser sessions."
                ),
            },
            {
                "field": "limitation",
                "message": XAU_FORWARD_JOURNAL_FORWARD_ONLY_LIMITATION,
            },
            {
                "field": "research_only",
                "message": XAU_FORWARD_JOURNAL_RESEARCH_ONLY_WARNING,
            },
            *(details or []),
        ],
    )
