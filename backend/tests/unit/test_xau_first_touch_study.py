from __future__ import annotations

import json
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from src.models.xau_market_context import XauPriceBar
from src.xau_first_touch_study.events import (
    build_first_touch_events,
    evaluate_first_passage,
    evaluate_published_label,
)
from src.xau_first_touch_study.models import (
    CountingMode,
    EventSide,
    FirstPassageStatus,
    FirstTouchEvent,
    MappedPlan,
    MappingMode,
    SnapshotSelection,
    SourceSnapshot,
    TimeAnchor,
)
from src.xau_first_touch_study.registry import load_registry
from src.xau_first_touch_study.runner import FirstTouchStudyConfig, run_study
from src.xau_first_touch_study.selection import (
    latest_closed_bar,
    map_selection,
    select_snapshot,
)
from src.xau_first_touch_study.shadow import ShadowSession

ZONE = ZoneInfo("Asia/Bangkok")
SESSION = date(2026, 7, 13)


def test_aggregated_counts_only_first_touch_per_tier_and_repeats() -> None:
    plan = _plan()
    bars = [
        _bar(8, 0, 100, 101, 99, 100),
        _bar(8, 1, 100, 121, 99, 120),
        _bar(8, 2, 120, 121, 119, 120),
        _bar(8, 3, 120, 131, 119, 130),
    ]

    events = build_first_touch_events(
        plan,
        bars,
        counting_mode=CountingMode.AGGREGATED,
    )

    assert [item.tier for item in events] == [1, 2, 3]
    assert len({item.tier for item in events}) == 3
    assert events[0].repeated_touch_count == 2
    assert all(item.first_touch for item in events)


def test_side_specific_remains_distinct_from_aggregated() -> None:
    plan = _plan()
    bars = [
        _bar(8, 0, 100, 111, 89, 100),
        _bar(8, 1, 100, 121, 79, 100),
    ]

    aggregated = build_first_touch_events(
        plan,
        bars,
        counting_mode=CountingMode.AGGREGATED,
    )
    side_specific = build_first_touch_events(
        plan,
        bars,
        counting_mode=CountingMode.SIDE_SPECIFIC,
    )

    assert len(aggregated) == 2
    assert len(side_specific) == 4
    assert {item.counting_mode for item in aggregated} == {CountingMode.AGGREGATED}
    assert {item.counting_mode for item in side_specific} == {CountingMode.SIDE_SPECIFIC}


def test_published_label_can_succeed_after_more_than_25_adverse_points() -> None:
    event = _event()
    bars = [
        _bar(8, 0, 100, 101, 99, 100),
        _bar(8, 1, 100, 101, 60, 70),
        _bar(8, 2, 70, 126, 69, 125),
    ]

    outcome = evaluate_published_label(event, bars)

    assert outcome.success is True
    assert outcome.maximum_adverse_before_reversal == 40


def test_strict_first_passage_stops_when_sl25_occurs_first() -> None:
    event = _event()
    bars = [
        _bar(8, 0, 100, 101, 99, 100),
        _bar(8, 1, 100, 101, 74, 75),
        _bar(8, 2, 75, 126, 75, 125),
    ]

    outcome = evaluate_first_passage(event, bars, tp_points=25, sl_points=25)

    assert outcome.status == FirstPassageStatus.SL_FIRST
    assert outcome.net_points == -25


def test_same_bar_ordering_remains_ambiguous_without_fine_data() -> None:
    event = _event()
    bars = [_bar(8, 0, 100, 126, 74, 100)]

    outcome = evaluate_first_passage(event, bars, tp_points=25, sl_points=25)

    assert outcome.status == FirstPassageStatus.SAME_BAR_AMBIGUOUS
    assert outcome.include_in_expectancy is False


def test_dte_nearest_080_selection_is_deterministic() -> None:
    low_activity = _snapshot("A", 0.79, 10, minute=0)
    high_activity_late = _snapshot("B", 0.81, 20, minute=2)
    high_activity_early = _snapshot("C", 0.81, 20, minute=1)

    selected = select_snapshot(
        [low_activity, high_activity_late, high_activity_early],
        anchor=TimeAnchor.T0_DTE_080,
        session_date=SESSION,
    )

    assert selected is not None
    assert selected.snapshot.series == "C"
    assert selected.strict_dte_eligible is True


def test_selected_plan_never_mixes_series() -> None:
    selected = select_snapshot(
        [_snapshot("A", 0.8, 20), _snapshot("B", 0.9, 100)],
        anchor=TimeAnchor.T0_DTE_080,
        session_date=SESSION,
    )

    assert selected is not None
    assert selected.snapshot.series == "A"
    assert all(level in selected.snapshot.ranges for level in (1, 2, 3))


