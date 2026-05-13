"""Build normalized local-only QuikStrike Matrix rows from sanitized table fixtures."""

from dataclasses import dataclass
from datetime import UTC, datetime

from src.models.quikstrike_matrix import (
    QUIKSTRIKE_MATRIX_RESEARCH_ONLY_WARNING,
    QuikStrikeMatrixBodyCell,
    QuikStrikeMatrixCellState,
    QuikStrikeMatrixExtractionRequest,
    QuikStrikeMatrixExtractionResult,
    QuikStrikeMatrixExtractionStatus,
    QuikStrikeMatrixMappingStatus,
    QuikStrikeMatrixMappingValidation,
    QuikStrikeMatrixMetadata,
    QuikStrikeMatrixNormalizedRow,
    QuikStrikeMatrixTableSnapshot,
    QuikStrikeMatrixViewType,
    value_type_for_matrix_view,
)
from src.quikstrike_matrix.table_reader import parse_matrix_table

LOCAL_ONLY_LIMITATION = "QuikStrike Matrix extraction is local-only and research-only."
SANITIZED_INPUT_LIMITATION = "Only sanitized visible metadata and HTML table cells are processed."
NO_ENDPOINT_REPLAY_LIMITATION = (
    "No endpoint replay, credentials, cookies, headers, HAR, screenshots, "
    "or viewstate are used."
)
ARTIFACT_SCOPE_LIMITATION = "Generated Matrix artifacts must stay under ignored local data paths."


@dataclass(frozen=True)
class QuikStrikeMatrixExtractionBundle:
    result: QuikStrikeMatrixExtractionResult
    rows: list[QuikStrikeMatrixNormalizedRow]


def build_extraction_from_request(
    request: QuikStrikeMatrixExtractionRequest,
    *,
    extraction_id: str | None = None,
    capture_timestamp: datetime | None = None,
) -> QuikStrikeMatrixExtractionBundle:
    """Build normalized matrix rows and extraction status from sanitized request fixtures."""

    timestamp = capture_timestamp or datetime.now(UTC)
    safe_extraction_id = extraction_id or _default_extraction_id(timestamp)
    rows: list[QuikStrikeMatrixNormalizedRow] = []
    warnings: list[str] = []
    completed_views: list[QuikStrikeMatrixViewType] = []
    partial_views: list[QuikStrikeMatrixViewType] = []
    missing_views: list[QuikStrikeMatrixViewType] = []
    view_mappings: list[QuikStrikeMatrixMappingValidation] = []

    for view in request.requested_views:
        metadata = request.metadata_by_view[view]
        snapshot = request.tables_by_view[view]
        view_rows, mapping = build_normalized_rows_for_view(
            extraction_id=safe_extraction_id,
            capture_timestamp=timestamp,
            metadata=metadata,
            snapshot=snapshot,
        )
        rows.extend(view_rows)
        view_mappings.append(mapping)
        warnings.extend(mapping.warnings)
        if not view_rows:
            missing_views.append(view)
        elif mapping.status == QuikStrikeMatrixMappingStatus.VALID:
            completed_views.append(view)
        else:
            partial_views.append(view)

    mapping = combine_mapping_validations(view_mappings)
    duplicate_count = _duplicate_count(rows)
    if duplicate_count:
        warnings.append(f"{duplicate_count} duplicate matrix row key(s) were detected.")
        mapping = mapping.model_copy(
            update={
                "duplicate_row_count": duplicate_count,
                "warnings": _dedupe([*mapping.warnings, *warnings]),
            }
        )

    status = _extraction_status(rows, missing_views, partial_views, mapping)
    available_rows = [
        row for row in rows if row.cell_state == QuikStrikeMatrixCellState.AVAILABLE
    ]
    conversion_eligible = (
        bool(available_rows)
        and mapping.status != QuikStrikeMatrixMappingStatus.BLOCKED
        and not _rows_missing_conversion_keys(available_rows)
    )
    result = QuikStrikeMatrixExtractionResult(
        extraction_id=safe_extraction_id,
        status=status,
        created_at=timestamp,
        completed_at=timestamp,
        requested_views=request.requested_views,
        completed_views=completed_views,
        partial_views=partial_views,
        missing_views=missing_views,
        row_count=len(rows),
        strike_count=len({row.strike for row in rows if row.strike is not None}),
        expiration_count=len({row.expiration for row in rows if row.expiration}),
        unavailable_cell_count=sum(
            row.cell_state != QuikStrikeMatrixCellState.AVAILABLE for row in rows
        ),
        mapping=mapping,
        conversion_eligible=conversion_eligible,
        warnings=_dedupe(warnings),
        limitations=[
            LOCAL_ONLY_LIMITATION,
            SANITIZED_INPUT_LIMITATION,
            NO_ENDPOINT_REPLAY_LIMITATION,
            ARTIFACT_SCOPE_LIMITATION,
        ],
        research_only_warnings=[QUIKSTRIKE_MATRIX_RESEARCH_ONLY_WARNING],
    )
    return QuikStrikeMatrixExtractionBundle(result=result, rows=rows)


