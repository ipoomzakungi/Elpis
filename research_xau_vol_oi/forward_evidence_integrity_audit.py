"""Forward evidence count reconciliation and integrity audit.

This layer explains the difference between promoted outcome-window rows,
journal observations, journal/rule events, and market sessions. It is
research-only and does not tune frozen rules, change governance thresholds, or
move any rule to a money-readiness state.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl


DEFAULT_RULE_ID = "FORWARD_OUTCOME_PREVIEW"
MIN_REVIEW_EVENTS = 30
MIN_VALIDATION_EVENTS = 60
FINAL_RECOMMENDATION = "COUNTS_RECONCILED_COLLECT_MORE_EVENTS"
RESEARCH_WARNING = (
    "Research-only integrity audit. No live trading, paper trading, broker "
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
COUNT_BASIS_VALUES = {
    "JOURNAL_RULE_EVENT",
    "UNIQUE_JOURNAL_OBSERVATION",
    "UNIQUE_MARKET_SESSION",
}


@dataclass(frozen=True)
class ForwardEvidenceIntegrityAuditResult:
    """Frames and final recommendation emitted by the integrity layer."""

    count_reconciliation: pl.DataFrame
    duplication_audit: pl.DataFrame
    sample_size_by_definition: pl.DataFrame
    final_recommendation: str
    governance_changed: bool
    paths: dict[str, Path]
    input_warnings: tuple[str, ...]


def run_forward_evidence_integrity_audit(
    *,
    output_dir: str | Path = "outputs",
    review_floor_count_basis: str = "JOURNAL_RULE_EVENT",
    write_outputs: bool = True,
) -> ForwardEvidenceIntegrityAuditResult:
    """Run count reconciliation, duplication audit, and sample-size audit."""

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    paths = {
        "promoted": output_root / "forward_evidence_outcomes_promoted.csv",
        "event_level": output_root / "forward_event_level_outcomes.csv",
        "rule_event": output_root / "forward_rule_event_evidence.csv",
        "governance": output_root / "forward_rule_governance.csv",
        "event_scorecard": output_root / "forward_event_scorecard.csv",
        "journal": output_root / "forward_evidence_journal.csv",
        "frozen_rulebook": output_root / "frozen_rulebook_v1.yaml",
        "rulebook_hash": output_root / "frozen_rulebook_v1_hash.txt",
        "count_reconciliation_csv": output_root
        / "forward_evidence_count_reconciliation.csv",
        "count_reconciliation_md": output_root
        / "forward_evidence_count_reconciliation.md",
        "duplication_audit_csv": output_root / "forward_event_duplication_audit.csv",
        "duplication_audit_md": output_root / "forward_event_duplication_audit.md",
        "sample_size_csv": output_root / "forward_sample_size_by_definition.csv",
        "sample_size_md": output_root / "forward_sample_size_by_definition.md",
    }

    promoted = _read_csv_frame(paths["promoted"])
    event_level = _read_csv_frame(paths["event_level"])
    rule_event = _read_csv_frame(paths["rule_event"])
    governance = _read_csv_frame(paths["governance"])
    event_scorecard = _read_csv_frame(paths["event_scorecard"])
    journal = _read_csv_frame(paths["journal"])
    input_warnings = tuple(
        _input_warnings(
            paths=paths,
            promoted=promoted,
            event_level=event_level,
            governance=governance,
            journal=journal,
        )
    )
    count_reconciliation = build_count_reconciliation(
        promoted_outcomes=promoted,
        event_level_outcomes=event_level,
    )
    duplication_audit = build_duplication_audit(
        promoted_outcomes=promoted,
        event_level_outcomes=event_level,
        rule_event_evidence=rule_event,
        event_scorecard=event_scorecard,
    )
    sample_size = build_sample_size_by_definition(
        promoted_outcomes=promoted,
        event_level_outcomes=event_level,
        review_floor_count_basis=review_floor_count_basis,
    )
    final_recommendation = choose_final_recommendation(duplication_audit)
    governance_changed = False

    if write_outputs:
        count_reconciliation.write_csv(paths["count_reconciliation_csv"])
        duplication_audit.write_csv(paths["duplication_audit_csv"])
        sample_size.write_csv(paths["sample_size_csv"])
        _write_count_reconciliation_markdown(
            paths["count_reconciliation_md"],
            count_reconciliation,
            input_warnings,
        )
        _write_markdown_table(
            paths["duplication_audit_md"],
            "# Forward Event Duplication / Inflation Audit",
            duplication_audit,
            [
                "INFO rows document expected expansion. WARNING/ERROR rows require review.",
                RESEARCH_WARNING,
            ],
        )
        _write_markdown_table(
            paths["sample_size_md"],
            "# Forward Sample Size By Definition",
            sample_size,
            [
                "Rule governance may use journal/rule events for rule-specific evidence.",
                "Money-readiness review must use unique market sessions plus out-of-sample evidence.",
                "No rule is marked validated by this audit.",
                RESEARCH_WARNING,
            ],
        )

    return ForwardEvidenceIntegrityAuditResult(
        count_reconciliation=count_reconciliation,
        duplication_audit=duplication_audit,
        sample_size_by_definition=sample_size,
        final_recommendation=final_recommendation,
        governance_changed=governance_changed,
        paths=paths,
        input_warnings=input_warnings,
    )


def build_count_reconciliation(
    *,
    promoted_outcomes: pl.DataFrame,
    event_level_outcomes: pl.DataFrame,
) -> pl.DataFrame:
    """Reconcile windows, journal observations, rule events, and sessions."""

    promoted_window_rows = promoted_outcomes.height
    unique_outcome_windows = _unique_key_count(
        promoted_outcomes,
        ["journal_id", "outcome_window"],
    )
    unique_journal_ids = _unique_count(promoted_outcomes, "journal_id") or _unique_count(
        event_level_outcomes,
        "journal_id",
    )
    unique_journal_rule_events = _unique_key_count(
        event_level_outcomes,
        ["journal_id", "rule_id", "signal_context"],
    )
    unique_market_sessions = _unique_count(event_level_outcomes, "session_date") or _unique_count(
        promoted_outcomes,
        "session_date",
    )
    unique_trade_dates = _unique_count(promoted_outcomes, "trade_date")
    rules_per_journal_avg = (
        unique_journal_rule_events / unique_journal_ids if unique_journal_ids else 0.0
    )
    windows_per_journal_avg = (
        unique_outcome_windows / unique_journal_ids if unique_journal_ids else 0.0
    )
    multi_rule_expansion = (
        unique_journal_rule_events > promoted_window_rows
        and rules_per_journal_avg > 1.0
        and _unique_count(event_level_outcomes, "rule_id") > 1
    )
    explanation = _count_explanation(
        promoted_window_rows=promoted_window_rows,
        unique_outcome_windows=unique_outcome_windows,
        unique_journal_ids=unique_journal_ids,
        unique_journal_rule_events=unique_journal_rule_events,
        unique_market_sessions=unique_market_sessions,
        multi_rule_expansion=multi_rule_expansion,
    )
    return pl.DataFrame(
        [
            {
                "promoted_window_rows": promoted_window_rows,
                "unique_outcome_windows": unique_outcome_windows,
                "unique_journal_ids": unique_journal_ids,
                "unique_journal_rule_events": unique_journal_rule_events,
                "unique_market_sessions": unique_market_sessions,
                "unique_trade_dates": unique_trade_dates,
                "rules_per_journal_observation_avg": rules_per_journal_avg,
                "windows_per_journal_observation_avg": windows_per_journal_avg,
                "reason_event_count_exceeds_window_count": multi_rule_expansion,
                "explanation_plain_english": explanation,
            }
        ],
        schema=_count_reconciliation_schema(),
        infer_schema_length=None,
    )


def build_duplication_audit(
    *,
    promoted_outcomes: pl.DataFrame,
    event_level_outcomes: pl.DataFrame,
    rule_event_evidence: pl.DataFrame = pl.DataFrame(),
    event_scorecard: pl.DataFrame = pl.DataFrame(),
) -> pl.DataFrame:
    """Detect duplicate keys and document expected expansion conditions."""

    rows = []
    duplicate_windows = _duplicate_rows(promoted_outcomes, ["journal_id", "outcome_window"])
    rows.append(
        _audit_row(
            "duplicate_outcome_windows",
            duplicate_windows,
            "ERROR" if duplicate_windows else "INFO",
            "Remove duplicate promoted rows before interpreting outcomes."
            if duplicate_windows
            else "No duplicate journal/window outcome rows were found.",
        )
    )
    duplicate_journal_rule_window = _duplicate_rows(
        promoted_outcomes,
        ["journal_id", "rule_id", "outcome_window"],
    )
    rows.append(
        _audit_row(
            "duplicate_journal_id_rule_id_window_rows",
            duplicate_journal_rule_window,
            "ERROR" if duplicate_journal_rule_window else "INFO",
            "Deduplicate journal/rule/window rows before aggregation."
            if duplicate_journal_rule_window
            else "No duplicate journal/rule/window promoted rows were found.",
        )
    )
    duplicated_rule_contexts = _duplicate_rule_context_rows(event_level_outcomes)
    rows.append(
        _audit_row(
            "duplicated_rule_contexts",
            duplicated_rule_contexts,
            "WARNING" if duplicated_rule_contexts else "INFO",
            "Inspect rules with multiple contexts for the same journal before changing governance."
            if duplicated_rule_contexts
            else "No duplicated journal/rule contexts were found.",
        )
    )
    duplicated_session_counts = _duplicated_session_context_count(rule_event_evidence)
    rows.append(
        _audit_row(
            "duplicated_market_session_counts",
            duplicated_session_counts,
            "INFO" if duplicated_session_counts else "INFO",
            "Multiple rules can reference the same market session; use unique session counts for money-readiness review."
            if duplicated_session_counts
            else "No duplicated market-session rule contexts were found.",
        )
    )
    placeholder_inflation = _placeholder_expansion_count(
        promoted_outcomes=promoted_outcomes,
        event_level_outcomes=event_level_outcomes,
    )
    rows.append(
        _audit_row(
            "placeholder_rule_expansion_inflation",
            placeholder_inflation,
            "INFO" if placeholder_inflation else "INFO",
            "Promoted preview rows used placeholder rule IDs and were expanded into frozen-rule contexts."
            if placeholder_inflation
            else "No placeholder rule expansion was detected.",
        )
    )
    extra_events = _extra_events_from_enrichment(
        promoted_outcomes=promoted_outcomes,
        event_level_outcomes=event_level_outcomes,
    )
    rows.append(
        _audit_row(
            "extra_events_from_enrichment_logic",
            extra_events,
            "INFO" if extra_events else "INFO",
            "Enrichment added rule-context events; this is allowed only when documented and kept below review floors."
            if extra_events
            else "No rule received more events than available journal observations.",
        )
    )
    rows.append(
        _audit_row(
            "event_scorecard_window_event_gap",
            _scorecard_gap(event_scorecard),
            "INFO",
            "Event scorecard separates promoted window rows from journal/rule events.",
        )
    )
    return pl.DataFrame(rows, schema=_duplication_schema(), infer_schema_length=None)


def build_sample_size_by_definition(
    *,
    promoted_outcomes: pl.DataFrame,
    event_level_outcomes: pl.DataFrame,
    review_floor_count_basis: str = "JOURNAL_RULE_EVENT",
) -> pl.DataFrame:
    """Build rule sample-size warnings under explicit count-basis definitions."""

    basis = review_floor_count_basis.upper()
    if basis not in COUNT_BASIS_VALUES:
        raise ValueError(f"Unsupported review_floor_count_basis: {review_floor_count_basis}")
    if event_level_outcomes.is_empty():
        return pl.DataFrame(schema=_sample_size_schema())

    window_lookup = _window_rows_by_journal(promoted_outcomes)
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in event_level_outcomes.to_dicts():
        rule_id = _string(row.get("rule_id"))
        if rule_id:
            groups.setdefault(rule_id, []).append(row)

    rows = []
    for rule_id, records in groups.items():
        first = records[0]
        journal_rule_events = len(
            {
                (
                    _string(row.get("journal_id")),
                    _string(row.get("rule_id")),
                    _string(row.get("signal_context")),
                )
                for row in records
            }
        )
        journal_ids = {_string(row.get("journal_id")) for row in records if _string(row.get("journal_id"))}
        sessions = {
            _string(row.get("session_date")) for row in records if _string(row.get("session_date"))
        }
        outcome_window_rows = sum(window_lookup.get(journal_id, 0) for journal_id in journal_ids)
        unique_journal_observations = len(journal_ids)
        unique_market_sessions = len(sessions)
        basis_count = _basis_count(
            basis=basis,
            journal_rule_events=journal_rule_events,
            unique_journal_observations=unique_journal_observations,
            unique_market_sessions=unique_market_sessions,
        )
        below_30 = basis_count < MIN_REVIEW_EVENTS
        below_60 = basis_count < MIN_VALIDATION_EVENTS
        rows.append(
            {
                "rule_id": rule_id,
                "rule_name": _string(first.get("rule_name")) or rule_id,
                "rule_family": _string(first.get("rule_family")),
                "outcome_window_rows": outcome_window_rows,
                "journal_rule_events": journal_rule_events,
                "unique_journal_observations": unique_journal_observations,
                "unique_market_sessions": unique_market_sessions,
                "review_floor_count_basis": basis,
                "below_30_event_floor": below_30,
                "below_60_validation_floor": below_60,
                "sample_size_warning": below_30 or below_60,
            }
        )
    return pl.DataFrame(rows, schema=_sample_size_schema(), infer_schema_length=None)


def choose_final_recommendation(duplication_audit: pl.DataFrame) -> str:
    """Return a conservative integrity recommendation."""

    if duplication_audit.is_empty():
        return "INVESTIGATE_EVENT_COUNT_INFLATION"
    severities = {_string(row.get("severity")) for row in duplication_audit.to_dicts()}
    if "ERROR" in severities:
        return "INVESTIGATE_EVENT_COUNT_INFLATION"
    if "WARNING" in severities:
        return "COUNTS_RECONCILED_COLLECT_MORE_EVENTS"
    return FINAL_RECOMMENDATION


def forward_evidence_integrity_report_lines(
    result: ForwardEvidenceIntegrityAuditResult | None,
) -> list[str]:
    """Return research_report.md sections for the integrity audit."""

    if result is None:
        return [
            "## Forward Evidence Count Reconciliation",
            "",
            "Forward evidence integrity audit was not run.",
        ]
    row = (
        result.count_reconciliation.row(0, named=True)
        if not result.count_reconciliation.is_empty()
        else {}
    )
    return [
        "## Forward Evidence Count Reconciliation",
        "",
        _frame_markdown(result.count_reconciliation),
        "",
        "## Duplication / Inflation Audit",
        "",
        _frame_markdown(result.duplication_audit),
        "",
        "## Sample Size Definitions",
        "",
        _frame_markdown(result.sample_size_by_definition),
        "",
        "## Window Rows vs Journal/Rule Events vs Market Sessions",
        "",
        f"- Promoted outcome-window rows: `{row.get('promoted_window_rows', 0)}`.",
        f"- Unique journal observations: `{row.get('unique_journal_ids', 0)}`.",
        f"- Journal/rule events: `{row.get('unique_journal_rule_events', 0)}`.",
        f"- Unique market sessions: `{row.get('unique_market_sessions', 0)}`.",
        "- Journal/rule events can exceed outcome-window rows when one journal observation maps to multiple frozen-rule contexts.",
        "- Truly independent market-session evidence is smaller and must be used for money-readiness review.",
        "",
        "## Conservative Interpretation",
        "",
        f"- Final recommendation: `{result.final_recommendation}`.",
        f"- Governance changed by this audit: `{result.governance_changed}`.",
        "- Counts are reconciled only for research interpretation; no rule is validated here.",
        f"- {RESEARCH_WARNING}",
    ]


def _count_explanation(
    *,
    promoted_window_rows: int,
    unique_outcome_windows: int,
    unique_journal_ids: int,
    unique_journal_rule_events: int,
    unique_market_sessions: int,
    multi_rule_expansion: bool,
) -> str:
    if promoted_window_rows == 0:
        return "No promoted outcome-window rows are available for reconciliation."
    if multi_rule_expansion:
        return (
            f"{promoted_window_rows} promoted window rows represent {unique_journal_ids} "
            f"journal observations and {unique_outcome_windows} unique journal/window pairs. "
            f"Those observations expand to {unique_journal_rule_events} journal/rule events "
            f"because multiple frozen-rule contexts are attached to each observation. The market-session "
            f"count is {unique_market_sessions}, which is the stricter independence view."
        )
    return (
        f"{promoted_window_rows} promoted window rows reconcile to {unique_journal_ids} "
        f"journal observations, {unique_journal_rule_events} journal/rule events, and "
        f"{unique_market_sessions} market sessions."
    )


def _audit_row(
    issue_type: str,
    affected_rows: int,
    severity: str,
    recommended_fix: str,
) -> dict[str, Any]:
    return {
        "issue_type": issue_type,
        "affected_rows": affected_rows,
        "severity": severity,
        "recommended_fix": recommended_fix,
    }


def _duplicate_rows(frame: pl.DataFrame, columns: list[str]) -> int:
    if frame.is_empty() or not all(column in frame.columns for column in columns):
        return 0
    grouped = frame.group_by(columns).len().filter(pl.col("len") > 1)
    if grouped.is_empty():
        return 0
    return int(grouped.get_column("len").sum())


def _duplicate_rule_context_rows(event_level_outcomes: pl.DataFrame) -> int:
    if event_level_outcomes.is_empty() or not {"journal_id", "rule_id"}.issubset(
        event_level_outcomes.columns
    ):
        return 0
    if "signal_context" not in event_level_outcomes.columns:
        return _duplicate_rows(event_level_outcomes, ["journal_id", "rule_id"])
    grouped = (
        event_level_outcomes.group_by(["journal_id", "rule_id"])
        .agg(pl.col("signal_context").n_unique().alias("context_count"))
        .filter(pl.col("context_count") > 1)
    )
    return grouped.height


def _duplicated_session_context_count(rule_event_evidence: pl.DataFrame) -> int:
    if rule_event_evidence.is_empty() or "rule_id" not in rule_event_evidence.columns:
        return 0
    return _duplicate_rows(rule_event_evidence, ["rule_id"])


def _placeholder_expansion_count(
    *,
    promoted_outcomes: pl.DataFrame,
    event_level_outcomes: pl.DataFrame,
) -> int:
    if promoted_outcomes.is_empty() or event_level_outcomes.is_empty():
        return 0
    promoted_rule_ids = _unique_values(promoted_outcomes, "rule_id")
    event_rule_ids = _unique_values(event_level_outcomes, "rule_id")
    if promoted_rule_ids == {DEFAULT_RULE_ID} and len(event_rule_ids - {DEFAULT_RULE_ID}) > 1:
        return event_level_outcomes.height
    return 0


def _extra_events_from_enrichment(
    *,
    promoted_outcomes: pl.DataFrame,
    event_level_outcomes: pl.DataFrame,
) -> int:
    unique_journal_ids = _unique_count(promoted_outcomes, "journal_id") or _unique_count(
        event_level_outcomes,
        "journal_id",
    )
    if not unique_journal_ids or event_level_outcomes.is_empty():
        return 0
    count = 0
    for row in event_level_outcomes.group_by("rule_id").len().to_dicts():
        if (_optional_int(row.get("len")) or 0) > unique_journal_ids:
            count += 1
    return count


def _scorecard_gap(event_scorecard: pl.DataFrame) -> int:
    if event_scorecard.is_empty():
        return 0
    row = event_scorecard.row(0, named=True)
    return max(
        (_optional_int(row.get("independent_events")) or 0)
        - (_optional_int(row.get("promoted_window_rows")) or 0),
        0,
    )


def _basis_count(
    *,
    basis: str,
    journal_rule_events: int,
    unique_journal_observations: int,
    unique_market_sessions: int,
) -> int:
    if basis == "UNIQUE_MARKET_SESSION":
        return unique_market_sessions
    if basis == "UNIQUE_JOURNAL_OBSERVATION":
        return unique_journal_observations
    return journal_rule_events


def _window_rows_by_journal(promoted_outcomes: pl.DataFrame) -> dict[str, int]:
    if promoted_outcomes.is_empty() or "journal_id" not in promoted_outcomes.columns:
        return {}
    if "outcome_window" not in promoted_outcomes.columns:
        return {
            _string(row.get("journal_id")): 1
            for row in promoted_outcomes.select("journal_id").unique().to_dicts()
        }
    result = {}
    grouped = promoted_outcomes.group_by("journal_id").agg(
        pl.col("outcome_window").n_unique().alias("window_count")
    )
    for row in grouped.to_dicts():
        result[_string(row.get("journal_id"))] = _optional_int(row.get("window_count")) or 0
    return result


def _input_warnings(
    *,
    paths: dict[str, Path],
    promoted: pl.DataFrame,
    event_level: pl.DataFrame,
    governance: pl.DataFrame,
    journal: pl.DataFrame,
) -> list[str]:
    warnings = []
    if promoted.is_empty():
        warnings.append("forward_evidence_outcomes_promoted.csv is missing or empty.")
    if event_level.is_empty():
        warnings.append("forward_event_level_outcomes.csv is missing or empty.")
    if governance.is_empty():
        warnings.append("forward_rule_governance.csv is missing or empty.")
    if journal.is_empty() and not paths["journal"].exists():
        warnings.append("forward_evidence_journal.csv is missing; promoted outcomes define journal counts.")
    if not paths["frozen_rulebook"].exists():
        warnings.append("frozen_rulebook_v1.yaml is missing; rulebook content was not reloaded here.")
    if not paths["rulebook_hash"].exists():
        warnings.append("frozen_rulebook_v1_hash.txt is missing; hash was not rechecked here.")
    return warnings


def _write_count_reconciliation_markdown(
    path: Path,
    count_reconciliation: pl.DataFrame,
    input_warnings: tuple[str, ...],
) -> None:
    warnings = "\n".join(f"- {warning}" for warning in input_warnings) or "- none"
    lines = [
        "# Forward Evidence Count Reconciliation",
        "",
        _frame_markdown(count_reconciliation),
        "",
        "## Input Warnings",
        "",
        warnings,
        "",
        "- Outcome-window rows, journal observations, journal/rule events, and market sessions are separate count bases.",
        "- Money-readiness review must use unique market sessions plus out-of-sample evidence.",
        f"- {RESEARCH_WARNING}",
    ]
    path.write_text(_safe_report_text("\n".join(lines)), encoding="utf-8")


def _write_markdown_table(
    path: Path,
    title: str,
    frame: pl.DataFrame,
    notes: list[str],
) -> None:
    lines = [title, "", _frame_markdown(frame), ""]
    lines.extend(f"- {note}" for note in notes)
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


def _unique_key_count(frame: pl.DataFrame, columns: list[str]) -> int:
    if frame.is_empty() or not all(column in frame.columns for column in columns):
        return 0
    return frame.select(columns).unique().height


def _unique_count(frame: pl.DataFrame, column: str) -> int:
    if frame.is_empty() or column not in frame.columns:
        return 0
    return frame.select(column).unique().height


def _unique_values(frame: pl.DataFrame, column: str) -> set[str]:
    if frame.is_empty() or column not in frame.columns:
        return set()
    return {_string(value) for value in frame.get_column(column).to_list() if _string(value)}


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


def _string(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _count_reconciliation_schema() -> dict[str, Any]:
    return {
        "promoted_window_rows": pl.Int64,
        "unique_outcome_windows": pl.Int64,
        "unique_journal_ids": pl.Int64,
        "unique_journal_rule_events": pl.Int64,
        "unique_market_sessions": pl.Int64,
        "unique_trade_dates": pl.Int64,
        "rules_per_journal_observation_avg": pl.Float64,
        "windows_per_journal_observation_avg": pl.Float64,
        "reason_event_count_exceeds_window_count": pl.Boolean,
        "explanation_plain_english": pl.String,
    }


def _duplication_schema() -> dict[str, Any]:
    return {
        "issue_type": pl.String,
        "affected_rows": pl.Int64,
        "severity": pl.String,
        "recommended_fix": pl.String,
    }


def _sample_size_schema() -> dict[str, Any]:
    return {
        "rule_id": pl.String,
        "rule_name": pl.String,
        "rule_family": pl.String,
        "outcome_window_rows": pl.Int64,
        "journal_rule_events": pl.Int64,
        "unique_journal_observations": pl.Int64,
        "unique_market_sessions": pl.Int64,
        "review_floor_count_basis": pl.String,
        "below_30_event_floor": pl.Boolean,
        "below_60_validation_floor": pl.Boolean,
        "sample_size_warning": pl.Boolean,
    }


def main() -> None:
    """CLI entry point for local integrity report generation."""

    result = run_forward_evidence_integrity_audit()
    row = result.count_reconciliation.row(0, named=True) if not result.count_reconciliation.is_empty() else {}
    print(f"promoted_window_rows: {row.get('promoted_window_rows', 0)}")
    print(f"unique_journal_ids: {row.get('unique_journal_ids', 0)}")
    print(f"unique_journal_rule_events: {row.get('unique_journal_rule_events', 0)}")
    print(f"unique_market_sessions: {row.get('unique_market_sessions', 0)}")
    print(f"final_recommendation: {result.final_recommendation}")


if __name__ == "__main__":
    main()
