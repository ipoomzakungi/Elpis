from __future__ import annotations

from src.models.xau_market_context import XauBasisStatus, XauVolatilityStatus
from src.models.xau_systematic_research import (
    XauAlignedSourceState,
    XauSourceManifest,
    XauSystematicReadiness,
    XauSystematicSourceStatus,
)

RESEARCH_DOCTRINE_LIMITATIONS = [
    "CME OI Matrix provides structural walls only, never direction by itself.",
    "OI Change and Volume provide freshness/activation context only.",
    "Vol2Vol/IV defines expected range and volatility regime; unavailable IV caps readiness.",
    "GC/CME levels are futures-side and must be basis-adjusted before XAUUSD/GO use.",
    "Session open, ATR/RV, and candle state must come from traded-side bars.",
    "Missing basis, price bars, session open, ATR/RV, or candle state blocks action promotion.",
    "Research-only. Not a buy/sell signal.",
]


def build_source_manifest(
    state: XauAlignedSourceState,
    *,
    cme_partial: bool = False,
    warnings: list[str] | None = None,
    ai_pack_status: XauSystematicSourceStatus = XauSystematicSourceStatus.UNAVAILABLE,
) -> XauSourceManifest:
    cme_status = _cme_status(state, cme_partial=cme_partial)
    traded_status = _status_from_available(state.price.latest_price is not None)
    basis_status = _basis_status(state)
    session_status = _status_from_available(state.session.session_open is not None)
    volatility_status = _volatility_status(state)
    candle_status = _status_from_available(state.states.candle_state != "unavailable")

    missing = _missing_sources(
        {
            "cme_fusion": cme_status,
            "traded_price": traded_status,
            "basis": basis_status,
            "session_open": session_status,
            "volatility": volatility_status,
            "candle_state": candle_status,
        }
    )
    stale = []
    if state.cme.cme_age_minutes is not None and cme_status == XauSystematicSourceStatus.STALE:
        stale.append("cme_fusion")
    if (
        state.price.price_age_minutes is not None
        and traded_status == XauSystematicSourceStatus.STALE
    ):
        stale.append("traded_price")

    return XauSourceManifest(
        cme_vol2vol_status=_upstream_status(state.cme.vol2vol_report_id, cme_status),
        cme_matrix_status=_upstream_status(state.cme.matrix_report_id, cme_status),
        fusion_status=cme_status,
        traded_price_status=traded_status,
        basis_status=basis_status,
        session_open_status=session_status,
        volatility_status=volatility_status,
        candle_state_status=candle_status,
        ai_pack_status=ai_pack_status,
        missing_sources=missing,
        stale_sources=stale,
        warnings=_dedupe(warnings or []),
        limitations=RESEARCH_DOCTRINE_LIMITATIONS,
    )


def readiness_from_state(
    state: XauAlignedSourceState,
    *,
    cme_is_stale: bool,
    price_is_stale: bool,
    allow_stale_basis: bool,
) -> XauSystematicReadiness:
    if state.cme.fusion_report_id is None:
        return XauSystematicReadiness.BLOCKED
    if state.price.bars_path is None:
        return XauSystematicReadiness.BLOCKED
    if state.price.latest_price is None:
        return XauSystematicReadiness.BLOCKED
    if state.basis.basis_status == XauBasisStatus.UNAVAILABLE:
        return XauSystematicReadiness.BLOCKED
    if state.basis.basis_status == XauBasisStatus.STALE and not allow_stale_basis:
        return XauSystematicReadiness.BLOCKED

    partial_reasons = [
        state.session.session_open is None,
        state.volatility.status == XauVolatilityStatus.UNAVAILABLE,
        not state.mapped_structure.top_mapped_walls,
        state.states.candle_state == "unavailable",
        state.states.iv_state == "unavailable",
        state.states.volume_state in {"unavailable", "stale"},
        cme_is_stale,
        price_is_stale,
    ]
    if any(partial_reasons):
        return XauSystematicReadiness.PARTIAL
    return XauSystematicReadiness.READY_FOR_SHADOW_REVIEW


def readiness_flags(readiness: XauSystematicReadiness) -> dict[str, bool]:
    return {
        "blocked": readiness == XauSystematicReadiness.BLOCKED,
        "partial": readiness == XauSystematicReadiness.PARTIAL,
        "ready_for_shadow_review": readiness
        == XauSystematicReadiness.READY_FOR_SHADOW_REVIEW,
    }


def no_trade_reasons_for_readiness(
    state: XauAlignedSourceState,
    readiness: XauSystematicReadiness,
) -> list[str]:
    reasons: list[str] = []
    if state.cme.fusion_report_id is None:
        reasons.append("no CME fusion report")
    if state.price.bars_path is None:
        reasons.append("no traded price bars")
    if state.price.latest_price is None:
        reasons.append("latest traded price unavailable")
    if state.basis.basis_status == XauBasisStatus.UNAVAILABLE:
        reasons.append("basis unavailable")
    if state.session.session_open is None:
        reasons.append("session open unavailable")
    if state.volatility.status == XauVolatilityStatus.UNAVAILABLE:
        reasons.append("ATR/RV unavailable")
    if state.states.candle_state == "unavailable":
        reasons.append("candle state unavailable")
    if state.states.iv_state == "unavailable":
        reasons.append("IV/expected range unavailable")
    if state.states.volume_state in {"unavailable", "stale"}:
        reasons.append("volume/OI change freshness incomplete")
    if readiness == XauSystematicReadiness.READY_FOR_SHADOW_REVIEW:
        reasons.append("research-only shadow review; no signal is allowed")
    return _dedupe(reasons)


def _cme_status(
    state: XauAlignedSourceState,
    *,
    cme_partial: bool,
) -> XauSystematicSourceStatus:
    if state.cme.fusion_report_id is None:
        return XauSystematicSourceStatus.UNAVAILABLE
    if cme_partial:
        return XauSystematicSourceStatus.PARTIAL
    return XauSystematicSourceStatus.AVAILABLE


def _upstream_status(
    report_id: str | None,
    fallback: XauSystematicSourceStatus,
) -> XauSystematicSourceStatus:
    if report_id is None:
        return XauSystematicSourceStatus.UNAVAILABLE
    if fallback == XauSystematicSourceStatus.UNAVAILABLE:
        return XauSystematicSourceStatus.PARTIAL
    return fallback


def _basis_status(state: XauAlignedSourceState) -> XauSystematicSourceStatus:
    if state.basis.basis_status == XauBasisStatus.ALIGNED:
        return XauSystematicSourceStatus.AVAILABLE
    if state.basis.basis_status == XauBasisStatus.STALE:
        return XauSystematicSourceStatus.STALE
    return XauSystematicSourceStatus.UNAVAILABLE


def _volatility_status(state: XauAlignedSourceState) -> XauSystematicSourceStatus:
    if state.volatility.status == XauVolatilityStatus.AVAILABLE:
        return XauSystematicSourceStatus.AVAILABLE
    if state.volatility.status == XauVolatilityStatus.PARTIAL:
        return XauSystematicSourceStatus.PARTIAL
    return XauSystematicSourceStatus.UNAVAILABLE


def _status_from_available(available: bool) -> XauSystematicSourceStatus:
    return (
        XauSystematicSourceStatus.AVAILABLE
        if available
        else XauSystematicSourceStatus.UNAVAILABLE
    )


def _missing_sources(statuses: dict[str, XauSystematicSourceStatus]) -> list[str]:
    return [
        name
        for name, status in statuses.items()
        if status in {XauSystematicSourceStatus.UNAVAILABLE, XauSystematicSourceStatus.BLOCKED}
    ]


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
