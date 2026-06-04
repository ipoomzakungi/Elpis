from datetime import UTC, date, datetime

import pytest

from src.models.quikstrike_matrix import (
    QuikStrikeMatrixBodyCell,
    QuikStrikeMatrixCellState,
)
from src.models.xau import (
    XauDailyStructuralMapReadiness,
    XauDailyStructuralMapWallMappingStatus,
    XauExpectedRangeSource,
    XauFreshnessFactorStatus,
    XauOiWall,
    XauWallType,
)
from src.xau_quikstrike_fusion.basis import calculate_basis_state
from src.xau_quikstrike_fusion.daily_structural_map import (
    BASIS_UNAVAILABLE_NO_SIGNAL_REASON,
    EXPECTED_RANGE_UNAVAILABLE_NO_SIGNAL_REASON,
    MAP_ONLY_NO_SIGNAL_REASON,
    SESSION_OPEN_UNAVAILABLE_NO_SIGNAL_REASON,
    build_daily_structural_map,
)
from src.xau_quikstrike_fusion.expected_range import build_expected_range_snapshot


def test_full_context_creates_ready_map_but_does_not_allow_signals() -> None:
    basis_state = calculate_basis_state(
        xauusd_spot_reference=4536.7,
        gc_futures_reference=4549.2,
    )

    daily_map = build_daily_structural_map(
        map_id="xau_map_20260602_og1m6",
        session_date=date(2026, 6, 2),
        created_at=datetime(2026, 6, 4, 12, 0, tzinfo=UTC),
        source_product="Gold",
        traded_instrument="XAUUSD",
        traded_reference_price=4536.7,
        expected_range_snapshot=_native_expected_range_snapshot(),
        basis_state=basis_state,
        walls=[_wall()],
        session_open_price=4538.0,
        session_open_source="manual_research_input",
        wall_oi_change_by_id={"wall_4550_call": 25.0},
        wall_volume_by_id={"wall_4550_call": 80.0},
    )

    assert daily_map.data_quality_state == XauDailyStructuralMapReadiness.STRUCTURAL_MAP_READY
    assert daily_map.signal_allowed is False
    assert daily_map.no_signal_reasons == [MAP_ONLY_NO_SIGNAL_REASON]
    assert daily_map.basis == pytest.approx(12.5)
    assert daily_map.expected_range_source == XauExpectedRangeSource.CME_NATIVE
    assert daily_map.wall_count == 1
    wall = daily_map.walls[0]
    assert wall.mapping_status == XauDailyStructuralMapWallMappingStatus.MAPPED
    assert wall.spot_equivalent_level == pytest.approx(4537.5)
    assert wall.distance_to_traded_price == pytest.approx(0.8)
    assert wall.distance_to_session_open == pytest.approx(-0.5)
    assert wall.inside_1sd is True
    assert wall.inside_2sd is True
    assert wall.oi_change == 25.0
    assert wall.volume == 80.0


def test_missing_basis_keeps_spot_equivalent_level_null() -> None:
    basis_state = calculate_basis_state(gc_futures_reference=4549.2)

    daily_map = build_daily_structural_map(
        map_id="xau_map_missing_basis",
        session_date=date(2026, 6, 2),
        created_at=datetime(2026, 6, 4, 12, 0, tzinfo=UTC),
        source_product="Gold",
        traded_instrument="XAUUSD",
        traded_reference_price=4536.7,
        expected_range_snapshot=_native_expected_range_snapshot(),
        basis_state=basis_state,
        walls=[_wall()],
        session_open_price=4538.0,
    )

    assert daily_map.data_quality_state == XauDailyStructuralMapReadiness.PARTIAL_MISSING_BASIS
    assert BASIS_UNAVAILABLE_NO_SIGNAL_REASON in daily_map.no_signal_reasons
    assert daily_map.basis is None
    assert daily_map.basis_mapping_available is False
    assert daily_map.walls[0].spot_equivalent_level is None
    assert daily_map.walls[0].distance_to_traded_price is None
    assert daily_map.walls[0].mapping_status == (
        XauDailyStructuralMapWallMappingStatus.BASIS_UNAVAILABLE
    )


def test_missing_expected_range_keeps_sd_fields_null() -> None:
    basis_state = calculate_basis_state(
        xauusd_spot_reference=4536.7,
        gc_futures_reference=4549.2,
    )

    daily_map = build_daily_structural_map(
        map_id="xau_map_missing_range",
        session_date=date(2026, 6, 2),
        created_at=datetime(2026, 6, 4, 12, 0, tzinfo=UTC),
        source_product="Gold",
        traded_instrument="XAUUSD",
        traded_reference_price=4536.7,
        expected_range_snapshot=None,
        basis_state=basis_state,
        walls=[_wall()],
        session_open_price=4538.0,
    )

    assert daily_map.data_quality_state == (
        XauDailyStructuralMapReadiness.PARTIAL_MISSING_EXPECTED_RANGE
    )
    assert EXPECTED_RANGE_UNAVAILABLE_NO_SIGNAL_REASON in daily_map.no_signal_reasons
    assert daily_map.expected_range_source is None
    assert daily_map.lower_1sd is None
    assert daily_map.upper_2sd is None
    assert daily_map.walls[0].inside_1sd is None
    assert daily_map.walls[0].near_expected_range_boundary is None


