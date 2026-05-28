from __future__ import annotations

import re
from pathlib import Path

import polars as pl

from research_xau_vol_oi.cme_wall_realistic_loss_decomposition import (
    cme_wall_realistic_loss_decomposition_report_lines,
    report_text_is_safe,
    run_cme_wall_realistic_loss_decomposition,
)


def test_loss_by_strategy_detects_worst_strategy(tmp_path: Path) -> None:
    result = run_cme_wall_realistic_loss_decomposition(output_dir=_fixture_outputs(tmp_path))
    worst = result.loss_by_strategy.sort("net_pnl").row(0, named=True)

    assert worst["strategy_name"] == "WALL_ACCEPTANCE_CONTINUATION"


def test_cost_drag_identifies_win_to_loss_flips(tmp_path: Path) -> None:
    result = run_cme_wall_realistic_loss_decomposition(output_dir=_fixture_outputs(tmp_path))
    row = result.cost_drag.filter(
        pl.col("strategy_name") == "SD_2_REJECTION_CONFIRMED_FADE",
    ).row(0, named=True)

    assert row["trades_flipped_from_win_to_loss_by_cost"] >= 1
    assert row["cost_explains_loss"] is True


def test_exit_reason_grouping_works(tmp_path: Path) -> None:
    result = run_cme_wall_realistic_loss_decomposition(output_dir=_fixture_outputs(tmp_path))
    reasons = set(result.loss_by_exit_reason.get_column("exit_reason").to_list())
    ambiguous = result.loss_by_exit_reason.filter(
        pl.col("exit_reason") == "AMBIGUOUS_SAME_CANDLE",
    ).row(0, named=True)

    assert {"TARGET_HIT", "STOP_HIT", "SESSION_CLOSE", "INVALIDATION", "AMBIGUOUS_SAME_CANDLE", "NO_ENTRY"} <= reasons
    assert ambiguous["trade_count"] >= 1


def test_wall_type_grouping_works(tmp_path: Path) -> None:
    result = run_cme_wall_realistic_loss_decomposition(output_dir=_fixture_outputs(tmp_path))
    wall_types = set(result.loss_by_wall_type.get_column("wall_type").to_list())

    assert "CALL_VOLUME_WALL" in wall_types
    assert "OI_WALL" in wall_types


def test_direction_grouping_works(tmp_path: Path) -> None:
    result = run_cme_wall_realistic_loss_decomposition(output_dir=_fixture_outputs(tmp_path))
    directions = set(result.loss_by_direction.get_column("direction").to_list())

    assert {"LONG", "SHORT", "NONE"} <= directions


def test_session_clustered_loss_warning_works(tmp_path: Path) -> None:
    result = run_cme_wall_realistic_loss_decomposition(output_dir=_fixture_outputs(tmp_path))

    assert result.loss_by_session.get_column("clustered_loss_warning").any()


def test_fixability_labels_acceptance_continuation_quarantine(tmp_path: Path) -> None:
    result = run_cme_wall_realistic_loss_decomposition(output_dir=_fixture_outputs(tmp_path))
    row = result.fixability_audit.filter(
        pl.col("strategy_name") == "WALL_ACCEPTANCE_CONTINUATION",
    ).row(0, named=True)

    assert row["main_failure_mode"] == "FALSE_BREAKOUTS"
    assert row["recommended_next_action"] == "QUARANTINE"


def test_sd2_rejection_gets_cost_drag_review_when_pf_positive_but_net_negative(tmp_path: Path) -> None:
    result = run_cme_wall_realistic_loss_decomposition(output_dir=_fixture_outputs(tmp_path))
    row = result.fixability_audit.filter(
        pl.col("strategy_name") == "SD_2_REJECTION_CONFIRMED_FADE",
    ).row(0, named=True)

    assert row["main_failure_mode"] == "COST_DRAG"
    assert row["recommended_next_action"] == "KEEP_RESEARCH"


