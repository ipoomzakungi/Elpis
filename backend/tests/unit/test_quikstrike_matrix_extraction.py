from datetime import UTC, datetime

from src.models.quikstrike_matrix import (
    QuikStrikeMatrixCellState,
    QuikStrikeMatrixExtractionRequest,
    QuikStrikeMatrixExtractionStatus,
    QuikStrikeMatrixMappingStatus,
    QuikStrikeMatrixMetadata,
    QuikStrikeMatrixOptionType,
    QuikStrikeMatrixTableSnapshot,
    QuikStrikeMatrixValueType,
    QuikStrikeMatrixViewType,
)
from src.quikstrike_matrix.extraction import build_extraction_from_request
from src.quikstrike_matrix.metadata import parse_matrix_metadata


def test_metadata_parser_extracts_gold_open_interest_context():
    metadata = parse_matrix_metadata(
        raw_visible_text="OPEN INTEREST Matrix Gold (OG|GC) OI Matrix GC 4722.6",
        view_type=QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX,
        capture_timestamp=datetime(2026, 5, 13, tzinfo=UTC),
    )

    assert metadata.product == "Gold"
    assert metadata.option_product_code == "OG|GC"
    assert metadata.futures_symbol == "GC"
    assert metadata.source_menu == "OPEN INTEREST Matrix"
    assert metadata.selected_view_label == "OI Matrix"


def test_normalized_row_builder_extracts_all_three_views():
    bundle = build_extraction_from_request(
        _request(),
        extraction_id="matrix_all_views",
        capture_timestamp=datetime(2026, 5, 13, tzinfo=UTC),
    )

    assert bundle.result.status == QuikStrikeMatrixExtractionStatus.COMPLETED
    assert bundle.result.mapping.status == QuikStrikeMatrixMappingStatus.VALID
    assert bundle.result.conversion_eligible is True
    assert len(bundle.rows) == 24
    assert {row.view_type for row in bundle.rows} == set(QuikStrikeMatrixViewType)
    assert {row.value_type for row in bundle.rows} == {
        QuikStrikeMatrixValueType.OPEN_INTEREST,
        QuikStrikeMatrixValueType.OI_CHANGE,
        QuikStrikeMatrixValueType.VOLUME,
    }


def test_table_presence_and_no_row_validation_blocks_conversion():
    bundle = build_extraction_from_request(
        _request(
            {
                QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX: _snapshot(
                    QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX,
                    rows="<tr><th>Total</th><td>999</td><td>888</td></tr>",
                )
            }
        ),
        extraction_id="matrix_no_rows",
        capture_timestamp=datetime(2026, 5, 13, tzinfo=UTC),
    )

    assert bundle.result.status == QuikStrikeMatrixExtractionStatus.BLOCKED
    assert bundle.result.conversion_eligible is False
    assert "Matrix table rows were not found." in bundle.result.mapping.blocked_reasons


def test_missing_strike_or_expiration_blocks_mapping():
    no_expiration = build_extraction_from_request(
        _request(
            {
                QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX: QuikStrikeMatrixTableSnapshot(
                    view_type=QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX,
                    html_table=(
                        "<table><tr><th>Strike</th><th>Call</th><th>Put</th></tr>"
                        "<tr><th>4700</th><td>120</td><td>95</td></tr></table>"
                    ),
                )
            }
        ),
        extraction_id="matrix_missing_expiration",
        capture_timestamp=datetime(2026, 5, 13, tzinfo=UTC),
    )

    assert no_expiration.result.mapping.status == QuikStrikeMatrixMappingStatus.BLOCKED
    assert "Expiration columns could not be determined." in (
        no_expiration.result.mapping.blocked_reasons
    )


