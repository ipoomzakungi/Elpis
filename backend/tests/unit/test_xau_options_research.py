from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

import polars as pl

from src.models.xau_market_context import XauPriceBar
from src.models.xau_options_research import XauOptionsCheckpoint, XauOptionsEvent
from src.models.xau_vol2vol_history_walkforward import (
    XauMappingMode,
    XauVol2VolRangeDeskSnapshot,
    XauVol2VolStrikeSnapshot,
)
from src.xau_options_research.event_builder import build_raw_events
from src.xau_options_research.event_deduplication import deduplicate_events
from src.xau_options_research.experiment_registry import load_experiment_registry
from src.xau_options_research.feature_panel import build_checkpoint_rows
from src.xau_options_research.labels import label_events
from src.xau_options_research.negative_controls import build_negative_controls
from src.xau_options_research.report_store import _write_parquet
from src.xau_options_research.strategy_simulator import run_preregistered_strategies
from src.xau_options_research.validation import build_validation_report, evidence_status
from src.xau_vol2vol_history_walkforward.oi_flow_audit import StrikeSnapshotIndex
from src.xau_vol2vol_history_walkforward.planning import XauPlanningSelection


def test_registry_contains_only_hashed_preregistered_experiments() -> None:
    registry = load_experiment_registry(
        Path("config/xau_options_research_experiments_v1.json")
    )

    assert [row["experiment_id"] for row in registry["experiments"]] == [
        "MR0",
        "MR1",
        "MR2",
        "MR3",
        "BO0",
        "BO1",
        "PIN0",
    ]
    assert all(len(row["experiment_hash"]) == 64 for row in registry["experiments"])


