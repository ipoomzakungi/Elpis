import pytest

from src.models.xau_range_desk import (
    XauRangeDeskLevelInput,
    XauRangeDeskLevelKind,
    XauRangeDeskOiWallInput,
    XauRangeDeskPlanRequest,
    XauRangeDeskReadiness,
    XauRangeDeskZoneKind,
)
from src.xau_range_desk.planner import build_xau_range_desk_plan


def test_range_desk_maps_future_level_to_traded_level_with_diff() -> None:
    plan = build_xau_range_desk_plan(
        XauRangeDeskPlanRequest(
            future_reference_price=4500.0,
            traded_reference_price=4470.0,
            levels=[
                XauRangeDeskLevelInput(
                    label=XauRangeDeskLevelKind.UPPER_2SD,
                    futures_level=4520.0,
                )
            ],
        )
    )

    assert plan.basis_snapshot.diff_points == pytest.approx(30.0)
    assert plan.basis_snapshot.traded_offset == pytest.approx(-30.0)
    assert plan.traded_levels[0].mapped_traded_level == pytest.approx(4490.0)
    assert plan.signal_allowed is False
    assert plan.research_only is True


def test_range_desk_builds_sd_zones_and_target_planning_levels() -> None:
    plan = build_xau_range_desk_plan(
        XauRangeDeskPlanRequest(
            future_reference_price=4500.0,
            traded_reference_price=4470.0,
            session_open_price=4472.0,
            levels=_full_sd_levels(),
            oi_walls=[
                XauRangeDeskOiWallInput(wall_id="wall_4485", futures_level=4515.0),
                XauRangeDeskOiWallInput(wall_id="wall_4460", futures_level=4490.0),
            ],
        )
    )

    assert plan.readiness == XauRangeDeskReadiness.READY
    assert plan.block_size_points == pytest.approx(10.0)
    no_trade_zone = next(
        zone for zone in plan.zones if zone.zone == XauRangeDeskZoneKind.NO_TRADE_INSIDE_1SD
    )
    assert no_trade_zone.lower_traded_level == pytest.approx(4460.0)
    assert no_trade_zone.upper_traded_level == pytest.approx(4480.0)
    short_plan = next(
        target for target in plan.target_plans if target.side == "short_reversion_research_plan"
    )
    assert short_plan.target_1 == pytest.approx(4480.0)
    assert short_plan.target_2 == pytest.approx(4470.0)
    assert short_plan.target_3 == pytest.approx(4460.0)
    assert short_plan.invalidation_reference == pytest.approx(4500.0)


def test_range_desk_preserves_missing_context_as_partial_not_signal() -> None:
    plan = build_xau_range_desk_plan(
        XauRangeDeskPlanRequest(
            future_reference_price=4500.0,
            traded_reference_price=4470.0,
            levels=[
                XauRangeDeskLevelInput(
                    label=XauRangeDeskLevelKind.LOWER_1SD,
                    futures_level=4490.0,
                )
            ],
        )
    )

    assert plan.readiness == XauRangeDeskReadiness.PARTIAL
    assert "levels.upper_1sd" in plan.missing_inputs
    assert "levels.upper_3sd" in plan.missing_inputs
    assert plan.signal_allowed is False


def _full_sd_levels() -> list[XauRangeDeskLevelInput]:
    return [
        XauRangeDeskLevelInput(label=XauRangeDeskLevelKind.LOWER_3SD, futures_level=4440.0),
        XauRangeDeskLevelInput(label=XauRangeDeskLevelKind.LOWER_2SD, futures_level=4460.0),
        XauRangeDeskLevelInput(label=XauRangeDeskLevelKind.LOWER_1SD, futures_level=4490.0),
        XauRangeDeskLevelInput(label=XauRangeDeskLevelKind.MEAN, futures_level=4500.0),
        XauRangeDeskLevelInput(label=XauRangeDeskLevelKind.UPPER_1SD, futures_level=4510.0),
        XauRangeDeskLevelInput(label=XauRangeDeskLevelKind.UPPER_2SD, futures_level=4520.0),
        XauRangeDeskLevelInput(label=XauRangeDeskLevelKind.UPPER_3SD, futures_level=4530.0),
    ]
