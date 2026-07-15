from __future__ import annotations

import json
from datetime import datetime

import pytest

from src.models.xau_market_context import XauPriceBar
from src.xau_vol2vol_history_walkforward.matched_validation import (
    AppendOnlyJournal,
    build_episode_maps,
    build_execution_cost_stress,
    build_feature_quality_audit,
    build_matched_comparisons,
    build_robustness_report,
    protocol_hash,
)


def test_multiple_rolling_plans_share_episode_until_reset() -> None:
    result = build_episode_maps(
        [_result_set()],
        [_feature()],
        [],
        {"F0": []},
        reset_sd=0.5,
    )

    assert result["plan_version_count"] == 2
    assert result["unique_opportunity_count"] == 2
    assert result["matched_anchor_opportunity_count"] == 1
    assert result["unique_episode_count"] == 1


def test_inside_return_creates_new_episode() -> None:
    result = build_episode_maps(
        [_result_set()],
        [_feature()],
        [_bar("08:15:00", 95)],
        {"F0": []},
        reset_sd=0.5,
    )

    assert result["unique_episode_count"] == 2
    assert result["episodes"][0]["reset_reason"] == "returned_0.5sd_inside"


def test_matched_comparisons_pair_same_opportunity_and_strategy() -> None:
    f0 = _outcome("opp-1", "A", 2)
    f1 = {**f0}
    f2 = {**f0, "net_points": 3, "entry_price": 91}
    f3 = {**f2}
    variants = {"F0": [f0], "F1": [f1], "F2": [f2], "F3": [f3], "BR": [f0]}
    episodes = {
        "episodes": [{"episode_id": "E1", "opportunity_ids": ["opp-1"]}]
    }

    result = build_matched_comparisons([_feature()], variants, episodes, [])

    assert result["F1"]["retained"]["unique_opportunity_count"] == 1
    assert result["F2"]["pairs"][0]["net_points_difference"] == 1
    assert result["F3"]["pairs"][0]["net_points_difference"] == 0
    assert result["strategy_summaries"][0]["strategy_id"] == "A"


def test_cost_scenarios_do_not_multiply_episode_count() -> None:
    result = build_execution_cost_stress(
        {"F0": [_outcome("opp-1", "A", 2)]},
        {"unique_episode_count": 1},
    )

    assert len(result["scenarios"]) == 12
    assert {row["unique_episode_count"] for row in result["scenarios"]} == {1}
    assert result["cost_scenarios_multiply_sample"] is False


def test_all_zero_snapshot_cannot_produce_top_rank() -> None:
    feature = _feature()
    for state_name in ("plan_state", "touch_state"):
        feature[state_name]["oi"].update(
            {
                "all_zero_snapshot": True,
                "insufficient_active_strikes": True,
                "top_5": False,
                "top_10": False,
                "rank": None,
                "active_strike_count": 0,
                "maximum_value_tie_count": 10,
                "derived_change": 0,
                "source_provided_change": 0,
                "change_discrepancy": 0,
                "total": 0,
            }
        )

    result = build_feature_quality_audit([feature])

    assert result["all_zero_oi_snapshot_count"] == 2
    assert result["hard_violation_count"] == 0


def test_session_robustness_is_deterministic() -> None:
    matched = {
        "F2": {
            "pairs": [
                _pair("2026-07-01", 1),
                _pair("2026-07-01", 2),
                _pair("2026-07-02", -1),
            ]
        }
    }
    variants = {"F0": [_outcome("opp-1", "A", 2)]}

    first = build_robustness_report([_feature()], matched, variants, seed=7, bootstrap_samples=50)
    second = build_robustness_report([_feature()], matched, variants, seed=7, bootstrap_samples=50)

    assert first["session_clustered_bootstrap"] == second["session_clustered_bootstrap"]
    assert first["session_clustered_bootstrap"]["unit"] == "independent_session"
    assert len(first["leave_one_session_out"]) == 2


def test_protocol_hash_changes_when_rules_change() -> None:
    payload = {"protocol_version": "v1", "rules": {"reset_sd": 0.5}}
    changed = {"protocol_version": "v1", "rules": {"reset_sd": 1.0}}

    assert protocol_hash(payload) != protocol_hash(changed)


def test_journal_rejects_rewrite_but_allows_superseding_append(tmp_path) -> None:
    journal = AppendOnlyJournal(tmp_path, "v1", "abc")
    journal.append("plans", {"record_id": "p1", "finalized": True})

    with pytest.raises(ValueError, match="append-only"):
        journal.append("plans", {"record_id": "p1", "finalized": True})

    journal.append(
        "plans",
        {
            "record_id": "p1-correction",
            "finalized": True,
            "supersedes_record_id": "p1",
        },
    )
    rows = [json.loads(line) for line in (tmp_path / "plans.jsonl").read_text().splitlines()]
    assert len(rows) == 2
    assert all(row["research_only"] for row in rows)
    assert all(row["signal_allowed"] is False for row in rows)


