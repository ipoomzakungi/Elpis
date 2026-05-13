from fastapi import APIRouter, Depends, HTTPException, status

from src.models.quikstrike_matrix import (
    QuikStrikeMatrixConversionRowsResponse,
    QuikStrikeMatrixExtractionListResponse,
    QuikStrikeMatrixExtractionReport,
    QuikStrikeMatrixExtractionRequest,
    QuikStrikeMatrixRowsResponse,
    validate_quikstrike_matrix_safe_id,
)
from src.quikstrike_matrix.conversion import convert_to_xau_vol_oi_rows
from src.quikstrike_matrix.extraction import build_extraction_from_request
from src.quikstrike_matrix.report_store import QuikStrikeMatrixReportStore

router = APIRouter()


def get_quikstrike_matrix_report_store() -> QuikStrikeMatrixReportStore:
    return QuikStrikeMatrixReportStore()


@router.post(
    "/quikstrike-matrix/extractions/from-fixture",
    response_model=QuikStrikeMatrixExtractionReport,
    status_code=status.HTTP_201_CREATED,
)
async def create_quikstrike_matrix_extraction_from_fixture(
    request: QuikStrikeMatrixExtractionRequest,
    store: QuikStrikeMatrixReportStore = Depends(get_quikstrike_matrix_report_store),
) -> QuikStrikeMatrixExtractionReport:
    """Create a local-only QuikStrike Matrix extraction from sanitized fixtures."""

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

    raise HTTPException(status_code=500, detail="QuikStrike Matrix extraction failed")


@router.get(
    "/quikstrike-matrix/extractions",
    response_model=QuikStrikeMatrixExtractionListResponse,
)
async def list_quikstrike_matrix_extractions(
    store: QuikStrikeMatrixReportStore = Depends(get_quikstrike_matrix_report_store),
) -> QuikStrikeMatrixExtractionListResponse:
    """List saved local-only QuikStrike Matrix extraction reports."""

    return store.list_reports()


@router.get(
    "/quikstrike-matrix/extractions/{extraction_id}",
    response_model=QuikStrikeMatrixExtractionReport,
)
async def get_quikstrike_matrix_extraction(
    extraction_id: str,
    store: QuikStrikeMatrixReportStore = Depends(get_quikstrike_matrix_report_store),
) -> QuikStrikeMatrixExtractionReport:
    """Read one saved local-only QuikStrike Matrix extraction report."""

    _validate_extraction_id(extraction_id)
    try:
        return store.read_report(extraction_id)
    except FileNotFoundError:
        _not_found(extraction_id)

    raise HTTPException(status_code=500, detail="QuikStrike Matrix extraction read failed")


@router.get(
    "/quikstrike-matrix/extractions/{extraction_id}/rows",
    response_model=QuikStrikeMatrixRowsResponse,
)
async def get_quikstrike_matrix_extraction_rows(
    extraction_id: str,
    store: QuikStrikeMatrixReportStore = Depends(get_quikstrike_matrix_report_store),
) -> QuikStrikeMatrixRowsResponse:
    """Read normalized rows for one saved QuikStrike Matrix extraction."""

    _validate_extraction_id(extraction_id)
    try:
        return store.read_rows_response(extraction_id)
    except FileNotFoundError:
        _not_found(extraction_id)

    raise HTTPException(status_code=500, detail="QuikStrike Matrix rows read failed")


@router.get(
    "/quikstrike-matrix/extractions/{extraction_id}/conversion",
    response_model=QuikStrikeMatrixConversionRowsResponse,
)
async def get_quikstrike_matrix_extraction_conversion(
    extraction_id: str,
    store: QuikStrikeMatrixReportStore = Depends(get_quikstrike_matrix_report_store),
) -> QuikStrikeMatrixConversionRowsResponse:
    """Read XAU Vol-OI compatible conversion status and rows for one extraction."""

    _validate_extraction_id(extraction_id)
    try:
        return store.read_conversion_response(extraction_id)
    except FileNotFoundError:
        _not_found(extraction_id)

    raise HTTPException(status_code=500, detail="QuikStrike Matrix conversion read failed")


def _validate_extraction_id(extraction_id: str) -> None:
    try:
        validate_quikstrike_matrix_safe_id(extraction_id)
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
                "message": f"QuikStrike Matrix extraction '{extraction_id}' was not found",
                "details": [],
            }
        },
    )
