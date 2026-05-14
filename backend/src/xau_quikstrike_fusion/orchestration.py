from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from src.models.xau import (
    XauReferencePrice,
    XauReferenceType,
    XauVolatilitySnapshot,
    XauVolatilitySource,
    XauVolOiReportRequest,
)
from src.models.xau_quikstrike_fusion import (
    XauFusionContextStatus,
    XauFusionCoverageSummary,
    XauFusionDownstreamResult,
    XauFusionMissingContextItem,
    XauFusionReportStatus,
    XauFusionSourceType,
    XauFusionVolOiInputRow,
    XauQuikStrikeFusionReport,
    XauQuikStrikeFusionRequest,
    XauQuikStrikeSourceRef,
    validate_xau_fusion_safe_id,
)
from src.models.xau_reaction import XauReactionLabel, XauReactionReportRequest
from src.quikstrike.report_store import QuikStrikeReportStore
from src.quikstrike_matrix.report_store import QuikStrikeMatrixReportStore
from src.xau.orchestration import XauReportOrchestrator
from src.xau.report_store import XauReportStore
from src.xau_quikstrike_fusion.basis import calculate_basis_state
from src.xau_quikstrike_fusion.fusion import (
    attach_context_to_rows,
    build_conservative_downstream_result,
    build_context_summary,
    build_fusion_rows,
    build_xau_vol_oi_input_rows,
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
from src.xau_reaction.orchestration import (
    XauReactionReportBlockedError,
    XauReactionReportOrchestrator,
)
from src.xau_reaction.report_store import XauReactionReportStore


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
    fusion_store = report_store or XauQuikStrikeFusionReportStore()
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
    xau_input_conversion = build_xau_vol_oi_input_rows(
        fused_rows,
        upstream_blocked_reasons=blocked_reasons,
    )
    downstream_result = _downstream_result(
        request=request,
        fusion_report_id=fusion_report_id,
        created_at=now,
        report_store=fusion_store,
        xau_input_rows=xau_input_conversion.rows,
        conversion_status=xau_input_conversion.status,
        conversion_blocked_reasons=xau_input_conversion.blocked_reasons,
        conversion_warnings=xau_input_conversion.warnings,
        conservative_result=downstream_result,
    )

    warnings = _dedupe([*loaded_vol2vol.ref.warnings, *loaded_matrix.ref.warnings])
    warnings.extend(reason for reason in blocked_reasons if reason not in warnings)
    warnings.extend(
        warning for warning in xau_input_conversion.warnings if warning not in warnings
    )
    warnings.extend(
        reason for reason in xau_input_conversion.blocked_reasons if reason not in warnings
    )
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
        xau_vol_oi_input_row_count=len(xau_input_conversion.rows),
        fused_rows=fused_rows,
        downstream_result=downstream_result,
        warnings=_dedupe(warnings),
        limitations=limitations,
    )
    if request.persist_report:
        return fusion_store.persist_report(
            report,
            xau_vol_oi_input_rows=xau_input_conversion.rows,
        )
    return report


