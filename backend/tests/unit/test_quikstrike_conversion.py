from datetime import UTC, datetime

from src.models.quikstrike import (
    QuikStrikeConversionStatus,
    QuikStrikeExtractionRequest,
    QuikStrikeExtractionStatus,
    QuikStrikeViewType,
)
from src.quikstrike.conversion import convert_to_xau_vol_oi_rows
from src.quikstrike.dom_metadata import parse_dom_metadata
from src.quikstrike.extraction import build_extraction_from_request
from src.quikstrike.highcharts_reader import parse_highcharts_chart


def _chart_fixture(view: QuikStrikeViewType) -> dict:
    value_by_view = {
        QuikStrikeViewType.INTRADAY_VOLUME: (10, 12),
        QuikStrikeViewType.EOD_VOLUME: (15, 18),
        QuikStrikeViewType.OPEN_INTEREST: (120, 95),
        QuikStrikeViewType.OI_CHANGE: (5, -2),
        QuikStrikeViewType.CHURN: (0.25, 0.31),
    }
    put_value, call_value = value_by_view[view]
    return {
        "title": {"text": "G2RK6 Intraday Volume"},
        "series": [
            {
                "name": "Put",
                "data": [
                    {
                        "x": 4700,
                        "y": put_value,
                        "name": "4700",
                        "category": "4700",
                        "Tag": {"StrikeId": "7240183"},
                    }
                ],
            },
            {
                "name": "Call",
                "data": [
                    {
                        "x": 4700,
                        "y": call_value,
                        "name": "4700",
                        "category": "4700",
                        "Tag": {"StrikeId": "7240184"},
                    }
                ],
            },
            {"name": "Vol Settle", "data": [{"x": 4700, "y": 26.7}]},
        ]
    }


def _completed_extraction(*, code_only_expiration: bool = False) -> tuple:
    views = [
        QuikStrikeViewType.INTRADAY_VOLUME,
        QuikStrikeViewType.EOD_VOLUME,
        QuikStrikeViewType.OPEN_INTEREST,
        QuikStrikeViewType.OI_CHANGE,
        QuikStrikeViewType.CHURN,
    ]
    request = QuikStrikeExtractionRequest(
        requested_views=views,
        dom_metadata_by_view={
            view: (
                parse_dom_metadata(
                    f"Gold (OG|GC) G2RK6 (1.4 DTE) vs 4710.9 - {view.value}",
                    selected_view_type=view,
                )
                if code_only_expiration
                else parse_dom_metadata(
                    f"Gold (OG|GC) OG3K6 (2.59 DTE) vs 4722.6 - {view.value}",
                    selector_text="OG3K6 15 May 2026",
                    selected_view_type=view,
                )
            )
            for view in views
        },
        highcharts_by_view={
            view: parse_highcharts_chart(_chart_fixture(view), view) for view in views
        },
        research_only_acknowledged=True,
    )
    bundle = build_extraction_from_request(
        request,
        extraction_id="quikstrike_conversion",
        capture_timestamp=datetime(2026, 5, 13, tzinfo=UTC),
    )
    return bundle.result, bundle.rows


def test_convert_to_xau_vol_oi_rows_aggregates_supported_views():
    extraction_result, rows = _completed_extraction()

    conversion = convert_to_xau_vol_oi_rows(
        extraction_result=extraction_result,
        rows=rows,
        conversion_id="quikstrike_conversion_xau",
        created_at=datetime(2026, 5, 13, tzinfo=UTC),
    )

    assert conversion.result.status == QuikStrikeConversionStatus.COMPLETED
    assert conversion.result.row_count == 2
    put_row = next(row for row in conversion.rows if row.option_type == "put")
    call_row = next(row for row in conversion.rows if row.option_type == "call")
    assert put_row.open_interest == 120
    assert put_row.oi_change == 5
    assert put_row.intraday_volume == 10
    assert put_row.eod_volume == 15
    assert put_row.volume == 10
    assert put_row.churn == 0.25
    assert put_row.implied_volatility == 26.7
    assert put_row.underlying_futures_price == 4722.6
    assert put_row.expiration_code == "OG3K6"
    assert call_row.open_interest == 95
    assert call_row.oi_change == -2
    assert conversion.result.output_artifacts[0].path.startswith(
        "data/processed/quikstrike/"
    )


def test_convert_to_xau_vol_oi_blocks_partial_or_uncertain_extractions():
    extraction_result, rows = _completed_extraction()
    blocked_result = extraction_result.model_copy(
        update={
            "status": QuikStrikeExtractionStatus.PARTIAL,
            "conversion_eligible": False,
        }
    )

    conversion = convert_to_xau_vol_oi_rows(
        extraction_result=blocked_result,
        rows=rows,
        conversion_id="quikstrike_blocked_xau",
    )

    assert conversion.result.status == QuikStrikeConversionStatus.BLOCKED
    assert conversion.rows == []
    assert any(
        "not marked conversion eligible" in reason
        for reason in conversion.result.blocked_reasons
    )


def test_convert_to_xau_vol_oi_succeeds_with_expiration_code_without_calendar_date():
    extraction_result, rows = _completed_extraction(code_only_expiration=True)

    conversion = convert_to_xau_vol_oi_rows(
        extraction_result=extraction_result,
        rows=rows,
        conversion_id="quikstrike_code_only_xau",
    )

    assert conversion.result.status == QuikStrikeConversionStatus.COMPLETED
    assert conversion.rows
    assert all(row.expiry is None for row in conversion.rows)
    assert {row.expiration_code for row in conversion.rows} == {"G2RK6"}
    assert "expiration code parsed, calendar expiry date unavailable" in (
        conversion.result.warnings
    )


def test_convert_to_xau_vol_oi_blocks_missing_required_expiration_reference():
    extraction_result, rows = _completed_extraction()
    rows[0] = rows[0].model_copy(update={"expiration": None, "expiration_code": None})

    conversion = convert_to_xau_vol_oi_rows(
        extraction_result=extraction_result,
        rows=rows,
        conversion_id="quikstrike_missing_context",
    )

    assert conversion.result.status == QuikStrikeConversionStatus.BLOCKED
    assert any(
        "expiration reference" in reason for reason in conversion.result.blocked_reasons
    )
