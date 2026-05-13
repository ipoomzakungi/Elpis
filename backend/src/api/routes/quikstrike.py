from fastapi import APIRouter, Depends, HTTPException, status

from src.models.quikstrike import (
    QuikStrikeConversionRowsResponse,
    QuikStrikeExtractionListResponse,
    QuikStrikeExtractionReport,
    QuikStrikeExtractionRequest,
    QuikStrikeRowsResponse,
    validate_quikstrike_safe_id,
)
from src.quikstrike.conversion import convert_to_xau_vol_oi_rows
from src.quikstrike.extraction import build_extraction_from_request
from src.quikstrike.report_store import QuikStrikeReportStore

router = APIRouter()


def get_quikstrike_report_store() -> QuikStrikeReportStore:
    return QuikStrikeReportStore()


@router.post(
    "/quikstrike/extractions/from-fixture",
    response_model=QuikStrikeExtractionReport,
    status_code=status.HTTP_201_CREATED,
)
async def create_quikstrike_extraction_from_fixture(
    request: QuikStrikeExtractionRequest,
    store: QuikStrikeReportStore = Depends(get_quikstrike_report_store),
) -> QuikStrikeExtractionReport:
    """Create a local-only QuikStrike extraction from sanitized fixture payloads."""

    try:
        extraction = build_extraction_from_request(request)
        conversion = convert_to_xau_vol_oi_rows(
            extraction_result=extraction.result,
            rows=extraction.rows,
        )
        return store.persist_report(
            extraction_result=extraction.result,
            normalized_rows=extraction.rows,
            conversion_result=conversion.result,
            conversion_rows=conversion.rows,
        )
    except ValueError as exc:
        _validation_error(str(exc))

    raise HTTPException(status_code=500, detail="QuikStrike extraction failed")


@router.get(
    "/quikstrike/extractions",
    response_model=QuikStrikeExtractionListResponse,
)
async def list_quikstrike_extractions(
    store: QuikStrikeReportStore = Depends(get_quikstrike_report_store),
) -> QuikStrikeExtractionListResponse:
    """List saved local-only QuikStrike extraction reports."""

    return store.list_reports()


@router.get(
    "/quikstrike/extractions/{extraction_id}",
    response_model=QuikStrikeExtractionReport,
)
async def get_quikstrike_extraction(
    extraction_id: str,
    store: QuikStrikeReportStore = Depends(get_quikstrike_report_store),
) -> QuikStrikeExtractionReport:
    """Read one saved local-only QuikStrike extraction report."""

    _validate_extraction_id(extraction_id)
    try:
        return store.read_report(extraction_id)
    except FileNotFoundError:
        _not_found(extraction_id)

    raise HTTPException(status_code=500, detail="QuikStrike extraction read failed")


@router.get(
    "/quikstrike/extractions/{extraction_id}/rows",
    response_model=QuikStrikeRowsResponse,
)
async def get_quikstrike_extraction_rows(
    extraction_id: str,
    store: QuikStrikeReportStore = Depends(get_quikstrike_report_store),
) -> QuikStrikeRowsResponse:
    """Read normalized rows for one saved QuikStrike extraction."""

    _validate_extraction_id(extraction_id)
    try:
        return store.read_rows_response(extraction_id)
    except FileNotFoundError:
        _not_found(extraction_id)

    raise HTTPException(status_code=500, detail="QuikStrike rows read failed")


@router.get(
    "/quikstrike/extractions/{extraction_id}/conversion",
    response_model=QuikStrikeConversionRowsResponse,
)
async def get_quikstrike_extraction_conversion(
    extraction_id: str,
    store: QuikStrikeReportStore = Depends(get_quikstrike_report_store),
) -> QuikStrikeConversionRowsResponse:
    """Read XAU Vol-OI compatible conversion status and rows for one extraction."""

    _validate_extraction_id(extraction_id)
    try:
        return store.read_conversion_response(extraction_id)
    except FileNotFoundError:
        _not_found(extraction_id)

    raise HTTPException(status_code=500, detail="QuikStrike conversion read failed")


def _validate_extraction_id(extraction_id: str) -> None:
    try:
        validate_quikstrike_safe_id(extraction_id)
    except ValueError as exc:
        _validation_error(str(exc))


def _validation_error(message: str) -> None:
    raise HTTPException(
        status_code=400,
        detail={"error": {"code": "VALIDATION_ERROR", "message": message, "details": []}},
    )


def _not_found(extraction_id: str) -> None:
    raise HTTPException(
        status_code=404,
        detail={
            "error": {
                "code": "NOT_FOUND",
                "message": f"QuikStrike extraction '{extraction_id}' was not found",
                "details": [],
            }
        },
    )
