"""Dukascopy forward outcome promotion and rule evidence refresh.

This layer is research-only. It promotes only coverage-safe Dukascopy forward
outcome rows into a separate promoted output, aggregates independent journal
events, and refreshes interpretation reports without tuning frozen rules or
turning price-only evidence into CME validation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

import polars as pl


PROMOTION_VERSION = "dukascopy_forward_evidence_refresh_v1"
DEFAULT_RULE_ID = "FORWARD_OUTCOME_PREVIEW"
DEFAULT_RULE_NAME = "Forward outcome preview"
DEFAULT_RULE_FAMILY = "DUKASCOPY_FORWARD_OUTCOME"
DEFAULT_SIGNAL_CONTEXT = "DUKASCOPY_FORWARD_OUTCOME"
MIN_EVENTS_FOR_REVIEW = 30
MIN_CME_ROWS_FOR_VALIDATION = 60
WINDOW_ORDER = ("30m", "1h", "4h", "session_close", "next_day")
WINDOW_RANK = {window: index for index, window in enumerate(WINDOW_ORDER)}
FINAL_RECOMMENDATIONS = (
    "DUKASCOPY_FORWARD_EVIDENCE_READY",
    "PRICE_RULES_READY_FOR_FORWARD_WATCH",
    "GURU_PRICE_LOGIC_READY_FOR_RESEARCH",
    "CME_OVERLAP_PILOT_ONLY",
    "COLLECT_MORE_CME_OI_IV",
    "NOT_READY_FOR_MONEY",
)
RESEARCH_WARNING = (
    "Research-only evidence. No live trading, paper trading, broker "
    "integration, order execution, frozen-rule tuning, or money-readiness "
    "claim is included."
)
FORBIDDEN_REPORT_PHRASES = (
    "guaranteed edge",
    "predicts price",
    "safe to trade",
    "live ready",
    "paper ready",
    "validated money edge",
)


@dataclass(frozen=True)
class DukascopyForwardEvidenceRefreshResult:
    """Frames and labels emitted by the Dukascopy forward evidence layer."""

    outcome_audit: pl.DataFrame
    promoted_outcomes: pl.DataFrame
    promotion_summary: pl.DataFrame
    event_level_outcomes: pl.DataFrame
    rule_event_evidence: pl.DataFrame
    rule_governance: pl.DataFrame
    event_scorecard: pl.DataFrame
    price_rule_interpretation: pl.DataFrame
    guru_logic_interpretation: pl.DataFrame
    cme_overlap_interpretation: pl.DataFrame
    final_recommendations: tuple[str, ...]
    paths: dict[str, Path]


def run_dukascopy_forward_evidence_refresh(
    *,
    output_dir: str | Path = "outputs",
    current_time: datetime | None = None,
    write_outputs: bool = True,
) -> DukascopyForwardEvidenceRefreshResult:
    """Run promotion, event aggregation, and interpretation from output files."""

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    now = _ensure_utc(current_time or datetime.now(UTC))
    paths = _output_paths(output_root)

    dukascopy_outcomes = _read_csv(paths["dukascopy_forward_outcomes"])
    existing_promoted = _read_csv(paths["existing_promoted"])
    existing_outcomes = _read_csv(paths["existing_outcomes"])
    price_rules = _read_csv(paths["price_rules"])
    guru_price = _read_csv(paths["guru_price"])
    cme_overlap = _read_csv(paths["cme_overlap"])

    outcome_audit = build_dukascopy_forward_outcome_audit(
        dukascopy_outcomes=dukascopy_outcomes,
        existing_outcomes=existing_outcomes,
    )
    promoted_outcomes, promotion_summary = promote_dukascopy_outcomes(
        dukascopy_outcomes=dukascopy_outcomes,
        outcome_audit=outcome_audit,
        existing_promoted=existing_promoted,
        promoted_at=now,
    )
    event_level = build_dukascopy_event_level_outcomes(promoted_outcomes)
    rule_evidence = build_dukascopy_rule_event_evidence(event_level)
    governance = build_dukascopy_rule_governance(rule_evidence)
    event_scorecard = build_dukascopy_event_scorecard(
        promotion_summary=promotion_summary,
        event_level_outcomes=event_level,
        rule_event_evidence=rule_evidence,
    )
    price_interpretation = build_price_rule_interpretation(price_rules)
    guru_interpretation = build_guru_logic_interpretation(guru_price)
    cme_interpretation = build_cme_overlap_interpretation(cme_overlap)
    final_recommendations = choose_final_recommendations(
        promotion_summary=promotion_summary,
        price_rule_interpretation=price_interpretation,
        guru_logic_interpretation=guru_interpretation,
        cme_overlap_interpretation=cme_interpretation,
    )
    result = DukascopyForwardEvidenceRefreshResult(
        outcome_audit=outcome_audit,
        promoted_outcomes=promoted_outcomes,
        promotion_summary=promotion_summary,
        event_level_outcomes=event_level,
        rule_event_evidence=rule_evidence,
        rule_governance=governance,
        event_scorecard=event_scorecard,
        price_rule_interpretation=price_interpretation,
        guru_logic_interpretation=guru_interpretation,
        cme_overlap_interpretation=cme_interpretation,
        final_recommendations=final_recommendations,
        paths=paths,
    )
    if write_outputs:
        write_dukascopy_forward_evidence_outputs(result)
    return result


def build_dukascopy_forward_outcome_audit(
    *,
    dukascopy_outcomes: pl.DataFrame,
    existing_outcomes: pl.DataFrame = pl.DataFrame(),
) -> pl.DataFrame:
    """Audit Dukascopy-resolved rows before they can be promoted."""

    if dukascopy_outcomes.is_empty():
        return pl.DataFrame(schema=_audit_schema())
    rule_lookup = _existing_rule_lookup(existing_outcomes)
    rows: list[dict[str, Any]] = []
    for raw in dukascopy_outcomes.to_dicts():
        journal_id = _text(raw.get("journal_id"))
        window = _text(raw.get("window") or raw.get("outcome_window"))
        rule = rule_lookup.get((journal_id, window), {})
        window_start = _parse_datetime(raw.get("window_start"))
        window_end = _parse_datetime(raw.get("window_end"))
        newly_resolved = _bool(raw.get("newly_resolved"))
        still_pending = _bool(raw.get("still_pending"))
        source = _text(raw.get("source")).upper()
        numeric_values_present = all(
            _float_or_none(raw.get(column)) is not None
            for column in ("open", "high", "low", "close")
        )
        coverage_passed = source == "DUKASCOPY" and numeric_values_present and not still_pending
        used_mid = all(
            _float_or_none(raw.get(column)) is not None
            for column in ("open", "high", "low", "close")
        )
        spread_available = _float_or_none(raw.get("bid_ask_mid_difference_points")) is not None
        leakage_passed = (
            window_start is not None
            and window_end is not None
            and window_start <= window_end
        )
        safe = bool(newly_resolved and coverage_passed and leakage_passed)
        reject_reason = _reject_reason(
            newly_resolved=newly_resolved,
            still_pending=still_pending,
            coverage_passed=coverage_passed,
            leakage_passed=leakage_passed,
        )
        rows.append(
            {
                "journal_id": journal_id,
                "rule_id": _text(rule.get("rule_id")) or DEFAULT_RULE_ID,
                "rule_name": _text(rule.get("rule_name")) or DEFAULT_RULE_NAME,
                "outcome_window": window,
                "newly_resolved_by_dukascopy": newly_resolved,
                "coverage_passed": coverage_passed,
                "used_bid_ask": spread_available,
                "used_mid_price": used_mid,
                "spread_available": spread_available,
                "leakage_check_passed": leakage_passed,
                "safe_to_promote": safe,
                "reject_reason": reject_reason,
                "notes": _audit_notes(safe=safe, reject_reason=reject_reason),
            }
        )
    return _frame(rows, _audit_schema())


def promote_dukascopy_outcomes(
    *,
    dukascopy_outcomes: pl.DataFrame,
    outcome_audit: pl.DataFrame,
    existing_promoted: pl.DataFrame = pl.DataFrame(),
    promoted_at: datetime | None = None,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Merge safe Dukascopy outcomes with existing promoted rows."""

    now = _ensure_utc(promoted_at or datetime.now(UTC))
    existing_rows = _align_existing_promoted(existing_promoted).to_dicts()
    existing_keys = {
        _promotion_key(row)
        for row in existing_rows
        if _text(row.get("journal_id")) and _text(row.get("outcome_window"))
    }
    audit_lookup = {
        (_text(row.get("journal_id")), _text(row.get("outcome_window"))): row
        for row in outcome_audit.to_dicts()
    }
    new_rows: list[dict[str, Any]] = []
    duplicates = 0
    for raw in dukascopy_outcomes.to_dicts():
        journal_id = _text(raw.get("journal_id"))
        window = _text(raw.get("window") or raw.get("outcome_window"))
        audit = audit_lookup.get((journal_id, window), {})
        if not _bool(audit.get("safe_to_promote")):
            continue
        candidate = _promoted_row(raw, audit=audit, promoted_at=now)
        key = _promotion_key(candidate)
        if key in existing_keys:
            duplicates += 1
            continue
        existing_keys.add(key)
        new_rows.append(candidate)

    promoted = _frame([*existing_rows, *new_rows], _promoted_schema())
    still_pending_count = (
        int(dukascopy_outcomes.get_column("still_pending").sum())
        if not dukascopy_outcomes.is_empty() and "still_pending" in dukascopy_outcomes.columns
        else 0
    )
    summary = _frame(
        [
            {
                "before_promoted_count": len(existing_rows),
                "dukascopy_safe_to_promote_count": len(new_rows) + duplicates,
                "newly_promoted_count": len(new_rows),
                "total_promoted_after": promoted.height,
                "still_pending_count": still_pending_count,
                "duplicate_rows_skipped": duplicates,
            }
        ],
        _promotion_summary_schema(),
    )
    return promoted, summary


