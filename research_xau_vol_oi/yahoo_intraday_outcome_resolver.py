"""Yahoo intraday fetch planning, resampling, and partial outcome resolution.

This module is research-only. It plans public Yahoo/yfinance OHLC fetches,
resamples local intraday bars, and previews covered forward-journal outcome
windows without creating journal rows, changing frozen rules, or using daily
OHLC as strict intraday evidence.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Iterable

import polars as pl

from research_xau_vol_oi.daily_forward_data_gate import (
    WINDOW_ORDER,
    expected_market_session_date,
    is_weekend,
    required_window_ranges,
)


PLAN_INTERVALS = ("1m", "5m", "15m", "30m", "60m", "1h", "4h", "1d")
YAHOO_DIRECT_INTERVALS = {
    "1m",
    "2m",
    "5m",
    "15m",
    "30m",
    "60m",
    "90m",
    "1h",
    "1d",
}
DEFAULT_YAHOO_SYMBOLS = ("GC=F", "XAUUSD=X")
REQUIRED_PLAN_SYMBOLS = ("GC=F", "XAUUSD=X", "GLD")
DEFAULT_YAHOO_INTERVALS = ("1m", "30m", "60m", "1h", "1d")
INTRADAY_WINDOWS = ("30m", "1h", "4h")
FETCH_DISABLED_NOTE = (
    "Fetch is disabled by default. Set XAU_ENABLE_YAHOO_INTRADAY_FETCH=true "
    "for a local public-data refresh."
)
RESEARCH_WARNING = (
    "Research-only evidence. No live trading, paper trading, broker "
    "integration, order execution, or money-readiness claim is included."
)
FORBIDDEN_REPORT_PHRASES = (
    "profitable",
    "guaranteed edge",
    "predicts price",
    "safe to trade",
    "live ready",
    "live-readiness evidence",
)


@dataclass(frozen=True)
class YahooIntradayConfig:
    """Environment-driven settings for local Yahoo intraday research."""

    enable_fetch: bool = False
    yahoo_symbols: tuple[str, ...] = DEFAULT_YAHOO_SYMBOLS
    yahoo_intervals: tuple[str, ...] = DEFAULT_YAHOO_INTERVALS
    yahoo_period: str = "7d"
    data_dir: Path = Path("data/yahoo_intraday")


@dataclass(frozen=True)
class LocalOhlcSource:
    """Normalized local OHLC source used by resampling and resolution."""

    symbol: str
    interval: str
    path: Path
    frame: pl.DataFrame
    quality: str


@dataclass(frozen=True)
class YahooIntradayOutcomeResolverResult:
    """Output frames and recommendation from the resolver layer."""

    fetch_plan: pl.DataFrame
    resample_coverage: pl.DataFrame
    partial_resolution: pl.DataFrame
    outcome_preview: pl.DataFrame
    status_scorecard: pl.DataFrame
    useful_evidence: pl.DataFrame
    final_recommendation: str
    paths: dict[str, Path]
    fetch_warnings: tuple[str, ...]


def load_config(
    *,
    env: dict[str, str] | None = None,
    data_dir: str | Path | None = None,
) -> YahooIntradayConfig:
    """Load resolver config without reading private files."""

    values = env if env is not None else os.environ
    configured_dir = Path(data_dir) if data_dir is not None else Path(
        values.get("XAU_YAHOO_INTRADAY_DATA_DIR", "data/yahoo_intraday")
    )
    return YahooIntradayConfig(
        enable_fetch=_env_bool(values.get("XAU_ENABLE_YAHOO_INTRADAY_FETCH"), False),
        yahoo_symbols=_split_env(values.get("XAU_YAHOO_SYMBOLS"), DEFAULT_YAHOO_SYMBOLS),
        yahoo_intervals=_split_env(
            values.get("XAU_YAHOO_INTERVALS"),
            DEFAULT_YAHOO_INTERVALS,
        ),
        yahoo_period=str(values.get("XAU_YAHOO_PERIOD") or "7d"),
        data_dir=configured_dir,
    )


def run_yahoo_intraday_outcome_resolver(
    *,
    output_dir: str | Path = "outputs",
    repo_root: str | Path = ".",
    config: YahooIntradayConfig | None = None,
    current_time: datetime | None = None,
    write_outputs: bool = True,
) -> YahooIntradayOutcomeResolverResult:
    """Run fetch planning, optional fetch, resampling, and resolution preview."""

    root = Path(repo_root)
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    now = _ensure_utc(current_time or datetime.now(UTC))
    cfg = config or load_config()

    coverage = _read_csv_frame(output_root / "outcome_coverage_check.csv")
    provider_audit = _read_csv_frame(output_root / "forward_data_provider_audit.csv")
    fetch_plan = build_yahoo_intraday_fetch_plan(
        repo_root=root,
        output_dir=output_root,
        coverage=coverage,
        provider_audit=provider_audit,
        config=cfg,
        current_time=now,
    )

    fetch_warnings: tuple[str, ...] = ()
    if cfg.enable_fetch:
        fetch_warnings = tuple(
            fetch_yahoo_intraday_ohlc(
                repo_root=root,
                config=cfg,
                current_time=now,
            )
        )

    sources = discover_local_ohlc_sources(repo_root=root, config=cfg)
    resample_coverage, derived_sources = build_intraday_resample_coverage(sources)
    partial_resolution = build_partial_outcome_resolution(coverage)
    outcome_preview = build_forward_outcome_preview(
        coverage=coverage,
        sources=[*sources, *derived_sources],
    )
    status_scorecard = build_forward_journal_scorecard(
        coverage=coverage,
        partial_resolution=partial_resolution,
    )
    useful_evidence = build_useful_evidence_summary(
        output_dir=output_root,
        coverage=coverage,
        status_scorecard=status_scorecard,
    )
    final_recommendation = choose_final_recommendation(
        fetch_plan=fetch_plan,
        status_scorecard=status_scorecard,
    )

    paths = {
        "fetch_plan_csv": output_root / "yahoo_intraday_fetch_plan.csv",
        "fetch_plan_md": output_root / "yahoo_intraday_fetch_plan.md",
        "resample_coverage_csv": output_root / "intraday_resample_coverage.csv",
        "resample_coverage_md": output_root / "intraday_resample_coverage.md",
        "partial_resolution_csv": output_root / "partial_outcome_resolution.csv",
        "partial_resolution_md": output_root / "partial_outcome_resolution.md",
        "outcome_preview_csv": output_root / "forward_evidence_outcomes_preview.csv",
        "status_report_md": output_root / "forward_journal_status_report.md",
        "scorecard_csv": output_root / "forward_journal_scorecard.csv",
        "useful_evidence_csv": output_root / "useful_evidence_so_far.csv",
        "useful_evidence_md": output_root / "useful_evidence_so_far.md",
    }
    if write_outputs:
        _write_artifacts(
            paths=paths,
            fetch_plan=fetch_plan,
            resample_coverage=resample_coverage,
            partial_resolution=partial_resolution,
            outcome_preview=outcome_preview,
            status_scorecard=status_scorecard,
            useful_evidence=useful_evidence,
            final_recommendation=final_recommendation,
            fetch_warnings=fetch_warnings,
        )

    return YahooIntradayOutcomeResolverResult(
        fetch_plan=fetch_plan,
        resample_coverage=resample_coverage,
        partial_resolution=partial_resolution,
        outcome_preview=outcome_preview,
        status_scorecard=status_scorecard,
        useful_evidence=useful_evidence,
        final_recommendation=final_recommendation,
        paths=paths,
        fetch_warnings=fetch_warnings,
    )


def build_yahoo_intraday_fetch_plan(
    *,
    repo_root: Path,
    output_dir: Path,
    coverage: pl.DataFrame,
    provider_audit: pl.DataFrame,
    config: YahooIntradayConfig,
    current_time: datetime,
) -> pl.DataFrame:
    """Build the requested Yahoo intraday fetch plan table."""

    del output_dir
    now = _ensure_utc(current_time)
    needed_until = _needed_until_timestamp(coverage, now)
    fetch_start = now - timedelta(days=_period_days(config.yahoo_period))
    market_closed = _market_closed(now.date())
    expected_session = expected_market_session_date(now.date())
    rows: list[dict[str, Any]] = []
    symbols = _ordered_unique([*config.yahoo_symbols, *REQUIRED_PLAN_SYMBOLS])
    for symbol in symbols:
        configured = symbol in config.yahoo_symbols or symbol == "GLD"
        for interval in PLAN_INTERVALS:
            purpose = _fetch_purpose(symbol, interval)
            can_fetch_directly = interval in YAHOO_DIRECT_INTERVALS and interval != "4h"
            if symbol == "XAUUSD=X" and not configured:
                can_fetch_directly = False
            current_latest = _latest_local_timestamp(
                repo_root=repo_root,
                provider_audit=provider_audit,
                symbol=symbol,
                interval=interval,
                config=config,
            )
            fetch_needed = bool(
                can_fetch_directly
                and purpose != "PROXY_ONLY"
                and not market_closed
                and (current_latest is None or current_latest < needed_until)
            )
            warning = _expected_limit_warning(interval, market_closed)
            notes = _fetch_plan_notes(
                symbol=symbol,
                interval=interval,
                configured=configured,
                market_closed=market_closed,
                expected_session=expected_session,
            )
            rows.append(
                {
                    "symbol": symbol,
                    "interval": interval,
                    "purpose": purpose,
                    "can_fetch_directly": can_fetch_directly,
                    "fetch_window_start": _iso(fetch_start),
                    "fetch_window_end": _iso(now),
                    "expected_limit_warning": warning,
                    "current_local_latest_timestamp": _iso(current_latest),
                    "needed_until_timestamp": _iso(needed_until),
                    "fetch_needed": fetch_needed,
                    "notes": notes,
                }
            )
    return pl.DataFrame(rows, schema=_fetch_plan_schema(), infer_schema_length=None)


def fetch_yahoo_intraday_ohlc(
    *,
    repo_root: Path,
    config: YahooIntradayConfig,
    current_time: datetime | None = None,
) -> list[str]:
    """Optionally fetch public Yahoo OHLC into ignored local data.

    The function never raises on network/provider failure. It returns warnings
    that are written into the local research report.
    """

    try:
        import yfinance as yf  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover - depends on local env
        return [f"yfinance import failed: {exc}"]

    now = _ensure_utc(current_time or datetime.now(UTC))
    target_dir = repo_root / config.data_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    for symbol in config.yahoo_symbols:
        for interval in config.yahoo_intervals:
            normalized_interval = interval.strip().lower()
            if normalized_interval == "4h":
                warnings.append("Skipped 4h direct fetch; use intraday resampling.")
                continue
            if normalized_interval not in YAHOO_DIRECT_INTERVALS:
                warnings.append(f"Skipped unsupported Yahoo interval {interval}.")
                continue
            try:
                history = yf.Ticker(symbol).history(
                    period=config.yahoo_period,
                    interval=normalized_interval,
                    auto_adjust=False,
                )
            except Exception as exc:  # pragma: no cover - network dependent
                warnings.append(f"Yahoo fetch failed for {symbol} {interval}: {exc}")
                continue
            try:
                frame = _normalize_yfinance_history(
                    history,
                    symbol=symbol,
                    interval=normalized_interval,
                )
            except ValueError as exc:
                warnings.append(str(exc))
                continue
            if frame.is_empty():
                warnings.append(f"Yahoo returned no rows for {symbol} {interval}.")
                continue
            slug = _symbol_slug(symbol)
            suffix = now.strftime("%Y%m%d_%H%M%S")
            frame.write_parquet(target_dir / f"{slug}_{normalized_interval}_ohlcv_{suffix}.parquet")
    return warnings


def discover_local_ohlc_sources(
    *,
    repo_root: Path,
    config: YahooIntradayConfig,
) -> list[LocalOhlcSource]:
    """Discover local Yahoo/proxy OHLC files without exposing absolute paths."""

    symbols = _ordered_unique([*config.yahoo_symbols, "GLD"])
    sources: list[LocalOhlcSource] = []
    for symbol in symbols:
        for interval in ("1m", "30m", "60m", "1h", "1d"):
            path = _latest_yahoo_path(repo_root, symbol=symbol, interval=interval, config=config)
            if path is None and interval == "60m":
                path = _latest_yahoo_path(repo_root, symbol=symbol, interval="1h", config=config)
            if path is None:
                continue
            try:
                frame = load_ohlc_frame(path)
            except ValueError:
                continue
            if frame.is_empty():
                continue
            sources.append(
                LocalOhlcSource(
                    symbol=symbol,
                    interval=interval,
                    path=path,
                    frame=frame,
                    quality=_source_quality(symbol, interval),
                )
            )
    return _dedupe_sources(sources)


def load_ohlc_frame(path: Path) -> pl.DataFrame:
    """Load a CSV or Parquet OHLC table into normalized UTC columns."""

    if not path.exists():
        raise ValueError(f"OHLC source does not exist: {redact_path(path)}")
    if path.suffix.lower() == ".parquet":
        frame = pl.read_parquet(path)
    elif path.suffix.lower() == ".csv":
        frame = pl.read_csv(path)
    else:
        raise ValueError(f"Unsupported OHLC format: {path.suffix}")
    if frame.is_empty():
        return _empty_ohlc_frame()
    column_map = _ohlc_column_map(frame.columns)
    missing = [name for name in ("timestamp", "open", "high", "low", "close") if name not in column_map]
    if missing:
        raise ValueError(f"Missing OHLC columns: {', '.join(missing)}")
    timestamp_col = column_map["timestamp"]
    volume_expr = (
        pl.col(column_map["volume"]).cast(pl.Float64, strict=False)
        if "volume" in column_map
        else pl.lit(None).cast(pl.Float64)
    )
    normalized = (
        frame.with_columns(
            [
                _timestamp_expr(frame, timestamp_col),
                pl.col(column_map["open"]).cast(pl.Float64, strict=False).alias("open"),
                pl.col(column_map["high"]).cast(pl.Float64, strict=False).alias("high"),
                pl.col(column_map["low"]).cast(pl.Float64, strict=False).alias("low"),
                pl.col(column_map["close"]).cast(pl.Float64, strict=False).alias("close"),
                volume_expr.alias("volume"),
            ]
        )
        .select(["timestamp", "open", "high", "low", "close", "volume"])
        .drop_nulls(subset=["timestamp", "open", "high", "low", "close"])
        .unique(subset=["timestamp"], keep="last")
        .sort("timestamp")
    )
    invalid = normalized.filter(
        (pl.col("high") < pl.col("low"))
        | (pl.col("high") < pl.col("open"))
        | (pl.col("high") < pl.col("close"))
        | (pl.col("low") > pl.col("open"))
        | (pl.col("low") > pl.col("close"))
    )
    if invalid.height:
        raise ValueError("Invalid OHLC values: high/low do not bound open/close.")
    return normalized


def build_intraday_resample_coverage(
    sources: Iterable[LocalOhlcSource],
) -> tuple[pl.DataFrame, list[LocalOhlcSource]]:
    """Build 30m, 1h, and 4h bars from lower-timeframe local sources."""

    source_list = list(sources)
    rows: list[dict[str, Any]] = []
    derived: list[LocalOhlcSource] = []
    for source in source_list:
        targets = _resample_targets(source.interval)
        for target in targets:
            quality = _resample_quality(source.interval, target)
            if quality == "DAILY_APPROX":
                rows.append(_resample_row(source, target, pl.DataFrame(), quality, False))
                continue
            if source.frame.is_empty():
                rows.append(_resample_row(source, target, pl.DataFrame(), "INSUFFICIENT", False))
                continue
            resampled = resample_ohlc(source.frame, target)
            coverage_ok = not resampled.is_empty()
            rows.append(_resample_row(source, target, resampled, quality, coverage_ok))
            if coverage_ok:
                derived.append(
                    LocalOhlcSource(
                        symbol=source.symbol,
                        interval=target,
                        path=source.path,
                        frame=resampled,
                        quality=quality,
                    )
                )
    if not rows:
        return pl.DataFrame(schema=_resample_schema()), []
    return pl.DataFrame(rows, schema=_resample_schema(), infer_schema_length=None), derived


def resample_ohlc(frame: pl.DataFrame, target_interval: str) -> pl.DataFrame:
    """Resample normalized OHLC bars to a supported target interval."""

    every = _polars_interval(target_interval)
    if every is None:
        raise ValueError(f"Unsupported resample target: {target_interval}")
    if frame.is_empty():
        return _empty_ohlc_frame()
    return (
        frame.sort("timestamp")
        .group_by_dynamic("timestamp", every=every, period=every, closed="left", label="left")
        .agg(
            [
                pl.col("open").first().alias("open"),
                pl.col("high").max().alias("high"),
                pl.col("low").min().alias("low"),
                pl.col("close").last().alias("close"),
                pl.col("volume").sum().alias("volume"),
            ]
        )
        .drop_nulls(subset=["open", "high", "low", "close"])
        .sort("timestamp")
    )


def build_partial_outcome_resolution(coverage: pl.DataFrame) -> pl.DataFrame:
    """Classify each pending journal row by resolvable and pending windows."""

    if coverage.is_empty():
        return pl.DataFrame(schema=_partial_resolution_schema())
    rows = []
    for row in coverage.to_dicts():
        resolvable = [window for window in WINDOW_ORDER if _coverage_value(row, window)]
        remaining = [window for window in WINDOW_ORDER if window not in resolvable]
        full = len(resolvable) == len(WINDOW_ORDER)
        partial = bool(resolvable and remaining)
        if full:
            reason = "All required windows have strict intraday OHLC coverage."
        elif partial:
            reason = "Some windows have strict intraday OHLC coverage; unresolved windows stay pending."
        else:
            reason = str(row.get("missing_coverage_reason") or "No strict intraday coverage yet.")
        rows.append(
            {
                "journal_id": row.get("journal_id", ""),
                "observation_timestamp": row.get("observation_timestamp", ""),
                "trade_date": row.get("trade_date", ""),
                "session_date": row.get("session_date", ""),
                "coverage_30m": _coverage_value(row, "30m"),
                "coverage_1h": _coverage_value(row, "1h"),
                "coverage_4h": _coverage_value(row, "4h"),
                "coverage_session_close": _coverage_value(row, "session_close"),
                "coverage_next_day": _coverage_value(row, "next_day"),
                "windows_resolvable_now": "|".join(resolvable),
                "windows_remaining_pending": "|".join(remaining),
                "can_resolve_partial": partial,
                "can_resolve_full": full,
                "reason": reason,
            }
        )
    return pl.DataFrame(rows, schema=_partial_resolution_schema(), infer_schema_length=None)


def build_forward_outcome_preview(
    *,
    coverage: pl.DataFrame,
    sources: Iterable[LocalOhlcSource],
) -> pl.DataFrame:
    """Build a controlled outcome preview without mutating journal observations."""

    if coverage.is_empty():
        return pl.DataFrame(schema=_outcome_preview_schema())
    source_list = list(sources)
    rows: list[dict[str, Any]] = []
    for coverage_row in coverage.to_dicts():
        observation = _parse_datetime(coverage_row.get("observation_timestamp"))
        if observation is None:
            continue
        ranges = required_window_ranges(observation)
        for window in WINDOW_ORDER:
            can_resolve = _coverage_value(coverage_row, window)
            start, end = ranges[window]
            preview = {
                "journal_id": coverage_row.get("journal_id", ""),
                "observation_timestamp": _iso(observation),
                "trade_date": coverage_row.get("trade_date", ""),
                "session_date": coverage_row.get("session_date", ""),
                "window": window,
                "window_start": _iso(start),
                "window_end": _iso(end),
                "outcome_status": "pending",
                "resolution_action": "leave_pending",
                "source_symbol": "",
                "source_interval": "",
                "quality": "INSUFFICIENT",
                "observed_start": "",
                "observed_end": "",
                "open": None,
                "high": None,
                "low": None,
                "close": None,
                "row_count": 0,
                "notes": "No sufficient strict intraday OHLC coverage for this window.",
            }
            if can_resolve:
                metrics = _covered_window_metrics(source_list, start, end, window)
                if metrics:
                    preview.update(metrics)
            rows.append(preview)
    return pl.DataFrame(rows, schema=_outcome_preview_schema(), infer_schema_length=None)


def build_forward_journal_scorecard(
    *,
    coverage: pl.DataFrame,
    partial_resolution: pl.DataFrame,
) -> pl.DataFrame:
    """Create the requested forward journal status scorecard."""

    total = coverage.height
    if partial_resolution.is_empty():
        row = _empty_scorecard_row()
        return pl.DataFrame([row], schema=_scorecard_schema(), infer_schema_length=None)
    full = _sum_bool(partial_resolution, "can_resolve_full")
    partial = _sum_bool(partial_resolution, "can_resolve_partial")
    resolvable = sum(
        1
        for row in partial_resolution.to_dicts()
        if str(row.get("windows_resolvable_now") or "").strip()
    )
    unresolved = total - resolvable
    latest_ohlc = _latest_ohlc_from_coverage(coverage)
    latest_observation = _latest_observation_from_coverage(coverage)
    weekend_blocked = _count_weekend_artifact_rows(coverage)
    if total == 0:
        label = "INSUFFICIENT_FORWARD_EVENTS"
    elif resolvable and unresolved:
        label = "PARTIAL_OUTCOMES_READY"
    elif resolvable:
        label = "PARTIAL_OUTCOMES_READY"
    elif weekend_blocked:
        label = "SKIP_WEEKEND_ARTIFACT"
    else:
        label = "WAIT_FOR_INTRADAY_OHLC"
    row = {
        "total_journal_rows": total,
        "pending_rows": total,
        "fully_resolved_rows": full,
        "partially_resolved_rows": partial,
        "unresolved_rows": unresolved,
        "resolvable_now_rows": resolvable,
        "blocked_by_weekend_artifact_rows": weekend_blocked,
        "blocked_by_missing_intraday_rows": unresolved,
        "latest_ohlc_timestamp": _iso(latest_ohlc),
        "latest_observation_timestamp": _iso(latest_observation),
        "current_research_label": label,
    }
    return pl.DataFrame([row], schema=_scorecard_schema(), infer_schema_length=None)


def build_useful_evidence_summary(
    *,
    output_dir: Path,
    coverage: pl.DataFrame,
    status_scorecard: pl.DataFrame,
) -> pl.DataFrame:
    """Build a concise useful-evidence summary without performance claims."""

    rule_summary = _read_csv_frame(output_dir / "guru_rule_backtest_summary.csv")
    rule_library = _read_csv_frame(output_dir / "guru_rule_library.csv")
    enough_rules = _rules_with_enough_events(rule_summary)
    filter_rules = _rules_by_type(rule_library, "FILTER")
    context_rules = _context_rules(rule_library)
    score = status_scorecard.row(0, named=True) if not status_scorecard.is_empty() else {}
    rows = [
        {
            "question": "What have we learned so far?",
            "answer": (
                "Useful pilot evidence exists for inspecting filters, market maps, "
                "and covered forward outcomes, but it is still research evidence."
            ),
            "evidence_status": "PILOT_EVIDENCE_EXISTS",
        },
        {
            "question": "Which rules have enough events to inspect?",
            "answer": enough_rules or "No rule has enough resolved events for inspection yet.",
            "evidence_status": "INSPECT_ONLY",
        },
        {
            "question": "Which rules look useful as filters?",
            "answer": filter_rules or "Filter usefulness remains a pilot question.",
            "evidence_status": "FILTER_REVIEW_ONLY",
        },
        {
            "question": "Which rules are still only context?",
            "answer": context_rules or "Most market-map and transcript rules remain context.",
            "evidence_status": "CONTEXT_ONLY",
        },
        {
            "question": "Which CME/guru evidence is pilot-only?",
            "answer": (
                "CME/guru evidence is pilot-only until more validation-grade days "
                "and timestamp-safe outcomes are collected."
            ),
            "evidence_status": "PILOT_ONLY",
        },
        {
            "question": "Which rows can be resolved now?",
            "answer": (
                f"{score.get('resolvable_now_rows', 0)} journal rows can be "
                "preview-resolved from strict intraday coverage now."
            ),
            "evidence_status": "PARTIAL_OUTCOMES_READY",
        },
        {
            "question": "What is still not proven?",
            "answer": (
                "No proven money edge yet, no paper/live trading readiness, and no "
                "claim that frozen rules should be traded."
            ),
            "evidence_status": "NOT_READY_FOR_MONEY",
        },
    ]
    if coverage.is_empty():
        rows.append(
            {
                "question": "Forward evidence coverage",
                "answer": "No pending forward coverage rows were available.",
                "evidence_status": "INSUFFICIENT_FORWARD_EVENTS",
            }
        )
    return pl.DataFrame(rows, schema=_useful_evidence_schema(), infer_schema_length=None)


def choose_final_recommendation(
    *,
    fetch_plan: pl.DataFrame,
    status_scorecard: pl.DataFrame,
) -> str:
    """Choose one of the requested final recommendation labels."""

    row = status_scorecard.row(0, named=True) if not status_scorecard.is_empty() else {}
    resolvable = int(row.get("resolvable_now_rows") or 0)
    unresolved = int(row.get("unresolved_rows") or 0)
    weekend_blocked = int(row.get("blocked_by_weekend_artifact_rows") or 0)
    if resolvable and weekend_blocked:
        return "SKIP_NEW_ROWS_BUT_RESOLVE_OLD_OUTCOMES"
    if resolvable:
        return "PARTIAL_OUTCOME_RESOLUTION_READY"
    if _any_true(fetch_plan, "fetch_needed"):
        return "FETCH_INTRADAY_OHLC"
    if unresolved:
        return "WAIT_FOR_INTRADAY_OHLC"
    return "COLLECTING_EVIDENCE"


def yahoo_intraday_outcome_report_lines(
    result: YahooIntradayOutcomeResolverResult | None,
) -> list[str]:
    """Return research_report.md sections for the Yahoo intraday resolver."""

    if result is None:
        return [
            "## Yahoo Intraday Fetch Plan",
            "",
            "Yahoo intraday outcome resolver was not run.",
        ]
    return [
        "## Yahoo Intraday Fetch Plan",
        "",
        _frame_markdown(result.fetch_plan),
        "",
        "## Intraday Resample Coverage",
        "",
        _frame_markdown(result.resample_coverage),
        "",
        "## Partial Outcome Resolution",
        "",
        _frame_markdown(result.partial_resolution),
        "",
        "## Forward Journal Status",
        "",
        _frame_markdown(result.status_scorecard),
        "",
        "## Useful Evidence So Far",
        "",
        _frame_markdown(result.useful_evidence),
        "",
        "## Yahoo Intraday Final Recommendation",
        "",
        f"`{result.final_recommendation}`",
        "",
        "- 4h outcomes are resampled from lower-timeframe intraday bars.",
        "- Daily OHLC is excluded from strict intraday outcome evidence.",
        f"- {RESEARCH_WARNING}",
    ]


def redact_path(path: str | Path | None) -> str:
    """Return a stable non-private path label for reports."""

    if path is None:
        return ""
    path_value = Path(path)
    safe_name = re.sub(r"[^A-Za-z0-9_.=-]", "_", path_value.name)[:80] or "source"
    digest = hashlib.sha256(path_value.as_posix().encode("utf-8")).hexdigest()[:8]
    return f"<REDACTED_PATH>/{safe_name}|{digest}{path_value.suffix.lower()}"


def _write_artifacts(
    *,
    paths: dict[str, Path],
    fetch_plan: pl.DataFrame,
    resample_coverage: pl.DataFrame,
    partial_resolution: pl.DataFrame,
    outcome_preview: pl.DataFrame,
    status_scorecard: pl.DataFrame,
    useful_evidence: pl.DataFrame,
    final_recommendation: str,
    fetch_warnings: tuple[str, ...],
) -> None:
    fetch_plan.write_csv(paths["fetch_plan_csv"])
    resample_coverage.write_csv(paths["resample_coverage_csv"])
    partial_resolution.write_csv(paths["partial_resolution_csv"])
    outcome_preview.write_csv(paths["outcome_preview_csv"])
    status_scorecard.write_csv(paths["scorecard_csv"])
    useful_evidence.write_csv(paths["useful_evidence_csv"])

    _write_markdown(paths["fetch_plan_md"], "# Yahoo Intraday Fetch Plan", fetch_plan)
    _write_markdown(
        paths["resample_coverage_md"],
        "# Intraday Resample Coverage",
        resample_coverage,
    )
    _write_partial_resolution_markdown(
        paths["partial_resolution_md"],
        partial_resolution,
        outcome_preview,
    )
    _write_status_markdown(
        paths["status_report_md"],
        status_scorecard,
        final_recommendation=final_recommendation,
        fetch_warnings=fetch_warnings,
    )
    _write_useful_evidence_markdown(paths["useful_evidence_md"], useful_evidence)


def _write_markdown(path: Path, title: str, frame: pl.DataFrame) -> None:
    text = "\n\n".join([title, _frame_markdown(frame), "", RESEARCH_WARNING])
    path.write_text(_safe_report_text(text), encoding="utf-8")


def _write_partial_resolution_markdown(
    path: Path,
    partial_resolution: pl.DataFrame,
    outcome_preview: pl.DataFrame,
) -> None:
    resolved_windows = (
        outcome_preview.filter(pl.col("resolution_action") == "preview_resolve").height
        if not outcome_preview.is_empty()
        else 0
    )
    lines = [
        "# Partial Outcome Resolution",
        "",
        _frame_markdown(partial_resolution),
        "",
        f"- Preview-resolved windows: `{resolved_windows}`",
        "- Missing windows remain pending.",
        "- Original journal observations were not mutated.",
        f"- {RESEARCH_WARNING}",
    ]
    path.write_text(_safe_report_text("\n".join(lines)), encoding="utf-8")


def _write_status_markdown(
    path: Path,
    scorecard: pl.DataFrame,
    *,
    final_recommendation: str,
    fetch_warnings: tuple[str, ...],
) -> None:
    warnings = "\n".join(f"- {warning}" for warning in fetch_warnings) or "- none"
    lines = [
        "# Forward Journal Status Report",
        "",
        _frame_markdown(scorecard),
        "",
        f"- Final recommendation: `{final_recommendation}`",
        "- Weekend artifacts block new journal rows.",
        "- Older rows with strict OHLC coverage can still be preview-resolved.",
        "- Daily OHLC is not used for strict 30m, 1h, or 4h outcome windows.",
        "",
        "## Fetch Warnings",
        "",
        warnings,
        "",
        f"- {RESEARCH_WARNING}",
    ]
    path.write_text(_safe_report_text("\n".join(lines)), encoding="utf-8")


def _write_useful_evidence_markdown(path: Path, useful_evidence: pl.DataFrame) -> None:
    lines = [
        "# Useful Evidence So Far",
        "",
        _frame_markdown(useful_evidence),
        "",
        "- Useful pilot evidence exists.",
        "- No proven money edge yet.",
        "- No paper/live trading readiness.",
        "- CME/guru evidence remains pilot-only.",
        "",
        f"- {RESEARCH_WARNING}",
    ]
    path.write_text(_safe_report_text("\n".join(lines)), encoding="utf-8")


def _covered_window_metrics(
    sources: list[LocalOhlcSource],
    start: datetime,
    end: datetime,
    window: str,
) -> dict[str, Any] | None:
    for source in _preferred_sources(sources, window):
        if not _source_covers(source.frame, start, end):
            continue
        sliced = source.frame.filter(
            (pl.col("timestamp") >= start) & (pl.col("timestamp") <= end)
        ).sort("timestamp")
        if sliced.is_empty():
            continue
        return {
            "outcome_status": "resolved_preview",
            "resolution_action": "preview_resolve",
            "source_symbol": source.symbol,
            "source_interval": source.interval,
            "quality": source.quality,
            "observed_start": _iso(_column_min_datetime(sliced, "timestamp")),
            "observed_end": _iso(_column_max_datetime(sliced, "timestamp")),
            "open": _first_float(sliced, "open"),
            "high": _max_float(sliced, "high"),
            "low": _min_float(sliced, "low"),
            "close": _last_float(sliced, "close"),
            "row_count": sliced.height,
            "notes": (
                "Preview only. Strict intraday OHLC coverage is available for "
                "this window; original journal files were not mutated."
            ),
        }
    return None


def _preferred_sources(sources: list[LocalOhlcSource], window: str) -> list[LocalOhlcSource]:
    allowed = {"30m": {"1m", "30m"}, "1h": {"1m", "30m", "60m", "1h"}}
    allowed["4h"] = {"1m", "30m", "60m", "1h", "4h"}
    allowed["session_close"] = {"1m", "30m", "60m", "1h", "4h"}
    allowed["next_day"] = {"1m", "30m", "60m", "1h", "4h"}
    order = {"XAUUSD=X": 0, "GC=F": 1, "GLD": 9}
    quality_order = {"EXACT_FROM_1M": 0, "INTRADAY_DIRECT": 1, "RESAMPLED_FROM_1H": 2}
    return sorted(
        [
            source
            for source in sources
            if source.interval in allowed.get(window, set())
            and source.quality != "DAILY_APPROX"
            and source.symbol != "GLD"
        ],
        key=lambda item: (
            order.get(item.symbol, 5),
            quality_order.get(item.quality, 5),
            item.interval,
        ),
    )


def _source_covers(frame: pl.DataFrame, start: datetime, end: datetime) -> bool:
    if frame.is_empty():
        return False
    first = _column_min_datetime(frame, "timestamp")
    last = _column_max_datetime(frame, "timestamp")
    return bool(first and last and first <= start and last >= end)


def _resample_row(
    source: LocalOhlcSource,
    target_interval: str,
    frame: pl.DataFrame,
    quality: str,
    coverage_ok: bool,
) -> dict[str, Any]:
    missing_gaps = _missing_gap_count(source.frame, source.interval)
    notes = f"Source path {redact_path(source.path)}."
    if source.symbol == "GLD":
        notes = f"GLD is PROXY_ONLY and excluded from strict XAU outcome resolution. {notes}"
    if quality == "DAILY_APPROX":
        notes = "Daily OHLC is excluded from strict intraday outcome evidence."
        if source.symbol == "GLD":
            notes = f"GLD is PROXY_ONLY. {notes}"
    return {
        "source_symbol": source.symbol,
        "source_interval": source.interval,
        "target_interval": target_interval,
        "rows_in": source.frame.height,
        "rows_out": frame.height if not frame.is_empty() else 0,
        "date_start": _iso(_column_min_datetime(frame, "timestamp")),
        "date_end": _iso(_column_max_datetime(frame, "timestamp")),
        "coverage_ok": coverage_ok,
        "missing_gaps": missing_gaps,
        "quality": quality if coverage_ok or quality == "DAILY_APPROX" else "INSUFFICIENT",
        "notes": notes,
    }


def _resample_targets(source_interval: str) -> tuple[str, ...]:
    normalized = source_interval.lower()
    if normalized == "1m":
        return ("30m", "1h", "4h")
    if normalized in {"30m", "60m", "1h"}:
        return ("4h",)
    if normalized == "1d":
        return ("30m", "1h", "4h")
    return ()


def _resample_quality(source_interval: str, target_interval: str) -> str:
    if source_interval == "1d":
        return "DAILY_APPROX"
    if source_interval == "1m":
        return "EXACT_FROM_1M"
    if target_interval == "4h" and source_interval in {"60m", "1h"}:
        return "RESAMPLED_FROM_1H"
    return "INTRADAY_DIRECT"


def _source_quality(symbol: str, interval: str) -> str:
    if interval == "1d":
        return "DAILY_APPROX"
    if symbol == "GLD":
        return "PROXY_ONLY"
    return "INTRADAY_DIRECT"


def _normalize_yfinance_history(history: Any, *, symbol: str, interval: str) -> pl.DataFrame:
    if history is None or getattr(history, "empty", False):
        return _empty_ohlc_frame()
    try:
        frame = pl.from_pandas(history.reset_index())
    except Exception as exc:
        raise ValueError(f"Yahoo returned unreadable rows for {symbol} {interval}.") from exc
    timestamp = _first_existing(frame.columns, ("Datetime", "Date", "index"))
    if timestamp is None:
        raise ValueError(f"Yahoo returned no timestamp column for {symbol} {interval}.")
    required = {"Open": "open", "High": "high", "Low": "low", "Close": "close"}
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"Yahoo returned missing OHLC columns: {', '.join(missing)}.")
    volume = pl.col("Volume").cast(pl.Float64, strict=False) if "Volume" in frame.columns else pl.lit(None)
    return (
        frame.with_columns(
            [
                _timestamp_expr(frame, timestamp),
                pl.col("Open").cast(pl.Float64).alias("open"),
                pl.col("High").cast(pl.Float64).alias("high"),
                pl.col("Low").cast(pl.Float64).alias("low"),
                pl.col("Close").cast(pl.Float64).alias("close"),
                volume.alias("volume"),
                pl.lit("yahoo_finance").alias("provider"),
                pl.lit(symbol).alias("symbol"),
                pl.lit(interval).alias("timeframe"),
                pl.lit(_source_quality(symbol, interval)).alias("source_label"),
            ]
        )
        .select(
            [
                "timestamp",
                "provider",
                "symbol",
                "timeframe",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "source_label",
            ]
        )
        .drop_nulls(subset=["timestamp", "open", "high", "low", "close"])
        .unique(subset=["timestamp"], keep="last")
        .sort("timestamp")
    )


def _fetch_purpose(symbol: str, interval: str) -> str:
    if symbol == "GLD":
        return "PROXY_ONLY"
    if interval == "1d":
        return "DAILY_APPROX_OUTCOME"
    return "INTRADAY_OUTCOME"


def _expected_limit_warning(interval: str, market_closed: bool) -> str:
    messages = []
    if interval == "1m":
        messages.append("Yahoo 1m intraday history is recent-window limited.")
    elif interval in {"5m", "15m", "30m", "60m", "1h"}:
        messages.append("Yahoo intraday history is limited to recent periods.")
    elif interval == "4h":
        messages.append("RESAMPLE_FROM_INTRADAY; 4h is not a required direct fetch.")
    elif interval == "1d":
        messages.append("DAILY_APPROX only; excluded from strict intraday evidence.")
    if market_closed:
        messages.append("Market is closed; no new candles expected until next session.")
    return " ".join(messages)


def _fetch_plan_notes(
    *,
    symbol: str,
    interval: str,
    configured: bool,
    market_closed: bool,
    expected_session: date,
) -> str:
    notes = []
    if symbol == "GLD":
        notes.append("PROXY_ONLY; do not treat as XAUUSD spot.")
    if symbol == "XAUUSD=X" and not configured:
        notes.append("Symbol is optional and not configured.")
    if interval == "4h":
        notes.append("RESAMPLE_FROM_INTRADAY using 1m or 1h bars.")
    if interval == "1d":
        notes.append("DAILY_APPROX only; not strict intraday evidence.")
    if market_closed:
        notes.append(
            "No new candles expected until the next market session after "
            f"{expected_session.isoformat()}."
        )
    notes.append(FETCH_DISABLED_NOTE)
    return " ".join(notes)


def _latest_local_timestamp(
    *,
    repo_root: Path,
    provider_audit: pl.DataFrame,
    symbol: str,
    interval: str,
    config: YahooIntradayConfig,
) -> datetime | None:
    candidates: list[datetime] = []
    if not provider_audit.is_empty() and {"symbol", "timeframe", "latest_timestamp"}.issubset(
        provider_audit.columns
    ):
        for row in provider_audit.to_dicts():
            if str(row.get("symbol") or "").upper() != symbol.upper():
                continue
            timeframe = str(row.get("timeframe") or "").lower()
            if timeframe not in {interval.lower(), _interval_alias(interval)}:
                continue
            parsed = _parse_datetime(row.get("latest_timestamp"))
            if parsed:
                candidates.append(parsed)
    path = _latest_yahoo_path(repo_root, symbol=symbol, interval=interval, config=config)
    if path:
        try:
            frame = load_ohlc_frame(path)
        except ValueError:
            frame = pl.DataFrame()
        latest = _column_max_datetime(frame, "timestamp")
        if latest:
            candidates.append(latest)
    return max(candidates) if candidates else None


def _needed_until_timestamp(coverage: pl.DataFrame, fallback: datetime) -> datetime:
    observations = []
    if not coverage.is_empty() and "observation_timestamp" in coverage.columns:
        observations = [
            parsed
            for parsed in (_parse_datetime(value) for value in coverage["observation_timestamp"])
            if parsed is not None
        ]
    if not observations:
        return fallback
    return max(required_window_ranges(observation)["next_day"][1] for observation in observations)


def _latest_ohlc_from_coverage(coverage: pl.DataFrame) -> datetime | None:
    if coverage.is_empty() or "latest_available_ohlc_timestamp" not in coverage.columns:
        return None
    values = [
        parsed
        for parsed in (
            _parse_datetime(value) for value in coverage["latest_available_ohlc_timestamp"]
        )
        if parsed is not None
    ]
    return max(values) if values else None


def _latest_observation_from_coverage(coverage: pl.DataFrame) -> datetime | None:
    if coverage.is_empty() or "observation_timestamp" not in coverage.columns:
        return None
    values = [
        parsed
        for parsed in (_parse_datetime(value) for value in coverage["observation_timestamp"])
        if parsed is not None
    ]
    return max(values) if values else None


def _count_weekend_artifact_rows(coverage: pl.DataFrame) -> int:
    if coverage.is_empty() or not {"trade_date", "session_date"}.issubset(coverage.columns):
        return 0
    count = 0
    for row in coverage.to_dicts():
        trade_day = str(row.get("trade_date") or "")
        session_day = str(row.get("session_date") or "")
        if trade_day and session_day and trade_day != session_day:
            count += 1
    return count


def _rules_with_enough_events(frame: pl.DataFrame) -> str:
    if frame.is_empty() or "event_count" not in frame.columns:
        return ""
    selected = frame.filter(pl.col("event_count").cast(pl.Int64, strict=False) >= 5)
    if selected.is_empty() or "rule_id" not in selected.columns:
        return ""
    return "|".join(str(value) for value in selected["rule_id"].head(8).to_list())


def _rules_by_type(frame: pl.DataFrame, rule_type: str) -> str:
    if frame.is_empty() or not {"rule_type", "rule_id"}.issubset(frame.columns):
        return ""
    selected = frame.filter(pl.col("rule_type") == rule_type)
    return "|".join(str(value) for value in selected["rule_id"].head(8).to_list())


def _context_rules(frame: pl.DataFrame) -> str:
    if frame.is_empty() or not {"rule_type", "rule_id"}.issubset(frame.columns):
        return ""
    selected = frame.filter(pl.col("rule_type").is_in(["MARKET_MAP", "CONTEXT"]))
    return "|".join(str(value) for value in selected["rule_id"].head(8).to_list())


def _latest_yahoo_path(
    repo_root: Path,
    *,
    symbol: str,
    interval: str,
    config: YahooIntradayConfig,
) -> Path | None:
    slug = _symbol_slug(symbol)
    aliases = {interval}
    if interval == "60m":
        aliases.add("1h")
    roots = (repo_root / config.data_dir, repo_root / "data" / "raw" / "yahoo")
    candidates: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for alias in aliases:
            candidates.extend(root.glob(f"{slug}_{alias}_ohlcv*.parquet"))
            candidates.extend(root.glob(f"{slug}_{alias}_ohlcv*.csv"))
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item.stat().st_mtime, item.name))


def _dedupe_sources(sources: list[LocalOhlcSource]) -> list[LocalOhlcSource]:
    seen: set[tuple[str, str, str]] = set()
    result: list[LocalOhlcSource] = []
    for source in sources:
        key = (source.symbol, source.interval, source.path.as_posix())
        if key in seen:
            continue
        seen.add(key)
        result.append(source)
    return result


def _period_days(period: str) -> int:
    match = re.fullmatch(r"(\d+)\s*d", period.strip().lower())
    if match:
        return max(1, int(match.group(1)))
    return 7


def _market_closed(day: date) -> bool:
    return is_weekend(day)


def _coverage_value(row: dict[str, Any], window: str) -> bool:
    key = f"coverage_{window}"
    value = row.get(key)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


def _sum_bool(frame: pl.DataFrame, column: str) -> int:
    if frame.is_empty() or column not in frame.columns:
        return 0
    return sum(1 for value in frame[column].to_list() if bool(value))


def _any_true(frame: pl.DataFrame, column: str) -> bool:
    if frame.is_empty() or column not in frame.columns:
        return False
    return any(bool(value) for value in frame[column].to_list())


def _empty_scorecard_row() -> dict[str, Any]:
    return {
        "total_journal_rows": 0,
        "pending_rows": 0,
        "fully_resolved_rows": 0,
        "partially_resolved_rows": 0,
        "unresolved_rows": 0,
        "resolvable_now_rows": 0,
        "blocked_by_weekend_artifact_rows": 0,
        "blocked_by_missing_intraday_rows": 0,
        "latest_ohlc_timestamp": "",
        "latest_observation_timestamp": "",
        "current_research_label": "INSUFFICIENT_FORWARD_EVENTS",
    }


def _read_csv_frame(path: Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    try:
        return pl.read_csv(path, infer_schema_length=None)
    except Exception:
        return pl.DataFrame()


def _safe_report_text(text: str) -> str:
    lower = text.lower()
    for phrase in FORBIDDEN_REPORT_PHRASES:
        if phrase in lower:
            raise ValueError(f"Forbidden report phrase: {phrase}")
    return text


def _frame_markdown(frame: pl.DataFrame, *, limit: int = 20) -> str:
    if frame.is_empty():
        return "_No rows._"
    columns = frame.columns
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in frame.head(limit).to_dicts():
        lines.append(
            "| "
            + " | ".join(_markdown_cell(row.get(column, "")) for column in columns)
            + " |"
        )
    return "\n".join(lines)


def _markdown_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _empty_ohlc_frame() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "timestamp": pl.Datetime(time_zone="UTC"),
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "volume": pl.Float64,
        }
    )


def _ohlc_column_map(columns: Iterable[str]) -> dict[str, str]:
    normalized = {_normalize_name(column): column for column in columns}
    aliases = {
        "timestamp": ("timestamp", "datetime", "date", "time"),
        "open": ("open",),
        "high": ("high",),
        "low": ("low",),
        "close": ("close", "last", "price"),
        "volume": ("volume", "intraday_volume"),
    }
    result = {}
    for target, names in aliases.items():
        for name in names:
            if name in normalized:
                result[target] = normalized[name]
                break
    return result


def _timestamp_expr(frame: pl.DataFrame, column: str) -> pl.Expr:
    dtype = frame.schema.get(column)
    if dtype == pl.Utf8:
        return pl.col(column).str.to_datetime(time_zone="UTC", strict=False).alias("timestamp")
    return pl.col(column).cast(pl.Datetime(time_zone="UTC"), strict=False).alias("timestamp")


def _normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def _polars_interval(interval: str) -> str | None:
    return {"30m": "30m", "1h": "1h", "4h": "4h"}.get(interval)


def _missing_gap_count(frame: pl.DataFrame, interval: str) -> int:
    expected = _interval_seconds(interval)
    if expected is None or frame.height < 2:
        return 0
    timestamps = [
        value for value in frame.sort("timestamp")["timestamp"].to_list() if isinstance(value, datetime)
    ]
    return sum(
        1
        for left, right in zip(timestamps, timestamps[1:], strict=False)
        if (right - left).total_seconds() > expected * 1.5
    )


def _interval_seconds(interval: str) -> int | None:
    return {
        "1m": 60,
        "5m": 300,
        "15m": 900,
        "30m": 1800,
        "60m": 3600,
        "1h": 3600,
        "4h": 14400,
    }.get(interval.lower())


def _first_existing(columns: Iterable[str], candidates: Iterable[str]) -> str | None:
    column_set = set(columns)
    for candidate in candidates:
        if candidate in column_set:
            return candidate
    return None


def _ordered_unique(values: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        cleaned = value.strip()
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return tuple(result)


def _split_env(value: str | None, default: tuple[str, ...]) -> tuple[str, ...]:
    if not value:
        return default
    parsed = tuple(item.strip() for item in value.split(",") if item.strip())
    return parsed or default


def _env_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _symbol_slug(symbol: str) -> str:
    return symbol.lower().replace("/", "").replace("=", "=").replace(" ", "_")


def _interval_alias(interval: str) -> str:
    return "1h" if interval == "60m" else interval


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return _ensure_utc(value)
    if isinstance(value, date):
        return datetime.combine(value, time(), tzinfo=UTC)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return _ensure_utc(parsed)


def _ensure_utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


def _iso(value: datetime | None) -> str:
    if value is None:
        return ""
    return _ensure_utc(value).isoformat().replace("+00:00", "Z")


def _column_min_datetime(frame: pl.DataFrame, column: str) -> datetime | None:
    if frame.is_empty() or column not in frame.columns:
        return None
    value = frame.select(pl.col(column).min()).item()
    return _ensure_utc(value) if isinstance(value, datetime) else _parse_datetime(value)


def _column_max_datetime(frame: pl.DataFrame, column: str) -> datetime | None:
    if frame.is_empty() or column not in frame.columns:
        return None
    value = frame.select(pl.col(column).max()).item()
    return _ensure_utc(value) if isinstance(value, datetime) else _parse_datetime(value)


def _first_float(frame: pl.DataFrame, column: str) -> float | None:
    value = frame[column].head(1).item()
    return float(value) if value is not None else None


def _last_float(frame: pl.DataFrame, column: str) -> float | None:
    value = frame[column].tail(1).item()
    return float(value) if value is not None else None


def _max_float(frame: pl.DataFrame, column: str) -> float | None:
    value = frame.select(pl.col(column).max()).item()
    return float(value) if value is not None else None


def _min_float(frame: pl.DataFrame, column: str) -> float | None:
    value = frame.select(pl.col(column).min()).item()
    return float(value) if value is not None else None


def _fetch_plan_schema() -> dict[str, Any]:
    return {
        "symbol": pl.String,
        "interval": pl.String,
        "purpose": pl.String,
        "can_fetch_directly": pl.Boolean,
        "fetch_window_start": pl.String,
        "fetch_window_end": pl.String,
        "expected_limit_warning": pl.String,
        "current_local_latest_timestamp": pl.String,
        "needed_until_timestamp": pl.String,
        "fetch_needed": pl.Boolean,
        "notes": pl.String,
    }


def _resample_schema() -> dict[str, Any]:
    return {
        "source_symbol": pl.String,
        "source_interval": pl.String,
        "target_interval": pl.String,
        "rows_in": pl.Int64,
        "rows_out": pl.Int64,
        "date_start": pl.String,
        "date_end": pl.String,
        "coverage_ok": pl.Boolean,
        "missing_gaps": pl.Int64,
        "quality": pl.String,
        "notes": pl.String,
    }


def _partial_resolution_schema() -> dict[str, Any]:
    return {
        "journal_id": pl.String,
        "observation_timestamp": pl.String,
        "trade_date": pl.String,
        "session_date": pl.String,
        "coverage_30m": pl.Boolean,
        "coverage_1h": pl.Boolean,
        "coverage_4h": pl.Boolean,
        "coverage_session_close": pl.Boolean,
        "coverage_next_day": pl.Boolean,
        "windows_resolvable_now": pl.String,
        "windows_remaining_pending": pl.String,
        "can_resolve_partial": pl.Boolean,
        "can_resolve_full": pl.Boolean,
        "reason": pl.String,
    }


def _outcome_preview_schema() -> dict[str, Any]:
    return {
        "journal_id": pl.String,
        "observation_timestamp": pl.String,
        "trade_date": pl.String,
        "session_date": pl.String,
        "window": pl.String,
        "window_start": pl.String,
        "window_end": pl.String,
        "outcome_status": pl.String,
        "resolution_action": pl.String,
        "source_symbol": pl.String,
        "source_interval": pl.String,
        "quality": pl.String,
        "observed_start": pl.String,
        "observed_end": pl.String,
        "open": pl.Float64,
        "high": pl.Float64,
        "low": pl.Float64,
        "close": pl.Float64,
        "row_count": pl.Int64,
        "notes": pl.String,
    }


def _scorecard_schema() -> dict[str, Any]:
    return {
        "total_journal_rows": pl.Int64,
        "pending_rows": pl.Int64,
        "fully_resolved_rows": pl.Int64,
        "partially_resolved_rows": pl.Int64,
        "unresolved_rows": pl.Int64,
        "resolvable_now_rows": pl.Int64,
        "blocked_by_weekend_artifact_rows": pl.Int64,
        "blocked_by_missing_intraday_rows": pl.Int64,
        "latest_ohlc_timestamp": pl.String,
        "latest_observation_timestamp": pl.String,
        "current_research_label": pl.String,
    }


def _useful_evidence_schema() -> dict[str, Any]:
    return {
        "question": pl.String,
        "answer": pl.String,
        "evidence_status": pl.String,
    }


def main() -> None:
    """CLI entry point for manual local runs."""

    result = run_yahoo_intraday_outcome_resolver()
    print(f"final_recommendation: {result.final_recommendation}")
    print(f"resolvable_rows: {_sum_bool(result.partial_resolution, 'can_resolve_full')}")
    print("fetch_configured: false" if not load_config().enable_fetch else "fetch_configured: true")


if __name__ == "__main__":
    main()
