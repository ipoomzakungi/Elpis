from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from research_xau_vol_oi.dukascopy_forward_evidence_refresh import (
    build_cme_overlap_interpretation,
    build_dukascopy_event_level_outcomes,
    build_dukascopy_forward_outcome_audit,
    build_guru_logic_interpretation,
    build_price_rule_interpretation,
    promote_dukascopy_outcomes,
    report_text_is_safe,
    run_dukascopy_forward_evidence_refresh,
)


def test_dukascopy_resolved_rows_promote_only_with_coverage() -> None:
    audit = build_dukascopy_forward_outcome_audit(
        dukascopy_outcomes=pl.DataFrame(
            [
                _dukascopy_row("j1", "30m", newly=True),
                _dukascopy_row("j1", "1h", newly=True, still_pending=True),
                _dukascopy_row("j1", "4h", newly=True, source="YAHOO"),
            ],
            infer_schema_length=None,
        )
    )

    assert audit.filter(pl.col("safe_to_promote")).height == 1
    assert "STILL_PENDING" in audit.row(1, named=True)["reject_reason"]
    assert "INSUFFICIENT_DUKASCOPY_COVERAGE" in audit.row(2, named=True)["reject_reason"]


def test_promotion_does_not_duplicate_existing_outcomes() -> None:
    dukascopy = pl.DataFrame(
        [
            _dukascopy_row("j1", "30m", newly=True),
            _dukascopy_row("j1", "1h", newly=True),
        ],
        infer_schema_length=None,
    )
    audit = build_dukascopy_forward_outcome_audit(dukascopy_outcomes=dukascopy)
    existing = pl.DataFrame(
        [
            {
                "journal_id": "j1",
                "outcome_window": "30m",
                "rule_id": "FORWARD_OUTCOME_PREVIEW",
                "rule_name": "Forward outcome preview",
            }
        ],
        infer_schema_length=None,
    )

    promoted, summary = promote_dukascopy_outcomes(
        dukascopy_outcomes=dukascopy,
        outcome_audit=audit,
        existing_promoted=existing,
        promoted_at=datetime(2026, 5, 26, tzinfo=UTC),
    )

    row = summary.row(0, named=True)
    assert row["before_promoted_count"] == 1
    assert row["newly_promoted_count"] == 1
    assert row["duplicate_rows_skipped"] == 1
    assert promoted.height == 2


def test_event_aggregation_uses_independent_events_not_windows() -> None:
    promoted = pl.DataFrame(
        [
            _promoted_row("j1", "30m", close_return=2.0),
            _promoted_row("j1", "1h", close_return=-1.0),
            _promoted_row("j2", "30m", close_return=3.0),
        ],
        infer_schema_length=None,
    )

    events = build_dukascopy_event_level_outcomes(promoted)

    assert events.height == 2
    assert events.get_column("independent_event_count").sum() == 2
    assert events.filter(pl.col("journal_id") == "j1").row(0, named=True)[
        "windows_available"
    ] == "30m,1h"


def test_no_trade_middle_interpreted_as_filter_when_expectancy_is_negative() -> None:
    interpretation = build_price_rule_interpretation(
        pl.DataFrame(
            [
                _price_rule("NO_TRADE_MIDDLE_RANGE", -7.0, 100),
                _price_rule("ACCEPTANCE_BREAKOUT", 1.5, 100, win_rate=0.52),
            ],
            infer_schema_length=None,
        )
    )

    no_trade = interpretation.filter(pl.col("rule") == "NO_TRADE_MIDDLE_RANGE").row(
        0,
        named=True,
    )
    assert no_trade["use_case"] == "NO_TRADE_FILTER"
    assert no_trade["evidence_strength"] == "PROMISING"


def test_acceptance_breakout_interpreted_as_entry_confirmation_candidate() -> None:
    interpretation = build_price_rule_interpretation(
        pl.DataFrame(
            [_price_rule("ACCEPTANCE_BREAKOUT", 1.7, 292, win_rate=0.5205)],
            infer_schema_length=None,
        )
    )

    row = interpretation.row(0, named=True)
    assert row["use_case"] == "ENTRY_CONFIRMATION"
    assert row["evidence_strength"] == "PROMISING"


def test_cme_overlap_with_eleven_rows_remains_pilot_only() -> None:
    cme = pl.DataFrame(
        [
            {"validation_grade": "CME_PILOT_ONLY", "can_test_oi_wall": True, "can_test_iv_range": True}
            for _ in range(11)
        ],
        infer_schema_length=None,
    )

    interpretation = build_cme_overlap_interpretation(cme)

    assert set(interpretation.get_column("interpretation_label").to_list()) == {
        "CME_OVERLAP_PILOT_ONLY"
    }
    assert not any(interpretation.get_column("enough_for_validation").to_list())


