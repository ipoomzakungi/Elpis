"""Build normalized local-only QuikStrike extraction rows from sanitized fixtures."""

from dataclasses import dataclass
from datetime import UTC, datetime

from src.models.quikstrike import (
    QUIKSTRIKE_RESEARCH_ONLY_WARNING,
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
    value_type_for_view,
)

LOCAL_ONLY_LIMITATION = "QuikStrike extraction is local-only and research-only."
SANITIZED_INPUT_LIMITATION = (
    "Only sanitized visible DOM metadata and Highcharts point fields are processed."
)


@dataclass(frozen=True)
class QuikStrikeExtractionBundle:
    result: QuikStrikeExtractionResult
    rows: list[QuikStrikeNormalizedRow]


def build_extraction_from_request(
    request: QuikStrikeExtractionRequest,
    *,
    extraction_id: str | None = None,
    capture_timestamp: datetime | None = None,
) -> QuikStrikeExtractionBundle:
    """Build normalized rows and extraction status from sanitized request fixtures."""

    timestamp = capture_timestamp or datetime.now(UTC)
    safe_extraction_id = extraction_id or _default_extraction_id(timestamp)
    rows: list[QuikStrikeNormalizedRow] = []
    warnings: list[str] = []
    partial_views: list[QuikStrikeViewType] = []
    missing_views: list[QuikStrikeViewType] = []

    mapping = validate_strike_mapping(
        [request.highcharts_by_view[view] for view in request.requested_views]
    )

    for view in request.requested_views:
        metadata = request.dom_metadata_by_view[view]
        snapshot = request.highcharts_by_view[view]
        view_rows = build_normalized_rows_for_view(
            extraction_id=safe_extraction_id,
            capture_timestamp=timestamp,
            metadata=metadata,
            snapshot=snapshot,
            strike_mapping=mapping,
        )
        rows.extend(view_rows)
        has_put = any(row.option_type == QuikStrikeOptionType.PUT for row in view_rows)
        has_call = any(row.option_type == QuikStrikeOptionType.CALL for row in view_rows)
        if not view_rows:
            missing_views.append(view)
            warnings.append(f"{view.value} produced no Put/Call rows.")
        elif not (has_put and has_call):
            partial_views.append(view)
            warnings.append(f"{view.value} did not include both Put and Call rows.")

    completed_views = [
        view
        for view in request.requested_views
        if view not in missing_views and view not in partial_views
    ]
    status = _extraction_status(rows, missing_views, partial_views, mapping)
    conversion_eligible = (
        status == QuikStrikeExtractionStatus.COMPLETED
        and mapping.confidence == QuikStrikeStrikeMappingConfidence.HIGH
    )
    result = QuikStrikeExtractionResult(
        extraction_id=safe_extraction_id,
        status=status,
        created_at=timestamp,
        completed_at=timestamp,
        requested_views=request.requested_views,
        completed_views=completed_views,
        partial_views=partial_views,
        missing_views=missing_views,
        row_count=len(rows),
        put_row_count=sum(row.option_type == QuikStrikeOptionType.PUT for row in rows),
        call_row_count=sum(row.option_type == QuikStrikeOptionType.CALL for row in rows),
        strike_mapping=mapping,
        conversion_eligible=conversion_eligible,
        warnings=warnings,
        limitations=[LOCAL_ONLY_LIMITATION, SANITIZED_INPUT_LIMITATION],
        research_only_warnings=[QUIKSTRIKE_RESEARCH_ONLY_WARNING],
    )
    return QuikStrikeExtractionBundle(result=result, rows=rows)


