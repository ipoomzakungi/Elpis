"""Convert validated QuikStrike Matrix rows into XAU Vol-OI local input rows."""

from dataclasses import dataclass
from datetime import UTC, datetime

from src.models.quikstrike_matrix import (
    QuikStrikeMatrixArtifact,
    QuikStrikeMatrixArtifactFormat,
    QuikStrikeMatrixArtifactType,
    QuikStrikeMatrixCellState,
    QuikStrikeMatrixConversionResult,
    QuikStrikeMatrixConversionStatus,
    QuikStrikeMatrixExtractionResult,
    QuikStrikeMatrixExtractionStatus,
    QuikStrikeMatrixMappingStatus,
    QuikStrikeMatrixNormalizedRow,
    QuikStrikeMatrixValueType,
    QuikStrikeMatrixXauVolOiRow,
)

CONVERSION_LIMITATION = (
    "Conversion prepares local XAU Vol-OI research input only and does not run wall scoring."
)
SOURCE_LIMITATION = (
    "Converted from local QuikStrike Matrix table extraction; source limitations are preserved."
)
UNAVAILABLE_CELL_WARNING = "Unavailable cells were omitted and not treated as zero."
MATRIX_VIEW_ORDER = (
    "open_interest_matrix",
    "oi_change_matrix",
    "volume_matrix",
)


@dataclass(frozen=True)
class QuikStrikeMatrixConversionBundle:
    result: QuikStrikeMatrixConversionResult
    rows: list[QuikStrikeMatrixXauVolOiRow]


def convert_to_xau_vol_oi_rows(
    *,
    extraction_result: QuikStrikeMatrixExtractionResult,
    rows: list[QuikStrikeMatrixNormalizedRow],
    conversion_id: str | None = None,
    created_at: datetime | None = None,
) -> QuikStrikeMatrixConversionBundle:
    """Convert validated matrix rows to existing XAU Vol-OI local input shape."""

    timestamp = created_at or datetime.now(UTC)
    safe_conversion_id = conversion_id or f"{extraction_result.extraction_id}_xau_vol_oi"
    blocked_reasons = _conversion_blockers(extraction_result, rows)
    if blocked_reasons:
        return QuikStrikeMatrixConversionBundle(
            result=QuikStrikeMatrixConversionResult(
                conversion_id=safe_conversion_id,
                extraction_id=extraction_result.extraction_id,
                status=QuikStrikeMatrixConversionStatus.BLOCKED,
                row_count=0,
                blocked_reasons=blocked_reasons,
                limitations=[CONVERSION_LIMITATION],
            ),
            rows=[],
        )

    converted_rows = _aggregate_rows(rows)
    artifact = QuikStrikeMatrixArtifact(
        artifact_type=QuikStrikeMatrixArtifactType.PROCESSED_XAU_VOL_OI_CSV,
        path=f"data/processed/quikstrike_matrix/{safe_conversion_id}_input.csv",
        format=QuikStrikeMatrixArtifactFormat.CSV,
        rows=len(converted_rows),
        created_at=timestamp,
        limitations=[SOURCE_LIMITATION],
    )
    result = QuikStrikeMatrixConversionResult(
        conversion_id=safe_conversion_id,
        extraction_id=extraction_result.extraction_id,
        status=QuikStrikeMatrixConversionStatus.COMPLETED,
        row_count=len(converted_rows),
        output_artifacts=[artifact],
        blocked_reasons=[],
        warnings=_conversion_warnings(rows),
        limitations=[CONVERSION_LIMITATION, SOURCE_LIMITATION],
    )
    return QuikStrikeMatrixConversionBundle(result=result, rows=converted_rows)