def test_checkpoint_uses_only_past_snapshots_and_keeps_oi_volume_separate() -> None:
    rows = build_checkpoint_rows(
        [_selection()],
        [_bar("06:59:00", 100), _bar("07:00:00", 101)],
        StrikeSnapshotIndex(_strike_rows()),
        timezone="Asia/Bangkok",
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["source_snapshot_at"] <= row["checkpoint_at"]
    assert row["oi_snapshot_at"] <= row["checkpoint_at"]
    assert row["volume_snapshot_at"] <= row["checkpoint_at"]
    assert row["oi_total"] == 100
    assert row["volume_total"] == 40
    assert row["oi_nearest_wall"] != row["volume_nearest_wall"]
    assert row["future_feature_violation"] is False
    assert row["monthly_oi_confluence"] is None


def test_mapped_strike_uses_same_time_basis_and_oi_change_same_strike() -> None:
    row = build_checkpoint_rows(
        [_selection()],
        [_bar("06:59:00", 100), _bar("07:00:00", 101)],
        StrikeSnapshotIndex(_strike_rows()),
        timezone="Asia/Bangkok",
    )[0]

    assert row["current_basis"] == 20
    assert row["oi_nearest_wall"] == 100
    assert row["oi_change"] == 20


def test_fixed_morning_iv_state_uses_only_prior_raw_snapshots() -> None:
    selection = _selection()
    earlier = selection.range_snapshot.model_copy(
        update={"observed_at": _time("06:30:00"), "vol_now": 20.2}
    )
    current = selection.range_snapshot.model_copy(update={"vol_now": 20.0})
    selection = replace(selection, range_snapshot=current)

    row = build_checkpoint_rows(
        [selection],
        [_bar("06:59:00", 100)],
        StrikeSnapshotIndex(_strike_rows()),
        timezone="Asia/Bangkok",
        range_snapshots=[earlier, current],
    )[0]

    assert row["iv_slope_30m"] < 0
    assert row["iv_state"] == "compressing"
    assert row["source_snapshot_at"] <= row["checkpoint_at"]


def test_event_builder_never_uses_checkpoint_after_event() -> None:
    checkpoint = _checkpoint_dict()
    events = build_raw_events(
        [checkpoint],
        [_bar("07:01:00", 90), _wide_bar("07:02:00", 89, 91, 88)],
        timezone="Asia/Bangkok",
    )

    assert events
    assert all(row["feature_timestamp"] <= row["event_timestamp"] for row in events)


def test_repeated_rolling_events_cluster_into_one_episode() -> None:
    first = _event_dict("07:05:00", "first")
    second = _event_dict("07:35:00", "second")

    annotated, episodes = deduplicate_events(
        [first, second],
        [_bar("07:10:00", 89), _bar("07:30:00", 89)],
    )

    assert len(annotated) == 2
    assert len(episodes) == 1
    assert annotated[0]["episode_id"] == annotated[1]["episode_id"]


def test_event_labels_preserve_same_bar_competing_ambiguity() -> None:
    event = _event_dict("07:05:00", "first")
    event["entry_price"] = 90
    labels = label_events(
        [event],
        [_wide_bar("07:05:00", 90, 93, 84), _bar("07:06:00", 90)],
    )

    assert labels[0]["competing_outcome_first"] == "same_bar_ambiguous"


def test_cost_scenarios_do_not_multiply_unique_episode_count() -> None:
    event = _event_dict("07:05:00", "episode")
    event.update(
        {
            "iv_state": "stable",
            "oi_rank": 1,
            "oi_distance_sd": 0.1,
            "volume_change_percentile": 0.5,
        }
    )
    result = run_preregistered_strategies(
        [event],
        [_bar("07:05:00", 90), _bar("07:06:00", 93)],
    )

    mr0 = [row for row in result["summaries"] if row["experiment_id"] == "MR0"]
    assert mr0
    assert {row["unique_episode_count"] for row in mr0} == {1}
    assert result["cost_scenarios_multiply_sample"] is False


def test_negative_controls_are_deterministic() -> None:
    event = _event_dict("07:05:00", "episode")
    bars = [_bar("07:05:00", 90), _bar("07:06:00", 93)]

    first = build_negative_controls([event], bars, seed=99)
    second = build_negative_controls([event], bars, seed=99)

    assert first == second


def test_development_and_holdout_are_chronological_and_isolated() -> None:
    outcomes = []
    for day in range(1, 11):
        outcomes.append(
            {
                "experiment_id": "MR0",
                "planning_mode": "fixed_morning",
                "target_sd": 0.25,
                "spread_points": 1.0,
                "slippage_points_per_side": 0.0,
                "session_date": f"2026-06-{day:02d}",
                "episode_id": f"E{day}",
                "net_points": 1.0,
                "status": "target_hit",
                "same_bar_ambiguous": False,
            }
        )
    strategy = {"outcomes": outcomes, "summaries": []}

    validation, holdout, _ = build_validation_report(
        strategy, [f"2026-06-{day:02d}" for day in range(1, 11)]
    )

    assert validation["development_sessions"] == [
        f"2026-06-{day:02d}" for day in range(1, 8)
    ]
    assert holdout["holdout_sessions"] == [
        f"2026-06-{day:02d}" for day in range(8, 11)
    ]
    assert validation["threshold_selection_uses_holdout"] is False
    assert validation["resampling_unit"] == "session"


def test_evidence_gate_requires_statistical_support_not_only_sample_size() -> None:
    sample = {
        "unique_episodes": 100,
        "holdout_episodes": 20,
        "sessions_with_events": 15,
        "integrity_violations": 0,
    }

    assert evidence_status(**sample, statistical_support=False) == "insufficient_sample"
    assert evidence_status(**sample, statistical_support=True) == "provisional"


def test_parquet_writer_infers_mixed_null_boolean_column_across_all_rows(
    tmp_path: Path,
) -> None:
    path = tmp_path / "mixed.parquet"
    rows = [{"monthly_oi_confluence": None} for _ in range(100)]
    rows.append({"monthly_oi_confluence": False})

    _write_parquet(path, rows)

    result = pl.read_parquet(path)
    assert result.height == 101
    assert result.schema["monthly_oi_confluence"] == pl.Boolean


def test_research_models_forbid_signal_outputs() -> None:
    checkpoint = XauOptionsCheckpoint(
        checkpoint_id="checkpoint",
        session_date=date(2026, 7, 1),
        planning_mode="fixed_morning",
        checkpoint_at=_time("07:00:00"),
        source_snapshot_at=_time("06:55:00"),
    )
    event = XauOptionsEvent(
        event_id="event",
        episode_id="episode",
        session_date=date(2026, 7, 1),
        planning_mode="fixed_morning",
        event_type="lower_1sd_touch",
        side="long_reversion",
        event_timestamp=_time("08:00:00"),
        checkpoint_id="checkpoint",
        entry_price=90,
        one_sd_points=10,
    )

    assert checkpoint.research_only and checkpoint.signal_allowed is False
    assert event.research_only and event.signal_allowed is False


def _selection() -> XauPlanningSelection:
    snapshot = XauVol2VolRangeDeskSnapshot(
        session_date=date(2026, 7, 1),
        observed_at=_time("06:55:00"),
        series="SERIES",
        dte=0.8,
        future_open=120,
        cfd_open=100,
        diff=20,
        vol_now=20,
        future_buy_1sd=110,
        future_buy_2sd=100,
        future_buy_3sd=90,
        future_sell_1sd=130,
        future_sell_2sd=140,
        future_sell_3sd=150,
    )
    return XauPlanningSelection(
        session_date=date(2026, 7, 1),
        source_session_date=date(2026, 7, 1),
        cycle_label="fixed_morning_0700",
        planning_at=_time("07:00:00"),
        simulation_window_start=_time("07:01:00"),
        simulation_window_end=_time("23:59:00"),
        range_snapshot=snapshot,
        mapping_mode=XauMappingMode.SAME_TIME_BASIS,
        source_alignment_seconds=0,
        snapshot_age_at_planning_seconds=300,
    )


def _strike_rows() -> list[XauVol2VolStrikeSnapshot]:
    rows = []
    for observed, oi_total, volume_total in (
        ("06:30:00", 80, 30),
        ("06:55:00", 100, 40),
    ):
        rows.extend(
            [
                XauVol2VolStrikeSnapshot(
                    session_date=date(2026, 7, 1),
                    observed_at=_time(observed),
                    series="SERIES",
                    snapshot_kind="open_interest",
                    strike=120,
                    call=oi_total,
                    put=0,
                    total=oi_total,
                    total_change=oi_total - 80,
                    source="fixture",
                ),
                XauVol2VolStrikeSnapshot(
                    session_date=date(2026, 7, 1),
                    observed_at=_time(observed),
                    series="SERIES",
                    snapshot_kind="intraday_volume",
                    strike=130,
                    call=volume_total,
                    put=0,
                    total=volume_total,
                    total_change=volume_total - 30,
                    source="fixture",
                ),
            ]
        )
    return rows


def _checkpoint_dict() -> dict:
    return {
        "checkpoint_id": "2026-07-01:fixed:0700",
        "session_date": "2026-07-01",
        "source_session_date": "2026-07-01",
        "planning_mode": "fixed_morning",
        "checkpoint_at": _time("07:00:00").isoformat(),
        "source_snapshot_at": _time("06:55:00").isoformat(),
        "current_xauusd": 100,
        "mapped_center": 100,
        "one_sd_points": 10,
        "price_z_from_current_snapshot": 0,
        "lower_1sd": 90,
        "lower_1_5sd": 85,
        "lower_2sd": 80,
        "upper_1sd": 110,
        "upper_1_5sd": 115,
        "upper_2sd": 120,
        "oi_nearest_wall": 90,
        "oi_distance_sd": 1,
        "oi_low_activity_gap_above": False,
        "oi_low_activity_gap_below": False,
        "future_feature_violation": False,
        "research_only": True,
        "signal_allowed": False,
    }


def _event_dict(hhmmss: str, suffix: str) -> dict:
    return {
        **_checkpoint_dict(),
        "event_id": f"event-{suffix}",
        "episode_id": f"episode-{suffix}",
        "event_type": "lower_1sd_touch",
        "side": "long_reversion",
        "event_timestamp": _time(hhmmss).isoformat(),
        "entry_price": 90,
        "feature_timestamp": _time("07:00:00").isoformat(),
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


def _wide_bar(hhmmss: str, close: float, high: float, low: float) -> XauPriceBar:
    return XauPriceBar(
        timestamp=_time(hhmmss),
        open=close,
        high=high,
        low=low,
        close=close,
        volume=1,
    )


def _time(hhmmss: str) -> datetime:
    return datetime.fromisoformat(f"2026-07-01T{hhmmss}+07:00")
