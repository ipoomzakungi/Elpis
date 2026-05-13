from __future__ import annotations

from dataclasses import dataclass
from datetime import date as dt_date
from typing import Any

from src.models.xau_quikstrike_fusion import (
    XauFusionContextStatus,
    XauFusionMissingContextItem,
    XauFusionSourceType,
    XauFusionSourceValue,
    XauQuikStrikeSourceRef,
)
from src.quikstrike.report_store import QuikStrikeReportStore
from src.quikstrike_matrix.report_store import QuikStrikeMatrixReportStore


@dataclass(frozen=True)
class LoadedFusionSource:
    """Sanitized source reference plus normalized fusion source values."""

    ref: XauQuikStrikeSourceRef
    values: list[XauFusionSourceValue]


def load_vol2vol_source_ref(
    report_id: str,
    *,
    store: QuikStrikeReportStore | None = None,
) -> XauQuikStrikeSourceRef:
    """Load a sanitized Vol2Vol source report reference."""

    return load_vol2vol_source(report_id, store=store).ref


def load_matrix_source_ref(
    report_id: str,
    *,
    store: QuikStrikeMatrixReportStore | None = None,
) -> XauQuikStrikeSourceRef:
    """Load a sanitized Matrix source report reference."""

    return load_matrix_source(report_id, store=store).ref


def load_vol2vol_source(
    report_id: str,
    *,
    store: QuikStrikeReportStore | None = None,
) -> LoadedFusionSource:
    """Load a saved feature 012 Vol2Vol report and normalize rows for fusion."""

    report_store = store or QuikStrikeReportStore()
    report = report_store.read_report(report_id)
    rows = report_store.read_normalized_rows(report_id)
    source_ref = XauQuikStrikeSourceRef(
        source_type=XauFusionSourceType.VOL2VOL,
        report_id=report.extraction_id,
        status=_enum_value(report.status),
        product=_first_attr(rows, "product"),
        option_product_code=_first_attr(rows, "option_product_code"),
        row_count=len(rows),
        conversion_status=(
            _enum_value(report.conversion_result.status)
            if report.conversion_result is not None
            else None
        ),
        warnings=[
            *report.warnings,
            *report.strike_mapping.warnings,
        ],
        limitations=[
            *report.limitations,
            *report.strike_mapping.limitations,
            *report.research_only_warnings,
        ],
        artifact_paths=[artifact.path for artifact in report.artifacts],
    )
    return LoadedFusionSource(
        ref=source_ref,
        values=normalize_vol2vol_rows(report.extraction_id, rows),
    )


def load_matrix_source(
    report_id: str,
    *,
    store: QuikStrikeMatrixReportStore | None = None,
) -> LoadedFusionSource:
    """Load a saved feature 013 Matrix report and normalize rows for fusion."""

    report_store = store or QuikStrikeMatrixReportStore()
    report = report_store.read_report(report_id)
    rows = report_store.read_normalized_rows(report_id)
    source_ref = XauQuikStrikeSourceRef(
        source_type=XauFusionSourceType.MATRIX,
        report_id=report.extraction_id,
        status=_enum_value(report.status),
        product=_first_attr(rows, "product"),
        option_product_code=_first_attr(rows, "option_product_code"),
        row_count=len(rows),
        conversion_status=(
            _enum_value(report.conversion_result.status)
            if report.conversion_result is not None
            else None
        ),
        warnings=[
            *report.warnings,
            *report.mapping.warnings,
        ],
        limitations=[
            *report.limitations,
            *report.mapping.limitations,
            *report.research_only_warnings,
        ],
        artifact_paths=[artifact.path for artifact in report.artifacts],
    )
    return LoadedFusionSource(
        ref=source_ref,
        values=normalize_matrix_rows(report.extraction_id, rows),
    )


