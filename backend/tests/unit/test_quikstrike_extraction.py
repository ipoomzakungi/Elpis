from datetime import UTC, datetime

from src.models.quikstrike import (
    QuikStrikeExtractionRequest,
    QuikStrikeExtractionStatus,
    QuikStrikeSeriesType,
    QuikStrikeStrikeMappingConfidence,
    QuikStrikeViewType,
)
from src.quikstrike.dom_metadata import parse_dom_metadata
from src.quikstrike.extraction import (
    build_extraction_from_request,
    validate_strike_mapping,
)
from src.quikstrike.highcharts_reader import parse_highcharts_chart


def _chart_fixture(
    *,
    view: QuikStrikeViewType,
    include_call: bool = True,
    include_cross_check: bool = True,
    conflicting_label: bool = False,
    strike_id: str = "strike-4700",
    title_code: str = "OG3K6",
) -> dict:
    put_point = {"x": 4700, "y": 120}
    call_point = {"x": 4700, "y": 95}
    if include_cross_check:
        label = "4800" if conflicting_label else "4700"
        put_point.update(
            {
                "name": label,
                "category": label,
                "Tag": {"StrikeId": strike_id},
            }
        )
        call_point.update(
            {
                "name": label,
                "category": label,
                "Tag": {"StrikeId": strike_id},
            }
        )
    series = [
        {"name": "Put", "data": [put_point]},
        {"name": "Vol Settle", "data": [{"x": 4700, "y": 26.7}]},
        {"name": "Ranges", "data": [{"x": 4650, "x2": 4750, "y": 0, "Tag": {"Range": "1SD"}}]},
    ]
    if include_call:
        series.insert(1, {"name": "Call", "data": [call_point]})
    return {"title": {"text": f"{title_code} {view.value}"}, "series": series}


def _request_for_views(
    views: list[QuikStrikeViewType],
    *,
    include_call: bool = True,
    include_cross_check: bool = True,
) -> QuikStrikeExtractionRequest:
    dom_metadata_by_view = {}
    highcharts_by_view = {}
    for view in views:
        dom_metadata_by_view[view] = parse_dom_metadata(
            f"Gold (OG|GC) OG3K6 (2.59 DTE) vs 4722.6 - {view.value}",
            selector_text="Metals Precious Metals Gold (OG|GC) OG3K6 15 May 2026",
            selected_view_type=view,
        )
        highcharts_by_view[view] = parse_highcharts_chart(
            _chart_fixture(
                view=view,
                include_call=include_call,
                include_cross_check=include_cross_check,
            ),
            view,
        )
    return QuikStrikeExtractionRequest(
        requested_views=views,
        dom_metadata_by_view=dom_metadata_by_view,
        highcharts_by_view=highcharts_by_view,
        research_only_acknowledged=True,
    )


def test_build_extraction_from_request_normalizes_all_supported_views():
    views = [
        QuikStrikeViewType.INTRADAY_VOLUME,
        QuikStrikeViewType.EOD_VOLUME,
        QuikStrikeViewType.OPEN_INTEREST,
        QuikStrikeViewType.OI_CHANGE,
        QuikStrikeViewType.CHURN,
    ]
    bundle = build_extraction_from_request(
        _request_for_views(views),
        extraction_id="quikstrike_fixture",
        capture_timestamp=datetime(2026, 5, 13, tzinfo=UTC),
    )

    assert bundle.result.status == QuikStrikeExtractionStatus.COMPLETED
    assert bundle.result.conversion_eligible is True
    assert bundle.result.row_count == 10
    assert bundle.result.put_row_count == 5
    assert bundle.result.call_row_count == 5
    assert {row.value_type for row in bundle.rows} == {view.value for view in views}
    assert all(row.product == "Gold" for row in bundle.rows)
    assert all(row.strike == 4700 for row in bundle.rows)
    assert all(row.expiration_code == "OG3K6" for row in bundle.rows)
    assert all(row.vol_settle == 26.7 for row in bundle.rows)
    assert all(row.range_label == "1SD" for row in bundle.rows)


def test_extraction_marks_partial_when_put_call_separation_is_incomplete():
    bundle = build_extraction_from_request(
        _request_for_views([QuikStrikeViewType.OPEN_INTEREST], include_call=False),
        extraction_id="quikstrike_put_only",
        capture_timestamp=datetime(2026, 5, 13, tzinfo=UTC),
    )

    assert bundle.result.status == QuikStrikeExtractionStatus.PARTIAL
    assert bundle.result.conversion_eligible is False
    assert bundle.result.partial_views == [QuikStrikeViewType.OPEN_INTEREST]
    assert "both Put and Call" in bundle.result.warnings[0]


