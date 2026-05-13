"""Convert validated QuikStrike normalized rows into XAU Vol-OI local input rows."""

from dataclasses import dataclass
from datetime import UTC, datetime

from src.models.quikstrike import (
    QuikStrikeArtifact,
    QuikStrikeArtifactFormat,
    QuikStrikeArtifactType,
    QuikStrikeConversionResult,
    QuikStrikeConversionStatus,
    QuikStrikeExtractionResult,
    QuikStrikeExtractionStatus,
    QuikStrikeNormalizedRow,
    QuikStrikeOptionType,
    QuikStrikeStrikeMappingConfidence,
    QuikStrikeViewType,
    QuikStrikeXauVolOiRow,
)

CONVERSION_LIMITATION = (
    "Conversion prepares local XAU Vol-OI research input only and does not run wall scoring."
)
SOURCE_LIMITATION = (
    "Converted from local QuikStrike chart extraction; source limitations are preserved."
)
EXPIRATION_CODE_WARNING = "expiration code parsed, calendar expiry date unavailable"
ACCEPTABLE_STRIKE_CONFIDENCE = {
    QuikStrikeStrikeMappingConfidence.HIGH,
    QuikStrikeStrikeMappingConfidence.PARTIAL,
}


@dataclass(frozen=True)
class QuikStrikeConversionBundle:
    result: QuikStrikeConversionResult
    rows: list[QuikStrikeXauVolOiRow]


def convert_to_xau_vol_oi_rows(
    *,
    extraction_result: QuikStrikeExtractionResult,
    rows: list[QuikStrikeNormalizedRow],
    conversion_id: str | None = None,
    created_at: datetime | None = None,
) -> QuikStrikeConversionBundle:
    """Convert high-confidence normalized rows to existing XAU Vol-OI row shape."""

    timestamp = created_at or datetime.now(UTC)
    safe_conversion_id = conversion_id or f"{extraction_result.extraction_id}_xau_vol_oi"
    blocked_reasons = _conversion_blockers(extraction_result, rows)
    if blocked_reasons:
        return QuikStrikeConversionBundle(
            result=QuikStrikeConversionResult(
                conversion_id=safe_conversion_id,
                extraction_id=extraction_result.extraction_id,
                status=QuikStrikeConversionStatus.BLOCKED,
                row_count=0,
                blocked_reasons=blocked_reasons,
                limitations=[CONVERSION_LIMITATION],
            ),
            rows=[],
        )

    converted_rows = _aggregate_rows(rows)
    warnings = _conversion_warnings(rows)
    artifact = QuikStrikeArtifact(
        artifact_type=QuikStrikeArtifactType.PROCESSED_XAU_VOL_OI_CSV,
        path=f"data/processed/quikstrike/{safe_conversion_id}_input.csv",
        format=QuikStrikeArtifactFormat.CSV,
        rows=len(converted_rows),
        created_at=timestamp,
        limitations=[SOURCE_LIMITATION],
    )
    result = QuikStrikeConversionResult(
        conversion_id=safe_conversion_id,
        extraction_id=extraction_result.extraction_id,
        status=QuikStrikeConversionStatus.COMPLETED,
        row_count=len(converted_rows),
        output_artifacts=[artifact],
        warnings=warnings,
        limitations=[CONVERSION_LIMITATION, SOURCE_LIMITATION],
    )
    return QuikStrikeConversionBundle(result=result, rows=converted_rows)


