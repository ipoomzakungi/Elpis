"""Forward outcome preview audit, promotion, and evidence summaries.

This layer is research-only. It reviews already-generated preview outcomes,
promotes only rows that pass conservative coverage and leakage checks, and
summarizes frozen-rule evidence without tuning rules or changing journal
observations.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any, Iterable

import polars as pl

from research_xau_vol_oi.daily_forward_data_gate import INTRADAY_WINDOWS, WINDOW_ORDER


STRICT_INTRADAY_WINDOWS = set(INTRADAY_WINDOWS)
DAILY_APPROX_ALLOWED_WINDOWS = {"session_close", "next_day"}
PROMOTION_VERSION = "forward_outcome_review_v1"
MIN_VALIDATION_EVENTS = 30
PILOT_EVENT_FLOOR = 5
DEFAULT_RULE_ID = "FORWARD_OUTCOME_PREVIEW"
DEFAULT_RULE_NAME = "Forward outcome preview"
DEFAULT_RULE_FAMILY = "FORWARD_OUTCOME"
RESEARCH_WARNING = (
    "Research-only evidence. No live trading, paper trading, broker "
    "integration, order execution, or money-readiness claim is included."
)
FORBIDDEN_REPORT_PHRASES = (
    "profitable",
    "guaranteed edge",
    "predicts price",
    "safe to trade",
    "live ready",
    "validated money edge",
)


@dataclass(frozen=True)
class ForwardOutcomeReviewResult:
    """Frames and labels emitted by the forward outcome review layer."""

    preview_audit: pl.DataFrame
    promoted_batch: pl.DataFrame
    official_outcomes: pl.DataFrame
    rule_evidence_summary: pl.DataFrame
    filter_evidence: pl.DataFrame
    market_map_evidence: pl.DataFrame
    pending_summary: pl.DataFrame
    evidence_scorecard: pl.DataFrame
    final_recommendation: str
    paths: dict[str, Path]
    input_warnings: tuple[str, ...]


def run_forward_outcome_review(
    *,
    output_dir: str | Path = "outputs",
    repo_root: str | Path = ".",
    current_time: datetime | None = None,
    write_outputs: bool = True,
) -> ForwardOutcomeReviewResult:
    """Run audit, promotion, and summary generation from local output files."""

    del repo_root
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    now = _ensure_utc(current_time or datetime.now(UTC))

    paths = {
        "preview": output_root / "forward_evidence_outcomes_preview.csv",
        "journal": output_root / "forward_evidence_journal.csv",
        "coverage": output_root / "outcome_coverage_check.csv",
        "partial_resolution": output_root / "partial_outcome_resolution.csv",
        "rulebook_hash": output_root / "frozen_rulebook_v1_hash.txt",
        "experiment_registry": output_root / "experiment_registry.csv",
        "official_outcomes": output_root / "forward_evidence_outcomes.csv",
        "preview_audit_csv": output_root / "forward_outcome_preview_audit.csv",
        "preview_audit_md": output_root / "forward_outcome_preview_audit.md",
        "promoted_csv": output_root / "forward_evidence_outcomes_promoted.csv",
        "promotion_report_md": output_root / "forward_outcome_promotion_report.md",
        "rule_summary_csv": output_root / "forward_rule_evidence_summary.csv",
        "rule_summary_md": output_root / "forward_rule_evidence_summary.md",
        "filter_evidence_csv": output_root / "forward_filter_evidence.csv",
        "filter_evidence_md": output_root / "forward_filter_evidence.md",
        "market_map_evidence_csv": output_root / "forward_market_map_evidence.csv",
        "market_map_evidence_md": output_root / "forward_market_map_evidence.md",
        "pending_summary_csv": output_root / "forward_pending_outcome_summary.csv",
        "pending_summary_md": output_root / "forward_pending_outcome_summary.md",
        "scorecard_csv": output_root / "forward_evidence_scorecard.csv",
        "scorecard_md": output_root / "forward_evidence_scorecard.md",
    }

    preview = _read_csv_frame(paths["preview"])
    journal = _read_csv_frame(paths["journal"])
    coverage = _read_csv_frame(paths["coverage"])
    partial_resolution = _read_csv_frame(paths["partial_resolution"])
    experiment_registry = _read_csv_frame(paths["experiment_registry"])
    rule_library = _read_csv_frame(output_root / "guru_rule_library.csv")
    rule_backtest_summary = _read_csv_frame(output_root / "guru_rule_backtest_summary.csv")
    rule_events = _read_csv_frame(output_root / "guru_rule_backtest_events.csv")
    status_scorecard = _read_csv_frame(output_root / "forward_journal_scorecard.csv")
    official_existing = _read_csv_frame(paths["official_outcomes"])
    expected_rulebook_hash = _read_text(paths["rulebook_hash"]).strip()
    if not expected_rulebook_hash:
        expected_rulebook_hash = _frame_digest(rule_library)

    input_warnings = tuple(
        _input_warnings(
            paths=paths,
            preview=preview,
            journal=journal,
            experiment_registry=experiment_registry,
            expected_rulebook_hash=expected_rulebook_hash,
        )
    )
    preview_audit = build_preview_outcome_audit(
        preview=preview,
        journal=journal,
        coverage=coverage,
        rule_library=rule_library,
        expected_rulebook_hash=expected_rulebook_hash,
        input_warnings=input_warnings,
    )
    promoted_batch, official_outcomes = promote_safe_outcomes(
        preview=preview,
        preview_audit=preview_audit,
        existing_outcomes=official_existing,
        promoted_at=now,
        promotion_source_file="outputs/forward_evidence_outcomes_preview.csv",
        promotion_version=PROMOTION_VERSION,
    )
    rule_evidence_summary = build_rule_evidence_summary(
        promoted_outcomes=promoted_batch,
        rule_library=rule_library,
        rule_events=rule_events,
    )
    filter_evidence = build_filter_evidence(
        rule_library=rule_library,
        rule_backtest_summary=rule_backtest_summary,
        rule_events=rule_events,
    )
    market_map_evidence = build_market_map_evidence(
        rule_library=rule_library,
        rule_backtest_summary=rule_backtest_summary,
        rule_events=rule_events,
    )
    pending_summary = build_pending_outcome_summary(
        partial_resolution=partial_resolution,
        coverage=coverage,
        rule_library=rule_library,
    )
    evidence_scorecard = build_evidence_scorecard(
        preview=preview,
        preview_audit=preview_audit,
        promoted_outcomes=promoted_batch,
        pending_summary=pending_summary,
        rule_summary=rule_evidence_summary,
        status_scorecard=status_scorecard,
    )
    final_recommendation = choose_final_recommendation(evidence_scorecard)

    if write_outputs:
        preview_audit.write_csv(paths["preview_audit_csv"])
        promoted_batch.write_csv(paths["promoted_csv"])
        official_outcomes.write_csv(paths["official_outcomes"])
        rule_evidence_summary.write_csv(paths["rule_summary_csv"])
        filter_evidence.write_csv(paths["filter_evidence_csv"])
        market_map_evidence.write_csv(paths["market_map_evidence_csv"])
        pending_summary.write_csv(paths["pending_summary_csv"])
        evidence_scorecard.write_csv(paths["scorecard_csv"])
        _write_preview_audit_markdown(paths["preview_audit_md"], preview_audit, input_warnings)
        _write_promotion_report(paths["promotion_report_md"], promoted_batch, preview_audit)
        _write_markdown_table(
            paths["rule_summary_md"],
            "# Rule-Level Forward Evidence",
            rule_evidence_summary,
            [
                "Labels are pilot/candidate labels only while forward event counts are small.",
                RESEARCH_WARNING,
            ],
        )
        _write_markdown_table(
            paths["filter_evidence_md"],
            "# Forward Filter Evidence",
            filter_evidence,
            [
                "A filter can be useful as a risk screen even without directional prediction.",
                "Weak filters block too many favorable outcomes relative to avoided adverse outcomes.",
                RESEARCH_WARNING,
            ],
        )
        _write_markdown_table(
            paths["market_map_evidence_md"],
            "# Forward Market-Map Evidence",
            market_map_evidence,
            [
                "Market-map rows describe touch/rejection/acceptance context only.",
                RESEARCH_WARNING,
            ],
        )
        _write_markdown_table(
            paths["pending_summary_md"],
            "# Forward Pending Outcome Summary",
            pending_summary,
            [
                "Pending rows require additional strict intraday or approved daily-approx data before review.",
                RESEARCH_WARNING,
            ],
        )
        _write_scorecard_markdown(
            paths["scorecard_md"],
            evidence_scorecard,
            final_recommendation=final_recommendation,
        )

    return ForwardOutcomeReviewResult(
        preview_audit=preview_audit,
        promoted_batch=promoted_batch,
        official_outcomes=official_outcomes,
        rule_evidence_summary=rule_evidence_summary,
        filter_evidence=filter_evidence,
        market_map_evidence=market_map_evidence,
        pending_summary=pending_summary,
        evidence_scorecard=evidence_scorecard,
        final_recommendation=final_recommendation,
        paths=paths,
        input_warnings=input_warnings,
    )


def build_preview_outcome_audit(
    *,
    preview: pl.DataFrame,
    journal: pl.DataFrame,
    coverage: pl.DataFrame,
    rule_library: pl.DataFrame,
    expected_rulebook_hash: str,
    input_warnings: Iterable[str] = (),
) -> pl.DataFrame:
    """Audit each preview outcome row before promotion."""

    if preview.is_empty():
        return pl.DataFrame(schema=_preview_audit_schema())
    rule_lookup = _rule_lookup(rule_library)
    coverage_lookup = _coverage_lookup(coverage)
    warnings_text = " ".join(input_warnings)
    rows: list[dict[str, Any]] = []
    for preview_row in preview.to_dicts():
        journal_rows = _matching_journal_rows(preview_row, journal)
        for journal_row in journal_rows:
            merged = {**journal_row, **preview_row}
            window = _string(merged.get("window") or merged.get("outcome_window"))
            rule_id = _string(merged.get("rule_id")) or DEFAULT_RULE_ID
            meta = rule_lookup.get(rule_id, {})
            rule_name = _string(merged.get("rule_name") or meta.get("rule_name")) or DEFAULT_RULE_NAME
            rule_family = (
                _string(merged.get("rule_family") or meta.get("rule_family"))
                or DEFAULT_RULE_FAMILY
            )
            rule_type = _string(merged.get("rule_type") or meta.get("rule_type")) or "OUTCOME_REVIEW"
            signal_context = (
                _string(
                    merged.get("signal_context")
                    or merged.get("mode")
                    or merged.get("logic_source")
                    or meta.get("logic_source")
                )
                or "FORWARD_OUTCOME_PREVIEW"
            )
            coverage_passed = _coverage_passed(merged, coverage_lookup, window)
            used_daily_approx = _used_daily_approx(merged)
            used_intraday = _used_intraday_ohlc(merged)
            source_allowed = _source_allowed(window, used_intraday, used_daily_approx)
            observation_precedes = _observation_precedes_outcome(merged)
            leakage_check = (
                observation_precedes
                and _observed_range_within_window(merged)
                and source_allowed
                and not _unknown_timing_guru_context(merged, rule_family, signal_context)
            )
            rulebook_hash_matches = _rulebook_hash_matches(
                journal_row=journal_row,
                expected_rulebook_hash=expected_rulebook_hash,
                journal_available=not journal.is_empty(),
            )
            safe, reject_reason = _promotion_decision(
                merged=merged,
                coverage_passed=coverage_passed,
                leakage_check_passed=leakage_check,
                rulebook_hash_matches=rulebook_hash_matches,
                source_allowed=source_allowed,
                used_intraday_ohlc=used_intraday,
                used_daily_approx=used_daily_approx,
                rule_family=rule_family,
                signal_context=signal_context,
            )
            notes = _audit_notes(
                merged=merged,
                input_warning_text=warnings_text,
                used_daily_approx=used_daily_approx,
                used_intraday_ohlc=used_intraday,
                source_allowed=source_allowed,
            )
            rows.append(
                {
                    "journal_id": _string(merged.get("journal_id")),
                    "rule_id": rule_id,
                    "rule_name": rule_name,
                    "rule_family": rule_family,
                    "signal_context": signal_context,
                    "rule_type": rule_type,
                    "observation_timestamp": _string(merged.get("observation_timestamp")),
                    "trade_date": _string(merged.get("trade_date")),
                    "session_date": _string(merged.get("session_date")),
                    "outcome_window": window,
                    "window_start": _string(merged.get("window_start")),
                    "window_end": _string(merged.get("window_end")),
                    "outcome_status": _string(merged.get("outcome_status")),
                    "resolution_action": _string(merged.get("resolution_action")),
                    "source_symbol": _string(merged.get("source_symbol")),
                    "source_interval": _string(merged.get("source_interval")),
                    "quality": _string(merged.get("quality")),
                    "observed_start": _string(merged.get("observed_start")),
                    "observed_end": _string(merged.get("observed_end")),
                    "open": _optional_float(merged.get("open")),
                    "high": _optional_float(merged.get("high")),
                    "low": _optional_float(merged.get("low")),
                    "close": _optional_float(merged.get("close")),
                    "row_count": _optional_int(merged.get("row_count")) or 0,
                    "coverage_passed": coverage_passed,
                    "leakage_check_passed": leakage_check,
                    "rulebook_hash_matches": rulebook_hash_matches,
                    "observation_precedes_outcome": observation_precedes,
                    "used_intraday_ohlc": used_intraday,
                    "used_daily_approx": used_daily_approx,
                    "safe_to_promote": safe,
                    "reject_reason": reject_reason,
                    "notes": notes,
                }
            )
    return pl.DataFrame(rows, schema=_preview_audit_schema(), infer_schema_length=None)


def promote_safe_outcomes(
    *,
    preview: pl.DataFrame,
    preview_audit: pl.DataFrame,
    existing_outcomes: pl.DataFrame,
    promoted_at: datetime,
    promotion_source_file: str,
    promotion_version: str = PROMOTION_VERSION,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Build promoted outcomes and merged official history without duplicates."""

    del preview
    if preview_audit.is_empty():
        promoted_batch = pl.DataFrame(schema=_promoted_schema())
        return promoted_batch, _merge_without_duplicates(existing_outcomes, promoted_batch)

    promoted_rows = []
    for row in preview_audit.filter(pl.col("safe_to_promote")).to_dicts():
        close_return = _close_return(row)
        mfe = _mfe(row)
        mae = _mae(row)
        promoted_rows.append(
            {
                **{key: row.get(key) for key in _preview_audit_schema()},
                "promoted_at_timestamp": _iso(promoted_at),
                "promotion_source_file": promotion_source_file,
                "promotion_version": promotion_version,
                "coverage_basis": _coverage_basis(row),
                "leakage_check_passed": bool(row.get("leakage_check_passed")),
                "close_return": close_return,
                "mfe": mfe,
                "mae": mae,
                "outcome_result": _outcome_result(close_return, mfe, mae),
            }
        )
    promoted_batch = (
        _dedupe_rows(pl.DataFrame(promoted_rows, schema=_promoted_schema(), infer_schema_length=None))
        if promoted_rows
        else pl.DataFrame(schema=_promoted_schema())
    )
    official = _merge_without_duplicates(existing_outcomes, promoted_batch)
    return promoted_batch, official


