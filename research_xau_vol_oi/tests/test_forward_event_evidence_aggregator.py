from __future__ import annotations

from pathlib import Path

import polars as pl

from research_xau_vol_oi.forward_event_evidence_aggregator import (
    build_event_level_outcomes,
    build_event_scorecard,
    build_next_rule_focus_list,
    build_rule_event_evidence,
    build_rule_governance,
    forward_event_evidence_report_lines,
    run_forward_event_evidence_aggregator,
)


def test_multiple_windows_for_same_journal_id_aggregate_into_one_event() -> None:
    events = build_event_level_outcomes(
        promoted_outcomes=_promoted_frame(
            [
                _promoted_row("journal_1", "RULE_A", "30m", close_return=-1.0),
                _promoted_row("journal_1", "RULE_A", "1h", close_return=2.0),
                _promoted_row("journal_1", "RULE_A", "4h", close_return=3.0),
            ]
        )
    )

    row = events.row(0, named=True)
    assert events.height == 1
    assert row["windows_available"] == "30m|1h|4h"
    assert row["windows_supported_count"] == 2
    assert row["windows_failed_count"] == 1


def test_window_rows_are_not_counted_as_independent_trades() -> None:
    promoted = _promoted_frame(
        [
            _promoted_row("journal_1", "RULE_A", "30m", close_return=-1.0),
            _promoted_row("journal_1", "RULE_A", "1h", close_return=2.0),
            _promoted_row("journal_1", "RULE_A", "4h", close_return=3.0),
        ]
    )
    events = build_event_level_outcomes(promoted_outcomes=promoted)
    scorecard = build_event_scorecard(
        promoted_outcomes=promoted,
        event_level_outcomes=events,
        pending_summary=pl.DataFrame(),
        rule_event_evidence=build_rule_event_evidence(events),
    )

    row = scorecard.row(0, named=True)
    assert row["promoted_window_rows"] == 3
    assert row["independent_events"] == 1


def test_primary_window_selection_by_rule_type() -> None:
    promoted = _promoted_frame(
        [
            _promoted_row("entry_1", "ENTRY_RULE", "30m", close_return=-1.0),
            _promoted_row("entry_1", "ENTRY_RULE", "1h", close_return=2.0),
            _promoted_row("entry_1", "ENTRY_RULE", "session_close", close_return=-3.0),
            _promoted_row(
                "filter_1",
                "FILTER_RULE",
                "1h",
                rule_type="FILTER",
                event_type="BLOCK",
                blocked_trade=True,
                close_return=4.0,
            ),
            _promoted_row(
                "filter_1",
                "FILTER_RULE",
                "session_close",
                rule_type="FILTER",
                event_type="BLOCK",
                blocked_trade=True,
                close_return=-5.0,
            ),
            _promoted_row(
                "map_1",
                "MAP_RULE",
                "1h",
                rule_type="MARKET_MAP",
                close_return=1.0,
                wall_touched=False,
                wall_accepted=False,
            ),
            _promoted_row(
                "map_1",
                "MAP_RULE",
                "4h",
                rule_type="MARKET_MAP",
                close_return=-1.0,
                wall_touched=True,
            ),
        ]
    )

    events = build_event_level_outcomes(promoted_outcomes=promoted)
    rows = {row["rule_id"]: row for row in events.to_dicts()}
    assert rows["ENTRY_RULE"]["primary_window"] == "1h"
    assert rows["ENTRY_RULE"]["primary_window_result"] == "supported"
    assert rows["FILTER_RULE"]["primary_window"] == "session_close"
    assert rows["FILTER_RULE"]["event_outcome_label"] == "EVENT_MIXED"
    assert rows["MAP_RULE"]["primary_window"] == "4h"
    assert rows["MAP_RULE"]["event_outcome_label"] == "EVENT_SUPPORTED"


def test_event_level_sample_size_warning_uses_independent_event_count() -> None:
    promoted = _promoted_frame(
        [
            _promoted_row("journal_1", "RULE_A", "30m", close_return=1.0),
            _promoted_row("journal_1", "RULE_A", "1h", close_return=1.0),
            _promoted_row("journal_2", "RULE_A", "30m", close_return=-1.0),
            _promoted_row("journal_2", "RULE_A", "1h", close_return=-1.0),
        ]
    )
    rule_evidence = build_rule_event_evidence(
        build_event_level_outcomes(promoted_outcomes=promoted)
    )

    row = rule_evidence.row(0, named=True)
    assert row["independent_event_count"] == 2
    assert row["event_sample_size_warning"] is True
    assert row["evidence_label"] in {"TOO_EARLY", "PROMISING_PILOT"}


