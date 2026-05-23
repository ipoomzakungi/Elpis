"""Validation-grade CME/QuikStrike history normalization.

This module converts local, read-only CME/QuikStrike-style exports into
canonical daily panels for XAU research. It does not scrape, replay browser
traffic, store secrets, connect to brokers, or create trading instructions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Iterable

import polars as pl

from research_xau_vol_oi.config import ResearchConfig
from research_xau_vol_oi.data_loader import DataLoadError, load_table
from research_xau_vol_oi.data_recovery_audit import (
    RecoveryAuditConfig,
    build_recovery_audit_config,
    hash_source_id,
    redact_path,
)


TABLE_EXTENSIONS = {".csv", ".parquet", ".xlsx", ".xls"}
DEFAULT_HISTORY_ROOTS = (
    Path("data/raw"),
    Path("data/processed"),
    Path("backend/data/raw"),
    Path("backend/data/processed"),
)
FILE_HINTS = (
    "quikstrike",
    "cme",
    "xau",
    "gold",
    "gc=f",
    "options",
    "option",
    "strike",
    "oi",
    "open_interest",
    "volume",
    "vol",
    "future",
    "spot",
    "settlement",
    "calendar",
    "event",
)
VALIDATION_FIELDS = (
    ("cme_options_oi", "has_cme_options_oi", "HIGH"),
    ("oi_change", "has_oi_change", "HIGH"),
    ("intraday_volume", "has_intraday_volume", "HIGH"),
    ("iv_context", "has_iv_context", "HIGH"),
    ("futures_reference_price", "has_futures_reference_price", "HIGH"),
    ("xau_spot_or_proxy_price", "has_xau_spot_or_proxy_price", "HIGH"),
    ("futures_to_spot_basis", "has_basis", "HIGH"),
    ("session_open", "has_session_open", "MEDIUM"),
    ("event_calendar_tags", "has_event_calendar", "MEDIUM"),
)
EXPIRY_RE = re.compile(r"expires?:\s*(?P<date>\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", re.IGNORECASE)
ISO_DATE_RE = re.compile(r"(?P<year>20\d{2})[-_/](?P<month>\d{1,2})[-_/](?P<day>\d{1,2})")
DTE_BEFORE_EXPIRES_RE = re.compile(r"(?P<dte>\d{1,3})\s+DTE\s+expires?", re.IGNORECASE)
DTE_RE = re.compile(r"(?P<dte>\d{1,3})\s+DTE", re.IGNORECASE)


@dataclass(frozen=True)
class CmeHistoryNormalizerConfig:
    """Local input and redaction settings for CME history normalization."""

    input_roots: tuple[Path, ...] = DEFAULT_HISTORY_ROOTS
    redact_paths: bool = True
    include_outputs: bool = False


@dataclass(frozen=True)
class CmeHistoryNormalizerResult:
    """Canonical panels and diagnostics from the normalizer."""

    daily_panel: pl.DataFrame
    session_panel: pl.DataFrame
    coverage_report: pl.DataFrame
    missing_field_report: pl.DataFrame
    duplicate_conflict_report: pl.DataFrame
    source_inventory: pl.DataFrame
    first_validation_grade_date: str | None
    last_validation_grade_date: str | None
    complete_validation_days: int
    missing_fields_for_full_proof: tuple[str, ...]


def run_cme_history_normalizer(
    *,
    output_dir: str | Path,
    config: ResearchConfig | None = None,
    normalizer_config: CmeHistoryNormalizerConfig | None = None,
    input_paths: Iterable[str | Path] | None = None,
    input_roots: Iterable[str | Path] | None = None,
    recovery_config: RecoveryAuditConfig | None = None,
) -> CmeHistoryNormalizerResult:
    """Normalize local CME/QuikStrike history and write canonical outputs."""

    cfg = config or ResearchConfig()
    norm_cfg = normalizer_config or CmeHistoryNormalizerConfig()
    privacy_cfg = recovery_config or build_recovery_audit_config()
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    paths = list(input_paths) if input_paths is not None else discover_cme_history_files(
        input_roots or norm_cfg.input_roots,
        config=cfg,
    )
    option_rows, price_rows, event_rows, source_inventory = normalize_cme_history_sources(
        paths,
        recovery_config=privacy_cfg,
    )
    duplicate_conflicts = build_duplicate_conflict_report(option_rows)
    daily_panel = build_daily_strike_expiry_panel(
        option_rows,
        price_rows=price_rows,
        event_rows=event_rows,
        duplicate_conflicts=duplicate_conflicts,
    )
    session_panel = build_session_regime_panel(
        daily_panel,
        price_rows=price_rows,
        event_rows=event_rows,
    )
    coverage_report = build_coverage_report(session_panel)
    missing_field_report = build_missing_field_report(coverage_report)
    result = summarize_cme_history_normalization(
        daily_panel=daily_panel,
        session_panel=session_panel,
        coverage_report=coverage_report,
        missing_field_report=missing_field_report,
        duplicate_conflict_report=duplicate_conflicts,
        source_inventory=source_inventory,
    )

    daily_panel.write_parquet(output_root / "cme_daily_strike_expiry_panel.parquet")
    session_panel.write_parquet(output_root / "cme_session_regime_panel.parquet")
    coverage_report.write_csv(output_root / "cme_history_coverage_report.csv")
    missing_field_report.write_csv(output_root / "cme_history_missing_field_report.csv")
    duplicate_conflicts.write_csv(output_root / "cme_history_duplicate_conflict_report.csv")
    source_inventory.write_csv(output_root / "cme_history_source_inventory.csv")
    (output_root / "cme_history_coverage_report.md").write_text(
        cme_history_coverage_markdown(result),
        encoding="utf-8",
    )
    return result


def discover_cme_history_files(
    roots: Iterable[str | Path],
    *,
    config: ResearchConfig | None = None,
) -> list[Path]:
    """Discover likely local CME/QuikStrike/price/calendar tables."""

    cfg = config or ResearchConfig()
    paths: list[Path] = []
    for raw_root in roots:
        root = Path(raw_root)
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in TABLE_EXTENSIONS:
                continue
            if _is_generated_cme_output(path):
                continue
            if any(part in cfg.exclude_dir_names for part in path.parts):
                continue
            text = path.as_posix().lower()
            if any(hint in text for hint in FILE_HINTS):
                paths.append(path)
    return sorted(set(paths))


def normalize_cme_history_sources(
    paths: Iterable[str | Path],
    *,
    recovery_config: RecoveryAuditConfig | None = None,
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """Load and normalize candidate source tables into option, price, and event rows."""

    privacy_cfg = recovery_config or build_recovery_audit_config()
    option_frames: list[pl.DataFrame] = []
    price_frames: list[pl.DataFrame] = []
    event_frames: list[pl.DataFrame] = []
    inventory_rows: list[dict[str, Any]] = []

    for raw_path in paths:
        path = Path(raw_path)
        source_id = hash_source_id(str(path.resolve()) if path.exists() else str(path))
        redacted = redact_path(str(path), privacy_cfg)
        try:
            frame = load_table(path)
            kinds = classify_cme_history_frame(path, frame)
            if "option_matrix" in kinds:
                options = normalize_option_history_frame(path, frame, source_id=source_id, recovery_config=privacy_cfg)
                if not options.is_empty():
                    option_frames.append(options)
            if "price_reference" in kinds:
                prices = normalize_price_reference_frame(path, frame, source_id=source_id, recovery_config=privacy_cfg)
                if not prices.is_empty():
                    price_frames.append(prices)
            if "event_calendar" in kinds:
                events = normalize_event_calendar_frame(path, frame, source_id=source_id, recovery_config=privacy_cfg)
                if not events.is_empty():
                    event_frames.append(events)
            inventory_rows.append(
                {
                    "source_id_hash": source_id,
                    "redacted_file_path": redacted,
                    "file_name": path.name,
                    "source_kind": ",".join(kinds) if kinds else "unclassified",
                    "load_status": "loaded",
                    "row_count": frame.height,
                    "column_count": len(frame.columns),
                    "columns_detected": "|".join(frame.columns),
                    "date_start": _frame_date_start(frame),
                    "date_end": _frame_date_end(frame),
                    "notes": "",
                }
            )
        except (DataLoadError, OSError, ValueError) as exc:
            inventory_rows.append(
                {
                    "source_id_hash": source_id,
                    "redacted_file_path": redacted,
                    "file_name": path.name,
                    "source_kind": "unreadable",
                    "load_status": "failed",
                    "row_count": 0,
                    "column_count": 0,
                    "columns_detected": "",
                    "date_start": None,
                    "date_end": None,
                    "notes": str(exc),
                }
            )

    return (
        _concat_or_empty(option_frames, _option_schema()),
        _concat_or_empty(price_frames, _price_schema()),
        _concat_or_empty(event_frames, _event_schema()),
        pl.DataFrame(inventory_rows, infer_schema_length=None)
        if inventory_rows
        else pl.DataFrame(schema=_source_inventory_schema()),
    )


def classify_cme_history_frame(path: str | Path, frame: pl.DataFrame) -> set[str]:
    """Classify a loaded table by schema and neutral path hints."""

    path_text = Path(path).as_posix().lower()
    lower_cols = {column.lower() for column in frame.columns}
    kinds: set[str] = set()
    has_strike = _has_any(lower_cols, STRIKE_ALIASES)
    has_option_metric = _has_any(
        lower_cols,
        OPEN_INTEREST_ALIASES
        + CALL_OI_ALIASES
        + PUT_OI_ALIASES
        + OI_CHANGE_ALIASES
        + VOLUME_ALIASES
        + IV_ALIASES,
    )
    has_many_matrix_columns = has_strike and len(frame.columns) >= 3
    if has_strike and (has_option_metric or has_many_matrix_columns):
        kinds.add("option_matrix")
    if _has_any(lower_cols, OPEN_ALIASES + HIGH_ALIASES + LOW_ALIASES + CLOSE_ALIASES):
        kinds.add("price_reference")
    if _has_any(lower_cols, FUTURES_PRICE_ALIASES + SPOT_PRICE_ALIASES + SESSION_OPEN_ALIASES) and not has_strike:
        kinds.add("price_reference")
    if _has_any(lower_cols, EVENT_ALIASES):
        kinds.add("event_calendar")
    if ("vol2vol" in path_text or "expected" in path_text) and not has_strike:
        kinds.add("price_reference")
    return kinds


def normalize_option_history_frame(
    path: str | Path,
    frame: pl.DataFrame,
    *,
    source_id: str,
    recovery_config: RecoveryAuditConfig | None = None,
) -> pl.DataFrame:
    """Normalize row-wise or wide matrix option data into long option rows."""

    if _has_column(frame, STRIKE_ALIASES) and _has_any(set(map(str.lower, frame.columns)), OPTION_ROW_HINT_ALIASES):
        rows = _normalize_row_option_frame(path, frame, source_id=source_id, recovery_config=recovery_config)
    else:
        rows = _normalize_wide_matrix_frame(path, frame, source_id=source_id, recovery_config=recovery_config)
    return pl.DataFrame(rows, infer_schema_length=None) if rows else pl.DataFrame(schema=_option_schema())


def normalize_price_reference_frame(
    path: str | Path,
    frame: pl.DataFrame,
    *,
    source_id: str,
    recovery_config: RecoveryAuditConfig | None = None,
) -> pl.DataFrame:
    """Normalize futures, spot/proxy price, session-open, and vol context rows."""

    path_obj = Path(path)
    redacted = redact_path(str(path_obj), recovery_config)
    timestamp_col = _find_optional_column(frame.columns, TIMESTAMP_ALIASES)
    symbol_col = _find_optional_column(frame.columns, SYMBOL_ALIASES)
    open_col = _find_optional_column(frame.columns, OPEN_ALIASES)
    close_col = _find_optional_column(frame.columns, CLOSE_ALIASES)
    futures_col = _find_optional_column(frame.columns, FUTURES_PRICE_ALIASES)
    spot_col = _find_optional_column(frame.columns, SPOT_PRICE_ALIASES)
    session_open_col = _find_optional_column(frame.columns, SESSION_OPEN_ALIASES)
    iv_col = _find_optional_column(frame.columns, IV_ALIASES)
    realized_vol_col = _find_optional_column(frame.columns, REALIZED_VOL_ALIASES)
    vrp_col = _find_optional_column(frame.columns, VRP_ALIASES)
    expected_range_col = _find_optional_column(frame.columns, EXPECTED_RANGE_ALIASES)
    term_structure_col = _find_optional_column(frame.columns, TERM_STRUCTURE_ALIASES)

    rows: list[dict[str, Any]] = []
    for index, raw in enumerate(frame.to_dicts(), start=1):
        timestamp = _parse_timestamp(raw.get(timestamp_col), fallback=_date_from_filename(path_obj), row=index)
        if timestamp is None:
            continue
        symbol = str(raw.get(symbol_col) or _symbol_from_path(path_obj) or "UNKNOWN")
        close_price = _optional_float(raw.get(close_col))
        open_price = _optional_float(raw.get(open_col))
        explicit_futures = _optional_float(raw.get(futures_col))
        explicit_spot = _optional_float(raw.get(spot_col))
        role = _price_role(path_obj, symbol)
        futures_price = explicit_futures if explicit_futures is not None else (close_price if role == "futures" else None)
        spot_price = explicit_spot if explicit_spot is not None else (close_price if role == "spot" else None)
        session_open = _optional_float(raw.get(session_open_col))
        if session_open is None:
            session_open = open_price
        rows.append(
            {
                "timestamp": timestamp,
                "session_date": timestamp.date().isoformat(),
                "source_id_hash": source_id,
                "redacted_file_path": redacted,
                "file_name": path_obj.name,
                "symbol": symbol,
                "price_role": role,
                "open": open_price,
                "close": close_price,
                "futures_price": futures_price,
                "spot_price": spot_price,
                "session_open": session_open,
                "iv_percent": _normalize_iv(_optional_float(raw.get(iv_col))),
                "realized_vol_percent": _normalize_iv(_optional_float(raw.get(realized_vol_col))),
                "vrp": _optional_float(raw.get(vrp_col)),
                "expected_range": _optional_float(raw.get(expected_range_col)),
                "term_structure_regime": str(raw.get(term_structure_col) or ""),
            }
        )
    return pl.DataFrame(rows, infer_schema_length=None) if rows else pl.DataFrame(schema=_price_schema())


def normalize_event_calendar_frame(
    path: str | Path,
    frame: pl.DataFrame,
    *,
    source_id: str,
    recovery_config: RecoveryAuditConfig | None = None,
) -> pl.DataFrame:
    """Normalize event-calendar rows into session-date tags."""

    path_obj = Path(path)
    redacted = redact_path(str(path_obj), recovery_config)
    timestamp_col = _find_optional_column(frame.columns, TIMESTAMP_ALIASES)
    event_col = _find_optional_column(frame.columns, EVENT_ALIASES)
    tag_col = _find_optional_column(frame.columns, EVENT_TAG_ALIASES)
    dollar_col = _find_optional_column(frame.columns, DOLLAR_REGIME_ALIASES)
    rows: list[dict[str, Any]] = []
    for index, raw in enumerate(frame.to_dicts(), start=1):
        timestamp = _parse_timestamp(raw.get(timestamp_col), fallback=_date_from_filename(path_obj), row=index)
        if timestamp is None:
            continue
        name = str(raw.get(event_col) or raw.get(tag_col) or path_obj.stem)
        event_tags = _event_tags(name, raw.get(tag_col))
        rows.append(
            {
                "timestamp": timestamp,
                "session_date": timestamp.date().isoformat(),
                "source_id_hash": source_id,
                "redacted_file_path": redacted,
                "file_name": path_obj.name,
                "event_name": name,
                "event_tags": "|".join(event_tags),
                "has_cpi": "CPI" in event_tags,
                "has_nfp": "NFP" in event_tags,
                "has_fomc": "FOMC" in event_tags,
                "dollar_regime_tag": str(raw.get(dollar_col) or ""),
            }
        )
    return pl.DataFrame(rows, infer_schema_length=None) if rows else pl.DataFrame(schema=_event_schema())


def build_daily_strike_expiry_panel(
    option_rows: pl.DataFrame,
    *,
    price_rows: pl.DataFrame | None = None,
    event_rows: pl.DataFrame | None = None,
    duplicate_conflicts: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Build one canonical row per session, expiry, and strike."""

    if option_rows.is_empty():
        return pl.DataFrame(schema=_daily_panel_schema())

    sorted_options = option_rows.sort("timestamp")
    latest = sorted_options.group_by(
        ["session_date", "expiry", "expiry_date", "strike", "option_type"],
        maintain_order=True,
    ).agg(
        [
            pl.col("timestamp").max().alias("panel_timestamp"),
            pl.col("futures_symbol").drop_nulls().last().alias("futures_symbol"),
            pl.col("dte").drop_nulls().last().alias("dte"),
            pl.col("open_interest").drop_nulls().last().alias("open_interest"),
            pl.col("oi_change").drop_nulls().last().alias("oi_change"),
            pl.col("volume").drop_nulls().last().alias("volume"),
            pl.col("iv_percent").drop_nulls().last().alias("iv_percent"),
            pl.col("expected_range").drop_nulls().last().alias("expected_range"),
            pl.col("settlement_price").drop_nulls().last().alias("settlement_price"),
            pl.col("futures_price").drop_nulls().last().alias("futures_price"),
            pl.col("spot_price").drop_nulls().last().alias("spot_price"),
            pl.col("session_open").drop_nulls().last().alias("session_open"),
            pl.col("source_id_hash").n_unique().alias("source_count"),
        ]
    )

    base_keys = ["session_date", "expiry", "expiry_date", "strike"]
    daily = latest.group_by(base_keys, maintain_order=True).agg(
        [
            pl.col("panel_timestamp").max().alias("panel_timestamp"),
            pl.col("futures_symbol").drop_nulls().last().alias("futures_symbol"),
            pl.col("dte").drop_nulls().last().alias("dte"),
            _sum_type("call", "open_interest", "call_oi"),
            _sum_type("put", "open_interest", "put_oi"),
            pl.col("open_interest").drop_nulls().sum().alias("total_oi"),
            _sum_type("call", "oi_change", "call_oi_change"),
            _sum_type("put", "oi_change", "put_oi_change"),
            pl.col("oi_change").drop_nulls().sum().alias("total_oi_change"),
            _sum_type("call", "volume", "call_volume"),
            _sum_type("put", "volume", "put_volume"),
            pl.col("volume").drop_nulls().sum().alias("total_volume"),
            _mean_type("call", "iv_percent", "call_iv_percent"),
            _mean_type("put", "iv_percent", "put_iv_percent"),
            pl.col("iv_percent").drop_nulls().mean().alias("mean_iv_percent"),
            pl.col("expected_range").drop_nulls().last().alias("expected_range"),
            pl.col("settlement_price").drop_nulls().last().alias("settlement_price"),
            pl.col("futures_price").drop_nulls().last().alias("futures_price"),
            pl.col("spot_price").drop_nulls().last().alias("spot_price"),
            pl.col("session_open").drop_nulls().last().alias("session_open"),
            pl.col("source_count").sum().alias("source_count"),
        ]
    )

    price_daily = _price_daily(_frame_or_empty(price_rows, _price_schema()))
    if not price_daily.is_empty():
        daily = daily.join(price_daily, on="session_date", how="left").with_columns(
            [
                pl.coalesce(["futures_price", "futures_reference_price"]).alias("futures_price"),
                pl.coalesce(["spot_price", "xauusd_spot_or_proxy_price"]).alias("spot_price"),
                pl.coalesce(["session_open", "price_session_open"]).alias("session_open"),
                pl.coalesce(["mean_iv_percent", "price_iv_percent"]).alias("mean_iv_percent"),
                pl.coalesce(["expected_range", "price_expected_range"]).alias("expected_range"),
                pl.col("realized_vol_percent"),
                pl.col("vrp"),
                pl.col("term_structure_regime"),
            ]
        ).drop(
            [
                column
                for column in [
                    "futures_reference_price",
                    "xauusd_spot_or_proxy_price",
                    "price_session_open",
                    "price_iv_percent",
                    "price_expected_range",
                ]
                if column in daily.columns
            ]
        )
    else:
        daily = daily.with_columns(
            [
                pl.lit(None, dtype=pl.Float64).alias("realized_vol_percent"),
                pl.lit(None, dtype=pl.Float64).alias("vrp"),
                pl.lit("").alias("term_structure_regime"),
            ]
        )

    event_daily = _event_daily(_frame_or_empty(event_rows, _event_schema()))
    if not event_daily.is_empty():
        daily = daily.join(event_daily, on="session_date", how="left")
    else:
        daily = daily.with_columns(
            [
                pl.lit("").alias("event_tags"),
                pl.lit(False).alias("has_cpi"),
                pl.lit(False).alias("has_nfp"),
                pl.lit(False).alias("has_fomc"),
                pl.lit("").alias("dollar_regime_tag"),
            ]
        )

    conflict_keys = _conflict_key_set(_frame_or_empty(duplicate_conflicts, _duplicate_schema()))
    rows = []
    for raw in daily.to_dicts():
        session_date = str(raw.get("session_date") or "")
        dte = _optional_float(raw.get("dte"))
        futures_price = _optional_float(raw.get("futures_price"))
        spot_price = _optional_float(raw.get("spot_price"))
        basis = futures_price - spot_price if futures_price is not None and spot_price is not None else None
        strike = _optional_float(raw.get("strike"))
        key = _daily_conflict_key(raw)
        rows.append(
            {
                **raw,
                "basis": basis,
                "spot_equivalent_strike": strike - basis if strike is not None and basis is not None else None,
                "day_of_week": _day_of_week(session_date),
                "expiry_bucket": _expiry_bucket(dte),
                "expiration_proximity": _expiration_proximity(dte),
                "is_expiry_day": dte is not None and dte <= 0,
                "has_conflict": key in conflict_keys,
                "validation_grade": _daily_row_validation_grade(raw, basis),
            }
        )
    return pl.DataFrame(rows, infer_schema_length=None).sort(["session_date", "expiry", "strike"])


