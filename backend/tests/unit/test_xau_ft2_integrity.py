from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from src.models.xau_ft2_candidate import (
    XauFt2AcknowledgementRequest,
    XauFt2OrderType,
)
from src.models.xau_market_context import XauPriceBar
from src.xau_first_touch_study.models import (
    MappingMode,
    SnapshotSelection,
    SourceSnapshot,
    TimeAnchor,
)
from src.xau_first_touch_study.selection import latest_closed_bar, map_selection
from src.xau_ft2_candidate.executable_fill import (
    ExecutableEvent,
    evaluate_executable_fill,
)
from src.xau_ft2_candidate.integrity_policy import (
    load_integrity_policy,
    synchronized_reference_accepted,
)
from src.xau_ft2_candidate.policy import load_candidate_policy
from src.xau_ft2_candidate.service import XauFt2CandidateService

ZONE = ZoneInfo("Asia/Bangkok")
CANDIDATE_POLICY = Path("config/xau_ft2_raw_candidate_v1.json")
INTEGRITY_POLICY = Path("config/xau_ft2_integrity_v1.json")


def test_source_session_and_bangkok_trading_date_remain_distinct() -> None:
    selection = _selection()

    assert selection.snapshot.session_date == date(2026, 7, 5)
    assert selection.activation_at.astimezone(ZONE).date() == date(2026, 7, 6)


def test_2212_utc_snapshot_activates_0512_bangkok_next_day() -> None:
    selection = _selection()

    assert selection.snapshot.observed_at.hour == 22
    assert selection.activation_at.astimezone(ZONE).hour == 5
    assert selection.activation_at.astimezone(ZONE).minute == 12


def test_july_5_source_can_select_july_6_closed_xau_bar() -> None:
    selection = _selection()
    bars = [_bar(2026, 7, 6, 5, 11, 100, 101, 99, 100)]

    plan = map_selection(
        selection,
        bars,
        mapping_mode=MappingMode.DISTANCE_REANCHORED,
        maximum_gap_seconds=120,
    )

    assert plan is not None
    assert plan.session_date == date(2026, 7, 5)
    assert plan.planning_xau_timestamp.astimezone(ZONE).date() == date(2026, 7, 6)
    assert plan.source_gap_seconds == pytest.approx(30)


def test_five_hour_reference_is_rejected() -> None:
    stale = SimpleNamespace(
        closed_bar_status="closed",
        source_gap_seconds=18_748,
    )

    assert not synchronized_reference_accepted(
        stale,
        maximum_gap_seconds=120,
    )


def test_stale_plan_cannot_enter_denominator() -> None:
    plans = [
        SimpleNamespace(closed_bar_status="closed", source_gap_seconds=30),
        SimpleNamespace(closed_bar_status="closed", source_gap_seconds=18_748),
    ]

    accepted = [
        plan for plan in plans if synchronized_reference_accepted(plan, maximum_gap_seconds=120)
    ]

    assert len(accepted) == 1


def test_latest_bar_must_be_fully_closed() -> None:
    at = datetime(2026, 7, 6, 5, 12, 30, tzinfo=ZONE)
    closed = _bar(2026, 7, 6, 5, 11, 100, 101, 99, 100)
    open_bar = _bar(2026, 7, 6, 5, 12, 100, 101, 99, 100)

    assert latest_closed_bar([closed, open_bar], at) == closed


def test_long_limit_fill_requires_ask() -> None:
    event = _event("lower_long")
    reference_touch_only = [_bar(2026, 7, 6, 6, 0, 100, 100.2, 99.8, 100)]

    result = evaluate_executable_fill(
        event,
        reference_touch_only,
        spread_points=0.5,
        tp_points=25,
        sl_points=25,
    )

    assert result["reference_boundary_touched"] is True
    assert result["status"] == "not_filled_due_to_spread"


def test_short_limit_fill_uses_bid_and_cover_uses_ask() -> None:
    event = _event("upper_short")
    bars = [
        _bar(2026, 7, 6, 6, 0, 99, 100, 98, 99),
        _bar(2026, 7, 6, 6, 1, 90, 91, 74, 80),
    ]

    result = evaluate_executable_fill(
        event,
        bars,
        spread_points=1,
        tp_points=25,
        sl_points=25,
    )

    assert result["executable_entry_filled"] is True
    assert result["entry_price_side"] == "bid"
    assert result["exit_price_side"] == "ask"
    assert result["status"] == "tp_first"


def test_cost_subtraction_cannot_create_an_executable_fill() -> None:
    result = evaluate_executable_fill(
        _event("lower_long"),
        [_bar(2026, 7, 6, 6, 0, 100, 100.2, 99.8, 100)],
        spread_points=2.5,
        tp_points=25,
        sl_points=25,
    )

    assert result["status"] == "not_filled_due_to_spread"
    assert "cost_points" not in result


