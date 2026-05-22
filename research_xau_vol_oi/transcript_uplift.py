"""Transcript-conditioned uplift tests for XAU Vol-OI research.

This layer asks whether transcript-derived rule availability improves future
signal outcomes beyond the base Vol-OI engine. It is deliberately
research-only: no live trading, no future transcript content for real tests,
no no-trade row removal, and no duplicate event counting.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import polars as pl

from research_xau_vol_oi.config import DIRECTIONAL_SIGNALS, ResearchConfig, Signal
from research_xau_vol_oi.transcript_timeline import RULE_TAGS


FLAG_RULES = {
    "BASIS_ADJUSTMENT": "has_basis_adjustment_tag",
    "IV_EXPECTED_MOVE": "has_iv_expected_move_tag",
    "ONE_SD_RANGE": "has_one_sd_range_tag",
    "TWO_SD_STRESS": "has_two_sd_stress_tag",
    "OI_WALL": "has_oi_wall_tag",
    "INTRADAY_VOLUME": "has_intraday_volume_tag",
    "OI_CHANGE_FRESHNESS": "has_oi_change_freshness_tag",
    "REJECTION_AT_WALL": "has_rejection_at_wall_tag",
    "ACCEPTANCE_CLOSE_CONFIRMATION": "has_acceptance_close_confirmation_tag",
    "NO_TRADE_DISCIPLINE": "has_no_trade_discipline_tag",
    "IV_RV_VRP": "has_iv_rv_vrp_tag",
    "LOW_OI_GAP": "has_low_oi_gap_tag",
    "SQUEEZE_RISK": "has_squeeze_risk_tag",
}
RULE_COMBINATIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("BASIS_ADJUSTMENT+OI_WALL", ("BASIS_ADJUSTMENT", "OI_WALL")),
    ("IV_EXPECTED_MOVE+ONE_SD_RANGE", ("IV_EXPECTED_MOVE", "ONE_SD_RANGE")),
    ("OI_WALL+INTRADAY_VOLUME", ("OI_WALL", "INTRADAY_VOLUME")),
    ("OI_WALL+REJECTION_AT_WALL", ("OI_WALL", "REJECTION_AT_WALL")),
    (
        "OI_WALL+ACCEPTANCE_CLOSE_CONFIRMATION",
        ("OI_WALL", "ACCEPTANCE_CLOSE_CONFIRMATION"),
    ),
    (
        "BASIS_ADJUSTMENT+IV_EXPECTED_MOVE+OI_WALL",
        ("BASIS_ADJUSTMENT", "IV_EXPECTED_MOVE", "OI_WALL"),
    ),
    ("NO_TRADE_DISCIPLINE+middle_1sd", ("NO_TRADE_DISCIPLINE", "middle_1sd")),
    ("IV_RV_VRP+OI_WALL", ("IV_RV_VRP", "OI_WALL")),
    ("LOW_OI_GAP+SQUEEZE_RISK", ("LOW_OI_GAP", "SQUEEZE_RISK")),
)
LOGICAL_CONTEXT_TAGS = {
    "BASIS_ADJUSTMENT",
    "IV_EXPECTED_MOVE",
    "ONE_SD_RANGE",
    "OI_WALL",
    "NO_TRADE_DISCIPLINE",
    "NEWS_EVENT_WARNING",
    "STALE_DATA_WARNING",
}
MIN_SAMPLE_SIZE = 20
PLACEBO_TYPES = ("REAL", "SHUFFLED_TAGS", "SHIFTED_AVAILABILITY", "LEAKAGE_PLACEBO")


@dataclass(frozen=True)
class TranscriptUpliftResult:
    """Generated uplift frames and conservative final decision."""

    conditioned_events: pl.DataFrame
    rule_uplift: pl.DataFrame
    combination_uplift: pl.DataFrame
    walk_forward_uplift: pl.DataFrame
    placebo_tests: pl.DataFrame
    keep_kill: pl.DataFrame
    final_decision: str


def run_transcript_uplift_layer(
    *,
    feature_table: pl.DataFrame,
    signal_events: pl.DataFrame,
    trades: pl.DataFrame,
    transcript_timeline: pl.DataFrame,
    output_dir: Path,
    charts_dir: Path,
    config: ResearchConfig | None = None,
) -> TranscriptUpliftResult:
    """Run transcript-conditioned uplift tests and write all requested outputs."""

    cfg = config or ResearchConfig()
    output_dir.mkdir(parents=True, exist_ok=True)
    charts_dir.mkdir(parents=True, exist_ok=True)

    conditioned = build_transcript_conditioned_events(
        signal_events,
        transcript_timeline,
        config=cfg,
    )
    rule_uplift = transcript_rule_uplift(conditioned, trades)
    combination_uplift = transcript_rule_combination_uplift(conditioned, trades)
    walk_forward = walk_forward_transcript_uplift(
        feature_table,
        conditioned,
        trades,
        config=cfg,
    )
    placebo = transcript_placebo_tests(
        signal_events,
        transcript_timeline,
        trades,
        config=cfg,
    )
    keep_kill = build_transcript_rule_keep_kill(
        rule_uplift,
        combination_uplift,
        walk_forward,
        placebo,
    )
    final_decision = transcript_uplift_final_decision(
        rule_uplift,
        walk_forward,
        placebo,
        keep_kill,
        conditioned,
    )

    conditioned.write_csv(output_dir / "transcript_conditioned_events.csv")
    rule_uplift.write_csv(output_dir / "transcript_rule_uplift.csv")
    combination_uplift.write_csv(output_dir / "transcript_rule_combination_uplift.csv")
    walk_forward.write_csv(output_dir / "transcript_walk_forward_uplift.csv")
    placebo.write_csv(output_dir / "transcript_placebo_tests.csv")
    keep_kill.write_csv(output_dir / "transcript_rule_keep_kill.csv")
    write_transcript_uplift_report(
        output_dir / "transcript_uplift_report.md",
        rule_uplift=rule_uplift,
        combination_uplift=combination_uplift,
        walk_forward=walk_forward,
        placebo=placebo,
        keep_kill=keep_kill,
        final_decision=final_decision,
        conditioned_events=conditioned,
    )
    write_transcript_uplift_charts(
        charts_dir=charts_dir,
        rule_uplift=rule_uplift,
        combination_uplift=combination_uplift,
        walk_forward=walk_forward,
    )

    return TranscriptUpliftResult(
        conditioned_events=conditioned,
        rule_uplift=rule_uplift,
        combination_uplift=combination_uplift,
        walk_forward_uplift=walk_forward,
        placebo_tests=placebo,
        keep_kill=keep_kill,
        final_decision=final_decision,
    )


def build_transcript_conditioned_events(
    signal_events: pl.DataFrame,
    transcript_timeline: pl.DataFrame,
    *,
    config: ResearchConfig | None = None,
    allow_future_transcripts: bool = False,
) -> pl.DataFrame:
    """Attach as-of active transcript rule tags to every signal event.

    Real research runs use only transcripts with
    ``availability_timestamp <= event_timestamp``. ``allow_future_transcripts``
    exists only for the explicitly labeled leakage placebo.
    """

    _ = config or ResearchConfig()
    if signal_events.is_empty():
        return _empty_conditioned_events()

    transcripts = _timeline_rows(transcript_timeline)
    rows: list[dict[str, Any]] = []
    for event in signal_events.sort("event_timestamp").to_dicts():
        event_ts = _to_utc_datetime(event.get("event_timestamp"))
        if event_ts is None:
            active = []
        elif allow_future_transcripts:
            active = [item for item in transcripts if item["availability_timestamp"] > event_ts]
        else:
            active = [item for item in transcripts if item["availability_timestamp"] <= event_ts]
        active_tags = sorted({tag for item in active for tag in item["tags"]})
        confidences = [float(item["confidence_score"]) for item in active]
        latest_availability = max((item["availability_timestamp"] for item in active), default=None)
        age_hours = (
            (event_ts - latest_availability).total_seconds() / 3600.0
            if event_ts is not None and latest_availability is not None
            else None
        )
        enriched = {
            **event,
            "active_transcript_rule_tags": "|".join(active_tags),
            "active_rule_count": len(active_tags),
            "latest_transcript_age_hours": age_hours,
            "transcript_confidence_max": max(confidences) if confidences else None,
            "transcript_confidence_mean": _average(confidences),
            "middle_1sd": _is_middle_1sd(event),
            "no_trade_row_retained": str(event.get("signal") or "").startswith("NO_TRADE"),
        }
        for tag, column in FLAG_RULES.items():
            enriched[column] = tag in active_tags
        rows.append(enriched)
    return _rows_frame(rows) if rows else _empty_conditioned_events()


def transcript_rule_uplift(
    conditioned_events: pl.DataFrame,
    trades: pl.DataFrame,
    *,
    min_sample_size: int = MIN_SAMPLE_SIZE,
) -> pl.DataFrame:
    """Compare event outcomes with and without each active transcript rule tag."""

    if conditioned_events.is_empty():
        return _empty_uplift()
    return _uplift_rows(
        conditioned_events,
        trades,
        candidates=[
            _Candidate("ANY_TRANSCRIPT_TAG", "any_tag", tuple(), lambda row: int(row.get("active_rule_count") or 0) > 0),
            *[
                _Candidate(tag, "rule_tag", (tag,), lambda row, tag=tag: _row_has_tag(row, tag))
                for tag in RULE_TAGS
            ],
        ],
        min_sample_size=min_sample_size,
    )


def transcript_rule_combination_uplift(
    conditioned_events: pl.DataFrame,
    trades: pl.DataFrame,
    *,
    min_sample_size: int = MIN_SAMPLE_SIZE,
) -> pl.DataFrame:
    """Evaluate predefined transcript rule combinations."""

    if conditioned_events.is_empty():
        return _empty_uplift()
    candidates = [
        _Candidate(name, "rule_combination", tags, lambda row, tags=tags: _row_has_all(row, tags))
        for name, tags in RULE_COMBINATIONS
    ]
    return _uplift_rows(
        conditioned_events,
        trades,
        candidates=candidates,
        min_sample_size=min_sample_size,
    )


def walk_forward_transcript_uplift(
    feature_table: pl.DataFrame,
    conditioned_events: pl.DataFrame,
    trades: pl.DataFrame,
    *,
    config: ResearchConfig | None = None,
    min_sample_size: int = MIN_SAMPLE_SIZE,
) -> pl.DataFrame:
    """Select positive-uplift transcript rules in train and freeze them in test."""

    cfg = config or ResearchConfig()
    if conditioned_events.is_empty():
        return _empty_walk_forward()
    timeline = _price_timestamps(feature_table, conditioned_events)
    if not timeline:
        return _empty_walk_forward()
    candidates = _all_candidates()
    rows: list[dict[str, Any]] = []
    start = 0
    split_id = 1
    while start + cfg.walk_forward_train_bars < len(timeline):
        train_end = start + cfg.walk_forward_train_bars - 1
        test_start = train_end + 1
        test_end = min(test_start + cfg.walk_forward_test_bars - 1, len(timeline) - 1)
        train_start_ts = timeline[start]
        train_end_ts = timeline[train_end]
        test_start_ts = timeline[test_start]
        test_end_ts = timeline[test_end]
        train_events = _time_slice_events(conditioned_events, train_start_ts, train_end_ts)
        test_events = _time_slice_events(conditioned_events, test_start_ts, test_end_ts)
        selected = _select_train_rules(
            train_events,
            trades,
            candidates=candidates,
            min_sample_size=max(3, min_sample_size // 2),
        )
        selected_ids = [item["candidate"].identifier for item in selected]
        selected_test_events = _union_candidate_events(test_events, [item["candidate"] for item in selected])
        selected_metrics = _event_subset_metrics(selected_test_events, trades)
        base_metrics = _event_subset_metrics(test_events, trades)
        uplift = _delta(selected_metrics["expectancy"], base_metrics["expectancy"])
        bad_trade_delta = _bad_trade_rate(selected_metrics) - _bad_trade_rate(base_metrics)
        passed = (
            bool(selected_ids)
            and selected_metrics["directional_trade_count"] >= min_sample_size
            and _none_safe(uplift) > 0
            and bad_trade_delta <= 0
        )
        rows.append(
            {
                "split_id": split_id,
                "train_start": train_start_ts,
                "train_end": train_end_ts,
                "test_start": test_start_ts,
                "test_end": test_end_ts,
                "selected_rules": ",".join(selected_ids),
                "selected_rule_count": len(selected_ids),
                "train_best_uplift": max(
                    (_none_safe(item["uplift_vs_no_tag"]) for item in selected),
                    default=None,
                ),
                "test_event_count": selected_metrics["event_count"],
                "test_directional_trade_count": selected_metrics["directional_trade_count"],
                "test_no_trade_count": selected_metrics["no_trade_count"],
                "test_expectancy": selected_metrics["expectancy"],
                "test_profit_factor": selected_metrics["profit_factor"],
                "test_max_drawdown": selected_metrics["max_drawdown"],
                "test_base_expectancy": base_metrics["expectancy"],
                "test_uplift_vs_base_score": uplift,
                "test_bad_trade_rate": _bad_trade_rate(selected_metrics),
                "test_base_bad_trade_rate": _bad_trade_rate(base_metrics),
                "bad_trade_rate_delta": bad_trade_delta,
                "pass_fail": "PASS" if passed else "FAIL",
                "no_lookahead": train_end_ts < test_start_ts,
            }
        )
        split_id += 1
        start = test_end + 1
    return _rows_frame(rows) if rows else _empty_walk_forward()


def transcript_placebo_tests(
    signal_events: pl.DataFrame,
    transcript_timeline: pl.DataFrame,
    trades: pl.DataFrame,
    *,
    config: ResearchConfig | None = None,
    min_sample_size: int = MIN_SAMPLE_SIZE,
) -> pl.DataFrame:
    """Run shuffle, timestamp-shift, and leakage placebo tests."""

    cfg = config or ResearchConfig()
    rng = random.Random(cfg.random_seed)
    scenarios = {
        "REAL": (transcript_timeline, False),
        "SHUFFLED_TAGS": (_shuffle_timeline_tags(transcript_timeline, rng), False),
        "SHIFTED_AVAILABILITY": (_shift_timeline_availability(transcript_timeline, rng), False),
        "LEAKAGE_PLACEBO": (transcript_timeline, True),
    }
    rows = []
    real_best: dict[str, Any] | None = None
    for placebo_type, (timeline, allow_future) in scenarios.items():
        conditioned = build_transcript_conditioned_events(
            signal_events,
            timeline,
            config=cfg,
            allow_future_transcripts=allow_future,
        )
        rule_rows = transcript_rule_uplift(
            conditioned,
            trades,
            min_sample_size=min_sample_size,
        )
        combination_rows = transcript_rule_combination_uplift(
            conditioned,
            trades,
            min_sample_size=min_sample_size,
        )
        best = _best_uplift_row(
            pl.concat([rule_rows, combination_rows], how="diagonal_relaxed"),
            min_sample_size=min_sample_size,
        )
        if placebo_type == "REAL":
            real_best = best
        rows.append(
            {
                "placebo_type": placebo_type,
                "best_rule_id": best.get("rule_id"),
                "best_rule_type": best.get("rule_type"),
                "best_trade_count": best.get("directional_trade_count"),
                "best_expectancy": best.get("expectancy"),
                "best_uplift_vs_no_tag": best.get("uplift_vs_no_tag"),
                "real_best_uplift": None,
                "real_beats_placebo": None,
                "used_future_transcripts": allow_future,
                "placebo_passed": None,
            }
        )
    real_uplift = _none_safe((real_best or {}).get("uplift_vs_no_tag"))
    finalized = []
    for row in rows:
        placebo_uplift = _none_safe(row.get("best_uplift_vs_no_tag"))
        real_beats = real_uplift > placebo_uplift if row["placebo_type"] != "REAL" else None
        finalized.append(
            {
                **row,
                "real_best_uplift": real_uplift,
                "real_beats_placebo": real_beats,
                "placebo_passed": real_beats
                if row["placebo_type"] in {"SHUFFLED_TAGS", "SHIFTED_AVAILABILITY"}
                else None,
            }
        )
    return _rows_frame(finalized)


def build_transcript_rule_keep_kill(
    rule_uplift: pl.DataFrame,
    combination_uplift: pl.DataFrame,
    walk_forward: pl.DataFrame,
    placebo: pl.DataFrame,
    *,
    min_sample_size: int = MIN_SAMPLE_SIZE,
) -> pl.DataFrame:
    """Create conservative keep/filter/quarantine/kill recommendations."""

    if rule_uplift.is_empty() and combination_uplift.is_empty():
        return _empty_keep_kill()
    frames = []
    if not rule_uplift.is_empty():
        frames.append(rule_uplift)
    if not combination_uplift.is_empty():
        frames.append(combination_uplift)
    rows = pl.concat(frames, how="diagonal_relaxed").to_dicts()
    wf_pass_ids = _walk_forward_pass_ids(walk_forward)
    placebo_passed = _placebo_passed(placebo)
    recommendations = []
    for row in rows:
        rule_id = str(row.get("rule_id") or "")
        trade_count = int(row.get("directional_trade_count") or 0)
        uplift = row.get("uplift_vs_no_tag")
        wf_pass = rule_id in wf_pass_ids
        recommendation, reason = _keep_kill_recommendation(
            rule_id=rule_id,
            rule_type=str(row.get("rule_type") or ""),
            trade_count=trade_count,
            uplift=uplift,
            walk_forward_pass=wf_pass,
            placebo_passed=placebo_passed,
            min_sample_size=min_sample_size,
        )
        recommendations.append(
            {
                "rule_id": rule_id,
                "rule_type": row.get("rule_type"),
                "event_count": row.get("event_count"),
                "directional_trade_count": trade_count,
                "no_trade_count": row.get("no_trade_count"),
                "expectancy": row.get("expectancy"),
                "profit_factor": row.get("profit_factor"),
                "uplift_vs_no_tag": uplift,
                "walk_forward_pass": wf_pass,
                "placebo_passed": placebo_passed,
                "recommendation": recommendation,
                "reason": reason,
            }
        )
    return _rows_frame(recommendations) if recommendations else _empty_keep_kill()


def transcript_uplift_final_decision(
    rule_uplift: pl.DataFrame,
    walk_forward: pl.DataFrame,
    placebo: pl.DataFrame,
    keep_kill: pl.DataFrame,
    conditioned_events: pl.DataFrame,
) -> str:
    """Return the final transcript uplift decision."""

    if conditioned_events.is_empty() or rule_uplift.is_empty():
        return "TRANSCRIPT_NO_UPLIFT"
    no_trade_retained = (
        conditioned_events.filter(pl.col("no_trade_row_retained")).height > 0
        if "no_trade_row_retained" in conditioned_events.columns
        else False
    )
    placebo_passed = _placebo_passed(placebo)
    wf_pass = walk_forward.filter(pl.col("pass_fail") == "PASS").height > 0 if not walk_forward.is_empty() else False
    enough = (
        rule_uplift.filter(pl.col("directional_trade_count") >= MIN_SAMPLE_SIZE).height > 0
        if not rule_uplift.is_empty()
        else False
    )
    materially_better = (
        rule_uplift.filter(
            (pl.col("uplift_vs_base_score") > 0)
            | (pl.col("uplift_vs_no_tag") > 0)
        ).height
        > 0
        if not rule_uplift.is_empty()
        else False
    )
    if wf_pass and placebo_passed and enough and no_trade_retained and materially_better:
        return "TRANSCRIPT_VALIDATED_FILTER"
    if wf_pass and enough and materially_better:
        return "TRANSCRIPT_PROMISING_UPLIFT"
    if not keep_kill.is_empty() and keep_kill.filter(
        pl.col("recommendation").is_in(["KEEP_AS_CONTEXT", "QUARANTINE"])
    ).height:
        return "TRANSCRIPT_CONTEXT_ONLY"
    return "TRANSCRIPT_NO_UPLIFT"


def write_transcript_uplift_report(
    path: Path,
    *,
    rule_uplift: pl.DataFrame,
    combination_uplift: pl.DataFrame,
    walk_forward: pl.DataFrame,
    placebo: pl.DataFrame,
    keep_kill: pl.DataFrame,
    final_decision: str,
    conditioned_events: pl.DataFrame,
) -> None:
    """Write Markdown transcript uplift report."""

    no_trade_count = (
        conditioned_events.filter(pl.col("no_trade_row_retained")).height
        if not conditioned_events.is_empty() and "no_trade_row_retained" in conditioned_events.columns
        else 0
    )
    lines = [
        "# Transcript-Conditioned Uplift Report",
        "",
        "Research-only uplift test. This report does not approve live trading.",
        "",
        f"- Final decision: `{final_decision}`",
        f"- Conditioned signal events: {conditioned_events.height}",
        f"- No-trade rows retained: {no_trade_count}",
        f"- Placebo tests passed: {_placebo_passed(placebo)}",
        "",
        "## Rule Tag Uplift",
        "",
        _frame_markdown(_report_columns(rule_uplift)),
        "",
        "## Rule Combination Uplift",
        "",
        _frame_markdown(_report_columns(combination_uplift)),
        "",
        "## Walk-Forward Transcript Uplift",
        "",
        _frame_markdown(walk_forward),
        "",
        "## Placebo Tests",
        "",
        _frame_markdown(placebo),
        "",
        "## Transcript Rule Keep/Kill Decision",
        "",
        _frame_markdown(keep_kill),
        "",
        "## Final Decision",
        "",
        "- `TRANSCRIPT_VALIDATED_FILTER` is blocked unless walk-forward uplift is positive, "
        "shuffled and shifted placebo tests are beaten, samples are sufficient, no-trade rows "
        "are retained, and no future transcript content is used.",
        "- `LEAKAGE_PLACEBO` intentionally uses future transcript content as a negative control "
        "and is never used for recommendations.",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_transcript_uplift_charts(
    *,
    charts_dir: Path,
    rule_uplift: pl.DataFrame,
    combination_uplift: pl.DataFrame,
    walk_forward: pl.DataFrame,
) -> None:
    """Write SVG charts for transcript uplift outputs."""

    charts_dir.mkdir(parents=True, exist_ok=True)
    rule_rows = _top_uplift_rows(rule_uplift)
    _write_bar_svg(
        charts_dir / "transcript_rule_uplift.svg",
        title="Transcript rule uplift vs no-tag",
        labels=[row["rule_id"] for row in rule_rows],
        values=[_none_safe(row.get("uplift_vs_no_tag")) for row in rule_rows],
    )
    combo_rows = _top_uplift_rows(combination_uplift)
    _write_bar_svg(
        charts_dir / "transcript_combination_uplift.svg",
        title="Transcript combination uplift vs no-tag",
        labels=[row["rule_id"] for row in combo_rows],
        values=[_none_safe(row.get("uplift_vs_no_tag")) for row in combo_rows],
    )
    wf_rows = walk_forward.sort("split_id").to_dicts() if not walk_forward.is_empty() else []
    _write_bar_svg(
        charts_dir / "transcript_walk_forward_uplift.svg",
        title="Walk-forward transcript uplift",
        labels=[str(row.get("split_id")) for row in wf_rows],
        values=[_none_safe(row.get("test_uplift_vs_base_score")) for row in wf_rows],
    )


@dataclass(frozen=True)
class _Candidate:
    identifier: str
    rule_type: str
    required_tags: tuple[str, ...]
    predicate: Callable[[dict[str, Any]], bool]


def _uplift_rows(
    conditioned_events: pl.DataFrame,
    trades: pl.DataFrame,
    *,
    candidates: list[_Candidate],
    min_sample_size: int,
) -> pl.DataFrame:
    event_rows = conditioned_events.to_dicts()
    all_metrics = _event_subset_metrics(conditioned_events, trades)
    bollinger_metrics = _trade_metrics(
        [row for row in trades.to_dicts() if row.get("signal") == Signal.BOLLINGER_BASELINE.value]
    )
    random_metrics = _trade_metrics(
        [row for row in trades.to_dicts() if row.get("signal") == Signal.RANDOM_BASELINE.value]
    )
    rows = []
    for candidate in candidates:
        with_events = [row for row in event_rows if candidate.predicate(row)]
        without_events = [row for row in event_rows if not candidate.predicate(row)]
        with_metrics = _event_subset_metrics(_rows_frame(with_events) if with_events else _empty_like(conditioned_events), trades)
        without_metrics = _event_subset_metrics(
            _rows_frame(without_events) if without_events else _empty_like(conditioned_events),
            trades,
        )
        rows.append(
            {
                "rule_id": candidate.identifier,
                "rule_type": candidate.rule_type,
                "required_tags": "|".join(candidate.required_tags),
                **with_metrics,
                "without_tag_event_count": without_metrics["event_count"],
                "without_tag_directional_trade_count": without_metrics["directional_trade_count"],
                "without_tag_expectancy": without_metrics["expectancy"],
                "base_score_expectancy": all_metrics["expectancy"],
                "bollinger_baseline_expectancy": bollinger_metrics["expectancy"],
                "random_baseline_expectancy": random_metrics["expectancy"],
                "sample_size_warning": with_metrics["directional_trade_count"] < min_sample_size,
                "uplift_vs_no_tag": _delta(with_metrics["expectancy"], without_metrics["expectancy"]),
                "uplift_vs_base_score": _delta(with_metrics["expectancy"], all_metrics["expectancy"]),
                "uplift_vs_bollinger_baseline": _delta(
                    with_metrics["expectancy"],
                    bollinger_metrics["expectancy"],
                ),
                "uplift_vs_random_baseline": _delta(
                    with_metrics["expectancy"],
                    random_metrics["expectancy"],
                ),
            }
        )
    return _rows_frame(rows) if rows else _empty_uplift()


def _event_subset_metrics(events: pl.DataFrame, trades: pl.DataFrame) -> dict[str, Any]:
    event_rows = events.to_dicts() if not events.is_empty() else []
    event_keys = {_event_key(row) for row in event_rows}
    directional_trade_rows = [
        row
        for row in trades.to_dicts()
        if row.get("signal") in {signal.value for signal in DIRECTIONAL_SIGNALS}
        and _event_key(row) in event_keys
    ]
    metrics = _trade_metrics(directional_trade_rows)
    return {
        "event_count": len(event_rows),
        "directional_trade_count": metrics["directional_trade_count"],
        "no_trade_count": sum(1 for row in event_rows if str(row.get("signal") or "").startswith("NO_TRADE")),
        "win_rate": metrics["win_rate"],
        "expectancy": metrics["expectancy"],
        "profit_factor": metrics["profit_factor"],
        "max_drawdown": metrics["max_drawdown"],
        "average_mae": metrics["average_mae"],
        "average_mfe": metrics["average_mfe"],
        "average_holding_time": metrics["average_holding_time"],
        "loss_count": metrics["loss_count"],
    }


def _trade_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    pnl = [float(row.get("net_pnl_points", row.get("pnl_points", 0.0)) or 0.0) for row in rows]
    wins = [value for value in pnl if value > 0]
    losses = [value for value in pnl if value < 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    return {
        "directional_trade_count": len(rows),
        "win_rate": len(wins) / len(rows) if rows else None,
        "expectancy": sum(pnl) / len(pnl) if pnl else None,
        "profit_factor": gross_win / gross_loss if gross_loss > 0 else None,
        "max_drawdown": _max_drawdown(pnl),
        "average_mae": _average([float(row.get("mae_points") or 0.0) for row in rows]),
        "average_mfe": _average([float(row.get("mfe_points") or 0.0) for row in rows]),
        "average_holding_time": _average([float(row.get("time_in_trade_bars") or 0.0) for row in rows]),
        "loss_count": len(losses),
        "event_count": None,
        "no_trade_count": 0,
    }


def _all_candidates() -> list[_Candidate]:
    return [
        *[
            _Candidate(tag, "rule_tag", (tag,), lambda row, tag=tag: _row_has_tag(row, tag))
            for tag in RULE_TAGS
        ],
        *[
            _Candidate(name, "rule_combination", tags, lambda row, tags=tags: _row_has_all(row, tags))
            for name, tags in RULE_COMBINATIONS
        ],
    ]


def _select_train_rules(
    train_events: pl.DataFrame,
    trades: pl.DataFrame,
    *,
    candidates: list[_Candidate],
    min_sample_size: int,
) -> list[dict[str, Any]]:
    rows = []
    for candidate in candidates:
        with_event_rows = [row for row in train_events.to_dicts() if candidate.predicate(row)]
        without_event_rows = [row for row in train_events.to_dicts() if not candidate.predicate(row)]
        with_events = _rows_frame(with_event_rows) if with_event_rows else _empty_like(train_events)
        without_events = _rows_frame(without_event_rows) if without_event_rows else _empty_like(train_events)
        with_metrics = _event_subset_metrics(with_events, trades)
        without_metrics = _event_subset_metrics(without_events, trades)
        uplift = _delta(with_metrics["expectancy"], without_metrics["expectancy"])
        if (
            with_metrics["directional_trade_count"] >= min_sample_size
            and uplift is not None
            and uplift > 0
        ):
            rows.append(
                {
                    "candidate": candidate,
                    "uplift_vs_no_tag": uplift,
                    "expectancy": with_metrics["expectancy"],
                    "trade_count": with_metrics["directional_trade_count"],
                }
            )
    return sorted(
        rows,
        key=lambda row: (_none_safe(row["uplift_vs_no_tag"]), _none_safe(row["expectancy"])),
        reverse=True,
    )[:5]


def _union_candidate_events(events: pl.DataFrame, candidates: list[_Candidate]) -> pl.DataFrame:
    if events.is_empty() or not candidates:
        return _empty_like(events)
    rows = []
    seen = set()
    for row in events.to_dicts():
        if not any(candidate.predicate(row) for candidate in candidates):
            continue
        key = _event_key(row)
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
    return _rows_frame(rows) if rows else _empty_like(events)


def _timeline_rows(timeline: pl.DataFrame) -> list[dict[str, Any]]:
    if timeline.is_empty():
        return []
    rows = []
    for row in timeline.to_dicts():
        availability = _to_utc_datetime(row.get("availability_timestamp"))
        if availability is None:
            continue
        rows.append(
            {
                "transcript_id": row.get("transcript_id"),
                "availability_timestamp": availability,
                "tags": _split_tags(row.get("detected_rule_tags")),
                "confidence_score": float(row.get("confidence_score") or 0.0),
            }
        )
    return sorted(rows, key=lambda row: row["availability_timestamp"])


def _shuffle_timeline_tags(timeline: pl.DataFrame, rng: random.Random) -> pl.DataFrame:
    if timeline.is_empty() or "detected_rule_tags" not in timeline.columns:
        return timeline
    rows = timeline.to_dicts()
    tags = [row.get("detected_rule_tags") for row in rows]
    rng.shuffle(tags)
    return _rows_frame([{**row, "detected_rule_tags": tags[index]} for index, row in enumerate(rows)])


def _shift_timeline_availability(timeline: pl.DataFrame, rng: random.Random) -> pl.DataFrame:
    if timeline.is_empty() or "availability_timestamp" not in timeline.columns:
        return timeline
    rows = []
    for row in timeline.to_dicts():
        availability = _to_utc_datetime(row.get("availability_timestamp"))
        offset_hours = rng.randint(6, 120)
        rows.append(
            {
                **row,
                "availability_timestamp": availability + timedelta(hours=offset_hours)
                if availability is not None
                else None,
            }
        )
    return _rows_frame(rows)


def _best_uplift_row(frame: pl.DataFrame, *, min_sample_size: int) -> dict[str, Any]:
    if frame.is_empty():
        return {}
    candidates = [
        row
        for row in frame.to_dicts()
        if row.get("uplift_vs_no_tag") is not None
        and int(row.get("directional_trade_count") or 0) >= min_sample_size
    ]
    if not candidates:
        candidates = [
            row
            for row in frame.to_dicts()
            if row.get("uplift_vs_no_tag") is not None
        ]
    return max(
        candidates,
        key=lambda row: (
            _none_safe(row.get("uplift_vs_no_tag")),
            int(row.get("directional_trade_count") or 0),
        ),
        default={},
    )


def _keep_kill_recommendation(
    *,
    rule_id: str,
    rule_type: str,
    trade_count: int,
    uplift: Any,
    walk_forward_pass: bool,
    placebo_passed: bool,
    min_sample_size: int,
) -> tuple[str, str]:
    value = _none_safe(uplift)
    if trade_count < min_sample_size:
        return "UNVALIDATED", "sample too small for uplift decision"
    if value < 0:
        return "KILL", "negative uplift with enough sample"
    if walk_forward_pass and placebo_passed and value > 0:
        return "KEEP_AS_FILTER", "positive uplift survived walk-forward and placebo checks"
    if value > 0 and not walk_forward_pass:
        return "QUARANTINE", "in-sample uplift did not survive walk-forward selection"
    if rule_type == "rule_tag" and rule_id in LOGICAL_CONTEXT_TAGS:
        return "KEEP_AS_CONTEXT", "logically useful context but not predictive as a filter"
    return "UNVALIDATED", "no validated uplift"


def _walk_forward_pass_ids(walk_forward: pl.DataFrame) -> set[str]:
    if walk_forward.is_empty():
        return set()
    result = set()
    for row in walk_forward.filter(pl.col("pass_fail") == "PASS").to_dicts():
        result.update(part for part in str(row.get("selected_rules") or "").split(",") if part)
    return result


def _placebo_passed(placebo: pl.DataFrame) -> bool:
    if placebo.is_empty():
        return False
    required = placebo.filter(pl.col("placebo_type").is_in(["SHUFFLED_TAGS", "SHIFTED_AVAILABILITY"]))
    if required.is_empty():
        return False
    return all(bool(row.get("placebo_passed")) for row in required.to_dicts())


def _price_timestamps(feature_table: pl.DataFrame, conditioned_events: pl.DataFrame) -> list[datetime]:
    source = feature_table if not feature_table.is_empty() and "timestamp" in feature_table.columns else conditioned_events
    column = "timestamp" if "timestamp" in source.columns else "event_timestamp"
    values = [_to_utc_datetime(value) for value in source.get_column(column).to_list()]
    return sorted(value for value in values if value is not None)


def _time_slice_events(events: pl.DataFrame, start: datetime, end: datetime) -> pl.DataFrame:
    rows = [
        row
        for row in events.to_dicts()
        if (timestamp := _to_utc_datetime(row.get("event_timestamp"))) is not None
        and start <= timestamp <= end
    ]
    return _rows_frame(rows) if rows else _empty_like(events)


def _row_has_tag(row: dict[str, Any], tag: str) -> bool:
    return tag in _split_tags(row.get("active_transcript_rule_tags"))


def _row_has_all(row: dict[str, Any], tags: tuple[str, ...]) -> bool:
    active = set(_split_tags(row.get("active_transcript_rule_tags")))
    for tag in tags:
        if tag == "middle_1sd":
            if not bool(row.get("middle_1sd")):
                return False
            continue
        if tag not in active:
            return False
    return True


def _is_middle_1sd(row: dict[str, Any]) -> bool:
    zone = str(row.get("sigma_zone") or "").lower()
    if zone in {"inside_1sd", "middle_1sd", "inside middle 1sd"}:
        return True
    sigma = row.get("sigma_position")
    try:
        return abs(float(sigma)) < 1.0
    except (TypeError, ValueError):
        return False


def _event_key(row: dict[str, Any]) -> str:
    timestamp = _to_utc_datetime(row.get("event_timestamp"))
    timestamp_value = timestamp.isoformat() if timestamp else str(row.get("event_timestamp") or "")
    return f"{timestamp_value}::{str(row.get('signal') or '')}"


def _split_tags(value: Any) -> list[str]:
    if value is None:
        return []
    return [tag for tag in str(value).split("|") if tag]


def _to_utc_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value)
        if not text or text.lower() == "none":
            return None
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        if len(text) >= 5 and text[-5] in {"+", "-"} and text[-2] != ":":
            text = f"{text[:-2]}:{text[-2:]}"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _average(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _delta(left: Any, right: Any) -> float | None:
    if left is None or right is None:
        return None
    return _none_safe(left) - _none_safe(right)


def _none_safe(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _max_drawdown(pnl: list[float]) -> float:
    peak = 0.0
    running = 0.0
    drawdown = 0.0
    for value in pnl:
        running += value
        peak = max(peak, running)
        drawdown = min(drawdown, running - peak)
    return drawdown


def _bad_trade_rate(metrics: dict[str, Any]) -> float:
    count = int(metrics.get("directional_trade_count") or 0)
    if count == 0:
        return 0.0
    return int(metrics.get("loss_count") or 0) / count


def _top_uplift_rows(frame: pl.DataFrame) -> list[dict[str, Any]]:
    if frame.is_empty():
        return []
    return sorted(
        frame.to_dicts(),
        key=lambda row: _none_safe(row.get("uplift_vs_no_tag")),
        reverse=True,
    )[:20]


def _report_columns(frame: pl.DataFrame) -> pl.DataFrame:
    if frame.is_empty():
        return frame
    columns = [
        "rule_id",
        "rule_type",
        "event_count",
        "directional_trade_count",
        "no_trade_count",
        "expectancy",
        "profit_factor",
        "sample_size_warning",
        "uplift_vs_no_tag",
        "uplift_vs_base_score",
        "uplift_vs_bollinger_baseline",
        "uplift_vs_random_baseline",
    ]
    return frame.select([column for column in columns if column in frame.columns])


def _frame_markdown(frame: pl.DataFrame) -> str:
    if frame.is_empty():
        return "_No rows._"
    rows = ["| " + " | ".join(frame.columns) + " |", "|" + "|".join(["---"] * len(frame.columns)) + "|"]
    for raw in frame.head(25).to_dicts():
        rows.append("| " + " | ".join(str(raw.get(column, "")) for column in frame.columns) + " |")
    return "\n".join(rows)


def _empty_like(frame: pl.DataFrame) -> pl.DataFrame:
    return frame.head(0) if not frame.is_empty() else pl.DataFrame()


def _rows_frame(rows: list[dict[str, Any]]) -> pl.DataFrame:
    return pl.DataFrame(rows, infer_schema_length=None)


def _empty_conditioned_events() -> pl.DataFrame:
    schema = {
        "event_timestamp": pl.Datetime(time_zone="UTC"),
        "source_bar_timestamp": pl.Datetime(time_zone="UTC"),
        "signal": pl.String,
        "active_transcript_rule_tags": pl.String,
        "active_rule_count": pl.Int64,
        "latest_transcript_age_hours": pl.Float64,
        "transcript_confidence_max": pl.Float64,
        "transcript_confidence_mean": pl.Float64,
        "middle_1sd": pl.Boolean,
        "no_trade_row_retained": pl.Boolean,
    }
    for column in FLAG_RULES.values():
        schema[column] = pl.Boolean
    return pl.DataFrame(schema=schema)


def _empty_uplift() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "rule_id": pl.String,
            "rule_type": pl.String,
            "required_tags": pl.String,
            "event_count": pl.Int64,
            "directional_trade_count": pl.Int64,
            "no_trade_count": pl.Int64,
            "win_rate": pl.Float64,
            "expectancy": pl.Float64,
            "profit_factor": pl.Float64,
            "max_drawdown": pl.Float64,
            "average_mae": pl.Float64,
            "average_mfe": pl.Float64,
            "average_holding_time": pl.Float64,
            "loss_count": pl.Int64,
            "without_tag_event_count": pl.Int64,
            "without_tag_directional_trade_count": pl.Int64,
            "without_tag_expectancy": pl.Float64,
            "base_score_expectancy": pl.Float64,
            "bollinger_baseline_expectancy": pl.Float64,
            "random_baseline_expectancy": pl.Float64,
            "sample_size_warning": pl.Boolean,
            "uplift_vs_no_tag": pl.Float64,
            "uplift_vs_base_score": pl.Float64,
            "uplift_vs_bollinger_baseline": pl.Float64,
            "uplift_vs_random_baseline": pl.Float64,
        }
    )


def _empty_walk_forward() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "split_id": pl.Int64,
            "train_start": pl.Datetime(time_zone="UTC"),
            "train_end": pl.Datetime(time_zone="UTC"),
            "test_start": pl.Datetime(time_zone="UTC"),
            "test_end": pl.Datetime(time_zone="UTC"),
            "selected_rules": pl.String,
            "selected_rule_count": pl.Int64,
            "train_best_uplift": pl.Float64,
            "test_event_count": pl.Int64,
            "test_directional_trade_count": pl.Int64,
            "test_no_trade_count": pl.Int64,
            "test_expectancy": pl.Float64,
            "test_profit_factor": pl.Float64,
            "test_max_drawdown": pl.Float64,
            "test_base_expectancy": pl.Float64,
            "test_uplift_vs_base_score": pl.Float64,
            "test_bad_trade_rate": pl.Float64,
            "test_base_bad_trade_rate": pl.Float64,
            "bad_trade_rate_delta": pl.Float64,
            "pass_fail": pl.String,
            "no_lookahead": pl.Boolean,
        }
    )


def _empty_keep_kill() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "rule_id": pl.String,
            "rule_type": pl.String,
            "event_count": pl.Int64,
            "directional_trade_count": pl.Int64,
            "no_trade_count": pl.Int64,
            "expectancy": pl.Float64,
            "profit_factor": pl.Float64,
            "uplift_vs_no_tag": pl.Float64,
            "walk_forward_pass": pl.Boolean,
            "placebo_passed": pl.Boolean,
            "recommendation": pl.String,
            "reason": pl.String,
        }
    )


def _write_bar_svg(path: Path, *, title: str, labels: list[str], values: list[float]) -> None:
    width = 900
    maximum = max(values + [0.0])
    minimum = min(values + [0.0])
    span = maximum - minimum or 1.0
    count = max(len(values), 1)
    bar_width = max((width - 90) / count * 0.72, 4)
    body = [
        '<line x1="45" y1="285" x2="870" y2="285" stroke="#94a3b8" stroke-width="1" />',
        '<line x1="45" y1="45" x2="45" y2="285" stroke="#94a3b8" stroke-width="1" />',
    ]
    for index, value in enumerate(values):
        x = 55 + index * ((width - 100) / count)
        y = 285 - ((value - minimum) / span) * 225
        base_y = 285 - ((0.0 - minimum) / span) * 225
        color = "#0f766e" if value >= 0 else "#b91c1c"
        body.append(
            f'<rect x="{x:.1f}" y="{min(y, base_y):.1f}" width="{bar_width:.1f}" '
            f'height="{max(abs(base_y - y), 1.0):.1f}" fill="{color}" />'
        )
        body.append(
            f'<text x="{x:.1f}" y="310" font-size="9" font-family="Arial" '
            f'transform="rotate(35 {x:.1f},310)">{labels[index][:22]}</text>'
        )
    path.write_text(_svg(title, "\n".join(body)), encoding="utf-8")


def _svg(title: str, body: str) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="340" '
        'viewBox="0 0 900 340">'
        '<rect width="900" height="340" fill="#ffffff" />'
        f'<text x="40" y="30" font-size="18" font-family="Arial">{title}</text>'
        f"{body}</svg>"
    )
