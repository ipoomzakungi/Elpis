from __future__ import annotations

import re

from src.models.xau_quikstrike_fusion import (
    XauFusionAgreementStatus,
    XauFusionBasisState,
    XauFusionContextStatus,
    XauFusionContextSummary,
    XauFusionCoverageSummary,
    XauFusionDownstreamResult,
    XauFusionMatchKey,
    XauFusionMissingContextItem,
    XauFusionRow,
    XauFusionSourceType,
    XauFusionSourceValue,
    XauQuikStrikeFusionRequest,
    XauQuikStrikeSourceRef,
    validate_xau_fusion_safe_id,
)
from src.xau_quikstrike_fusion.basis import calculate_spot_equivalent_level
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
