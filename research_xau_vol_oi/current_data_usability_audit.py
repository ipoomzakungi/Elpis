"""Current CME data usability audit and one-week pilot summaries.

This module reads local generated outputs and user-provided local research
files only. It does not fetch protected data, log in to CME/QuikStrike,
connect to brokers, or create execution instructions.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Iterable

import polars as pl

from research_xau_vol_oi.cme_history_importer import (
    DEFAULT_CME_IMPORT_ROOTS,
    detect_cme_export_type,
    discover_cme_history_import_files,
    load_supported_table,
)
from research_xau_vol_oi.data_recovery_audit import hash_source_id


POSSIBLE_IV_COLUMNS = (
    "implied_volatility",
    "impliedVolatility",
    "implied_vol",
    "iv",
    "IV",
    "volatility",
    "atm_iv",
    "quikvol",
    "cvol",
    "vol2vol",
    "sigma",
    "expected_move",
    "one_sd",
)
FORBIDDEN_REPORT_PHRASES = (
    "profitable",
    "guaranteed",
    "safe to trade",
    "live ready",
    "buy now",
    "sell now",
)
GENERATED_AUDIT_OUTPUT_NAMES = {
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
}


@dataclass(frozen=True)
class CurrentDataUsabilityAuditResult:
    """Frames and recommendation produced by the current-data audit."""

    date_usability: pl.DataFrame
    iv_field_mapping_audit: pl.DataFrame
    spot_basis_join_audit: pl.DataFrame
    one_week_cme_pilot_summary: pl.DataFrame
    ohlc_guru_price_only_pilot: pl.DataFrame
    cme_fetch_tool_gap_audit: pl.DataFrame
    final_recommendation: str


def run_current_data_usability_audit(
    *,
    output_dir: str | Path = "outputs",
    search_roots: Iterable[str | Path] | None = None,
    script_roots: Iterable[str | Path] | None = None,
) -> CurrentDataUsabilityAuditResult:
    """Build all requested current-data audit artifacts."""

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    charts_dir = output_root / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    frames = _load_existing_outputs(output_root)
    roots = tuple(Path(root) for root in (search_roots or DEFAULT_CME_IMPORT_ROOTS))

    date_usability = build_current_cme_date_usability(frames)
    iv_audit = build_iv_field_mapping_audit(
        output_root=output_root,
        search_roots=roots,
        canonical_iv=frames["option_iv"],
        date_usability=date_usability,
    )
    spot_basis = build_spot_basis_join_audit(
        frames=frames,
        output_root=output_root,
        search_roots=roots,
    )
    one_week = build_one_week_cme_pilot_summary(frames=frames, date_usability=date_usability)
    ohlc_guru = build_ohlc_guru_price_only_pilot(frames=frames)
    fetch_audit = build_cme_fetch_tool_gap_audit(script_roots=script_roots)
    recommendation = choose_final_recommendation(
        date_usability=date_usability,
        iv_audit=iv_audit,
        one_week=one_week,
        ohlc_guru=ohlc_guru,
    )

    date_usability.write_csv(output_root / "current_cme_date_usability.csv")
    iv_audit.write_csv(output_root / "iv_field_mapping_audit.csv")
    spot_basis.write_csv(output_root / "spot_basis_join_audit.csv")
    one_week.write_csv(output_root / "one_week_cme_pilot_summary.csv")
    ohlc_guru.write_csv(output_root / "ohlc_guru_price_only_pilot.csv")
    fetch_audit.write_csv(output_root / "cme_fetch_tool_gap_audit.csv")

    (output_root / "current_cme_date_usability.md").write_text(
        current_cme_date_usability_markdown(date_usability, recommendation),
        encoding="utf-8",
    )
    (output_root / "iv_field_mapping_audit.md").write_text(
        iv_field_mapping_audit_markdown(iv_audit, date_usability),
        encoding="utf-8",
    )
    (output_root / "spot_basis_join_audit.md").write_text(
        spot_basis_join_audit_markdown(spot_basis),
        encoding="utf-8",
    )
    (output_root / "one_week_cme_pilot_report.md").write_text(
        one_week_cme_pilot_markdown(one_week),
        encoding="utf-8",
    )
    (output_root / "ohlc_guru_price_only_pilot.md").write_text(
        ohlc_guru_price_only_markdown(ohlc_guru),
        encoding="utf-8",
    )
    (output_root / "cme_fetch_tool_gap_audit.md").write_text(
        cme_fetch_tool_gap_markdown(fetch_audit),
        encoding="utf-8",
    )
    write_one_week_wall_map_svg(charts_dir / "one_week_cme_wall_map.svg", one_week)
    write_one_week_expected_range_svg(charts_dir / "one_week_cme_expected_range.svg", one_week)

    return CurrentDataUsabilityAuditResult(
        date_usability=date_usability,
        iv_field_mapping_audit=iv_audit,
        spot_basis_join_audit=spot_basis,
        one_week_cme_pilot_summary=one_week,
        ohlc_guru_price_only_pilot=ohlc_guru,
        cme_fetch_tool_gap_audit=fetch_audit,
        final_recommendation=recommendation,
    )


def build_current_cme_date_usability(frames: dict[str, pl.DataFrame]) -> pl.DataFrame:
    """Explain strict rejection and partial pilot usability for each date."""

    validation = frames["validation_days"]
    transcript_dates = _transcript_dates(frames)
    dates = set(transcript_dates)
    for key in ("validation_days", "option_oi", "option_iv", "futures", "spot", "basis", "events"):
        dates.update(_trade_dates(frames[key]))
    rows: list[dict[str, Any]] = []
    validation_by_date = _rows_by_date(validation, "trade_date")

    for trade_date in sorted(dates):
        flags = _flags_for_date(frames, trade_date)
        fallback = validation_by_date.get(trade_date, {})
        for key in _flag_columns():
            if not flags[key] and key in fallback:
                flags[key] = bool(fallback[key])
        strict_grade = str(
            fallback.get("strict_validation_grade")
            or fallback.get("validation_grade")
            or _strict_validation_grade(flags)
        )
        pilot_grade = str(fallback.get("pilot_usability_grade") or _pilot_usability_grade(flags, trade_date in transcript_dates))
        missing = _missing_components(flags)
        rows.append(
            {
                "trade_date": trade_date,
                "current_validation_grade": str(fallback.get("validation_grade") or strict_grade),
                "strict_validation_grade": strict_grade,
                "pilot_usability_grade": pilot_grade,
                "complete_validation_grade": strict_grade == "FULL_CME_VOL_OI",
                **flags,
                "missing_components": "|".join(missing),
                "can_use_for_full_validation": strict_grade == "FULL_CME_VOL_OI",
                "can_use_for_cme_oi_pilot": pilot_grade
                in {"FULL_CME_VOL_OI", "CME_OI_VOLUME_NEEDS_SPOT_BASIS", "CME_OI_ONLY_NO_IV"},
                "can_use_for_cme_iv_pilot": bool(flags["has_option_iv"] and (flags["has_gc_futures_price"] or flags["has_xau_spot_price"])),
                "can_use_for_price_only_pilot": bool(flags["has_xau_spot_price"] or flags["has_gc_futures_price"]),
                "can_use_for_guru_logic_alignment": bool(trade_date in transcript_dates or frames["guru_kb"].height > 0),
                "reason_plain_english": _reason_plain_english(flags, strict_grade, pilot_grade),
                "next_fix_needed": _next_fix_needed(flags, pilot_grade),
            }
        )
    return _frame(rows, _date_usability_schema()).sort("trade_date")


def build_iv_field_mapping_audit(
    *,
    output_root: Path,
    search_roots: Iterable[Path],
    canonical_iv: pl.DataFrame,
    date_usability: pl.DataFrame,
) -> pl.DataFrame:
    """Search raw and canonical files for IV-like fields and mapping gaps."""

    canonical_hashes = _source_hashes(canonical_iv)
    paths = _audit_candidate_paths(output_root, search_roots)
    rows: list[dict[str, Any]] = []
    usability_by_date = _rows_by_date(date_usability, "trade_date")
    for path in paths:
        try:
            frame = load_supported_table(path)
        except Exception:
            continue
        detected = _detected_iv_columns(frame.columns)
        if not detected:
            continue
        source_hash = hash_source_id(str(path.resolve()) if path.exists() else str(path))
        likely = _likely_iv_column(detected)
        date_start, date_end = _date_range(frame, fallback_path=path)
        used = source_hash in canonical_hashes or path.name == "cme_canonical_option_iv_by_strike.parquet"
        dates = _dates_between(date_start, date_end)
        date_has_missing_iv = any(not bool(usability_by_date.get(item, {}).get("has_option_iv")) for item in dates)
        mapping_fix = bool(likely and (not used or date_has_missing_iv))
        rows.append(
            {
                "file_hash": source_hash,
                "redacted_file_name": _redacted_file_name(path),
                "detected_columns": "|".join(detected),
                "likely_iv_column": likely or "",
                "likely_iv_unit": _likely_iv_unit(frame, likely),
                "rows_count": frame.height,
                "date_start": date_start or "",
                "date_end": date_end or "",
                "currently_used_as_option_iv": used,
                "mapping_fix_needed": mapping_fix,
                "recommended_canonical_mapping": _recommended_iv_mapping(likely, mapping_fix),
            }
        )
    return _frame(rows, _iv_audit_schema()).sort(["mapping_fix_needed", "redacted_file_name"], descending=[True, False])


def build_spot_basis_join_audit(
    *,
    frames: dict[str, pl.DataFrame],
    output_root: Path,
    search_roots: Iterable[Path],
) -> pl.DataFrame:
    """Explain spot/futures/basis coverage and why basis is missing."""

    spot_files = _spot_file_summary(output_root, search_roots)
    dates = set()
    for key in ("futures", "spot", "basis"):
        dates.update(_trade_dates(frames[key]))
    rows: list[dict[str, Any]] = []
    for trade_date in sorted(dates):
        futures = _date_filter(frames["futures"], trade_date)
        spot = _date_filter(frames["spot"], trade_date)
        basis = _date_filter(frames["basis"], trade_date)
        can_calc = not futures.is_empty() and not spot.is_empty()
        if not basis.is_empty():
            reason = "basis_available"
        elif spot.is_empty():
            reason = "missing_xau_spot_price"
        elif futures.is_empty():
            reason = "missing_gc_futures_price"
        elif can_calc:
            reason = "importer_failure_or_stale_basis_output"
        else:
            reason = "insufficient_price_inputs"
        rows.append(
            {
                "trade_date": trade_date,
                "xau_spot_files_exist": bool(spot_files),
                "xau_spot_file_count": len(spot_files),
                "redacted_spot_files": "|".join(item["redacted_file_name"] for item in spot_files[:8]),
                "spot_date_coverage": _coverage_text(frames["spot"]),
                "futures_date_coverage": _coverage_text(frames["futures"]),
                "basis_date_coverage": _coverage_text(frames["basis"]),
                "spot_rows": spot.height,
                "futures_rows": futures.height,
                "basis_rows": basis.height,
                "timestamp_granularity": _granularity(spot if not spot.is_empty() else futures),
                "joins_to_cme_futures_dates": can_calc,
                "basis_can_be_calculated_from_existing": can_calc,
                "basis_missing_reason": reason,
                "likely_root_cause": _basis_root_cause(reason),
            }
        )
    return _frame(rows, _spot_basis_schema()).sort("trade_date")


def build_one_week_cme_pilot_summary(
    *,
    frames: dict[str, pl.DataFrame],
    date_usability: pl.DataFrame,
) -> pl.DataFrame:
    """Build a partial/full CME pilot summary for dates with strike-level CME data."""

    cme_dates = _trade_dates(frames["option_oi"]) | _trade_dates(frames["option_iv"])
    if not cme_dates:
        cme_dates = {
            row["trade_date"]
            for row in date_usability.to_dicts()
            if row.get("pilot_usability_grade") in {"FULL_CME_VOL_OI", "CME_FUTURES_ONLY"}
        }
    rows: list[dict[str, Any]] = []
    usability = _rows_by_date(date_usability, "trade_date")
    guru_dates = _transcript_dates(frames)
    for trade_date in sorted(cme_dates):
        flags = usability.get(trade_date, {})
        pilot_grade = _pilot_report_grade(str(flags.get("pilot_usability_grade") or "GURU_LOGIC_ONLY"))
        oi_rows = _date_filter(frames["option_oi"], trade_date)
        iv_rows = _date_filter(frames["option_iv"], trade_date)
        spot_row = _last_row(_date_filter(frames["spot"], trade_date))
        futures_row = _last_row(_date_filter(frames["futures"], trade_date))
        basis_row = _last_row(_date_filter(frames["basis"], trade_date))
        basis = _float(basis_row.get("basis"))
        spot_price = _float(spot_row.get("close"))
        futures_price = _float(futures_row.get("settle")) or _float(futures_row.get("close"))
        reference_price = spot_price or futures_price
        walls = _top_wall_levels(oi_rows, basis=basis)
        nearest = _nearest_wall_pair(walls, reference_price)
        iv_value = _atm_iv(iv_rows, reference_price=reference_price, basis=basis)
        expected_move = (reference_price * (iv_value / 100.0) / (252.0**0.5)) if reference_price and iv_value else None
        reaction = _price_reaction(_date_filter(frames["spot"], trade_date), _date_filter(frames["futures"], trade_date), nearest)
        rows.append(
            {
                "trade_date": trade_date,
                "pilot_grade": pilot_grade,
                "top_wall_above": nearest["above"],
                "top_wall_below": nearest["below"],
                "top_wall_score": nearest["score"],
                "oi_change_freshness_available": bool(flags.get("has_option_oi_change")),
                "option_volume_available": bool(flags.get("has_option_volume")),
                "iv_available": bool(flags.get("has_option_iv") or iv_value is not None),
                "basis_available": basis is not None,
                "spot_available": spot_price is not None,
                "price_reaction_available": bool(reaction),
                "guru_context_available": trade_date in guru_dates or frames["guru_kb"].height > 0,
                "expected_move": expected_move,
                "wall_level_basis": "spot_equivalent" if basis is not None else "futures_strike_NEEDS_BASIS",
                "pilot_observation": _pilot_observation(pilot_grade, reaction, iv_value, basis),
                "confidence": _pilot_confidence(pilot_grade, basis is not None, spot_price is not None),
            }
        )
    return _frame(rows, _one_week_schema()).sort("trade_date")


def build_ohlc_guru_price_only_pilot(frames: dict[str, pl.DataFrame]) -> pl.DataFrame:
    """Summarize non-CME-dependent guru/price pilot metrics."""

    events = frames["transcript_conditioned_events"]
    outcomes = frames["guru_episode_outcomes"]
    signal_events = frames["signal_events"]
    rows = [_price_only_metric_row("overall_price_only_guru", events, outcomes, signal_events)]
    if not outcomes.is_empty() and "rule_tag" in outcomes.columns:
        for rule_tag in sorted(str(value) for value in outcomes.get_column("rule_tag").unique().to_list() if value):
            subset = outcomes.filter(pl.col("rule_tag") == rule_tag)
            rows.append(_price_only_metric_row(f"rule:{rule_tag}", events, subset, signal_events))
    return _frame(rows, _ohlc_guru_schema())


def build_cme_fetch_tool_gap_audit(
    *,
    script_roots: Iterable[str | Path] | None = None,
) -> pl.DataFrame:
    """Inspect local fetch/collection scripts for missing sources."""

    paths = _fetch_script_paths(script_roots)
    required_sources = {
        "XAU/USD spot OHLC": ("xau", "spot"),
        "GC futures OHLC": ("gc", "futures"),
        "basis calculation": ("basis",),
        "QuikVol / IV": ("quikvol", "implied", "iv", "vol2vol"),
        "Vol2Vol expected range": ("vol2vol", "expected"),
        "option settlements": ("settlement", "settle"),
        "Most Active Strikes": ("most active", "active strikes", "volume"),
        "macro event calendar": ("macro", "economic", "calendar"),
        "session open / high / low / close": ("session", "open", "high", "low", "close"),
        "realized volatility": ("realized", "volatility"),
    }
    rows: list[dict[str, Any]] = []
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
        lower = text.lower()
        collected = _collected_sources(lower)
        missing = [name for name, hints in required_sources.items() if not all(hint in lower for hint in hints)]
        is_quikstrike = "quikstrike" in lower or "cmegroup-sso" in lower
        rows.append(
            {
                "script_name": path.name,
                "current_collected_sources": "|".join(collected),
                "missing_sources": "|".join(missing),
                "can_fetch_automatically": not is_quikstrike and bool(collected),
                "requires_manual_export": is_quikstrike,
                "auth_or_login_needed": is_quikstrike,
                "recommended_script_change": _recommended_fetch_change(missing, is_quikstrike),
            }
        )
    return _frame(rows, _fetch_audit_schema()).sort("script_name")


def choose_final_recommendation(
    *,
    date_usability: pl.DataFrame,
    iv_audit: pl.DataFrame,
    one_week: pl.DataFrame,
    ohlc_guru: pl.DataFrame,
) -> str:
    """Choose one allowed recommendation label."""

    if not one_week.is_empty() and _any_true(one_week, "option_volume_available"):
        return "CURRENT_WEEK_PILOT_READY"
    if not ohlc_guru.is_empty() and _max(ohlc_guru, "event_count") > 0:
        return "OHLC_GURU_ONLY_READY"
    if _any_true(iv_audit, "mapping_fix_needed"):
        return "ADD_IV_MAPPING_FIRST"
    if _any_true(date_usability, "can_use_for_cme_oi_pilot"):
        return "ADD_SPOT_BASIS_FIRST"
    return "FIX_IMPORT_MAPPING_FIRST"


def current_data_usability_report_lines(result: CurrentDataUsabilityAuditResult | None) -> list[str]:
    """Return Markdown lines for embedding in the main research report."""

    if result is None:
        return ["Current data usability audit was not run."]
    usable = result.date_usability.filter(pl.col("can_use_for_cme_oi_pilot")) if not result.date_usability.is_empty() else result.date_usability
    rejected = (
        result.date_usability.filter((pl.col("current_validation_grade") == "UNUSABLE") & (pl.col("pilot_usability_grade") != "GURU_LOGIC_ONLY"))
        if not result.date_usability.is_empty()
        else result.date_usability
    )
    return [
        "## Current Data Usability Audit",
        "",
        f"- Final recommendation: `{result.final_recommendation}`",
        f"- Dates usable for CME OI pilot now: {usable.height}",
        f"- Strictly rejected dates with partial pilot value: {rejected.height}",
        "- Strict validation remains conservative; pilot usability is reported separately.",
        "",
        "## Why Some CME Dates Are Rejected",
        "",
        _frame_markdown(
            rejected.select(
                [
                    "trade_date",
                    "current_validation_grade",
                    "pilot_usability_grade",
                    "missing_components",
                    "reason_plain_english",
                    "next_fix_needed",
                ]
            ).tail(12)
            if not rejected.is_empty()
            else rejected
        ),
        "",
        "## IV Field Mapping Audit",
        "",
        _frame_markdown(
            result.iv_field_mapping_audit.select(
                [
                    "redacted_file_name",
                    "detected_columns",
                    "likely_iv_column",
                    "likely_iv_unit",
                    "currently_used_as_option_iv",
                    "mapping_fix_needed",
                    "recommended_canonical_mapping",
                ]
            ).head(12)
            if not result.iv_field_mapping_audit.is_empty()
            else result.iv_field_mapping_audit
        ),
        "",
        "## Spot/Basis Join Audit",
        "",
        _frame_markdown(
            result.spot_basis_join_audit.select(
                [
                    "trade_date",
                    "spot_rows",
                    "futures_rows",
                    "basis_rows",
                    "basis_can_be_calculated_from_existing",
                    "basis_missing_reason",
                ]
            ).tail(12)
            if not result.spot_basis_join_audit.is_empty()
            else result.spot_basis_join_audit
        ),
        "",
        "## One-Week CME Pilot",
        "",
        _frame_markdown(
            result.one_week_cme_pilot_summary.select(
                [
                    "trade_date",
                    "pilot_grade",
                    "top_wall_above",
                    "top_wall_below",
                    "iv_available",
                    "basis_available",
                    "spot_available",
                    "confidence",
                ]
            )
            if not result.one_week_cme_pilot_summary.is_empty()
            else result.one_week_cme_pilot_summary
        ),
        "",
        "## OHLC + Guru Price-Only Pilot",
        "",
        _frame_markdown(result.ohlc_guru_price_only_pilot.head(12)),
        "",
        "## Fetch Tool Gap Audit",
        "",
        _frame_markdown(result.cme_fetch_tool_gap_audit),
        "",
        "## What We Can Do Now vs What Needs More Data",
        "",
        "- Current-week CME OI/volume walls can be reviewed as futures-strike pilot evidence when spot/basis is missing.",
        "- Full validation still needs complete spot, basis, IV, settlement, macro, and enough date coverage.",
        "- OHLC plus guru logic can continue as price-only context without CME-dependent conclusions.",
    ]


def current_cme_date_usability_markdown(frame: pl.DataFrame, recommendation: str) -> str:
    counts = frame.group_by("pilot_usability_grade").len().sort("pilot_usability_grade") if not frame.is_empty() else frame
    rejected = (
        frame.filter((pl.col("current_validation_grade") == "UNUSABLE") & (pl.col("pilot_usability_grade") != "GURU_LOGIC_ONLY"))
        if not frame.is_empty()
        else frame
    )
    return "\n".join(
        [
            "# Current CME Date Usability",
            "",
            "Research-only data availability audit. Strict validation is separate from pilot usability.",
            "",
            f"- Recommendation: `{recommendation}`",
            "",
            "## Pilot Grade Counts",
            "",
            _frame_markdown(counts),
            "",
            "## Strict Rejections With Partial Pilot Use",
            "",
            _frame_markdown(rejected.tail(30)),
        ]
    )


def iv_field_mapping_audit_markdown(frame: pl.DataFrame, date_usability: pl.DataFrame) -> str:
    bug_count = frame.filter(pl.col("mapping_fix_needed")).height if not frame.is_empty() else 0
    missing_iv_dates = (
        date_usability.filter(~pl.col("has_option_iv")).height if not date_usability.is_empty() else 0
    )
    return "\n".join(
        [
            "# IV Field Mapping Audit",
            "",
            "Research-only mapping audit. File names are redacted to names and hashes only.",
            "",
            f"- IV-like files needing mapping review: {bug_count}",
            f"- Dates currently missing canonical option IV: {missing_iv_dates}",
            "",
            _frame_markdown(frame),
        ]
    )


def spot_basis_join_audit_markdown(frame: pl.DataFrame) -> str:
    missing = frame.filter(pl.col("basis_rows") == 0) if not frame.is_empty() else frame
    return "\n".join(
        [
            "# Spot/Basis Join Audit",
            "",
            "Basis is calculated only when same-date futures and XAU spot/proxy rows exist.",
            "",
            _frame_markdown(missing.tail(40)),
        ]
    )


def one_week_cme_pilot_markdown(frame: pl.DataFrame) -> str:
    return "\n".join(
        [
            "# One-Week CME Pilot Report",
            "",
            "Partial CME data is shown as pilot context, not as a completed validation set.",
            "",
            _frame_markdown(frame),
        ]
    )


def ohlc_guru_price_only_markdown(frame: pl.DataFrame) -> str:
    return "\n".join(
        [
            "# OHLC + Guru Price-Only Pilot",
            "",
            "This pilot uses price/transcript context only when CME components are absent.",
            "",
            _frame_markdown(frame),
        ]
    )


def cme_fetch_tool_gap_markdown(frame: pl.DataFrame) -> str:
    return "\n".join(
        [
            "# CME Fetch Tool Gap Audit",
            "",
            "Manual-login CME/QuikStrike sources are reported as manual. No protected-data scraping is added.",
            "",
            _frame_markdown(frame),
        ]
    )


def write_one_week_wall_map_svg(path: Path, frame: pl.DataFrame) -> None:
    """Write a small static wall map SVG."""

    if frame.is_empty():
        path.write_text(_svg("One-week CME wall map", "<text x='30' y='70'>No CME pilot rows.</text>"), encoding="utf-8")
        return
    rows = frame.to_dicts()
    labels = [str(row["trade_date"]) for row in rows]
    above = [_float(row.get("top_wall_above")) for row in rows]
    below = [_float(row.get("top_wall_below")) for row in rows]
    values = [value for value in [*above, *below] if value is not None]
    if not values:
        path.write_text(_svg("One-week CME wall map", "<text x='30' y='70'>No wall levels available.</text>"), encoding="utf-8")
        return
    minimum, maximum = min(values), max(values)
    span = max(maximum - minimum, 1.0)
    body = []
    for index, label in enumerate(labels):
        x = 60 + index * 95
        body.append(f"<text x='{x}' y='280' font-size='10' transform='rotate(45 {x},280)'>{html.escape(label)}</text>")
        for value, color, name in ((above[index], "#dc2626", "above"), (below[index], "#2563eb", "below")):
            if value is None:
                continue
            y = 245 - ((value - minimum) / span) * 190
            body.append(f"<circle cx='{x}' cy='{y:.1f}' r='5' fill='{color}'><title>{name}: {value:.2f}</title></circle>")
    path.write_text(_svg("One-week CME wall map", "\n".join(body)), encoding="utf-8")


def write_one_week_expected_range_svg(path: Path, frame: pl.DataFrame) -> None:
    """Write a small static expected-range SVG."""

    if frame.is_empty() or "expected_move" not in frame.columns:
        path.write_text(_svg("One-week CME expected range", "<text x='30' y='70'>No expected range rows.</text>"), encoding="utf-8")
        return
    rows = frame.to_dicts()
    values = [_float(row.get("expected_move")) for row in rows]
    clean = [value for value in values if value is not None]
    if not clean:
        path.write_text(_svg("One-week CME expected range", "<text x='30' y='70'>IV/expected move not available.</text>"), encoding="utf-8")
        return
    maximum = max(clean) or 1.0
    body = []
    for index, row in enumerate(rows):
        value = _float(row.get("expected_move"))
        if value is None:
            continue
        x = 60 + index * 95
        height = value / maximum * 190
        y = 245 - height
        label = html.escape(str(row.get("trade_date")))
        body.append(f"<rect x='{x}' y='{y:.1f}' width='42' height='{height:.1f}' fill='#0f766e'><title>{label}: {value:.2f}</title></rect>")
        body.append(f"<text x='{x}' y='280' font-size='10' transform='rotate(45 {x},280)'>{label}</text>")
    path.write_text(_svg("One-week CME expected range", "\n".join(body)), encoding="utf-8")


def _load_existing_outputs(output_root: Path) -> dict[str, pl.DataFrame]:
    spot = _read_frame(output_root / "cme_canonical_xau_spot_price.parquet", _spot_schema())
    return {
        "validation_days": _read_frame(output_root / "cme_validation_grade_days.csv", _date_usability_input_schema()),
        "option_oi": _read_frame(output_root / "cme_canonical_option_oi_by_strike.parquet", _option_oi_schema()),
        "option_iv": _read_frame(output_root / "cme_canonical_option_iv_by_strike.parquet", _option_iv_schema()),
        "futures": _read_frame(output_root / "cme_canonical_futures_price.parquet", _futures_schema()),
        "spot": _compact_price_frame(spot),
        "basis": _read_frame(output_root / "cme_canonical_basis.parquet", _basis_schema()),
        "events": _read_frame(output_root / "cme_canonical_macro_event_calendar.csv", _event_schema()),
        "validation_dataset": _read_frame(output_root / "xau_vol_oi_validation_dataset.parquet", {}),
        "guru_kb": _read_frame(output_root / "guru_logic_knowledge_base.csv", {}),
        "guru_priority": _read_frame(output_root / "guru_logic_priority_rank.csv", {}),
        "gold_baseline": _read_frame(output_root / "gold_baseline_metrics.csv", {}),
        "signal_events": _read_frame(output_root / "signal_events.csv", {}),
        "backtest_summary": _read_frame(output_root / "backtest_summary.csv", {}),
        "transcript_timeline": _read_frame(output_root / "transcript_rule_timeline.csv", {}),
        "transcript_conditioned_events": _read_frame(output_root / "transcript_conditioned_events.csv", {}),
        "guru_episode_outcomes": _read_frame(output_root / "guru_episode_outcomes.csv", {}),
    }


def _read_frame(path: Path, schema: dict[str, Any]) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame(schema=schema)
    try:
        if path.suffix == ".parquet":
            return pl.read_parquet(path)
        return pl.read_csv(path)
    except Exception:
        return pl.DataFrame(schema=schema)


def _compact_price_frame(frame: pl.DataFrame, *, max_rows: int = 20_000) -> pl.DataFrame:
    """Reduce large intraday price frames to date-level OHLC for this audit."""

    if frame.is_empty() or frame.height <= max_rows or "trade_date" not in frame.columns:
        return frame
    columns = set(frame.columns)
    aggregations = []
    if "timestamp" in columns:
        aggregations.append(pl.col("timestamp").max().alias("timestamp"))
    if "open" in columns:
        aggregations.append(pl.col("open").first().alias("open"))
    if "high" in columns:
        aggregations.append(pl.col("high").max().alias("high"))
    if "low" in columns:
        aggregations.append(pl.col("low").min().alias("low"))
    if "close" in columns:
        aggregations.append(pl.col("close").last().alias("close"))
    if "spot_price" in columns:
        aggregations.append(pl.col("spot_price").last().alias("spot_price"))
    if not aggregations:
        return frame
    return frame.sort("timestamp" if "timestamp" in columns else "trade_date").group_by(
        "trade_date"
    ).agg(aggregations).sort("trade_date")


def _flags_for_date(frames: dict[str, pl.DataFrame], trade_date: str) -> dict[str, bool]:
    oi = _date_filter(frames["option_oi"], trade_date)
    iv = _date_filter(frames["option_iv"], trade_date)
    futures = _date_filter(frames["futures"], trade_date)
    spot = _date_filter(frames["spot"], trade_date)
    basis = _date_filter(frames["basis"], trade_date)
    events = _date_filter(frames["events"], trade_date)
    return {
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


def _strict_validation_grade(flags: dict[str, bool]) -> str:
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


def _pilot_usability_grade(flags: dict[str, bool], has_transcript: bool = False) -> str:
    strict = _strict_validation_grade(flags)
    if strict == "FULL_CME_VOL_OI":
        return "FULL_CME_VOL_OI"
    has_oi = flags["has_option_oi_by_strike"] and flags["has_expiry_dte"]
    has_freshness = flags["has_option_oi_change"] or flags["has_option_volume"]
    has_spot = flags["has_xau_spot_price"]
    has_futures = flags["has_gc_futures_price"]
    has_basis = flags["has_basis"]
    has_iv = flags["has_option_iv"]
    if has_oi and has_freshness and has_futures and (not has_spot or not has_basis):
        return "CME_OI_VOLUME_NEEDS_SPOT_BASIS"
    if has_oi and has_futures and has_spot and not has_iv:
        return "CME_OI_ONLY_NO_IV"
    if has_iv and not has_oi and (has_spot or has_futures):
        return "CME_IV_ONLY_NO_OI"
    if has_futures and not has_oi and not has_iv:
        return "CME_FUTURES_ONLY"
    if has_spot:
        return "PRICE_ONLY_GURU_PILOT"
    return "GURU_LOGIC_ONLY" if has_transcript else "GURU_LOGIC_ONLY"


def _pilot_report_grade(grade: str) -> str:
    return "PRICE_ONLY_GURU" if grade == "PRICE_ONLY_GURU_PILOT" else grade.replace("GURU_LOGIC_ONLY", "GURU_ONLY")


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


def _reason_plain_english(flags: dict[str, bool], strict_grade: str, pilot_grade: str) -> str:
    if strict_grade == "FULL_CME_VOL_OI":
        return "Full strict validation inputs exist for this date."
    if pilot_grade == "CME_OI_VOLUME_NEEDS_SPOT_BASIS":
        return "CME OI/volume and futures exist, but spot/basis are missing, so strict validation rejects the date."
    if pilot_grade == "CME_OI_ONLY_NO_IV":
        return "OI and price context exist, but IV is missing, so this is OI-only pilot data."
    if pilot_grade == "CME_IV_ONLY_NO_OI":
        return "IV exists without enough OI-by-strike context for an OI-wall pilot."
    if pilot_grade == "CME_FUTURES_ONLY":
        return "Futures OHLC exists, but strike-level CME option context is missing."
    if pilot_grade == "PRICE_ONLY_GURU_PILOT":
        return "Spot/price context exists without CME option context; use price-only guru logic checks."
    if not flags["has_xau_spot_price"]:
        return "Strict validation needs spot and basis before CME walls can be mapped to XAU spot levels."
    return "Only transcript or insufficient market context exists for this date."


def _next_fix_needed(flags: dict[str, bool], pilot_grade: str) -> str:
    if pilot_grade == "FULL_CME_VOL_OI":
        return "No immediate data fix for strict components; continue collecting more days."
    if not flags["has_xau_spot_price"]:
        return "Add XAU spot/proxy OHLC for the date."
    if not flags["has_basis"]:
        return "Calculate basis from same-date futures and spot rows."
    if not flags["has_option_iv"]:
        return "Map/import IV fields into canonical option IV."
    if not flags["has_option_settlement"]:
        return "Import option settlement fields if available."
    return "Add missing CME option, macro, or freshness fields."


def _detected_iv_columns(columns: Iterable[str]) -> list[str]:
    normalized_targets = {_normalize_name(value) for value in POSSIBLE_IV_COLUMNS}
    result = []
    for column in columns:
        normalized = _normalize_name(column)
        if normalized in normalized_targets or any(token in normalized for token in ("volatility", "vol2vol", "quikvol", "cvol")):
            result.append(str(column))
    return result


def _likely_iv_column(columns: list[str]) -> str:
    priority = [_normalize_name(value) for value in POSSIBLE_IV_COLUMNS]
    ranked = sorted(columns, key=lambda column: priority.index(_normalize_name(column)) if _normalize_name(column) in priority else 999)
    return ranked[0] if ranked else ""


def _likely_iv_unit(frame: pl.DataFrame, column: str | None) -> str:
    if not column or column not in frame.columns:
        return "unknown"
    values = [_float(value) for value in frame.get_column(column).to_list()]
    clean = [value for value in values if value is not None and value > 0]
    if not clean:
        return "unknown"
    maximum = max(clean)
    if maximum <= 1.5:
        return "decimal"
    if maximum <= 250:
        return "percent"
    return "unknown"


def _recommended_iv_mapping(column: str, mapping_fix_needed: bool) -> str:
    if not column:
        return "none"
    if mapping_fix_needed:
        return f"map {column} to canonical implied_vol and normalize decimal values to percent"
    return "already represented in canonical option_iv_by_strike"


def _spot_file_summary(output_root: Path, search_roots: Iterable[Path]) -> list[dict[str, str]]:
    paths = _audit_candidate_paths(output_root, search_roots)
    rows = []
    for path in paths:
        try:
            frame = load_supported_table(path)
            detection = detect_cme_export_type(path, frame)
        except Exception:
            continue
        if detection.get("detected_type") == "XAU_SPOT_PRICE" or ("spot" in path.name.lower() and "xau" in path.name.lower()):
            rows.append(
                {
                    "redacted_file_name": _redacted_file_name(path),
                    "file_hash": hash_source_id(str(path.resolve()) if path.exists() else str(path)),
                }
            )
    return rows


def _audit_candidate_paths(output_root: Path, search_roots: Iterable[Path]) -> list[Path]:
    paths = set()
    for name in (
        "cme_canonical_option_iv_by_strike.parquet",
        "cme_canonical_option_oi_by_strike.parquet",
        "cme_canonical_futures_price.parquet",
        "cme_canonical_xau_spot_price.parquet",
        "cme_canonical_basis.parquet",
    ):
        path = output_root / name
        if path.exists():
            paths.add(path)
    for path in discover_cme_history_import_files(search_roots):
        if path.name in GENERATED_AUDIT_OUTPUT_NAMES:
            continue
        paths.add(path)
    return sorted(paths, key=lambda item: item.as_posix().lower())


def _top_wall_levels(option_oi: pl.DataFrame, *, basis: float | None) -> list[dict[str, float]]:
    if option_oi.is_empty() or "total_oi" not in option_oi.columns:
        return []
    max_oi = _max(option_oi, "total_oi") or 1.0
    rows = []
    for row in option_oi.sort("total_oi", descending=True).head(25).to_dicts():
        strike = _float(row.get("strike"))
        oi = _float(row.get("total_oi"))
        if strike is None or oi is None:
            continue
        rows.append({"level": strike - basis if basis is not None else strike, "score": oi / max_oi})
    return rows


def _nearest_wall_pair(walls: list[dict[str, float]], price: float | None) -> dict[str, Any]:
    result = {"above": None, "below": None, "score": None}
    if price is None or not walls:
        if walls:
            result["score"] = max(row["score"] for row in walls)
        return result
    above = [row for row in walls if row["level"] >= price]
    below = [row for row in walls if row["level"] <= price]
    if above:
        row = min(above, key=lambda item: abs(item["level"] - price))
        result["above"] = row["level"]
        result["score"] = row["score"]
    if below:
        row = min(below, key=lambda item: abs(item["level"] - price))
        result["below"] = row["level"]
        result["score"] = max(result["score"] or 0.0, row["score"])
    return result


def _atm_iv(option_iv: pl.DataFrame, *, reference_price: float | None, basis: float | None) -> float | None:
    if option_iv.is_empty():
        return None
    values = []
    for row in option_iv.to_dicts():
        iv = _float(row.get("implied_vol"))
        strike = _float(row.get("strike"))
        if iv is None or strike is None:
            continue
        level = strike - basis if basis is not None else strike
        distance = abs(level - reference_price) if reference_price is not None else 0.0
        values.append((distance, iv))
    return min(values)[1] if values else None


def _price_reaction(spot: pl.DataFrame, futures: pl.DataFrame, nearest: dict[str, Any]) -> str:
    frame = spot if not spot.is_empty() else futures
    if frame.is_empty():
        return ""
    high = _max(frame, "high")
    low = _min(frame, "low")
    close = _float(_last_row(frame).get("close")) or _float(_last_row(frame).get("settle"))
    wall_above = _float(nearest.get("above"))
    wall_below = _float(nearest.get("below"))
    if wall_above is not None and high >= wall_above and close is not None:
        return "touched_wall_above_rejected" if close < wall_above else "accepted_above_wall"
    if wall_below is not None and low <= wall_below and close is not None:
        return "touched_wall_below_rejected" if close > wall_below else "accepted_below_wall"
    return ""


def _pilot_observation(pilot_grade: str, reaction: str, iv: float | None, basis: float | None) -> str:
    parts = [f"{pilot_grade} can be reviewed as pilot context."]
    if basis is None and pilot_grade.startswith("CME_OI"):
        parts.append("Levels are futures strikes until basis is added.")
    if iv is None:
        parts.append("IV/expected-move context is unavailable.")
    if reaction:
        parts.append(f"Observed price relation: {reaction}.")
    return " ".join(parts)


def _pilot_confidence(pilot_grade: str, basis_available: bool, spot_available: bool) -> str:
    if pilot_grade == "FULL_CME_VOL_OI":
        return "HIGH"
    if pilot_grade == "CME_OI_VOLUME_NEEDS_SPOT_BASIS":
        return "MEDIUM" if basis_available and spot_available else "LOW"
    if pilot_grade in {"CME_OI_ONLY_NO_IV", "PRICE_ONLY_GURU"}:
        return "LOW"
    return "DEBUG_ONLY"


def _price_only_metric_row(
    bucket: str,
    events: pl.DataFrame,
    outcomes: pl.DataFrame,
    signal_events: pl.DataFrame,
) -> dict[str, Any]:
    event_count = events.height if not events.is_empty() else signal_events.height
    signal_count = _unique_count(signal_events, "signal")
    avoided = _true_count(events, "no_trade_row_retained") if not events.is_empty() else _signal_count(signal_events, "NO_TRADE")
    breakout_rows = _filter_text(outcomes, "thesis_type", "BREAK")
    rejection_rows = _filter_text(outcomes, "thesis_type", "REJECT")
    no_clear = _filter_text(outcomes, "outcome_label", "NO_CLEAR")
    direction_known = outcomes.filter(pl.col("direction_correct").is_not_null()) if not outcomes.is_empty() and "direction_correct" in outcomes.columns else pl.DataFrame()
    false_block_proxy = _safe_ratio(_signal_count(signal_events, "NO_TRADE"), signal_events.height)
    status = "INSUFFICIENT_DATA"
    if event_count > 0 and outcomes.height > 0:
        status = "PRICE_ONLY_FILTER_CANDIDATE"
    elif event_count > 0:
        status = "PRICE_ONLY_CONTEXT"
    if _contains_cme_dependent_tags(bucket):
        status = "NEEDS_CME_CONFIRMATION"
    return {
        "logic_bucket": bucket,
        "event_count": event_count,
        "signal_count": signal_count,
        "avoided_trade_proxy": avoided,
        "chop_rate": _safe_ratio(no_clear.height, outcomes.height),
        "breakout_followthrough_rate": _true_rate(breakout_rows, "direction_correct"),
        "rejection_followthrough_rate": _true_rate(rejection_rows, "wall_rejected"),
        "false_block_rate": false_block_proxy,
        "sample_size_warning": event_count < 30 or direction_known.height < 30,
        "validation_status": status,
    }


def _fetch_script_paths(script_roots: Iterable[str | Path] | None) -> list[Path]:
    if script_roots is not None:
        roots = [Path(root) for root in script_roots]
        paths: list[Path] = []
        for root in roots:
            if root.is_file():
                paths.append(root)
            elif root.exists():
                paths.extend(path for path in root.rglob("*") if path.suffix.lower() in {".py", ".ps1", ".md"})
        return sorted(paths)
    candidates = [
        Path("backend/scripts/xau_daily_quikstrike_snapshot.py"),
        Path("backend/scripts/quikstrike_playwright_extract.py"),
        Path("backend/scripts/quikstrike_matrix_playwright_extract.py"),
        Path("scripts/run_daily_xau_quikstrike_snapshot.ps1"),
        Path("docs/operations/xau_daily_quikstrike_snapshot.md"),
    ]
    return [path for path in candidates if path.exists()]


def _collected_sources(lower_text: str) -> list[str]:
    found = []
    checks = {
        "QuikStrike Vol2Vol": ("vol2vol",),
        "QuikStrike Matrix": ("matrix",),
        "XAU QuikStrike Fusion": ("fusion",),
        "Forward Journal snapshot": ("forward journal", "daily_snapshot"),
        "option OI by strike": ("open interest", "strike"),
        "option volume": ("volume",),
        "GC/futures reference": ("futures", "gc"),
    }
    for name, hints in checks.items():
        if all(hint in lower_text for hint in hints):
            found.append(name)
    return found


def _recommended_fetch_change(missing: list[str], is_quikstrike: bool) -> str:
    prefix = "Keep manual login/export boundaries for CME/QuikStrike. " if is_quikstrike else ""
    if not missing:
        return prefix + "No immediate source addition detected from static audit."
    priority = [item for item in missing if item in {"XAU/USD spot OHLC", "basis calculation", "QuikVol / IV", "option settlements"}]
    selected = priority or missing[:3]
    return prefix + "Add or document source handling for: " + ", ".join(selected) + "."


def _contains_cme_dependent_tags(text: str) -> bool:
    upper = text.upper()
    return any(token in upper for token in ("OI_WALL", "BASIS", "IV_", "SQUEEZE", "PIN_RISK"))


def _date_filter(frame: pl.DataFrame, trade_date: str) -> pl.DataFrame:
    if frame.is_empty() or "trade_date" not in frame.columns:
        return frame.clear()
    return frame.filter(pl.col("trade_date").cast(pl.String) == trade_date)


def _last_row(frame: pl.DataFrame) -> dict[str, Any]:
    if frame.is_empty():
        return {}
    if "timestamp" in frame.columns:
        return frame.sort("timestamp").tail(1).to_dicts()[0]
    if "asof_timestamp" in frame.columns:
        return frame.sort("asof_timestamp").tail(1).to_dicts()[0]
    return frame.tail(1).to_dicts()[0]


def _trade_dates(frame: pl.DataFrame) -> set[str]:
    if frame.is_empty() or "trade_date" not in frame.columns:
        return set()
    return {str(value) for value in frame.get_column("trade_date").to_list() if value}


def _transcript_dates(frames: dict[str, pl.DataFrame]) -> set[str]:
    result = set()
    timeline = frames.get("transcript_timeline", pl.DataFrame())
    if not timeline.is_empty() and "transcript_date" in timeline.columns:
        result.update(str(value) for value in timeline.get_column("transcript_date").to_list() if value)
    episodes = frames.get("guru_episode_outcomes", pl.DataFrame())
    if not episodes.is_empty() and "availability_timestamp" in episodes.columns:
        for value in episodes.get_column("availability_timestamp").to_list():
            parsed = _parse_datetime(value)
            if parsed is not None:
                result.add(parsed.date().isoformat())
    return result


def _rows_by_date(frame: pl.DataFrame, column: str) -> dict[str, dict[str, Any]]:
    if frame.is_empty() or column not in frame.columns:
        return {}
    return {str(row[column]): row for row in frame.to_dicts() if row.get(column)}


def _source_hashes(frame: pl.DataFrame) -> set[str]:
    if frame.is_empty() or "source_file_hash" not in frame.columns:
        return set()
    values = frame.get_column("source_file_hash").to_list()
    hashes: set[str] = set()
    for value in values:
        if not value:
            continue
        hashes.update(part for part in str(value).split("|") if part)
    return hashes


def _date_range(frame: pl.DataFrame, *, fallback_path: Path | None = None) -> tuple[str | None, str | None]:
    dates = []
    for column in ("trade_date", "date", "timestamp", "datetime", "asof_timestamp"):
        if column not in frame.columns:
            continue
        for value in frame.get_column(column).to_list():
            parsed = _parse_datetime(value)
            if parsed is not None:
                dates.append(parsed.date())
            elif isinstance(value, str) and re.match(r"20\d{2}-\d{2}-\d{2}", value):
                dates.append(date.fromisoformat(value[:10]))
    if not dates and fallback_path is not None:
        parsed = _date_from_text(fallback_path.as_posix())
        if parsed is not None:
            dates.append(parsed)
    return (min(dates).isoformat(), max(dates).isoformat()) if dates else (None, None)


def _dates_between(start: str | None, end: str | None) -> set[str]:
    if not start:
        return set()
    if not end or end == start:
        return {start}
    return {start, end}


def _coverage_text(frame: pl.DataFrame) -> str:
    dates = sorted(_trade_dates(frame))
    if not dates:
        return "none"
    return f"{dates[0]} to {dates[-1]} ({len(dates)} dates)"


def _granularity(frame: pl.DataFrame) -> str:
    if frame.is_empty():
        return "none"
    if frame.height <= 1:
        return "single_snapshot"
    if "timestamp" not in frame.columns:
        return "date_only"
    per_date = frame.group_by("trade_date").len() if "trade_date" in frame.columns else pl.DataFrame()
    max_rows = _max(per_date, "len") if not per_date.is_empty() else frame.height
    if max_rows >= 24:
        return "intraday"
    if max_rows > 1:
        return "multi_snapshot_daily"
    return "daily"


def _basis_root_cause(reason: str) -> str:
    return {
        "basis_available": "basis_join_ok",
        "missing_xau_spot_price": "missing_spot",
        "missing_gc_futures_price": "missing_futures",
        "importer_failure_or_stale_basis_output": "spot_and_futures_exist_but_basis_missing",
    }.get(reason, "unknown")


def _redacted_file_name(path: Path) -> str:
    suffix = path.suffix.lower() or ".file"
    stem = re.sub(r"[^A-Za-z0-9_.-]", "_", path.name)[:80]
    return f"{stem}|{hash_source_id(str(path.resolve()) if path.exists() else str(path))[:8]}{suffix}"


def _normalize_name(value: str) -> str:
    text = re.sub(r"(?<!^)(?=[A-Z])", "_", str(value).strip())
    return text.lower().replace(" ", "_").replace("-", "_")


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        parsed_date = _date_from_text(text)
        return datetime(parsed_date.year, parsed_date.month, parsed_date.day, tzinfo=UTC) if parsed_date else None


def _date_from_text(text: str) -> date | None:
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


def _max(frame: pl.DataFrame, column: str) -> float:
    if frame.is_empty() or column not in frame.columns:
        return 0.0
    values = [_float(value) for value in frame.get_column(column).to_list()]
    clean = [value for value in values if value is not None]
    return max(clean) if clean else 0.0


def _min(frame: pl.DataFrame, column: str) -> float:
    if frame.is_empty() or column not in frame.columns:
        return 0.0
    values = [_float(value) for value in frame.get_column(column).to_list()]
    clean = [value for value in values if value is not None]
    return min(clean) if clean else 0.0


def _abs_max(frame: pl.DataFrame, column: str) -> float:
    if frame.is_empty() or column not in frame.columns:
        return 0.0
    values = [_float(value) for value in frame.get_column(column).to_list()]
    clean = [abs(value) for value in values if value is not None]
    return max(clean) if clean else 0.0


def _any_true(frame: pl.DataFrame, column: str) -> bool:
    return _true_count(frame, column) > 0


def _true_count(frame: pl.DataFrame, column: str) -> int:
    if frame.is_empty() or column not in frame.columns:
        return 0
    return sum(1 for value in frame.get_column(column).to_list() if bool(value))


def _true_rate(frame: pl.DataFrame, column: str) -> float | None:
    if frame.is_empty() or column not in frame.columns:
        return None
    values = [value for value in frame.get_column(column).to_list() if value is not None]
    return sum(1 for value in values if bool(value)) / len(values) if values else None


def _safe_ratio(numerator: int | float, denominator: int | float) -> float | None:
    return float(numerator) / float(denominator) if denominator else None


def _unique_count(frame: pl.DataFrame, column: str) -> int:
    if frame.is_empty() or column not in frame.columns:
        return 0
    return len(set(frame.get_column(column).to_list()))


def _signal_count(frame: pl.DataFrame, token: str) -> int:
    if frame.is_empty() or "signal" not in frame.columns:
        return 0
    return frame.filter(pl.col("signal").cast(pl.String).str.contains(token, literal=True)).height


def _filter_text(frame: pl.DataFrame, column: str, token: str) -> pl.DataFrame:
    if frame.is_empty() or column not in frame.columns:
        return pl.DataFrame()
    return frame.filter(pl.col(column).cast(pl.String).str.contains(token, literal=True))


def _has_expiry_dte(frame: pl.DataFrame) -> bool:
    if frame.is_empty():
        return False
    has_expiry = "expiry" in frame.columns and any(bool(value) for value in frame.get_column("expiry").to_list())
    has_dte = "dte" in frame.columns and any(value is not None for value in frame.get_column("dte").to_list())
    return has_expiry and has_dte


def _frame(rows: list[dict[str, Any]], schema: dict[str, Any]) -> pl.DataFrame:
    if not rows:
        return pl.DataFrame(schema=schema)
    frame = pl.DataFrame(rows, infer_schema_length=None)
    for column, dtype in schema.items():
        if column not in frame.columns:
            frame = frame.with_columns(pl.lit(None).cast(dtype).alias(column))
    return frame.select(list(schema))


def _frame_markdown(frame: pl.DataFrame, *, limit: int = 40) -> str:
    if frame.is_empty():
        return "_No rows._"
    columns = frame.columns
    rows = ["| " + " | ".join(columns) + " |", "| " + " | ".join("---" for _ in columns) + " |"]
    for raw in frame.head(limit).to_dicts():
        rows.append("| " + " | ".join(_markdown_cell(raw.get(column, "")) for column in columns) + " |")
    return "\n".join(rows)


def _markdown_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _svg(title: str, body: str) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="300" viewBox="0 0 900 300">'
        '<rect width="900" height="300" fill="#ffffff" />'
        f'<text x="30" y="30" font-size="18" font-family="Arial">{html.escape(title)}</text>'
        f"{body}</svg>"
    )


def _flag_columns() -> tuple[str, ...]:
    return (
        "has_xau_spot_price",
        "has_gc_futures_price",
        "has_basis",
        "has_option_oi_by_strike",
        "has_option_oi_change",
        "has_option_volume",
        "has_option_iv",
        "has_option_settlement",
        "has_expiry_dte",
        "has_macro_event_flag",
    )


def _date_usability_input_schema() -> dict[str, Any]:
    schema = {column: pl.Boolean for column in _flag_columns()}
    return {
        "trade_date": pl.String,
        **schema,
        "complete_validation_grade": pl.Boolean,
        "missing_components": pl.String,
        "strict_validation_grade": pl.String,
        "pilot_usability_grade": pl.String,
        "validation_grade": pl.String,
    }


def _date_usability_schema() -> dict[str, Any]:
    schema = {column: pl.Boolean for column in _flag_columns()}
    return {
        "trade_date": pl.String,
        "current_validation_grade": pl.String,
        "strict_validation_grade": pl.String,
        "pilot_usability_grade": pl.String,
        "complete_validation_grade": pl.Boolean,
        **schema,
        "missing_components": pl.String,
        "can_use_for_full_validation": pl.Boolean,
        "can_use_for_cme_oi_pilot": pl.Boolean,
        "can_use_for_cme_iv_pilot": pl.Boolean,
        "can_use_for_price_only_pilot": pl.Boolean,
        "can_use_for_guru_logic_alignment": pl.Boolean,
        "reason_plain_english": pl.String,
        "next_fix_needed": pl.String,
    }


def _iv_audit_schema() -> dict[str, Any]:
    return {
        "file_hash": pl.String,
        "redacted_file_name": pl.String,
        "detected_columns": pl.String,
        "likely_iv_column": pl.String,
        "likely_iv_unit": pl.String,
        "rows_count": pl.Int64,
        "date_start": pl.String,
        "date_end": pl.String,
        "currently_used_as_option_iv": pl.Boolean,
        "mapping_fix_needed": pl.Boolean,
        "recommended_canonical_mapping": pl.String,
    }


def _spot_basis_schema() -> dict[str, Any]:
    return {
        "trade_date": pl.String,
        "xau_spot_files_exist": pl.Boolean,
        "xau_spot_file_count": pl.Int64,
        "redacted_spot_files": pl.String,
        "spot_date_coverage": pl.String,
        "futures_date_coverage": pl.String,
        "basis_date_coverage": pl.String,
        "spot_rows": pl.Int64,
        "futures_rows": pl.Int64,
        "basis_rows": pl.Int64,
        "timestamp_granularity": pl.String,
        "joins_to_cme_futures_dates": pl.Boolean,
        "basis_can_be_calculated_from_existing": pl.Boolean,
        "basis_missing_reason": pl.String,
        "likely_root_cause": pl.String,
    }


def _one_week_schema() -> dict[str, Any]:
    return {
        "trade_date": pl.String,
        "pilot_grade": pl.String,
        "top_wall_above": pl.Float64,
        "top_wall_below": pl.Float64,
        "top_wall_score": pl.Float64,
        "oi_change_freshness_available": pl.Boolean,
        "option_volume_available": pl.Boolean,
        "iv_available": pl.Boolean,
        "basis_available": pl.Boolean,
        "spot_available": pl.Boolean,
        "price_reaction_available": pl.Boolean,
        "guru_context_available": pl.Boolean,
        "expected_move": pl.Float64,
        "wall_level_basis": pl.String,
        "pilot_observation": pl.String,
        "confidence": pl.String,
    }


def _ohlc_guru_schema() -> dict[str, Any]:
    return {
        "logic_bucket": pl.String,
        "event_count": pl.Int64,
        "signal_count": pl.Int64,
        "avoided_trade_proxy": pl.Int64,
        "chop_rate": pl.Float64,
        "breakout_followthrough_rate": pl.Float64,
        "rejection_followthrough_rate": pl.Float64,
        "false_block_rate": pl.Float64,
        "sample_size_warning": pl.Boolean,
        "validation_status": pl.String,
    }


def _fetch_audit_schema() -> dict[str, Any]:
    return {
        "script_name": pl.String,
        "current_collected_sources": pl.String,
        "missing_sources": pl.String,
        "can_fetch_automatically": pl.Boolean,
        "requires_manual_export": pl.Boolean,
        "auth_or_login_needed": pl.Boolean,
        "recommended_script_change": pl.String,
    }


def _option_oi_schema() -> dict[str, Any]:
    return {"trade_date": pl.String, "expiry": pl.String, "dte": pl.Float64, "strike": pl.Float64, "total_oi": pl.Float64}


def _option_iv_schema() -> dict[str, Any]:
    return {"trade_date": pl.String, "expiry": pl.String, "dte": pl.Float64, "strike": pl.Float64, "implied_vol": pl.Float64}


def _futures_schema() -> dict[str, Any]:
    return {"timestamp": pl.Datetime(time_zone="UTC"), "trade_date": pl.String, "close": pl.Float64, "settle": pl.Float64}


def _spot_schema() -> dict[str, Any]:
    return {"timestamp": pl.Datetime(time_zone="UTC"), "trade_date": pl.String, "close": pl.Float64}


def _basis_schema() -> dict[str, Any]:
    return {"trade_date": pl.String, "basis": pl.Float64}


def _event_schema() -> dict[str, Any]:
    return {"trade_date": pl.String, "event_name": pl.String}
