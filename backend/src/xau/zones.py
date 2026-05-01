from src.models.xau import (
    XauExpectedRange,
    XauFreshnessFactorStatus,
    XauOiWall,
    XauWallType,
    XauZone,
    XauZoneConfidence,
    XauZoneType,
)

RESEARCH_ZONE_NOTE = "XAU zones are research annotations only and not trading signals."
LOW_SCORE_THRESHOLD = 0.05
SQUEEZE_SCORE_THRESHOLD = 0.20


def zone_classification_inputs_available(walls: list[XauOiWall]) -> bool:
    """Return whether wall rows exist for zone classification."""

    return bool(walls)


def classify_zones(
    walls: list[XauOiWall],
    *,
    expected_range: XauExpectedRange | None = None,
    reference_price: float | None = None,
) -> list[XauZone]:
    """Classify transparent research zones from scored wall rows."""

    if not walls:
        return [
            _zone(
                zone_id="no_trade_no_walls",
                zone_type=XauZoneType.NO_TRADE_ZONE,
                confidence=XauZoneConfidence.UNAVAILABLE,
                no_trade_warning=True,
                notes=[
                    RESEARCH_ZONE_NOTE,
                    "No usable OI walls are available for zone classification.",
                ],
            )
        ]

    reference = reference_price or (expected_range.reference_price if expected_range else None)
    zones: list[XauZone] = []
    for wall in sorted(walls, key=lambda item: item.wall_score, reverse=True):
        zones.extend(_zones_for_wall(wall, reference=reference, expected_range=expected_range))
    return zones


def _zones_for_wall(
    wall: XauOiWall,
    *,
    reference: float | None,
    expected_range: XauExpectedRange | None,
) -> list[XauZone]:
    if wall.spot_equivalent_level is None:
        return [
            _zone(
                zone_id=f"no_trade_{wall.wall_id}",
                zone_type=XauZoneType.NO_TRADE_ZONE,
                linked_wall_ids=[wall.wall_id],
                wall_score=wall.wall_score,
                confidence=XauZoneConfidence.UNAVAILABLE,
                no_trade_warning=True,
                notes=[
                    RESEARCH_ZONE_NOTE,
                    "Spot-equivalent level is unavailable because basis mapping is missing.",
                ],
                limitations=wall.limitations,
            )
        ]
    if wall.wall_score < LOW_SCORE_THRESHOLD:
        return [
            _zone(
                zone_id=f"no_trade_low_score_{wall.wall_id}",
                zone_type=XauZoneType.NO_TRADE_ZONE,
                level=wall.spot_equivalent_level,
                linked_wall_ids=[wall.wall_id],
                wall_score=wall.wall_score,
                confidence=XauZoneConfidence.UNAVAILABLE,
                no_trade_warning=True,
                notes=[
                    RESEARCH_ZONE_NOTE,
                    "Wall score is too low for a directional research-zone label.",
                ],
                limitations=wall.limitations,
            )
        ]

    zones: list[XauZone] = []
    if reference is not None:
        zones.extend(_directional_zones(wall, reference))
        zones.extend(_pin_and_squeeze_zones(wall, reference, expected_range))
    zones.extend(_range_edge_zones(wall, expected_range))
    if not zones:
        zones.append(
            _zone(
                zone_id=f"no_trade_unclassified_{wall.wall_id}",
                zone_type=XauZoneType.NO_TRADE_ZONE,
                level=wall.spot_equivalent_level,
                linked_wall_ids=[wall.wall_id],
                wall_score=wall.wall_score,
                confidence=XauZoneConfidence.LOW,
                no_trade_warning=True,
                notes=[
                    RESEARCH_ZONE_NOTE,
                    "Wall evidence is usable but not enough for a specific zone label.",
                ],
                limitations=wall.limitations,
            )
        )
    return zones


def _directional_zones(wall: XauOiWall, reference: float) -> list[XauZone]:
    level = wall.spot_equivalent_level
    if level is None:
        return []
    if wall.option_type in {XauWallType.PUT, XauWallType.MIXED} and level <= reference:
        return [
            _zone(
                zone_id=f"support_{wall.wall_id}",
                zone_type=XauZoneType.SUPPORT_CANDIDATE,
                level=level,
                linked_wall_ids=[wall.wall_id],
                wall_score=wall.wall_score,
                confidence=_confidence(wall.wall_score),
                notes=[
                    RESEARCH_ZONE_NOTE,
                    "Put or mixed wall sits below or near the reference price.",
                ],
                limitations=wall.limitations,
            )
        ]
    if wall.option_type in {XauWallType.CALL, XauWallType.MIXED} and level >= reference:
        return [
            _zone(
                zone_id=f"resistance_{wall.wall_id}",
                zone_type=XauZoneType.RESISTANCE_CANDIDATE,
                level=level,
                linked_wall_ids=[wall.wall_id],
                wall_score=wall.wall_score,
                confidence=_confidence(wall.wall_score),
                notes=[
                    RESEARCH_ZONE_NOTE,
                    "Call or mixed wall sits above or near the reference price.",
                ],
                limitations=wall.limitations,
            )
        ]
    return []