def test_manual_acknowledgement_separates_reference_and_actual_fill(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    service.journal.append(
        "alerts",
        {
            "alert_id": "alert-1",
            "broker_symbol": "XAUUSD.demo",
            "mapped_xauusd_level": 100,
        },
        id_field="alert_id",
    )

    row = service.acknowledge(
        "alert-1",
        XauFt2AcknowledgementRequest(
            acknowledged_by="researcher",
            broker_symbol="XAUUSD.demo",
            actual_fill_timestamp=datetime(2026, 7, 6, 6, 1, tzinfo=ZONE),
            actual_fill_price=101.2,
            bid=101.1,
            ask=101.3,
            order_type=XauFt2OrderType.MARKET_AFTER_ALERT,
        ),
    )

    assert row["reference_entry_price"] == 100
    assert row["actual_fill_price"] == 101.2
    assert row["spread"] == pytest.approx(0.2)


def test_observation_only_acknowledgement_cannot_claim_a_fill() -> None:
    with pytest.raises(ValidationError, match="observation-only"):
        XauFt2AcknowledgementRequest(
            acknowledged_by="researcher",
            actual_fill_timestamp=datetime.now(UTC),
            actual_fill_price=100,
        )


def test_reference_alert_without_actual_fill_has_no_manual_outcome(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    service.journal.append(
        "alerts",
        {
            "alert_id": "alert-1",
            "session_date": "2026-07-05",
            "side": "BUY",
            "mapped_xauusd_level": 100,
            "touch_timestamp": datetime(2026, 7, 6, 6, 0, tzinfo=ZONE).isoformat(),
        },
        id_field="alert_id",
    )

    service._resolve_open_alerts(
        [_bar(2026, 7, 6, 6, 1, 100, 130, 70, 100)],
        datetime(2026, 7, 7, tzinfo=ZONE),
    )

    assert service.journal.read("outcomes") == []


def test_manual_outcome_uses_actual_fill_barriers(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.journal.append(
        "alerts",
        {
            "alert_id": "alert-1",
            "session_date": "2026-07-05",
            "side": "BUY",
            "broker_symbol": "XAUUSD.demo",
            "mapped_xauusd_level": 90,
            "touch_timestamp": datetime(2026, 7, 6, 6, 0, tzinfo=ZONE).isoformat(),
        },
        id_field="alert_id",
    )
    fill_at = datetime(2026, 7, 6, 6, 1, tzinfo=ZONE)
    service.acknowledge(
        "alert-1",
        XauFt2AcknowledgementRequest(
            acknowledged_by="researcher",
            actual_fill_timestamp=fill_at,
            actual_fill_price=100,
            bid=99.9,
            ask=100.1,
            order_type=XauFt2OrderType.PENDING_LIMIT,
        ),
    )

    service._resolve_open_alerts(
        [
            _bar(2026, 7, 6, 6, 1, 100, 101, 99, 100),
            _bar(2026, 7, 6, 6, 2, 110, 126, 109, 125),
        ],
        datetime(2026, 7, 6, 6, 3, tzinfo=ZONE),
    )

    outcome = service.journal.read("outcomes")[0]
    assert outcome["status"] == "TP_HIT"
    assert outcome["reference_entry_price"] == 90
    assert outcome["actual_fill_price"] == 100
    assert outcome["take_profit_from_actual_fill"] == 125


def test_candidate_hash_and_research_guardrails_remain_frozen() -> None:
    candidate = load_candidate_policy(CANDIDATE_POLICY)
    engine = load_integrity_policy(
        INTEGRITY_POLICY,
        candidate_policy_path=CANDIDATE_POLICY,
    )

    assert candidate["candidate_hash"] == (
        "14dd47390dee635d942db6d01a43fb96fc6a94c467a2bf068e60d53efdb4963f"
    )
    assert engine["candidate_hash"] == candidate["candidate_hash"]
    assert engine["guardrails"] == {
        "position_sizing_allowed": False,
        "averaging_allowed": False,
        "recovery_allowed": False,
        "martingale_allowed": False,
        "automatic_execution_allowed": False,
        "signal_allowed": False,
        "order_submission_allowed": False,
        "research_only": True,
    }


def test_integrity_outputs_are_research_only_and_non_executable() -> None:
    engine = json.loads(INTEGRITY_POLICY.read_text(encoding="utf-8"))

    assert engine["guardrails"]["research_only"] is True
    assert engine["guardrails"]["signal_allowed"] is False
    assert engine["guardrails"]["order_submission_allowed"] is False


def _selection() -> SnapshotSelection:
    observed = datetime(2026, 7, 5, 22, 12, 30, tzinfo=UTC)
    snapshot = SourceSnapshot(
        snapshot_id="july-5",
        session_date=date(2026, 7, 5),
        observed_at=observed,
        series="G1MN6",
        kind="open_interest",
        source_dte=0.8,
        future_reference=200,
        atm_iv=None,
        iv_change=None,
        future_change=None,
        activity_total=100,
        ranges={1: (190, 210), 2: (180, 220), 3: (170, 230)},
    )
    return SnapshotSelection(
        anchor=TimeAnchor.T0_DTE_080,
        snapshot=snapshot,
        activation_at=observed.astimezone(ZONE),
        selection_reason="test",
        target_at=None,
        dte_error=0,
        strict_dte_eligible=True,
    )


def _event(side: str) -> ExecutableEvent:
    return ExecutableEvent(
        event_id=f"event-{side}",
        side=side,
        entry=100,
        touch_timestamp=datetime(2026, 7, 6, 6, 0, tzinfo=ZONE),
    )


def _service(tmp_path: Path) -> XauFt2CandidateService:
    return XauFt2CandidateService(
        journal_root=tmp_path / "journal",
        policy_path=CANDIDATE_POLICY,
        integrity_policy_path=INTEGRITY_POLICY,
        vol2vol_root=tmp_path / "vol",
        price_bars_folder=tmp_path / "bars",
    )


def _bar(
    year: int,
    month: int,
    day: int,
    hour: int,
    minute: int,
    open_price: float,
    high: float,
    low: float,
    close: float,
) -> XauPriceBar:
    return XauPriceBar(
        timestamp=datetime(year, month, day, hour, minute, tzinfo=ZONE),
        open=open_price,
        high=high,
        low=low,
        close=close,
    )