def build_rule_evidence_summary(
    *,
    promoted_outcomes: pl.DataFrame,
    rule_library: pl.DataFrame,
    rule_events: pl.DataFrame,
) -> pl.DataFrame:
    """Summarize rule-level forward outcome evidence from promoted rows."""

    if promoted_outcomes.is_empty():
        return pl.DataFrame(schema=_rule_summary_schema())
    linked = _link_promoted_to_rule_events(
        promoted_outcomes=promoted_outcomes,
        rule_library=rule_library,
        rule_events=rule_events,
    )
    if not linked:
        return pl.DataFrame(schema=_rule_summary_schema())

    groups: dict[tuple[str, str, str, str, str, str], list[dict[str, Any]]] = {}
    for row in linked:
        key = (
            _string(row.get("rule_id")),
            _string(row.get("rule_name")),
            _string(row.get("rule_family")),
            _string(row.get("signal_context")),
            _string(row.get("rule_type")),
            _string(row.get("outcome_window")),
        )
        groups.setdefault(key, []).append(row)

    rows = []
    for (rule_id, rule_name, rule_family, signal_context, rule_type, window), items in groups.items():
        count = len(items)
        supported = sum(1 for item in items if _is_supported(item))
        failed = sum(1 for item in items if _is_failed(item))
        mixed = sum(1 for item in items if _is_mixed(item))
        no_clear = max(count - supported - failed - mixed, 0)
        close_returns = [_optional_float(item.get("close_return")) for item in items]
        mfes = [_optional_float(item.get("mfe")) for item in items]
        maes = [_optional_float(item.get("mae")) for item in items]
        helped = sum(1 for item in items if _bool(item.get("blocked_trade")) and _event_return(item) < 0)
        false_block = sum(1 for item in items if _bool(item.get("blocked_trade")) and _event_return(item) > 0)
        wall_touch = sum(1 for item in items if _bool(item.get("wall_touched") or item.get("level_touched")))
        wall_reject = sum(1 for item in items if _bool(item.get("wall_rejected") or item.get("level_rejected")))
        wall_accept = sum(1 for item in items if _bool(item.get("wall_accepted") or item.get("level_accepted")))
        support_rate = supported / count if count else 0.0
        fail_rate = failed / count if count else 0.0
        sample_warning = count < MIN_VALIDATION_EVENTS or any(
            _bool(item.get("sample_size_warning")) for item in items
        )
        rows.append(
            {
                "rule_id": rule_id,
                "rule_name": rule_name,
                "rule_family": rule_family,
                "signal_context": signal_context,
                "rule_type": rule_type,
                "outcome_window": window,
                "observations_count": count,
                "promoted_outcomes_count": _unique_outcome_count(items),
                "supported_count": supported,
                "failed_count": failed,
                "mixed_count": mixed,
                "no_clear_outcome_count": no_clear,
                "support_rate": support_rate,
                "fail_rate": fail_rate,
                "average_close_return": _mean(close_returns),
                "average_mfe": _mean(mfes),
                "average_mae": _mean(maes),
                "max_adverse_excursion": _min(maes),
                "no_trade_filter_helped_count": helped,
                "no_trade_filter_false_block_count": false_block,
                "wall_touch_count": wall_touch,
                "wall_rejection_count": wall_reject,
                "wall_acceptance_count": wall_accept,
                "sample_size_warning": sample_warning,
                "evidence_label": _rule_evidence_label(
                    count=count,
                    rule_type=rule_type,
                    support_rate=support_rate,
                    fail_rate=fail_rate,
                    helped=helped,
                    false_block=false_block,
                    wall_touch=wall_touch,
                ),
            }
        )
    return pl.DataFrame(rows, schema=_rule_summary_schema(), infer_schema_length=None).sort(
        ["rule_id", "outcome_window"]
    )


