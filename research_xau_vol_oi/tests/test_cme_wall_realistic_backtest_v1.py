from __future__ import annotations

import re
from pathlib import Path

import polars as pl

from research_xau_vol_oi.cme_wall_realistic_backtest_v1 import (
    cme_wall_realistic_backtest_v1_report_lines,
    report_text_is_safe,
    run_cme_wall_realistic_backtest_v1,
)


def test_no_trade_created_before_confirmation(tmp_path: Path) -> None:
    result = run_cme_wall_realistic_backtest_v1(
        output_dir=_fixture_outputs(tmp_path, mode="no_confirmation"),
    )

    active = result.trade_events.filter(pl.col("direction").is_in(["LONG", "SHORT"]))
    assert active.is_empty()


def test_target_and_stop_are_known_at_entry(tmp_path: Path) -> None:
    result = run_cme_wall_realistic_backtest_v1(output_dir=_fixture_outputs(tmp_path))
    active = result.trade_events.filter(pl.col("direction").is_in(["LONG", "SHORT"]))

    assert active.height > 0
    assert active.get_column("entry_timestamp").null_count() == 0
    assert active.get_column("target_price").null_count() == 0
    assert active.get_column("stop_price").null_count() == 0


def test_acceptance_target_is_beyond_entry_price(tmp_path: Path) -> None:
    result = run_cme_wall_realistic_backtest_v1(
        output_dir=_fixture_outputs(tmp_path, mode="acceptance_target_behind_entry"),
    )
    row = result.trade_events.filter(
        (pl.col("strategy_name") == "WALL_ACCEPTANCE_CONTINUATION")
        & (pl.col("wall_level") == 90.0),
    ).row(0, named=True)

    assert row["direction"] == "SHORT"
    assert row["target_price"] < row["entry_price"]
    assert row["exit_reason"] == "TARGET_HIT"
    assert row["gross_pnl_points"] > 0


def test_target_stop_path_check_uses_after_entry_candles_only(tmp_path: Path) -> None:
    result = run_cme_wall_realistic_backtest_v1(
        output_dir=_fixture_outputs(tmp_path, mode="pre_entry_target_only"),
    )
    row = result.trade_events.filter(
        pl.col("strategy_name") == "WALL_REJECTION_CONFIRMED_FADE",
    ).row(0, named=True)

    assert row["entry_timestamp"] > row["setup_timestamp"]
    assert row["exit_reason"] == "SESSION_CLOSE"


def test_same_event_cannot_create_duplicated_trades(tmp_path: Path) -> None:
    result = run_cme_wall_realistic_backtest_v1(
        output_dir=_fixture_outputs(tmp_path, duplicate_ranking=True),
    )
    rejection_rows = result.trade_events.filter(
        pl.col("strategy_name") == "WALL_REJECTION_CONFIRMED_FADE",
    )

    keys = {
        (
            row["strategy_name"],
            row["setup_timestamp"],
            row["wall_level"],
            row["wall_type"],
        )
        for row in rejection_rows.to_dicts()
    }
    assert len(keys) == rejection_rows.height


def test_ambiguous_same_candle_tp_sl_is_conservative(tmp_path: Path) -> None:
    result = run_cme_wall_realistic_backtest_v1(
        output_dir=_fixture_outputs(tmp_path, mode="ambiguous"),
    )
    row = result.trade_events.filter(
        pl.col("strategy_name") == "WALL_REJECTION_CONFIRMED_FADE",
    ).row(0, named=True)

    assert row["exit_reason"] == "STOP_HIT"
    assert row["net_pnl_points"] < 0


def test_filter_only_strategy_has_no_fake_pnl(tmp_path: Path) -> None:
    result = run_cme_wall_realistic_backtest_v1(output_dir=_fixture_outputs(tmp_path))
    row = result.trade_events.filter(
        pl.col("strategy_name") == "AVOID_DIRECT_WALL_TRADE_FILTER",
    ).row(0, named=True)
    perf = result.performance_summary.filter(
        pl.col("strategy_name") == "AVOID_DIRECT_WALL_TRADE_FILTER",
    ).row(0, named=True)

    assert row["direction"] == "NONE"
    assert row["net_pnl_points"] == 0
    assert perf["total_trades"] == 0