def _conversion_blockers(
    extraction_result: QuikStrikeExtractionResult,
    rows: list[QuikStrikeNormalizedRow],
) -> list[str]:
    blockers: list[str] = []
    if not rows:
        blockers.append("No normalized QuikStrike rows are available for conversion.")
    if extraction_result.status in {
        QuikStrikeExtractionStatus.BLOCKED,
        QuikStrikeExtractionStatus.FAILED,
    }:
        blockers.append(f"Extraction status is {extraction_result.status.value}.")
    if extraction_result.missing_views:
        blockers.append("One or more requested views produced no rows.")
    if extraction_result.partial_views:
        blockers.append("One or more requested views are missing Put/Call separation.")
    if not extraction_result.conversion_eligible:
        blockers.append("Extraction result is not marked conversion eligible.")
    if extraction_result.strike_mapping.confidence not in ACCEPTABLE_STRIKE_CONFIDENCE:
        blockers.append(
            f"Strike mapping confidence is {extraction_result.strike_mapping.confidence.value}."
        )
    if any(
        row.strike_mapping_confidence not in ACCEPTABLE_STRIKE_CONFIDENCE
        for row in rows
    ):
        blockers.append(
            "One or more rows do not have acceptable strike mapping confidence."
        )
    if any(row.expiration is None and row.expiration_code is None for row in rows):
        blockers.append("One or more rows are missing option expiration reference.")
    if any(row.future_reference_price is None for row in rows):
        blockers.append("One or more rows are missing the future reference price.")
    return _dedupe(blockers)


def _aggregate_rows(rows: list[QuikStrikeNormalizedRow]) -> list[QuikStrikeXauVolOiRow]:
    grouped: dict[tuple[str, float, QuikStrikeOptionType], QuikStrikeXauVolOiRow] = {}
    for row in rows:
        expiration_reference = _expiration_reference(row)
        key = (expiration_reference, row.strike, row.option_type)
        current = grouped.get(key)
        if current is None:
            current = QuikStrikeXauVolOiRow(
                timestamp=row.capture_timestamp,
                expiry=row.expiration,
                expiration_code=row.expiration_code,
                strike=row.strike,
                option_type=row.option_type,
                implied_volatility=row.vol_settle,
                underlying_futures_price=row.future_reference_price,
                dte=row.dte,
                source_view=row.source_view,
                source_extraction_id=row.extraction_id,
                limitations=_row_limitations(row),
            )
        grouped[key] = _apply_view_value(current, row)
    return sorted(
        grouped.values(),
        key=lambda item: (
            item.expiry.isoformat() if item.expiry else item.expiration_code or "",
            item.strike,
            item.option_type.value,
        ),
    )


def _apply_view_value(
    current: QuikStrikeXauVolOiRow,
    row: QuikStrikeNormalizedRow,
) -> QuikStrikeXauVolOiRow:
    update: dict[str, float | None] = {}
    if row.view_type == QuikStrikeViewType.OPEN_INTEREST:
        update["open_interest"] = row.value
    elif row.view_type == QuikStrikeViewType.OI_CHANGE:
        update["oi_change"] = row.value
    elif row.view_type == QuikStrikeViewType.INTRADAY_VOLUME:
        update["intraday_volume"] = row.value
        update["volume"] = row.value
    elif row.view_type == QuikStrikeViewType.EOD_VOLUME:
        update["eod_volume"] = row.value
        if current.volume is None:
            update["volume"] = row.value
    elif row.view_type == QuikStrikeViewType.CHURN:
        update["churn"] = row.value

    if current.implied_volatility is None and row.vol_settle is not None:
        update["implied_volatility"] = row.vol_settle
    return current.model_copy(update=update)


def _row_limitations(row: QuikStrikeNormalizedRow) -> list[str]:
    return _dedupe([SOURCE_LIMITATION, *row.extraction_limitations])


def _expiration_reference(row: QuikStrikeNormalizedRow) -> str:
    if row.expiration is not None:
        return row.expiration.isoformat()
    if row.expiration_code is not None:
        return row.expiration_code
    raise ValueError("row is missing expiration reference")


def _conversion_warnings(rows: list[QuikStrikeNormalizedRow]) -> list[str]:
    warnings: list[str] = []
    if any(row.expiration is None and row.expiration_code is not None for row in rows):
        warnings.append(EXPIRATION_CODE_WARNING)
    return warnings


def _dedupe(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        if value and value not in deduped:
            deduped.append(value)
    return deduped