def _downstream_result(
    *,
    request: XauQuikStrikeFusionRequest,
    fusion_report_id: str,
    created_at: datetime,
    report_store: XauQuikStrikeFusionReportStore,
    xau_input_rows: list[XauFusionVolOiInputRow],
    conversion_status: XauFusionReportStatus,
    conversion_blocked_reasons: list[str],
    conversion_warnings: list[str],
    conservative_result: XauFusionDownstreamResult | None,
) -> XauFusionDownstreamResult | None:
    if (
        not request.create_xau_vol_oi_report
        and not request.create_xau_reaction_report
        and conservative_result is None
        and not conversion_blocked_reasons
        and not conversion_warnings
    ):
        return None

    notes = list(conservative_result.notes if conservative_result else [])
    notes.extend(conversion_warnings)
    xau_report_id = conservative_result.xau_vol_oi_report_id if conservative_result else None
    xau_reaction_report_id = (
        conservative_result.xau_reaction_report_id if conservative_result else None
    )
    xau_report_status = conservative_result.xau_report_status if conservative_result else None
    reaction_report_status = (
        conservative_result.reaction_report_status if conservative_result else None
    )
    reaction_row_count = conservative_result.reaction_row_count if conservative_result else None
    no_trade_count = conservative_result.no_trade_count if conservative_result else None
    all_reactions_no_trade = (
        conservative_result.all_reactions_no_trade if conservative_result else None
    )

    if conversion_status == XauFusionReportStatus.BLOCKED:
        notes.append(
            "Fused XAU Vol-OI input conversion is blocked because required mapping is unavailable."
        )
        notes.extend(conversion_blocked_reasons)
    elif conversion_status == XauFusionReportStatus.PARTIAL:
        notes.append(
            "Fused XAU Vol-OI input conversion is partial; blocked rows are documented."
        )
        notes.extend(conversion_blocked_reasons)
    elif xau_input_rows:
        notes.append(
            f"Fused XAU Vol-OI input conversion completed with {len(xau_input_rows)} rows."
        )

    if request.create_xau_vol_oi_report:
        xau_report, xau_notes = _create_xau_vol_oi_report(
            request=request,
            fusion_report_id=fusion_report_id,
            created_at=created_at,
            report_store=report_store,
            xau_input_rows=xau_input_rows,
        )
        notes.extend(xau_notes)
        if xau_report is not None:
            xau_report_id = xau_report.report_id
            xau_report_status = xau_report.status.value
    elif request.create_xau_reaction_report:
        notes.append("XAU Vol-OI report creation is required before XAU reaction linking.")

    if request.create_xau_reaction_report:
        if xau_report_id is None:
            notes.append(
                "XAU reaction report was not created because no linked XAU Vol-OI report exists."
            )
        else:
            reaction_report, reaction_notes = _create_xau_reaction_report(
                xau_report_id=xau_report_id,
                request=request,
                report_store=report_store,
            )
            notes.extend(reaction_notes)
            if reaction_report is not None:
                xau_reaction_report_id = reaction_report.report_id
                reaction_report_status = reaction_report.status.value
                reaction_row_count = reaction_report.reaction_count
                no_trade_count = reaction_report.no_trade_count
                all_reactions_no_trade = (
                    reaction_report.reaction_count > 0
                    and reaction_report.no_trade_count == reaction_report.reaction_count
                )
                if all_reactions_no_trade:
                    notes.append(
                        "XAU reaction rows remain NO_TRADE because confirmation context is "
                        "incomplete."
                    )

    return XauFusionDownstreamResult(
        xau_vol_oi_report_id=xau_report_id,
        xau_reaction_report_id=xau_reaction_report_id,
        xau_report_status=xau_report_status,
        reaction_report_status=reaction_report_status,
        reaction_row_count=reaction_row_count,
        no_trade_count=no_trade_count,
        all_reactions_no_trade=all_reactions_no_trade,
        notes=_dedupe(notes),
    )


def _create_xau_vol_oi_report(
    *,
    request: XauQuikStrikeFusionRequest,
    fusion_report_id: str,
    created_at: datetime,
    report_store: XauQuikStrikeFusionReportStore,
    xau_input_rows: list[XauFusionVolOiInputRow],
) -> tuple[object | None, list[str]]:
    eligible_rows = _downstream_xau_eligible_rows(xau_input_rows, created_at=created_at)
    if not eligible_rows:
        return None, [
            (
                "XAU Vol-OI report was not created because no converted row has both "
                "calendar expiry and open interest."
            )
        ]

    report_store.write_xau_vol_oi_input_rows(
        fusion_report_id,
        eligible_rows,
        filename="xau_vol_oi_report_input.csv",
    )
    input_path = report_store.artifact_path(fusion_report_id, "xau_vol_oi_report_input.csv")
    try:
        xau_request = _xau_report_request(
            request=request,
            input_path=input_path,
            created_at=created_at,
            rows=eligible_rows,
        )
        xau_report = XauReportOrchestrator(
            report_store=XauReportStore(reports_dir=report_store.reports_dir)
        ).run(xau_request)
    except Exception as exc:  # pragma: no cover - defensive operational boundary
        return None, [f"XAU Vol-OI report creation was not completed: {exc}"]
    return xau_report, [f"Linked XAU Vol-OI report {xau_report.report_id}."]


