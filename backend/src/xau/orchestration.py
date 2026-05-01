from datetime import UTC, date, datetime

from src.models.xau import (
    XauExpectedRange,
    XauOptionsImportReport,
    XauReportStatus,
    XauVolOiReport,
    XauVolOiReportRequest,
)
from src.xau.basis import build_basis_snapshot
from src.xau.imports import validate_options_oi_file
from src.xau.report_store import XauReportStore
from src.xau.volatility import expected_range_from_snapshot, unavailable_expected_range

RESEARCH_ONLY_XAU_WARNING = (
    "XAU Vol-OI outputs are research annotations only and do not imply profitability, "
    "predictive power, safety, or live readiness."
)


class XauReportValidationError(ValueError):
    """Raised when an XAU report request cannot pass local input preflight."""

    def __init__(self, validation_report: XauOptionsImportReport) -> None:
        super().__init__("Gold options OI file is not valid for XAU wall analysis")
        self.validation_report = validation_report


class XauReportOrchestrator:
    """Coordinate the current XAU local import preflight report slice."""

    def __init__(self, report_store: XauReportStore | None = None) -> None:
        self.report_store = report_store or XauReportStore()

    def run(self, request: XauVolOiReportRequest) -> XauVolOiReport:
        source_validation = validate_options_oi_file(request.options_oi_file_path)
        if not source_validation.is_valid:
            raise XauReportValidationError(source_validation)

        report = self._build_preflight_report(request, source_validation)
        return self.report_store.save_source_validation_report(report)

    def _build_preflight_report(
        self,
        request: XauVolOiReportRequest,
        source_validation: XauOptionsImportReport,
    ) -> XauVolOiReport:
        created_at = datetime.now(UTC)
        session_date = request.session_date or _derive_session_date(source_validation)
        basis_snapshot = build_basis_snapshot(
            spot_reference=request.spot_reference,
            futures_reference=request.futures_reference,
            manual_basis=request.manual_basis,
        )
        expected_range = _expected_range(request)
        warnings = [
            RESEARCH_ONLY_XAU_WARNING,
            "Wall scoring and zone classification are not included in this import preflight slice.",
            *source_validation.warnings,
        ]
        missing_instructions = _missing_data_instructions(
            request=request,
            source_validation=source_validation,
            expected_range=expected_range,
            basis_mapping_available=basis_snapshot.mapping_available,
        )
        return XauVolOiReport(
            report_id=_report_id(created_at),
            status=XauReportStatus.PARTIAL,
            created_at=created_at,
            session_date=session_date,
            request=request,
            source_validation=source_validation,
            basis_snapshot=basis_snapshot,
            expected_range=expected_range,
            source_row_count=source_validation.source_row_count,
            accepted_row_count=source_validation.accepted_row_count,
            rejected_row_count=source_validation.rejected_row_count,
            wall_count=0,
            zone_count=0,
            warnings=warnings,
            limitations=[
                "Local imported options data must be independently verified for completeness.",
                "Yahoo Finance GC=F and GLD are OHLCV proxies only, not gold options OI or IV.",
            ],
            missing_data_instructions=missing_instructions,
        )


def _derive_session_date(source_validation: XauOptionsImportReport) -> date | None:
    if not source_validation.rows:
        return None
    return min(row.timestamp.date() for row in source_validation.rows)


def _expected_range(request: XauVolOiReportRequest) -> XauExpectedRange:
    reference_price = request.spot_reference.price if request.spot_reference else None
    if request.volatility_snapshot is None:
        return unavailable_expected_range("Volatility snapshot is unavailable.")
    return expected_range_from_snapshot(
        snapshot=request.volatility_snapshot,
        reference_price=reference_price,
        include_2sd_range=request.include_2sd_range,
    )


def _missing_data_instructions(
    *,
    request: XauVolOiReportRequest,
    source_validation: XauOptionsImportReport,
    expected_range: XauExpectedRange,
    basis_mapping_available: bool,
) -> list[str]:
    instructions = list(source_validation.instructions)
    optional_present = set(source_validation.optional_columns_present)
    if "implied_volatility" not in optional_present and request.volatility_snapshot is None:
        instructions.append(
            "Import implied_volatility or provide a volatility_snapshot to compute IV ranges."
        )
    if "oi_change" not in optional_present and "volume" not in optional_present:
        instructions.append(
            "Import oi_change or volume to improve freshness scoring in a later wall phase."
        )
    if not basis_mapping_available:
        instructions.append(
            "Provide spot_reference and futures_reference, or manual_basis, "
            "for spot-equivalent mapping."
        )
    if expected_range.unavailable_reason:
        instructions.append(expected_range.unavailable_reason)
    return _deduplicate(instructions)


def _report_id(created_at: datetime) -> str:
    return f"xau_vol_oi_{created_at.strftime('%Y%m%d_%H%M%S_%f')}"


def _deduplicate(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
