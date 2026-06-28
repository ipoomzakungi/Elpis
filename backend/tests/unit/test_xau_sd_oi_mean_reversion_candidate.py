from datetime import UTC, date, datetime

import pytest

from src.models.xau import XauFreshnessFactorStatus, XauOiWall, XauWallType
from src.models.xau_sd_oi_candidate import (
    XauSdOiCandidateSide,
    XauSdOiReadinessState,
    XauSdOiStretchZone,
)
from src.xau_quikstrike_fusion.basis import calculate_basis_state
from src.xau_quikstrike_fusion.daily_structural_map import build_daily_structural_map
from src.xau_quikstrike_fusion.expected_range import build_expected_range_snapshot
from src.xau_sd_oi_candidate.classifier import (
    BASIS_MISSING_REASON_CODE,
    DERIVED_3_5SD_LIMITATION,
    build_xau_sd_oi_candidate_set,
)

TIMESTAMP = datetime(2026, 6, 2, 14, 30, tzinfo=UTC)


def test_missing_basis_blocks_candidate_and_keeps_signal_disabled() -> None:
    daily_map = _daily_map(basis_available=False)

    candidate_set = build_xau_sd_oi_candidate_set(
        daily_map,
        timestamp=TIMESTAMP,
        traded_price=112.0,
        gc_price=122.0,
        confirmation_state="rejection",
        iv_state="stable",
        flow_state="not_breakout_confirmed",
    )
    candidate = candidate_set.candidates[0]

    assert candidate.side == XauSdOiCandidateSide.NO_TRADE
    assert candidate.signal_allowed is False
    assert candidate_set.signal_allowed is False
    assert candidate.readiness_state == XauSdOiReadinessState.BLOCKED_MISSING_CONTEXT
    assert BASIS_MISSING_REASON_CODE in {reason.reason_code for reason in candidate.reasons}


def test_upper_2sd_to_3sd_rejection_creates_short_reversion_candidate() -> None:
    candidate_set = build_xau_sd_oi_candidate_set(
        _daily_map(),
        timestamp=TIMESTAMP,
        traded_price=112.0,
        gc_price=122.0,
        confirmation_state="rejection",
        iv_state="stable",
        flow_state="not_breakout_confirmed",
    )
    candidate = candidate_set.candidates[0]

    assert candidate.side == XauSdOiCandidateSide.SHORT_REVERSION_CANDIDATE
    assert candidate.stretch_zone == XauSdOiStretchZone.UPPER_2SD_TO_3SD
    assert candidate.target_1 == pytest.approx(100.0)
    assert candidate.target_2 == pytest.approx(90.0)
    assert candidate.stop_reference == pytest.approx(125.0)
    assert candidate.signal_allowed is False
    assert candidate.research_only is True


def test_lower_2sd_to_3sd_rejection_creates_long_reversion_candidate() -> None:
    candidate_set = build_xau_sd_oi_candidate_set(
        _daily_map(),
        timestamp=TIMESTAMP,
        traded_price=68.0,
        gc_price=78.0,
        confirmation_state="close_back_inside",
        iv_state="compressing",
        flow_state="not_breakout_confirmed",
    )
    candidate = candidate_set.candidates[0]

    assert candidate.side == XauSdOiCandidateSide.LONG_REVERSION_CANDIDATE
    assert candidate.stretch_zone == XauSdOiStretchZone.LOWER_2SD_TO_3SD
    assert candidate.target_1 == pytest.approx(80.0)
    assert candidate.target_2 == pytest.approx(90.0)
    assert candidate.stop_reference == pytest.approx(55.0)
    assert candidate.signal_allowed is False
    assert candidate.research_only is True


def test_iv_expansion_flow_through_wall_and_acceptance_marks_breakout_risk() -> None:
    candidate_set = build_xau_sd_oi_candidate_set(
        _daily_map(),
        timestamp=TIMESTAMP,
        traded_price=112.0,
        gc_price=122.0,
        confirmation_state="acceptance",
        iv_state="expanding",
        flow_state="flow_through_wall",
    )
    candidate = candidate_set.candidates[0]

    assert candidate.side == XauSdOiCandidateSide.BREAKOUT_RISK
    assert candidate.readiness_state == XauSdOiReadinessState.BREAKOUT_RISK
    assert candidate.signal_allowed is False


