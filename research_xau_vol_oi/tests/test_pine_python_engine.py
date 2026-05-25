from datetime import UTC, datetime, timedelta

import polars as pl

from research_xau_vol_oi.pine_python_engine import (
    PinePythonEngineConfig,
    acceptance_breakout,
    canonicalize_yahoo_ohlc,
    cme_wall_filter_allows,
    donchian_high_low,
    ema,
    guru_filter_allows,
    macd,
    no_trade_middle_range,
    rejection_after_touch,
    resample_ohlc,
    rsi,
    run_pine_python_engine_lab,
    run_python_backtest,
    standard_deviation_bands,
    tradingview_parity_report,
    write_chart_artifacts,
    yahoo_inventory_markdown,
)


def test_yahoo_ohlc_canonical_schema() -> None:
    frame = canonicalize_yahoo_ohlc(
        pl.DataFrame(
            [
                {
                    "Datetime": datetime(2026, 5, 25, 12, tzinfo=UTC),
                    "Open": 100.0,
                    "High": 102.0,
                    "Low": 99.0,
                    "Close": 101.0,
                    "Volume": 1000,
                }
            ]
        ),
        symbol="GC=F",
        interval="1h",
        source="TEST",
        quality="DIRECT_YAHOO",
    )

    assert frame.columns == [
        "timestamp",
        "symbol",
        "interval",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "source",
        "quality",
    ]
    assert frame.row(0, named=True)["quality"] == "DIRECT_YAHOO"


def test_4h_resample_from_1h() -> None:
    source = canonicalize_yahoo_ohlc(
        _hourly_ohlc(8),
        symbol="GC=F",
        interval="1h",
        source="TEST",
        quality="DIRECT_YAHOO",
    )

    resampled = resample_ohlc(source, target_interval="4h", source_interval="1h")

    assert resampled.height == 2
    first = resampled.row(0, named=True)
    assert first["timestamp"] == datetime(2026, 5, 25, 4, tzinfo=UTC)
    assert first["open"] == 100.0
    assert first["close"] == 103.5
    assert first["quality"] == "RESAMPLED_FROM_1H"


def test_ema_matches_known_values() -> None:
    assert ema([1.0, 2.0, 3.0], 3) == [1.0, 1.5, 2.25]


def test_rsi_no_lookahead() -> None:
    values = [1.0, 2.0, 3.0, 2.0, 5.0, 100.0]
    full = rsi(values, length=3)
    prefix = rsi(values[:5], length=3)

    assert full[4] == prefix[-1]


def test_macd_no_lookahead() -> None:
    values = [1.0, 2.0, 3.0, 2.0, 5.0, 100.0]
    full = macd(values, fast=2, slow=3, signal=2)[2]
    prefix = macd(values[:5], fast=2, slow=3, signal=2)[2]

    assert full[4] == prefix[-1]


def test_donchian_no_lookahead() -> None:
    high = [1.0, 2.0, 3.0, 100.0]
    low = [1.0, 1.0, 1.0, 1.0]
    full_high, _ = donchian_high_low(high, low, length=3)
    prefix_high, _ = donchian_high_low(high[:3], low[:3], length=3)

    assert full_high[2] == 3.0
    assert full_high[2] == prefix_high[-1]


def test_sd_band_no_lookahead() -> None:
    values = [1.0, 2.0, 3.0, 100.0]
    full_mid, full_upper, full_lower, _ = standard_deviation_bands(values, length=3)
    prefix_mid, prefix_upper, prefix_lower, _ = standard_deviation_bands(values[:3], length=3)

    assert full_mid[2] == prefix_mid[-1]
    assert full_upper[2] == prefix_upper[-1]
    assert full_lower[2] == prefix_lower[-1]


def test_acceptance_breakout_logic() -> None:
    result = acceptance_breakout([99.0, 101.0, 102.0], 100.0, hold_bars=2)

    assert result == [False, False, True]


def test_rejection_after_touch_logic() -> None:
    long_result = rejection_after_touch([101.0], [99.0], [101.0], 100.0, direction="LONG")
    short_result = rejection_after_touch([101.0], [99.0], [99.0], 100.0, direction="SHORT")

    assert long_result == [True]
    assert short_result == [True]


def test_no_trade_middle_range_logic() -> None:
    assert no_trade_middle_range([-0.4, 0.6, None], no_trade_sd=0.5) == [True, False, False]


def test_backtest_does_not_use_future_bars() -> None:
    config = PinePythonEngineConfig(
        min_warmup_bars=0,
        max_hold_bars=2,
        slippage_points=0.0,
        commission_rate=0.0,
    )
    ohlc = canonicalize_yahoo_ohlc(
        _close_ohlc([100.0, 100.0, 105.0, 106.0, 50.0]),
        symbol="GC=F",
        interval="1h",
        source="TEST",
    )
    changed_future = canonicalize_yahoo_ohlc(
        _close_ohlc([100.0, 100.0, 105.0, 106.0, 500.0]),
        symbol="GC=F",
        interval="1h",
        source="TEST",
    )
    signals = _manual_signal_frame(ohlc, direction="LONG", sd_std=100.0, atr=100.0)

    trades, _ = run_python_backtest(ohlc, signals, config=config)
    changed_trades, _ = run_python_backtest(changed_future, signals, config=config)

    assert trades.row(0, named=True)["exit_bar_index"] == 3
    assert trades.row(0, named=True)["pnl_after_cost"] == changed_trades.row(0, named=True)[
        "pnl_after_cost"
    ]


