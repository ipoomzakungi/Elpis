from datetime import UTC, date, datetime

import pytest

from src.models.quikstrike_matrix import (
    QuikStrikeMatrixBodyCell,
    QuikStrikeMatrixCellState,
)
from src.models.xau import (
    XauExpectedRangeSource,
    XauVolatilitySource,
)
from src.xau_quikstrike_fusion.basis import (
    calculate_basis_state,
    calculate_spot_equivalent_level,
)
from src.xau_quikstrike_fusion.expected_range import (
    DERIVED_RANGE_LIMITATION,
    RANGE_LABEL_LIMITATION,
    build_expected_range_snapshot,
    expected_range_from_snapshot,
)


def test_cme_native_expected_range_preserves_numeric_bands() -> None:
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
    expected_range = expected_range_from_snapshot(snapshot)

    assert snapshot.range_source == XauExpectedRangeSource.CME_NATIVE
    assert snapshot.cme_numeric_1sd == 111.3
    assert snapshot.upper_3sd == 4883.1
    assert DERIVED_RANGE_LIMITATION not in snapshot.limitations
    assert expected_range.source == XauVolatilitySource.CME_NATIVE
    assert expected_range.upper_2sd == 4771.8


def test_derived_expected_range_uses_report_level_iv_and_fractional_dte() -> None:
    snapshot = build_expected_range_snapshot(
        source_report_id="vol2vol_20260604",
        source_view="QUIKOPTIONS VOL2VOL",
        capture_timestamp=datetime(2026, 6, 4, 12, 0, tzinfo=UTC),
        product="Gold",
        option_product_code="OG|GC",
        reference_futures_price=4549.2,
        report_level_iv=0.2508,
        fractional_dte=3.47,
    )
    expected_sd1 = 4549.2 * 0.2508 * (3.47 / 365.0) ** 0.5
    expected_range = expected_range_from_snapshot(snapshot)

    assert snapshot.range_source == XauExpectedRangeSource.DERIVED_FROM_IV
    assert snapshot.cme_numeric_1sd == pytest.approx(expected_sd1)
    assert snapshot.cme_numeric_2sd == pytest.approx(expected_sd1 * 2.0)
    assert snapshot.cme_numeric_3sd == pytest.approx(expected_sd1 * 3.0)
    assert snapshot.upper_1sd == pytest.approx(4549.2 + expected_sd1)
    assert DERIVED_RANGE_LIMITATION in snapshot.limitations
    assert expected_range.source == XauVolatilitySource.DERIVED_FROM_IV
    assert expected_range.fractional_dte == 3.47


def test_range_label_only_does_not_create_numeric_sd_bands() -> None:
    snapshot = build_expected_range_snapshot(
        source_report_id="vol2vol_20260604",
        source_view="QUIKOPTIONS VOL2VOL",
        capture_timestamp=datetime(2026, 6, 4, 12, 0, tzinfo=UTC),
        product="Gold",
        option_product_code="OG|GC",
        reference_futures_price=4549.2,
        vol_settle=0.3628798179067303,
        fractional_dte=3.47,
        range_label="3",
    )
    expected_range = expected_range_from_snapshot(snapshot)

    assert snapshot.range_source == XauExpectedRangeSource.UNAVAILABLE
    assert snapshot.cme_numeric_1sd is None
    assert snapshot.upper_1sd is None
    assert RANGE_LABEL_LIMITATION in snapshot.limitations
    assert expected_range.source == XauVolatilitySource.UNAVAILABLE


def test_missing_basis_keeps_spot_equivalent_level_unavailable() -> None:
    basis_state = calculate_basis_state(
        xauusd_spot_reference=None,
        gc_futures_reference=4549.2,
    )

    assert basis_state.status.value == "unavailable"
    assert calculate_spot_equivalent_level(4550.0, basis_state) is None


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