def _pin_and_squeeze_zones(
    wall: XauOiWall,
    reference: float,
    expected_range: XauExpectedRange | None,
) -> list[XauZone]:
    level = wall.spot_equivalent_level
    if level is None:
        return []
    near_threshold = _near_threshold(expected_range)
    zones: list[XauZone] = []
    if abs(level - reference) <= near_threshold:
        zones.append(
            _zone(
                zone_id=f"pin_{wall.wall_id}",
                zone_type=XauZoneType.PIN_RISK_ZONE,
                level=level,
                lower_bound=level - near_threshold,
                upper_bound=level + near_threshold,
                linked_wall_ids=[wall.wall_id],
                wall_score=wall.wall_score,
                pin_risk_score=min(1.0, wall.wall_score / SQUEEZE_SCORE_THRESHOLD),
                confidence=_confidence(wall.wall_score),
                notes=[
                    RESEARCH_ZONE_NOTE,
                    "Wall is near the current reference level, creating pin-risk context.",
                ],
                limitations=wall.limitations,
            )
        )
    if (
        wall.freshness_status == XauFreshnessFactorStatus.CONFIRMED
        and wall.wall_score >= SQUEEZE_SCORE_THRESHOLD
    ):
        zones.append(
            _zone(
                zone_id=f"squeeze_{wall.wall_id}",
                zone_type=XauZoneType.SQUEEZE_RISK_ZONE,
                level=level,
                linked_wall_ids=[wall.wall_id],
                wall_score=wall.wall_score,
                squeeze_risk_score=min(1.0, wall.wall_score / SQUEEZE_SCORE_THRESHOLD),
                confidence=_confidence(wall.wall_score),
                notes=[
                    RESEARCH_ZONE_NOTE,
                    "Fresh OI change or volume confirms active positioning at this wall.",
                ],
                limitations=wall.limitations,
            )
        )
    return zones


def _range_edge_zones(
    wall: XauOiWall,
    expected_range: XauExpectedRange | None,
) -> list[XauZone]:
    level = wall.spot_equivalent_level
    if level is None or expected_range is None:
        return []
    zones: list[XauZone] = []
    if expected_range.upper_1sd is not None and level >= expected_range.upper_1sd:
        zones.append(
            _zone(
                zone_id=f"breakout_{wall.wall_id}",
                zone_type=XauZoneType.BREAKOUT_CANDIDATE,
                level=level,
                lower_bound=expected_range.upper_1sd,
                linked_wall_ids=[wall.wall_id],
                wall_score=wall.wall_score,
                confidence=_confidence(wall.wall_score),
                notes=[
                    RESEARCH_ZONE_NOTE,
                    "Wall is at or beyond the upper 1SD expected-range edge.",
                ],
                limitations=wall.limitations,
            )
        )
    if expected_range.lower_1sd is not None and level <= expected_range.lower_1sd:
        zones.append(
            _zone(
                zone_id=f"reversal_{wall.wall_id}",
                zone_type=XauZoneType.REVERSAL_CANDIDATE,
                level=level,
                upper_bound=expected_range.lower_1sd,
                linked_wall_ids=[wall.wall_id],
                wall_score=wall.wall_score,
                confidence=_confidence(wall.wall_score),
                notes=[
                    RESEARCH_ZONE_NOTE,
                    "Wall is at or beyond the lower 1SD expected-range edge.",
                ],
                limitations=wall.limitations,
            )
        )
    return zones


def _zone(
    *,
    zone_id: str,
    zone_type: XauZoneType,
    confidence: XauZoneConfidence,
    no_trade_warning: bool = False,
    level: float | None = None,
    lower_bound: float | None = None,
    upper_bound: float | None = None,
    linked_wall_ids: list[str] | None = None,
    wall_score: float | None = None,
    pin_risk_score: float | None = None,
    squeeze_risk_score: float | None = None,
    notes: list[str] | None = None,
    limitations: list[str] | None = None,
) -> XauZone:
    return XauZone(
        zone_id=zone_id,
        zone_type=zone_type,
        level=level,
        lower_bound=lower_bound,
        upper_bound=upper_bound,
        linked_wall_ids=linked_wall_ids or [],
        wall_score=wall_score,
        pin_risk_score=pin_risk_score,
        squeeze_risk_score=squeeze_risk_score,
        confidence=confidence,
        no_trade_warning=no_trade_warning,
        notes=notes or [RESEARCH_ZONE_NOTE],
        limitations=limitations or [],
    )


def _near_threshold(expected_range: XauExpectedRange | None) -> float:
    if expected_range and expected_range.expected_move is not None:
        return max(5.0, expected_range.expected_move * 0.15)
    return 10.0


def _confidence(wall_score: float) -> XauZoneConfidence:
    if wall_score >= 0.25:
        return XauZoneConfidence.HIGH
    if wall_score >= 0.10:
        return XauZoneConfidence.MEDIUM
    return XauZoneConfidence.LOW