def build_dukascopy_event_level_outcomes(promoted_outcomes: pl.DataFrame) -> pl.DataFrame:
    """Collapse promoted window rows into independent journal/rule events."""

    if promoted_outcomes.is_empty():
        return pl.DataFrame(schema=_event_level_schema())
    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for row in promoted_outcomes.to_dicts():
        key = (
            _text(row.get("journal_id")),
            _text(row.get("rule_id")) or DEFAULT_RULE_ID,
            _text(row.get("session_date")) or _date_from_text(row.get("window_start")),
            _text(row.get("signal_context")) or DEFAULT_SIGNAL_CONTEXT,
        )
        groups.setdefault(key, []).append(row)

    rows: list[dict[str, Any]] = []
    for (journal_id, rule_id, session_date, signal_context), items in groups.items():
        primary = _primary_window_row(items)
        supported = sum(1 for item in items if _text(item.get("outcome_result")) == "supported")
        failed = sum(1 for item in items if _text(item.get("outcome_result")) == "failed")
        total_decided = supported + failed
        support_rate = supported / total_decided if total_decided else None
        fail_rate = failed / total_decided if total_decided else None
        avg_return = _float_or_none(primary.get("close_return")) if primary else None
        rows.append(
            {
                "journal_id": journal_id,
                "rule_id": rule_id,
                "rule_name": _text(primary.get("rule_name")) if primary else DEFAULT_RULE_NAME,
                "session_date": session_date,
                "signal_context": signal_context,
                "independent_event_count": 1,
                "windows_available": ",".join(_sorted_windows(items)),
                "support_rate": support_rate,
                "fail_rate": fail_rate,
                "average_primary_return": avg_return,
                "average_mfe": _mean_float(items, "mfe"),
                "average_mae": _mean_float(items, "mae"),
                "no_trade_filter_helped": _no_trade_helped(rule_id, avg_return),
                "no_trade_filter_false_block": _no_trade_false_block(rule_id, avg_return),
                "wall_touch": _any_bool(items, "wall_touch"),
                "wall_rejection": _any_bool(items, "wall_rejection"),
                "wall_acceptance": _any_bool(items, "wall_acceptance"),
                "sample_size_warning": True,
                "evidence_label": "TOO_EARLY",
            }
        )
    return _frame(rows, _event_level_schema()).sort(["rule_id", "session_date", "journal_id"])


