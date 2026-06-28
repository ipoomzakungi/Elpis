from datetime import UTC, datetime

import pytest

from src.models.xau_walk_forward_research import (
    XauResearchOrderPlanConfig,
    XauResearchOrderSide,
    XauResearchOrderStage,
    XauResearchRiskConfig,
    XauResearchRiskStatus,
)
from src.xau_walk_forward.order_planner import generate_research_order_plans
from src.xau_walk_forward.price_provider import ManualPriceProvider
from src.xau_walk_forward.sd_source import fixture_sd_snapshot


def test_order_planner_builds_initial_long_and_short_levels() -> None:
    timestamp = datetime(2026, 6, 8, 10, 10, tzinfo=UTC)
    plans = generate_research_order_plans(
        snapshot_id="snap_1",
        timestamp=timestamp,
        price_snapshot=ManualPriceProvider().snapshot(
            timestamp=timestamp,
            future_reference_price=4500.0,
            traded_reference_price=4470.0,
        ),
        sd_snapshot=fixture_sd_snapshot(timestamp=timestamp, reference_price=4500.0),
        config=XauResearchOrderPlanConfig(max_recovery_steps=0),
        risk_config=XauResearchRiskConfig(),
    )

    long_plan = next(plan for plan in plans if plan.side == XauResearchOrderSide.LONG_REVERSION)
    short_plan = next(plan for plan in plans if plan.side == XauResearchOrderSide.SHORT_REVERSION)
    assert long_plan.entry_level == pytest.approx(4420.0)
    assert long_plan.target_level == pytest.approx(4445.0)
    assert long_plan.stop_level == pytest.approx(4407.5)
    assert long_plan.tp_points == pytest.approx(25.0)
    assert long_plan.sl_points == pytest.approx(12.5)
    assert short_plan.entry_level == pytest.approx(4520.0)
    assert short_plan.target_level == pytest.approx(4495.0)
    assert short_plan.stop_level == pytest.approx(4532.5)
    assert short_plan.signal_allowed is False


def test_order_planner_supports_custom_stop_sd() -> None:
    timestamp = datetime(2026, 6, 8, 10, 10, tzinfo=UTC)
    plans = generate_research_order_plans(
        snapshot_id="snap_1b",
        timestamp=timestamp,
        price_snapshot=ManualPriceProvider().snapshot(
            timestamp=timestamp,
            future_reference_price=4500.0,
            traded_reference_price=4470.0,
        ),
        sd_snapshot=fixture_sd_snapshot(timestamp=timestamp, reference_price=4500.0),
        config=XauResearchOrderPlanConfig(stop_sd_abs=0.5, max_recovery_steps=0),
        risk_config=XauResearchRiskConfig(),
    )

    long_plan = next(
        plan for plan in plans if plan.side == XauResearchOrderSide.LONG_REVERSION
    )
    short_plan = next(
        plan for plan in plans if plan.side == XauResearchOrderSide.SHORT_REVERSION
    )
    assert long_plan.stop_level == pytest.approx(4407.5)
    assert short_plan.stop_level == pytest.approx(4532.5)


def test_recovery_size_formula_and_max_size_block() -> None:
    timestamp = datetime(2026, 6, 8, 10, 10, tzinfo=UTC)
    plans = generate_research_order_plans(
        snapshot_id="snap_2",
        timestamp=timestamp,
        price_snapshot=ManualPriceProvider().snapshot(
            timestamp=timestamp,
            future_reference_price=4500.0,
            traded_reference_price=4470.0,
        ),
        sd_snapshot=fixture_sd_snapshot(timestamp=timestamp, reference_price=4500.0),
        config=XauResearchOrderPlanConfig(max_recovery_steps=1),
        risk_config=XauResearchRiskConfig(
            recovery_enabled=True,
            point_value_per_size_unit=1.0,
            max_size=1.0,
            leverage=100.0,
        ),
    )

    recovery = next(plan for plan in plans if plan.stage == XauResearchOrderStage.RECOVERY_1)
    assert recovery.planned_size == pytest.approx(1.5)
    assert recovery.risk_status == XauResearchRiskStatus.BLOCKED
    assert "max_size" in recovery.risk_reasons[0]


def test_recovery_missing_point_value_is_missing_config() -> None:
    timestamp = datetime(2026, 6, 8, 10, 10, tzinfo=UTC)
    plans = generate_research_order_plans(
        snapshot_id="snap_3",
        timestamp=timestamp,
        price_snapshot=ManualPriceProvider().snapshot(
            timestamp=timestamp,
            future_reference_price=4500.0,
            traded_reference_price=4470.0,
        ),
        sd_snapshot=fixture_sd_snapshot(timestamp=timestamp, reference_price=4500.0),
        config=XauResearchOrderPlanConfig(max_recovery_steps=1),
        risk_config=XauResearchRiskConfig(recovery_enabled=True),
    )

    recovery = next(plan for plan in plans if plan.stage == XauResearchOrderStage.RECOVERY_1)
    assert recovery.risk_status == XauResearchRiskStatus.MISSING_CONFIG
    assert recovery.planned_size is None


def test_recovery_multiplier_scales_recovery_size() -> None:
    timestamp = datetime(2026, 6, 8, 10, 10, tzinfo=UTC)
    plans = generate_research_order_plans(
        snapshot_id="snap_4",
        timestamp=timestamp,
        price_snapshot=ManualPriceProvider().snapshot(
            timestamp=timestamp,
            future_reference_price=4500.0,
            traded_reference_price=4470.0,
        ),
        sd_snapshot=fixture_sd_snapshot(timestamp=timestamp, reference_price=4500.0),
        config=XauResearchOrderPlanConfig(max_recovery_steps=1),
        risk_config=XauResearchRiskConfig(
            recovery_enabled=True,
            point_value_per_size_unit=1.0,
            recovery_multiplier=3.0,
            max_size=10.0,
        ),
    )

    recovery = next(plan for plan in plans if plan.stage == XauResearchOrderStage.RECOVERY_1)
    assert recovery.planned_size == pytest.approx(4.5)
    assert recovery.risk_status == XauResearchRiskStatus.ALLOWED