def build_filter_evidence(
    *,
    rule_library: pl.DataFrame,
    rule_backtest_summary: pl.DataFrame,
    rule_events: pl.DataFrame,
) -> pl.DataFrame:
    """Build filter/no-trade evidence summary."""

    filter_ids = _rule_ids_by_type(rule_library, {"FILTER", "NO_TRADE"})
    rows = []
    if not rule_backtest_summary.is_empty() and "rule_id" in rule_backtest_summary.columns:
        for rule_id in sorted(filter_ids | set(_filter_rule_ids_from_summary(rule_backtest_summary))):
            records = [
                row
                for row in rule_backtest_summary.to_dicts()
                if _string(row.get("rule_id")) == rule_id
            ]
            if not records:
                continue
            meta = _rule_lookup(rule_library).get(rule_id, {})
            blocked = sum(_optional_int(row.get("blocked_trade_count")) or 0 for row in records)
            avoided = sum(_optional_int(row.get("avoided_losing_trade_count")) or 0 for row in records)
            false_blocks = sum(_optional_int(row.get("avoided_winning_trade_count")) or 0 for row in records)
            net_values = [_optional_float(row.get("net_filter_value_proxy")) for row in records]
            avoided_loss_proxy = float(avoided)
            opportunity_cost_proxy = float(false_blocks)
            net_proxy = _sum_values(net_values)
            if net_proxy is None:
                net_proxy = avoided_loss_proxy - opportunity_cost_proxy
            false_rate = false_blocks / blocked if blocked else None
            useful = blocked > 0 and net_proxy > 0 and (false_rate is None or false_rate <= 0.5)
            rows.append(
                {
                    "rule_id": rule_id,
                    "rule_name": _string(meta.get("rule_name")) or rule_id,
                    "blocked_count": blocked,
                    "avoided_losing_count": avoided,
                    "blocked_winning_count": false_blocks,
                    "avoided_loss_proxy": avoided_loss_proxy,
                    "opportunity_cost_proxy": opportunity_cost_proxy,
                    "net_filter_value_proxy": net_proxy,
                    "false_block_rate": false_rate,
                    "useful_filter_candidate": useful,
                    "reason": _filter_reason(blocked, avoided, false_blocks, net_proxy, false_rate),
                }
            )
    if rows:
        return pl.DataFrame(rows, schema=_filter_evidence_schema(), infer_schema_length=None)
    return _filter_evidence_from_events(rule_library=rule_library, rule_events=rule_events)


def build_market_map_evidence(
    *,
    rule_library: pl.DataFrame,
    rule_backtest_summary: pl.DataFrame,
    rule_events: pl.DataFrame,
) -> pl.DataFrame:
    """Build CME/guru market-map evidence summary."""

    map_ids = _rule_ids_by_type(rule_library, {"MARKET_MAP", "CONTEXT"})
    rows = []
    if not rule_backtest_summary.is_empty() and "rule_id" in rule_backtest_summary.columns:
        for rule_id in sorted(map_ids | set(_market_map_rule_ids_from_summary(rule_backtest_summary))):
            records = [
                row
                for row in rule_backtest_summary.to_dicts()
                if _string(row.get("rule_id")) == rule_id
            ]
            if not records:
                continue
            meta = _rule_lookup(rule_library).get(rule_id, {})
            event_count = sum(_optional_int(row.get("event_count")) or 0 for row in records)
            wall_touch = _rate_count(records, "wall_touch_rate", event_count)
            wall_reject = _rate_count(records, "wall_rejection_rate", event_count)
            wall_accept = _rate_count(records, "wall_acceptance_rate", event_count)
            hit_rate = wall_touch / event_count if event_count else None
            useful = event_count >= PILOT_EVENT_FLOOR and hit_rate is not None and hit_rate >= 0.5
            rows.append(
                {
                    "rule_id": rule_id,
                    "rule_name": _string(meta.get("rule_name")) or rule_id,
                    "map_event_count": event_count,
                    "wall_touch_count": wall_touch,
                    "wall_rejection_count": wall_reject,
                    "wall_acceptance_count": wall_accept,
                    "time_to_touch": "",
                    "average_distance_to_wall": None,
                    "map_hit_rate": hit_rate,
                    "useful_market_map_candidate": useful,
                    "reason": _market_map_reason(event_count, hit_rate, useful),
                }
            )
    if rows:
        return pl.DataFrame(rows, schema=_market_map_evidence_schema(), infer_schema_length=None)
    return _market_map_evidence_from_events(rule_library=rule_library, rule_events=rule_events)


def build_pending_outcome_summary(
    *,
    partial_resolution: pl.DataFrame,
    coverage: pl.DataFrame,
    rule_library: pl.DataFrame,
) -> pl.DataFrame:
    """Summarize journal rows whose windows remain pending."""

    del rule_library
    if partial_resolution.is_empty():
        return pl.DataFrame(schema=_pending_summary_schema())
    coverage_by_journal = {
        _string(row.get("journal_id")): row for row in coverage.to_dicts()
    } if not coverage.is_empty() else {}
    rows = []
    for row in partial_resolution.to_dicts():
        missing_windows = _string(row.get("windows_remaining_pending"))
        can_full = _bool(row.get("can_resolve_full"))
        if can_full or not missing_windows:
            continue
        journal_id = _string(row.get("journal_id"))
        coverage_row = coverage_by_journal.get(journal_id, {})
        reason = _string(row.get("reason") or coverage_row.get("missing_coverage_reason"))
        rows.append(
            {
                "journal_id": journal_id,
                "rule_id": DEFAULT_RULE_ID,
                "rule_name": DEFAULT_RULE_NAME,
                "observation_timestamp": _string(row.get("observation_timestamp")),
                "missing_windows": missing_windows,
                "missing_ohlc_until": _string(coverage_row.get("latest_available_ohlc_timestamp")),
                "reason_pending": reason,
                "next_data_needed": _next_data_needed(missing_windows),
                "expected_recheck_time": _string(coverage_row.get("next_check_recommended_at")),
            }
        )
    return pl.DataFrame(rows, schema=_pending_summary_schema(), infer_schema_length=None)


