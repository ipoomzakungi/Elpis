from __future__ import annotations

from datetime import UTC, date, datetime

from src.models.xau_market_context import XauBasisStatus, XauVolatilityStatus
from src.models.xau_systematic_research import (
    XauAlignedSourceState,
    XauSystematicBasisState,
    XauSystematicCmeState,
    XauSystematicMappedStructure,
    XauSystematicPriceProvider,
    XauSystematicPriceState,
    XauSystematicReadinessFlags,
    XauSystematicRegimeStates,
    XauSystematicSessionState,
    XauSystematicSourceStatus,
    XauSystematicVolatilityState,
)
from src.xau_systematic_research.source_manifest import build_source_manifest


def test_source_manifest_marks_oi_as_structural_not_directional() -> None:
    state = _state()
    manifest = build_source_manifest(state, ai_pack_status=XauSystematicSourceStatus.AVAILABLE)

    assert state.states.oi_state == "structural_only"
    assert any("structural walls only" in item for item in manifest.limitations)
    assert any("never direction by itself" in item for item in manifest.limitations)
    assert manifest.ai_pack_status == XauSystematicSourceStatus.AVAILABLE


def _state() -> XauAlignedSourceState:
    return XauAlignedSourceState(
        cycle_id="cycle",
        created_at=datetime(2026, 6, 8, tzinfo=UTC),
        session_date=date(2026, 6, 8),
        cme=XauSystematicCmeState(
            vol2vol_report_id="vol2vol",
            matrix_report_id="matrix",
            fusion_report_id="fusion",
        ),
        price=XauSystematicPriceState(
            traded_symbol="XAUUSD",
            provider=XauSystematicPriceProvider.LOCAL_BARS,
            latest_price=4050,
        ),
        basis=XauSystematicBasisState(
            gc_futures_price=4070,
            xauusd_spot_price=4050,
            basis_points=20,
            basis_status=XauBasisStatus.ALIGNED,
        ),
        session=XauSystematicSessionState(active_session="asia", session_open=4040),
        volatility=XauSystematicVolatilityState(atr_5m=2, status=XauVolatilityStatus.PARTIAL),
        mapped_structure=XauSystematicMappedStructure(
            top_mapped_walls=[{"futures_level": 4100, "mapped_level": 4080}]
        ),
        states=XauSystematicRegimeStates(
            oi_state="structural_only",
            iv_state="available",
            volume_state="available",
            candle_state="accepted_below",
            regime_state="research_context_only",
        ),
        readiness=XauSystematicReadinessFlags(
            blocked=False,
            partial=False,
            ready_for_shadow_review=True,
        ),
    )
