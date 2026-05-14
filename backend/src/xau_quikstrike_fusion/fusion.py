from __future__ import annotations

import re
from dataclasses import dataclass

from src.models.xau_quikstrike_fusion import (
    XauFusionAgreementStatus,
    XauFusionBasisState,
    XauFusionContextStatus,
    XauFusionContextSummary,
    XauFusionCoverageSummary,
    XauFusionDownstreamResult,
    XauFusionMatchKey,
    XauFusionMissingContextItem,
    XauFusionReportStatus,
    XauFusionRow,
    XauFusionSourceType,
    XauFusionSourceValue,
    XauFusionVolOiInputRow,
    XauQuikStrikeFusionRequest,
    XauQuikStrikeSourceRef,
    validate_xau_fusion_safe_id,
)
from src.xau_quikstrike_fusion.basis import calculate_spot_equivalent_level
from src.xau_quikstrike_fusion.matching import (
    evaluate_source_agreement,
    match_source_rows,
)

XAU_VOL_OI_SOURCE_LIMITATION = (
    "Fused XAU Vol-OI input is a local research annotation derived from sanitized "
    "QuikStrike Vol2Vol and Matrix outputs."
)
EXPIRATION_CODE_ONLY_WARNING = "expiration code parsed, calendar expiry date unavailable"
SUPPORTED_XAU_VALUE_TYPES = {
    "open_interest",
    "oi_change",
    "volume",
    "intraday_volume",
    "eod_volume",
    "churn",
}


@dataclass(frozen=True)
class XauFusionVolOiConversionBundle:
    """Converted XAU Vol-OI input rows plus explicit conversion status."""

    status: XauFusionReportStatus
    rows: list[XauFusionVolOiInputRow]
    blocked_reasons: list[str]
    warnings: list[str]


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


def build_xau_vol_oi_input_rows(
    rows: list[XauFusionRow],
    *,
    upstream_blocked_reasons: list[str] | None = None,
) -> XauFusionVolOiConversionBundle:
    """Convert fused rows into the local XAU Vol-OI input row shape."""

    blocked_reasons = list(upstream_blocked_reasons or [])
    drafts: dict[tuple[str, float, str], dict] = {}
    for row in rows:
        row_blockers = _conversion_blockers_for_row(row)
        if row_blockers:
            blocked_reasons.extend(
                f"{row.fusion_row_id}: {reason}" for reason in row_blockers
            )
            continue
        key = _xau_input_key(row)
        draft = drafts.setdefault(key, _base_xau_input_draft(row))
        applied = _apply_xau_input_values(draft, row)
        if not applied:
            blocked_reasons.append(
                f"{row.fusion_row_id}: unsupported value mapping '{row.match_key.value_type}'."
            )

    converted_rows: list[XauFusionVolOiInputRow] = []
    for key, draft in sorted(drafts.items(), key=lambda item: item[0]):
        try:
            converted_rows.append(XauFusionVolOiInputRow(**draft))
        except ValueError as exc:
            blocked_reasons.append(f"{key}: {exc}")

    warnings = _conversion_warnings(converted_rows)
    if converted_rows and blocked_reasons:
        status = XauFusionReportStatus.PARTIAL
    elif converted_rows:
        status = XauFusionReportStatus.COMPLETED
    else:
        status = XauFusionReportStatus.BLOCKED
    return XauFusionVolOiConversionBundle(
        status=status,
        rows=converted_rows,
        blocked_reasons=_dedupe(blocked_reasons),
        warnings=warnings,
    )