def test_proxy_vs_realistic_comparison_flags_overcount(tmp_path: Path) -> None:
    result = run_cme_wall_realistic_backtest_v1(output_dir=_fixture_outputs(tmp_path))
    row = result.proxy_vs_realistic.filter(
        pl.col("realistic_strategy_name") == "WALL_REJECTION_CONFIRMED_FADE",
    ).row(0, named=True)

    assert row["proxy_row_count"] > row["realistic_trade_count"]
    assert row["overcount_ratio"] > 1


def test_performance_report_computes_drawdown_and_profit_factor(tmp_path: Path) -> None:
    result = run_cme_wall_realistic_backtest_v1(output_dir=_fixture_outputs(tmp_path))
    row = result.performance_summary.filter(
        pl.col("strategy_name") == "WALL_REJECTION_CONFIRMED_FADE",
    ).row(0, named=True)

    assert row["total_trades"] == 2
    assert row["profit_factor"] is not None
    assert row["max_drawdown_points"] < 0


def test_reports_avoid_direct_order_terms_and_money_result_claims(tmp_path: Path) -> None:
    result = run_cme_wall_realistic_backtest_v1(output_dir=_fixture_outputs(tmp_path))
    report = "\n".join(cme_wall_realistic_backtest_v1_report_lines(result))
    direct_order_pattern = re.compile(r"\b(?:bu[y]|se[ll])\b", flags=re.IGNORECASE)

    assert direct_order_pattern.search(report) is None
    assert "profitable" not in report.lower()
    assert "profitability" not in report.lower()
    assert report_text_is_safe(report)


def test_redacted_paths_only() -> None:
    assert report_text_is_safe(r"C:\Users\example\private\wall.csv") is True


def _fixture_outputs(
    tmp_path: Path,
    *,
    mode: str = "mixed",
    duplicate_ranking: bool = False,
) -> Path:
    output = tmp_path / "outputs"
    output.mkdir(parents=True)
    _rankings(mode=mode, duplicate=duplicate_ranking).write_csv(
        output / "fetched_cme_wall_rankings.csv",
    )
    _price(mode=mode).write_parquet(output / "dukascopy_xau_15m.parquet")
    _proxy_independent().write_csv(output / "cme_wall_strategy_independent_event_performance.csv")
    _proxy_realism().write_csv(output / "cme_wall_strategy_trade_realism_audit.csv")
    _empty_named(["snapshot_timestamp"]).write_csv(output / "fetched_cme_wall_outcome_journal.csv")
    _empty_named(["strategy_name"]).write_csv(output / "fetched_cme_wall_role_summary.csv")
    _empty_named(["strategy_name"]).write_csv(output / "cme_wall_strategy_entry_exit_rewrite_plan.csv")
    _empty_named(["event_type"]).write_csv(output / "gemini_sd_grid_events.csv")
    return output


def _rankings(*, mode: str, duplicate: bool) -> pl.DataFrame:
    if mode == "no_confirmation":
        rows = [_ranking("2026-05-20T00:00:00+00:00", 110.0)]
    elif mode in {"pre_entry_target_only", "ambiguous"}:
        rows = [_ranking("2026-05-20T00:00:00+00:00", 110.0)]
    elif mode == "acceptance_target_behind_entry":
        rows = [
            _ranking(
                "2026-05-20T00:00:00+00:00",
                90.0,
                future_price=100.0,
                side="BELOW",
                wall_type="OI_WALL",
            ),
            _ranking(
                "2026-05-20T00:00:00+00:00",
                85.0,
                future_price=100.0,
                side="BELOW",
                wall_type="OI_WALL",
                rank=2,
            ),
        ]
    else:
        rows = [
            _ranking("2026-05-20T00:00:00+00:00", 110.0),
            _ranking("2026-05-20T02:00:00+00:00", 110.0),
            _ranking("2026-05-20T04:00:00+00:00", 110.0),
        ]
    if duplicate:
        rows.append(dict(rows[0]))
    return pl.DataFrame(rows, infer_schema_length=None)


