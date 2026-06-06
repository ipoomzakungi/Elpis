from datetime import UTC, datetime, timedelta

import polars as pl

from research_xau_vol_oi.pine_python_engine import PinePythonEngineConfig
from research_xau_vol_oi.python_single_timeframe_validation import (
    build_4h_deep_dive,
    build_fee_drag_by_timeframe,
    build_single_timeframe_results,
    build_timeframe_decision,
    build_walk_forward_by_timeframe,
    timeframe_decision_markdown,
)


def test_single_timeframe_results_do_not_aggregate_intervals() -> None:
    results = build_single_timeframe_results(_expanded_summary())

    assert results.height == 4
    assert "ALL" not in set(results.get_column("interval").to_list())
    assert set(results.get_column("interval").to_list()) == {"15m", "4h", "1d"}


def test_gld_marked_proxy_only() -> None:
    results = build_single_timeframe_results(_expanded_summary())
    row = results.filter(pl.col("symbol") == "GLD").row(0, named=True)

    assert row["proxy_warning"]
    assert row["timeframe_label"] == "PROXY_ONLY"


def test_xauusd_two_row_data_marked_insufficient() -> None:
    results = build_single_timeframe_results(_expanded_summary())
    row = results.filter(pl.col("symbol") == "XAUUSD=X").row(0, named=True)

    assert row["rows"] == 2
    assert row["timeframe_label"] == "INSUFFICIENT_DATA"


def test_walk_forward_chooses_policy_only_on_train() -> None:
    walk = build_walk_forward_by_timeframe(
        _policy_selection_trades(),
        config=_test_config(),
        min_test_trades=20,
    )

    first = walk.row(0, named=True)
    assert first["selected_filter_policy"] == "FEE_HURDLE_FILTER"
    assert first["test_net_pnl"] < 0


def test_walk_forward_test_period_frozen() -> None:
    walk = build_walk_forward_by_timeframe(
        _policy_selection_trades(),
        config=_test_config(),
        min_test_trades=20,
    )

    policies = set(walk.get_column("selected_filter_policy").to_list())
    assert policies == {"FEE_HURDLE_FILTER"}


def test_4h_deep_dive_generated(tmp_path) -> None:
    deep = build_4h_deep_dive(_deep_dive_trades(), output_root=tmp_path, config=_test_config())

    assert deep.height == 1
    assert deep.row(0, named=True)["direction"] == "LONG"


def test_fee_drag_report_flags_high_frequency_fee_problem() -> None:
    fee = build_fee_drag_by_timeframe(
        build_single_timeframe_results(_expanded_summary()),
        _fee_drag_trades(),
        _grid_preview("INCREASED"),
    )

    row = fee.filter((pl.col("symbol") == "GC=F") & (pl.col("interval") == "15m")).row(
        0,
        named=True,
    )
    assert row["recommendation"] == "DO_NOT_LOWER_GRID"


def test_lowering_grid_warning_preserved() -> None:
    fee = build_fee_drag_by_timeframe(
        build_single_timeframe_results(_expanded_summary()),
        _fee_drag_trades(),
        _grid_preview("INCREASED"),
    )

    assert set(fee.get_column("lowering_grid_sd_len_effect").to_list()) == {"INCREASED"}


def test_decision_report_does_not_claim_money_readiness() -> None:
    results = build_single_timeframe_results(_expanded_summary())
    walk = build_walk_forward_by_timeframe(_policy_selection_trades(), config=_test_config())
    fee = build_fee_drag_by_timeframe(results, _fee_drag_trades(), _grid_preview("INCREASED"))
    decision = build_timeframe_decision(results, walk, fee)
    labels = set(decision.get_column("decision_label").to_list())

    assert "READY_FOR_MONEY" not in labels
    assert "LIVE_READY" not in labels
    assert "PAPER_READY" not in labels
    assert "NOT_READY_FOR_MONEY" in labels


def test_reports_use_redacted_paths() -> None:
    markdown = timeframe_decision_markdown(
        pl.DataFrame(
            [
                {
                    "decision_label": "NOT_READY_FOR_MONEY",
                    "active": True,
                    "reason": r"C:\Users\example\secret.csv",
                    "research_only": True,
                }
            ]
        )
    )

    assert r"C:\Users" not in markdown
    assert "<REDACTED_PATH>" in markdown


def _expanded_summary() -> pl.DataFrame:
    return pl.DataFrame(
        [
            _summary("GC=F", "15m", "DIRECT_YAHOO", 712, 24, -84.38),
            _summary("GC=F", "4h", "RESAMPLED_FROM_1H", 852, 38, 940.65),
            _summary("XAUUSD=X", "1d", "DIRECT_YAHOO", 2, 0, 0.0),
            _summary("GLD", "1d", "PROXY_ONLY", 3901, 139, -381.66),
        ]
    )


