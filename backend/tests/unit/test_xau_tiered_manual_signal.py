from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from src.models.xau_market_context import XauPriceBar
from src.models.xau_tiered_manual_signal import (
    XauBrokerQuote,
    XauManualSignalAcknowledgementRequest,
    XauManualSignalState,
)
from src.xau_first_touch_study.models import (
    CountingMode,
    EventSide,
    FirstTouchEvent,
    MappedPlan,
    MappingMode,
    SnapshotSelection,
    SourceSnapshot,
    TimeAnchor,
)
from src.xau_tiered_manual_signal.journal import STREAMS, ManualSignalJournal
from src.xau_tiered_manual_signal.policy import load_policy
from src.xau_tiered_manual_signal.runner import TieredStudyConfig, run_tiered_study
from src.xau_tiered_manual_signal.service import XauTieredManualSignalService
from src.xau_tiered_manual_signal.tiers import (
    build_tier_events,
    evaluate_tier_barrier,
    executable_rejection_entry,
    extended_tier_levels,
    qualifying_lower_oi_zone,
)

ZONE = ZoneInfo("Asia/Bangkok")
SESSION = date(2026, 7, 13)
POLICY = Path("config/xau_tiered_first_touch_manual_signal_v1.json")


def test_policy_hash_and_guardrails_are_frozen() -> None:
    policy = load_policy(POLICY)

    assert policy["policy_hash"] == (
        "717eea13732f6094f8c9d9c1aa6e57b33623dc74c34a0000e302a115f9bc4a65"
    )
    assert policy["tier_matrix"][0]["initial_state"] == "SHADOW_ONLY"
    assert policy["guardrails"] == {
        "position_sizing_allowed": False,
        "averaging_allowed": False,
        "recovery_allowed": False,
        "martingale_allowed": False,
        "automatic_execution_allowed": False,
        "signal_allowed": False,
        "order_submission_allowed": False,
        "research_only": True,
    }


def test_literal_one_and_half_sd_is_midpoint() -> None:
    assert extended_tier_levels(_plan())[1.5] == (85, 115)


def test_aggregated_tier_events_are_first_touch_only() -> None:
    bars = [
        _bar(8, 0, 100, 101, 89, 90),
        _bar(8, 1, 90, 91, 84, 85),
        _bar(8, 2, 85, 86, 79, 80),
        _bar(8, 3, 80, 81, 69, 70),
    ]

    events = build_tier_events(
        _plan(),
        bars,
        counting_mode=CountingMode.AGGREGATED,
    )

    assert [item.tier for item in events] == [1.0, 1.5, 2.0, 3.0]
    assert len({item.tier for item in events}) == 4
    assert events[0].repeated_touch_count == 3


def test_oi_wall_is_mapped_from_futures_to_xau() -> None:
    zone = qualifying_lower_oi_zone(
        _plan(),
        maximum_distance_points=12.5,
        minimum_percentile=0.8,
    )

    assert zone is not None
    assert zone.boundary == 80
    assert zone.mapped_wall == 81
    assert zone.wall_distance_points == 1
    assert zone.source_snapshot_at < _event().touch_timestamp


def test_rejection_uses_closed_confirmation_and_next_bar_open() -> None:
    plan = _plan()
    event = _event()
    zone = qualifying_lower_oi_zone(
        plan,
        maximum_distance_points=12.5,
        minimum_percentile=0.8,
    )
    bars = [
        _bar(8, 0, 81, 82, 79, 79.5),
        _bar(8, 1, 79.5, 82, 79, 80.5),
        _bar(8, 2, 82, 84, 81, 83),
    ]

    assert zone is not None
    r1 = executable_rejection_entry(zone, event, bars, rule="R1_BOUNDARY")
    r2 = executable_rejection_entry(zone, event, bars, rule="R2_WHOLE_ZONE")

    assert r1 is not None
    assert r1["confirmation_timestamp"] == bars[1].timestamp
    assert r1["entry_timestamp"] == bars[2].timestamp
    assert r1["entry_price"] == 82
    assert r2 is None


def test_known_next_bar_open_classifies_single_barrier_hit() -> None:
    event = FirstTouchEvent(
        **{
            **_event().__dict__,
            "boundary": 82,
            "touch_timestamp": datetime(2026, 7, 13, 8, 2, tzinfo=ZONE),
        }
    )
    outcome = evaluate_tier_barrier(
        event,
        [_bar(8, 2, 82, 95, 81, 94)],
        tp_points=12.5,
        sl_points=12.5,
        cost_points=1,
        known_entry_at_bar_open=True,
    )

    assert outcome.status == "tp_first"
    assert outcome.same_bar_ambiguous is False
    assert outcome.net_points == 11.5


