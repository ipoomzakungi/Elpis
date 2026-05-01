from datetime import date

from src.models.xau import (
    XauExpectedRange,
    XauFreshnessFactorStatus,
    XauOiWall,
    XauVolatilitySource,
    XauWallType,
    XauZoneConfidence,
    XauZoneType,
)
from src.xau.zones import RESEARCH_ZONE_NOTE, classify_zones


def _wall(
    wall_id: str,
    wall_type: XauWallType,
    level: float | None,
    score: float,
    *,
    freshness: XauFreshnessFactorStatus = XauFreshnessFactorStatus.CONFIRMED,
) -> XauOiWall:
    return XauOiWall(
        wall_id=wall_id,
        expiry=date(2026, 5, 7),
        strike=level + 7.0 if level is not None else 2400.0,
        spot_equivalent_level=level,
        basis=7.0 if level is not None else None,
        option_type=wall_type,
        open_interest=1000.0,
        total_expiry_open_interest=2000.0,
        oi_share=0.5,
        expiry_weight=0.8,
        freshness_factor=1.1 if freshness == XauFreshnessFactorStatus.CONFIRMED else 1.0,
        wall_score=score,
        freshness_status=freshness,
        notes=["test wall"],
        limitations=[] if level is not None else ["basis unavailable"],
    )


def _range() -> XauExpectedRange:
    return XauExpectedRange(
        source=XauVolatilitySource.IV,
        reference_price=2403.0,
        expected_move=50.0,
        lower_1sd=2353.0,
        upper_1sd=2453.0,
        days_to_expiry=7,
    )


def test_classify_zones_creates_support_resistance_pin_squeeze_breakout_and_reversal():
    zones = classify_zones(
        [
            _wall("put_support", XauWallType.PUT, 2390.0, 0.25),
            _wall("call_resistance", XauWallType.CALL, 2425.0, 0.24),
            _wall("mixed_pin", XauWallType.MIXED, 2404.0, 0.22),
            _wall("call_breakout", XauWallType.CALL, 2465.0, 0.18),
            _wall("put_reversal", XauWallType.PUT, 2340.0, 0.18),
        ],
        expected_range=_range(),
        reference_price=2403.0,
    )

    zone_types = {zone.zone_type for zone in zones}
    assert XauZoneType.SUPPORT_CANDIDATE in zone_types
    assert XauZoneType.RESISTANCE_CANDIDATE in zone_types
    assert XauZoneType.PIN_RISK_ZONE in zone_types
    assert XauZoneType.SQUEEZE_RISK_ZONE in zone_types
    assert XauZoneType.BREAKOUT_CANDIDATE in zone_types
    assert XauZoneType.REVERSAL_CANDIDATE in zone_types
    assert all(RESEARCH_ZONE_NOTE in zone.notes for zone in zones)


def test_classify_zones_marks_missing_mapping_or_low_score_as_no_trade():
    zones = classify_zones(
        [
            _wall("missing_basis", XauWallType.UNKNOWN, None, 0.20),
            _wall(
                "low_score",
                XauWallType.CALL,
                2410.0,
                0.01,
                freshness=XauFreshnessFactorStatus.UNAVAILABLE,
            ),
        ],
        expected_range=_range(),
        reference_price=2403.0,
    )

    no_trade_zones = [zone for zone in zones if zone.zone_type == XauZoneType.NO_TRADE_ZONE]
    assert len(no_trade_zones) == 2
    assert all(zone.no_trade_warning for zone in no_trade_zones)
    assert all(zone.confidence == XauZoneConfidence.UNAVAILABLE for zone in no_trade_zones)


def test_zone_notes_do_not_claim_profitability_or_live_readiness():
    zones = classify_zones([_wall("put_support", XauWallType.PUT, 2390.0, 0.25)])

    combined_notes = " ".join(note for zone in zones for note in zone.notes)
    assert "research annotations" in combined_notes
    assert "not trading signals" in combined_notes
    assert "profitable" not in combined_notes.lower()
    assert "live ready" not in combined_notes.lower()