def build_context_summary(
    *,
    rows: list[XauFusionRow],
    basis_state: XauFusionBasisState,
    request: XauQuikStrikeFusionRequest,
    source_quality_status: XauFusionContextStatus,
    source_agreement_status: XauFusionContextStatus,
    source_refs: list[str],
    source_issues: list[XauFusionMissingContextItem] | None = None,
) -> XauFusionContextSummary:
    """Build the US2 context summary without fabricating missing inputs."""

    iv_range_status = detect_iv_range_status(rows)
    open_regime_status = (
        XauFusionContextStatus.AVAILABLE
        if request.session_open_price is not None
        else XauFusionContextStatus.UNAVAILABLE
    )
    candle_acceptance_status = (
        XauFusionContextStatus.AVAILABLE
        if _has_candle_context(request.candle_context)
        else XauFusionContextStatus.UNAVAILABLE
    )
    realized_volatility_status = (
        XauFusionContextStatus.AVAILABLE
        if request.realized_volatility is not None
        else XauFusionContextStatus.UNAVAILABLE
    )
    missing_context = [
        *(source_issues or []),
        *build_missing_context_items(
            basis_state=basis_state,
            iv_range_status=iv_range_status,
            open_regime_status=open_regime_status,
            candle_acceptance_status=candle_acceptance_status,
            realized_volatility_status=realized_volatility_status,
            source_quality_status=source_quality_status,
            source_agreement_status=source_agreement_status,
            source_refs=source_refs,
        ),
    ]
    return XauFusionContextSummary(
        basis_status=basis_state.status,
        iv_range_status=iv_range_status,
        open_regime_status=open_regime_status,
        candle_acceptance_status=candle_acceptance_status,
        realized_volatility_status=realized_volatility_status,
        source_agreement_status=source_agreement_status,
        missing_context=missing_context,
    )


def build_missing_context_items(
    *,
    basis_state: XauFusionBasisState,
    iv_range_status: XauFusionContextStatus,
    open_regime_status: XauFusionContextStatus,
    candle_acceptance_status: XauFusionContextStatus,
    realized_volatility_status: XauFusionContextStatus,
    source_quality_status: XauFusionContextStatus,
    source_agreement_status: XauFusionContextStatus,
    source_refs: list[str] | None = None,
) -> list[XauFusionMissingContextItem]:
    """Generate the structured context checklist for downstream interpretation."""

    refs = source_refs or []
    return [
        _context_item(
            "basis",
            basis_state.status,
            _basis_message(basis_state),
            source_refs=refs,
            blocks_reaction_confidence=basis_state.status != XauFusionContextStatus.AVAILABLE,
        ),
        _context_item(
            "iv_range",
            iv_range_status,
            _iv_range_message(iv_range_status),
            source_refs=refs,
            blocks_reaction_confidence=iv_range_status != XauFusionContextStatus.AVAILABLE,
        ),
        _context_item(
            "session_open",
            open_regime_status,
            _session_open_message(open_regime_status),
            source_refs=refs,
            blocks_reaction_confidence=open_regime_status != XauFusionContextStatus.AVAILABLE,
        ),
        _context_item(
            "candle_acceptance",
            candle_acceptance_status,
            _candle_message(candle_acceptance_status),
            source_refs=refs,
            blocks_reaction_confidence=(
                candle_acceptance_status != XauFusionContextStatus.AVAILABLE
            ),
        ),
        _context_item(
            "realized_volatility",
            realized_volatility_status,
            _realized_volatility_message(realized_volatility_status),
            source_refs=refs,
            blocks_reaction_confidence=(
                realized_volatility_status != XauFusionContextStatus.AVAILABLE
            ),
        ),
        _context_item(
            "source_quality",
            source_quality_status,
            _source_quality_message(source_quality_status),
            source_refs=refs,
            blocks_fusion=source_quality_status == XauFusionContextStatus.BLOCKED,
            blocks_reaction_confidence=(
                source_quality_status
                in {XauFusionContextStatus.PARTIAL, XauFusionContextStatus.CONFLICT}
            ),
        ),
        _context_item(
            "source_agreement",
            source_agreement_status,
            _source_agreement_message(source_agreement_status),
            source_refs=refs,
            blocks_reaction_confidence=source_agreement_status
            in {XauFusionContextStatus.CONFLICT, XauFusionContextStatus.PARTIAL},
        ),
    ]


