from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl

from research_xau_vol_oi.xau_decision_support_dashboard import (
    build_blocking_reasons,
    build_current_price_state,
    build_watchlist_state,
    report_text_is_safe,
    run_xau_decision_support_dashboard,
)


def test_dashboard_never_outputs_buy_or_sell(tmp_path: Path) -> None:
    output = _write_dashboard_inputs(tmp_path)

    result = run_xau_decision_support_dashboard(output_dir=output)
    text = (output / "xau_decision_support_dashboard.md").read_text(encoding="utf-8")

    assert "BUY" not in text.upper()
    assert "SELL" not in text.upper()
    assert " buy " not in f" {text.lower()} "
    assert " sell " not in f" {text.lower()} "
    assert report_text_is_safe(text)
    assert result.final_recommendation == "NOT_READY_FOR_MONEY"


def test_dashboard_blocks_no_trade_middle_range() -> None:
    price_state = build_current_price_state(price_frames={"15m": _price_frame(close_position=0.5)})
    watchlist = build_watchlist_state(
        price_rules=_price_interpretation(),
        guru_logic=_guru_interpretation(),
        cme_overlap=_cme_interpretation(valid_rows=11),
        forward_governance=_forward_governance(),
        current_price_state=price_state,
    )

    row = watchlist.filter(pl.col("rule") == "NO_TRADE_MIDDLE_RANGE").row(0, named=True)
    assert row["state_label"] == "BLOCKED_NO_TRADE_RANGE"
    assert row["active"]


def test_dashboard_blocks_no_trade_middle_range_on_higher_timeframe() -> None:
    price_state = build_current_price_state(
        price_frames={
            "15m": _price_frame(close_position=0.8),
            "4h": _price_frame(close_position=0.5),
        }
    )
    watchlist = build_watchlist_state(
        price_rules=_price_interpretation(),
        guru_logic=_guru_interpretation(),
        cme_overlap=_cme_interpretation(valid_rows=11),
        forward_governance=_forward_governance(),
        current_price_state=price_state,
    )

    row = watchlist.filter(pl.col("rule") == "NO_TRADE_MIDDLE_RANGE").row(0, named=True)
    assert row["state_label"] == "BLOCKED_NO_TRADE_RANGE"
    assert "4h=MIDDLE_RANGE" in row["what_it_sees"]


def test_dashboard_marks_cme_as_pilot_only() -> None:
    output = _write_dashboard_inputs(Path.cwd() / "tmp_decision_dashboard_test_cme")
    try:
        result = run_xau_decision_support_dashboard(output_dir=output)
        cme = result.watchlist_state.filter(pl.col("rule") == "CME_OI_WALL_CONTEXT").row(
            0,
            named=True,
        )
        assert cme["state_label"] == "WATCH_CME_WALL"
        assert "CME_OVERLAP_PILOT_ONLY" in cme["data_support"]
        assert result.final_recommendation == "NOT_READY_FOR_MONEY"
    finally:
        _cleanup_tmp(output)


def test_guru_context_is_not_direct_signal() -> None:
    price_state = build_current_price_state(price_frames={"15m": _price_frame(close_position=0.8)})
    watchlist = build_watchlist_state(
        price_rules=_price_interpretation(),
        guru_logic=_guru_interpretation(),
        cme_overlap=_cme_interpretation(valid_rows=11),
        forward_governance=_forward_governance(),
        current_price_state=price_state,
    )

    row = watchlist.filter(pl.col("rule") == "GURU_FILTER_CONTEXT").row(0, named=True)
    assert row["state_label"] == "WATCH_GURU_CONTEXT"
    assert "context" in row["why_it_matters"].lower()
    assert "execution recommendation" in row["plain_english_explanation"]


def test_missing_cme_produces_context_only() -> None:
    price_state = build_current_price_state(price_frames={"15m": _price_frame(close_position=0.8)})
    watchlist = build_watchlist_state(
        price_rules=_price_interpretation(),
        guru_logic=_guru_interpretation(),
        cme_overlap=pl.DataFrame(),
        forward_governance=_forward_governance(),
        current_price_state=price_state,
    )

    row = watchlist.filter(pl.col("rule") == "CME_OI_WALL_CONTEXT").row(0, named=True)
    assert row["state_label"] == "CONTEXT_ONLY"
    assert not row["active"]


def test_spread_fee_hurdle_can_block_setup() -> None:
    price_state = build_current_price_state(
        price_frames={"15m": _price_frame(close_position=0.8, elevated_spread=True)}
    )
    watchlist = build_watchlist_state(
        price_rules=_price_interpretation(),
        guru_logic=_guru_interpretation(),
        cme_overlap=_cme_interpretation(valid_rows=11),
        forward_governance=_forward_governance(),
        current_price_state=price_state,
    )
    blockers = build_blocking_reasons(watchlist)

    row = blockers.filter(pl.col("reason_label") == "BLOCKED_SPREAD_FEE").row(0, named=True)
    assert row["active"]


