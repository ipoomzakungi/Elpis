from datetime import UTC, datetime

from src.models.quikstrike_matrix import (
    QuikStrikeMatrixConversionStatus,
    QuikStrikeMatrixExtractionRequest,
    QuikStrikeMatrixExtractionStatus,
    QuikStrikeMatrixMappingStatus,
    QuikStrikeMatrixMetadata,
    QuikStrikeMatrixTableSnapshot,
    QuikStrikeMatrixViewType,
)
from src.quikstrike_matrix.conversion import convert_to_xau_vol_oi_rows
from src.quikstrike_matrix.extraction import build_extraction_from_request


def test_matrix_rows_convert_to_xau_vol_oi_fields():
    extraction = build_extraction_from_request(
        _request(),
        extraction_id="matrix_conversion",
        capture_timestamp=datetime(2026, 5, 13, tzinfo=UTC),
    )

    conversion = convert_to_xau_vol_oi_rows(
        extraction_result=extraction.result,
        rows=extraction.rows,
        conversion_id="matrix_conversion_xau",
        created_at=datetime(2026, 5, 13, tzinfo=UTC),
    )

    assert conversion.result.status == QuikStrikeMatrixConversionStatus.COMPLETED
    assert conversion.result.row_count == 2
    first = conversion.rows[0]
    assert first.open_interest == 120
    assert first.oi_change == -12
    assert first.volume == 33
    assert first.expiry == "G2RK6"
    assert first.strike == 4700
    assert first.source == "quikstrike_matrix_local"


def test_conversion_blocks_missing_expiration_mapping():
    extraction = build_extraction_from_request(
        _request(
            {
                QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX: QuikStrikeMatrixTableSnapshot(
                    view_type=QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX,
                    html_table=(
                        "<table><tr><th>Strike</th><th>Call</th></tr>"
                        "<tr><th>4700</th><td>120</td></tr></table>"
                    ),
                )
            }
        ),
        extraction_id="matrix_missing_expiration_conversion",
        capture_timestamp=datetime(2026, 5, 13, tzinfo=UTC),
    )

    conversion = convert_to_xau_vol_oi_rows(
        extraction_result=extraction.result,
        rows=extraction.rows,
        conversion_id="matrix_missing_expiration_conversion_xau",
        created_at=datetime(2026, 5, 13, tzinfo=UTC),
    )

    assert extraction.result.status == QuikStrikeMatrixExtractionStatus.BLOCKED
    assert extraction.result.mapping.status == QuikStrikeMatrixMappingStatus.BLOCKED
    assert conversion.result.status == QuikStrikeMatrixConversionStatus.BLOCKED
    assert "Matrix mapping is blocked." in conversion.result.blocked_reasons


def test_conversion_blocks_unavailable_only_cells():
    extraction = build_extraction_from_request(
        _request(
                {
                    QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX: _snapshot(
                        QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX,
                        value="--",
                        extra_value="--",
                    )
                }
            ),
        extraction_id="matrix_unavailable_only_conversion",
        capture_timestamp=datetime(2026, 5, 13, tzinfo=UTC),
    )

    conversion = convert_to_xau_vol_oi_rows(
        extraction_result=extraction.result,
        rows=extraction.rows,
        conversion_id="matrix_unavailable_only_conversion_xau",
        created_at=datetime(2026, 5, 13, tzinfo=UTC),
    )

    assert conversion.result.status == QuikStrikeMatrixConversionStatus.BLOCKED
    assert "No available QuikStrike Matrix rows are available for conversion." in (
        conversion.result.blocked_reasons
    )


def test_conversion_preserves_unavailable_cell_warning_when_some_cells_are_missing():
    extraction = build_extraction_from_request(
        _request(
            {
                QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX: _snapshot(
                    QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX,
                    value="120",
                    extra_value="-",
                )
            }
        ),
        extraction_id="matrix_some_unavailable_conversion",
        capture_timestamp=datetime(2026, 5, 13, tzinfo=UTC),
    )

    conversion = convert_to_xau_vol_oi_rows(
        extraction_result=extraction.result,
        rows=extraction.rows,
        conversion_id="matrix_some_unavailable_conversion_xau",
        created_at=datetime(2026, 5, 13, tzinfo=UTC),
    )

    assert conversion.result.status == QuikStrikeMatrixConversionStatus.COMPLETED
    assert "Unavailable cells were omitted and not treated as zero." in (
        conversion.result.warnings
    )


def _request(
    snapshots: dict[QuikStrikeMatrixViewType, QuikStrikeMatrixTableSnapshot] | None = None,
) -> QuikStrikeMatrixExtractionRequest:
    snapshots = snapshots or {
        QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX: _snapshot(
            QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX,
            value="120",
        ),
        QuikStrikeMatrixViewType.OI_CHANGE_MATRIX: _snapshot(
            QuikStrikeMatrixViewType.OI_CHANGE_MATRIX,
            value="-12",
        ),
        QuikStrikeMatrixViewType.VOLUME_MATRIX: _snapshot(
            QuikStrikeMatrixViewType.VOLUME_MATRIX,
            value="33",
        ),
    }
    return QuikStrikeMatrixExtractionRequest(
        requested_views=list(snapshots),
        metadata_by_view={view: _metadata(view) for view in snapshots},
        tables_by_view=snapshots,
        research_only_acknowledged=True,
    )


def _metadata(view: QuikStrikeMatrixViewType) -> QuikStrikeMatrixMetadata:
    return QuikStrikeMatrixMetadata(
        capture_timestamp=datetime(2026, 5, 13, tzinfo=UTC),
        product="Gold (OG|GC)",
        option_product_code="OG|GC",
        futures_symbol="GC",
        source_menu="OPEN INTEREST Matrix",
        selected_view_type=view,
        selected_view_label=view.value,
        raw_visible_text="Gold (OG|GC) OPEN INTEREST Matrix",
    )


def _snapshot(
    view_type: QuikStrikeMatrixViewType,
    *,
    value: str,
    extra_value: str = "11",
) -> QuikStrikeMatrixTableSnapshot:
    return QuikStrikeMatrixTableSnapshot(
        view_type=view_type,
        html_table=(
            "<table><thead><tr><th>Strike</th><th colspan='2'>G2RK6 GC 2 DTE 4722.6</th></tr>"
            "<tr><th></th><th>Call</th><th>Put</th></tr></thead>"
            f"<tbody><tr><th>4700</th><td>{value}</td><td>{extra_value}</td></tr></tbody></table>"
        ),
    )