def test_service_emits_reference_alert_without_broker_quote(tmp_path: Path) -> None:
    service = _service(tmp_path)
    bars = _rejection_bars()

    signal = service._signal_for_event(
        plan=_plan(),
        event=_event(),
        bars=bars,
        broker_quote=None,
        now=bars[-1].timestamp,
        active_candidate=False,
    )

    assert signal is not None
    assert signal.status == XauManualSignalState.REFERENCE_ALERT
    assert signal.entry is None
    assert signal.reference_entry == 82
    assert "BROKER_QUOTE_REQUIRED_FOR_EXACT_ENTRY" in signal.data_block_reasons


def test_valid_broker_quote_translates_manual_candidate(tmp_path: Path) -> None:
    service = _service(tmp_path)
    bars = _rejection_bars()
    quote = XauBrokerQuote(
        timestamp=bars[-1].timestamp + timedelta(seconds=20),
        symbol="XAUUSD.demo",
        bid=82.2,
        ask=82.4,
    )

    signal = service._signal_for_event(
        plan=_plan(),
        event=_event(),
        bars=bars,
        broker_quote=quote,
        now=bars[-1].timestamp + timedelta(seconds=30),
        active_candidate=False,
    )

    assert signal is not None
    assert signal.status == XauManualSignalState.MANUAL_CANDIDATE
    assert signal.entry == pytest.approx(82.3)
    assert signal.take_profit == pytest.approx(107.3)
    assert signal.stop_loss == pytest.approx(57.3)
    assert signal.order_submission_allowed is False


def test_stale_or_wide_quote_never_becomes_manual_candidate(tmp_path: Path) -> None:
    service = _service(tmp_path)
    bars = _rejection_bars()
    quote = XauBrokerQuote(
        timestamp=bars[-1].timestamp - timedelta(minutes=5),
        symbol="XAUUSD.demo",
        bid=80,
        ask=83,
    )

    signal = service._signal_for_event(
        plan=_plan(),
        event=_event(),
        bars=bars,
        broker_quote=quote,
        now=bars[-1].timestamp,
        active_candidate=False,
    )

    assert signal is not None
    assert signal.status == XauManualSignalState.REFERENCE_ALERT
    assert {"BROKER_QUOTE_STALE", "BROKER_SPREAD_TOO_WIDE"} <= set(
        signal.data_block_reasons
    )


def test_acknowledgement_does_not_close_active_candidate(tmp_path: Path) -> None:
    service = _service(tmp_path)
    signal = service._signal_for_event(
        plan=_plan(),
        event=_event(),
        bars=_rejection_bars(),
        broker_quote=XauBrokerQuote(
            timestamp=_rejection_bars()[-1].timestamp,
            symbol="XAUUSD.demo",
            bid=81.9,
            ask=82.1,
        ),
        now=_rejection_bars()[-1].timestamp,
        active_candidate=False,
    )
    assert signal is not None
    service.journal.append(
        "signals",
        signal.model_dump(mode="json"),
        id_field="signal_id",
    )

    service.acknowledge(
        signal.signal_id,
        XauManualSignalAcknowledgementRequest(acknowledged_by="researcher"),
    )

    assert service._has_active_manual_candidate() is True
    service.journal.append(
        "outcomes",
        {"outcome_id": "outcome-1", "signal_id": signal.signal_id, "status": "TP_HIT"},
        id_field="outcome_id",
    )
    assert service._has_active_manual_candidate() is False


def test_active_candidate_blocks_later_tier(tmp_path: Path) -> None:
    service = _service(tmp_path)

    signal = service._signal_for_event(
        plan=_plan(),
        event=_event(),
        bars=_rejection_bars(),
        broker_quote=None,
        now=_rejection_bars()[-1].timestamp,
        active_candidate=True,
    )

    assert signal is not None
    assert signal.status == XauManualSignalState.MISSED_DUE_TO_ACTIVE_POSITION


def test_journal_creates_all_streams_and_rejects_duplicate_ids(tmp_path: Path) -> None:
    journal = ManualSignalJournal(tmp_path, "policy")
    journal.append("plans", {"plan_id": "p1"}, id_field="plan_id")

    assert {item.stem for item in tmp_path.glob("*.jsonl")} == STREAMS
    with pytest.raises(ValueError, match="Duplicate immutable plan_id"):
        journal.append("plans", {"plan_id": "p1"}, id_field="plan_id")