def build_normalized_rows_for_view(
    *,
    extraction_id: str,
    capture_timestamp: datetime,
    metadata: QuikStrikeMatrixMetadata,
    snapshot: QuikStrikeMatrixTableSnapshot,
) -> tuple[list[QuikStrikeMatrixNormalizedRow], QuikStrikeMatrixMappingValidation]:
    """Combine one sanitized metadata object with one parsed matrix table."""

    if metadata.selected_view_type != snapshot.view_type:
        raise ValueError("metadata and matrix snapshot view types must match")

    parsed = parse_matrix_table(snapshot)
    mapping = validate_matrix_mapping(parsed.body_cells)
    rows = [
        _normalized_row(
            extraction_id=extraction_id,
            capture_timestamp=capture_timestamp,
            metadata=metadata,
            snapshot=snapshot,
            cell=cell,
            warnings=parsed.warnings,
            limitations=parsed.limitations,
        )
        for cell in parsed.body_cells
    ]
    return rows, mapping


def validate_matrix_mapping(
    body_cells: list[QuikStrikeMatrixBodyCell],
) -> QuikStrikeMatrixMappingValidation:
    """Validate table structure and conversion-relevant matrix mappings."""

    table_present = bool(body_cells)
    strike_count = len({cell.strike for cell in body_cells if cell.strike is not None})
    expiration_count = len({cell.expiration for cell in body_cells if cell.expiration})
    numeric_count = sum(
        cell.cell_state == QuikStrikeMatrixCellState.AVAILABLE for cell in body_cells
    )
    unavailable_count = sum(
        cell.cell_state != QuikStrikeMatrixCellState.AVAILABLE for cell in body_cells
    )
    option_types = {cell.option_type for cell in body_cells if cell.option_type is not None}
    blocked_reasons: list[str] = []
    warnings: list[str] = []

    if not table_present:
        blocked_reasons.append("Matrix table rows were not found.")
    if strike_count == 0:
        blocked_reasons.append("Strike rows could not be determined.")
    if expiration_count == 0:
        blocked_reasons.append("Expiration columns could not be determined.")
    if numeric_count == 0:
        blocked_reasons.append("No numeric matrix values were available.")
    if unavailable_count:
        warnings.append("Unavailable cells were preserved and not treated as zero.")
    if not option_types:
        warnings.append("Option-side mapping was not available.")

    status = (
        QuikStrikeMatrixMappingStatus.BLOCKED
        if blocked_reasons
        else QuikStrikeMatrixMappingStatus.VALID
    )
    return QuikStrikeMatrixMappingValidation(
        status=status,
        table_present=table_present,
        strike_rows_found=strike_count,
        expiration_columns_found=expiration_count,
        option_side_mapping=_option_side_mapping(option_types),
        numeric_cell_count=numeric_count,
        unavailable_cell_count=unavailable_count,
        duplicate_row_count=0,
        blocked_reasons=blocked_reasons,
        warnings=warnings,
        limitations=(
            [] if not blocked_reasons else ["Conversion is blocked until mapping is valid."]
        ),
    )


def combine_mapping_validations(
    mappings: list[QuikStrikeMatrixMappingValidation],
) -> QuikStrikeMatrixMappingValidation:
    """Aggregate per-view mapping validations into report-level status."""

    if not mappings:
        return QuikStrikeMatrixMappingValidation(
            status=QuikStrikeMatrixMappingStatus.BLOCKED,
            table_present=False,
            strike_rows_found=0,
            expiration_columns_found=0,
            option_side_mapping="unknown",
            numeric_cell_count=0,
            unavailable_cell_count=0,
            duplicate_row_count=0,
            blocked_reasons=["No requested matrix views were supplied."],
        )

    blocked_reasons = _dedupe(
        [reason for mapping in mappings for reason in mapping.blocked_reasons]
    )
    status = (
        QuikStrikeMatrixMappingStatus.BLOCKED
        if all(mapping.status == QuikStrikeMatrixMappingStatus.BLOCKED for mapping in mappings)
        else QuikStrikeMatrixMappingStatus.PARTIAL
        if blocked_reasons
        else QuikStrikeMatrixMappingStatus.VALID
    )
    option_types = {mapping.option_side_mapping for mapping in mappings}
    return QuikStrikeMatrixMappingValidation(
        status=status,
        table_present=any(mapping.table_present for mapping in mappings),
        strike_rows_found=sum(mapping.strike_rows_found for mapping in mappings),
        expiration_columns_found=sum(mapping.expiration_columns_found for mapping in mappings),
        option_side_mapping="/".join(sorted(option_types)),
        numeric_cell_count=sum(mapping.numeric_cell_count for mapping in mappings),
        unavailable_cell_count=sum(mapping.unavailable_cell_count for mapping in mappings),
        duplicate_row_count=sum(mapping.duplicate_row_count for mapping in mappings),
        blocked_reasons=blocked_reasons,
        warnings=_dedupe([warning for mapping in mappings for warning in mapping.warnings]),
        limitations=_dedupe(
            [limitation for mapping in mappings for limitation in mapping.limitations]
        ),
    )


