import pytest

from src.models.xau_quikstrike_fusion import XauFusionContextStatus
from src.xau_quikstrike_fusion.basis import (
    calculate_basis_state,
    calculate_spot_equivalent_level,
)


def test_basis_state_available_when_spot_and_futures_references_are_supplied():
    basis = calculate_basis_state(
        xauusd_spot_reference=4692.1,
        gc_futures_reference=4696.7,
    )

    assert basis.status == XauFusionContextStatus.AVAILABLE
    assert basis.basis_points == pytest.approx(4.6)
    assert "research annotations" in (basis.calculation_note or "")
    assert basis.warnings == []


def test_basis_state_unavailable_when_reference_is_missing():
    basis = calculate_basis_state(xauusd_spot_reference=4692.1)

    assert basis.status == XauFusionContextStatus.UNAVAILABLE
    assert basis.basis_points is None
    assert "not both provided" in (basis.calculation_note or "")
    assert "not computed" in basis.warnings[0]


def test_basis_state_blocks_invalid_reference_values_without_persisting_them():
    basis = calculate_basis_state(
        xauusd_spot_reference=-1.0,
        gc_futures_reference=4696.7,
    )

    assert basis.status == XauFusionContextStatus.BLOCKED
    assert basis.xauusd_spot_reference is None
    assert basis.gc_futures_reference is None
    assert basis.basis_points is None
    assert "invalid" in (basis.calculation_note or "")


def test_basis_state_marks_conflicting_references_outside_tolerance():
    basis = calculate_basis_state(
        xauusd_spot_reference=4700.0,
        gc_futures_reference=5200.0,
        max_abs_basis_points=100.0,
    )

    assert basis.status == XauFusionContextStatus.CONFLICT
    assert basis.basis_points == 500.0
    assert "conflicting" in basis.warnings[0]


def test_spot_equivalent_level_uses_available_basis():
    basis = calculate_basis_state(
        xauusd_spot_reference=4692.1,
        gc_futures_reference=4696.7,
    )

    assert calculate_spot_equivalent_level(4700.0, basis) == pytest.approx(4695.4)


def test_spot_equivalent_level_is_unavailable_without_basis():
    basis = calculate_basis_state()

    assert calculate_spot_equivalent_level(4700.0, basis) is None


def test_spot_equivalent_level_rejects_invalid_futures_strike():
    basis = calculate_basis_state(
        xauusd_spot_reference=4692.1,
        gc_futures_reference=4696.7,
    )

    with pytest.raises(ValueError, match="positive"):
        calculate_spot_equivalent_level(0.0, basis)
