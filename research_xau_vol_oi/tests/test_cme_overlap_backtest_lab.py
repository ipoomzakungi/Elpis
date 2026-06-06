from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl

from research_xau_vol_oi.cme_overlap_backtest_lab import (
    build_candidate_source_report,
    build_cme_iv_range_filter_effect,
    build_cme_overlap_date_audit,
    build_cme_overlap_pilot_decision,
    build_cme_overlap_trade_candidates,
    build_filter_overlay_backtest,
    report_text_is_safe,
    run_cme_overlap_backtest_lab,
)


def test_date_audit_classifies_cme_overlap_days() -> None:
    audit = build_cme_overlap_date_audit(inputs=_inputs())
    row = audit.row(0, named=True)

    assert row["trade_date"] == "2026-05-15"
    assert row["has_dukascopy_price"]
    assert row["has_cme_oi"]
    assert row["has_cme_iv"]
    assert row["has_basis"]
    assert row["pilot_grade"] == "FULL_CME_PILOT"
    assert row["can_run_combined_test"]


def test_candidate_source_priority_chooses_tradingview_csv_if_available() -> None:
    inputs = _inputs(tradingview=True)
    audit = build_cme_overlap_date_audit(inputs=inputs)
    source = build_candidate_source_report(inputs=inputs, date_audit=audit)
    selected = source.filter(pl.col("selected_for_backtest")).row(0, named=True)

    assert selected["candidate_source"] == "TRADINGVIEW_TRADE_CSV"


def test_python_pine_like_candidate_fallback_works() -> None:
    inputs = _inputs(tradingview=False)
    audit = build_cme_overlap_date_audit(inputs=inputs)
    source = build_candidate_source_report(inputs=inputs, date_audit=audit)
    candidates = build_cme_overlap_trade_candidates(
        inputs=inputs,
        date_audit=audit,
        candidate_source_report=source,
    )

    assert source.filter(pl.col("selected_for_backtest")).row(0, named=True)["candidate_source"] == "PYTHON_PINE_LIKE"
    assert candidates.height == 2
    assert set(candidates.get_column("candidate_source").to_list()) == {"PYTHON_PINE_LIKE"}


def test_cme_wall_filter_blocks_trade_into_wall() -> None:
    candidates = _candidate_frame(distance_to_wall=2.0, acceptance=False)

    backtest = build_filter_overlay_backtest(candidates)
    row = backtest.filter(pl.col("scenario") == "CME_WALL_FILTER_ONLY").row(0, named=True)

    assert row["allowed_count"] == 0
    assert row["blocked_count"] == 1
    assert row["avoided_losing_candidates"] == 1


def test_iv_filter_labels_missing_iv_as_context_only() -> None:
    effect = build_cme_iv_range_filter_effect(
        _candidate_frame(cme_iv_context="IV_MISSING_CONTEXT_ONLY"),
    )
    row = effect.filter(pl.col("case_type") == "IV_MISSING").row(0, named=True)

    assert row["candidate_count"] == 1
    assert row["interpretation"] == "INSUFFICIENT_SAMPLE"


def test_guru_context_does_not_create_trade_alone() -> None:
    inputs = _inputs(include_python=False, guru_only=True)
    audit = build_cme_overlap_date_audit(inputs=inputs)
    source = build_candidate_source_report(inputs=inputs, date_audit=audit)
    candidates = build_cme_overlap_trade_candidates(
        inputs=inputs,
        date_audit=audit,
        candidate_source_report=source,
    )

    assert not source.filter(pl.col("selected_for_backtest")).height
    assert candidates.is_empty()


def test_combined_filter_metrics_calculated() -> None:
    candidates = pl.concat(
        [
            _candidate_frame(distance_to_wall=20.0, raw_pnl=3.0),
            _candidate_frame(distance_to_wall=2.0, raw_pnl=-4.0),
        ],
        how="vertical",
    )

    backtest = build_filter_overlay_backtest(candidates)
    row = backtest.filter(pl.col("scenario") == "COMBINED_CONSERVATIVE_FILTER").row(0, named=True)

    assert row["candidate_count"] == 2
    assert row["allowed_count"] == 1
    assert row["blocked_count"] == 1
    assert row["net_filter_value_proxy"] == 4.0


def test_tiny_sample_forces_insufficient_sample() -> None:
    inputs = _inputs()
    audit = build_cme_overlap_date_audit(inputs=inputs)
    source = build_candidate_source_report(inputs=inputs, date_audit=audit)
    candidates = build_cme_overlap_trade_candidates(
        inputs=inputs,
        date_audit=audit,
        candidate_source_report=source,
    )
    backtest = build_filter_overlay_backtest(candidates)
    decision = build_cme_overlap_pilot_decision(
        date_audit=audit,
        candidate_source_report=source,
        candidates=candidates,
        filter_backtest=backtest,
        wall_effect=pl.DataFrame(),
        iv_effect=pl.DataFrame(),
        guru_effect=pl.DataFrame(),
    )

    assert decision.row(0, named=True)["final_label"] == "INSUFFICIENT_SAMPLE"
    assert "NEED_MORE_CME_DAYS" in decision.row(0, named=True)["supporting_labels"]


