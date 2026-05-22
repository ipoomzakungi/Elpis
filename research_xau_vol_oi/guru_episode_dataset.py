"""Guru decision episode dataset builder.

The episode dataset reconstructs what was visible when a transcript rule became
available, keeps the guru statement separate from market data, and evaluates
future outcomes only after the availability timestamp. It is research-only and
does not create trading signals.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import polars as pl

from research_xau_vol_oi.config import ResearchConfig


OUTCOME_WINDOWS = ("1h", "4h", "session_close", "next_session", "3_sessions", "5_sessions")
PRIMARY_PERFORMANCE_WINDOW = "4h"
REVIEW_DECISIONS = {"APPROVE", "REJECT", "NEEDS_MORE_CONTEXT", "POST_EVENT_ONLY", "DUPLICATE"}
FINAL_DECISIONS = (
    "GURU_EPISODE_REVIEW_REQUIRED",
    "GURU_EPISODE_CONTEXT_ONLY",
    "GURU_EPISODE_FILTER_CANDIDATE",
    "GURU_EPISODE_VALIDATED_FILTER",
)
THESIS_TYPES = (
    "REJECT_LEVEL",
    "BREAK_LEVEL",
    "RANGE_ROTATION",
    "PIN_OR_MAGNET",
    "SQUEEZE_CONTINUATION",
    "NO_TRADE",
    "WATCH_ONLY",
    "CONTEXT_ONLY",
    "POST_EVENT_COMMENTARY",
    "UNTESTABLE",
)
EXPECTED_DIRECTIONS = ("LONG", "SHORT", "RANGE", "NO_TRADE", "NONE")


@dataclass(frozen=True)
class GuruEpisodeDatasetResult:
    """Episode layer outputs and conservative validation status."""

    episodes: pl.DataFrame
    outcomes: pl.DataFrame
    performance: pl.DataFrame
    review_sample: pl.DataFrame
    final_decision: str
    approved_only_can_run: bool
    no_trade_rows_retained: int


def run_guru_episode_dataset_layer(
    *,
    review_queue: pl.DataFrame,
    feature_table: pl.DataFrame,
    signal_events: pl.DataFrame,
    trades: pl.DataFrame,
    output_dir: Path,
    charts_dir: Path,
    config: ResearchConfig | None = None,
    approved_only: bool = False,
) -> GuruEpisodeDatasetResult:
    """Build guru decision episodes, future outcomes, summaries, reports, and charts."""

    cfg = config or ResearchConfig()
    output_dir.mkdir(parents=True, exist_ok=True)
    charts_dir.mkdir(parents=True, exist_ok=True)
    episodes = build_guru_decision_episodes(
        review_queue=review_queue,
        feature_table=feature_table,
        signal_events=signal_events,
        config=cfg,
        approved_only=approved_only,
    )
    outcomes = build_guru_episode_outcomes(episodes, feature_table, config=cfg)
    performance = summarize_guru_episode_performance(episodes, outcomes)
    review_sample = build_guru_episode_review_sample(episodes)
    approved_only_can_run = episodes.filter(pl.col("reviewer_decision") == "APPROVE").height > 0
    final_decision = guru_episode_final_decision(
        episodes=episodes,
        performance=performance,
        approved_only_can_run=approved_only_can_run,
    )
    no_trade_rows_retained = _no_trade_count(signal_events)

    episodes.write_csv(output_dir / "guru_decision_episodes.csv")
    outcomes.write_csv(output_dir / "guru_episode_outcomes.csv")
    performance.write_csv(output_dir / "guru_episode_rule_performance.csv")
    review_sample.write_csv(output_dir / "guru_episode_review_sample.csv")
    write_guru_episode_report(
        output_dir / "guru_episode_report.md",
        episodes=episodes,
        outcomes=outcomes,
        performance=performance,
        review_sample=review_sample,
        final_decision=final_decision,
        approved_only_can_run=approved_only_can_run,
        no_trade_rows_retained=no_trade_rows_retained,
    )
    write_guru_episode_charts(charts_dir=charts_dir, performance=performance)
    return GuruEpisodeDatasetResult(
        episodes=episodes,
        outcomes=outcomes,
        performance=performance,
        review_sample=review_sample,
        final_decision=final_decision,
        approved_only_can_run=approved_only_can_run,
        no_trade_rows_retained=no_trade_rows_retained,
    )


def build_guru_decision_episodes(
    *,
    review_queue: pl.DataFrame,
    feature_table: pl.DataFrame,
    signal_events: pl.DataFrame,
    config: ResearchConfig | None = None,
    approved_only: bool = False,
) -> pl.DataFrame:
    """Create one episode per reviewed or high-priority transcript rule row."""

    cfg = config or ResearchConfig()
    if review_queue.is_empty():
        return _empty_episodes()
    rows = []
    feature_rows = _feature_rows(feature_table)
    no_trade_signal_count = _no_trade_count(signal_events)
    for review in _selected_review_rows(review_queue, approved_only=approved_only):
        availability = _to_datetime(review.get("availability_timestamp"))
        snapshot = _market_snapshot(feature_rows, availability)
        thesis = extract_guru_thesis(review, snapshot)
        reviewed_status = _reviewed_status(review)
        session_usable = _same_session_predictive_allowed(availability, cfg)
        preview_status = (
            "APPROVED"
            if reviewed_status == "APPROVE"
            else "PREVIEW_ONLY"
            if cfg.research_preview_mode
            else "PREVIEW_ONLY_BLOCKED"
        )
        episode_id = _episode_id(review, availability)
        rows.append(
            {
                "episode_id": episode_id,
                "transcript_id": review.get("transcript_id"),
                "transcript_date": review.get("transcript_date"),
                "availability_timestamp": availability,
                "source_excerpt": review.get("source_excerpt"),
                "normalized_english_summary": review.get("normalized_english_summary"),
                "reviewer_decision": reviewed_status,
                "reviewer_notes": review.get("reviewer_notes"),
                "rule_tag": review.get("rule_tag"),
                "rule_type": review.get("rule_type"),
                "quality_label": review.get("quality_label"),
                "action_bias": review.get("action_bias"),
                "condition_text": review.get("condition"),
                "invalidation_rule": thesis["invalidation_rule"],
                "target_text": thesis["target_text"],
                "mentioned_levels": thesis["mentioned_levels"],
                "mentioned_direction": thesis["mentioned_direction"],
                "mentioned_time_horizon": thesis["mentioned_time_horizon"],
                "required_market_data": review.get("required_market_data"),
                "data_available_timestamp": snapshot.get("data_available_timestamp"),
                "spot_price": snapshot.get("spot_price"),
                "session_open": snapshot.get("session_open"),
                "open_side": snapshot.get("open_side"),
                "distance_from_open": snapshot.get("distance_from_open"),
                "annualized_iv": snapshot.get("annualized_iv"),
                "realized_vol": snapshot.get("realized_vol"),
                "vrp": snapshot.get("vrp"),
                "one_sd_level_upper": snapshot.get("one_sd_level_upper"),
                "one_sd_level_lower": snapshot.get("one_sd_level_lower"),
                "two_sd_level_upper": snapshot.get("two_sd_level_upper"),
                "two_sd_level_lower": snapshot.get("two_sd_level_lower"),
                "sigma_position": snapshot.get("sigma_position"),
                "nearest_wall_above": snapshot.get("nearest_wall_above"),
                "nearest_wall_below": snapshot.get("nearest_wall_below"),
                "nearest_wall_above_score": snapshot.get("nearest_wall_above_score"),
                "nearest_wall_below_score": snapshot.get("nearest_wall_below_score"),
                "basis": snapshot.get("basis"),
                "nearest_spot_equivalent_strike": snapshot.get("nearest_spot_equivalent_strike"),
                "intraday_volume_near_level": snapshot.get("intraday_volume_near_level"),
                "oi_change_near_level": snapshot.get("oi_change_near_level"),
                "data_quality_status": snapshot.get("data_quality_status"),
                "sigma_zone": snapshot.get("sigma_zone"),
                "wall_score_bucket": snapshot.get("wall_score_bucket"),
                "vol_regime": snapshot.get("vol_regime"),
                "wall_level": snapshot.get("wall_level"),
                "wall_score": snapshot.get("wall_score"),
                "thesis_type": thesis["thesis_type"],
                "expected_direction": thesis["expected_direction"],
                "expected_from_level": thesis["expected_from_level"],
                "expected_to_level": thesis["expected_to_level"],
                "invalidation_level": thesis["invalidation_level"],
                "confidence_score": _float_or_none(review.get("confidence_score")),
                "testability_score": _float_or_none(review.get("testability_score")),
                "leakage_risk_score": _float_or_none(review.get("leakage_risk_score")),
                "episode_review_status": preview_status,
                "predictive_claim_allowed": reviewed_status == "APPROVE" and session_usable,
                "same_session_predictive_allowed": session_usable,
                "published_after_session_close": not session_usable,
                "no_trade_signal_rows_retained": no_trade_signal_count,
                "research_only": True,
            }
        )
    return _rows_frame(rows) if rows else _empty_episodes()


def extract_guru_thesis(review: dict[str, Any], snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    """Extract deterministic, audit-friendly thesis fields from a review row."""

    text = " ".join(
        str(review.get(column) or "")
        for column in ("source_excerpt", "normalized_english_summary", "condition", "rule_tag", "action_bias")
    )
    levels = _parse_levels(review.get("extracted_numeric_levels") or text)
    timestamp_like_levels = _parse_levels(review.get("timestamp_like_numeric_levels") or "")
    if timestamp_like_levels:
        levels = [
            level
            for level in levels
            if not any(abs(level - timestamp_level) < 1e-9 for timestamp_level in timestamp_like_levels)
        ]
    thesis_type = _thesis_type(
        rule_tag=str(review.get("rule_tag") or ""),
        rule_type=str(review.get("rule_type") or ""),
        quality_label=str(review.get("quality_label") or ""),
        action_bias=str(review.get("action_bias") or ""),
        text=text,
    )
    mentioned_direction = _mentioned_direction(text)
    expected_direction = _expected_direction(thesis_type, str(review.get("action_bias") or ""), mentioned_direction)
    invalidation_level = _keyword_level(text, ("invalid", "invalidation", "stop", "above", "below"))
    target_level = _keyword_level(text, ("target", "toward", "to", "tp", "take profit"))
    expected_from = levels[0] if levels else _float_or_none((snapshot or {}).get("wall_level"))
    return {
        "thesis_type": thesis_type,
        "expected_direction": expected_direction,
        "expected_from_level": expected_from,
        "expected_to_level": target_level,
        "invalidation_level": invalidation_level,
        "invalidation_rule": _invalidation_text(text),
        "target_text": _target_text(text),
        "mentioned_levels": "|".join(_format_level(value) for value in levels),
        "mentioned_direction": mentioned_direction,
        "mentioned_time_horizon": _mentioned_time_horizon(text),
    }


def build_guru_episode_outcomes(
    episodes: pl.DataFrame,
    feature_table: pl.DataFrame,
    *,
    config: ResearchConfig | None = None,
) -> pl.DataFrame:
    """Evaluate future-only outcomes for each episode and window."""

    cfg = config or ResearchConfig()
    if episodes.is_empty():
        return _empty_outcomes()
    feature_rows = _feature_rows(feature_table)
    rows = []
    for episode in episodes.to_dicts():
        availability = _to_datetime(episode.get("availability_timestamp"))
        for window in OUTCOME_WINDOWS:
            outcome = _evaluate_window(episode, feature_rows, availability, window, cfg)
            rows.append(outcome)
    return _rows_frame(rows) if rows else _empty_outcomes()


def summarize_guru_episode_performance(episodes: pl.DataFrame, outcomes: pl.DataFrame) -> pl.DataFrame:
    """Summarize primary-window episode performance by requested research groups."""

    if episodes.is_empty() or outcomes.is_empty():
        return _empty_performance()
    primary = outcomes.filter(pl.col("outcome_window") == PRIMARY_PERFORMANCE_WINDOW)
    if primary.is_empty():
        primary = outcomes.group_by("episode_id").first()
    joined = episodes.join(primary, on="episode_id", how="left")
    group_columns = [
        "rule_tag",
        "thesis_type",
        "action_bias",
        "reviewed_status",
        "sigma_zone",
        "wall_score_bucket",
        "vol_regime",
    ]
    rows = []
    for item in joined.to_dicts():
        item["reviewed_status"] = "approved" if item.get("reviewer_decision") == "APPROVE" else "preview_or_unreviewed"
    enriched = _rows_frame(joined.to_dicts()).with_columns(
        pl.when(pl.col("reviewer_decision") == "APPROVE")
        .then(pl.lit("approved"))
        .otherwise(pl.lit("preview_or_unreviewed"))
        .alias("reviewed_status")
    )
    for key, group in _group_rows(enriched.to_dicts(), group_columns).items():
        rows.append(_performance_row(group_columns, key, group))
    return _rows_frame(rows) if rows else _empty_performance()


def build_guru_episode_review_sample(episodes: pl.DataFrame) -> pl.DataFrame:
    """Return HIGH-priority preview episodes for human review."""

    if episodes.is_empty():
        return _empty_episodes()
    if "episode_review_status" not in episodes.columns:
        return episodes.head(0)
    sample = episodes.filter(pl.col("episode_review_status") != "APPROVED")
    if "quality_label" in sample.columns:
        sample = sample.sort(["leakage_risk_score", "testability_score"], descending=[True, True])
    return sample.head(100)


def guru_episode_final_decision(
    *,
    episodes: pl.DataFrame,
    performance: pl.DataFrame,
    approved_only_can_run: bool,
) -> str:
    """Return conservative final decision for episode validation."""

    if episodes.is_empty() or not approved_only_can_run:
        return "GURU_EPISODE_REVIEW_REQUIRED"
    approved_count = episodes.filter(pl.col("reviewer_decision") == "APPROVE").height
    if approved_count < 20:
        return "GURU_EPISODE_CONTEXT_ONLY"
    if performance.is_empty():
        return "GURU_EPISODE_CONTEXT_ONLY"
    candidates = performance.filter(
        (pl.col("approved_count") >= 20)
        & (pl.col("target_hit_rate").fill_null(0.0) > pl.col("invalidation_hit_rate").fill_null(0.0))
        & (pl.col("direction_accuracy").fill_null(0.0) >= 0.55)
    )
    if candidates.is_empty():
        return "GURU_EPISODE_CONTEXT_ONLY"
    validated = candidates.filter(pl.col("walk_forward_pass") & pl.col("placebo_pass"))
    if validated.is_empty():
        return "GURU_EPISODE_FILTER_CANDIDATE"
    return "GURU_EPISODE_VALIDATED_FILTER"


def write_guru_episode_report(
    path: Path,
    *,
    episodes: pl.DataFrame,
    outcomes: pl.DataFrame,
    performance: pl.DataFrame,
    review_sample: pl.DataFrame,
    final_decision: str,
    approved_only_can_run: bool,
    no_trade_rows_retained: int,
) -> None:
    """Write Markdown report for the guru episode dataset."""

    snapshot_fields = [
        "spot_price",
        "session_open",
        "open_side",
        "distance_from_open",
        "annualized_iv",
        "realized_vol",
        "vrp",
        "one_sd_level_upper",
        "one_sd_level_lower",
        "two_sd_level_upper",
        "two_sd_level_lower",
        "sigma_position",
        "nearest_wall_above",
        "nearest_wall_below",
        "basis",
        "nearest_spot_equivalent_strike",
        "data_quality_status",
    ]
    lines = [
        "# Guru Decision Episode Dataset",
        "",
        "Research-only reconstruction of transcript rule episodes. No live trading or direct trade signals.",
        "",
        f"- Final decision: `{final_decision}`",
        f"- Episodes: {episodes.height}",
        f"- Outcome rows: {outcomes.height}",
        f"- Approved-only episode validation can run: {approved_only_can_run}",
        f"- No-trade signal rows retained: {no_trade_rows_retained}",
        "",
        "## What Data Guru Could See",
        "",
        "- Market snapshots use the latest feature row with `timestamp <= availability_timestamp`.",
        "- Outcome rows use only rows with `timestamp > availability_timestamp`.",
        "- Snapshot fields created: " + ", ".join(f"`{field}`" for field in snapshot_fields),
        "",
        "## Guru Thesis vs Market Outcome",
        "",
        _frame_markdown(_report_columns(episodes)),
        "",
        "## Target / Invalidation Accuracy",
        "",
        _frame_markdown(_report_columns(outcomes)),
        "",
        "## Approved vs Preview Episodes",
        "",
        _frame_markdown(_approval_counts(episodes)),
        "",
        "## Episode-Level Rule Performance",
        "",
        _frame_markdown(performance),
        "",
        "## Review Sample",
        "",
        _frame_markdown(_report_columns(review_sample)),
        "",
        "## Final Guru Logic Decision",
        "",
        "- `GURU_EPISODE_VALIDATED_FILTER` is blocked unless human-approved records exist, "
        "approved sample size is sufficient, walk-forward and placebo checks pass, "
        "target/invalidation logic is clear, future transcript leakage is zero, and no-trade rows are retained.",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_guru_episode_charts(*, charts_dir: Path, performance: pl.DataFrame) -> None:
    """Write SVG charts for episode summaries."""

    charts_dir.mkdir(parents=True, exist_ok=True)
    rows = performance.sort("episode_count", descending=True).head(20).to_dicts() if not performance.is_empty() else []
    _write_bar_svg(
        charts_dir / "guru_episode_outcome_by_rule.svg",
        title="Guru episode expectancy proxy by rule",
        labels=[str(row.get("rule_tag")) for row in rows],
        values=[_float_or_zero(row.get("expectancy_proxy")) for row in rows],
    )
    _write_bar_svg(
        charts_dir / "guru_episode_target_hit_rate.svg",
        title="Guru episode target hit rate",
        labels=[str(row.get("rule_tag")) for row in rows],
        values=[_float_or_zero(row.get("target_hit_rate")) for row in rows],
    )
    _write_grouped_bar_svg(
        charts_dir / "guru_episode_mfe_mae.svg",
        title="Guru episode average MFE and MAE",
        labels=[str(row.get("rule_tag")) for row in rows],
        positive=[_float_or_zero(row.get("average_MFE")) for row in rows],
        negative=[_float_or_zero(row.get("average_MAE")) for row in rows],
    )


def _selected_review_rows(review_queue: pl.DataFrame, *, approved_only: bool) -> list[dict[str, Any]]:
    rows = []
    seen: set[str] = set()
    for row in review_queue.to_dicts():
        decision = _reviewed_status(row)
        high_priority = str(row.get("suggested_review_priority") or "").upper() == "HIGH"
        reviewed = decision in REVIEW_DECISIONS
        if approved_only and decision != "APPROVE":
            continue
        if not approved_only and not (reviewed or high_priority):
            continue
        review_id = str(row.get("review_id") or "")
        if review_id in seen:
            continue
        seen.add(review_id)
        rows.append(row)
    return rows


def _market_snapshot(feature_rows: list[dict[str, Any]], availability: datetime | None) -> dict[str, Any]:
    if availability is None:
        return _empty_snapshot()
    visible = [row for row in feature_rows if _to_datetime(row.get("timestamp")) and _to_datetime(row.get("timestamp")) <= availability]
    if not visible:
        return _empty_snapshot()
    row = visible[-1]
    close = _float_or_none(row.get("close"))
    session_open = _float_or_none(row.get("session_open"))
    wall_level = _float_or_none(row.get("wall_level"))
    wall_score = _float_or_none(row.get("wall_score"))
    wall_side = str(row.get("wall_side") or "").lower()
    above_level = wall_level if wall_side == "resistance" or (close is not None and wall_level and wall_level >= close) else None
    below_level = wall_level if wall_side == "support" or (close is not None and wall_level and wall_level <= close) else None
    return {
        "data_available_timestamp": _to_datetime(row.get("timestamp")),
        "spot_price": close,
        "session_open": session_open,
        "open_side": _open_side(close, session_open),
        "distance_from_open": close - session_open if close is not None and session_open is not None else None,
        "annualized_iv": _float_or_none(row.get("annualized_iv_percent")),
        "realized_vol": _float_or_none(row.get("rv_percent")),
        "vrp": _float_or_none(row.get("vrp")),
        "one_sd_level_upper": _float_or_none(row.get("upper_1sd")),
        "one_sd_level_lower": _float_or_none(row.get("lower_1sd")),
        "two_sd_level_upper": _float_or_none(row.get("upper_2sd")),
        "two_sd_level_lower": _float_or_none(row.get("lower_2sd")),
        "sigma_position": _float_or_none(row.get("sigma_position")),
        "nearest_wall_above": above_level,
        "nearest_wall_below": below_level,
        "nearest_wall_above_score": wall_score if above_level is not None else None,
        "nearest_wall_below_score": wall_score if below_level is not None else None,
        "basis": _float_or_none(row.get("basis")),
        "nearest_spot_equivalent_strike": wall_level,
        "intraday_volume_near_level": _float_or_none(row.get("intraday_volume_near_level")),
        "oi_change_near_level": _float_or_none(row.get("oi_change_near_level")),
        "data_quality_status": row.get("data_quality_state"),
        "sigma_zone": row.get("sigma_zone"),
        "wall_score_bucket": row.get("wall_score_bucket"),
        "vol_regime": row.get("vol_regime"),
        "wall_level": wall_level,
        "wall_score": wall_score,
    }


def _evaluate_window(
    episode: dict[str, Any],
    feature_rows: list[dict[str, Any]],
    availability: datetime | None,
    window: str,
    config: ResearchConfig,
) -> dict[str, Any]:
    base = {
        "episode_id": episode.get("episode_id"),
        "transcript_id": episode.get("transcript_id"),
        "rule_tag": episode.get("rule_tag"),
        "thesis_type": episode.get("thesis_type"),
        "action_bias": episode.get("action_bias"),
        "expected_direction": episode.get("expected_direction"),
        "outcome_window": window,
        "availability_timestamp": availability,
        "window_start": availability,
        "window_end": None,
        "evaluation_data_start": None,
        "evaluation_data_end": None,
        "target_hit": None,
        "invalidation_hit": None,
        "direction_correct": None,
        "max_favorable_excursion": None,
        "max_adverse_excursion": None,
        "close_return": None,
        "signed_close_return": None,
        "realized_vol_after": None,
        "wall_rejected": None,
        "wall_accepted": None,
        "stayed_inside_1sd": None,
        "broke_1sd": None,
        "broke_2sd": None,
        "outcome_label": "UNTESTABLE",
        "evaluation_notes": "",
        "research_only": True,
    }
    if availability is None:
        return {**base, "evaluation_notes": "missing availability timestamp"}
    end = _window_end(availability, window, config)
    if end is None:
        return {
            **base,
            "outcome_label": "UNTESTABLE",
            "evaluation_notes": "availability is after same-session close; not a same-session pre-event thesis",
        }
    future = [
        row
        for row in feature_rows
        if (timestamp := _to_datetime(row.get("timestamp"))) is not None and availability < timestamp <= end
    ]
    if not future:
        return {**base, "window_end": end, "outcome_label": "NO_CLEAR_OUTCOME", "evaluation_notes": "no future rows in window"}
    spot = _float_or_none(episode.get("spot_price"))
    if spot is None:
        return {**base, "window_end": end, "outcome_label": "UNTESTABLE", "evaluation_notes": "missing snapshot spot price"}
    high = max(_float_or_none(row.get("high")) for row in future if _float_or_none(row.get("high")) is not None)
    low = min(_float_or_none(row.get("low")) for row in future if _float_or_none(row.get("low")) is not None)
    close = _float_or_none(future[-1].get("close"))
    direction = str(episode.get("expected_direction") or "NONE")
    mfe, mae = _mfe_mae(direction, spot, high, low)
    close_return = close - spot if close is not None else None
    signed_close_return = _signed_close_return(direction, close_return)
    target_hit = _level_hit(
        level=_float_or_none(episode.get("expected_to_level")),
        direction=direction,
        spot=spot,
        high=high,
        low=low,
    )
    invalidation_hit = _level_hit(
        level=_float_or_none(episode.get("invalidation_level")),
        direction=_opposite_direction(direction),
        spot=spot,
        high=high,
        low=low,
    )
    direction_correct = _direction_correct(direction, close_return, episode, future)
    upper_1sd = _float_or_none(episode.get("one_sd_level_upper"))
    lower_1sd = _float_or_none(episode.get("one_sd_level_lower"))
    upper_2sd = _float_or_none(episode.get("two_sd_level_upper"))
    lower_2sd = _float_or_none(episode.get("two_sd_level_lower"))
    wall_rejected, wall_accepted = _wall_reaction(episode, high, low, close)
    return {
        **base,
        "window_end": end,
        "evaluation_data_start": _to_datetime(future[0].get("timestamp")),
        "evaluation_data_end": _to_datetime(future[-1].get("timestamp")),
        "target_hit": target_hit,
        "invalidation_hit": invalidation_hit,
        "direction_correct": direction_correct,
        "max_favorable_excursion": mfe,
        "max_adverse_excursion": mae,
        "close_return": close_return,
        "signed_close_return": signed_close_return,
        "realized_vol_after": _realized_vol_after(future),
        "wall_rejected": wall_rejected,
        "wall_accepted": wall_accepted,
        "stayed_inside_1sd": _stayed_inside(high, low, upper_1sd, lower_1sd),
        "broke_1sd": _broke_band(high, low, upper_1sd, lower_1sd),
        "broke_2sd": _broke_band(high, low, upper_2sd, lower_2sd),
        "outcome_label": _outcome_label(episode, target_hit, invalidation_hit, direction_correct),
        "evaluation_notes": "future rows after availability only",
    }


def _performance_row(columns: list[str], key: tuple[Any, ...], rows: list[dict[str, Any]]) -> dict[str, Any]:
    target_values = [_bool_value(row.get("target_hit")) for row in rows if row.get("target_hit") is not None]
    invalid_values = [_bool_value(row.get("invalidation_hit")) for row in rows if row.get("invalidation_hit") is not None]
    direction_values = [_bool_value(row.get("direction_correct")) for row in rows if row.get("direction_correct") is not None]
    mfe_values = [_float_or_none(row.get("max_favorable_excursion")) for row in rows]
    mae_values = [_float_or_none(row.get("max_adverse_excursion")) for row in rows]
    expectancy_values = [_float_or_none(row.get("signed_close_return")) for row in rows]
    approved_count = sum(1 for row in rows if row.get("reviewer_decision") == "APPROVE")
    episode_count = len({row.get("episode_id") for row in rows})
    row = {column: key[index] for index, column in enumerate(columns)}
    target_hit_rate = _mean(target_values)
    invalidation_hit_rate = _mean(invalid_values)
    direction_accuracy = _mean(direction_values)
    expectancy = _mean([value for value in expectancy_values if value is not None])
    row.update(
        {
            "episode_count": episode_count,
            "approved_count": approved_count,
            "target_hit_rate": target_hit_rate,
            "invalidation_hit_rate": invalidation_hit_rate,
            "direction_accuracy": direction_accuracy,
            "average_MFE": _mean([value for value in mfe_values if value is not None]),
            "average_MAE": _mean([value for value in mae_values if value is not None]),
            "expectancy_proxy": expectancy,
            "sample_size_warning": episode_count < 20,
            "walk_forward_pass": False,
            "placebo_pass": False,
            "recommendation": _episode_recommendation(
                approved_count=approved_count,
                episode_count=episode_count,
                target_hit_rate=target_hit_rate,
                invalidation_hit_rate=invalidation_hit_rate,
                direction_accuracy=direction_accuracy,
                expectancy=expectancy,
            ),
        }
    )
    return row


def _episode_recommendation(
    *,
    approved_count: int,
    episode_count: int,
    target_hit_rate: float | None,
    invalidation_hit_rate: float | None,
    direction_accuracy: float | None,
    expectancy: float | None,
) -> str:
    if approved_count == 0:
        return "REVIEW_REQUIRED"
    if episode_count < 20:
        return "TEST_MORE"
    if expectancy is not None and expectancy < 0 and direction_accuracy is not None and direction_accuracy < 0.45:
        return "KILL"
    if target_hit_rate is not None and invalidation_hit_rate is not None and target_hit_rate > invalidation_hit_rate:
        return "FILTER_CANDIDATE"
    return "KEEP_AS_CONTEXT"


def _thesis_type(rule_tag: str, rule_type: str, quality_label: str, action_bias: str, text: str) -> str:
    tag = rule_tag.upper()
    kind = rule_type.upper()
    quality = quality_label.upper()
    bias = action_bias.upper()
    lower = text.lower()
    if "POST_EVENT" in kind or "POST_EVENT" in quality:
        return "POST_EVENT_COMMENTARY"
    if "UNTESTABLE" in kind or "UNTESTABLE" in quality:
        return "UNTESTABLE"
    if tag in {"REJECTION_AT_WALL"} or "reject" in lower:
        return "REJECT_LEVEL"
    if tag in {"ACCEPTANCE_CLOSE_CONFIRMATION"} or bias == "BREAKOUT" or "accept" in lower or "break" in lower:
        return "BREAK_LEVEL"
    if tag in {"PIN_RISK"}:
        return "PIN_OR_MAGNET"
    if tag in {"SQUEEZE_RISK", "LOW_OI_GAP"}:
        return "SQUEEZE_CONTINUATION"
    if tag in {"NO_TRADE_DISCIPLINE", "NEWS_EVENT_WARNING", "STALE_DATA_WARNING"}:
        return "NO_TRADE"
    if tag in {"ONE_SD_RANGE", "TWO_SD_STRESS", "THREE_SD_EXTREME", "IV_EXPECTED_MOVE"}:
        return "RANGE_ROTATION"
    if bias == "WATCH_ONLY":
        return "WATCH_ONLY"
    if tag in {"BASIS_ADJUSTMENT", "OI_WALL", "IV_RV_VRP", "VOLATILITY_SMILE_SKEW", "MARKET_MAKER_GAMMA"}:
        return "CONTEXT_ONLY"
    return "CONTEXT_ONLY"


def _expected_direction(thesis_type: str, action_bias: str, mentioned_direction: str) -> str:
    if thesis_type in {"NO_TRADE"}:
        return "NO_TRADE"
    if thesis_type in {"CONTEXT_ONLY", "WATCH_ONLY", "POST_EVENT_COMMENTARY", "UNTESTABLE"}:
        return "NONE"
    if mentioned_direction in {"LONG", "SHORT", "RANGE", "NO_TRADE"}:
        return mentioned_direction
    bias = action_bias.upper()
    if bias in {"PIN_RISK", "SQUEEZE_RISK"}:
        return "NONE"
    if thesis_type == "RANGE_ROTATION":
        return "RANGE"
    return "NONE"


def _mentioned_direction(text: str) -> str:
    lower = text.lower()
    if re.search(r"\b(no[-_ ]?trade|do not trade|stay out)\b|ไม่เทรด", lower):
        return "NO_TRADE"
    if re.search(r"\b(short|sell|down|bearish|resistance)\b|ขาย", lower):
        return "SHORT"
    if re.search(r"\b(long|buy|up|bullish|support)\b|ซื้อ", lower):
        return "LONG"
    if re.search(r"\b(range|rotate|middle|mean)\b", lower):
        return "RANGE"
    return "NONE"


def _mentioned_time_horizon(text: str) -> str:
    lower = text.lower()
    if re.search(r"\b1h|1 hour|one hour\b", lower):
        return "1h"
    if re.search(r"\b4h|4 hour|four hour\b", lower):
        return "4h"
    if "session" in lower:
        return "session"
    if "next" in lower:
        return "next_session"
    if "today" in lower:
        return "today"
    return ""


def _keyword_level(text: str, keywords: tuple[str, ...]) -> float | None:
    for keyword in keywords:
        match = re.search(rf"{re.escape(keyword)}[^0-9]{{0,30}}(\d{{3,5}}(?:\.\d+)?)", text, flags=re.IGNORECASE)
        if match:
            return _float_or_none(match.group(1))
    return None


def _invalidation_text(text: str) -> str:
    return _keyword_phrase(text, ("invalid", "invalidation", "stop"))


def _target_text(text: str) -> str:
    return _keyword_phrase(text, ("target", "toward", "tp", "take profit"))


def _keyword_phrase(text: str, keywords: tuple[str, ...]) -> str:
    for keyword in keywords:
        match = re.search(rf"(.{{0,20}}{re.escape(keyword)}.{{0,60}})", text, flags=re.IGNORECASE)
        if match:
            return " ".join(match.group(1).split())
    return ""


def _parse_levels(value: Any) -> list[float]:
    text = str(value or "")
    levels = []
    for raw in re.findall(r"\d{3,5}(?:\.\d+)?", text.replace(",", "")):
        parsed = _float_or_none(raw)
        if parsed is not None and 100 <= parsed <= 10_000:
            levels.append(parsed)
    return _unique_floats(levels, limit=8)


def _window_end(availability: datetime, window: str, config: ResearchConfig) -> datetime | None:
    if window == "1h":
        return availability + timedelta(hours=1)
    if window == "4h":
        return availability + timedelta(hours=4)
    if window == "session_close":
        close = availability.replace(
            hour=config.session_close_hour_utc,
            minute=0,
            second=0,
            microsecond=0,
        )
        return close if close > availability else None
    days = {"next_session": 1, "3_sessions": 3, "5_sessions": 5}.get(window)
    if days is None:
        return None
    return (availability + timedelta(days=days)).replace(
        hour=config.session_close_hour_utc,
        minute=0,
        second=0,
        microsecond=0,
    )


def _mfe_mae(direction: str, spot: float, high: float, low: float) -> tuple[float | None, float | None]:
    if direction == "LONG":
        return high - spot, low - spot
    if direction == "SHORT":
        return spot - low, spot - high
    if direction == "RANGE":
        return min(abs(high - spot), abs(spot - low)), -max(abs(high - spot), abs(spot - low))
    return None, None


def _level_hit(
    *,
    level: float | None,
    direction: str,
    spot: float,
    high: float,
    low: float,
) -> bool | None:
    if level is None:
        return None
    resolved_direction = direction
    if resolved_direction not in {"LONG", "SHORT"}:
        resolved_direction = "LONG" if level >= spot else "SHORT"
    if resolved_direction == "LONG":
        return high >= level
    return low <= level


def _direction_correct(
    direction: str,
    close_return: float | None,
    episode: dict[str, Any],
    future: list[dict[str, Any]],
) -> bool | None:
    if close_return is None:
        return None
    if direction == "LONG":
        return close_return > 0
    if direction == "SHORT":
        return close_return < 0
    if direction == "RANGE":
        upper = _float_or_none(episode.get("one_sd_level_upper"))
        lower = _float_or_none(episode.get("one_sd_level_lower"))
        if upper is None or lower is None:
            return None
        highs = [_float_or_none(row.get("high")) for row in future]
        lows = [_float_or_none(row.get("low")) for row in future]
        return max(value for value in highs if value is not None) <= upper and min(
            value for value in lows if value is not None
        ) >= lower
    if direction == "NO_TRADE":
        return True
    return None


def _signed_close_return(direction: str, close_return: float | None) -> float | None:
    if close_return is None:
        return None
    if direction == "LONG":
        return close_return
    if direction == "SHORT":
        return -close_return
    if direction == "RANGE":
        return -abs(close_return)
    if direction == "NO_TRADE":
        return 0.0
    return None


def _opposite_direction(direction: str) -> str:
    if direction == "LONG":
        return "SHORT"
    if direction == "SHORT":
        return "LONG"
    return direction


def _wall_reaction(episode: dict[str, Any], high: float, low: float, close: float | None) -> tuple[bool | None, bool | None]:
    level = _float_or_none(episode.get("expected_from_level")) or _float_or_none(episode.get("wall_level"))
    if level is None or close is None:
        return None, None
    spot = _float_or_none(episode.get("spot_price"))
    if spot is None:
        return None, None
    if level >= spot:
        touched = high >= level
        return touched and close < level, touched and close > level
    touched = low <= level
    return touched and close > level, touched and close < level


def _stayed_inside(high: float, low: float, upper: float | None, lower: float | None) -> bool | None:
    if upper is None or lower is None:
        return None
    return high <= upper and low >= lower


def _broke_band(high: float, low: float, upper: float | None, lower: float | None) -> bool | None:
    if upper is None or lower is None:
        return None
    return high > upper or low < lower


def _outcome_label(
    episode: dict[str, Any],
    target_hit: bool | None,
    invalidation_hit: bool | None,
    direction_correct: bool | None,
) -> str:
    thesis_type = str(episode.get("thesis_type") or "")
    if thesis_type in {"POST_EVENT_COMMENTARY", "UNTESTABLE", "CONTEXT_ONLY", "WATCH_ONLY"}:
        return "UNTESTABLE" if thesis_type in {"POST_EVENT_COMMENTARY", "UNTESTABLE"} else "NO_CLEAR_OUTCOME"
    if target_hit is True and invalidation_hit is not True:
        return "THESIS_SUPPORTED"
    if invalidation_hit is True and target_hit is not True:
        return "THESIS_FAILED"
    if target_hit is True and invalidation_hit is True:
        return "MIXED"
    if direction_correct is True:
        return "THESIS_SUPPORTED"
    if direction_correct is False:
        return "THESIS_FAILED"
    return "NO_CLEAR_OUTCOME"


def _realized_vol_after(rows: list[dict[str, Any]]) -> float | None:
    closes = [_float_or_none(row.get("close")) for row in rows]
    closes = [value for value in closes if value is not None and value > 0]
    if len(closes) < 2:
        return None
    returns = [math.log(closes[index] / closes[index - 1]) for index in range(1, len(closes))]
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((value - mean) ** 2 for value in returns) / (len(returns) - 1)
    return math.sqrt(variance) * math.sqrt(252) * 100


def _feature_rows(feature_table: pl.DataFrame) -> list[dict[str, Any]]:
    if feature_table.is_empty():
        return []
    return sorted(feature_table.to_dicts(), key=lambda row: _to_datetime(row.get("timestamp")) or datetime.min.replace(tzinfo=UTC))


def _same_session_predictive_allowed(availability: datetime | None, config: ResearchConfig) -> bool:
    if availability is None:
        return False
    return availability.hour < config.session_close_hour_utc


def _open_side(close: float | None, session_open: float | None) -> str:
    if close is None or session_open is None:
        return "UNKNOWN"
    if close > session_open:
        return "ABOVE_OPEN"
    if close < session_open:
        return "BELOW_OPEN"
    return "AT_OPEN"


def _reviewed_status(row: dict[str, Any]) -> str:
    value = str(row.get("reviewer_decision") or "").strip().upper()
    return value if value in REVIEW_DECISIONS else ""


def _episode_id(row: dict[str, Any], availability: datetime | None) -> str:
    raw = "|".join(
        [
            str(row.get("review_id") or ""),
            str(row.get("transcript_id") or ""),
            str(row.get("rule_tag") or ""),
            str(availability or ""),
            str(row.get("source_excerpt") or "")[:120],
        ]
    )
    return "gep_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _approval_counts(episodes: pl.DataFrame) -> pl.DataFrame:
    if episodes.is_empty():
        return pl.DataFrame(schema={"episode_review_status": pl.String, "len": pl.Int64})
    return episodes.group_by("episode_review_status").len().sort("episode_review_status")


def _group_rows(rows: list[dict[str, Any]], columns: list[str]) -> dict[tuple[Any, ...], list[dict[str, Any]]]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for row in rows:
        key = tuple(row.get(column) for column in columns)
        grouped.setdefault(key, []).append(row)
    return grouped


def _no_trade_count(signal_events: pl.DataFrame) -> int:
    if signal_events.is_empty() or "signal" not in signal_events.columns:
        return 0
    return signal_events.filter(pl.col("signal").str.contains("NO_TRADE")).height


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() == "true"


def _mean(values: list[float | bool]) -> float | None:
    if not values:
        return None
    numbers = [1.0 if value is True else 0.0 if value is False else float(value) for value in values]
    return sum(numbers) / len(numbers)


def _unique_floats(values: list[float], *, limit: int) -> list[float]:
    result = []
    for value in values:
        if not any(abs(value - existing) < 1e-9 for existing in result):
            result.append(value)
        if len(result) >= limit:
            break
    return result


def _format_level(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(parsed):
        return None
    return parsed


def _float_or_zero(value: Any) -> float:
    parsed = _float_or_none(value)
    return parsed if parsed is not None else 0.0


def _to_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _empty_snapshot() -> dict[str, Any]:
    return {
        "data_available_timestamp": None,
        "spot_price": None,
        "session_open": None,
        "open_side": "UNKNOWN",
        "distance_from_open": None,
        "annualized_iv": None,
        "realized_vol": None,
        "vrp": None,
        "one_sd_level_upper": None,
        "one_sd_level_lower": None,
        "two_sd_level_upper": None,
        "two_sd_level_lower": None,
        "sigma_position": None,
        "nearest_wall_above": None,
        "nearest_wall_below": None,
        "nearest_wall_above_score": None,
        "nearest_wall_below_score": None,
        "basis": None,
        "nearest_spot_equivalent_strike": None,
        "intraday_volume_near_level": None,
        "oi_change_near_level": None,
        "data_quality_status": "MISSING_SNAPSHOT",
        "sigma_zone": "unknown",
        "wall_score_bucket": "unknown",
        "vol_regime": "UNKNOWN",
        "wall_level": None,
        "wall_score": None,
    }


def _report_columns(frame: pl.DataFrame) -> pl.DataFrame:
    if frame.is_empty():
        return frame
    preferred = [
        "episode_id",
        "transcript_id",
        "rule_tag",
        "thesis_type",
        "expected_direction",
        "reviewer_decision",
        "episode_review_status",
        "spot_price",
        "expected_from_level",
        "expected_to_level",
        "invalidation_level",
        "outcome_window",
        "target_hit",
        "invalidation_hit",
        "direction_correct",
        "outcome_label",
    ]
    columns = [column for column in preferred if column in frame.columns]
    return frame.select(columns) if columns else frame


def _frame_markdown(frame: pl.DataFrame) -> str:
    if frame.is_empty():
        return "_No rows._"
    columns = frame.columns
    rows = ["| " + " | ".join(columns) + " |", "|" + "|".join(["---"] * len(columns)) + "|"]
    for raw in frame.head(20).to_dicts():
        rows.append("| " + " | ".join(str(raw.get(column, "")) for column in columns) + " |")
    return "\n".join(rows)


def _rows_frame(rows: list[dict[str, Any]]) -> pl.DataFrame:
    return pl.DataFrame(rows, infer_schema_length=None)


def _empty_episodes() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "episode_id": pl.String,
            "transcript_id": pl.String,
            "transcript_date": pl.String,
            "availability_timestamp": pl.Datetime(time_zone="UTC"),
            "source_excerpt": pl.String,
            "normalized_english_summary": pl.String,
            "reviewer_decision": pl.String,
            "rule_tag": pl.String,
            "rule_type": pl.String,
            "quality_label": pl.String,
            "action_bias": pl.String,
            "condition_text": pl.String,
            "invalidation_rule": pl.String,
            "target_text": pl.String,
            "mentioned_levels": pl.String,
            "mentioned_direction": pl.String,
            "mentioned_time_horizon": pl.String,
            "required_market_data": pl.String,
            "data_available_timestamp": pl.Datetime(time_zone="UTC"),
            "spot_price": pl.Float64,
            "session_open": pl.Float64,
            "open_side": pl.String,
            "distance_from_open": pl.Float64,
            "annualized_iv": pl.Float64,
            "realized_vol": pl.Float64,
            "vrp": pl.Float64,
            "one_sd_level_upper": pl.Float64,
            "one_sd_level_lower": pl.Float64,
            "two_sd_level_upper": pl.Float64,
            "two_sd_level_lower": pl.Float64,
            "sigma_position": pl.Float64,
            "nearest_wall_above": pl.Float64,
            "nearest_wall_below": pl.Float64,
            "nearest_wall_above_score": pl.Float64,
            "nearest_wall_below_score": pl.Float64,
            "basis": pl.Float64,
            "nearest_spot_equivalent_strike": pl.Float64,
            "intraday_volume_near_level": pl.Float64,
            "oi_change_near_level": pl.Float64,
            "data_quality_status": pl.String,
            "thesis_type": pl.String,
            "expected_direction": pl.String,
            "expected_from_level": pl.Float64,
            "expected_to_level": pl.Float64,
            "invalidation_level": pl.Float64,
            "confidence_score": pl.Float64,
            "testability_score": pl.Float64,
            "leakage_risk_score": pl.Float64,
        }
    )


def _empty_outcomes() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "episode_id": pl.String,
            "outcome_window": pl.String,
            "window_start": pl.Datetime(time_zone="UTC"),
            "window_end": pl.Datetime(time_zone="UTC"),
            "target_hit": pl.Boolean,
            "invalidation_hit": pl.Boolean,
            "direction_correct": pl.Boolean,
            "max_favorable_excursion": pl.Float64,
            "max_adverse_excursion": pl.Float64,
            "close_return": pl.Float64,
            "realized_vol_after": pl.Float64,
            "wall_rejected": pl.Boolean,
            "wall_accepted": pl.Boolean,
            "stayed_inside_1sd": pl.Boolean,
            "broke_1sd": pl.Boolean,
            "broke_2sd": pl.Boolean,
            "outcome_label": pl.String,
        }
    )


def _empty_performance() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "rule_tag": pl.String,
            "thesis_type": pl.String,
            "action_bias": pl.String,
            "reviewed_status": pl.String,
            "sigma_zone": pl.String,
            "wall_score_bucket": pl.String,
            "vol_regime": pl.String,
            "episode_count": pl.Int64,
            "approved_count": pl.Int64,
            "target_hit_rate": pl.Float64,
            "invalidation_hit_rate": pl.Float64,
            "direction_accuracy": pl.Float64,
            "average_MFE": pl.Float64,
            "average_MAE": pl.Float64,
            "expectancy_proxy": pl.Float64,
            "sample_size_warning": pl.Boolean,
            "walk_forward_pass": pl.Boolean,
            "placebo_pass": pl.Boolean,
            "recommendation": pl.String,
        }
    )


def _write_bar_svg(path: Path, *, title: str, labels: list[str], values: list[float]) -> None:
    width, height = 900, 300
    if not values:
        _write_empty_svg(path, title)
        return
    maximum = max(max(abs(value) for value in values), 1.0)
    bar_width = max(4, (width - 80) / max(len(values), 1))
    bars = []
    for index, value in enumerate(values):
        x = 40 + index * bar_width
        bar_height = abs(value) / maximum * (height - 90)
        y = height - 40 - bar_height
        color = "#0f766e" if value >= 0 else "#b91c1c"
        bars.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width * 0.8:.1f}" '
            f'height="{bar_height:.1f}" fill="{color}"><title>{labels[index]}</title></rect>'
        )
    path.write_text(_svg(title, "\n".join(bars)), encoding="utf-8")


def _write_grouped_bar_svg(
    path: Path,
    *,
    title: str,
    labels: list[str],
    positive: list[float],
    negative: list[float],
) -> None:
    values = [*positive, *negative]
    if not values:
        _write_empty_svg(path, title)
        return
    width = 900
    maximum = max(max(abs(value) for value in values), 1.0)
    bar_width = max(4, (width - 80) / max(len(labels) * 2, 1))
    body = ['<line x1="40" y1="160" x2="860" y2="160" stroke="#6b7280" />']
    for index, label in enumerate(labels):
        x = 40 + index * bar_width * 2
        pos_height = positive[index] / maximum * 120 if index < len(positive) else 0
        neg_height = abs(negative[index]) / maximum * 120 if index < len(negative) else 0
        body.append(
            f'<rect x="{x:.1f}" y="{160 - pos_height:.1f}" width="{bar_width * 0.8:.1f}" '
            f'height="{pos_height:.1f}" fill="#0f766e"><title>{label} MFE</title></rect>'
        )
        body.append(
            f'<rect x="{x + bar_width:.1f}" y="160" width="{bar_width * 0.8:.1f}" '
            f'height="{neg_height:.1f}" fill="#b91c1c"><title>{label} MAE</title></rect>'
        )
    path.write_text(_svg(title, "\n".join(body)), encoding="utf-8")


def _write_empty_svg(path: Path, title: str) -> None:
    path.write_text(_svg(title, '<text x="40" y="80">No data available.</text>'), encoding="utf-8")


def _svg(title: str, body: str) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="320" viewBox="0 0 900 320">'
        '<rect width="900" height="320" fill="#ffffff" />'
        f'<text x="40" y="30" font-size="18" font-family="Arial">{title}</text>'
        f"{body}</svg>"
    )