def detect_iv_range_status(rows: list[XauFusionRow]) -> XauFusionContextStatus:
    """Detect Vol2Vol range/volatility context from source metadata only."""

    vol2vol_values = [row.vol2vol_value for row in rows if row.vol2vol_value is not None]
    if not vol2vol_values:
        return XauFusionContextStatus.UNAVAILABLE
    values_with_context = [
        value
        for value in vol2vol_values
        if (
            value.vol_settle is not None
            or value.range_label is not None
            or value.sigma_label is not None
        )
    ]
    if len(values_with_context) == len(vol2vol_values):
        return XauFusionContextStatus.AVAILABLE
    if values_with_context:
        return XauFusionContextStatus.PARTIAL
    return XauFusionContextStatus.UNAVAILABLE


def determine_source_quality_status(
    vol2vol_source: XauQuikStrikeSourceRef,
    matrix_source: XauQuikStrikeSourceRef,
) -> XauFusionContextStatus:
    if any(
        source.status not in {"completed", "partial"} or source.row_count <= 0
        for source in (vol2vol_source, matrix_source)
    ):
        return XauFusionContextStatus.BLOCKED
    if vol2vol_source.warnings or matrix_source.warnings:
        return XauFusionContextStatus.PARTIAL
    return XauFusionContextStatus.AVAILABLE


def determine_source_agreement_status(rows: list[XauFusionRow]) -> XauFusionContextStatus:
    if not rows:
        return XauFusionContextStatus.BLOCKED
    if any(row.match_status.value == "conflict" for row in rows):
        return XauFusionContextStatus.CONFLICT
    if any(row.agreement_status == XauFusionAgreementStatus.DISAGREEMENT for row in rows):
        return XauFusionContextStatus.CONFLICT
    if any(row.source_type == XauFusionSourceType.FUSED for row in rows):
        return XauFusionContextStatus.AVAILABLE
    return XauFusionContextStatus.PARTIAL


def attach_context_to_rows(
    rows: list[XauFusionRow],
    *,
    basis_state: XauFusionBasisState,
    missing_context: list[XauFusionMissingContextItem],
) -> list[XauFusionRow]:
    """Attach basis annotations and conservative missing-context notes to rows."""

    notes = [
        item.message
        for item in missing_context
        if item.status != XauFusionContextStatus.AVAILABLE
    ]
    enriched: list[XauFusionRow] = []
    for row in rows:
        spot_equivalent_level = calculate_spot_equivalent_level(row.match_key.strike, basis_state)
        enriched.append(
            row.model_copy(
                update={
                    "basis_points": (
                        basis_state.basis_points
                        if basis_state.status == XauFusionContextStatus.AVAILABLE
                        else None
                    ),
                    "spot_equivalent_level": spot_equivalent_level,
                    "missing_context_notes": _dedupe([*row.missing_context_notes, *notes]),
                }
            )
        )
    return enriched


def build_conservative_downstream_result(
    missing_context: list[XauFusionMissingContextItem],
) -> XauFusionDownstreamResult | None:
    """Summarize why later XAU reaction output should stay conservative."""

    conservative_items = [
        item
        for item in missing_context
        if item.blocks_reaction_confidence and item.status != XauFusionContextStatus.AVAILABLE
    ]
    if not conservative_items:
        return None
    context_keys = ", ".join(item.context_key for item in conservative_items)
    return XauFusionDownstreamResult(
        notes=[
            (
                "Downstream XAU reaction output should remain conservative, including "
                f"NO_TRADE annotations where required, because context is unavailable "
                f"or conflicting: {context_keys}."
            )
        ]
    )


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


