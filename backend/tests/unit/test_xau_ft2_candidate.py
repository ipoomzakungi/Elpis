from __future__ import annotations

import json
from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from src.models.xau_ft2_candidate import (
    XauFt2AcknowledgementRequest,
    XauFt2BrokerQuote,
    XauFt2State,
)
from src.models.xau_market_context import XauPriceBar
from src.xau_first_touch_study.models import (
    CountingMode,
    EventSide,
    FirstTouchEvent,
    MappingMode,
    TimeAnchor,
)
from src.xau_ft2_candidate.coverage_audit import (
    DTE_FIELD_MISSING,
    SERIES_SELECTION_FAILURE,
    XAU_PRICE_UNAVAILABLE,
    CoverageAuditConfig,
    run_coverage_audit,
)
from src.xau_ft2_candidate.external_importer import validate_external_study_file
from src.xau_ft2_candidate.journal import STREAMS, Ft2CandidateJournal
from src.xau_ft2_candidate.policy import candidate_hash, load_candidate_policy
from src.xau_ft2_candidate.runner import (
    Ft2CandidateRunConfig,
    _outcome_matrix,
    run_candidate_study,
)
from src.xau_ft2_candidate.service import XauFt2CandidateService

ZONE = ZoneInfo("Asia/Bangkok")
SESSION = date(2026, 7, 13)
POLICY = Path("config/xau_ft2_raw_candidate_v1.json")


def test_candidate_manifest_is_frozen_and_recovery_is_absent() -> None:
    policy = load_candidate_policy(POLICY)

    assert policy["candidate_id"] == "FT2_RAW_V1"
    assert policy["candidate_hash"] == (
        "14dd47390dee635d942db6d01a43fb96fc6a94c467a2bf068e60d53efdb4963f"
    )
    assert policy["canonical_plan"]["tier"] == 2.0
    assert policy["context"]["oi_gates_primary"] is False
    assert policy["context"]["rejection_gates_primary"] is False
    assert policy["guardrails"]["recovery_allowed"] is False
    assert policy["guardrails"]["martingale_allowed"] is False


def test_candidate_hash_changes_when_a_rule_changes() -> None:
    policy = load_candidate_policy(POLICY)
    changed = deepcopy(policy)
    changed["canonical_plan"]["take_profit_points"] = 26

    assert candidate_hash(changed) != policy["candidate_hash"]


def test_audit_distinguishes_missing_dte_from_incomplete_sd_rows(
    tmp_path: Path,
) -> None:
    vol = tmp_path / "vol"
    bars = tmp_path / "bars"
    bars.mkdir()
    _write_raw(
        vol,
        SESSION,
        [
            _snapshot(dte=None, ranges=_ranges()),
        ],
    )
    missing = run_coverage_audit(_audit_config(vol, bars))
    _write_raw(
        vol,
        SESSION,
        [
            _snapshot(dte=0.8, ranges=None),
        ],
    )
    incomplete = run_coverage_audit(_audit_config(vol, bars))

    assert missing["rows"][0]["classification"] == DTE_FIELD_MISSING
    assert incomplete["rows"][0]["classification"] == SERIES_SELECTION_FAILURE
    assert incomplete["rows"][0]["raw_dte_qualified_complete_range_count"] == 0
    assert incomplete["rows"][0]["recoverable"] is False


def test_complete_strict_row_is_parser_qualified_before_mapping(tmp_path: Path) -> None:
    vol = tmp_path / "vol"
    bars = tmp_path / "bars"
    bars.mkdir()
    _write_raw(vol, SESSION, [_snapshot(dte=0.8, ranges=_ranges())])

    report = run_coverage_audit(_audit_config(vol, bars))
    row = report["rows"][0]

    assert row["source_dte_qualified"] is True
    assert row["parser_dte_qualified"] is True
    assert row["classification"] == XAU_PRICE_UNAVAILABLE
    assert row["recoverable"] is True