def build_normalized_rows_for_view(
    *,
    extraction_id: str,
    capture_timestamp: datetime,
    metadata: QuikStrikeDomMetadata,
    snapshot: QuikStrikeHighchartsSnapshot,
    strike_mapping: QuikStrikeStrikeMappingValidation | None = None,
) -> list[QuikStrikeNormalizedRow]:
    """Combine one sanitized DOM metadata object with one parsed Highcharts snapshot."""

    if metadata.selected_view_type != snapshot.view_type:
        raise ValueError("DOM metadata and Highcharts snapshot view types must match")

    mapping = strike_mapping or validate_strike_mapping(snapshot)
    vol_settle_by_strike = _vol_settle_by_strike(snapshot)
    ranges = _range_points(snapshot)
    rows: list[QuikStrikeNormalizedRow] = []

    for series in _put_call_series(snapshot):
        option_type = (
            QuikStrikeOptionType.PUT
            if series.series_type == QuikStrikeSeriesType.PUT
            else QuikStrikeOptionType.CALL
        )
        for point in series.points:
            if point.x is None:
                continue
            strike_key = _strike_key(point.x)
            range_point = _matching_range(point.x, ranges)
            row_warnings = _point_warnings(point)
            row_limitations = _row_limitations(metadata, snapshot, series)
            rows.append(
                QuikStrikeNormalizedRow(
                    row_id=_row_id(
                        extraction_id,
                        snapshot.view_type,
                        point.x,
                        option_type,
                    ),
                    extraction_id=extraction_id,
                    capture_timestamp=capture_timestamp,
                    product=metadata.product,
                    option_product_code=metadata.option_product_code,
                    futures_symbol=metadata.futures_symbol,
                    expiration=metadata.expiration,
                    dte=metadata.dte,
                    future_reference_price=metadata.future_reference_price,
                    view_type=snapshot.view_type,
                    strike=point.x,
                    strike_id=point.strike_id,
                    option_type=option_type,
                    value=point.y if point.y is not None else 0.0,
                    value_type=value_type_for_view(snapshot.view_type),
                    vol_settle=vol_settle_by_strike.get(strike_key),
                    range_label=point.range_label
                    or (range_point.range_label if range_point else None),
                    sigma_label=point.sigma_label
                    or (range_point.sigma_label if range_point else None),
                    source_view=metadata.source_view,
                    strike_mapping_confidence=mapping.confidence,
                    extraction_warnings=row_warnings,
                    extraction_limitations=row_limitations,
                )
            )
    return rows


def validate_strike_mapping(
    snapshots: QuikStrikeHighchartsSnapshot | list[QuikStrikeHighchartsSnapshot],
) -> QuikStrikeStrikeMappingValidation:
    """Validate whether chart x values can be treated as strike coordinates."""

    snapshot_list = snapshots if isinstance(snapshots, list) else [snapshots]
    points = [
        point
        for snapshot in snapshot_list
        for series in _put_call_series(snapshot)
        for point in series.points
    ]
    if not points:
        return QuikStrikeStrikeMappingValidation(
            confidence=QuikStrikeStrikeMappingConfidence.UNKNOWN,
            method="blocked_no_put_call_points",
            matched_point_count=0,
            unmatched_point_count=0,
            conflict_count=0,
            warnings=["No Put/Call points were available for strike mapping."],
            limitations=["Conversion is blocked until strike coordinates are available."],
        )

    matched_count = 0
    unmatched_count = 0
    conflict_count = 0
    evidence: list[str] = []
    warnings: list[str] = []

    for point in points:
        point_result = _point_mapping_status(point)
        if point_result == "matched":
            matched_count += 1
        elif point_result == "conflict":
            conflict_count += 1
        else:
            unmatched_count += 1

    if matched_count:
        evidence.append("Highcharts x values align with StrikeId or visible point labels.")
    if unmatched_count:
        warnings.append("Some strike x values could not be cross-checked.")
    if conflict_count:
        warnings.append("Some StrikeId or label metadata conflicts with x values.")

    if conflict_count:
        confidence = QuikStrikeStrikeMappingConfidence.CONFLICT
        method = "strike_metadata_conflict"
    elif unmatched_count == 0 and matched_count > 0:
        confidence = QuikStrikeStrikeMappingConfidence.HIGH
        method = "x_strike_id_or_label_match"
    else:
        confidence = QuikStrikeStrikeMappingConfidence.PARTIAL
        method = "x_only_without_cross_check"

    return QuikStrikeStrikeMappingValidation(
        confidence=confidence,
        method=method,
        matched_point_count=matched_count,
        unmatched_point_count=unmatched_count,
        conflict_count=conflict_count,
        evidence=evidence,
        warnings=warnings,
        limitations=[] if confidence == QuikStrikeStrikeMappingConfidence.HIGH else [
            "XAU Vol-OI conversion requires high strike mapping confidence."
        ],
    )