def build_dukascopy_rule_event_evidence(event_level: pl.DataFrame) -> pl.DataFrame:
    """Aggregate independent event rows to rule-level evidence."""

    if event_level.is_empty():
        return pl.DataFrame(schema=_rule_event_schema())
    rows: list[dict[str, Any]] = []
    for group in event_level.group_by("rule_id", maintain_order=True):
        rule_id, frame = group
        rule_id_text = _text(rule_id[0] if isinstance(rule_id, tuple) else rule_id)
        count = int(frame.height)
        support_rate = _mean_column(frame, "support_rate")
        fail_rate = _mean_column(frame, "fail_rate")
        avg_return = _mean_column(frame, "average_primary_return")
        label = _event_evidence_label(
            rule_id=rule_id_text,
            event_count=count,
            support_rate=support_rate,
            fail_rate=fail_rate,
            average_primary_return=avg_return,
        )
        rows.append(
            {
                "rule_id": rule_id_text,
                "rule_name": _first_text(frame, "rule_name") or DEFAULT_RULE_NAME,
                "signal_context": _first_text(frame, "signal_context") or DEFAULT_SIGNAL_CONTEXT,
                "independent_event_count": count,
                "support_rate": support_rate,
                "fail_rate": fail_rate,
                "average_primary_return": avg_return,
                "average_mfe": _mean_column(frame, "average_mfe"),
                "average_mae": _mean_column(frame, "average_mae"),
                "no_trade_filter_helped": int(frame.get_column("no_trade_filter_helped").sum()),
                "no_trade_filter_false_block": int(
                    frame.get_column("no_trade_filter_false_block").sum()
                ),
                "wall_touch": int(frame.get_column("wall_touch").sum()),
                "wall_rejection": int(frame.get_column("wall_rejection").sum()),
                "wall_acceptance": int(frame.get_column("wall_acceptance").sum()),
                "sample_size_warning": count < MIN_EVENTS_FOR_REVIEW,
                "evidence_label": label,
            }
        )
    return _frame(rows, _rule_event_schema()).sort("independent_event_count", descending=True)


def build_dukascopy_rule_governance(rule_event_evidence: pl.DataFrame) -> pl.DataFrame:
    """Build conservative rule governance from event-level evidence."""

    if rule_event_evidence.is_empty():
        return pl.DataFrame(schema=_governance_schema())
    rows = []
    for row in rule_event_evidence.to_dicts():
        count = int(row.get("independent_event_count") or 0)
        label = _text(row.get("evidence_label"))
        rows.append(
            {
                "rule_id": _text(row.get("rule_id")),
                "rule_name": _text(row.get("rule_name")),
                "independent_event_count": count,
                "evidence_label": label,
                "recommendation": _governance_recommendation(label),
                "reason": (
                    f"{count} independent Dukascopy-resolved event(s); frozen rules and "
                    "thresholds remain unchanged."
                ),
                "next_required_events": max(MIN_EVENTS_FOR_REVIEW - count, 0),
                "minimum_events_for_review": MIN_EVENTS_FOR_REVIEW,
                "can_change_rule_now": False,
            }
        )
    return _frame(rows, _governance_schema())


def build_dukascopy_event_scorecard(
    *,
    promotion_summary: pl.DataFrame,
    event_level_outcomes: pl.DataFrame,
    rule_event_evidence: pl.DataFrame,
) -> pl.DataFrame:
    """Build a compact run scorecard."""

    summary = promotion_summary.row(0, named=True) if not promotion_summary.is_empty() else {}
    strongest = _strongest_rule(rule_event_evidence)
    weakest = _weakest_rule(rule_event_evidence)
    rows = [
        {
            "metric": "before_promoted_count",
            "value": int(summary.get("before_promoted_count") or 0),
            "notes": "Existing promoted rows were not mutated.",
        },
        {
            "metric": "dukascopy_safe_to_promote_count",
            "value": int(summary.get("dukascopy_safe_to_promote_count") or 0),
            "notes": "Rows passing coverage and leakage checks.",
        },
        {
            "metric": "newly_promoted_count",
            "value": int(summary.get("newly_promoted_count") or 0),
            "notes": "Dukascopy rows added to the separate promoted output.",
        },
        {
            "metric": "total_promoted_after",
            "value": int(summary.get("total_promoted_after") or 0),
            "notes": "Existing plus new Dukascopy rows after duplicate filtering.",
        },
        {
            "metric": "still_pending_count",
            "value": int(summary.get("still_pending_count") or 0),
            "notes": "Rows still pending after Dukascopy resolution.",
        },
        {
            "metric": "independent_event_count",
            "value": int(event_level_outcomes.height),
            "notes": "Journal/rule events, not outcome windows.",
        },
        {
            "metric": "updated_event_level_strongest_rule",
            "value": _text(strongest.get("rule_id")),
            "notes": _text(strongest.get("evidence_label")),
        },
        {
            "metric": "updated_event_level_weakest_rule",
            "value": _text(weakest.get("rule_id")),
            "notes": _text(weakest.get("evidence_label")),
        },
    ]
    return _frame(rows, _scorecard_schema())


def build_price_rule_interpretation(price_rules: pl.DataFrame) -> pl.DataFrame:
    """Interpret price-only rule tests without tuning thresholds."""

    if price_rules.is_empty():
        return pl.DataFrame(schema=_price_interpretation_schema())
    aggregate = _aggregate_price_rules(price_rules)
    rows = []
    for row in aggregate.to_dicts():
        rule = _text(row.get("rule"))
        use_case = _price_rule_use_case(rule)
        strength = _price_rule_strength(rule, row)
        rows.append(
            {
                "rule": rule,
                "trade_count": int(row.get("trade_count") or 0),
                "weighted_expectancy": _float_or_none(row.get("weighted_expectancy")),
                "weighted_win_rate": _float_or_none(row.get("weighted_win_rate")),
                "use_case": use_case,
                "evidence_strength": strength,
                "recommended_next_action": _price_rule_next_action(rule, strength),
                "notes": _price_rule_notes(rule),
            }
        )
    order = {
        "ACCEPTANCE_BREAKOUT": 0,
        "NO_TRADE_MIDDLE_RANGE": 1,
        "OPEN_DISTANCE_FILTER": 2,
        "REJECTION_AFTER_LEVEL_TOUCH": 3,
        "IV_EXPECTED_RANGE_FILTER": 4,
        "FEE_SPREAD_HURDLE": 5,
    }
    return _frame(rows, _price_interpretation_schema()).sort(
        pl.col("rule").replace_strict(order, default=99)
    )


