from __future__ import annotations

from src.models.xau_quikstrike_fusion import XauFusionBasisState, XauFusionContextStatus

DEFAULT_MAX_ABS_BASIS_POINTS = 250.0
BASIS_RESEARCH_NOTE = "Spot-equivalent levels are local research annotations only."


def calculate_basis_state(
    *,
    xauusd_spot_reference: float | None = None,
    gc_futures_reference: float | None = None,
    max_abs_basis_points: float = DEFAULT_MAX_ABS_BASIS_POINTS,
) -> XauFusionBasisState:
    """Calculate optional GC futures versus XAUUSD spot basis."""

    if xauusd_spot_reference is None or gc_futures_reference is None:
        return XauFusionBasisState(
            status=XauFusionContextStatus.UNAVAILABLE,
            calculation_note=(
                "Basis was not computed because spot and futures references were not "
                "both provided; futures-strike levels are preserved."
            ),
            warnings=[
                "Basis context is unavailable; spot-equivalent strike levels were not computed."
            ],
        )
    if xauusd_spot_reference <= 0 or gc_futures_reference <= 0:
        return XauFusionBasisState(
            status=XauFusionContextStatus.BLOCKED,
            calculation_note="Basis was not computed because a reference price is invalid.",
            warnings=["Basis references must be positive numbers."],
        )
    basis_points = gc_futures_reference - xauusd_spot_reference
    if abs(basis_points) > max_abs_basis_points:
        return XauFusionBasisState(
            status=XauFusionContextStatus.CONFLICT,
            xauusd_spot_reference=xauusd_spot_reference,
            gc_futures_reference=gc_futures_reference,
            basis_points=basis_points,
            calculation_note=(
                "Basis references were provided, but the futures/spot gap is outside "
                "the configured research tolerance."
            ),
            warnings=[
                "Basis context is conflicting; spot-equivalent strike levels were not computed."
            ],
        )
    return XauFusionBasisState(
        status=XauFusionContextStatus.AVAILABLE,
        xauusd_spot_reference=xauusd_spot_reference,
        gc_futures_reference=gc_futures_reference,
        basis_points=basis_points,
        calculation_note=BASIS_RESEARCH_NOTE,
    )


def calculate_spot_equivalent_level(
    futures_strike: float,
    basis_state: XauFusionBasisState,
) -> float | None:
    """Convert a futures strike to spot-equivalent level when basis is available."""

    if futures_strike <= 0:
        raise ValueError("futures_strike must be positive")
    if (
        basis_state.status != XauFusionContextStatus.AVAILABLE
        or basis_state.basis_points is None
    ):
        return None
    spot_equivalent = futures_strike - basis_state.basis_points
    if spot_equivalent <= 0:
        raise ValueError("spot-equivalent level must remain positive")
    return spot_equivalent
