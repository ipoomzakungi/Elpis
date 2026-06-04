from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, date, datetime
from pathlib import Path

from src.models.xau import XauExpectedRangeSnapshot, XauOiWall, XauTimestampAlignmentStatus
from src.models.xau_daily_structural_map import XauDailyStructuralMapReportResult
from src.models.xau_quikstrike_fusion import XauFusionBasisState, XauFusionContextStatus
from src.xau_daily_structural_map.report_store import XauDailyStructuralMapReportStore
from src.xau_quikstrike_fusion.daily_structural_map import build_daily_structural_map


def generate_xau_daily_structural_map_report(
    *,
    session_date: date,
    source_product: str,
    traded_instrument: str,
    walls: Iterable[XauOiWall],
    expected_range_snapshot: XauExpectedRangeSnapshot | None = None,
    basis_state: XauFusionBasisState | None = None,
    manual_basis: float | None = None,
    gc_reference_price: float | None = None,
    traded_reference_price: float | None = None,
    session_open_price: float | None = None,
    session_open_source: str | None = None,
    map_id: str | None = None,
    created_at: datetime | None = None,
    expiration_code: str | None = None,
    option_product_code: str | None = None,
    futures_symbol: str | None = None,
    expiry_date: date | None = None,
    source_report_ids: list[str] | None = None,
    source_kind: str | None = None,
    output_dir: Path | None = None,
    report_store: XauDailyStructuralMapReportStore | None = None,
    overwrite_allowed: bool = False,
    basis_timestamp_alignment_status: XauTimestampAlignmentStatus = (
        XauTimestampAlignmentStatus.UNKNOWN
    ),
    wall_oi_change_by_id: Mapping[str, float | None] | None = None,
    wall_volume_by_id: Mapping[str, float | None] | None = None,
    limitations: Sequence[str] | None = None,
) -> XauDailyStructuralMapReportResult:
    """Build and persist one local research-only daily structural map report."""

    resolved_basis_state = basis_state or _basis_state_from_manual_inputs(
        manual_basis=manual_basis,
        expected_range_snapshot=expected_range_snapshot,
        gc_reference_price=gc_reference_price,
        traded_reference_price=traded_reference_price,
    )
    resolved_map_id = map_id or stable_xau_daily_structural_map_id(
        session_date=session_date,
        expiration_code=(
            expiration_code
            or (expected_range_snapshot.expiration_code if expected_range_snapshot else None)
        ),
    )
    daily_map = build_daily_structural_map(
        map_id=resolved_map_id,
        session_date=session_date,
        created_at=created_at or datetime.now(UTC),
        source_product=source_product,
        traded_instrument=traded_instrument,
        walls=walls,
        expected_range_snapshot=expected_range_snapshot,
        basis_state=resolved_basis_state,
        traded_reference_price=traded_reference_price,
        session_open_price=session_open_price,
        session_open_source=session_open_source,
        option_product_code=option_product_code,
        futures_symbol=futures_symbol,
        expiration_code=expiration_code,
        expiry_date=expiry_date,
        basis_timestamp_alignment_status=basis_timestamp_alignment_status,
        wall_oi_change_by_id=wall_oi_change_by_id,
        wall_volume_by_id=wall_volume_by_id,
        limitations=limitations,
    )
    store = report_store or XauDailyStructuralMapReportStore(reports_dir=output_dir)
    return store.persist_map(
        daily_map,
        source_report_ids=source_report_ids,
        source_kind=source_kind,
        overwrite_allowed=overwrite_allowed,
    )


def stable_xau_daily_structural_map_id(
    *,
    session_date: date,
    expiration_code: str | None,
) -> str:
    expiration = expiration_code or "unknown_expiry"
    safe_expiration = "".join(
        character for character in expiration if character.isalnum() or character in "_-"
    )
    return f"xau_daily_structural_map_{session_date.isoformat()}_{safe_expiration}"


def _basis_state_from_manual_inputs(
    *,
    manual_basis: float | None,
    expected_range_snapshot: XauExpectedRangeSnapshot | None,
    gc_reference_price: float | None,
    traded_reference_price: float | None,
) -> XauFusionBasisState | None:
    if manual_basis is None:
        return None
    resolved_gc_reference = gc_reference_price or (
        expected_range_snapshot.reference_futures_price if expected_range_snapshot else None
    )
    resolved_traded_reference = traded_reference_price
    if resolved_gc_reference is None and resolved_traded_reference is not None:
        resolved_gc_reference = resolved_traded_reference + manual_basis
    if resolved_traded_reference is None and resolved_gc_reference is not None:
        resolved_traded_reference = resolved_gc_reference - manual_basis
    if resolved_gc_reference is None or resolved_traded_reference is None:
        return XauFusionBasisState(
            status=XauFusionContextStatus.UNAVAILABLE,
            calculation_note=(
                "Manual basis was supplied, but a futures or traded reference was missing; "
                "spot-equivalent strike levels were not computed."
            ),
            warnings=["Basis mapping unavailable."],
        )
    return XauFusionBasisState(
        status=XauFusionContextStatus.AVAILABLE,
        xauusd_spot_reference=resolved_traded_reference,
        gc_futures_reference=resolved_gc_reference,
        basis_points=manual_basis,
        calculation_note="Manual basis supplied for local structural-map research.",
    )


__all__ = [
    "generate_xau_daily_structural_map_report",
    "stable_xau_daily_structural_map_id",
]
