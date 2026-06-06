from __future__ import annotations

from pathlib import Path

import polars as pl

from research_xau_vol_oi.xau_trade_quality_usage_guide import (
    ALLOWED_JOURNAL_ACTIONS,
    build_component_guide,
    report_text_is_safe,
    run_xau_trade_quality_usage_guide,
)


def test_guide_never_outputs_buy_or_sell(tmp_path: Path) -> None:
    output = _write_usage_inputs(tmp_path)

    run_xau_trade_quality_usage_guide(output_dir=output)
    text = "\n".join(
        [
            (output / "xau_trade_quality_usage_guide.md").read_text(encoding="utf-8"),
            (output / "xau_manual_trade_review_checklist.md").read_text(encoding="utf-8"),
            (output / "xau_latest_watchlist_explanation.md").read_text(encoding="utf-8"),
        ]
    )

    assert "BUY" not in text.upper()
    assert "SELL" not in text.upper()
    assert report_text_is_safe(text)


def test_hard_blockers_are_marked_correctly() -> None:
    guide = build_component_guide(component_failure=_component_failure())
    roles = {row["component_name"]: row["current_role"] for row in guide.to_dicts()}

    assert roles["fee_spread_hurdle_component"] == "HARD_BLOCKER"
    assert roles["data_quality_component"] == "HARD_BLOCKER"
    assert roles["stale_data_component"] == "HARD_BLOCKER"
    assert roles["no_trade_middle_range_component"] == "HARD_BLOCKER"


def test_cme_and_guru_components_are_not_marked_validated(tmp_path: Path) -> None:
    result = run_xau_trade_quality_usage_guide(output_dir=_write_usage_inputs(tmp_path))
    rows = {row["component_name"]: row for row in result.component_guide.to_dicts()}

    assert rows["cme_wall_context_component"]["current_confidence"] == "PILOT_ONLY"
    assert rows["cme_iv_range_component"]["current_confidence"] == "PILOT_ONLY"
    assert rows["guru_filter_component"]["current_confidence"] == "CONTEXT_ONLY"
    assert rows["guru_filter_component"]["current_role"] == "CONTEXT_ONLY"


def test_v1_tuning_is_forbidden(tmp_path: Path) -> None:
    result = run_xau_trade_quality_usage_guide(output_dir=_write_usage_inputs(tmp_path))
    guardrail = result.guardrail_summary.row(0, named=True)

    assert guardrail["v1_tuning_forbidden"]
    assert "KEEP_V1_FROZEN" in guardrail["guardrails"]
    assert result.final_recommendation == "USE_AS_MANUAL_CHECKLIST"


def test_checklist_outputs_only_allowed_journal_actions(tmp_path: Path) -> None:
    result = run_xau_trade_quality_usage_guide(output_dir=_write_usage_inputs(tmp_path))

    actions = set(result.checklist.get_column("journal_action").to_list())
    assert actions.issubset(set(ALLOWED_JOURNAL_ACTIONS))


def test_latest_watchlist_explanation_is_generated(tmp_path: Path) -> None:
    output = _write_usage_inputs(tmp_path)

    result = run_xau_trade_quality_usage_guide(output_dir=output)
    text = (output / "xau_latest_watchlist_explanation.md").read_text(encoding="utf-8")
    row = result.latest_watchlist.row(0, named=True)

    assert row["latest_score"] == 47
    assert row["score_bucket"] == "WATCH_ONLY"
    assert "manual review aid" in text


def test_report_does_not_claim_profitability(tmp_path: Path) -> None:
    output = _write_usage_inputs(tmp_path)

    run_xau_trade_quality_usage_guide(output_dir=output)
    text = (output / "xau_score_guardrail_summary.md").read_text(encoding="utf-8")

    assert "profitability" not in text.lower()
    assert "profitable" not in text.lower()
    assert "guaranteed edge" not in text.lower()
    assert report_text_is_safe(text)


def test_reports_use_redacted_paths_only(tmp_path: Path) -> None:
    output = _write_usage_inputs(tmp_path)

    run_xau_trade_quality_usage_guide(output_dir=output)
    text = (output / "xau_trade_quality_usage_guide.md").read_text(encoding="utf-8")

    assert str(tmp_path) not in text
    assert "C:" not in text
    assert report_text_is_safe(text)