def _summary(
    symbol: str,
    interval: str,
    quality: str,
    rows: int,
    trade_count: int,
    net_pnl: float,
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "interval": interval,
        "quality": quality,
        "rows": rows,
        "date_start": "2026-01-01T00:00:00Z",
        "date_end": "2026-05-01T00:00:00Z",
        "trade_count": trade_count,
        "win_rate": 0.5,
        "avg_win": 10.0,
        "avg_loss": -8.0,
        "avg_pnl": net_pnl / trade_count if trade_count else 0.0,
        "net_pnl_after_cost": net_pnl,
        "commission_paid": float(trade_count),
        "profit_factor": 1.2,
        "max_drawdown": -20.0,
        "long_pnl": net_pnl * 0.6,
        "short_pnl": net_pnl * 0.4,
        "sample_size_warning": trade_count < 30,
    }


def _policy_selection_trades() -> pl.DataFrame:
    rows = []
    start = datetime(2026, 1, 1, tzinfo=UTC)
    for index in range(100):
        train = index < 50
        fee_pass = index % 2 == 0
        pnl = 5.0 if train and fee_pass else -20.0 if train else -10.0 if fee_pass else 20.0
        rows.append(
            _trade_row(
                index=index,
                timestamp=start + timedelta(hours=4 * index),
                run_symbol="GC=F",
                run_interval="4h",
                pnl=pnl,
                fee_pass=fee_pass,
            )
        )
    return pl.DataFrame(rows)


def _deep_dive_trades() -> pl.DataFrame:
    return pl.DataFrame(
        [
            _trade_row(
                index=2,
                timestamp=datetime(2026, 1, 1, tzinfo=UTC),
                run_symbol="GC=F",
                run_interval="4h",
                pnl=12.0,
                fee_pass=True,
            )
        ]
    )


def _fee_drag_trades() -> pl.DataFrame:
    rows = []
    start = datetime(2026, 1, 1, tzinfo=UTC)
    for index in range(24):
        rows.append(
            _trade_row(
                index=index,
                timestamp=start + timedelta(minutes=15 * index),
                run_symbol="GC=F",
                run_interval="15m",
                pnl=-1.0,
                fee_pass=True,
            )
        )
    return pl.DataFrame(rows)


def _trade_row(
    *,
    index: int,
    timestamp: datetime,
    run_symbol: str,
    run_interval: str,
    pnl: float,
    fee_pass: bool,
) -> dict[str, object]:
    return {
        "trade_id": f"t{index}",
        "symbol": run_symbol,
        "interval": run_interval,
        "direction": "LONG" if index % 2 == 0 else "SHORT",
        "signal_timestamp": timestamp,
        "entry_timestamp": timestamp + timedelta(hours=1),
        "exit_timestamp": timestamp + timedelta(hours=2),
        "signal_bar_index": index,
        "entry_bar_index": index + 1,
        "exit_bar_index": index + 2,
        "entry_price": 100.0,
        "exit_price": 100.0 + pnl,
        "gross_pnl_before_cost": pnl + 0.2,
        "pnl_after_cost": pnl,
        "commission_paid": 0.1,
        "slippage_paid": 0.1,
        "bars_in_trade": 1,
        "entry_reason": "TEST",
        "exit_reason": "TEST",
        "pine_like_score": 1.0,
        "sd_position": 1.5,
        "atr": 1.0,
        "stop_price": 90.0,
        "target_price": 110.0,
        "research_only": True,
        "run_symbol": run_symbol,
        "run_interval": run_interval,
        "data_quality": "DIRECT_YAHOO",
        "no_trade_middle_range": False,
        "acceptance_breakout": True,
        "rejection_after_level_touch": False,
        "session_open_distance": 0.0,
        "signal_atr": 5.0 if fee_pass else 0.0,
        "signal_sd_std": 5.0 if fee_pass else 0.0,
    }


def _grid_preview(effect: str) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "grid_sd_len": 20,
                "entry_sd": 1.25,
                "no_trade_sd": 0.5,
                "formation_trade_count": 10,
                "test_trade_count": 10,
                "full_sample_trade_count": 20,
                "formation_avg_pnl": 1.0,
                "test_avg_pnl": 1.0,
                "full_sample_avg_pnl": 1.0,
                "formation_commission_paid": 1.0,
                "full_sample_commission_paid": 2.0,
                "selected_for_test": True,
                "selection_basis": "formation_only",
                "lower_grid_sd_len_frequency_effect": effect,
                "sample_size_warning": True,
            }
        ]
    )


def _test_config() -> PinePythonEngineConfig:
    return PinePythonEngineConfig(fee_buffer_points=0.0, open_distance_limit_points=25.0)
