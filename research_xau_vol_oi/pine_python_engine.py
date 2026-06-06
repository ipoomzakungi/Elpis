"""Pine-to-Python indicator engine and Yahoo OHLC backtest lab.

This module is research-only. It builds a Pine-like strategy candidate from
Yahoo-style OHLC data, then evaluates conservative price/CME/guru filters with
timestamp-safe joins. The goal is a reproducible Python research baseline, not
TradingView parity on the first pass and not an execution system.
"""

from __future__ import annotations

import argparse
import html
import math
import os
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from statistics import median
from typing import Any, Sequence

import polars as pl

from research_xau_vol_oi.pine_strategy_overlay_lab import (
    BASELINE_REPORT_VALUES,
)


FORBIDDEN_REPORT_PHRASES = (
    "profitable",
    "safe to trade",
    "live ready",
    "live-ready",
    "paper ready",
    "paper-ready",
    "real-money ready",
    "broker integration ready",
)
SUPPORTED_SYMBOLS = ("GC=F", "XAUUSD=X", "XAUUSD", "GLD")
SUPPORTED_INTERVALS = ("1m", "5m", "15m", "30m", "60m", "1h", "4h", "1d")
DIRECT_INTERVALS = ("1m", "5m", "15m", "30m", "60m", "1h", "1d")
LOCAL_OHLC_CANDIDATES = (
    "xau_feature_table.parquet",
    "cme_canonical_xau_spot_price.parquet",
    "cme_canonical_futures_price.parquet",
    "xau_spot_backfilled.parquet",
)


@dataclass(frozen=True)
class PinePythonEngineConfig:
    """Conservative defaults for the Python Pine-like research candidate."""

    start: str | None = None
    end: str | None = None
    symbol: str = "GC=F"
    interval: str = "15m"
    enable_yahoo_intraday_fetch: bool = False
    grid_sd_len: int = 50
    entry_sd: float = 1.25
    stop_sd: float = 2.25
    no_trade_sd: float = 0.50
    donchian_len: int = 20
    atr_len: int = 14
    ema_fast_len: int = 21
    ema_slow_len: int = 55
    cci_len: int = 20
    stochastic_len: int = 14
    max_hold_bars: int = 12
    commission_rate: float = 0.0005
    slippage_points: float = 1.0
    open_distance_limit_points: float = 25.0
    fee_buffer_points: float = 0.25
    min_warmup_bars: int = 80

    @classmethod
    def from_env(cls) -> PinePythonEngineConfig:
        """Build config from environment without fetching by default."""

        fetch_flag = os.getenv("XAU_ENABLE_YAHOO_INTRADAY_FETCH", "false").strip().lower()
        return cls(
            start=os.getenv("XAU_BACKTEST_START") or None,
            end=os.getenv("XAU_BACKTEST_END") or None,
            symbol=os.getenv("XAU_BACKTEST_SYMBOL") or "GC=F",
            interval=os.getenv("XAU_BACKTEST_INTERVAL") or "15m",
            enable_yahoo_intraday_fetch=fetch_flag in {"1", "true", "yes", "y"},
        )


@dataclass(frozen=True)
class PinePythonEngineResult:
    """Generated frames and labels for the Python engine lab."""

    yahoo_ohlc_inventory: pl.DataFrame
    ohlc: pl.DataFrame
    indicator_snapshot: pl.DataFrame
    signals: pl.DataFrame
    backtest_trades: pl.DataFrame
    backtest_summary: pl.DataFrame
    overlay_trades: pl.DataFrame
    overlay_summary: pl.DataFrame
    parity: pl.DataFrame
    fast_use_decision: pl.DataFrame
    yahoo_data_coverage: str
    final_label: str


def run_pine_python_engine_lab(
    *,
    output_dir: str | Path = "outputs",
    config: PinePythonEngineConfig | None = None,
    pine_path: str | Path | None = "Tradingview.pine",
) -> PinePythonEngineResult:
    """Run the Yahoo/Pine-like Python lab and write all requested artifacts."""

    output_root = Path(output_dir)
    charts_dir = output_root / "charts"
    output_root.mkdir(parents=True, exist_ok=True)
    charts_dir.mkdir(parents=True, exist_ok=True)

    cfg = config or PinePythonEngineConfig.from_env()
    inventory, ohlc = build_yahoo_ohlc_inventory(output_root=output_root, config=cfg)
    if ohlc.is_empty():
        write_yahoo_data_request(output_root / "yahoo_ohlc_data_request.md", cfg)

    indicators = build_indicator_snapshot(ohlc, config=cfg)
    signals = build_pine_like_signals(ohlc, config=cfg)
    trades, summary = run_python_backtest(ohlc, signals, config=cfg)
    overlay_trades, overlay_summary = apply_cme_guru_overlay(
        trades,
        signals,
        output_root=output_root,
        config=cfg,
    )
    parity = tradingview_parity_report(
        summary,
        output_root=output_root,
        pine_path=Path(pine_path) if pine_path is not None else None,
    )
    fast_use = build_fast_use_decision(summary, overlay_summary, parity)
    final_label = _final_label(fast_use)
    result = PinePythonEngineResult(
        yahoo_ohlc_inventory=inventory,
        ohlc=ohlc,
        indicator_snapshot=indicators,
        signals=signals,
        backtest_trades=trades,
        backtest_summary=summary,
        overlay_trades=overlay_trades,
        overlay_summary=overlay_summary,
        parity=parity,
        fast_use_decision=fast_use,
        yahoo_data_coverage=_coverage_label(inventory, ohlc),
        final_label=final_label,
    )
    write_engine_outputs(output_root=output_root, charts_dir=charts_dir, result=result, config=cfg)
    return result


# ---------------------------------------------------------------------------
# Yahoo OHLC adapter