def validate_source_compatibility(
    vol2vol_source: XauQuikStrikeSourceRef,
    matrix_source: XauQuikStrikeSourceRef,
) -> list[XauFusionMissingContextItem]:
    """Return blocking source-compatibility reasons for the fusion MVP."""

    issues: list[XauFusionMissingContextItem] = []
    for source_ref in (vol2vol_source, matrix_source):
        source_label = source_ref.source_type.value
        if source_ref.status not in {"completed", "partial"}:
            issues.append(
                _blocking_item(
                    f"{source_label}_status",
                    f"{source_label} source report is not completed or partial.",
                    source_ref.report_id,
                )
            )
        if source_ref.row_count <= 0:
            issues.append(
                _blocking_item(
                    f"{source_label}_rows",
                    f"{source_label} source report has no usable rows.",
                    source_ref.report_id,
                )
            )
        if not _is_gold_og_gc_source(source_ref):
            issues.append(
                _blocking_item(
                    f"{source_label}_product",
                    f"{source_label} source report is not Gold/OG/GC compatible.",
                    source_ref.report_id,
                )
            )
    return issues


def normalize_vol2vol_rows(report_id: str, rows: list[Any]) -> list[XauFusionSourceValue]:
    """Normalize feature 012 rows into fusion source values."""

    normalized: list[XauFusionSourceValue] = []
    for row in rows:
        normalized.append(
            XauFusionSourceValue(
                source_type=XauFusionSourceType.VOL2VOL,
                source_report_id=report_id,
                source_row_id=row.row_id,
                value=row.value,
                value_type=_enum_value(row.value_type),
                source_view=_enum_value(row.view_type),
                strike=row.strike,
                expiration=_date_text(row.expiration),
                expiration_code=row.expiration_code,
                option_type=_enum_value(row.option_type),
                future_reference_price=row.future_reference_price,
                dte=row.dte,
                vol_settle=row.vol_settle,
                range_label=row.range_label,
                sigma_label=row.sigma_label,
                warnings=row.extraction_warnings,
                limitations=row.extraction_limitations,
            )
        )
    return normalized


def normalize_matrix_rows(report_id: str, rows: list[Any]) -> list[XauFusionSourceValue]:
    """Normalize feature 013 rows into fusion source values."""

    normalized: list[XauFusionSourceValue] = []
    for row in rows:
        expiration, expiration_code = _split_expiration_reference(row.expiration)
        normalized.append(
            XauFusionSourceValue(
                source_type=XauFusionSourceType.MATRIX,
                source_report_id=report_id,
                source_row_id=row.row_id,
                value=row.value,
                value_type=_enum_value(row.value_type),
                source_view=_enum_value(row.view_type),
                strike=row.strike,
                expiration=expiration,
                expiration_code=expiration_code,
                option_type=_enum_value(row.option_type) if row.option_type is not None else None,
                future_reference_price=row.future_reference_price,
                dte=row.dte,
                warnings=row.extraction_warnings,
                limitations=row.extraction_limitations,
            )
        )
    return normalized


def _blocking_item(
    context_key: str,
    message: str,
    source_report_id: str,
) -> XauFusionMissingContextItem:
    return XauFusionMissingContextItem(
        context_key=context_key,
        status=XauFusionContextStatus.BLOCKED,
        severity="error",
        blocks_fusion=True,
        message=message,
        source_refs=[source_report_id],
    )


def _is_gold_og_gc_source(source_ref: XauQuikStrikeSourceRef) -> bool:
    scope = f"{source_ref.product or ''} {source_ref.option_product_code or ''}".lower()
    return "gold" in scope or "og|gc" in scope


def _enum_value(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _first_attr(rows: list[Any], attr: str) -> str | None:
    for row in rows:
        value = getattr(row, attr, None)
        if value:
            return str(value)
    return None


def _date_text(value: dt_date | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, dt_date):
        return value.isoformat()
    return str(value)


def _split_expiration_reference(value: str | None) -> tuple[str | None, str | None]:
    if value is None:
        return None, None
    cleaned = value.strip()
    if not cleaned:
        return None, None
    if _looks_like_calendar_date(cleaned):
        return cleaned, None
    return None, cleaned


def _looks_like_calendar_date(value: str) -> bool:
    parts = value.split("-")
    return len(parts) == 3 and all(part.isdigit() for part in parts)