def _ranking(
    timestamp: str,
    strike: float,
    *,
    future_price: float = 100.0,
    side: str = "ABOVE",
    wall_type: str = "CALL_VOLUME_WALL",
    rank: int = 1,
) -> dict[str, object]:
    return {
        "snapshot_timestamp": timestamp,
        "trade_date": timestamp[:10],
        "expiration": "2026-05-29",
        "dte": 1.0,
        "future_price": future_price,
        "strike": strike,
        "option_type": "call",
        "call_volume": 100.0,
        "put_volume": 0.0,
        "total_volume": 100.0,
        "open_interest": 1000.0,
        "implied_volatility": 0.2,
        "distance_from_price": strike - future_price,
        "side_relative_to_price": side,
        "wall_type": wall_type,
        "wall_score": 100.0,
        "rank_overall": rank,
        "rank_above": rank if side == "ABOVE" else None,
        "rank_below": None,
        "active_threshold_passed": True,
        "context_threshold_passed": True,
        "distance_bucket": "0_25",
        "notes": "Synthetic context-only wall.",
    }


def _price(*, mode: str) -> pl.DataFrame:
    if mode == "no_confirmation":
        rows = [
            _candle("2026-05-20T00:00:00+00:00", 100, 104, 99, 101),
            _candle("2026-05-20T00:15:00+00:00", 101, 105, 100, 102),
            _candle("2026-05-20T00:30:00+00:00", 102, 106, 101, 103),
        ]
    elif mode == "pre_entry_target_only":
        rows = [
            _candle("2026-05-20T00:00:00+00:00", 100, 100, 100, 100),
            _candle("2026-05-20T00:15:00+00:00", 101, 111, 80, 108),
            _candle("2026-05-20T00:30:00+00:00", 108, 109, 106, 107),
            _candle("2026-05-20T00:45:00+00:00", 107, 108, 105, 106),
        ]
    elif mode == "ambiguous":
        rows = [
            _candle("2026-05-20T00:00:00+00:00", 100, 100, 100, 100),
            _candle("2026-05-20T00:15:00+00:00", 101, 111, 100, 108),
            _candle("2026-05-20T00:30:00+00:00", 108, 123, 99, 112),
        ]
    elif mode == "acceptance_target_behind_entry":
        rows = [
            _candle("2026-05-20T00:00:00+00:00", 100, 100, 100, 100),
            _candle("2026-05-20T00:15:00+00:00", 88, 89, 84, 85),
            _candle("2026-05-20T00:30:00+00:00", 84, 86, 82, 83),
            _candle("2026-05-20T00:45:00+00:00", 80, 81, 74, 76),
        ]
    else:
        rows = [
            _candle("2026-05-20T00:00:00+00:00", 100, 100, 100, 100),
            _candle("2026-05-20T00:15:00+00:00", 101, 111, 100, 108),
            _candle("2026-05-20T00:30:00+00:00", 108, 109, 100, 101),
            _candle("2026-05-20T02:00:00+00:00", 100, 100, 100, 100),
            _candle("2026-05-20T02:15:00+00:00", 101, 111, 100, 108),
            _candle("2026-05-20T02:30:00+00:00", 108, 123, 99, 112),
            _candle("2026-05-20T04:00:00+00:00", 100, 100, 100, 100),
            _candle("2026-05-20T04:15:00+00:00", 110, 112, 109, 111),
            _candle("2026-05-20T04:30:00+00:00", 111, 113, 110, 112),
            _candle("2026-05-20T04:45:00+00:00", 112, 125, 111, 124),
        ]
    return pl.DataFrame(rows, infer_schema_length=None)


def _candle(timestamp: str, open_: float, high: float, low: float, close: float) -> dict[str, object]:
    return {
        "timestamp": timestamp,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "spread_points": 0.5,
    }


def _proxy_independent() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "strategy_name": "WALL_REJECTION_FADE",
                "independent_event_count": 10,
                "net_pnl_proxy": 100.0,
            },
            {
                "strategy_name": "WALL_ACCEPTANCE_CONTINUATION",
                "independent_event_count": 8,
                "net_pnl_proxy": 80.0,
            },
        ],
        infer_schema_length=None,
    )


def _proxy_realism() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {"strategy_name": "WALL_REJECTION_FADE", "trade_count": 10},
            {"strategy_name": "WALL_ACCEPTANCE_CONTINUATION", "trade_count": 8},
        ],
        infer_schema_length=None,
    )


def _empty_named(columns: list[str]) -> pl.DataFrame:
    return pl.DataFrame(schema={column: pl.Utf8 for column in columns})
