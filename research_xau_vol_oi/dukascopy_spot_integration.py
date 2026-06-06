"""Dukascopy XAUUSD spot integration and research refresh layer.

This layer treats Dukascopy bid/ask XAUUSD M1 data as the primary spot
price/outcome source. It remains research-only: CME OI/IV coverage is audited
separately, no future data is used for feature/event formation, and reports do
not make money-edge, prediction, safety, paper, or live-readiness claims.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

import polars as pl

from research_xau_vol_oi.daily_forward_data_gate import required_window_ranges


TIMEFRAMES = ("5m", "15m", "30m", "1h", "4h", "1d")
PRICE_RULE_TIMEFRAMES = ("15m", "30m", "1h", "4h", "1d")
PRICE_RULES = (
    "NO_TRADE_MIDDLE_RANGE",
    "OPEN_DISTANCE_FILTER",
    "ACCEPTANCE_BREAKOUT",
    "REJECTION_AFTER_LEVEL_TOUCH",
    "IV_EXPECTED_RANGE_FILTER",
    "FEE_SPREAD_HURDLE",
)
FINAL_LABELS = (
    "DUKASCOPY_PRICE_BACKTEST_READY",
    "GURU_PRICE_LOGIC_TEST_READY",
    "CME_OVERLAP_PILOT_READY",
    "CME_VALIDATION_STILL_NEEDS_MORE_CME",
    "NOT_READY_FOR_MONEY",
)
FORBIDDEN_REPORT_PHRASES = (
    "profitable",
    "guaranteed edge",
    "predicts price",
    "safe to trade",
    "live ready",
    "live-ready",
    "paper ready",
    "paper-ready",
    "money ready",
)
CACHE_SCHEMA_VERSION = 1
CACHE_MANIFEST_NAME = "dukascopy_spot_integration_cache.json"


@dataclass(frozen=True)
class DukascopyValidation:
    """Cleaned Dukascopy coverage and quality summary."""

    row_count: int
    date_start: str
    date_end: str
    missing_minutes: int
    duplicate_timestamps: int
    suspicious_candles: int
    max_spread: float | None
    average_spread: float | None
    abnormal_spread_count: int
    validation_pass: bool
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class DukascopySpotIntegrationResult:
    """All generated frames and final labels for the layer."""

    validation: DukascopyValidation
    spread_report: pl.DataFrame
    resample_report: pl.DataFrame
    price_source_priority: pl.DataFrame
    price_rule_backtest: pl.DataFrame
    price_rule_by_timeframe: pl.DataFrame
    guru_price_test: pl.DataFrame
    cme_overlap_validation: pl.DataFrame
    forward_outcomes: pl.DataFrame
    readiness_summary: pl.DataFrame
    final_labels: tuple[str, ...]
    paths: dict[str, Path]


def run_dukascopy_spot_integration(
    *,
    cleaned_path: str | Path = "data_pipeline/data/processed/xauusd_m1_2024_to_now.parquet",
    output_dir: str | Path = "outputs",
    repo_root: str | Path = ".",
    abnormal_spread_points: float = 5.0,
    write_outputs: bool = True,
    use_cache: bool = True,
) -> DukascopySpotIntegrationResult:
    """Run canonical spot, resample, rule, guru, CME, and forward refreshes."""

    root = Path(repo_root)
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    source = Path(cleaned_path)

    if not source.exists():
        validation = DukascopyValidation(
            row_count=0,
            date_start="",
            date_end="",
            missing_minutes=0,
            duplicate_timestamps=0,
            suspicious_candles=0,
            max_spread=None,
            average_spread=None,
            abnormal_spread_count=0,
            validation_pass=False,
            warnings=("Cleaned Dukascopy XAUUSD M1 Parquet was not found.",),
        )
        result = _empty_result(validation, output_root)
        if write_outputs:
            _write_missing_outputs(output_root, result)
        return result

    cache_key = _source_cache_key(
        source,
        abnormal_spread_points=abnormal_spread_points,
    )
    if write_outputs and use_cache:
        cached = _load_cached_result(output_root, expected_cache_key=cache_key)
        if cached is not None:
            return cached

    canonical = create_canonical_spot_table(
        pl.read_parquet(source),
        abnormal_spread_points=abnormal_spread_points,
    )
    validation = validate_canonical_spot(
        canonical,
        abnormal_spread_points=abnormal_spread_points,
    )
    spread_report = build_spread_report(
        canonical,
        validation=validation,
        source_path=source,
        abnormal_spread_points=abnormal_spread_points,
    )
    resampled = {
        timeframe: resample_canonical_spot(canonical, timeframe)
        for timeframe in TIMEFRAMES
    }
    resample_report = build_resample_report(resampled)
    price_priority = build_price_source_priority_report(
        repo_root=root,
        output_dir=output_root,
        cleaned_path=source,
        validation=validation,
    )
    price_backtest = run_price_only_rule_backtest(resampled)
    by_timeframe = summarize_rule_backtest_by_timeframe(price_backtest)
    guru_test = run_guru_price_only_test(
        price_backtest=price_backtest,
        output_dir=output_root,
    )
    cme_overlap = run_cme_overlap_validation(
        canonical=canonical,
        output_dir=output_root,
    )
    forward_outcomes = resolve_forward_outcomes_with_dukascopy(
        canonical=canonical,
        resampled=resampled,
        output_dir=output_root,
    )
    readiness = build_data_readiness_summary(
        validation=validation,
        price_backtest=price_backtest,
        guru_test=guru_test,
        cme_overlap=cme_overlap,
        forward_outcomes=forward_outcomes,
    )
    final_labels = tuple(readiness.get_column("label").to_list())
    paths = _output_paths(output_root)
    result = DukascopySpotIntegrationResult(
        validation=validation,
        spread_report=spread_report,
        resample_report=resample_report,
        price_source_priority=price_priority,
        price_rule_backtest=price_backtest,
        price_rule_by_timeframe=by_timeframe,
        guru_price_test=guru_test,
        cme_overlap_validation=cme_overlap,
        forward_outcomes=forward_outcomes,
        readiness_summary=readiness,
        final_labels=final_labels,
        paths=paths,
    )
    if write_outputs:
        write_dukascopy_outputs(
            output_root=output_root,
            canonical=canonical,
            resampled=resampled,
            result=result,
            source_path=source,
            cache_key=cache_key,
        )
    return result


def create_canonical_spot_table(
    frame: pl.DataFrame,
    *,
    abnormal_spread_points: float = 5.0,
) -> pl.DataFrame:
    """Create the canonical M1 bid/ask/mid spot table from cleaned data."""

    if frame.is_empty():
        return _empty_canonical()
    columns = {_normalize_name(column): column for column in frame.columns}
    timestamp_col = _first_existing(columns, ("timestamp", "datetime", "time"))
    if timestamp_col is None:
        raise ValueError("Dukascopy cleaned frame requires timestamp/datetime.")

    working = _normalize_timestamp(frame, timestamp_col)
    required = {
        "bid_open": _first_existing(columns, ("bid_open", "bidopen")),
        "bid_high": _first_existing(columns, ("bid_high", "bidhigh")),
        "bid_low": _first_existing(columns, ("bid_low", "bidlow")),
        "bid_close": _first_existing(columns, ("bid_close", "bidclose")),
        "ask_open": _first_existing(columns, ("ask_open", "askopen")),
        "ask_high": _first_existing(columns, ("ask_high", "askhigh")),
        "ask_low": _first_existing(columns, ("ask_low", "asklow")),
        "ask_close": _first_existing(columns, ("ask_close", "askclose")),
    }
    missing = [target for target, source in required.items() if source is None]
    if missing:
        raise ValueError("Dukascopy frame missing bid/ask columns: " + ", ".join(missing))

    canonical = (
        working.select(
            [
                pl.col("timestamp"),
                pl.col(required["bid_open"]).cast(pl.Float64).alias("bid_open"),
                pl.col(required["bid_high"]).cast(pl.Float64).alias("bid_high"),
                pl.col(required["bid_low"]).cast(pl.Float64).alias("bid_low"),
                pl.col(required["bid_close"]).cast(pl.Float64).alias("bid_close"),
                pl.col(required["ask_open"]).cast(pl.Float64).alias("ask_open"),
                pl.col(required["ask_high"]).cast(pl.Float64).alias("ask_high"),
                pl.col(required["ask_low"]).cast(pl.Float64).alias("ask_low"),
                pl.col(required["ask_close"]).cast(pl.Float64).alias("ask_close"),
            ]
        )
        .drop_nulls()
        .unique(subset=["timestamp"], keep="first")
        .sort("timestamp")
        .with_columns(
            [
                ((pl.col("bid_open") + pl.col("ask_open")) / 2.0).alias("mid_open"),
                ((pl.col("bid_high") + pl.col("ask_high")) / 2.0).alias("mid_high"),
                ((pl.col("bid_low") + pl.col("ask_low")) / 2.0).alias("mid_low"),
                ((pl.col("bid_close") + pl.col("ask_close")) / 2.0).alias("mid_close"),
                (pl.col("ask_close") - pl.col("bid_close")).alias("spread_close"),
                (pl.col("ask_close") - pl.col("bid_close")).alias("spread_points"),
                pl.lit("DUKASCOPY").alias("source"),
            ]
        )
        .with_columns(
            [
                pl.col("timestamp").dt.date().cast(pl.String).alias("trade_date"),
                pl.when(pl.col("spread_points") < 0)
                .then(pl.lit("INVALID_NEGATIVE_SPREAD"))
                .when(pl.col("spread_points") > abnormal_spread_points)
                .then(pl.lit("WARN_ABNORMAL_SPREAD"))
                .otherwise(pl.lit("GOOD"))
                .alias("quality"),
                pl.col("mid_open").alias("open"),
                pl.col("mid_high").alias("high"),
                pl.col("mid_low").alias("low"),
                pl.col("mid_close").alias("close"),
                pl.lit("DUKASCOPY_XAUUSD_BID_ASK").alias("price_source_label"),
                pl.lit(True).alias("spread_available"),
            ]
        )
    )
    return canonical.select(_canonical_columns())


def validate_canonical_spot(
    frame: pl.DataFrame,
    *,
    abnormal_spread_points: float = 5.0,
) -> DukascopyValidation:
    """Validate timestamp, OHLC, duplicate, and spread quality."""

    if frame.is_empty():
        return DukascopyValidation(
            row_count=0,
            date_start="",
            date_end="",
            missing_minutes=0,
            duplicate_timestamps=0,
            suspicious_candles=0,
            max_spread=None,
            average_spread=None,
            abnormal_spread_count=0,
            validation_pass=False,
            warnings=("Canonical Dukascopy table is empty.",),
        )
    sorted_frame = frame.sort("timestamp")
    duplicate_count = (
        sorted_frame.group_by("timestamp")
        .len()
        .filter(pl.col("len") > 1)
        .height
    )
    suspicious = sorted_frame.filter(
        (pl.col("mid_high") < pl.col("mid_low"))
        | (pl.col("mid_open") > pl.col("mid_high"))
        | (pl.col("mid_open") < pl.col("mid_low"))
        | (pl.col("mid_close") > pl.col("mid_high"))
        | (pl.col("mid_close") < pl.col("mid_low"))
        | (pl.col("ask_close") < pl.col("bid_close"))
    )
    spread = sorted_frame.select(
        [
            pl.col("spread_close").mean().alias("average"),
            pl.col("spread_close").max().alias("maximum"),
            (pl.col("spread_points") > abnormal_spread_points)
            .sum()
            .alias("abnormal_count"),
        ]
    ).row(0, named=True)
    missing = count_missing_gaps(sorted_frame, "1m")
    warnings: list[str] = []
    if int(spread["abnormal_count"] or 0) > 0:
        warnings.append(
            f"{int(spread['abnormal_count'])} M1 rows exceed "
            f"{abnormal_spread_points:g} spread points."
        )
    validation_pass = (
        sorted_frame.height > 0
        and missing == 0
        and duplicate_count == 0
        and suspicious.height == 0
    )
    return DukascopyValidation(
        row_count=sorted_frame.height,
        date_start=_iso(_column_datetime(sorted_frame, "timestamp", "min")),
        date_end=_iso(_column_datetime(sorted_frame, "timestamp", "max")),
        missing_minutes=missing,
        duplicate_timestamps=duplicate_count,
        suspicious_candles=suspicious.height,
        max_spread=_float_or_none(spread["maximum"]),
        average_spread=_float_or_none(spread["average"]),
        abnormal_spread_count=int(spread["abnormal_count"] or 0),
        validation_pass=validation_pass,
        warnings=tuple(warnings),
    )


def build_spread_report(
    frame: pl.DataFrame,
    *,
    validation: DukascopyValidation,
    source_path: Path,
    abnormal_spread_points: float = 5.0,
) -> pl.DataFrame:
    """Build a compact spread report with redacted source metadata."""

    if frame.is_empty():
        return pl.DataFrame(schema=_spread_report_schema())
    stats = frame.select(
        [
            pl.col("spread_close").min().alias("min_spread"),
            pl.col("spread_close").mean().alias("average_spread"),
            pl.col("spread_close").median().alias("median_spread"),
            pl.col("spread_close").quantile(0.95).alias("p95_spread"),
            pl.col("spread_close").quantile(0.99).alias("p99_spread"),
            pl.col("spread_close").max().alias("max_spread"),
            (pl.col("spread_close") < 0).sum().alias("negative_spread_count"),
            (pl.col("spread_close") == 0).sum().alias("zero_spread_count"),
            (pl.col("spread_points") > abnormal_spread_points)
            .sum()
            .alias("abnormal_spread_count"),
        ]
    ).row(0, named=True)
    row = {
        "source": "DUKASCOPY",
        "redacted_source_path": redact_path(source_path),
        "rows": validation.row_count,
        "date_start": validation.date_start,
        "date_end": validation.date_end,
        "validation_pass": validation.validation_pass,
        "abnormal_spread_threshold_points": abnormal_spread_points,
        **stats,
    }
    return _rows_frame([row], _spread_report_schema())


def resample_canonical_spot(frame: pl.DataFrame, timeframe: str) -> pl.DataFrame:
    """Resample M1 canonical rows to a higher timeframe."""

    if frame.is_empty():
        return _empty_resampled()
    every = _polars_every(timeframe)
    sorted_frame = frame.sort("timestamp").set_sorted("timestamp")
    resampled = (
        sorted_frame.group_by_dynamic(
            "timestamp",
            every=every,
            period=every,
            closed="left",
            label="left",
        )
        .agg(
            [
                pl.col("bid_open").first().alias("bid_open"),
                pl.col("bid_high").max().alias("bid_high"),
                pl.col("bid_low").min().alias("bid_low"),
                pl.col("bid_close").last().alias("bid_close"),
                pl.col("ask_open").first().alias("ask_open"),
                pl.col("ask_high").max().alias("ask_high"),
                pl.col("ask_low").min().alias("ask_low"),
                pl.col("ask_close").last().alias("ask_close"),
                pl.col("mid_open").first().alias("mid_open"),
                pl.col("mid_high").max().alias("mid_high"),
                pl.col("mid_low").min().alias("mid_low"),
                pl.col("mid_close").last().alias("mid_close"),
                pl.col("spread_close").mean().alias("spread_close"),
                pl.col("spread_points").mean().alias("spread_points"),
                pl.col("quality").str.contains("WARN|INVALID").any().alias("has_warning"),
            ]
        )
        .drop_nulls(subset=["mid_open", "mid_high", "mid_low", "mid_close"])
        .with_columns(
            [
                pl.col("timestamp").dt.date().cast(pl.String).alias("trade_date"),
                pl.lit("DUKASCOPY").alias("source"),
                pl.when(pl.col("has_warning"))
                .then(pl.lit("WARN_SOURCE_ROW"))
                .otherwise(pl.lit("GOOD"))
                .alias("quality"),
                pl.col("mid_open").alias("open"),
                pl.col("mid_high").alias("high"),
                pl.col("mid_low").alias("low"),
                pl.col("mid_close").alias("close"),
                pl.lit("DUKASCOPY_XAUUSD_BID_ASK").alias("price_source_label"),
                pl.lit(True).alias("spread_available"),
                pl.lit(timeframe).alias("timeframe"),
            ]
        )
        .drop("has_warning")
    )
    return resampled.select(_resampled_columns())


def build_resample_report(resampled: dict[str, pl.DataFrame]) -> pl.DataFrame:
    """Summarize resampled timeframe coverage."""

    rows = []
    for timeframe, frame in resampled.items():
        rows.append(
            {
                "timeframe": timeframe,
                "rows": frame.height,
                "date_start": _iso(_column_datetime(frame, "timestamp", "min")),
                "date_end": _iso(_column_datetime(frame, "timestamp", "max")),
                "missing_gaps": count_missing_gaps(frame, timeframe),
                "average_spread": _column_float(frame, "spread_close", "mean"),
                "max_spread": _column_float(frame, "spread_close", "max"),
                "quality_flag": "PASS" if frame.height and count_missing_gaps(frame, timeframe) == 0 else "CHECK",
            }
        )
    return _rows_frame(rows, _resample_report_schema())


def build_price_source_priority_report(
    *,
    repo_root: Path,
    output_dir: Path,
    cleaned_path: Path,
    validation: DukascopyValidation,
) -> pl.DataFrame:
    """Build the XAU price-source priority table."""

    sources = [
        {
            "priority": 1,
            "source_name": "Dukascopy XAUUSD cleaned bid/ask mid",
            "source_type": "TRUE_XAUUSD_SPOT_BID_ASK",
            "available": cleaned_path.exists() and validation.validation_pass,
            "selected": cleaned_path.exists() and validation.validation_pass,
            "limitation": "Primary price/outcome source; does not contain CME OI or IV.",
            "redacted_path": redact_path(cleaned_path),
        },
        _glob_source_row(
            2,
            "Yahoo XAUUSD",
            "PUBLIC_XAUUSD_SPOT_IF_AVAILABLE",
            repo_root / "data" / "raw" / "yahoo",
            ("*xauusd*ohlcv*.parquet", "*xauusd*ohlcv*.csv"),
            selected=False,
            limitation="Fallback only when Dukascopy cleaned spot is unavailable.",
        ),
        _glob_source_row(
            3,
            "Yahoo GC=F",
            "GC_FUTURES_PROXY",
            repo_root / "data" / "raw" / "yahoo",
            ("*gc=f*ohlcv*.parquet", "*gc=f*ohlcv*.csv"),
            selected=False,
            limitation="Proxy only; not true XAUUSD spot.",
        ),
        _glob_source_row(
            4,
            "GLD ETF",
            "PROXY_ONLY",
            repo_root / "data" / "raw" / "yahoo",
            ("*gld*ohlcv*.parquet", "*gld*ohlcv*.csv"),
            selected=False,
            limitation="ETF proxy only and must be labeled PROXY_ONLY.",
        ),
    ]
    if not sources[0]["selected"]:
        for row in sources[1:]:
            if row["available"]:
                row["selected"] = True
                break
    # Include generated canonical output as a reference without changing priority.
    sources.append(
        {
            "priority": 1,
            "source_name": "Generated canonical Dukascopy spot output",
            "source_type": "GENERATED_CANONICAL_SPOT",
            "available": (output_dir / "dukascopy_xau_m1_mid.parquet").exists(),
            "selected": False,
            "limitation": "Generated artifact from cleaned bid/ask source.",
            "redacted_path": redact_path(output_dir / "dukascopy_xau_m1_mid.parquet"),
        }
    )
    return _rows_frame(sources, _price_priority_schema()).sort(["priority", "source_name"])


def run_price_only_rule_backtest(
    resampled: dict[str, pl.DataFrame],
    *,
    horizon_bars: int = 4,
) -> pl.DataFrame:
    """Run deterministic price-only rule tests without CME data."""

    rows: list[dict[str, Any]] = []
    for timeframe in PRICE_RULE_TIMEFRAMES:
        frame = resampled.get(timeframe, pl.DataFrame())
        events = _price_rule_events(frame, timeframe=timeframe, horizon_bars=horizon_bars)
        for rule in PRICE_RULES:
            rule_events = [event for event in events if event["rule"] == rule]
            rows.append(_metrics_row(rule_events, timeframe=timeframe, rule=rule))
    return _rows_frame(rows, _price_rule_schema())


def summarize_rule_backtest_by_timeframe(frame: pl.DataFrame) -> pl.DataFrame:
    """Aggregate price-only rule results by timeframe."""

    if frame.is_empty():
        return pl.DataFrame(schema=_price_rule_timeframe_schema())
    rows = []
    for timeframe in PRICE_RULE_TIMEFRAMES:
        subset = frame.filter(pl.col("timeframe") == timeframe)
        if subset.is_empty():
            continue
        trade_count = int(subset.get_column("trade_count").sum())
        weighted_expectancy = _weighted_average(subset, "expectancy", "trade_count")
        long_pnl = float(subset.get_column("long_pnl").sum())
        short_pnl = float(subset.get_column("short_pnl").sum())
        rows.append(
            {
                "timeframe": timeframe,
                "rule_count": subset.height,
                "trade_count": trade_count,
                "expectancy": weighted_expectancy,
                "long_pnl": long_pnl,
                "short_pnl": short_pnl,
                "sample_size_warning": trade_count < 30,
            }
        )
    return _rows_frame(rows, _price_rule_timeframe_schema())


def run_guru_price_only_test(
    *,
    price_backtest: pl.DataFrame,
    output_dir: Path,
) -> pl.DataFrame:
    """Map extracted guru logic categories to Dukascopy price-only outcomes."""

    timing_confirmed = _timing_confirmed_count(output_dir)
    rows = []
    mapping = [
        ("no-trade filter", ("NO_TRADE_MIDDLE_RANGE", "FEE_SPREAD_HURDLE")),
        ("open-distance filter", ("OPEN_DISTANCE_FILTER",)),
        ("acceptance/rejection logic", ("ACCEPTANCE_BREAKOUT", "REJECTION_AFTER_LEVEL_TOUCH")),
        ("session behavior", ("OPEN_DISTANCE_FILTER", "NO_TRADE_MIDDLE_RANGE")),
        ("post-transcript forward outcome", tuple(PRICE_RULES)),
        ("historical playbook context", tuple(PRICE_RULES)),
    ]
    for name, rules in mapping:
        subset = (
            price_backtest.filter(pl.col("rule").is_in(rules))
            if not price_backtest.is_empty()
            else price_backtest
        )
        event_count = int(subset.get_column("trade_count").sum()) if not subset.is_empty() else 0
        timed = min(event_count, timing_confirmed) if "post-transcript" in name else 0
        context = max(event_count - timed, 0)
        avoided_loss = _avoided_loss_proxy(subset)
        rows.append(
            {
                "test_name": name,
                "event_count": event_count,
                "timing_confirmed_event_count": timed,
                "context_only_event_count": context,
                "avoided_loss_proxy": avoided_loss,
                "false_block_rate": _false_block_rate(subset),
                "breakout_followthrough_rate": _rate_for_rule(subset, "ACCEPTANCE_BREAKOUT"),
                "rejection_followthrough_rate": _rate_for_rule(
                    subset,
                    "REJECTION_AFTER_LEVEL_TOUCH",
                ),
                "sample_size_warning": event_count < 30,
                "leakage_warning": (
                    "TIMING_UNKNOWN_CONTEXT_ONLY" if context and timed == 0 else "NO_LEAKAGE_FLAG"
                ),
            }
        )
    return _rows_frame(rows, _guru_price_schema())


def run_cme_overlap_validation(
    *,
    canonical: pl.DataFrame,
    output_dir: Path,
) -> pl.DataFrame:
    """Validate only dates where Dukascopy price and CME artifacts overlap."""

    cme_oi = _load_optional(output_dir / "cme_canonical_option_oi_by_strike.parquet")
    cme_iv = _load_optional(output_dir / "cme_canonical_option_iv_by_strike.parquet")
    futures = _load_optional(output_dir / "cme_canonical_futures_price.parquet")
    basis = _load_optional(output_dir / "cme_canonical_basis.parquet")
    dates = sorted(
        _trade_dates(cme_oi)
        | _trade_dates(cme_iv)
        | _trade_dates(futures)
        | _trade_dates(basis)
    )
    if not dates:
        dates = sorted(_trade_dates(canonical))[-7:]
    rows = []
    full_cme_dates = {
        trade_date
        for trade_date in dates
        if not _date_rows(cme_oi, trade_date).is_empty()
        and not _date_rows(cme_iv, trade_date).is_empty()
        and not _date_rows(futures, trade_date).is_empty()
        and not _date_rows(basis, trade_date).is_empty()
    }
    pilot_only = len(full_cme_dates) < 60
    for trade_date in dates:
        price_day = _date_rows(canonical, trade_date)
        oi_day = _date_rows(cme_oi, trade_date)
        iv_day = _date_rows(cme_iv, trade_date)
        futures_day = _date_rows(futures, trade_date)
        basis_day = _date_rows(basis, trade_date)
        wall = _top_wall(oi_day)
        basis_value = _last_numeric(basis_day, ("basis",))
        wall_level = None
        if wall is not None:
            wall_level = wall - basis_value if basis_value is not None else wall
        reaction = _wall_reaction(price_day, wall_level)
        has_price = not price_day.is_empty()
        has_oi = not oi_day.is_empty()
        has_iv = not iv_day.is_empty()
        has_futures = not futures_day.is_empty()
        has_basis = basis_value is not None
        can_oi = bool(has_price and has_oi)
        can_iv = bool(has_price and has_iv)
        grade = _cme_validation_grade(
            has_price=has_price,
            has_oi=has_oi,
            has_iv=has_iv,
            has_futures=has_futures,
            has_basis=has_basis,
            pilot_only=pilot_only,
        )
        rows.append(
            {
                "trade_date": trade_date,
                "has_dukascopy_spot": has_price,
                "has_gc_futures": has_futures,
                "basis_available": has_basis,
                "has_cme_oi": has_oi,
                "has_cme_iv": has_iv,
                "can_test_oi_wall": can_oi,
                "can_test_iv_range": can_iv,
                "wall_touch": reaction["wall_touch"],
                "wall_rejection": reaction["wall_rejection"],
                "wall_acceptance": reaction["wall_acceptance"],
                "squeeze_gap_followthrough": reaction["squeeze_gap_followthrough"],
                "pin_behavior": reaction["pin_behavior"],
                "validation_grade": grade,
            }
        )
    return _rows_frame(rows, _cme_overlap_schema())


def resolve_forward_outcomes_with_dukascopy(
    *,
    canonical: pl.DataFrame,
    resampled: dict[str, pl.DataFrame],
    output_dir: Path,
) -> pl.DataFrame:
    """Resolve forward journal windows using strict Dukascopy intraday OHLC."""

    coverage = _load_optional(output_dir / "outcome_coverage_check.csv")
    prior = _load_optional(output_dir / "forward_evidence_outcomes_preview.csv")
    if coverage.is_empty() or "observation_timestamp" not in coverage.columns:
        return pl.DataFrame(schema=_forward_outcome_schema())
    source_by_window = {
        "30m": canonical,
        "1h": resampled.get("15m", canonical),
        "4h": resampled.get("30m", canonical),
        "session_close": resampled.get("1h", canonical),
        "next_day": resampled.get("4h", canonical),
    }
    prior_keys = _prior_resolved_keys(prior)
    rows = []
    for journal in coverage.to_dicts():
        observation = _parse_datetime(journal.get("observation_timestamp"))
        if observation is None:
            continue
        windows = required_window_ranges(observation)
        for window, (start, end) in windows.items():
            source = source_by_window[window]
            sliced = _slice_window(source, start, end)
            status = "resolved_with_dukascopy" if not sliced.is_empty() else "still_pending"
            key = (str(journal.get("journal_id") or ""), window)
            rows.append(
                {
                    "journal_id": key[0],
                    "window": window,
                    "window_start": _iso(start),
                    "window_end": _iso(end),
                    "prior_yahoo_resolution": "resolved" if key in prior_keys else "not_resolved",
                    "dukascopy_resolution": status,
                    "newly_resolved": status == "resolved_with_dukascopy" and key not in prior_keys,
                    "still_pending": status == "still_pending",
                    "open": _first_float(sliced, "mid_open"),
                    "high": _column_float(sliced, "mid_high", "max"),
                    "low": _column_float(sliced, "mid_low", "min"),
                    "close": _last_float(sliced, "mid_close"),
                    "mfe_mid": _mfe(sliced),
                    "mae_mid": _mae(sliced),
                    "bid_ask_mid_difference_points": _column_float(
                        sliced,
                        "spread_close",
                        "mean",
                    ),
                    "source": "DUKASCOPY",
                }
            )
    return _rows_frame(rows, _forward_outcome_schema())


def build_data_readiness_summary(
    *,
    validation: DukascopyValidation,
    price_backtest: pl.DataFrame,
    guru_test: pl.DataFrame,
    cme_overlap: pl.DataFrame,
    forward_outcomes: pl.DataFrame,
) -> pl.DataFrame:
    """Build answers and final readiness labels."""

    has_price = validation.validation_pass
    has_price_tests = not price_backtest.is_empty() and int(
        price_backtest.get_column("trade_count").sum()
    ) > 0
    has_guru = not guru_test.is_empty() and int(guru_test.get_column("event_count").sum()) > 0
    cme_pilot = _any_true(cme_overlap, "can_test_oi_wall") or _any_true(
        cme_overlap,
        "can_test_iv_range",
    )
    newly = (
        int(forward_outcomes.get_column("newly_resolved").sum())
        if not forward_outcomes.is_empty()
        else 0
    )
    rows = [
        {
            "question": "What can be tested now with Dukascopy?",
            "answer": (
                "Price-only rules, spread-aware outcomes, MFE/MAE, session behavior, "
                "and forward outcome resolution."
                if has_price
                else "Dukascopy cleaned spot is not ready."
            ),
            "label": "DUKASCOPY_PRICE_BACKTEST_READY" if has_price_tests else "PRICE_DATA_NOT_READY",
        },
        {
            "question": "What still requires CME OI/IV?",
            "answer": "OI walls, OI change, option volume, IV range, and strike/expiry validation.",
            "label": "CME_VALIDATION_STILL_NEEDS_MORE_CME",
        },
        {
            "question": "What still requires TradingView trade CSV?",
            "answer": "Pine/TradingView trade-list parity and discretionary execution audit.",
            "label": "TRADINGVIEW_TRADE_CSV_STILL_NEEDED",
        },
        {
            "question": "What still requires guru metadata?",
            "answer": "Transcript timing, pre-event availability, and context-only separation.",
            "label": "GURU_METADATA_STILL_NEEDED",
        },
        {
            "question": "What can be used for forward journal now?",
            "answer": f"Dukascopy strict intraday OHLC; newly resolved preview rows: {newly}.",
            "label": "GURU_PRICE_LOGIC_TEST_READY" if has_guru else "GURU_CONTEXT_ONLY",
        },
        {
            "question": "What is still not ready for money?",
            "answer": "Full validation still needs more CME history and forward evidence.",
            "label": "NOT_READY_FOR_MONEY",
        },
    ]
    if cme_pilot:
        rows.insert(
            2,
            {
                "question": "Can CME overlap be tested now?",
                "answer": "Yes, only as a CME overlap pilot on dates with actual CME fields.",
                "label": "CME_OVERLAP_PILOT_READY",
            },
        )
    else:
        rows.insert(
            2,
            {
                "question": "Can CME overlap be tested now?",
                "answer": "Only after CME OI/IV overlap rows are present.",
                "label": "CME_OVERLAP_WAIT_FOR_CME",
            },
        )
    frame = _rows_frame(rows, _readiness_schema())
    ordered = [label for label in FINAL_LABELS if label in set(frame["label"].to_list())]
    rest = [row for row in frame.to_dicts() if row["label"] not in set(ordered)]
    final_rows = [row for label in ordered for row in frame.to_dicts() if row["label"] == label]
    return _rows_frame([*final_rows, *rest], _readiness_schema())


def write_dukascopy_outputs(
    *,
    output_root: Path,
    canonical: pl.DataFrame,
    resampled: dict[str, pl.DataFrame],
    result: DukascopySpotIntegrationResult,
    source_path: Path,
    cache_key: dict[str, Any],
) -> None:
    """Write all generated CSV, Markdown, and Parquet artifacts."""

    output_root.mkdir(parents=True, exist_ok=True)
    canonical.write_parquet(output_root / "dukascopy_xau_m1_mid.parquet")
    _spot_alias_frame(canonical, "m1").write_parquet(output_root / "xau_spot_dukascopy_m1.parquet")
    _spot_alias_frame(canonical, "m1").write_parquet(
        output_root / "cme_canonical_xau_spot_price_from_dukascopy.parquet"
    )
    for timeframe, frame in resampled.items():
        frame.write_parquet(output_root / f"dukascopy_xau_{timeframe}.parquet")
        _spot_alias_frame(frame, timeframe).write_parquet(
            output_root / f"xau_spot_dukascopy_{timeframe}.parquet"
        )

    _write_frame_pair(
        output_root / "dukascopy_xau_spread_report",
        result.spread_report,
        title="Dukascopy XAUUSD Spread Report",
    )
    _write_frame_pair(
        output_root / "dukascopy_resample_report",
        result.resample_report,
        title="Dukascopy XAUUSD Resample Report",
    )
    _write_frame_pair(
        output_root / "price_source_priority_report",
        result.price_source_priority,
        title="XAU Price Source Priority",
    )
    _write_frame_pair(
        output_root / "dukascopy_price_only_rule_backtest",
        result.price_rule_backtest,
        title="Dukascopy Price-Only Rule Backtest",
    )
    _write_frame_pair(
        output_root / "dukascopy_rule_backtest_by_timeframe",
        result.price_rule_by_timeframe,
        title="Dukascopy Rule Backtest By Timeframe",
    )
    _write_frame_pair(
        output_root / "dukascopy_guru_price_only_test",
        result.guru_price_test,
        title="Dukascopy Guru Price-Only Test",
    )
    _write_frame_pair(
        output_root / "dukascopy_cme_overlap_validation",
        result.cme_overlap_validation,
        title="Dukascopy CME Overlap Validation",
    )
    _write_frame_pair(
        output_root / "forward_outcomes_with_dukascopy",
        result.forward_outcomes,
        title="Forward Outcomes With Dukascopy",
    )
    _write_frame_pair(
        output_root / "dukascopy_data_readiness_summary",
        result.readiness_summary,
        title="Dukascopy Data Readiness Summary",
    )
    _write_cache_manifest(
        output_root=output_root,
        source_path=source_path,
        cache_key=cache_key,
        result=result,
    )


def dukascopy_report_lines(result: DukascopySpotIntegrationResult | None) -> list[str]:
    """Return research_report.md sections for this layer."""

    if result is None:
        return [
            "## Dukascopy XAUUSD Data Integration",
            "",
            "Dukascopy integration layer was not run.",
        ]
    validation_row = pl.DataFrame(
        [
            {
                "row_count": result.validation.row_count,
                "date_start": result.validation.date_start,
                "date_end": result.validation.date_end,
                "missing_minutes": result.validation.missing_minutes,
                "duplicate_timestamps": result.validation.duplicate_timestamps,
                "suspicious_candles": result.validation.suspicious_candles,
                "max_spread": result.validation.max_spread,
                "average_spread": result.validation.average_spread,
                "validation_pass": result.validation.validation_pass,
            }
        ]
    )
    return [
        "## Dukascopy XAUUSD Data Integration",
        "",
        "Dukascopy XAUUSD bid/ask data is used as the primary spot price/outcome source "
        "where the cleaned file validates. CME OI/IV coverage remains separate.",
        "",
        "## Clean/Validation Report",
        "",
        _frame_markdown(validation_row),
        "",
        "## Resampled OHLC Coverage",
        "",
        _frame_markdown(result.resample_report),
        "",
        "## Price Source Priority",
        "",
        _frame_markdown(result.price_source_priority),
        "",
        "## Dukascopy Price-Only Rule Backtest",
        "",
        _frame_markdown(result.price_rule_backtest),
        "",
        "## Guru Logic Price-Only Test",
        "",
        _frame_markdown(result.guru_price_test),
        "",
        "## CME Overlap Pilot",
        "",
        _frame_markdown(result.cme_overlap_validation),
        "",
        "## Forward Outcome Resolution With Dukascopy",
        "",
        _frame_markdown(result.forward_outcomes),
        "",
        "## What Can Be Tested Now",
        "",
        _frame_markdown(result.readiness_summary),
    ]


def count_missing_gaps(frame: pl.DataFrame, timeframe: str) -> int:
    """Count timestamp gaps larger than the expected interval."""

    if frame.is_empty() or "timestamp" not in frame.columns or frame.height < 2:
        return 0
    seconds = _timeframe_seconds(timeframe)
    if seconds <= 0:
        return 0
    timestamps = [
        _parse_datetime(value)
        for value in frame.sort("timestamp").get_column("timestamp").to_list()
    ]
    clean = [value for value in timestamps if value is not None]
    return sum(
        1
        for left, right in zip(clean, clean[1:], strict=False)
        if (right - left).total_seconds() > seconds * 1.5
    )


def report_text_is_safe(text: str) -> bool:
    """Return whether report text avoids forbidden claims and local paths."""

    try:
        _safe_report_text(text)
    except ValueError:
        return False
    return True


def _price_rule_events(
    frame: pl.DataFrame,
    *,
    timeframe: str,
    horizon_bars: int,
) -> list[dict[str, Any]]:
    if frame.is_empty() or frame.height < 40:
        return []
    rows = frame.sort("timestamp").to_dicts()
    lookback = _lookback_for_timeframe(timeframe)
    events: list[dict[str, Any]] = []
    session_open_by_date: dict[str, float] = {}
    for row in rows:
        session_open_by_date.setdefault(str(row["trade_date"]), float(row["mid_open"]))
    for index in range(lookback, max(lookback, len(rows) - horizon_bars)):
        current = rows[index]
        previous = rows[index - lookback : index]
        future = rows[index + horizon_bars]
        prior_high = max(float(row["mid_high"]) for row in previous)
        prior_low = min(float(row["mid_low"]) for row in previous)
        width = max(prior_high - prior_low, 1e-9)
        close = float(current["mid_close"])
        open_price = float(current["mid_open"])
        spread = max(float(current.get("spread_close") or 0.0), 0.0)
        session_open = session_open_by_date.get(str(current["trade_date"]), open_price)
        middle_lower = prior_low + width * 0.40
        middle_upper = prior_low + width * 0.60
        rv_band = _realized_vol_band(previous)
        long_pnl = _long_pnl(current, future)
        short_pnl = _short_pnl(current, future)
        if middle_lower <= close <= middle_upper:
            events.append(
                _event_row(
                    current,
                    rule="NO_TRADE_MIDDLE_RANGE",
                    direction="filter",
                    pnl=min(long_pnl, short_pnl),
                    long_pnl=long_pnl,
                    short_pnl=short_pnl,
                    spread=spread,
                )
            )
        if abs(close - session_open) <= max(spread * 3.0, width * 0.05):
            events.append(
                _event_row(
                    current,
                    rule="OPEN_DISTANCE_FILTER",
                    direction="filter",
                    pnl=min(long_pnl, short_pnl),
                    long_pnl=long_pnl,
                    short_pnl=short_pnl,
                    spread=spread,
                )
            )
        if close > prior_high and open_price > prior_high:
            events.append(
                _event_row(
                    current,
                    rule="ACCEPTANCE_BREAKOUT",
                    direction="long",
                    pnl=long_pnl,
                    long_pnl=long_pnl,
                    short_pnl=short_pnl,
                    spread=spread,
                )
            )
        elif close < prior_low and open_price < prior_low:
            events.append(
                _event_row(
                    current,
                    rule="ACCEPTANCE_BREAKOUT",
                    direction="short",
                    pnl=short_pnl,
                    long_pnl=long_pnl,
                    short_pnl=short_pnl,
                    spread=spread,
                )
            )
        if float(current["mid_high"]) >= prior_high and close < prior_high:
            events.append(
                _event_row(
                    current,
                    rule="REJECTION_AFTER_LEVEL_TOUCH",
                    direction="short",
                    pnl=short_pnl,
                    long_pnl=long_pnl,
                    short_pnl=short_pnl,
                    spread=spread,
                )
            )
        if float(current["mid_low"]) <= prior_low and close > prior_low:
            events.append(
                _event_row(
                    current,
                    rule="REJECTION_AFTER_LEVEL_TOUCH",
                    direction="long",
                    pnl=long_pnl,
                    long_pnl=long_pnl,
                    short_pnl=short_pnl,
                    spread=spread,
                )
            )
        if rv_band is not None and close > rv_band["upper"]:
            events.append(
                _event_row(
                    current,
                    rule="IV_EXPECTED_RANGE_FILTER",
                    direction="short",
                    pnl=short_pnl,
                    long_pnl=long_pnl,
                    short_pnl=short_pnl,
                    spread=spread,
                    note="REALIZED_VOL_PROXY",
                )
            )
        elif rv_band is not None and close < rv_band["lower"]:
            events.append(
                _event_row(
                    current,
                    rule="IV_EXPECTED_RANGE_FILTER",
                    direction="long",
                    pnl=long_pnl,
                    long_pnl=long_pnl,
                    short_pnl=short_pnl,
                    spread=spread,
                    note="REALIZED_VOL_PROXY",
                )
            )
        if abs(float(future["mid_close"]) - close) <= spread * 2.0:
            events.append(
                _event_row(
                    current,
                    rule="FEE_SPREAD_HURDLE",
                    direction="filter",
                    pnl=min(long_pnl, short_pnl),
                    long_pnl=long_pnl,
                    short_pnl=short_pnl,
                    spread=spread,
                )
            )
    return events


def _metrics_row(events: list[dict[str, Any]], *, timeframe: str, rule: str) -> dict[str, Any]:
    pnl = [float(event["pnl_points"]) for event in events]
    wins = [value for value in pnl if value > 0]
    losses = [value for value in pnl if value < 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    equity = []
    running = 0.0
    for value in pnl:
        running += value
        equity.append(running)
    return {
        "timeframe": timeframe,
        "rule": rule,
        "trade_count": len(events),
        "win_rate": len(wins) / len(pnl) if pnl else None,
        "avg_win": sum(wins) / len(wins) if wins else 0.0,
        "avg_loss": sum(losses) / len(losses) if losses else 0.0,
        "expectancy": sum(pnl) / len(pnl) if pnl else None,
        "profit_factor": gross_win / gross_loss if gross_loss > 0 else None,
        "max_drawdown": _max_drawdown(equity),
        "spread_cost_estimate": sum(float(event["spread_cost_estimate"]) for event in events),
        "long_pnl": sum(float(event["long_pnl"]) for event in events),
        "short_pnl": sum(float(event["short_pnl"]) for event in events),
        "sample_size_warning": len(events) < 30,
        "source": "DUKASCOPY_PRICE_ONLY",
        "notes": "REALIZED_VOL_PROXY" if rule == "IV_EXPECTED_RANGE_FILTER" else "",
    }


def _event_row(
    row: dict[str, Any],
    *,
    rule: str,
    direction: str,
    pnl: float,
    long_pnl: float,
    short_pnl: float,
    spread: float,
    note: str = "",
) -> dict[str, Any]:
    return {
        "timestamp": row["timestamp"],
        "trade_date": row["trade_date"],
        "rule": rule,
        "direction": direction,
        "pnl_points": pnl,
        "long_pnl": long_pnl,
        "short_pnl": short_pnl,
        "spread_cost_estimate": spread,
        "note": note,
    }


def _long_pnl(entry: dict[str, Any], exit_row: dict[str, Any]) -> float:
    entry_price = float(entry.get("ask_close") or entry["mid_close"])
    exit_price = float(exit_row.get("bid_close") or exit_row["mid_close"])
    return exit_price - entry_price


def _short_pnl(entry: dict[str, Any], exit_row: dict[str, Any]) -> float:
    entry_price = float(entry.get("bid_close") or entry["mid_close"])
    exit_price = float(exit_row.get("ask_close") or exit_row["mid_close"])
    return entry_price - exit_price


def _realized_vol_band(previous: list[dict[str, Any]]) -> dict[str, float] | None:
    closes = [float(row["mid_close"]) for row in previous]
    if len(closes) < 10:
        return None
    returns = [right - left for left, right in zip(closes, closes[1:], strict=False)]
    mean = sum(returns) / len(returns)
    variance = sum((value - mean) ** 2 for value in returns) / len(returns)
    sd = math.sqrt(max(variance, 0.0))
    anchor = closes[-1]
    return {"upper": anchor + 2.0 * sd, "lower": anchor - 2.0 * sd}


def _write_frame_pair(path_stem: Path, frame: pl.DataFrame, *, title: str) -> None:
    frame.write_csv(path_stem.with_suffix(".csv"))
    path_stem.with_suffix(".md").write_text(
        _safe_report_text("\n\n".join([f"# {title}", "", _frame_markdown(frame)])),
        encoding="utf-8",
    )


def _source_cache_key(
    source: Path,
    *,
    abnormal_spread_points: float,
) -> dict[str, Any]:
    stat = source.stat()
    return {
        "cache_schema_version": CACHE_SCHEMA_VERSION,
        "source_file_name": source.name,
        "source_size_bytes": stat.st_size,
        "source_modified_ns": stat.st_mtime_ns,
        "abnormal_spread_points": float(abnormal_spread_points),
    }


def _load_cached_result(
    output_root: Path,
    *,
    expected_cache_key: dict[str, Any],
) -> DukascopySpotIntegrationResult | None:
    manifest_path = output_root / CACHE_MANIFEST_NAME
    if not manifest_path.exists():
        return None
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if payload.get("cache_key") != expected_cache_key:
        return None
    if not all((output_root / name).exists() for name in _cache_required_output_names()):
        return None
    validation = _validation_from_cache_payload(payload.get("validation", {}))
    spread_report = _read_cached_csv(
        output_root / "dukascopy_xau_spread_report.csv",
        _spread_report_schema(),
    )
    resample_report = _read_cached_csv(
        output_root / "dukascopy_resample_report.csv",
        _resample_report_schema(),
    )
    price_source_priority = _read_cached_csv(
        output_root / "price_source_priority_report.csv",
        _price_priority_schema(),
    )
    price_rule_backtest = _read_cached_csv(
        output_root / "dukascopy_price_only_rule_backtest.csv",
        _price_rule_schema(),
    )
    price_rule_by_timeframe = _read_cached_csv(
        output_root / "dukascopy_rule_backtest_by_timeframe.csv",
        _price_rule_timeframe_schema(),
    )
    guru_price_test = _read_cached_csv(
        output_root / "dukascopy_guru_price_only_test.csv",
        _guru_price_schema(),
    )
    cme_overlap_validation = _read_cached_csv(
        output_root / "dukascopy_cme_overlap_validation.csv",
        _cme_overlap_schema(),
    )
    forward_outcomes = _read_cached_csv(
        output_root / "forward_outcomes_with_dukascopy.csv",
        _forward_outcome_schema(),
    )
    readiness_summary = _read_cached_csv(
        output_root / "dukascopy_data_readiness_summary.csv",
        _readiness_schema(),
    )
    labels = payload.get("final_labels")
    if not isinstance(labels, list):
        labels = (
            readiness_summary.get_column("label").to_list()
            if "label" in readiness_summary.columns
            else []
        )
    return DukascopySpotIntegrationResult(
        validation=validation,
        spread_report=spread_report,
        resample_report=resample_report,
        price_source_priority=price_source_priority,
        price_rule_backtest=price_rule_backtest,
        price_rule_by_timeframe=price_rule_by_timeframe,
        guru_price_test=guru_price_test,
        cme_overlap_validation=cme_overlap_validation,
        forward_outcomes=forward_outcomes,
        readiness_summary=readiness_summary,
        final_labels=tuple(str(label) for label in labels),
        paths=_output_paths(output_root),
    )


def _write_cache_manifest(
    *,
    output_root: Path,
    source_path: Path,
    cache_key: dict[str, Any],
    result: DukascopySpotIntegrationResult,
) -> None:
    payload = {
        "cache_schema_version": CACHE_SCHEMA_VERSION,
        "generated_at_utc": datetime.now(tz=UTC).isoformat(),
        "cache_key": cache_key,
        "source": {
            "redacted_path": redact_path(source_path),
            "file_name": source_path.name,
        },
        "validation": asdict(result.validation),
        "final_labels": list(result.final_labels),
        "outputs": {name: path.name for name, path in result.paths.items()},
    }
    (output_root / CACHE_MANIFEST_NAME).write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _validation_from_cache_payload(payload: dict[str, Any]) -> DukascopyValidation:
    return DukascopyValidation(
        row_count=int(payload.get("row_count") or 0),
        date_start=str(payload.get("date_start") or ""),
        date_end=str(payload.get("date_end") or ""),
        missing_minutes=int(payload.get("missing_minutes") or 0),
        duplicate_timestamps=int(payload.get("duplicate_timestamps") or 0),
        suspicious_candles=int(payload.get("suspicious_candles") or 0),
        max_spread=_float_or_none(payload.get("max_spread")),
        average_spread=_float_or_none(payload.get("average_spread")),
        abnormal_spread_count=int(payload.get("abnormal_spread_count") or 0),
        validation_pass=bool(payload.get("validation_pass")),
        warnings=tuple(str(item) for item in payload.get("warnings", []) if item),
    )


def _read_cached_csv(path: Path, schema: dict[str, Any]) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame(schema=schema)
    try:
        return pl.read_csv(path)
    except Exception:  # noqa: BLE001 - corrupt cache should rebuild next run.
        return pl.DataFrame(schema=schema)


def _cache_required_output_names() -> tuple[str, ...]:
    names = [
        CACHE_MANIFEST_NAME,
        "dukascopy_xau_m1_mid.parquet",
        "xau_spot_dukascopy_m1.parquet",
        "cme_canonical_xau_spot_price_from_dukascopy.parquet",
        "dukascopy_xau_spread_report.csv",
        "dukascopy_xau_spread_report.md",
        "dukascopy_resample_report.csv",
        "dukascopy_resample_report.md",
        "price_source_priority_report.csv",
        "price_source_priority_report.md",
        "dukascopy_price_only_rule_backtest.csv",
        "dukascopy_price_only_rule_backtest.md",
        "dukascopy_rule_backtest_by_timeframe.csv",
        "dukascopy_rule_backtest_by_timeframe.md",
        "dukascopy_guru_price_only_test.csv",
        "dukascopy_guru_price_only_test.md",
        "dukascopy_cme_overlap_validation.csv",
        "dukascopy_cme_overlap_validation.md",
        "forward_outcomes_with_dukascopy.csv",
        "forward_outcomes_with_dukascopy.md",
        "dukascopy_data_readiness_summary.csv",
        "dukascopy_data_readiness_summary.md",
    ]
    for timeframe in TIMEFRAMES:
        names.append(f"dukascopy_xau_{timeframe}.parquet")
        names.append(f"xau_spot_dukascopy_{timeframe}.parquet")
    return tuple(names)


def _write_missing_outputs(
    output_root: Path,
    result: DukascopySpotIntegrationResult,
) -> None:
    for stem, frame, title in [
        ("dukascopy_xau_spread_report", result.spread_report, "Dukascopy Spread Report"),
        ("dukascopy_resample_report", result.resample_report, "Dukascopy Resample Report"),
        ("price_source_priority_report", result.price_source_priority, "Price Source Priority"),
        (
            "dukascopy_data_readiness_summary",
            result.readiness_summary,
            "Dukascopy Data Readiness Summary",
        ),
    ]:
        _write_frame_pair(output_root / stem, frame, title=title)


def _empty_result(validation: DukascopyValidation, output_root: Path) -> DukascopySpotIntegrationResult:
    readiness = build_data_readiness_summary(
        validation=validation,
        price_backtest=pl.DataFrame(schema=_price_rule_schema()),
        guru_test=pl.DataFrame(schema=_guru_price_schema()),
        cme_overlap=pl.DataFrame(schema=_cme_overlap_schema()),
        forward_outcomes=pl.DataFrame(schema=_forward_outcome_schema()),
    )
    return DukascopySpotIntegrationResult(
        validation=validation,
        spread_report=pl.DataFrame(schema=_spread_report_schema()),
        resample_report=pl.DataFrame(schema=_resample_report_schema()),
        price_source_priority=pl.DataFrame(schema=_price_priority_schema()),
        price_rule_backtest=pl.DataFrame(schema=_price_rule_schema()),
        price_rule_by_timeframe=pl.DataFrame(schema=_price_rule_timeframe_schema()),
        guru_price_test=pl.DataFrame(schema=_guru_price_schema()),
        cme_overlap_validation=pl.DataFrame(schema=_cme_overlap_schema()),
        forward_outcomes=pl.DataFrame(schema=_forward_outcome_schema()),
        readiness_summary=readiness,
        final_labels=tuple(readiness.get_column("label").to_list()),
        paths=_output_paths(output_root),
    )


def _glob_source_row(
    priority: int,
    source_name: str,
    source_type: str,
    root: Path,
    patterns: tuple[str, ...],
    *,
    selected: bool,
    limitation: str,
) -> dict[str, Any]:
    candidates: list[Path] = []
    for pattern in patterns:
        if root.exists():
            candidates.extend(root.glob(pattern))
    latest = max(candidates, key=lambda item: item.stat().st_mtime) if candidates else None
    return {
        "priority": priority,
        "source_name": source_name,
        "source_type": source_type,
        "available": latest is not None,
        "selected": selected,
        "limitation": limitation,
        "redacted_path": redact_path(latest) if latest else "",
    }


def _spot_alias_frame(frame: pl.DataFrame, timeframe: str) -> pl.DataFrame:
    if frame.is_empty():
        return _empty_alias_price()
    return frame.select(
        [
            "timestamp",
            "trade_date",
            "open",
            "high",
            "low",
            "close",
            "spread_points",
            "bid_open",
            "bid_high",
            "bid_low",
            "bid_close",
            "ask_open",
            "ask_high",
            "ask_low",
            "ask_close",
            "spread_available",
            "price_source_label",
        ]
    ).with_columns(
        [
            pl.lit(timeframe).alias("timeframe"),
            pl.col("close").alias("spot_price"),
        ]
    )


def _top_wall(frame: pl.DataFrame) -> float | None:
    if frame.is_empty():
        return None
    strike_col = _first_existing(
        {_normalize_name(column): column for column in frame.columns},
        ("strike", "option_strike", "cme_option_strike"),
    )
    if strike_col is None:
        return None
    score_col = _first_existing(
        {_normalize_name(column): column for column in frame.columns},
        ("total_oi", "open_interest", "oi", "call_oi", "put_oi"),
    )
    working = frame.with_columns(pl.col(strike_col).cast(pl.Float64, strict=False).alias("_strike"))
    if score_col is not None:
        working = working.with_columns(
            pl.col(score_col).cast(pl.Float64, strict=False).alias("_score")
        )
    else:
        working = working.with_columns(pl.lit(1.0).alias("_score"))
    rows = working.drop_nulls("_strike").sort("_score", descending=True).head(1).to_dicts()
    return _float_or_none(rows[0]["_strike"]) if rows else None


def _wall_reaction(frame: pl.DataFrame, wall_level: float | None) -> dict[str, bool]:
    base = {
        "wall_touch": False,
        "wall_rejection": False,
        "wall_acceptance": False,
        "squeeze_gap_followthrough": False,
        "pin_behavior": False,
    }
    if frame.is_empty() or wall_level is None:
        return base
    high = _column_float(frame, "mid_high", "max")
    low = _column_float(frame, "mid_low", "min")
    close = _last_float(frame, "mid_close")
    open_price = _first_float(frame, "mid_open")
    if high is None or low is None or close is None or open_price is None:
        return base
    touched = bool(low <= wall_level <= high)
    rejected = touched and abs(close - wall_level) > abs(open_price - wall_level)
    accepted = touched and ((open_price < wall_level < close) or (open_price > wall_level > close))
    base["wall_touch"] = touched
    base["wall_rejection"] = rejected
    base["wall_acceptance"] = accepted
    base["squeeze_gap_followthrough"] = accepted and abs(close - wall_level) > (high - low) * 0.25
    base["pin_behavior"] = touched and abs(close - wall_level) <= max((high - low) * 0.10, 1.0)
    return base


def _cme_validation_grade(
    *,
    has_price: bool,
    has_oi: bool,
    has_iv: bool,
    has_futures: bool,
    has_basis: bool,
    pilot_only: bool,
) -> str:
    if has_price and has_oi and has_iv and has_futures and has_basis:
        return "CME_PILOT_ONLY" if pilot_only else "FULL_CME_VOL_OI_CANDIDATE"
    if has_price and (has_oi or has_iv):
        return "CME_PILOT_ONLY"
    if has_price:
        return "PRICE_ONLY"
    return "UNUSABLE"


def _prior_resolved_keys(frame: pl.DataFrame) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    if frame.is_empty():
        return keys
    for row in frame.to_dicts():
        status = " ".join(str(row.get(key) or "") for key in ("outcome_status", "resolution_action"))
        if "resolve" in status.lower() or "completed" in status.lower():
            keys.add((str(row.get("journal_id") or ""), str(row.get("window") or "")))
    return keys


def _slice_window(frame: pl.DataFrame, start: datetime, end: datetime) -> pl.DataFrame:
    if frame.is_empty():
        return frame
    return frame.filter((pl.col("timestamp") >= start) & (pl.col("timestamp") <= end))


def _mfe(frame: pl.DataFrame) -> float | None:
    if frame.is_empty():
        return None
    first = _first_float(frame, "mid_close")
    high = _column_float(frame, "mid_high", "max")
    return high - first if first is not None and high is not None else None


def _mae(frame: pl.DataFrame) -> float | None:
    if frame.is_empty():
        return None
    first = _first_float(frame, "mid_close")
    low = _column_float(frame, "mid_low", "min")
    return low - first if first is not None and low is not None else None


def _rate_for_rule(frame: pl.DataFrame, rule: str) -> float | None:
    if frame.is_empty() or "rule" not in frame.columns:
        return None
    subset = frame.filter(pl.col("rule") == rule)
    if subset.is_empty():
        return None
    count = int(subset.get_column("trade_count").sum())
    if count <= 0:
        return None
    wins = subset.with_columns(
        (pl.col("win_rate").fill_null(0.0) * pl.col("trade_count")).alias("_wins")
    ).get_column("_wins").sum()
    return float(wins) / count


def _avoided_loss_proxy(frame: pl.DataFrame) -> float | None:
    if frame.is_empty() or "expectancy" not in frame.columns:
        return None
    losses = [
        abs(float(row.get("expectancy") or 0.0)) * int(row.get("trade_count") or 0)
        for row in frame.to_dicts()
        if float(row.get("expectancy") or 0.0) < 0
    ]
    return sum(losses) if losses else 0.0


def _false_block_rate(frame: pl.DataFrame) -> float | None:
    if frame.is_empty() or "trade_count" not in frame.columns:
        return None
    total = int(frame.get_column("trade_count").sum())
    if total <= 0:
        return None
    positive = sum(
        int(row.get("trade_count") or 0)
        for row in frame.to_dicts()
        if float(row.get("expectancy") or 0.0) > 0
    )
    return positive / total


def _timing_confirmed_count(output_dir: Path) -> int:
    candidates = [
        output_dir / "transcript_timing_metadata_audit.csv",
        output_dir / "transcript_timing_evidence.csv",
        output_dir / "transcript_rule_timeline.csv",
    ]
    for path in candidates:
        frame = _load_optional(path)
        if frame.is_empty():
            continue
        columns = {_normalize_name(column): column for column in frame.columns}
        timestamp_col = _first_existing(
            columns,
            ("availability_timestamp", "known_before_timestamp", "transcript_date"),
        )
        if timestamp_col is None:
            continue
        return frame.filter(pl.col(timestamp_col).is_not_null()).height
    return 0


def _any_true(frame: pl.DataFrame, column: str) -> bool:
    if frame.is_empty() or column not in frame.columns:
        return False
    return any(bool(value) for value in frame.get_column(column).to_list())


def _trade_dates(frame: pl.DataFrame) -> set[str]:
    if frame.is_empty():
        return set()
    if "trade_date" in frame.columns:
        return {str(value) for value in frame["trade_date"].to_list() if value}
    date_col = _first_existing(
        {_normalize_name(column): column for column in frame.columns},
        ("timestamp", "datetime", "asof_timestamp", "date"),
    )
    if date_col is None:
        return set()
    return {
        text
        for value in frame[date_col].to_list()
        if (text := _date_text(value))
    }


def _date_rows(frame: pl.DataFrame, trade_date: str) -> pl.DataFrame:
    if frame.is_empty():
        return frame
    if "trade_date" in frame.columns:
        return frame.filter(pl.col("trade_date").cast(pl.String) == trade_date)
    date_col = _first_existing(
        {_normalize_name(column): column for column in frame.columns},
        ("timestamp", "datetime", "asof_timestamp", "date"),
    )
    if date_col is None:
        return frame.clear()
    return frame.filter(pl.col(date_col).cast(pl.String).str.slice(0, 10) == trade_date)


def _last_numeric(frame: pl.DataFrame, candidates: tuple[str, ...]) -> float | None:
    if frame.is_empty():
        return None
    columns = {_normalize_name(column): column for column in frame.columns}
    selected = _first_existing(columns, candidates)
    if selected is None:
        return None
    values = [
        _float_or_none(value)
        for value in frame.get_column(selected).to_list()
        if _float_or_none(value) is not None
    ]
    return values[-1] if values else None


def _load_optional(path: Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    try:
        if path.suffix.lower() == ".parquet":
            return pl.read_parquet(path)
        if path.suffix.lower() == ".csv":
            return pl.read_csv(path, infer_schema_length=1000)
    except Exception:
        return pl.DataFrame()
    return pl.DataFrame()


def _normalize_timestamp(frame: pl.DataFrame, timestamp_col: str) -> pl.DataFrame:
    dtype = frame.schema.get(timestamp_col)
    if str(dtype).startswith("Datetime"):
        return frame.with_columns(
            pl.col(timestamp_col).dt.convert_time_zone("UTC").alias("timestamp")
        )
    return frame.with_columns(
        pl.col(timestamp_col)
        .cast(pl.String, strict=False)
        .str.replace(r"\+0000$", "+00:00")
        .str.to_datetime(strict=False, time_zone="UTC")
        .alias("timestamp")
    )


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _column_datetime(frame: pl.DataFrame, column: str, op: str) -> datetime | None:
    if frame.is_empty() or column not in frame.columns:
        return None
    expr = pl.col(column).min() if op == "min" else pl.col(column).max()
    return _parse_datetime(frame.select(expr).item())


def _column_float(frame: pl.DataFrame, column: str, op: str) -> float | None:
    if frame.is_empty() or column not in frame.columns:
        return None
    if op == "min":
        value = frame.select(pl.col(column).min()).item()
    elif op == "max":
        value = frame.select(pl.col(column).max()).item()
    else:
        value = frame.select(pl.col(column).mean()).item()
    return _float_or_none(value)


def _first_float(frame: pl.DataFrame, column: str) -> float | None:
    if frame.is_empty() or column not in frame.columns:
        return None
    return _float_or_none(frame.get_column(column).head(1).item())


def _last_float(frame: pl.DataFrame, column: str) -> float | None:
    if frame.is_empty() or column not in frame.columns:
        return None
    return _float_or_none(frame.get_column(column).tail(1).item())


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(parsed) else parsed


def _weighted_average(frame: pl.DataFrame, value_col: str, weight_col: str) -> float | None:
    rows = frame.to_dicts()
    numerator = 0.0
    denominator = 0
    for row in rows:
        value = _float_or_none(row.get(value_col))
        weight = int(row.get(weight_col) or 0)
        if value is not None and weight > 0:
            numerator += value * weight
            denominator += weight
    return numerator / denominator if denominator else None


def _max_drawdown(equity: list[float]) -> float:
    peak = 0.0
    drawdown = 0.0
    for value in equity:
        peak = max(peak, value)
        drawdown = min(drawdown, value - peak)
    return drawdown


def _lookback_for_timeframe(timeframe: str) -> int:
    return {"15m": 96, "30m": 48, "1h": 24, "4h": 12, "1d": 20}.get(timeframe, 24)


def _polars_every(timeframe: str) -> str:
    mapping = {"5m": "5m", "15m": "15m", "30m": "30m", "1h": "1h", "4h": "4h", "1d": "1d"}
    if timeframe not in mapping:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    return mapping[timeframe]


def _timeframe_seconds(timeframe: str) -> int:
    return {
        "1m": 60,
        "5m": 300,
        "15m": 900,
        "30m": 1800,
        "1h": 3600,
        "4h": 14400,
        "1d": 86400,
    }.get(timeframe, 0)


def _iso(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _date_text(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    match = re.search(r"20\d{2}-\d{2}-\d{2}", str(value or ""))
    return match.group(0) if match else ""


def _normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def _first_existing(columns: dict[str, str], candidates: Iterable[str]) -> str | None:
    for candidate in candidates:
        match = columns.get(_normalize_name(candidate))
        if match is not None:
            return match
    return None


def redact_path(path: str | Path | None) -> str:
    """Return a stable redacted source reference."""

    if path is None:
        return ""
    source = Path(path)
    digest = hashlib.sha256(source.as_posix().encode("utf-8")).hexdigest()[:8]
    safe_name = re.sub(r"[^A-Za-z0-9_.=-]", "_", source.name)[:80] or "source"
    return f"<REDACTED_PATH>/{safe_name}|{digest}{source.suffix.lower()}"


def _safe_report_text(text: str) -> str:
    safe = re.sub(r"[A-Za-z]:[\\/]+Users[\\/]+[^`|\s,\"]+", "<REDACTED_PATH>", text)
    safe = re.sub(r"[A-Za-z]:[\\/]+[^`|\s,\"]+", "<REDACTED_PATH>", safe)
    safe = re.sub(r"/Users/[^`|\s,\"]+", "<REDACTED_PATH>", safe)
    lowered = safe.lower()
    for phrase in FORBIDDEN_REPORT_PHRASES:
        if phrase in lowered:
            raise ValueError(f"Forbidden report phrase: {phrase}")
    return safe


def _frame_markdown(frame: pl.DataFrame, *, limit: int = 20) -> str:
    if frame.is_empty():
        return "_No rows._"
    rows = ["| " + " | ".join(frame.columns) + " |"]
    rows.append("| " + " | ".join("---" for _ in frame.columns) + " |")
    for raw in frame.head(limit).to_dicts():
        rows.append("| " + " | ".join(_markdown_cell(raw.get(column, "")) for column in frame.columns) + " |")
    return "\n".join(rows)


def _markdown_cell(value: Any) -> str:
    return _safe_report_text(str(value).replace("|", "\\|").replace("\n", " "))[:700]


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


def _canonical_columns() -> list[str]:
    return [
        "timestamp",
        "trade_date",
        "bid_open",
        "bid_high",
        "bid_low",
        "bid_close",
        "ask_open",
        "ask_high",
        "ask_low",
        "ask_close",
        "mid_open",
        "mid_high",
        "mid_low",
        "mid_close",
        "spread_close",
        "spread_points",
        "source",
        "quality",
        "open",
        "high",
        "low",
        "close",
        "price_source_label",
        "spread_available",
    ]


def _resampled_columns() -> list[str]:
    return [*_canonical_columns(), "timeframe"]


def _output_paths(output_root: Path) -> dict[str, Path]:
    return {
        "canonical_m1": output_root / "dukascopy_xau_m1_mid.parquet",
        "spread_report_csv": output_root / "dukascopy_xau_spread_report.csv",
        "spread_report_md": output_root / "dukascopy_xau_spread_report.md",
        "resample_report_csv": output_root / "dukascopy_resample_report.csv",
        "price_backtest_csv": output_root / "dukascopy_price_only_rule_backtest.csv",
        "guru_price_test_csv": output_root / "dukascopy_guru_price_only_test.csv",
        "cme_overlap_csv": output_root / "dukascopy_cme_overlap_validation.csv",
        "forward_outcomes_csv": output_root / "forward_outcomes_with_dukascopy.csv",
        "readiness_md": output_root / "dukascopy_data_readiness_summary.md",
        "cache_manifest": output_root / CACHE_MANIFEST_NAME,
    }


def _empty_canonical() -> pl.DataFrame:
    return pl.DataFrame(schema={column: pl.String for column in _canonical_columns()})


def _empty_resampled() -> pl.DataFrame:
    return pl.DataFrame(schema={column: pl.String for column in _resampled_columns()})


def _empty_alias_price() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "timestamp": pl.Datetime(time_zone="UTC"),
            "trade_date": pl.String,
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "spot_price": pl.Float64,
        }
    )


def _spread_report_schema() -> dict[str, Any]:
    return {
        "source": pl.String,
        "redacted_source_path": pl.String,
        "rows": pl.Int64,
        "date_start": pl.String,
        "date_end": pl.String,
        "validation_pass": pl.Boolean,
        "abnormal_spread_threshold_points": pl.Float64,
        "min_spread": pl.Float64,
        "average_spread": pl.Float64,
        "median_spread": pl.Float64,
        "p95_spread": pl.Float64,
        "p99_spread": pl.Float64,
        "max_spread": pl.Float64,
        "negative_spread_count": pl.Int64,
        "zero_spread_count": pl.Int64,
        "abnormal_spread_count": pl.Int64,
    }


def _resample_report_schema() -> dict[str, Any]:
    return {
        "timeframe": pl.String,
        "rows": pl.Int64,
        "date_start": pl.String,
        "date_end": pl.String,
        "missing_gaps": pl.Int64,
        "average_spread": pl.Float64,
        "max_spread": pl.Float64,
        "quality_flag": pl.String,
    }


def _price_priority_schema() -> dict[str, Any]:
    return {
        "priority": pl.Int64,
        "source_name": pl.String,
        "source_type": pl.String,
        "available": pl.Boolean,
        "selected": pl.Boolean,
        "limitation": pl.String,
        "redacted_path": pl.String,
    }


def _price_rule_schema() -> dict[str, Any]:
    return {
        "timeframe": pl.String,
        "rule": pl.String,
        "trade_count": pl.Int64,
        "win_rate": pl.Float64,
        "avg_win": pl.Float64,
        "avg_loss": pl.Float64,
        "expectancy": pl.Float64,
        "profit_factor": pl.Float64,
        "max_drawdown": pl.Float64,
        "spread_cost_estimate": pl.Float64,
        "long_pnl": pl.Float64,
        "short_pnl": pl.Float64,
        "sample_size_warning": pl.Boolean,
        "source": pl.String,
        "notes": pl.String,
    }


def _price_rule_timeframe_schema() -> dict[str, Any]:
    return {
        "timeframe": pl.String,
        "rule_count": pl.Int64,
        "trade_count": pl.Int64,
        "expectancy": pl.Float64,
        "long_pnl": pl.Float64,
        "short_pnl": pl.Float64,
        "sample_size_warning": pl.Boolean,
    }


def _guru_price_schema() -> dict[str, Any]:
    return {
        "test_name": pl.String,
        "event_count": pl.Int64,
        "timing_confirmed_event_count": pl.Int64,
        "context_only_event_count": pl.Int64,
        "avoided_loss_proxy": pl.Float64,
        "false_block_rate": pl.Float64,
        "breakout_followthrough_rate": pl.Float64,
        "rejection_followthrough_rate": pl.Float64,
        "sample_size_warning": pl.Boolean,
        "leakage_warning": pl.String,
    }


def _cme_overlap_schema() -> dict[str, Any]:
    return {
        "trade_date": pl.String,
        "has_dukascopy_spot": pl.Boolean,
        "has_gc_futures": pl.Boolean,
        "basis_available": pl.Boolean,
        "has_cme_oi": pl.Boolean,
        "has_cme_iv": pl.Boolean,
        "can_test_oi_wall": pl.Boolean,
        "can_test_iv_range": pl.Boolean,
        "wall_touch": pl.Boolean,
        "wall_rejection": pl.Boolean,
        "wall_acceptance": pl.Boolean,
        "squeeze_gap_followthrough": pl.Boolean,
        "pin_behavior": pl.Boolean,
        "validation_grade": pl.String,
    }


def _forward_outcome_schema() -> dict[str, Any]:
    return {
        "journal_id": pl.String,
        "window": pl.String,
        "window_start": pl.String,
        "window_end": pl.String,
        "prior_yahoo_resolution": pl.String,
        "dukascopy_resolution": pl.String,
        "newly_resolved": pl.Boolean,
        "still_pending": pl.Boolean,
        "open": pl.Float64,
        "high": pl.Float64,
        "low": pl.Float64,
        "close": pl.Float64,
        "mfe_mid": pl.Float64,
        "mae_mid": pl.Float64,
        "bid_ask_mid_difference_points": pl.Float64,
        "source": pl.String,
    }


def _readiness_schema() -> dict[str, Any]:
    return {
        "question": pl.String,
        "answer": pl.String,
        "label": pl.String,
    }
