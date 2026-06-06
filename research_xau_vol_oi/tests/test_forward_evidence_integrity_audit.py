from __future__ import annotations

from pathlib import Path

import polars as pl

from research_xau_vol_oi.forward_evidence_integrity_audit import (
    ForwardEvidenceIntegrityAuditResult,
    build_count_reconciliation,
    build_duplication_audit,
    build_sample_size_by_definition,
    forward_evidence_integrity_report_lines,
    run_forward_evidence_integrity_audit,
)


def test_outcome_window_rows_are_distinct_from_journal_rule_events() -> None:
    promoted = _promoted_frame(
        [
            _promoted_row("journal_1", "30m"),
            _promoted_row("journal_1", "1h"),
            _promoted_row("journal_2", "30m"),
            _promoted_row("journal_2", "1h"),
        ]
    )
    event_level = _event_frame(
        [
            _event_row("journal_1", "RULE_A"),
            _event_row("journal_1", "RULE_B"),
            _event_row("journal_2", "RULE_A"),
            _event_row("journal_2", "RULE_B"),
            _event_row("journal_2", "RULE_C"),
        ]
    )

    reconciliation = build_count_reconciliation(
        promoted_outcomes=promoted,
        event_level_outcomes=event_level,
    )

    row = reconciliation.row(0, named=True)
    assert row["promoted_window_rows"] == 4
    assert row["unique_journal_ids"] == 2
    assert row["unique_journal_rule_events"] == 5
    assert row["rules_per_journal_observation_avg"] == 2.5


def test_event_count_can_exceed_window_count_only_with_documented_multi_rule_expansion() -> None:
    promoted = _promoted_frame(
        [
            _promoted_row("journal_1", "30m"),
            _promoted_row("journal_1", "1h"),
        ]
    )
    event_level = _event_frame(
        [
            _event_row("journal_1", "RULE_A"),
            _event_row("journal_1", "RULE_B"),
            _event_row("journal_1", "RULE_C"),
        ]
    )

    reconciliation = build_count_reconciliation(
        promoted_outcomes=promoted,
        event_level_outcomes=event_level,
    )
    audit = build_duplication_audit(
        promoted_outcomes=promoted,
        event_level_outcomes=event_level,
        event_scorecard=pl.DataFrame(
            [{"promoted_window_rows": 2, "independent_events": 3}]
        ),
    )

    row = reconciliation.row(0, named=True)
    assert row["reason_event_count_exceeds_window_count"] is True
    assert "multiple frozen-rule contexts" in row["explanation_plain_english"]
    gap = audit.filter(pl.col("issue_type") == "event_scorecard_window_event_gap").row(
        0,
        named=True,
    )
    assert gap["severity"] == "INFO"
    assert gap["affected_rows"] == 1


def test_duplicate_journal_rule_window_rows_are_detected() -> None:
    promoted = _promoted_frame(
        [
            _promoted_row("journal_1", "30m", rule_id="RULE_A"),
            _promoted_row("journal_1", "30m", rule_id="RULE_A"),
        ]
    )

    audit = build_duplication_audit(
        promoted_outcomes=promoted,
        event_level_outcomes=_event_frame([_event_row("journal_1", "RULE_A")]),
    )

    duplicate = audit.filter(
        pl.col("issue_type") == "duplicate_journal_id_rule_id_window_rows"
    ).row(0, named=True)
    assert duplicate["affected_rows"] == 2
    assert duplicate["severity"] == "ERROR"


def test_sample_size_warning_uses_configured_count_basis() -> None:
    promoted = _promoted_frame(
        [_promoted_row(f"journal_{index}", "30m") for index in range(30)]
    )
    event_level = _event_frame(
        [_event_row(f"journal_{index}", "RULE_A", session_date="2026-05-14") for index in range(30)]
    )

    by_rule_event = build_sample_size_by_definition(
        promoted_outcomes=promoted,
        event_level_outcomes=event_level,
        review_floor_count_basis="JOURNAL_RULE_EVENT",
    )
    by_market_session = build_sample_size_by_definition(
        promoted_outcomes=promoted,
        event_level_outcomes=event_level,
        review_floor_count_basis="UNIQUE_MARKET_SESSION",
    )

    assert by_rule_event.row(0, named=True)["below_30_event_floor"] is False
    assert by_market_session.row(0, named=True)["below_30_event_floor"] is True
    assert by_market_session.row(0, named=True)["review_floor_count_basis"] == "UNIQUE_MARKET_SESSION"


def test_validation_label_is_blocked_below_floor() -> None:
    sample = build_sample_size_by_definition(
        promoted_outcomes=_promoted_frame(
            [_promoted_row(f"journal_{index}", "30m") for index in range(10)]
        ),
        event_level_outcomes=_event_frame(
            [_event_row(f"journal_{index}", "RULE_A") for index in range(10)]
        ),
    )

    row = sample.row(0, named=True)
    assert row["below_60_validation_floor"] is True
    assert row["sample_size_warning"] is True


