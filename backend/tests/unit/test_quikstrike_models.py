from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from src.models.quikstrike import (
    QuikStrikeConversionResult,
    QuikStrikeConversionStatus,
    QuikStrikeDomMetadata,
    QuikStrikeExtractionRequest,
    QuikStrikeExtractionResult,
    QuikStrikeExtractionStatus,
    QuikStrikeHighchartsSnapshot,
    QuikStrikeNormalizedRow,
    QuikStrikeOptionType,
    QuikStrikePoint,
    QuikStrikeSeriesSnapshot,
    QuikStrikeSeriesType,
    QuikStrikeStrikeMappingConfidence,
    QuikStrikeStrikeMappingValidation,
    QuikStrikeViewType,
    validate_quikstrike_safe_id,
    value_type_for_view,
)


def _dom_metadata() -> QuikStrikeDomMetadata:
    return QuikStrikeDomMetadata(
        product="Gold",
        option_product_code="OG|GC",
        futures_symbol="GC",
        expiration=date(2026, 5, 15),
        dte=2.59,
        future_reference_price=4722.6,
        selected_view_type=QuikStrikeViewType.OPEN_INTEREST,
        raw_header_text="Gold (OG|GC) OG3K6 (2.59 DTE) vs 4722.6 - Open Interest",
    )


def _highcharts_snapshot() -> QuikStrikeHighchartsSnapshot:
    return QuikStrikeHighchartsSnapshot(
        chart_title="OG3K6 Open Interest",
        view_type=QuikStrikeViewType.OPEN_INTEREST,
        series=[
            QuikStrikeSeriesSnapshot(
                series_name="Put",
                series_type=QuikStrikeSeriesType.PUT,
                point_count=1,
                points=[
                    QuikStrikePoint(
                        series_type=QuikStrikeSeriesType.PUT,
                        x=4700,
                        y=120,
                        strike_id="strike-4700",
                    )
                ],
            )
        ],
    )


def test_quikstrike_enums_and_value_type_mapping():
    assert QuikStrikeViewType.INTRADAY_VOLUME == "intraday_volume"
    assert QuikStrikeViewType.EOD_VOLUME == "eod_volume"
    assert QuikStrikeViewType.OPEN_INTEREST == "open_interest"
    assert QuikStrikeViewType.OI_CHANGE == "oi_change"
    assert QuikStrikeViewType.CHURN == "churn"
    assert QuikStrikeSeriesType.VOL_SETTLE == "vol_settle"
    assert value_type_for_view(QuikStrikeViewType.OI_CHANGE) == "oi_change"


def test_dom_metadata_is_strict_gold_vol2vol_metadata():
    metadata = _dom_metadata()

    assert metadata.product == "Gold"
    assert metadata.option_product_code == "OG|GC"
    assert metadata.futures_symbol == "GC"
    assert metadata.expiration == date(2026, 5, 15)

    with pytest.raises(ValidationError, match="Gold"):
        QuikStrikeDomMetadata(
            product="Corn",
            option_product_code="OZC|ZC",
            selected_view_type=QuikStrikeViewType.OPEN_INTEREST,
            raw_header_text="Corn (OZC|ZC) - Open Interest",
        )


def test_models_reject_extra_and_secret_like_fields():
    with pytest.raises(ValidationError):
        QuikStrikeDomMetadata(
            product="Gold",
            option_product_code="OG|GC",
            selected_view_type=QuikStrikeViewType.OPEN_INTEREST,
            raw_header_text="Gold (OG|GC) - Open Interest",
            unexpected="value",
        )

    with pytest.raises(ValidationError, match="secret/session fields"):
        QuikStrikeExtractionRequest(
            requested_views=[QuikStrikeViewType.OPEN_INTEREST],
            dom_metadata_by_view={QuikStrikeViewType.OPEN_INTEREST: _dom_metadata()},
            highcharts_by_view={QuikStrikeViewType.OPEN_INTEREST: _highcharts_snapshot()},
            research_only_acknowledged=True,
            headers={"Cookie": "not allowed"},
        )

    with pytest.raises(ValidationError, match="secret/session fields"):
        QuikStrikeDomMetadata(
            product="Gold",
            option_product_code="OG|GC",
            selected_view_type=QuikStrikeViewType.OPEN_INTEREST,
            raw_header_text="https://private.example.test/User/QuikStrikeView.aspx",
        )