def test_blank_dash_unavailable_and_explicit_zero_cells_are_preserved():
    bundle = build_extraction_from_request(
        _request(
            {
                QuikStrikeMatrixViewType.VOLUME_MATRIX: _snapshot(
                    QuikStrikeMatrixViewType.VOLUME_MATRIX,
                    value_1="0",
                    value_2="-",
                    value_3="",
                    value_4="n/a",
                )
            }
        ),
        extraction_id="matrix_unavailable_cells",
        capture_timestamp=datetime(2026, 5, 13, tzinfo=UTC),
    )

    zero_row = next(row for row in bundle.rows if row.table_column_label.endswith("Call"))
    unavailable_states = {row.cell_state for row in bundle.rows if row.value is None}
    assert zero_row.value == 0
    assert zero_row.cell_state == QuikStrikeMatrixCellState.AVAILABLE
    assert QuikStrikeMatrixCellState.BLANK in unavailable_states
    assert QuikStrikeMatrixCellState.UNAVAILABLE in unavailable_states
    assert "Unavailable cells were preserved and not treated as zero." in (
        bundle.result.mapping.warnings
    )


def test_signed_negative_parenthesized_and_comma_values_parse():
    bundle = build_extraction_from_request(
        _request(
            {
                QuikStrikeMatrixViewType.OI_CHANGE_MATRIX: _snapshot(
                    QuikStrikeMatrixViewType.OI_CHANGE_MATRIX,
                    value_1="-25",
                    value_2="(12)",
                    value_3="+1,234",
                    value_4="0",
                )
            }
        ),
        extraction_id="matrix_signed_values",
        capture_timestamp=datetime(2026, 5, 13, tzinfo=UTC),
    )

    values = [row.value for row in bundle.rows[:4]]
    assert values == [-25, -12, 1234, 0]


def test_duplicate_row_keys_are_reported_deterministically():
    bundle = build_extraction_from_request(
        _request(
            {
                QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX: _snapshot(
                    QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX,
                    rows=(
                        "<tr><th>4700</th><td>120</td><td>95</td><td>10</td><td>11</td></tr>"
                        "<tr><th>4700</th><td>121</td><td>96</td><td>12</td><td>13</td></tr>"
                    ),
                )
            }
        ),
        extraction_id="matrix_duplicate_rows",
        capture_timestamp=datetime(2026, 5, 13, tzinfo=UTC),
    )

    assert bundle.result.mapping.duplicate_row_count == 4
    assert "4 duplicate matrix row key(s) were detected." in bundle.result.mapping.warnings


def test_extraction_results_do_not_persist_secret_like_content():
    bundle = build_extraction_from_request(
        _request(),
        extraction_id="matrix_no_secret_content",
        capture_timestamp=datetime(2026, 5, 13, tzinfo=UTC),
    )
    payload = bundle.result.model_dump_json()

    assert "cookie=value" not in payload.lower()
    assert "__viewstate" not in payload.lower()
    assert "authorization:" not in payload.lower()
    assert all(
        row.option_type in {QuikStrikeMatrixOptionType.CALL, QuikStrikeMatrixOptionType.PUT}
        for row in bundle.rows
    )


def _request(
    snapshots: dict[QuikStrikeMatrixViewType, QuikStrikeMatrixTableSnapshot] | None = None,
) -> QuikStrikeMatrixExtractionRequest:
    snapshots = snapshots or {
        view: _snapshot(view)
        for view in (
            QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX,
            QuikStrikeMatrixViewType.OI_CHANGE_MATRIX,
            QuikStrikeMatrixViewType.VOLUME_MATRIX,
        )
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
    value_1: str = "120",
    value_2: str = "95",
    value_3: str = "10",
    value_4: str = "11",
    rows: str | None = None,
) -> QuikStrikeMatrixTableSnapshot:
    rows = rows or (
        f"<tr><th>4700</th><td>{value_1}</td><td>{value_2}</td><td>{value_3}</td><td>{value_4}</td></tr>"
        "<tr><th>4750</th><td>5</td><td>6</td><td>7</td><td>8</td></tr>"
    )
    return QuikStrikeMatrixTableSnapshot(
        view_type=view_type,
        html_table=(
            "<table><thead>"
            "<tr><th>Strike</th><th colspan='2'>G2RK6 GC 2 DTE 4722.6</th>"
            "<th colspan='2'>G2RM6 GC 30 DTE 4740.5</th></tr>"
            "<tr><th></th><th>Call</th><th>Put</th><th>Call</th><th>Put</th></tr>"
            "</thead><tbody>"
            f"{rows}"
            "</tbody></table>"
        ),
    )
