from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from src.models.xau_market_context import XauPriceBar
from src.xau_options_research.ambiguity_resolver import resolve_ambiguous_outcome
from src.xau_options_research.candidate_validation_reporting import (
    build_validation_summary,
)
from src.xau_options_research.candidate_validation_runner import (
    load_frozen_manifest,
    run_frozen_candidates,
    validate_completed_session,
)
from src.xau_options_research.candidate_validation_store import (
    CandidateValidationStore,
    DuplicateValidationSessionError,
)

BACKEND = Path(__file__).resolve().parents[2]
MANIFEST = BACKEND / "config" / "xau_options_candidate_validation_v2.json"
FIXTURE = BACKEND / "tests" / "fixtures" / "xau_candidate_validation_post_cutoff.json"


def _fixture() -> tuple[dict, list[dict], list[XauPriceBar]]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return (
        load_frozen_manifest(MANIFEST),
        payload["episode_events"],
        [XauPriceBar.model_validate(row) for row in payload["bars"]],
    )


@pytest.mark.parametrize(
    ("requested", "returned", "status", "coverage", "reason"),
    [
        (date(2026, 7, 16), "2026-07-16", "complete", True, "PRE_CUTOFF_SESSION"),
        (date(2026, 7, 17), "2026-07-18", "complete", True, "RETURNED_DATE_MISMATCH"),
        (date(2026, 7, 17), "2026-07-17", "incomplete", True, "SESSION_INCOMPLETE"),
        (
            date(2026, 7, 17),
            "2026-07-17",
            "complete",
            False,
            "PRICE_COVERAGE_INCOMPLETE",
        ),
    ],
)
def test_session_gate_fails_closed(requested, returned, status, coverage, reason) -> None:
    manifest = load_frozen_manifest(MANIFEST)
    result = validate_completed_session(
        requested_date=requested,
        returned_date=returned,
        source_status=status,
        price_coverage_complete=coverage,
        manifest=manifest,
    )
    assert result.accepted is False
    assert result.reason == reason


def test_missing_source_is_not_mislabeled_as_date_mismatch() -> None:
    manifest = load_frozen_manifest(MANIFEST)
    result = validate_completed_session(
        requested_date=date(2026, 7, 17),
        returned_date="",
        source_status="missing",
        price_coverage_complete=False,
        manifest=manifest,
    )
    assert result.reason == "SESSION_INCOMPLETE"


def test_manifest_tampering_fails_closed(tmp_path: Path) -> None:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    payload["costs"]["spread_points"] = 0.5
    changed = tmp_path / "manifest.json"
    changed.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="manifest hash mismatch"):
        load_frozen_manifest(changed)


def test_only_frozen_c1_c2_create_outcomes() -> None:
    manifest, events, bars = _fixture()
    result = run_frozen_candidates(manifest=manifest, episode_events=events, bars=bars)
    assert {row["candidate_id"] for row in result["outcomes"]} == {"C1", "C2"}
    assert result["c3_descriptive_eligibility_count"] == 1
    assert result["c3_outcome_count"] == 0
    assert result["bo0_monitor_observation_count"] == 1
    assert result["bo0_candidate_outcome_count"] == 0
    assert all(row["candidate_hash"] for row in result["outcomes"])


def test_same_bar_stays_ambiguous_without_finer_data() -> None:
    manifest, events, bars = _fixture()
    outcome = next(
        row
        for row in run_frozen_candidates(
            manifest=manifest, episode_events=events, bars=bars
        )["outcomes"]
        if row["candidate_id"] == "C2"
    )
    outcome["outcome_id"] = f"C2:{outcome['episode_id']}"
    resolved, audit = resolve_ambiguous_outcome(
        outcome, tick_rows=None, resolution_source=None
    )
    assert resolved["resolved_status"] == "same_bar_ambiguous"
    assert resolved["net_points"] is None
    assert audit["favorable_sequence_assumed"] is False


