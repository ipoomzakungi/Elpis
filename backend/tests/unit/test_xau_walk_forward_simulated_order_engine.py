from datetime import UTC, datetime, timedelta

from src.models.xau_walk_forward_research import (
    XauOhlcvBar,
    XauResearchOrderOutcomeStatus,
    XauResearchOrderPlanConfig,
    XauResearchOrderSide,
    XauResearchRiskConfig,
)
from src.xau_walk_forward.order_planner import generate_research_order_plans
from src.xau_walk_forward.price_provider import ManualPriceProvider
from src.xau_walk_forward.sd_source import fixture_sd_snapshot
from src.xau_walk_forward.simulated_order_engine import simulate_research_order_outcome


def test_long_plan_hits_target() -> None:
    timestamp = datetime(2026, 6, 8, 10, 10, tzinfo=UTC)
    long_plan = _plan(timestamp, XauResearchOrderSide.LONG_REVERSION)
    outcome = simulate_research_order_outcome(
        long_plan,
        [
            XauOhlcvBar(
                timestamp=timestamp + timedelta(minutes=10),
                open=4430,
                high=4448,
                low=4418,
                close=4446,
            )
        ],
    )

    assert outcome.status == XauResearchOrderOutcomeStatus.TARGET_HIT
    assert outcome.realized_points == 25.0


def test_short_plan_hits_stop() -> None:
    timestamp = datetime(2026, 6, 8, 10, 10, tzinfo=UTC)
    short_plan = _plan(timestamp, XauResearchOrderSide.SHORT_REVERSION)
    outcome = simulate_research_order_outcome(
        short_plan,
        [
            XauOhlcvBar(
                timestamp=timestamp + timedelta(minutes=10),
                open=4521,
                high=4535,
                low=4519,
                close=4533,
            )
        ],
    )

    assert outcome.status == XauResearchOrderOutcomeStatus.STOP_HIT
    assert outcome.realized_points == -12.5


def test_ambiguous_same_candle_can_be_marked_ambiguous() -> None:
    timestamp = datetime(2026, 6, 8, 10, 10, tzinfo=UTC)
    long_plan = _plan(timestamp, XauResearchOrderSide.LONG_REVERSION)
    outcome = simulate_research_order_outcome(
        long_plan,
        [
            XauOhlcvBar(
                timestamp=timestamp + timedelta(minutes=10),
                open=4420,
                high=4450,
                low=4400,
                close=4430,
            )
        ],
        conservative_ordering=False,
    )

    assert outcome.status == XauResearchOrderOutcomeStatus.AMBIGUOUS


def test_missing_bars_returns_unavailable() -> None:
    timestamp = datetime(2026, 6, 8, 10, 10, tzinfo=UTC)
    outcome = simulate_research_order_outcome(
        _plan(timestamp, XauResearchOrderSide.LONG_REVERSION),
        [],
    )

    assert outcome.status == XauResearchOrderOutcomeStatus.UNAVAILABLE


def _plan(timestamp, side):
    plans = generate_research_order_plans(
        snapshot_id="snap_sim",
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
    return next(plan for plan in plans if plan.side == side)