def test_reports_do_not_claim_profitability_or_expose_paths(tmp_path: Path) -> None:
    output = _write_dashboard_inputs(tmp_path)

    run_xau_decision_support_dashboard(output_dir=output)
    text = (output / "xau_decision_support_dashboard.md").read_text(encoding="utf-8")

    assert "profitability" not in text.lower()
    assert "profitable" not in text.lower()
    assert str(tmp_path) not in text
    assert "C:" not in text
    assert report_text_is_safe(text)


def _write_dashboard_inputs(tmp_path: Path) -> Path:
    output = tmp_path / "outputs"
    output.mkdir(parents=True, exist_ok=True)
    _price_interpretation().write_csv(output / "dukascopy_price_rule_interpretation.csv")
    _guru_interpretation().write_csv(output / "dukascopy_guru_logic_interpretation.csv")
    _cme_interpretation(valid_rows=11).write_csv(output / "dukascopy_cme_overlap_interpretation.csv")
    _forward_governance().write_csv(output / "dukascopy_forward_rule_governance.csv")
    pl.DataFrame(
        [
            {"metric": "newly_promoted_count", "value": "89", "notes": "research evidence"},
            {"metric": "independent_event_count", "value": "22", "notes": "window rows grouped"},
        ]
    ).write_csv(output / "dukascopy_forward_event_scorecard.csv")
    for timeframe in ("15m", "1h", "4h", "1d"):
        _price_frame(close_position=0.5).write_parquet(output / f"dukascopy_xau_{timeframe}.parquet")
    pl.DataFrame([{"trade_date": "2026-05-26"}]).write_csv(
        output / "current_week_cme_guru_replay.csv"
    )
    pl.DataFrame([{"resolved_market_session_date": "2026-05-26"}]).write_csv(
        output / "same_day_filter_evidence_after_metadata.csv"
    )
    pl.DataFrame([{"resolved_market_session_date": "2026-05-26"}]).write_csv(
        output / "same_day_market_map_evidence_after_metadata.csv"
    )
    return output


def _price_frame(*, close_position: float, elevated_spread: bool = False) -> pl.DataFrame:
    start = datetime(2026, 5, 26, 0, 0, tzinfo=UTC)
    rows = []
    for index in range(40):
        low = 100.0
        high = 110.0
        close = low + (high - low) * close_position
        spread = 0.5
        if elevated_spread and index == 39:
            spread = 10.0
        rows.append(
            {
                "timestamp": start + timedelta(minutes=15 * index),
                "trade_date": "2026-05-26",
                "open": close - 1.0,
                "high": high,
                "low": low,
                "close": close,
                "spread_points": spread,
                "spread_close": spread,
                "quality": "GOOD",
            }
        )
    return pl.DataFrame(rows, infer_schema_length=None)


def _price_interpretation() -> pl.DataFrame:
    return pl.DataFrame(
        [
            _rule("ACCEPTANCE_BREAKOUT", "ENTRY_CONFIRMATION", "PROMISING", 1.7),
            _rule("NO_TRADE_MIDDLE_RANGE", "NO_TRADE_FILTER", "PROMISING", -7.0),
            _rule("OPEN_DISTANCE_FILTER", "NO_TRADE_FILTER", "PROMISING", -3.9),
            _rule("FEE_SPREAD_HURDLE", "NO_TRADE_FILTER", "PROMISING", -1.4),
        ],
        infer_schema_length=None,
    )


def _rule(rule: str, use_case: str, strength: str, expectancy: float) -> dict[str, object]:
    return {
        "rule": rule,
        "trade_count": 100,
        "weighted_expectancy": expectancy,
        "weighted_win_rate": 0.52 if expectancy > 0 else 0.0,
        "use_case": use_case,
        "evidence_strength": strength,
        "recommended_next_action": "research watch",
        "notes": "research-only",
    }


def _guru_interpretation() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "guru_logic": "historical playbook context",
                "event_count": 20,
                "price_only_testable": True,
                "requires_cme": False,
                "requires_timing_metadata": True,
                "remain_context_only": True,
                "interpretation": "context only",
                "recommended_next_action": "collect timing metadata",
            }
        ],
        infer_schema_length=None,
    )


def _cme_interpretation(*, valid_rows: int) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "question": "Can CME OI wall be tested now?",
                "answer": "Pilot only.",
                "valid_overlap_rows": valid_rows,
                "enough_for_validation": False,
                "interpretation_label": "CME_OVERLAP_PILOT_ONLY",
                "fields_still_needed": "CME OI and IV history",
            }
        ],
        infer_schema_length=None,
    )


def _forward_governance() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "rule_id": "FORWARD_OUTCOME_PREVIEW",
                "rule_name": "Forward outcome preview",
                "independent_event_count": 22,
                "evidence_label": "WEAK_OR_FAILED",
                "recommendation": "collect more forward data",
                "reason": "early evidence",
                "next_required_events": 8,
                "minimum_events_for_review": 30,
                "can_change_rule_now": False,
            }
        ],
        infer_schema_length=None,
    )


def _cleanup_tmp(output: Path) -> None:
    if output.exists() and "tmp_decision_dashboard_test_cme" in str(output):
        for path in sorted(output.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
        for path in sorted(output.rglob("*"), reverse=True):
            if path.is_dir():
                path.rmdir()
        output.rmdir()