def _normalized_row(
    *,
    extraction_id: str,
    capture_timestamp: datetime,
    metadata: QuikStrikeMatrixMetadata,
    snapshot: QuikStrikeMatrixTableSnapshot,
    cell: QuikStrikeMatrixBodyCell,
    warnings: list[str],
    limitations: list[str],
) -> QuikStrikeMatrixNormalizedRow:
    value_type = value_type_for_matrix_view(snapshot.view_type)
    option_type_label = cell.option_type.value if cell.option_type else "unknown"
    expiration_label = _safe_text(cell.expiration or "unknown_expiration")
    strike_label = _safe_number(cell.strike) if cell.strike is not None else "unknown_strike"
    return QuikStrikeMatrixNormalizedRow(
        row_id=(
            f"{extraction_id}_{snapshot.view_type.value}_{expiration_label}_"
            f"{strike_label}_{option_type_label}"
        ),
        extraction_id=extraction_id,
        capture_timestamp=metadata.capture_timestamp or capture_timestamp,
        product=metadata.product,
        option_product_code=metadata.option_product_code,
        futures_symbol=cell.futures_symbol or metadata.futures_symbol,
        source_menu=metadata.source_menu,
        view_type=snapshot.view_type,
        strike=cell.strike,
        expiration=cell.expiration,
        dte=cell.dte,
        future_reference_price=cell.future_reference_price,
        option_type=cell.option_type,
        value=cell.numeric_value,
        value_type=value_type,
        cell_state=cell.cell_state,
        table_row_label=cell.row_label,
        table_column_label=cell.column_label,
        extraction_warnings=_dedupe([*metadata.warnings, *snapshot.warnings, *warnings]),
        extraction_limitations=_dedupe(
            [
                LOCAL_ONLY_LIMITATION,
                SANITIZED_INPUT_LIMITATION,
                *metadata.limitations,
                *snapshot.limitations,
                *limitations,
            ]
        ),
    )


def _extraction_status(
    rows: list[QuikStrikeMatrixNormalizedRow],
    missing_views: list[QuikStrikeMatrixViewType],
    partial_views: list[QuikStrikeMatrixViewType],
    mapping: QuikStrikeMatrixMappingValidation,
) -> QuikStrikeMatrixExtractionStatus:
    if not rows or mapping.status == QuikStrikeMatrixMappingStatus.BLOCKED:
        return QuikStrikeMatrixExtractionStatus.BLOCKED
    if missing_views or partial_views or mapping.status == QuikStrikeMatrixMappingStatus.PARTIAL:
        return QuikStrikeMatrixExtractionStatus.PARTIAL
    return QuikStrikeMatrixExtractionStatus.COMPLETED


def _rows_missing_conversion_keys(rows: list[QuikStrikeMatrixNormalizedRow]) -> bool:
    return any(
        row.strike is None
        or row.expiration is None
        or row.option_type is None
        or row.value is None
        for row in rows
    )


def _option_side_mapping(option_types: set[object]) -> str:
    values = sorted(getattr(option_type, "value", str(option_type)) for option_type in option_types)
    if values == ["call", "put"]:
        return "call_put"
    if values:
        return "_".join(values)
    return "unknown"


def _duplicate_count(rows: list[QuikStrikeMatrixNormalizedRow]) -> int:
    seen: set[tuple[str, str | None, float | None, str | None, str]] = set()
    duplicates = 0
    for row in rows:
        key = (
            row.view_type.value,
            row.expiration,
            row.strike,
            row.option_type.value if row.option_type else None,
            row.value_type.value,
        )
        if key in seen:
            duplicates += 1
        seen.add(key)
    return duplicates


def _default_extraction_id(timestamp: datetime) -> str:
    return f"quikstrike_matrix_{timestamp.strftime('%Y%m%d_%H%M%S')}"


def _safe_number(value: float | None) -> str:
    if value is None:
        return "unknown"
    return f"{value:.8f}".rstrip("0").rstrip(".").replace(".", "_").replace("-", "m")


def _safe_text(value: str) -> str:
    return "".join(character if character.isalnum() else "_" for character in value).strip("_")


def _dedupe(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        if value and value not in deduped:
            deduped.append(value)
    return deduped
