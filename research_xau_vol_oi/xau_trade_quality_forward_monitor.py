"""Forward stability monitor for the frozen XAU Trade Quality Score.

The monitor freezes score v1, joins frozen score rows to later forward outcome
rows when present, and reports whether bucket/component ordering survives
without changing score weights, thresholds, or evidence rules.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

import polars as pl

from research_xau_vol_oi.xau_trade_quality_score import (
    COMPONENT_DELTAS,
    COMPONENT_ORDER,
    SCORE_BUCKETS,
)


SCORE_VERSION = "xau_trade_quality_score_v1"
BUCKET_THRESHOLDS = {
    "BLOCK": "hard block active or score <= 35",
    "WATCH_ONLY": "36 <= score < 60",
    "ALLOW_RESEARCH": "60 <= score < 80",
    "HIGH_QUALITY_RESEARCH": "score >= 80",
}
HARD_BLOCK_COMPONENTS = (
    "no_trade_middle_range_component",
    "open_distance_component",
    "fee_spread_hurdle_component",
    "data_quality_component",
    "stale_data_component",
)
FINAL_RECOMMENDATIONS = (
    "SCORE_READY_FOR_FORWARD_MONITORING",
    "SCORE_BUCKETS_STABLE_PRELIMINARY",
    "SCORE_NOT_STABLE_YET",
    "USE_AS_WATCHLIST_FILTER_ONLY",
    "NEEDS_MORE_FORWARD_DATA",
    "NOT_READY_FOR_MONEY",
)
RESEARCH_WARNING = (
    "Research-only forward monitor. Score weights and bucket thresholds are "
    "frozen. No live trading, paper trading, broker integration, score tuning, "
    "threshold optimization, or money-readiness claim is included."
)
PILOT_WARNING = "CME OI/IV remains PILOT_ONLY; guru context remains filter/playbook context."
FORBIDDEN_REPORT_PHRASES = (
    " buy ",
    " sell ",
    "profitable",
    "profitability",
    "guaranteed edge",
    "predicts price",
    "safe to trade",
    "live ready",
    "paper ready",
    "validated money edge",
)


@dataclass(frozen=True)
class FrozenScoreConfig:
    """Frozen v1 score configuration metadata."""

    version: str
    config_hash: str
    yaml_path: Path
    hash_path: Path
    markdown_path: Path
    overwritten: bool


@dataclass(frozen=True)
class XauTradeQualityForwardMonitorResult:
    """Frames and labels emitted by the forward stability monitor."""

    frozen_config: FrozenScoreConfig
    forward_monitor: pl.DataFrame
    bucket_stability: pl.DataFrame
    component_stability: pl.DataFrame
    daily_watchlist: pl.DataFrame
    final_recommendation: str
    high_score_forward_outperformed_low_score: bool
    paths: dict[str, Path]


def run_xau_trade_quality_forward_monitor(
    *,
    output_dir: str | Path = "outputs",
    force_freeze: bool = False,
    write_outputs: bool = True,
    frozen_at: datetime | None = None,
) -> XauTradeQualityForwardMonitorResult:
    """Run the frozen score monitor and optionally write artifacts."""

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    paths = _output_paths(output_root)
    inputs = _load_inputs(paths)
    frozen = freeze_score_config(
        output_dir=output_root,
        force=force_freeze,
        frozen_at=frozen_at,
        write_outputs=write_outputs,
    )
    monitor = build_forward_monitor(
        score_rows=inputs["score_rows"],
        forward_journal=inputs["forward_journal"],
        promoted_outcomes=inputs["promoted_outcomes"],
    )
    bucket = build_bucket_stability(
        replay_backtest=inputs["score_backtest"],
        forward_monitor=monitor,
    )
    component = build_component_stability(
        score_ablation=inputs["score_ablation"],
        forward_monitor=monitor,
    )
    daily = build_daily_watchlist(
        score_rows=inputs["score_rows"],
        price_frames=inputs["price_frames"],
    )
    high_outperformed = high_score_outperformed_low_score_forward(bucket)
    final = choose_final_recommendation(
        bucket_stability=bucket,
        forward_monitor=monitor,
        governance=inputs["forward_governance"],
        high_score_outperformed=high_outperformed,
    )
    result = XauTradeQualityForwardMonitorResult(
        frozen_config=frozen,
        forward_monitor=monitor,
        bucket_stability=bucket,
        component_stability=component,
        daily_watchlist=daily,
        final_recommendation=final,
        high_score_forward_outperformed_low_score=high_outperformed,
        paths=paths,
    )
    if write_outputs:
        write_forward_monitor_outputs(result)
    return result


def freeze_score_config(
    *,
    output_dir: str | Path = "outputs",
    force: bool = False,
    frozen_at: datetime | None = None,
    write_outputs: bool = True,
) -> FrozenScoreConfig:
    """Write the frozen score v1 config unless it already exists."""

    output_root = Path(output_dir)
    paths = _output_paths(output_root)
    payload = frozen_score_payload()
    config_hash = stable_score_config_hash(payload)
    timestamp = _ensure_utc(frozen_at or datetime.now(UTC)).isoformat().replace("+00:00", "Z")
    yaml_text = _frozen_yaml(payload, config_hash=config_hash, frozen_timestamp=timestamp)
    markdown_text = _safe_report_text(_frozen_markdown(payload, config_hash=config_hash, frozen_timestamp=timestamp))
    yaml_exists = paths["score_config_yaml"].exists()
    overwritten = bool(force and yaml_exists)
    if write_outputs:
        output_root.mkdir(parents=True, exist_ok=True)
        if force or not yaml_exists:
            paths["score_config_yaml"].write_text(yaml_text, encoding="utf-8")
            paths["score_config_md"].write_text(markdown_text, encoding="utf-8")
        if force or not paths["score_config_hash"].exists():
            paths["score_config_hash"].write_text(f"{config_hash}\n", encoding="utf-8")
    return FrozenScoreConfig(
        version=SCORE_VERSION,
        config_hash=config_hash,
        yaml_path=paths["score_config_yaml"],
        hash_path=paths["score_config_hash"],
        markdown_path=paths["score_config_md"],
        overwritten=overwritten,
    )


def frozen_score_payload() -> dict[str, Any]:
    """Return the canonical v1 payload used for stable hashing."""

    return {
        "version": SCORE_VERSION,
        "score_components": [
            {
                "component_name": component,
                "fixed_score_weight": COMPONENT_DELTAS[component],
            }
            for component in COMPONENT_ORDER
        ],
        "bucket_thresholds": BUCKET_THRESHOLDS,
        "hard_block_components": list(HARD_BLOCK_COMPONENTS),
        "evidence_source": (
            "outputs/xau_trade_quality_score.csv; "
            "outputs/xau_trade_quality_score_backtest.csv; "
            "outputs/xau_trade_quality_score_ablation.csv"
        ),
        "tuning_allowed": False,
        "threshold_optimization_allowed": False,
        "validated": False,
        "warnings": [
            "Research-only score freeze.",
            "No score weights may be changed by the monitor.",
            "No thresholds may be tuned from replay or forward rows.",
            "CME OI/IV remains PILOT_ONLY.",
            "Guru context cannot create a standalone signal.",
            "Money-readiness remains NOT_READY_FOR_MONEY.",
        ],
    }


def stable_score_config_hash(payload: dict[str, Any] | None = None) -> str:
    """Return the stable SHA-256 hash for the frozen score payload."""

    canonical = json.dumps(payload or frozen_score_payload(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_forward_monitor(
    *,
    score_rows: pl.DataFrame,
    forward_journal: pl.DataFrame = pl.DataFrame(),
    promoted_outcomes: pl.DataFrame = pl.DataFrame(),
) -> pl.DataFrame:
    """Join forward outcome rows to frozen score rows without recomputing scores."""

    events = _forward_events(forward_journal, promoted_outcomes)
    if events.is_empty():
        return pl.DataFrame(schema=_forward_monitor_schema())
    score_index = _score_index(score_rows)
    rows = []
    for event in events.to_dicts():
        timestamp = _parse_datetime(event.get("timestamp"))
        timeframe = _timeframe_for_event(event)
        score = _nearest_score(score_index, timeframe=timeframe, timestamp=timestamp)
        bucket = _score_bucket(score)
        outcome_return = _float_or_none(event.get("outcome_return"))
        outcome_status = _text(event.get("outcome_status")) or ("RESOLVED" if outcome_return is not None else "PENDING")
        filter_helped = bucket == "BLOCK" and outcome_return is not None and outcome_return <= 0
        false_block = bucket == "BLOCK" and outcome_return is not None and outcome_return > 0
        active_components = _active_components(score)
        rows.append(
            {
                "timestamp": timestamp,
                "session_date": _text(event.get("session_date")),
                "timeframe": timeframe,
                "score": _int(score.get("trade_quality_score")) if score else None,
                "score_bucket": bucket,
                "active_components": active_components,
                "blocked_reasons": _text(score.get("blocked_reasons")) if score else "MISSING_SCORE_ROW",
                "data_quality": _data_quality_label(score),
                "outcome_status": outcome_status if outcome_status in {"PENDING", "RESOLVED"} else "PENDING",
                "outcome_return": outcome_return,
                "mfe": _float_or_none(event.get("mfe")),
                "mae": _float_or_none(event.get("mae")),
                "filter_helped": filter_helped,
                "false_block": false_block,
            }
        )
    return _frame(rows, _forward_monitor_schema()).sort(["session_date", "timestamp", "timeframe"])


def build_bucket_stability(
    *,
    replay_backtest: pl.DataFrame,
    forward_monitor: pl.DataFrame,
) -> pl.DataFrame:
    """Compare replay and forward bucket behavior in fixed bucket order."""

    rows = []
    for bucket in SCORE_BUCKETS:
        replay = _replay_bucket_row(replay_backtest, bucket)
        forward = _forward_bucket_metrics(forward_monitor, bucket)
        rows.append(
            {
                "score_bucket": bucket,
                "bucket_order": _bucket_order(bucket),
                "replay_event_count": replay.get("event_count"),
                "replay_resolved_count": replay.get("trade_count"),
                "replay_average_return": replay.get("average_return"),
                "replay_support_rate": replay.get("support_rate"),
                "replay_failure_rate": replay.get("failure_rate"),
                "replay_average_mfe": replay.get("average_mfe"),
                "replay_average_mae": replay.get("average_mae"),
                "replay_false_block_rate": replay.get("false_block_rate"),
                "forward_event_count": forward["event_count"],
                "forward_resolved_count": forward["resolved_count"],
                "forward_average_return": forward["average_return"],
                "forward_support_rate": forward["support_rate"],
                "forward_failure_rate": forward["failure_rate"],
                "forward_average_mfe": forward["average_mfe"],
                "forward_average_mae": forward["average_mae"],
                "forward_false_block_rate": forward["false_block_rate"],
                "sample_size_warning": forward["resolved_count"] < 30,
                "bucket_order_pass": False,
            }
        )
    pass_value = bucket_order_pass(_frame(rows, _bucket_stability_schema()), prefix="forward")
    return _frame([{**row, "bucket_order_pass": pass_value} for row in rows], _bucket_stability_schema())


def bucket_order_pass(bucket_stability: pl.DataFrame, *, prefix: str = "forward") -> bool:
    """Return true when high-score bucket returns beat low-score bucket returns."""

    high = _bucket_group_average(
        bucket_stability,
        buckets={"ALLOW_RESEARCH", "HIGH_QUALITY_RESEARCH"},
        value_col=f"{prefix}_average_return",
        weight_col=f"{prefix}_resolved_count",
    )
    low = _bucket_group_average(
        bucket_stability,
        buckets={"BLOCK", "WATCH_ONLY"},
        value_col=f"{prefix}_average_return",
        weight_col=f"{prefix}_resolved_count",
    )
    return high is not None and low is not None and high > low


def high_score_outperformed_low_score_forward(bucket_stability: pl.DataFrame) -> bool:
    """Return the forward high-vs-low ordering result."""

    return bucket_order_pass(bucket_stability, prefix="forward")


def build_component_stability(
    *,
    score_ablation: pl.DataFrame,
    forward_monitor: pl.DataFrame,
) -> pl.DataFrame:
    """Evaluate whether each component keeps its expected forward direction."""

    rows = []
    for component in COMPONENT_ORDER:
        active_rows = _rows_with_component(forward_monitor, component)
        inactive_rows = _rows_without_component(forward_monitor, component)
        active_avg = _mean_column(active_rows, "outcome_return")
        inactive_avg = _mean_column(inactive_rows, "outcome_return")
        forward_effect = (
            active_avg - inactive_avg
            if active_avg is not None and inactive_avg is not None
            else None
        )
        replay_effect = _component_replay_effect(score_ablation, component)
        stable = _stable_component_direction(component, forward_effect)
        evidence_count = int(active_rows.filter(pl.col("outcome_status") == "RESOLVED").height) if not active_rows.is_empty() else 0
        rows.append(
            {
                "component_name": component,
                "replay_effect": replay_effect,
                "forward_effect": forward_effect,
                "stable_direction": stable,
                "evidence_count": evidence_count,
                "recommendation": _component_recommendation(
                    component,
                    stable_direction=stable,
                    evidence_count=evidence_count,
                ),
            }
        )
    return _frame(rows, _component_stability_schema())


def build_daily_watchlist(
    *,
    score_rows: pl.DataFrame,
    price_frames: dict[str, pl.DataFrame],
) -> pl.DataFrame:
    """Build one latest-session watchlist row from the frozen score output."""

    if score_rows.is_empty():
        return pl.DataFrame(schema=_daily_watchlist_schema())
    scores = _normalize_score_rows(score_rows)
    if scores.is_empty():
        return pl.DataFrame(schema=_daily_watchlist_schema())
    latest = scores.sort("timestamp").tail(1).row(0, named=True)
    timeframe = _text(latest.get("timeframe"))
    latest_price = _latest_price(price_frames, timeframe=timeframe, timestamp=latest.get("timestamp"))
    score_bucket = _score_bucket(latest)
    action = _journal_action(latest)
    rows = [
        {
            "session_date": _date_text(latest.get("timestamp")),
            "timeframe": timeframe,
            "latest_price": latest_price,
            "latest_score": _int(latest.get("trade_quality_score")),
            "score_bucket": score_bucket,
            "active_positive_components": _text(latest.get("active_positive_components")),
            "active_negative_components": _text(latest.get("active_negative_components")),
            "blocked_reasons": _text(latest.get("blocked_reasons")),
            "watch_reasons": _text(latest.get("watch_reasons")),
            "journal_action": action,
            "plain_english_summary": _daily_summary(latest, action=action, latest_price=latest_price),
        }
    ]
    return _frame(rows, _daily_watchlist_schema())


def choose_final_recommendation(
    *,
    bucket_stability: pl.DataFrame,
    forward_monitor: pl.DataFrame,
    governance: pl.DataFrame,
    high_score_outperformed: bool,
) -> str:
    """Choose a conservative monitor recommendation."""

    if bucket_stability.is_empty():
        return "NEEDS_MORE_FORWARD_DATA"
    resolved_count = (
        int(forward_monitor.filter(pl.col("outcome_status") == "RESOLVED").height)
        if not forward_monitor.is_empty()
        else 0
    )
    independent_count = _max_int(governance, "independent_event_count")
    if resolved_count == 0:
        return "SCORE_READY_FOR_FORWARD_MONITORING"
    if independent_count < 30:
        return "SCORE_READY_FOR_FORWARD_MONITORING"
    if high_score_outperformed:
        return "SCORE_BUCKETS_STABLE_PRELIMINARY"
    return "SCORE_NOT_STABLE_YET"


def write_forward_monitor_outputs(result: XauTradeQualityForwardMonitorResult) -> None:
    """Write monitor CSV and Markdown artifacts."""

    result.forward_monitor.write_csv(result.paths["forward_monitor_csv"])
    result.bucket_stability.write_csv(result.paths["bucket_stability_csv"])
    result.component_stability.write_csv(result.paths["component_stability_csv"])
    result.daily_watchlist.write_csv(result.paths["daily_watchlist_csv"])
    result.paths["forward_monitor_md"].write_text(
        _safe_report_text(_forward_monitor_markdown(result)),
        encoding="utf-8",
    )
    result.paths["bucket_stability_md"].write_text(
        _safe_report_text(_bucket_stability_markdown(result)),
        encoding="utf-8",
    )
    result.paths["component_stability_md"].write_text(
        _safe_report_text(_component_stability_markdown(result)),
        encoding="utf-8",
    )
    result.paths["daily_watchlist_md"].write_text(
        _safe_report_text(_daily_watchlist_markdown(result)),
        encoding="utf-8",
    )


def xau_trade_quality_forward_monitor_report_lines(
    result: XauTradeQualityForwardMonitorResult | None,
) -> list[str]:
    """Return research_report.md lines for the forward monitor."""

    if result is None:
        return [
            "## Frozen XAU Trade Quality Score v1",
            "",
            "XAU Trade Quality Score Forward Stability Monitor was not run.",
        ]
    return [
        "## Frozen XAU Trade Quality Score v1",
        "",
        RESEARCH_WARNING,
        "",
        f"- Score version: `{result.frozen_config.version}`",
        f"- Score hash: `{result.frozen_config.config_hash}`",
        "- Config path: `outputs/xau_trade_quality_score_v1.yaml`",
        f"- {PILOT_WARNING}",
        "",
        "## Forward Bucket Stability",
        "",
        _frame_markdown(result.bucket_stability),
        "",
        "## Component Stability",
        "",
        _frame_markdown(result.component_stability),
        "",
        "## Daily Watchlist",
        "",
        _frame_markdown(result.daily_watchlist),
        "",
        "## Current Score Validation Status",
        "",
        f"- Final recommendation: `{result.final_recommendation}`",
        f"- High-score buckets beat low-score buckets in forward rows: `{result.high_score_forward_outperformed_low_score}`",
        "- Watchlist guardrail: `USE_AS_WATCHLIST_FILTER_ONLY`",
        "- Money-readiness guardrail: `NOT_READY_FOR_MONEY`",
    ]


def report_text_is_safe(text: str) -> bool:
    """Return true when report text avoids forbidden claim/instruction phrases."""

    lowered = f" {text.lower()} "
    return not any(phrase in lowered for phrase in FORBIDDEN_REPORT_PHRASES)


def _load_inputs(paths: dict[str, Path]) -> dict[str, Any]:
    return {
        "score_rows": _read_csv(paths["score_csv"]),
        "score_backtest": _read_csv(paths["score_backtest"]),
        "score_ablation": _read_csv(paths["score_ablation"]),
        "forward_journal": _read_csv(paths["forward_journal"]),
        "promoted_outcomes": _read_csv(paths["promoted_outcomes"]),
        "forward_governance": _read_csv(paths["forward_governance"]),
        "forward_scorecard": _read_csv(paths["forward_scorecard"]),
        "price_frames": {
            timeframe: _read_parquet(paths[f"price_{timeframe}"])
            for timeframe in ("15m", "1h", "4h")
        },
        "current_week": _read_csv(paths["current_week"]),
        "same_day_filter": _read_csv(paths["same_day_filter"]),
        "same_day_market_map": _read_csv(paths["same_day_market_map"]),
    }


def _forward_events(forward_journal: pl.DataFrame, promoted_outcomes: pl.DataFrame) -> pl.DataFrame:
    source = forward_journal if not forward_journal.is_empty() else promoted_outcomes
    if source.is_empty():
        return pl.DataFrame(schema=_forward_event_schema())
    rows = []
    for raw in source.to_dicts():
        timestamp = (
            raw.get("timestamp")
            or raw.get("observation_timestamp")
            or raw.get("window_start")
        )
        session_date = raw.get("session_date") or raw.get("trade_date")
        outcome_return = raw.get("outcome_return") if "outcome_return" in raw else raw.get("close_return")
        outcome_status = raw.get("outcome_status")
        if _float_or_none(outcome_return) is not None:
            outcome_status = "RESOLVED"
        rows.append(
            {
                "timestamp": timestamp,
                "session_date": session_date,
                "timeframe": raw.get("timeframe") or raw.get("source_interval") or raw.get("outcome_window"),
                "outcome_status": outcome_status or "PENDING",
                "outcome_return": outcome_return,
                "mfe": raw.get("mfe"),
                "mae": raw.get("mae"),
            }
        )
    return _frame(rows, _forward_event_schema())


def _score_index(score_rows: pl.DataFrame) -> dict[str, list[dict[str, Any]]]:
    rows = _normalize_score_rows(score_rows)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows.to_dicts():
        grouped.setdefault(_text(row.get("timeframe")), []).append(row)
    for timeframe, items in grouped.items():
        grouped[timeframe] = sorted(items, key=lambda item: item["timestamp"])
    return grouped


def _normalize_score_rows(score_rows: pl.DataFrame) -> pl.DataFrame:
    if score_rows.is_empty() or "timestamp" not in score_rows.columns:
        return pl.DataFrame(schema=_score_schema())
    rows = []
    for raw in score_rows.to_dicts():
        parsed = _parse_datetime(raw.get("timestamp"))
        if parsed is None:
            continue
        rows.append({**raw, "timestamp": parsed})
    return _frame(rows, _score_schema())


def _nearest_score(
    score_index: dict[str, list[dict[str, Any]]],
    *,
    timeframe: str,
    timestamp: datetime | None,
) -> dict[str, Any]:
    if timestamp is None:
        return {}
    candidates = score_index.get(timeframe)
    if not candidates and timeframe == "30m":
        candidates = score_index.get("15m")
    if not candidates and timeframe in {"session_close", "next_day"}:
        candidates = score_index.get("1h")
    if not candidates:
        candidates = score_index.get("15m") or score_index.get("1h") or []
    selected: dict[str, Any] = {}
    for row in candidates:
        row_timestamp = row.get("timestamp")
        if isinstance(row_timestamp, datetime) and row_timestamp <= timestamp:
            selected = row
        elif selected:
            break
    return selected


def _score_bucket(score: dict[str, Any]) -> str:
    bucket = _text(score.get("score_bucket")) if score else ""
    return bucket if bucket in SCORE_BUCKETS else "WATCH_ONLY"


def _timeframe_for_event(event: dict[str, Any]) -> str:
    timeframe = _text(event.get("timeframe"))
    if timeframe in {"30m", "15m", "1h", "4h"}:
        return timeframe
    if timeframe in {"session_close", "next_day"}:
        return "1h"
    return "15m"


def _active_components(score: dict[str, Any]) -> str:
    if not score:
        return ""
    parts = []
    for column in ("active_positive_components", "active_negative_components"):
        for value in _text(score.get(column)).split(";"):
            if value and value not in parts:
                parts.append(value)
    return ";".join(parts)


def _data_quality_label(score: dict[str, Any]) -> str:
    if not score:
        return "MISSING_SCORE"
    notes = _text(score.get("data_quality_notes"))
    if notes:
        return notes
    if "data_quality_component" in _active_components(score):
        return "OK"
    return "CHECK"


def _forward_bucket_metrics(frame: pl.DataFrame, bucket: str) -> dict[str, Any]:
    if frame.is_empty():
        return _empty_forward_bucket_metrics()
    rows = frame.filter(pl.col("score_bucket") == bucket)
    resolved = rows.filter(pl.col("outcome_status") == "RESOLVED") if not rows.is_empty() else rows
    returns = _column_values(resolved, "outcome_return")
    support = [value for value in returns if value > 0]
    failure = [value for value in returns if value <= 0]
    false_block_count = int(resolved.filter(pl.col("false_block")).height) if not resolved.is_empty() else 0
    return {
        "event_count": rows.height,
        "resolved_count": resolved.height,
        "average_return": _average(returns),
        "support_rate": len(support) / len(returns) if returns else None,
        "failure_rate": len(failure) / len(returns) if returns else None,
        "average_mfe": _mean_column(resolved, "mfe"),
        "average_mae": _mean_column(resolved, "mae"),
        "false_block_rate": false_block_count / resolved.height if resolved.height else None,
    }


def _empty_forward_bucket_metrics() -> dict[str, Any]:
    return {
        "event_count": 0,
        "resolved_count": 0,
        "average_return": None,
        "support_rate": None,
        "failure_rate": None,
        "average_mfe": None,
        "average_mae": None,
        "false_block_rate": None,
    }


def _replay_bucket_row(frame: pl.DataFrame, bucket: str) -> dict[str, Any]:
    if frame.is_empty() or "score_bucket" not in frame.columns:
        return {}
    rows = frame.filter(pl.col("score_bucket") == bucket)
    return rows.row(0, named=True) if not rows.is_empty() else {}


def _bucket_group_average(
    frame: pl.DataFrame,
    *,
    buckets: set[str],
    value_col: str,
    weight_col: str,
) -> float | None:
    if frame.is_empty() or value_col not in frame.columns or weight_col not in frame.columns:
        return None
    selected = frame.filter(pl.col("score_bucket").is_in(sorted(buckets)))
    numerator = 0.0
    denominator = 0.0
    for row in selected.to_dicts():
        value = _float_or_none(row.get(value_col))
        weight = _float_or_none(row.get(weight_col)) or 0.0
        if value is not None and weight > 0:
            numerator += value * weight
            denominator += weight
    return numerator / denominator if denominator else None


def _rows_with_component(frame: pl.DataFrame, component: str) -> pl.DataFrame:
    if frame.is_empty() or "active_components" not in frame.columns:
        return pl.DataFrame(schema=_forward_monitor_schema())
    return frame.filter(pl.col("active_components").str.contains(component, literal=True))


def _rows_without_component(frame: pl.DataFrame, component: str) -> pl.DataFrame:
    if frame.is_empty() or "active_components" not in frame.columns:
        return pl.DataFrame(schema=_forward_monitor_schema())
    return frame.filter(~pl.col("active_components").str.contains(component, literal=True))


def _component_replay_effect(score_ablation: pl.DataFrame, component: str) -> str:
    ablation = _ablation_name_for_component(component)
    if not ablation or score_ablation.is_empty() or "ablation" not in score_ablation.columns:
        return "REPLAY_CONTEXT_ONLY"
    rows = score_ablation.filter(pl.col("ablation") == ablation)
    if rows.is_empty():
        return "REPLAY_CONTEXT_ONLY"
    change = _float_or_none(rows.row(0, named=True).get("expectancy_change"))
    if change is None:
        return "NEEDS_MORE_FORWARD_DATA"
    if change < 0:
        return "REMOVAL_WEAKENED_SCORE"
    if change > 0:
        return "REMOVAL_IMPROVED_REPLAY"
    return "NEUTRAL_REPLAY"


def _ablation_name_for_component(component: str) -> str:
    mapping = {
        "acceptance_breakout_component": "without_acceptance_breakout",
        "no_trade_middle_range_component": "without_no_trade_middle_range",
        "open_distance_component": "without_open_distance",
        "fee_spread_hurdle_component": "without_fee_spread_hurdle",
        "cme_wall_context_component": "without_cme_wall",
        "cme_iv_range_component": "without_cme_wall",
        "guru_filter_component": "without_guru_filter",
        "data_quality_component": "without_data_quality",
    }
    return mapping.get(component, "")


def _stable_component_direction(component: str, forward_effect: float | None) -> bool:
    if forward_effect is None:
        return False
    weight = COMPONENT_DELTAS.get(component, 0)
    if weight > 0:
        return forward_effect >= 0
    if weight < 0:
        return forward_effect <= 0
    return False


def _component_recommendation(
    component: str,
    *,
    stable_direction: bool,
    evidence_count: int,
) -> str:
    if evidence_count < 10:
        return "NEEDS_MORE_FORWARD_DATA"
    if component.startswith("cme_"):
        return "KEEP_MONITORING"
    if component == "guru_filter_component":
        return "DO_NOT_TUNE_YET"
    if stable_direction and evidence_count >= 30:
        return "PROMISING"
    if stable_direction:
        return "KEEP_MONITORING"
    return "WEAK"


def _latest_price(
    price_frames: dict[str, pl.DataFrame],
    *,
    timeframe: str,
    timestamp: Any,
) -> float | None:
    frame = price_frames.get(timeframe, pl.DataFrame())
    if frame.is_empty() or "timestamp" not in frame.columns or "close" not in frame.columns:
        frame = price_frames.get("15m", pl.DataFrame())
    if frame.is_empty() or "timestamp" not in frame.columns or "close" not in frame.columns:
        return None
    parsed_timestamp = timestamp if isinstance(timestamp, datetime) else _parse_datetime(timestamp)
    rows = []
    for raw in frame.to_dicts():
        row_timestamp = raw.get("timestamp")
        if parsed_timestamp is None or not isinstance(row_timestamp, datetime) or row_timestamp <= parsed_timestamp:
            rows.append(raw)
    selected = rows[-1] if rows else frame.sort("timestamp").tail(1).row(0, named=True)
    return _float_or_none(selected.get("close"))


def _journal_action(score: dict[str, Any]) -> str:
    bucket = _score_bucket(score)
    final_label = _text(score.get("final_label"))
    if final_label == "INSUFFICIENT_DATA":
        return "INSUFFICIENT_DATA"
    if bucket == "BLOCK":
        return "BLOCK"
    if bucket == "WATCH_ONLY":
        return "WATCH_ONLY"
    return "ALLOW_RESEARCH_CANDIDATE"


def _daily_summary(score: dict[str, Any], *, action: str, latest_price: float | None) -> str:
    bucket = _score_bucket(score)
    components = _active_components(score) or "no active component listed"
    price_text = f"{latest_price:.4f}" if latest_price is not None else "unknown price"
    return (
        f"Latest frozen-score row is {bucket} with action {action} at {price_text}. "
        f"Active components: {components}. This is journal/watchlist context only."
    )


def _frozen_yaml(payload: dict[str, Any], *, config_hash: str, frozen_timestamp: str) -> str:
    lines = [
        f"version: {payload['version']}",
        f"config_hash: {config_hash}",
        f"frozen_timestamp: {frozen_timestamp}",
        "validated: false",
        "tuning_allowed: false",
        "threshold_optimization_allowed: false",
        "score_components:",
    ]
    for component in payload["score_components"]:
        lines.append(f"  - component_name: {component['component_name']}")
        lines.append(f"    fixed_score_weight: {component['fixed_score_weight']}")
    lines.append("bucket_thresholds:")
    for bucket in SCORE_BUCKETS:
        lines.append(f"  {bucket}: {payload['bucket_thresholds'][bucket]}")
    lines.append("hard_block_components:")
    for component in payload["hard_block_components"]:
        lines.append(f"  - {component}")
    lines.append(f"evidence_source: {payload['evidence_source']}")
    lines.append("warnings:")
    for warning in payload["warnings"]:
        lines.append(f"  - {warning}")
    return "\n".join(lines) + "\n"


def _frozen_markdown(payload: dict[str, Any], *, config_hash: str, frozen_timestamp: str) -> str:
    components = pl.DataFrame(payload["score_components"], infer_schema_length=None)
    thresholds = pl.DataFrame(
        [
            {"score_bucket": bucket, "threshold": threshold}
            for bucket, threshold in payload["bucket_thresholds"].items()
        ],
        infer_schema_length=None,
    )
    return "\n\n".join(
        [
            "# Frozen XAU Trade Quality Score v1",
            RESEARCH_WARNING,
            f"Version: `{payload['version']}`.",
            f"Config hash: `{config_hash}`.",
            f"Frozen timestamp: `{frozen_timestamp}`.",
            "This frozen score is not validated and must not be tuned by the monitor.",
            PILOT_WARNING,
            "## Components",
            _frame_markdown(components),
            "## Bucket Thresholds",
            _frame_markdown(thresholds),
        ]
    )


def _forward_monitor_markdown(result: XauTradeQualityForwardMonitorResult) -> str:
    return "\n\n".join(
        [
            "# XAU Trade Quality Forward Monitor",
            RESEARCH_WARNING,
            f"Score version: `{result.frozen_config.version}`.",
            f"Score hash: `{result.frozen_config.config_hash}`.",
            f"Final recommendation: `{result.final_recommendation}`.",
            PILOT_WARNING,
            _frame_markdown(result.forward_monitor),
        ]
    )


def _bucket_stability_markdown(result: XauTradeQualityForwardMonitorResult) -> str:
    status = (
        "High-score buckets beat low-score buckets in available forward rows."
        if result.high_score_forward_outperformed_low_score
        else "High-score buckets did not beat low-score buckets in available forward rows."
    )
    return "\n\n".join(
        [
            "# XAU Trade Quality Bucket Stability",
            RESEARCH_WARNING,
            status,
            _frame_markdown(result.bucket_stability),
        ]
    )


def _component_stability_markdown(result: XauTradeQualityForwardMonitorResult) -> str:
    return "\n\n".join(
        [
            "# XAU Trade Quality Component Stability",
            RESEARCH_WARNING,
            PILOT_WARNING,
            _frame_markdown(result.component_stability),
        ]
    )


def _daily_watchlist_markdown(result: XauTradeQualityForwardMonitorResult) -> str:
    return "\n\n".join(
        [
            "# XAU Trade Quality Daily Watchlist",
            RESEARCH_WARNING,
            "Daily watchlist actions are limited to BLOCK, WATCH_ONLY, ALLOW_RESEARCH_CANDIDATE, or INSUFFICIENT_DATA.",
            _frame_markdown(result.daily_watchlist),
        ]
    )


def _safe_report_text(text: str) -> str:
    safe = text
    for phrase in FORBIDDEN_REPORT_PHRASES:
        replacement = " [redacted research-safety phrase] "
        safe = safe.replace(phrase, replacement)
        safe = safe.replace(phrase.upper(), replacement)
    return safe


def _output_paths(output_root: Path) -> dict[str, Path]:
    return {
        "score_csv": output_root / "xau_trade_quality_score.csv",
        "score_backtest": output_root / "xau_trade_quality_score_backtest.csv",
        "score_ablation": output_root / "xau_trade_quality_score_ablation.csv",
        "forward_journal": output_root / "forward_evidence_journal.csv",
        "promoted_outcomes": output_root / "forward_evidence_outcomes_dukascopy_promoted.csv",
        "forward_governance": output_root / "dukascopy_forward_rule_governance.csv",
        "forward_scorecard": output_root / "dukascopy_forward_event_scorecard.csv",
        "price_15m": output_root / "dukascopy_xau_15m.parquet",
        "price_1h": output_root / "dukascopy_xau_1h.parquet",
        "price_4h": output_root / "dukascopy_xau_4h.parquet",
        "current_week": output_root / "current_week_cme_guru_replay.csv",
        "same_day_filter": output_root / "same_day_filter_evidence_after_metadata.csv",
        "same_day_market_map": output_root / "same_day_market_map_evidence_after_metadata.csv",
        "score_config_yaml": output_root / "xau_trade_quality_score_v1.yaml",
        "score_config_hash": output_root / "xau_trade_quality_score_v1_hash.txt",
        "score_config_md": output_root / "xau_trade_quality_score_v1.md",
        "forward_monitor_csv": output_root / "xau_trade_quality_forward_monitor.csv",
        "forward_monitor_md": output_root / "xau_trade_quality_forward_monitor.md",
        "bucket_stability_csv": output_root / "xau_trade_quality_bucket_stability.csv",
        "bucket_stability_md": output_root / "xau_trade_quality_bucket_stability.md",
        "component_stability_csv": output_root / "xau_trade_quality_component_stability.csv",
        "component_stability_md": output_root / "xau_trade_quality_component_stability.md",
        "daily_watchlist_csv": output_root / "xau_trade_quality_daily_watchlist.csv",
        "daily_watchlist_md": output_root / "xau_trade_quality_daily_watchlist.md",
    }


def _read_csv(path: Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    try:
        return pl.read_csv(path, infer_schema_length=None)
    except Exception:  # noqa: BLE001 - optional monitor inputs degrade to empty frames.
        return pl.DataFrame()


def _read_parquet(path: Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    try:
        return pl.read_parquet(path)
    except Exception:  # noqa: BLE001 - optional monitor inputs degrade to empty frames.
        return pl.DataFrame()


def _frame(rows: list[dict[str, Any]], schema: dict[str, Any]) -> pl.DataFrame:
    if not rows:
        return pl.DataFrame(schema=schema)
    frame = pl.DataFrame(rows, infer_schema_length=None)
    for column, dtype in schema.items():
        if column not in frame.columns:
            frame = frame.with_columns(pl.lit(None).cast(dtype).alias(column))
        else:
            frame = frame.with_columns(pl.col(column).cast(dtype, strict=False).alias(column))
    return frame.select(list(schema))


def _frame_markdown(frame: pl.DataFrame, *, limit: int = 25) -> str:
    if frame.is_empty():
        return "_No rows._"
    sample = frame.head(limit)
    lines = [
        "| " + " | ".join(sample.columns) + " |",
        "| " + " | ".join("---" for _ in sample.columns) + " |",
    ]
    for row in sample.to_dicts():
        lines.append("| " + " | ".join(_markdown_cell(row.get(column, "")) for column in sample.columns) + " |")
    if frame.height > limit:
        lines.append(f"\n_Showing {limit} of {frame.height} rows._")
    return "\n".join(lines)


def _markdown_cell(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("|", "\\|").replace("\n", " ")[:700]


def _bucket_order(bucket: str) -> int:
    return list(SCORE_BUCKETS).index(bucket)


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return _ensure_utc(value)
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _date_text(value: Any) -> str:
    parsed = _parse_datetime(value)
    return parsed.date().isoformat() if parsed else _text(value)[:10]


def _column_values(frame: pl.DataFrame, column: str) -> list[float]:
    if frame.is_empty() or column not in frame.columns:
        return []
    values = [_float_or_none(value) for value in frame.get_column(column).to_list()]
    return [value for value in values if value is not None]


def _mean_column(frame: pl.DataFrame, column: str) -> float | None:
    return _average(_column_values(frame, column))


def _average(values: Iterable[float]) -> float | None:
    clean = [value for value in values if value is not None]
    return sum(clean) / len(clean) if clean else None


def _max_int(frame: pl.DataFrame, column: str) -> int:
    if frame.is_empty() or column not in frame.columns:
        return 0
    values = [_int(value) for value in frame.get_column(column).to_list()]
    return max(values) if values else 0


def _int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _score_schema() -> dict[str, Any]:
    return {
        "timestamp": pl.Datetime(time_zone="UTC"),
        "timeframe": pl.String,
        "candidate_direction": pl.String,
        "base_candidate_source": pl.String,
        "trade_quality_score": pl.Int64,
        "score_bucket": pl.String,
        "active_positive_components": pl.String,
        "active_negative_components": pl.String,
        "blocked_reasons": pl.String,
        "watch_reasons": pl.String,
        "data_quality_notes": pl.String,
        "final_label": pl.String,
    }


def _forward_event_schema() -> dict[str, Any]:
    return {
        "timestamp": pl.String,
        "session_date": pl.String,
        "timeframe": pl.String,
        "outcome_status": pl.String,
        "outcome_return": pl.Float64,
        "mfe": pl.Float64,
        "mae": pl.Float64,
    }


def _forward_monitor_schema() -> dict[str, Any]:
    return {
        "timestamp": pl.Datetime(time_zone="UTC"),
        "session_date": pl.String,
        "timeframe": pl.String,
        "score": pl.Int64,
        "score_bucket": pl.String,
        "active_components": pl.String,
        "blocked_reasons": pl.String,
        "data_quality": pl.String,
        "outcome_status": pl.String,
        "outcome_return": pl.Float64,
        "mfe": pl.Float64,
        "mae": pl.Float64,
        "filter_helped": pl.Boolean,
        "false_block": pl.Boolean,
    }


def _bucket_stability_schema() -> dict[str, Any]:
    return {
        "score_bucket": pl.String,
        "bucket_order": pl.Int64,
        "replay_event_count": pl.Int64,
        "replay_resolved_count": pl.Int64,
        "replay_average_return": pl.Float64,
        "replay_support_rate": pl.Float64,
        "replay_failure_rate": pl.Float64,
        "replay_average_mfe": pl.Float64,
        "replay_average_mae": pl.Float64,
        "replay_false_block_rate": pl.Float64,
        "forward_event_count": pl.Int64,
        "forward_resolved_count": pl.Int64,
        "forward_average_return": pl.Float64,
        "forward_support_rate": pl.Float64,
        "forward_failure_rate": pl.Float64,
        "forward_average_mfe": pl.Float64,
        "forward_average_mae": pl.Float64,
        "forward_false_block_rate": pl.Float64,
        "sample_size_warning": pl.Boolean,
        "bucket_order_pass": pl.Boolean,
    }


def _component_stability_schema() -> dict[str, Any]:
    return {
        "component_name": pl.String,
        "replay_effect": pl.String,
        "forward_effect": pl.Float64,
        "stable_direction": pl.Boolean,
        "evidence_count": pl.Int64,
        "recommendation": pl.String,
    }


def _daily_watchlist_schema() -> dict[str, Any]:
    return {
        "session_date": pl.String,
        "timeframe": pl.String,
        "latest_price": pl.Float64,
        "latest_score": pl.Int64,
        "score_bucket": pl.String,
        "active_positive_components": pl.String,
        "active_negative_components": pl.String,
        "blocked_reasons": pl.String,
        "watch_reasons": pl.String,
        "journal_action": pl.String,
        "plain_english_summary": pl.String,
    }
