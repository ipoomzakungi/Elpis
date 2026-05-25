from datetime import UTC, datetime, timedelta

import polars as pl

from research_xau_vol_oi.pine_python_engine import PinePythonEngineConfig, canonicalize_yahoo_ohlc
from research_xau_vol_oi.python_engine_expanded_backtest import (
    build_data_expansion_plan,
    build_expanded_fast_use_decision,
    build_expanded_overlay_summary,
    build_grid_sensitivity_preview,
    build_pine_parity_gap_report,
    data_plan_markdown,
    run_expanded_backtests,
    run_python_engine_expanded_backtest_lab,
)


def test_data_expansion_plan_handles_missing_yahoo_data() -> None:
    plan = build_data_expansion_plan(pl.DataFrame())

    gc_1m = plan.filter((pl.col("symbol") == "GC=F") & (pl.col("interval") == "1m")).row(
        0,
        named=True,
    )
    assert gc_1m["current_rows"] == 0
    assert gc_1m["fetch_needed"]


def test_expanded_backtest_works_across_multiple_intervals() -> None:
    frames = [_canonical_bars("15m", 140), _canonical_bars("1h", 140)]

    summary, trades = run_expanded_backtests(
        output_root=none_path(),
        local_frames=frames,
        base_config=_fast_config(interval="15m"),
    )

    intervals = set(summary.get_column("interval").to_list())
    assert {"15m", "1h"}.issubset(intervals)
    assert "trade_count" in summary.columns
    assert trades.height >= 0


def test_4h_resampling_included() -> None:
    summary, _ = run_expanded_backtests(
        output_root=none_path(),
        local_frames=[_canonical_bars("1h", 160)],
        base_config=_fast_config(interval="1h"),
    )

    assert "4h" in set(summary.get_column("interval").to_list())


def test_overlay_comparison_labels_small_sample(tmp_path) -> None:
    _, trades = run_expanded_backtests(
        output_root=tmp_path,
        local_frames=[_canonical_bars("15m", 80)],
        base_config=_fast_config(interval="15m"),
    )

    overlay = build_expanded_overlay_summary(trades, output_root=tmp_path, config=_fast_config())

    raw = overlay.filter(pl.col("policy") == "raw_python_strategy").row(0, named=True)
    assert raw["sample_size_warning"]


def test_parity_gap_report_generated_when_tradingview_trade_list_missing(tmp_path) -> None:
    gap = build_pine_parity_gap_report(output_root=tmp_path)
    missing = gap.filter(pl.col("gap") == "missing_pine_trade_list").row(0, named=True)

    assert missing["status"] == "OPEN"
    assert missing["priority_fix_rank"] == 1


def test_grid_sensitivity_uses_formation_test_split(tmp_path) -> None:
    _canonical_bars("15m", 160).write_parquet(tmp_path / "xau_feature_table.parquet")

    preview = build_grid_sensitivity_preview(
        output_root=tmp_path,
        base_config=_fast_config(interval="15m"),
    )

    assert not preview.is_empty()
    assert set(preview.get_column("selection_basis").to_list()) == {"formation_only"}
    assert preview.filter(pl.col("selected_for_test")).height == 1


def test_lowering_grid_sd_len_reports_frequency_effect(tmp_path) -> None:
    _canonical_bars("15m", 160).write_parquet(tmp_path / "xau_feature_table.parquet")

    preview = build_grid_sensitivity_preview(
        output_root=tmp_path,
        base_config=_fast_config(interval="15m"),
    )

    effects = set(preview.get_column("lower_grid_sd_len_frequency_effect").to_list())
    assert effects <= {"INCREASED", "DECREASED", "NO_CHANGE"}
    assert effects


def test_fast_use_decision_never_outputs_money_readiness() -> None:
    decision = build_expanded_fast_use_decision(
        data_plan=build_data_expansion_plan(pl.DataFrame()),
        expanded_summary=pl.DataFrame(),
        overlay_summary=pl.DataFrame(
            [
                {
                    "policy": "raw_python_strategy",
                    "trades_allowed": 1,
                    "trades_blocked": 0,
                    "net_pnl_after_cost": -1.0,
                    "avg_pnl": -1.0,
                    "win_rate": 0.0,
                    "profit_factor": None,
                    "avoided_loss": 0.0,
                    "opportunity_cost": 0.0,
                    "net_filter_value": 0.0,
                    "false_block_rate": 0.0,
                    "sample_size_warning": True,
                    "research_only": True,
                }
            ]
        ),
        parity_gap=build_pine_parity_gap_report(output_root=none_path()),
    )
    labels = set(decision.get_column("decision_label").to_list())

    assert "READY_FOR_MONEY" not in labels
    assert "LIVE_READY" not in labels
    assert "PAPER_READY" not in labels
    assert "NOT_READY_FOR_MONEY" in labels


def test_reports_do_not_claim_profitability(tmp_path) -> None:
    _canonical_bars("15m", 100).write_parquet(tmp_path / "xau_feature_table.parquet")

    run_python_engine_expanded_backtest_lab(
        output_dir=tmp_path,
        config=_fast_config(interval="15m"),
    )
    text = "\n".join(path.read_text(encoding="utf-8").lower() for path in tmp_path.rglob("*.md"))

    assert "profitable" not in text
    assert "profitability" not in text
    assert "safe to trade" not in text
    assert "live ready" not in text


def test_redacted_paths_only() -> None:
    markdown = data_plan_markdown(
        pl.DataFrame(
            [
                {
                    "symbol": "GC=F",
                    "interval": "1h",
                    "period": "test",
                    "expected_history_limit": r"C:\Users\example\secret.csv",
                    "current_rows": 0,
                    "current_date_start": None,
                    "current_date_end": None,
                    "fetch_needed": True,
                    "useful_for": "indicator_parity",
                }
            ]
        )
    )

    assert r"C:\Users" not in markdown
    assert "<REDACTED_PATH>" in markdown


def _canonical_bars(interval: str, count: int) -> pl.DataFrame:
    minutes = {"15m": 15, "1h": 60}[interval]
    raw = []
    start = datetime(2026, 5, 1, tzinfo=UTC)
    price = 100.0
    for index in range(count):
        wave = 7.0 if index % 18 == 0 else -7.0 if index % 18 == 9 else 0.0
        drift = (index % 5 - 2) * 0.35
        close = price + wave + drift
        raw.append(
            {
                "timestamp": start + timedelta(minutes=minutes * index),
                "symbol": "GC=F",
                "open": price,
                "high": max(price, close) + 1.5,
                "low": min(price, close) - 1.5,
                "close": close,
                "volume": 100.0 + index,
            }
        )
        price = close
    return canonicalize_yahoo_ohlc(
        pl.DataFrame(raw),
        symbol="GC=F",
        interval=interval,
        source="TEST",
        quality="DIRECT_YAHOO",
    )


def _fast_config(interval: str = "15m") -> PinePythonEngineConfig:
    return PinePythonEngineConfig(
        symbol="GC=F",
        interval=interval,
        grid_sd_len=20,
        min_warmup_bars=25,
        max_hold_bars=4,
        slippage_points=0.1,
    )


def none_path():
    return __import__("pathlib").Path("__unused__")