def test_t2_does_not_select_future_snapshot() -> None:
    before = _snapshot("A", 0.8, 10, hour=6, minute=59)
    after = _snapshot("B", 0.8, 100, hour=7, minute=1)

    selected = select_snapshot(
        [after, before],
        anchor=TimeAnchor.T2_BANGKOK_0700,
        session_date=SESSION,
    )

    assert selected is not None
    assert selected.snapshot.series == "A"
    assert selected.snapshot.observed_at.astimezone(ZONE).time() < time(7, 0)


def test_mapping_modes_remain_separate() -> None:
    selection = _selection()
    bars = [
        _bar(6, 58, 100, 100, 100, 100),
        _bar(7, 0, 105, 105, 105, 105),
    ]

    distance = map_selection(
        selection,
        bars,
        mapping_mode=MappingMode.DISTANCE_REANCHORED,
    )
    same_time = map_selection(
        selection,
        bars,
        mapping_mode=MappingMode.SAME_TIME_REFERENCE_BASIS,
    )

    assert distance is not None
    assert same_time is not None
    assert distance.mapping_quality == "distance_proxy_not_validated_basis"
    assert same_time.mapping_quality == "same_time_reference_pass"
    assert distance.basis_points is None
    assert same_time.basis_points == 100
    assert distance.mapped_levels[1] != same_time.mapped_levels[1]


def test_closed_bar_timing_is_enforced() -> None:
    bar = _bar(7, 0, 100, 100, 100, 100)

    assert latest_closed_bar([bar], datetime(2026, 7, 13, 7, 0, tzinfo=ZONE)) is None
    assert latest_closed_bar([bar], datetime(2026, 7, 13, 7, 1, tzinfo=ZONE)) == bar


def test_oi_hard_feature_is_disabled_for_distance_mapping() -> None:
    plan = map_selection(
        _selection(),
        [_bar(6, 58, 100, 100, 100, 100), _bar(7, 0, 105, 105, 105, 105)],
        mapping_mode=MappingMode.DISTANCE_REANCHORED,
    )

    assert plan is not None
    assert plan.oi_hard_feature_allowed is False


def test_same_time_mapping_rejects_stale_reference() -> None:
    stale_snapshot = _snapshot("A", 0.8, 10, hour=7, minute=10)
    selection = SnapshotSelection(
        anchor=TimeAnchor.T0_DTE_080,
        snapshot=stale_snapshot,
        activation_at=stale_snapshot.observed_at,
        selection_reason="test",
        target_at=None,
        dte_error=0,
        strict_dte_eligible=True,
    )

    plan = map_selection(
        selection,
        [_bar(7, 0, 100, 100, 100, 100)],
        mapping_mode=MappingMode.SAME_TIME_REFERENCE_BASIS,
    )

    assert plan is None


def test_costs_do_not_multiply_event_count() -> None:
    event = _event()
    bars = [
        _bar(8, 0, 100, 101, 99, 100),
        _bar(8, 1, 100, 126, 100, 125),
    ]

    outcomes = [
        evaluate_first_passage(
            event,
            bars,
            tp_points=25,
            sl_points=25,
            cost_points=cost,
        )
        for cost in (0, 0.5, 1.0, 2.5)
    ]

    assert len(outcomes) == 4
    assert {item.event_id for item in outcomes} == {event.event_id}
    assert [item.net_points for item in outcomes] == [25, 24.5, 24, 22.5]


def test_shadow_state_machine_creates_no_order_and_locks_tier() -> None:
    shadow = ShadowSession()
    shadow.load_plan(_plan())

    candidate = shadow.first_touch(_event(tier=2))
    repeated = shadow.first_touch(_event(tier=2, event_id="repeat"))

    assert candidate is not None
    assert candidate["order_submission_allowed"] is False
    assert repeated is None
    assert shadow.as_record()["broker_orders"] == []


def test_shadow_has_no_recovery_martingale_or_averaging_path() -> None:
    record = ShadowSession().as_record()

    assert record["recovery_allowed"] is False
    assert record["martingale_allowed"] is False
    assert record["averaging_allowed"] is False


def test_all_event_and_plan_outputs_remain_research_only() -> None:
    plan = _plan()
    event = _event()

    for value in (plan, event):
        assert value.research_only is True
        assert value.signal_allowed is False
        assert value.order_submission_allowed is False


def test_registry_hash_is_frozen() -> None:
    registry = load_registry(Path("config/xau_vol2vol_first_touch_study_v1.json"))

    assert registry["experiment_hash"] == (
        "446757f6c055ea88654b73a07650ac694ddad10981edbbf2143475903d2882f7"
    )