def _write_usage_inputs(tmp_path: Path) -> Path:
    output = tmp_path / "outputs"
    output.mkdir(parents=True, exist_ok=True)
    (output / "xau_trade_quality_score_v1.yaml").write_text(
        "\n".join(
            [
                "version: xau_trade_quality_score_v1",
                "tuning_allowed: false",
                "threshold_optimization_allowed: false",
                "validated: false",
            ]
        ),
        encoding="utf-8",
    )
    _daily_watchlist().write_csv(output / "xau_trade_quality_daily_watchlist.csv")
    _bucket_inversion().write_csv(output / "xau_score_bucket_inversion_audit.csv")
    _component_failure().write_csv(output / "xau_score_component_failure_audit.csv")
    _join_audit().write_csv(output / "xau_score_forward_join_audit.csv")
    _failure_decision().write_csv(output / "xau_score_failure_decision.csv")
    _price_interpretation().write_csv(output / "dukascopy_price_rule_interpretation.csv")
    _guru_interpretation().write_csv(output / "dukascopy_guru_logic_interpretation.csv")
    _cme_interpretation().write_csv(output / "dukascopy_cme_overlap_interpretation.csv")
    return output


def _daily_watchlist() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "session_date": "2026-05-26",
                "timeframe": "15m",
                "latest_price": 4542.5035,
                "latest_score": 47,
                "score_bucket": "WATCH_ONLY",
                "active_positive_components": "data_quality_component;cme_wall_context_component",
                "active_negative_components": "guru_filter_component",
                "blocked_reasons": "GURU_FILTER_CONTEXT",
                "watch_reasons": "CME_WALL_CONTEXT;CME_IV_CONTEXT",
                "journal_action": "WATCH_ONLY",
            }
        ],
        infer_schema_length=None,
    )


def _bucket_inversion() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "bucket": "ALLOW_RESEARCH",
                "resolved_count": 4,
                "average_return": -28.825,
                "reason_bucket_underperformed": "SAMPLE_TOO_SMALL;SESSION_CLUSTERED",
            },
            {
                "bucket": "WATCH_ONLY",
                "resolved_count": 105,
                "average_return": -16.113,
                "reason_bucket_underperformed": "LOW_SCORE_CONTROL_ROWS_NOT_DIRECTLY_COMPARABLE",
            },
        ],
        infer_schema_length=None,
    )


def _component_failure() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "component_name": "acceptance_breakout_component",
                "effect_direction": "TOO_EARLY",
                "possible_issue": "SAMPLE_TOO_SMALL",
                "recommended_action": "DO_NOT_TUNE_YET",
            },
            {
                "component_name": "fee_spread_hurdle_component",
                "effect_direction": "TOO_EARLY",
                "possible_issue": "SAMPLE_TOO_SMALL",
                "recommended_action": "DO_NOT_TUNE_YET",
            },
        ],
        infer_schema_length=None,
    )


def _join_audit() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "issue_type": "same_event_counted_multiple_times",
                "affected_rows": 109,
                "severity": "WARNING",
                "recommended_fix": "Use event-level review.",
            }
        ],
        infer_schema_length=None,
    )


def _failure_decision() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "final_recommendation": "NEEDS_MORE_FORWARD_DATA",
                "high_score_resolved_count": 4,
                "low_score_resolved_count": 105,
                "join_error_count": 0,
            }
        ],
        infer_schema_length=None,
    )


def _price_interpretation() -> pl.DataFrame:
    return pl.DataFrame(
        [{"rule": "ACCEPTANCE_BREAKOUT", "evidence_strength": "PROMISING"}],
        infer_schema_length=None,
    )


def _guru_interpretation() -> pl.DataFrame:
    return pl.DataFrame(
        [{"guru_logic": "context", "remain_context_only": True}],
        infer_schema_length=None,
    )


def _cme_interpretation() -> pl.DataFrame:
    return pl.DataFrame(
        [{"interpretation_label": "CME_OVERLAP_PILOT_ONLY"}],
        infer_schema_length=None,
    )