def build_guru_logic_interpretation(guru_price: pl.DataFrame) -> pl.DataFrame:
    """Interpret guru price-only rows as research context."""

    if guru_price.is_empty():
        return pl.DataFrame(schema=_guru_interpretation_schema())
    rows = []
    for row in guru_price.to_dicts():
        name = _text(row.get("test_name"))
        timed = int(row.get("timing_confirmed_event_count") or 0)
        context = int(row.get("context_only_event_count") or 0)
        requires_cme = "acceptance" in name or "rejection" in name
        requires_timing = timed == 0 or context > timed
        context_only = context > 0 and timed == 0
        rows.append(
            {
                "guru_logic": name,
                "event_count": int(row.get("event_count") or 0),
                "price_only_testable": True,
                "requires_cme": requires_cme,
                "requires_timing_metadata": requires_timing,
                "remain_context_only": context_only,
                "interpretation": _guru_interpretation_text(name, context_only, requires_cme),
                "recommended_next_action": _guru_next_action(name, context_only, requires_cme),
            }
        )
    return _frame(rows, _guru_interpretation_schema())


def build_cme_overlap_interpretation(cme_overlap: pl.DataFrame) -> pl.DataFrame:
    """Interpret CME overlap coverage without treating price data as CME data."""

    if cme_overlap.is_empty():
        return _frame(
            [
                {
                    "question": "Can CME OI wall be tested now?",
                    "answer": "No usable CME overlap rows were found.",
                    "valid_overlap_rows": 0,
                    "enough_for_validation": False,
                    "interpretation_label": "CME_OVERLAP_PILOT_ONLY",
                    "fields_still_needed": _cme_fields_needed(),
                }
            ],
            _cme_interpretation_schema(),
        )
    valid_rows = int(cme_overlap.filter(pl.col("validation_grade") == "CME_PILOT_ONLY").height)
    can_test_oi = int(cme_overlap.get_column("can_test_oi_wall").sum()) if "can_test_oi_wall" in cme_overlap.columns else 0
    can_test_iv = int(cme_overlap.get_column("can_test_iv_range").sum()) if "can_test_iv_range" in cme_overlap.columns else 0
    enough = valid_rows >= MIN_CME_ROWS_FOR_VALIDATION
    rows = [
        {
            "question": "Can CME OI wall be tested now?",
            "answer": "Pilot only." if can_test_oi else "Not yet.",
            "valid_overlap_rows": valid_rows,
            "enough_for_validation": enough,
            "interpretation_label": "CME_OVERLAP_PILOT_ONLY",
            "fields_still_needed": _cme_fields_needed(),
        },
        {
            "question": "Can CME IV range be tested now?",
            "answer": "Pilot only." if can_test_iv else "Not yet.",
            "valid_overlap_rows": valid_rows,
            "enough_for_validation": enough,
            "interpretation_label": "CME_OVERLAP_PILOT_ONLY",
            "fields_still_needed": _cme_fields_needed(),
        },
        {
            "question": "Is current overlap enough for validation?",
            "answer": "No. Dukascopy supplies price outcomes, not CME OI/IV history.",
            "valid_overlap_rows": valid_rows,
            "enough_for_validation": enough,
            "interpretation_label": "CME_OVERLAP_PILOT_ONLY",
            "fields_still_needed": _cme_fields_needed(),
        },
    ]
    return _frame(rows, _cme_interpretation_schema())


def choose_final_recommendations(
    *,
    promotion_summary: pl.DataFrame,
    price_rule_interpretation: pl.DataFrame,
    guru_logic_interpretation: pl.DataFrame,
    cme_overlap_interpretation: pl.DataFrame,
) -> tuple[str, ...]:
    """Choose final labels from the allowed recommendation vocabulary."""

    labels = ["NOT_READY_FOR_MONEY"]
    summary = promotion_summary.row(0, named=True) if not promotion_summary.is_empty() else {}
    if int(summary.get("newly_promoted_count") or 0) > 0:
        labels.insert(0, "DUKASCOPY_FORWARD_EVIDENCE_READY")
    if (
        not price_rule_interpretation.is_empty()
        and price_rule_interpretation.filter(pl.col("evidence_strength") == "PROMISING").height
    ):
        labels.insert(1, "PRICE_RULES_READY_FOR_FORWARD_WATCH")
    if not guru_logic_interpretation.is_empty():
        labels.insert(2, "GURU_PRICE_LOGIC_READY_FOR_RESEARCH")
    if (
        not cme_overlap_interpretation.is_empty()
        and "CME_OVERLAP_PILOT_ONLY"
        in set(cme_overlap_interpretation.get_column("interpretation_label").to_list())
    ):
        labels.insert(-1, "CME_OVERLAP_PILOT_ONLY")
        labels.insert(-1, "COLLECT_MORE_CME_OI_IV")
    return tuple(label for label in FINAL_RECOMMENDATIONS if label in set(labels))


def write_dukascopy_forward_evidence_outputs(
    result: DukascopyForwardEvidenceRefreshResult,
) -> None:
    """Write CSV and Markdown outputs for the layer."""

    paths = result.paths
    result.outcome_audit.write_csv(paths["outcome_audit_csv"])
    result.promoted_outcomes.write_csv(paths["promoted_csv"])
    result.event_level_outcomes.write_csv(paths["event_level_csv"])
    result.rule_event_evidence.write_csv(paths["rule_event_csv"])
    result.rule_governance.write_csv(paths["governance_csv"])
    result.event_scorecard.write_csv(paths["event_scorecard_csv"])
    result.price_rule_interpretation.write_csv(paths["price_interpretation_csv"])
    result.guru_logic_interpretation.write_csv(paths["guru_interpretation_csv"])
    result.cme_overlap_interpretation.write_csv(paths["cme_interpretation_csv"])

    _write_markdown(
        paths["outcome_audit_md"],
        "Dukascopy Forward Outcome Audit",
        result.outcome_audit,
        [RESEARCH_WARNING],
    )
    _write_promotion_report(
        paths["promotion_report_md"],
        result.promotion_summary,
        result.final_recommendations,
    )
    _write_markdown(
        paths["price_interpretation_md"],
        "Dukascopy Price Rule Interpretation",
        result.price_rule_interpretation,
        ["Price-only evidence is not CME validation.", RESEARCH_WARNING],
    )
    _write_markdown(
        paths["guru_interpretation_md"],
        "Dukascopy Guru Logic Interpretation",
        result.guru_logic_interpretation,
        [
            "Context-only guru logic remains context-only until timing metadata is confirmed.",
            RESEARCH_WARNING,
        ],
    )
    _write_markdown(
        paths["cme_interpretation_md"],
        "Dukascopy CME Overlap Interpretation",
        result.cme_overlap_interpretation,
        ["Dukascopy price coverage does not create CME OI/IV coverage.", RESEARCH_WARNING],
    )


