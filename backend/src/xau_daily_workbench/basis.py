from __future__ import annotations

from datetime import datetime

from src.models.xau_daily_workbench import (
    XauDailyWorkbenchBasisSnapshot,
    XauDailyWorkbenchMissingInput,
    XauDailyWorkbenchMissingInputSeverity,
    XauDailyWorkbenchProviderState,
    XauDailyWorkbenchProviderStatus,
    XauDailyWorkbenchProviderType,
    XauDailyWorkbenchRunRequest,
    XauDailyWorkbenchSourceQuality,
    missing_input,
    provider_status,
)

BASIS_UNAVAILABLE_NO_SIGNAL_REASON = "Basis mapping unavailable."


def build_workbench_basis_snapshot(
    request: XauDailyWorkbenchRunRequest,
    *,
    timestamp: datetime,
) -> tuple[
    XauDailyWorkbenchBasisSnapshot,
    XauDailyWorkbenchProviderStatus,
    list[XauDailyWorkbenchMissingInput],
    list[str],
]:
    """Build a research-only basis snapshot without fabricating missing prices."""

    if request.manual_basis is not None:
        return (
            XauDailyWorkbenchBasisSnapshot(
                timestamp=timestamp,
                gc_reference_price=request.gc_reference_price,
                traded_reference_price=request.traded_reference_price,
                traded_instrument=request.traded_instrument,
                basis=request.manual_basis,
                formula="manual_basis",
                source=XauDailyWorkbenchSourceQuality.MANUAL_OVERRIDE,
                alignment_status="manual_override",
                limitations=["Manual basis must be independently verified before research use."],
            ),
            provider_status(
                provider_name="ManualBasisProvider",
                provider_type=XauDailyWorkbenchProviderType.BASIS,
                status=XauDailyWorkbenchProviderState.AVAILABLE,
                source_quality=XauDailyWorkbenchSourceQuality.MANUAL_OVERRIDE,
                message="Manual basis supplied by request.",
                limitations=["Manual override is local research input."],
            ),
            [],
            [],
        )

    if request.gc_reference_price is not None and request.traded_reference_price is not None:
        return (
            XauDailyWorkbenchBasisSnapshot(
                timestamp=timestamp,
                gc_reference_price=request.gc_reference_price,
                traded_reference_price=request.traded_reference_price,
                traded_instrument=request.traded_instrument,
                basis=request.gc_reference_price - request.traded_reference_price,
                formula="gc_reference_price - traded_reference_price",
                source=XauDailyWorkbenchSourceQuality.MANUAL_OVERRIDE,
                alignment_status="request_reference_prices",
                limitations=[
                    "Basis uses request-supplied reference prices and must be checked "
                    "against the actual traded instrument."
                ],
            ),
            provider_status(
                provider_name="ReferencePriceBasisProvider",
                provider_type=XauDailyWorkbenchProviderType.BASIS,
                status=XauDailyWorkbenchProviderState.AVAILABLE,
                source_quality=XauDailyWorkbenchSourceQuality.MANUAL_OVERRIDE,
                message="Basis calculated from request GC and traded reference prices.",
                limitations=["Reference prices are local research inputs."],
            ),
            [],
            [],
        )

    missing = []
    if request.gc_reference_price is None:
        missing.append(
            missing_input(
                "gc_reference_price",
                "GC/futures reference price is missing for basis calculation.",
                severity=XauDailyWorkbenchMissingInputSeverity.WARNING,
            )
        )
    if request.traded_reference_price is None:
        missing.append(
            missing_input(
                "traded_reference_price",
                "Traded-side reference price is missing for basis calculation.",
                severity=XauDailyWorkbenchMissingInputSeverity.WARNING,
            )
        )
    return (
        XauDailyWorkbenchBasisSnapshot(
            timestamp=timestamp,
            gc_reference_price=request.gc_reference_price,
            traded_reference_price=request.traded_reference_price,
            traded_instrument=request.traded_instrument,
            basis=None,
            formula="unavailable",
            source=XauDailyWorkbenchSourceQuality.MANUAL_OVERRIDE,
            alignment_status="unavailable",
            limitations=[BASIS_UNAVAILABLE_NO_SIGNAL_REASON],
        ),
        provider_status(
            provider_name="ReferencePriceBasisProvider",
            provider_type=XauDailyWorkbenchProviderType.BASIS,
            status=XauDailyWorkbenchProviderState.UNAVAILABLE,
            source_quality=XauDailyWorkbenchSourceQuality.MANUAL_OVERRIDE,
            message="Basis could not be calculated because reference prices were missing.",
            limitations=[BASIS_UNAVAILABLE_NO_SIGNAL_REASON],
        ),
        missing,
        [BASIS_UNAVAILABLE_NO_SIGNAL_REASON],
    )


__all__ = [
    "BASIS_UNAVAILABLE_NO_SIGNAL_REASON",
    "build_workbench_basis_snapshot",
]
