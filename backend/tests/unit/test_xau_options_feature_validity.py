from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from src.models.xau_vol2vol_history_walkforward import (
    XauVol2VolStrikeSnapshot,
)
from src.xau_options_research.candidate_validation import (
    build_validation_v2_status,
    candidate_hash,
    load_candidate_registry,
)
from src.xau_options_research.clustered_inference import (
    build_clustered_inference_audit,
    consistency_status,
)
from src.xau_options_research.event_independence import enforce_non_overlapping_positions
from src.xau_options_research.feature_validity import (
    actual_value_updates,
    build_feature_semantics_audit,
    derive_interval_volume,
)
from src.xau_options_research.matched_controls import build_matched_negative_control_report


def test_all_zero_source_oi_change_is_non_informative() -> None:
    audit = build_feature_semantics_audit(
        [_checkpoint("2026-07-01", "07:00:00", oi_change=0)],
        [],
        [_strike("2026-07-01", "07:00:00", "open_interest", 100, 0)],
    )

    assert audit["oi_change_status"] == "non_informative"
    assert audit["feature_summaries"]["source_oi_change"]["non_zero_count"] == 0


def test_repeated_oi_snapshots_do_not_create_false_change() -> None:
    rows = [
        _strike("2026-07-01", "07:00:00", "open_interest", 100, 0),
        _strike("2026-07-01", "07:30:00", "open_interest", 100, 0),
    ]
    audit = build_feature_semantics_audit([], [], rows)

    assert audit["feature_summaries"]["derived_oi_change"]["non_zero_count"] == 0
    assert audit["feature_summaries"]["derived_oi_change"]["information_status"] == (
        "non_informative"
    )


def test_cumulative_volume_becomes_non_negative_interval_volume() -> None:
    assert derive_interval_volume(125, 100, same_session_and_series=True) == 25


def test_session_or_series_reset_does_not_create_negative_interval_volume() -> None:
    assert derive_interval_volume(10, 100, same_session_and_series=True) is None
    assert derive_interval_volume(10, 100, same_session_and_series=False) is None


def test_repeated_iv_values_are_not_fake_updates() -> None:
    updates = actual_value_updates(
        [
            (_time("07:00:00"), 20.0),
            (_time("07:05:00"), 20.0),
            (_time("07:10:00"), 20.1),
        ]
    )

    assert updates == [(_time("07:00:00"), 20.0), (_time("07:10:00"), 20.1)]


def test_concurrent_rolling_outcomes_cannot_open_multiple_positions() -> None:
    first = _outcome("E1", "07:00:00", "08:00:00")
    second = _outcome("E2", "07:30:00", "08:30:00")

    kept, blocked = enforce_non_overlapping_positions(
        [first, second], {"E1": _event("SERIES"), "E2": _event("SERIES")}
    )

    assert [row["episode_id"] for row in kept] == ["E1"]
    assert blocked == 1


def test_exit_reset_allows_new_independent_opportunity() -> None:
    first = _outcome("E1", "07:00:00", "07:20:00")
    second = _outcome("E2", "07:30:00", "08:00:00")

    kept, blocked = enforce_non_overlapping_positions(
        [first, second], {"E1": _event("SERIES"), "E2": _event("SERIES")}
    )

    assert len(kept) == 2
    assert blocked == 0


def test_cost_scenarios_do_not_change_non_overlapping_episode_identity() -> None:
    first = _outcome("E1", "07:00:00", "07:20:00")
    cost_copy = {**first, "spread_points": 1.5}

    kept, _ = enforce_non_overlapping_positions([first, cost_copy], {"E1": _event("SERIES")})

    assert len({row["episode_id"] for row in kept}) == 1


def test_clustered_inference_uses_sessions_not_episode_count() -> None:
    rows = [
        _outcome(f"E{index}", "07:00:00", "07:20:00", session="2026-07-01") for index in range(20)
    ] + [_outcome("E21", "07:00:00", "07:20:00", session="2026-07-02")]
    audit = build_clustered_inference_audit(rows, iterations=50)

    assert audit["trials"][0]["independent_session_count"] == 2
    assert audit["trials"][0]["resampling_unit"] == "session"


