import pytest

from src.models.quikstrike import QuikStrikeSeriesType, QuikStrikeViewType
from src.quikstrike.highcharts_reader import (
    classify_series_name,
    parse_highcharts_chart,
    put_call_points,
    view_value_type,
)


def _highcharts_fixture() -> dict:
    return {
        "title": {"text": "OG3K6 Open Interest"},
        "series": [
            {
                "name": "Put",
                "data": [
                    {
                        "x": 4700,
                        "y": 120,
                        "name": "4700",
                        "category": "4700",
                        "options": {"Tag": {"StrikeId": "strike-4700"}},
                    }
                ],
            },
            {
                "name": "Call",
                "points": [
                    {
                        "x": 4700,
                        "y": 95,
                        "name": "4700",
                        "category": "4700",
                        "Tag": {"StrikeId": "strike-4700"},
                    }
                ],
            },
            {
                "name": "Vol Settle",
                "data": [{"x": 4700, "y": 26.7, "name": "4700"}],
            },
            {
                "name": "Ranges",
                "data": [
                    {
                        "x": 4650,
                        "x2": 4750,
                        "y": 0,
                        "Tag": {"Range": "1SD", "Sigma": "1"},
                    }
                ],
            },
        ],
    }


def test_parse_highcharts_chart_extracts_series_points_and_metadata():
    snapshot = parse_highcharts_chart(_highcharts_fixture(), QuikStrikeViewType.OPEN_INTEREST)

    assert snapshot.chart_title == "OG3K6 Open Interest"
    assert snapshot.view_type == QuikStrikeViewType.OPEN_INTEREST
    assert [series.series_type for series in snapshot.series] == [
        QuikStrikeSeriesType.PUT,
        QuikStrikeSeriesType.CALL,
        QuikStrikeSeriesType.VOL_SETTLE,
        QuikStrikeSeriesType.RANGES,
    ]
    put = snapshot.series[0].points[0]
    call = snapshot.series[1].points[0]
    range_point = snapshot.series[3].points[0]
    assert put.x == 4700
    assert put.y == 120
    assert put.strike_id == "strike-4700"
    assert "StrikeId" in put.metadata_keys
    assert call.strike_id == "strike-4700"
    assert range_point.x2 == 4750
    assert range_point.range_label == "1SD"
    assert range_point.sigma_label == "1"


def test_put_call_points_returns_only_put_and_call_points():
    snapshot = parse_highcharts_chart(_highcharts_fixture(), "open_interest")

    points = put_call_points(snapshot)

    assert len(points) == 2
    assert {point.series_type for point in points} == {
        QuikStrikeSeriesType.PUT,
        QuikStrikeSeriesType.CALL,
    }


def test_view_value_type_comes_from_view_type():
    assert view_value_type(QuikStrikeViewType.INTRADAY_VOLUME) == "intraday_volume"
    assert view_value_type("eod_volume") == "eod_volume"
    assert view_value_type(QuikStrikeViewType.CHURN) == "churn"


def test_classify_series_name_handles_supported_series():
    assert classify_series_name("Put") == QuikStrikeSeriesType.PUT
    assert classify_series_name("Call") == QuikStrikeSeriesType.CALL
    assert classify_series_name("Vol Settle") == QuikStrikeSeriesType.VOL_SETTLE
    assert classify_series_name("Ranges") == QuikStrikeSeriesType.RANGES
    assert classify_series_name("Other") == QuikStrikeSeriesType.UNKNOWN


def test_parse_highcharts_chart_rejects_secret_like_payloads():
    payload = _highcharts_fixture()
    payload["headers"] = {"Cookie": "not allowed"}

    with pytest.raises(ValueError, match="secret/session fields"):
        parse_highcharts_chart(payload, QuikStrikeViewType.OPEN_INTEREST)


def test_parse_highcharts_chart_validates_point_shape():
    payload = {"series": [{"name": "Put", "data": [{"x": 4700}]}]}

    with pytest.raises(ValueError, match="numeric x and y"):
        parse_highcharts_chart(payload, QuikStrikeViewType.OPEN_INTEREST)