def test_reports_avoid_direct_trade_instructions_and_money_result_claims(tmp_path: Path) -> None:
    result = run_cme_wall_realistic_loss_decomposition(output_dir=_fixture_outputs(tmp_path))
    report = "\n".join(cme_wall_realistic_loss_decomposition_report_lines(result))
    direct_order_pattern = re.compile(r"\b(?:bu[y]|se[ll])\b", flags=re.IGNORECASE)

    assert direct_order_pattern.search(report) is None
    assert "profitable" not in report.lower()
    assert "profitability" not in report.lower()
    assert report_text_is_safe(report)


def test_redacted_paths_only() -> None:
    assert report_text_is_safe(r"C:\Users\example\private\loss.csv") is True


def _fixture_outputs(tmp_path: Path) -> Path:
    output = tmp_path / "outputs"
    output.mkdir(parents=True)
    _trade_events().write_csv(output / "cme_wall_realistic_trade_events.csv")
    _performance().write_csv(output / "cme_wall_realistic_performance_summary.csv")
    _daily_pnl().write_csv(output / "cme_wall_realistic_daily_pnl.csv")
    _price().write_parquet(output / "dukascopy_xau_15m.parquet")
    _empty_named(["timestamp"]).write_csv(output / "cme_wall_realistic_equity_curve.csv")
    _empty_named(["trade_date"]).write_csv(output / "cme_wall_realistic_bad_days.csv")
    _empty_named(["strategy_name"]).write_csv(output / "cme_wall_realistic_quality_grade.csv")
    _empty_named(["proxy_strategy_name"]).write_csv(output / "cme_wall_proxy_vs_realistic_comparison.csv")
    _empty_named(["snapshot_timestamp"]).write_csv(output / "fetched_cme_wall_rankings.csv")
    _empty_named(["trade_date"]).write_csv(output / "fetched_cme_daily_wall_state.csv")
    return output


def _trade_events() -> pl.DataFrame:
    rows = [
        _trade(
            "R1",
            "WALL_REJECTION_CONFIRMED_FADE",
            "LONG",
            "TARGET_HIT",
            10.0,
            9.0,
            "CALL_VOLUME_WALL",
            100.0,
            110.0,
            95.0,
            110.0,
            "2026-05-20T00:15:00+00:00",
        ),
        _trade(
            "R2",
            "WALL_REJECTION_CONFIRMED_FADE",
            "LONG",
            "STOP_HIT",
            -20.0,
            -21.0,
            "CALL_VOLUME_WALL",
            100.0,
            110.0,
            80.0,
            110.0,
            "2026-05-20T00:30:00+00:00",
        ),
        _trade(
            "A1",
            "WALL_ACCEPTANCE_CONTINUATION",
            "SHORT",
            "INVALIDATION",
            -1200.0,
            -1201.0,
            "OI_WALL",
            110.0,
            90.0,
            120.0,
            110.0,
            "2026-05-20T01:00:00+00:00",
        ),
        _trade(
            "S1",
            "SD_2_REJECTION_CONFIRMED_FADE",
            "LONG",
            "TARGET_HIT",
            10.0,
            -1.0,
            "SD_2_REALIZED_VOL_PROXY",
            100.0,
            110.0,
            90.0,
            101.0,
            "2026-05-20T01:15:00+00:00",
            spread=10.0,
            slippage=1.0,
        ),
        _trade(
            "S2",
            "SD_2_REJECTION_CONFIRMED_FADE",
            "LONG",
            "STOP_HIT",
            -9.0,
            -10.0,
            "SD_2_REALIZED_VOL_PROXY",
            100.0,
            110.0,
            90.0,
            102.0,
            "2026-05-20T01:30:00+00:00",
        ),
        _trade(
            "C1",
            "COMBINED_CONSERVATIVE_REALISTIC",
            "SHORT",
            "SESSION_CLOSE",
            -50.0,
            -51.0,
            "PUT_VOLUME_WALL",
            100.0,
            90.0,
            112.0,
            100.0,
            "2026-05-20T02:00:00+00:00",
        ),
        _trade(
            "C2",
            "COMBINED_CONSERVATIVE_REALISTIC",
            "LONG",
            "STOP_HIT",
            -12.0,
            -13.0,
            "TOTAL_VOLUME_WALL",
            100.0,
            110.0,
            90.0,
            100.0,
            "2026-05-20T02:15:00+00:00",
        ),
        _filter(),
    ]
    return pl.DataFrame(rows, infer_schema_length=None)