def test_tiny_episode_p_value_cannot_override_clustered_ci() -> None:
    assert consistency_status(0.001, [-2.0, 3.0]) == "failed"


def test_mr2_controls_keep_matched_opportunity_counts() -> None:
    events = []
    outcomes = []
    for index in range(4):
        episode = f"E{index}"
        events.append(
            {
                "episode_id": episode,
                "session_date": f"2026-07-0{index + 1}",
                "side": "long_reversion",
                "entry_price": 100,
                "one_sd_points": 10,
                "oi_rank": 1 if index < 2 else 10,
                "oi_distance_sd": 0.1 if index < 2 else 0.5,
                "oi_nearest_wall": 101,
                "oi_wall_persistence": index == 0,
                "iv_state": "stable",
            }
        )
        outcomes.append(
            _outcome(
                episode,
                "07:00:00",
                "07:20:00",
                session=f"2026-07-0{index + 1}",
            )
        )
    report = build_matched_negative_control_report(outcomes, events, permutations=20)

    assert all(row["matched_counts_equal"] for row in report["oi_matched_controls"])


def test_candidate_hash_changes_when_rule_changes() -> None:
    candidate = {"candidate_id": "C1", "target_sd": 0.5}
    changed = {**candidate, "target_sd": 0.25}

    assert candidate_hash(candidate) != candidate_hash(changed)


def test_candidate_registry_hashes_are_valid() -> None:
    registry = load_candidate_registry(Path("config/xau_options_candidate_validation_v2.json"))

    assert len(registry["candidates"]) == 4
    assert all(len(row["candidate_hash"]) == 64 for row in registry["candidates"])


def test_pre_cutoff_sessions_cannot_enter_validation_v2() -> None:
    manifest = {
        "data_cutoff": "2026-07-16",
        "validation_start_date": "2026-07-17",
        "review_schedule_sessions": [10, 20, 30],
    }
    rows = [
        {"session_date": "2026-07-16"},
        {"session_date": "2026-07-17"},
    ]

    status = build_validation_v2_status(rows, manifest)

    assert status["validation_v2_sessions"] == ["2026-07-17"]
    assert status["pre_cutoff_row_count"] == 0
    assert status["research_only"] and status["signal_allowed"] is False


def _checkpoint(session: str, hhmmss: str, *, oi_change: float) -> dict:
    return {
        "session_date": session,
        "checkpoint_at": f"{session}T{hhmmss}+07:00",
        "atm_iv": 20.0,
        "atm_iv_change_previous": 0.0,
        "iv_slope_30m": 0.0,
        "iv_slope_60m": 0.0,
        "oi_total": 100.0,
        "oi_change": oi_change,
        "volume_total": 20.0,
        "volume_change": 0.0,
        "basis_drift": 0.0,
        "monthly_oi_confluence": None,
    }


def _strike(
    session: str,
    hhmmss: str,
    kind: str,
    total: float,
    total_change: float,
) -> XauVol2VolStrikeSnapshot:
    return XauVol2VolStrikeSnapshot(
        session_date=date.fromisoformat(session),
        observed_at=datetime.fromisoformat(f"{session}T{hhmmss}+07:00"),
        series="SERIES",
        snapshot_kind=kind,
        strike=100,
        total=total,
        total_change=total_change,
        source="fixture",
    )


def _event(series: str) -> dict:
    return {"selected_series": series}


def _outcome(
    episode: str,
    entry: str,
    exit_at: str,
    *,
    session: str = "2026-07-01",
) -> dict:
    return {
        "episode_id": episode,
        "event_id": episode,
        "session_date": session,
        "planning_mode": "rolling_30m",
        "side": "long_reversion",
        "event_type": "lower_1sd_touch",
        "entry_timestamp": f"{session}T{entry}+07:00",
        "exit_timestamp": f"{session}T{exit_at}+07:00",
        "experiment_id": "MR0",
        "target_sd": 0.5,
        "spread_points": 1.0,
        "slippage_points_per_side": 0.0,
        "net_points": 1.0,
        "status": "target_hit",
        "same_bar_ambiguous": False,
    }


def _time(hhmmss: str) -> datetime:
    return datetime.fromisoformat(f"2026-07-01T{hhmmss}+07:00")