def test_guru_timing_unknown_remains_context_only() -> None:
    interpretation = build_guru_logic_interpretation(
        pl.DataFrame(
            [
                {
                    "test_name": "historical playbook context",
                    "event_count": 20,
                    "timing_confirmed_event_count": 0,
                    "context_only_event_count": 20,
                }
            ],
            infer_schema_length=None,
        )
    )

    row = interpretation.row(0, named=True)
    assert row["remain_context_only"]
    assert row["requires_timing_metadata"]


def test_run_layer_writes_outputs_and_safe_reports(tmp_path: Path) -> None:
    output = tmp_path / "outputs"
    output.mkdir()
    pl.DataFrame(
        [
            _dukascopy_row("j1", "30m", newly=True),
            _dukascopy_row("j1", "1h", newly=False),
        ],
        infer_schema_length=None,
    ).write_csv(output / "forward_outcomes_with_dukascopy.csv")
    pl.DataFrame([_price_rule("ACCEPTANCE_BREAKOUT", 1.7, 292, win_rate=0.52)]).write_csv(
        output / "dukascopy_price_only_rule_backtest.csv"
    )
    pl.DataFrame(
        [
            {
                "test_name": "historical playbook context",
                "event_count": 10,
                "timing_confirmed_event_count": 0,
                "context_only_event_count": 10,
            }
        ]
    ).write_csv(output / "dukascopy_guru_price_only_test.csv")
    pl.DataFrame(
        [{"validation_grade": "CME_PILOT_ONLY", "can_test_oi_wall": True, "can_test_iv_range": True}]
    ).write_csv(output / "dukascopy_cme_overlap_validation.csv")

    result = run_dukascopy_forward_evidence_refresh(
        output_dir=output,
        current_time=datetime(2026, 5, 26, tzinfo=UTC),
    )

    assert result.promotion_summary.row(0, named=True)["newly_promoted_count"] == 1
    assert (output / "dukascopy_forward_outcome_audit.csv").exists()
    assert (output / "forward_evidence_outcomes_dukascopy_promoted.csv").exists()
    report = (output / "dukascopy_forward_promotion_report.md").read_text(encoding="utf-8")
    assert report_text_is_safe(report)
    assert str(tmp_path) not in report


def _dukascopy_row(
    journal_id: str,
    window: str,
    *,
    newly: bool,
    still_pending: bool = False,
    source: str = "DUKASCOPY",
) -> dict[str, object]:
    return {
        "journal_id": journal_id,
        "window": window,
        "window_start": "2026-05-20T00:00:00Z",
        "window_end": "2026-05-20T01:00:00Z",
        "prior_yahoo_resolution": "PENDING",
        "dukascopy_resolution": "RESOLVED_BY_DUKASCOPY",
        "newly_resolved": newly,
        "still_pending": still_pending,
        "open": 100.0,
        "high": 106.0,
        "low": 99.0,
        "close": 104.0,
        "mfe_mid": 6.0,
        "mae_mid": -1.0,
        "bid_ask_mid_difference_points": 0.7,
        "source": source,
    }


def _promoted_row(journal_id: str, window: str, *, close_return: float) -> dict[str, object]:
    return {
        "journal_id": journal_id,
        "rule_id": "FORWARD_OUTCOME_PREVIEW",
        "rule_name": "Forward outcome preview",
        "session_date": "2026-05-20",
        "signal_context": "DUKASCOPY_FORWARD_OUTCOME",
        "outcome_window": window,
        "window_start": "2026-05-20T00:00:00Z",
        "window_end": "2026-05-20T01:00:00Z",
        "close_return": close_return,
        "mfe": 5.0,
        "mae": -1.0,
        "outcome_result": "supported" if close_return > 0 else "failed",
    }


def _price_rule(
    rule: str,
    expectancy: float,
    trade_count: int,
    *,
    win_rate: float = 0.0,
) -> dict[str, object]:
    return {
        "timeframe": "15m",
        "rule": rule,
        "trade_count": trade_count,
        "win_rate": win_rate,
        "avg_win": 1.0,
        "avg_loss": -1.0,
        "expectancy": expectancy,
        "profit_factor": 1.0,
        "max_drawdown": -10.0,
        "spread_cost_estimate": 1.0,
        "long_pnl": 1.0,
        "short_pnl": -1.0,
        "sample_size_warning": False,
        "source": "DUKASCOPY_PRICE_ONLY",
        "notes": "",
    }