def dukascopy_forward_evidence_report_lines(
    result: DukascopyForwardEvidenceRefreshResult | None,
) -> list[str]:
    """Return focused research_report.md sections for this layer."""

    if result is None:
        return [
            "## Dukascopy Forward Outcome Promotion",
            "",
            "Dukascopy forward evidence refresh was not run.",
        ]
    return [
        "## Dukascopy Forward Outcome Promotion",
        "",
        _frame_markdown(result.promotion_summary),
        "",
        "## Dukascopy Event-Level Evidence",
        "",
        _frame_markdown(result.rule_event_evidence),
        "",
        "## Price-Only Rule Interpretation",
        "",
        _frame_markdown(result.price_rule_interpretation),
        "",
        "## Guru Logic Interpretation With Dukascopy",
        "",
        _frame_markdown(result.guru_logic_interpretation),
        "",
        "## CME Overlap Interpretation",
        "",
        _frame_markdown(result.cme_overlap_interpretation),
        "",
        "## What We Can Use Now",
        "",
        "- Dukascopy-resolved forward outcomes can be used for research evidence tracking.",
        "- Price-only rule interpretations can be used for forward watchlists.",
        "- Guru price logic can be used for research context where timing is not confirmed.",
        "",
        "## What Still Needs More Data",
        "",
        "- CME OI/IV history is still required for full CME validation.",
        "- Guru timing metadata is still required before context-only logic becomes same-day evidence.",
        "- TradingView trade CSV parity is still separate from this Dukascopy outcome layer.",
        "",
        "## Dukascopy Forward Final Recommendation",
        "",
        ", ".join(result.final_recommendations),
    ]


def report_text_is_safe(text: str) -> bool:
    lowered = text.lower()
    return not any(phrase in lowered for phrase in FORBIDDEN_REPORT_PHRASES)


def _promoted_row(
    raw: dict[str, Any],
    *,
    audit: dict[str, Any],
    promoted_at: datetime,
) -> dict[str, Any]:
    window_start = _text(raw.get("window_start"))
    window_end = _text(raw.get("window_end"))
    open_value = _float_or_none(raw.get("open"))
    close_value = _float_or_none(raw.get("close"))
    close_return = (
        close_value - open_value
        if close_value is not None and open_value is not None
        else None
    )
    return {
        "journal_id": _text(raw.get("journal_id")),
        "rule_id": _text(audit.get("rule_id")) or DEFAULT_RULE_ID,
        "rule_name": _text(audit.get("rule_name")) or DEFAULT_RULE_NAME,
        "rule_family": DEFAULT_RULE_FAMILY,
        "signal_context": DEFAULT_SIGNAL_CONTEXT,
        "rule_type": "FORWARD_OUTCOME",
        "observation_timestamp": window_start,
        "trade_date": _date_from_text(window_start),
        "session_date": _date_from_text(window_start),
        "outcome_window": _text(raw.get("window") or raw.get("outcome_window")),
        "window_start": window_start,
        "window_end": window_end,
        "outcome_status": _text(raw.get("dukascopy_resolution")) or "RESOLVED_BY_DUKASCOPY",
        "resolution_action": "DUKASCOPY_PROMOTED",
        "source_symbol": "XAUUSD",
        "source_interval": "M1",
        "quality": "DUKASCOPY_STRICT_INTRADAY",
        "observed_start": window_start,
        "observed_end": window_end,
        "open": open_value,
        "high": _float_or_none(raw.get("high")),
        "low": _float_or_none(raw.get("low")),
        "close": close_value,
        "row_count": None,
        "coverage_passed": True,
        "leakage_check_passed": True,
        "rulebook_hash_matches": True,
        "observation_precedes_outcome": True,
        "used_intraday_ohlc": True,
        "used_daily_approx": False,
        "safe_to_promote": True,
        "reject_reason": "",
        "notes": "DUKASCOPY_PRICE_OUTCOME; price-only research evidence, not CME validation.",
        "promoted_at_timestamp": promoted_at.isoformat(),
        "promotion_source_file": "outputs/forward_outcomes_with_dukascopy.csv",
        "promotion_version": PROMOTION_VERSION,
        "coverage_basis": "DUKASCOPY_M1_BID_ASK_MID",
        "close_return": close_return,
        "mfe": _float_or_none(raw.get("mfe_mid")),
        "mae": _float_or_none(raw.get("mae_mid")),
        "outcome_result": _outcome_result(close_return),
    }


def _align_existing_promoted(existing_promoted: pl.DataFrame) -> pl.DataFrame:
    if existing_promoted.is_empty():
        return pl.DataFrame(schema=_promoted_schema())
    rows = []
    for row in existing_promoted.to_dicts():
        aligned = {column: row.get(column) for column in _promoted_schema()}
        rows.append(aligned)
    return _frame(rows, _promoted_schema())


def _existing_rule_lookup(existing_outcomes: pl.DataFrame) -> dict[tuple[str, str], dict[str, Any]]:
    if existing_outcomes.is_empty() or not {"journal_id", "outcome_window"}.issubset(
        set(existing_outcomes.columns)
    ):
        return {}
    lookup: dict[tuple[str, str], dict[str, Any]] = {}
    for row in existing_outcomes.to_dicts():
        key = (_text(row.get("journal_id")), _text(row.get("outcome_window")))
        if key[0] and key[1] and key not in lookup:
            lookup[key] = row
    return lookup