def test_visual_replay_artifact_created(tmp_path: Path) -> None:
    output = _write_lab_inputs(tmp_path)

    run_cme_overlap_backtest_lab(output_dir=output)

    assert (output / "charts" / "cme_overlap_replay.html").exists()
    assert (output / "cme_overlap_replay.md").exists()


def test_reports_do_not_claim_profitability(tmp_path: Path) -> None:
    output = _write_lab_inputs(tmp_path)

    run_cme_overlap_backtest_lab(output_dir=output)
    text = (output / "cme_overlap_filter_backtest.md").read_text(encoding="utf-8")

    assert "profitability" not in text.lower()
    assert "profitable" not in text.lower()
    assert report_text_is_safe(text)


def test_reports_never_output_buy_or_sell(tmp_path: Path) -> None:
    output = _write_lab_inputs(tmp_path)

    run_cme_overlap_backtest_lab(output_dir=output)
    text = "\n".join(
        [
            (output / "cme_overlap_filter_backtest.md").read_text(encoding="utf-8"),
            (output / "cme_overlap_pilot_decision.md").read_text(encoding="utf-8"),
            (output / "cme_overlap_replay.md").read_text(encoding="utf-8"),
        ]
    )

    assert "BUY" not in text.upper()
    assert "SELL" not in text.upper()
    assert report_text_is_safe(text)


def test_reports_use_redacted_paths_only(tmp_path: Path) -> None:
    output = _write_lab_inputs(tmp_path, path_in_reason=True)

    run_cme_overlap_backtest_lab(output_dir=output)
    text = (output / "cme_overlap_trade_candidates.md").read_text(encoding="utf-8")

    assert str(tmp_path) not in text
    assert "C:" not in text
    assert "<REDACTED_PATH>" in text
    assert report_text_is_safe(text)


def _inputs(
    *,
    tradingview: bool = False,
    include_python: bool = True,
    guru_only: bool = False,
) -> dict[str, object]:
    return {
        "price_by_timeframe": {"1h": _price_frame()},
        "cme_oi": _cme_oi(),
        "cme_iv": _cme_iv(),
        "cme_futures": _cme_futures(),
        "basis": _basis(),
        "guru_replay": _guru_replay(),
        "overlap_validation": pl.DataFrame(),
        "pine_signals": _pine_signals() if include_python and not guru_only else pl.DataFrame(),
        "python_trades": _python_trades() if include_python and not guru_only else pl.DataFrame(),
        "python_overlay_trades": pl.DataFrame(),
        "tradingview_trades": _tradingview_trades() if tradingview else pl.DataFrame(),
        "score_rows": pl.DataFrame(),
        "same_day_filter": _same_day_filter(),
        "same_day_market_map": _same_day_market_map(),
        "market_map": _market_map(),
    }


def _write_lab_inputs(tmp_path: Path, *, path_in_reason: bool = False) -> Path:
    output = tmp_path / "outputs"
    output.mkdir(parents=True, exist_ok=True)
    _price_frame().write_parquet(output / "dukascopy_xau_1h.parquet")
    _cme_oi().write_parquet(output / "cme_canonical_option_oi_by_strike.parquet")
    _cme_iv().write_parquet(output / "cme_canonical_option_iv_by_strike.parquet")
    _cme_futures().write_parquet(output / "cme_canonical_futures_price.parquet")
    _basis().write_parquet(output / "xau_basis_backfilled.parquet")
    _guru_replay().write_csv(output / "current_week_cme_guru_replay.csv")
    _same_day_filter().write_csv(output / "same_day_filter_evidence_after_metadata.csv")
    _same_day_market_map().write_csv(output / "same_day_market_map_evidence_after_metadata.csv")
    _market_map().write_csv(output / "cme_overlap_market_map.csv")
    _python_trades(path_in_reason=path_in_reason).write_csv(output / "python_pine_like_backtest_trades.csv")
    return output


def _price_frame() -> pl.DataFrame:
    start = datetime(2026, 5, 15, tzinfo=UTC)
    rows = []
    for index in range(4):
        timestamp = start + timedelta(hours=index)
        rows.append(
            {
                "timestamp": timestamp,
                "trade_date": "2026-05-15",
                "timeframe": "1h",
                "open": 4500.0 + index,
                "high": 4510.0 + index,
                "low": 4490.0 + index,
                "close": 4502.0 + index,
                "spread_points": 0.2,
            }
        )
    return pl.DataFrame(rows, infer_schema_length=None)


def _cme_oi() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "trade_date": "2026-05-15",
                "strike": 4510.0,
                "open_interest": 1000,
                "oi_change": 25,
                "volume": 100,
            }
        ],
        infer_schema_length=None,
    )


def _cme_iv() -> pl.DataFrame:
    return pl.DataFrame(
        [{"trade_date": "2026-05-15", "strike": 4510.0, "implied_volatility": 0.18}],
        infer_schema_length=None,
    )


