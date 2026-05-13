from __future__ import annotations

import re

from src.models.xau_quikstrike_fusion import (
    XauFusionCoverageSummary,
    XauFusionMatchKey,
    XauFusionMissingContextItem,
    XauFusionRow,
    XauFusionSourceType,
    XauFusionSourceValue,
    validate_xau_fusion_safe_id,
)
from src.xau_quikstrike_fusion.matching import (
    evaluate_source_agreement,
    match_source_rows,
)


def build_fusion_rows(
    *,
    fusion_report_id: str,
    vol2vol_values: list[XauFusionSourceValue],
    matrix_values: list[XauFusionSourceValue],
) -> tuple[list[XauFusionRow], XauFusionCoverageSummary, list[str]]:
    """Build deterministic fused rows while preserving both source values."""

    match_result = match_source_rows(vol2vol_values, matrix_values)
    rows: list[XauFusionRow] = []
    for pair in match_result.pairs:
        vol2vol_value = pair.vol2vol_value
        matrix_value = pair.matrix_value
        agreement_status, agreement_notes = evaluate_source_agreement(
            vol2vol_value,
            matrix_value,
        )
        source_type = _source_type_for_pair(vol2vol_value, matrix_value)
        rows.append(
            XauFusionRow(
                fusion_row_id=stable_fusion_row_id(fusion_report_id, pair.match_key),
                fusion_report_id=fusion_report_id,
                match_key=pair.match_key,
                source_type=source_type,
                match_status=pair.match_status,
                agreement_status=agreement_status,
                vol2vol_value=vol2vol_value,
                matrix_value=matrix_value,
                source_agreement_notes=agreement_notes,
                warnings=list(pair.warnings),
                limitations=_row_limitations(vol2vol_value, matrix_value),
            )
        )
    return rows, match_result.coverage, match_result.blocked_reasons


def build_missing_context_items() -> list[XauFusionMissingContextItem]:
    """Return the US1 placeholder checklist.

    Detailed basis, IV/range, open-regime, and candle-context checks are part of
    the later missing-context slice. US1 only reports source compatibility issues.
    """

    return []


def stable_fusion_row_id(fusion_report_id: str, match_key: XauFusionMatchKey) -> str:
    """Create a stable safe id from report id and normalized match key."""

    components = [
        fusion_report_id,
        _safe_component(match_key.expiration_key or "unknown_expiry"),
        _number_component(match_key.strike),
        _safe_component(match_key.option_type),
        _safe_component(match_key.value_type),
    ]
    return validate_xau_fusion_safe_id("_".join(components), "fusion_row_id")


def _source_type_for_pair(
    vol2vol_value: XauFusionSourceValue | None,
    matrix_value: XauFusionSourceValue | None,
) -> XauFusionSourceType:
    if vol2vol_value is not None and matrix_value is not None:
        return XauFusionSourceType.FUSED
    if vol2vol_value is not None:
        return XauFusionSourceType.VOL2VOL
    return XauFusionSourceType.MATRIX


def _row_limitations(
    vol2vol_value: XauFusionSourceValue | None,
    matrix_value: XauFusionSourceValue | None,
) -> list[str]:
    limitations = ["Fused row is a local-only research annotation."]
    for value in (vol2vol_value, matrix_value):
        if value is None:
            continue
        limitations.extend(value.limitations)
    return list(dict.fromkeys(limitations))


def _safe_component(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", value.strip())
    return cleaned.strip("_") or "unknown"


def _number_component(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return str(value).replace("-", "m").replace(".", "p")