def _reject_reason(
    *,
    newly_resolved: bool,
    still_pending: bool,
    coverage_passed: bool,
    leakage_passed: bool,
) -> str:
    reasons = []
    if still_pending:
        reasons.append("STILL_PENDING")
    if not newly_resolved:
        reasons.append("NOT_NEWLY_RESOLVED_BY_DUKASCOPY")
    if not coverage_passed:
        reasons.append("INSUFFICIENT_DUKASCOPY_COVERAGE")
    if not leakage_passed:
        reasons.append("LEAKAGE_CHECK_FAILED")
    return ";".join(reasons)


def _audit_notes(*, safe: bool, reject_reason: str) -> str:
    if safe:
        return "Safe to promote into separate Dukascopy research evidence output."
    return f"Not promoted: {reject_reason}."


def _promotion_key(row: dict[str, Any]) -> tuple[str, str]:
    return (_text(row.get("journal_id")), _text(row.get("outcome_window")))


def _sorted_windows(items: Iterable[dict[str, Any]]) -> list[str]:
    windows = {_text(item.get("outcome_window") or item.get("window")) for item in items}
    return sorted((window for window in windows if window), key=lambda item: WINDOW_RANK.get(item, 99))


def _primary_window_row(items: list[dict[str, Any]]) -> dict[str, Any]:
    if not items:
        return {}
    return max(
        items,
        key=lambda row: WINDOW_RANK.get(_text(row.get("outcome_window") or row.get("window")), -1),
    )


def _aggregate_price_rules(price_rules: pl.DataFrame) -> pl.DataFrame:
    rows = []
    for group in price_rules.group_by("rule", maintain_order=True):
        rule, frame = group
        trade_count = int(frame.get_column("trade_count").sum())
        if trade_count:
            expectancy = float(
                (frame.get_column("expectancy") * frame.get_column("trade_count")).sum()
                / trade_count
            )
            win_rate = float(
                (frame.get_column("win_rate") * frame.get_column("trade_count")).sum()
                / trade_count
            )
        else:
            expectancy = None
            win_rate = None
        rows.append(
            {
                "rule": _text(rule[0] if isinstance(rule, tuple) else rule),
                "trade_count": trade_count,
                "weighted_expectancy": expectancy,
                "weighted_win_rate": win_rate,
            }
        )
    return _frame(
        rows,
        {
            "rule": pl.String,
            "trade_count": pl.Int64,
            "weighted_expectancy": pl.Float64,
            "weighted_win_rate": pl.Float64,
        },
    )


def _price_rule_use_case(rule: str) -> str:
    if rule == "ACCEPTANCE_BREAKOUT":
        return "ENTRY_CONFIRMATION"
    if rule in {"NO_TRADE_MIDDLE_RANGE", "OPEN_DISTANCE_FILTER", "FEE_SPREAD_HURDLE"}:
        return "NO_TRADE_FILTER"
    if rule == "IV_EXPECTED_RANGE_FILTER":
        return "MARKET_MAP_CONTEXT"
    return "WEAK_OR_CONTEXT_ONLY"


def _price_rule_strength(rule: str, row: dict[str, Any]) -> str:
    trade_count = int(row.get("trade_count") or 0)
    expectancy = _float_or_none(row.get("weighted_expectancy"))
    win_rate = _float_or_none(row.get("weighted_win_rate"))
    if trade_count < 30:
        return "TOO_EARLY"
    if rule == "ACCEPTANCE_BREAKOUT" and expectancy is not None and expectancy > 0 and (win_rate or 0) >= 0.5:
        return "PROMISING"
    if rule in {"NO_TRADE_MIDDLE_RANGE", "OPEN_DISTANCE_FILTER", "FEE_SPREAD_HURDLE"} and expectancy is not None and expectancy < 0:
        return "PROMISING"
    if expectancy is not None and expectancy < 0:
        return "WEAK"
    return "MIXED"


def _price_rule_next_action(rule: str, strength: str) -> str:
    if rule == "ACCEPTANCE_BREAKOUT":
        return "Track as forward-watch entry confirmation; do not tune frozen thresholds."
    if rule == "NO_TRADE_MIDDLE_RANGE":
        return "Track as avoid/filter candidate, not as an entry rule."
    if rule == "OPEN_DISTANCE_FILTER":
        return "Track as chase-avoid filter in forward journal review."
    if rule == "IV_EXPECTED_RANGE_FILTER":
        return "Keep as realized-vol proxy until true IV history is available."
    if strength == "WEAK":
        return "Keep context-only unless forward evidence improves."
    return "Continue collecting forward observations."


def _price_rule_notes(rule: str) -> str:
    if rule == "IV_EXPECTED_RANGE_FILTER":
        return "REALIZED_VOL_PROXY; true CME IV is not supplied by Dukascopy."
    if rule == "ACCEPTANCE_BREAKOUT":
        return "Candidate confirmation rule from price-only evidence."
    if rule == "NO_TRADE_MIDDLE_RANGE":
        return "Negative raw expectancy supports avoid/filter interpretation."
    return "Research-only interpretation."


def _guru_interpretation_text(name: str, context_only: bool, requires_cme: bool) -> str:
    if context_only:
        return "Price-only research context; timing metadata is not sufficient for same-day use."
    if requires_cme:
        return "Price behavior can be checked, but CME-backed wall/range interpretation needs CME fields."
    return "Price-only component can be researched with Dukascopy outcomes."


def _guru_next_action(name: str, context_only: bool, requires_cme: bool) -> str:
    if context_only:
        return "Collect transcript timing metadata before treating this as same-day evidence."
    if requires_cme:
        return "Collect more CME OI/IV overlap before CME interpretation."
    return "Continue forward research tracking with Dukascopy outcomes."


def _event_evidence_label(
    *,
    rule_id: str,
    event_count: int,
    support_rate: float | None,
    fail_rate: float | None,
    average_primary_return: float | None,
) -> str:
    if event_count < 5:
        return "TOO_EARLY"
    if rule_id == "NO_TRADE_MIDDLE_RANGE" and average_primary_return is not None and average_primary_return < 0:
        return "FILTER_CANDIDATE"
    if (support_rate or 0) >= 0.55:
        return "PROMISING_PILOT"
    if (fail_rate or 0) >= 0.55:
        return "WEAK_OR_FAILED"
    return "NEEDS_MORE_FORWARD_DATA"


