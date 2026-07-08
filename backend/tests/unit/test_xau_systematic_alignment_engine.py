from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from src.models.xau import (
    XauExpectedRangeExtractionQuality,
    XauExpectedRangeSnapshot,
    XauExpectedRangeSource,
    XauExpectedRangeSourceStatus,
)
from src.models.xau_market_context import XauBasisStatus, XauPriceBar
from src.models.xau_quikstrike_fusion import (
    XauFusionContextStatus,
    XauFusionContextSummary,
    XauFusionMatchKey,
    XauFusionReportStatus,
    XauQuikStrikeFusionReport,
)
from src.models.xau_systematic_research import (
    XauSystematicCmeSourceMode,
    XauSystematicCycleRequest,
    XauSystematicPriceProvider,
)
from src.xau_systematic_research.alignment_engine import (
    XauSystematicAlignmentEngine,
    map_cme_level_to_spot_equivalent,
)
from tests.helpers.test_xau_quikstrike_fusion_data import (
    sample_coverage_summary,
    sample_fused_row,
    sample_matrix_source_ref,
    sample_matrix_source_value,
    sample_vol2vol_source_ref,
    sample_vol2vol_source_value,
)


def test_missing_basis_blocks_and_preserves_unavailable_values_as_none() -> None:
    bars = _many_bars()
    report = _fusion_report(include_gc_reference=False)
    state = XauSystematicAlignmentEngine().align(
        request=_request(),
        cycle_id="cycle",
        created_at=bars[-1].timestamp,
        fusion_report=report,
        fusion_report_path=None,
        price_bars=bars,
        bars_path=Path("bars.csv"),
        current_timestamp=bars[-1].timestamp,
    )

    assert state.readiness.blocked is True
    assert state.basis.basis_status == XauBasisStatus.UNAVAILABLE
    assert state.basis.basis_points is None
    assert state.mapped_structure.top_mapped_walls[0]["mapped_level"] is None


def test_missing_traded_bars_blocks() -> None:
    state = XauSystematicAlignmentEngine().align(
        request=_request(),
        cycle_id="cycle",
        created_at=datetime(2026, 6, 8, 10, 0, tzinfo=UTC),
        fusion_report=_fusion_report(),
        fusion_report_path=None,
        price_bars=[],
        bars_path=None,
    )

    assert state.readiness.blocked is True
    assert "no traded price bars" in state.no_trade_reasons


def test_cme_partial_with_price_context_is_partial_not_ready() -> None:
    bars = _many_bars()
    state = XauSystematicAlignmentEngine().align(
        request=_request(),
        cycle_id="cycle",
        created_at=bars[-1].timestamp,
        fusion_report=_fusion_report(),
        fusion_report_path=None,
        price_bars=bars,
        bars_path=Path("bars.csv"),
        current_timestamp=bars[-1].timestamp,
        cme_partial=True,
    )

    assert state.readiness.partial is True
    assert state.readiness.ready_for_shadow_review is False


def test_complete_context_is_ready_for_shadow_review_but_not_signal() -> None:
    bars = _many_bars()
    state = XauSystematicAlignmentEngine().align(
        request=_request(),
        cycle_id="cycle",
        created_at=bars[-1].timestamp,
        fusion_report=_fusion_report(),
        fusion_report_path=None,
        price_bars=bars,
        bars_path=Path("bars.csv"),
        current_timestamp=bars[-1].timestamp,
    )

    assert state.readiness.ready_for_shadow_review is True
    assert state.signal_allowed is False
    assert state.research_only is True


def test_basis_formula_maps_cme_level_to_spot_equivalent() -> None:
    mapped = map_cme_level_to_spot_equivalent(
        xauusd_spot_price=4050,
        gc_futures_price=4070,
        cme_level=4100,
    )

    assert mapped == 4080


def _request() -> XauSystematicCycleRequest:
    return XauSystematicCycleRequest(
        cycle_label="manual",
        cycle_time="manual",
        cme_source_mode=XauSystematicCmeSourceMode.LATEST_EXISTING,
        price_provider=XauSystematicPriceProvider.LOCAL_BARS,
        research_only_acknowledged=True,
    )


def _fusion_report(*, include_gc_reference: bool = True) -> XauQuikStrikeFusionReport:
    vol2vol_value = sample_vol2vol_source_value().model_copy(
        update={
            "future_reference_price": 4070.0 if include_gc_reference else None,
            "value_type": "volume",
            "value": 20.0,
        }
    )
    matrix_value = sample_matrix_source_value().model_copy(
        update={"value_type": "volume", "value": 20.0}
    )
    row = sample_fused_row().model_copy(
        update={
            "match_key": XauFusionMatchKey(
                strike=4100,
                expiration_code="G2RK6",
                option_type="call",
                value_type="volume",
            ),
            "vol2vol_value": vol2vol_value,
            "matrix_value": matrix_value,
        }
    )
    return XauQuikStrikeFusionReport(
        report_id="fusion_report",
        status=XauFusionReportStatus.COMPLETED,
        created_at=datetime(2026, 6, 8, 15, 0, tzinfo=ZoneInfo("Asia/Bangkok")),
        vol2vol_source=sample_vol2vol_source_ref(),
        matrix_source=sample_matrix_source_ref(),
        coverage=sample_coverage_summary(),
        context_summary=XauFusionContextSummary(
            basis_status=XauFusionContextStatus.AVAILABLE,
            iv_range_status=XauFusionContextStatus.AVAILABLE,
            open_regime_status=XauFusionContextStatus.AVAILABLE,
            candle_acceptance_status=XauFusionContextStatus.AVAILABLE,
            realized_volatility_status=XauFusionContextStatus.AVAILABLE,
            source_agreement_status=XauFusionContextStatus.AVAILABLE,
        ),
        expected_range_snapshot=XauExpectedRangeSnapshot(
            source_report_id="vol2vol_report",
            source_view="vol2vol",
            capture_timestamp=datetime(2026, 6, 8, 8, 0, tzinfo=UTC),
            source_status=XauExpectedRangeSourceStatus.UNKNOWN,
            product="Gold",
            option_product_code="OG|GC",
            futures_symbol="GC",
            reference_futures_price=4070,
            cme_numeric_1sd=30,
            cme_numeric_2sd=60,
            cme_numeric_3sd=90,
            upper_1sd=4100,
            lower_1sd=4040,
            upper_2sd=4130,
            lower_2sd=4010,
            upper_3sd=4160,
            lower_3sd=3980,
            range_source=XauExpectedRangeSource.CME_NATIVE,
            extraction_quality=XauExpectedRangeExtractionQuality.COMPLETE,
        ),
        fused_row_count=1,
        fused_rows=[row],
    )


def _many_bars() -> list[XauPriceBar]:
    tz = ZoneInfo("Asia/Bangkok")
    start = datetime(2026, 6, 8, 13, 0, tzinfo=tz)
    return [_bar(start + timedelta(minutes=index), 4050 + (index * 0.05)) for index in range(121)]


def _bar(timestamp: datetime, close: float) -> XauPriceBar:
    return XauPriceBar(
        timestamp=timestamp,
        open=close,
        high=close + 1,
        low=close - 1,
        close=close,
        volume=10,
        symbol="XAUUSD",
        timeframe="1m",
    )