def _conversion_blockers_for_row(row: XauFusionRow) -> list[str]:
    blockers: list[str] = []
    if row.match_key.strike <= 0:
        blockers.append("strike is missing or invalid")
    if row.match_key.expiration is None and row.match_key.expiration_code is None:
        blockers.append("expiration or expiration_code is required")
    if row.match_key.option_type not in {"call", "put"}:
        blockers.append("option_type must be call or put")
    if row.match_key.value_type not in SUPPORTED_XAU_VALUE_TYPES:
        blockers.append(f"value_type '{row.match_key.value_type}' is not supported")
    if not _has_usable_source_value(row):
        blockers.append("no usable source value is available")
    return blockers


def _xau_input_key(row: XauFusionRow) -> tuple[str, float, str]:
    expiration_key = row.match_key.expiration or row.match_key.expiration_code or ""
    return (expiration_key, row.match_key.strike, row.match_key.option_type)


def _base_xau_input_draft(row: XauFusionRow) -> dict:
    source_values = _source_values(row)
    return {
        "expiry": row.match_key.expiration,
        "expiration_code": row.match_key.expiration_code,
        "strike": row.match_key.strike,
        "spot_equivalent_strike": row.spot_equivalent_level,
        "option_type": row.match_key.option_type,
        "underlying_futures_price": _first_float(
            value.future_reference_price for value in source_values
        ),
        "source_report_ids": _dedupe(
            [value.source_report_id for value in source_values if value.source_report_id]
        ),
        "source_agreement_status": row.agreement_status,
        "limitations": _dedupe(
            [
                XAU_VOL_OI_SOURCE_LIMITATION,
                *row.limitations,
                *(limitation for value in source_values for limitation in value.limitations),
            ]
        ),
    }


def _apply_xau_input_values(draft: dict, row: XauFusionRow) -> bool:
    applied = False
    source_values = _source_values(row)
    draft["source_report_ids"] = _dedupe(
        [
            *draft.get("source_report_ids", []),
            *(value.source_report_id for value in source_values if value.source_report_id),
        ]
    )
    draft["limitations"] = _dedupe(
        [
            *draft.get("limitations", []),
            *row.limitations,
            *(limitation for value in source_values for limitation in value.limitations),
        ]
    )
    matrix_value = row.matrix_value
    if matrix_value is not None:
        applied = _apply_source_value(draft, matrix_value, prefer_existing=False) or applied
    vol2vol_value = row.vol2vol_value
    if vol2vol_value is not None:
        applied = _apply_source_value(draft, vol2vol_value, prefer_existing=True) or applied
        if draft.get("implied_volatility") is None and vol2vol_value.vol_settle is not None:
            draft["implied_volatility"] = vol2vol_value.vol_settle
    if draft.get("underlying_futures_price") is None:
        draft["underlying_futures_price"] = _first_float(
            value.future_reference_price for value in source_values
        )
    return applied


def _apply_source_value(
    draft: dict,
    value: XauFusionSourceValue,
    *,
    prefer_existing: bool,
) -> bool:
    field = _xau_field_for_source_value(value)
    if field is None or value.value is None:
        return False
    if prefer_existing and draft.get(field) is not None:
        return True
    draft[field] = value.value
    if field in {"intraday_volume", "eod_volume"} and draft.get("volume") is None:
        draft["volume"] = value.value
    return True


def _xau_field_for_source_value(value: XauFusionSourceValue) -> str | None:
    value_type = value.value_type.strip().lower()
    source_view = (value.source_view or "").strip().lower()
    if value_type == "open_interest":
        return "open_interest"
    if value_type == "oi_change":
        return "oi_change"
    if value_type == "churn":
        return "churn"
    if source_view == "intraday_volume" or value_type == "intraday_volume":
        return "intraday_volume"
    if source_view == "eod_volume" or value_type == "eod_volume":
        return "eod_volume"
    if value_type == "volume":
        return "volume"
    return None


def _has_usable_source_value(row: XauFusionRow) -> bool:
    return any(value.value is not None for value in _source_values(row))


def _source_values(row: XauFusionRow) -> list[XauFusionSourceValue]:
    return [value for value in (row.matrix_value, row.vol2vol_value) if value is not None]