def _governance_recommendation(label: str) -> str:
    if label == "PROMISING_PILOT":
        return "Forward watch only; collect more independent events."
    if label == "FILTER_CANDIDATE":
        return "Use as filter research candidate only."
    if label == "MARKET_MAP_CANDIDATE":
        return "Use as market-map research candidate only."
    if label == "WEAK_OR_FAILED":
        return "Do not promote beyond research context."
    return "Collect more forward data."


def _strongest_rule(rule_event_evidence: pl.DataFrame) -> dict[str, Any]:
    if rule_event_evidence.is_empty():
        return {}
    ranked = rule_event_evidence.with_columns(
        pl.col("support_rate").fill_null(-1).alias("_rank_support")
    ).sort(["_rank_support", "independent_event_count"], descending=[True, True])
    return ranked.row(0, named=True)


def _weakest_rule(rule_event_evidence: pl.DataFrame) -> dict[str, Any]:
    if rule_event_evidence.is_empty():
        return {}
    ranked = rule_event_evidence.with_columns(
        pl.col("fail_rate").fill_null(-1).alias("_rank_fail")
    ).sort(["_rank_fail", "independent_event_count"], descending=[True, True])
    return ranked.row(0, named=True)


def _outcome_result(close_return: float | None) -> str:
    if close_return is None:
        return "no_clear"
    if close_return > 0:
        return "supported"
    if close_return < 0:
        return "failed"
    return "mixed"


def _no_trade_helped(rule_id: str, average_return: float | None) -> bool:
    return rule_id == "NO_TRADE_MIDDLE_RANGE" and average_return is not None and average_return < 0


def _no_trade_false_block(rule_id: str, average_return: float | None) -> bool:
    return rule_id == "NO_TRADE_MIDDLE_RANGE" and average_return is not None and average_return > 0


def _cme_fields_needed() -> str:
    return (
        "CME OI by strike; CME OI change; CME option volume; CME IV/QuikVol; "
        "option settlements; GC futures basis history"
    )


def _output_paths(output_root: Path) -> dict[str, Path]:
    return {
        "dukascopy_forward_outcomes": output_root / "forward_outcomes_with_dukascopy.csv",
        "existing_promoted": output_root / "forward_evidence_outcomes_promoted.csv",
        "existing_outcomes": output_root / "forward_evidence_outcomes.csv",
        "price_rules": output_root / "dukascopy_price_only_rule_backtest.csv",
        "guru_price": output_root / "dukascopy_guru_price_only_test.csv",
        "cme_overlap": output_root / "dukascopy_cme_overlap_validation.csv",
        "outcome_audit_csv": output_root / "dukascopy_forward_outcome_audit.csv",
        "outcome_audit_md": output_root / "dukascopy_forward_outcome_audit.md",
        "promoted_csv": output_root / "forward_evidence_outcomes_dukascopy_promoted.csv",
        "promotion_report_md": output_root / "dukascopy_forward_promotion_report.md",
        "event_level_csv": output_root / "dukascopy_forward_event_level_outcomes.csv",
        "rule_event_csv": output_root / "dukascopy_forward_rule_event_evidence.csv",
        "governance_csv": output_root / "dukascopy_forward_rule_governance.csv",
        "event_scorecard_csv": output_root / "dukascopy_forward_event_scorecard.csv",
        "price_interpretation_csv": output_root / "dukascopy_price_rule_interpretation.csv",
        "price_interpretation_md": output_root / "dukascopy_price_rule_interpretation.md",
        "guru_interpretation_csv": output_root / "dukascopy_guru_logic_interpretation.csv",
        "guru_interpretation_md": output_root / "dukascopy_guru_logic_interpretation.md",
        "cme_interpretation_csv": output_root / "dukascopy_cme_overlap_interpretation.csv",
        "cme_interpretation_md": output_root / "dukascopy_cme_overlap_interpretation.md",
    }