def test_money_readiness_uses_market_session_count_not_window_rows() -> None:
    promoted = _promoted_frame(
        [
            _promoted_row("journal_1", "30m"),
            _promoted_row("journal_1", "1h"),
            _promoted_row("journal_1", "4h"),
        ]
    )
    event_level = _event_frame([_event_row("journal_1", "RULE_A", session_date="2026-05-14")])

    reconciliation = build_count_reconciliation(
        promoted_outcomes=promoted,
        event_level_outcomes=event_level,
    )
    sample = build_sample_size_by_definition(
        promoted_outcomes=promoted,
        event_level_outcomes=event_level,
        review_floor_count_basis="UNIQUE_MARKET_SESSION",
    )

    assert reconciliation.row(0, named=True)["promoted_window_rows"] == 3
    assert reconciliation.row(0, named=True)["unique_market_sessions"] == 1
    assert sample.row(0, named=True)["below_30_event_floor"] is True


def test_report_does_not_claim_profitability() -> None:
    promoted = _promoted_frame([_promoted_row("journal_1", "30m")])
    event_level = _event_frame([_event_row("journal_1", "RULE_A")])
    reconciliation = build_count_reconciliation(
        promoted_outcomes=promoted,
        event_level_outcomes=event_level,
    )
    audit = build_duplication_audit(
        promoted_outcomes=promoted,
        event_level_outcomes=event_level,
    )
    sample = build_sample_size_by_definition(
        promoted_outcomes=promoted,
        event_level_outcomes=event_level,
    )
    text = "\n".join(
        forward_evidence_integrity_report_lines(
            ForwardEvidenceIntegrityAuditResult(
                count_reconciliation=reconciliation,
                duplication_audit=audit,
                sample_size_by_definition=sample,
                final_recommendation="COUNTS_RECONCILED_COLLECT_MORE_EVENTS",
                governance_changed=False,
                paths={},
                input_warnings=(),
            )
        )
    ).lower()

    assert "profitable" not in text
    assert "profitability" not in text
    assert "predicts price" not in text
    assert "live ready" not in text


def test_reports_use_redacted_paths(tmp_path: Path) -> None:
    output = tmp_path / "outputs"
    output.mkdir()
    _promoted_frame([_promoted_row("journal_1", "30m")]).write_csv(
        output / "forward_evidence_outcomes_promoted.csv"
    )
    _event_frame([_event_row("journal_1", "RULE_A")]).write_csv(
        output / "forward_event_level_outcomes.csv"
    )
    pl.DataFrame(
        [
            {
                "rule_id": "RULE_A",
                "independent_event_count": 1,
                "event_sample_size_warning": True,
            }
        ]
    ).write_csv(output / "forward_rule_event_evidence.csv")
    pl.DataFrame(
        [
            {
                "rule_id": "RULE_A",
                "recommendation": "KEEP_COLLECTING",
            }
        ]
    ).write_csv(output / "forward_rule_governance.csv")

    run_forward_evidence_integrity_audit(output_dir=output)

    report_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in output.glob("forward_*integrity*.md")
    )
    report_text += "\n".join(
        path.read_text(encoding="utf-8")
        for path in output.glob("forward_*reconciliation.md")
    )
    report_text += "\n".join(
        path.read_text(encoding="utf-8")
        for path in output.glob("forward_*duplication*.md")
    )
    report_text += "\n".join(
        path.read_text(encoding="utf-8")
        for path in output.glob("forward_sample_size*.md")
    )
    assert str(tmp_path) not in report_text
    assert "C:\\" not in report_text


def _promoted_frame(rows: list[dict[str, object]]) -> pl.DataFrame:
    return pl.DataFrame(rows, infer_schema_length=None)


def _event_frame(rows: list[dict[str, object]]) -> pl.DataFrame:
    return pl.DataFrame(rows, infer_schema_length=None)


def _promoted_row(
    journal_id: str,
    outcome_window: str,
    *,
    rule_id: str = "FORWARD_OUTCOME_PREVIEW",
    session_date: str = "2026-05-14",
) -> dict[str, object]:
    return {
        "journal_id": journal_id,
        "rule_id": rule_id,
        "outcome_window": outcome_window,
        "trade_date": session_date,
        "session_date": session_date,
    }


def _event_row(
    journal_id: str,
    rule_id: str,
    *,
    signal_context: str = "PRICE_ONLY_RULES",
    session_date: str = "2026-05-14",
) -> dict[str, object]:
    return {
        "journal_id": journal_id,
        "rule_id": rule_id,
        "rule_name": rule_id.title().replace("_", " "),
        "rule_family": "PRICE_ONLY",
        "signal_context": signal_context,
        "session_date": session_date,
        "windows_available": "30m|1h",
    }
