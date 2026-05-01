from dataclasses import dataclass
from itertools import groupby
from operator import attrgetter

from src.models.xau import (
    XauBasisSnapshot,
    XauFreshnessFactorStatus,
    XauOiWall,
    XauOptionsOiRow,
    XauOptionType,
    XauVolatilitySource,
    XauWallType,
)
from src.xau.basis import map_strike_to_spot_equivalent


@dataclass(frozen=True)
class XauFreshnessScore:
    factor: float
    status: XauFreshnessFactorStatus
    notes: list[str]


def wall_scoring_inputs_available(rows: list[XauOptionsOiRow]) -> bool:
    """Return whether normalized rows exist for wall scoring."""

    return bool(rows)


def compute_expiry_weight(days_to_expiry: int) -> float:
    """Compute a bounded near-expiry weight.

    Nearer expiries receive a larger weight, while long-dated expiries keep a
    visible floor so their OI is not silently discarded.
    """

    if days_to_expiry < 0:
        raise ValueError("days_to_expiry must be greater than or equal to 0")
    raw_weight = 1.0 / (1.0 + (days_to_expiry / 30.0))
    return max(0.25, min(1.0, raw_weight))


def compute_freshness_factor(
    oi_change: float | None,
    volume: float | None,
) -> XauFreshnessScore:
    """Score optional recent-positioning evidence from OI change and volume."""

    if oi_change is None and volume is None:
        return XauFreshnessScore(
            factor=1.0,
            status=XauFreshnessFactorStatus.UNAVAILABLE,
            notes=["Freshness evidence unavailable; oi_change or volume was not imported."],
        )
    if (oi_change or 0.0) > 0 or (volume or 0.0) > 0:
        return XauFreshnessScore(
            factor=1.1,
            status=XauFreshnessFactorStatus.CONFIRMED,
            notes=["Recent OI change or volume confirms activity at this wall."],
        )
    if (oi_change or 0.0) < 0 and (volume or 0.0) <= 0:
        return XauFreshnessScore(
            factor=0.9,
            status=XauFreshnessFactorStatus.STALE,
            notes=["OI change is negative and no volume confirms fresh activity."],
        )
    return XauFreshnessScore(
        factor=1.0,
        status=XauFreshnessFactorStatus.NEUTRAL,
        notes=["Freshness evidence is neutral at this wall."],
    )


def classify_wall_type(option_types: list[XauOptionType]) -> XauWallType:
    """Classify a grouped strike/expiry by its put/call composition."""

    normalized = set(option_types)
    has_call = XauOptionType.CALL in normalized
    has_put = XauOptionType.PUT in normalized
    if has_call and has_put:
        return XauWallType.MIXED
    if has_call and not has_put and XauOptionType.UNKNOWN not in normalized:
        return XauWallType.CALL
    if has_put and not has_call and XauOptionType.UNKNOWN not in normalized:
        return XauWallType.PUT
    return XauWallType.UNKNOWN


def build_oi_walls(
    rows: list[XauOptionsOiRow],
    *,
    basis_snapshot: XauBasisSnapshot | None = None,
    expected_range: object | None = None,
    min_wall_score: float = 0.0,
) -> list[XauOiWall]:
    """Build transparent OI wall rows grouped by expiry and strike."""

    if not rows:
        return []
    total_oi_by_expiry = _total_oi_by_expiry(rows)
    sorted_rows = sorted(rows, key=attrgetter("expiry", "strike"))
    walls: list[XauOiWall] = []
    for (expiry, strike), group_iter in groupby(sorted_rows, key=attrgetter("expiry", "strike")):
        group = list(group_iter)
        total_expiry_oi = total_oi_by_expiry[expiry]
        open_interest = sum(row.open_interest for row in group)
        if total_expiry_oi <= 0 or open_interest <= 0:
            continue

        option_type = classify_wall_type([row.option_type for row in group])
        oi_share = open_interest / total_expiry_oi
        expiry_weight = compute_expiry_weight(min(row.days_to_expiry for row in group))
        oi_change = _sum_optional(row.oi_change for row in group)
        volume = _sum_optional(row.volume for row in group)
        freshness = compute_freshness_factor(oi_change=oi_change, volume=volume)
        wall_score = oi_share * expiry_weight * freshness.factor
        if wall_score < min_wall_score:
            continue

        spot_equivalent_level, basis, basis_limitation = _map_spot_equivalent(
            strike,
            basis_snapshot,
        )
        limitations = _wall_limitations(
            group,
            basis_limitation=basis_limitation,
            expected_range=expected_range,
        )
        walls.append(
            XauOiWall(
                wall_id=_wall_id(expiry, strike, option_type),
                expiry=expiry,
                strike=strike,
                spot_equivalent_level=spot_equivalent_level,
                basis=basis,
                option_type=option_type,
                open_interest=open_interest,
                total_expiry_open_interest=total_expiry_oi,
                oi_share=oi_share,
                expiry_weight=expiry_weight,
                freshness_factor=freshness.factor,
                wall_score=wall_score,
                freshness_status=freshness.status,
                notes=[
                    "wall_score = oi_share * expiry_weight * freshness_factor",
                    *freshness.notes,
                ],
                limitations=limitations,
            )
        )
    return sorted(walls, key=lambda wall: wall.wall_score, reverse=True)


def _total_oi_by_expiry(rows: list[XauOptionsOiRow]) -> dict[object, float]:
    totals: dict[object, float] = {}
    for row in rows:
        totals[row.expiry] = totals.get(row.expiry, 0.0) + row.open_interest
    return totals


def _sum_optional(values: object) -> float | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return float(sum(present))


def _map_spot_equivalent(
    strike: float,
    basis_snapshot: XauBasisSnapshot | None,
) -> tuple[float | None, float | None, str | None]:
    if basis_snapshot is None or not basis_snapshot.mapping_available:
        return (
            None,
            None,
            "Spot-equivalent mapping unavailable because basis inputs are missing.",
        )
    basis = basis_snapshot.basis
    if basis is None:
        return (
            None,
            None,
            "Spot-equivalent mapping unavailable because basis is unavailable.",
        )
    return map_strike_to_spot_equivalent(strike, basis), basis, None


def _wall_limitations(
    group: list[XauOptionsOiRow],
    *,
    basis_limitation: str | None,
    expected_range: object | None,
) -> list[str]:
    limitations: list[str] = []
    if basis_limitation:
        limitations.append(basis_limitation)
    if all(row.oi_change is None and row.volume is None for row in group):
        limitations.append("Freshness factor is neutral because oi_change or volume is missing.")
    if all(row.implied_volatility is None for row in group) and _range_unavailable(expected_range):
        limitations.append("IV context is unavailable for this wall.")
    if any(row.option_type == XauOptionType.UNKNOWN for row in group):
        limitations.append("Put/call split is unknown for at least one source row.")
    return limitations


def _range_unavailable(expected_range: object | None) -> bool:
    if expected_range is None:
        return True
    return getattr(expected_range, "source", None) == XauVolatilitySource.UNAVAILABLE


def _wall_id(expiry: object, strike: float, option_type: XauWallType) -> str:
    strike_text = f"{strike:g}".replace(".", "_")
    return f"{expiry}_{strike_text}_{option_type.value}"
