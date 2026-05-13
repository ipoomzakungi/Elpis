from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.models.quikstrike_matrix import (
    QuikStrikeMatrixArtifact,
    QuikStrikeMatrixArtifactFormat,
    QuikStrikeMatrixArtifactType,
    QuikStrikeMatrixCellState,
    QuikStrikeMatrixExtractionRequest,
    QuikStrikeMatrixMetadata,
    QuikStrikeMatrixNormalizedRow,
    QuikStrikeMatrixOptionType,
    QuikStrikeMatrixTableSnapshot,
    QuikStrikeMatrixValueType,
    QuikStrikeMatrixViewType,
    validate_quikstrike_matrix_safe_id,
    value_type_for_matrix_view,
)


def _metadata() -> QuikStrikeMatrixMetadata:
    return QuikStrikeMatrixMetadata(
        capture_timestamp=datetime(2026, 5, 13, tzinfo=UTC),
        product="Gold",
        option_product_code="OG|GC",
        futures_symbol="GC",
        source_menu="OPEN INTEREST Matrix",
        selected_view_type=QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX,
        selected_view_label="OI Matrix",
        table_title="Gold OI Matrix",
        raw_visible_text="Gold (OG|GC) OPEN INTEREST OI Matrix",
    )


def _table() -> QuikStrikeMatrixTableSnapshot:
    return QuikStrikeMatrixTableSnapshot(
        view_type=QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX,
        html_table=(
            "<table><thead><tr><th>Strike</th><th colspan='2'>G2RK6 2 DTE</th></tr>"
            "<tr><th></th><th>Call</th><th>Put</th></tr></thead>"
            "<tbody><tr><th>4700</th><td>120</td><td>95</td></tr></tbody></table>"
        ),
    )


def test_quikstrike_matrix_enums_and_value_mapping():
    assert QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX == "open_interest_matrix"
    assert QuikStrikeMatrixViewType.OI_CHANGE_MATRIX == "oi_change_matrix"
    assert QuikStrikeMatrixViewType.VOLUME_MATRIX == "volume_matrix"
    assert value_type_for_matrix_view(
        QuikStrikeMatrixViewType.OI_CHANGE_MATRIX
    ) == QuikStrikeMatrixValueType.OI_CHANGE


def test_metadata_requires_gold_open_interest_context():
    metadata = _metadata()

    assert metadata.product == "Gold"
    assert metadata.option_product_code == "OG|GC"

    with pytest.raises(ValidationError, match="Gold"):
        QuikStrikeMatrixMetadata(
            product="Corn",
            option_product_code="OZC|ZC",
            source_menu="OPEN INTEREST Matrix",
            selected_view_type=QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX,
            raw_visible_text="Corn Open Interest",
        )

    with pytest.raises(ValidationError, match="OPEN INTEREST"):
        QuikStrikeMatrixMetadata(
            product="Gold",
            option_product_code="OG|GC",
            source_menu="QUIKOPTIONS VOL2VOL",
            selected_view_type=QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX,
            raw_visible_text="Gold (OG|GC)",
        )


def test_models_reject_extra_and_secret_like_fields():
    with pytest.raises(ValidationError):
        QuikStrikeMatrixMetadata(
            product="Gold",
            option_product_code="OG|GC",
            source_menu="OPEN INTEREST Matrix",
            selected_view_type=QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX,
            raw_visible_text="Gold (OG|GC)",
            unexpected="value",
        )

    with pytest.raises(ValidationError, match="secret/session fields"):
        QuikStrikeMatrixExtractionRequest(
            requested_views=[QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX],
            metadata_by_view={QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX: _metadata()},
            tables_by_view={QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX: _table()},
            research_only_acknowledged=True,
            headers={"Cookie": "not allowed"},
        )

    with pytest.raises(ValidationError, match="secret/session fields"):
        QuikStrikeMatrixMetadata(
            product="Gold",
            option_product_code="OG|GC",
            source_menu="OPEN INTEREST Matrix",
            selected_view_type=QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX,
            raw_visible_text="https://private.example.test/User/QuikStrikeView.aspx",
        )


def test_request_requires_ack_and_matching_views():
    request = QuikStrikeMatrixExtractionRequest(
        requested_views=[
            QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX,
            QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX,
        ],
        metadata_by_view={QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX: _metadata()},
        tables_by_view={QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX: _table()},
        research_only_acknowledged=True,
    )

    assert request.requested_views == [QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX]

    with pytest.raises(ValidationError, match="research_only_acknowledged"):
        QuikStrikeMatrixExtractionRequest(
            requested_views=[QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX],
            metadata_by_view={QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX: _metadata()},
            tables_by_view={QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX: _table()},
            research_only_acknowledged=False,
        )


def test_normalized_row_state_and_value_type_validation():
    row = QuikStrikeMatrixNormalizedRow(
        row_id="row_1",
        extraction_id="quikstrike_matrix_20260513",
        capture_timestamp=datetime(2026, 5, 13, tzinfo=UTC),
        product="Gold",
        option_product_code="OG|GC",
        source_menu="OPEN INTEREST Matrix",
        view_type=QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX,
        strike=4700,
        expiration="G2RK6",
        option_type=QuikStrikeMatrixOptionType.CALL,
        value=120,
        value_type=QuikStrikeMatrixValueType.OPEN_INTEREST,
        cell_state=QuikStrikeMatrixCellState.AVAILABLE,
        table_row_label="4700",
        table_column_label="G2RK6 Call",
    )

    assert row.value == 120

    with pytest.raises(ValidationError, match="value_type"):
        QuikStrikeMatrixNormalizedRow(
            **{**row.model_dump(), "value_type": QuikStrikeMatrixValueType.VOLUME}
        )

    with pytest.raises(ValidationError, match="must not include value"):
        QuikStrikeMatrixNormalizedRow(
            **{
                **row.model_dump(),
                "row_id": "row_2",
                "cell_state": QuikStrikeMatrixCellState.BLANK,
            }
        )


def test_artifact_path_and_safe_id_validation():
    artifact = QuikStrikeMatrixArtifact(
        artifact_type=QuikStrikeMatrixArtifactType.RAW_METADATA,
        path="data/raw/quikstrike_matrix/example.json",
        format=QuikStrikeMatrixArtifactFormat.JSON,
        created_at=datetime(2026, 5, 13, tzinfo=UTC),
    )

    assert artifact.path == "data/raw/quikstrike_matrix/example.json"
    assert validate_quikstrike_matrix_safe_id("quikstrike_matrix_20260513")

    for value in ("", "../outside", "nested/id", "bad id"):
        with pytest.raises(ValueError):
            validate_quikstrike_matrix_safe_id(value)

    with pytest.raises(ValidationError, match="ignored local roots"):
        QuikStrikeMatrixArtifact(
            artifact_type=QuikStrikeMatrixArtifactType.RAW_METADATA,
            path="data/raw/quikstrike/example.json",
            format=QuikStrikeMatrixArtifactFormat.JSON,
            created_at=datetime(2026, 5, 13, tzinfo=UTC),
        )
