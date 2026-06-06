"""Build sanitized expected-range band artifacts from QuikStrike chart data."""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from src.models.quikstrike import (
    QuikStrikeExtractionRequest,
    QuikStrikeHighchartsSnapshot,
    QuikStrikePoint,
    QuikStrikeSeriesType,
    QuikStrikeViewType,
    ensure_no_forbidden_quikstrike_content,
)

RANGE_BANDS_LIMITATIONS = [
    "Range bands are captured from sanitized Highcharts Ranges series only.",
    "No credentials, cookies, headers, HAR, screenshots, viewstate, full URLs, "
    "request bodies, or response bodies are saved.",
]


def build_range_bands_payload(
    *,
    extraction_id: str,
    request: QuikStrikeExtractionRequest,
    created_at: datetime,
) -> dict[str, Any]:
    """Create a local-only range-band artifact from sanitized Vol2Vol snapshots."""

    views = [
        _view_payload(
            view=view,
            snapshot=request.highcharts_by_view[view],
            metadata=request.dom_metadata_by_view[view],
        )
        for view in request.requested_views
    ]
    payload = {
        "extraction_id": extraction_id,
        "created_at": created_at.isoformat(),
        "source": "quikstrike_highcharts_local",
        "views": views,
        "view_count": len(views),
        "limitations": RANGE_BANDS_LIMITATIONS,
    }
    ensure_no_forbidden_quikstrike_content(payload)
    return payload


def range_bands_payload_has_data(payload: dict[str, Any]) -> bool:
    """Return true when at least one view has chart-native range segments."""

    return any(view.get("segments") for view in payload.get("views", []))


def _view_payload(
    *,
    view: QuikStrikeViewType,
    snapshot: QuikStrikeHighchartsSnapshot,
    metadata: Any,
) -> dict[str, Any]:
    segments = [_segment_payload(point) for point in _range_points(snapshot)]
    segments = [segment for segment in segments if segment is not None]
    cumulative_bands = _cumulative_bands(
        segments,
        reference_price=metadata.future_reference_price,
    )
    return {
        "view_type": view.value,
        "product": metadata.product,
        "option_product_code": metadata.option_product_code,
        "futures_symbol": metadata.futures_symbol,
        "expiration": metadata.expiration.isoformat() if metadata.expiration else None,
        "expiration_code": metadata.expiration_code,
        "dte": metadata.dte,
        "future_reference_price": metadata.future_reference_price,
        "chart_title": snapshot.chart_title,
        "segments": segments,
        "cumulative_bands": cumulative_bands,
        "segment_count": len(segments),
        "cumulative_band_count": len(cumulative_bands),
    }


def _range_points(snapshot: QuikStrikeHighchartsSnapshot) -> Iterable[QuikStrikePoint]:
    for series in snapshot.series:
        if series.series_type != QuikStrikeSeriesType.RANGES:
            continue
        yield from series.points


def _segment_payload(point: QuikStrikePoint) -> dict[str, Any] | None:
    if point.x is None or point.x2 is None:
        return None
    lower = min(point.x, point.x2)
    upper = max(point.x, point.x2)
    sigma = _sigma_value(point)
    return {
        "range_label": point.range_label,
        "sigma_label": point.sigma_label,
        "sigma": sigma,
        "lower_strike": lower,
        "upper_strike": upper,
        "width": upper - lower,
    }


def _cumulative_bands(
    segments: list[dict[str, Any]],
    *,
    reference_price: float | None,
) -> list[dict[str, Any]]:
    numeric_sigmas = sorted(
        {
            segment["sigma"]
            for segment in segments
            if isinstance(segment.get("sigma"), int | float)
        }
    )
    bands: list[dict[str, Any]] = []
    for sigma in numeric_sigmas:
        included = [
            segment
            for segment in segments
            if isinstance(segment.get("sigma"), int | float)
            and float(segment["sigma"]) <= float(sigma)
        ]
        if not included:
            continue
        lower = min(float(segment["lower_strike"]) for segment in included)
        upper = max(float(segment["upper_strike"]) for segment in included)
        lower_move = (
            abs(float(reference_price) - lower) if reference_price is not None else None
        )
        upper_move = (
            abs(upper - float(reference_price)) if reference_price is not None else None
        )
        cme_numeric_sd = (
            max(lower_move, upper_move)
            if lower_move is not None and upper_move is not None
            else (upper - lower) / 2.0
        )
        bands.append(
            {
                "sigma": sigma,
                "label": _sigma_label(sigma),
                "lower_strike": lower,
                "upper_strike": upper,
                "width": upper - lower,
                "lower_move": lower_move,
                "upper_move": upper_move,
                "cme_numeric_sd": cme_numeric_sd,
            }
        )
    return bands


def _sigma_value(point: QuikStrikePoint) -> float | None:
    for value in (point.sigma_label, point.range_label):
        sigma = _parse_sigma(value)
        if sigma is not None:
            return sigma
    return None


def _parse_sigma(value: str | None) -> float | None:
    if value is None:
        return None
    match = re.search(r"\d+(?:\.\d+)?", value)
    return float(match.group(0)) if match else None


def _sigma_label(sigma: float) -> str:
    if sigma.is_integer():
        return f"{int(sigma)}SD"
    return f"{sigma:g}SD"
