from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl

from research_xau_vol_oi.gemini_sd_grid_confirmation_backtest import (
    _safe_report_text,
    build_entry_model_comparison,
    build_grid_clustering_test,
    build_sd_grid_event_dataset,
    build_tp_sl_model_comparison,
    gemini_sd_grid_confirmation_report_lines,
    report_text_is_safe,
    run_gemini_sd_grid_confirmation_backtest,
)


def test_blind_3sd_and_confirmed_3sd_are_separate_models() -> None:
    events = build_sd_grid_event_dataset(inputs=_inputs())
    comparison = build_entry_model_comparison(
        events=events,
        price_by_timeframe=_price_by_timeframe(),
    )
    models = set(comparison.get_column("model_id").to_list())

    assert "BLIND_3SD_FADE" in models
    assert "REJECTION_CONFIRMED_3SD_FADE" in models


def test_rejection_confirmed_model_requires_close_back_inside() -> None:
    events = build_sd_grid_event_dataset(inputs=_inputs())
    comparison = build_entry_model_comparison(
        events=events,
        price_by_timeframe=_price_by_timeframe(),
    )
    rejection_events = events.filter(
        (pl.col("event_type") == "REJECTION_BACK_INSIDE")
        & (pl.col("level_type") == "3SD")
    )
    row = comparison.filter(pl.col("model_id") == "REJECTION_CONFIRMED_3SD_FADE").row(
        0,
        named=True,
    )

    assert rejection_events.height > 0
    assert rejection_events.filter(~pl.col("close_back_inside")).height == 0
    assert row["entry_count"] == rejection_events.height


def test_acceptance_continuation_requires_hold_beyond_level() -> None:
    events = build_sd_grid_event_dataset(inputs=_inputs())
    acceptance = events.filter(pl.col("event_type") == "ACCEPTANCE_1H_CLOSE")

    assert acceptance.height > 0
    assert acceptance.filter(~pl.col("hold_beyond_level")).height == 0


def test_1sd_filter_blocks_middle_zone_events() -> None:
    events = build_sd_grid_event_dataset(inputs=_inputs())
    comparison = build_entry_model_comparison(
        events=events,
        price_by_timeframe=_price_by_timeframe(),
    )
    row = comparison.filter(pl.col("model_id") == "NO_TRADE_1SD_FILTER").row(0, named=True)

    assert row["event_count"] > 0
    assert row["entry_count"] == 0


def test_tp_sl_comparison_includes_half_block_and_full_block() -> None:
    events = build_sd_grid_event_dataset(inputs=_inputs())
    comparison = build_tp_sl_model_comparison(
        events=events,
        price_by_timeframe=_price_by_timeframe(),
    )
    models = set(comparison.get_column("model_id").to_list())

    assert "TP_HALF_BLOCK_12_50_SL_HALF_BLOCK_12_50" in models
    assert "TP_FULL_BLOCK_25_SL_HALF_BLOCK_12_50" in models
    assert "TP_FULL_BLOCK_25_SL_3_5SD" in models


def test_grid_clustering_compares_random_shifted_baseline() -> None:
    grid = build_grid_clustering_test(inputs=_inputs())

    assert grid.height > 0
    assert grid.filter(pl.col("random_grid_baseline").is_not_null()).height == grid.height


def test_output_marks_realized_vol_proxy_when_iv_missing() -> None:
    events = build_sd_grid_event_dataset(inputs=_inputs())

    assert set(events.get_column("sd_proxy_source").to_list()) == {"REALIZED_VOL_PROXY"}


def test_report_does_not_output_buy_or_sell(tmp_path: Path) -> None:
    result = _run_tmp(tmp_path)
    report = "\n".join(gemini_sd_grid_confirmation_report_lines(result))

    assert "BUY" not in report.upper()
    assert "SELL" not in report.upper()
    assert report_text_is_safe(report)


def test_report_does_not_claim_profitability(tmp_path: Path) -> None:
    result = _run_tmp(tmp_path)
    report = "\n".join(gemini_sd_grid_confirmation_report_lines(result))

    assert "profitable" not in report.lower()
    assert "profitability" not in report.lower()
    assert report_text_is_safe(report)


