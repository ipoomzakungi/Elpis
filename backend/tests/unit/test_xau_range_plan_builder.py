from __future__ import annotations

from datetime import date, datetime

import pytest

from src.models.xau_vol2vol_history_walkforward import (
    XauOiConfluenceLabel,
    XauPlanReadiness,
    XauSdEntryLevel,
    XauSlMode,
    XauTpMode,
    XauTradeSide,
    XauVol2VolRangeDeskSnapshot,
    XauVol2VolStrikeSnapshot,
    XauWormholeLabel,
)
from src.xau_vol2vol_history_walkforward.range_plan_builder import (
    XauRangePlanBuildConfig,
    build_sd_mean_reversion_plans,
    map_future_level_to_cfd,
)


def test_basis_diff_formula_maps_future_to_cfd_level() -> None:
    assert map_future_level_to_cfd(4094.10, 10.33) == 4083.77


def test_range_plan_builder_maps_long_2sd_and_half_sd_tp() -> None:
    plans = build_sd_mean_reversion_plans(
        range_snapshot=_range_snapshot(),
        config=XauRangePlanBuildConfig(
            entry_sds=(XauSdEntryLevel.TWO_SD,),
            tp_modes=(XauTpMode.HALF_SD,),
            sl_modes=(XauSlMode.THREE_5SD,),
            sides=(XauTradeSide.LONG_REVERSION,),
        ),
    )

    plan = plans[0]
    assert plan.readiness == XauPlanReadiness.READY
    assert plan.entry_level == 4071.37
    assert plan.target_level == 4083.77
    assert plan.stop_level == pytest.approx(4046.57)


def test_range_plan_builder_maps_short_2sd_and_fixed_25_tp() -> None:
    plans = build_sd_mean_reversion_plans(
        range_snapshot=_range_snapshot(),
        config=XauRangePlanBuildConfig(
            entry_sds=(XauSdEntryLevel.TWO_SD,),
            tp_modes=(XauTpMode.FIXED_25,),
            sl_modes=(XauSlMode.NEXT_HALF_SD,),
            sides=(XauTradeSide.SHORT_REVERSION,),
        ),
    )

    plan = plans[0]
    assert plan.entry_level == 4120.97
    assert plan.target_level == pytest.approx(4095.97)
    assert plan.stop_level == 4133.37


def test_missing_diff_blocks_readiness() -> None:
    snapshot = _range_snapshot().model_copy(update={"diff": None})

    plan = build_sd_mean_reversion_plans(
        range_snapshot=snapshot,
        config=XauRangePlanBuildConfig(
            entry_sds=(XauSdEntryLevel.TWO_SD,),
            tp_modes=(XauTpMode.HALF_SD,),
            sl_modes=(XauSlMode.NEXT_HALF_SD,),
            sides=(XauTradeSide.LONG_REVERSION,),
        ),
    )[0]

    assert plan.readiness == XauPlanReadiness.BLOCKED
    assert "Missing Diff/Basis" in plan.blocked_reasons[0]


def test_oi_confluence_strong_when_entry_near_top_ranked_strike() -> None:
    rows = [
        _strike(4081.7, total=200),
        _strike(4100.0, total=50),
        _strike(4050.0, total=10),
    ]

    plan = build_sd_mean_reversion_plans(
        range_snapshot=_range_snapshot(),
        strike_rows=rows,
        config=XauRangePlanBuildConfig(
            entry_sds=(XauSdEntryLevel.TWO_SD,),
            tp_modes=(XauTpMode.HALF_SD,),
            sl_modes=(XauSlMode.NEXT_HALF_SD,),
            sides=(XauTradeSide.LONG_REVERSION,),
        ),
    )[0]

    assert plan.oi_confluence is not None
    assert plan.oi_confluence.confluence_label == XauOiConfluenceLabel.STRONG


def test_wormhole_detected_between_entry_and_target() -> None:
    rows = [_strike(4085, total=1), _strike(4090, total=2), _strike(4100, total=100)]

    plan = build_sd_mean_reversion_plans(
        range_snapshot=_range_snapshot(),
        strike_rows=rows,
        config=XauRangePlanBuildConfig(
            entry_sds=(XauSdEntryLevel.TWO_SD,),
            tp_modes=(XauTpMode.HALF_SD,),
            sl_modes=(XauSlMode.NEXT_HALF_SD,),
            sides=(XauTradeSide.LONG_REVERSION,),
        ),
    )[0]

    assert plan.wormhole_state is not None
    assert plan.wormhole_state.wormhole_label == XauWormholeLabel.TARGET_VACUUM
    assert "not direction" in plan.wormhole_state.notes[0]


def _range_snapshot() -> XauVol2VolRangeDeskSnapshot:
    return XauVol2VolRangeDeskSnapshot(
        session_date=date(2026, 7, 8),
        observed_at=datetime.fromisoformat("2026-07-08T10:00:00+07:00"),
        series="G2WN6",
        future_open=4106.5,
        cfd_open=4096.17,
        diff=10.33,
        vol_now=28.0,
        sd_step_1=24.8,
        cfd_buy_1sd=4083.77,
        cfd_buy_2sd=4071.37,
        cfd_buy_3sd=4058.97,
        cfd_sell_1sd=4108.57,
        cfd_sell_2sd=4120.97,
        cfd_sell_3sd=4133.37,
        future_buy_1sd=4094.10,
    )


def _strike(strike: float, *, total: float) -> XauVol2VolStrikeSnapshot:
    return XauVol2VolStrikeSnapshot(
        session_date=date(2026, 7, 8),
        observed_at=datetime.fromisoformat("2026-07-08T10:00:00+07:00"),
        series="G2WN6",
        snapshot_kind="open_interest",
        strike=strike,
        call=total,
        put=0,
        total=total,
        source="fixture",
    )