def test_extraction_allows_conversion_for_plausible_x_only_strikes():
    bundle = build_extraction_from_request(
        _request_for_views(
            [QuikStrikeViewType.OPEN_INTEREST],
            include_cross_check=False,
        ),
        extraction_id="quikstrike_x_only",
        capture_timestamp=datetime(2026, 5, 13, tzinfo=UTC),
    )

    assert bundle.result.status == QuikStrikeExtractionStatus.PARTIAL
    assert bundle.result.strike_mapping.confidence == QuikStrikeStrikeMappingConfidence.PARTIAL
    assert bundle.result.conversion_eligible is True


def test_extraction_blocks_when_requested_view_has_no_put_call_rows():
    snapshot = parse_highcharts_chart(
        {"series": [{"name": "Ranges", "data": [{"x": 4650, "x2": 4750, "y": 0}]}]},
        QuikStrikeViewType.OPEN_INTEREST,
    )
    metadata = parse_dom_metadata(
        "Gold (OG|GC) OG3K6 (2.59 DTE) vs 4722.6 - Open Interest",
        selector_text="OG3K6 15 May 2026",
        selected_view_type=QuikStrikeViewType.OPEN_INTEREST,
    )
    request = QuikStrikeExtractionRequest(
        requested_views=[QuikStrikeViewType.OPEN_INTEREST],
        dom_metadata_by_view={QuikStrikeViewType.OPEN_INTEREST: metadata},
        highcharts_by_view={QuikStrikeViewType.OPEN_INTEREST: snapshot},
        research_only_acknowledged=True,
    )

    bundle = build_extraction_from_request(
        request,
        extraction_id="quikstrike_blocked",
        capture_timestamp=datetime(2026, 5, 13, tzinfo=UTC),
    )

    assert bundle.result.status == QuikStrikeExtractionStatus.BLOCKED
    assert bundle.result.missing_views == [QuikStrikeViewType.OPEN_INTEREST]
    assert bundle.result.strike_mapping.confidence == QuikStrikeStrikeMappingConfidence.UNKNOWN


def test_validate_strike_mapping_confidence_states():
    high = validate_strike_mapping(
        parse_highcharts_chart(
            _chart_fixture(view=QuikStrikeViewType.OPEN_INTEREST),
            QuikStrikeViewType.OPEN_INTEREST,
        )
    )
    partial = validate_strike_mapping(
        parse_highcharts_chart(
            _chart_fixture(
                view=QuikStrikeViewType.OPEN_INTEREST,
                include_cross_check=False,
            ),
            QuikStrikeViewType.OPEN_INTEREST,
        )
    )
    conflict = validate_strike_mapping(
        parse_highcharts_chart(
            _chart_fixture(
                view=QuikStrikeViewType.OPEN_INTEREST,
                conflicting_label=True,
            ),
            QuikStrikeViewType.OPEN_INTEREST,
        )
    )

    assert high.confidence == QuikStrikeStrikeMappingConfidence.HIGH
    assert high.matched_point_count == 2
    assert partial.confidence == QuikStrikeStrikeMappingConfidence.PARTIAL
    assert partial.unmatched_point_count == 2
    assert conflict.confidence == QuikStrikeStrikeMappingConfidence.CONFLICT
    assert conflict.conflict_count == 2


def test_real_like_strike_id_is_preserved_without_mapping_conflict():
    view = QuikStrikeViewType.INTRADAY_VOLUME
    request = QuikStrikeExtractionRequest(
        requested_views=[view],
        dom_metadata_by_view={
            view: parse_dom_metadata(
                "Gold (OG|GC) (1.4 DTE) vs 4710.9 - Intraday Volume",
                selected_view_type=view,
            )
        },
        highcharts_by_view={
            view: parse_highcharts_chart(
                _chart_fixture(view=view, strike_id="7240183", title_code="G2RK6"),
                view,
            )
        },
        research_only_acknowledged=True,
    )

    bundle = build_extraction_from_request(
        request,
        extraction_id="quikstrike_real_like",
        capture_timestamp=datetime(2026, 5, 13, tzinfo=UTC),
    )

    assert bundle.result.strike_mapping.confidence == QuikStrikeStrikeMappingConfidence.HIGH
    assert bundle.result.strike_mapping.conflict_count == 0
    assert {row.strike_id for row in bundle.rows} == {"7240183"}
    assert all(row.strike == 4700 for row in bundle.rows)
    assert all(row.expiration is None for row in bundle.rows)
    assert all(row.expiration_code == "G2RK6" for row in bundle.rows)
    assert any(
        "internal QuikStrike metadata" in warning
        for warning in bundle.result.strike_mapping.warnings
    )


def test_validate_strike_mapping_ignores_context_series_for_mapping():
    snapshot = parse_highcharts_chart(
        {"series": [{"name": "Vol Settle", "data": [{"x": 4700, "y": 26.7}]}]},
        QuikStrikeViewType.OPEN_INTEREST,
    )

    mapping = validate_strike_mapping(snapshot)

    assert mapping.confidence == QuikStrikeStrikeMappingConfidence.UNKNOWN
    assert mapping.method == "blocked_no_put_call_points"
    assert not any(series.series_type == QuikStrikeSeriesType.PUT for series in snapshot.series)
