from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl

from research_xau_vol_oi.xau_trade_quality_score import (
    build_score_ablation,
    build_score_bucket_backtest,
    build_score_components,
    build_trade_quality_scores,
    report_text_is_safe,
    run_xau_trade_quality_score_lab,
)


def test_score_never_outputs_buy_or_sell(tmp_path: Path) -> None:
    output = _write_lab_inputs(tmp_path, _price_frame("acceptance"))

    result = run_xau_trade_quality_score_lab(output_dir=output)
    text = (output / "xau_trade_quality_score.md").read_text(encoding="utf-8")
    score_text = result.scores.write_csv()

    assert "BUY" not in text.upper()
    assert "SELL" not in text.upper()
    assert " buy " not in f" {score_text.lower()} "
    assert " sell " not in f" {score_text.lower()} "
    assert report_text_is_safe(text)


def test_no_trade_middle_reduces_score() -> None:
    components = _components()
    neutral = build_trade_quality_scores(
        price_frames={"15m": _price_frame("upper_range")},
        components=components,
    ).public_scores.tail(1).row(0, named=True)
    middle = build_trade_quality_scores(
        price_frames={"15m": _price_frame("middle_range")},
        components=components,
    ).public_scores.tail(1).row(0, named=True)

    assert middle["trade_quality_score"] < neutral["trade_quality_score"]
    assert middle["score_bucket"] == "BLOCK"
    assert middle["final_label"] == "BLOCKED_NO_TRADE_RANGE"


def test_acceptance_breakout_increases_score() -> None:
    components = _components()
    neutral = build_trade_quality_scores(
        price_frames={"15m": _price_frame("upper_range")},
        components=components,
    ).public_scores.tail(1).row(0, named=True)
    acceptance = build_trade_quality_scores(
        price_frames={"15m": _price_frame("acceptance")},
        components=components,
    ).public_scores.tail(1).row(0, named=True)

    assert acceptance["trade_quality_score"] > neutral["trade_quality_score"]
    assert acceptance["candidate_direction"] == "LONG"
    assert "acceptance_breakout_component" in acceptance["active_positive_components"]


def test_fee_spread_failure_blocks_score() -> None:
    score = build_trade_quality_scores(
        price_frames={"15m": _price_frame("acceptance", elevated_spread=True)},
        components=_components(),
    ).public_scores.tail(1).row(0, named=True)

    assert score["score_bucket"] == "BLOCK"
    assert score["final_label"] == "BLOCKED_SPREAD_FEE"
    assert "fee_spread_hurdle_component" in score["active_negative_components"]


def test_cme_wall_missing_marks_pilot_only_or_missing_data() -> None:
    components = build_score_components(
        price_rule_interpretation=_price_interpretation(),
        cme_overlap_interpretation=pl.DataFrame(),
        guru_logic_interpretation=_guru_interpretation(),
        price_frames={"15m": _price_frame("acceptance")},
    )
    row = components.filter(pl.col("component_name") == "cme_wall_context_component").row(
        0,
        named=True,
    )

    assert row["confidence"] in {"PILOT_ONLY", "MISSING_DATA"}
    assert not row["data_available"]


def test_guru_context_cannot_create_trade_alone() -> None:
    contexts = {
        "same_day_filter": {
            "2026-05-26": {
                "resolved_market_session_date": "2026-05-26",
                "same_day_filter_matches": 3,
                "no_trade_filter_active": False,
            }
        }
    }
    score = build_trade_quality_scores(
        price_frames={"15m": _price_frame("upper_range")},
        contexts=contexts,
        components=_components(),
    ).public_scores.tail(1).row(0, named=True)

    assert score["base_candidate_source"] == "GURU_CONTEXT"
    assert score["candidate_direction"] == "NONE"
    assert score["score_bucket"] != "ALLOW_RESEARCH"


def test_high_low_score_bucket_backtest_works() -> None:
    backtest = build_score_bucket_backtest(
        [
            _evaluation_row("HIGH_QUALITY_RESEARCH", 3.0),
            _evaluation_row("HIGH_QUALITY_RESEARCH", 2.0),
            _evaluation_row("BLOCK", -2.0),
            _evaluation_row("BLOCK", -1.0),
        ],
        min_trade_count=1,
    )

    high = backtest.filter(pl.col("score_bucket") == "HIGH_QUALITY_RESEARCH").row(0, named=True)
    low = backtest.filter(pl.col("score_bucket") == "BLOCK").row(0, named=True)
    assert high["average_return"] > low["average_return"]
    assert low["filter_helped_rate"] == 1.0


def test_ablation_output_schema_exists() -> None:
    components = _components()
    scored = build_trade_quality_scores(
        price_frames={"15m": _price_frame("acceptance")},
        components=components,
    )
    baseline = build_score_bucket_backtest(scored.evaluation_rows, min_trade_count=1)
    ablation = build_score_ablation(
        price_frames={"15m": _price_frame("acceptance")},
        contexts={},
        components=components,
        baseline_backtest=baseline,
    )

    assert ablation.height == 7
    assert {
        "ablation",
        "event_count",
        "score_monotonicity_change",
        "expectancy_change",
        "false_block_change",
        "interpretation",
    }.issubset(ablation.columns)


def test_report_does_not_claim_profitability(tmp_path: Path) -> None:
    output = _write_lab_inputs(tmp_path, _price_frame("acceptance"))

    run_xau_trade_quality_score_lab(output_dir=output)
    text = (output / "xau_trade_quality_score_backtest.md").read_text(encoding="utf-8")

    assert "profitability" not in text.lower()
    assert "profitable" not in text.lower()
    assert "guaranteed edge" not in text.lower()
    assert report_text_is_safe(text)