def _trade(
    event_id: str,
    strategy: str,
    direction: str,
    exit_reason: str,
    gross: float,
    net: float,
    wall_type: str,
    entry: float,
    target: float,
    stop: float,
    wall: float,
    timestamp: str,
    *,
    spread: float = 0.5,
    slippage: float = 0.5,
) -> dict[str, object]:
    return {
        "event_id": event_id,
        "strategy_name": strategy,
        "trade_date": timestamp[:10],
        "setup_timestamp": "2026-05-20T00:00:00+00:00",
        "entry_timestamp": timestamp,
        "exit_timestamp": timestamp,
        "direction": direction,
        "entry_price": entry,
        "target_price": target,
        "stop_price": stop,
        "exit_price": entry + gross if direction == "LONG" else entry - gross,
        "wall_level": wall,
        "wall_type": wall_type,
        "entry_confirmation": "REJECTION_CONFIRMED",
        "exit_reason": exit_reason,
        "gross_pnl_points": gross,
        "spread_cost_points": spread,
        "slippage_points": slippage,
        "net_pnl_points": net,
        "mfe": max(gross, 0.0),
        "mae": min(gross, 0.0),
        "bars_held": 1,
        "data_quality": "MID_PRICE_PROXY_INTRADAY_PATH",
        "sample_warning": True,
    }


def _filter() -> dict[str, object]:
    row = _trade(
        "F1",
        "AVOID_DIRECT_WALL_TRADE_FILTER",
        "NONE",
        "NO_ENTRY",
        0.0,
        0.0,
        "CALL_VOLUME_WALL",
        100.0,
        0.0,
        0.0,
        110.0,
        "2026-05-20T03:00:00+00:00",
    )
    row["entry_timestamp"] = ""
    row["exit_timestamp"] = ""
    row["target_price"] = None
    row["stop_price"] = None
    row["exit_price"] = None
    return row


def _performance() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {"strategy_name": "WALL_REJECTION_CONFIRMED_FADE", "max_drawdown_points": -21.0},
            {"strategy_name": "WALL_ACCEPTANCE_CONTINUATION", "max_drawdown_points": -1201.0},
            {"strategy_name": "SD_2_REJECTION_CONFIRMED_FADE", "max_drawdown_points": -11.0},
            {"strategy_name": "COMBINED_CONSERVATIVE_REALISTIC", "max_drawdown_points": -64.0},
        ],
        infer_schema_length=None,
    )


def _daily_pnl() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "trade_date": "2026-05-20",
                "strategy_name": "WALL_ACCEPTANCE_CONTINUATION",
                "bad_day": True,
            }
        ],
        infer_schema_length=None,
    )


def _price() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {"timestamp": "2026-05-20T00:15:00+00:00", "high": 111.0, "low": 99.0, "close": 110.0},
            {"timestamp": "2026-05-20T00:30:00+00:00", "high": 115.0, "low": 75.0, "close": 80.0},
            {"timestamp": "2026-05-20T01:00:00+00:00", "high": 121.0, "low": 90.0, "close": 120.0},
            {"timestamp": "2026-05-20T01:15:00+00:00", "high": 110.0, "low": 99.0, "close": 101.0},
            {"timestamp": "2026-05-20T01:30:00+00:00", "high": 102.0, "low": 90.0, "close": 90.0},
            {"timestamp": "2026-05-20T02:00:00+00:00", "high": 151.0, "low": 100.0, "close": 150.0},
            {"timestamp": "2026-05-20T02:15:00+00:00", "high": 112.0, "low": 89.0, "close": 90.0},
        ],
        infer_schema_length=None,
    )


def _empty_named(columns: list[str]) -> pl.DataFrame:
    return pl.DataFrame(schema={column: pl.Utf8 for column in columns})