def test_raw_first_touch_alert_does_not_require_oi_or_rejection(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    event = service._first_touch(_plan(), _bars())

    assert event is not None
    alert = service._create_alert(
        plan=_plan(),
        event=event,
        bars=_bars(),
        broker_quote=None,
        now=_bars()[-1].timestamp + timedelta(minutes=1),
    )

    assert alert.status == XauFt2State.REFERENCE_ALERT
    assert alert.mapped_xauusd_level == 80
    assert alert.reference_take_profit == 105
    assert alert.reference_stop_loss == 55
    assert alert.rejection_context["state"] == "not_required_for_primary"


def test_only_first_aggregated_2sd_touch_is_selected(tmp_path: Path) -> None:
    service = _service(tmp_path)

    event = service._first_touch(_plan(), _bars())

    assert event is not None
    assert event["side"] == "lower_long"
    assert event["touch_timestamp"] == _bars()[1].timestamp.isoformat()
    assert event["repeated_touch_allowed"] is False


def test_valid_quote_translates_entry_tp_and_sl_consistently(tmp_path: Path) -> None:
    service = _service(tmp_path)
    bars = _bars()
    event = service._first_touch(_plan(), bars)
    quote = XauFt2BrokerQuote(
        timestamp=bars[-2].timestamp + timedelta(seconds=20),
        symbol="XAUUSD.demo",
        bid=100.2,
        ask=100.4,
    )

    assert event is not None
    alert = service._create_alert(
        plan=_plan(),
        event=event,
        bars=bars,
        broker_quote=quote,
        now=quote.timestamp + timedelta(seconds=10),
    )

    assert alert.status == XauFt2State.PROVISIONAL_MANUAL_ALERT
    assert alert.broker_offset_points == pytest.approx(0.3)
    assert alert.broker_translated_level == pytest.approx(80.3)
    assert alert.take_profit == pytest.approx(105.3)
    assert alert.stop_loss == pytest.approx(55.3)
    assert alert.order_submission_allowed is False


def test_stale_touch_cannot_become_provisional_manual_alert(tmp_path: Path) -> None:
    service = _service(tmp_path)
    bars = _bars()
    event = service._first_touch(_plan(), bars)
    quote = XauFt2BrokerQuote(
        timestamp=bars[-1].timestamp + timedelta(minutes=5),
        symbol="XAUUSD.demo",
        bid=100.2,
        ask=100.4,
    )

    assert event is not None
    alert = service._create_alert(
        plan=_plan(),
        event=event,
        bars=bars,
        broker_quote=quote,
        now=quote.timestamp,
    )

    assert alert.status == XauFt2State.REFERENCE_ALERT
    assert "FIRST_TOUCH_ALERT_STALE" in alert.data_block_reasons
    assert "BROKER_QUOTE_NOT_SYNCHRONIZED_TO_TOUCH" in alert.data_block_reasons


def test_one_active_candidate_locks_later_alert(tmp_path: Path) -> None:
    service = _service(tmp_path)
    bars = _bars()
    event = service._first_touch(_plan(), bars)
    quote = XauFt2BrokerQuote(
        timestamp=bars[-1].timestamp,
        symbol="XAUUSD.demo",
        bid=99.9,
        ask=100.1,
    )
    assert event is not None
    active = service._create_alert(
        plan=_plan(),
        event=event,
        bars=bars,
        broker_quote=quote,
        now=quote.timestamp,
    )
    service.journal.append(
        "alerts",
        active.model_dump(mode="json"),
        id_field="alert_id",
    )
    later_plan = {**_plan(), "session_date": "2026-07-14"}
    later_event = {**event, "session_date": "2026-07-14"}

    locked = service._create_alert(
        plan=later_plan,
        event=later_event,
        bars=bars,
        broker_quote=quote,
        now=quote.timestamp,
    )

    assert locked.status == XauFt2State.TIER_LOCKED


def test_acknowledgement_does_not_close_active_candidate(tmp_path: Path) -> None:
    service = _service(tmp_path)
    alert = _provisional_alert(service)
    service.journal.append(
        "alerts",
        alert.model_dump(mode="json"),
        id_field="alert_id",
    )

    service.acknowledge(
        alert.alert_id,
        XauFt2AcknowledgementRequest(acknowledged_by="researcher"),
    )

    assert service._active_provisional_alert() is not None


def test_journal_is_append_only_and_supports_superseding_records(
    tmp_path: Path,
) -> None:
    journal = Ft2CandidateJournal(tmp_path, "hash")
    journal.append("plans", {"plan_id": "p1"}, id_field="plan_id")
    journal.append(
        "plans",
        {"plan_id": "p2", "supersedes_id": "p1"},
        id_field="plan_id",
    )

    assert {item.stem for item in tmp_path.glob("*.jsonl")} == STREAMS
    with pytest.raises(ValueError, match="Duplicate immutable plan_id"):
        journal.append("plans", {"plan_id": "p1"}, id_field="plan_id")


def test_unchanged_blocked_plan_is_not_appended_twice(tmp_path: Path) -> None:
    service = _service(tmp_path)
    now = datetime(2026, 7, 13, 23, 0, tzinfo=ZONE)

    service.process_session(session_date=SESSION, now=now)
    service.process_session(session_date=SESSION, now=now)

    assert len(service.journal.read("plans")) == 1
    assert service.journal.read("plans")[0]["status"] == "DATA_BLOCKED"


def test_challengers_cannot_create_manual_alerts() -> None:
    policy = load_candidate_policy(POLICY)

    assert policy["challengers"]["FT2_SMALL_V1"]["manual_alert_allowed"] is False
    assert (
        policy["challengers"]["FT2_REJECTION_V1"]["manual_alert_allowed"] is False
    )


def test_forty_plans_cannot_pass_frozen_promotion_gate() -> None:
    policy = load_candidate_policy(POLICY)

    assert 40 >= policy["promotion_gates"]["minimum_local_first_touch_events"]
    assert policy["promotion_gates"]["maximum_drawdown_points"] is None
    assert policy["promotion_gates"]["external_prior_bypass_allowed"] is False


def test_cost_scenarios_do_not_multiply_event_count() -> None:
    event = FirstTouchEvent(
        event_id="event",
        plan_id="plan",
        session_date=SESSION,
        anchor=TimeAnchor.T0_DTE_080,
        mapping_mode=MappingMode.DISTANCE_REANCHORED,
        counting_mode=CountingMode.AGGREGATED,
        tier=2,
        side=EventSide.LOWER_LONG,
        boundary=80,
        touch_timestamp=_bars()[1].timestamp,
        touch_bar_index=1,
        source_series="G2",
        source_dte=0.8,
        selected_snapshot_at=datetime(2026, 7, 13, 7, 0, tzinfo=ZONE),
        repeated_touch_count=1,
        one_sd_points=10,
    )

    matrix = _outcome_matrix(
        [event],
        {SESSION: _bars()},
        costs=[0.3, 1.0, 2.5],
        tp_points=25,
        sl_points=25,
    )

    assert [item["event_count"] for item in matrix["rows"]] == [1, 1, 1]
    assert matrix["event_count_is_not_multiplied_by_costs"] is True


def test_external_importer_keeps_observations_separate(tmp_path: Path) -> None:
    path = tmp_path / "external.json"
    path.write_text(
        json.dumps(
            [
                {
                    "session_date": "2026-01-01",
                    "selected_series": "G1",
                    "dte": 0.8,
                    "futures_reference": 4000,
                    "lower_2sd": 3950,
                    "upper_2sd": 4050,
                    "touch_time": "2026-01-01T10:00:00Z",
                    "mapping_mode": "distance_reanchored",
                    "mapping_reference": 3980,
                    "barrier_ordering": "TP_FIRST",
                }
            ]
        ),
        encoding="utf-8",
    )

    report = validate_external_study_file(path)

    assert report["valid_row_count"] == 1
    assert report["rows"][0]["eligible_for_elpis_local_pool"] is False
    assert report["fabricated_observations_allowed"] is False


def test_blocked_runner_writes_required_research_artifacts(tmp_path: Path) -> None:
    bars = tmp_path / "bars"
    bars.mkdir()
    run_dir = run_candidate_study(
        Ft2CandidateRunConfig(
            vol2vol_root=tmp_path / "vol",
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
        "strict_dte_coverage_audit.json",
        "strict_dte_coverage_audit.md",
        "frozen_plans.json",
        "ft2_raw_events.json",
        "ft2_raw_outcomes.json",
        "ft2_small_shadow_outcomes.json",
        "sample_report.json",
        "sample_report.md",
        "promotion_gates.json",
        "integrity_report.json",
        "current_plan.json",
        "review_handoff.md",
    }
    assert required <= {item.name for item in run_dir.iterdir()}
    sample = json.loads((run_dir / "sample_report.json").read_text(encoding="utf-8"))
    assert sample["promotion"]["all_standard_gates_passed"] is False
    assert sample["order_submission_allowed"] is False


def _audit_config(vol: Path, bars: Path) -> CoverageAuditConfig:
    return CoverageAuditConfig(
        vol2vol_root=vol,
        price_bars_folder=bars,
        session_date_from=SESSION,
        session_date_to=SESSION,
        as_of_date=SESSION + timedelta(days=1),
    )


def _service(tmp_path: Path) -> XauFt2CandidateService:
    return XauFt2CandidateService(
        journal_root=tmp_path / "journal",
        policy_path=POLICY,
        vol2vol_root=tmp_path / "vol",
        price_bars_folder=tmp_path / "bars",
    )


def _provisional_alert(service: XauFt2CandidateService):
    bars = _bars()
    event = service._first_touch(_plan(), bars)
    quote = XauFt2BrokerQuote(
        timestamp=bars[-1].timestamp,
        symbol="XAUUSD.demo",
        bid=99.9,
        ask=100.1,
    )
    assert event is not None
    return service._create_alert(
        plan=_plan(),
        event=event,
        bars=bars,
        broker_quote=quote,
        now=quote.timestamp,
    )


def _plan() -> dict:
    return {
        "plan_id": "FT2_RAW_V1_2026-07-13",
        "candidate_id": "FT2_RAW_V1",
        "session_date": SESSION.isoformat(),
        "status": "PLAN_READY",
        "selected_series": "G2",
        "source_dte": 0.8,
        "selected_snapshot_timestamp": datetime(
            2026, 7, 13, 7, 0, tzinfo=ZONE
        ).isoformat(),
        "activation_timestamp": datetime(
            2026, 7, 13, 7, 1, tzinfo=ZONE
        ).isoformat(),
        "original_futures_reference": 200,
        "raw_futures_lower_2sd": 180,
        "raw_futures_upper_2sd": 220,
        "mapped_xauusd_lower_2sd": 80,
        "mapped_xauusd_upper_2sd": 120,
        "xau_reference_timestamp": datetime(
            2026, 7, 13, 7, 0, tzinfo=ZONE
        ).isoformat(),
        "xau_reference_price": 100,
        "source_gap_seconds": 0,
        "mapping_mode": "distance_reanchored",
        "mapping_quality": "distance_proxy_not_validated_basis",
        "levels_frozen": True,
        "context": {},
    }


def _bars() -> list[XauPriceBar]:
    return [
        _bar(8, 0, 100, 101, 99, 100),
        _bar(8, 1, 100, 101, 79, 80),
        _bar(8, 2, 80, 100.1, 78, 100),
        _bar(8, 3, 100, 101, 77, 99),
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


def _write_raw(
    root: Path,
    session_date: date,
    snapshots: list[dict],
) -> None:
    folder = root / "daily" / session_date.isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "raw.json").write_text(
        json.dumps(
            {
                "sessionDate": session_date.isoformat(),
                "snapshots": snapshots,
            }
        ),
        encoding="utf-8",
    )


def _snapshot(*, dte, ranges) -> dict:
    return {
        "id": "snapshot",
        "sessionDate": SESSION.isoformat(),
        "observedAt": "2026-07-13T07:00:00+07:00",
        "series": "G2",
        "kind": "intraday",
        "dte": dte,
        "currentPrice": 200,
        "ranges": ranges,
        "rows": [],
    }


def _ranges() -> list[dict]:
    return [
        {"sd": 1, "down": 10, "up": 10},
        {"sd": 2, "down": 20, "up": 20},
        {"sd": 3, "down": 30, "up": 30},
    ]