def test_runner_writes_required_blocked_research_artifacts(tmp_path: Path) -> None:
    registry = Path("config/xau_vol2vol_first_touch_study_v1.json")
    bars = tmp_path / "bars"
    bars.mkdir()
    run_dir = run_study(
        FirstTouchStudyConfig(
            vol2vol_root=tmp_path / "vol2vol",
            price_bars_folder=bars,
            registry_path=registry,
            output_root=tmp_path / "reports",
            session_date_from=SESSION,
            session_date_to=SESSION,
            as_of_date=SESSION,
        )
    )

    required = {
        "study_manifest.json",
        "session_eligibility.json",
        "selected_snapshots.json",
        "first_touch_events.json",
        "published_label_results.json",
        "strict_first_passage_results.json",
        "barrier_sensitivity.json",
        "dte_sensitivity.json",
        "time_anchor_sensitivity.json",
        "mapping_sensitivity.json",
        "side_comparison.json",
        "oi_iv_flow_context.json",
        "external_prior_comparison.json",
        "shadow_plan.json",
        "integrity_report.json",
        "review_handoff.md",
        "metadata.json",
    }
    assert required <= {item.name for item in run_dir.iterdir()}
    metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
    shadow = json.loads((run_dir / "shadow_plan.json").read_text(encoding="utf-8"))
    assert metadata["research_only"] is True
    assert metadata["signal_allowed"] is False
    assert metadata["order_submission_allowed"] is False
    assert shadow["session"]["order_submission_allowed"] is False


def _snapshot(
    series: str,
    dte: float,
    activity: float,
    *,
    hour: int = 7,
    minute: int = 0,
) -> SourceSnapshot:
    return SourceSnapshot(
        snapshot_id=f"{series}-{hour}-{minute}",
        session_date=SESSION,
        observed_at=datetime(2026, 7, 13, hour, minute, tzinfo=ZONE),
        series=series,
        kind="intraday",
        source_dte=dte,
        future_reference=200,
        atm_iv=15,
        iv_change=0,
        future_change=0,
        activity_total=activity,
        ranges={1: (190, 210), 2: (180, 220), 3: (170, 230)},
    )


def _selection() -> SnapshotSelection:
    snapshot = _snapshot("A", 0.8, 10, hour=6, minute=59)
    return SnapshotSelection(
        anchor=TimeAnchor.T2_BANGKOK_0700,
        snapshot=snapshot,
        activation_at=datetime(2026, 7, 13, 7, 2, tzinfo=ZONE),
        selection_reason="test",
        target_at=datetime(2026, 7, 13, 7, 0, tzinfo=ZONE),
        dte_error=0,
        strict_dte_eligible=True,
    )


def _plan() -> MappedPlan:
    selection = _selection()
    return MappedPlan(
        plan_id="plan",
        session_date=SESSION,
        anchor=TimeAnchor.T0_DTE_080,
        mapping_mode=MappingMode.DISTANCE_REANCHORED,
        selection=selection,
        planning_xau_timestamp=datetime(2026, 7, 13, 7, 0, tzinfo=ZONE),
        planning_xau_price=100,
        source_xau_timestamp=datetime(2026, 7, 13, 6, 58, tzinfo=ZONE),
        source_xau_price=100,
        source_gap_seconds=0,
        mapping_quality="distance_proxy_not_validated_basis",
        closed_bar_status="closed",
        basis_points=None,
        mapped_levels={1: (90, 110), 2: (80, 120), 3: (70, 130)},
        one_sd_points=10,
        oi_hard_feature_allowed=False,
    )


def _event(
    *,
    tier: int = 2,
    event_id: str = "event",
) -> FirstTouchEvent:
    return FirstTouchEvent(
        event_id=event_id,
        plan_id="plan",
        session_date=SESSION,
        anchor=TimeAnchor.T0_DTE_080,
        mapping_mode=MappingMode.DISTANCE_REANCHORED,
        counting_mode=CountingMode.AGGREGATED,
        tier=tier,
        side=EventSide.LOWER_LONG,
        boundary=100,
        touch_timestamp=datetime(2026, 7, 13, 8, 0, tzinfo=ZONE),
        touch_bar_index=0,
        source_series="A",
        source_dte=0.8,
        selected_snapshot_at=datetime(2026, 7, 13, 7, 0, tzinfo=ZONE),
        repeated_touch_count=0,
        one_sd_points=10,
    )


def _bar(
    hour: int,
    minute: int,
    open_price: float,
    high: float,
    low: float,
    close: float,
) -> XauPriceBar:
    return XauPriceBar(
        timestamp=datetime(2026, 7, 13, hour, minute, tzinfo=ZONE),
        open=open_price,
        high=high,
        low=low,
        close=close,
    )