def test_tick_resolution_uses_observed_sequence(tmp_path: Path) -> None:
    manifest, events, bars = _fixture()
    outcome = next(
        row
        for row in run_frozen_candidates(
            manifest=manifest, episode_events=events, bars=bars
        )["outcomes"]
        if row["candidate_id"] == "C2"
    )
    source = tmp_path / "ticks.json"
    source.write_text("[]", encoding="utf-8")
    ticks = [
        {"timestamp": "2026-07-17T09:00:01+07:00", "bid": 100.0},
        {"timestamp": "2026-07-17T09:00:02+07:00", "bid": 102.5},
    ]
    resolved, audit = resolve_ambiguous_outcome(
        outcome, tick_rows=ticks, resolution_source=source
    )
    assert resolved["resolved_status"] == "target_hit"
    assert resolved["original_m1_status"] == "same_bar_ambiguous"
    assert audit["favorable_sequence_assumed"] is False
    assert audit["resolution_confidence"] == 1.0


def test_append_store_rejects_duplicate_session_and_preserves_guardrails(
    tmp_path: Path,
) -> None:
    store = CandidateValidationStore(tmp_path, "manifest")
    bundle = {
        "session": {"session_date": "2026-07-17"},
        "opportunities": [],
        "outcomes": [],
        "resolutions": [],
        "daily_summary": {"session_date": "2026-07-17"},
    }
    store.append_session_bundle(**bundle)
    with pytest.raises(DuplicateValidationSessionError):
        store.append_session_bundle(**bundle)
    for stream in ("sessions", "daily_summaries"):
        row = store.read(stream)[0]
        assert row["research_only"] is True
        assert row["signal_allowed"] is False
        assert row["order_submission_allowed"] is False


def test_correction_appends_a_new_superseding_record(tmp_path: Path) -> None:
    store = CandidateValidationStore(tmp_path, "manifest")
    store.append("outcomes", {"outcome_id": "C1:E1", "resolved_status": "ambiguous"})
    store.append_superseding(
        "outcomes",
        {"outcome_id": "C1:E1:R1", "resolved_status": "target_hit"},
        id_field="outcome_id",
        supersedes_id="C1:E1",
    )
    rows = store.read("outcomes")
    assert len(rows) == 2
    assert rows[0]["resolved_status"] == "ambiguous"
    assert rows[1]["supersedes_id"] == "C1:E1"


def test_validation_summary_keeps_calibration_out_and_subgroups_descriptive() -> None:
    rows = [
        {
            "candidate_id": "C1",
            "episode_id": "v2:E1",
            "session_date": "2026-07-17",
            "resolved_status": "target_hit",
            "net_points": 4.0,
            "gross_points": 5.0,
            "entry_timestamp": "2026-07-17T08:00:00+07:00",
            "entry_zone": "1.5SD",
            "side": "long_reversion",
        }
    ]
    summary = build_validation_summary(
        rows,
        calibration=[{"candidate_id": "C1", "net_expectancy_points": 1.46}],
    )
    c1 = summary["candidates"][0]
    assert summary["calibration_rows_in_validation"] == 0
    assert summary["subgroups_are_descriptive_only"] is True
    assert c1["validation_minus_calibration_points"] == pytest.approx(2.54)
    assert c1["evidence_status"] == "insufficient_sample"
    assert summary["research_only"] is True
    assert summary["signal_allowed"] is False
    assert summary["order_submission_allowed"] is False


def test_completed_session_counts_even_without_opportunities() -> None:
    summary = build_validation_summary([], accepted_session_dates=["2026-07-17"])
    assert summary["validation_session_count"] == 1
    assert summary["real_accepted_session_count"] == 1
    assert summary["synthetic_fixture_session_count"] == 0
    assert summary["rejected_session_count"] == 0
    assert all(row["validation_session_count"] == 1 for row in summary["candidates"])
    assert all(row["sessions_with_opportunities"] == 0 for row in summary["candidates"])


def test_synthetic_fixture_never_counts_as_validation_session() -> None:
    summary = build_validation_summary(
        [],
        accepted_session_dates=[],
        synthetic_fixture_session_count=1,
    )
    assert summary["validation_session_count"] == 0
    assert summary["real_accepted_session_count"] == 0
    assert summary["synthetic_fixture_session_count"] == 1
    assert all(row["validation_session_count"] == 0 for row in summary["candidates"])