def _first_float(values: object) -> float | None:
    for value in values:
        if value is not None:
            return value
    return None


def _conversion_warnings(rows: list[XauFusionVolOiInputRow]) -> list[str]:
    warnings: list[str] = []
    if any(row.expiry is None and row.expiration_code is not None for row in rows):
        warnings.append(EXPIRATION_CODE_ONLY_WARNING)
    return warnings


def _context_item(
    context_key: str,
    status: XauFusionContextStatus,
    message: str,
    *,
    source_refs: list[str],
    blocks_fusion: bool = False,
    blocks_reaction_confidence: bool = False,
) -> XauFusionMissingContextItem:
    severity = "info"
    if status in {XauFusionContextStatus.UNAVAILABLE, XauFusionContextStatus.PARTIAL}:
        severity = "warning"
    if status in {XauFusionContextStatus.CONFLICT, XauFusionContextStatus.BLOCKED}:
        severity = "error"
    return XauFusionMissingContextItem(
        context_key=context_key,
        status=status,
        severity=severity,
        blocks_fusion=blocks_fusion,
        blocks_reaction_confidence=blocks_reaction_confidence,
        message=message,
        source_refs=source_refs,
    )


def _basis_message(basis_state: XauFusionBasisState) -> str:
    if basis_state.status == XauFusionContextStatus.AVAILABLE:
        return "Basis context is available from supplied XAUUSD spot and GC futures references."
    if basis_state.status == XauFusionContextStatus.CONFLICT:
        return "Basis references conflict with the configured research tolerance."
    if basis_state.status == XauFusionContextStatus.BLOCKED:
        return "Basis context is blocked because a supplied reference is invalid."
    return (
        "XAUUSD spot and GC futures references were not both provided; "
        "futures-strike levels are preserved."
    )


def _iv_range_message(status: XauFusionContextStatus) -> str:
    if status == XauFusionContextStatus.AVAILABLE:
        return "Vol2Vol range or volatility-style context is available."
    if status == XauFusionContextStatus.PARTIAL:
        return "Vol2Vol range or volatility-style context is partial across fused rows."
    return "Vol2Vol range or volatility-style context is unavailable."


def _session_open_message(status: XauFusionContextStatus) -> str:
    if status == XauFusionContextStatus.AVAILABLE:
        return "Session-open context is available from the fusion request."
    return "Session-open price was not provided; open-regime context remains unavailable."


def _candle_message(status: XauFusionContextStatus) -> str:
    if status == XauFusionContextStatus.AVAILABLE:
        return "Candle acceptance/rejection context is available from the fusion request."
    return (
        "Candle acceptance/rejection context was not provided; reaction output should "
        "remain conservative."
    )


def _realized_volatility_message(status: XauFusionContextStatus) -> str:
    if status == XauFusionContextStatus.AVAILABLE:
        return "Realized-volatility context is available from the fusion request."
    return "Realized-volatility context was not provided."


def _source_quality_message(status: XauFusionContextStatus) -> str:
    if status == XauFusionContextStatus.AVAILABLE:
        return "Source report quality is available for both selected reports."
    if status == XauFusionContextStatus.PARTIAL:
        return "At least one selected source report carries warnings or partial quality notes."
    return "At least one selected source report is missing, blocked, or has no usable rows."


def _source_agreement_message(status: XauFusionContextStatus) -> str:
    if status == XauFusionContextStatus.AVAILABLE:
        return "Overlapping source values agree or are available for review."
    if status == XauFusionContextStatus.PARTIAL:
        return "Source agreement is partial because some rows are source-only."
    if status == XauFusionContextStatus.CONFLICT:
        return "One or more overlapping source values disagree and require review."
    return "Source agreement is unavailable because fusion rows are unavailable."


def _has_candle_context(value: list[dict] | dict) -> bool:
    if isinstance(value, list):
        return len(value) > 0
    return bool(value)


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
