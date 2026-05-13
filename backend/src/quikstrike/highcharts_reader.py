"""Parse sanitized synthetic Highcharts-like chart objects for QuikStrike."""

from collections.abc import Mapping, Sequence
from typing import Any

from src.models.quikstrike import (
    QuikStrikeHighchartsSnapshot,
    QuikStrikePoint,
    QuikStrikeSeriesSnapshot,
    QuikStrikeSeriesType,
    QuikStrikeViewType,
    ensure_no_forbidden_quikstrike_content,
    value_type_for_view,
)


def parse_highcharts_chart(
    chart: Mapping[str, Any], view_type: QuikStrikeViewType | str
) -> QuikStrikeHighchartsSnapshot:
    """Parse a sanitized Highcharts-like chart fixture into strict snapshots."""

    ensure_no_forbidden_quikstrike_content(chart)
    normalized_view_type = QuikStrikeViewType(view_type)
    raw_series = _series_from_chart(chart)
    series = [_parse_series(series_item) for series_item in raw_series]
    return QuikStrikeHighchartsSnapshot(
        chart_title=_chart_title(chart),
        view_type=normalized_view_type,
        series=series,
        chart_warnings=[] if series else ["No Highcharts series were available."],
        chart_limitations=[
            "Synthetic or sanitized Highcharts chart object; no browser session data stored."
        ],
    )


def put_call_points(snapshot: QuikStrikeHighchartsSnapshot) -> list[QuikStrikePoint]:
    """Return Put/Call points from a parsed chart snapshot."""

    return [
        point
        for series in snapshot.series
        if series.series_type in {QuikStrikeSeriesType.PUT, QuikStrikeSeriesType.CALL}
        for point in series.points
    ]


def view_value_type(view_type: QuikStrikeViewType | str) -> str:
    """Map a supported QuikStrike view to the normalized row value_type."""

    return value_type_for_view(view_type)


def classify_series_name(name: str | None) -> QuikStrikeSeriesType:
    normalized = (name or "").strip().lower()
    if normalized == "put" or normalized.startswith("put "):
        return QuikStrikeSeriesType.PUT
    if normalized == "call" or normalized.startswith("call "):
        return QuikStrikeSeriesType.CALL
    if "vol settle" in normalized or normalized in {"volatility", "vol"}:
        return QuikStrikeSeriesType.VOL_SETTLE
    if "range" in normalized:
        return QuikStrikeSeriesType.RANGES
    return QuikStrikeSeriesType.UNKNOWN


def _series_from_chart(chart: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    raw_series = chart.get("series")
    if raw_series is None and isinstance(chart.get("userOptions"), Mapping):
        raw_series = chart["userOptions"].get("series")
    if raw_series is None:
        raw_series = []
    if not isinstance(raw_series, list):
        raise ValueError("Highcharts series must be a list")
    if not all(isinstance(item, Mapping) for item in raw_series):
        raise ValueError("Highcharts series items must be objects")
    return list(raw_series)


def _parse_series(series: Mapping[str, Any]) -> QuikStrikeSeriesSnapshot:
    series_name = _string_value(series.get("name")) or "Unknown"
    series_type = _series_type_from_item(series, series_name)
    raw_points = _points_from_series(series)
    points = [_parse_point(point, series_type) for point in raw_points]
    return QuikStrikeSeriesSnapshot(
        series_name=series_name,
        series_type=series_type,
        point_count=len(points),
        points=points,
        warnings=[],
        limitations=[],
    )


def _series_type_from_item(series: Mapping[str, Any], series_name: str) -> QuikStrikeSeriesType:
    raw_type = series.get("series_type")
    if raw_type:
        return QuikStrikeSeriesType(raw_type)
    return classify_series_name(series_name)


def _points_from_series(series: Mapping[str, Any]) -> list[Any]:
    raw_points = series.get("points", series.get("data", []))
    if not isinstance(raw_points, list):
        raise ValueError("Highcharts series points/data must be a list")
    return raw_points


def _parse_point(point: Any, series_type: QuikStrikeSeriesType) -> QuikStrikePoint:
    if isinstance(point, Sequence) and not isinstance(point, (str, bytes, bytearray, Mapping)):
        point_mapping: Mapping[str, Any] = {
            "x": point[0] if len(point) > 0 else None,
            "y": point[1] if len(point) > 1 else None,
        }
    elif isinstance(point, Mapping):
        point_mapping = point
    else:
        raise ValueError("Highcharts points must be objects or x/y arrays")

    options = point_mapping.get("options")
    if not isinstance(options, Mapping):
        options = {}
    tag = _tag_from_point(point_mapping, options)
    metadata_keys = list(tag.keys()) if isinstance(tag, Mapping) else []
    if isinstance(point_mapping, Mapping):
        metadata_keys.extend(
            str(key)
            for key in point_mapping
            if str(key).lower() in {"tag", "strikeid", "range", "sigma"}
        )

    return QuikStrikePoint(
        series_type=series_type,
        x=_optional_float(_first_present(point_mapping.get("x"), options.get("x"))),
        y=_optional_float(_first_present(point_mapping.get("y"), options.get("y"))),
        x2=_optional_float(_first_present(point_mapping.get("x2"), options.get("x2"))),
        name=_string_value(
            _first_present(point_mapping.get("name"), options.get("name"), point_mapping.get("key"))
        ),
        category=_string_value(point_mapping.get("category")),
        strike_id=_string_value(
            _first_present(
                point_mapping.get("strike_id"),
                point_mapping.get("StrikeId"),
                _mapping_value(tag, "StrikeId"),
                _mapping_value(tag, "strikeId"),
                _mapping_value(tag, "strike_id"),
            )
        ),
        range_label=_string_value(
            _first_present(
                point_mapping.get("range_label"),
                _mapping_value(tag, "Range"),
                _mapping_value(tag, "range"),
            )
        ),
        sigma_label=_string_value(
            _first_present(
                point_mapping.get("sigma_label"),
                _mapping_value(tag, "Sigma"),
                _mapping_value(tag, "sigma"),
            )
        ),
        metadata_keys=metadata_keys,
    )


def _tag_from_point(
    point_mapping: Mapping[str, Any], options: Mapping[str, Any]
) -> Mapping[str, Any]:
    tag = point_mapping.get("Tag", point_mapping.get("tag"))
    if not isinstance(tag, Mapping):
        tag = options.get("Tag", options.get("tag"))
    return tag if isinstance(tag, Mapping) else {}


def _chart_title(chart: Mapping[str, Any]) -> str | None:
    explicit = _string_value(chart.get("chart_title"))
    if explicit:
        return explicit
    title = chart.get("title")
    if isinstance(title, Mapping):
        return _string_value(title.get("text"))
    options = chart.get("options")
    if isinstance(options, Mapping) and isinstance(options.get("title"), Mapping):
        return _string_value(options["title"].get("text"))
    return None


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _mapping_value(mapping: Mapping[str, Any], key: str) -> Any:
    return mapping.get(key)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("boolean values are not valid Highcharts numeric points")
    return float(value)


def _string_value(value: Any) -> str | None:
    if value is None:
        return None
    normalized = " ".join(str(value).split())
    return normalized or None