def test_extraction_request_requires_ack_and_matching_views():
    request = QuikStrikeExtractionRequest(
        requested_views=[QuikStrikeViewType.OPEN_INTEREST, QuikStrikeViewType.OPEN_INTEREST],
        dom_metadata_by_view={QuikStrikeViewType.OPEN_INTEREST: _dom_metadata()},
        highcharts_by_view={QuikStrikeViewType.OPEN_INTEREST: _highcharts_snapshot()},
        research_only_acknowledged=True,
    )

    assert request.requested_views == [QuikStrikeViewType.OPEN_INTEREST]

    with pytest.raises(ValidationError, match="research_only_acknowledged"):
        QuikStrikeExtractionRequest(
            requested_views=[QuikStrikeViewType.OPEN_INTEREST],
            dom_metadata_by_view={QuikStrikeViewType.OPEN_INTEREST: _dom_metadata()},
            highcharts_by_view={QuikStrikeViewType.OPEN_INTEREST: _highcharts_snapshot()},
            research_only_acknowledged=False,
        )


def test_extraction_result_blocks_conversion_without_high_mapping():
    mapping = QuikStrikeStrikeMappingValidation(
        confidence=QuikStrikeStrikeMappingConfidence.PARTIAL,
        method="x_only",
        matched_point_count=1,
        unmatched_point_count=1,
        conflict_count=0,
    )

    with pytest.raises(ValidationError, match="conversion_eligible"):
        QuikStrikeExtractionResult(
            extraction_id="quikstrike_20260513",
            status=QuikStrikeExtractionStatus.PARTIAL,
            created_at=datetime(2026, 5, 13, tzinfo=UTC),
            row_count=2,
            put_row_count=1,
            call_row_count=1,
            strike_mapping=mapping,
            conversion_eligible=True,
        )


def test_normalized_row_value_type_must_match_selected_view():
    row = QuikStrikeNormalizedRow(
        row_id="row_1",
        extraction_id="quikstrike_20260513",
        capture_timestamp=datetime(2026, 5, 13, tzinfo=UTC),
        product="Gold",
        option_product_code="OG|GC",
        futures_symbol="GC",
        expiration=date(2026, 5, 15),
        dte=2.59,
        future_reference_price=4722.6,
        view_type=QuikStrikeViewType.OPEN_INTEREST,
        strike=4700,
        strike_id="strike_4700",
        option_type=QuikStrikeOptionType.PUT,
        value=120,
        value_type="open_interest",
        source_view="QUIKOPTIONS VOL2VOL",
        strike_mapping_confidence=QuikStrikeStrikeMappingConfidence.HIGH,
    )

    assert row.value_type == "open_interest"

    with pytest.raises(ValidationError, match="value_type"):
        QuikStrikeNormalizedRow(
            row_id="row_1",
            extraction_id="quikstrike_20260513",
            capture_timestamp=datetime(2026, 5, 13, tzinfo=UTC),
            product="Gold",
            option_product_code="OG|GC",
            futures_symbol="GC",
            view_type=QuikStrikeViewType.OPEN_INTEREST,
            strike=4700,
            option_type=QuikStrikeOptionType.PUT,
            value=120,
            value_type="intraday_volume",
            source_view="QUIKOPTIONS VOL2VOL",
            strike_mapping_confidence=QuikStrikeStrikeMappingConfidence.HIGH,
        )


def test_conversion_result_requires_blocked_reason_or_output_artifact():
    with pytest.raises(ValidationError, match="blocked conversion"):
        QuikStrikeConversionResult(
            conversion_id="conversion_1",
            extraction_id="quikstrike_20260513",
            status=QuikStrikeConversionStatus.BLOCKED,
            row_count=0,
        )

    with pytest.raises(ValidationError, match="completed conversion"):
        QuikStrikeConversionResult(
            conversion_id="conversion_1",
            extraction_id="quikstrike_20260513",
            status=QuikStrikeConversionStatus.COMPLETED,
            row_count=10,
        )


def test_validate_quikstrike_safe_id_rejects_unsafe_values():
    assert validate_quikstrike_safe_id("quikstrike_20260513") == "quikstrike_20260513"
    for value in ("", "../outside", "nested/id", "bad id"):
        with pytest.raises(ValueError):
            validate_quikstrike_safe_id(value)