def build_yahoo_ohlc_inventory(
    *,
    output_root: Path,
    config: PinePythonEngineConfig,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Discover local Yahoo-style OHLC and select the configured research frame."""

    discovered = load_local_yahoo_frames(output_root)
    if config.enable_yahoo_intraday_fetch:
        fetched = fetch_yahoo_ohlc_if_enabled(config)
        if not fetched.is_empty():
            discovered.append(fetched)

    inventory_rows: list[dict[str, Any]] = []
    for frame in discovered:
        if frame.is_empty():
            continue
        for raw in frame.group_by(["symbol", "interval", "source", "quality"]).agg(
            pl.len().alias("rows"),
            pl.col("timestamp").min().alias("start"),
            pl.col("timestamp").max().alias("end"),
        ).to_dicts():
            inventory_rows.append(
                {
                    "symbol": raw["symbol"],
                    "interval": raw["interval"],
                    "rows": raw["rows"],
                    "start": _timestamp_text(raw["start"]),
                    "end": _timestamp_text(raw["end"]),
                    "source": raw["source"],
                    "quality": raw["quality"],
                    "available": True,
                    "note": _quality_note(str(raw["quality"])),
                }
            )
    inventory_rows.extend(_missing_inventory_rows(inventory_rows))
    inventory = _rows_frame(inventory_rows, _inventory_schema())

    selected = select_ohlc_frame(discovered, config=config)
    return inventory, selected


def load_local_yahoo_frames(output_root: Path) -> list[pl.DataFrame]:
    """Load known local OHLC artifacts and canonicalize them."""

    frames: list[pl.DataFrame] = []
    for name in LOCAL_OHLC_CANDIDATES:
        path = output_root / name
        raw = _load_optional(path)
        if raw.is_empty():
            continue
        interval = infer_interval(raw)
        source = "LOCAL_YAHOO_OHLC"
        if name.startswith("cme_canonical"):
            source = "LOCAL_CANONICAL_OHLC"
        frame = canonicalize_yahoo_ohlc(
            raw,
            symbol=None,
            interval=interval,
            source=source,
            quality=None,
        )
        if not frame.is_empty():
            frames.append(frame)

    for path in _glob_yahoo_ohlc_files():
        if path.parent == output_root and path.name in LOCAL_OHLC_CANDIDATES:
            continue
        raw = _load_optional(path)
        if raw.is_empty():
            continue
        frame = canonicalize_yahoo_ohlc(
            raw,
            symbol=None,
            interval=infer_interval(raw),
            source="LOCAL_YAHOO_OHLC",
            quality=None,
        )
        if not frame.is_empty():
            frames.append(frame)
    return frames


def canonicalize_yahoo_ohlc(
    frame: pl.DataFrame,
    *,
    symbol: str | None,
    interval: str,
    source: str,
    quality: str | None = "DIRECT_YAHOO",
) -> pl.DataFrame:
    """Return the canonical Yahoo OHLC schema."""

    if frame.is_empty():
        return _empty_ohlc()
    rows: list[dict[str, Any]] = []
    columns = {_normal_column(column): column for column in frame.columns}
    for raw in frame.to_dicts():
        timestamp = _timestamp_value(_get_first(raw, columns, ("timestamp", "datetime", "date", "time")))
        if timestamp is None:
            timestamp = _timestamp_value(_get_first(raw, columns, ("trade_date", "session_date")))
        open_price = _float_or_none(_get_first(raw, columns, ("open",)))
        high = _float_or_none(_get_first(raw, columns, ("high",)))
        low = _float_or_none(_get_first(raw, columns, ("low",)))
        close = _float_or_none(_get_first(raw, columns, ("close", "adj_close", "last", "price")))
        if timestamp is None or close is None:
            continue
        row_symbol = str(_get_first(raw, columns, ("symbol", "ticker")) or symbol or "GC=F")
        if row_symbol == "XAUUSD":
            row_symbol = "XAUUSD=X"
        row_quality = quality or ("PROXY_ONLY" if row_symbol == "GLD" else "DIRECT_YAHOO")
        if row_symbol == "GLD":
            row_quality = "PROXY_ONLY"
        rows.append(
            {
                "timestamp": timestamp,
                "symbol": row_symbol,
                "interval": _normal_interval(interval),
                "open": open_price if open_price is not None else close,
                "high": high if high is not None else close,
                "low": low if low is not None else close,
                "close": close,
                "volume": _float_or_none(_get_first(raw, columns, ("volume",))) or 0.0,
                "source": source,
                "quality": row_quality,
            }
        )
    return _rows_frame(rows, _ohlc_schema()).sort(["symbol", "timestamp"])


def select_ohlc_frame(
    frames: list[pl.DataFrame],
    *,
    config: PinePythonEngineConfig,
) -> pl.DataFrame:
    """Select or resample the configured symbol/interval frame."""

    if not frames:
        return _empty_ohlc()
    combined = pl.concat(frames, how="vertical_relaxed").unique(
        subset=["timestamp", "symbol", "interval"],
        keep="first",
    )
    symbol_choices = _symbol_priority(config.symbol)
    interval = _normal_interval(config.interval)
    filtered = _filter_date_range(combined, config)
    for symbol in symbol_choices:
        direct = filtered.filter((pl.col("symbol") == symbol) & (pl.col("interval") == interval))
        if not direct.is_empty():
            return direct.sort("timestamp")

    if interval in {"30m", "1h", "4h", "1d"}:
        for symbol in symbol_choices:
            for source_interval in _resample_source_intervals(interval):
                source = filtered.filter(
                    (pl.col("symbol") == symbol) & (pl.col("interval") == source_interval)
                )
                if not source.is_empty():
                    return resample_ohlc(source, target_interval=interval, source_interval=source_interval)
    for symbol in symbol_choices:
        fallback = filtered.filter(pl.col("symbol") == symbol)
        if not fallback.is_empty():
            return fallback.sort("timestamp")
    return filtered.sort("timestamp")


def resample_ohlc(
    frame: pl.DataFrame,
    *,
    target_interval: str,
    source_interval: str | None = None,
) -> pl.DataFrame:
    """Resample closed OHLC bars and timestamp the output at bucket close."""

    if frame.is_empty():
        return _empty_ohlc()
    target = _normal_interval(target_interval)
    minutes = _interval_minutes(target)
    if minutes is None:
        raise ValueError(f"Unsupported target interval: {target_interval}")
    source = _normal_interval(source_interval or _frame_interval(frame))
    quality = _resampled_quality(target, source)
    rows: list[dict[str, Any]] = []
    grouped: dict[tuple[str, datetime], list[dict[str, Any]]] = {}
    for raw in frame.sort("timestamp").to_dicts():
        ts = _timestamp_value(raw.get("timestamp"))
        if ts is None:
            continue
        bucket = _bucket_start(ts, minutes)
        grouped.setdefault((str(raw.get("symbol") or "GC=F"), bucket), []).append(raw)
    for (symbol, bucket_start), bucket_rows in sorted(grouped.items(), key=lambda item: item[0]):
        if not bucket_rows:
            continue
        timestamp = bucket_start + timedelta(minutes=minutes)
        rows.append(
            {
                "timestamp": timestamp,
                "symbol": symbol,
                "interval": target,
                "open": _float_or_zero(bucket_rows[0].get("open")),
                "high": max(_float_or_zero(row.get("high")) for row in bucket_rows),
                "low": min(_float_or_zero(row.get("low")) for row in bucket_rows),
                "close": _float_or_zero(bucket_rows[-1].get("close")),
                "volume": sum(_float_or_zero(row.get("volume")) for row in bucket_rows),
                "source": f"RESAMPLED_{source.upper()}",
                "quality": "PROXY_ONLY" if symbol == "GLD" else quality,
            }
        )
    return _rows_frame(rows, _ohlc_schema()).sort(["symbol", "timestamp"])


def fetch_yahoo_ohlc_if_enabled(config: PinePythonEngineConfig) -> pl.DataFrame:
    """Optionally fetch Yahoo OHLC only when the environment explicitly enables it."""

    if not config.enable_yahoo_intraday_fetch:
        return _empty_ohlc()
    try:
        import yfinance as yf  # type: ignore[import-not-found]
    except Exception:
        return _empty_ohlc()
    try:
        ticker = yf.Ticker(config.symbol)
        raw = ticker.history(
            start=config.start,
            end=config.end,
            interval=_yahoo_interval(config.interval),
            auto_adjust=False,
        )
    except Exception:
        return _empty_ohlc()
    if raw is None or raw.empty:
        return _empty_ohlc()
    raw = raw.reset_index()
    return canonicalize_yahoo_ohlc(
        pl.from_pandas(raw),
        symbol=config.symbol,
        interval=config.interval,
        source="YFINANCE_FETCH",
        quality="DIRECT_YAHOO" if config.symbol != "GLD" else "PROXY_ONLY",
    )


# ---------------------------------------------------------------------------
# Indicator library


def ema(values: Sequence[float | None], length: int) -> list[float | None]:
    """Exponential moving average using only current and prior values."""

    if length <= 0:
        raise ValueError("length must be positive")
    alpha = 2.0 / (length + 1.0)
    output: list[float | None] = []
    previous: float | None = None
    for value in values:
        numeric = _float_or_none(value)
        if numeric is None:
            output.append(previous)
            continue
        previous = numeric if previous is None else alpha * numeric + (1.0 - alpha) * previous
        output.append(previous)
    return output


def sma(values: Sequence[float | None], length: int) -> list[float | None]:
    """Simple moving average with warmup NaNs represented as None."""

    output: list[float | None] = []
    for index in range(len(values)):
        window = [_float_or_none(value) for value in values[max(0, index - length + 1) : index + 1]]
        if len(window) < length or any(value is None for value in window):
            output.append(None)
        else:
            output.append(sum(value for value in window if value is not None) / length)
    return output


def stdev(values: Sequence[float | None], length: int) -> list[float | None]:
    """Rolling population standard deviation without lookahead."""

    output: list[float | None] = []
    for index in range(len(values)):
        window = [_float_or_none(value) for value in values[max(0, index - length + 1) : index + 1]]
        if len(window) < length or any(value is None for value in window):
            output.append(None)
            continue
        clean = [value for value in window if value is not None]
        mean_value = sum(clean) / length
        output.append(math.sqrt(sum((value - mean_value) ** 2 for value in clean) / length))
    return output


def zscore(values: Sequence[float | None], length: int) -> list[float | None]:
    """Rolling z-score using the current closed bar and prior bars only."""

    means = sma(values, length)
    deviations = stdev(values, length)
    output: list[float | None] = []
    for value, mean_value, deviation in zip(values, means, deviations, strict=False):
        numeric = _float_or_none(value)
        if numeric is None or mean_value is None or deviation in {None, 0.0}:
            output.append(None)
        else:
            output.append((numeric - mean_value) / deviation)
    return output


def atr(
    high: Sequence[float | None],
    low: Sequence[float | None],
    close: Sequence[float | None],
    length: int = 14,
) -> list[float | None]:
    """Average true range using previous close for each true-range row."""

    true_ranges: list[float | None] = []
    for index, (high_value, low_value, close_value) in enumerate(
        zip(high, low, close, strict=False)
    ):
        h = _float_or_none(high_value)
        lo = _float_or_none(low_value)
        c = _float_or_none(close_value)
        if h is None or lo is None or c is None:
            true_ranges.append(None)
            continue
        if index == 0:
            true_ranges.append(h - lo)
            continue
        previous_close = _float_or_none(close[index - 1])
        if previous_close is None:
            true_ranges.append(h - lo)
        else:
            true_ranges.append(max(h - lo, abs(h - previous_close), abs(lo - previous_close)))
    return sma(true_ranges, length)


def donchian_high_low(
    high: Sequence[float | None],
    low: Sequence[float | None],
    length: int = 20,
) -> tuple[list[float | None], list[float | None]]:
    """Rolling Donchian high/low including the current closed bar."""

    highs: list[float | None] = []
    lows: list[float | None] = []
    for index in range(len(high)):
        high_window = [_float_or_none(value) for value in high[max(0, index - length + 1) : index + 1]]
        low_window = [_float_or_none(value) for value in low[max(0, index - length + 1) : index + 1]]
        if len(high_window) < length or any(value is None for value in high_window + low_window):
            highs.append(None)
            lows.append(None)
        else:
            highs.append(max(value for value in high_window if value is not None))
            lows.append(min(value for value in low_window if value is not None))
    return highs, lows


def rsi(values: Sequence[float | None], length: int = 14) -> list[float | None]:
    """Wilder RSI with timestamp-safe warmup."""

    output: list[float | None] = [None] * len(values)
    if len(values) <= length:
        return output
    gains: list[float] = []
    losses: list[float] = []
    for index in range(1, length + 1):
        previous = _float_or_none(values[index - 1])
        current = _float_or_none(values[index])
        if previous is None or current is None:
            return output
        change = current - previous
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    average_gain = sum(gains) / length
    average_loss = sum(losses) / length
    output[length] = _rsi_value(average_gain, average_loss)
    for index in range(length + 1, len(values)):
        previous = _float_or_none(values[index - 1])
        current = _float_or_none(values[index])
        if previous is None or current is None:
            output[index] = output[index - 1]
            continue
        change = current - previous
        gain = max(change, 0.0)
        loss = max(-change, 0.0)
        average_gain = (average_gain * (length - 1) + gain) / length
        average_loss = (average_loss * (length - 1) + loss) / length
        output[index] = _rsi_value(average_gain, average_loss)
    return output


def macd(
    values: Sequence[float | None],
    *,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """MACD line, signal line, and histogram with no future rows."""

    fast_ema = ema(values, fast)
    slow_ema = ema(values, slow)
    line: list[float | None] = []
    for fast_value, slow_value in zip(fast_ema, slow_ema, strict=False):
        if fast_value is None or slow_value is None:
            line.append(None)
        else:
            line.append(fast_value - slow_value)
    signal_line = ema(line, signal)
    histogram = [
        None if line_value is None or signal_value is None else line_value - signal_value
        for line_value, signal_value in zip(line, signal_line, strict=False)
    ]
    return line, signal_line, histogram


def stochastic(
    high: Sequence[float | None],
    low: Sequence[float | None],
    close: Sequence[float | None],
    *,
    length: int = 14,
    smooth: int = 3,
) -> tuple[list[float | None], list[float | None]]:
    """Stochastic %K/%D using closed bars only."""

    k_values: list[float | None] = []
    for index in range(len(close)):
        high_window = [_float_or_none(value) for value in high[max(0, index - length + 1) : index + 1]]
        low_window = [_float_or_none(value) for value in low[max(0, index - length + 1) : index + 1]]
        current = _float_or_none(close[index])
        if len(high_window) < length or current is None or any(
            value is None for value in high_window + low_window
        ):
            k_values.append(None)
            continue
        highest = max(value for value in high_window if value is not None)
        lowest = min(value for value in low_window if value is not None)
        if highest == lowest:
            k_values.append(50.0)
        else:
            k_values.append(100.0 * (current - lowest) / (highest - lowest))
    return k_values, sma(k_values, smooth)


def cci(
    high: Sequence[float | None],
    low: Sequence[float | None],
    close: Sequence[float | None],
    *,
    length: int = 20,
) -> list[float | None]:
    """Commodity Channel Index using typical price and rolling mean deviation."""

    typical = [
        None
        if _float_or_none(high_value) is None
        or _float_or_none(low_value) is None
        or _float_or_none(close_value) is None
        else (
            _float_or_none(high_value)
            + _float_or_none(low_value)
            + _float_or_none(close_value)
        )
        / 3.0
        for high_value, low_value, close_value in zip(high, low, close, strict=False)
    ]
    means = sma(typical, length)
    output: list[float | None] = []
    for index, (typical_value, mean_value) in enumerate(zip(typical, means, strict=False)):
        if typical_value is None or mean_value is None:
            output.append(None)
            continue
        window = [
            _float_or_none(value)
            for value in typical[max(0, index - length + 1) : index + 1]
        ]
        if len(window) < length or any(value is None for value in window):
            output.append(None)
            continue
        mean_dev = sum(abs(value - mean_value) for value in window if value is not None) / length
        output.append(0.0 if mean_dev == 0 else (typical_value - mean_value) / (0.015 * mean_dev))
    return output


def parabolic_sar(
    high: Sequence[float | None],
    low: Sequence[float | None],
    *,
    step: float = 0.02,
    maximum: float = 0.2,
) -> list[float | None]:
    """Simple Parabolic SAR approximation suitable for first-pass research."""

    if not high or not low:
        return []
    output: list[float | None] = [None] * len(high)
    initial_high = _float_or_none(high[0])
    initial_low = _float_or_none(low[0])
    if initial_high is None or initial_low is None:
        return output
    long_trend = True
    sar = initial_low
    extreme = initial_high
    acceleration = step
    output[0] = sar
    for index in range(1, len(high)):
        h = _float_or_none(high[index])
        lo = _float_or_none(low[index])
        if h is None or lo is None:
            output[index] = output[index - 1]
            continue
        sar = sar + acceleration * (extreme - sar)
        if long_trend:
            if lo < sar:
                long_trend = False
                sar = extreme
                extreme = lo
                acceleration = step
            elif h > extreme:
                extreme = h
                acceleration = min(acceleration + step, maximum)
        else:
            if h > sar:
                long_trend = True
                sar = extreme
                extreme = h
                acceleration = step
            elif lo < extreme:
                extreme = lo
                acceleration = min(acceleration + step, maximum)
        output[index] = sar
    return output


def envelope_bands(
    values: Sequence[float | None],
    *,
    length: int = 20,
    percent: float = 0.01,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """SMA envelope bands."""

    middle = sma(values, length)
    upper = [None if value is None else value * (1.0 + percent) for value in middle]
    lower = [None if value is None else value * (1.0 - percent) for value in middle]
    return middle, upper, lower


def standard_deviation_bands(
    values: Sequence[float | None],
    *,
    length: int = 20,
    multiplier: float = 2.0,
) -> tuple[list[float | None], list[float | None], list[float | None], list[float | None]]:
    """Rolling mean plus/minus standard deviation bands."""

    middle = sma(values, length)
    deviations = stdev(values, length)
    upper = [
        None if mean_value is None or deviation is None else mean_value + multiplier * deviation
        for mean_value, deviation in zip(middle, deviations, strict=False)
    ]
    lower = [
        None if mean_value is None or deviation is None else mean_value - multiplier * deviation
        for mean_value, deviation in zip(middle, deviations, strict=False)
    ]
    return middle, upper, lower, deviations


def session_open_distance(frame: pl.DataFrame) -> list[float | None]:
    """Distance from each bar close to its session open."""

    if frame.is_empty():
        return []
    opens_by_date: dict[str, float] = {}
    output: list[float | None] = []
    for raw in frame.sort("timestamp").to_dicts():
        ts = _timestamp_value(raw.get("timestamp"))
        close = _float_or_none(raw.get("close"))
        open_price = _float_or_none(raw.get("open"))
        if ts is None or close is None:
            output.append(None)
            continue
        key = ts.date().isoformat()
        if key not in opens_by_date and open_price is not None:
            opens_by_date[key] = open_price
        session_open = opens_by_date.get(key)
        output.append(None if session_open is None else close - session_open)
    return output


def realized_volatility(values: Sequence[float | None], *, length: int = 20) -> list[float | None]:
    """Rolling realized volatility from log returns."""

    returns: list[float | None] = [None]
    for previous, current in zip(values[:-1], values[1:], strict=False):
        prev = _float_or_none(previous)
        curr = _float_or_none(current)
        if prev is None or curr is None or prev <= 0 or curr <= 0:
            returns.append(None)
        else:
            returns.append(math.log(curr / prev))
    deviations = stdev(returns, length)
    return [None if value is None else value * math.sqrt(length) for value in deviations]


def range_regime(
    high: Sequence[float | None],
    low: Sequence[float | None],
    close: Sequence[float | None],
    *,
    length: int = 20,
) -> list[str]:
    """Classify range expansion/compression from ATR versus rolling ATR mean."""

    atr_values = atr(high, low, close, length=length)
    atr_mean = sma(atr_values, length)
    output: list[str] = []
    for current, mean_value in zip(atr_values, atr_mean, strict=False):
        if current is None or mean_value in {None, 0.0}:
            output.append("UNKNOWN")
        elif current > mean_value * 1.15:
            output.append("EXPANDING")
        elif current < mean_value * 0.85:
            output.append("COMPRESSED")
        else:
            output.append("NORMAL")
    return output


def acceptance_breakout(
    close: Sequence[float | None],
    level: Sequence[float | None] | float,
    *,
    buffer: float = 0.0,
    hold_bars: int = 2,
    direction: str = "UP",
) -> list[bool]:
    """Return True after price accepts beyond a level for closed bars."""

    levels = _expand_level(level, len(close))
    output: list[bool] = []
    for index in range(len(close)):
        if index + 1 < hold_bars:
            output.append(False)
            continue
        accepted = True
        for offset in range(hold_bars):
            current = _float_or_none(close[index - offset])
            level_value = _float_or_none(levels[index - offset])
            if current is None or level_value is None:
                accepted = False
                break
            if direction.upper() in {"UP", "LONG"}:
                accepted = accepted and current > level_value + buffer
            else:
                accepted = accepted and current < level_value - buffer
        output.append(accepted)
    return output


def rejection_after_touch(
    high: Sequence[float | None],
    low: Sequence[float | None],
    close: Sequence[float | None],
    level: Sequence[float | None] | float,
    *,
    direction: str = "LONG",
    buffer: float = 0.0,
) -> list[bool]:
    """Return True when a level is touched and the closed bar rejects it."""

    levels = _expand_level(level, len(close))
    output: list[bool] = []
    for h, lo, current, level_value in zip(high, low, close, levels, strict=False):
        high_value = _float_or_none(h)
        low_value = _float_or_none(lo)
        close_value = _float_or_none(current)
        lvl = _float_or_none(level_value)
        if high_value is None or low_value is None or close_value is None or lvl is None:
            output.append(False)
            continue
        if direction.upper() in {"LONG", "UP", "SUPPORT"}:
            output.append(low_value <= lvl + buffer and close_value > lvl + buffer)
        else:
            output.append(high_value >= lvl - buffer and close_value < lvl - buffer)
    return output


def no_trade_middle_range(
    sd_position: Sequence[float | None],
    *,
    no_trade_sd: float = 0.50,
) -> list[bool]:
    """Middle-range no-trade zone from absolute SD position."""

    return [
        False if _float_or_none(value) is None else abs(_float_or_none(value) or 0.0) <= no_trade_sd
        for value in sd_position
    ]


# ---------------------------------------------------------------------------
# Pine-like signal and backtest engine


def build_indicator_snapshot(
    ohlc: pl.DataFrame,
    *,
    config: PinePythonEngineConfig,
) -> pl.DataFrame:
    """Create an indicator snapshot for the selected OHLC frame."""

    signals = build_pine_like_signals(ohlc, config=config)
    if signals.is_empty():
        return _rows_frame(
            [
                {
                    "timestamp": None,
                    "symbol": config.symbol,
                    "interval": config.interval,
                    "close": None,
                    "ema_fast": None,
                    "ema_slow": None,
                    "rsi": None,
                    "macd_line": None,
                    "macd_signal": None,
                    "macd_hist": None,
                    "stoch_k": None,
                    "stoch_d": None,
                    "cci": None,
                    "atr": None,
                    "donchian_high": None,
                    "donchian_low": None,
                    "sd_mid": None,
                    "sd_upper": None,
                    "sd_lower": None,
                    "sd_position": None,
                    "session_open_distance": None,
                    "realized_volatility": None,
                    "range_state": "NO_DATA",
                    "parabolic_sar": None,
                    "lookahead_safe": True,
                }
            ],
            _indicator_snapshot_schema(),
        )
    columns = [column for column in _indicator_snapshot_schema() if column in signals.columns]
    rows = signals.select(columns).tail(20).to_dicts()
    for row in rows:
        row["lookahead_safe"] = True
    return _rows_frame(rows, _indicator_snapshot_schema())


def build_pine_like_signals(
    ohlc: pl.DataFrame,
    *,
    config: PinePythonEngineConfig | None = None,
) -> pl.DataFrame:
    """Recreate a simplified Pine dashboard/grid strategy candidate in Python."""

    cfg = config or PinePythonEngineConfig()
    price = _prepare_ohlc_for_engine(ohlc)
    if price.is_empty():
        return _empty_signals()
    rows = price.to_dicts()
    close = [_float_or_none(row.get("close")) for row in rows]
    high = [_float_or_none(row.get("high")) for row in rows]
    low = [_float_or_none(row.get("low")) for row in rows]

    ema_fast = ema(close, cfg.ema_fast_len)
    ema_slow = ema(close, cfg.ema_slow_len)
    rsi_values = rsi(close, 14)
    macd_line, macd_signal, macd_hist = macd(close)
    stoch_k, stoch_d = stochastic(high, low, close, length=cfg.stochastic_len)
    cci_values = cci(high, low, close, length=cfg.cci_len)
    atr_values = atr(high, low, close, length=cfg.atr_len)
    don_high, don_low = donchian_high_low(high, low, length=cfg.donchian_len)
    sd_mid, sd_upper, sd_lower, sd_std = standard_deviation_bands(
        close,
        length=cfg.grid_sd_len,
        multiplier=cfg.entry_sd,
    )
    sd_position = zscore(close, cfg.grid_sd_len)
    range_states = range_regime(high, low, close, length=cfg.donchian_len)
    rv_values = realized_volatility(close, length=20)
    sar_values = parabolic_sar(high, low)
    env_mid, env_upper, env_lower = envelope_bands(close, length=20, percent=0.01)
    open_distance = session_open_distance(price)
    no_trade = no_trade_middle_range(sd_position, no_trade_sd=cfg.no_trade_sd)

    previous_don_high = _shift(don_high, 1)
    previous_don_low = _shift(don_low, 1)
    accept_up = acceptance_breakout(close, previous_don_high, buffer=0.0, hold_bars=1, direction="UP")
    accept_down = acceptance_breakout(close, previous_don_low, buffer=0.0, hold_bars=1, direction="DOWN")
    reject_long = rejection_after_touch(high, low, close, sd_lower, direction="LONG")
    reject_short = rejection_after_touch(high, low, close, sd_upper, direction="SHORT")

    output: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        trend_score = _trend_score(
            ema_fast[index],
            ema_slow[index],
            macd_hist[index],
            close[index],
            env_mid[index],
        )
        momentum_score = _momentum_score(rsi_values[index], stoch_k[index], stoch_d[index], cci_values[index])
        volatility_score = _volatility_score(sd_position[index], atr_values[index], range_states[index])
        direction, raw_signal, reason = _direction_candidate(
            index=index,
            config=cfg,
            trend_score=trend_score,
            momentum_score=momentum_score,
            sd_position=sd_position[index],
            no_trade=no_trade[index],
            acceptance_up=accept_up[index],
            acceptance_down=accept_down[index],
            reject_long=reject_long[index],
            reject_short=reject_short[index],
        )
        output.append(
            {
                "timestamp": row["timestamp"],
                "symbol": row["symbol"],
                "interval": row["interval"],
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "volume": row["volume"],
                "pine_like_score": trend_score + momentum_score + volatility_score,
                "trend_score": trend_score,
                "momentum_score": momentum_score,
                "volatility_score": volatility_score,
                "range_state": range_states[index],
                "sd_position": sd_position[index],
                "no_trade_middle_range": no_trade[index],
                "acceptance_breakout": accept_up[index] or accept_down[index],
                "acceptance_breakdown": accept_down[index],
                "rejection_after_level_touch": reject_long[index] or reject_short[index],
                "direction_candidate": direction,
                "raw_signal": raw_signal,
                "reason": reason,
                "ema_fast": ema_fast[index],
                "ema_slow": ema_slow[index],
                "rsi": rsi_values[index],
                "macd_line": macd_line[index],
                "macd_signal": macd_signal[index],
                "macd_hist": macd_hist[index],
                "stoch_k": stoch_k[index],
                "stoch_d": stoch_d[index],
                "cci": cci_values[index],
                "atr": atr_values[index],
                "donchian_high": don_high[index],
                "donchian_low": don_low[index],
                "sd_mid": sd_mid[index],
                "sd_upper": sd_upper[index],
                "sd_lower": sd_lower[index],
                "sd_std": sd_std[index],
                "env_mid": env_mid[index],
                "env_upper": env_upper[index],
                "env_lower": env_lower[index],
                "session_open_distance": open_distance[index],
                "realized_volatility": rv_values[index],
                "parabolic_sar": sar_values[index],
            }
        )
    return _rows_frame(output, _signals_schema())


def run_python_backtest(
    ohlc: pl.DataFrame,
    signals: pl.DataFrame,
    *,
    config: PinePythonEngineConfig | None = None,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Backtest Pine-like candidates with bar-close execution only."""

    cfg = config or PinePythonEngineConfig()
    if ohlc.is_empty() or signals.is_empty():
        trades = _empty_trades()
        return trades, summarize_backtest(trades, config=cfg, data_mode="NO_DATA")

    price = _prepare_ohlc_for_engine(ohlc).to_dicts()
    signal_rows = signals.sort("timestamp").to_dicts()
    signal_by_timestamp = {_timestamp_text(row["timestamp"]): row for row in signal_rows}
    price_index_by_timestamp = {_timestamp_text(row["timestamp"]): index for index, row in enumerate(price)}

    trades: list[dict[str, Any]] = []
    next_allowed_index = 0
    trade_id = 1
    for signal in signal_rows:
        direction = str(signal.get("direction_candidate") or "NONE")
        if direction not in {"LONG", "SHORT"}:
            continue
        signal_index = price_index_by_timestamp.get(_timestamp_text(signal.get("timestamp")))
        if signal_index is None or signal_index < cfg.min_warmup_bars or signal_index < next_allowed_index:
            continue
        entry_index = signal_index + 1
        if entry_index >= len(price):
            continue
        trade = _simulate_trade(
            trade_id=trade_id,
            direction=direction,
            signal=signal,
            signal_index=signal_index,
            entry_index=entry_index,
            price_rows=price,
            signal_by_timestamp=signal_by_timestamp,
            config=cfg,
        )
        if trade is None:
            continue
        trades.append(trade)
        trade_id += 1
        next_allowed_index = int(trade["exit_bar_index"]) + 1
    trade_frame = _rows_frame(trades, _trades_schema())
    return trade_frame, summarize_backtest(trade_frame, config=cfg, data_mode="PYTHON_PINE_LIKE")


def summarize_backtest(
    trades: pl.DataFrame,
    *,
    config: PinePythonEngineConfig,
    data_mode: str,
) -> pl.DataFrame:
    """Summarize backtest metrics after commission and slippage."""

    rows = trades.to_dicts() if not trades.is_empty() else []
    pnl = [_float_or_zero(row.get("pnl_after_cost")) for row in rows]
    wins = [value for value in pnl if value > 0]
    losses = [value for value in pnl if value < 0]
    gross_wins = sum(wins)
    gross_losses = abs(sum(losses))
    long_pnl = sum(
        _float_or_zero(row.get("pnl_after_cost")) for row in rows if row.get("direction") == "LONG"
    )
    short_pnl = sum(
        _float_or_zero(row.get("pnl_after_cost")) for row in rows if row.get("direction") == "SHORT"
    )
    cumulative = _cumulative(pnl)
    summary_rows = [
        {
            "strategy": "python_pine_like",
            "data_mode": data_mode,
            "symbol": rows[0].get("symbol") if rows else config.symbol,
            "interval": rows[0].get("interval") if rows else config.interval,
            "trade_count": len(rows),
            "win_rate": len(wins) / len(rows) if rows else 0.0,
            "avg_win": sum(wins) / len(wins) if wins else 0.0,
            "avg_loss": sum(losses) / len(losses) if losses else 0.0,
            "avg_pnl": sum(pnl) / len(pnl) if pnl else 0.0,
            "expectancy": sum(pnl) / len(pnl) if pnl else 0.0,
            "profit_factor": gross_wins / gross_losses if gross_losses else None,
            "max_drawdown": _max_drawdown(cumulative),
            "sharpe_proxy": _sharpe_proxy(pnl),
            "commission_paid": sum(_float_or_zero(row.get("commission_paid")) for row in rows),
            "long_pnl": long_pnl,
            "short_pnl": short_pnl,
            "long_trade_count": sum(1 for row in rows if row.get("direction") == "LONG"),
            "short_trade_count": sum(1 for row in rows if row.get("direction") == "SHORT"),
            "average_hold_bars": sum(int(row.get("bars_in_trade") or 0) for row in rows) / len(rows)
            if rows
            else 0.0,
            "outlier_loss_count": _outlier_loss_count(pnl),
            "sample_size_warning": len(rows) < 30,
            "research_only": True,
        }
    ]
    return _rows_frame(summary_rows, _backtest_summary_schema())


# ---------------------------------------------------------------------------
# CME/guru overlay


def apply_cme_guru_overlay(
    trades: pl.DataFrame,
    signals: pl.DataFrame,
    *,
    output_root: Path,
    config: PinePythonEngineConfig | None = None,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Apply price-only, CME, guru, and combined conservative filters."""

    cfg = config or PinePythonEngineConfig()
    if trades.is_empty():
        empty = _empty_overlay_trades()
        return empty, summarize_overlay(empty)
    cme_by_date = _rows_by_date(_load_optional(output_root / "current_week_cme_guru_replay.csv"), "trade_date")
    guru_by_date = _rows_by_date(
        _load_optional(output_root / "same_day_filter_evidence_after_metadata.csv"),
        "resolved_market_session_date",
    )
    signal_by_timestamp = {
        _timestamp_text(row.get("timestamp")): row for row in signals.to_dicts()
    } if not signals.is_empty() else {}
    rows: list[dict[str, Any]] = []
    for trade in trades.to_dicts():
        signal = signal_by_timestamp.get(_timestamp_text(trade.get("signal_timestamp")), {})
        session_date = _date_text(trade.get("signal_timestamp") or trade.get("entry_timestamp"))
        cme_row = cme_by_date.get(session_date, {})
        guru_row = guru_by_date.get(session_date, {})
        price_allowed, price_state = price_filter_allows(trade, signal, config=cfg)
        cme_allowed, cme_state = cme_wall_filter_allows(trade, cme_row, return_state=True)
        guru_allowed, guru_state = guru_filter_allows(trade, guru_row, signal, return_state=True)
        combined = price_allowed and cme_allowed and guru_allowed
        rows.append(
            {
                **trade,
                "session_date": session_date,
                "price_filter_state": price_state,
                "cme_filter_state": cme_state,
                "guru_filter_state": guru_state,
                "price_only_allow": price_allowed,
                "cme_allow": cme_allowed,
                "guru_allow": guru_allowed,
                "combined_conservative_allow": combined,
                "basis_adjusted_wall_distance": _basis_adjusted_wall_distance(trade, cme_row),
                "historical_playbook_context": "DIAGNOSTIC_ONLY",
            }
        )
    overlay = _rows_frame(rows, _overlay_trades_schema())
    return overlay, summarize_overlay(overlay)


def price_filter_allows(
    trade: dict[str, Any],
    signal: dict[str, Any],
    *,
    config: PinePythonEngineConfig,
) -> tuple[bool, str]:
    """Apply price-only filters before CME/guru context."""

    if _bool_value(signal.get("no_trade_middle_range")):
        return False, "BLOCK_NO_TRADE_MIDDLE_RANGE"
    if abs(_float_or_zero(signal.get("session_open_distance"))) > config.open_distance_limit_points:
        return False, "BLOCK_OPEN_DISTANCE_CHASE"
    has_acceptance = _bool_value(signal.get("acceptance_breakout")) or _bool_value(
        signal.get("acceptance_breakdown")
    )
    has_rejection = _bool_value(signal.get("rejection_after_level_touch"))
    if not (has_acceptance or has_rejection):
        return False, "BLOCK_NO_ACCEPTANCE_OR_REJECTION"
    expected = abs(_float_or_zero(signal.get("atr"))) + abs(_float_or_zero(signal.get("sd_std")))
    cost = abs(_float_or_zero(trade.get("slippage_paid"))) + abs(
        _float_or_zero(trade.get("commission_paid"))
    )
    if expected <= cost + config.fee_buffer_points:
        return False, "BLOCK_FEE_HURDLE"
    return True, "PRICE_FILTER_ALLOW"


def cme_wall_filter_allows(
    trade: dict[str, Any],
    cme_row: dict[str, Any],
    *,
    strong_wall_threshold: float = 0.20,
    wall_proximity_points: float = 8.0,
    return_state: bool = False,
) -> bool | tuple[bool, str]:
    """Block candidates that point directly into a nearby strong CME wall."""

    if not cme_row:
        return (True, "NO_CME_CONTEXT") if return_state else True
    direction = str(trade.get("direction") or "").upper()
    entry = _float_or_none(trade.get("entry_price"))
    wall_score = _float_or_none(cme_row.get("wall_score")) or 0.0
    if entry is None or wall_score < strong_wall_threshold:
        return (True, "CME_WEAK_OR_NO_NEAR_WALL") if return_state else True
    above = _float_or_none(cme_row.get("nearest_wall_above_price"))
    below = _float_or_none(cme_row.get("nearest_wall_below_price"))
    accepted = _bool_value(cme_row.get("accepted_wall"))
    rejected = _bool_value(cme_row.get("rejected_wall"))
    if direction == "LONG" and above is not None and 0 <= above - entry <= wall_proximity_points:
        state = "ALLOW_ACCEPTED_WALL_BREAK_LONG" if accepted else "BLOCK_LONG_INTO_STRONG_WALL"
        return (accepted, state) if return_state else accepted
    if direction == "SHORT" and below is not None and 0 <= entry - below <= wall_proximity_points:
        state = "ALLOW_ACCEPTED_WALL_BREAK_SHORT" if accepted else "BLOCK_SHORT_INTO_STRONG_WALL"
        return (accepted, state) if return_state else accepted
    if rejected:
        return (True, "ALLOW_REJECTION_CONTEXT") if return_state else True
    return (True, "CME_NO_BLOCK") if return_state else True


def guru_filter_allows(
    trade: dict[str, Any],
    guru_row: dict[str, Any],
    signal: dict[str, Any] | None = None,
    *,
    return_state: bool = False,
) -> bool | tuple[bool, str]:
    """Use timing-confirmed guru no-trade context only as a filter."""

    if signal and _bool_value(signal.get("no_trade_middle_range")):
        return (False, "BLOCK_NO_TRADE_MIDDLE_RANGE") if return_state else False
    if not guru_row:
        return (True, "NO_GURU_CONTEXT") if return_state else True
    evidence = str(guru_row.get("evidence_status") or "").upper()
    active = _bool_value(guru_row.get("no_trade_filter_active"))
    names = str(guru_row.get("active_filter_logic_names") or "")
    if "UNKNOWN" in evidence:
        return (True, "GURU_CONTEXT_ONLY_UNKNOWN_TIMING") if return_state else True
    if "STALE" in names.upper():
        return (False, "BLOCK_STALE_DATA_PERIOD") if return_state else False
    if active and evidence == "TIMING_CONFIRMED":
        return (False, "BLOCK_GURU_SAME_DAY_AVOID") if return_state else False
    return (True, "GURU_NO_BLOCK") if return_state else True


def summarize_overlay(overlay_trades: pl.DataFrame) -> pl.DataFrame:
    """Summarize raw and filtered overlay policies."""

    rows = overlay_trades.to_dicts() if not overlay_trades.is_empty() else []
    policies = {
        "raw_python_pine_like": lambda row: True,
        "price_only_filtered": lambda row: _bool_value(row.get("price_only_allow")),
        "cme_filtered": lambda row: _bool_value(row.get("cme_allow")),
        "guru_filtered": lambda row: _bool_value(row.get("guru_allow")),
        "combined_conservative_filter": lambda row: _bool_value(
            row.get("combined_conservative_allow")
        ),
    }
    output: list[dict[str, Any]] = []
    for policy, predicate in policies.items():
        allowed = [row for row in rows if predicate(row)]
        blocked = [row for row in rows if not predicate(row)]
        pnl = [_float_or_zero(row.get("pnl_after_cost")) for row in allowed]
        wins = [value for value in pnl if value > 0]
        losses = [value for value in pnl if value < 0]
        blocked_pnl = [_float_or_zero(row.get("pnl_after_cost")) for row in blocked]
        avoided_loss = abs(sum(value for value in blocked_pnl if value < 0))
        opportunity_cost = sum(value for value in blocked_pnl if value > 0)
        gross_wins = sum(wins)
        gross_losses = abs(sum(losses))
        output.append(
            {
                "policy": policy,
                "trade_count": len(allowed),
                "blocked_trade_count": len(blocked),
                "win_rate": len(wins) / len(allowed) if allowed else 0.0,
                "net_pnl_after_cost": sum(pnl),
                "avg_win": sum(wins) / len(wins) if wins else 0.0,
                "avg_loss": sum(losses) / len(losses) if losses else 0.0,
                "avg_pnl": sum(pnl) / len(pnl) if pnl else 0.0,
                "profit_factor": gross_wins / gross_losses if gross_losses else None,
                "max_drawdown": _max_drawdown(_cumulative(pnl)),
                "sharpe_proxy": _sharpe_proxy(pnl),
                "fee_paid": sum(_float_or_zero(row.get("commission_paid")) for row in allowed),
                "outlier_loss_count": _outlier_loss_count(pnl),
                "false_block_rate": opportunity_cost / max(abs(sum(blocked_pnl)), 1.0),
                "avoided_loss": avoided_loss,
                "opportunity_cost": opportunity_cost,
                "net_filter_value": avoided_loss - opportunity_cost,
                "sample_size_warning": len(allowed) < 30,
                "leakage_warning": False,
                "research_only": True,
            }
        )
    return _rows_frame(output, _overlay_summary_schema())


# ---------------------------------------------------------------------------
# TradingView parity, charts, and reports


def tradingview_parity_report(
    python_summary: pl.DataFrame,
    *,
    output_root: Path,
    pine_path: Path | None = Path("Tradingview.pine"),
) -> pl.DataFrame:
    """Compare Python summary to the supplied TradingView baseline where possible."""

    pine_present = bool(pine_path and pine_path.exists())
    trade_list_present = any(
        (output_root / name).exists()
        for name in (
            "pine_trades.csv",
            "pine_trade_list.csv",
            "tradingview_trades.csv",
            "tradingview_list_of_trades.csv",
            "TradingView_List_of_Trades.csv",
            "List of Trades.csv",
        )
    )
    if not pine_present:
        write_pine_script_request(output_root / "pine_script_needed_for_exact_parity.md")
    row = python_summary.row(0, named=True) if not python_summary.is_empty() else {}
    parity_rows = [
        _parity_row("trade_count", row.get("trade_count"), BASELINE_REPORT_VALUES["total_trades"]),
        _parity_row("long_trade_count", row.get("long_trade_count"), BASELINE_REPORT_VALUES["long_trade_count"]),
        _parity_row("short_trade_count", row.get("short_trade_count"), BASELINE_REPORT_VALUES["short_trade_count"]),
        _parity_row("win_rate", row.get("win_rate"), BASELINE_REPORT_VALUES["win_rate"]),
        _parity_row("net_pnl", row.get("expectancy"), BASELINE_REPORT_VALUES["avg_pnl"]),
        _parity_row("avg_win", row.get("avg_win"), BASELINE_REPORT_VALUES["avg_win"]),
        _parity_row("avg_loss", row.get("avg_loss"), BASELINE_REPORT_VALUES["avg_loss"]),
        _parity_row("commission", row.get("commission_paid"), BASELINE_REPORT_VALUES["commissions"]),
    ]
    status = "PARITY_APPROXIMATE_REQUIRES_TRADE_LIST" if pine_present else "PINE_SCRIPT_MISSING"
    if not trade_list_present:
        status = "PARITY_CHECK_NEEDED"
    return _rows_frame(
        [
            {
                **item,
                "pine_script_present": pine_present,
                "trade_list_present": trade_list_present,
                "parity_status": status,
                "major_mismatch_reasons": (
                    "Yahoo OHLC, simplified Pine-like rules, bar-close fills, "
                    "and no TradingView broker emulator parity yet."
                ),
            }
            for item in parity_rows
        ],
        _parity_schema(),
    )


def write_engine_outputs(
    *,
    output_root: Path,
    charts_dir: Path,
    result: PinePythonEngineResult,
    config: PinePythonEngineConfig,
) -> None:
    """Write all requested Pine-to-Python artifacts."""

    result.yahoo_ohlc_inventory.write_csv(output_root / "yahoo_ohlc_inventory.csv")
    (output_root / "yahoo_ohlc_inventory.md").write_text(
        yahoo_inventory_markdown(result.yahoo_ohlc_inventory),
        encoding="utf-8",
    )
    result.indicator_snapshot.write_csv(output_root / "python_indicator_snapshot.csv")
    (output_root / "python_indicator_snapshot.md").write_text(
        indicator_snapshot_markdown(result.indicator_snapshot),
        encoding="utf-8",
    )
    result.signals.write_csv(output_root / "python_pine_like_signals.csv")
    (output_root / "python_pine_like_signals.md").write_text(
        pine_like_signals_markdown(result.signals),
        encoding="utf-8",
    )
    result.backtest_trades.write_csv(output_root / "python_pine_like_backtest_trades.csv")
    result.backtest_summary.write_csv(output_root / "python_pine_like_backtest_summary.csv")
    (output_root / "python_pine_like_backtest_report.md").write_text(
        backtest_report_markdown(result.backtest_summary),
        encoding="utf-8",
    )
    result.overlay_trades.write_csv(output_root / "python_cme_guru_overlay_trades.csv")
    result.overlay_summary.write_csv(output_root / "python_cme_guru_overlay_summary.csv")
    (output_root / "python_cme_guru_overlay_report.md").write_text(
        overlay_report_markdown(result.overlay_summary),
        encoding="utf-8",
    )
    result.parity.write_csv(output_root / "python_vs_tradingview_parity.csv")
    (output_root / "python_vs_tradingview_parity.md").write_text(
        tradingview_parity_markdown(result.parity),
        encoding="utf-8",
    )
    result.fast_use_decision.write_csv(output_root / "python_fast_use_decision.csv")
    (output_root / "python_fast_use_decision.md").write_text(
        fast_use_decision_markdown(result.fast_use_decision),
        encoding="utf-8",
    )
    write_chart_artifacts(
        charts_dir=charts_dir,
        ohlc=result.ohlc,
        signals=result.signals,
        overlay_trades=result.overlay_trades,
    )
    append_python_engine_sections_to_research_report(
        output_root / "research_report.md",
        result=result,
        config=config,
    )


def write_chart_artifacts(
    *,
    charts_dir: Path,
    ohlc: pl.DataFrame,
    signals: pl.DataFrame,
    overlay_trades: pl.DataFrame | None = None,
) -> tuple[Path, Path]:
    """Create dependency-free HTML charts for quick inspection."""

    charts_dir.mkdir(parents=True, exist_ok=True)
    pine_chart = charts_dir / "python_pine_like_chart.html"
    overlay_chart = charts_dir / "python_cme_guru_overlay_chart.html"
    pine_chart.write_text(
        _chart_html(
            title="Python Pine-Like Candidate Chart",
            ohlc=ohlc,
            signals=signals,
            overlay_trades=None,
        ),
        encoding="utf-8",
    )
    overlay_chart.write_text(
        _chart_html(
            title="Python CME/Guru Overlay Chart",
            ohlc=ohlc,
            signals=signals,
            overlay_trades=overlay_trades,
        ),
        encoding="utf-8",
    )
    return pine_chart, overlay_chart


def append_python_engine_sections_to_research_report(
    path: Path,
    *,
    result: PinePythonEngineResult,
    config: PinePythonEngineConfig,
) -> None:
    """Add or replace Pine-to-Python sections in the main research report."""

    start = "<!-- PINE PYTHON ENGINE START -->"
    end = "<!-- PINE PYTHON ENGINE END -->"
    section = "\n".join([start, *python_engine_report_lines(result, config), end])
    existing = path.read_text(encoding="utf-8") if path.exists() else "# XAU Vol-OI Research Report\n"
    pattern = re.compile(f"{re.escape(start)}.*?{re.escape(end)}", flags=re.DOTALL)
    updated = pattern.sub(section, existing) if pattern.search(existing) else existing.rstrip() + "\n\n" + section + "\n"
    path.write_text(_safe_report_text(updated), encoding="utf-8")


def python_engine_report_lines(
    result: PinePythonEngineResult,
    config: PinePythonEngineConfig,
) -> list[str]:
    """Main report sections requested by the user."""

    backtest = result.backtest_summary.row(0, named=True) if not result.backtest_summary.is_empty() else {}
    raw_overlay = _summary_policy(result.overlay_summary, "raw_python_pine_like")
    combined = _summary_policy(result.overlay_summary, "combined_conservative_filter")
    parity_status = (
        result.parity.row(0, named=True)["parity_status"] if not result.parity.is_empty() else "PARITY_CHECK_NEEDED"
    )
    return [
        "## Pine-to-Python Engine",
        "",
        "- Scope: research-only Python replication candidate using Yahoo-style OHLC.",
        f"- Engine label: `{_engine_label(result)}`",
        f"- Requested symbol/interval: `{config.symbol}` / `{config.interval}`",
        f"- Data coverage: `{result.yahoo_data_coverage}`",
        "",
        "## Yahoo OHLC Backtest",
        "",
        f"- Raw trade count: `{backtest.get('trade_count', 0)}`",
        f"- Raw after-cost PnL: `{_format_float(backtest.get('expectancy', 0.0) * backtest.get('trade_count', 0))}`",
        f"- Average PnL per trade: `{_format_float(backtest.get('avg_pnl', 0.0))}`",
        f"- Long / short PnL: `{_format_float(backtest.get('long_pnl', 0.0))}` / `{_format_float(backtest.get('short_pnl', 0.0))}`",
        f"- Sample warning: `{backtest.get('sample_size_warning', True)}`",
        "",
        "## Python Indicator Snapshot",
        "",
        "- Implemented: EMA, SMA, standard deviation, z-score, ATR, Donchian, RSI, MACD, stochastic, CCI, Parabolic SAR approximation, envelope bands, SD bands, open-distance, realized volatility, range regime, acceptance breakout, rejection after touch.",
        "- Warmup rows remain null, and each function uses current/prior bars only.",
        "",
        "## Python Pine-like Signals",
        "",
        f"- Signal rows: `{result.signals.height}`",
        f"- Candidate rows: `{result.signals.filter(pl.col('direction_candidate') != 'NONE').height if not result.signals.is_empty() else 0}`",
        "- TradingView parity is approximate until the latest Pine script and List of Trades export are supplied.",
        "",
        "## CME/Guru Overlay",
        "",
        f"- Raw overlay PnL: `{_format_float(raw_overlay.get('net_pnl_after_cost', 0.0))}`",
        f"- Combined conservative PnL: `{_format_float(combined.get('net_pnl_after_cost', 0.0))}`",
        f"- Combined blocked trades: `{combined.get('blocked_trade_count', 0)}`",
        "- Guru UNKNOWN timing remains context-only and is not used as a direct signal.",
        "",
        "## TradingView Parity Check",
        "",
        f"- Status: `{parity_status}`",
        "- Expected mismatch drivers: Yahoo OHLC, simplified rules, bar-close fills, and missing broker-emulator parity.",
        "",
        "## Chart Engine",
        "",
        "- Wrote `outputs/charts/python_pine_like_chart.html`.",
        "- Wrote `outputs/charts/python_cme_guru_overlay_chart.html`.",
        "",
        "## Fast-Use Decision",
        "",
        f"- Final label: `{result.final_label}`",
        "- Baseline and filtered candidates remain watchlist/research artifacts until out-of-sample evidence is sufficient.",
    ]


def yahoo_inventory_markdown(frame: pl.DataFrame) -> str:
    return _safe_report_text("# Yahoo OHLC Inventory\n\n" + _frame_markdown(frame, limit=80))


def indicator_snapshot_markdown(frame: pl.DataFrame) -> str:
    return _safe_report_text("# Python Indicator Snapshot\n\n" + _frame_markdown(frame, limit=30))


def pine_like_signals_markdown(frame: pl.DataFrame) -> str:
    summary = (
        pl.DataFrame(
            [
                {
                    "rows": frame.height,
                    "long_candidates": frame.filter(pl.col("direction_candidate") == "LONG").height
                    if not frame.is_empty()
                    else 0,
                    "short_candidates": frame.filter(pl.col("direction_candidate") == "SHORT").height
                    if not frame.is_empty()
                    else 0,
                    "no_trade_rows": frame.filter(pl.col("raw_signal") == "NO_TRADE").height
                    if not frame.is_empty()
                    else 0,
                }
            ]
        )
        if not frame.is_empty()
        else pl.DataFrame([{"rows": 0, "long_candidates": 0, "short_candidates": 0, "no_trade_rows": 0}])
    )
    return _safe_report_text("# Python Pine-Like Signals\n\n" + _frame_markdown(summary))


def backtest_report_markdown(frame: pl.DataFrame) -> str:
    return _safe_report_text(
        "# Python Pine-Like Backtest Report\n\n"
        "Bar-close research simulation with commission and slippage applied.\n\n"
        + _frame_markdown(frame)
    )


def overlay_report_markdown(frame: pl.DataFrame) -> str:
    return _safe_report_text(
        "# Python CME/Guru Overlay Report\n\n"
        "Filters are conservative blockers only. CME walls and guru text are not direct trade signals.\n\n"
        + _frame_markdown(frame)
    )


def tradingview_parity_markdown(frame: pl.DataFrame) -> str:
    return _safe_report_text(
        "# Python vs TradingView Parity\n\n"
        "Initial parity is approximate and should be checked against a TradingView List of Trades CSV.\n\n"
        + _frame_markdown(frame)
    )


def fast_use_decision_markdown(frame: pl.DataFrame) -> str:
    return _safe_report_text("# Fast-Use Decision\n\n" + _frame_markdown(frame))


def write_yahoo_data_request(path: Path, config: PinePythonEngineConfig) -> None:
    """Write a clear data request when local OHLC is unavailable."""

    lines = [
        "# Yahoo OHLC Data Request",
        "",
        "No local Yahoo-style OHLC rows were found for the configured research run.",
        f"- Symbol: `{config.symbol}`",
        f"- Interval: `{config.interval}`",
        "- Set `XAU_ENABLE_YAHOO_INTRADAY_FETCH=true` to allow a yfinance fetch, or place a CSV/Parquet OHLC export under the project data/output folders.",
        "- Yahoo OHLC is price-only research data and is not a replacement for CME OI or IV.",
    ]
    path.write_text(_safe_report_text("\n".join(lines)), encoding="utf-8")


def write_pine_script_request(path: Path) -> None:
    """Write a clear request for the latest Pine script."""

    lines = [
        "# Pine Script Needed For Exact Parity",
        "",
        "The latest Pine script was not found, so exact TradingView parity cannot be checked.",
        "Please provide the latest Pine script and, for trade-level parity, a TradingView List of Trades CSV.",
    ]
    path.write_text(_safe_report_text("\n".join(lines)), encoding="utf-8")


def build_fast_use_decision(
    backtest_summary: pl.DataFrame,
    overlay_summary: pl.DataFrame,
    parity: pl.DataFrame,
) -> pl.DataFrame:
    """Return conservative final labels without execution readiness wording."""

    backtest = backtest_summary.row(0, named=True) if not backtest_summary.is_empty() else {}
    combined = _summary_policy(overlay_summary, "combined_conservative_filter")
    parity_status = parity.row(0, named=True)["parity_status"] if not parity.is_empty() else "PARITY_CHECK_NEEDED"
    labels = ["PYTHON_ENGINE_READY"]
    if int(backtest.get("trade_count") or 0) > 0:
        labels.append("PYTHON_BACKTEST_READY")
    if parity_status != "PARITY_MATCHED":
        labels.append("PARITY_CHECK_NEEDED")
    if int(combined.get("trade_count") or 0) > 0:
        labels.append("FILTER_OVERLAY_CANDIDATE")
    labels.extend(["USE_AS_WATCHLIST_ONLY", "NOT_READY_FOR_MONEY"])
    rows = [
        {
            "decision_rank": index + 1,
            "decision_label": label,
            "reason": _decision_reason(label, backtest, combined, parity_status),
            "research_only": True,
        }
        for index, label in enumerate(dict.fromkeys(labels))
    ]
    return _rows_frame(rows, _fast_use_schema())


# ---------------------------------------------------------------------------
# Internal calculation helpers


def _simulate_trade(
    *,
    trade_id: int,
    direction: str,
    signal: dict[str, Any],
    signal_index: int,
    entry_index: int,
    price_rows: list[dict[str, Any]],
    signal_by_timestamp: dict[str, dict[str, Any]],
    config: PinePythonEngineConfig,
) -> dict[str, Any] | None:
    entry_row = price_rows[entry_index]
    raw_entry = _float_or_none(entry_row.get("close"))
    if raw_entry is None:
        return None
    entry_price = raw_entry + config.slippage_points if direction == "LONG" else raw_entry - config.slippage_points
    atr_value = abs(_float_or_zero(signal.get("atr")))
    sd_value = abs(_float_or_zero(signal.get("sd_std")))
    stop_distance = max(config.stop_sd * sd_value, 1.5 * atr_value, config.slippage_points * 2.0, 1.0)
    target_distance = max(config.entry_sd * sd_value, atr_value, config.slippage_points * 2.0, 1.0)
    stop_price = entry_price - stop_distance if direction == "LONG" else entry_price + stop_distance
    target_price = entry_price + target_distance if direction == "LONG" else entry_price - target_distance
    max_exit_index = min(len(price_rows) - 1, entry_index + config.max_hold_bars)
    exit_index = max_exit_index
    exit_reason = "MAX_HOLD_BAR_CLOSE"
    for index in range(entry_index + 1, max_exit_index + 1):
        current = _float_or_none(price_rows[index].get("close"))
        if current is None:
            continue
        if direction == "LONG" and current <= stop_price:
            exit_index = index
            exit_reason = "STOP_SD_BAR_CLOSE"
            break
        if direction == "SHORT" and current >= stop_price:
            exit_index = index
            exit_reason = "STOP_SD_BAR_CLOSE"
            break
        if direction == "LONG" and current >= target_price:
            exit_index = index
            exit_reason = "TARGET_ATR_SD_BAR_CLOSE"
            break
        if direction == "SHORT" and current <= target_price:
            exit_index = index
            exit_reason = "TARGET_ATR_SD_BAR_CLOSE"
            break
    exit_row = price_rows[exit_index]
    raw_exit = _float_or_none(exit_row.get("close"))
    if raw_exit is None:
        return None
    exit_price = raw_exit - config.slippage_points if direction == "LONG" else raw_exit + config.slippage_points
    gross_before_slippage = (
        raw_exit - raw_entry if direction == "LONG" else raw_entry - raw_exit
    )
    gross_after_slippage = (
        exit_price - entry_price if direction == "LONG" else entry_price - exit_price
    )
    commission = config.commission_rate * (abs(entry_price) + abs(exit_price))
    pnl_after_cost = gross_after_slippage - commission
    signal_timestamp = signal.get("timestamp")
    entry_signal = signal_by_timestamp.get(_timestamp_text(signal_timestamp), signal)
    return {
        "trade_id": f"py_{trade_id}",
        "symbol": entry_row.get("symbol"),
        "interval": entry_row.get("interval"),
        "direction": direction,
        "signal_timestamp": signal_timestamp,
        "entry_timestamp": entry_row.get("timestamp"),
        "exit_timestamp": exit_row.get("timestamp"),
        "signal_bar_index": signal_index,
        "entry_bar_index": entry_index,
        "exit_bar_index": exit_index,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "gross_pnl_before_cost": gross_before_slippage,
        "pnl_after_cost": pnl_after_cost,
        "commission_paid": commission,
        "slippage_paid": config.slippage_points * 2.0,
        "bars_in_trade": exit_index - entry_index,
        "entry_reason": str(entry_signal.get("reason") or ""),
        "exit_reason": exit_reason,
        "pine_like_score": _float_or_none(entry_signal.get("pine_like_score")),
        "sd_position": _float_or_none(entry_signal.get("sd_position")),
        "atr": _float_or_none(entry_signal.get("atr")),
        "stop_price": stop_price,
        "target_price": target_price,
        "research_only": True,
    }


def _direction_candidate(
    *,
    index: int,
    config: PinePythonEngineConfig,
    trend_score: int,
    momentum_score: int,
    sd_position: float | None,
    no_trade: bool,
    acceptance_up: bool,
    acceptance_down: bool,
    reject_long: bool,
    reject_short: bool,
) -> tuple[str, str, str]:
    if index < config.min_warmup_bars:
        return "NONE", "WATCH_ONLY", "warmup"
    if no_trade:
        return "NONE", "NO_TRADE", "NO_TRADE_MIDDLE_RANGE"
    sigma = _float_or_none(sd_position)
    if acceptance_up and trend_score > 0:
        return "LONG", "LONG_CANDIDATE", "ACCEPTANCE_BREAKOUT_WITH_TREND"
    if acceptance_down and trend_score < 0:
        return "SHORT", "SHORT_CANDIDATE", "ACCEPTANCE_BREAKDOWN_WITH_TREND"
    if reject_long and sigma is not None and sigma <= -config.entry_sd and momentum_score >= -1:
        return "LONG", "LONG_CANDIDATE", "REJECTION_AFTER_LOWER_LEVEL_TOUCH"
    if reject_short and sigma is not None and sigma >= config.entry_sd and momentum_score <= 1:
        return "SHORT", "SHORT_CANDIDATE", "REJECTION_AFTER_UPPER_LEVEL_TOUCH"
    if sigma is not None and sigma <= -config.entry_sd and trend_score >= 0:
        return "LONG", "LONG_CANDIDATE", "ENTRY_SD_LOWER_GRID"
    if sigma is not None and sigma >= config.entry_sd and trend_score <= 0:
        return "SHORT", "SHORT_CANDIDATE", "ENTRY_SD_UPPER_GRID"
    return "NONE", "WATCH_ONLY", "NO_CONFIRMED_CANDIDATE"


def _trend_score(
    ema_fast_value: float | None,
    ema_slow_value: float | None,
    macd_hist_value: float | None,
    close_value: float | None,
    env_mid_value: float | None,
) -> int:
    score = 0
    if ema_fast_value is not None and ema_slow_value is not None:
        score += 1 if ema_fast_value > ema_slow_value else -1
    if macd_hist_value is not None:
        score += 1 if macd_hist_value > 0 else -1 if macd_hist_value < 0 else 0
    if close_value is not None and env_mid_value is not None:
        score += 1 if close_value > env_mid_value else -1
    return score


def _momentum_score(
    rsi_value: float | None,
    stoch_k_value: float | None,
    stoch_d_value: float | None,
    cci_value: float | None,
) -> int:
    score = 0
    if rsi_value is not None:
        score += 1 if rsi_value > 55 else -1 if rsi_value < 45 else 0
    if stoch_k_value is not None and stoch_d_value is not None:
        score += 1 if stoch_k_value > stoch_d_value else -1 if stoch_k_value < stoch_d_value else 0
    if cci_value is not None:
        score += 1 if cci_value > 50 else -1 if cci_value < -50 else 0
    return score


def _volatility_score(sd_value: float | None, atr_value: float | None, regime: str) -> int:
    score = 0
    if sd_value is not None and abs(sd_value) > 1.0:
        score += 1
    if atr_value is not None and atr_value > 0:
        score += 1
    if regime == "EXPANDING":
        score += 1
    elif regime == "COMPRESSED":
        score -= 1
    return score


def _prepare_ohlc_for_engine(frame: pl.DataFrame) -> pl.DataFrame:
    if frame.is_empty():
        return _empty_ohlc()
    if set(_ohlc_schema()).issubset(set(frame.columns)):
        return frame.select(list(_ohlc_schema())).sort("timestamp")
    return canonicalize_yahoo_ohlc(
        frame,
        symbol=None,
        interval=infer_interval(frame),
        source="LOCAL_OHLC",
        quality=None,
    )


def _filter_date_range(frame: pl.DataFrame, config: PinePythonEngineConfig) -> pl.DataFrame:
    output = frame
    if config.start:
        start = _timestamp_value(config.start)
        if start is not None:
            output = output.filter(pl.col("timestamp") >= start)
    if config.end:
        end = _timestamp_value(config.end)
        if end is not None:
            output = output.filter(pl.col("timestamp") <= end)
    return output


def _rows_by_date(frame: pl.DataFrame, date_column: str) -> dict[str, dict[str, Any]]:
    if frame.is_empty() or date_column not in frame.columns:
        return {}
    rows: dict[str, dict[str, Any]] = {}
    for raw in frame.to_dicts():
        key = _date_text(raw.get(date_column))
        if key:
            rows[key] = raw
    return rows


def _basis_adjusted_wall_distance(trade: dict[str, Any], cme_row: dict[str, Any]) -> float | None:
    entry = _float_or_none(trade.get("entry_price"))
    if entry is None or not cme_row:
        return None
    direction = str(trade.get("direction") or "").upper()
    if direction == "LONG":
        wall = _float_or_none(cme_row.get("nearest_wall_above_price"))
        return None if wall is None else wall - entry
    wall = _float_or_none(cme_row.get("nearest_wall_below_price"))
    return None if wall is None else entry - wall


def _parity_row(metric: str, python_value: Any, tradingview_value: Any) -> dict[str, Any]:
    py = _float_or_none(python_value)
    tv = _float_or_none(tradingview_value)
    return {
        "metric": metric,
        "python_value": py,
        "tradingview_value": tv,
        "absolute_difference": None if py is None or tv is None else py - tv,
    }


def _decision_reason(
    label: str,
    backtest: dict[str, Any],
    combined: dict[str, Any],
    parity_status: str,
) -> str:
    if label == "PYTHON_ENGINE_READY":
        return "Indicator and artifact engine ran with timestamp-safe functions."
    if label == "PYTHON_BACKTEST_READY":
        return "Python bar-close research backtest produced candidate metrics."
    if label == "PARITY_CHECK_NEEDED":
        return f"TradingView parity status is {parity_status}."
    if label == "FILTER_OVERLAY_CANDIDATE":
        return "CME/guru overlays are blockers for research comparison only."
    if label == "USE_AS_WATCHLIST_ONLY":
        return "Current evidence is not sufficient for execution readiness."
    if label == "NOT_READY_FOR_MONEY":
        return "Research-only phase; no live, broker, or account integration."
    return "Research-only label."


def _engine_label(result: PinePythonEngineResult) -> str:
    if result.ohlc.is_empty():
        return "PARITY_CHECK_NEEDED"
    if result.backtest_summary.is_empty():
        return "PYTHON_ENGINE_READY"
    return "PYTHON_BACKTEST_READY"


def _final_label(frame: pl.DataFrame) -> str:
    if frame.is_empty():
        return "NOT_READY_FOR_MONEY"
    labels = frame.get_column("decision_label").to_list()
    if "NOT_READY_FOR_MONEY" in labels:
        return "NOT_READY_FOR_MONEY"
    return str(labels[-1])


def _coverage_label(inventory: pl.DataFrame, ohlc: pl.DataFrame) -> str:
    if ohlc.is_empty():
        return "NO_LOCAL_YAHOO_OHLC"
    row = ohlc.select(
        pl.len().alias("rows"),
        pl.col("symbol").first().alias("symbol"),
        pl.col("interval").first().alias("interval"),
        pl.col("timestamp").min().alias("start"),
        pl.col("timestamp").max().alias("end"),
        pl.col("quality").first().alias("quality"),
    ).row(0, named=True)
    return (
        f"{row['symbol']} {row['interval']} {row['quality']} "
        f"{row['rows']} rows { _date_text(row['start']) } to { _date_text(row['end']) }"
    )


def _quality_note(quality: str) -> str:
    if quality == "PROXY_ONLY":
        return "GLD proxy only; use for price research, not CME OI/IV replacement."
    if quality.startswith("RESAMPLED"):
        return "Resampled bar timestamp is bucket close."
    if quality == "DAILY_APPROX":
        return "Daily approximation from intraday bars."
    return "Direct local Yahoo-style OHLC."


def _missing_inventory_rows(existing: list[dict[str, Any]]) -> list[dict[str, Any]]:
    available = {(row["symbol"], row["interval"]) for row in existing}
    rows: list[dict[str, Any]] = []
    for symbol in ("GC=F", "XAUUSD=X", "GLD"):
        for interval in SUPPORTED_INTERVALS:
            if (symbol, interval) in available:
                continue
            rows.append(
                {
                    "symbol": symbol,
                    "interval": interval,
                    "rows": 0,
                    "start": None,
                    "end": None,
                    "source": "NOT_FOUND",
                    "quality": "PROXY_ONLY" if symbol == "GLD" else "DIRECT_YAHOO",
                    "available": False,
                    "note": "Not present locally; fetch disabled unless explicitly enabled.",
                }
            )
    return rows


def _resample_source_intervals(target: str) -> tuple[str, ...]:
    if target in {"30m", "1h"}:
        return ("1m", "5m", "15m")
    if target == "4h":
        return ("1h", "60m", "30m", "15m", "5m", "1m")
    if target == "1d":
        return ("1h", "60m", "30m", "15m", "5m", "1m")
    return ()


def _resampled_quality(target: str, source: str) -> str:
    if target == "1d":
        return "DAILY_APPROX"
    if source == "1m":
        return "RESAMPLED_FROM_1M"
    if source in {"1h", "60m"}:
        return "RESAMPLED_FROM_1H"
    return f"RESAMPLED_FROM_{source.upper()}"


def infer_interval(frame: pl.DataFrame) -> str:
    """Infer interval from timestamp spacing."""

    if frame.is_empty():
        return "1d"
    columns = {_normal_column(column): column for column in frame.columns}
    timestamp_col = columns.get("timestamp") or columns.get("datetime") or columns.get("date")
    if timestamp_col is None:
        return "1d"
    timestamps = sorted(
        ts for ts in (_timestamp_value(value) for value in frame.get_column(timestamp_col).head(500).to_list()) if ts
    )
    if len(timestamps) < 2:
        return "1d"
    diffs = [
        int((right - left).total_seconds() // 60)
        for left, right in zip(timestamps[:-1], timestamps[1:], strict=False)
        if right > left
    ]
    if not diffs:
        return "1d"
    minutes = int(median(diffs))
    if minutes <= 1:
        return "1m"
    if minutes <= 5:
        return "5m"
    if minutes <= 15:
        return "15m"
    if minutes <= 30:
        return "30m"
    if minutes <= 60:
        return "1h"
    if minutes <= 240:
        return "4h"
    return "1d"


def _frame_interval(frame: pl.DataFrame) -> str:
    if "interval" in frame.columns and not frame.is_empty():
        return _normal_interval(str(frame.get_column("interval").drop_nulls().head(1).item()))
    return infer_interval(frame)


def _normal_interval(interval: str) -> str:
    value = str(interval).strip().lower()
    if value == "60m":
        return "1h"
    if value == "1hour":
        return "1h"
    return value


def _interval_minutes(interval: str) -> int | None:
    mapping = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "60m": 60, "1h": 60, "4h": 240, "1d": 1440}
    return mapping.get(_normal_interval(interval))


def _bucket_start(timestamp: datetime, minutes: int) -> datetime:
    if minutes >= 1440:
        return datetime.combine(timestamp.date(), time.min, tzinfo=UTC)
    midnight = datetime.combine(timestamp.date(), time.min, tzinfo=UTC)
    elapsed = int((timestamp - midnight).total_seconds() // 60)
    bucket_minutes = (elapsed // minutes) * minutes
    return midnight + timedelta(minutes=bucket_minutes)


def _symbol_priority(symbol: str) -> tuple[str, ...]:
    requested = "XAUUSD=X" if symbol == "XAUUSD" else symbol
    choices = [requested, "GC=F", "XAUUSD=X", "GLD"]
    output: list[str] = []
    for item in choices:
        if item not in output:
            output.append(item)
    return tuple(output)


def _yahoo_interval(interval: str) -> str:
    value = _normal_interval(interval)
    return "60m" if value == "1h" else value


def _glob_yahoo_ohlc_files() -> list[Path]:
    roots = [Path("data"), Path("backend/data")]
    paths: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for pattern in ("*yahoo*ohlc*.parquet", "*yahoo*ohlc*.csv", "*GC=F*.csv", "*GC=F*.parquet"):
            paths.extend(root.rglob(pattern))
    return paths


def _shift(values: Sequence[Any], periods: int) -> list[Any]:
    if periods <= 0:
        return list(values)
    return [None] * periods + list(values[:-periods])


def _expand_level(level: Sequence[float | None] | float, size: int) -> list[float | None]:
    if isinstance(level, int | float):
        return [float(level)] * size
    return list(level)


def _rsi_value(average_gain: float, average_loss: float) -> float:
    if average_loss == 0:
        return 100.0
    relative_strength = average_gain / average_loss
    return 100.0 - (100.0 / (1.0 + relative_strength))


def _outlier_loss_count(pnl: list[float]) -> int:
    if not pnl:
        return 0
    losses = [value for value in pnl if value < 0]
    if not losses:
        return 0
    mean_loss = sum(losses) / len(losses)
    threshold = min(mean_loss * 2.0, mean_loss - _stddev(losses) * 2.0)
    return sum(1 for value in losses if value <= threshold)


def _stddev(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    mean_value = sum(values) / len(values)
    return math.sqrt(sum((value - mean_value) ** 2 for value in values) / len(values))


def _cumulative(values: Sequence[float]) -> list[float]:
    total = 0.0
    output: list[float] = []
    for value in values:
        total += value
        output.append(total)
    return output


def _max_drawdown(cumulative: Sequence[float]) -> float:
    peak = 0.0
    max_dd = 0.0
    for value in cumulative:
        peak = max(peak, value)
        max_dd = min(max_dd, value - peak)
    return max_dd


def _sharpe_proxy(values: Sequence[float]) -> float | None:
    if len(values) < 2:
        return None
    mean_value = sum(values) / len(values)
    deviation = _stddev(values)
    if deviation == 0:
        return None
    return mean_value / deviation * math.sqrt(len(values))


def _summary_policy(frame: pl.DataFrame, policy: str) -> dict[str, Any]:
    if frame.is_empty() or "policy" not in frame.columns:
        return {}
    rows = frame.filter(pl.col("policy") == policy).to_dicts()
    return rows[0] if rows else {}


def _chart_html(
    *,
    title: str,
    ohlc: pl.DataFrame,
    signals: pl.DataFrame,
    overlay_trades: pl.DataFrame | None,
) -> str:
    rows = ohlc.tail(180).to_dicts() if not ohlc.is_empty() else []
    signal_rows = signals.tail(180).to_dicts() if not signals.is_empty() else []
    width = 960
    height = 420
    closes = [_float_or_zero(row.get("close")) for row in rows if _float_or_none(row.get("close")) is not None]
    upper = [_float_or_none(row.get("sd_upper")) for row in signal_rows]
    lower = [_float_or_none(row.get("sd_lower")) for row in signal_rows]
    band_values = [value for value in upper + lower if value is not None]
    all_values = closes + band_values
    if not all_values:
        body = "<p>No chart rows available.</p>"
    else:
        min_price = min(all_values)
        max_price = max(all_values)
        span = max(max_price - min_price, 1.0)

        def point(index: int, value: float | None) -> str:
            if value is None:
                value = min_price
            x = 20 + index * ((width - 40) / max(len(rows) - 1, 1))
            y = height - 20 - ((value - min_price) / span) * (height - 40)
            return f"{x:.1f},{y:.1f}"

        price_points = " ".join(point(index, _float_or_none(row.get("close"))) for index, row in enumerate(rows))
        upper_points = " ".join(
            point(index, _float_or_none(row.get("sd_upper"))) for index, row in enumerate(signal_rows[: len(rows)])
        )
        lower_points = " ".join(
            point(index, _float_or_none(row.get("sd_lower"))) for index, row in enumerate(signal_rows[: len(rows)])
        )
        markers = []
        for index, signal in enumerate(signal_rows[: len(rows)]):
            direction = str(signal.get("direction_candidate") or "NONE")
            if direction == "NONE":
                continue
            close = _float_or_none(signal.get("close"))
            color = "#166534" if direction == "LONG" else "#991b1b"
            markers.append(
                f'<circle cx="{point(index, close).split(",")[0]}" cy="{point(index, close).split(",")[1]}" r="4" fill="{color}" />'
            )
        body = (
            f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" role="img">'
            '<rect width="100%" height="100%" fill="#ffffff" />'
            f'<polyline points="{upper_points}" fill="none" stroke="#94a3b8" stroke-width="1" />'
            f'<polyline points="{lower_points}" fill="none" stroke="#94a3b8" stroke-width="1" />'
            f'<polyline points="{price_points}" fill="none" stroke="#0f172a" stroke-width="2" />'
            + "".join(markers)
            + "</svg>"
        )
    overlay_note = ""
    if overlay_trades is not None and not overlay_trades.is_empty():
        blocked = overlay_trades.filter(~pl.col("combined_conservative_allow")).height
        overlay_note = f"<p>Combined filter blocked trades: {blocked}</p>"
    return _safe_report_text(
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        f"<title>{html.escape(title)}</title>"
        "<style>body{font-family:Arial,sans-serif;margin:24px;color:#111827}"
        ".note{color:#475569;font-size:13px}</style></head><body>"
        f"<h1>{html.escape(title)}</h1>"
        "<p class=\"note\">Research-only chart. Markers are candidates, not execution instructions.</p>"
        f"{body}{overlay_note}</body></html>"
    )


# ---------------------------------------------------------------------------
# Schemas and low-level helpers


def _inventory_schema() -> dict[str, Any]:
    return {
        "symbol": pl.Utf8,
        "interval": pl.Utf8,
        "rows": pl.Int64,
        "start": pl.Utf8,
        "end": pl.Utf8,
        "source": pl.Utf8,
        "quality": pl.Utf8,
        "available": pl.Boolean,
        "note": pl.Utf8,
    }


def _ohlc_schema() -> dict[str, Any]:
    return {
        "timestamp": pl.Datetime(time_zone="UTC"),
        "symbol": pl.Utf8,
        "interval": pl.Utf8,
        "open": pl.Float64,
        "high": pl.Float64,
        "low": pl.Float64,
        "close": pl.Float64,
        "volume": pl.Float64,
        "source": pl.Utf8,
        "quality": pl.Utf8,
    }


def _indicator_snapshot_schema() -> dict[str, Any]:
    return {
        "timestamp": pl.Datetime(time_zone="UTC"),
        "symbol": pl.Utf8,
        "interval": pl.Utf8,
        "close": pl.Float64,
        "ema_fast": pl.Float64,
        "ema_slow": pl.Float64,
        "rsi": pl.Float64,
        "macd_line": pl.Float64,
        "macd_signal": pl.Float64,
        "macd_hist": pl.Float64,
        "stoch_k": pl.Float64,
        "stoch_d": pl.Float64,
        "cci": pl.Float64,
        "atr": pl.Float64,
        "donchian_high": pl.Float64,
        "donchian_low": pl.Float64,
        "sd_mid": pl.Float64,
        "sd_upper": pl.Float64,
        "sd_lower": pl.Float64,
        "sd_position": pl.Float64,
        "session_open_distance": pl.Float64,
        "realized_volatility": pl.Float64,
        "range_state": pl.Utf8,
        "parabolic_sar": pl.Float64,
        "lookahead_safe": pl.Boolean,
    }


def _signals_schema() -> dict[str, Any]:
    return {
        "timestamp": pl.Datetime(time_zone="UTC"),
        "symbol": pl.Utf8,
        "interval": pl.Utf8,
        "open": pl.Float64,
        "high": pl.Float64,
        "low": pl.Float64,
        "close": pl.Float64,
        "volume": pl.Float64,
        "pine_like_score": pl.Int64,
        "trend_score": pl.Int64,
        "momentum_score": pl.Int64,
        "volatility_score": pl.Int64,
        "range_state": pl.Utf8,
        "sd_position": pl.Float64,
        "no_trade_middle_range": pl.Boolean,
        "acceptance_breakout": pl.Boolean,
        "acceptance_breakdown": pl.Boolean,
        "rejection_after_level_touch": pl.Boolean,
        "direction_candidate": pl.Utf8,
        "raw_signal": pl.Utf8,
        "reason": pl.Utf8,
        "ema_fast": pl.Float64,
        "ema_slow": pl.Float64,
        "rsi": pl.Float64,
        "macd_line": pl.Float64,
        "macd_signal": pl.Float64,
        "macd_hist": pl.Float64,
        "stoch_k": pl.Float64,
        "stoch_d": pl.Float64,
        "cci": pl.Float64,
        "atr": pl.Float64,
        "donchian_high": pl.Float64,
        "donchian_low": pl.Float64,
        "sd_mid": pl.Float64,
        "sd_upper": pl.Float64,
        "sd_lower": pl.Float64,
        "sd_std": pl.Float64,
        "env_mid": pl.Float64,
        "env_upper": pl.Float64,
        "env_lower": pl.Float64,
        "session_open_distance": pl.Float64,
        "realized_volatility": pl.Float64,
        "parabolic_sar": pl.Float64,
    }


def _trades_schema() -> dict[str, Any]:
    return {
        "trade_id": pl.Utf8,
        "symbol": pl.Utf8,
        "interval": pl.Utf8,
        "direction": pl.Utf8,
        "signal_timestamp": pl.Datetime(time_zone="UTC"),
        "entry_timestamp": pl.Datetime(time_zone="UTC"),
        "exit_timestamp": pl.Datetime(time_zone="UTC"),
        "signal_bar_index": pl.Int64,
        "entry_bar_index": pl.Int64,
        "exit_bar_index": pl.Int64,
        "entry_price": pl.Float64,
        "exit_price": pl.Float64,
        "gross_pnl_before_cost": pl.Float64,
        "pnl_after_cost": pl.Float64,
        "commission_paid": pl.Float64,
        "slippage_paid": pl.Float64,
        "bars_in_trade": pl.Int64,
        "entry_reason": pl.Utf8,
        "exit_reason": pl.Utf8,
        "pine_like_score": pl.Float64,
        "sd_position": pl.Float64,
        "atr": pl.Float64,
        "stop_price": pl.Float64,
        "target_price": pl.Float64,
        "research_only": pl.Boolean,
    }


def _backtest_summary_schema() -> dict[str, Any]:
    return {
        "strategy": pl.Utf8,
        "data_mode": pl.Utf8,
        "symbol": pl.Utf8,
        "interval": pl.Utf8,
        "trade_count": pl.Int64,
        "win_rate": pl.Float64,
        "avg_win": pl.Float64,
        "avg_loss": pl.Float64,
        "avg_pnl": pl.Float64,
        "expectancy": pl.Float64,
        "profit_factor": pl.Float64,
        "max_drawdown": pl.Float64,
        "sharpe_proxy": pl.Float64,
        "commission_paid": pl.Float64,
        "long_pnl": pl.Float64,
        "short_pnl": pl.Float64,
        "long_trade_count": pl.Int64,
        "short_trade_count": pl.Int64,
        "average_hold_bars": pl.Float64,
        "outlier_loss_count": pl.Int64,
        "sample_size_warning": pl.Boolean,
        "research_only": pl.Boolean,
    }


def _overlay_trades_schema() -> dict[str, Any]:
    schema = dict(_trades_schema())
    schema.update(
        {
            "session_date": pl.Utf8,
            "price_filter_state": pl.Utf8,
            "cme_filter_state": pl.Utf8,
            "guru_filter_state": pl.Utf8,
            "price_only_allow": pl.Boolean,
            "cme_allow": pl.Boolean,
            "guru_allow": pl.Boolean,
            "combined_conservative_allow": pl.Boolean,
            "basis_adjusted_wall_distance": pl.Float64,
            "historical_playbook_context": pl.Utf8,
        }
    )
    return schema


def _overlay_summary_schema() -> dict[str, Any]:
    return {
        "policy": pl.Utf8,
        "trade_count": pl.Int64,
        "blocked_trade_count": pl.Int64,
        "win_rate": pl.Float64,
        "net_pnl_after_cost": pl.Float64,
        "avg_win": pl.Float64,
        "avg_loss": pl.Float64,
        "avg_pnl": pl.Float64,
        "profit_factor": pl.Float64,
        "max_drawdown": pl.Float64,
        "sharpe_proxy": pl.Float64,
        "fee_paid": pl.Float64,
        "outlier_loss_count": pl.Int64,
        "false_block_rate": pl.Float64,
        "avoided_loss": pl.Float64,
        "opportunity_cost": pl.Float64,
        "net_filter_value": pl.Float64,
        "sample_size_warning": pl.Boolean,
        "leakage_warning": pl.Boolean,
        "research_only": pl.Boolean,
    }


def _parity_schema() -> dict[str, Any]:
    return {
        "metric": pl.Utf8,
        "python_value": pl.Float64,
        "tradingview_value": pl.Float64,
        "absolute_difference": pl.Float64,
        "pine_script_present": pl.Boolean,
        "trade_list_present": pl.Boolean,
        "parity_status": pl.Utf8,
        "major_mismatch_reasons": pl.Utf8,
    }


def _fast_use_schema() -> dict[str, Any]:
    return {
        "decision_rank": pl.Int64,
        "decision_label": pl.Utf8,
        "reason": pl.Utf8,
        "research_only": pl.Boolean,
    }


def _empty_ohlc() -> pl.DataFrame:
    return pl.DataFrame(schema=_ohlc_schema())


def _empty_signals() -> pl.DataFrame:
    return pl.DataFrame(schema=_signals_schema())


def _empty_trades() -> pl.DataFrame:
    return pl.DataFrame(schema=_trades_schema())


def _empty_overlay_trades() -> pl.DataFrame:
    return pl.DataFrame(schema=_overlay_trades_schema())


def _rows_frame(rows: list[dict[str, Any]], schema: dict[str, Any]) -> pl.DataFrame:
    if not rows:
        return pl.DataFrame(schema=schema)
    frame = pl.DataFrame(rows, infer_schema_length=None)
    for column, dtype in schema.items():
        if column not in frame.columns:
            frame = frame.with_columns(pl.lit(None).cast(dtype).alias(column))
        else:
            frame = frame.with_columns(pl.col(column).cast(dtype, strict=False))
    return frame.select(list(schema))


def _load_optional(path: Path | None) -> pl.DataFrame:
    if path is None or not path.exists():
        return pl.DataFrame()
    try:
        if path.suffix.lower() == ".parquet":
            return pl.read_parquet(path)
        if path.suffix.lower() == ".csv":
            return pl.read_csv(path, infer_schema_length=1000)
    except Exception:
        return pl.DataFrame()
    return pl.DataFrame()


def _normal_column(column: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", column.lower())


def _get_first(raw: dict[str, Any], columns: dict[str, str], names: tuple[str, ...]) -> Any:
    for name in names:
        column = columns.get(_normal_column(name))
        if column is not None:
            return raw.get(column)
    return None


def _timestamp_value(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=UTC)
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except ValueError:
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d").replace(tzinfo=UTC)
        except ValueError:
            return None


def _timestamp_text(value: Any) -> str:
    timestamp = _timestamp_value(value)
    return "" if timestamp is None else timestamp.isoformat().replace("+00:00", "Z")


def _date_text(value: Any) -> str:
    timestamp = _timestamp_value(value)
    return "" if timestamp is None else timestamp.date().isoformat()


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(numeric) or math.isinf(numeric):
        return None
    return numeric


def _float_or_zero(value: Any) -> float:
    return _float_or_none(value) or 0.0


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, int | float):
        return bool(value)
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def _format_float(value: Any) -> str:
    numeric = _float_or_none(value)
    if numeric is None:
        return "n/a"
    return f"{numeric:.2f}"


def _frame_markdown(frame: pl.DataFrame, *, limit: int = 20) -> str:
    if frame.is_empty():
        return "_No rows._"
    rows = ["| " + " | ".join(frame.columns) + " |", "|" + "|".join(["---"] * len(frame.columns)) + "|"]
    for raw in frame.head(limit).to_dicts():
        rows.append("| " + " | ".join(_markdown_cell(raw.get(column, "")) for column in frame.columns) + " |")
    return "\n".join(rows)


def _markdown_cell(value: Any) -> str:
    return _redact_text(str(value).replace("|", "\\|").replace("\n", " "))[:700]


def _safe_report_text(text: str) -> str:
    safe = _redact_text(text)
    lowered = safe.lower()
    for phrase in FORBIDDEN_REPORT_PHRASES:
        if phrase in lowered:
            raise ValueError(f"Forbidden report phrase: {phrase}")
    if re.search(r"[A-Za-z]:[\\/]+Users[\\/]+", safe):
        raise ValueError("Report contains an unredacted local source path.")
    return safe


def _redact_text(text: str) -> str:
    text = re.sub(r"[A-Za-z]:[\\/]+Users[\\/]+[^`|\s,\"]+", "<REDACTED_PATH>", text)
    text = re.sub(r"[A-Za-z]:[\\/]+[^`|\s,\"]+", "<REDACTED_PATH>", text)
    text = re.sub(r"/Users/[^`|\s,\"]+", "<REDACTED_PATH>", text)
    return text


def main() -> None:
    """CLI entry point."""

    parser = argparse.ArgumentParser(description="Run Pine-to-Python Yahoo backtest lab.")
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    parser.add_argument("--pine", type=Path, default=Path("Tradingview.pine"))
    args = parser.parse_args()
    result = run_pine_python_engine_lab(output_dir=args.output_dir, pine_path=args.pine)
    print(f"coverage: {result.yahoo_data_coverage}")
    print(f"final_label: {result.final_label}")


if __name__ == "__main__":
    main()
