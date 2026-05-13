from src.models.quikstrike_matrix import (
    QuikStrikeMatrixCellState,
    QuikStrikeMatrixOptionType,
    QuikStrikeMatrixTableSnapshot,
    QuikStrikeMatrixViewType,
)
from src.quikstrike_matrix.table_reader import (
    parse_matrix_table,
    parse_numeric_cell,
    parse_strike,
)


def test_oi_matrix_table_parser_extracts_strikes_expirations_and_sides():
    parsed = parse_matrix_table(_snapshot(QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX))

    available_cells = [
        cell for cell in parsed.body_cells if cell.cell_state == QuikStrikeMatrixCellState.AVAILABLE
    ]
    assert len(available_cells) == 7
    assert {cell.strike for cell in parsed.body_cells} == {4700, 4750}
    assert {cell.expiration for cell in parsed.body_cells} == {"G2RK6", "G2RM6"}
    assert {cell.option_type for cell in parsed.body_cells} == {
        QuikStrikeMatrixOptionType.CALL,
        QuikStrikeMatrixOptionType.PUT,
    }
    assert parsed.body_cells[0].dte == 2
    assert parsed.body_cells[0].futures_symbol == "GC"


def test_oi_change_matrix_parser_preserves_negative_and_parenthesized_values():
    parsed = parse_matrix_table(
        _snapshot(
            QuikStrikeMatrixViewType.OI_CHANGE_MATRIX,
            first_value="-25",
            second_value="(12)",
        )
    )

    values = [cell.numeric_value for cell in parsed.body_cells[:2]]
    assert values == [-25, -12]


def test_volume_matrix_parser_distinguishes_blank_from_zero():
    parsed = parse_matrix_table(
        _snapshot(
            QuikStrikeMatrixViewType.VOLUME_MATRIX,
            first_value="0",
            second_value="-",
        )
    )

    assert parsed.body_cells[0].numeric_value == 0
    assert parsed.body_cells[0].cell_state == QuikStrikeMatrixCellState.AVAILABLE
    assert parsed.body_cells[1].numeric_value is None
    assert parsed.body_cells[1].cell_state == QuikStrikeMatrixCellState.UNAVAILABLE


def test_header_rowspans_preserve_expiration_and_call_put_columns():
    parsed = parse_matrix_table(
        QuikStrikeMatrixTableSnapshot(
            view_type=QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX,
            html_table=(
                "<table><thead>"
                "<tr><th rowspan='2'>Strike</th>"
                "<th colspan='2'>G2RK6 GC 2 DTE 4722.6</th>"
                "<th colspan='2'>G2RM6 GC 30 DTE 4740.5</th></tr>"
                "<tr><th>Call</th><th>Put</th><th>Call</th><th>Put</th></tr>"
                "</thead><tbody>"
                "<tr><th>4700</th><td>120</td><td>95</td><td>10</td><td>11</td></tr>"
                "</tbody></table>"
            ),
        )
    )

    extracted = [
        (cell.expiration, cell.option_type, cell.numeric_value)
        for cell in parsed.body_cells
    ]
    assert extracted == [
        ("G2RK6", QuikStrikeMatrixOptionType.CALL, 120),
        ("G2RK6", QuikStrikeMatrixOptionType.PUT, 95),
        ("G2RM6", QuikStrikeMatrixOptionType.CALL, 10),
        ("G2RM6", QuikStrikeMatrixOptionType.PUT, 11),
    ]


def test_non_strike_labels_are_excluded():
    parsed = parse_matrix_table(
        QuikStrikeMatrixTableSnapshot(
            view_type=QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX,
            html_table=(
                "<table><tr><th>Strike</th><th>G2RK6 Call</th></tr>"
                "<tr><th>Total</th><td>999</td></tr>"
                "<tr><th>4700</th><td>120</td></tr></table>"
            ),
        )
    )

    assert {cell.strike for cell in parsed.body_cells} == {4700}


def test_parse_numeric_cell_variants():
    assert parse_numeric_cell("1,234")[0] == 1234
    assert parse_numeric_cell("+12")[0] == 12
    assert parse_numeric_cell("(12)")[0] == -12
    assert parse_numeric_cell("")[1] == QuikStrikeMatrixCellState.BLANK
    assert parse_numeric_cell("n/a")[1] == QuikStrikeMatrixCellState.UNAVAILABLE
    assert parse_numeric_cell("abc")[1] == QuikStrikeMatrixCellState.INVALID


def test_parse_strike_plausibility():
    assert parse_strike("4,700") == 4700
    assert parse_strike("Total") is None
    assert parse_strike("10") is None


def _snapshot(
    view_type: QuikStrikeMatrixViewType,
    *,
    first_value: str = "120",
    second_value: str = "95",
) -> QuikStrikeMatrixTableSnapshot:
    return QuikStrikeMatrixTableSnapshot(
        view_type=view_type,
        html_table=(
            "<table><thead>"
            "<tr><th>Strike</th><th colspan='2'>G2RK6 GC 2 DTE 4722.6</th>"
            "<th colspan='2'>G2RM6 GC 30 DTE 4740.5</th></tr>"
            "<tr><th></th><th>Call</th><th>Put</th><th>Call</th><th>Put</th></tr>"
            "</thead><tbody>"
            f"<tr><th>4700</th><td>{first_value}</td><td>{second_value}</td><td>10</td><td>11</td></tr>"
            "<tr><th>4750</th><td></td><td>33</td><td>0</td><td>44</td></tr>"
            "</tbody></table>"
        ),
    )
