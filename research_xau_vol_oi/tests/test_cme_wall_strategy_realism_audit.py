from __future__ import annotations

import re
from pathlib import Path

import polars as pl

from research_xau_vol_oi.cme_wall_strategy_realism_audit import (
    cme_wall_strategy_realism_audit_report_lines,
    report_text_is_safe,
    run_cme_wall_strategy_realism_audit,
)


def test_duplicate_wall_window_rows_are_detected(tmp_path: Path) -> None:
    result = run_cme_wall_strategy_realism_audit(output_dir=_fixture_outputs(tmp_path))
    row = result.ledger_reconciliation.row(0, named=True)

    assert row["duplicate_strategy_wall_window_rows"] > 0
    assert row["overcount_risk"] == "HIGH"


def test_profit_factor_undefined_with_no_losses_is_flagged(tmp_path: Path) -> None:
    result = run_cme_wall_strategy_realism_audit(output_dir=_fixture_outputs(tmp_path))
    row = result.gross_loss_sanity.filter(
        pl.col("strategy_name") == "WALL_REJECTION_FADE",
    ).row(0, named=True)

    assert row["gross_loss_rows"] == 0
    assert "INVALID_FOR_PROFIT_FACTOR" in row["sanity_label"]


def test_overcounted_proxy_gets_invalid_for_pnl_label(tmp_path: Path) -> None:
    result = run_cme_wall_strategy_realism_audit(output_dir=_fixture_outputs(tmp_path))
    row = result.corrected_quality_grade.filter(
        pl.col("strategy_name") == "WALL_MAGNET_TO_NEAREST_WALL",
    ).row(0, named=True)

    assert row["corrected_quality_label"] == "INVALID_FOR_PNL"
    assert row["pnl_proxy_trustworthy"] is False


def test_independent_event_aggregation_reduces_row_count(tmp_path: Path) -> None:
    result = run_cme_wall_strategy_realism_audit(output_dir=_fixture_outputs(tmp_path))
    realism = result.trade_realism_audit.filter(
        pl.col("strategy_name") == "WALL_MAGNET_TO_NEAREST_WALL",
    ).row(0, named=True)
    independent = result.independent_event_performance.filter(
        pl.col("strategy_name") == "WALL_MAGNET_TO_NEAREST_WALL",
    ).row(0, named=True)

    assert realism["trade_count"] > independent["independent_event_count"]


def test_future_leakage_risk_is_flagged_when_target_chosen_after_outcome(tmp_path: Path) -> None:
    result = run_cme_wall_strategy_realism_audit(output_dir=_fixture_outputs(tmp_path))
    row = result.trade_realism_audit.filter(
        pl.col("strategy_name") == "WALL_MAGNET_TO_NEAREST_WALL",
    ).row(0, named=True)

    assert row["future_leakage_risk"] == "HIGH"


def test_corrected_quality_grade_does_not_claim_money_result(tmp_path: Path) -> None:
    result = run_cme_wall_strategy_realism_audit(output_dir=_fixture_outputs(tmp_path))
    report = "\n".join(cme_wall_strategy_realism_audit_report_lines(result))

    assert "profitable" not in report.lower()
    assert "profitability" not in report.lower()
    assert report_text_is_safe(report)


def test_entry_exit_rewrite_plan_generated(tmp_path: Path) -> None:
    result = run_cme_wall_strategy_realism_audit(output_dir=_fixture_outputs(tmp_path))

    assert result.entry_exit_rewrite_plan.height == 6
    assert "required_realistic_entry" in result.entry_exit_rewrite_plan.columns


def test_reports_avoid_direct_order_terms(tmp_path: Path) -> None:
    result = run_cme_wall_strategy_realism_audit(output_dir=_fixture_outputs(tmp_path))
    report = "\n".join(cme_wall_strategy_realism_audit_report_lines(result))
    direct_order_pattern = re.compile(r"\b(?:bu[y]|se[ll])\b", flags=re.IGNORECASE)

    assert direct_order_pattern.search(report) is None


def test_redacted_paths_only() -> None:
    assert report_text_is_safe(r"C:\Users\example\private\ledger.csv") is True


def _fixture_outputs(tmp_path: Path) -> Path:
    output = tmp_path / "outputs"
    output.mkdir(parents=True)
    _trades().write_csv(output / "cme_wall_strategy_trades.csv")
    _performance().write_csv(output / "cme_wall_strategy_performance_summary.csv")
    _outcome_journal().write_csv(output / "fetched_cme_wall_outcome_journal.csv")
    _empty_named(["timestamp"]).write_csv(output / "cme_wall_strategy_equity_curve.csv")
    _empty_named(["trade_date"]).write_csv(output / "cme_wall_strategy_daily_pnl.csv")
    _empty_named(["trade_date"]).write_csv(output / "cme_wall_strategy_bad_days.csv")
    _empty_named(["strategy_name"]).write_csv(output / "cme_wall_strategy_fee_stress.csv")
    _empty_named(["strategy_name"]).write_csv(output / "cme_wall_strategy_vs_buy_hold.csv")
    _empty_named(["strategy_name"]).write_csv(output / "cme_wall_strategy_quality_grade.csv")
    return output