def test_latest_successful_workflow_excludes_dry_runs_and_blocked_attempts(
    tmp_path,
) -> None:
    journal = AppendOnlyJournal(tmp_path, "v1", "abc")
    common = {
        "session_date": "2026-07-13",
        "planning_mode": "fixed_morning",
        "stage": "prepare",
        "finalized": True,
    }
    journal.append(
        "daily_summary",
        {
            **common,
            "record_id": "dry",
            "workflow_attempt_id": "dry-attempt",
            "observation_mode": "dry_run",
            "dry_run": True,
            "operational_state": "PLAN_READY",
        },
    )
    journal.append(
        "daily_summary",
        {
            **common,
            "record_id": "blocked",
            "workflow_attempt_id": "blocked-attempt",
            "observation_mode": "retrospective_replay",
            "operational_state": "DATA_BLOCKED",
        },
    )
    journal.append(
        "daily_summary",
        {
            **common,
            "record_id": "success",
            "workflow_attempt_id": "successful-attempt",
            "observation_mode": "retrospective_replay",
            "operational_state": "PLAN_READY",
        },
    )
    journal.append(
        "outcomes",
        {
            "record_id": "dry-outcome",
            "finalized": True,
            "session_date": "2026-07-13",
            "planning_mode": "fixed_morning",
            "workflow_attempt_id": "dry-attempt",
            "observation_mode": "dry_run",
        },
    )
    journal.append(
        "outcomes",
        {
            "record_id": "retrospective-outcome",
            "finalized": True,
            "session_date": "2026-07-13",
            "planning_mode": "fixed_morning",
            "workflow_attempt_id": "successful-attempt",
            "observation_mode": "retrospective_replay",
        },
    )

    prepare = journal.latest_successful_prepare(
        session_date="2026-07-13",
        planning_mode="fixed_morning",
    )
    rows = journal.latest_successful_workflow_rows(
        "outcomes",
        session_date="2026-07-13",
        planning_mode="fixed_morning",
    )
    diagnostics = [
        json.loads(line)
        for line in (tmp_path / "daily_summary.jsonl").read_text().splitlines()
    ]

    assert prepare is not None
    assert prepare["workflow_attempt_id"] == "successful-attempt"
    assert [row["record_id"] for row in rows] == ["retrospective-outcome"]
    assert not any(row["observation_mode"] == "true_forward" for row in rows)
    assert any(row["operational_state"] == "DATA_BLOCKED" for row in diagnostics)


def _result_set() -> dict:
    return {
        "planning_mode": "rolling_30m",
        "mapping_mode": "same_time_basis",
        "opportunities": [
            _plan_version("08:00:00", "08:05:00", "opp-plan-1"),
            _plan_version("08:30:00", "08:35:00", "opp-plan-2"),
        ],
    }


def _plan_version(plan_time: str, touch_time: str, opportunity_id: str) -> dict:
    return {
        "opportunity_id": opportunity_id,
        "session_date": "2026-07-07",
        "planning_at": _time(plan_time).isoformat(),
        "first_touch_time": _time(touch_time).isoformat(),
        "planning_mode": "rolling_30m",
        "mapping_mode": "same_time_basis",
        "side": "long_reversion",
        "entry_definition": "zone_2_entry",
        "entry_level": 90,
        "touched": True,
    }


def _feature() -> dict:
    state_feature = {
        "all_zero_snapshot": False,
        "insufficient_active_strikes": False,
        "top_5": True,
        "top_10": True,
        "rank": 1,
        "active_strike_count": 10,
        "maximum_value_tie_count": 1,
        "derived_change": 1,
        "source_provided_change": 1,
        "change_discrepancy": 0,
        "total": 100,
        "selected_series": "SERIES",
        "distance_to_entry_sd": 0.1,
    }
    return {
        "opportunity_id": "opp-1",
        "session_date": "2026-07-07",
        "planning_mode": "rolling_30m",
        "mapping_mode": "same_time_basis",
        "side": "long_reversion",
        "entry_definition": "zone_2_entry",
        "entry_level": 90,
        "xau_reference": 100,
        "one_sd_points": 10,
        "plan_oi_snapshot_time": _time("07:55:00").isoformat(),
        "touch_oi_snapshot_time": _time("08:04:00").isoformat(),
        "plan_volume_snapshot_time": _time("07:55:00").isoformat(),
        "touch_volume_snapshot_time": _time("08:04:00").isoformat(),
        "plan_state": {"oi": {**state_feature}, "volume": {**state_feature}},
        "touch_state": {"oi": {**state_feature}, "volume": {**state_feature}},
    }


def _outcome(opportunity_id: str, strategy: str, net: float) -> dict:
    return {
        "opportunity_id": opportunity_id,
        "strategy_id": strategy,
        "session_date": "2026-07-07",
        "planning_mode": "rolling_30m",
        "side": "long_reversion",
        "entry_definition": "zone_2_entry",
        "entry_level": 90,
        "triggered_at": _time("08:05:00").isoformat(),
        "exited_at": _time("08:15:00").isoformat(),
        "status": "target_hit",
        "net_points": net,
        "mfe_points": 5,
        "mae_points": -1,
    }


def _pair(session_date: str, difference: float) -> dict:
    return {
        "session_date": session_date,
        "net_points_difference": difference,
        "baseline_net_points": 1,
        "comparison_net_points": 1 + difference,
        "mae_difference": 0,
    }


def _bar(hhmmss: str, close: float) -> XauPriceBar:
    return XauPriceBar(
        timestamp=_time(hhmmss),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1,
    )


def _time(hhmmss: str) -> datetime:
    return datetime.fromisoformat(f"2026-07-07T{hhmmss}+07:00")