def test_runner_writes_blocked_research_artifacts(tmp_path: Path) -> None:
    bars = tmp_path / "bars"
    bars.mkdir()
    run_dir = run_tiered_study(
        TieredStudyConfig(
            vol2vol_root=tmp_path / "vol2vol",
            price_bars_folder=bars,
            policy_path=POLICY,
            output_root=tmp_path / "reports",
            journal_root=tmp_path / "journal",
            session_date_from=SESSION,
            session_date_to=SESSION,
            as_of_date=SESSION,
        )
    )

    required = {
        "metadata.json",
        "eligibility.json",
        "plans.json",
        "events.json",
        "historical_matrix.json",
        "side_sensitivity.json",
        "executable_confluence.json",
        "plans_vs_events.json",
        "integrity_report.json",
        "promotion_gates.json",
        "current_plan.json",
        "review_handoff.md",
    }
    assert required <= {item.name for item in run_dir.iterdir()}
    metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["planned_session_count"] == 0
    assert metadata["research_only"] is True
    assert metadata["order_submission_allowed"] is False


def _service(tmp_path: Path) -> XauTieredManualSignalService:
    return XauTieredManualSignalService(
        journal_root=tmp_path / "journal",
        policy_path=POLICY,
        vol2vol_root=tmp_path / "vol2vol",
        price_bars_folder=tmp_path / "bars",
    )


def _plan() -> MappedPlan:
    snapshot = SourceSnapshot(
        snapshot_id="snapshot",
        session_date=SESSION,
        observed_at=datetime(2026, 7, 13, 7, 0, tzinfo=ZONE),
        series="G2",
        kind="intraday",
        source_dte=0.8,
        future_reference=200,
        atm_iv=15,
        iv_change=0,
        future_change=0,
        activity_total=100,
        ranges={1: (190, 210), 2: (180, 220), 3: (170, 230)},
        strike_rows=[
            {"strike": 181, "total": 100},
            {"strike": 190, "total": 10},
            {"strike": 220, "total": 5},
            {"strike": 230, "total": 1},
            {"strike": 240, "total": 0},
        ],
    )
    selection = SnapshotSelection(
        anchor=TimeAnchor.T0_DTE_080,
        snapshot=snapshot,
        activation_at=datetime(2026, 7, 13, 7, 1, tzinfo=ZONE),
        selection_reason="test",
        target_at=None,
        dte_error=0,
        strict_dte_eligible=True,
    )
    return MappedPlan(
        plan_id="plan",
        session_date=SESSION,
        anchor=TimeAnchor.T0_DTE_080,
        mapping_mode=MappingMode.DISTANCE_REANCHORED,
        selection=selection,
        planning_xau_timestamp=datetime(2026, 7, 13, 7, 0, tzinfo=ZONE),
        planning_xau_price=100,
        source_xau_timestamp=datetime(2026, 7, 13, 7, 0, tzinfo=ZONE),
        source_xau_price=100,
        source_gap_seconds=0,
        mapping_quality="distance_proxy_not_validated_basis",
        closed_bar_status="closed",
        basis_points=None,
        mapped_levels={1: (90, 110), 2: (80, 120), 3: (70, 130)},
        one_sd_points=10,
        oi_hard_feature_allowed=False,
    )


def _event() -> FirstTouchEvent:
    return FirstTouchEvent(
        event_id="event",
        plan_id="plan",
        session_date=SESSION,
        anchor=TimeAnchor.T0_DTE_080,
        mapping_mode=MappingMode.DISTANCE_REANCHORED,
        counting_mode=CountingMode.AGGREGATED,
        tier=2,
        side=EventSide.LOWER_LONG,
        boundary=80,
        touch_timestamp=datetime(2026, 7, 13, 8, 0, tzinfo=ZONE),
        touch_bar_index=0,
        source_series="G2",
        source_dte=0.8,
        selected_snapshot_at=datetime(2026, 7, 13, 7, 0, tzinfo=ZONE),
        repeated_touch_count=0,
        one_sd_points=10,
    )


def _rejection_bars() -> list[XauPriceBar]:
    return [
        _bar(8, 0, 81, 82, 79, 79.5),
        _bar(8, 1, 79.5, 82, 79, 80.5),
        _bar(8, 2, 82, 83, 81, 82),
    ]


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