def _cme_futures() -> pl.DataFrame:
    return pl.DataFrame(
        [{"trade_date": "2026-05-15", "futures_price": 4508.0}],
        infer_schema_length=None,
    )


def _basis() -> pl.DataFrame:
    return pl.DataFrame(
        [{"trade_date": "2026-05-15", "basis": 5.0}],
        infer_schema_length=None,
    )


def _guru_replay() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "trade_date": "2026-05-15",
                "iv_available": True,
                "oi_available": True,
                "oi_change_available": True,
                "option_volume_available": True,
                "futures_available": True,
                "active_guru_logic": "SAME_DAY_TIMING_CONFIRMED_CONTEXT",
            }
        ],
        infer_schema_length=None,
    )


def _same_day_filter() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "resolved_market_session_date": "2026-05-15",
                "timing_confirmed_filter_matches": True,
                "no_trade_filter_active": False,
                "active_filter_logic_names": "CONTEXT_ONLY",
            }
        ],
        infer_schema_length=None,
    )


def _same_day_market_map() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "resolved_market_session_date": "2026-05-15",
                "top_wall_above": 4510.0,
                "top_wall_below": 4480.0,
                "price_touched_wall": True,
                "price_rejected_wall": False,
                "price_accepted_wall": True,
            }
        ],
        infer_schema_length=None,
    )


def _market_map() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "trade_date": "2026-05-15",
                "timeframe": "1h",
                "spot_equivalent_wall_above": 4510.0,
                "spot_equivalent_wall_below": 4480.0,
                "iv_range_available": True,
            }
        ],
        infer_schema_length=None,
    )


def _pine_signals() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "timestamp": datetime(2026, 5, 15, 1, 0, tzinfo=UTC),
                "interval": "1h",
                "direction_candidate": "LONG",
                "acceptance_breakout": True,
                "raw_signal": "ACCEPTANCE_BREAKOUT",
                "close": 4505.0,
            }
        ],
        infer_schema_length=None,
    )


def _python_trades(*, path_in_reason: bool = False) -> pl.DataFrame:
    reason = r"C:\Users\example\secret.csv" if path_in_reason else "ACCEPTANCE_BREAKOUT"
    return pl.DataFrame(
        [
            {
                "trade_id": "py_1",
                "signal_timestamp": datetime(2026, 5, 15, 1, 0, tzinfo=UTC),
                "entry_timestamp": datetime(2026, 5, 15, 2, 0, tzinfo=UTC),
                "interval": "1h",
                "direction": "LONG",
                "entry_price": 4505.0,
                "exit_price": 4510.0,
                "pnl_after_cost": 5.0,
                "entry_reason": reason,
                "mfe": 7.0,
                "mae": -1.0,
            },
            {
                "trade_id": "py_2",
                "signal_timestamp": datetime(2026, 5, 15, 3, 0, tzinfo=UTC),
                "entry_timestamp": datetime(2026, 5, 15, 4, 0, tzinfo=UTC),
                "interval": "1h",
                "direction": "SHORT",
                "entry_price": 4509.0,
                "exit_price": 4512.0,
                "pnl_after_cost": -3.0,
                "entry_reason": "OPEN_DISTANCE_FILTER",
                "mfe": 1.0,
                "mae": -4.0,
            },
        ],
        infer_schema_length=None,
    )


def _tradingview_trades() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "entry_timestamp": datetime(2026, 5, 15, 1, 30, tzinfo=UTC),
                "timeframe": "1h",
                "direction": "LONG",
                "entry_price": 4504.0,
                "exit_price": 4506.0,
                "raw_pnl": 2.0,
                "entry_reason": "EXPORTED_TRADE_ROW",
            }
        ],
        infer_schema_length=None,
    )


def _candidate_frame(
    *,
    distance_to_wall: float = 20.0,
    raw_pnl: float = -1.0,
    acceptance: bool = False,
    cme_iv_context: str = "IV_CONTEXT_AVAILABLE",
) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "candidate_id": "c1",
                "timestamp": "2026-05-15T01:00:00+00:00",
                "trade_date": "2026-05-15",
                "timeframe": "1h",
                "candidate_source": "PYTHON_PINE_LIKE",
                "direction": "LONG",
                "entry_price": 4505.0,
                "exit_price": 4504.0,
                "raw_pnl": raw_pnl,
                "signal_reason": "RESEARCH_CANDIDATE",
                "acceptance_breakout_active": acceptance,
                "rejection_after_touch_component": False,
                "no_trade_middle_range_active": False,
                "open_distance_filter_active": False,
                "fee_spread_hurdle_pass": True,
                "cme_wall_above": 4510.0,
                "cme_wall_below": 4480.0,
                "distance_to_wall": distance_to_wall,
                "cme_iv_context": cme_iv_context,
                "guru_filter_context": "NO_GURU_CONTEXT",
                "data_quality": "OK",
                "mfe": max(raw_pnl, 0.0),
                "mae": min(raw_pnl, 0.0),
            }
        ],
        infer_schema_length=None,
    )
