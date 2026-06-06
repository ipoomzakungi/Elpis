from datetime import UTC, datetime, timedelta

import polars as pl

from research_xau_vol_oi.pine_strategy_overlay_lab import (
    PineProxyConfig,
    build_baseline_summary,
    build_filter_overlay_plan,
    build_proxy_trade_candidates,
    build_sd_grid_sensitivity,
    cme_wall_filter_allows,
    fee_hurdle_allows,
    filter_overlay_plan_markdown,
    guru_no_trade_filter_allows,
    run_overlay_backtest,
    run_pine_strategy_overlay_lab,
)


def test_baseline_losing_strategy_labels_do_not_trade() -> None:
    summary = build_baseline_summary()
    row = summary.row(0, named=True)

    assert row["net_pnl"] < 0
    assert row["baseline_status_label"] == "DO_NOT_TRADE_BASELINE"


def test_long_only_and_short_only_metrics_are_separated() -> None:
    summary = run_overlay_backtest(_trade_candidates(), data_mode="ACTUAL_TRADE_LIST")
    by_policy = {row["policy"]: row for row in summary.to_dicts()}

    assert by_policy["long_only"]["trade_count"] == 2
    assert by_policy["short_only"]["trade_count"] == 2
    assert by_policy["long_only"]["net_pnl_after_cost"] != by_policy["short_only"]["net_pnl_after_cost"]


def test_fee_hurdle_blocks_low_expectancy_trades() -> None:
    assert fee_hurdle_allows(5.0, 2.0, buffer_points=0.5)
    assert not fee_hurdle_allows(2.0, 2.0, buffer_points=0.5)


def test_cme_wall_filter_blocks_trade_into_strong_wall() -> None:
    trade = {"direction": "long", "entry_price": 4700.0}
    cme = {
        "wall_score": 0.35,
        "nearest_wall_above_price": 4705.0,
        "accepted_wall": False,
        "rejected_wall": False,
    }

    allowed, state = cme_wall_filter_allows(trade, cme, return_state=True)

    assert not allowed
    assert state == "BLOCK_LONG_INTO_STRONG_WALL"


def test_guru_no_trade_filter_blocks_middle_range_trades() -> None:
    allowed, state = guru_no_trade_filter_allows(
        {"sd_position": 0.1},
        {},
        return_state=True,
    )

    assert not allowed
    assert state == "BLOCK_NO_TRADE_MIDDLE_RANGE"


def test_pyramiding_reduction_test_exists_in_plan() -> None:
    plan = build_filter_overlay_plan(trade_list_available=False, data_mode="PROXY_ONLY")
    rows = plan.filter(pl.col("overlay") == "outlier_loss_guard").to_dicts()

    assert rows
    assert "pyramiding 3 vs 1" in rows[0]["scenario"]


def test_sd_grid_sensitivity_uses_formation_selection_not_full_sample() -> None:
    sensitivity = build_sd_grid_sensitivity(_price_frame())
    selected = sensitivity.filter(pl.col("selected_for_test"))

    assert not selected.is_empty()
    assert set(selected.get_column("selection_basis").to_list()) == {"formation_only"}


def test_overlay_backtest_uses_actual_trade_list_if_provided(tmp_path) -> None:
    trade_list = tmp_path / "pine_trade_list.csv"
    pl.DataFrame(
        [
            {
                "timestamp": "2026-05-14T04:00:00Z",
                "direction": "long",
                "entry_price": 4700.0,
                "exit_price": 4710.0,
                "pnl": 8.0,
                "commission": 2.0,
            }
        ]
    ).write_csv(trade_list)

    result = run_pine_strategy_overlay_lab(
        output_dir=tmp_path,
        pine_path=None,
        trade_list_path=trade_list,
    )

    assert result.trade_list_available
    assert result.data_mode == "ACTUAL_TRADE_LIST"
    assert result.trade_candidates.height == 1
    assert not (tmp_path / "pine_trade_list_missing_request.md").exists()


