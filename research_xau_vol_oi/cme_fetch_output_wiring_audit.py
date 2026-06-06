"""Audit CME fetch outputs and wire fetched QuikStrike rows into wall context."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import polars as pl

from research_xau_vol_oi.quikstrike_intraday_volume_snapshot import (
    QuikStrikeIntradayVolumeSnapshotResult,
    report_text_is_safe as quikstrike_report_text_is_safe,
    run_quikstrike_intraday_volume_snapshot,
)


FINAL_RECOMMENDATIONS = (
    "FETCHED_CME_DATA_CONNECTED",
    "MANUAL_CSV_NOT_NEEDED",
    "FETCHED_DATA_FOUND_BUT_NEEDS_MAPPING",
    "FETCHED_DATA_MISSING_INTRADAY_VOLUME",
    "CME_PILOT_RERUN_READY",
    "NEED_MORE_CME_DAYS",
    "NOT_READY_FOR_MONEY",
)
RESEARCH_WARNING = (
    "Research-only CME fetch output wiring audit. Fetched CME/QuikStrike rows "
    "are context inputs only; wall reactions still require confirmation."
)


@dataclass(frozen=True)
class CmeFetchOutputWiringAuditResult:
    """Generated CME fetch audit and rerun artifacts."""

    inventory: pl.DataFrame
    command_audit: pl.DataFrame
    source_resolution: pl.DataFrame
    quikstrike_result: QuikStrikeIntradayVolumeSnapshotResult
    overlap_rerun: pl.DataFrame
    usability_gap: pl.DataFrame
    final_recommendation: str
    paths: dict[str, Path]


def run_cme_fetch_output_wiring_audit(
    *,
    output_dir: str | Path = "outputs",
    write_outputs: bool = True,
) -> CmeFetchOutputWiringAuditResult:
    """Build the fetch-output inventory, source resolution, and pilot rerun."""

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    repo_root = _repo_root_from_output(output_root)
    paths = _output_paths(output_root)
    inventory = build_cme_fetch_output_inventory(output_root=output_root, repo_root=repo_root)
    command_audit = build_cme_fetch_command_audit(repo_root=repo_root)
    quikstrike_result = run_quikstrike_intraday_volume_snapshot(
        output_dir=output_root,
        allow_fallback_example=False,
        write_outputs=True,
    )
    source_resolution = quikstrike_result.source_resolution
    overlap_rerun = build_cme_overlap_backtest_rerun(output_root=output_root)
    usability_gap = build_cme_fetched_data_usability_gap(
        inventory=inventory,
        source_resolution=source_resolution,
    )
    final = choose_final_recommendation(
        inventory=inventory,
        source_resolution=source_resolution,
        overlap_rerun=overlap_rerun,
    )
    result = CmeFetchOutputWiringAuditResult(
        inventory=inventory,
        command_audit=command_audit,
        source_resolution=source_resolution,
        quikstrike_result=quikstrike_result,
        overlap_rerun=overlap_rerun,
        usability_gap=usability_gap,
        final_recommendation=final,
        paths=paths,
    )
    if write_outputs:
        write_cme_fetch_output_wiring_audit_outputs(result)
    return result


def build_cme_fetch_output_inventory(*, output_root: Path, repo_root: Path) -> pl.DataFrame:
    """Inventory project-local CME/QuikStrike-related files."""

    rows: list[dict[str, Any]] = []
    for path in _candidate_inventory_files(repo_root=repo_root, output_root=output_root):
        metadata = _table_metadata(path)
        detected = _detect_type(path=path, columns=metadata["columns"])
        if detected == "UNKNOWN" and not _name_looks_relevant(path.name):
            continue
        rows.append(
            {
                "redacted_path": _redacted_project_path(path, repo_root),
                "source_hash": _hash_file_head(path),
                "file_name": path.name,
                "detected_type": detected,
                "rows_count": metadata["rows_count"],
                "date_start": metadata["date_start"],
                "date_end": metadata["date_end"],
                "key_columns": ",".join(metadata["key_columns"]),
                "can_feed_quikstrike_snapshot": _can_feed_quikstrike_snapshot(
                    metadata["columns"],
                ),
                "can_feed_cme_overlap_backtest": _can_feed_cme_overlap_backtest(
                    metadata["columns"],
                    path.name,
                ),
                "notes": _inventory_notes(path=path, detected_type=detected, columns=metadata["columns"]),
            }
        )
    return _frame(rows, _inventory_schema()).sort(["detected_type", "redacted_path"])


def build_cme_fetch_command_audit(*, repo_root: Path) -> pl.DataFrame:
    """Describe the existing command path and output schema."""

    runner = repo_root / "scripts" / "run_daily_xau_quikstrike_snapshot.ps1"
    daily = repo_root / "backend" / "scripts" / "xau_daily_quikstrike_snapshot.py"
    store = repo_root / "backend" / "src" / "xau_quikstrike_fusion" / "report_store.py"
    rows = [
        {
            "script_name": "scripts/run_daily_xau_quikstrike_snapshot.ps1",
            "command_name": "powershell scripts/run_daily_xau_quikstrike_snapshot.ps1",
            "current_outputs": "backend/data/reports/xau_quikstrike_fusion/*/xau_vol_oi_input.csv",
            "output_folder": "backend/data/reports/xau_quikstrike_fusion",
            "output_schema": _known_xau_vol_oi_schema(),
            "fetches_intraday_volume": _file_contains(daily, "intraday_volume")
            or _file_contains(store, "intraday_volume"),
            "fetches_oi": _file_contains(store, "open_interest"),
            "fetches_oi_change": _file_contains(store, "oi_change"),
            "fetches_iv": _file_contains(store, "implied_volatility"),
            "fetches_futures_price": _file_contains(store, "underlying_futures_price"),
            "missing_sources": "none detected for fusion CSV; source depends on current browser capture",
            "recommended_wiring_fix": (
                "Use xau_vol_oi_input.csv as the first QuikStrike snapshot source; "
                "manual CSV stays fallback."
            ),
        },
        {
            "script_name": "backend/scripts/xau_daily_quikstrike_snapshot.py",
            "command_name": "python scripts/xau_daily_quikstrike_snapshot.py --cdp-url ...",
            "current_outputs": "fusion report, XAU Vol-OI input CSV, downstream research reports",
            "output_folder": "backend/data/reports",
            "output_schema": "Vol2Vol plus Matrix rows fused into xau_vol_oi_input.csv",
            "fetches_intraday_volume": _file_contains(daily, "extract_vol2vol_from_cdp"),
            "fetches_oi": _file_contains(daily, "extract_matrix_from_cdp"),
            "fetches_oi_change": _file_contains(daily, "extract_matrix_from_cdp"),
            "fetches_iv": _file_contains(daily, "extract_vol2vol_from_cdp"),
            "fetches_futures_price": _file_contains(daily, "gc_futures_reference"),
            "missing_sources": "no structured blocker found",
            "recommended_wiring_fix": "Keep using the persisted fusion CSV for report-layer ingestion.",
        },
    ]
    if not runner.exists():
        rows[0]["missing_sources"] = "runner script not found"
    if not daily.exists():
        rows[1]["missing_sources"] = "daily fetch script not found"
    return _frame(rows, _command_audit_schema())


def build_cme_overlap_backtest_rerun(*, output_root: Path) -> pl.DataFrame:
    """Create a compact rerun table from the current CME overlap artifacts."""

    candidates = _read_optional(output_root / "cme_overlap_trade_candidates.csv")
    filters = _read_optional(output_root / "cme_overlap_filter_backtest.csv")
    overlap_dates = _overlap_date_count(output_root=output_root, candidates=candidates)
    candidate_count = candidates.height if not candidates.is_empty() else _max_int(filters, "candidate_count")
    if filters.is_empty():
        return _frame(
            [
                _rerun_row(
                    scenario="RAW_CANDIDATES",
                    overlap_dates=overlap_dates,
                    candidate_count=candidate_count,
                    allowed_count=0,
                    blocked_count=candidate_count,
                    avg_return=None,
                    expectancy_proxy=None,
                    avoided_loss=None,
                    blocked_winner_count=0,
                    false_block_rate=0.0,
                    sample_size_warning=True,
                    pilot_warning="CME overlap filter artifact unavailable.",
                )
            ],
            _overlap_rerun_schema(),
        )

    scenario_map = {
        "RAW_CANDIDATES": "RAW_CANDIDATES",
        "PRICE_ONLY_FILTER": "PRICE_ONLY_FILTERS",
        "CME_WALL_FILTER": "CME_WALL_FILTER_ONLY",
        "CME_IV_FILTER": "CME_IV_RANGE_FILTER_ONLY",
        "GURU_HARD_FILTER": "GURU_FILTER_ONLY",
        "COMBINED_CONSERVATIVE_FILTER": "COMBINED_CONSERVATIVE_FILTER",
    }
    rows = []
    by_scenario = {str(row["scenario"]): row for row in filters.to_dicts()}
    for label, source in scenario_map.items():
        raw = by_scenario.get(source, {})
        rows.append(_rerun_row_from_filter(label, raw, overlap_dates, candidate_count))
    rows.insert(5, _guru_soft_warning_row(candidates, overlap_dates, candidate_count))
    return _frame(rows, _overlap_rerun_schema())


def build_cme_fetched_data_usability_gap(
    *,
    inventory: pl.DataFrame,
    source_resolution: pl.DataFrame,
) -> pl.DataFrame:
    """Explain whether fetched files can feed the snapshot layer."""

    rows: list[dict[str, Any]] = []
    selected_source = _selected_source(source_resolution)
    if selected_source in {"FETCHED_CME_DATA", "CANONICAL_CME_DATA"}:
        rows.append(
            _gap_row(
                file_name="selected_source",
                detected_type=selected_source,
                missing_columns="",
                wrong_schema=False,
                wrong_date_format=False,
                expiration_mismatch=False,
                no_strike_column=False,
                no_call_put_separation=False,
                no_timestamp=False,
                parser_not_connected=False,
                needs_transformation=False,
                recommendation="Selected source maps into the QuikStrike wall schema.",
            )
        )
    for row in inventory.head(250).to_dicts():
        relevant = str(row.get("detected_type", ""))
        if not relevant.startswith(("QUIKSTRIKE", "CME_")):
            continue
        if bool(row.get("can_feed_quikstrike_snapshot")):
            continue
        key_columns = set(str(row.get("key_columns") or "").split(","))
        missing = _missing_snapshot_columns(key_columns)
        rows.append(
            _gap_row(
                file_name=str(row.get("file_name") or ""),
                detected_type=relevant,
                missing_columns=",".join(missing),
                wrong_schema=bool(missing),
                wrong_date_format=False,
                expiration_mismatch=False,
                no_strike_column="strike" in missing,
                no_call_put_separation="option_type" in missing,
                no_timestamp=not ({"timestamp", "asof_timestamp", "trade_date"} & key_columns),
                parser_not_connected=False,
                needs_transformation=True,
                recommendation="Use as context only unless transformed into strike/side/volume rows.",
            )
        )
    if not rows:
        rows.append(
            _gap_row(
                file_name="inventory",
                detected_type="NONE",
                missing_columns="",
                wrong_schema=False,
                wrong_date_format=False,
                expiration_mismatch=False,
                no_strike_column=False,
                no_call_put_separation=False,
                no_timestamp=False,
                parser_not_connected=True,
                needs_transformation=False,
                recommendation="No fetched CME/QuikStrike files were found in project-local roots.",
            )
        )
    return _frame(rows, _gap_schema())


def choose_final_recommendation(
    *,
    inventory: pl.DataFrame,
    source_resolution: pl.DataFrame,
    overlap_rerun: pl.DataFrame,
) -> str:
    """Choose the conservative audit recommendation."""

    selected = _selected_source(source_resolution)
    if selected == "FETCHED_CME_DATA":
        return "FETCHED_CME_DATA_CONNECTED"
    if selected == "CANONICAL_CME_DATA":
        return "MANUAL_CSV_NOT_NEEDED"
    if _any_true(inventory, "can_feed_quikstrike_snapshot"):
        return "FETCHED_DATA_FOUND_BUT_NEEDS_MAPPING"
    if _any_type(inventory, "QUIKSTRIKE_INTRADAY_VOLUME"):
        return "FETCHED_DATA_FOUND_BUT_NEEDS_MAPPING"
    if not overlap_rerun.is_empty():
        return "CME_PILOT_RERUN_READY"
    return "FETCHED_DATA_MISSING_INTRADAY_VOLUME"


def write_cme_fetch_output_wiring_audit_outputs(
    result: CmeFetchOutputWiringAuditResult,
) -> None:
    """Write CSV and Markdown audit artifacts."""

    result.inventory.write_csv(result.paths["inventory_csv"])
    result.paths["inventory_md"].write_text(
        _safe_report_text(_artifact_markdown("CME Fetch Output Inventory", result.inventory)),
        encoding="utf-8",
    )
    result.command_audit.write_csv(result.paths["command_audit_csv"])
    result.paths["command_audit_md"].write_text(
        _safe_report_text(_artifact_markdown("CME Fetch Command Audit", result.command_audit)),
        encoding="utf-8",
    )
    result.overlap_rerun.write_csv(result.paths["overlap_rerun_csv"])
    result.paths["overlap_rerun_md"].write_text(
        _safe_report_text(
            _artifact_markdown("CME Overlap Rerun With Fetched Data", result.overlap_rerun)
        ),
        encoding="utf-8",
    )
    result.usability_gap.write_csv(result.paths["usability_gap_csv"])
    result.paths["usability_gap_md"].write_text(
        _safe_report_text(_artifact_markdown("Fetched Data Usability Gap", result.usability_gap)),
        encoding="utf-8",
    )


def cme_fetch_output_wiring_audit_report_lines(
    result: CmeFetchOutputWiringAuditResult | None,
) -> list[str]:
    """Return report sections for research_report.md."""

    if result is None:
        return ["## CME Fetch Output Inventory", "", "CME fetch output wiring audit was not run."]
    return [
        "## CME Fetch Output Inventory",
        "",
        RESEARCH_WARNING,
        "",
        f"- Final recommendation: `{result.final_recommendation}`",
        f"- Selected snapshot source: `{_selected_source(result.source_resolution)}`",
        f"- Inventory rows: {result.inventory.height}",
        "",
        _frame_markdown(result.inventory.head(30)),
        "",
        "## Fetch Command Audit",
        "",
        _frame_markdown(result.command_audit),
        "",
        "## QuikStrike Snapshot Source Resolution",
        "",
        _frame_markdown(result.source_resolution),
        "",
        "## Fetched CME Wall State",
        "",
        _frame_markdown(result.quikstrike_result.latest_state_from_fetch),
        "",
        "## CME Overlap Rerun With Fetched Data",
        "",
        _frame_markdown(result.overlap_rerun),
        "",
        "## Fetched Data Usability Gap",
        "",
        _frame_markdown(result.usability_gap),
        "",
        "- Links: `outputs/cme_fetch_output_inventory.csv`, "
        "`outputs/cme_fetch_command_audit.csv`, "
        "`outputs/quikstrike_snapshot_source_resolution.csv`, "
        "`outputs/cme_overlap_backtest_rerun_with_fetched_cme.csv`, "
        "`outputs/cme_fetched_data_usability_gap.csv`.",
    ]


def report_text_is_safe(text: str) -> bool:
    """Return true when report text is redacted and avoids restricted phrases."""

    return quikstrike_report_text_is_safe(_safe_report_text(text))


def _candidate_inventory_files(*, repo_root: Path, output_root: Path) -> list[Path]:
    roots = [
        repo_root / "data",
        repo_root / "data_pipeline",
        output_root,
        repo_root / "tmp",
        repo_root / "backend" / "data" / "reports",
        repo_root / "backend" / "data" / "raw",
    ]
    extensions = {".csv", ".parquet", ".json", ".md", ".yaml", ".yml"}
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in extensions:
                continue
            if any(part in {".git", ".venv", "__pycache__", "node_modules"} for part in path.parts):
                continue
            if "youtube_transcripts" in {part.lower() for part in path.parts}:
                continue
            name = str(path).lower()
            if _name_looks_relevant(name):
                files.append(path)
    return sorted(set(files), key=lambda path: str(path))


def _name_looks_relevant(name: str) -> bool:
    lowered = name.lower()
    keywords = (
        "quikstrike",
        "cme",
        "intraday",
        "vol2vol",
        "matrix",
        "fusion",
        "forward_journal",
        "forward-journal",
        "option",
        "open_interest",
        "oi_",
        "oi-",
        "settlement",
        "futures",
    )
    return any(keyword in lowered for keyword in keywords)


def _table_metadata(path: Path) -> dict[str, Any]:
    frame = _read_table_sample(path)
    columns = frame.columns if not frame.is_empty() else _header_columns(path)
    rows_count = _row_count(path, frame)
    dates = _date_range(frame)
    key_columns = _key_columns(columns)
    return {
        "columns": columns,
        "rows_count": rows_count,
        "date_start": dates[0],
        "date_end": dates[1],
        "key_columns": key_columns,
    }


def _read_table_sample(path: Path) -> pl.DataFrame:
    try:
        suffix = path.suffix.lower()
        if suffix == ".parquet":
            return pl.read_parquet(path)
        if suffix == ".csv":
            return pl.read_csv(path, infer_schema_length=200)
        if suffix == ".json":
            return pl.read_json(path)
    except Exception:
        return pl.DataFrame()
    return pl.DataFrame()


def _header_columns(path: Path) -> list[str]:
    try:
        if path.suffix.lower() == ".csv":
            return path.read_text(encoding="utf-8", errors="ignore").splitlines()[0].split(",")
    except (OSError, IndexError):
        return []
    return []


def _row_count(path: Path, frame: pl.DataFrame) -> int:
    if not frame.is_empty():
        return frame.height
    if path.suffix.lower() == ".csv":
        try:
            return max(0, len(path.read_text(encoding="utf-8", errors="ignore").splitlines()) - 1)
        except OSError:
            return 0
    return 0


def _date_range(frame: pl.DataFrame) -> tuple[str, str]:
    if frame.is_empty():
        return "", ""
    for column in ["trade_date", "date", "timestamp", "asof_timestamp", "snapshot_timestamp"]:
        if column not in frame.columns:
            continue
        values = [_date_text(value) for value in frame.get_column(column).to_list()]
        values = sorted(value for value in values if value)
        if values:
            return values[0], values[-1]
    return "", ""


def _date_text(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value or "").strip()
    match = re.search(r"(20\d{2})[-_/]?(0\d|1[0-2])[-_/]?([0-3]\d)", text)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    return ""


def _key_columns(columns: list[str]) -> list[str]:
    important = {
        "date",
        "trade_date",
        "timestamp",
        "asof_timestamp",
        "snapshot_timestamp",
        "expiry",
        "expiration",
        "expiration_code",
        "strike",
        "option_type",
        "call_volume",
        "put_volume",
        "volume",
        "intraday_volume",
        "open_interest",
        "oi_change",
        "implied_volatility",
        "underlying_futures_price",
        "future_price",
    }
    return [column for column in columns if column in important]


def _detect_type(*, path: Path, columns: list[str]) -> str:
    name = path.name.lower()
    column_set = set(columns)
    if "xau_vol_oi_input" in name and {"intraday_volume", "option_type", "strike"} <= column_set:
        return "QUIKSTRIKE_INTRADAY_VOLUME"
    if "vol2vol" in name:
        return "QUIKSTRIKE_VOL2VOL"
    if "matrix" in name:
        return "QUIKSTRIKE_MATRIX"
    if "fusion" in name or "xau_vol_oi_input" in name:
        return "QUIKSTRIKE_FUSION"
    if {"call_volume", "put_volume", "strike"} <= column_set:
        return "QUIKSTRIKE_INTRADAY_VOLUME"
    if {"call_oi", "put_oi", "strike"} <= column_set or "open_interest" in column_set:
        return "QUIKSTRIKE_OI"
    if "oi_change" in column_set or "oi_change" in name:
        return "QUIKSTRIKE_OI_CHANGE"
    if "implied_volatility" in column_set or "_iv_" in name or name.endswith("_iv_by_strike.parquet"):
        return "CME_OPTION_IV"
    if "future" in name or "futures" in name or "underlying_futures_price" in column_set:
        return "CME_FUTURES_PRICE"
    if "forward_journal" in name or "forward-journal" in name:
        return "FORWARD_JOURNAL"
    return "UNKNOWN"


def _can_feed_quikstrike_snapshot(columns: list[str]) -> bool:
    column_set = set(columns)
    wide = {"strike", "call_volume", "put_volume"} <= column_set
    long = (
        "strike" in column_set
        and "option_type" in column_set
        and bool({"intraday_volume", "volume", "eod_volume", "total_volume"} & column_set)
    )
    return wide or long


def _can_feed_cme_overlap_backtest(columns: list[str], name: str) -> bool:
    column_set = set(columns)
    if "cme_overlap" in name.lower():
        return True
    return "strike" in column_set and bool(
        {"open_interest", "call_oi", "put_oi", "implied_volatility"} & column_set
    )


def _inventory_notes(*, path: Path, detected_type: str, columns: list[str]) -> str:
    if _can_feed_quikstrike_snapshot(columns):
        return "Can feed QuikStrike snapshot schema."
    if detected_type == "QUIKSTRIKE_FUSION":
        return "Fusion artifact detected; inspect schema before use."
    if path.suffix.lower() in {".md", ".yaml", ".yml"}:
        return "Text/config artifact; not a direct tabular source."
    return "Not directly connected to snapshot schema."


def _rerun_row_from_filter(
    label: str,
    raw: dict[str, Any],
    overlap_dates: int,
    candidate_count: int,
) -> dict[str, Any]:
    return _rerun_row(
        scenario=label,
        overlap_dates=overlap_dates,
        candidate_count=_int(raw.get("candidate_count")) or candidate_count,
        allowed_count=_int(raw.get("allowed_count")) or 0,
        blocked_count=_int(raw.get("blocked_count")) or 0,
        avg_return=_float(raw.get("average_return")),
        expectancy_proxy=_float(raw.get("expectancy_proxy")),
        avoided_loss=_float(raw.get("net_filter_value_proxy")),
        blocked_winner_count=_int(raw.get("blocked_winning_candidates")) or 0,
        false_block_rate=_float(raw.get("false_block_rate")) or 0.0,
        sample_size_warning=True,
        pilot_warning=_pilot_warning(overlap_dates, candidate_count),
    )


def _guru_soft_warning_row(
    candidates: pl.DataFrame,
    overlap_dates: int,
    candidate_count: int,
) -> dict[str, Any]:
    warning_count = 0
    avg_return = None
    if not candidates.is_empty():
        if "guru_filter_context" in candidates.columns:
            warning_count = candidates.filter(pl.col("guru_filter_context") != "OK").height
        if "raw_pnl" in candidates.columns:
            avg_return = _float(candidates.get_column("raw_pnl").mean())
    return _rerun_row(
        scenario="GURU_SOFT_WARNING",
        overlap_dates=overlap_dates,
        candidate_count=candidate_count,
        allowed_count=candidate_count,
        blocked_count=0,
        avg_return=avg_return,
        expectancy_proxy=avg_return,
        avoided_loss=0.0,
        blocked_winner_count=0,
        false_block_rate=0.0,
        sample_size_warning=True,
        pilot_warning=(
            f"Soft warning tags {warning_count} candidates but does not block them; "
            f"{_pilot_warning(overlap_dates, candidate_count)}"
        ),
    )


def _rerun_row(
    *,
    scenario: str,
    overlap_dates: int,
    candidate_count: int,
    allowed_count: int,
    blocked_count: int,
    avg_return: float | None,
    expectancy_proxy: float | None,
    avoided_loss: float | None,
    blocked_winner_count: int,
    false_block_rate: float,
    sample_size_warning: bool,
    pilot_warning: str,
) -> dict[str, Any]:
    return {
        "scenario": scenario,
        "overlap_dates": overlap_dates,
        "candidate_count": candidate_count,
        "allowed_count": allowed_count,
        "blocked_count": blocked_count,
        "avg_return": avg_return,
        "expectancy_proxy": expectancy_proxy,
        "avoided_loss": avoided_loss,
        "blocked_winner_count": blocked_winner_count,
        "false_block_rate": false_block_rate,
        "sample_size_warning": sample_size_warning,
        "pilot_warning": pilot_warning,
    }


def _pilot_warning(overlap_dates: int, candidate_count: int) -> str:
    if overlap_dates < 30 or candidate_count < 50:
        return "INSUFFICIENT_SAMPLE / NEED_MORE_CME_DAYS / NOT_READY_FOR_MONEY"
    return "Pilot sample expanded; still research-only."


def _overlap_date_count(*, output_root: Path, candidates: pl.DataFrame) -> int:
    date_audit = _read_optional(output_root / "cme_overlap_backtest_date_audit.csv")
    if not date_audit.is_empty() and "can_run_cme_filter_test" in date_audit.columns:
        return date_audit.filter(pl.col("can_run_cme_filter_test")).height
    if not candidates.is_empty() and "trade_date" in candidates.columns:
        return candidates.get_column("trade_date").n_unique()
    return 0


def _missing_snapshot_columns(key_columns: set[str]) -> list[str]:
    missing = []
    if "strike" not in key_columns:
        missing.append("strike")
    has_side = "option_type" in key_columns or {"call_volume", "put_volume"} <= key_columns
    if not has_side:
        missing.append("option_type")
    has_volume = bool({"intraday_volume", "volume", "call_volume", "put_volume"} & key_columns)
    if not has_volume:
        missing.append("intraday_volume")
    return missing


def _gap_row(
    *,
    file_name: str,
    detected_type: str,
    missing_columns: str,
    wrong_schema: bool,
    wrong_date_format: bool,
    expiration_mismatch: bool,
    no_strike_column: bool,
    no_call_put_separation: bool,
    no_timestamp: bool,
    parser_not_connected: bool,
    needs_transformation: bool,
    recommendation: str,
) -> dict[str, Any]:
    return {
        "file_name": file_name,
        "detected_type": detected_type,
        "missing_columns": missing_columns,
        "wrong_schema": wrong_schema,
        "wrong_date_format": wrong_date_format,
        "expiration_mismatch": expiration_mismatch,
        "no_strike_column": no_strike_column,
        "no_call_put_separation": no_call_put_separation,
        "no_timestamp": no_timestamp,
        "parser_not_connected": parser_not_connected,
        "needs_transformation": needs_transformation,
        "recommendation": recommendation,
    }


def _output_paths(output_root: Path) -> dict[str, Path]:
    return {
        "inventory_csv": output_root / "cme_fetch_output_inventory.csv",
        "inventory_md": output_root / "cme_fetch_output_inventory.md",
        "command_audit_csv": output_root / "cme_fetch_command_audit.csv",
        "command_audit_md": output_root / "cme_fetch_command_audit.md",
        "overlap_rerun_csv": output_root / "cme_overlap_backtest_rerun_with_fetched_cme.csv",
        "overlap_rerun_md": output_root / "cme_overlap_backtest_rerun_with_fetched_cme.md",
        "usability_gap_csv": output_root / "cme_fetched_data_usability_gap.csv",
        "usability_gap_md": output_root / "cme_fetched_data_usability_gap.md",
    }


def _known_xau_vol_oi_schema() -> str:
    columns = [
        "date",
        "timestamp",
        "expiry",
        "expiration_code",
        "strike",
        "option_type",
        "open_interest",
        "oi_change",
        "volume",
        "intraday_volume",
        "implied_volatility",
        "underlying_futures_price",
    ]
    return ",".join(columns)


def _file_contains(path: Path, text: str) -> bool:
    try:
        return text in path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False


def _read_optional(path: Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    try:
        if path.suffix.lower() == ".parquet":
            return pl.read_parquet(path)
        if path.suffix.lower() == ".csv":
            return pl.read_csv(path, infer_schema_length=None)
    except Exception:
        return pl.DataFrame()
    return pl.DataFrame()


def _selected_source(source_resolution: pl.DataFrame) -> str:
    if source_resolution.is_empty() or "selected_source_type" not in source_resolution.columns:
        return "NONE"
    return str(source_resolution.row(0, named=True).get("selected_source_type") or "NONE")


def _any_true(frame: pl.DataFrame, column: str) -> bool:
    if frame.is_empty() or column not in frame.columns:
        return False
    return bool(frame.get_column(column).any())


def _any_type(frame: pl.DataFrame, detected_type: str) -> bool:
    if frame.is_empty() or "detected_type" not in frame.columns:
        return False
    return detected_type in set(frame.get_column("detected_type").to_list())


def _max_int(frame: pl.DataFrame, column: str) -> int:
    if frame.is_empty() or column not in frame.columns:
        return 0
    values = [_int(value) for value in frame.get_column(column).to_list()]
    values = [value for value in values if value is not None]
    return max(values) if values else 0


def _float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _repo_root_from_output(output_root: Path) -> Path:
    resolved = output_root.resolve()
    for candidate in (resolved, *resolved.parents):
        if (candidate / "research_xau_vol_oi").exists():
            return candidate
    return resolved.parent


def _redacted_project_path(path: Path, repo_root: Path) -> str:
    try:
        relative = path.resolve().relative_to(repo_root.resolve())
        return "<PROJECT_ROOT>/" + "/".join(relative.parts)
    except ValueError:
        return "<REDACTED_PATH>/" + path.name


def _hash_file_head(path: Path) -> str:
    try:
        digest = hashlib.sha256()
        digest.update(str(path.stat().st_size).encode("utf-8"))
        with path.open("rb") as handle:
            digest.update(handle.read(1024 * 1024))
        return digest.hexdigest()[:16]
    except OSError:
        return ""


def _artifact_markdown(title: str, frame: pl.DataFrame) -> str:
    return "\n\n".join([f"# {title}", RESEARCH_WARNING, _frame_markdown(frame)])


def _frame_markdown(frame: pl.DataFrame, *, limit: int = 40) -> str:
    if frame.is_empty():
        return "_No rows._"
    sample = frame.head(limit)
    lines = [
        "| " + " | ".join(sample.columns) + " |",
        "| " + " | ".join("---" for _ in sample.columns) + " |",
    ]
    for row in sample.to_dicts():
        lines.append(
            "| "
            + " | ".join(_markdown_cell(row.get(column, "")) for column in sample.columns)
            + " |"
        )
    if frame.height > limit:
        lines.append(f"\n_Showing {limit} of {frame.height} rows._")
    return "\n".join(lines)


def _markdown_cell(value: Any) -> str:
    return _safe_text(value).replace("|", "\\|").replace("\n", " ")[:700]


def _safe_report_text(text: str) -> str:
    return _safe_text(text)


def _safe_text(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"[A-Za-z]:\\Users\\[^\s|)<>\"']+", "<REDACTED_PATH>", text)
    text = re.sub(r"[A-Za-z]:\\[^\s|)<>\"']+", "<REDACTED_PATH>", text)
    text = re.sub(r"/(?:Users|home|mnt|var|tmp)/[^\s|)<>\"']+", "<REDACTED_PATH>", text)
    text = re.sub(r"\bbuy\b", "direction", text, flags=re.IGNORECASE)
    text = re.sub(r"\bsell\b", "direction", text, flags=re.IGNORECASE)
    text = re.sub(r"profitable|profitability", "money-result", text, flags=re.IGNORECASE)
    return text.strip()


def _frame(rows: list[dict[str, Any]], schema: dict[str, Any]) -> pl.DataFrame:
    if not rows:
        return pl.DataFrame(schema=schema)
    frame = pl.DataFrame(rows, infer_schema_length=None)
    for column, dtype in schema.items():
        if column not in frame.columns:
            frame = frame.with_columns(pl.lit(None).cast(dtype).alias(column))
        else:
            frame = frame.with_columns(pl.col(column).cast(dtype, strict=False).alias(column))
    return frame.select(list(schema))


def _inventory_schema() -> dict[str, Any]:
    return {
        "redacted_path": pl.Utf8,
        "source_hash": pl.Utf8,
        "file_name": pl.Utf8,
        "detected_type": pl.Utf8,
        "rows_count": pl.Int64,
        "date_start": pl.Utf8,
        "date_end": pl.Utf8,
        "key_columns": pl.Utf8,
        "can_feed_quikstrike_snapshot": pl.Boolean,
        "can_feed_cme_overlap_backtest": pl.Boolean,
        "notes": pl.Utf8,
    }


def _command_audit_schema() -> dict[str, Any]:
    return {
        "script_name": pl.Utf8,
        "command_name": pl.Utf8,
        "current_outputs": pl.Utf8,
        "output_folder": pl.Utf8,
        "output_schema": pl.Utf8,
        "fetches_intraday_volume": pl.Boolean,
        "fetches_oi": pl.Boolean,
        "fetches_oi_change": pl.Boolean,
        "fetches_iv": pl.Boolean,
        "fetches_futures_price": pl.Boolean,
        "missing_sources": pl.Utf8,
        "recommended_wiring_fix": pl.Utf8,
    }


def _overlap_rerun_schema() -> dict[str, Any]:
    return {
        "scenario": pl.Utf8,
        "overlap_dates": pl.Int64,
        "candidate_count": pl.Int64,
        "allowed_count": pl.Int64,
        "blocked_count": pl.Int64,
        "avg_return": pl.Float64,
        "expectancy_proxy": pl.Float64,
        "avoided_loss": pl.Float64,
        "blocked_winner_count": pl.Int64,
        "false_block_rate": pl.Float64,
        "sample_size_warning": pl.Boolean,
        "pilot_warning": pl.Utf8,
    }


def _gap_schema() -> dict[str, Any]:
    return {
        "file_name": pl.Utf8,
        "detected_type": pl.Utf8,
        "missing_columns": pl.Utf8,
        "wrong_schema": pl.Boolean,
        "wrong_date_format": pl.Boolean,
        "expiration_mismatch": pl.Boolean,
        "no_strike_column": pl.Boolean,
        "no_call_put_separation": pl.Boolean,
        "no_timestamp": pl.Boolean,
        "parser_not_connected": pl.Boolean,
        "needs_transformation": pl.Boolean,
        "recommendation": pl.Utf8,
    }