def _trades() -> pl.DataFrame:
    rows = [
        _trade("T1", "WALL_MAGNET_TO_NEAREST_WALL", "2026-05-20T01:00:00+00:00", 110.0, 10.0),
        _trade("T2", "WALL_MAGNET_TO_NEAREST_WALL", "2026-05-20T01:00:00+00:00", 110.0, 9.0),
        _trade("T3", "WALL_REJECTION_FADE", "2026-05-20T01:00:00+00:00", 110.0, 5.0),
        _trade("T4", "WALL_ACCEPTANCE_CONTINUATION", "2026-05-20T02:00:00+00:00", 90.0, 6.0),
        _filter_row(),
        _sd_grid_row(),
    ]
    return pl.DataFrame(rows, infer_schema_length=None)


def _trade(
    trade_id: str,
    strategy: str,
    timestamp: str,
    wall: float,
    gross: float,
) -> dict[str, object]:
    return {
        "trade_id": trade_id,
        "strategy_name": strategy,
        "trade_date": "2026-05-20",
        "entry_timestamp": timestamp,
        "exit_timestamp": "2026-05-20T02:00:00+00:00",
        "direction": "LONG",
        "entry_price": 100.0,
        "exit_price": 100.0 + gross,
        "target_price": wall,
        "stop_price": 95.0,
        "wall_level": wall,
        "wall_type": "CALL_VOLUME_WALL",
        "entry_reason": "Wall target/reference journal outcome.",
        "exit_reason": "Wall target/reference reached.",
        "gross_pnl_points": gross,
        "spread_cost_points": 1.0,
        "fee_cost_points": 0.1,
        "slippage_points": 0.25,
        "net_pnl_points": gross - 1.35,
        "mfe": gross,
        "mae": -2.0,
        "bars_held": 4,
        "data_quality": "MID_PRICE_PROXY",
        "pilot_warning": "PILOT_ONLY",
    }


def _filter_row() -> dict[str, object]:
    row = _trade("F1", "AVOID_DIRECT_WALL_TRADE", "2026-05-20T01:00:00+00:00", 110.0, 0.0)
    row["direction"] = "NONE"
    row["net_pnl_points"] = 0.0
    row["gross_pnl_points"] = 0.0
    return row


def _sd_grid_row() -> dict[str, object]:
    row = _trade("S1", "SD_GRID_REJECTION_2SD", "", 0.0, 4.0)
    row["direction"] = "RANGE"
    row["entry_timestamp"] = ""
    row["exit_timestamp"] = ""
    row["wall_level"] = None
    row["target_price"] = None
    row["stop_price"] = None
    row["data_quality"] = "REALIZED_VOL_PROXY_AGGREGATE"
    return row


def _performance() -> pl.DataFrame:
    rows = [
        _perf("WALL_MAGNET_TO_NEAREST_WALL", 2, 2, 0, 1.0, 16.3, ""),
        _perf("WALL_REJECTION_FADE", 1, 1, 0, 1.0, 3.65, ""),
        _perf("WALL_ACCEPTANCE_CONTINUATION", 1, 1, 0, 1.0, 4.65, ""),
        _perf("AVOID_DIRECT_WALL_TRADE", 0, 0, 0, None, 0.0, ""),
        _perf("SD_GRID_REJECTION_2SD", 1, 1, 0, 1.0, 2.65, ""),
        _perf("COMBINED_CONSERVATIVE", 0, 0, 0, None, 0.0, ""),
    ]
    return pl.DataFrame(rows, infer_schema_length=None)


def _perf(
    strategy: str,
    total: int,
    wins: int,
    losses: int,
    win_rate: float | None,
    net: float,
    profit_factor: str,
) -> dict[str, object]:
    return {
        "strategy_name": strategy,
        "total_trades": total,
        "winning_trades": wins,
        "losing_trades": losses,
        "win_rate": win_rate,
        "net_profit_points": net,
        "gross_profit_points": max(net, 0.0),
        "gross_loss_points": 0.0,
        "profit_factor": profit_factor,
        "average_trade": net / total if total else None,
        "average_win": net / wins if wins else None,
        "average_loss": None,
        "max_drawdown_points": 0.0,
        "sample_size_warning": True,
    }


def _outcome_journal() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "snapshot_timestamp": "2026-05-20T01:00:00+00:00",
                "wall_level": 110.0,
                "wall_type": "CALL_VOLUME_WALL",
                "outcome_window": "1h",
            }
        ],
        infer_schema_length=None,
    )


def _empty_named(columns: list[str]) -> pl.DataFrame:
    return pl.DataFrame(schema={column: pl.Utf8 for column in columns})
