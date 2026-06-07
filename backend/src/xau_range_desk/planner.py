from __future__ import annotations

from collections.abc import Iterable

from src.models.xau_range_desk import (
    RANGE_DESK_NO_SIGNAL_REASON,
    XauRangeDeskBasisSnapshot,
    XauRangeDeskLevelInput,
    XauRangeDeskLevelKind,
    XauRangeDeskMappedLevel,
    XauRangeDeskMappedWall,
    XauRangeDeskPlan,
    XauRangeDeskPlanRequest,
    XauRangeDeskReadiness,
    XauRangeDeskTargetPlan,
    XauRangeDeskZone,
    XauRangeDeskZoneKind,
)


def build_xau_range_desk_plan(request: XauRangeDeskPlanRequest) -> XauRangeDeskPlan:
    """Map futures-side CME levels into traded-instrument planning levels."""

    diff_points = request.future_reference_price - request.traded_reference_price
    traded_offset = request.traded_reference_price - request.future_reference_price
    basis_snapshot = XauRangeDeskBasisSnapshot(
        future_reference_price=request.future_reference_price,
        traded_reference_price=request.traded_reference_price,
        diff_points=diff_points,
        traded_offset=traded_offset,
        formula="mapped_traded_level = futures_level + traded_offset",
    )
    mapped_levels = [
        _mapped_level(level, request.traded_reference_price, traded_offset)
        for level in _ordered_levels(request.levels)
    ]
    by_label = {level.label: level for level in mapped_levels}
    mapped_walls = [
        XauRangeDeskMappedWall(
            wall_id=wall.wall_id,
            wall_type=wall.wall_type,
            futures_level=wall.futures_level,
            mapped_traded_level=_map_level(wall.futures_level, traded_offset),
            distance_from_traded_reference=(
                _map_level(wall.futures_level, traded_offset)
                - request.traded_reference_price
            ),
            open_interest=wall.open_interest,
            oi_change=wall.oi_change,
            volume=wall.volume,
            source=wall.source,
        )
        for wall in sorted(request.oi_walls, key=lambda item: item.futures_level)
    ]
    zones = _zones(by_label)
    target_plans = _target_plans(
        by_label,
        mapped_walls,
        session_open_price=request.session_open_price,
    )
    missing_inputs = _missing_inputs(by_label)
    limitations = _limitations(request, missing_inputs)
    readiness = _readiness(missing_inputs, mapped_walls)
    return XauRangeDeskPlan(
        session_date=request.session_date,
        traded_instrument=request.traded_instrument,
        futures_symbol=request.futures_symbol,
        readiness=readiness,
        basis_snapshot=basis_snapshot,
        block_size_points=_block_size(by_label),
        futures_levels=mapped_levels,
        traded_levels=mapped_levels,
        mapped_oi_walls=mapped_walls,
        zones=zones,
        target_plans=target_plans,
        missing_inputs=missing_inputs,
        limitations=limitations,
        no_signal_reasons=[RANGE_DESK_NO_SIGNAL_REASON],
        research_only=True,
        signal_allowed=False,
    )


def _mapped_level(
    level: XauRangeDeskLevelInput,
    traded_reference_price: float,
    traded_offset: float,
) -> XauRangeDeskMappedLevel:
    mapped = _map_level(level.futures_level, traded_offset)
    return XauRangeDeskMappedLevel(
        label=level.label,
        futures_level=level.futures_level,
        mapped_traded_level=mapped,
        distance_from_traded_reference=mapped - traded_reference_price,
        source=level.source,
    )


def _ordered_levels(
    levels: Iterable[XauRangeDeskLevelInput],
) -> list[XauRangeDeskLevelInput]:
    order = {
        XauRangeDeskLevelKind.LOWER_3SD: 0,
        XauRangeDeskLevelKind.LOWER_2SD: 1,
        XauRangeDeskLevelKind.LOWER_1SD: 2,
        XauRangeDeskLevelKind.MEAN: 3,
        XauRangeDeskLevelKind.SESSION_OPEN: 4,
        XauRangeDeskLevelKind.UPPER_1SD: 5,
        XauRangeDeskLevelKind.UPPER_2SD: 6,
        XauRangeDeskLevelKind.UPPER_3SD: 7,
    }
    return sorted(levels, key=lambda level: order.get(level.label, 99))


def _zones(
    by_label: dict[XauRangeDeskLevelKind, XauRangeDeskMappedLevel],
) -> list[XauRangeDeskZone]:
    zones: list[XauRangeDeskZone] = []
    lower_1sd = by_label.get(XauRangeDeskLevelKind.LOWER_1SD)
    upper_1sd = by_label.get(XauRangeDeskLevelKind.UPPER_1SD)
    if lower_1sd and upper_1sd:
        zones.append(
            XauRangeDeskZone(
                zone=XauRangeDeskZoneKind.NO_TRADE_INSIDE_1SD,
                lower_traded_level=lower_1sd.mapped_traded_level,
                upper_traded_level=upper_1sd.mapped_traded_level,
                meaning="Inside 1SD is monitor-only planning context.",
            )
        )
    lower_3sd = by_label.get(XauRangeDeskLevelKind.LOWER_3SD)
    lower_2sd = by_label.get(XauRangeDeskLevelKind.LOWER_2SD)
    if lower_3sd and lower_2sd:
        zones.append(
            XauRangeDeskZone(
                zone=XauRangeDeskZoneKind.LOWER_STRETCH_2SD_TO_3SD,
                lower_traded_level=lower_3sd.mapped_traded_level,
                upper_traded_level=lower_2sd.mapped_traded_level,
                meaning="Lower 2SD-3SD stretch zone for research review only.",
            )
        )
    upper_2sd = by_label.get(XauRangeDeskLevelKind.UPPER_2SD)
    upper_3sd = by_label.get(XauRangeDeskLevelKind.UPPER_3SD)
    if upper_2sd and upper_3sd:
        zones.append(
            XauRangeDeskZone(
                zone=XauRangeDeskZoneKind.UPPER_STRETCH_2SD_TO_3SD,
                lower_traded_level=upper_2sd.mapped_traded_level,
                upper_traded_level=upper_3sd.mapped_traded_level,
                meaning="Upper 2SD-3SD stretch zone for research review only.",
            )
        )
    return zones


