"""Build research-only XAU daily structural maps."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime

from src.models.xau import (
    XauBasisSource,
    XauDailyStructuralMap,
    XauDailyStructuralMapReadiness,
    XauDailyStructuralMapWall,
    XauDailyStructuralMapWallMappingStatus,
    XauExpectedRangeSnapshot,
    XauExpectedRangeSource,
    XauOiWall,
    XauTimestampAlignmentStatus,
)
from src.models.xau_quikstrike_fusion import XauFusionBasisState, XauFusionContextStatus
from src.xau_quikstrike_fusion.basis import calculate_spot_equivalent_level

MAP_ONLY_NO_SIGNAL_REASON = "Feature 018 is map-only; signal generation is disabled."
BASIS_UNAVAILABLE_NO_SIGNAL_REASON = "Basis mapping unavailable."
EXPECTED_RANGE_UNAVAILABLE_NO_SIGNAL_REASON = "Expected range unavailable."
SESSION_OPEN_UNAVAILABLE_NO_SIGNAL_REASON = "Session open unavailable."
NO_WALLS_NO_SIGNAL_REASON = "No OI walls available."


def build_daily_structural_map(
    *,
    map_id: str,
    session_date: date,
    created_at: datetime,
    source_product: str,
    traded_instrument: str,
    walls: Iterable[XauOiWall],
    expected_range_snapshot: XauExpectedRangeSnapshot | None = None,
    basis_state: XauFusionBasisState | None = None,
    traded_reference_price: float | None = None,
    session_open_price: float | None = None,
    session_open_source: str | None = None,
    option_product_code: str | None = None,
    futures_symbol: str | None = None,
    expiration_code: str | None = None,
    expiry_date: date | None = None,
    basis_timestamp_alignment_status: XauTimestampAlignmentStatus = (
        XauTimestampAlignmentStatus.UNKNOWN
    ),
    wall_oi_change_by_id: Mapping[str, float | None] | None = None,
    wall_volume_by_id: Mapping[str, float | None] | None = None,
    boundary_tolerance_points: float = 5.0,
    limitations: Sequence[str] | None = None,
) -> XauDailyStructuralMap:
    """Create one map-only daily structural map from current research context."""

    wall_list = list(walls)
    basis_available = _basis_available(basis_state)
    basis_points = basis_state.basis_points if basis_available and basis_state else None
    resolved_traded_reference = _resolve_traded_reference_price(
        traded_reference_price=traded_reference_price,
        basis_state=basis_state,
    )
    resolved_expiration_code = _resolve_string(
        expiration_code,
        expected_range_snapshot.expiration_code if expected_range_snapshot else None,
    )
    resolved_expiry_date = expiry_date or (
        expected_range_snapshot.expiry_date if expected_range_snapshot else None
    )
    resolved_option_product_code = _resolve_string(
        option_product_code,
        expected_range_snapshot.option_product_code if expected_range_snapshot else None,
    )
    resolved_futures_symbol = _resolve_string(
        futures_symbol,
        expected_range_snapshot.futures_symbol if expected_range_snapshot else None,
    )
    resolved_reference_futures_price = _resolve_reference_futures_price(
        expected_range_snapshot=expected_range_snapshot,
        basis_state=basis_state,
    )

    no_signal_reasons = _no_signal_reasons(
        wall_count=len(wall_list),
        basis_available=basis_available,
        expected_range_snapshot=expected_range_snapshot,
        session_open_price=session_open_price,
    )
    map_limitations = _map_limitations(
        limitations=limitations,
        expected_range_snapshot=expected_range_snapshot,
        basis_state=basis_state,
    )
    map_walls = [
        _build_map_wall(
            wall=wall,
            expiration_code=resolved_expiration_code,
            basis_state=basis_state,
            traded_reference_price=resolved_traded_reference,
            session_open_price=session_open_price,
            expected_range_snapshot=expected_range_snapshot,
            boundary_tolerance_points=boundary_tolerance_points,
            oi_change=(
                wall_oi_change_by_id.get(wall.wall_id)
                if wall_oi_change_by_id is not None
                else None
            ),
            volume=(
                wall_volume_by_id.get(wall.wall_id)
                if wall_volume_by_id is not None
                else None
            ),
        )
        for wall in wall_list
    ]

    return XauDailyStructuralMap(
        map_id=map_id,
        session_date=session_date,
        created_at=created_at,
        source_product=source_product,
        option_product_code=resolved_option_product_code,
        futures_symbol=resolved_futures_symbol,
        expiration_code=resolved_expiration_code,
        expiry_date=resolved_expiry_date,
        reference_futures_price=resolved_reference_futures_price,
        traded_instrument=traded_instrument,
        traded_reference_price=resolved_traded_reference,
        basis=basis_points,
        basis_source=XauBasisSource.COMPUTED if basis_available else XauBasisSource.UNAVAILABLE,
        basis_mapping_available=basis_available,
        basis_timestamp_alignment_status=basis_timestamp_alignment_status,
        expected_range_source=(
            expected_range_snapshot.range_source if expected_range_snapshot else None
        ),
        report_level_iv=(
            expected_range_snapshot.report_level_iv if expected_range_snapshot else None
        ),
        fractional_dte=(
            expected_range_snapshot.fractional_dte if expected_range_snapshot else None
        ),
        lower_1sd=expected_range_snapshot.lower_1sd if expected_range_snapshot else None,
        upper_1sd=expected_range_snapshot.upper_1sd if expected_range_snapshot else None,
        lower_2sd=expected_range_snapshot.lower_2sd if expected_range_snapshot else None,
        upper_2sd=expected_range_snapshot.upper_2sd if expected_range_snapshot else None,
        lower_3sd=expected_range_snapshot.lower_3sd if expected_range_snapshot else None,
        upper_3sd=expected_range_snapshot.upper_3sd if expected_range_snapshot else None,
        session_open_price=session_open_price,
        session_open_source=session_open_source,
        session_open_available=session_open_price is not None,
        open_side_vs_1sd=_open_side_vs_1sd(
            session_open_price=session_open_price,
            expected_range_snapshot=expected_range_snapshot,
            basis_points=basis_points,
        ),
        open_distance_points=_distance(session_open_price, resolved_traded_reference),
        wall_count=len(map_walls),
        walls=map_walls,
        data_quality_state=_readiness_state(
            wall_count=len(wall_list),
            basis_available=basis_available,
            expected_range_snapshot=expected_range_snapshot,
            session_open_price=session_open_price,
        ),
        signal_allowed=False,
        no_signal_reasons=no_signal_reasons,
        limitations=map_limitations,
    )


def _build_map_wall(
    *,
    wall: XauOiWall,
    expiration_code: str | None,
    basis_state: XauFusionBasisState | None,
    traded_reference_price: float | None,
    session_open_price: float | None,
    expected_range_snapshot: XauExpectedRangeSnapshot | None,
    boundary_tolerance_points: float,
    oi_change: float | None,
    volume: float | None,
) -> XauDailyStructuralMapWall:
    spot_equivalent_level = (
        calculate_spot_equivalent_level(wall.strike, basis_state)
        if basis_state is not None
        else None
    )
    mapping_status = (
        XauDailyStructuralMapWallMappingStatus.MAPPED
        if spot_equivalent_level is not None
        else XauDailyStructuralMapWallMappingStatus.BASIS_UNAVAILABLE
    )
    wall_limitations = list(wall.limitations)
    if spot_equivalent_level is None:
        wall_limitations.append(BASIS_UNAVAILABLE_NO_SIGNAL_REASON)

    return XauDailyStructuralMapWall(
        wall_id=wall.wall_id,
        expiry=wall.expiry,
        expiration_code=expiration_code,
        strike=wall.strike,
        wall_type=wall.option_type,
        open_interest=wall.open_interest,
        oi_change=oi_change,
        volume=volume,
        wall_score=wall.wall_score,
        freshness_state=wall.freshness_status,
        spot_equivalent_level=spot_equivalent_level,
        distance_to_traded_price=_distance(spot_equivalent_level, traded_reference_price),
        distance_to_session_open=_distance(spot_equivalent_level, session_open_price),
        inside_1sd=_inside_range(
            wall.strike,
            expected_range_snapshot.lower_1sd if expected_range_snapshot else None,
            expected_range_snapshot.upper_1sd if expected_range_snapshot else None,
        ),
        inside_2sd=_inside_range(
            wall.strike,
            expected_range_snapshot.lower_2sd if expected_range_snapshot else None,
            expected_range_snapshot.upper_2sd if expected_range_snapshot else None,
        ),
        near_expected_range_boundary=_near_expected_range_boundary(
            wall.strike,
            expected_range_snapshot=expected_range_snapshot,
            tolerance_points=boundary_tolerance_points,
        ),
        open_side_vs_wall=_open_side_vs_wall(session_open_price, spot_equivalent_level),
        mapping_status=mapping_status,
        limitations=wall_limitations,
    )


def _basis_available(basis_state: XauFusionBasisState | None) -> bool:
    return (
        basis_state is not None
        and basis_state.status == XauFusionContextStatus.AVAILABLE
        and basis_state.basis_points is not None
    )


def _resolve_traded_reference_price(
    *,
    traded_reference_price: float | None,
    basis_state: XauFusionBasisState | None,
) -> float | None:
    if traded_reference_price is not None:
        return traded_reference_price
    if basis_state and basis_state.status == XauFusionContextStatus.AVAILABLE:
        return basis_state.xauusd_spot_reference
    return None


def _resolve_reference_futures_price(
    *,
    expected_range_snapshot: XauExpectedRangeSnapshot | None,
    basis_state: XauFusionBasisState | None,
) -> float | None:
    if expected_range_snapshot and expected_range_snapshot.reference_futures_price is not None:
        return expected_range_snapshot.reference_futures_price
    if basis_state and basis_state.status == XauFusionContextStatus.AVAILABLE:
        return basis_state.gc_futures_reference
    return None


def _readiness_state(
    *,
    wall_count: int,
    basis_available: bool,
    expected_range_snapshot: XauExpectedRangeSnapshot | None,
    session_open_price: float | None,
) -> XauDailyStructuralMapReadiness:
    range_available = _range_available(expected_range_snapshot)
    if wall_count == 0 or (not basis_available and not range_available):
        return XauDailyStructuralMapReadiness.BLOCKED_INSUFFICIENT_CONTEXT
    if not basis_available:
        return XauDailyStructuralMapReadiness.PARTIAL_MISSING_BASIS
    if not range_available:
        return XauDailyStructuralMapReadiness.PARTIAL_MISSING_EXPECTED_RANGE
    if session_open_price is None:
        return XauDailyStructuralMapReadiness.PARTIAL_MISSING_SESSION_OPEN
    return XauDailyStructuralMapReadiness.STRUCTURAL_MAP_READY


def _range_available(expected_range_snapshot: XauExpectedRangeSnapshot | None) -> bool:
    if expected_range_snapshot is None:
        return False
    return expected_range_snapshot.range_source != XauExpectedRangeSource.UNAVAILABLE


def _no_signal_reasons(
    *,
    wall_count: int,
    basis_available: bool,
    expected_range_snapshot: XauExpectedRangeSnapshot | None,
    session_open_price: float | None,
) -> list[str]:
    reasons = [MAP_ONLY_NO_SIGNAL_REASON]
    if wall_count == 0:
        reasons.append(NO_WALLS_NO_SIGNAL_REASON)
    if not basis_available:
        reasons.append(BASIS_UNAVAILABLE_NO_SIGNAL_REASON)
    if not _range_available(expected_range_snapshot):
        reasons.append(EXPECTED_RANGE_UNAVAILABLE_NO_SIGNAL_REASON)
    if session_open_price is None:
        reasons.append(SESSION_OPEN_UNAVAILABLE_NO_SIGNAL_REASON)
    return _dedupe(reasons)


def _map_limitations(
    *,
    limitations: Sequence[str] | None,
    expected_range_snapshot: XauExpectedRangeSnapshot | None,
    basis_state: XauFusionBasisState | None,
) -> list[str]:
    output = list(limitations or [])
    if expected_range_snapshot is not None:
        output.extend(expected_range_snapshot.limitations)
    if basis_state is not None:
        output.extend(basis_state.warnings)
    return _dedupe(output)


def _inside_range(
    value: float,
    lower: float | None,
    upper: float | None,
) -> bool | None:
    if lower is None or upper is None:
        return None
    return lower <= value <= upper


def _near_expected_range_boundary(
    value: float,
    *,
    expected_range_snapshot: XauExpectedRangeSnapshot | None,
    tolerance_points: float,
) -> bool | None:
    if expected_range_snapshot is None or not _range_available(expected_range_snapshot):
        return None
    boundaries = [
        expected_range_snapshot.lower_1sd,
        expected_range_snapshot.upper_1sd,
        expected_range_snapshot.lower_2sd,
        expected_range_snapshot.upper_2sd,
        expected_range_snapshot.lower_3sd,
        expected_range_snapshot.upper_3sd,
    ]
    available = [boundary for boundary in boundaries if boundary is not None]
    if not available:
        return None
    return any(abs(value - boundary) <= tolerance_points for boundary in available)


def _open_side_vs_1sd(
    *,
    session_open_price: float | None,
    expected_range_snapshot: XauExpectedRangeSnapshot | None,
    basis_points: float | None,
) -> str | None:
    if (
        session_open_price is None
        or expected_range_snapshot is None
        or expected_range_snapshot.lower_1sd is None
        or expected_range_snapshot.upper_1sd is None
    ):
        return None
    lower_1sd = expected_range_snapshot.lower_1sd
    upper_1sd = expected_range_snapshot.upper_1sd
    if basis_points is not None:
        lower_1sd -= basis_points
        upper_1sd -= basis_points
    if session_open_price < lower_1sd:
        return "below_1sd"
    if session_open_price > upper_1sd:
        return "above_1sd"
    return "inside_1sd"


def _open_side_vs_wall(
    session_open_price: float | None,
    spot_equivalent_level: float | None,
) -> str | None:
    if session_open_price is None or spot_equivalent_level is None:
        return None
    if session_open_price > spot_equivalent_level:
        return "above_wall"
    if session_open_price < spot_equivalent_level:
        return "below_wall"
    return "at_wall"


def _distance(level: float | None, reference: float | None) -> float | None:
    if level is None or reference is None:
        return None
    return level - reference


def _resolve_string(*values: str | None) -> str | None:
    for value in values:
        if value:
            normalized = " ".join(value.split())
            if normalized:
                return normalized
    return None


def _dedupe(values: Sequence[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = " ".join(str(value).split())
        if normalized and normalized not in seen:
            output.append(normalized)
            seen.add(normalized)
    return output


__all__ = [
    "BASIS_UNAVAILABLE_NO_SIGNAL_REASON",
    "EXPECTED_RANGE_UNAVAILABLE_NO_SIGNAL_REASON",
    "MAP_ONLY_NO_SIGNAL_REASON",
    "NO_WALLS_NO_SIGNAL_REASON",
    "SESSION_OPEN_UNAVAILABLE_NO_SIGNAL_REASON",
    "build_daily_structural_map",
]