def test_redacted_paths_only() -> None:
    redacted = _safe_report_text(r"C:\Users\example\private\source.parquet")

    assert "C:\\Users" not in redacted
    assert "<REDACTED_PATH>" in redacted


def _run_tmp(tmp_path: Path):
    _write_inputs(tmp_path)
    return run_gemini_sd_grid_confirmation_backtest(output_dir=tmp_path)


def _write_inputs(tmp_path: Path) -> None:
    _price_frame("15m").write_parquet(tmp_path / "dukascopy_xau_15m.parquet")
    _price_frame("30m").write_parquet(tmp_path / "dukascopy_xau_30m.parquet")
    _price_frame("1h").write_parquet(tmp_path / "dukascopy_xau_1h.parquet")
    _price_frame("4h").write_parquet(tmp_path / "dukascopy_xau_4h.parquet")
    _daily_frame().write_parquet(tmp_path / "dukascopy_xau_1d.parquet")


def _inputs() -> dict[str, pl.DataFrame]:
    return {
        "price_15m": _price_frame("15m"),
        "price_30m": _price_frame("30m"),
        "price_1h": _price_frame("1h"),
        "price_4h": _price_frame("4h"),
        "price_1d": _daily_frame(),
    }


def _price_by_timeframe() -> dict[str, pl.DataFrame]:
    return {
        "15m": _price_frame("15m"),
        "30m": _price_frame("30m"),
        "1h": _price_frame("1h"),
        "4h": _price_frame("4h"),
    }


def _price_frame(timeframe: str) -> pl.DataFrame:
    if timeframe == "1h":
        return _hourly_acceptance_frame()
    minutes = {"15m": 15, "30m": 30, "4h": 240}[timeframe]
    start = datetime(2026, 1, 1, tzinfo=UTC)
    rows = [
        _bar(start, 100.0, 101.0, 99.0, 100.0, timeframe),
        _bar(start + timedelta(minutes=minutes), 100.0, 121.0, 99.0, 121.0, timeframe),
        _bar(start + timedelta(minutes=2 * minutes), 121.0, 131.0, 118.0, 119.0, timeframe),
        _bar(start + timedelta(minutes=3 * minutes), 119.0, 120.0, 106.0, 108.0, timeframe),
        _bar(start + timedelta(minutes=4 * minutes), 108.0, 136.0, 120.0, 136.0, timeframe),
        _bar(start + timedelta(minutes=5 * minutes), 136.0, 139.0, 135.0, 138.0, timeframe),
    ]
    return pl.DataFrame(rows, infer_schema_length=None)


def _hourly_acceptance_frame() -> pl.DataFrame:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    rows = [
        _bar(start, 100.0, 101.0, 99.0, 100.0, "1h"),
        _bar(start + timedelta(hours=1), 100.0, 122.0, 99.0, 121.0, "1h"),
        _bar(start + timedelta(hours=2), 121.0, 126.0, 119.0, 123.0, "1h"),
        _bar(start + timedelta(hours=3), 123.0, 150.0, 122.0, 140.0, "1h"),
        _bar(start + timedelta(hours=4), 140.0, 142.0, 125.0, 130.0, "1h"),
    ]
    return pl.DataFrame(rows, infer_schema_length=None)


def _daily_frame() -> pl.DataFrame:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return pl.DataFrame(
        [
            {
                "timestamp": start,
                "trade_date": "2026-01-01",
                "timeframe": "1d",
                "open": 100.0,
                "high": 110.0,
                "low": 90.0,
                "close": 100.0,
                "spread_points": 0.5,
            }
        ],
        infer_schema_length=None,
    )


def _bar(
    timestamp: datetime,
    open_price: float,
    high: float,
    low: float,
    close: float,
    timeframe: str,
) -> dict[str, object]:
    return {
        "timestamp": timestamp,
        "trade_date": timestamp.date().isoformat(),
        "timeframe": timeframe,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "spread_points": 0.5,
    }