def _create_xau_reaction_report(
    *,
    xau_report_id: str,
    request: XauQuikStrikeFusionRequest,
    report_store: XauQuikStrikeFusionReportStore,
) -> tuple[object | None, list[str]]:
    try:
        reaction_request = XauReactionReportRequest(
            source_report_id=xau_report_id,
            current_price=request.xauusd_spot_reference or request.gc_futures_reference,
            research_only_acknowledged=True,
        )
        reaction_report = XauReactionReportOrchestrator(
            source_report_store=XauReportStore(reports_dir=report_store.reports_dir),
            reaction_report_store=XauReactionReportStore(reports_dir=report_store.reports_dir),
        ).run(reaction_request)
    except XauReactionReportBlockedError as exc:
        return None, [f"XAU reaction report was not created: {exc}"]
    except Exception as exc:  # pragma: no cover - defensive operational boundary
        return None, [f"XAU reaction report creation was not completed: {exc}"]
    no_trade_count = sum(
        1
        for reaction in reaction_report.reactions
        if reaction.reaction_label == XauReactionLabel.NO_TRADE
    )
    return reaction_report, [
        (
            f"Linked XAU reaction report {reaction_report.report_id} with "
            f"{no_trade_count} NO_TRADE rows."
        )
    ]


def _xau_report_request(
    *,
    request: XauQuikStrikeFusionRequest,
    input_path: Path,
    created_at: datetime,
    rows: list[XauFusionVolOiInputRow],
) -> XauVolOiReportRequest:
    spot_reference = (
        XauReferencePrice(
            source="xau_quikstrike_fusion_request",
            symbol="XAUUSD",
            price=request.xauusd_spot_reference,
            timestamp=created_at,
            reference_type=XauReferenceType.SPOT,
        )
        if request.xauusd_spot_reference is not None
        else None
    )
    futures_reference = (
        XauReferencePrice(
            source="xau_quikstrike_fusion_request",
            symbol="GC",
            price=request.gc_futures_reference,
            timestamp=created_at,
            reference_type=XauReferenceType.FUTURES,
        )
        if request.gc_futures_reference is not None
        else None
    )
    volatility_snapshot = _volatility_snapshot(request, created_at=created_at, rows=rows)
    return XauVolOiReportRequest(
        options_oi_file_path=input_path,
        session_date=created_at.date(),
        spot_reference=spot_reference,
        futures_reference=futures_reference,
        volatility_snapshot=volatility_snapshot,
    )


def _volatility_snapshot(
    request: XauQuikStrikeFusionRequest,
    *,
    created_at: datetime,
    rows: list[XauFusionVolOiInputRow],
) -> XauVolatilitySnapshot | None:
    if request.realized_volatility is None:
        return None
    days_to_expiry = _minimum_days_to_expiry(created_at, rows)
    if days_to_expiry is None:
        return None
    return XauVolatilitySnapshot(
        realized_volatility=request.realized_volatility,
        source=XauVolatilitySource.REALIZED_VOLATILITY,
        days_to_expiry=days_to_expiry,
        notes=["Realized-volatility context supplied by the fusion request."],
    )


def _minimum_days_to_expiry(
    created_at: datetime,
    rows: list[XauFusionVolOiInputRow],
) -> int | None:
    days: list[int] = []
    for row in rows:
        if row.expiry is None:
            continue
        try:
            expiry = datetime.fromisoformat(row.expiry[:10]).date()
        except ValueError:
            continue
        days.append(max(0, (expiry - created_at.date()).days))
    return min(days) if days else None


def _downstream_xau_eligible_rows(
    rows: list[XauFusionVolOiInputRow],
    *,
    created_at: datetime,
) -> list[XauFusionVolOiInputRow]:
    return [
        row.model_copy(update={"timestamp": row.timestamp or created_at})
        for row in rows
        if row.expiry is not None
        and _looks_like_calendar_date(row.expiry)
        and row.open_interest is not None
    ]


def _looks_like_calendar_date(value: str) -> bool:
    try:
        datetime.fromisoformat(value[:10])
    except ValueError:
        return False
    return True


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
