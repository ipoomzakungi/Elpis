import pytest

from src.models.xau import XauVolatilitySnapshot, XauVolatilitySource
from src.xau.volatility import compute_expected_move, expected_range_from_snapshot


def test_compute_expected_move_from_annualized_volatility():
    move = compute_expected_move(
        reference_price=2403.0,
        annualized_volatility=0.16,
        days_to_expiry=7,
    )

    assert move == pytest.approx(53.24, abs=0.01)


def test_expected_range_from_iv_with_1sd_and_2sd_bounds():
    snapshot = XauVolatilitySnapshot(
        implied_volatility=0.16,
        source=XauVolatilitySource.IV,
        days_to_expiry=7,
    )

    result = expected_range_from_snapshot(
        snapshot=snapshot,
        reference_price=2403.0,
        include_2sd_range=True,
    )

    assert result.source == XauVolatilitySource.IV
    assert result.expected_move == pytest.approx(53.24, abs=0.01)
    assert result.lower_1sd == pytest.approx(2349.76, abs=0.01)
    assert result.upper_1sd == pytest.approx(2456.24, abs=0.01)
    assert result.lower_2sd == pytest.approx(2296.51, abs=0.01)
    assert result.upper_2sd == pytest.approx(2509.49, abs=0.01)
    assert result.unavailable_reason is None


def test_expected_range_is_unavailable_when_iv_is_missing():
    snapshot = XauVolatilitySnapshot(source=XauVolatilitySource.IV, days_to_expiry=7)

    result = expected_range_from_snapshot(snapshot=snapshot, reference_price=2403.0)

    assert result.source == XauVolatilitySource.UNAVAILABLE
    assert result.expected_move is None
    assert "volatility input is unavailable" in result.unavailable_reason


def test_manual_expected_range_is_labeled_manual():
    snapshot = XauVolatilitySnapshot(
        manual_expected_move=25.0,
        source=XauVolatilitySource.MANUAL,
    )

    result = expected_range_from_snapshot(snapshot=snapshot, reference_price=2403.0)

    assert result.source == XauVolatilitySource.MANUAL
    assert result.expected_move == 25.0
    assert result.lower_1sd == 2378.0
    assert result.upper_1sd == 2428.0