def build_evidence_scorecard(
    *,
    preview: pl.DataFrame,
    preview_audit: pl.DataFrame,
    promoted_outcomes: pl.DataFrame,
    pending_summary: pl.DataFrame,
    rule_summary: pl.DataFrame,
    status_scorecard: pl.DataFrame,
) -> pl.DataFrame:
    """Build the overall forward evidence scorecard."""

    source = status_scorecard.row(0, named=True) if not status_scorecard.is_empty() else {}
    total_rows = _optional_int(source.get("total_journal_rows")) or _unique_count(preview, "journal_id")
    preview_count = preview.height
    promoted_count = promoted_outcomes.height
    safe_count = _count_true(preview_audit, "safe_to_promote")
    rejected_count = max(preview_audit.height - safe_count, 0)
    pending_rows = pending_summary.height or (_optional_int(source.get("unresolved_rows")) or 0)
    strongest = _strongest_candidate(rule_summary)
    weakest = _weakest_candidate(rule_summary)
    current_label = _scorecard_label(
        promoted_count=promoted_count,
        safe_count=safe_count,
        preview_count=preview_count,
        rejected_count=rejected_count,
        pending_rows=pending_rows,
    )
    reason = _scorecard_reason(
        promoted_count=promoted_count,
        safe_count=safe_count,
        rejected_count=rejected_count,
        pending_rows=pending_rows,
        strongest=strongest,
        weakest=weakest,
    )
    row = {
        "total_journal_rows": total_rows,
        "preview_outcomes_count": preview_count,
        "promoted_outcomes_count": promoted_count,
        "pending_rows": pending_rows,
        "safe_to_promote_count": safe_count,
        "rejected_preview_count": rejected_count,
        "rule_families_with_evidence": _families_with_evidence(rule_summary),
        "strongest_candidate_rule": strongest,
        "weakest_candidate_rule": weakest,
        "current_label": current_label,
        "reason": reason,
    }
    return pl.DataFrame([row], schema=_scorecard_schema(), infer_schema_length=None)


def choose_final_recommendation(scorecard: pl.DataFrame) -> str:
    """Choose the final research recommendation label."""

    row = scorecard.row(0, named=True) if not scorecard.is_empty() else {}
    promoted = _optional_int(row.get("promoted_outcomes_count")) or 0
    safe = _optional_int(row.get("safe_to_promote_count")) or 0
    pending = _optional_int(row.get("pending_rows")) or 0
    preview = _optional_int(row.get("preview_outcomes_count")) or 0
    rejected = _optional_int(row.get("rejected_preview_count")) or 0
    if promoted > 0:
        return "COLLECT_MORE_FORWARD_EVIDENCE"
    if safe > 0:
        return "PROMOTE_SAFE_FORWARD_OUTCOMES"
    if pending > 0 and preview == rejected:
        return "WAIT_FOR_INTRADAY_OHLC"
    if preview > 0:
        return "REVIEW_PREVIEW_OUTCOMES_FIRST"
    return "NOT_READY_FOR_MONEY"


def forward_outcome_review_report_lines(
    result: ForwardOutcomeReviewResult | None,
) -> list[str]:
    """Return research_report.md sections for the review layer."""

    if result is None:
        return [
            "## Forward Outcome Preview Audit",
            "",
            "Forward outcome review was not run.",
        ]
    score = result.evidence_scorecard.row(0, named=True) if not result.evidence_scorecard.is_empty() else {}
    return [
        "## Forward Outcome Preview Audit",
        "",
        _frame_markdown(_audit_report_view(result.preview_audit)),
        "",
        "## Promoted Forward Outcomes",
        "",
        _frame_markdown(_promotion_report_view(result.promoted_batch)),
        "",
        "## Rule-Level Forward Evidence",
        "",
        _frame_markdown(result.rule_evidence_summary),
        "",
        "## Filter Evidence",
        "",
        _frame_markdown(result.filter_evidence),
        "",
        "## Market-Map Evidence",
        "",
        _frame_markdown(result.market_map_evidence),
        "",
        "## Pending Outcome Summary",
        "",
        _frame_markdown(result.pending_summary),
        "",
        "## Forward Evidence Scorecard",
        "",
        _frame_markdown(result.evidence_scorecard),
        "",
        "## What Looks Useful So Far",
        "",
        *what_looks_useful_lines(result),
        "",
        "## What Is Still Not Proven",
        "",
        "- The current evidence is still pilot/candidate evidence only.",
        "- Frozen thresholds and rule definitions were not changed.",
        "- No money edge, paper trading readiness, live readiness, or execution suitability is established.",
        "",
        "## Forward Outcome Review Final Recommendation",
        "",
        f"`{result.final_recommendation}`",
        "",
        f"- Current label: `{score.get('current_label', '')}`",
        f"- {RESEARCH_WARNING}",
    ]


def what_looks_useful_lines(result: ForwardOutcomeReviewResult) -> list[str]:
    """Return concise useful/weak evidence lines."""

    strongest = _first_value(result.evidence_scorecard, "strongest_candidate_rule")
    weakest = _first_value(result.evidence_scorecard, "weakest_candidate_rule")
    lines = [
        f"- Safe preview outcome rows promoted in this run: `{result.promoted_batch.height}`.",
        f"- Strongest current candidate: `{strongest or 'none'}`.",
        f"- Weakest current candidate: `{weakest or 'none'}`.",
    ]
    useful_filters = (
        result.filter_evidence.filter(pl.col("useful_filter_candidate"))
        if not result.filter_evidence.is_empty()
        else pl.DataFrame()
    )
    useful_maps = (
        result.market_map_evidence.filter(pl.col("useful_market_map_candidate"))
        if not result.market_map_evidence.is_empty()
        else pl.DataFrame()
    )
    if not useful_filters.is_empty():
        lines.append(
            "- Filter candidates for review: `"
            + "|".join(useful_filters.get_column("rule_id").to_list())
            + "`."
        )
    if not useful_maps.is_empty():
        lines.append(
            "- Market-map candidates for review: `"
            + "|".join(useful_maps.get_column("rule_id").to_list())
            + "`."
        )
    if result.pending_summary.height:
        lines.append(f"- Pending journal rows still needing data: `{result.pending_summary.height}`.")
    return lines


def _matching_journal_rows(preview_row: dict[str, Any], journal: pl.DataFrame) -> list[dict[str, Any]]:
    if journal.is_empty() or "journal_id" not in journal.columns:
        return [{}]
    journal_id = _string(preview_row.get("journal_id"))
    candidates = [row for row in journal.to_dicts() if _string(row.get("journal_id")) == journal_id]
    if not candidates:
        return [{}]
    window = _string(preview_row.get("window") or preview_row.get("outcome_window"))
    window_columns = [column for column in ("window", "outcome_window") if column in journal.columns]
    if window and window_columns:
        narrowed = [
            row
            for row in candidates
            if any(_string(row.get(column)) == window for column in window_columns)
        ]
        if narrowed:
            return narrowed
    return candidates


def _coverage_lookup(coverage: pl.DataFrame) -> dict[tuple[str, str], bool]:
    lookup = {}
    if coverage.is_empty() or "journal_id" not in coverage.columns:
        return lookup
    for row in coverage.to_dicts():
        journal_id = _string(row.get("journal_id"))
        for window in WINDOW_ORDER:
            lookup[(journal_id, window)] = _bool(row.get(f"coverage_{window}"))
    return lookup


def _coverage_passed(
    row: dict[str, Any],
    coverage_lookup: dict[tuple[str, str], bool],
    window: str,
) -> bool:
    key = (_string(row.get("journal_id")), window)
    if key in coverage_lookup:
        return coverage_lookup[key]
    return _string(row.get("resolution_action")) == "preview_resolve" and (
        _optional_int(row.get("row_count")) or 0
    ) > 0


