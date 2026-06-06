"""Local CME/QuikStrike history importer for validation-grade XAU research.

The importer reads user-provided local exports only. It does not fetch CME
data, replay browser sessions, connect to brokers, or create trading signals.
All source paths written to reports are redacted and paired with source hashes.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any, Iterable

import polars as pl

from research_xau_vol_oi.data_loader import DataLoadError, load_table
from research_xau_vol_oi.data_recovery_audit import (
    RecoveryAuditConfig,
    build_recovery_audit_config,
    hash_source_id,
    redact_path,
)


SUPPORTED_SUFFIXES = {".csv", ".xlsx", ".xls", ".parquet", ".json", ".jsonl", ".txt", ".tsv"}
DEFAULT_CME_IMPORT_ROOTS = (
    Path("data"),
    Path("data/cme"),
    Path("data/quikstrike"),
    Path("data/raw"),
    Path("data/vendor"),
    Path("backend/data/raw"),
    Path("backend/data/processed"),
    Path("backend/data/reports"),
    Path("outputs"),
)
GENERATED_OUTPUT_NAMES = {
    "cme_canonical_option_oi_by_strike.parquet",
    "cme_canonical_option_iv_by_strike.parquet",
    "cme_canonical_futures_price.parquet",
    "cme_canonical_xau_spot_price.parquet",
    "cme_canonical_basis.parquet",
    "xau_vol_oi_validation_dataset.parquet",
    "cme_validation_grade_days.csv",
    "cme_validation_grade_uplift.csv",
    "basis_adjustment_precision_report.csv",
    "cme_import_file_detection.csv",
    "cme_import_duplicate_conflict_report.csv",
    "cme_data_requirements_checklist.csv",
    "cme_canonical_macro_event_calendar.csv",
    "cme_daily_strike_expiry_panel.parquet",
    "cme_session_regime_panel.parquet",
    "oi_walls.csv",
    "signal_events.csv",
    "xau_feature_table.parquet",
    "gold_baseline_metrics.csv",
    "filter_avoided_pnl_report.csv",
    "cme_history_coverage_report.csv",
    "cme_history_missing_field_report.csv",
    "cme_history_duplicate_conflict_report.csv",
    "cme_history_source_inventory.csv",
    "current_cme_date_usability.csv",
    "current_cme_date_usability.md",
    "iv_field_mapping_audit.csv",
    "iv_field_mapping_audit.md",
    "spot_basis_join_audit.csv",
    "spot_basis_join_audit.md",
    "one_week_cme_pilot_summary.csv",
    "one_week_cme_pilot_report.md",
    "ohlc_guru_price_only_pilot.csv",
    "ohlc_guru_price_only_pilot.md",
    "cme_fetch_tool_gap_audit.csv",
    "cme_fetch_tool_gap_audit.md",
    "metadata.json",
    "report.json",
    "source_validation.json",
    "walls.parquet",
    "zones.parquet",
    "reactions.parquet",
    "risk_plans.parquet",
}
PRELIMINARY_VALIDATION_DAYS = 60
SERIOUS_VALIDATION_DAYS = 120
ROBUST_VALIDATION_DAYS = 250


@dataclass(frozen=True)
class CmeHistoryImporterConfig:
    """Read-only local import settings."""

    search_roots: tuple[Path, ...] = DEFAULT_CME_IMPORT_ROOTS
    redact_paths: bool = True
    minimum_preliminary_days: int = PRELIMINARY_VALIDATION_DAYS
    minimum_serious_days: int = SERIOUS_VALIDATION_DAYS
    minimum_robust_days: int = ROBUST_VALIDATION_DAYS


@dataclass(frozen=True)
class CmeHistoryImporterResult:
    """Canonical data and validation diagnostics from the importer."""

    file_detection: pl.DataFrame
    option_oi_by_strike: pl.DataFrame
    option_iv_by_strike: pl.DataFrame
    futures_price: pl.DataFrame
    xau_spot_price: pl.DataFrame
    basis: pl.DataFrame
    macro_event_calendar: pl.DataFrame
    validation_grade_days: pl.DataFrame
    validation_dataset: pl.DataFrame
    duplicate_conflict_report: pl.DataFrame
    basis_precision_report: pl.DataFrame
    validation_grade_uplift: pl.DataFrame
    data_requirements_checklist: pl.DataFrame
    orchestrator_context_markdown: str


def build_cme_history_importer_config(
    *,
    env_var: str = "XAU_CME_DATA_ROOTS",
) -> CmeHistoryImporterConfig:
    """Build config from safe defaults plus optional local env roots."""

    roots = list(DEFAULT_CME_IMPORT_ROOTS)
    raw = os.getenv(env_var)
    if raw:
        roots.extend(Path(item.strip()) for item in raw.split(os.pathsep) if item.strip())
    return CmeHistoryImporterConfig(search_roots=tuple(_dedupe_paths(roots)))


def run_cme_history_importer(
    *,
    output_dir: str | Path,
    input_paths: Iterable[str | Path] | None = None,
    importer_config: CmeHistoryImporterConfig | None = None,
    recovery_config: RecoveryAuditConfig | None = None,
) -> CmeHistoryImporterResult:
    """Run local import, write canonical outputs, and return diagnostics."""

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    config = importer_config or build_cme_history_importer_config()
    privacy = recovery_config or build_recovery_audit_config()
    paths = [Path(path) for path in input_paths] if input_paths is not None else discover_cme_history_import_files(
        config.search_roots,
    )
    loaded = load_and_detect_cme_files(paths, recovery_config=privacy)
    canonical = build_canonical_cme_tables(loaded)
    duplicate_conflicts = build_import_duplicate_conflict_report(canonical["option_oi_by_strike"])
    validation_days = classify_validation_grade_days(canonical)
    validation_dataset = build_validation_dataset(canonical, validation_days)
    basis_precision = compare_basis_adjustment_precision(canonical, validation_dataset)
    uplift = build_validation_grade_uplift_report(validation_dataset)
    checklist = build_cme_data_requirements_checklist(
        loaded["file_detection"],
        validation_days,
    )
    context = orchestrator_gpt_context_markdown(
        file_detection=loaded["file_detection"],
        canonical=canonical,
        validation_days=validation_days,
        basis_precision=basis_precision,
        uplift=uplift,
        checklist=checklist,
        config=config,
    )
    result = CmeHistoryImporterResult(
        file_detection=loaded["file_detection"],
        option_oi_by_strike=canonical["option_oi_by_strike"],
        option_iv_by_strike=canonical["option_iv_by_strike"],
        futures_price=canonical["futures_price"],
        xau_spot_price=canonical["xau_spot_price"],
        basis=canonical["basis"],
        macro_event_calendar=canonical["macro_event_calendar"],
        validation_grade_days=validation_days,
        validation_dataset=validation_dataset,
        duplicate_conflict_report=duplicate_conflicts,
        basis_precision_report=basis_precision,
        validation_grade_uplift=uplift,
        data_requirements_checklist=checklist,
        orchestrator_context_markdown=context,
    )
    write_cme_history_import_outputs(output_root, result)
    return result


def discover_cme_history_import_files(roots: Iterable[str | Path]) -> list[Path]:
    """Discover local CME/QuikStrike candidate files without scanning home paths by default."""

    paths: list[Path] = []
    for root_value in roots:
        root = Path(root_value)
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            if (
                path.name in GENERATED_OUTPUT_NAMES
                or path.name.startswith("research_")
                or path.name.endswith("_metadata.json")
            ):
                continue
            if any(part in {".git", ".venv", "node_modules", "__pycache__"} for part in path.parts):
                continue
            if _looks_like_candidate(path):
                paths.append(path)
    return sorted(set(paths))


def load_and_detect_cme_files(
    paths: Iterable[str | Path],
    *,
    recovery_config: RecoveryAuditConfig | None = None,
) -> dict[str, Any]:
    """Load supported files, detect export type, and retain redacted metadata."""

    privacy = recovery_config or build_recovery_audit_config()
    table_records: list[dict[str, Any]] = []
    detection_rows: list[dict[str, Any]] = []
    for raw_path in paths:
        path = Path(raw_path)
        source_hash = hash_source_id(str(path.resolve()) if path.exists() else str(path))
        redacted = redact_path(str(path), privacy)
        try:
            frame = load_supported_table(path)
            detection = detect_cme_export_type(path, frame)
            parse_success = True
            error = ""
        except (DataLoadError, OSError, ValueError, pl.exceptions.PolarsError) as exc:
            frame = pl.DataFrame()
            detection = {
                "detected_type": "UNKNOWN",
                "confidence": 0.0,
                "matched_columns": "",
                "missing_required_columns": "unreadable",
            }
            parse_success = False
            error = str(exc)
        detection_rows.append(
            {
                "source_id_hash": source_hash,
                "redacted_file_path": redacted,
                "file_name": path.name,
                "detected_type": detection["detected_type"],
                "confidence": detection["confidence"],
                "matched_columns": detection["matched_columns"],
                "missing_required_columns": detection["missing_required_columns"],
                "parse_success": parse_success,
                "rows_loaded": frame.height,
                "date_start": _date_start(frame),
                "date_end": _date_end(frame),
                "error": error,
            }
        )
        if parse_success and not frame.is_empty():
            table_records.append(
                {
                    "path": path,
                    "source_file_hash": source_hash,
                    "redacted_file_path": redacted,
                    "detected_type": detection["detected_type"],
                    "frame": frame,
                }
            )
    return {
        "file_detection": pl.DataFrame(detection_rows, infer_schema_length=None)
        if detection_rows
        else pl.DataFrame(schema=_file_detection_schema()),
        "tables": table_records,
    }


def load_supported_table(path: str | Path) -> pl.DataFrame:
    """Load CSV, Excel, Parquet, JSON, TSV, or table-like text exports."""

    source = Path(path)
    suffix = source.suffix.lower()
    if suffix in {".csv", ".parquet", ".xlsx", ".xls"}:
        return load_table(source)
    if suffix == ".json":
        try:
            return pl.read_json(source)
        except Exception:
            payload = json.loads(source.read_text(encoding="utf-8", errors="replace"))
            rows = payload if isinstance(payload, list) else payload.get("rows", [])
            return pl.DataFrame(rows) if rows else pl.DataFrame()
    if suffix == ".jsonl":
        return pl.read_ndjson(source)
    if suffix in {".txt", ".tsv"}:
        separator = "\t" if suffix == ".tsv" else _detect_text_separator(source)
        return pl.read_csv(source, separator=separator)
    raise DataLoadError(f"Unsupported CME import format: {suffix}")


def detect_cme_export_type(path: str | Path, frame: pl.DataFrame) -> dict[str, Any]:
    """Classify one local export by columns and non-private path hints."""

    path_text = Path(path).name.lower()
    cols = {_normalize_name(column) for column in frame.columns}
    scores: dict[str, set[str]] = {
        "OPEN_INTEREST_HEATMAP": _matched(cols, ["strike", "open_interest", "total_oi", "call_oi", "put_oi"]),
        "OPEN_INTEREST_PROFILE": _matched(cols, ["strike", "expiry", "open_interest", "total_oi"]),
        "MOST_ACTIVE_STRIKES": _matched(cols, ["strike", "volume", "total_volume", "call_volume", "put_volume"]),
        "OPTION_SETTLEMENTS": _matched(cols, ["strike", "expiry", "settlement_price", "settle"]),
        "QUIKVOL": _matched(
            cols,
            [
                "implied_vol",
                "implied_volatility",
                "impliedVolatility",
                "iv",
                "IV",
                "volatility",
                "atm_iv",
                "quikvol",
                "cvol",
                "vol2vol",
                "expected_range",
                "expected_move",
                "one_sd",
            ],
        ),
        "VOLATILITY_TERM_STRUCTURE": _matched(cols, ["term_structure", "expiry", "dte", "implied_vol"]),
        "ECONOMIC_EVENT_ANALYZER": _matched(cols, ["event_name", "event_type", "forecast", "previous"]),
        "FUTURES_VOLUME_OI": _matched(cols, ["futures_symbol", "volume", "open_interest"]),
        "FUTURES_PRICE": _matched(cols, ["timestamp", "open", "high", "low", "close", "settle"]),
        "XAU_SPOT_PRICE": _matched(cols, ["timestamp", "symbol", "open", "high", "low", "close"]),
    }
    path_boosts = {
        "OPEN_INTEREST_HEATMAP": ("heatmap", "matrix"),
        "OPEN_INTEREST_PROFILE": ("profile",),
        "MOST_ACTIVE_STRIKES": ("most_active", "active_strikes", "volume"),
        "OPTION_SETTLEMENTS": ("settlement", "settle"),
        "QUIKVOL": ("quikvol", "vol2vol", "expected"),
        "VOLATILITY_TERM_STRUCTURE": ("term_structure", "term-structure"),
        "ECONOMIC_EVENT_ANALYZER": ("event", "calendar", "economic"),
        "FUTURES_VOLUME_OI": ("futures_oi", "volume_oi"),
        "FUTURES_PRICE": ("future", "gc=", "gc_f"),
        "XAU_SPOT_PRICE": ("xau", "spot"),
    }
    best_type = "UNKNOWN"
    best_score = 0.0
    best_matches: set[str] = set()
    for candidate, matches in scores.items():
        score = len(matches)
        if any(hint in path_text for hint in path_boosts[candidate]):
            score += 1.5
        if candidate == "XAU_SPOT_PRICE" and "gc" in path_text and "xau" not in path_text:
            score -= 2.0
        if candidate == "FUTURES_PRICE" and "xau" in path_text and "future" not in path_text:
            score -= 1.0
        if score > best_score:
            best_type = candidate
            best_score = score
            best_matches = matches
    required = _required_columns_for_type(best_type)
    missing = [column for column in required if column not in cols]
    confidence = min(1.0, best_score / max(len(required), 1)) if best_type != "UNKNOWN" else 0.0
    return {
        "detected_type": best_type if confidence >= 0.25 else "UNKNOWN",
        "confidence": round(confidence, 3),
        "matched_columns": "|".join(sorted(best_matches)),
        "missing_required_columns": "|".join(missing),
    }


def build_canonical_cme_tables(loaded: dict[str, Any]) -> dict[str, pl.DataFrame]:
    """Build all canonical CME/spot/basis/calendar tables from loaded sources."""

    oi_rows: list[dict[str, Any]] = []
    iv_rows: list[dict[str, Any]] = []
    futures_rows: list[dict[str, Any]] = []
    spot_rows: list[dict[str, Any]] = []
    event_rows: list[dict[str, Any]] = []
    for record in loaded.get("tables", []):
        frame = record["frame"]
        source_type = record["detected_type"]
        if source_type in {
            "OPEN_INTEREST_HEATMAP",
            "OPEN_INTEREST_PROFILE",
            "MOST_ACTIVE_STRIKES",
            "OPTION_SETTLEMENTS",
            "QUIKVOL",
            "VOLATILITY_TERM_STRUCTURE",
        }:
            oi_rows.extend(_option_oi_rows(record, frame))
            iv_rows.extend(_option_iv_rows(record, frame))
            embedded = _embedded_option_price_rows(record, frame)
            futures_rows.extend(embedded["futures"])
            spot_rows.extend(embedded["spot"])
        if source_type in {"FUTURES_PRICE", "FUTURES_VOLUME_OI"}:
            futures_rows.extend(_futures_price_rows(record, frame))
        if source_type == "XAU_SPOT_PRICE":
            spot_rows.extend(_spot_price_rows(record, frame))
        if source_type == "ECONOMIC_EVENT_ANALYZER":
            event_rows.extend(_event_rows(record, frame))
    option_oi = _frame_from_rows(oi_rows, _option_oi_schema())
    option_iv = _frame_from_rows(iv_rows, _option_iv_schema())
    futures = _frame_from_rows(futures_rows, _futures_schema())
    spot = _frame_from_rows(spot_rows, _spot_schema())
    events = _frame_from_rows(event_rows, _event_schema())
    basis = build_basis_table(futures, spot)
    return {
        "option_oi_by_strike": option_oi,
        "option_iv_by_strike": option_iv,
        "futures_price": futures,
        "xau_spot_price": spot,
        "basis": basis,
        "macro_event_calendar": events,
    }


def build_basis_table(futures: pl.DataFrame, spot: pl.DataFrame) -> pl.DataFrame:
    """Build daily/session basis from futures and spot close prices."""

    if futures.is_empty() or spot.is_empty():
        return pl.DataFrame(schema=_basis_schema())
    futures_daily = _last_by_trade_date(futures, "futures_price")
    spot_daily = _last_by_trade_date(spot, "spot_price")
    rows = []
    for future in futures_daily.to_dicts():
        trade_date = future["trade_date"]
        spot_rows = spot_daily.filter(pl.col("trade_date") == trade_date).to_dicts()
        if not spot_rows:
            continue
        spot_row = spot_rows[0]
        futures_price = _float(future.get("futures_price"))
        spot_price = _float(spot_row.get("spot_price"))
        if futures_price is None or spot_price is None:
            continue
        rows.append(
            {
                "timestamp": future.get("timestamp"),
                "trade_date": trade_date,
                "futures_symbol": future.get("futures_symbol") or "GC",
                "futures_price": futures_price,
                "spot_price": spot_price,
                "basis": futures_price - spot_price,
                "basis_quality": "DAILY_CLOSE_ALIGNED",
                "source_file_hash": f"{future.get('source_file_hash')}|{spot_row.get('source_file_hash')}",
            }
        )
    return _frame_from_rows(rows, _basis_schema())


def classify_validation_grade_days(canonical: dict[str, pl.DataFrame]) -> pl.DataFrame:
    """Classify each trade date into validation-grade coverage levels."""

    dates = _all_trade_dates(canonical.values())
    rows = []
    for trade_date in sorted(dates):
        oi = _date_filter(canonical["option_oi_by_strike"], trade_date)
        iv = _date_filter(canonical["option_iv_by_strike"], trade_date)
        futures = _date_filter(canonical["futures_price"], trade_date)
        spot = _date_filter(canonical["xau_spot_price"], trade_date)
        basis = _date_filter(canonical["basis"], trade_date)
        events = _date_filter(canonical["macro_event_calendar"], trade_date)
        flags = {
            "has_xau_spot_price": not spot.is_empty(),
            "has_gc_futures_price": not futures.is_empty(),
            "has_basis": not basis.is_empty(),
            "has_option_oi_by_strike": not oi.is_empty() and _max(oi, "total_oi") > 0,
            "has_option_oi_change": not oi.is_empty() and _abs_max(oi, "total_oi_change") > 0,
            "has_option_volume": not oi.is_empty() and _max(oi, "total_volume") > 0,
            "has_option_iv": not iv.is_empty() and _max(iv, "implied_vol") > 0,
            "has_option_settlement": not iv.is_empty() and _max(iv, "settlement_price") > 0,
            "has_expiry_dte": _has_expiry_dte(oi) or _has_expiry_dte(iv),
            "has_macro_event_flag": not events.is_empty(),
        }
        grade = _validation_grade(flags)
        pilot_grade = _pilot_usability_grade(flags)
        full = grade == "FULL_CME_VOL_OI"
        missing = _missing_components(flags)
        rows.append(
            {
                "trade_date": trade_date,
                **flags,
                "complete_validation_grade": full,
                "missing_components": "|".join(missing),
                "strict_validation_grade": grade,
                "pilot_usability_grade": pilot_grade,
                "validation_grade": grade,
            }
        )
    return _frame_from_rows(rows, _validation_days_schema()).sort("trade_date")


def build_validation_dataset(
    canonical: dict[str, pl.DataFrame],
    validation_days: pl.DataFrame,
) -> pl.DataFrame:
    """Build one session-level validation row per available trade date."""

    rows = []
    grades = {row["trade_date"]: row for row in validation_days.to_dicts()}
    for trade_date, grade_row in grades.items():
        spot_row = _last_row(_date_filter(canonical["xau_spot_price"], trade_date))
        futures_row = _last_row(_date_filter(canonical["futures_price"], trade_date))
        basis_row = _last_row(_date_filter(canonical["basis"], trade_date))
        spot_price = _float(spot_row.get("close")) or _float(spot_row.get("spot_price"))
        futures_price = _float(futures_row.get("settle")) or _float(futures_row.get("close"))
        basis = _float(basis_row.get("basis"))
        oi_rows = _date_filter(canonical["option_oi_by_strike"], trade_date)
        iv_rows = _date_filter(canonical["option_iv_by_strike"], trade_date)
        wall = _nearest_walls(oi_rows, spot_price=spot_price, basis=basis)
        atm_iv = _atm_iv(iv_rows, spot_price=spot_price, basis=basis)
        session_open = _float(spot_row.get("open"))
        one_sd = spot_price * (atm_iv / 100.0) / (252.0**0.5) if spot_price and atm_iv else None
        rows.append(
            {
                "timestamp": spot_row.get("timestamp") or futures_row.get("timestamp") or basis_row.get("timestamp"),
                "trade_date": trade_date,
                "spot_price": spot_price,
                "futures_price": futures_price,
                "basis": basis,
                "nearest_spot_equivalent_wall_above": wall["above_level"],
                "nearest_spot_equivalent_wall_below": wall["below_level"],
                "wall_score_above": wall["above_score"],
                "wall_score_below": wall["below_score"],
                "total_oi_near_spot": wall["total_oi_near_spot"],
                "oi_change_near_spot": wall["oi_change_near_spot"],
                "volume_near_spot": wall["volume_near_spot"],
                "implied_vol_atm": atm_iv,
                "iv_skew_call_put": _iv_skew(iv_rows),
                "one_sd_upper": spot_price + one_sd if spot_price and one_sd else None,
                "one_sd_lower": spot_price - one_sd if spot_price and one_sd else None,
                "two_sd_upper": spot_price + 2 * one_sd if spot_price and one_sd else None,
                "two_sd_lower": spot_price - 2 * one_sd if spot_price and one_sd else None,
                "sigma_position": (spot_price - session_open) / one_sd if spot_price and session_open and one_sd else None,
                "strict_validation_grade": grade_row.get("strict_validation_grade") or grade_row.get("validation_grade"),
                "pilot_usability_grade": grade_row.get("pilot_usability_grade"),
                "validation_grade": grade_row.get("validation_grade"),
            }
        )
    return _frame_from_rows(rows, _validation_dataset_schema()).sort("trade_date")


def compare_basis_adjustment_precision(
    canonical: dict[str, pl.DataFrame],
    validation_dataset: pl.DataFrame,
) -> pl.DataFrame:
    """Compare raw futures-strike walls against basis-adjusted spot-equivalent walls."""

    rows = []
    for data_row in validation_dataset.to_dicts():
        trade_date = data_row.get("trade_date")
        spot_price = _float(data_row.get("spot_price"))
        basis = _float(data_row.get("basis"))
        if spot_price is None:
            continue
        oi_rows = _date_filter(canonical["option_oi_by_strike"], str(trade_date))
        if oi_rows.is_empty():
            continue
        top = oi_rows.sort("total_oi", descending=True).head(1).to_dicts()[0]
        strike = _float(top.get("strike"))
        if strike is None:
            continue
        raw_error = abs(strike - spot_price)
        adjusted_wall = strike - basis if basis is not None else None
        adjusted_error = abs(adjusted_wall - spot_price) if adjusted_wall is not None else None
        rows.append(_precision_row(trade_date, "RAW_STRIKE", strike, raw_error, spot_price))
        if adjusted_wall is not None and adjusted_error is not None:
            rows.append(
                _precision_row(
                    trade_date,
                    "BASIS_ADJUSTED",
                    adjusted_wall,
                    adjusted_error,
                    spot_price,
                )
            )
    frame = _frame_from_rows(rows, _basis_precision_schema())
    if frame.is_empty():
        return frame
    summary_rows = []
    for method in ["RAW_STRIKE", "BASIS_ADJUSTED"]:
        method_rows = frame.filter(pl.col("mapping_method") == method)
        if method_rows.is_empty():
            continue
        summary_rows.append(
            {
                "trade_date": "ALL",
                "mapping_method": f"{method}_SUMMARY",
                "wall_level": None,
                "spot_price": None,
                "distance_to_actual_turning_point": method_rows.get_column(
                    "distance_to_actual_turning_point"
                ).mean(),
                "wall_touch_rate": _mean_bool(method_rows, "wall_touched"),
                "rejection_rate": _mean_bool(method_rows, "wall_rejected"),
                "acceptance_rate": _mean_bool(method_rows, "wall_accepted"),
                "map_hit_rate": _mean_bool(method_rows, "map_hit"),
                "average_error_points": method_rows.get_column("average_error_points").mean(),
                "basis_adjustment_improves": False,
                "sample_size_warning": method_rows.height < 20,
            }
        )
    combined = pl.concat([frame, _frame_from_rows(summary_rows, _basis_precision_schema())], how="diagonal_relaxed")
    return _mark_basis_improvement(combined)


def build_validation_grade_uplift_report(validation_dataset: pl.DataFrame) -> pl.DataFrame:
    """Evaluate simple baseline/uplift cohorts on validation-grade days only."""

    rows = []
    price_rows = validation_dataset.filter(pl.col("validation_grade") == "PRICE_ONLY") if not validation_dataset.is_empty() else validation_dataset
    price_baseline = _dataset_expectancy(price_rows)
    for stage in ["PRICE_ONLY", "CME_OI_ONLY", "CME_IV_ONLY", "FULL_CME_VOL_OI"]:
        stage_rows = validation_dataset.filter(pl.col("validation_grade") == stage) if not validation_dataset.is_empty() else validation_dataset
        stats = _dataset_stats(stage_rows)
        rows.append(
            {
                "stage": stage,
                "event_count": stage_rows.height,
                "trade_count": stats["trade_count"],
                "expectancy": stats["expectancy"],
                "profit_factor": stats["profit_factor"],
                "max_drawdown": stats["max_drawdown"],
                "win_rate": stats["win_rate"],
                "walk_forward_pass": False,
                "placebo_pass": False,
                "sample_size_warning": stage_rows.height < 60,
                "cost_stress_survival": False,
                "uplift_vs_price_only": stats["expectancy"] - price_baseline if stats["expectancy"] is not None else None,
                "uplift_vs_bollinger": None,
                "uplift_vs_sd_only": None,
                "notes": "Validation-grade sample is descriptive only until longer CME history exists.",
            }
        )
    return _frame_from_rows(rows, _uplift_schema())


def build_cme_data_requirements_checklist(
    file_detection: pl.DataFrame,
    validation_days: pl.DataFrame,
) -> pl.DataFrame:
    """Build the user-facing checklist for missing validation-grade components."""

    detected = set(file_detection.get_column("detected_type").to_list()) if not file_detection.is_empty() else set()
    full_days = _true_count(validation_days, "complete_validation_grade")
    specs = [
        ("CME Open Interest Heatmap export", "OI walls by strike/expiry", "trade_date, expiry, dte, strike, call_oi, put_oi, total_oi", {"OPEN_INTEREST_HEATMAP"}, "CRITICAL"),
        ("CME Open Interest Profile export", "Cross-check OI walls and expiry concentration", "trade_date, expiry, strike, open_interest", {"OPEN_INTEREST_PROFILE"}, "HIGH"),
        ("Most Active Strikes export", "Freshness and intraday participation", "trade_date, expiry, strike, call_volume, put_volume, total_volume", {"MOST_ACTIVE_STRIKES"}, "HIGH"),
        ("Option Settlements export", "Settlement and IV/price context", "trade_date, expiry, strike, option_type, settlement_price", {"OPTION_SETTLEMENTS"}, "HIGH"),
        ("QuikVol / IV export", "Expected-move and IV regime", "trade_date, expiry, strike, implied_vol", {"QUIKVOL"}, "CRITICAL"),
        ("Volatility Term Structure export", "Term-structure regime", "trade_date, expiry, dte, implied_vol", {"VOLATILITY_TERM_STRUCTURE"}, "MEDIUM"),
        ("Gold futures price/OI", "Futures reference and basis", "timestamp, futures_symbol, open, high, low, close, settle, volume, open_interest", {"FUTURES_PRICE", "FUTURES_VOLUME_OI"}, "CRITICAL"),
        ("XAU/USD intraday spot price", "Spot reference and outcome windows", "timestamp, symbol, open, high, low, close", {"XAU_SPOT_PRICE"}, "CRITICAL"),
        ("Macro event calendar", "Event-day controls and news disable labels", "event_timestamp, event_name, event_type, forecast, actual", {"ECONOMIC_EVENT_ANALYZER"}, "HIGH"),
    ]
    rows = []
    for source_name, why, fields, types, priority in specs:
        available = bool(detected & types)
        current_status = "AVAILABLE" if available and full_days > 0 else "PARTIAL" if available else "MISSING"
        rows.append(
            {
                "source_name": source_name,
                "why_needed": why,
                "minimum_fields": fields,
                "current_status": current_status,
                "priority": priority,
                "example_export_name": _generic_export_example(source_name),
                "user_action_required": _user_action(current_status, source_name),
            }
        )
    return _frame_from_rows(rows, _requirements_schema())


def write_cme_history_import_outputs(output_root: Path, result: CmeHistoryImporterResult) -> None:
    """Write all importer outputs."""

    result.file_detection.write_csv(output_root / "cme_import_file_detection.csv")
    result.option_oi_by_strike.write_parquet(output_root / "cme_canonical_option_oi_by_strike.parquet")
    result.option_iv_by_strike.write_parquet(output_root / "cme_canonical_option_iv_by_strike.parquet")
    result.futures_price.write_parquet(output_root / "cme_canonical_futures_price.parquet")
    result.xau_spot_price.write_parquet(output_root / "cme_canonical_xau_spot_price.parquet")
    result.basis.write_parquet(output_root / "cme_canonical_basis.parquet")
    result.macro_event_calendar.write_csv(output_root / "cme_canonical_macro_event_calendar.csv")
    result.validation_dataset.write_parquet(output_root / "xau_vol_oi_validation_dataset.parquet")
    result.validation_grade_days.write_csv(output_root / "cme_validation_grade_days.csv")
    result.duplicate_conflict_report.write_csv(output_root / "cme_import_duplicate_conflict_report.csv")
    result.basis_precision_report.write_csv(output_root / "basis_adjustment_precision_report.csv")
    result.validation_grade_uplift.write_csv(output_root / "cme_validation_grade_uplift.csv")
    result.data_requirements_checklist.write_csv(output_root / "cme_data_requirements_checklist.csv")
    (output_root / "cme_validation_grade_report.md").write_text(
        validation_grade_markdown(result),
        encoding="utf-8",
    )
    (output_root / "basis_adjustment_precision_report.md").write_text(
        basis_precision_markdown(result.basis_precision_report),
        encoding="utf-8",
    )
    (output_root / "cme_validation_grade_uplift_report.md").write_text(
        validation_uplift_markdown(result.validation_grade_uplift),
        encoding="utf-8",
    )
    (output_root / "cme_data_requirements_checklist.md").write_text(
        checklist_markdown(result.data_requirements_checklist),
        encoding="utf-8",
    )
    (output_root / "orchestrator_gpt_context.md").write_text(
        result.orchestrator_context_markdown,
        encoding="utf-8",
    )


def validation_grade_markdown(result: CmeHistoryImporterResult) -> str:
    """Render validation-grade day coverage."""

    complete_days = _true_count(result.validation_grade_days, "complete_validation_grade")
    grade_counts = (
        result.validation_grade_days.group_by("validation_grade").len().sort("validation_grade")
        if not result.validation_grade_days.is_empty()
        else pl.DataFrame()
    )
    return "\n".join(
        [
            "# CME Validation-Grade Data Report",
            "",
            "Research-only. This report only describes local user-provided exports.",
            "",
            f"- Files detected: {result.file_detection.height}",
            f"- Complete validation-grade days: {complete_days}",
            f"- Canonical OI rows: {result.option_oi_by_strike.height}",
            f"- Canonical IV rows: {result.option_iv_by_strike.height}",
            f"- Futures price rows: {result.futures_price.height}",
            f"- XAU spot rows: {result.xau_spot_price.height}",
            f"- Basis rows: {result.basis.height}",
            "",
            "## Grade Counts",
            "",
            _frame_markdown(grade_counts),
            "",
            "## Validation Days",
            "",
            _frame_markdown(result.validation_grade_days),
        ]
    )


def basis_precision_markdown(frame: pl.DataFrame) -> str:
    """Render basis-adjustment precision comparison."""

    if frame.is_empty():
        decision = "INSUFFICIENT_DATA"
    else:
        decision = "BASIS_ADJUSTMENT_PROMISING" if _any_true(frame, "basis_adjustment_improves") else "NOT_PROVEN"
    return "\n".join(
        [
            "# Basis Adjustment Precision Report",
            "",
            f"- Decision: `{decision}`",
            "- Raw futures strikes and basis-adjusted spot-equivalent strikes are compared only when local data exists.",
            "",
            _frame_markdown(frame),
        ]
    )


def validation_uplift_markdown(frame: pl.DataFrame) -> str:
    """Render validation-grade uplift report."""

    return "\n".join(
        [
            "# CME Validation-Grade Uplift Report",
            "",
            "No edge is claimed. Walk-forward and placebo columns must pass before interpretation.",
            "",
            _frame_markdown(frame),
        ]
    )


def checklist_markdown(frame: pl.DataFrame) -> str:
    """Render CME data requirement checklist."""

    return "\n".join(["# CME Data Requirements Checklist", "", _frame_markdown(frame)])


def orchestrator_gpt_context_markdown(
    *,
    file_detection: pl.DataFrame,
    canonical: dict[str, pl.DataFrame],
    validation_days: pl.DataFrame,
    basis_precision: pl.DataFrame,
    uplift: pl.DataFrame,
    checklist: pl.DataFrame,
    config: CmeHistoryImporterConfig,
) -> str:
    """Create a compact context pack for an orchestrator model."""

    detected_counts = (
        file_detection.group_by("detected_type").len().sort("detected_type")
        if not file_detection.is_empty()
        else pl.DataFrame()
    )
    complete_days = _true_count(validation_days, "complete_validation_grade")
    missing_critical = checklist.filter(
        (pl.col("priority") == "CRITICAL") & (pl.col("current_status") != "AVAILABLE")
    ) if not checklist.is_empty() else checklist
    return "\n".join(
        [
            "# Orchestrator GPT Context: XAU CME Data State",
            "",
            "Use this as context for planning only. Do not infer trading edge or create execution instructions.",
            "",
            "## Current Decision Gate Context",
            "",
            "- Final readiness label remains `NOT_READY_DATA_INSUFFICIENT` unless validation-grade days pass the configured threshold.",
            f"- Preliminary threshold: {config.minimum_preliminary_days} complete validation-grade days.",
            f"- Current complete validation-grade days: {complete_days}.",
            "",
            "## Files Detected By Type",
            "",
            _frame_markdown(detected_counts),
            "",
            "## Canonical Row Counts",
            "",
            _frame_markdown(
                pl.DataFrame(
                    [
                        {"table": name, "rows": frame.height}
                        for name, frame in canonical.items()
                    ]
                )
            ),
            "",
            "## Validation Grade Days",
            "",
            _frame_markdown(validation_days),
            "",
            "## Missing Critical Components",
            "",
            _frame_markdown(missing_critical),
            "",
            "## Basis Precision",
            "",
            _frame_markdown(basis_precision),
            "",
            "## CME Uplift On Validation-Grade Days",
            "",
            _frame_markdown(uplift),
            "",
            "## Next User Action",
            "",
            "- Add more local CME/QuikStrike exports with OI by strike/expiry, IV, futures reference, XAU spot/proxy, and freshness fields.",
            "- Keep source paths local; reports use redacted paths and source hashes.",
        ]
    )


def _option_oi_rows(record: dict[str, Any], frame: pl.DataFrame) -> list[dict[str, Any]]:
    rows = []
    columns = frame.columns
    timestamp_col = _find_col(columns, ["asof_timestamp", "timestamp", "date", "trade_date"])
    strike_col = _find_col(columns, ["strike", "option_strike", "cme_option_strike"])
    expiry_col = _find_col(columns, ["expiry", "expiration", "expiration_date", "expiry_date"])
    dte_col = _find_col(columns, ["dte", "days_to_expiry", "days_to_expiration"])
    option_type_col = _find_col(columns, ["option_type", "put_call", "type", "side"])
    call_oi_col = _find_col(columns, ["call_oi", "calls_oi", "call_open_interest"])
    put_oi_col = _find_col(columns, ["put_oi", "puts_oi", "put_open_interest"])
    total_oi_col = _find_col(columns, ["total_oi", "open_interest", "oi"])
    call_vol_col = _find_col(columns, ["call_volume", "calls_volume"])
    put_vol_col = _find_col(columns, ["put_volume", "puts_volume"])
    total_vol_col = _find_col(columns, ["total_volume", "volume", "intraday_volume"])
    call_change_col = _find_col(columns, ["call_oi_change", "call_open_interest_change"])
    put_change_col = _find_col(columns, ["put_oi_change", "put_open_interest_change"])
    total_change_col = _find_col(columns, ["total_oi_change", "oi_change", "open_interest_change"])
    product_col = _find_col(columns, ["product", "commodity"])
    symbol_col = _find_col(columns, ["underlying_symbol", "symbol", "futures_symbol"])
    contract_col = _find_col(columns, ["contract_month", "contract"])
    if strike_col is None:
        return rows
    for index, raw in enumerate(frame.to_dicts(), start=1):
        timestamp = _parse_datetime(raw.get(timestamp_col), fallback=record["path"], row=index)
        strike = _float(raw.get(strike_col))
        if timestamp is None or strike is None:
            continue
        expiry = _parse_date(raw.get(expiry_col), fallback_date=timestamp.date())
        dte = _float(raw.get(dte_col))
        if dte is None and expiry is not None:
            dte = float((expiry - timestamp.date()).days)
        option_type = _normalize_option_type(raw.get(option_type_col))
        call_oi = _float(raw.get(call_oi_col))
        put_oi = _float(raw.get(put_oi_col))
        total_oi = _float(raw.get(total_oi_col))
        if option_type == "call" and total_oi is not None and call_oi is None:
            call_oi = total_oi
        if option_type == "put" and total_oi is not None and put_oi is None:
            put_oi = total_oi
        call_oi = call_oi or 0.0
        put_oi = put_oi or 0.0
        total_oi = total_oi if total_oi is not None else call_oi + put_oi
        call_volume = _float(raw.get(call_vol_col)) or (0.0 if option_type != "call" else _float(raw.get(total_vol_col)) or 0.0)
        put_volume = _float(raw.get(put_vol_col)) or (0.0 if option_type != "put" else _float(raw.get(total_vol_col)) or 0.0)
        total_volume = _float(raw.get(total_vol_col))
        total_volume = total_volume if total_volume is not None else call_volume + put_volume
        call_change = _float(raw.get(call_change_col)) or (0.0 if option_type != "call" else _float(raw.get(total_change_col)) or 0.0)
        put_change = _float(raw.get(put_change_col)) or (0.0 if option_type != "put" else _float(raw.get(total_change_col)) or 0.0)
        total_change = _float(raw.get(total_change_col))
        total_change = total_change if total_change is not None else call_change + put_change
        rows.append(
            {
                "asof_timestamp": timestamp,
                "trade_date": timestamp.date().isoformat(),
                "product": str(raw.get(product_col) or "Gold"),
                "underlying_symbol": str(raw.get(symbol_col) or "GC"),
                "contract_month": str(raw.get(contract_col) or ""),
                "expiry": expiry.isoformat() if expiry else "",
                "dte": dte,
                "option_type": option_type,
                "strike": strike,
                "call_oi": call_oi,
                "put_oi": put_oi,
                "total_oi": total_oi,
                "call_volume": call_volume,
                "put_volume": put_volume,
                "total_volume": total_volume,
                "call_oi_change": call_change,
                "put_oi_change": put_change,
                "total_oi_change": total_change,
                "source_file_hash": record["source_file_hash"],
                "source_type": record["detected_type"],
            }
        )
    return rows


def _option_iv_rows(record: dict[str, Any], frame: pl.DataFrame) -> list[dict[str, Any]]:
    rows = []
    columns = frame.columns
    timestamp_col = _find_col(columns, ["asof_timestamp", "timestamp", "date", "trade_date"])
    strike_col = _find_col(columns, ["strike", "option_strike", "cme_option_strike"])
    expiry_col = _find_col(columns, ["expiry", "expiration", "expiration_date", "expiry_date"])
    dte_col = _find_col(columns, ["dte", "days_to_expiry", "days_to_expiration"])
    option_type_col = _find_col(columns, ["option_type", "put_call", "type", "side"])
    iv_col = _find_col(
        columns,
        [
            "implied_vol",
            "implied_volatility",
            "impliedVolatility",
            "iv",
            "IV",
            "iv_percent",
            "volatility",
            "atm_iv",
            "quikvol",
            "cvol",
            "vol2vol",
        ],
    )
    delta_col = _find_col(columns, ["delta"])
    gamma_col = _find_col(columns, ["gamma"])
    vega_col = _find_col(columns, ["vega"])
    theta_col = _find_col(columns, ["theta"])
    settle_col = _find_col(columns, ["settlement_price", "option_settlement", "settle", "settlement"])
    product_col = _find_col(columns, ["product", "commodity"])
    if strike_col is None:
        return rows
    for index, raw in enumerate(frame.to_dicts(), start=1):
        timestamp = _parse_datetime(raw.get(timestamp_col), fallback=record["path"], row=index)
        strike = _float(raw.get(strike_col))
        if timestamp is None or strike is None:
            continue
        expiry = _parse_date(raw.get(expiry_col), fallback_date=timestamp.date())
        dte = _float(raw.get(dte_col))
        if dte is None and expiry is not None:
            dte = float((expiry - timestamp.date()).days)
        iv = _normalize_iv(_float(raw.get(iv_col)))
        settlement = _float(raw.get(settle_col))
        if iv is None and settlement is None:
            continue
        rows.append(
            {
                "asof_timestamp": timestamp,
                "trade_date": timestamp.date().isoformat(),
                "product": str(raw.get(product_col) or "Gold"),
                "expiry": expiry.isoformat() if expiry else "",
                "dte": dte,
                "option_type": _normalize_option_type(raw.get(option_type_col)),
                "strike": strike,
                "implied_vol": iv,
                "delta": _float(raw.get(delta_col)),
                "gamma": _float(raw.get(gamma_col)),
                "vega": _float(raw.get(vega_col)),
                "theta": _float(raw.get(theta_col)),
                "settlement_price": settlement,
                "source_file_hash": record["source_file_hash"],
                "source_type": record["detected_type"],
            }
        )
    return rows


def _futures_price_rows(record: dict[str, Any], frame: pl.DataFrame) -> list[dict[str, Any]]:
    rows = []
    columns = frame.columns
    timestamp_col = _find_col(columns, ["timestamp", "datetime", "date", "trade_date"])
    symbol_col = _find_col(columns, ["futures_symbol", "symbol", "underlying_symbol"])
    product_col = _find_col(columns, ["product", "commodity"])
    contract_col = _find_col(columns, ["contract_month", "contract"])
    open_col = _find_col(columns, ["open"])
    high_col = _find_col(columns, ["high"])
    low_col = _find_col(columns, ["low"])
    close_col = _find_col(columns, ["close", "last", "price"])
    settle_col = _find_col(columns, ["settle", "settlement", "settlement_price"])
    volume_col = _find_col(columns, ["volume"])
    oi_col = _find_col(columns, ["open_interest", "oi"])
    for index, raw in enumerate(frame.to_dicts(), start=1):
        timestamp = _parse_datetime(raw.get(timestamp_col), fallback=record["path"], row=index)
        if timestamp is None:
            continue
        close = _float(raw.get(close_col)) or _float(raw.get(settle_col))
        rows.append(
            {
                "timestamp": timestamp,
                "trade_date": timestamp.date().isoformat(),
                "product": str(raw.get(product_col) or "Gold"),
                "contract_month": str(raw.get(contract_col) or ""),
                "futures_symbol": str(raw.get(symbol_col) or "GC"),
                "open": _float(raw.get(open_col)),
                "high": _float(raw.get(high_col)),
                "low": _float(raw.get(low_col)),
                "close": close,
                "settle": _float(raw.get(settle_col)) or close,
                "volume": _float(raw.get(volume_col)),
                "open_interest": _float(raw.get(oi_col)),
                "source_file_hash": record["source_file_hash"],
            }
        )
    return rows


def _spot_price_rows(record: dict[str, Any], frame: pl.DataFrame) -> list[dict[str, Any]]:
    futures_record = dict(record)
    rows = _futures_price_rows(futures_record, frame)
    spot = []
    for row in rows:
        spot.append(
            {
                "timestamp": row["timestamp"],
                "trade_date": row["trade_date"],
                "symbol": row["futures_symbol"] if row["futures_symbol"] != "GC" else "XAUUSD",
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "volume": row["volume"],
                "source_file_hash": row["source_file_hash"],
            }
        )
    return spot


def _event_rows(record: dict[str, Any], frame: pl.DataFrame) -> list[dict[str, Any]]:
    rows = []
    columns = frame.columns
    timestamp_col = _find_col(columns, ["event_timestamp", "timestamp", "datetime", "date", "trade_date"])
    name_col = _find_col(columns, ["event_name", "event", "macro_event"])
    type_col = _find_col(columns, ["event_type", "event_tag", "tag"])
    importance_col = _find_col(columns, ["expected_importance", "importance"])
    actual_col = _find_col(columns, ["actual"])
    forecast_col = _find_col(columns, ["forecast", "expected"])
    previous_col = _find_col(columns, ["previous", "prior"])
    for index, raw in enumerate(frame.to_dicts(), start=1):
        timestamp = _parse_datetime(raw.get(timestamp_col), fallback=record["path"], row=index)
        if timestamp is None:
            continue
        rows.append(
            {
                "event_timestamp": timestamp,
                "trade_date": timestamp.date().isoformat(),
                "event_name": str(raw.get(name_col) or ""),
                "event_type": str(raw.get(type_col) or ""),
                "expected_importance": str(raw.get(importance_col) or ""),
                "actual": str(raw.get(actual_col) or ""),
                "forecast": str(raw.get(forecast_col) or ""),
                "previous": str(raw.get(previous_col) or ""),
                "source_file_hash": record["source_file_hash"],
            }
        )
    return rows


def _embedded_option_price_rows(record: dict[str, Any], frame: pl.DataFrame) -> dict[str, list[dict[str, Any]]]:
    """Extract futures/spot reference prices embedded in option exports."""

    columns = frame.columns
    timestamp_col = _find_col(columns, ["asof_timestamp", "timestamp", "date", "trade_date"])
    futures_col = _find_col(columns, ["underlying_futures_price", "futures_price", "gold_futures_price", "gc_price"])
    spot_col = _find_col(columns, ["xauusd_spot_price", "spot_price", "xau_price", "xauusd"])
    symbol_col = _find_col(columns, ["underlying_symbol", "futures_symbol", "symbol"])
    futures_rows = []
    spot_rows = []
    seen_futures: set[tuple[str, float]] = set()
    seen_spot: set[tuple[str, float]] = set()
    for index, raw in enumerate(frame.to_dicts(), start=1):
        timestamp = _parse_datetime(raw.get(timestamp_col), fallback=record["path"], row=index)
        if timestamp is None:
            continue
        futures_price = _float(raw.get(futures_col))
        spot_price = _float(raw.get(spot_col))
        if futures_price is not None:
            key = (timestamp.isoformat(), futures_price)
            if key not in seen_futures:
                seen_futures.add(key)
                futures_rows.append(
                    {
                        "timestamp": timestamp,
                        "trade_date": timestamp.date().isoformat(),
                        "product": "Gold",
                        "contract_month": "",
                        "futures_symbol": str(raw.get(symbol_col) or "GC"),
                        "open": None,
                        "high": None,
                        "low": None,
                        "close": futures_price,
                        "settle": futures_price,
                        "volume": None,
                        "open_interest": None,
                        "source_file_hash": record["source_file_hash"],
                    }
                )
        if spot_price is not None:
            key = (timestamp.isoformat(), spot_price)
            if key not in seen_spot:
                seen_spot.add(key)
                spot_rows.append(
                    {
                        "timestamp": timestamp,
                        "trade_date": timestamp.date().isoformat(),
                        "symbol": "XAUUSD",
                        "open": spot_price,
                        "high": spot_price,
                        "low": spot_price,
                        "close": spot_price,
                        "volume": None,
                        "source_file_hash": record["source_file_hash"],
                    }
                )
    return {"futures": futures_rows, "spot": spot_rows}


def build_import_duplicate_conflict_report(option_oi: pl.DataFrame) -> pl.DataFrame:
    """Report duplicate daily strike-expiry snapshots with conflicting values."""

    if option_oi.is_empty():
        return pl.DataFrame(schema=_duplicate_schema())
    keys = ["trade_date", "expiry", "strike", "option_type"]
    grouped = option_oi.group_by(keys).agg(
        [
            pl.len().alias("row_count"),
            pl.col("source_file_hash").n_unique().alias("source_count"),
            pl.col("total_oi").n_unique().alias("total_oi_value_count"),
            pl.col("total_volume").n_unique().alias("total_volume_value_count"),
            pl.col("total_oi_change").n_unique().alias("total_oi_change_value_count"),
        ]
    )
    rows = []
    for row in grouped.to_dicts():
        conflict_fields = [
            name.replace("_value_count", "")
            for name in ["total_oi_value_count", "total_volume_value_count", "total_oi_change_value_count"]
            if (row.get(name) or 0) > 1
        ]
        if row["row_count"] <= 1:
            continue
        rows.append(
            {
                **{key: row[key] for key in keys},
                "row_count": row["row_count"],
                "source_count": row["source_count"],
                "conflict_fields": "|".join(conflict_fields),
                "has_conflict": bool(conflict_fields),
                "resolution": "latest_asof_timestamp_preferred_in_downstream_panel",
            }
        )
    return _frame_from_rows(rows, _duplicate_schema())


def _precision_row(trade_date: Any, method: str, wall_level: float, error: float, spot_price: float) -> dict[str, Any]:
    touched = error <= 25.0
    return {
        "trade_date": str(trade_date),
        "mapping_method": method,
        "wall_level": wall_level,
        "spot_price": spot_price,
        "distance_to_actual_turning_point": error,
        "wall_touch_rate": 1.0 if touched else 0.0,
        "rejection_rate": 0.0,
        "acceptance_rate": 1.0 if touched else 0.0,
        "map_hit_rate": 1.0 if error <= 10.0 else 0.0,
        "average_error_points": error,
        "basis_adjustment_improves": False,
        "sample_size_warning": True,
    }


def _dataset_stats(frame: pl.DataFrame) -> dict[str, Any]:
    if frame.is_empty() or "spot_price" not in frame.columns:
        return {"trade_count": 0, "expectancy": None, "profit_factor": None, "max_drawdown": None, "win_rate": None}
    prices = [value for value in frame.get_column("spot_price").to_list() if value is not None]
    if len(prices) < 2:
        return {"trade_count": 0, "expectancy": None, "profit_factor": None, "max_drawdown": None, "win_rate": None}
    returns = [prices[index + 1] - prices[index] for index in range(len(prices) - 1)]
    wins = [value for value in returns if value > 0]
    losses = [value for value in returns if value < 0]
    profit_factor = sum(wins) / abs(sum(losses)) if losses else None
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for value in returns:
        equity += value
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity - peak)
    return {
        "trade_count": len(returns),
        "expectancy": sum(returns) / len(returns),
        "profit_factor": profit_factor,
        "max_drawdown": max_drawdown,
        "win_rate": len(wins) / len(returns),
    }


def _dataset_expectancy(frame: pl.DataFrame) -> float:
    stats = _dataset_stats(frame)
    value = stats["expectancy"]
    return float(value) if value is not None else 0.0


def _nearest_walls(option_oi: pl.DataFrame, *, spot_price: float | None, basis: float | None) -> dict[str, Any]:
    result = {
        "above_level": None,
        "below_level": None,
        "above_score": None,
        "below_score": None,
        "total_oi_near_spot": None,
        "oi_change_near_spot": None,
        "volume_near_spot": None,
    }
    if option_oi.is_empty() or spot_price is None:
        return result
    rows = []
    max_oi = _max(option_oi, "total_oi") or 1.0
    for row in option_oi.to_dicts():
        strike = _float(row.get("strike"))
        if strike is None:
            continue
        level = strike - basis if basis is not None else strike
        rows.append({**row, "spot_equivalent_level": level, "score": (_float(row.get("total_oi")) or 0.0) / max_oi})
    above = [row for row in rows if row["spot_equivalent_level"] >= spot_price]
    below = [row for row in rows if row["spot_equivalent_level"] <= spot_price]
    if above:
        nearest = min(above, key=lambda row: abs(row["spot_equivalent_level"] - spot_price))
        result["above_level"] = nearest["spot_equivalent_level"]
        result["above_score"] = nearest["score"]
    if below:
        nearest = min(below, key=lambda row: abs(row["spot_equivalent_level"] - spot_price))
        result["below_level"] = nearest["spot_equivalent_level"]
        result["below_score"] = nearest["score"]
    near = [row for row in rows if abs(row["spot_equivalent_level"] - spot_price) <= 25.0]
    if near:
        result["total_oi_near_spot"] = sum(_float(row.get("total_oi")) or 0.0 for row in near)
        result["oi_change_near_spot"] = sum(_float(row.get("total_oi_change")) or 0.0 for row in near)
        result["volume_near_spot"] = sum(_float(row.get("total_volume")) or 0.0 for row in near)
    return result


def _atm_iv(option_iv: pl.DataFrame, *, spot_price: float | None, basis: float | None) -> float | None:
    if option_iv.is_empty() or spot_price is None:
        return None
    candidates = []
    for row in option_iv.to_dicts():
        iv = _float(row.get("implied_vol"))
        strike = _float(row.get("strike"))
        if iv is None or strike is None:
            continue
        level = strike - basis if basis is not None else strike
        candidates.append((abs(level - spot_price), iv))
    return min(candidates)[1] if candidates else None


def _iv_skew(option_iv: pl.DataFrame) -> float | None:
    if option_iv.is_empty():
        return None
    calls = [_float(row.get("implied_vol")) for row in option_iv.to_dicts() if row.get("option_type") == "call"]
    puts = [_float(row.get("implied_vol")) for row in option_iv.to_dicts() if row.get("option_type") == "put"]
    calls = [value for value in calls if value is not None]
    puts = [value for value in puts if value is not None]
    if not calls or not puts:
        return None
    return sum(calls) / len(calls) - sum(puts) / len(puts)


def _last_by_trade_date(frame: pl.DataFrame, price_name: str) -> pl.DataFrame:
    if frame.is_empty():
        return frame
    close_expr = pl.coalesce([column for column in ["settle", "close"] if column in frame.columns]).last().alias(price_name)
    return frame.sort("timestamp").group_by("trade_date").agg(
        [
            pl.col("timestamp").last(),
            pl.col("source_file_hash").last(),
            pl.col("futures_symbol").last() if "futures_symbol" in frame.columns else pl.lit("XAUUSD").alias("futures_symbol"),
            close_expr,
        ]
    )


def _all_trade_dates(frames: Iterable[pl.DataFrame]) -> set[str]:
    dates: set[str] = set()
    for frame in frames:
        if not frame.is_empty() and "trade_date" in frame.columns:
            dates.update(str(value) for value in frame.get_column("trade_date").to_list() if value)
    return dates


def _validation_grade(flags: dict[str, bool]) -> str:
    has_price = flags["has_xau_spot_price"]
    has_futures_basis = flags["has_gc_futures_price"] and flags["has_basis"]
    has_oi = flags["has_option_oi_by_strike"] and flags["has_expiry_dte"]
    has_iv = flags["has_option_iv"]
    has_freshness = flags["has_option_oi_change"] or flags["has_option_volume"]
    if has_price and has_futures_basis and has_oi and has_iv and has_freshness:
        return "FULL_CME_VOL_OI"
    if has_price and has_futures_basis and has_oi:
        return "CME_OI_ONLY"
    if has_price and has_iv and not has_oi:
        return "CME_IV_ONLY"
    if has_price:
        return "PRICE_ONLY"
    return "UNUSABLE"


def _pilot_usability_grade(flags: dict[str, bool]) -> str:
    """Classify the best research pilot a date can support now."""

    strict_grade = _validation_grade(flags)
    if strict_grade == "FULL_CME_VOL_OI":
        return "FULL_CME_VOL_OI"

    has_spot = flags["has_xau_spot_price"]
    has_futures = flags["has_gc_futures_price"]
    has_basis = flags["has_basis"]
    has_oi = flags["has_option_oi_by_strike"] and flags["has_expiry_dte"]
    has_freshness = flags["has_option_oi_change"] or flags["has_option_volume"]
    has_iv = flags["has_option_iv"]

    if has_oi and has_freshness and has_futures and (not has_spot or not has_basis):
        return "CME_OI_VOLUME_NEEDS_SPOT_BASIS"
    if has_oi and has_futures and has_spot and not has_iv:
        return "CME_OI_ONLY_NO_IV"
    if has_iv and not has_oi and (has_spot or has_futures):
        return "CME_IV_ONLY_NO_OI"
    if has_futures and not has_oi and not has_iv:
        return "CME_FUTURES_ONLY"
    if has_spot and not has_oi and not has_iv:
        return "PRICE_ONLY_GURU_PILOT"
    return "GURU_LOGIC_ONLY"


def _missing_components(flags: dict[str, bool]) -> list[str]:
    required = {
        "has_xau_spot_price": "xau_spot_price",
        "has_gc_futures_price": "gc_futures_price",
        "has_basis": "basis",
        "has_option_oi_by_strike": "option_oi_by_strike",
        "has_option_iv": "option_iv",
        "has_expiry_dte": "expiry_dte",
    }
    missing = [label for key, label in required.items() if not flags[key]]
    if not (flags["has_option_oi_change"] or flags["has_option_volume"]):
        missing.append("oi_change_or_option_volume")
    if not flags["has_macro_event_flag"]:
        missing.append("macro_event_flag")
    if not flags["has_option_settlement"]:
        missing.append("option_settlement")
    return missing


def _mark_basis_improvement(frame: pl.DataFrame) -> pl.DataFrame:
    raw = frame.filter(pl.col("mapping_method") == "RAW_STRIKE_SUMMARY")
    adjusted = frame.filter(pl.col("mapping_method") == "BASIS_ADJUSTED_SUMMARY")
    if raw.is_empty() or adjusted.is_empty():
        return frame
    raw_error = _float(raw.row(0, named=True).get("average_error_points"))
    adjusted_error = _float(adjusted.row(0, named=True).get("average_error_points"))
    improves = adjusted_error is not None and raw_error is not None and adjusted_error < raw_error
    return frame.with_columns(pl.when(pl.col("mapping_method") == "BASIS_ADJUSTED_SUMMARY").then(pl.lit(improves)).otherwise(pl.col("basis_adjustment_improves")).alias("basis_adjustment_improves"))


def _date_filter(frame: pl.DataFrame, trade_date: str) -> pl.DataFrame:
    if frame.is_empty() or "trade_date" not in frame.columns:
        return frame.clear()
    return frame.filter(pl.col("trade_date") == trade_date)


def _last_row(frame: pl.DataFrame) -> dict[str, Any]:
    return frame.sort("timestamp").tail(1).to_dicts()[0] if not frame.is_empty() and "timestamp" in frame.columns else {}


def _has_expiry_dte(frame: pl.DataFrame) -> bool:
    if frame.is_empty():
        return False
    has_expiry = "expiry" in frame.columns and any(bool(value) for value in frame.get_column("expiry").to_list())
    has_dte = "dte" in frame.columns and any(value is not None for value in frame.get_column("dte").to_list())
    return has_expiry and has_dte


def _looks_like_candidate(path: Path) -> bool:
    text = path.as_posix().lower()
    if "transcript" in text or "research_report" in text:
        return False
    hints = ("cme", "quikstrike", "xau", "gold", "gc", "option", "strike", "vol", "oi", "futures", "spot", "event")
    return any(hint in text for hint in hints)


def _detect_text_separator(path: Path) -> str:
    sample = path.read_text(encoding="utf-8", errors="replace")[:2048]
    return "\t" if sample.count("\t") >= sample.count(",") else ","


def _required_columns_for_type(detected_type: str) -> set[str]:
    return {
        "OPEN_INTEREST_HEATMAP": {"strike"},
        "OPEN_INTEREST_PROFILE": {"strike"},
        "MOST_ACTIVE_STRIKES": {"strike"},
        "OPTION_SETTLEMENTS": {"strike"},
        "QUIKVOL": {"strike"},
        "VOLATILITY_TERM_STRUCTURE": {"expiry"},
        "ECONOMIC_EVENT_ANALYZER": {"event_name"},
        "FUTURES_VOLUME_OI": {"volume"},
        "FUTURES_PRICE": {"open", "high", "low", "close"},
        "XAU_SPOT_PRICE": {"open", "high", "low", "close"},
    }.get(detected_type, set())


def _matched(cols: set[str], aliases: Iterable[str]) -> set[str]:
    normalized = {_normalize_name(alias) for alias in aliases}
    return cols & normalized


def _normalize_name(value: str) -> str:
    import re

    text = re.sub(r"(?<!^)(?=[A-Z])", "_", str(value).strip())
    return text.lower().replace(" ", "_").replace("-", "_")


def _find_col(columns: Iterable[str], aliases: Iterable[str]) -> str | None:
    lookup = {_normalize_name(column): column for column in columns}
    for alias in aliases:
        match = lookup.get(_normalize_name(alias))
        if match is not None:
            return match
    return None


def _parse_datetime(value: Any, *, fallback: str | Path | None = None, row: int = 0) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, date):
        return datetime.combine(value, time(0, 0), tzinfo=UTC)
    if value is not None and str(value).strip():
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            try:
                parsed_date = date.fromisoformat(str(value)[:10])
                return datetime.combine(parsed_date, time(0, 0), tzinfo=UTC)
            except ValueError:
                pass
    fallback_date = _date_from_path(fallback)
    if fallback_date is None:
        return None
    return datetime.combine(fallback_date, time(min(row, 23), 0), tzinfo=UTC)


def _parse_date(value: Any, *, fallback_date: date | None = None) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value is not None and str(value).strip():
        text = str(value).strip()[:10].replace("/", "-")
        try:
            return date.fromisoformat(text)
        except ValueError:
            pass
    return fallback_date


def _date_from_path(path: str | Path | None) -> date | None:
    if path is None:
        return None
    text = Path(path).as_posix()
    import re

    match = re.search(r"(20\d{2})[-_]?(\d{2})[-_]?(\d{2})", text)
    if not match:
        return None
    return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if isinstance(value, str):
            value = value.replace(",", "").replace("%", "").strip()
            if not value:
                return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_iv(value: float | None) -> float | None:
    if value is None:
        return None
    return value * 100.0 if 0 < value <= 1.0 else value


def _normalize_option_type(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text.startswith("c"):
        return "call"
    if text.startswith("p"):
        return "put"
    return "unknown"


def _date_start(frame: pl.DataFrame) -> str | None:
    dates = _extract_dates(frame)
    return min(dates).isoformat() if dates else None


def _date_end(frame: pl.DataFrame) -> str | None:
    dates = _extract_dates(frame)
    return max(dates).isoformat() if dates else None


def _extract_dates(frame: pl.DataFrame) -> list[date]:
    column = _find_col(frame.columns, ["timestamp", "datetime", "date", "trade_date", "asof_timestamp"])
    if column is None:
        return []
    dates = []
    for value in frame.get_column(column).to_list():
        parsed = _parse_datetime(value)
        if parsed is not None:
            dates.append(parsed.date())
    return dates


def _frame_from_rows(rows: list[dict[str, Any]], schema: dict[str, Any]) -> pl.DataFrame:
    return pl.DataFrame(rows, infer_schema_length=None) if rows else pl.DataFrame(schema=schema)


def _dedupe_paths(paths: Iterable[Path]) -> list[Path]:
    seen = set()
    result = []
    for path in paths:
        key = path.as_posix().lower()
        if key not in seen:
            seen.add(key)
            result.append(path)
    return result


def _max(frame: pl.DataFrame, column: str) -> float:
    if frame.is_empty() or column not in frame.columns:
        return 0.0
    values = [_float(value) for value in frame.get_column(column).to_list()]
    clean = [value for value in values if value is not None]
    return max(clean) if clean else 0.0


def _abs_max(frame: pl.DataFrame, column: str) -> float:
    if frame.is_empty() or column not in frame.columns:
        return 0.0
    values = [_float(value) for value in frame.get_column(column).to_list()]
    clean = [abs(value) for value in values if value is not None]
    return max(clean) if clean else 0.0


def _true_count(frame: pl.DataFrame, column: str) -> int:
    if frame.is_empty() or column not in frame.columns:
        return 0
    return sum(1 for value in frame.get_column(column).to_list() if bool(value))


def _any_true(frame: pl.DataFrame, column: str) -> bool:
    return _true_count(frame, column) > 0


def _mean_bool(frame: pl.DataFrame, column: str) -> float:
    if frame.is_empty() or column not in frame.columns:
        return 0.0
    values = [bool(value) for value in frame.get_column(column).to_list()]
    return sum(values) / len(values) if values else 0.0


def _generic_export_example(source_name: str) -> str:
    slug = _normalize_name(source_name).replace("__", "_")
    return f"{slug}_YYYYMMDD.csv"


def _user_action(status: str, source_name: str) -> str:
    if status == "AVAILABLE":
        return "No immediate action; verify date coverage and duplicates."
    if status == "PARTIAL":
        return f"Add more dates or missing fields for {source_name}."
    return f"Export/import {source_name} as a local CSV/XLSX/Parquet file."


def _frame_markdown(frame: pl.DataFrame) -> str:
    if frame.is_empty():
        return "_No rows._"
    columns = frame.columns
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join("---" for _ in columns) + " |"]
    for row in frame.head(40).to_dicts():
        lines.append("| " + " | ".join(str(row.get(column, "")).replace("|", "\\|") for column in columns) + " |")
    return "\n".join(lines)


def _file_detection_schema() -> dict[str, Any]:
    return {
        "source_id_hash": pl.String,
        "redacted_file_path": pl.String,
        "file_name": pl.String,
        "detected_type": pl.String,
        "confidence": pl.Float64,
        "matched_columns": pl.String,
        "missing_required_columns": pl.String,
        "parse_success": pl.Boolean,
        "rows_loaded": pl.Int64,
        "date_start": pl.String,
        "date_end": pl.String,
        "error": pl.String,
    }


def _option_oi_schema() -> dict[str, Any]:
    return {
        "asof_timestamp": pl.Datetime(time_zone="UTC"),
        "trade_date": pl.String,
        "product": pl.String,
        "underlying_symbol": pl.String,
        "contract_month": pl.String,
        "expiry": pl.String,
        "dte": pl.Float64,
        "option_type": pl.String,
        "strike": pl.Float64,
        "call_oi": pl.Float64,
        "put_oi": pl.Float64,
        "total_oi": pl.Float64,
        "call_volume": pl.Float64,
        "put_volume": pl.Float64,
        "total_volume": pl.Float64,
        "call_oi_change": pl.Float64,
        "put_oi_change": pl.Float64,
        "total_oi_change": pl.Float64,
        "source_file_hash": pl.String,
        "source_type": pl.String,
    }


def _option_iv_schema() -> dict[str, Any]:
    return {
        "asof_timestamp": pl.Datetime(time_zone="UTC"),
        "trade_date": pl.String,
        "product": pl.String,
        "expiry": pl.String,
        "dte": pl.Float64,
        "option_type": pl.String,
        "strike": pl.Float64,
        "implied_vol": pl.Float64,
        "delta": pl.Float64,
        "gamma": pl.Float64,
        "vega": pl.Float64,
        "theta": pl.Float64,
        "settlement_price": pl.Float64,
        "source_file_hash": pl.String,
        "source_type": pl.String,
    }


def _futures_schema() -> dict[str, Any]:
    return {
        "timestamp": pl.Datetime(time_zone="UTC"),
        "trade_date": pl.String,
        "product": pl.String,
        "contract_month": pl.String,
        "futures_symbol": pl.String,
        "open": pl.Float64,
        "high": pl.Float64,
        "low": pl.Float64,
        "close": pl.Float64,
        "settle": pl.Float64,
        "volume": pl.Float64,
        "open_interest": pl.Float64,
        "source_file_hash": pl.String,
    }


def _spot_schema() -> dict[str, Any]:
    return {
        "timestamp": pl.Datetime(time_zone="UTC"),
        "trade_date": pl.String,
        "symbol": pl.String,
        "open": pl.Float64,
        "high": pl.Float64,
        "low": pl.Float64,
        "close": pl.Float64,
        "volume": pl.Float64,
        "source_file_hash": pl.String,
    }


def _basis_schema() -> dict[str, Any]:
    return {
        "timestamp": pl.Datetime(time_zone="UTC"),
        "trade_date": pl.String,
        "futures_symbol": pl.String,
        "futures_price": pl.Float64,
        "spot_price": pl.Float64,
        "basis": pl.Float64,
        "basis_quality": pl.String,
        "source_file_hash": pl.String,
    }


def _event_schema() -> dict[str, Any]:
    return {
        "event_timestamp": pl.Datetime(time_zone="UTC"),
        "trade_date": pl.String,
        "event_name": pl.String,
        "event_type": pl.String,
        "expected_importance": pl.String,
        "actual": pl.String,
        "forecast": pl.String,
        "previous": pl.String,
        "source_file_hash": pl.String,
    }


def _validation_days_schema() -> dict[str, Any]:
    return {
        "trade_date": pl.String,
        "has_xau_spot_price": pl.Boolean,
        "has_gc_futures_price": pl.Boolean,
        "has_basis": pl.Boolean,
        "has_option_oi_by_strike": pl.Boolean,
        "has_option_oi_change": pl.Boolean,
        "has_option_volume": pl.Boolean,
        "has_option_iv": pl.Boolean,
        "has_option_settlement": pl.Boolean,
        "has_expiry_dte": pl.Boolean,
        "has_macro_event_flag": pl.Boolean,
        "complete_validation_grade": pl.Boolean,
        "missing_components": pl.String,
        "strict_validation_grade": pl.String,
        "pilot_usability_grade": pl.String,
        "validation_grade": pl.String,
    }


def _validation_dataset_schema() -> dict[str, Any]:
    return {
        "timestamp": pl.Datetime(time_zone="UTC"),
        "trade_date": pl.String,
        "spot_price": pl.Float64,
        "futures_price": pl.Float64,
        "basis": pl.Float64,
        "nearest_spot_equivalent_wall_above": pl.Float64,
        "nearest_spot_equivalent_wall_below": pl.Float64,
        "wall_score_above": pl.Float64,
        "wall_score_below": pl.Float64,
        "total_oi_near_spot": pl.Float64,
        "oi_change_near_spot": pl.Float64,
        "volume_near_spot": pl.Float64,
        "implied_vol_atm": pl.Float64,
        "iv_skew_call_put": pl.Float64,
        "one_sd_upper": pl.Float64,
        "one_sd_lower": pl.Float64,
        "two_sd_upper": pl.Float64,
        "two_sd_lower": pl.Float64,
        "sigma_position": pl.Float64,
        "strict_validation_grade": pl.String,
        "pilot_usability_grade": pl.String,
        "validation_grade": pl.String,
    }


def _basis_precision_schema() -> dict[str, Any]:
    return {
        "trade_date": pl.String,
        "mapping_method": pl.String,
        "wall_level": pl.Float64,
        "spot_price": pl.Float64,
        "distance_to_actual_turning_point": pl.Float64,
        "wall_touch_rate": pl.Float64,
        "rejection_rate": pl.Float64,
        "acceptance_rate": pl.Float64,
        "map_hit_rate": pl.Float64,
        "average_error_points": pl.Float64,
        "basis_adjustment_improves": pl.Boolean,
        "sample_size_warning": pl.Boolean,
    }


def _uplift_schema() -> dict[str, Any]:
    return {
        "stage": pl.String,
        "event_count": pl.Int64,
        "trade_count": pl.Int64,
        "expectancy": pl.Float64,
        "profit_factor": pl.Float64,
        "max_drawdown": pl.Float64,
        "win_rate": pl.Float64,
        "walk_forward_pass": pl.Boolean,
        "placebo_pass": pl.Boolean,
        "sample_size_warning": pl.Boolean,
        "cost_stress_survival": pl.Boolean,
        "uplift_vs_price_only": pl.Float64,
        "uplift_vs_bollinger": pl.Float64,
        "uplift_vs_sd_only": pl.Float64,
        "notes": pl.String,
    }


def _requirements_schema() -> dict[str, Any]:
    return {
        "source_name": pl.String,
        "why_needed": pl.String,
        "minimum_fields": pl.String,
        "current_status": pl.String,
        "priority": pl.String,
        "example_export_name": pl.String,
        "user_action_required": pl.String,
    }


def _duplicate_schema() -> dict[str, Any]:
    return {
        "trade_date": pl.String,
        "expiry": pl.String,
        "strike": pl.Float64,
        "option_type": pl.String,
        "row_count": pl.Int64,
        "source_count": pl.Int64,
        "conflict_fields": pl.String,
        "has_conflict": pl.Boolean,
        "resolution": pl.String,
    }