def test_reports_use_redacted_paths_only(tmp_path: Path) -> None:
    output = _write_lab_inputs(tmp_path, _price_frame("acceptance"))

    run_xau_trade_quality_score_lab(output_dir=output)
    text = (output / "xau_trade_quality_forward_usage.md").read_text(encoding="utf-8")

    assert str(tmp_path) not in text
    assert "C:" not in text
    assert report_text_is_safe(text)


def _components() -> pl.DataFrame:
    return build_score_components(
        price_rule_interpretation=_price_interpretation(),
        cme_overlap_interpretation=_cme_interpretation(),
        guru_logic_interpretation=_guru_interpretation(),
        price_frames={"15m": _price_frame("acceptance")},
    )


def _write_lab_inputs(tmp_path: Path, price_frame: pl.DataFrame) -> Path:
    output = tmp_path / "outputs"
    output.mkdir(parents=True, exist_ok=True)
    _price_interpretation().write_csv(output / "dukascopy_price_rule_interpretation.csv")
    _price_backtest().write_csv(output / "dukascopy_price_only_rule_backtest.csv")
    _guru_interpretation().write_csv(output / "dukascopy_guru_logic_interpretation.csv")
    _cme_interpretation().write_csv(output / "dukascopy_cme_overlap_interpretation.csv")
    pl.DataFrame([{"trade_date": "2026-05-26", "iv_available": True}]).write_csv(
        output / "current_week_cme_guru_replay.csv"
    )
    pl.DataFrame(
        [
            {
                "resolved_market_session_date": "2026-05-26",
                "same_day_filter_matches": 1,
                "no_trade_filter_active": False,
            }
        ]
    ).write_csv(output / "same_day_filter_evidence_after_metadata.csv")
    pl.DataFrame(
        [
            {
                "resolved_market_session_date": "2026-05-26",
                "cme_oi_walls_available": True,
                "spot_equivalent_walls_available": True,
                "price_touched_wall": True,
                "price_accepted_wall": True,
            }
        ]
    ).write_csv(output / "same_day_market_map_evidence_after_metadata.csv")
    for timeframe in ("15m", "1h", "4h", "1d"):
        price_frame.write_parquet(output / f"dukascopy_xau_{timeframe}.parquet")
    return output


def _price_frame(pattern: str, *, elevated_spread: bool = False) -> pl.DataFrame:
    start = datetime(2026, 5, 26, 0, 0, tzinfo=UTC)
    rows = []
    for index in range(40):
        close = 108.0 if pattern == "upper_range" else 105.0
        open_value = close
        high = 110.0
        low = 100.0
        spread = 0.5
        if index == 39 and pattern == "acceptance":
            open_value = 110.5
            close = 112.0
            high = 113.0
            low = 109.0
        if index == 39 and pattern == "upper_range":
            high = 109.0
            low = 101.0
        if index == 39 and elevated_spread:
            spread = 10.0
        rows.append(
            {
                "timestamp": start + timedelta(minutes=15 * index),
                "trade_date": "2026-05-26",
                "open": open_value,
                "high": high,
                "low": low,
                "close": close,
                "spread_points": spread,
                "spread_close": spread,
                "quality": "GOOD",
                "timeframe": "15m",
            }
        )
    return pl.DataFrame(rows, infer_schema_length=None)


def _price_interpretation() -> pl.DataFrame:
    return pl.DataFrame(
        [
            _rule("ACCEPTANCE_BREAKOUT", "PROMISING"),
            _rule("NO_TRADE_MIDDLE_RANGE", "PROMISING"),
            _rule("OPEN_DISTANCE_FILTER", "PROMISING"),
            _rule("REJECTION_AFTER_LEVEL_TOUCH", "WEAK"),
        ],
        infer_schema_length=None,
    )


def _price_backtest() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "timeframe": "15m",
                "rule": "ACCEPTANCE_BREAKOUT",
                "trade_count": 40,
                "win_rate": 0.55,
                "expectancy": 1.0,
            }
        ]
    )


def _rule(rule: str, strength: str) -> dict[str, object]:
    return {
        "rule": rule,
        "trade_count": 40,
        "weighted_expectancy": 1.0 if rule == "ACCEPTANCE_BREAKOUT" else -1.0,
        "weighted_win_rate": 0.55,
        "use_case": "ENTRY_CONFIRMATION",
        "evidence_strength": strength,
        "recommended_next_action": "research watch",
        "notes": "research-only",
    }


def _guru_interpretation() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "guru_logic": "context",
                "event_count": 10,
                "price_only_testable": True,
                "requires_cme": False,
                "requires_timing_metadata": True,
                "remain_context_only": True,
                "interpretation": "context only",
                "recommended_next_action": "collect metadata",
            }
        ],
        infer_schema_length=None,
    )


def _cme_interpretation() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "question": "Can CME wall be tested now?",
                "answer": "Pilot only.",
                "valid_overlap_rows": 11,
                "enough_for_validation": False,
                "interpretation_label": "CME_OVERLAP_PILOT_ONLY",
                "fields_still_needed": "more CME OI IV history",
            }
        ],
        infer_schema_length=None,
    )


def _evaluation_row(bucket: str, forward_return: float) -> dict[str, object]:
    return {
        "score_bucket": bucket,
        "candidate_direction": "LONG",
        "_forward_return": forward_return,
        "_mfe": max(forward_return, 0.0),
        "_mae": min(forward_return, 0.0),
    }