def _used_intraday_ohlc(row: dict[str, Any]) -> bool:
    interval = _string(row.get("source_interval")).lower()
    quality = _string(row.get("quality")).upper()
    if (_optional_int(row.get("row_count")) or 0) <= 0:
        return False
    if interval in {"", "1d", "daily"} or quality == "DAILY_APPROX":
        return False
    return any(token in quality for token in ("INTRADAY", "EXACT", "RESAMPLED")) or interval in {
        "1m",
        "5m",
        "15m",
        "30m",
        "60m",
        "1h",
        "4h",
    }


def _used_daily_approx(row: dict[str, Any]) -> bool:
    interval = _string(row.get("source_interval")).lower()
    quality = _string(row.get("quality")).upper()
    return interval in {"1d", "daily"} or quality == "DAILY_APPROX"


def _source_allowed(window: str, used_intraday_ohlc: bool, used_daily_approx: bool) -> bool:
    if window in STRICT_INTRADAY_WINDOWS:
        return used_intraday_ohlc and not used_daily_approx
    if window in DAILY_APPROX_ALLOWED_WINDOWS:
        return used_intraday_ohlc or used_daily_approx
    return False


def _observation_precedes_outcome(row: dict[str, Any]) -> bool:
    observation = _parse_datetime(row.get("observation_timestamp"))
    window_start = _parse_datetime(row.get("window_start"))
    window_end = _parse_datetime(row.get("window_end"))
    if observation is None or window_start is None or window_end is None:
        return False
    return observation <= window_start and observation < window_end


def _observed_range_within_window(row: dict[str, Any]) -> bool:
    if _string(row.get("resolution_action")) != "preview_resolve":
        return False
    observed_start = _parse_datetime(row.get("observed_start"))
    observed_end = _parse_datetime(row.get("observed_end"))
    window_start = _parse_datetime(row.get("window_start"))
    window_end = _parse_datetime(row.get("window_end"))
    if not all([observed_start, observed_end, window_start, window_end]):
        return False
    return bool(window_start <= observed_start <= observed_end <= window_end)


def _rulebook_hash_matches(
    *,
    journal_row: dict[str, Any],
    expected_rulebook_hash: str,
    journal_available: bool,
) -> bool:
    row_hash = _string(
        journal_row.get("rulebook_hash")
        or journal_row.get("frozen_rulebook_hash")
        or journal_row.get("rulebook_v1_hash")
    )
    if expected_rulebook_hash and row_hash:
        return row_hash == expected_rulebook_hash
    if expected_rulebook_hash and journal_available:
        return False
    return True


def _promotion_decision(
    *,
    merged: dict[str, Any],
    coverage_passed: bool,
    leakage_check_passed: bool,
    rulebook_hash_matches: bool,
    source_allowed: bool,
    used_intraday_ohlc: bool,
    used_daily_approx: bool,
    rule_family: str,
    signal_context: str,
) -> tuple[bool, str]:
    reasons = []
    window = _string(merged.get("window") or merged.get("outcome_window"))
    if not coverage_passed:
        reasons.append("missing_coverage")
    if _string(merged.get("resolution_action")) != "preview_resolve":
        reasons.append("preview_not_resolved")
    if (_optional_int(merged.get("row_count")) or 0) <= 0:
        reasons.append("no_preview_price_metrics")
    if window in STRICT_INTRADAY_WINDOWS and (used_daily_approx or not used_intraday_ohlc):
        reasons.append("daily_approx_not_allowed_for_intraday_window")
    if not source_allowed:
        reasons.append("source_not_allowed_for_window")
    if not leakage_check_passed:
        reasons.append("leakage_check_failed")
    if not rulebook_hash_matches:
        reasons.append("rulebook_hash_mismatch")
    if _is_weekend_artifact(merged):
        reasons.append("weekend_artifact_context_only")
    if _unknown_timing_guru_context(merged, rule_family, signal_context):
        reasons.append("unknown_timing_guru_context_only")
    safe = not reasons
    return safe, "" if safe else "|".join(dict.fromkeys(reasons))


def _audit_notes(
    *,
    merged: dict[str, Any],
    input_warning_text: str,
    used_daily_approx: bool,
    used_intraday_ohlc: bool,
    source_allowed: bool,
) -> str:
    notes = [_string(merged.get("notes"))]
    if input_warning_text:
        notes.append(input_warning_text)
    if used_daily_approx:
        notes.append("Daily approximation is marked and is not used for strict intraday windows.")
    if used_intraday_ohlc:
        notes.append("Intraday or resampled intraday OHLC is present.")
    if not source_allowed:
        notes.append("Source granularity is not sufficient for this outcome window.")
    return " ".join(note for note in notes if note).strip()


def _link_promoted_to_rule_events(
    *,
    promoted_outcomes: pl.DataFrame,
    rule_library: pl.DataFrame,
    rule_events: pl.DataFrame,
) -> list[dict[str, Any]]:
    rule_lookup = _rule_lookup(rule_library)
    events_by_date: dict[str, list[dict[str, Any]]] = {}
    if not rule_events.is_empty() and "event_date" in rule_events.columns:
        for event in rule_events.to_dicts():
            events_by_date.setdefault(_string(event.get("event_date")), []).append(event)
    linked = []
    for promoted in promoted_outcomes.to_dicts():
        event_date = _event_date_for_promoted(promoted)
        events = events_by_date.get(event_date, [])
        if not events:
            events = [{}]
        else:
            events = _aggregate_events_by_rule(events)
        for event in events:
            rule_id = _string(event.get("rule_id") or promoted.get("rule_id"))
            if rule_id == DEFAULT_RULE_ID and _string(promoted.get("rule_id")):
                rule_id = _string(promoted.get("rule_id"))
            meta = rule_lookup.get(rule_id, {})
            rule_name = _string(meta.get("rule_name") or promoted.get("rule_name")) or rule_id
            rule_family = _string(meta.get("rule_family") or promoted.get("rule_family"))
            rule_type = _string(meta.get("rule_type") or promoted.get("rule_type"))
            signal_context = _string(event.get("mode") or promoted.get("signal_context"))
            linked.append(
                {
                    **promoted,
                    **event,
                    "rule_id": rule_id,
                    "rule_name": rule_name,
                    "rule_family": rule_family,
                    "rule_type": rule_type,
                    "signal_context": signal_context or "FORWARD_OUTCOME_PREVIEW",
                }
            )
    return linked


