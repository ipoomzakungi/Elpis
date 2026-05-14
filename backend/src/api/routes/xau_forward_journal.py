from fastapi import APIRouter, Depends, status

from src.api.validation import api_error
from src.models.xau_forward_journal import (
    XauForwardJournalCreateRequest,
    XauForwardJournalEntry,
    XauForwardJournalListResponse,
    XauForwardOutcomeResponse,
    XauForwardOutcomeUpdateRequest,
    XauForwardPriceCoverageRequest,
    XauForwardPriceCoverageResponse,
    XauForwardPriceDataUpdateRequest,
    XauForwardPriceOutcomeUpdateResponse,
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
    get_xau_forward_journal_price_coverage as orchestrate_get_xau_forward_journal_price_coverage,
)
from src.xau_forward_journal.orchestration import (
    update_xau_forward_journal_outcomes as orchestrate_update_xau_forward_journal_outcomes,
)
from src.xau_forward_journal.orchestration import (
    update_xau_forward_journal_outcomes_from_price_data as orchestrate_price_outcome_update,
)
from src.xau_forward_journal.outcome import (
    XauForwardOutcomeConflictError,
    XauForwardOutcomeUpdateError,
)
from src.xau_forward_journal.price_data import XauForwardPriceDataError
from src.xau_forward_journal.report_store import XauForwardJournalReportStore

router = APIRouter()


def get_xau_forward_journal_report_store() -> XauForwardJournalReportStore:
    return XauForwardJournalReportStore()


def get_xau_forward_price_coverage_request(
    source_label: str,
    ohlc_path: str,
    research_only_acknowledged: bool,
    source_symbol: str | None = None,
    timestamp_column: str = "timestamp",
    open_column: str = "open",
    high_column: str = "high",
    low_column: str = "low",
    close_column: str = "close",
    timezone: str = "UTC",
) -> XauForwardPriceCoverageRequest:
    try:
        return XauForwardPriceCoverageRequest(
            source_label=source_label,
            source_symbol=source_symbol,
            ohlc_path=ohlc_path,
            timestamp_column=timestamp_column,
            open_column=open_column,
            high_column=high_column,
            low_column=low_column,
            close_column=close_column,
            timezone=timezone,
            research_only_acknowledged=research_only_acknowledged,
        )
    except ValueError as exc:
        api_error(400, "VALIDATION_ERROR", str(exc))

    raise RuntimeError("unreachable")


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


@router.post(
    "/xau/forward-journal/entries/{journal_id}/outcomes/from-price-data",
    response_model=XauForwardPriceOutcomeUpdateResponse,
)
async def update_xau_forward_journal_outcomes_from_price_data(
    journal_id: str,
    request: XauForwardPriceDataUpdateRequest,
    store: XauForwardJournalReportStore = Depends(get_xau_forward_journal_report_store),
) -> XauForwardPriceOutcomeUpdateResponse:
    """Update saved outcome windows from local/public OHLC research candles."""

    _validate_journal_id(journal_id)
    try:
        return orchestrate_price_outcome_update(
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
    except XauForwardPriceDataError as exc:
        api_error(_price_data_status_code(exc), exc.code, str(exc), exc.details)
    except ValueError as exc:
        api_error(400, "VALIDATION_ERROR", str(exc))

    raise RuntimeError("unreachable")


@router.get(
    "/xau/forward-journal/entries/{journal_id}/price-coverage",
    response_model=XauForwardPriceCoverageResponse,
)
async def get_xau_forward_journal_price_coverage(
    journal_id: str,
    request: XauForwardPriceCoverageRequest = Depends(get_xau_forward_price_coverage_request),
    store: XauForwardJournalReportStore = Depends(get_xau_forward_journal_report_store),
) -> XauForwardPriceCoverageResponse:
    """Inspect price-candle coverage for a saved journal entry without mutating outcomes."""

    _validate_journal_id(journal_id)
    try:
        return orchestrate_get_xau_forward_journal_price_coverage(
            journal_id,
            request,
            report_store=store,
        )
    except FileNotFoundError:
        _journal_not_found(journal_id)
    except XauForwardPriceDataError as exc:
        api_error(_price_data_status_code(exc), exc.code, str(exc), exc.details)
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


def _price_data_status_code(exc: XauForwardPriceDataError) -> int:
    if exc.code == "PRICE_DATA_NOT_FOUND":
        return 404
    return 400