def test_governance_does_not_validate_rules_below_threshold() -> None:
    governance = build_rule_governance(
        _rule_event_evidence_frame(
            independent_event_count=10,
            evidence_label="PROMISING_PILOT",
            support_rate_event_level=0.7,
            fail_rate_event_level=0.3,
        )
    )

    row = governance.row(0, named=True)
    assert "VALIDATED" not in row["recommendation"]
    assert row["can_change_rule_now"] is False
    assert row["next_required_events"] == 20


def test_governance_does_not_tune_frozen_rules() -> None:
    governance = build_rule_governance(
        _rule_event_evidence_frame(
            independent_event_count=8,
            evidence_label="PROMISING_PILOT",
            support_rate_event_level=0.8,
            fail_rate_event_level=0.2,
        )
    )

    row = governance.row(0, named=True)
    assert row["can_change_rule_now"] is False
    assert "tune" not in row["reason"].lower()


def test_weak_low_sample_rules_are_not_killed_automatically() -> None:
    governance = build_rule_governance(
        _rule_event_evidence_frame(
            independent_event_count=10,
            evidence_label="TOO_EARLY",
            support_rate_event_level=0.1,
            fail_rate_event_level=0.9,
        )
    )

    assert governance.row(0, named=True)["recommendation"] == "WEAK_BUT_TOO_EARLY"


def test_filter_candidate_recommendation_works() -> None:
    promoted = _promoted_frame(
        [
            _promoted_row(
                f"filter_{index}",
                "FILTER_RULE",
                "session_close",
                rule_type="FILTER",
                event_type="BLOCK",
                blocked_trade=True,
                close_return=-1.0,
            )
            for index in range(5)
        ]
    )
    events = build_event_level_outcomes(promoted_outcomes=promoted)
    governance = build_rule_governance(build_rule_event_evidence(events))

    row = governance.row(0, named=True)
    assert row["evidence_label"] == "PROMISING_PILOT"
    assert row["recommendation"] == "KEEP_AS_FILTER_CANDIDATE"


def test_market_map_context_recommendation_works() -> None:
    promoted = _promoted_frame(
        [
            _promoted_row(
                f"map_{index}",
                "MAP_RULE",
                "1h",
                rule_type="MARKET_MAP",
                wall_touched=True,
                close_return=1.0,
            )
            for index in range(5)
        ]
    )
    events = build_event_level_outcomes(promoted_outcomes=promoted)
    governance = build_rule_governance(build_rule_event_evidence(events))

    row = governance.row(0, named=True)
    assert row["evidence_label"] == "PROMISING_PILOT"
    assert row["recommendation"] == "KEEP_AS_MARKET_MAP_CONTEXT"


def test_scorecard_reports_independent_events_separately_from_window_rows() -> None:
    promoted = _promoted_frame(
        [
            _promoted_row("journal_1", "RULE_A", "30m", close_return=1.0),
            _promoted_row("journal_1", "RULE_A", "1h", close_return=1.0),
            _promoted_row("journal_1", "RULE_A", "4h", close_return=1.0),
        ]
    )
    events = build_event_level_outcomes(promoted_outcomes=promoted)
    scorecard = build_event_scorecard(
        promoted_outcomes=promoted,
        event_level_outcomes=events,
        pending_summary=pl.DataFrame([{"journal_id": "pending_1"}]),
        rule_event_evidence=build_rule_event_evidence(events),
    )

    row = scorecard.row(0, named=True)
    assert row["promoted_window_rows"] == 3
    assert row["independent_events"] == 1
    assert row["pending_events"] == 1


def test_report_does_not_claim_profitability() -> None:
    promoted = _promoted_frame([_promoted_row("journal_1", "RULE_A", "1h", close_return=1.0)])
    events = build_event_level_outcomes(promoted_outcomes=promoted)
    rule_evidence = build_rule_event_evidence(events)
    result_lines = forward_event_evidence_report_lines(
        _result_for_report(
            events=events,
            rule_evidence=rule_evidence,
            governance=build_rule_governance(rule_evidence),
            focus=build_next_rule_focus_list(
                rule_event_evidence=rule_evidence,
                rule_governance=build_rule_governance(rule_evidence),
            ),
            scorecard=build_event_scorecard(
                promoted_outcomes=promoted,
                event_level_outcomes=events,
                pending_summary=pl.DataFrame(),
                rule_event_evidence=rule_evidence,
            ),
        )
    )
    text = "\n".join(result_lines).lower()
    assert "profitable" not in text
    assert "profitability" not in text
    assert "predicts price" not in text
    assert "live ready" not in text