def _aggregate_events_by_rule(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        grouped.setdefault(_string(event.get("rule_id")), []).append(event)
    aggregated = []
    for rule_id, records in grouped.items():
        returns = [_optional_float(row.get("future_return_points")) for row in records]
        average_return = _mean(returns)
        favorable = sum(1 for row in records if _bool(row.get("favorable_followthrough")))
        unfavorable = sum(1 for row in records if not _bool(row.get("favorable_followthrough")))
        first = records[0]
        aggregated.append(
            {
                **first,
                "rule_id": rule_id,
                "future_return_points": average_return,
                "favorable_followthrough": favorable >= unfavorable,
                "trade_candidate": any(_bool(row.get("trade_candidate")) for row in records),
                "blocked_trade": any(_bool(row.get("blocked_trade")) for row in records),
                "level_touched": any(_bool(row.get("level_touched")) for row in records),
                "level_rejected": any(_bool(row.get("level_rejected")) for row in records),
                "level_accepted": any(_bool(row.get("level_accepted")) for row in records),
                "wall_touched": any(_bool(row.get("wall_touched")) for row in records),
                "wall_rejected": any(_bool(row.get("wall_rejected")) for row in records),
                "wall_accepted": any(_bool(row.get("wall_accepted")) for row in records),
                "sample_size_warning": any(_bool(row.get("sample_size_warning")) for row in records),
            }
        )
    return aggregated


def _event_date_for_promoted(row: dict[str, Any]) -> str:
    for key in ("session_date", "trade_date"):
        value = _string(row.get(key))
        if value:
            return value[:10]
    parsed = _parse_datetime(row.get("observation_timestamp"))
    return parsed.date().isoformat() if parsed else ""


def _is_supported(row: dict[str, Any]) -> bool:
    if "favorable_followthrough" in row and row.get("favorable_followthrough") is not None:
        return _bool(row.get("favorable_followthrough"))
    return (_optional_float(row.get("close_return")) or 0.0) > 0


def _is_failed(row: dict[str, Any]) -> bool:
    if "favorable_followthrough" in row and row.get("favorable_followthrough") is not None:
        return not _bool(row.get("favorable_followthrough"))
    return (_optional_float(row.get("close_return")) or 0.0) < 0


def _is_mixed(row: dict[str, Any]) -> bool:
    close_return = _optional_float(row.get("close_return")) or 0.0
    mfe = _optional_float(row.get("mfe")) or 0.0
    mae = _optional_float(row.get("mae")) or 0.0
    return close_return == 0 and mfe > 0 and mae < 0


def _rule_evidence_label(
    *,
    count: int,
    rule_type: str,
    support_rate: float,
    fail_rate: float,
    helped: int,
    false_block: int,
    wall_touch: int,
) -> str:
    if count < PILOT_EVENT_FLOOR:
        return "TOO_EARLY"
    normalized_type = rule_type.upper()
    if normalized_type in {"FILTER", "NO_TRADE"} and helped > false_block and helped > 0:
        return "FILTER_CANDIDATE"
    if normalized_type == "MARKET_MAP" and wall_touch > 0:
        return "MARKET_MAP_CANDIDATE"
    if support_rate >= 0.6 and count < MIN_VALIDATION_EVENTS:
        return "USEFUL_PILOT_EVIDENCE"
    if fail_rate >= 0.6:
        return "WEAK_OR_FAILED"
    return "NEEDS_MORE_FORWARD_DATA"


def _filter_evidence_from_events(*, rule_library: pl.DataFrame, rule_events: pl.DataFrame) -> pl.DataFrame:
    if rule_events.is_empty():
        return pl.DataFrame(schema=_filter_evidence_schema())
    rule_lookup = _rule_lookup(rule_library)
    filter_ids = _rule_ids_by_type(rule_library, {"FILTER", "NO_TRADE"})
    rows = []
    for rule_id in sorted(filter_ids):
        records = [row for row in rule_events.to_dicts() if _string(row.get("rule_id")) == rule_id]
        if not records:
            continue
        blocked = sum(1 for row in records if _bool(row.get("blocked_trade")))
        avoided = sum(1 for row in records if _bool(row.get("blocked_trade")) and _event_return(row) < 0)
        false_blocks = sum(1 for row in records if _bool(row.get("blocked_trade")) and _event_return(row) > 0)
        avoided_loss_proxy = sum(abs(_event_return(row)) for row in records if _bool(row.get("blocked_trade")) and _event_return(row) < 0)
        opportunity_cost_proxy = sum(_event_return(row) for row in records if _bool(row.get("blocked_trade")) and _event_return(row) > 0)
        net_proxy = avoided_loss_proxy - opportunity_cost_proxy
        false_rate = false_blocks / blocked if blocked else None
        rows.append(
            {
                "rule_id": rule_id,
                "rule_name": _string(rule_lookup.get(rule_id, {}).get("rule_name")) or rule_id,
                "blocked_count": blocked,
                "avoided_losing_count": avoided,
                "blocked_winning_count": false_blocks,
                "avoided_loss_proxy": avoided_loss_proxy,
                "opportunity_cost_proxy": opportunity_cost_proxy,
                "net_filter_value_proxy": net_proxy,
                "false_block_rate": false_rate,
                "useful_filter_candidate": blocked > 0 and net_proxy > 0 and (false_rate is None or false_rate <= 0.5),
                "reason": _filter_reason(blocked, avoided, false_blocks, net_proxy, false_rate),
            }
        )
    return pl.DataFrame(rows, schema=_filter_evidence_schema(), infer_schema_length=None)


def _market_map_evidence_from_events(
    *,
    rule_library: pl.DataFrame,
    rule_events: pl.DataFrame,
) -> pl.DataFrame:
    if rule_events.is_empty():
        return pl.DataFrame(schema=_market_map_evidence_schema())
    rule_lookup = _rule_lookup(rule_library)
    map_ids = _rule_ids_by_type(rule_library, {"MARKET_MAP", "CONTEXT"})
    rows = []
    for rule_id in sorted(map_ids):
        records = [row for row in rule_events.to_dicts() if _string(row.get("rule_id")) == rule_id]
        if not records:
            continue
        count = len(records)
        touch = sum(1 for row in records if _bool(row.get("wall_touched") or row.get("level_touched")))
        rejection = sum(1 for row in records if _bool(row.get("wall_rejected") or row.get("level_rejected")))
        acceptance = sum(1 for row in records if _bool(row.get("wall_accepted") or row.get("level_accepted")))
        hit_rate = touch / count if count else None
        useful = count >= PILOT_EVENT_FLOOR and hit_rate is not None and hit_rate >= 0.5
        rows.append(
            {
                "rule_id": rule_id,
                "rule_name": _string(rule_lookup.get(rule_id, {}).get("rule_name")) or rule_id,
                "map_event_count": count,
                "wall_touch_count": touch,
                "wall_rejection_count": rejection,
                "wall_acceptance_count": acceptance,
                "time_to_touch": "",
                "average_distance_to_wall": None,
                "map_hit_rate": hit_rate,
                "useful_market_map_candidate": useful,
                "reason": _market_map_reason(count, hit_rate, useful),
            }
        )
    return pl.DataFrame(rows, schema=_market_map_evidence_schema(), infer_schema_length=None)


def _merge_without_duplicates(existing: pl.DataFrame, promoted_batch: pl.DataFrame) -> pl.DataFrame:
    if existing.is_empty() and promoted_batch.is_empty():
        return pl.DataFrame(schema=_promoted_schema())
    combined_rows = []
    seen: set[tuple[str, str, str]] = set()
    for frame in (existing, promoted_batch):
        for row in frame.to_dicts() if not frame.is_empty() else []:
            key = (
                _string(row.get("journal_id")),
                _string(row.get("rule_id")),
                _string(row.get("outcome_window") or row.get("window")),
            )
            if key in seen:
                continue
            seen.add(key)
            combined_rows.append(row)
    return _rows_to_promoted_frame(combined_rows)


def _dedupe_rows(frame: pl.DataFrame) -> pl.DataFrame:
    if frame.is_empty():
        return frame
    rows = []
    seen = set()
    for row in frame.to_dicts():
        key = (
            _string(row.get("journal_id")),
            _string(row.get("rule_id")),
            _string(row.get("outcome_window")),
        )
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
    return _rows_to_promoted_frame(rows)


def _rows_to_promoted_frame(rows: list[dict[str, Any]]) -> pl.DataFrame:
    if not rows:
        return pl.DataFrame(schema=_promoted_schema())
    schema = _promoted_schema()
    normalized = [{column: row.get(column) for column in schema} for row in rows]
    return pl.DataFrame(normalized, schema=schema, infer_schema_length=None)


def _coverage_basis(row: dict[str, Any]) -> str:
    if _bool(row.get("used_intraday_ohlc")):
        return "outcome_coverage_check.csv|strict_intraday_or_resampled_intraday"
    if _bool(row.get("used_daily_approx")):
        return "outcome_coverage_check.csv|daily_approx_allowed_window"
    return "outcome_coverage_check.csv|insufficient"


def _close_return(row: dict[str, Any]) -> float | None:
    open_price = _optional_float(row.get("open"))
    close_price = _optional_float(row.get("close"))
    if open_price is None or close_price is None:
        return None
    return close_price - open_price


def _mfe(row: dict[str, Any]) -> float | None:
    open_price = _optional_float(row.get("open"))
    high = _optional_float(row.get("high"))
    if open_price is None or high is None:
        return None
    return high - open_price


def _mae(row: dict[str, Any]) -> float | None:
    open_price = _optional_float(row.get("open"))
    low = _optional_float(row.get("low"))
    if open_price is None or low is None:
        return None
    return low - open_price


def _outcome_result(close_return: float | None, mfe: float | None, mae: float | None) -> str:
    if close_return is None:
        return "no_clear_outcome"
    if close_return > 0:
        return "supported"
    if close_return < 0:
        return "failed"
    if (mfe or 0.0) > 0 and (mae or 0.0) < 0:
        return "mixed"
    return "no_clear_outcome"


def _rule_lookup(rule_library: pl.DataFrame) -> dict[str, dict[str, Any]]:
    if rule_library.is_empty() or "rule_id" not in rule_library.columns:
        return {}
    result = {}
    for row in rule_library.to_dicts():
        rule_id = _string(row.get("rule_id"))
        if rule_id:
            result[rule_id] = row
    return result


def _rule_ids_by_type(rule_library: pl.DataFrame, rule_types: set[str]) -> set[str]:
    result = set()
    if rule_library.is_empty() or not {"rule_id", "rule_type"}.issubset(rule_library.columns):
        return result
    for row in rule_library.to_dicts():
        if _string(row.get("rule_type")).upper() in rule_types:
            result.add(_string(row.get("rule_id")))
    return result


def _filter_rule_ids_from_summary(frame: pl.DataFrame) -> set[str]:
    return {
        _string(row.get("rule_id"))
        for row in frame.to_dicts()
        if _string(row.get("rule_type")).upper() in {"FILTER", "NO_TRADE"}
    }


def _market_map_rule_ids_from_summary(frame: pl.DataFrame) -> set[str]:
    return {
        _string(row.get("rule_id"))
        for row in frame.to_dicts()
        if _string(row.get("rule_type")).upper() in {"MARKET_MAP", "CONTEXT"}
    }


def _filter_reason(
    blocked: int,
    avoided: int,
    false_blocks: int,
    net_proxy: float,
    false_rate: float | None,
) -> str:
    if blocked == 0:
        return "No blocked outcomes are available yet."
    if net_proxy > 0 and (false_rate is None or false_rate <= 0.5):
        return "Filter is a pilot candidate because avoided adverse outcomes exceed blocked favorable outcomes."
    if false_blocks > avoided:
        return "Filter is weak in this sample because blocked favorable outcomes exceed avoided adverse outcomes."
    return "Filter needs more forward rows before interpretation."


def _market_map_reason(count: int, hit_rate: float | None, useful: bool) -> str:
    if count == 0:
        return "No map events are available yet."
    if useful:
        return "Market-map rule is a pilot candidate because wall-touch context appears inspectable."
    if hit_rate is None or hit_rate == 0:
        return "Market-map evidence is weak in this sample because no wall touch was observed."
    return "Market-map evidence needs more forward rows before interpretation."


def _rate_count(records: list[dict[str, Any]], rate_column: str, event_count: int) -> int:
    weighted = 0.0
    total = 0
    for row in records:
        count = _optional_int(row.get("event_count")) or 0
        rate = _optional_float(row.get(rate_column))
        if rate is None:
            continue
        weighted += rate * count
        total += count
    if total == 0 and event_count:
        values = [_optional_float(row.get(rate_column)) for row in records]
        value = _mean(values)
        return int(round((value or 0.0) * event_count))
    return int(round(weighted))


def _event_return(row: dict[str, Any]) -> float:
    return _optional_float(row.get("future_return_points")) or 0.0


def _unique_outcome_count(items: list[dict[str, Any]]) -> int:
    return len(
        {
            (
                _string(item.get("journal_id")),
                _string(item.get("outcome_window")),
                _string(item.get("rule_id")),
            )
            for item in items
        }
    )


def _next_data_needed(missing_windows: str) -> str:
    windows = [item for item in missing_windows.split("|") if item]
    strict = [window for window in windows if window in STRICT_INTRADAY_WINDOWS]
    if strict:
        return "Strict intraday or resampled intraday OHLC for " + "|".join(strict)
    return "Approved daily approximation or intraday OHLC for " + "|".join(windows)


def _families_with_evidence(rule_summary: pl.DataFrame) -> str:
    if rule_summary.is_empty() or "rule_family" not in rule_summary.columns:
        return ""
    families = []
    for row in rule_summary.to_dicts():
        if (_optional_int(row.get("promoted_outcomes_count")) or 0) <= 0:
            continue
        family = _string(row.get("rule_family"))
        if family and family not in families:
            families.append(family)
    return "|".join(families)


def _strongest_candidate(rule_summary: pl.DataFrame) -> str:
    if rule_summary.is_empty():
        return ""
    candidates = []
    for row in rule_summary.to_dicts():
        label = _string(row.get("evidence_label"))
        if label not in {"USEFUL_PILOT_EVIDENCE", "FILTER_CANDIDATE", "MARKET_MAP_CANDIDATE"}:
            continue
        score = (
            (_optional_float(row.get("support_rate")) or 0.0)
            + min((_optional_int(row.get("wall_touch_count")) or 0) / 10.0, 1.0)
            + min((_optional_int(row.get("no_trade_filter_helped_count")) or 0) / 10.0, 1.0)
        )
        candidates.append((score, _string(row.get("rule_id"))))
    if not candidates:
        return ""
    return sorted(candidates, key=lambda item: (-item[0], item[1]))[0][1]


def _weakest_candidate(rule_summary: pl.DataFrame) -> str:
    if rule_summary.is_empty():
        return ""
    candidates = []
    for row in rule_summary.to_dicts():
        score = (
            (_optional_float(row.get("fail_rate")) or 0.0)
            + min((_optional_int(row.get("no_trade_filter_false_block_count")) or 0) / 10.0, 1.0)
        )
        candidates.append((score, _string(row.get("rule_id"))))
    if not candidates:
        return ""
    return sorted(candidates, key=lambda item: (-item[0], item[1]))[0][1]


def _scorecard_label(
    *,
    promoted_count: int,
    safe_count: int,
    preview_count: int,
    rejected_count: int,
    pending_rows: int,
) -> str:
    if promoted_count > 0 and pending_rows > 0:
        return "PARTIAL_OUTCOMES_PROMOTED"
    if promoted_count > 0:
        return "COLLECTING_FORWARD_EVIDENCE"
    if safe_count > 0:
        return "FORWARD_OUTCOME_PREVIEW_READY"
    if preview_count == 0 or (preview_count > 0 and rejected_count == preview_count):
        return "DATA_QUALITY_BLOCKED"
    if pending_rows > 0:
        return "COLLECTING_FORWARD_EVIDENCE"
    return "TOO_EARLY_TO_JUDGE"


def _scorecard_reason(
    *,
    promoted_count: int,
    safe_count: int,
    rejected_count: int,
    pending_rows: int,
    strongest: str,
    weakest: str,
) -> str:
    return (
        f"{promoted_count} safe preview outcome rows were promoted; "
        f"{safe_count} rows passed audit and {rejected_count} preview rows were rejected. "
        f"{pending_rows} journal rows still need more data. "
        f"Strongest candidate: {strongest or 'none'}; weakest candidate: {weakest or 'none'}. "
        "Evidence remains research-only and needs more forward rows before any money-readiness decision."
    )


def _input_warnings(
    *,
    paths: dict[str, Path],
    preview: pl.DataFrame,
    journal: pl.DataFrame,
    experiment_registry: pl.DataFrame,
    expected_rulebook_hash: str,
) -> list[str]:
    warnings = []
    if preview.is_empty():
        warnings.append("forward_evidence_outcomes_preview.csv is missing or empty.")
    if journal.is_empty() and not paths["journal"].exists():
        warnings.append("forward_evidence_journal.csv is missing; fallback preview metadata was used.")
    if experiment_registry.is_empty() and not paths["experiment_registry"].exists():
        warnings.append("experiment_registry.csv is missing; no experiment metadata was attached.")
    if not paths["rulebook_hash"].exists() and expected_rulebook_hash:
        warnings.append("frozen_rulebook_v1_hash.txt is missing; current rule-library digest was used.")
    return warnings


def _is_weekend_artifact(row: dict[str, Any]) -> bool:
    trade_day = _parse_date(row.get("trade_date"))
    session_day = _parse_date(row.get("session_date"))
    return bool(trade_day and session_day and trade_day != session_day)


def _unknown_timing_guru_context(
    row: dict[str, Any],
    rule_family: str,
    signal_context: str,
) -> bool:
    text = " ".join(
        [
            rule_family,
            signal_context,
            _string(row.get("timing_status")),
            _string(row.get("timing_context")),
            _string(row.get("evidence_status")),
        ]
    ).upper()
    return "GURU" in text and ("UNKNOWN" in text or "UNKNOWN_TIMING" in text)


def _frame_digest(frame: pl.DataFrame) -> str:
    if frame.is_empty():
        return ""
    payload = frame.sort(frame.columns).write_csv()
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _read_csv_frame(path: Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    try:
        return pl.read_csv(path, infer_schema_length=None)
    except Exception:
        return pl.DataFrame()


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _write_preview_audit_markdown(
    path: Path,
    preview_audit: pl.DataFrame,
    input_warnings: tuple[str, ...],
) -> None:
    warnings = "\n".join(f"- {warning}" for warning in input_warnings) or "- none"
    lines = [
        "# Forward Outcome Preview Audit",
        "",
        _frame_markdown(_audit_report_view(preview_audit)),
        "",
        "## Input Warnings",
        "",
        warnings,
        "",
        "- Safe-to-promote requires coverage, anti-leakage, source-granularity, and rulebook checks.",
        f"- {RESEARCH_WARNING}",
    ]
    path.write_text(_safe_report_text("\n".join(lines)), encoding="utf-8")


def _write_promotion_report(
    path: Path,
    promoted_batch: pl.DataFrame,
    preview_audit: pl.DataFrame,
) -> None:
    safe = _count_true(preview_audit, "safe_to_promote")
    rejected = preview_audit.height - safe if not preview_audit.is_empty() else 0
    if promoted_batch.is_empty():
        explanation = "No preview rows were promoted because no row passed every audit check."
    else:
        explanation = f"{promoted_batch.height} preview outcome rows were promoted into official history."
    lines = [
        "# Forward Outcome Promotion Report",
        "",
        explanation,
        "",
        f"- Safe-to-promote rows: `{safe}`",
        f"- Rejected preview rows: `{rejected}`",
        "- Original journal observations were not mutated.",
        "- Preview outcome file was left unchanged.",
        "",
        _frame_markdown(_promotion_report_view(promoted_batch)),
        "",
        f"- {RESEARCH_WARNING}",
    ]
    path.write_text(_safe_report_text("\n".join(lines)), encoding="utf-8")


def _write_markdown_table(path: Path, title: str, frame: pl.DataFrame, notes: list[str]) -> None:
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
        "# Forward Evidence Scorecard",
        "",
        _frame_markdown(scorecard),
        "",
        f"- Final recommendation: `{final_recommendation}`",
        "- Overall state remains forward evidence collection, not a money-readiness gate pass.",
        f"- {RESEARCH_WARNING}",
    ]
    path.write_text(_safe_report_text("\n".join(lines)), encoding="utf-8")


def _audit_report_view(frame: pl.DataFrame) -> pl.DataFrame:
    columns = [
        "journal_id",
        "rule_id",
        "outcome_window",
        "coverage_passed",
        "leakage_check_passed",
        "used_intraday_ohlc",
        "used_daily_approx",
        "safe_to_promote",
        "reject_reason",
    ]
    return _select_existing(frame, columns)


def _promotion_report_view(frame: pl.DataFrame) -> pl.DataFrame:
    columns = [
        "journal_id",
        "rule_id",
        "outcome_window",
        "promoted_at_timestamp",
        "coverage_basis",
        "close_return",
        "outcome_result",
    ]
    return _select_existing(frame, columns)


def _select_existing(frame: pl.DataFrame, columns: list[str]) -> pl.DataFrame:
    if frame.is_empty():
        return frame
    selected = [column for column in columns if column in frame.columns]
    return frame.select(selected) if selected else frame


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


def _preview_audit_schema() -> dict[str, Any]:
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
    }