def _target_plans(
    by_label: dict[XauRangeDeskLevelKind, XauRangeDeskMappedLevel],
    mapped_walls: list[XauRangeDeskMappedWall],
    *,
    session_open_price: float | None,
) -> list[XauRangeDeskTargetPlan]:
    lower_1sd = by_label.get(XauRangeDeskLevelKind.LOWER_1SD)
    upper_1sd = by_label.get(XauRangeDeskLevelKind.UPPER_1SD)
    lower_3sd = by_label.get(XauRangeDeskLevelKind.LOWER_3SD)
    upper_3sd = by_label.get(XauRangeDeskLevelKind.UPPER_3SD)
    mean = by_label.get(XauRangeDeskLevelKind.MEAN)
    mean_or_open = mean.mapped_traded_level if mean else session_open_price
    return [
        XauRangeDeskTargetPlan(
            side="short_reversion_research_plan",
            target_1=upper_1sd.mapped_traded_level if upper_1sd else None,
            target_2=mean_or_open,
            target_3=_nearest_wall_below(mapped_walls, mean_or_open),
            invalidation_reference=upper_3sd.mapped_traded_level if upper_3sd else None,
            planning_note="Planning-only levels; no entry, order, PnL, or signal is produced.",
        ),
        XauRangeDeskTargetPlan(
            side="long_reversion_research_plan",
            target_1=lower_1sd.mapped_traded_level if lower_1sd else None,
            target_2=mean_or_open,
            target_3=_nearest_wall_above(mapped_walls, mean_or_open),
            invalidation_reference=lower_3sd.mapped_traded_level if lower_3sd else None,
            planning_note="Planning-only levels; no entry, order, PnL, or signal is produced.",
        ),
    ]


def _nearest_wall_below(
    mapped_walls: list[XauRangeDeskMappedWall],
    reference: float | None,
) -> float | None:
    if reference is None:
        return None
    below = [
        wall.mapped_traded_level
        for wall in mapped_walls
        if wall.mapped_traded_level < reference
    ]
    return max(below) if below else None


def _nearest_wall_above(
    mapped_walls: list[XauRangeDeskMappedWall],
    reference: float | None,
) -> float | None:
    if reference is None:
        return None
    above = [
        wall.mapped_traded_level
        for wall in mapped_walls
        if wall.mapped_traded_level > reference
    ]
    return min(above) if above else None


def _missing_inputs(
    by_label: dict[XauRangeDeskLevelKind, XauRangeDeskMappedLevel],
) -> list[str]:
    required = [
        XauRangeDeskLevelKind.LOWER_1SD,
        XauRangeDeskLevelKind.UPPER_1SD,
        XauRangeDeskLevelKind.LOWER_2SD,
        XauRangeDeskLevelKind.UPPER_2SD,
        XauRangeDeskLevelKind.LOWER_3SD,
        XauRangeDeskLevelKind.UPPER_3SD,
    ]
    return [
        f"levels.{label.value}"
        for label in required
        if label not in by_label
    ]


def _limitations(
    request: XauRangeDeskPlanRequest,
    missing_inputs: list[str],
) -> list[str]:
    limitations = [
        (
            "Range Desk output maps CME futures levels to the traded instrument only; "
            "it is not a signal."
        )
    ]
    if missing_inputs:
        limitations.append("Missing SD levels prevent a complete Range Desk table.")
    if not request.oi_walls:
        limitations.append("No OI wall inputs were supplied, so OI wall targets are unavailable.")
    if request.session_open_price is None:
        limitations.append("Session open was not supplied; mean target fallback is limited.")
    return limitations


def _readiness(
    missing_inputs: list[str],
    mapped_walls: list[XauRangeDeskMappedWall],
) -> XauRangeDeskReadiness:
    if missing_inputs:
        return XauRangeDeskReadiness.PARTIAL
    if not mapped_walls:
        return XauRangeDeskReadiness.PARTIAL
    return XauRangeDeskReadiness.READY


def _block_size(
    by_label: dict[XauRangeDeskLevelKind, XauRangeDeskMappedLevel],
) -> float | None:
    lower_1sd = by_label.get(XauRangeDeskLevelKind.LOWER_1SD)
    upper_1sd = by_label.get(XauRangeDeskLevelKind.UPPER_1SD)
    if lower_1sd is None or upper_1sd is None:
        return None
    return abs(upper_1sd.mapped_traded_level - lower_1sd.mapped_traded_level) / 2


def _map_level(futures_level: float, traded_offset: float) -> float:
    return futures_level + traded_offset


__all__ = ["build_xau_range_desk_plan"]