def test_inside_2sd_is_monitor_only_no_trade() -> None:
    candidate_set = build_xau_sd_oi_candidate_set(
        _daily_map(),
        timestamp=TIMESTAMP,
        traded_price=95.0,
        gc_price=105.0,
        confirmation_state="neutral",
        iv_state="stable",
        flow_state="neutral",
    )
    candidate = candidate_set.candidates[0]

    assert candidate.side == XauSdOiCandidateSide.NO_TRADE
    assert candidate.stretch_zone == XauSdOiStretchZone.INSIDE_NORMAL_RANGE
    assert candidate.readiness_state == XauSdOiReadinessState.MONITOR_ONLY
    assert candidate.signal_allowed is False


def test_null_oi_change_and_volume_are_preserved_not_zeroed() -> None:
    candidate_set = build_xau_sd_oi_candidate_set(
        _daily_map(oi_change=None, volume=None),
        timestamp=TIMESTAMP,
        traded_price=96.0,
        gc_price=106.0,
        confirmation_state="neutral",
        iv_state="stable",
        flow_state="neutral",
    )
    candidate = candidate_set.candidates[0]

    assert candidate.nearest_wall_oi_change is None
    assert candidate.nearest_wall_volume is None
    assert candidate.nearest_wall_level == pytest.approx(95.0)


def test_derived_3_5sd_uses_1sd_distance_and_records_limitation() -> None:
    candidate_set = build_xau_sd_oi_candidate_set(
        _daily_map(),
        timestamp=TIMESTAMP,
        traded_price=112.0,
        gc_price=122.0,
        confirmation_state="rejection",
        iv_state="stable",
        flow_state="not_breakout_confirmed",
    )
    candidate = candidate_set.candidates[0]

    assert candidate.lower_3_5sd == pytest.approx(55.0)
    assert candidate.upper_3_5sd == pytest.approx(125.0)
    assert DERIVED_3_5SD_LIMITATION in candidate.limitations
    assert DERIVED_3_5SD_LIMITATION in candidate_set.limitations


def _daily_map(
    *,
    basis_available: bool = True,
    oi_change: float | None = 25.0,
    volume: float | None = 80.0,
):
    basis_state = (
        calculate_basis_state(xauusd_spot_reference=90.0, gc_futures_reference=100.0)
        if basis_available
        else calculate_basis_state(gc_futures_reference=100.0)
    )
    return build_daily_structural_map(
        map_id="xau_sd_oi_candidate_fixture",
        session_date=date(2026, 6, 2),
        created_at=datetime(2026, 6, 2, 12, 0, tzinfo=UTC),
        source_product="Gold",
        traded_instrument="XAUUSD",
        traded_reference_price=90.0,
        expected_range_snapshot=_expected_range_snapshot(),
        basis_state=basis_state,
        walls=[_wall()],
        session_open_price=90.0,
        session_open_source="manual_research_input",
        wall_oi_change_by_id={"wall_105_call": oi_change},
        wall_volume_by_id={"wall_105_call": volume},
    )


def _expected_range_snapshot():
    return build_expected_range_snapshot(
        source_report_id="vol2vol_fixture",
        source_view="QUIKOPTIONS VOL2VOL",
        capture_timestamp=datetime(2026, 6, 2, 12, 0, tzinfo=UTC),
        product="Gold",
        option_product_code="OG|GC",
        futures_symbol="GC",
        expiration_code="OG1M6",
        expiry_date=date(2026, 6, 5),
        reference_futures_price=100.0,
        report_level_iv=0.25,
        vol_settle=0.25,
        fractional_dte=3.0,
        cme_numeric_1sd=10.0,
        cme_numeric_2sd=20.0,
        cme_numeric_3sd=30.0,
        upper_1sd=110.0,
        lower_1sd=90.0,
        upper_2sd=120.0,
        lower_2sd=80.0,
        upper_3sd=130.0,
        lower_3sd=70.0,
    )


def _wall() -> XauOiWall:
    return XauOiWall(
        wall_id="wall_105_call",
        expiry=date(2026, 6, 5),
        strike=105.0,
        option_type=XauWallType.CALL,
        open_interest=1000.0,
        total_expiry_open_interest=5000.0,
        oi_share=0.2,
        expiry_weight=1.0,
        freshness_factor=1.0,
        wall_score=0.42,
        freshness_status=XauFreshnessFactorStatus.CONFIRMED,
    )
