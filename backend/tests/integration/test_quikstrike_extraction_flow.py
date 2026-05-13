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
from src.quikstrike.report_store import QuikStrikeReportStore


def test_quikstrike_synthetic_extraction_conversion_and_persistence_flow(tmp_path):
    request = _all_views_request()

    extraction = build_extraction_from_request(
        request,
        extraction_id="quikstrike_integration",
        capture_timestamp=datetime(2026, 5, 13, tzinfo=UTC),
    )
    conversion = convert_to_xau_vol_oi_rows(
        extraction_result=extraction.result,
        rows=extraction.rows,
        conversion_id="quikstrike_integration_xau",
        created_at=datetime(2026, 5, 13, tzinfo=UTC),
    )
    store = QuikStrikeReportStore(reports_dir=tmp_path / "data" / "reports")
    report = store.persist_report(
        extraction_result=extraction.result,
        normalized_rows=extraction.rows,
        conversion_result=conversion.result,
        conversion_rows=conversion.rows,
    )

    assert extraction.result.status == QuikStrikeExtractionStatus.COMPLETED
    assert extraction.result.row_count == 10
    assert conversion.result.status == QuikStrikeConversionStatus.COMPLETED
    assert conversion.result.row_count == 2
    assert report.extraction_id == "quikstrike_integration"
    assert store.list_reports().extractions[0].extraction_id == "quikstrike_integration"
    assert len(store.read_rows_response("quikstrike_integration").rows) == 10
    assert len(store.read_conversion_response("quikstrike_integration").rows) == 2

    response_text = report.model_dump_json().lower()
    forbidden_terms = [
        "cookie:",
        "set-cookie",
        "authorization:",
        "__viewstate",
        "__eventvalidation",
        "bearer ",
    ]
    for term in forbidden_terms:
        assert term not in response_text


def _all_views_request() -> QuikStrikeExtractionRequest:
    views = [
        QuikStrikeViewType.INTRADAY_VOLUME,
        QuikStrikeViewType.EOD_VOLUME,
        QuikStrikeViewType.OPEN_INTEREST,
        QuikStrikeViewType.OI_CHANGE,
        QuikStrikeViewType.CHURN,
    ]
    return QuikStrikeExtractionRequest(
        requested_views=views,
        dom_metadata_by_view={
            view: parse_dom_metadata(
                f"Gold (OG|GC) OG3K6 (2.59 DTE) vs 4722.6 - {view.value}",
                selector_text="Metals Precious Metals Gold (OG|GC) OG3K6 15 May 2026",
                selected_view_type=view,
            )
            for view in views
        },
        highcharts_by_view={
            view: parse_highcharts_chart(_chart_fixture(view), view) for view in views
        },
        run_label="integration",
        research_only_acknowledged=True,
    )


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
        "series": [
            {
                "name": "Put",
                "data": [
                    {
                        "x": 4700,
                        "y": put_value,
                        "name": "4700",
                        "category": "4700",
                        "Tag": {"StrikeId": "strike-4700"},
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
                        "Tag": {"StrikeId": "strike-4700"},
                    }
                ],
            },
            {"name": "Vol Settle", "data": [{"x": 4700, "y": 26.7}]},
            {
                "name": "Ranges",
                "data": [{"x": 4650, "x2": 4750, "y": 0, "Tag": {"Range": "1SD"}}],
            },
        ]
    }
