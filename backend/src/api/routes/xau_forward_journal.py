from fastapi import APIRouter, Depends, status

from src.api.validation import api_error
from src.models.xau_forward_journal import (
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
from src.xau_forward_journal.orchestration import (
    get_xau_forward_journal_outcomes as orchestrate_get_xau_forward_journal_outcomes,
)
from src.xau_forward_journal.orchestration import (
    update_xau_forward_journal_outcomes as orchestrate_update_xau_forward_journal_outcomes,
)
from src.xau_forward_journal.outcome import (
    XauForwardOutcomeConflictError,
    XauForwardOutcomeUpdateError,
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
async def list_xau_forward_journal_entries(
    store: XauForwardJournalReportStore = Depends(get_xau_forward_journal_report_store),
) -> XauForwardJournalListResponse:
    """List saved local-only XAU forward journal entries."""

    try:
        return store.list_entries()
    except ValueError as exc:
        api_error(400, "VALIDATION_ERROR", str(exc))

    raise RuntimeError("unreachable")


@router.get(
    "/xau/forward-journal/entries/{journal_id}",
    response_model=XauForwardJournalEntry,
)
async def get_xau_forward_journal_entry(
    journal_id: str,
    store: XauForwardJournalReportStore = Depends(get_xau_forward_journal_report_store),
) -> XauForwardJournalEntry:
    """Read one saved local-only XAU forward journal entry."""

    _validate_journal_id(journal_id)
    try:
        return store.read_entry(journal_id)
    except FileNotFoundError:
        _journal_not_found(journal_id)
    except ValueError as exc:
        api_error(400, "VALIDATION_ERROR", str(exc))

    raise RuntimeError("unreachable")


@router.post(
    "/xau/forward-journal/entries/{journal_id}/outcomes",
    response_model=XauForwardOutcomeResponse,
)
async def update_xau_forward_journal_outcomes(
    journal_id: str,
    request: XauForwardOutcomeUpdateRequest,
    store: XauForwardJournalReportStore = Depends(get_xau_forward_journal_report_store),
) -> XauForwardOutcomeResponse:
    """Attach later local-only outcome windows to a saved journal entry."""

    _validate_journal_id(journal_id)
    try:
        return orchestrate_update_xau_forward_journal_outcomes(
            journal_id,
            request,
            report_store=store,
        )
    except FileNotFoundError:
        _journal_not_found(journal_id)
    except XauForwardOutcomeConflictError as exc:
        api_error(409, exc.code, str(exc), exc.details)
    except XauForwardOutcomeUpdateError as exc:
        api_error(400, exc.code, str(exc), exc.details)
    except ValueError as exc:
        api_error(400, "VALIDATION_ERROR", str(exc))

    raise RuntimeError("unreachable")


@router.get(
    "/xau/forward-journal/entries/{journal_id}/outcomes",
    response_model=XauForwardOutcomeResponse,
)
async def get_xau_forward_journal_outcomes(
    journal_id: str,
    store: XauForwardJournalReportStore = Depends(get_xau_forward_journal_report_store),
) -> XauForwardOutcomeResponse:
    """Read later local-only outcome windows for a saved journal entry."""

    _validate_journal_id(journal_id)
    try:
        return orchestrate_get_xau_forward_journal_outcomes(
            journal_id,
            report_store=store,
        )
    except FileNotFoundError:
        _journal_not_found(journal_id)
    except ValueError as exc:
        api_error(400, "VALIDATION_ERROR", str(exc))

    raise RuntimeError("unreachable")


def _validate_journal_id(journal_id: str) -> None:
    try:
        validate_xau_forward_journal_safe_id(journal_id, "journal_id")
    except ValueError as exc:
        api_error(400, "VALIDATION_ERROR", str(exc))


def _journal_not_found(journal_id: str) -> None:
    api_error(
        404,
        "NOT_FOUND",
        f"XAU forward journal entry '{journal_id}' was not found",
        [{"field": "journal_id", "message": journal_id}],
    )