def _promoted_schema() -> dict[str, Any]:
    schema = dict(_preview_audit_schema())
    schema.update(
        {
            "promoted_at_timestamp": pl.String,
            "promotion_source_file": pl.String,
            "promotion_version": pl.String,
            "coverage_basis": pl.String,
            "close_return": pl.Float64,
            "mfe": pl.Float64,
            "mae": pl.Float64,
            "outcome_result": pl.String,
        }
    )
    return schema


def _rule_summary_schema() -> dict[str, Any]:
    return {
        "rule_id": pl.String,
        "rule_name": pl.String,
        "rule_family": pl.String,
        "signal_context": pl.String,
        "rule_type": pl.String,
        "outcome_window": pl.String,
        "observations_count": pl.Int64,
        "promoted_outcomes_count": pl.Int64,
        "supported_count": pl.Int64,
        "failed_count": pl.Int64,
        "mixed_count": pl.Int64,
        "no_clear_outcome_count": pl.Int64,
        "support_rate": pl.Float64,
        "fail_rate": pl.Float64,
        "average_close_return": pl.Float64,
        "average_mfe": pl.Float64,
        "average_mae": pl.Float64,
        "max_adverse_excursion": pl.Float64,
        "no_trade_filter_helped_count": pl.Int64,
        "no_trade_filter_false_block_count": pl.Int64,
        "wall_touch_count": pl.Int64,
        "wall_rejection_count": pl.Int64,
        "wall_acceptance_count": pl.Int64,
        "sample_size_warning": pl.Boolean,
        "evidence_label": pl.String,
    }