def test_commission_and_slippage_applied() -> None:
    config = PinePythonEngineConfig(
        min_warmup_bars=0,
        max_hold_bars=1,
        slippage_points=1.0,
        commission_rate=0.0005,
    )
    ohlc = canonicalize_yahoo_ohlc(
        _close_ohlc([100.0, 100.0, 110.0]),
        symbol="GC=F",
        interval="1h",
        source="TEST",
    )
    signals = _manual_signal_frame(ohlc, direction="LONG", sd_std=100.0, atr=100.0)

    trades, _ = run_python_backtest(ohlc, signals, config=config)

    assert round(trades.row(0, named=True)["pnl_after_cost"], 3) == 7.895
    assert round(trades.row(0, named=True)["commission_paid"], 3) == 0.105


def test_cme_wall_filter_blocks_long_into_wall() -> None:
    allowed, state = cme_wall_filter_allows(
        {"direction": "LONG", "entry_price": 100.0},
        {
            "wall_score": 0.3,
            "nearest_wall_above_price": 104.0,
            "accepted_wall": False,
            "rejected_wall": False,
        },
        return_state=True,
    )

    assert not allowed
    assert state == "BLOCK_LONG_INTO_STRONG_WALL"


def test_guru_unknown_timing_is_context_only() -> None:
    allowed, state = guru_filter_allows(
        {},
        {"evidence_status": "UNKNOWN_TIMING", "no_trade_filter_active": True},
        {},
        return_state=True,
    )

    assert allowed
    assert state == "GURU_CONTEXT_ONLY_UNKNOWN_TIMING"


def test_tradingview_parity_report_handles_missing_pine_script(tmp_path) -> None:
    summary = pl.DataFrame(
        [
            {
                "strategy": "python_pine_like",
                "data_mode": "TEST",
                "symbol": "GC=F",
                "interval": "1h",
                "trade_count": 0,
                "win_rate": 0.0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "avg_pnl": 0.0,
                "expectancy": 0.0,
                "profit_factor": None,
                "max_drawdown": 0.0,
                "sharpe_proxy": None,
                "commission_paid": 0.0,
                "long_pnl": 0.0,
                "short_pnl": 0.0,
                "long_trade_count": 0,
                "short_trade_count": 0,
                "average_hold_bars": 0.0,
                "outlier_loss_count": 0,
                "sample_size_warning": True,
                "research_only": True,
            }
        ]
    )

    parity = tradingview_parity_report(summary, output_root=tmp_path, pine_path=tmp_path / "missing.pine")

    assert (tmp_path / "pine_script_needed_for_exact_parity.md").exists()
    assert set(parity.get_column("parity_status").to_list()) == {"PARITY_CHECK_NEEDED"}


def test_chart_artifact_created(tmp_path) -> None:
    ohlc = canonicalize_yahoo_ohlc(
        _close_ohlc([100.0, 101.0, 102.0]),
        symbol="GC=F",
        interval="1h",
        source="TEST",
    )
    signals = _manual_signal_frame(ohlc, direction="LONG", sd_std=1.0, atr=1.0)

    pine_chart, overlay_chart = write_chart_artifacts(
        charts_dir=tmp_path / "charts",
        ohlc=ohlc,
        signals=signals,
        overlay_trades=pl.DataFrame(),
    )

    assert pine_chart.exists()
    assert overlay_chart.exists()


def test_reports_do_not_claim_profitability(tmp_path) -> None:
    run_pine_python_engine_lab(
        output_dir=tmp_path,
        config=PinePythonEngineConfig(enable_yahoo_intraday_fetch=False),
        pine_path=None,
    )
    text = "\n".join(path.read_text(encoding="utf-8").lower() for path in tmp_path.rglob("*.md"))

    assert "profitable" not in text
    assert "profitability" not in text
    assert "safe to trade" not in text
    assert "live ready" not in text


def test_redacted_paths_only() -> None:
    markdown = yahoo_inventory_markdown(
        pl.DataFrame(
            [
                {
                    "symbol": "GC=F",
                    "interval": "1h",
                    "rows": 1,
                    "start": "2026-05-25T00:00:00Z",
                    "end": "2026-05-25T01:00:00Z",
                    "source": r"C:\Users\example\secret.csv",
                    "quality": "DIRECT_YAHOO",
                    "available": True,
                    "note": "path redaction check",
                }
            ]
        )
    )

    assert r"C:\Users" not in markdown
    assert "<REDACTED_PATH>" in markdown


def _hourly_ohlc(count: int) -> pl.DataFrame:
    start = datetime(2026, 5, 25, tzinfo=UTC)
    return pl.DataFrame(
        [
            {
                "timestamp": start + timedelta(hours=index),
                "open": 100.0 + index,
                "high": 101.0 + index,
                "low": 99.0 + index,
                "close": 100.5 + index,
                "volume": 10.0 + index,
            }
            for index in range(count)
        ]
    )


def _close_ohlc(closes: list[float]) -> pl.DataFrame:
    start = datetime(2026, 5, 25, tzinfo=UTC)
    return pl.DataFrame(
        [
            {
                "timestamp": start + timedelta(hours=index),
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "volume": 100.0,
            }
            for index, close in enumerate(closes)
        ]
    )


def _manual_signal_frame(
    ohlc: pl.DataFrame,
    *,
    direction: str,
    sd_std: float,
    atr: float,
) -> pl.DataFrame:
    first = ohlc.row(0, named=True)
    return pl.DataFrame(
        [
            {
                "timestamp": first["timestamp"],
                "direction_candidate": direction,
                "reason": "TEST_SIGNAL",
                "pine_like_score": 1.0,
                "sd_position": 1.5,
                "sd_std": sd_std,
                "atr": atr,
                "no_trade_middle_range": False,
                "acceptance_breakout": True,
                "acceptance_breakdown": False,
                "rejection_after_level_touch": False,
                "session_open_distance": 0.0,
            }
        ]
    )