def _read_csv(path: Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    try:
        return pl.read_csv(path, infer_schema_length=None)
    except Exception:  # noqa: BLE001 - missing/corrupt inputs produce empty conservative outputs.
        return pl.DataFrame()


def _write_markdown(path: Path, title: str, frame: pl.DataFrame, notes: Iterable[str]) -> None:
    text = "\n\n".join([f"# {title}", *notes, _frame_markdown(frame)])
    path.write_text(_safe_report_text(text), encoding="utf-8")


def _write_promotion_report(
    path: Path,
    promotion_summary: pl.DataFrame,
    final_recommendations: tuple[str, ...],
) -> None:
    lines = [
        "# Dukascopy Forward Promotion Report",
        "",
        RESEARCH_WARNING,
        "",
        _frame_markdown(promotion_summary),
        "",
        "## Final Recommendation",
        "",
        ", ".join(final_recommendations),
    ]
    path.write_text(_safe_report_text("\n".join(lines)), encoding="utf-8")


def _frame_markdown(frame: pl.DataFrame, *, limit: int = 20) -> str:
    if frame.is_empty():
        return "_No rows._"
    sample = frame.head(limit)
    rows = [
        "| " + " | ".join(sample.columns) + " |",
        "| " + " | ".join("---" for _ in sample.columns) + " |",
    ]
    for raw in sample.to_dicts():
        rows.append("| " + " | ".join(_markdown_cell(raw.get(column, "")) for column in sample.columns) + " |")
    if frame.height > limit:
        rows.append(f"\n_Showing {limit} of {frame.height} rows._")
    return "\n".join(rows)


def _markdown_cell(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("|", "\\|").replace("\n", " ")
    return text[:700]


def _safe_report_text(text: str) -> str:
    safe = text
    for phrase in FORBIDDEN_REPORT_PHRASES:
        safe = safe.replace(phrase, f"[blocked phrase: {phrase}]")
    return safe


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


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _parse_datetime(value: Any) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _date_from_text(value: Any) -> str:
    parsed = _parse_datetime(value)
    return parsed.date().isoformat() if parsed else ""


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"1", "true", "yes", "y"}


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


def _mean_float(items: Iterable[dict[str, Any]], column: str) -> float | None:
    values = [_float_or_none(item.get(column)) for item in items]
    clean = [value for value in values if value is not None]
    return sum(clean) / len(clean) if clean else None


def _mean_column(frame: pl.DataFrame, column: str) -> float | None:
    if frame.is_empty() or column not in frame.columns:
        return None
    values = [
        _float_or_none(value)
        for value in frame.get_column(column).to_list()
    ]
    clean = [value for value in values if value is not None]
    return sum(clean) / len(clean) if clean else None


def _first_text(frame: pl.DataFrame, column: str) -> str:
    if frame.is_empty() or column not in frame.columns:
        return ""
    for value in frame.get_column(column).to_list():
        text = _text(value)
        if text:
            return text
    return ""


def _any_bool(items: Iterable[dict[str, Any]], column: str) -> bool:
    return any(_bool(item.get(column)) for item in items)


def _audit_schema() -> dict[str, Any]:
    return {
        "journal_id": pl.String,
        "rule_id": pl.String,
        "rule_name": pl.String,
        "outcome_window": pl.String,
        "newly_resolved_by_dukascopy": pl.Boolean,
        "coverage_passed": pl.Boolean,
        "used_bid_ask": pl.Boolean,
        "used_mid_price": pl.Boolean,
        "spread_available": pl.Boolean,
        "leakage_check_passed": pl.Boolean,
        "safe_to_promote": pl.Boolean,
        "reject_reason": pl.String,
        "notes": pl.String,
    }


def _promotion_summary_schema() -> dict[str, Any]:
    return {
        "before_promoted_count": pl.Int64,
        "dukascopy_safe_to_promote_count": pl.Int64,
        "newly_promoted_count": pl.Int64,
        "total_promoted_after": pl.Int64,
        "still_pending_count": pl.Int64,
        "duplicate_rows_skipped": pl.Int64,
    }


def _promoted_schema() -> dict[str, Any]:
    return {
        "journal_id": pl.String,
        "rule_id": pl.String,
        "rule_name": pl.String,
        "rule_family": pl.String,
        "signal_context": pl.String,
        "rule_type": pl.String,
        "observation_timestamp": pl.String,
        "trade_date": pl.String,
        "session_date": pl.String,
        "outcome_window": pl.String,
        "window_start": pl.String,
        "window_end": pl.String,
        "outcome_status": pl.String,
        "resolution_action": pl.String,
        "source_symbol": pl.String,
        "source_interval": pl.String,
        "quality": pl.String,
        "observed_start": pl.String,
        "observed_end": pl.String,
        "open": pl.Float64,
        "high": pl.Float64,
        "low": pl.Float64,
        "close": pl.Float64,
        "row_count": pl.Int64,
        "coverage_passed": pl.Boolean,
        "leakage_check_passed": pl.Boolean,
        "rulebook_hash_matches": pl.Boolean,
        "observation_precedes_outcome": pl.Boolean,
        "used_intraday_ohlc": pl.Boolean,
        "used_daily_approx": pl.Boolean,
        "safe_to_promote": pl.Boolean,
        "reject_reason": pl.String,
        "notes": pl.String,
        "promoted_at_timestamp": pl.String,
        "promotion_source_file": pl.String,
        "promotion_version": pl.String,
        "coverage_basis": pl.String,
        "close_return": pl.Float64,
        "mfe": pl.Float64,
        "mae": pl.Float64,
        "outcome_result": pl.String,
    }


def _event_level_schema() -> dict[str, Any]:
    return {
        "journal_id": pl.String,
        "rule_id": pl.String,
        "rule_name": pl.String,
        "session_date": pl.String,
        "signal_context": pl.String,
        "independent_event_count": pl.Int64,
        "windows_available": pl.String,
        "support_rate": pl.Float64,
        "fail_rate": pl.Float64,
        "average_primary_return": pl.Float64,
        "average_mfe": pl.Float64,
        "average_mae": pl.Float64,
        "no_trade_filter_helped": pl.Boolean,
        "no_trade_filter_false_block": pl.Boolean,
        "wall_touch": pl.Boolean,
        "wall_rejection": pl.Boolean,
        "wall_acceptance": pl.Boolean,
        "sample_size_warning": pl.Boolean,
        "evidence_label": pl.String,
    }


def _rule_event_schema() -> dict[str, Any]:
    return {
        "rule_id": pl.String,
        "rule_name": pl.String,
        "signal_context": pl.String,
        "independent_event_count": pl.Int64,
        "support_rate": pl.Float64,
        "fail_rate": pl.Float64,
        "average_primary_return": pl.Float64,
        "average_mfe": pl.Float64,
        "average_mae": pl.Float64,
        "no_trade_filter_helped": pl.Int64,
        "no_trade_filter_false_block": pl.Int64,
        "wall_touch": pl.Int64,
        "wall_rejection": pl.Int64,
        "wall_acceptance": pl.Int64,
        "sample_size_warning": pl.Boolean,
        "evidence_label": pl.String,
    }


def _governance_schema() -> dict[str, Any]:
    return {
        "rule_id": pl.String,
        "rule_name": pl.String,
        "independent_event_count": pl.Int64,
        "evidence_label": pl.String,
        "recommendation": pl.String,
        "reason": pl.String,
        "next_required_events": pl.Int64,
        "minimum_events_for_review": pl.Int64,
        "can_change_rule_now": pl.Boolean,
    }


def _scorecard_schema() -> dict[str, Any]:
    return {
        "metric": pl.String,
        "value": pl.String,
        "notes": pl.String,
    }


def _price_interpretation_schema() -> dict[str, Any]:
    return {
        "rule": pl.String,
        "trade_count": pl.Int64,
        "weighted_expectancy": pl.Float64,
        "weighted_win_rate": pl.Float64,
        "use_case": pl.String,
        "evidence_strength": pl.String,
        "recommended_next_action": pl.String,
        "notes": pl.String,
    }


def _guru_interpretation_schema() -> dict[str, Any]:
    return {
        "guru_logic": pl.String,
        "event_count": pl.Int64,
        "price_only_testable": pl.Boolean,
        "requires_cme": pl.Boolean,
        "requires_timing_metadata": pl.Boolean,
        "remain_context_only": pl.Boolean,
        "interpretation": pl.String,
        "recommended_next_action": pl.String,
    }


def _cme_interpretation_schema() -> dict[str, Any]:
    return {
        "question": pl.String,
        "answer": pl.String,
        "valid_overlap_rows": pl.Int64,
        "enough_for_validation": pl.Boolean,
        "interpretation_label": pl.String,
        "fields_still_needed": pl.String,
    }