def build_session_regime_panel(
    daily_panel: pl.DataFrame,
    *,
    price_rows: pl.DataFrame | None = None,
    event_rows: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Build a canonical session-level regime and coverage panel."""

    price_daily = {
        row["session_date"]: row
        for row in _price_daily(_frame_or_empty(price_rows, _price_schema())).to_dicts()
    }
    event_daily = {
        row["session_date"]: row
        for row in _event_daily(_frame_or_empty(event_rows, _event_schema())).to_dicts()
    }
    daily_by_date: dict[str, list[dict[str, Any]]] = {}
    for row in daily_panel.to_dicts():
        daily_by_date.setdefault(str(row.get("session_date")), []).append(row)
    dates = sorted(set(daily_by_date) | set(price_daily) | set(event_daily))
    rows = []
    for session_date in dates:
        strike_rows = daily_by_date.get(session_date, [])
        price = price_daily.get(session_date, {})
        event = event_daily.get(session_date, {})
        basis_values = [_optional_float(row.get("basis")) for row in strike_rows]
        basis_values = [value for value in basis_values if value is not None]
        iv_values = [_optional_float(row.get("mean_iv_percent")) for row in strike_rows]
        iv_values = [value for value in iv_values if value is not None]
        total_oi = sum(_optional_float(row.get("total_oi")) or 0.0 for row in strike_rows)
        total_volume = sum(_optional_float(row.get("total_volume")) or 0.0 for row in strike_rows)
        total_oi_change = sum(_optional_float(row.get("total_oi_change")) or 0.0 for row in strike_rows)
        dtes = [_optional_float(row.get("dte")) for row in strike_rows]
        dtes = [value for value in dtes if value is not None]
        futures_price = _last_non_null([row.get("futures_price") for row in strike_rows], price.get("futures_reference_price"))
        spot_price = _last_non_null([row.get("spot_price") for row in strike_rows], price.get("xauusd_spot_or_proxy_price"))
        session_open = _last_non_null([row.get("session_open") for row in strike_rows], price.get("price_session_open"))
        row = {
            "session_date": session_date,
            "day_of_week": _day_of_week(session_date),
            "strike_expiry_rows": len(strike_rows),
            "strike_count": len({row.get("strike") for row in strike_rows}),
            "expiry_count": len({row.get("expiry") for row in strike_rows}),
            "nearest_dte": min(dtes) if dtes else None,
            "expiry_bucket": _expiry_bucket(min(dtes) if dtes else None),
            "is_expiry_day": any((value <= 0 for value in dtes)),
            "total_oi": total_oi if strike_rows else None,
            "total_volume": total_volume if strike_rows else None,
            "total_oi_change": total_oi_change if strike_rows else None,
            "mean_iv_percent": sum(iv_values) / len(iv_values) if iv_values else price.get("price_iv_percent"),
            "realized_vol_percent": price.get("realized_vol_percent"),
            "vrp": price.get("vrp"),
            "term_structure_regime": price.get("term_structure_regime") or "",
            "futures_reference_price": futures_price,
            "xauusd_spot_or_proxy_price": spot_price,
            "basis": sum(basis_values) / len(basis_values) if basis_values else None,
            "session_open": session_open,
            "event_tags": event.get("event_tags") or "",
            "has_cpi": bool(event.get("has_cpi")),
            "has_nfp": bool(event.get("has_nfp")),
            "has_fomc": bool(event.get("has_fomc")),
            "dollar_regime_tag": event.get("dollar_regime_tag") or "UNKNOWN",
            "has_duplicate_conflict": any(bool(row.get("has_conflict")) for row in strike_rows),
        }
        row.update(_session_field_flags(row, strike_rows))
        rows.append(row)
    return pl.DataFrame(rows, infer_schema_length=None) if rows else pl.DataFrame(schema=_session_schema())


def build_coverage_report(session_panel: pl.DataFrame) -> pl.DataFrame:
    """Create one coverage row per session date."""

    if session_panel.is_empty():
        return pl.DataFrame(schema=_coverage_schema())
    rows = []
    for row in session_panel.to_dicts():
        missing = [field for field, flag, _severity in VALIDATION_FIELDS if not bool(row.get(flag))]
        complete = len(missing) == 0 and not bool(row.get("has_duplicate_conflict"))
        rows.append(
            {
                "session_date": row.get("session_date"),
                "day_of_week": row.get("day_of_week"),
                "strike_expiry_rows": row.get("strike_expiry_rows"),
                "expiry_count": row.get("expiry_count"),
                "strike_count": row.get("strike_count"),
                "has_cme_options_oi": row.get("has_cme_options_oi"),
                "has_oi_change": row.get("has_oi_change"),
                "has_intraday_volume": row.get("has_intraday_volume"),
                "has_iv_context": row.get("has_iv_context"),
                "has_futures_reference_price": row.get("has_futures_reference_price"),
                "has_xau_spot_or_proxy_price": row.get("has_xau_spot_or_proxy_price"),
                "has_basis": row.get("has_basis"),
                "has_session_open": row.get("has_session_open"),
                "has_event_calendar": row.get("has_event_calendar"),
                "has_duplicate_conflict": row.get("has_duplicate_conflict"),
                "complete_validation_day": complete,
                "missing_fields": "|".join(missing),
                "reason_if_not_complete": "complete" if complete else _coverage_reason(missing, row),
            }
        )
    return pl.DataFrame(rows, infer_schema_length=None).sort("session_date")


def build_missing_field_report(coverage_report: pl.DataFrame) -> pl.DataFrame:
    """Expand missing validation fields into an auditable daily report."""

    rows = []
    for row in coverage_report.to_dicts():
        for field, flag, severity in VALIDATION_FIELDS:
            if bool(row.get(flag)):
                continue
            rows.append(
                {
                    "session_date": row.get("session_date"),
                    "missing_field": field,
                    "severity": severity,
                    "blocks_full_proof": True,
                    "remediation": _field_remediation(field),
                }
            )
        if bool(row.get("has_duplicate_conflict")):
            rows.append(
                {
                    "session_date": row.get("session_date"),
                    "missing_field": "duplicate_or_conflicting_snapshot_resolution",
                    "severity": "MEDIUM",
                    "blocks_full_proof": True,
                    "remediation": "Review duplicate/conflict report and confirm the latest-snapshot policy is valid.",
                }
            )
    return pl.DataFrame(rows, infer_schema_length=None) if rows else pl.DataFrame(schema=_missing_schema())


def build_duplicate_conflict_report(option_rows: pl.DataFrame) -> pl.DataFrame:
    """Report duplicate daily keys and conflicting values before latest-snapshot resolution."""

    if option_rows.is_empty():
        return pl.DataFrame(schema=_duplicate_schema())
    groups: dict[tuple[str, str, str, float, str], list[dict[str, Any]]] = {}
    for row in option_rows.to_dicts():
        key = (
            str(row.get("session_date") or ""),
            str(row.get("expiry") or ""),
            str(row.get("expiry_date") or ""),
            float(row.get("strike") or 0.0),
            str(row.get("option_type") or "unknown"),
        )
        groups.setdefault(key, []).append(row)
    rows = []
    for key, group in groups.items():
        if len(group) <= 1:
            continue
        conflict_fields = []
        for field in ["open_interest", "oi_change", "volume", "iv_percent", "futures_price", "spot_price"]:
            values = {_round_for_conflict(row.get(field)) for row in group if row.get(field) is not None}
            if len(values) > 1:
                conflict_fields.append(field)
        timestamps = {str(row.get("timestamp")) for row in group}
        sources = {str(row.get("source_id_hash")) for row in group}
        rows.append(
            {
                "session_date": key[0],
                "expiry": key[1],
                "expiry_date": key[2],
                "strike": key[3],
                "option_type": key[4],
                "row_count": len(group),
                "timestamp_count": len(timestamps),
                "source_count": len(sources),
                "conflict_fields": "|".join(conflict_fields),
                "has_conflict": bool(conflict_fields),
                "resolution": "latest_non_null_metric_by_session_selected",
            }
        )
    return pl.DataFrame(rows, infer_schema_length=None) if rows else pl.DataFrame(schema=_duplicate_schema())


def summarize_cme_history_normalization(
    *,
    daily_panel: pl.DataFrame,
    session_panel: pl.DataFrame,
    coverage_report: pl.DataFrame,
    missing_field_report: pl.DataFrame,
    duplicate_conflict_report: pl.DataFrame,
    source_inventory: pl.DataFrame,
) -> CmeHistoryNormalizerResult:
    """Summarize first/last validation-grade dates and missing proof fields."""

    complete = (
        coverage_report.filter(pl.col("complete_validation_day"))
        if not coverage_report.is_empty()
        else coverage_report
    )
    first_date = complete.get_column("session_date").min() if not complete.is_empty() else None
    last_date = complete.get_column("session_date").max() if not complete.is_empty() else None
    missing_fields = (
        tuple(sorted(set(missing_field_report.get_column("missing_field").to_list())))
        if not missing_field_report.is_empty()
        else ()
    )
    return CmeHistoryNormalizerResult(
        daily_panel=daily_panel,
        session_panel=session_panel,
        coverage_report=coverage_report,
        missing_field_report=missing_field_report,
        duplicate_conflict_report=duplicate_conflict_report,
        source_inventory=source_inventory,
        first_validation_grade_date=first_date,
        last_validation_grade_date=last_date,
        complete_validation_days=complete.height,
        missing_fields_for_full_proof=missing_fields,
    )


def cme_history_coverage_markdown(result: CmeHistoryNormalizerResult) -> str:
    """Render a compact Markdown coverage report."""

    lines = [
        "# CME History Normalization Coverage",
        "",
        "Research-only local normalization. No live trading, scraping replay, secrets, or broker integration.",
        "",
        f"- First validation-grade date: `{result.first_validation_grade_date or 'n/a'}`",
        f"- Last validation-grade date: `{result.last_validation_grade_date or 'n/a'}`",
        f"- Complete validation-grade days: {result.complete_validation_days}",
        f"- Daily strike-expiry rows: {result.daily_panel.height}",
        f"- Session rows: {result.session_panel.height}",
        f"- Source files inspected: {result.source_inventory.height}",
        f"- Duplicate/conflict rows: {result.duplicate_conflict_report.height}",
        "",
        "## Missing Fields For Full Proof",
        "",
        *[f"- `{field}`" for field in result.missing_fields_for_full_proof],
        "",
        "## Coverage By Session",
        "",
        _frame_markdown(
            result.coverage_report.select(
                [
                    column
                    for column in [
                        "session_date",
                        "complete_validation_day",
                        "strike_expiry_rows",
                        "expiry_count",
                        "strike_count",
                        "missing_fields",
                        "reason_if_not_complete",
                    ]
                    if column in result.coverage_report.columns
                ]
            )
            if not result.coverage_report.is_empty()
            else result.coverage_report
        ),
    ]
    return "\n".join(lines)


def _normalize_row_option_frame(
    path: str | Path,
    frame: pl.DataFrame,
    *,
    source_id: str,
    recovery_config: RecoveryAuditConfig | None,
) -> list[dict[str, Any]]:
    path_obj = Path(path)
    redacted = redact_path(str(path_obj), recovery_config)
    timestamp_col = _find_optional_column(frame.columns, TIMESTAMP_ALIASES)
    strike_col = _find_optional_column(frame.columns, STRIKE_ALIASES)
    expiry_col = _find_optional_column(frame.columns, EXPIRY_ALIASES)
    dte_col = _find_optional_column(frame.columns, DTE_ALIASES)
    option_type_col = _find_optional_column(frame.columns, OPTION_TYPE_ALIASES)
    oi_col = _find_optional_column(frame.columns, OPEN_INTEREST_ALIASES)
    call_oi_col = _find_optional_column(frame.columns, CALL_OI_ALIASES)
    put_oi_col = _find_optional_column(frame.columns, PUT_OI_ALIASES)
    oi_change_col = _find_optional_column(frame.columns, OI_CHANGE_ALIASES)
    call_oi_change_col = _find_optional_column(frame.columns, CALL_OI_CHANGE_ALIASES)
    put_oi_change_col = _find_optional_column(frame.columns, PUT_OI_CHANGE_ALIASES)
    volume_col = _find_optional_column(frame.columns, VOLUME_ALIASES)
    call_volume_col = _find_optional_column(frame.columns, CALL_VOLUME_ALIASES)
    put_volume_col = _find_optional_column(frame.columns, PUT_VOLUME_ALIASES)
    iv_col = _find_optional_column(frame.columns, IV_ALIASES)
    call_iv_col = _find_optional_column(frame.columns, CALL_IV_ALIASES)
    put_iv_col = _find_optional_column(frame.columns, PUT_IV_ALIASES)
    futures_col = _find_optional_column(frame.columns, FUTURES_PRICE_ALIASES)
    spot_col = _find_optional_column(frame.columns, SPOT_PRICE_ALIASES)
    session_open_col = _find_optional_column(frame.columns, SESSION_OPEN_ALIASES)
    settlement_col = _find_optional_column(frame.columns, SETTLEMENT_ALIASES)
    futures_symbol_col = _find_optional_column(frame.columns, FUTURES_SYMBOL_ALIASES)
    source_view_col = _find_optional_column(frame.columns, SOURCE_VIEW_ALIASES)
    label_col = _find_optional_column(frame.columns, LABEL_ALIASES)
    expected_range_col = _find_optional_column(frame.columns, EXPECTED_RANGE_ALIASES)

    if strike_col is None:
        return []
    rows = []
    for index, raw in enumerate(frame.to_dicts(), start=1):
        timestamp = _parse_timestamp(raw.get(timestamp_col), fallback=_date_from_filename(path_obj), row=index)
        if timestamp is None:
            continue
        strike = _optional_float(raw.get(strike_col))
        if strike is None:
            continue
        label = " ".join(str(raw.get(column) or "") for column in [label_col, source_view_col] if column)
        raw_dte = _optional_float(raw.get(dte_col))
        label_dte = _parse_dte_from_label(label)
        expiry_date = _parse_expiry_date(raw.get(expiry_col), timestamp=timestamp, dte=label_dte or raw_dte, label=label)
        dte = float((expiry_date - timestamp.date()).days) if expiry_date else _plausible_dte(label_dte or raw_dte)
        expiry = expiry_date.isoformat() if expiry_date else str(raw.get(expiry_col) or "UNKNOWN")
        common = {
            "timestamp": timestamp,
            "session_date": timestamp.date().isoformat(),
            "source_id_hash": source_id,
            "redacted_file_path": redacted,
            "file_name": path_obj.name,
            "source_kind": _source_metric_from_path(path_obj),
            "source_view": str(raw.get(source_view_col) or ""),
            "futures_symbol": str(raw.get(futures_symbol_col) or "GC"),
            "expiry": expiry,
            "expiry_date": expiry_date.isoformat() if expiry_date else "",
            "dte": dte,
            "strike": strike,
            "expected_range": _optional_float(raw.get(expected_range_col)),
            "settlement_price": _optional_float(raw.get(settlement_col)),
            "futures_price": _optional_float(raw.get(futures_col)),
            "spot_price": _optional_float(raw.get(spot_col)),
            "session_open": _optional_float(raw.get(session_open_col)),
        }
        option_type = _normalize_option_type(raw.get(option_type_col)) if option_type_col else "unknown"
        if option_type in {"call", "put"}:
            rows.append(
                _option_record(
                    common,
                    option_type=option_type,
                    open_interest=_optional_float(raw.get(oi_col)),
                    oi_change=_optional_float(raw.get(oi_change_col)),
                    volume=_optional_float(raw.get(volume_col)),
                    iv_percent=_normalize_iv(_optional_float(raw.get(iv_col))),
                )
            )
            continue
        if call_oi_col or call_oi_change_col or call_volume_col or call_iv_col:
            rows.append(
                _option_record(
                    common,
                    option_type="call",
                    open_interest=_optional_float(raw.get(call_oi_col)),
                    oi_change=_optional_float(raw.get(call_oi_change_col)) or _optional_float(raw.get(oi_change_col)),
                    volume=_optional_float(raw.get(call_volume_col)) or _optional_float(raw.get(volume_col)),
                    iv_percent=_normalize_iv(_optional_float(raw.get(call_iv_col)) or _optional_float(raw.get(iv_col))),
                )
            )
        if put_oi_col or put_oi_change_col or put_volume_col or put_iv_col:
            rows.append(
                _option_record(
                    common,
                    option_type="put",
                    open_interest=_optional_float(raw.get(put_oi_col)),
                    oi_change=_optional_float(raw.get(put_oi_change_col)) or _optional_float(raw.get(oi_change_col)),
                    volume=_optional_float(raw.get(put_volume_col)) or _optional_float(raw.get(volume_col)),
                    iv_percent=_normalize_iv(_optional_float(raw.get(put_iv_col)) or _optional_float(raw.get(iv_col))),
                )
            )
        if not (call_oi_col or put_oi_col):
            rows.append(
                _option_record(
                    common,
                    option_type="unknown",
                    open_interest=_optional_float(raw.get(oi_col)),
                    oi_change=_optional_float(raw.get(oi_change_col)),
                    volume=_optional_float(raw.get(volume_col)),
                    iv_percent=_normalize_iv(_optional_float(raw.get(iv_col))),
                )
            )
    return rows


def _normalize_wide_matrix_frame(
    path: str | Path,
    frame: pl.DataFrame,
    *,
    source_id: str,
    recovery_config: RecoveryAuditConfig | None,
) -> list[dict[str, Any]]:
    path_obj = Path(path)
    redacted = redact_path(str(path_obj), recovery_config)
    strike_col = _find_optional_column(frame.columns, STRIKE_ALIASES) or frame.columns[0]
    timestamp_col = _find_optional_column(frame.columns, TIMESTAMP_ALIASES)
    source_metric = _source_metric_from_path(path_obj)
    rows = []
    for index, raw in enumerate(frame.to_dicts(), start=1):
        timestamp = _parse_timestamp(raw.get(timestamp_col), fallback=_date_from_filename(path_obj), row=index)
        if timestamp is None:
            continue
        strike = _optional_float(raw.get(strike_col))
        if strike is None:
            continue
        for column in frame.columns:
            if column == strike_col or column == timestamp_col:
                continue
            value = _optional_float(raw.get(column))
            if value is None:
                continue
            label = str(column)
            option_type = _parse_option_type_from_label(label)
            dte = _parse_dte_from_label(label)
            expiry_date = _parse_expiry_date(None, timestamp=timestamp, dte=dte, label=label)
            common = {
                "timestamp": timestamp,
                "session_date": timestamp.date().isoformat(),
                "source_id_hash": source_id,
                "redacted_file_path": redacted,
                "file_name": path_obj.name,
                "source_kind": source_metric,
                "source_view": source_metric,
                "futures_symbol": "GC",
                "expiry": expiry_date.isoformat() if expiry_date else label[:80],
                "expiry_date": expiry_date.isoformat() if expiry_date else "",
                "dte": float((expiry_date - timestamp.date()).days) if expiry_date else _plausible_dte(dte),
                "strike": strike,
                "expected_range": None,
                "settlement_price": None,
                "futures_price": _parse_futures_price_from_label(label),
                "spot_price": None,
                "session_open": None,
            }
            rows.append(
                _option_record(
                    common,
                    option_type=option_type,
                    open_interest=value if source_metric == "open_interest_matrix" else None,
                    oi_change=value if source_metric == "oi_change_matrix" else None,
                    volume=value if source_metric == "volume_matrix" else None,
                    iv_percent=_normalize_iv(value) if source_metric == "iv_context" else None,
                )
            )
    return rows


def _option_record(
    common: dict[str, Any],
    *,
    option_type: str,
    open_interest: float | None,
    oi_change: float | None,
    volume: float | None,
    iv_percent: float | None,
) -> dict[str, Any]:
    return {
        **common,
        "option_type": option_type,
        "open_interest": open_interest,
        "oi_change": oi_change,
        "volume": volume,
        "iv_percent": iv_percent,
    }


def _price_daily(price_rows: pl.DataFrame) -> pl.DataFrame:
    if price_rows.is_empty():
        return pl.DataFrame(schema=_price_daily_schema())
    return price_rows.sort("timestamp").group_by("session_date", maintain_order=True).agg(
        [
            pl.col("futures_price").drop_nulls().last().alias("futures_reference_price"),
            pl.col("spot_price").drop_nulls().last().alias("xauusd_spot_or_proxy_price"),
            pl.col("session_open").drop_nulls().first().alias("price_session_open"),
            pl.col("iv_percent").drop_nulls().last().alias("price_iv_percent"),
            pl.col("realized_vol_percent").drop_nulls().last().alias("realized_vol_percent"),
            pl.col("vrp").drop_nulls().last().alias("vrp"),
            pl.col("expected_range").drop_nulls().last().alias("price_expected_range"),
            pl.col("term_structure_regime").drop_nulls().last().alias("term_structure_regime"),
        ]
    )


def _event_daily(event_rows: pl.DataFrame) -> pl.DataFrame:
    if event_rows.is_empty():
        return pl.DataFrame(schema=_event_daily_schema())
    rows = []
    for session_date, group in _group_dicts(event_rows.to_dicts(), "session_date").items():
        tags = sorted(
            {
                tag
                for row in group
                for tag in str(row.get("event_tags") or "").split("|")
                if tag
            }
        )
        dollar_tags = [str(row.get("dollar_regime_tag") or "") for row in group if row.get("dollar_regime_tag")]
        rows.append(
            {
                "session_date": session_date,
                "event_tags": "|".join(tags),
                "has_cpi": "CPI" in tags,
                "has_nfp": "NFP" in tags,
                "has_fomc": "FOMC" in tags,
                "dollar_regime_tag": dollar_tags[-1] if dollar_tags else "",
            }
        )
    return pl.DataFrame(rows, infer_schema_length=None)


def _session_field_flags(row: dict[str, Any], strike_rows: list[dict[str, Any]]) -> dict[str, bool]:
    has_oi_change = any(item.get("total_oi_change") is not None for item in strike_rows)
    has_volume = any(item.get("total_volume") is not None for item in strike_rows)
    has_iv = any(item.get("mean_iv_percent") is not None for item in strike_rows) or row.get("mean_iv_percent") is not None
    has_futures = row.get("futures_reference_price") is not None
    has_spot = row.get("xauusd_spot_or_proxy_price") is not None
    return {
        "has_cme_options_oi": bool(strike_rows) and any((_optional_float(item.get("total_oi")) or 0.0) > 0 for item in strike_rows),
        "has_oi_change": has_oi_change,
        "has_intraday_volume": has_volume,
        "has_iv_context": has_iv,
        "has_futures_reference_price": has_futures,
        "has_xau_spot_or_proxy_price": has_spot,
        "has_basis": row.get("basis") is not None,
        "has_session_open": row.get("session_open") is not None,
        "has_event_calendar": bool(row.get("event_tags")),
    }


def _daily_row_validation_grade(row: dict[str, Any], basis: float | None) -> bool:
    return all(
        [
            (_optional_float(row.get("total_oi")) or 0.0) > 0,
            row.get("total_oi_change") is not None,
            row.get("total_volume") is not None,
            row.get("mean_iv_percent") is not None,
            row.get("futures_price") is not None,
            row.get("spot_price") is not None,
            basis is not None,
            row.get("session_open") is not None,
            bool(row.get("event_tags")),
        ]
    )


def _coverage_reason(missing: list[str], row: dict[str, Any]) -> str:
    reasons = []
    if missing:
        reasons.append("missing " + ", ".join(missing))
    if bool(row.get("has_duplicate_conflict")):
        reasons.append("duplicate/conflict review required")
    return "; ".join(reasons) if reasons else "incomplete"


def _field_remediation(field: str) -> str:
    return {
        "cme_options_oi": "Load CME/QuikStrike OI Matrix or option open interest export for this session.",
        "oi_change": "Load OI Change Matrix or an export containing open interest change.",
        "intraday_volume": "Load Volume Matrix or a source containing same-session option volume.",
        "iv_context": "Load Vol2Vol, option settlements, or IV/expected-range context.",
        "futures_reference_price": "Load GC futures reference price or ensure option exports include underlying futures price.",
        "xau_spot_or_proxy_price": "Load XAU/USD spot or an explicitly labeled proxy price source.",
        "futures_to_spot_basis": "Provide same-session futures and spot/proxy prices so basis can be computed.",
        "session_open": "Load session open from OHLC data or a session-level reference file.",
        "event_calendar_tags": "Load CPI/NFP/FOMC/event calendar rows for this session.",
    }.get(field, "Review local data coverage and source mapping.")


def _event_tags(name: str, explicit: Any) -> list[str]:
    text = f"{name} {explicit or ''}".upper()
    tags = []
    if "CPI" in text or "INFLATION" in text:
        tags.append("CPI")
    if "NFP" in text or "NONFARM" in text or "PAYROLL" in text:
        tags.append("NFP")
    if "FOMC" in text or "FED" in text or "POWELL" in text:
        tags.append("FOMC")
    if "DXY" in text or "DOLLAR" in text or "USD" in text:
        tags.append("DOLLAR")
    if not tags and str(name).strip():
        tags.append("OTHER_EVENT")
    return tags


def _source_metric_from_path(path: Path) -> str:
    text = path.as_posix().lower()
    if "change" in text:
        return "oi_change_matrix"
    if "volume" in text:
        return "volume_matrix"
    if "vol2vol" in text or "implied" in text or " iv" in text or "_iv" in text:
        return "iv_context"
    if "settlement" in text:
        return "option_settlement"
    return "open_interest_matrix"


def _price_role(path: Path, symbol: str) -> str:
    text = f"{path.as_posix()} {symbol}".lower()
    if "xau" in text or "spot" in text:
        return "spot"
    if "gc=f" in text or "gc" in text or "future" in text:
        return "futures"
    return "unknown"


def _symbol_from_path(path: Path) -> str | None:
    text = path.name.lower()
    if "gc=f" in text:
        return "GC=F"
    if "xau" in text:
        return "XAUUSD"
    if "gold" in text or "gc" in text:
        return "GC"
    return None


def _parse_timestamp(value: Any, *, fallback: date | None, row: int) -> datetime | None:
    if value is None or value == "":
        return datetime.combine(fallback, time.min, tzinfo=UTC) if fallback else None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, time.min)
    else:
        text = str(value).strip()
        if not text:
            return datetime.combine(fallback, time.min, tzinfo=UTC) if fallback else None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            if fallback:
                return datetime.combine(fallback, time.min, tzinfo=UTC)
            raise ValueError(f"row {row}: timestamp is not parseable") from exc
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _parse_expiry_date(value: Any, *, timestamp: datetime, dte: float | None, label: str) -> date | None:
    label_match = EXPIRY_RE.search(label or "")
    if label_match:
        parsed = _parse_date_text(label_match.group("date"))
        if parsed:
            return parsed
    parsed_value = _parse_date_text(value)
    if parsed_value:
        return parsed_value
    plausible_dte = _plausible_dte(dte)
    if plausible_dte is not None:
        return timestamp.date() + timedelta(days=int(plausible_dte))
    return None


def _parse_date_text(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    iso_match = ISO_DATE_RE.search(text)
    if iso_match:
        return date(
            int(iso_match.group("year")),
            int(iso_match.group("month")),
            int(iso_match.group("day")),
        )
    slash = re.search(r"(?P<month>\d{1,2})[/-](?P<day>\d{1,2})[/-](?P<year>\d{2,4})", text)
    if slash:
        year = int(slash.group("year"))
        if year < 100:
            year += 2000
        return date(year, int(slash.group("month")), int(slash.group("day")))
    return None


def _parse_dte_from_label(label: str) -> float | None:
    preferred = DTE_BEFORE_EXPIRES_RE.search(label or "")
    if preferred:
        return float(preferred.group("dte"))
    matches = DTE_RE.findall(label or "")
    if matches:
        return float(matches[-1])
    return None


def _parse_option_type_from_label(label: str) -> str:
    tokens = re.split(r"[^A-Za-z]+", label.upper())
    if tokens and tokens[-1] in {"C", "CALL"}:
        return "call"
    if tokens and tokens[-1] in {"P", "PUT"}:
        return "put"
    if "CALL" in tokens:
        return "call"
    if "PUT" in tokens:
        return "put"
    return "unknown"


def _parse_futures_price_from_label(label: str) -> float | None:
    numbers = [float(item) for item in re.findall(r"\b\d{3,5}(?:\.\d+)?\b", label)]
    plausible = [value for value in numbers if 1000 <= value <= 10000]
    return plausible[0] if plausible else None


def _plausible_dte(value: float | None) -> float | None:
    if value is None:
        return None
    return float(value) if 0 <= value <= 730 else None


def _normalize_option_type(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"c", "call", "calls"}:
        return "call"
    if normalized in {"p", "put", "puts"}:
        return "put"
    return "unknown"


def _normalize_iv(value: float | None) -> float | None:
    if value is None:
        return None
    if value <= 1.0:
        return value * 100.0
    return value


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed


def _date_from_filename(path: Path) -> date | None:
    match = re.search(r"(20\d{2})[-_]?(\d{2})[-_]?(\d{2})", path.name)
    if not match:
        return None
    return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))


def _day_of_week(session_date: str) -> str:
    try:
        return date.fromisoformat(session_date).strftime("%A")
    except ValueError:
        return "UNKNOWN"


def _expiry_bucket(dte: float | None) -> str:
    if dte is None:
        return "UNKNOWN"
    if dte <= 0:
        return "EXPIRY_DAY"
    if dte <= 3:
        return "0_3D"
    if dte <= 7:
        return "4_7D"
    if dte <= 30:
        return "8_30D"
    return "31D_PLUS"


def _expiration_proximity(dte: float | None) -> str:
    if dte is None:
        return "UNKNOWN"
    if dte <= 0:
        return "EXPIRING"
    if dte <= 3:
        return "NEAR_EXPIRY"
    if dte <= 7:
        return "WEEKLY"
    return "STANDARD"


def _sum_type(option_type: str, column: str, alias: str) -> pl.Expr:
    return (
        pl.when(pl.col("option_type") == option_type)
        .then(pl.col(column))
        .otherwise(None)
        .drop_nulls()
        .sum()
        .alias(alias)
    )


def _mean_type(option_type: str, column: str, alias: str) -> pl.Expr:
    return (
        pl.when(pl.col("option_type") == option_type)
        .then(pl.col(column))
        .otherwise(None)
        .drop_nulls()
        .mean()
        .alias(alias)
    )


def _last_non_null(values: list[Any], fallback: Any = None) -> Any:
    for value in reversed(values):
        if value is not None:
            return value
    return fallback


def _round_for_conflict(value: Any) -> Any:
    parsed = _optional_float(value)
    return round(parsed, 8) if parsed is not None else str(value)


def _daily_conflict_key(row: dict[str, Any]) -> tuple[str, str, str, float]:
    return (
        str(row.get("session_date") or ""),
        str(row.get("expiry") or ""),
        str(row.get("expiry_date") or ""),
        float(row.get("strike") or 0.0),
    )


def _conflict_key_set(conflicts: pl.DataFrame) -> set[tuple[str, str, str, float]]:
    return {_daily_conflict_key(row) for row in conflicts.to_dicts()} if not conflicts.is_empty() else set()


def _group_dicts(rows: list[dict[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get(key) or ""), []).append(row)
    return grouped


def _concat_or_empty(frames: list[pl.DataFrame], schema: dict[str, Any]) -> pl.DataFrame:
    return pl.concat(frames, how="diagonal_relaxed") if frames else pl.DataFrame(schema=schema)


def _frame_or_empty(frame: pl.DataFrame | None, schema: dict[str, Any]) -> pl.DataFrame:
    return frame if frame is not None else pl.DataFrame(schema=schema)


def _is_generated_cme_output(path: Path) -> bool:
    name = path.name.lower()
    return name.startswith(("cme_daily_", "cme_session_", "cme_history_"))


def _frame_date_start(frame: pl.DataFrame) -> str | None:
    dates = _frame_dates(frame)
    return min(dates).isoformat() if dates else None


def _frame_date_end(frame: pl.DataFrame) -> str | None:
    dates = _frame_dates(frame)
    return max(dates).isoformat() if dates else None


def _frame_dates(frame: pl.DataFrame) -> list[date]:
    timestamp_col = _find_optional_column(frame.columns, TIMESTAMP_ALIASES)
    if timestamp_col is None:
        return []
    dates = []
    for index, row in enumerate(frame.to_dicts(), start=1):
        parsed = _parse_timestamp(row.get(timestamp_col), fallback=None, row=index)
        if parsed:
            dates.append(parsed.date())
    return dates


def _find_optional_column(columns: Iterable[str], aliases: Iterable[str]) -> str | None:
    lookup = {column.lower(): column for column in columns}
    for alias in aliases:
        match = lookup.get(alias.lower())
        if match is not None:
            return match
    return None


def _has_column(frame: pl.DataFrame, aliases: Iterable[str]) -> bool:
    return _find_optional_column(frame.columns, aliases) is not None


def _has_any(lower_cols: set[str], aliases: Iterable[str]) -> bool:
    alias_set = {alias.lower() for alias in aliases}
    return any(column in alias_set for column in lower_cols)


def _frame_markdown(frame: pl.DataFrame) -> str:
    if frame.is_empty():
        return "_No rows._"
    columns = frame.columns
    rows = frame.head(20).to_dicts()
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_markdown_cell(row.get(column, "")) for column in columns) + " |")
    return "\n".join(lines)


def _markdown_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


TIMESTAMP_ALIASES = ("timestamp", "datetime", "date", "time", "session_date", "trade_date")
SYMBOL_ALIASES = ("symbol", "ticker", "futures_symbol", "underlying")
OPEN_ALIASES = ("open", "Open", "session_open")
HIGH_ALIASES = ("high", "High")
LOW_ALIASES = ("low", "Low")
CLOSE_ALIASES = ("close", "Close", "last", "price", "settle", "settlement")
STRIKE_ALIASES = ("strike", "option_strike", "cme_option_strike", "table_row_label")
EXPIRY_ALIASES = ("expiry", "expiration", "expiration_date", "expiry_date")
DTE_ALIASES = ("dte", "days_to_expiry", "DTE")
OPTION_TYPE_ALIASES = ("option_type", "put_call", "type", "side")
OPEN_INTEREST_ALIASES = ("open_interest", "total_oi", "oi", "Open Interest")
CALL_OI_ALIASES = ("call_oi", "calls_oi", "call_open_interest")
PUT_OI_ALIASES = ("put_oi", "puts_oi", "put_open_interest")
OI_CHANGE_ALIASES = ("oi_change", "open_interest_change", "change_oi")
CALL_OI_CHANGE_ALIASES = ("call_oi_change", "call_open_interest_change")
PUT_OI_CHANGE_ALIASES = ("put_oi_change", "put_open_interest_change")
VOLUME_ALIASES = ("volume", "Volume", "intraday_volume")
CALL_VOLUME_ALIASES = ("call_volume", "calls_volume")
PUT_VOLUME_ALIASES = ("put_volume", "puts_volume")
IV_ALIASES = ("iv", "implied_volatility", "annualized_iv_percent", "implied_volatility_percent", "iv_percent")
CALL_IV_ALIASES = ("call_iv", "call_iv_percent", "call_implied_volatility")
PUT_IV_ALIASES = ("put_iv", "put_iv_percent", "put_implied_volatility")
REALIZED_VOL_ALIASES = ("realized_vol", "realized_volatility", "rv_percent", "realized_vol_percent")
VRP_ALIASES = ("vrp", "iv_rv_spread", "vol_risk_premium")
FUTURES_PRICE_ALIASES = ("gold_futures_price", "underlying_futures_price", "futures_price", "gc_price")
SPOT_PRICE_ALIASES = ("xauusd_spot_price", "spot_price", "xauusd", "xau_price")
SESSION_OPEN_ALIASES = ("session_open", "xau_session_open", "open_price")
SETTLEMENT_ALIASES = ("settlement_price", "option_settlement", "settlement")
FUTURES_SYMBOL_ALIASES = ("futures_symbol", "underlying_symbol", "symbol")
SOURCE_VIEW_ALIASES = ("source_view", "source_menu", "view", "matrix")
LABEL_ALIASES = ("table_column_label", "column_label", "label")
EXPECTED_RANGE_ALIASES = ("expected_range", "expected_move", "one_sd_range", "vol2vol_expected_range")
TERM_STRUCTURE_ALIASES = ("term_structure_regime", "term_structure", "vol_term_structure")
EVENT_ALIASES = ("event_name", "event", "calendar_event", "macro_event")
EVENT_TAG_ALIASES = ("event_tag", "event_tags", "tag", "regime_tag")
DOLLAR_REGIME_ALIASES = ("dollar_regime", "dxy_regime", "usd_regime")
OPTION_ROW_HINT_ALIASES = (
    OPEN_INTEREST_ALIASES
    + CALL_OI_ALIASES
    + PUT_OI_ALIASES
    + OPTION_TYPE_ALIASES
    + OI_CHANGE_ALIASES
    + VOLUME_ALIASES
    + IV_ALIASES
)


def _option_schema() -> dict[str, Any]:
    return {
        "timestamp": pl.Datetime(time_zone="UTC"),
        "session_date": pl.String,
        "source_id_hash": pl.String,
        "redacted_file_path": pl.String,
        "file_name": pl.String,
        "source_kind": pl.String,
        "source_view": pl.String,
        "futures_symbol": pl.String,
        "expiry": pl.String,
        "expiry_date": pl.String,
        "dte": pl.Float64,
        "strike": pl.Float64,
        "option_type": pl.String,
        "open_interest": pl.Float64,
        "oi_change": pl.Float64,
        "volume": pl.Float64,
        "iv_percent": pl.Float64,
        "expected_range": pl.Float64,
        "settlement_price": pl.Float64,
        "futures_price": pl.Float64,
        "spot_price": pl.Float64,
        "session_open": pl.Float64,
    }


def _price_schema() -> dict[str, Any]:
    return {
        "timestamp": pl.Datetime(time_zone="UTC"),
        "session_date": pl.String,
        "source_id_hash": pl.String,
        "redacted_file_path": pl.String,
        "file_name": pl.String,
        "symbol": pl.String,
        "price_role": pl.String,
        "open": pl.Float64,
        "close": pl.Float64,
        "futures_price": pl.Float64,
        "spot_price": pl.Float64,
        "session_open": pl.Float64,
        "iv_percent": pl.Float64,
        "realized_vol_percent": pl.Float64,
        "vrp": pl.Float64,
        "expected_range": pl.Float64,
        "term_structure_regime": pl.String,
    }


def _event_schema() -> dict[str, Any]:
    return {
        "timestamp": pl.Datetime(time_zone="UTC"),
        "session_date": pl.String,
        "source_id_hash": pl.String,
        "redacted_file_path": pl.String,
        "file_name": pl.String,
        "event_name": pl.String,
        "event_tags": pl.String,
        "has_cpi": pl.Boolean,
        "has_nfp": pl.Boolean,
        "has_fomc": pl.Boolean,
        "dollar_regime_tag": pl.String,
    }


def _source_inventory_schema() -> dict[str, Any]:
    return {
        "source_id_hash": pl.String,
        "redacted_file_path": pl.String,
        "file_name": pl.String,
        "source_kind": pl.String,
        "load_status": pl.String,
        "row_count": pl.Int64,
        "column_count": pl.Int64,
        "columns_detected": pl.String,
        "date_start": pl.String,
        "date_end": pl.String,
        "notes": pl.String,
    }


def _daily_panel_schema() -> dict[str, Any]:
    return {
        "session_date": pl.String,
        "expiry": pl.String,
        "expiry_date": pl.String,
        "strike": pl.Float64,
        "panel_timestamp": pl.Datetime(time_zone="UTC"),
        "futures_symbol": pl.String,
        "dte": pl.Float64,
        "call_oi": pl.Float64,
        "put_oi": pl.Float64,
        "total_oi": pl.Float64,
        "call_oi_change": pl.Float64,
        "put_oi_change": pl.Float64,
        "total_oi_change": pl.Float64,
        "call_volume": pl.Float64,
        "put_volume": pl.Float64,
        "total_volume": pl.Float64,
        "call_iv_percent": pl.Float64,
        "put_iv_percent": pl.Float64,
        "mean_iv_percent": pl.Float64,
        "expected_range": pl.Float64,
        "futures_price": pl.Float64,
        "spot_price": pl.Float64,
        "basis": pl.Float64,
        "spot_equivalent_strike": pl.Float64,
        "session_open": pl.Float64,
        "event_tags": pl.String,
        "dollar_regime_tag": pl.String,
        "day_of_week": pl.String,
        "expiry_bucket": pl.String,
        "expiration_proximity": pl.String,
        "is_expiry_day": pl.Boolean,
        "has_conflict": pl.Boolean,
        "validation_grade": pl.Boolean,
    }


def _session_schema() -> dict[str, Any]:
    return {
        "session_date": pl.String,
        "day_of_week": pl.String,
        "strike_expiry_rows": pl.Int64,
        "strike_count": pl.Int64,
        "expiry_count": pl.Int64,
        "nearest_dte": pl.Float64,
        "expiry_bucket": pl.String,
        "is_expiry_day": pl.Boolean,
        "total_oi": pl.Float64,
        "total_volume": pl.Float64,
        "total_oi_change": pl.Float64,
        "mean_iv_percent": pl.Float64,
        "realized_vol_percent": pl.Float64,
        "vrp": pl.Float64,
        "term_structure_regime": pl.String,
        "futures_reference_price": pl.Float64,
        "xauusd_spot_or_proxy_price": pl.Float64,
        "basis": pl.Float64,
        "session_open": pl.Float64,
        "event_tags": pl.String,
        "has_cpi": pl.Boolean,
        "has_nfp": pl.Boolean,
        "has_fomc": pl.Boolean,
        "dollar_regime_tag": pl.String,
        "has_duplicate_conflict": pl.Boolean,
        "has_cme_options_oi": pl.Boolean,
        "has_oi_change": pl.Boolean,
        "has_intraday_volume": pl.Boolean,
        "has_iv_context": pl.Boolean,
        "has_futures_reference_price": pl.Boolean,
        "has_xau_spot_or_proxy_price": pl.Boolean,
        "has_basis": pl.Boolean,
        "has_session_open": pl.Boolean,
        "has_event_calendar": pl.Boolean,
    }


def _coverage_schema() -> dict[str, Any]:
    return {
        "session_date": pl.String,
        "day_of_week": pl.String,
        "strike_expiry_rows": pl.Int64,
        "expiry_count": pl.Int64,
        "strike_count": pl.Int64,
        "has_cme_options_oi": pl.Boolean,
        "has_oi_change": pl.Boolean,
        "has_intraday_volume": pl.Boolean,
        "has_iv_context": pl.Boolean,
        "has_futures_reference_price": pl.Boolean,
        "has_xau_spot_or_proxy_price": pl.Boolean,
        "has_basis": pl.Boolean,
        "has_session_open": pl.Boolean,
        "has_event_calendar": pl.Boolean,
        "has_duplicate_conflict": pl.Boolean,
        "complete_validation_day": pl.Boolean,
        "missing_fields": pl.String,
        "reason_if_not_complete": pl.String,
    }


def _missing_schema() -> dict[str, Any]:
    return {
        "session_date": pl.String,
        "missing_field": pl.String,
        "severity": pl.String,
        "blocks_full_proof": pl.Boolean,
        "remediation": pl.String,
    }


def _duplicate_schema() -> dict[str, Any]:
    return {
        "session_date": pl.String,
        "expiry": pl.String,
        "expiry_date": pl.String,
        "strike": pl.Float64,
        "option_type": pl.String,
        "row_count": pl.Int64,
        "timestamp_count": pl.Int64,
        "source_count": pl.Int64,
        "conflict_fields": pl.String,
        "has_conflict": pl.Boolean,
        "resolution": pl.String,
    }


def _price_daily_schema() -> dict[str, Any]:
    return {
        "session_date": pl.String,
        "futures_reference_price": pl.Float64,
        "xauusd_spot_or_proxy_price": pl.Float64,
        "price_session_open": pl.Float64,
        "price_iv_percent": pl.Float64,
        "realized_vol_percent": pl.Float64,
        "vrp": pl.Float64,
        "price_expected_range": pl.Float64,
        "term_structure_regime": pl.String,
    }


def _event_daily_schema() -> dict[str, Any]:
    return {
        "session_date": pl.String,
        "event_tags": pl.String,
        "has_cpi": pl.Boolean,
        "has_nfp": pl.Boolean,
        "has_fomc": pl.Boolean,
        "dollar_regime_tag": pl.String,
    }
