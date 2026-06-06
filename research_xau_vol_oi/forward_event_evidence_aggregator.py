"""Event-level forward evidence aggregation and rule governance reports.

This layer is research-only. It collapses promoted forward outcome-window rows
into independent journal/rule events before any rule-level interpretation. It
does not tune frozen rules, alter thresholds, mutate journal observations, or
make execution-readiness claims.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any, Iterable

import polars as pl


DEFAULT_RULE_ID = "FORWARD_OUTCOME_PREVIEW"
DEFAULT_RULE_NAME = "Forward outcome preview"
DEFAULT_RULE_FAMILY = "FORWARD_OUTCOME"
MIN_EVENTS_FOR_REVIEW = 30
MIN_EVENTS_FOR_VALIDATION = 60
PROMISING_PILOT_MIN_EVENTS = 5
WINDOW_ORDER = ("30m", "1h", "4h", "session_close", "next_day")
WINDOW_RANK = {window: index for index, window in enumerate(WINDOW_ORDER)}
FINAL_RECOMMENDATION = "COLLECT_MORE_FORWARD_EVENTS"
RESEARCH_WARNING = (
    "Research-only event evidence. No live trading, paper trading, broker "
    "integration, order execution, threshold tuning, or money-readiness claim is included."
)
FORBIDDEN_REPORT_PHRASES = (
    "profitable",
    "profitability",
    "guaranteed edge",
    "predicts price",
    "safe to trade",
    "live ready",
    "validated money edge",
)
FOCUS_PRIORITY = {
    "ACCEPTANCE_BREAKOUT": 1,
    "REJECTION_AFTER_LEVEL_TOUCH": 2,
    "NO_TRADE_MIDDLE_RANGE": 3,
    "OPEN_DISTANCE_FILTER": 4,
    "OI_WALL_WATCH_ZONE": 5,
    "LOW_OI_GAP_SQUEEZE": 6,
}


@dataclass(frozen=True)
class ForwardEventEvidenceAggregatorResult:
    """Frames and labels emitted by the event-level evidence layer."""

    event_level_outcomes: pl.DataFrame
    rule_event_evidence: pl.DataFrame
    rule_governance: pl.DataFrame
    focus_list: pl.DataFrame
    event_scorecard: pl.DataFrame
    final_recommendation: str
    paths: dict[str, Path]
    input_warnings: tuple[str, ...]


def run_forward_event_evidence_aggregator(
    *,
    output_dir: str | Path = "outputs",
    current_time: datetime | None = None,
    write_outputs: bool = True,
) -> ForwardEventEvidenceAggregatorResult:
    """Run event aggregation, rule governance, and focus-list generation."""

    del current_time
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    paths = {
        "promoted": output_root / "forward_evidence_outcomes_promoted.csv",
        "preview": output_root / "forward_evidence_outcomes_preview.csv",
        "preview_audit": output_root / "forward_outcome_preview_audit.csv",
        "window_rule_summary": output_root / "forward_rule_evidence_summary.csv",
        "filter_evidence": output_root / "forward_filter_evidence.csv",
        "market_map_evidence": output_root / "forward_market_map_evidence.csv",
        "pending_summary": output_root / "forward_pending_outcome_summary.csv",
        "forward_scorecard": output_root / "forward_evidence_scorecard.csv",
        "journal": output_root / "forward_evidence_journal.csv",
        "frozen_rulebook": output_root / "frozen_rulebook_v1.yaml",
        "rulebook_hash": output_root / "frozen_rulebook_v1_hash.txt",
        "rule_library": output_root / "guru_rule_library.csv",
        "rule_events": output_root / "guru_rule_backtest_events.csv",
        "event_level_csv": output_root / "forward_event_level_outcomes.csv",
        "event_level_md": output_root / "forward_event_level_outcomes.md",
        "rule_event_csv": output_root / "forward_rule_event_evidence.csv",
        "rule_event_md": output_root / "forward_rule_event_evidence.md",
        "governance_csv": output_root / "forward_rule_governance.csv",
        "governance_md": output_root / "forward_rule_governance.md",
        "focus_csv": output_root / "next_rule_focus_list.csv",
        "focus_md": output_root / "next_rule_focus_list.md",
        "event_scorecard_csv": output_root / "forward_event_scorecard.csv",
        "event_scorecard_md": output_root / "forward_event_scorecard.md",
    }

    promoted = _read_csv_frame(paths["promoted"])
    preview = _read_csv_frame(paths["preview"])
    preview_audit = _read_csv_frame(paths["preview_audit"])
    window_rule_summary = _read_csv_frame(paths["window_rule_summary"])
    filter_evidence = _read_csv_frame(paths["filter_evidence"])
    market_map_evidence = _read_csv_frame(paths["market_map_evidence"])
    pending_summary = _read_csv_frame(paths["pending_summary"])
    forward_scorecard = _read_csv_frame(paths["forward_scorecard"])
    journal = _read_csv_frame(paths["journal"])
    rule_library = _read_csv_frame(paths["rule_library"])
    rule_events = _read_csv_frame(paths["rule_events"])

    input_warnings = tuple(
        _input_warnings(
            paths=paths,
            promoted=promoted,
            preview=preview,
            preview_audit=preview_audit,
            journal=journal,
        )
    )
    event_level_outcomes = build_event_level_outcomes(
        promoted_outcomes=promoted,
        rule_library=rule_library,
        rule_events=rule_events,
        window_rule_summary=window_rule_summary,
    )
    rule_event_evidence = build_rule_event_evidence(event_level_outcomes)
    rule_governance = build_rule_governance(rule_event_evidence)
    focus_list = build_next_rule_focus_list(
        rule_event_evidence=rule_event_evidence,
        rule_governance=rule_governance,
        filter_evidence=filter_evidence,
        market_map_evidence=market_map_evidence,
        rule_library=rule_library,
    )
    event_scorecard = build_event_scorecard(
        promoted_outcomes=promoted,
        event_level_outcomes=event_level_outcomes,
        pending_summary=pending_summary,
        rule_event_evidence=rule_event_evidence,
        forward_scorecard=forward_scorecard,
    )
    final_recommendation = choose_final_recommendation(event_scorecard)

    if write_outputs:
        event_level_outcomes.write_csv(paths["event_level_csv"])
        rule_event_evidence.write_csv(paths["rule_event_csv"])
        rule_governance.write_csv(paths["governance_csv"])
        focus_list.write_csv(paths["focus_csv"])
        event_scorecard.write_csv(paths["event_scorecard_csv"])
        _write_markdown_table(
            paths["event_level_md"],
            "# Event-Level Forward Outcomes",
            _event_level_report_view(event_level_outcomes),
            [
                "Promoted outcome windows are grouped into journal/rule events.",
                "Window rows are not counted as independent trade events.",
                RESEARCH_WARNING,
                *_warning_lines(input_warnings),
            ],
        )
        _write_markdown_table(
            paths["rule_event_md"],
            "# Rule-Level Event Evidence",
            rule_event_evidence,
            [
                "Sample-size warnings use independent event counts, not window-row counts.",
                f"Rules below {MIN_EVENTS_FOR_REVIEW} independent events remain early-stage.",
                RESEARCH_WARNING,
            ],
        )
        _write_markdown_table(
            paths["governance_md"],
            "# Forward Rule Governance",
            rule_governance,
            [
                "Frozen rules remain unchanged. Threshold tuning is not part of this layer.",
                f"No rule can be validation-ready below {MIN_EVENTS_FOR_VALIDATION} independent events.",
                RESEARCH_WARNING,
            ],
        )
        _write_markdown_table(
            paths["focus_md"],
            "# Next Rule Focus List",
            focus_list,
            [
                "Focus ranking is for next-session inspection and data collection only.",
                RESEARCH_WARNING,
            ],
        )
        _write_scorecard_markdown(
            paths["event_scorecard_md"],
            event_scorecard,
            final_recommendation=final_recommendation,
        )

    return ForwardEventEvidenceAggregatorResult(
        event_level_outcomes=event_level_outcomes,
        rule_event_evidence=rule_event_evidence,
        rule_governance=rule_governance,
        focus_list=focus_list,
        event_scorecard=event_scorecard,
        final_recommendation=final_recommendation,
        paths=paths,
        input_warnings=input_warnings,
    )


def build_event_level_outcomes(
    *,
    promoted_outcomes: pl.DataFrame,
    rule_library: pl.DataFrame = pl.DataFrame(),
    rule_events: pl.DataFrame = pl.DataFrame(),
    window_rule_summary: pl.DataFrame = pl.DataFrame(),
) -> pl.DataFrame:
    """Aggregate promoted window rows into independent journal/rule events."""

    if promoted_outcomes.is_empty():
        return pl.DataFrame(schema=_event_level_schema())
    linked_rows = link_promoted_to_rule_context(
        promoted_outcomes=promoted_outcomes,
        rule_library=rule_library,
        rule_events=rule_events,
        window_rule_summary=window_rule_summary,
    )
    groups: dict[tuple[str, str, str, str, str, str, str], list[dict[str, Any]]] = {}
    for row in linked_rows:
        key = (
            _string(row.get("journal_id")),
            _string(row.get("rule_id")),
            _string(row.get("rule_name")),
            _string(row.get("rule_family")),
            _string(row.get("observation_timestamp")),
            _event_session_date(row),
            _string(row.get("signal_context")),
        )
        groups.setdefault(key, []).append(row)

    rows = []
    for key, items in groups.items():
        (
            journal_id,
            rule_id,
            rule_name,
            rule_family,
            observation_timestamp,
            session_date,
            signal_context,
        ) = key
        rule_type = _dominant_rule_type(items)
        windows = _sorted_windows(items)
        primary = _select_primary_window_row(items, rule_type)
        primary_result = _primary_window_result(primary, rule_type)
        supported = sum(1 for item in items if _row_result(item) == "supported")
        failed = sum(1 for item in items if _row_result(item) == "failed")
        mixed = sum(1 for item in items if _row_result(item) == "mixed")
        no_clear = max(len(items) - supported - failed - mixed, 0)
        wall_touch_any = any(_wall_touch(item) for item in items)
        wall_rejection_any = any(_wall_rejection(item) for item in items)
        wall_acceptance_any = any(_wall_acceptance(item) for item in items)
        filter_helped_any = any(_filter_helped(item, rule_type) for item in items)
        filter_false_block_any = any(_filter_false_block(item, rule_type) for item in items)
        primary_window = _string(primary.get("outcome_window") or primary.get("window"))
        rows.append(
            {
                "journal_id": journal_id,
                "rule_id": rule_id,
                "rule_name": rule_name,
                "rule_family": rule_family,
                "rule_type": rule_type,
                "observation_timestamp": observation_timestamp,
                "session_date": session_date,
                "signal_context": signal_context,
                "windows_available": "|".join(windows),
                "windows_supported_count": supported,
                "windows_failed_count": failed,
                "windows_mixed_count": mixed,
                "windows_no_clear_count": no_clear,
                "earliest_supported_window": _earliest_window(items, "supported"),
                "earliest_failed_window": _earliest_window(items, "failed"),
                "primary_window": primary_window,
                "primary_window_result": primary_result,
                "event_outcome_label": _event_outcome_label(
                    primary_result=primary_result,
                    rule_type=rule_type,
                    supported_count=supported,
                    failed_count=failed,
                    mixed_count=mixed,
                    filter_helped_any=filter_helped_any,
                    filter_false_block_any=filter_false_block_any,
                    wall_touch_any=wall_touch_any,
                ),
                "close_return_primary": _optional_float(primary.get("close_return")),
                "mfe_max": _max(_optional_float(item.get("mfe")) for item in items),
                "mae_max": _min(_optional_float(item.get("mae")) for item in items),
                "wall_touch_any": wall_touch_any,
                "wall_rejection_any": wall_rejection_any,
                "wall_acceptance_any": wall_acceptance_any,
                "no_trade_filter_helped_any": filter_helped_any,
                "no_trade_filter_false_block_any": filter_false_block_any,
                "event_quality": _event_quality(
                    rule_type=rule_type,
                    primary_window=primary_window,
                    windows=windows,
                ),
            }
        )
    return pl.DataFrame(rows, schema=_event_level_schema(), infer_schema_length=None)


def link_promoted_to_rule_context(
    *,
    promoted_outcomes: pl.DataFrame,
    rule_library: pl.DataFrame = pl.DataFrame(),
    rule_events: pl.DataFrame = pl.DataFrame(),
    window_rule_summary: pl.DataFrame = pl.DataFrame(),
) -> list[dict[str, Any]]:
    """Attach frozen-rule context to promoted rows, without changing the source rows."""

    rule_lookup = _rule_lookup(rule_library)
    events_by_date: dict[str, list[dict[str, Any]]] = {}
    if not rule_events.is_empty() and "event_date" in rule_events.columns:
        for event in rule_events.to_dicts():
            events_by_date.setdefault(_string(event.get("event_date"))[:10], []).append(event)

    summary_by_window: dict[str, list[dict[str, Any]]] = {}
    if not window_rule_summary.is_empty() and "outcome_window" in window_rule_summary.columns:
        for row in window_rule_summary.to_dicts():
            summary_by_window.setdefault(_string(row.get("outcome_window")), []).append(row)

    linked: list[dict[str, Any]] = []
    for promoted in promoted_outcomes.to_dicts():
        event_date = _event_session_date(promoted)
        context_rows = _aggregate_rule_context_rows(events_by_date.get(event_date, []))
        if not context_rows:
            context_rows = _context_rows_from_summary(promoted, summary_by_window)
        if not context_rows:
            context_rows = [{}]
        for context in context_rows:
            rule_id = _string(context.get("rule_id") or promoted.get("rule_id"))
            if not rule_id:
                rule_id = DEFAULT_RULE_ID
            meta = rule_lookup.get(rule_id, {})
            rule_name = (
                _string(meta.get("rule_name") or context.get("rule_name") or promoted.get("rule_name"))
                or rule_id
                or DEFAULT_RULE_NAME
            )
            rule_family = (
                _string(meta.get("rule_family") or context.get("rule_family") or promoted.get("rule_family"))
                or DEFAULT_RULE_FAMILY
            )
            rule_type = (
                _string(meta.get("rule_type") or context.get("rule_type") or promoted.get("rule_type"))
                or "OUTCOME_REVIEW"
            )
            signal_context = (
                _string(context.get("mode") or context.get("signal_context") or promoted.get("signal_context"))
                or "FORWARD_OUTCOME_PREVIEW"
            )
            linked.append(
                {
                    **promoted,
                    **context,
                    "rule_id": rule_id,
                    "rule_name": rule_name,
                    "rule_family": rule_family,
                    "rule_type": rule_type,
                    "signal_context": signal_context,
                    "outcome_window": _string(
                        promoted.get("outcome_window") or promoted.get("window")
                    ),
                }
            )
    return linked


def build_rule_event_evidence(event_level_outcomes: pl.DataFrame) -> pl.DataFrame:
    """Summarize frozen-rule evidence using independent event counts."""

    if event_level_outcomes.is_empty():
        return pl.DataFrame(schema=_rule_event_schema())
    groups: dict[tuple[str, str, str, str, str], list[dict[str, Any]]] = {}
    for row in event_level_outcomes.to_dicts():
        key = (
            _string(row.get("rule_id")),
            _string(row.get("rule_name")),
            _string(row.get("rule_family")),
            _string(row.get("rule_type")),
            _string(row.get("signal_context")),
        )
        groups.setdefault(key, []).append(row)

    rows = []
    for key, items in groups.items():
        rule_id, rule_name, rule_family, rule_type, signal_context = key
        count = len(items)
        supported = sum(1 for item in items if item.get("event_outcome_label") == "EVENT_SUPPORTED")
        failed = sum(1 for item in items if item.get("event_outcome_label") == "EVENT_FAILED")
        mixed = sum(1 for item in items if item.get("event_outcome_label") == "EVENT_MIXED")
        no_clear = sum(
            1 for item in items if item.get("event_outcome_label") == "EVENT_NO_CLEAR_OUTCOME"
        )
        support_rate = supported / count if count else 0.0
        fail_rate = failed / count if count else 0.0
        average_mfe = _mean(_optional_float(item.get("mfe_max")) for item in items)
        average_mae = _mean(_optional_float(item.get("mae_max")) for item in items)
        adverse_to_favorable = _adverse_to_favorable_ratio(average_mae, average_mfe)
        filter_helped = sum(1 for item in items if _bool(item.get("no_trade_filter_helped_any")))
        filter_false = sum(1 for item in items if _bool(item.get("no_trade_filter_false_block_any")))
        wall_touch = sum(1 for item in items if _bool(item.get("wall_touch_any")))
        wall_reject = sum(1 for item in items if _bool(item.get("wall_rejection_any")))
        wall_accept = sum(1 for item in items if _bool(item.get("wall_acceptance_any")))
        rows.append(
            {
                "rule_id": rule_id,
                "rule_name": rule_name,
                "rule_family": rule_family,
                "rule_type": rule_type,
                "signal_context": signal_context,
                "independent_event_count": count,
                "supported_events": supported,
                "failed_events": failed,
                "mixed_events": mixed,
                "no_clear_events": no_clear,
                "support_rate_event_level": support_rate,
                "fail_rate_event_level": fail_rate,
                "average_primary_return": _mean(
                    _optional_float(item.get("close_return_primary")) for item in items
                ),
                "average_mfe": average_mfe,
                "average_mae": average_mae,
                "adverse_to_favorable_ratio": adverse_to_favorable,
                "filter_helped_events": filter_helped,
                "filter_false_block_events": filter_false,
                "wall_touch_events": wall_touch,
                "wall_rejection_events": wall_reject,
                "wall_acceptance_events": wall_accept,
                "event_sample_size_warning": count < MIN_EVENTS_FOR_REVIEW,
                "evidence_label": _rule_event_label(
                    rule_type=rule_type,
                    count=count,
                    support_rate=support_rate,
                    fail_rate=fail_rate,
                    filter_helped=filter_helped,
                    filter_false=filter_false,
                    wall_touch=wall_touch,
                ),
            }
        )
    return pl.DataFrame(rows, schema=_rule_event_schema(), infer_schema_length=None)


def build_rule_governance(rule_event_evidence: pl.DataFrame) -> pl.DataFrame:
    """Create governance recommendations without validating or tuning rules."""

    if rule_event_evidence.is_empty():
        return pl.DataFrame(schema=_governance_schema())
    rows = []
    for row in _collapse_rule_event_rows_for_governance(rule_event_evidence):
        count = _optional_int(row.get("independent_event_count")) or 0
        label = _string(row.get("evidence_label"))
        rule_type = _string(row.get("rule_type")).upper()
        recommendation = _governance_recommendation(row)
        rows.append(
            {
                "rule_id": _string(row.get("rule_id")),
                "rule_name": _string(row.get("rule_name")),
                "rule_family": _string(row.get("rule_family")),
                "independent_event_count": count,
                "evidence_label": label,
                "recommendation": recommendation,
                "reason": _governance_reason(
                    count=count,
                    label=label,
                    rule_type=rule_type,
                    recommendation=recommendation,
                    fail_rate=_optional_float(row.get("fail_rate_event_level")) or 0.0,
                ),
                "next_required_events": max(MIN_EVENTS_FOR_REVIEW - count, 0),
                "minimum_events_for_review": MIN_EVENTS_FOR_REVIEW,
                "can_change_rule_now": False,
            }
        )
    return pl.DataFrame(rows, schema=_governance_schema(), infer_schema_length=None)


def _collapse_rule_event_rows_for_governance(rule_event_evidence: pl.DataFrame) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rule_event_evidence.to_dicts():
        rule_id = _string(row.get("rule_id"))
        if rule_id:
            groups.setdefault(rule_id, []).append(row)
    collapsed = []
    for rule_id, records in groups.items():
        first = max(
            records,
            key=lambda row: _optional_int(row.get("independent_event_count")) or 0,
        )
        count = sum(_optional_int(row.get("independent_event_count")) or 0 for row in records)
        supported = sum(_optional_int(row.get("supported_events")) or 0 for row in records)
        failed = sum(_optional_int(row.get("failed_events")) or 0 for row in records)
        mixed = sum(_optional_int(row.get("mixed_events")) or 0 for row in records)
        no_clear = sum(_optional_int(row.get("no_clear_events")) or 0 for row in records)
        filter_helped = sum(_optional_int(row.get("filter_helped_events")) or 0 for row in records)
        filter_false = sum(
            _optional_int(row.get("filter_false_block_events")) or 0 for row in records
        )
        wall_touch = sum(_optional_int(row.get("wall_touch_events")) or 0 for row in records)
        wall_reject = sum(_optional_int(row.get("wall_rejection_events")) or 0 for row in records)
        wall_accept = sum(_optional_int(row.get("wall_acceptance_events")) or 0 for row in records)
        support_rate = supported / count if count else 0.0
        fail_rate = failed / count if count else 0.0
        rule_type = _string(first.get("rule_type"))
        collapsed.append(
            {
                **first,
                "rule_id": rule_id,
                "independent_event_count": count,
                "supported_events": supported,
                "failed_events": failed,
                "mixed_events": mixed,
                "no_clear_events": no_clear,
                "support_rate_event_level": support_rate,
                "fail_rate_event_level": fail_rate,
                "filter_helped_events": filter_helped,
                "filter_false_block_events": filter_false,
                "wall_touch_events": wall_touch,
                "wall_rejection_events": wall_reject,
                "wall_acceptance_events": wall_accept,
                "event_sample_size_warning": count < MIN_EVENTS_FOR_REVIEW,
                "evidence_label": _rule_event_label(
                    rule_type=rule_type,
                    count=count,
                    support_rate=support_rate,
                    fail_rate=fail_rate,
                    filter_helped=filter_helped,
                    filter_false=filter_false,
                    wall_touch=wall_touch,
                ),
            }
        )
    return collapsed


def build_next_rule_focus_list(
    *,
    rule_event_evidence: pl.DataFrame,
    rule_governance: pl.DataFrame,
    filter_evidence: pl.DataFrame = pl.DataFrame(),
    market_map_evidence: pl.DataFrame = pl.DataFrame(),
    rule_library: pl.DataFrame = pl.DataFrame(),
) -> pl.DataFrame:
    """Rank rules for next-session inspection and data collection."""

    rows_by_rule: dict[str, dict[str, Any]] = {}
    for row in rule_event_evidence.to_dicts():
        rule_id = _string(row.get("rule_id"))
        if not rule_id:
            continue
        existing = rows_by_rule.get(rule_id)
        if existing is None or (
            (_optional_int(row.get("independent_event_count")) or 0)
            > (_optional_int(existing.get("independent_event_count")) or 0)
        ):
            rows_by_rule[rule_id] = dict(row)
    for row in rule_governance.to_dicts():
        rule_id = _string(row.get("rule_id"))
        if rule_id:
            rows_by_rule.setdefault(rule_id, {}).update(row)
    filter_lookup = _row_lookup(filter_evidence, "rule_id")
    map_lookup = _row_lookup(market_map_evidence, "rule_id")
    library_lookup = _rule_lookup(rule_library)
    for rule_id, meta in library_lookup.items():
        if rule_id in FOCUS_PRIORITY:
            rows_by_rule.setdefault(rule_id, {}).update(meta)

    focus_rows = []
    for rule_id, row in rows_by_rule.items():
        if rule_id in {DEFAULT_RULE_ID, ""}:
            continue
        meta = library_lookup.get(rule_id, {})
        combined = {**meta, **row}
        filter_row = filter_lookup.get(rule_id, {})
        map_row = map_lookup.get(rule_id, {})
        score = _focus_score(combined, filter_row, map_row)
        if rule_id in FOCUS_PRIORITY or score > 0:
            focus_rows.append(
                {
                    "rank": 0,
                    "rule_id": rule_id,
                    "rule_name": _string(combined.get("rule_name")) or rule_id,
                    "rule_family": _string(combined.get("rule_family")),
                    "rule_type": _string(combined.get("rule_type")),
                    "independent_event_count": _optional_int(
                        combined.get("independent_event_count")
                    )
                    or 0,
                    "evidence_label": _string(combined.get("evidence_label")) or "TOO_EARLY",
                    "recommendation": _string(combined.get("recommendation")) or "KEEP_COLLECTING",
                    "focus_score": score,
                    "why_focus": _why_focus(combined, filter_row, map_row),
                    "what_to_watch_next_session": _watch_next_session(combined),
                    "what_data_needed": _focus_data_needed(combined),
                    "failure_condition": _failure_condition(combined),
                    "when_to_reassess": _when_to_reassess(combined),
                }
            )
    focus_rows.sort(
        key=lambda item: (
            FOCUS_PRIORITY.get(_string(item.get("rule_id")), 100),
            -float(item.get("focus_score") or 0.0),
            _string(item.get("rule_id")),
        )
    )
    for index, row in enumerate(focus_rows, start=1):
        row["rank"] = index
    return pl.DataFrame(focus_rows, schema=_focus_schema(), infer_schema_length=None)


def build_event_scorecard(
    *,
    promoted_outcomes: pl.DataFrame,
    event_level_outcomes: pl.DataFrame,
    pending_summary: pl.DataFrame,
    rule_event_evidence: pl.DataFrame,
    forward_scorecard: pl.DataFrame = pl.DataFrame(),
) -> pl.DataFrame:
    """Build an event-level scorecard that separates windows from events."""

    del forward_scorecard
    strongest = _strongest_event_candidate(rule_event_evidence)
    weakest = _weakest_event_candidate(rule_event_evidence)
    rules_with_sample_warning = _rules_with_sample_warning_count(rule_event_evidence)
    rows = [
        {
            "promoted_window_rows": promoted_outcomes.height,
            "independent_events": event_level_outcomes.height,
            "pending_events": pending_summary.height,
            "rules_with_events": _unique_count(event_level_outcomes, "rule_id"),
            "rules_with_sample_warning": rules_with_sample_warning,
            "strongest_event_level_candidate": strongest,
            "weakest_event_level_candidate": weakest,
            "current_research_label": _event_scorecard_label(
                event_count=event_level_outcomes.height,
                rules_with_sample_warning=rules_with_sample_warning,
                rule_count=_unique_count(event_level_outcomes, "rule_id"),
                rule_event_evidence=rule_event_evidence,
            ),
        }
    ]
    return pl.DataFrame(rows, schema=_event_scorecard_schema(), infer_schema_length=None)


def choose_final_recommendation(event_scorecard: pl.DataFrame) -> str:
    """Choose a conservative final recommendation for the event-level layer."""

    if event_scorecard.is_empty():
        return "TOO_EARLY_TO_JUDGE"
    row = event_scorecard.row(0, named=True)
    event_count = _optional_int(row.get("independent_events")) or 0
    rules_with_warning = _optional_int(row.get("rules_with_sample_warning")) or 0
    if event_count == 0:
        return "TOO_EARLY_TO_JUDGE"
    if rules_with_warning > 0:
        return "COLLECT_MORE_FORWARD_EVENTS"
    return FINAL_RECOMMENDATION


def forward_event_evidence_report_lines(
    result: ForwardEventEvidenceAggregatorResult | None,
) -> list[str]:
    """Return research_report.md sections for event evidence and governance."""

    if result is None:
        return [
            "## Event-Level Forward Evidence",
            "",
            "Event-level forward evidence aggregation was not run.",
        ]
    score = result.event_scorecard.row(0, named=True) if not result.event_scorecard.is_empty() else {}
    return [
        "## Event-Level Forward Evidence",
        "",
        _frame_markdown(_event_level_report_view(result.event_level_outcomes)),
        "",
        "## Rule-Level Event Evidence",
        "",
        _frame_markdown(result.rule_event_evidence),
        "",
        "## Rule Governance",
        "",
        _frame_markdown(result.rule_governance),
        "",
        "## Candidate Focus List",
        "",
        _frame_markdown(result.focus_list),
        "",
        "## Window Rows vs Independent Events Warning",
        "",
        f"- Promoted window rows: `{score.get('promoted_window_rows', 0)}`.",
        f"- Independent journal/rule events: `{score.get('independent_events', 0)}`.",
        "- Multiple outcome windows for the same journal/rule are one event for evidence review.",
        "- Frozen thresholds were not changed and no rule was moved to a money-readiness state.",
        "",
        "## Current Forward Evidence Label",
        "",
        f"- Current research label: `{score.get('current_research_label', '')}`.",
        f"- Final recommendation: `{result.final_recommendation}`.",
        f"- {RESEARCH_WARNING}",
    ]


def _aggregate_rule_context_rows(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not events:
        return []
    groups: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        groups.setdefault(_string(event.get("rule_id")), []).append(event)
    rows = []
    for rule_id, records in groups.items():
        if not rule_id:
            continue
        first = records[0]
        returns = [_optional_float(row.get("future_return_points")) for row in records]
        favorable = sum(1 for row in records if _bool(row.get("favorable_followthrough")))
        unfavorable = sum(1 for row in records if not _bool(row.get("favorable_followthrough")))
        rows.append(
            {
                **first,
                "rule_id": rule_id,
                "future_return_points": _mean(returns),
                "favorable_followthrough": favorable >= unfavorable,
                "trade_candidate": any(_bool(row.get("trade_candidate")) for row in records),
                "blocked_trade": any(_bool(row.get("blocked_trade")) for row in records),
                "level_touched": any(_bool(row.get("level_touched")) for row in records),
                "level_rejected": any(_bool(row.get("level_rejected")) for row in records),
                "level_accepted": any(_bool(row.get("level_accepted")) for row in records),
                "wall_touched": any(_bool(row.get("wall_touched")) for row in records),
                "wall_rejected": any(_bool(row.get("wall_rejected")) for row in records),
                "wall_accepted": any(_bool(row.get("wall_accepted")) for row in records),
                "sample_size_warning": any(
                    _bool(row.get("sample_size_warning")) for row in records
                ),
            }
        )
    return rows


def _context_rows_from_summary(
    promoted: dict[str, Any],
    summary_by_window: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    window = _string(promoted.get("outcome_window") or promoted.get("window"))
    rows = summary_by_window.get(window, [])
    if not rows:
        return []
    return [
        {
            "rule_id": row.get("rule_id"),
            "rule_name": row.get("rule_name"),
            "rule_family": row.get("rule_family"),
            "rule_type": row.get("rule_type"),
            "signal_context": row.get("signal_context"),
            "favorable_followthrough": (
                (_optional_float(row.get("support_rate")) or 0.0)
                >= (_optional_float(row.get("fail_rate")) or 0.0)
            ),
            "blocked_trade": _string(row.get("rule_type")).upper() in {"FILTER", "NO_TRADE"},
            "level_touched": (_optional_int(row.get("wall_touch_count")) or 0) > 0,
            "level_rejected": (_optional_int(row.get("wall_rejection_count")) or 0) > 0,
            "level_accepted": (_optional_int(row.get("wall_acceptance_count")) or 0) > 0,
            "wall_touched": (_optional_int(row.get("wall_touch_count")) or 0) > 0,
            "wall_rejected": (_optional_int(row.get("wall_rejection_count")) or 0) > 0,
            "wall_accepted": (_optional_int(row.get("wall_acceptance_count")) or 0) > 0,
            "sample_size_warning": _bool(row.get("sample_size_warning")),
        }
        for row in rows
    ]


def _sorted_windows(items: list[dict[str, Any]]) -> list[str]:
    windows = {
        _string(item.get("outcome_window") or item.get("window"))
        for item in items
        if _string(item.get("outcome_window") or item.get("window"))
    }
    return sorted(windows, key=lambda window: WINDOW_RANK.get(window, 999))


def _select_primary_window_row(items: list[dict[str, Any]], rule_type: str) -> dict[str, Any]:
    if not items:
        return {}
    upper_type = rule_type.upper()
    if upper_type in {"MARKET_MAP", "CONTEXT"}:
        with_wall = [item for item in items if _wall_touch(item) or _wall_rejection(item) or _wall_acceptance(item)]
        if with_wall:
            return _first_by_preference(with_wall, ["1h", "4h", "session_close", "next_day", "30m"])
        return _first_by_preference(items, ["1h", "4h", "session_close", "next_day", "30m"])
    if upper_type in {"FILTER", "NO_TRADE"}:
        return _first_by_preference(items, ["session_close", "next_day", "4h", "1h", "30m"])
    if upper_type == "RISK_RULE":
        adverse = sorted(
            items,
            key=lambda item: (
                _optional_float(item.get("mae")) is None,
                _optional_float(item.get("mae")) or 0.0,
            ),
        )
        if adverse:
            return adverse[0]
    return _first_by_preference(items, ["1h", "4h", "30m", "session_close", "next_day"])


def _first_by_preference(items: list[dict[str, Any]], preferences: list[str]) -> dict[str, Any]:
    by_window = {
        _string(item.get("outcome_window") or item.get("window")): item
        for item in items
    }
    for window in preferences:
        if window in by_window:
            return by_window[window]
    return sorted(
        items,
        key=lambda item: WINDOW_RANK.get(
            _string(item.get("outcome_window") or item.get("window")),
            999,
        ),
    )[0]


def _primary_window_result(row: dict[str, Any], rule_type: str) -> str:
    upper_type = rule_type.upper()
    if upper_type in {"FILTER", "NO_TRADE"}:
        helped = _filter_helped(row, rule_type)
        false_block = _filter_false_block(row, rule_type)
        if helped and false_block:
            return "mixed"
        if helped:
            return "supported"
        if false_block:
            return "failed"
        return "no_clear_outcome"
    if upper_type in {"MARKET_MAP", "CONTEXT"}:
        return "supported" if _wall_touch(row) else "no_clear_outcome"
    followthrough = row.get("favorable_followthrough")
    if followthrough is not None and _string(followthrough):
        return "supported" if _bool(followthrough) else "failed"
    return _row_result(row)


def _row_result(row: dict[str, Any]) -> str:
    result = _string(row.get("outcome_result")).lower()
    if result in {"supported", "failed", "mixed", "no_clear_outcome"}:
        return result
    close_return = _optional_float(row.get("close_return"))
    if close_return is None:
        return "no_clear_outcome"
    if close_return > 0:
        return "supported"
    if close_return < 0:
        return "failed"
    mfe = _optional_float(row.get("mfe")) or 0.0
    mae = _optional_float(row.get("mae")) or 0.0
    if mfe > 0 and mae < 0:
        return "mixed"
    return "no_clear_outcome"


def _event_outcome_label(
    *,
    primary_result: str,
    rule_type: str,
    supported_count: int,
    failed_count: int,
    mixed_count: int,
    filter_helped_any: bool,
    filter_false_block_any: bool,
    wall_touch_any: bool,
) -> str:
    upper_type = rule_type.upper()
    if upper_type in {"FILTER", "NO_TRADE"}:
        if filter_helped_any and filter_false_block_any:
            return "EVENT_MIXED"
        if filter_helped_any:
            return "EVENT_SUPPORTED"
        if filter_false_block_any:
            return "EVENT_FAILED"
        return "EVENT_NO_CLEAR_OUTCOME"
    if upper_type in {"MARKET_MAP", "CONTEXT"}:
        return "EVENT_SUPPORTED" if wall_touch_any else "EVENT_NO_CLEAR_OUTCOME"
    if primary_result == "supported":
        return "EVENT_SUPPORTED"
    if primary_result == "failed":
        return "EVENT_FAILED"
    if primary_result == "mixed" or mixed_count > 0 or (supported_count > 0 and failed_count > 0):
        return "EVENT_MIXED"
    return "EVENT_NO_CLEAR_OUTCOME"


def _earliest_window(items: list[dict[str, Any]], result: str) -> str:
    matching = [
        _string(item.get("outcome_window") or item.get("window"))
        for item in items
        if _row_result(item) == result
    ]
    if not matching:
        return ""
    return sorted(matching, key=lambda window: WINDOW_RANK.get(window, 999))[0]


def _event_quality(*, rule_type: str, primary_window: str, windows: list[str]) -> str:
    if not windows:
        return "INCOMPLETE"
    if len(windows) == 1:
        return "LOW"
    preferred = _preferred_windows(rule_type)
    if primary_window in preferred[:2] and len(windows) >= 3:
        return "HIGH"
    return "MEDIUM"


def _preferred_windows(rule_type: str) -> list[str]:
    upper_type = rule_type.upper()
    if upper_type in {"FILTER", "NO_TRADE"}:
        return ["session_close", "next_day", "4h", "1h", "30m"]
    if upper_type in {"MARKET_MAP", "CONTEXT"}:
        return ["1h", "4h", "session_close", "next_day", "30m"]
    if upper_type == "RISK_RULE":
        return ["4h", "session_close", "next_day", "1h", "30m"]
    return ["1h", "4h", "30m", "session_close", "next_day"]


def _dominant_rule_type(items: list[dict[str, Any]]) -> str:
    counts: dict[str, int] = {}
    for item in items:
        value = _string(item.get("rule_type")) or "OUTCOME_REVIEW"
        counts[value] = counts.get(value, 0) + 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _wall_touch(row: dict[str, Any]) -> bool:
    return _bool(row.get("wall_touch_any")) or _bool(row.get("wall_touched")) or _bool(
        row.get("level_touched")
    )


def _wall_rejection(row: dict[str, Any]) -> bool:
    return _bool(row.get("wall_rejection_any")) or _bool(row.get("wall_rejected")) or _bool(
        row.get("level_rejected")
    )


def _wall_acceptance(row: dict[str, Any]) -> bool:
    return _bool(row.get("wall_acceptance_any")) or _bool(row.get("wall_accepted")) or _bool(
        row.get("level_accepted")
    )


def _filter_helped(row: dict[str, Any], rule_type: str) -> bool:
    if _bool(row.get("no_trade_filter_helped")) or _bool(row.get("no_trade_filter_helped_any")):
        return True
    if rule_type.upper() not in {"FILTER", "NO_TRADE"}:
        return False
    if not _bool(row.get("blocked_trade")) and _string(row.get("event_type")).upper() != "BLOCK":
        return False
    return (_return_for_filter(row) or 0.0) < 0


def _filter_false_block(row: dict[str, Any], rule_type: str) -> bool:
    if _bool(row.get("no_trade_filter_false_block")) or _bool(
        row.get("no_trade_filter_false_block_any")
    ):
        return True
    if rule_type.upper() not in {"FILTER", "NO_TRADE"}:
        return False
    if not _bool(row.get("blocked_trade")) and _string(row.get("event_type")).upper() != "BLOCK":
        return False
    return (_return_for_filter(row) or 0.0) > 0


def _return_for_filter(row: dict[str, Any]) -> float | None:
    event_return = _optional_float(row.get("future_return_points"))
    if event_return is not None and abs(event_return) > 1e-12:
        return event_return
    return _optional_float(row.get("close_return"))


def _rule_event_label(
    *,
    rule_type: str,
    count: int,
    support_rate: float,
    fail_rate: float,
    filter_helped: int,
    filter_false: int,
    wall_touch: int,
) -> str:
    upper_type = rule_type.upper()
    if count < PROMISING_PILOT_MIN_EVENTS:
        return "TOO_EARLY"
    if count < MIN_EVENTS_FOR_REVIEW:
        if upper_type in {"FILTER", "NO_TRADE"} and filter_helped > filter_false:
            return "PROMISING_PILOT"
        if upper_type in {"MARKET_MAP", "CONTEXT"} and wall_touch / count >= 0.5:
            return "PROMISING_PILOT"
        if upper_type not in {"FILTER", "NO_TRADE", "MARKET_MAP", "CONTEXT"} and support_rate >= 0.55:
            return "PROMISING_PILOT"
        return "TOO_EARLY"
    if upper_type in {"FILTER", "NO_TRADE"}:
        return "FILTER_CANDIDATE" if filter_helped > filter_false else "WEAK_OR_FAILED"
    if upper_type in {"MARKET_MAP", "CONTEXT"}:
        return "MARKET_MAP_CANDIDATE" if wall_touch / count >= 0.4 else "NEEDS_MORE_FORWARD_DATA"
    if support_rate >= 0.55 and fail_rate <= 0.45:
        return "PROMISING_PILOT"
    if fail_rate > support_rate:
        return "WEAK_OR_FAILED"
    return "NEEDS_MORE_FORWARD_DATA"


def _governance_recommendation(row: dict[str, Any]) -> str:
    count = _optional_int(row.get("independent_event_count")) or 0
    label = _string(row.get("evidence_label"))
    rule_type = _string(row.get("rule_type")).upper()
    fail_rate = _optional_float(row.get("fail_rate_event_level")) or 0.0
    filter_helped = _optional_int(row.get("filter_helped_events")) or 0
    filter_false = _optional_int(row.get("filter_false_block_events")) or 0
    wall_touch = _optional_int(row.get("wall_touch_events")) or 0
    if count < MIN_EVENTS_FOR_REVIEW:
        if rule_type in {"FILTER", "NO_TRADE"} and label == "PROMISING_PILOT":
            return "KEEP_AS_FILTER_CANDIDATE"
        if rule_type in {"MARKET_MAP", "CONTEXT"} and (label == "PROMISING_PILOT" or wall_touch > 0):
            return "KEEP_AS_MARKET_MAP_CONTEXT"
        if fail_rate >= 0.7 or filter_false > filter_helped:
            return "WEAK_BUT_TOO_EARLY"
        return "KEEP_COLLECTING"
    if rule_type in {"FILTER", "NO_TRADE"} and label == "FILTER_CANDIDATE":
        return "KEEP_AS_FILTER_CANDIDATE"
    if rule_type in {"MARKET_MAP", "CONTEXT"} and label == "MARKET_MAP_CANDIDATE":
        return "KEEP_AS_MARKET_MAP_CONTEXT"
    if label == "WEAK_OR_FAILED":
        return "WATCH_CLOSELY"
    return "KEEP_COLLECTING"


def _governance_reason(
    *,
    count: int,
    label: str,
    rule_type: str,
    recommendation: str,
    fail_rate: float,
) -> str:
    base = (
        f"{count} independent journal/rule events are available; "
        f"{MIN_EVENTS_FOR_REVIEW} are required for formal review and "
        f"{MIN_EVENTS_FOR_VALIDATION} for validation review."
    )
    if recommendation == "KEEP_AS_FILTER_CANDIDATE":
        return base + " Filter behavior is useful enough to keep collecting, with no threshold changes."
    if recommendation == "KEEP_AS_MARKET_MAP_CONTEXT":
        return base + " Market-map behavior remains context for inspection, not an entry rule."
    if recommendation == "WEAK_BUT_TOO_EARLY":
        return base + f" Weak pilot behavior is visible (fail rate {fail_rate:.3f}) but sample size is low."
    if recommendation == "WATCH_CLOSELY":
        return base + " Evidence is weak enough to watch closely, but the frozen rule is not deleted here."
    if label == "PROMISING_PILOT":
        return base + " Pilot evidence is promising, but it is not enough to change the frozen rule."
    if rule_type in {"FILTER", "NO_TRADE"}:
        return base + " Keep collecting filter outcomes before review."
    return base + " Keep collecting forward events before review."


def _focus_score(
    row: dict[str, Any],
    filter_row: dict[str, Any],
    map_row: dict[str, Any],
) -> float:
    rule_id = _string(row.get("rule_id"))
    rule_type = _string(row.get("rule_type")).upper()
    count = _optional_int(row.get("independent_event_count")) or 0
    support = _optional_float(row.get("support_rate_event_level")) or 0.0
    helped = _optional_int(row.get("filter_helped_events")) or 0
    false_block = _optional_int(row.get("filter_false_block_events")) or 0
    touch = _optional_int(row.get("wall_touch_events")) or 0
    score = min(count / MIN_EVENTS_FOR_REVIEW, 1.0) + support
    if rule_type in {"FILTER", "NO_TRADE"}:
        score += max(helped - false_block, 0) / max(count, 1)
        score += 0.5 if _bool(filter_row.get("useful_filter_candidate")) else 0.0
    if rule_type in {"MARKET_MAP", "CONTEXT"}:
        score += touch / max(count, 1)
        score += 0.25 if _optional_float(map_row.get("map_hit_rate")) else 0.0
    if rule_id in FOCUS_PRIORITY:
        score += (10 - FOCUS_PRIORITY[rule_id]) / 10
    return score


def _why_focus(row: dict[str, Any], filter_row: dict[str, Any], map_row: dict[str, Any]) -> str:
    rule_type = _string(row.get("rule_type")).upper()
    label = _string(row.get("evidence_label")) or "TOO_EARLY"
    if rule_type in {"FILTER", "NO_TRADE"}:
        if _bool(filter_row.get("useful_filter_candidate")):
            return "Useful filter behavior is forming; keep checking avoided adverse moves versus false blocks."
        return "Filter behavior needs more event-level rows before review."
    if rule_type in {"MARKET_MAP", "CONTEXT"}:
        hit_rate = _optional_float(map_row.get("map_hit_rate"))
        if hit_rate is not None:
            return f"Market-map context has a current wall-touch hit rate near {hit_rate:.3f}."
        return "Market-map context needs more wall touch/rejection/acceptance observations."
    if label == "PROMISING_PILOT":
        return "Price-action confirmation has promising pilot event evidence."
    return "Price-action confirmation remains important but needs more independent events."


def _watch_next_session(row: dict[str, Any]) -> str:
    rule_type = _string(row.get("rule_type")).upper()
    if rule_type in {"FILTER", "NO_TRADE"}:
        return "Track blocked setups and whether later windows would have been adverse or favorable."
    if rule_type in {"MARKET_MAP", "CONTEXT"}:
        return "Track wall approach, touch, rejection, acceptance, and time-to-touch."
    return "Track whether 1h and 4h follow-through support the frozen trigger."


def _focus_data_needed(row: dict[str, Any]) -> str:
    rule_family = _string(row.get("rule_family")).upper()
    if "CME" in rule_family:
        return "Promoted intraday outcomes plus aligned CME wall, IV, basis, and OI context."
    return "Promoted 30m, 1h, 4h, session-close, and next-day outcome windows."


def _failure_condition(row: dict[str, Any]) -> str:
    rule_type = _string(row.get("rule_type")).upper()
    if rule_type in {"FILTER", "NO_TRADE"}:
        return "False blocks persistently exceed avoided adverse outcomes after review-size samples."
    if rule_type in {"MARKET_MAP", "CONTEXT"}:
        return "Wall touch/rejection/acceptance remains sparse after review-size samples."
    return "Failed events persistently exceed supported events after review-size samples."


def _when_to_reassess(row: dict[str, Any]) -> str:
    count = _optional_int(row.get("independent_event_count")) or 0
    remaining = max(MIN_EVENTS_FOR_REVIEW - count, 0)
    if remaining == 0:
        return "Reassess now at event-review size; still do not tune thresholds here."
    return f"Reassess after at least {remaining} more independent events for this rule."


def _strongest_event_candidate(rule_event_evidence: pl.DataFrame) -> str:
    if rule_event_evidence.is_empty():
        return ""
    candidates = []
    for row in _collapse_rule_event_rows_for_governance(rule_event_evidence):
        label = _string(row.get("evidence_label"))
        if label not in {"PROMISING_PILOT", "FILTER_CANDIDATE", "MARKET_MAP_CANDIDATE"}:
            continue
        rule_id = _string(row.get("rule_id"))
        score = (
            (_optional_float(row.get("support_rate_event_level")) or 0.0)
            + min((_optional_int(row.get("filter_helped_events")) or 0) / 20.0, 1.0)
            + min((_optional_int(row.get("wall_touch_events")) or 0) / 20.0, 1.0)
            + (1.0 if rule_id == "ACCEPTANCE_BREAKOUT" else 0.0)
        )
        candidates.append((score, FOCUS_PRIORITY.get(rule_id, 100), rule_id))
    if not candidates:
        return ""
    return sorted(candidates, key=lambda item: (-item[0], item[1], item[2]))[0][2]


def _weakest_event_candidate(rule_event_evidence: pl.DataFrame) -> str:
    if rule_event_evidence.is_empty():
        return ""
    candidates = []
    for row in _collapse_rule_event_rows_for_governance(rule_event_evidence):
        rule_id = _string(row.get("rule_id"))
        score = (
            (_optional_float(row.get("fail_rate_event_level")) or 0.0)
            + min((_optional_int(row.get("filter_false_block_events")) or 0) / 20.0, 1.0)
            - min((_optional_int(row.get("supported_events")) or 0) / 50.0, 0.5)
        )
        candidates.append((score, FOCUS_PRIORITY.get(rule_id, 100), rule_id))
    if not candidates:
        return ""
    return sorted(candidates, key=lambda item: (-item[0], item[1], item[2]))[0][2]


def _rules_with_sample_warning_count(rule_event_evidence: pl.DataFrame) -> int:
    if rule_event_evidence.is_empty():
        return 0
    return sum(
        1
        for row in _collapse_rule_event_rows_for_governance(rule_event_evidence)
        if _bool(row.get("event_sample_size_warning"))
    )


def _event_scorecard_label(
    *,
    event_count: int,
    rules_with_sample_warning: int,
    rule_count: int,
    rule_event_evidence: pl.DataFrame,
) -> str:
    if event_count == 0:
        return "TOO_EARLY_TO_JUDGE"
    if _has_promising_filters(rule_event_evidence):
        return "FILTER_CANDIDATES_FORMING"
    if _has_market_map_only(rule_event_evidence):
        return "MARKET_MAP_NEEDS_MORE_DATA"
    if rules_with_sample_warning > 0 or rule_count == 0:
        return "COLLECT_MORE_FORWARD_EVENTS"
    return "EVENT_LEVEL_EVIDENCE_READY"


def _has_promising_filters(frame: pl.DataFrame) -> bool:
    if frame.is_empty():
        return False
    for row in frame.to_dicts():
        if _string(row.get("rule_type")).upper() in {"FILTER", "NO_TRADE"} and _string(
            row.get("evidence_label")
        ) == "PROMISING_PILOT":
            return True
    return False


def _has_market_map_only(frame: pl.DataFrame) -> bool:
    if frame.is_empty():
        return False
    market_rows = [
        row
        for row in frame.to_dicts()
        if _string(row.get("rule_type")).upper() in {"MARKET_MAP", "CONTEXT"}
    ]
    return bool(market_rows) and all(
        _optional_int(row.get("wall_touch_events")) or 0 for row in market_rows
    )


def _event_level_report_view(frame: pl.DataFrame) -> pl.DataFrame:
    columns = [
        "journal_id",
        "rule_id",
        "rule_type",
        "windows_available",
        "primary_window",
        "primary_window_result",
        "event_outcome_label",
        "event_quality",
    ]
    return _select_existing(frame, columns)


def _input_warnings(
    *,
    paths: dict[str, Path],
    promoted: pl.DataFrame,
    preview: pl.DataFrame,
    preview_audit: pl.DataFrame,
    journal: pl.DataFrame,
) -> list[str]:
    warnings = []
    if promoted.is_empty():
        warnings.append("forward_evidence_outcomes_promoted.csv is missing or empty.")
    if preview.is_empty() and not paths["preview"].exists():
        warnings.append("forward_evidence_outcomes_preview.csv is missing.")
    if preview_audit.is_empty() and not paths["preview_audit"].exists():
        warnings.append("forward_outcome_preview_audit.csv is missing.")
    if journal.is_empty() and not paths["journal"].exists():
        warnings.append("forward_evidence_journal.csv is missing; promoted rows were used as source.")
    if not paths["frozen_rulebook"].exists() and not paths["rule_library"].exists():
        warnings.append("Frozen rulebook YAML and rule library CSV are missing.")
    if not paths["rulebook_hash"].exists():
        warnings.append("frozen_rulebook_v1_hash.txt is missing; hash was not rechecked here.")
    return warnings


def _warning_lines(warnings: Iterable[str]) -> list[str]:
    return [f"Input warning: {warning}" for warning in warnings]


def _write_markdown_table(
    path: Path,
    title: str,
    frame: pl.DataFrame,
    notes: list[str],
) -> None:
    lines = [title, "", _frame_markdown(frame), ""]
    lines.extend(f"- {note}" for note in notes)
    path.write_text(_safe_report_text("\n".join(lines)), encoding="utf-8")


def _write_scorecard_markdown(
    path: Path,
    scorecard: pl.DataFrame,
    *,
    final_recommendation: str,
) -> None:
    lines = [
        "# Forward Event Scorecard",
        "",
        _frame_markdown(scorecard),
        "",
        f"- Final recommendation: `{final_recommendation}`",
        "- Event counts are journal/rule events, not promoted outcome-window rows.",
        f"- {RESEARCH_WARNING}",
    ]
    path.write_text(_safe_report_text("\n".join(lines)), encoding="utf-8")


def _frame_markdown(frame: pl.DataFrame, *, limit: int = 20) -> str:
    if frame.is_empty():
        return "_No rows._"
    columns = frame.columns
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in frame.head(limit).to_dicts():
        lines.append("| " + " | ".join(_markdown_cell(row.get(column, "")) for column in columns) + " |")
    return "\n".join(lines)


def _markdown_cell(value: Any) -> str:
    text = str(value)
    text = re.sub(r"[A-Za-z]:\\[^\s|]+", "<REDACTED_PATH>", text)
    return text.replace("|", "\\|").replace("\n", " ")


def _safe_report_text(text: str) -> str:
    lower = text.lower()
    for phrase in FORBIDDEN_REPORT_PHRASES:
        if phrase in lower:
            raise ValueError(f"Forbidden report phrase: {phrase}")
    if re.search(r"[A-Za-z]:\\", text):
        raise ValueError("Report text contains an absolute local path.")
    return text


def _read_csv_frame(path: Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    try:
        return pl.read_csv(path, infer_schema_length=None)
    except Exception:
        return pl.DataFrame()


def _row_lookup(frame: pl.DataFrame, key_column: str) -> dict[str, dict[str, Any]]:
    if frame.is_empty() or key_column not in frame.columns:
        return {}
    result = {}
    for row in frame.to_dicts():
        key = _string(row.get(key_column))
        if key:
            result[key] = row
    return result


def _rule_lookup(rule_library: pl.DataFrame) -> dict[str, dict[str, Any]]:
    return _row_lookup(rule_library, "rule_id")


def _select_existing(frame: pl.DataFrame, columns: list[str]) -> pl.DataFrame:
    if frame.is_empty():
        return frame
    selected = [column for column in columns if column in frame.columns]
    return frame.select(selected) if selected else frame


def _event_session_date(row: dict[str, Any]) -> str:
    for key in ("session_date", "trade_date", "event_date"):
        value = _string(row.get(key))
        if value:
            return value[:10]
    parsed = _parse_datetime(row.get("observation_timestamp") or row.get("event_timestamp"))
    return parsed.date().isoformat() if parsed else ""


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return _ensure_utc(value)
    if isinstance(value, date):
        return datetime.combine(value, time(), tzinfo=UTC)
    text = _string(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            return datetime.combine(date.fromisoformat(text[:10]), time(), tzinfo=UTC)
        except ValueError:
            return None
    return _ensure_utc(parsed)


def _ensure_utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _string(value).lower() in {"true", "1", "yes", "y"}


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    text = _string(value)
    if not text:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    text = _string(value)
    if not text:
        return None
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return None


def _mean(values: Iterable[float | None]) -> float | None:
    clean = [value for value in values if value is not None]
    if not clean:
        return None
    return sum(clean) / len(clean)


def _max(values: Iterable[float | None]) -> float | None:
    clean = [value for value in values if value is not None]
    return max(clean) if clean else None


def _min(values: Iterable[float | None]) -> float | None:
    clean = [value for value in values if value is not None]
    return min(clean) if clean else None


def _adverse_to_favorable_ratio(
    average_mae: float | None,
    average_mfe: float | None,
) -> float | None:
    if average_mae is None or average_mfe is None or average_mfe <= 0:
        return None
    return abs(average_mae) / average_mfe


def _unique_count(frame: pl.DataFrame, column: str) -> int:
    if frame.is_empty() or column not in frame.columns:
        return 0
    return frame.select(column).unique().height


def _count_true(frame: pl.DataFrame, column: str) -> int:
    if frame.is_empty() or column not in frame.columns:
        return 0
    return sum(1 for value in frame.get_column(column).to_list() if _bool(value))


def _string(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _event_level_schema() -> dict[str, Any]:
    return {
        "journal_id": pl.String,
        "rule_id": pl.String,
        "rule_name": pl.String,
        "rule_family": pl.String,
        "rule_type": pl.String,
        "observation_timestamp": pl.String,
        "session_date": pl.String,
        "signal_context": pl.String,
        "windows_available": pl.String,
        "windows_supported_count": pl.Int64,
        "windows_failed_count": pl.Int64,
        "windows_mixed_count": pl.Int64,
        "windows_no_clear_count": pl.Int64,
        "earliest_supported_window": pl.String,
        "earliest_failed_window": pl.String,
        "primary_window": pl.String,
        "primary_window_result": pl.String,
        "event_outcome_label": pl.String,
        "close_return_primary": pl.Float64,
        "mfe_max": pl.Float64,
        "mae_max": pl.Float64,
        "wall_touch_any": pl.Boolean,
        "wall_rejection_any": pl.Boolean,
        "wall_acceptance_any": pl.Boolean,
        "no_trade_filter_helped_any": pl.Boolean,
        "no_trade_filter_false_block_any": pl.Boolean,
        "event_quality": pl.String,
    }


def _rule_event_schema() -> dict[str, Any]:
    return {
        "rule_id": pl.String,
        "rule_name": pl.String,
        "rule_family": pl.String,
        "rule_type": pl.String,
        "signal_context": pl.String,
        "independent_event_count": pl.Int64,
        "supported_events": pl.Int64,
        "failed_events": pl.Int64,
        "mixed_events": pl.Int64,
        "no_clear_events": pl.Int64,
        "support_rate_event_level": pl.Float64,
        "fail_rate_event_level": pl.Float64,
        "average_primary_return": pl.Float64,
        "average_mfe": pl.Float64,
        "average_mae": pl.Float64,
        "adverse_to_favorable_ratio": pl.Float64,
        "filter_helped_events": pl.Int64,
        "filter_false_block_events": pl.Int64,
        "wall_touch_events": pl.Int64,
        "wall_rejection_events": pl.Int64,
        "wall_acceptance_events": pl.Int64,
        "event_sample_size_warning": pl.Boolean,
        "evidence_label": pl.String,
    }


def _governance_schema() -> dict[str, Any]:
    return {
        "rule_id": pl.String,
        "rule_name": pl.String,
        "rule_family": pl.String,
        "independent_event_count": pl.Int64,
        "evidence_label": pl.String,
        "recommendation": pl.String,
        "reason": pl.String,
        "next_required_events": pl.Int64,
        "minimum_events_for_review": pl.Int64,
        "can_change_rule_now": pl.Boolean,
    }


def _focus_schema() -> dict[str, Any]:
    return {
        "rank": pl.Int64,
        "rule_id": pl.String,
        "rule_name": pl.String,
        "rule_family": pl.String,
        "rule_type": pl.String,
        "independent_event_count": pl.Int64,
        "evidence_label": pl.String,
        "recommendation": pl.String,
        "focus_score": pl.Float64,
        "why_focus": pl.String,
        "what_to_watch_next_session": pl.String,
        "what_data_needed": pl.String,
        "failure_condition": pl.String,
        "when_to_reassess": pl.String,
    }


def _event_scorecard_schema() -> dict[str, Any]:
    return {
        "promoted_window_rows": pl.Int64,
        "independent_events": pl.Int64,
        "pending_events": pl.Int64,
        "rules_with_events": pl.Int64,
        "rules_with_sample_warning": pl.Int64,
        "strongest_event_level_candidate": pl.String,
        "weakest_event_level_candidate": pl.String,
        "current_research_label": pl.String,
    }


def main() -> None:
    """CLI entry point for local event-level report generation."""

    result = run_forward_event_evidence_aggregator()
    row = result.event_scorecard.row(0, named=True) if not result.event_scorecard.is_empty() else {}
    print(f"promoted_window_rows: {row.get('promoted_window_rows', 0)}")
    print(f"independent_events: {row.get('independent_events', 0)}")
    print(f"current_research_label: {row.get('current_research_label', '')}")
    print(f"final_recommendation: {result.final_recommendation}")


if __name__ == "__main__":
    main()