def test_missing_session_open_keeps_open_context_null_and_partial() -> None:
    basis_state = calculate_basis_state(
        xauusd_spot_reference=4536.7,
        gc_futures_reference=4549.2,
    )

    daily_map = build_daily_structural_map(
        map_id="xau_map_missing_open",
        session_date=date(2026, 6, 2),
        created_at=datetime(2026, 6, 4, 12, 0, tzinfo=UTC),
        source_product="Gold",
        traded_instrument="XAUUSD",
        traded_reference_price=4536.7,
        expected_range_snapshot=_native_expected_range_snapshot(),
        basis_state=basis_state,
        walls=[_wall()],
        session_open_price=None,
    )

    assert daily_map.data_quality_state == (
        XauDailyStructuralMapReadiness.PARTIAL_MISSING_SESSION_OPEN
    )
    assert SESSION_OPEN_UNAVAILABLE_NO_SIGNAL_REASON in daily_map.no_signal_reasons
    assert daily_map.session_open_available is False
    assert daily_map.session_open_price is None
    assert daily_map.open_side_vs_1sd is None
    assert daily_map.open_distance_points is None
    assert daily_map.walls[0].distance_to_session_open is None


def test_blank_matrix_cells_remain_blank_not_zero() -> None:
    blank_cell = QuikStrikeMatrixBodyCell(
        row_index=1,
        column_index=2,
        strike=4550.0,
        row_label="4550",
        column_label="OG1M6 Call",
        raw_value="",
        numeric_value=None,
        cell_state=QuikStrikeMatrixCellState.BLANK,
        option_type=None,
        expiration="2026-06-05",
    )

    assert blank_cell.cell_state == QuikStrikeMatrixCellState.BLANK
    assert blank_cell.numeric_value is None


def test_feature_017_snapshot_populates_structural_map_range_fields() -> None:
    snapshot = build_expected_range_snapshot(
        source_report_id="vol2vol_20260604",
        source_view="QUIKOPTIONS VOL2VOL",
        capture_timestamp=datetime(2026, 6, 4, 12, 0, tzinfo=UTC),
        product="Gold",
        option_product_code="OG|GC",
        futures_symbol="GC",
        expiration_code="OG1M6",
        expiry_date=date(2026, 6, 5),
        reference_futures_price=4549.2,
        report_level_iv=0.2508,
        fractional_dte=3.47,
    )
    basis_state = calculate_basis_state(
        xauusd_spot_reference=4536.7,
        gc_futures_reference=4549.2,
    )

    daily_map = build_daily_structural_map(
        map_id="xau_map_derived_range",
        session_date=date(2026, 6, 2),
        created_at=datetime(2026, 6, 4, 12, 0, tzinfo=UTC),
        source_product="Gold",
        traded_instrument="XAUUSD",
        expected_range_snapshot=snapshot,
        basis_state=basis_state,
        walls=[_wall()],
        session_open_price=4538.0,
    )

    assert daily_map.expected_range_source == XauExpectedRangeSource.DERIVED_FROM_IV
    assert daily_map.report_level_iv == 0.2508
    assert daily_map.fractional_dte == 3.47
    assert daily_map.lower_1sd == pytest.approx(snapshot.lower_1sd)
    assert daily_map.upper_3sd == pytest.approx(snapshot.upper_3sd)
    assert daily_map.reference_futures_price == 4549.2


def _native_expected_range_snapshot():
    return build_expected_range_snapshot(
        source_report_id="vol2vol_20260604",
        source_view="QUIKOPTIONS VOL2VOL",
        capture_timestamp=datetime(2026, 6, 4, 12, 0, tzinfo=UTC),
        product="Gold",
        option_product_code="OG|GC",
        futures_symbol="GC",
        expiration_code="OG1M6",
        expiry_date=date(2026, 6, 5),
        reference_futures_price=4549.2,
        report_level_iv=0.2508,
        vol_settle=0.2508,
        fractional_dte=3.47,
        cme_numeric_1sd=111.3,
        cme_numeric_2sd=222.6,
        cme_numeric_3sd=333.9,
        upper_1sd=4660.5,
        lower_1sd=4437.9,
        upper_2sd=4771.8,
        lower_2sd=4326.6,
        upper_3sd=4883.1,
        lower_3sd=4215.3,
    )


def _wall() -> XauOiWall:
    return XauOiWall(
        wall_id="wall_4550_call",
        expiry=date(2026, 6, 5),
        strike=4550.0,
        option_type=XauWallType.CALL,
        open_interest=1000.0,
        total_expiry_open_interest=5000.0,
        oi_share=0.2,
        expiry_weight=1.0,
        freshness_factor=1.0,
        wall_score=0.42,
        freshness_status=XauFreshnessFactorStatus.CONFIRMED,
    )