def test_reports_use_redacted_paths(tmp_path: Path) -> None:
    output = tmp_path / "outputs"
    output.mkdir()
    _promoted_frame(
        [
            _promoted_row("journal_1", "RULE_A", "30m", close_return=1.0),
            _promoted_row("journal_1", "RULE_A", "1h", close_return=1.0),
        ]
    ).write_csv(output / "forward_evidence_outcomes_promoted.csv")

    run_forward_event_evidence_aggregator(output_dir=output)

    report_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in output.glob("*event*.md")
    )
    assert str(tmp_path) not in report_text
    assert "C:\\" not in report_text


def _promoted_frame(rows: list[dict[str, object]]) -> pl.DataFrame:
    return pl.DataFrame(rows, infer_schema_length=None)


def _promoted_row(
    journal_id: str,
    rule_id: str,
    window: str,
    *,
    rule_type: str = "ENTRY_TRIGGER",
    rule_family: str = "PRICE_ONLY",
    signal_context: str = "PRICE_ONLY_RULES",
    close_return: float = 1.0,
    event_type: str = "TRADE_CANDIDATE",
    blocked_trade: bool = False,
    wall_touched: bool = True,
    wall_rejected: bool = False,
    wall_accepted: bool = True,
) -> dict[str, object]:
    return {
        "journal_id": journal_id,
        "rule_id": rule_id,
        "rule_name": rule_id.title().replace("_", " "),
        "rule_family": rule_family,
        "rule_type": rule_type,
        "signal_context": signal_context,
        "observation_timestamp": "2026-05-14T03:08:00Z",
        "trade_date": "2026-05-14",
        "session_date": "2026-05-14",
        "outcome_window": window,
        "close_return": close_return,
        "mfe": max(close_return, 0.5),
        "mae": min(close_return, -0.5),
        "outcome_result": _outcome_result(close_return),
        "event_type": event_type,
        "blocked_trade": blocked_trade,
        "wall_touched": wall_touched,
        "wall_rejected": wall_rejected,
        "wall_accepted": wall_accepted,
    }


def _outcome_result(close_return: float) -> str:
    if close_return > 0:
        return "supported"
    if close_return < 0:
        return "failed"
    return "no_clear_outcome"


def _rule_event_evidence_frame(
    *,
    independent_event_count: int,
    evidence_label: str,
    support_rate_event_level: float,
    fail_rate_event_level: float,
    rule_type: str = "ENTRY_TRIGGER",
) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "rule_id": "RULE_A",
                "rule_name": "Rule A",
                "rule_family": "PRICE_ONLY",
                "rule_type": rule_type,
                "signal_context": "PRICE_ONLY_RULES",
                "independent_event_count": independent_event_count,
                "supported_events": int(independent_event_count * support_rate_event_level),
                "failed_events": int(independent_event_count * fail_rate_event_level),
                "mixed_events": 0,
                "no_clear_events": 0,
                "support_rate_event_level": support_rate_event_level,
                "fail_rate_event_level": fail_rate_event_level,
                "average_primary_return": 1.0,
                "average_mfe": 2.0,
                "average_mae": -1.0,
                "adverse_to_favorable_ratio": 0.5,
                "filter_helped_events": 0,
                "filter_false_block_events": 0,
                "wall_touch_events": independent_event_count,
                "wall_rejection_events": 0,
                "wall_acceptance_events": independent_event_count,
                "event_sample_size_warning": independent_event_count < 30,
                "evidence_label": evidence_label,
            }
        ],
        infer_schema_length=None,
    )


def _result_for_report(
    *,
    events: pl.DataFrame,
    rule_evidence: pl.DataFrame,
    governance: pl.DataFrame,
    focus: pl.DataFrame,
    scorecard: pl.DataFrame,
):
    from research_xau_vol_oi.forward_event_evidence_aggregator import (
        ForwardEventEvidenceAggregatorResult,
    )

    return ForwardEventEvidenceAggregatorResult(
        event_level_outcomes=events,
        rule_event_evidence=rule_evidence,
        rule_governance=governance,
        focus_list=focus,
        event_scorecard=scorecard,
        final_recommendation="COLLECT_MORE_FORWARD_EVENTS",
        paths={},
        input_warnings=(),
    )
