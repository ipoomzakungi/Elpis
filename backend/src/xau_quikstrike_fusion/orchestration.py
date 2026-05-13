from __future__ import annotations

from datetime import UTC, datetime

from src.models.xau_quikstrike_fusion import (
    XauFusionContextStatus,
    XauFusionCoverageSummary,
    XauFusionMissingContextItem,
    XauFusionReportStatus,
    XauFusionSourceType,
    XauQuikStrikeFusionReport,
    XauQuikStrikeFusionRequest,
    XauQuikStrikeSourceRef,
    validate_xau_fusion_safe_id,
)
from src.quikstrike.report_store import QuikStrikeReportStore
from src.quikstrike_matrix.report_store import QuikStrikeMatrixReportStore
from src.xau_quikstrike_fusion.basis import calculate_basis_state
from src.xau_quikstrike_fusion.fusion import (
    attach_context_to_rows,
    build_conservative_downstream_result,
    build_context_summary,
    build_fusion_rows,
    determine_source_agreement_status,
    determine_source_quality_status,
)
from src.xau_quikstrike_fusion.loaders import (
    LoadedFusionSource,
    load_matrix_source,
    load_vol2vol_source,
    validate_source_compatibility,
)
from src.xau_quikstrike_fusion.report_store import XauQuikStrikeFusionReportStore


def create_xau_quikstrike_fusion_report(
    request: XauQuikStrikeFusionRequest,
    *,
    vol2vol_store: QuikStrikeReportStore | None = None,
    matrix_store: QuikStrikeMatrixReportStore | None = None,
    report_store: XauQuikStrikeFusionReportStore | None = None,
    report_id: str | None = None,
    created_at: datetime | None = None,
) -> XauQuikStrikeFusionReport:
    """Create an MVP fusion report from saved Vol2Vol and Matrix reports."""

    now = created_at or datetime.now(UTC)
    fusion_report_id = report_id or _new_report_id(request.run_label, now)
    loaded_vol2vol = _load_or_missing_vol2vol(request.vol2vol_report_id, vol2vol_store)
    loaded_matrix = _load_or_missing_matrix(request.matrix_report_id, matrix_store)
    missing_context = validate_source_compatibility(
        loaded_vol2vol.ref,
        loaded_matrix.ref,
    )
    basis_state = calculate_basis_state(
        xauusd_spot_reference=request.xauusd_spot_reference,
        gc_futures_reference=request.gc_futures_reference,
    )

    if missing_context:
        coverage = _empty_coverage()
        fused_rows = []
        blocked_reasons = [item.message for item in missing_context]
        status = XauFusionReportStatus.BLOCKED
    else:
        fused_rows, coverage, blocked_reasons = build_fusion_rows(
            fusion_report_id=fusion_report_id,
            vol2vol_values=loaded_vol2vol.values,
            matrix_values=loaded_matrix.values,
        )
        status = XauFusionReportStatus.PARTIAL if fused_rows else XauFusionReportStatus.BLOCKED
        if not fused_rows:
            missing_context.append(
                XauFusionMissingContextItem(
                    context_key="fusion_rows",
                    status=XauFusionContextStatus.BLOCKED,
                    severity="error",
                    blocks_fusion=True,
                    message="No compatible Vol2Vol or Matrix rows were available for fusion.",
                    source_refs=[request.vol2vol_report_id, request.matrix_report_id],
                )
            )
    source_quality_status = determine_source_quality_status(
        loaded_vol2vol.ref,
        loaded_matrix.ref,
    )
    source_agreement_status = determine_source_agreement_status(fused_rows)
    context_summary = build_context_summary(
        rows=fused_rows,
        basis_state=basis_state,
        request=request,
        source_quality_status=source_quality_status,
        source_agreement_status=source_agreement_status,
        source_refs=[request.vol2vol_report_id, request.matrix_report_id],
        source_issues=missing_context,
    )
    fused_rows = attach_context_to_rows(
        fused_rows,
        basis_state=basis_state,
        missing_context=context_summary.missing_context,
    )
    downstream_result = build_conservative_downstream_result(
        context_summary.missing_context,
    )

    warnings = _dedupe([*loaded_vol2vol.ref.warnings, *loaded_matrix.ref.warnings])
    warnings.extend(reason for reason in blocked_reasons if reason not in warnings)
    limitations = _dedupe(
        [
            "XAU QuikStrike fusion is local-only and research-only.",
            "Fusion preserves Vol2Vol and Matrix source values separately.",
            *loaded_vol2vol.ref.limitations,
            *loaded_matrix.ref.limitations,
        ]
    )
    report = XauQuikStrikeFusionReport(
        report_id=fusion_report_id,
        status=status,
        created_at=now,
        completed_at=now,
        request=request,
        vol2vol_source=loaded_vol2vol.ref,
        matrix_source=loaded_matrix.ref,
        coverage=coverage,
        context_summary=context_summary,
        basis_state=basis_state,
        fused_row_count=len(fused_rows),
        fused_rows=fused_rows,
        downstream_result=downstream_result,
        warnings=_dedupe(warnings),
        limitations=limitations,
    )
    if request.persist_report:
        return (report_store or XauQuikStrikeFusionReportStore()).persist_report(report)
    return report


def _load_or_missing_vol2vol(
    report_id: str,
    store: QuikStrikeReportStore | None,
) -> LoadedFusionSource:
    try:
        return load_vol2vol_source(report_id, store=store)
    except FileNotFoundError:
        return LoadedFusionSource(
            ref=_missing_source_ref(XauFusionSourceType.VOL2VOL, report_id),
            values=[],
        )


def _load_or_missing_matrix(
    report_id: str,
    store: QuikStrikeMatrixReportStore | None,
) -> LoadedFusionSource:
    try:
        return load_matrix_source(report_id, store=store)
    except FileNotFoundError:
        return LoadedFusionSource(
            ref=_missing_source_ref(XauFusionSourceType.MATRIX, report_id),
            values=[],
        )


def _missing_source_ref(
    source_type: XauFusionSourceType,
    report_id: str,
) -> XauQuikStrikeSourceRef:
    return XauQuikStrikeSourceRef(
        source_type=source_type,
        report_id=report_id,
        status="missing",
        row_count=0,
        warnings=[f"{source_type.value} source report was not found."],
    )


def _new_report_id(run_label: str | None, created_at: datetime) -> str:
    timestamp = created_at.strftime("%Y%m%d_%H%M%S")
    if run_label:
        return validate_xau_fusion_safe_id(
            f"xau_quikstrike_fusion_{timestamp}_{run_label}",
            "report_id",
        )
    return f"xau_quikstrike_fusion_{timestamp}"


def _empty_coverage() -> XauFusionCoverageSummary:
    return XauFusionCoverageSummary(
        matched_key_count=0,
        vol2vol_only_key_count=0,
        matrix_only_key_count=0,
        conflict_key_count=0,
        blocked_key_count=0,
        strike_count=0,
        expiration_count=0,
        option_type_count=0,
        value_type_count=0,
    )


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
