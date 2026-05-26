"""Failure diagnostics for the frozen XAU Trade Quality Score forward monitor.

This module explains forward bucket inversion without changing score weights,
thresholds, or score generation. It is a research-only diagnostic layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

import polars as pl

from research_xau_vol_oi.xau_trade_quality_forward_monitor import (
    SCORE_VERSION,
    stable_score_config_hash,
)
from research_xau_vol_oi.xau_trade_quality_score import (
    COMPONENT_DELTAS,
    COMPONENT_ORDER,
    SCORE_BUCKETS,
)


FINAL_RECOMMENDATIONS = (
    "KEEP_V1_MONITORING",
    "NEEDS_MORE_FORWARD_DATA",
    "BUG_FIX_REQUIRED",
    "SCORE_NOT_USEFUL_YET",
    "DO_NOT_TUNE_YET",
    "NOT_READY_FOR_MONEY",
)
DECISION_LABELS = (
    "KEEP_V1_MONITORING",
    "BUG_FIX_REQUIRED",
    "QUARANTINE_SCORE_COMPONENT",
    "SCORE_NOT_USEFUL_YET",
    "NEEDS_MORE_FORWARD_DATA",
    "DO_NOT_TUNE_YET",
)
RESEARCH_WARNING = (
    "Research-only failure diagnostic. It freezes the current score interpretation, "
    "does not change weights or thresholds, and does not create a v2 score."
)
PILOT_WARNING = "CME OI/IV remains PILOT_ONLY; guru context remains filter/playbook context."
HIGH_SCORE_BUCKETS = {"ALLOW_RESEARCH", "HIGH_QUALITY_RESEARCH"}
LOW_SCORE_BUCKETS = {"BLOCK", "WATCH_ONLY"}
MIN_FORWARD_RESOLVED = 30
MIN_COMPONENT_RESOLVED = 10
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
class XauTradeQualityFailureDiagnosticResult:
    """Frames and labels emitted by the forward failure diagnostic."""

    bucket_inversion: pl.DataFrame
    component_failure: pl.DataFrame
    join_alignment: pl.DataFrame
    regime_breakdown: pl.DataFrame
    decision: pl.DataFrame
    final_recommendation: str
    high_score_underperformed: bool
    high_score_resolved_count: int
    low_score_resolved_count: int
    outlier_driven: bool
    session_clustered: bool
    quarantined_components: list[str]
    paths: dict[str, Path]


def run_xau_trade_quality_failure_diagnostic(
    *,
    output_dir: str | Path = "outputs",
    write_outputs: bool = True,
) -> XauTradeQualityFailureDiagnosticResult:
    """Run the forward failure diagnostic and optionally write artifacts."""

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    paths = _output_paths(output_root)
    inputs = _load_inputs(paths)
    bucket = build_bucket_inversion_audit(
        forward_monitor=inputs["forward_monitor"],
    )
    component = build_component_failure_audit(
        forward_monitor=inputs["forward_monitor"],
    )
    join = build_forward_join_audit(
        score_rows=inputs["score_rows"],
        forward_monitor=inputs["forward_monitor"],
        promoted_outcomes=inputs["promoted_outcomes"],
        event_level_outcomes=inputs["event_level_outcomes"],
    )
    regime = build_regime_breakdown(
        forward_monitor=inputs["forward_monitor"],
        price_frames=inputs["price_frames"],
    )
    decision = build_failure_decision(
        bucket_inversion=bucket,
        component_failure=component,
        join_alignment=join,
    )
    decision_row = decision.row(0, named=True) if not decision.is_empty() else {}
    result = XauTradeQualityFailureDiagnosticResult(
        bucket_inversion=bucket,
        component_failure=component,
        join_alignment=join,
        regime_breakdown=regime,
        decision=decision,
        final_recommendation=_text(decision_row.get("final_recommendation")),
        high_score_underperformed=bool(decision_row.get("high_score_underperformed")),
        high_score_resolved_count=_int(decision_row.get("high_score_resolved_count")),
        low_score_resolved_count=_int(decision_row.get("low_score_resolved_count")),
        outlier_driven=bool(decision_row.get("outlier_driven")),
        session_clustered=bool(decision_row.get("session_clustered")),
        quarantined_components=[
            _text(row.get("component_name"))
            for row in component.filter(pl.col("recommended_action") == "QUARANTINE_COMPONENT").to_dicts()
        ]
        if not component.is_empty()
        else [],
        paths=paths,
    )
    if write_outputs:
        write_xau_trade_quality_failure_diagnostic_outputs(result)
    return result


def build_bucket_inversion_audit(*, forward_monitor: pl.DataFrame) -> pl.DataFrame:
    """Summarize forward behavior by frozen score bucket."""

    frame = _normalize_forward_monitor(forward_monitor)
    high_avg = _bucket_group_average(frame, HIGH_SCORE_BUCKETS)
    low_avg = _bucket_group_average(frame, LOW_SCORE_BUCKETS)
    high_underperformed = high_avg is not None and low_avg is not None and high_avg < low_avg
    rows = []
    for bucket in SCORE_BUCKETS:
        bucket_rows = frame.filter(pl.col("score_bucket") == bucket) if not frame.is_empty() else frame
        resolved = _resolved(bucket_rows)
        returns = _column_values(resolved, "outcome_return")
        reasons = _bucket_reasons(
            bucket=bucket,
            bucket_rows=bucket_rows,
            resolved=resolved,
            returns=returns,
            high_underperformed=high_underperformed,
        )
        rows.append(
            {
                "bucket": bucket,
                "event_count": bucket_rows.height,
                "resolved_count": resolved.height,
                "average_return": _average(returns),
                "median_return": _median(returns),
                "win_rate": _rate([value > 0 for value in returns]),
                "average_mfe": _mean_column(resolved, "mfe"),
                "average_mae": _mean_column(resolved, "mae"),
                "worst_event_return": min(returns) if returns else None,
                "best_event_return": max(returns) if returns else None,
                "outlier_count": _outlier_count(returns),
                "sample_size_warning": resolved.height < MIN_FORWARD_RESOLVED,
                "reason_bucket_underperformed": ";".join(reasons),
            }
        )
    return _frame(rows, _bucket_inversion_schema())


def build_component_failure_audit(*, forward_monitor: pl.DataFrame) -> pl.DataFrame:
    """Evaluate component behavior in the available forward monitor rows."""

    frame = _normalize_forward_monitor(forward_monitor)
    rows = []
    for component in COMPONENT_ORDER:
        active = _rows_with_component(frame, component)
        inactive = _rows_without_component(frame, component)
        active_resolved = _resolved(active)
        inactive_resolved = _resolved(inactive)
        active_returns = _column_values(active_resolved, "outcome_return")
        inactive_returns = _column_values(inactive_resolved, "outcome_return")
        active_avg = _average(active_returns)
        inactive_avg = _average(inactive_returns)
        effect = _component_effect_direction(
            component=component,
            active_avg=active_avg,
            inactive_avg=inactive_avg,
            active_count=len(active_returns),
            inactive_count=len(inactive_returns),
        )
        possible_issue = _component_possible_issue(
            component=component,
            active_returns=active_returns,
            inactive_returns=inactive_returns,
            effect_direction=effect,
        )
        rows.append(
            {
                "component_name": component,
                "positive_count": len([value for value in active_returns if value > 0]),
                "negative_count": len([value for value in active_returns if value <= 0]),
                "avg_return_when_active": active_avg,
                "avg_return_when_inactive": inactive_avg,
                "effect_direction": effect,
                "possible_issue": possible_issue,
                "recommended_action": _component_recommended_action(
                    effect_direction=effect,
                    possible_issue=possible_issue,
                    active_count=len(active_returns),
                ),
            }
        )
    return _frame(rows, _component_failure_schema())


def build_forward_join_audit(
    *,
    score_rows: pl.DataFrame,
    forward_monitor: pl.DataFrame,
    promoted_outcomes: pl.DataFrame,
    event_level_outcomes: pl.DataFrame = pl.DataFrame(),
) -> pl.DataFrame:
    """Audit score-to-forward-outcome alignment without mutating joins."""

    monitor = _normalize_forward_monitor(forward_monitor)
    outcomes = _normalize_promoted_outcomes(promoted_outcomes)
    joined = _joined_score_rows(score_rows=score_rows, outcomes=outcomes)
    rows = [
        _join_issue(
            "score_timestamp_after_outcome",
            _count_score_after_outcome(joined),
            "ERROR",
            "Fix score/outcome timestamp ordering before interpreting forward stability.",
        ),
        _join_issue(
            "missing_score_join",
            _count_missing_score_join(joined),
            "ERROR",
            "Require a frozen score row at or before each forward observation timestamp.",
        ),
        _join_issue(
            "duplicate_score_rows",
            _duplicate_count(score_rows, ["timestamp", "timeframe"]),
            "ERROR",
            "Deduplicate score rows by timestamp and timeframe before forward monitoring.",
        ),
        _join_issue(
            "duplicate_outcome_rows",
            _duplicate_count(promoted_outcomes, ["journal_id", "observation_timestamp", "outcome_window"]),
            "ERROR",
            "Deduplicate identical journal/window outcome rows before stability scoring.",
        ),
        _join_issue(
            "timeframe_fallback_join",
            _timeframe_fallback_count(joined),
            "WARNING",
            "Review timeframe fallback joins; 30m outcomes may map to 15m score rows.",
        ),
        _join_issue(
            "stale_score_join",
            _stale_join_count(joined),
            "WARNING",
            "Review score rows joined more than one source interval before the outcome observation.",
        ),
        _join_issue(
            "same_event_counted_multiple_times",
            _same_event_window_count(outcomes),
            "WARNING",
            "Interpret stability with event-level aggregation because one journal event can have multiple outcome windows.",
        ),
        _join_issue(
            "forward_rows_exceed_independent_events",
            _forward_rows_exceed_event_count(monitor, event_level_outcomes),
            "WARNING",
            "Compare bucket stability against independent event counts, not only window-level rows.",
        ),
        _join_issue(
            "outcome_window_source_interval_mismatch",
            _window_interval_mismatch_count(outcomes),
            "INFO",
            "Source interval can be an input granularity; confirm window-level metrics remain labeled.",
        ),
        _join_issue(
            "cme_guru_pilot_context_active",
            _cme_guru_active_count(monitor),
            "INFO",
            "Keep CME OI/IV and guru context as pilot/filter context until more forward rows exist.",
        ),
    ]
    return _frame(rows, _join_audit_schema())


def build_regime_breakdown(
    *,
    forward_monitor: pl.DataFrame,
    price_frames: dict[str, pl.DataFrame] | None = None,
) -> pl.DataFrame:
    """Break high/low score rows into simple regime and context slices."""

    frame = _normalize_forward_monitor(forward_monitor)
    if frame.is_empty():
        return pl.DataFrame(schema=_regime_breakdown_schema())
    price_lookup = _build_price_lookup(price_frames or {})
    rows = []
    enriched = []
    for row in frame.to_dicts():
        components = _text(row.get("active_components"))
        timestamp = _parse_datetime(row.get("timestamp"))
        timeframe = _text(row.get("timeframe"))
        price_regime = _price_volatility_regime(price_lookup, timeframe=timeframe, timestamp=timestamp)
        enriched.append(
            {
                **row,
                "_score_group": _score_group(_text(row.get("score_bucket"))),
                "_spread_regime": "FEE_SPREAD_HURDLE_ACTIVE"
                if _component_active(components, "fee_spread_hurdle_component")
                else "FEE_SPREAD_NOT_BLOCKING",
                "_volatility_regime": price_regime,
                "_open_distance_bucket": "OPEN_DISTANCE_ACTIVE"
                if _component_active(components, "open_distance_component")
                else "OPEN_DISTANCE_OK_OR_UNKNOWN",
                "_no_trade_middle_active": str(_component_active(components, "no_trade_middle_range_component")),
                "_acceptance_breakout_active": str(_component_active(components, "acceptance_breakout_component")),
                "_cme_wall_context_available": str(_component_active(components, "cme_wall_context_component")),
                "_guru_filter_active": str(_component_active(components, "guru_filter_component")),
            }
        )
    enriched_frame = pl.DataFrame(enriched, infer_schema_length=None)
    dimensions = {
        "timeframe": "timeframe",
        "session_date": "session_date",
        "spread_regime": "_spread_regime",
        "volatility_regime": "_volatility_regime",
        "open_distance_bucket": "_open_distance_bucket",
        "no_trade_middle_active": "_no_trade_middle_active",
        "acceptance_breakout_active": "_acceptance_breakout_active",
        "cme_wall_context_available": "_cme_wall_context_available",
        "guru_filter_active": "_guru_filter_active",
    }
    for breakdown_type, column in dimensions.items():
        for score_group in ("HIGH_SCORE", "LOW_SCORE"):
            subset = enriched_frame.filter(pl.col("_score_group") == score_group)
            values = sorted({_text(value) for value in subset.get_column(column).to_list() if _text(value)})
            for value in values:
                selected = subset.filter(pl.col(column) == value)
                resolved = _resolved(selected)
                returns = _column_values(resolved, "outcome_return")
                rows.append(
                    {
                        "score_group": score_group,
                        "breakdown_type": breakdown_type,
                        "breakdown_value": value,
                        "event_count": selected.height,
                        "resolved_count": resolved.height,
                        "average_return": _average(returns),
                        "support_rate": _rate([item > 0 for item in returns]),
                        "failure_rate": _rate([item <= 0 for item in returns]),
                        "average_mfe": _mean_column(resolved, "mfe"),
                        "average_mae": _mean_column(resolved, "mae"),
                        "issue_hint": _regime_issue_hint(score_group, resolved.height, _average(returns)),
                    }
                )
    return _frame(rows, _regime_breakdown_schema())


def build_failure_decision(
    *,
    bucket_inversion: pl.DataFrame,
    component_failure: pl.DataFrame,
    join_alignment: pl.DataFrame,
) -> pl.DataFrame:
    """Choose the conservative diagnostic decision."""

    join_errors = _severity_count(join_alignment, "ERROR")
    high_resolved = _bucket_resolved_count(bucket_inversion, HIGH_SCORE_BUCKETS)
    low_resolved = _bucket_resolved_count(bucket_inversion, LOW_SCORE_BUCKETS)
    high_avg = _bucket_audit_group_average(bucket_inversion, HIGH_SCORE_BUCKETS)
    low_avg = _bucket_audit_group_average(bucket_inversion, LOW_SCORE_BUCKETS)
    high_underperformed = high_avg is not None and low_avg is not None and high_avg < low_avg
    outlier_driven = _high_score_outlier_driven(bucket_inversion, high_avg=high_avg, low_avg=low_avg)
    session_clustered = _join_has_issue(join_alignment, "same_event_counted_multiple_times") or _high_session_clustered_hint(
        bucket_inversion
    )
    quarantined = (
        component_failure.filter(pl.col("recommended_action") == "QUARANTINE_COMPONENT")
        if not component_failure.is_empty()
        else pl.DataFrame()
    )
    if join_errors:
        decision_label = "BUG_FIX_REQUIRED"
        final = "BUG_FIX_REQUIRED"
        rationale = "Join/alignment ERROR exists, so stability interpretation must pause for a bug check."
    elif high_resolved < MIN_FORWARD_RESOLVED:
        decision_label = "NEEDS_MORE_FORWARD_DATA"
        final = "NEEDS_MORE_FORWARD_DATA"
        rationale = "High-score forward evidence is below the minimum resolved-row floor; keep v1 monitoring and do not tune."
    elif not quarantined.is_empty():
        decision_label = "QUARANTINE_SCORE_COMPONENT"
        final = "DO_NOT_TUNE_YET"
        rationale = "A component has enough harmful forward evidence for quarantine review, but weights remain frozen."
    elif high_underperformed:
        decision_label = "SCORE_NOT_USEFUL_YET"
        final = "SCORE_NOT_USEFUL_YET"
        rationale = "High-score rows underperformed low-score rows across enough available forward rows."
    else:
        decision_label = "KEEP_V1_MONITORING"
        final = "KEEP_V1_MONITORING"
        rationale = "No alignment bug or component quarantine was found; continue collecting forward rows."
    return _frame(
        [
            {
                "score_version": SCORE_VERSION,
                "score_hash": stable_score_config_hash(),
                "decision_label": decision_label,
                "final_recommendation": final,
                "high_score_underperformed": high_underperformed,
                "high_score_resolved_count": high_resolved,
                "low_score_resolved_count": low_resolved,
                "weighted_high_score_return": high_avg,
                "weighted_low_score_return": low_avg,
                "outlier_driven": outlier_driven,
                "session_clustered": session_clustered,
                "join_error_count": join_errors,
                "component_quarantine_count": quarantined.height,
                "keep_v1_monitoring": decision_label in {"NEEDS_MORE_FORWARD_DATA", "KEEP_V1_MONITORING"},
                "do_not_tune": True,
                "rationale": rationale,
            }
        ],
        _decision_schema(),
    )


def write_xau_trade_quality_failure_diagnostic_outputs(
    result: XauTradeQualityFailureDiagnosticResult,
) -> None:
    """Write failure diagnostic CSV and Markdown outputs."""

    result.bucket_inversion.write_csv(result.paths["bucket_inversion_csv"])
    result.component_failure.write_csv(result.paths["component_failure_csv"])
    result.join_alignment.write_csv(result.paths["join_audit_csv"])
    result.regime_breakdown.write_csv(result.paths["regime_breakdown_csv"])
    result.decision.write_csv(result.paths["failure_decision_csv"])
    result.paths["bucket_inversion_md"].write_text(
        _safe_report_text(_bucket_inversion_markdown(result)),
        encoding="utf-8",
    )
    result.paths["component_failure_md"].write_text(
        _safe_report_text(_component_failure_markdown(result)),
        encoding="utf-8",
    )
    result.paths["join_audit_md"].write_text(
        _safe_report_text(_join_audit_markdown(result)),
        encoding="utf-8",
    )
    result.paths["regime_breakdown_md"].write_text(
        _safe_report_text(_regime_breakdown_markdown(result)),
        encoding="utf-8",
    )
    result.paths["failure_decision_md"].write_text(
        _safe_report_text(_failure_decision_markdown(result)),
        encoding="utf-8",
    )


def xau_trade_quality_failure_diagnostic_report_lines(
    result: XauTradeQualityFailureDiagnosticResult | None,
) -> list[str]:
    """Return research_report.md lines for the failure diagnostic."""

    if result is None:
        return [
            "## XAU Score Bucket Inversion Audit",
            "",
            "XAU Trade Quality Score Forward Failure Diagnostic was not run.",
        ]
    return [
        "## XAU Score Bucket Inversion Audit",
        "",
        RESEARCH_WARNING,
        "",
        _frame_markdown(result.bucket_inversion),
        "",
        "## Component Failure Audit",
        "",
        PILOT_WARNING,
        "",
        _frame_markdown(result.component_failure),
        "",
        "## Forward Join/Alignment Audit",
        "",
        _frame_markdown(result.join_alignment),
        "",
        "## Regime Breakdown",
        "",
        _frame_markdown(result.regime_breakdown),
        "",
        "## Score Failure Decision",
        "",
        _frame_markdown(result.decision),
        "",
        f"- Final recommendation: `{result.final_recommendation}`",
        f"- High-score forward underperformed low-score forward: `{result.high_score_underperformed}`",
        f"- Keep v1 monitoring: `{_bool_text(result.final_recommendation in {'NEEDS_MORE_FORWARD_DATA', 'KEEP_V1_MONITORING'})}`",
        "- Do not tune score weights or thresholds from this diagnostic.",
        "- Money-readiness guardrail: `NOT_READY_FOR_MONEY`",
    ]


def report_text_is_safe(text: str) -> bool:
    """Return true when report text avoids forbidden claim/instruction phrases."""

    lowered = f" {text.lower()} "
    return not any(phrase in lowered for phrase in FORBIDDEN_REPORT_PHRASES)


def _bucket_reasons(
    *,
    bucket: str,
    bucket_rows: pl.DataFrame,
    resolved: pl.DataFrame,
    returns: list[float],
    high_underperformed: bool,
) -> list[str]:
    reasons = []
    if resolved.height < MIN_FORWARD_RESOLVED:
        reasons.append("SAMPLE_TOO_SMALL")
    if _outlier_count(returns):
        reasons.append("OUTLIER_CHECK_REQUIRED")
    if _session_clustered(resolved):
        reasons.append("SESSION_CLUSTERED")
    if bucket in HIGH_SCORE_BUCKETS and high_underperformed:
        reasons.append("HIGH_SCORE_FORWARD_UNDERPERFORMED")
    if bucket in LOW_SCORE_BUCKETS and bucket_rows.height:
        reasons.append("LOW_SCORE_CONTROL_ROWS_NOT_DIRECTLY_COMPARABLE")
    if not reasons:
        reasons.append("OK_KEEP_MONITORING")
    return reasons


def _component_effect_direction(
    *,
    component: str,
    active_avg: float | None,
    inactive_avg: float | None,
    active_count: int,
    inactive_count: int,
) -> str:
    if active_count < MIN_COMPONENT_RESOLVED or inactive_count < MIN_COMPONENT_RESOLVED:
        return "TOO_EARLY"
    if active_avg is None or inactive_avg is None:
        return "TOO_EARLY"
    diff = active_avg - inactive_avg
    if abs(diff) < 0.5:
        return "MIXED"
    weight = COMPONENT_DELTAS.get(component, 0)
    if weight > 0:
        return "HELPFUL" if diff > 0 else "HARMFUL"
    if weight < 0:
        return "HELPFUL" if diff < 0 else "HARMFUL"
    return "MIXED"


def _component_possible_issue(
    *,
    component: str,
    active_returns: list[float],
    inactive_returns: list[float],
    effect_direction: str,
) -> str:
    if len(active_returns) < MIN_COMPONENT_RESOLVED or len(inactive_returns) < MIN_COMPONENT_RESOLVED:
        return "SAMPLE_TOO_SMALL"
    if _outlier_count(active_returns):
        return "OUTLIER_DRIVEN"
    if effect_direction == "HARMFUL":
        return "WRONG_SIGN"
    if component == "stale_data_component":
        return "STALE_DATA"
    return "OK_KEEP_MONITORING"


def _component_recommended_action(
    *,
    effect_direction: str,
    possible_issue: str,
    active_count: int,
) -> str:
    if possible_issue == "WRONG_SIGN" and active_count >= 50:
        return "QUARANTINE_COMPONENT"
    if possible_issue in {"WRONG_SIGN", "JOIN_MISMATCH", "STALE_DATA"}:
        return "BUG_CHECK"
    if possible_issue == "SAMPLE_TOO_SMALL":
        return "DO_NOT_TUNE_YET"
    if effect_direction == "TOO_EARLY":
        return "DO_NOT_TUNE_YET"
    return "KEEP_MONITORING"


def _normalize_forward_monitor(frame: pl.DataFrame) -> pl.DataFrame:
    if frame.is_empty():
        return pl.DataFrame(schema=_forward_monitor_schema())
    rows = []
    for raw in frame.to_dicts():
        rows.append(
            {
                "timestamp": _parse_datetime(raw.get("timestamp")),
                "session_date": _text(raw.get("session_date")) or _date_text(raw.get("timestamp")),
                "timeframe": _text(raw.get("timeframe")),
                "score": _int(raw.get("score")),
                "score_bucket": _valid_bucket(raw.get("score_bucket")),
                "active_components": _text(raw.get("active_components")),
                "blocked_reasons": _text(raw.get("blocked_reasons")),
                "data_quality": _text(raw.get("data_quality")),
                "outcome_status": _text(raw.get("outcome_status")) or "PENDING",
                "outcome_return": _float_or_none(raw.get("outcome_return")),
                "mfe": _float_or_none(raw.get("mfe")),
                "mae": _float_or_none(raw.get("mae")),
                "filter_helped": _bool(raw.get("filter_helped")),
                "false_block": _bool(raw.get("false_block")),
            }
        )
    return _frame(rows, _forward_monitor_schema())


def _normalize_promoted_outcomes(frame: pl.DataFrame) -> pl.DataFrame:
    if frame.is_empty():
        return pl.DataFrame(schema=_promoted_outcome_schema())
    rows = []
    for raw in frame.to_dicts():
        observation = _parse_datetime(raw.get("observation_timestamp") or raw.get("timestamp"))
        rows.append(
            {
                "journal_id": _text(raw.get("journal_id")),
                "observation_timestamp": observation,
                "session_date": _text(raw.get("session_date")) or _date_text(observation),
                "outcome_window": _text(raw.get("outcome_window")),
                "source_interval": _text(raw.get("source_interval") or raw.get("timeframe")),
                "window_start": _parse_datetime(raw.get("window_start")),
                "window_end": _parse_datetime(raw.get("window_end")),
                "outcome_status": _text(raw.get("outcome_status")),
                "outcome_return": _float_or_none(raw.get("outcome_return") or raw.get("close_return")),
            }
        )
    return _frame(rows, _promoted_outcome_schema())


def _joined_score_rows(*, score_rows: pl.DataFrame, outcomes: pl.DataFrame) -> pl.DataFrame:
    if outcomes.is_empty():
        return pl.DataFrame(schema=_joined_score_schema())
    score_index = _score_index(score_rows)
    rows = []
    for outcome in outcomes.to_dicts():
        outcome_timestamp = outcome.get("observation_timestamp")
        event_timeframe = _event_timeframe(outcome)
        score = _nearest_score(score_index, timeframe=event_timeframe, timestamp=outcome_timestamp)
        score_timestamp = score.get("timestamp") if score else None
        rows.append(
            {
                "journal_id": _text(outcome.get("journal_id")),
                "outcome_timestamp": outcome_timestamp,
                "score_timestamp": score_timestamp,
                "event_timeframe": event_timeframe,
                "score_timeframe": _text(score.get("timeframe")) if score else "",
                "score_bucket": _valid_bucket(score.get("score_bucket")) if score else "",
            }
        )
    return _frame(rows, _joined_score_schema())


def _score_index(score_rows: pl.DataFrame) -> dict[str, list[dict[str, Any]]]:
    if score_rows.is_empty() or "timestamp" not in score_rows.columns:
        return {}
    grouped: dict[str, list[dict[str, Any]]] = {}
    for raw in score_rows.to_dicts():
        timestamp = _parse_datetime(raw.get("timestamp"))
        if timestamp is None:
            continue
        row = {**raw, "timestamp": timestamp, "timeframe": _text(raw.get("timeframe"))}
        grouped.setdefault(row["timeframe"], []).append(row)
    for timeframe, rows in grouped.items():
        grouped[timeframe] = sorted(rows, key=lambda item: item["timestamp"])
    return grouped


def _nearest_score(
    score_index: dict[str, list[dict[str, Any]]],
    *,
    timeframe: str,
    timestamp: Any,
) -> dict[str, Any]:
    parsed = timestamp if isinstance(timestamp, datetime) else _parse_datetime(timestamp)
    if parsed is None:
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
        if isinstance(row_timestamp, datetime) and row_timestamp <= parsed:
            selected = row
        elif selected:
            break
    return selected


def _event_timeframe(outcome: dict[str, Any]) -> str:
    value = _text(outcome.get("source_interval") or outcome.get("outcome_window"))
    if value in {"15m", "30m", "1h", "4h"}:
        return value
    if value in {"session_close", "next_day"}:
        return "1h"
    return "15m"


def _join_issue(issue_type: str, affected_rows: int, severity: str, recommended_fix: str) -> dict[str, Any]:
    return {
        "issue_type": issue_type,
        "affected_rows": affected_rows,
        "severity": severity if affected_rows else "INFO",
        "recommended_fix": recommended_fix if affected_rows else "No action from this check.",
    }


def _count_score_after_outcome(joined: pl.DataFrame) -> int:
    count = 0
    for row in joined.to_dicts():
        score_ts = row.get("score_timestamp")
        outcome_ts = row.get("outcome_timestamp")
        if isinstance(score_ts, datetime) and isinstance(outcome_ts, datetime) and score_ts > outcome_ts:
            count += 1
    return count


def _count_missing_score_join(joined: pl.DataFrame) -> int:
    return len([row for row in joined.to_dicts() if row.get("score_timestamp") is None])


def _timeframe_fallback_count(joined: pl.DataFrame) -> int:
    count = 0
    for row in joined.to_dicts():
        event_tf = _text(row.get("event_timeframe"))
        score_tf = _text(row.get("score_timeframe"))
        if event_tf and score_tf and event_tf != score_tf:
            count += 1
    return count


def _stale_join_count(joined: pl.DataFrame) -> int:
    count = 0
    for row in joined.to_dicts():
        score_ts = row.get("score_timestamp")
        outcome_ts = row.get("outcome_timestamp")
        if not isinstance(score_ts, datetime) or not isinstance(outcome_ts, datetime):
            continue
        allowed = _timeframe_minutes(_text(row.get("event_timeframe"))) * 2
        if (outcome_ts - score_ts).total_seconds() / 60 > max(allowed, 60):
            count += 1
    return count


def _same_event_window_count(outcomes: pl.DataFrame) -> int:
    if outcomes.is_empty():
        return 0
    groups: dict[tuple[str, str], int] = {}
    for row in outcomes.to_dicts():
        key = (_text(row.get("journal_id")), _text(row.get("observation_timestamp")))
        groups[key] = groups.get(key, 0) + 1
    return sum(count for count in groups.values() if count > 1)


def _forward_rows_exceed_event_count(monitor: pl.DataFrame, event_level_outcomes: pl.DataFrame) -> int:
    if monitor.is_empty() or event_level_outcomes.is_empty():
        return 0
    independent = event_level_outcomes.height
    return monitor.height - independent if monitor.height > independent else 0


def _window_interval_mismatch_count(outcomes: pl.DataFrame) -> int:
    if outcomes.is_empty():
        return 0
    count = 0
    for row in outcomes.to_dicts():
        window = _text(row.get("outcome_window"))
        interval = _text(row.get("source_interval"))
        if window in {"30m", "1h", "4h"} and interval and window != interval:
            count += 1
    return count


def _cme_guru_active_count(monitor: pl.DataFrame) -> int:
    count = 0
    for row in monitor.to_dicts():
        components = _text(row.get("active_components"))
        if "cme_" in components or "guru_filter_component" in components:
            count += 1
    return count


def _duplicate_count(frame: pl.DataFrame, columns: list[str]) -> int:
    if frame.is_empty() or not set(columns).issubset(frame.columns):
        return 0
    grouped = frame.group_by(columns).len().filter(pl.col("len") > 1)
    return int(grouped.get_column("len").sum()) if not grouped.is_empty() else 0


def _resolved(frame: pl.DataFrame) -> pl.DataFrame:
    if frame.is_empty() or "outcome_status" not in frame.columns:
        return pl.DataFrame(schema=frame.schema)
    return frame.filter(pl.col("outcome_status") == "RESOLVED")


def _rows_with_component(frame: pl.DataFrame, component: str) -> pl.DataFrame:
    if frame.is_empty() or "active_components" not in frame.columns:
        return pl.DataFrame(schema=_forward_monitor_schema())
    return frame.filter(pl.col("active_components").str.contains(component, literal=True))


def _rows_without_component(frame: pl.DataFrame, component: str) -> pl.DataFrame:
    if frame.is_empty() or "active_components" not in frame.columns:
        return pl.DataFrame(schema=_forward_monitor_schema())
    return frame.filter(~pl.col("active_components").str.contains(component, literal=True))


def _bucket_group_average(frame: pl.DataFrame, buckets: set[str]) -> float | None:
    if frame.is_empty():
        return None
    selected = _resolved(frame.filter(pl.col("score_bucket").is_in(sorted(buckets))))
    return _mean_column(selected, "outcome_return")


def _bucket_audit_group_average(frame: pl.DataFrame, buckets: set[str]) -> float | None:
    if frame.is_empty():
        return None
    numerator = 0.0
    denominator = 0.0
    for row in frame.filter(pl.col("bucket").is_in(sorted(buckets))).to_dicts():
        avg = _float_or_none(row.get("average_return"))
        weight = _float_or_none(row.get("resolved_count")) or 0.0
        if avg is not None and weight:
            numerator += avg * weight
            denominator += weight
    return numerator / denominator if denominator else None


def _bucket_resolved_count(frame: pl.DataFrame, buckets: set[str]) -> int:
    if frame.is_empty():
        return 0
    return sum(_int(row.get("resolved_count")) for row in frame.filter(pl.col("bucket").is_in(sorted(buckets))).to_dicts())


def _outlier_count(values: list[float]) -> int:
    if len(values) < 4:
        return 0
    ordered = sorted(values)
    q1 = _percentile(ordered, 0.25)
    q3 = _percentile(ordered, 0.75)
    iqr = q3 - q1
    if iqr == 0:
        median = _median(values) or 0.0
        return len([value for value in values if abs(value - median) > 20])
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    return len([value for value in values if value < lower or value > upper])


def _high_score_outlier_driven(
    bucket_inversion: pl.DataFrame,
    *,
    high_avg: float | None,
    low_avg: float | None,
) -> bool:
    if high_avg is None or low_avg is None or high_avg >= low_avg:
        return False
    high_rows = bucket_inversion.filter(pl.col("bucket").is_in(sorted(HIGH_SCORE_BUCKETS)))
    return any(_int(row.get("outlier_count")) > 0 for row in high_rows.to_dicts())


def _session_clustered(frame: pl.DataFrame) -> bool:
    if frame.is_empty() or "session_date" not in frame.columns or frame.height < 2:
        return False
    counts: dict[str, int] = {}
    for value in frame.get_column("session_date").to_list():
        key = _text(value)
        counts[key] = counts.get(key, 0) + 1
    return max(counts.values()) / frame.height >= 0.75


def _high_session_clustered_hint(bucket_inversion: pl.DataFrame) -> bool:
    if bucket_inversion.is_empty():
        return False
    rows = bucket_inversion.filter(pl.col("bucket").is_in(sorted(HIGH_SCORE_BUCKETS))).to_dicts()
    reasons = ";".join(_text(row.get("reason_bucket_underperformed")) for row in rows)
    return "SESSION_CLUSTERED" in reasons


def _severity_count(frame: pl.DataFrame, severity: str) -> int:
    if frame.is_empty() or "severity" not in frame.columns:
        return 0
    return int(frame.filter((pl.col("severity") == severity) & (pl.col("affected_rows") > 0)).height)


def _join_has_issue(frame: pl.DataFrame, issue_type: str) -> bool:
    if frame.is_empty():
        return False
    rows = frame.filter((pl.col("issue_type") == issue_type) & (pl.col("affected_rows") > 0))
    return not rows.is_empty()


def _build_price_lookup(price_frames: dict[str, pl.DataFrame]) -> dict[str, list[dict[str, Any]]]:
    lookup: dict[str, list[dict[str, Any]]] = {}
    for timeframe, frame in price_frames.items():
        if frame.is_empty() or "timestamp" not in frame.columns:
            continue
        rows = []
        for raw in frame.to_dicts():
            timestamp = _parse_datetime(raw.get("timestamp"))
            if timestamp is None:
                continue
            rows.append({**raw, "timestamp": timestamp})
        lookup[timeframe] = sorted(rows, key=lambda item: item["timestamp"])
    return lookup


def _price_volatility_regime(
    price_lookup: dict[str, list[dict[str, Any]]],
    *,
    timeframe: str,
    timestamp: datetime | None,
) -> str:
    if timestamp is None:
        return "UNKNOWN_VOLATILITY"
    rows = price_lookup.get(timeframe) or price_lookup.get("15m") or []
    selected: dict[str, Any] = {}
    for row in rows:
        row_ts = row.get("timestamp")
        if isinstance(row_ts, datetime) and row_ts <= timestamp:
            selected = row
        elif selected:
            break
    high = _float_or_none(selected.get("high"))
    low = _float_or_none(selected.get("low"))
    close = _float_or_none(selected.get("close"))
    if high is None or low is None or close in {None, 0.0}:
        return "UNKNOWN_VOLATILITY"
    range_ratio = abs(high - low) / abs(close)
    if range_ratio < 0.001:
        return "LOW_RANGE"
    if range_ratio < 0.003:
        return "MEDIUM_RANGE"
    return "HIGH_RANGE"


def _score_group(bucket: str) -> str:
    return "HIGH_SCORE" if bucket in HIGH_SCORE_BUCKETS else "LOW_SCORE"


def _regime_issue_hint(score_group: str, resolved_count: int, average_return: float | None) -> str:
    if resolved_count < MIN_COMPONENT_RESOLVED:
        return "TOO_EARLY"
    if score_group == "HIGH_SCORE" and average_return is not None and average_return < 0:
        return "HIGH_SCORE_WEAK_IN_THIS_SLICE"
    if score_group == "LOW_SCORE" and average_return is not None and average_return > 0:
        return "LOW_SCORE_CONTROL_NOT_COMPARABLE"
    return "KEEP_MONITORING"


def _component_active(components: str, component: str) -> bool:
    return component in {part.strip() for part in components.split(";") if part.strip()}


def _bucket_inversion_markdown(result: XauTradeQualityFailureDiagnosticResult) -> str:
    answer_lines = [
        "- Outlier-driven high-score failure: `" + _bool_text(result.outlier_driven) + "`",
        "- High-score sample too small: `" + _bool_text(result.high_score_resolved_count < MIN_FORWARD_RESOLVED) + "`",
        "- High-score events clustered: `" + _bool_text(result.session_clustered) + "`",
        "- Low-score rows are partly block/watch controls and are not direct candidate equivalents.",
    ]
    return "\n\n".join(
        [
            "# XAU Score Bucket Inversion Audit",
            RESEARCH_WARNING,
            "\n".join(answer_lines),
            _frame_markdown(result.bucket_inversion),
        ]
    )


def _component_failure_markdown(result: XauTradeQualityFailureDiagnosticResult) -> str:
    return "\n\n".join(
        [
            "# XAU Score Component Failure Audit",
            RESEARCH_WARNING,
            PILOT_WARNING,
            "No component weight is changed by this audit.",
            _frame_markdown(result.component_failure),
        ]
    )


def _join_audit_markdown(result: XauTradeQualityFailureDiagnosticResult) -> str:
    return "\n\n".join(
        [
            "# XAU Score Forward Join Audit",
            RESEARCH_WARNING,
            "ERROR rows require a bug check before interpreting stability. WARNING rows constrain interpretation.",
            _frame_markdown(result.join_alignment),
        ]
    )


def _regime_breakdown_markdown(result: XauTradeQualityFailureDiagnosticResult) -> str:
    return "\n\n".join(
        [
            "# XAU Score Regime Breakdown",
            RESEARCH_WARNING,
            "Slices are diagnostic only and must not be used for threshold tuning.",
            _frame_markdown(result.regime_breakdown),
        ]
    )


def _failure_decision_markdown(result: XauTradeQualityFailureDiagnosticResult) -> str:
    return "\n\n".join(
        [
            "# XAU Score Failure Decision",
            RESEARCH_WARNING,
            "The decision preserves v1 score weights and bucket thresholds.",
            _frame_markdown(result.decision),
        ]
    )


def _safe_report_text(text: str) -> str:
    safe = text
    for phrase in FORBIDDEN_REPORT_PHRASES:
        safe = safe.replace(phrase, " [redacted research-safety phrase] ")
        safe = safe.replace(phrase.upper(), " [redacted research-safety phrase] ")
    return safe


def _output_paths(output_root: Path) -> dict[str, Path]:
    return {
        "score_csv": output_root / "xau_trade_quality_score.csv",
        "score_backtest": output_root / "xau_trade_quality_score_backtest.csv",
        "score_ablation": output_root / "xau_trade_quality_score_ablation.csv",
        "forward_monitor": output_root / "xau_trade_quality_forward_monitor.csv",
        "bucket_stability": output_root / "xau_trade_quality_bucket_stability.csv",
        "component_stability": output_root / "xau_trade_quality_component_stability.csv",
        "daily_watchlist": output_root / "xau_trade_quality_daily_watchlist.csv",
        "promoted_outcomes": output_root / "forward_evidence_outcomes_dukascopy_promoted.csv",
        "forward_governance": output_root / "dukascopy_forward_rule_governance.csv",
        "forward_scorecard": output_root / "dukascopy_forward_event_scorecard.csv",
        "event_level_outcomes": output_root / "dukascopy_forward_event_level_outcomes.csv",
        "price_15m": output_root / "dukascopy_xau_15m.parquet",
        "price_1h": output_root / "dukascopy_xau_1h.parquet",
        "price_4h": output_root / "dukascopy_xau_4h.parquet",
        "bucket_inversion_csv": output_root / "xau_score_bucket_inversion_audit.csv",
        "bucket_inversion_md": output_root / "xau_score_bucket_inversion_audit.md",
        "component_failure_csv": output_root / "xau_score_component_failure_audit.csv",
        "component_failure_md": output_root / "xau_score_component_failure_audit.md",
        "join_audit_csv": output_root / "xau_score_forward_join_audit.csv",
        "join_audit_md": output_root / "xau_score_forward_join_audit.md",
        "regime_breakdown_csv": output_root / "xau_score_regime_breakdown.csv",
        "regime_breakdown_md": output_root / "xau_score_regime_breakdown.md",
        "failure_decision_csv": output_root / "xau_score_failure_decision.csv",
        "failure_decision_md": output_root / "xau_score_failure_decision.md",
    }


def _load_inputs(paths: dict[str, Path]) -> dict[str, Any]:
    return {
        "score_rows": _read_csv(paths["score_csv"]),
        "score_backtest": _read_csv(paths["score_backtest"]),
        "score_ablation": _read_csv(paths["score_ablation"]),
        "forward_monitor": _read_csv(paths["forward_monitor"]),
        "bucket_stability": _read_csv(paths["bucket_stability"]),
        "component_stability": _read_csv(paths["component_stability"]),
        "daily_watchlist": _read_csv(paths["daily_watchlist"]),
        "promoted_outcomes": _read_csv(paths["promoted_outcomes"]),
        "forward_governance": _read_csv(paths["forward_governance"]),
        "forward_scorecard": _read_csv(paths["forward_scorecard"]),
        "event_level_outcomes": _read_csv(paths["event_level_outcomes"]),
        "price_frames": {
            "15m": _read_parquet(paths["price_15m"]),
            "1h": _read_parquet(paths["price_1h"]),
            "4h": _read_parquet(paths["price_4h"]),
        },
    }


def _read_csv(path: Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    try:
        return pl.read_csv(path, infer_schema_length=None)
    except Exception:  # noqa: BLE001 - optional diagnostic inputs degrade to empty frames.
        return pl.DataFrame()


def _read_parquet(path: Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    try:
        return pl.read_parquet(path)
    except Exception:  # noqa: BLE001 - optional diagnostic inputs degrade to empty frames.
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


def _median(values: list[float]) -> float | None:
    clean = sorted(value for value in values if value is not None)
    if not clean:
        return None
    midpoint = len(clean) // 2
    if len(clean) % 2:
        return clean[midpoint]
    return (clean[midpoint - 1] + clean[midpoint]) / 2


def _percentile(ordered_values: list[float], percentile: float) -> float:
    if not ordered_values:
        return 0.0
    index = (len(ordered_values) - 1) * percentile
    lower = int(index)
    upper = min(lower + 1, len(ordered_values) - 1)
    weight = index - lower
    return ordered_values[lower] * (1 - weight) + ordered_values[upper] * weight


def _rate(values: list[bool]) -> float | None:
    return sum(1 for value in values if value) / len(values) if values else None


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return _ensure_utc(value)
    text = _text(value)
    if not text:
        return None
    try:
        normalized = text.replace("Z", "+00:00")
        if len(normalized) > 5 and normalized[-5] in {"+", "-"} and normalized[-3] != ":":
            normalized = f"{normalized[:-2]}:{normalized[-2:]}"
        return datetime.fromisoformat(normalized).astimezone(UTC)
    except ValueError:
        return None


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _date_text(value: Any) -> str:
    parsed = _parse_datetime(value)
    return parsed.date().isoformat() if parsed else _text(value)[:10]


def _timeframe_minutes(timeframe: str) -> int:
    return {"15m": 15, "30m": 30, "1h": 60, "4h": 240}.get(timeframe, 60)


def _valid_bucket(value: Any) -> str:
    bucket = _text(value)
    return bucket if bucket in SCORE_BUCKETS else "WATCH_ONLY"


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"true", "1", "yes"}


def _bool_text(value: bool) -> str:
    return "true" if value else "false"


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


def _promoted_outcome_schema() -> dict[str, Any]:
    return {
        "journal_id": pl.String,
        "observation_timestamp": pl.Datetime(time_zone="UTC"),
        "session_date": pl.String,
        "outcome_window": pl.String,
        "source_interval": pl.String,
        "window_start": pl.Datetime(time_zone="UTC"),
        "window_end": pl.Datetime(time_zone="UTC"),
        "outcome_status": pl.String,
        "outcome_return": pl.Float64,
    }


def _joined_score_schema() -> dict[str, Any]:
    return {
        "journal_id": pl.String,
        "outcome_timestamp": pl.Datetime(time_zone="UTC"),
        "score_timestamp": pl.Datetime(time_zone="UTC"),
        "event_timeframe": pl.String,
        "score_timeframe": pl.String,
        "score_bucket": pl.String,
    }


def _bucket_inversion_schema() -> dict[str, Any]:
    return {
        "bucket": pl.String,
        "event_count": pl.Int64,
        "resolved_count": pl.Int64,
        "average_return": pl.Float64,
        "median_return": pl.Float64,
        "win_rate": pl.Float64,
        "average_mfe": pl.Float64,
        "average_mae": pl.Float64,
        "worst_event_return": pl.Float64,
        "best_event_return": pl.Float64,
        "outlier_count": pl.Int64,
        "sample_size_warning": pl.Boolean,
        "reason_bucket_underperformed": pl.String,
    }


def _component_failure_schema() -> dict[str, Any]:
    return {
        "component_name": pl.String,
        "positive_count": pl.Int64,
        "negative_count": pl.Int64,
        "avg_return_when_active": pl.Float64,
        "avg_return_when_inactive": pl.Float64,
        "effect_direction": pl.String,
        "possible_issue": pl.String,
        "recommended_action": pl.String,
    }


def _join_audit_schema() -> dict[str, Any]:
    return {
        "issue_type": pl.String,
        "affected_rows": pl.Int64,
        "severity": pl.String,
        "recommended_fix": pl.String,
    }


def _regime_breakdown_schema() -> dict[str, Any]:
    return {
        "score_group": pl.String,
        "breakdown_type": pl.String,
        "breakdown_value": pl.String,
        "event_count": pl.Int64,
        "resolved_count": pl.Int64,
        "average_return": pl.Float64,
        "support_rate": pl.Float64,
        "failure_rate": pl.Float64,
        "average_mfe": pl.Float64,
        "average_mae": pl.Float64,
        "issue_hint": pl.String,
    }


def _decision_schema() -> dict[str, Any]:
    return {
        "score_version": pl.String,
        "score_hash": pl.String,
        "decision_label": pl.String,
        "final_recommendation": pl.String,
        "high_score_underperformed": pl.Boolean,
        "high_score_resolved_count": pl.Int64,
        "low_score_resolved_count": pl.Int64,
        "weighted_high_score_return": pl.Float64,
        "weighted_low_score_return": pl.Float64,
        "outlier_driven": pl.Boolean,
        "session_clustered": pl.Boolean,
        "join_error_count": pl.Int64,
        "component_quarantine_count": pl.Int64,
        "keep_v1_monitoring": pl.Boolean,
        "do_not_tune": pl.Boolean,
        "rationale": pl.String,
    }