def test_missing_trade_list_creates_clear_request_file(tmp_path) -> None:
    result = run_pine_strategy_overlay_lab(output_dir=tmp_path, pine_path=None)

    request = tmp_path / "pine_trade_list_missing_request.md"
    assert not result.trade_list_available
    assert request.exists()
    assert "TradingView List of Trades CSV was not found" in request.read_text(encoding="utf-8")


def test_fast_start_decision_never_claims_live_readiness_from_losing_baseline(tmp_path) -> None:
    result = run_pine_strategy_overlay_lab(output_dir=tmp_path, pine_path=None)
    labels = set(result.fast_start_decision.get_column("decision_label").to_list())

    assert "DO_NOT_TRADE_BASELINE" in labels
    assert "READY_FOR_SHADOW_REVIEW" not in labels


def test_reports_do_not_claim_profitability(tmp_path) -> None:
    run_pine_strategy_overlay_lab(output_dir=tmp_path, pine_path=None)
    combined = "\n".join(path.read_text(encoding="utf-8").lower() for path in tmp_path.glob("*.md"))

    assert "profitable" not in combined
    assert "safe to trade" not in combined
    assert "live ready" not in combined


def test_redacted_paths_only() -> None:
    markdown = filter_overlay_plan_markdown(
        pl.DataFrame(
            [
                {
                    "part": "X",
                    "overlay": "path_check",
                    "scenario": r"C:\Users\example\secret.csv",
                    "data_mode": "PROXY_ONLY",
                    "enabled": True,
                    "formation_test_required": False,
                    "notes": "redaction check",
                }
            ]
        )
    )

    assert r"C:\Users" not in markdown
    assert "<REDACTED_PATH>" in markdown


def test_python_pine_proxy_generates_candidates_on_yahoo_style_ohlc() -> None:
    candidates = build_proxy_trade_candidates(_price_frame(), config=PineProxyConfig())

    assert {"timestamp", "direction", "pnl_after_cost", "source_mode"}.issubset(candidates.columns)
    assert set(candidates.get_column("source_mode").to_list()) <= {"PROXY_ONLY"}


def _trade_candidates() -> pl.DataFrame:
    return pl.DataFrame(
        [
            _candidate("long", 10.0),
            _candidate("long", -4.0),
            _candidate("short", -12.0),
            _candidate("short", 3.0),
        ]
    )


def _candidate(direction: str, pnl: float) -> dict[str, object]:
    return {
        "timestamp": "2026-05-14T04:00:00Z",
        "trade_id": f"{direction}_{pnl}",
        "direction": direction,
        "entry_price": 4700.0,
        "exit_price": 4701.0,
        "pnl": pnl,
        "pnl_after_cost": pnl,
        "bars_in_trade": 2,
        "entry_reason": "test",
        "exit_reason": "test",
        "pine_signal_score": 1.0,
        "grid_state": "LOWER_ENTRY" if direction == "long" else "UPPER_ENTRY",
        "ladder_state": "L1",
        "sd_position": 1.2,
        "regime_state": "test",
        "trend_filter_state": "test",
        "sweep_confirmation": False,
        "fee_hurdle_passed": True,
        "cme_filter_state": "CME_NO_BLOCK",
        "guru_filter_state": "GURU_NO_BLOCK",
        "final_allow_trade": True,
        "session_date": "2026-05-14",
        "expected_move": 5.0,
        "round_trip_cost": 1.0,
        "source_mode": "ACTUAL_TRADE_LIST",
        "session_open": 4700.0,
    }


def _price_frame() -> pl.DataFrame:
    start = datetime(2026, 5, 1, 4, 0, tzinfo=UTC)
    rows = []
    price = 4700.0
    for index in range(180):
        wave = 18.0 if index % 18 == 0 else -18.0 if index % 18 == 9 else 0.0
        drift = (index % 7 - 3) * 0.4
        close = price + wave + drift
        rows.append(
            {
                "timestamp": start + timedelta(minutes=15 * index),
                "session_date": (start + timedelta(minutes=15 * index)).date().isoformat(),
                "open": price,
                "high": max(price, close) + 3.0,
                "low": min(price, close) - 3.0,
                "close": close,
                "session_open": 4700.0,
                "volume": 100.0 + index,
            }
        )
        price = close
    return pl.DataFrame(rows)