def _extraction_status(
    rows: list[QuikStrikeNormalizedRow],
    missing_views: list[QuikStrikeViewType],
    partial_views: list[QuikStrikeViewType],
    mapping: QuikStrikeStrikeMappingValidation,
) -> QuikStrikeExtractionStatus:
    if not rows or mapping.confidence == QuikStrikeStrikeMappingConfidence.UNKNOWN:
        return QuikStrikeExtractionStatus.BLOCKED
    if (
        missing_views
        or partial_views
        or mapping.confidence != QuikStrikeStrikeMappingConfidence.HIGH
    ):
        return QuikStrikeExtractionStatus.PARTIAL
    return QuikStrikeExtractionStatus.COMPLETED


def _put_call_series(
    snapshot: QuikStrikeHighchartsSnapshot,
) -> list[QuikStrikeSeriesSnapshot]:
    return [
        series
        for series in snapshot.series
        if series.series_type in {QuikStrikeSeriesType.PUT, QuikStrikeSeriesType.CALL}
    ]


def _vol_settle_by_strike(snapshot: QuikStrikeHighchartsSnapshot) -> dict[str, float]:
    values: dict[str, float] = {}
    for series in snapshot.series:
        if series.series_type != QuikStrikeSeriesType.VOL_SETTLE:
            continue
        for point in series.points:
            if point.x is not None and point.y is not None:
                values[_strike_key(point.x)] = point.y
    return values


def _range_points(snapshot: QuikStrikeHighchartsSnapshot) -> list[QuikStrikePoint]:
    return [
        point
        for series in snapshot.series
        if series.series_type == QuikStrikeSeriesType.RANGES
        for point in series.points
    ]


def _matching_range(strike: float, ranges: list[QuikStrikePoint]) -> QuikStrikePoint | None:
    for point in ranges:
        if point.x is None:
            continue
        upper = point.x2 if point.x2 is not None else point.x
        lower = min(point.x, upper)
        high = max(point.x, upper)
        if lower <= strike <= high:
            return point
    return None


def _point_mapping_status(point: QuikStrikePoint) -> str:
    if point.x is None:
        return "unmatched"
    strike = _strike_label(point.x)
    label_values = [
        _normalize_numeric_label(value)
        for value in (point.name, point.category)
        if value is not None
    ]
    label_matches = any(label == strike for label in label_values)
    has_strike_id = point.strike_id is not None
    strike_id_matches = has_strike_id and strike in _digits(point.strike_id)
    has_cross_check = point.strike_id is not None or bool(label_values)

    if strike_id_matches:
        return "matched"
    if has_strike_id:
        return "conflict"
    if label_matches:
        return "matched"
    if has_cross_check:
        return "conflict"
    return "unmatched"


def _point_warnings(point: QuikStrikePoint) -> list[str]:
    warnings: list[str] = []
    if point.strike_id is None:
        warnings.append("StrikeId metadata was not available for this point.")
    return warnings


def _row_limitations(
    metadata: QuikStrikeDomMetadata,
    snapshot: QuikStrikeHighchartsSnapshot,
    series: QuikStrikeSeriesSnapshot,
) -> list[str]:
    return _dedupe(
        [
            LOCAL_ONLY_LIMITATION,
            *metadata.limitations,
            *snapshot.chart_limitations,
            *series.limitations,
        ]
    )


def _row_id(
    extraction_id: str,
    view_type: QuikStrikeViewType,
    strike: float,
    option_type: QuikStrikeOptionType,
) -> str:
    return f"{extraction_id}_{view_type.value}_{_safe_strike(strike)}_{option_type.value}"


def _default_extraction_id(timestamp: datetime) -> str:
    return f"quikstrike_{timestamp.strftime('%Y%m%d_%H%M%S')}"


def _strike_key(value: float) -> str:
    return f"{value:.8f}".rstrip("0").rstrip(".")


def _strike_label(value: float) -> str:
    return _digits(_strike_key(value))


def _safe_strike(value: float) -> str:
    return _strike_key(value).replace(".", "_").replace("-", "m")


def _normalize_numeric_label(value: str) -> str:
    return _digits(value)


def _digits(value: str) -> str:
    return "".join(character for character in str(value) if character.isdigit())


def _dedupe(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        if value and value not in deduped:
            deduped.append(value)
    return deduped