def _conversion_blockers(
    extraction_result: QuikStrikeMatrixExtractionResult,
    rows: list[QuikStrikeMatrixNormalizedRow],
) -> list[str]:
    blockers: list[str] = []
    available_rows = [
        row for row in rows if row.cell_state == QuikStrikeMatrixCellState.AVAILABLE
    ]
    if not available_rows:
        blockers.append("No available QuikStrike Matrix rows are available for conversion.")
    if extraction_result.status in {
        QuikStrikeMatrixExtractionStatus.BLOCKED,
        QuikStrikeMatrixExtractionStatus.FAILED,
    }:
        blockers.append(f"Extraction status is {extraction_result.status.value}.")
    if extraction_result.mapping.status == QuikStrikeMatrixMappingStatus.BLOCKED:
        blockers.append("Matrix mapping is blocked.")
    if not extraction_result.conversion_eligible:
        blockers.append("Extraction result is not marked conversion eligible.")
    if any(row.strike is None for row in available_rows):
        blockers.append("One or more available rows are missing strike.")
    if any(row.expiration is None for row in available_rows):
        blockers.append("One or more available rows are missing expiration.")
    if any(row.option_type is None for row in available_rows):
        blockers.append("One or more available rows are missing option type.")
    return _dedupe(blockers)


def _aggregate_rows(
    rows: list[QuikStrikeMatrixNormalizedRow],
) -> list[QuikStrikeMatrixXauVolOiRow]:
    grouped: dict[tuple[str, float, str], QuikStrikeMatrixXauVolOiRow] = {}
    for row in rows:
        if (
            row.cell_state != QuikStrikeMatrixCellState.AVAILABLE
            or row.value is None
            or row.strike is None
            or row.expiration is None
            or row.option_type is None
        ):
            continue
        key = (row.expiration, row.strike, row.option_type.value)
        current = grouped.get(key)
        if current is None:
            current = QuikStrikeMatrixXauVolOiRow(
                timestamp=row.capture_timestamp,
                expiry=row.expiration,
                strike=row.strike,
                option_type=row.option_type,
                source_menu=row.source_menu,
                source_view=row.view_type.value,
                source_extraction_id=row.extraction_id,
                table_row_label=row.table_row_label,
                table_column_label=row.table_column_label,
                futures_symbol=row.futures_symbol,
                dte=row.dte,
                underlying_futures_price=row.future_reference_price,
                limitations=_row_limitations(row),
            )
        grouped[key] = _apply_row_value(current, row)
    return sorted(
        grouped.values(),
        key=lambda item: (item.expiry, item.strike, item.option_type.value),
    )


def _apply_row_value(
    current: QuikStrikeMatrixXauVolOiRow,
    row: QuikStrikeMatrixNormalizedRow,
) -> QuikStrikeMatrixXauVolOiRow:
    update: dict[str, float | str | None] = {
        "source_view": _merge_source_views(current.source_view, row.view_type.value),
    }
    if row.value_type == QuikStrikeMatrixValueType.OPEN_INTEREST:
        update["open_interest"] = row.value
    elif row.value_type == QuikStrikeMatrixValueType.OI_CHANGE:
        update["oi_change"] = row.value
    elif row.value_type == QuikStrikeMatrixValueType.VOLUME:
        update["volume"] = row.value
    return current.model_copy(update=update)


def _conversion_warnings(rows: list[QuikStrikeMatrixNormalizedRow]) -> list[str]:
    if any(row.cell_state != QuikStrikeMatrixCellState.AVAILABLE for row in rows):
        return [UNAVAILABLE_CELL_WARNING]
    return []


def _merge_source_views(current: str, incoming: str) -> str:
    values = {
        value.strip()
        for value in current.replace("|", ",").split(",")
        if value.strip()
    }
    values.add(incoming)
    ordered = [value for value in MATRIX_VIEW_ORDER if value in values]
    ordered.extend(sorted(values.difference(MATRIX_VIEW_ORDER)))
    return ",".join(ordered)


def _row_limitations(row: QuikStrikeMatrixNormalizedRow) -> list[str]:
    return _dedupe([SOURCE_LIMITATION, *row.extraction_limitations])


def _dedupe(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        if value and value not in deduped:
            deduped.append(value)
    return deduped