def _filter_evidence_schema() -> dict[str, Any]:
    return {
        "rule_id": pl.String,
        "rule_name": pl.String,
        "blocked_count": pl.Int64,
        "avoided_losing_count": pl.Int64,
        "blocked_winning_count": pl.Int64,
        "avoided_loss_proxy": pl.Float64,
        "opportunity_cost_proxy": pl.Float64,
        "net_filter_value_proxy": pl.Float64,
        "false_block_rate": pl.Float64,
        "useful_filter_candidate": pl.Boolean,
        "reason": pl.String,
    }


def _market_map_evidence_schema() -> dict[str, Any]:
    return {
        "rule_id": pl.String,
        "rule_name": pl.String,
        "map_event_count": pl.Int64,
        "wall_touch_count": pl.Int64,
        "wall_rejection_count": pl.Int64,
        "wall_acceptance_count": pl.Int64,
        "time_to_touch": pl.String,
        "average_distance_to_wall": pl.Float64,
        "map_hit_rate": pl.Float64,
        "useful_market_map_candidate": pl.Boolean,
        "reason": pl.String,
    }


def _pending_summary_schema() -> dict[str, Any]:
    return {
        "journal_id": pl.String,
        "rule_id": pl.String,
        "rule_name": pl.String,
        "observation_timestamp": pl.String,
        "missing_windows": pl.String,
        "missing_ohlc_until": pl.String,
        "reason_pending": pl.String,
        "next_data_needed": pl.String,
        "expected_recheck_time": pl.String,
    }


def _scorecard_schema() -> dict[str, Any]:
    return {
        "total_journal_rows": pl.Int64,
        "preview_outcomes_count": pl.Int64,
        "promoted_outcomes_count": pl.Int64,
        "pending_rows": pl.Int64,
        "safe_to_promote_count": pl.Int64,
        "rejected_preview_count": pl.Int64,
        "rule_families_with_evidence": pl.String,
        "strongest_candidate_rule": pl.String,
        "weakest_candidate_rule": pl.String,
        "current_label": pl.String,
        "reason": pl.String,
    }


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
        parsed_date = _parse_date(text)
        if parsed_date is None:
            return None
        return datetime.combine(parsed_date, time(), tzinfo=UTC)
    return _ensure_utc(parsed)


def _parse_date(value: Any) -> date | None:
    text = _string(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _ensure_utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


def _iso(value: datetime | None) -> str:
    if value is None:
        return ""
    return _ensure_utc(value).isoformat().replace("+00:00", "Z")


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


def _min(values: Iterable[float | None]) -> float | None:
    clean = [value for value in values if value is not None]
    return min(clean) if clean else None


def _sum_values(values: Iterable[float | None]) -> float | None:
    clean = [value for value in values if value is not None]
    if not clean:
        return None
    return sum(clean)


def _unique_count(frame: pl.DataFrame, column: str) -> int:
    if frame.is_empty() or column not in frame.columns:
        return 0
    return frame.select(column).unique().height


def _count_true(frame: pl.DataFrame, column: str) -> int:
    if frame.is_empty() or column not in frame.columns:
        return 0
    return sum(1 for value in frame.get_column(column).to_list() if _bool(value))


def _first_value(frame: pl.DataFrame, column: str) -> str:
    if frame.is_empty() or column not in frame.columns:
        return ""
    return _string(frame.get_column(column).head(1).item())


def _string(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def main() -> None:
    """CLI entry point for local review generation."""

    result = run_forward_outcome_review()
    row = result.evidence_scorecard.row(0, named=True) if not result.evidence_scorecard.is_empty() else {}
    print(f"preview_outcomes_count: {row.get('preview_outcomes_count', 0)}")
    print(f"safe_to_promote_count: {row.get('safe_to_promote_count', 0)}")
    print(f"promoted_outcomes_count: {row.get('promoted_outcomes_count', 0)}")
    print(f"final_recommendation: {result.final_recommendation}")


if __name__ == "__main__":
    main()
