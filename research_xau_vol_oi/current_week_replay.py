"""Current-week CME/guru replay and XAU spot/basis backfill diagnostics.

The layer is local research tooling only. It reads generated pipeline outputs
and user-provided local OHLC files, writes preview artifacts, and keeps
canonical CME files untouched.
"""

from __future__ import annotations

import html
import os
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Iterable

import polars as pl

from research_xau_vol_oi.cme_history_importer import load_supported_table
from research_xau_vol_oi.data_loader import load_table
from research_xau_vol_oi.data_recovery_audit import hash_source_id


DEFAULT_SPOT_DATA_ROOTS = (
    Path("data"),
    Path("data/xau"),
    Path("data/ohlc"),
    Path("data/raw"),
    Path("data/vendor"),
    Path("outputs"),
)
SUPPORTED_SPOT_EXTENSIONS = {".csv", ".parquet", ".xlsx", ".xls", ".json", ".jsonl", ".txt", ".tsv"}
EXCLUDED_DIR_NAMES = {".git", ".venv", "venv", "node_modules", ".next", "__pycache__", ".pytest_cache"}
MAX_SPOT_AUDIT_READ_BYTES = 20_000_000
PILOT_DATES = {
    "2026-05-14",
    "2026-05-15",
    "2026-05-16",
    "2026-05-18",
    "2026-05-19",
    "2026-05-21",
    "2026-05-23",
}
STRICT_FULL_CME_DATES = {"2026-04-30", "2026-05-13"}
FORBIDDEN_REPORT_PHRASES = ("profitable", "safe to trade", "live ready")
GENERATED_REPLAY_OUTPUT_NAMES = {
    "spot_basis_backfill_audit.csv",
    "spot_basis_backfill_report.md",
    "xau_spot_backfilled.parquet",
    "xau_basis_backfilled.parquet",
    "spot_basis_join_preview.csv",
    "current_week_cme_guru_replay.csv",
    "current_week_cme_guru_replay.md",
    "current_week_guru_filter_replay.csv",
    "current_week_guru_filter_replay.md",
    "cme_validation_grade_days_after_backfill.csv",
    "cme_validation_upgrade_report.md",
    "fetch_tool_next_changes.md",
}


@dataclass(frozen=True)
class CurrentWeekReplayResult:
    """Frames and final recommendation from the current-week replay layer."""

    spot_audit: pl.DataFrame
    spot_backfilled: pl.DataFrame
    basis_backfilled: pl.DataFrame
    join_preview: pl.DataFrame
    replay: pl.DataFrame
    guru_filter_replay: pl.DataFrame
    validation_upgrade: pl.DataFrame
    fetch_tool_next_changes: str
    final_recommendation: str


def run_current_week_replay_layer(
    *,
    output_dir: str | Path = "outputs",
    spot_roots: Iterable[str | Path] | None = None,
    join_tolerance_minutes: int = 1440,
    validation_day_threshold: int = 20,
) -> CurrentWeekReplayResult:
    """Run the spot/basis audit, backfill previews, and current-week replays."""

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    charts_dir = output_root / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    frames = load_current_week_inputs(output_root)
    cme_dates = _cme_dates_for_audit(frames)
    roots = resolve_spot_data_roots(spot_roots)

    spot_audit, detected_spot = detect_spot_ohlc_files(roots, cme_dates=cme_dates)
    spot_backfilled, basis_backfilled, join_preview = build_spot_basis_backfill(
        futures=frames["futures"],
        detected_spot=detected_spot,
        join_tolerance_minutes=join_tolerance_minutes,
    )
    replay = build_current_week_cme_guru_replay(
        frames=frames,
        backfilled_basis=basis_backfilled,
        backfilled_spot=spot_backfilled,
    )
    guru_filter = build_guru_filter_replay(frames=frames, replay_dates=_trade_dates(replay))
    validation_upgrade = build_validation_upgrade_report(
        date_usability=frames["date_usability"],
        backfilled_basis=basis_backfilled,
        validation_day_threshold=validation_day_threshold,
    )
    fetch_changes = fetch_tool_next_changes_markdown(
        frames=frames,
        spot_audit=spot_audit,
        basis_backfilled=basis_backfilled,
    )
    recommendation = choose_current_week_recommendation(
        spot_audit=spot_audit,
        basis_backfilled=basis_backfilled,
        replay=replay,
        guru_filter=guru_filter,
        validation_upgrade=validation_upgrade,
    )

    spot_audit.write_csv(output_root / "spot_basis_backfill_audit.csv")
    (output_root / "spot_basis_backfill_report.md").write_text(
        spot_basis_backfill_report_markdown(spot_audit, basis_backfilled),
        encoding="utf-8",
    )
    spot_backfilled.write_parquet(output_root / "xau_spot_backfilled.parquet")
    basis_backfilled.write_parquet(output_root / "xau_basis_backfilled.parquet")
    join_preview.write_csv(output_root / "spot_basis_join_preview.csv")
    replay.write_csv(output_root / "current_week_cme_guru_replay.csv")
    (output_root / "current_week_cme_guru_replay.md").write_text(
        current_week_cme_guru_replay_markdown(replay, recommendation),
        encoding="utf-8",
    )
    guru_filter.write_csv(output_root / "current_week_guru_filter_replay.csv")
    (output_root / "current_week_guru_filter_replay.md").write_text(
        guru_filter_replay_markdown(guru_filter),
        encoding="utf-8",
    )
    validation_upgrade.write_csv(output_root / "cme_validation_grade_days_after_backfill.csv")
    (output_root / "cme_validation_upgrade_report.md").write_text(
        validation_upgrade_markdown(validation_upgrade, validation_day_threshold),
        encoding="utf-8",
    )
    (output_root / "fetch_tool_next_changes.md").write_text(fetch_changes, encoding="utf-8")
    write_wall_replay_svg(charts_dir / "current_week_wall_replay.svg", replay)
    write_basis_replay_svg(charts_dir / "current_week_basis_replay.svg", replay)
    write_guru_filter_overlay_svg(charts_dir / "current_week_guru_filter_overlay.svg", guru_filter)
    append_research_report_sections(output_root / "research_report.md", replay, basis_backfilled, guru_filter, validation_upgrade, recommendation)

    return CurrentWeekReplayResult(
        spot_audit=spot_audit,
        spot_backfilled=spot_backfilled,
        basis_backfilled=basis_backfilled,
        join_preview=join_preview,
        replay=replay,
        guru_filter_replay=guru_filter,
        validation_upgrade=validation_upgrade,
        fetch_tool_next_changes=fetch_changes,
        final_recommendation=recommendation,
    )


def load_current_week_inputs(output_root: Path) -> dict[str, pl.DataFrame]:
    """Load optional input artifacts with empty-frame fallbacks."""

    dukascopy_spot = _compact_spot_frame(
        _load_optional(output_root / "cme_canonical_xau_spot_price_from_dukascopy.parquet")
    )
    canonical_spot = _compact_spot_frame(
        _load_optional(output_root / "cme_canonical_xau_spot_price.parquet")
    )
    return {
        "date_usability": _load_optional(output_root / "current_cme_date_usability.csv"),
        "one_week": _load_optional(output_root / "one_week_cme_pilot_summary.csv"),
        "ohlc_guru": _load_optional(output_root / "ohlc_guru_price_only_pilot.csv"),
        "option_oi": _load_optional(output_root / "cme_canonical_option_oi_by_strike.parquet"),
        "option_iv": _load_optional(output_root / "cme_canonical_option_iv_by_strike.parquet"),
        "futures": _load_optional(output_root / "cme_canonical_futures_price.parquet"),
        "spot": dukascopy_spot if not dukascopy_spot.is_empty() else canonical_spot,
        "basis": _load_optional(output_root / "cme_canonical_basis.parquet"),
        "validation_dataset": _load_optional(output_root / "xau_vol_oi_validation_dataset.parquet"),
        "guru_kb": _load_optional(output_root / "guru_logic_knowledge_base.csv"),
        "guru_priority": _load_optional(output_root / "guru_logic_priority_rank.csv"),
        "signal_events": _load_optional(output_root / "signal_events.csv"),
        "backtest_summary": _load_optional(output_root / "backtest_summary.csv"),
    }


def resolve_spot_data_roots(spot_roots: Iterable[str | Path] | None = None) -> tuple[Path, ...]:
    """Return configured local roots without adding user-specific hardcoded paths."""

    roots = [Path(root) for root in (spot_roots or DEFAULT_SPOT_DATA_ROOTS)]
    env_value = os.getenv("XAU_SPOT_DATA_ROOTS")
    if env_value:
        roots.extend(Path(item.strip()) for item in env_value.split(os.pathsep) if item.strip())
    deduped: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = root.as_posix().lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(root)
    return tuple(deduped)


def detect_spot_ohlc_files(
    roots: Iterable[str | Path],
    *,
    cme_dates: set[str],
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Find local files that look like XAU/USD or gold spot OHLC data."""

    audit_rows: list[dict[str, Any]] = []
    spot_frames: list[pl.DataFrame] = []
    for path in _candidate_paths(roots):
        if _is_large_spot_artifact(path):
            continue
        try:
            frame = load_supported_table(path)
        except Exception:
            continue
        detection = _detect_spot_frame(path, frame)
        if not detection["is_spot_candidate"]:
            continue
        normalized = _normalize_spot_frame(frame, path, detection)
        if not normalized.is_empty():
            spot_frames.append(normalized)
        dates = _trade_dates(normalized)
        matching = sorted(dates & cme_dates)
        missing = sorted(cme_dates - dates)
        audit_rows.append(
            {
                "redacted_path": _redacted_path(path),
                "source_hash": _source_hash(path),
                "detected_symbol": detection["detected_symbol"],
                "rows_count": normalized.height,
                "date_start": min(dates) if dates else "",
                "date_end": max(dates) if dates else "",
                "timestamp_granularity": _timestamp_granularity(normalized),
                "can_join_to_cme_dates": bool(matching),
                "matching_cme_dates": "|".join(matching),
                "missing_cme_dates": "|".join(missing),
                "recommended_mapping": _recommended_spot_mapping(detection, matching),
            }
        )
    detected_spot = _concat_or_empty(spot_frames, _spot_backfill_schema())
    return _frame(audit_rows, _spot_audit_schema()), detected_spot


def build_spot_basis_backfill(
    *,
    futures: pl.DataFrame,
    detected_spot: pl.DataFrame,
    join_tolerance_minutes: int,
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """Build preview spot and basis outputs without overwriting canonical files."""

    spot = _select_spot_rows(detected_spot)
    futures_norm = _normalize_futures_frame(futures)
    if futures_norm.is_empty() or spot.is_empty():
        return spot, _empty_basis_backfill(), _empty_join_preview()

    spot_by_date: dict[str, list[dict[str, Any]]] = {}
    for row in spot.to_dicts():
        spot_by_date.setdefault(str(row["trade_date"]), []).append(row)

    basis_rows: list[dict[str, Any]] = []
    for future in futures_norm.to_dicts():
        trade_date = str(future.get("trade_date") or "")
        candidates = spot_by_date.get(trade_date, [])
        if not candidates:
            continue
        future_ts = _parse_datetime(future.get("timestamp"))
        futures_price = _float(future.get("futures_price"))
        plausible = [
            row
            for row in candidates
            if _prices_are_plausible(futures_price, _float(row.get("close")))
        ]
        choices = plausible or candidates
        closest = min(choices, key=lambda row: abs((_parse_datetime(row.get("timestamp")) - future_ts).total_seconds()))
        spot_ts = _parse_datetime(closest.get("timestamp"))
        delta_minutes = abs((future_ts - spot_ts).total_seconds()) / 60.0
        spot_price = _float(closest.get("close"))
        if futures_price is None or spot_price is None:
            continue
        spot_granularity = str(closest.get("timestamp_granularity") or "")
        quality = _basis_quality(
            spot_granularity,
            delta_minutes,
            join_tolerance_minutes,
            futures_price=futures_price,
            spot_price=spot_price,
        )
        source_hashes = f"{future.get('source_file_hash') or ''}|{closest.get('source_hash') or ''}".strip("|")
        basis_rows.append(
            {
                "trade_date": trade_date,
                "timestamp": future_ts,
                "futures_price": futures_price,
                "spot_price": spot_price,
                "basis": futures_price - spot_price,
                "basis_quality": quality,
                "join_tolerance": f"{join_tolerance_minutes}m",
                "source_hashes": source_hashes,
                "notes": _basis_note(quality),
            }
        )
    basis = _frame(basis_rows, _basis_backfill_schema()).sort(["trade_date", "timestamp"])
    return spot, basis, basis


def build_current_week_cme_guru_replay(
    *,
    frames: dict[str, pl.DataFrame],
    backfilled_basis: pl.DataFrame,
    backfilled_spot: pl.DataFrame,
) -> pl.DataFrame:
    """Create one replay row per current-week/full-CME pilot date."""

    dates = _replay_dates(frames)
    date_rows = _rows_by_date(frames["date_usability"], "trade_date")
    basis_frame = _prefer_backfilled(frames["basis"], backfilled_basis)
    spot_frame = _prefer_backfilled_spot(frames["spot"], backfilled_spot)
    event_dates = _event_dates(frames["signal_events"])
    guru_logic = _active_guru_logic(frames["guru_kb"], frames["guru_priority"])

    rows: list[dict[str, Any]] = []
    for trade_date in dates:
        flags = date_rows.get(trade_date, {})
        oi_rows = _date_filter(frames["option_oi"], trade_date)
        iv_rows = _date_filter(frames["option_iv"], trade_date)
        futures_rows = _date_filter(frames["futures"], trade_date)
        spot_rows = _date_filter(spot_frame, trade_date)
        basis_rows = _date_filter(basis_frame, trade_date)
        validation_rows = _date_filter(frames["validation_dataset"], trade_date)
        spot_row = _last_row(spot_rows)
        futures_row = _last_row(futures_rows)
        basis_row = _last_valid_basis_row(basis_rows)
        spot_price = (
            _float(spot_row.get("close"))
            or _float(spot_row.get("spot_price"))
            or _float(basis_row.get("spot_price"))
        )
        futures_price = _float(futures_row.get("settle")) or _float(futures_row.get("close"))
        basis = _float(basis_row.get("basis"))
        basis_is_usable = _basis_row_is_usable(basis_row)
        reference_price = spot_price if spot_price is not None else futures_price
        walls = _top_wall_rows(oi_rows, basis=basis if basis_is_usable else None)
        nearest = _nearest_wall_pair(walls, reference_price)
        reaction = _reaction_flags(spot_rows if not spot_rows.is_empty() else futures_rows, nearest, validation_rows)
        date_events = frames["signal_events"].filter(
            pl.col("event_timestamp").cast(pl.String).str.slice(0, 10) == trade_date
        ) if not frames["signal_events"].is_empty() and "event_timestamp" in frames["signal_events"].columns else pl.DataFrame()
        no_trade = _has_no_trade(date_events) or _logic_type_exists(frames["guru_kb"], "NO_TRADE_FILTER")
        market_map = not oi_rows.is_empty() or _logic_type_exists(frames["guru_kb"], "OI_WALL_ZONE")
        row = {
            "trade_date": trade_date,
            "pilot_usability_grade": str(flags.get("pilot_usability_grade") or _one_week_value(frames["one_week"], trade_date, "pilot_grade") or "UNKNOWN"),
            "strict_validation_grade": str(flags.get("strict_validation_grade") or flags.get("validation_grade") or "UNUSABLE"),
            "spot_available": spot_price is not None,
            "basis_available": basis_is_usable,
            "basis_quality": str(basis_row.get("basis_quality") or "MISSING"),
            "iv_available": not iv_rows.is_empty() or bool(flags.get("has_option_iv")),
            "oi_available": not oi_rows.is_empty() or bool(flags.get("has_option_oi_by_strike")),
            "oi_change_available": _column_has_value(oi_rows, "total_oi_change") or bool(flags.get("has_option_oi_change")),
            "option_volume_available": _column_has_value(oi_rows, "total_volume") or bool(flags.get("has_option_volume")),
            "futures_available": futures_price is not None or bool(flags.get("has_gc_futures_price")),
            "guru_context_available": trade_date in event_dates or bool(guru_logic),
            "top_oi_wall_1": _wall_level(walls, 0),
            "top_oi_wall_2": _wall_level(walls, 1),
            "top_oi_wall_3": _wall_level(walls, 2),
            "wall_type": "SPOT_EQUIVALENT_LEVEL" if basis_is_usable else "FUTURES_STRIKE_LEVEL",
            "wall_score": nearest.get("score"),
            "oi_change_near_wall": nearest.get("oi_change"),
            "volume_near_wall": nearest.get("volume"),
            "iv_near_wall": _iv_near_wall(iv_rows, nearest.get("strike")),
            "nearest_wall_above_price": nearest.get("above"),
            "nearest_wall_below_price": nearest.get("below"),
            "active_guru_logic": guru_logic,
            "no_trade_filter_active": no_trade,
            "market_map_logic_active": market_map,
            "rejection_logic_active": _logic_type_exists(frames["guru_kb"], "REJECTION_LOGIC"),
            "acceptance_logic_active": _logic_type_exists(frames["guru_kb"], "ACCEPTANCE_LOGIC"),
            "squeeze_or_pin_logic_active": _logic_name_contains(frames["guru_kb"], ("squeeze", "pin")),
            **reaction,
        }
        row.update(_pilot_observation_fields(row))
        rows.append(row)
    return _frame(rows, _replay_schema()).sort("trade_date")


def build_guru_filter_replay(
    *,
    frames: dict[str, pl.DataFrame],
    replay_dates: set[str],
) -> pl.DataFrame:
    """Replay current-week no-trade filter rows from signal events."""

    events = frames["signal_events"]
    if events.is_empty() or "event_timestamp" not in events.columns:
        return _frame([], _guru_filter_schema())

    rows: list[dict[str, Any]] = []
    for event in events.to_dicts():
        timestamp = str(event.get("event_timestamp") or "")
        trade_date = timestamp[:10]
        if replay_dates and trade_date not in replay_dates:
            continue
        signal = str(event.get("signal") or "")
        reason = str(event.get("reason") or "")
        blocks = signal.startswith("NO_TRADE") or "no_trade" in reason.lower() or "mapping_block" in reason.lower()
        evidence = "PRICE_ONLY_PROXY" if blocks else "MISSING_OUTCOME"
        rows.append(
            {
                "timestamp": timestamp,
                "trade_date": trade_date,
                "base_signal": signal,
                "guru_filter_active": blocks,
                "no_trade_reason": reason if blocks else "",
                "would_block_trade": blocks,
                "blocked_trade_outcome_if_known": "unknown",
                "avoided_loss_proxy": 1.0 if blocks and "quality" in reason.lower() else None,
                "opportunity_cost_proxy": None,
                "net_filter_value_proxy": None,
                "evidence_status": evidence,
            }
        )
    return _frame(rows, _guru_filter_schema()).sort(["trade_date", "timestamp"])


def build_validation_upgrade_report(
    *,
    date_usability: pl.DataFrame,
    backfilled_basis: pl.DataFrame,
    validation_day_threshold: int,
) -> pl.DataFrame:
    """Compare strict validation days before and after spot/basis backfill previews."""

    if date_usability.is_empty():
        return _frame([], _validation_upgrade_schema())
    basis_dates = _trade_dates(_usable_basis_frame(backfilled_basis))
    before_full = _true_count(date_usability, "complete_validation_grade")
    rows = []
    after_full_count = 0
    for raw in date_usability.to_dicts():
        flags = {key: bool(raw.get(key)) for key in _flag_columns()}
        trade_date = str(raw.get("trade_date") or "")
        if trade_date in basis_dates:
            flags["has_xau_spot_price"] = True
            flags["has_basis"] = True
        after_grade = _validation_grade(flags)
        after_full = after_grade == "FULL_CME_VOL_OI"
        after_full_count += int(after_full)
        before_full_for_date = bool(raw.get("complete_validation_grade"))
        rows.append(
            {
                "trade_date": trade_date,
                "before_strict_validation_grade": str(raw.get("strict_validation_grade") or raw.get("validation_grade") or "UNUSABLE"),
                "after_strict_validation_grade": after_grade,
                "before_complete_validation_days": before_full,
                "after_complete_validation_days": 0,
                "day_upgraded": after_full and not before_full_for_date,
                "still_missing_components_by_date": "|".join(_missing_components(flags)),
                "next_missing_component": _next_missing_component(flags),
                "money_readiness_changed": False,
                "validation_threshold": validation_day_threshold,
            }
        )
    for row in rows:
        row["after_complete_validation_days"] = after_full_count
    return _frame(rows, _validation_upgrade_schema()).sort("trade_date")


def choose_current_week_recommendation(
    *,
    spot_audit: pl.DataFrame,
    basis_backfilled: pl.DataFrame,
    replay: pl.DataFrame,
    guru_filter: pl.DataFrame,
    validation_upgrade: pl.DataFrame,
) -> str:
    """Choose an allowed final recommendation without claiming validation."""

    if not validation_upgrade.is_empty() and _true_count(validation_upgrade, "day_upgraded") > 0:
        return "SPOT_BASIS_BACKFILL_SUCCESS"
    if not replay.is_empty() and _any_true(replay, "oi_available"):
        return "CURRENT_WEEK_REPLAY_READY"
    if not basis_backfilled.is_empty():
        return "SPOT_BASIS_BACKFILL_SUCCESS"
    if spot_audit.is_empty():
        return "NEEDS_MANUAL_SPOT_DATA"
    if not guru_filter.is_empty():
        return "PRICE_ONLY_GURU_REPLAY_READY"
    return "ADD_SPOT_BASIS_FIRST"


def current_week_replay_report_lines(result: CurrentWeekReplayResult | None) -> list[str]:
    """Return Markdown lines for embedding in the main research report."""

    if result is None:
        return ["Current-week replay layer was not run."]
    upgraded = _true_count(result.validation_upgrade, "day_upgraded")
    return [
        "## Current-Week CME/Guru Replay",
        "",
        f"- Final recommendation: `{result.final_recommendation}`",
        f"- Replay dates: {result.replay.height}",
        f"- Spot/OHLC candidate files found: {result.spot_audit.height}",
        f"- Basis preview rows created: {result.basis_backfilled.height}",
        "- This is pilot analysis and data-debugging only, not a validated edge.",
        "",
        "## Spot/Basis Backfill Audit",
        "",
        _frame_markdown(
            result.spot_audit.select(
                [
                    "redacted_path",
                    "detected_symbol",
                    "rows_count",
                    "date_start",
                    "date_end",
                    "timestamp_granularity",
                    "can_join_to_cme_dates",
                    "recommended_mapping",
                ]
            )
            if not result.spot_audit.is_empty()
            else result.spot_audit
        ),
        "",
        "## Wall Map Replay",
        "",
        _frame_markdown(
            result.replay.select(
                [
                    "trade_date",
                    "pilot_usability_grade",
                    "wall_type",
                    "top_oi_wall_1",
                    "top_oi_wall_2",
                    "nearest_wall_above_price",
                    "nearest_wall_below_price",
                    "observation_confidence",
                    "next_fix_needed",
                ]
            )
            if not result.replay.is_empty()
            else result.replay
        ),
        "",
        "## Guru Filter Replay",
        "",
        f"- Rows replayed: {result.guru_filter_replay.height}",
        f"- Would-block rows: {_true_count(result.guru_filter_replay, 'would_block_trade')}",
        "- Filter value remains proxy-only until outcome labels are joined.",
        "",
        "## Validation Upgrade After Backfill",
        "",
        f"- Dates upgraded by preview backfill: {upgraded}",
        "- Money-readiness is intentionally unchanged by this layer.",
        "",
        "## What We Can Learn From Current Data",
        "",
        "- Current-week CME OI walls, IV availability, futures price context, and guru no-trade rows can be replayed day by day.",
        "- When basis exists, walls can be shown as spot-equivalent levels; otherwise they remain futures strike levels.",
        "",
        "## What Still Cannot Be Proven",
        "",
        "- The replay cannot prove profitability, predictive power, safety, or live readiness.",
        "- Missing or weak XAU spot joins still block more validation-grade CME days.",
    ]


def spot_basis_backfill_report_markdown(spot_audit: pl.DataFrame, basis: pl.DataFrame) -> str:
    """Render spot/basis backfill diagnostics."""

    lines = [
        "# Spot/Basis Backfill Audit",
        "",
        "Research-only local audit. Canonical CME files are not overwritten.",
        "",
        f"- Spot/OHLC candidates found: {spot_audit.height}",
        f"- Backfilled basis preview rows: {basis.height}",
        "",
        _frame_markdown(spot_audit),
        "",
        "## Basis Preview",
        "",
        _frame_markdown(basis),
        "",
        "No profitability, prediction, safety, or live-readiness claim is made.",
    ]
    return _safe_report("\n".join(lines))


def current_week_cme_guru_replay_markdown(replay: pl.DataFrame, recommendation: str) -> str:
    """Render the day-by-day CME/guru replay report."""

    lines = [
        "# Current-Week CME/Guru Replay",
        "",
        f"- Final recommendation: `{recommendation}`",
        "- Status: pilot replay, not a validated edge.",
        "",
        _frame_markdown(replay),
        "",
        "## Interpretation Guardrails",
        "",
        "- FUTURES_STRIKE_LEVEL means XAU spot/basis is missing or not joined for that date.",
        "- SPOT_EQUIVALENT_LEVEL means a basis preview or canonical basis row was available.",
        "- Price reactions are observations only.",
    ]
    return _safe_report("\n".join(lines))


def guru_filter_replay_markdown(frame: pl.DataFrame) -> str:
    """Render the no-trade filter replay report."""

    lines = [
        "# Current-Week Guru Filter Replay",
        "",
        f"- Event rows: {frame.height}",
        f"- Would-block rows: {_true_count(frame, 'would_block_trade')}",
        "- Evidence status is proxy/debug unless outcome data is joined.",
        "",
        _frame_markdown(frame),
        "",
        "This report says pilot and does not claim a validated edge.",
    ]
    return _safe_report("\n".join(lines))


def validation_upgrade_markdown(frame: pl.DataFrame, threshold: int) -> str:
    """Render validation-grade day comparison."""

    after = _max_int(frame, "after_complete_validation_days")
    lines = [
        "# CME Validation Upgrade After Backfill",
        "",
        f"- Complete validation days after preview backfill: {after}",
        f"- Configured threshold for readiness change: {threshold}",
        "- Money-readiness changed: `false`.",
        "- This layer cannot change final money-readiness by itself.",
        "",
        _frame_markdown(frame),
    ]
    return _safe_report("\n".join(lines))


def fetch_tool_next_changes_markdown(
    *,
    frames: dict[str, pl.DataFrame],
    spot_audit: pl.DataFrame,
    basis_backfilled: pl.DataFrame,
) -> str:
    """Answer the next collection/importer change questions."""

    has_oi = not frames["option_oi"].is_empty()
    has_iv = not frames["option_iv"].is_empty()
    has_futures = not frames["futures"].is_empty()
    has_spot_candidates = not spot_audit.is_empty()
    has_basis_preview = not basis_backfilled.is_empty()
    available_not_mapped = []
    if has_spot_candidates and not has_basis_preview:
        available_not_mapped.append("XAU spot/OHLC candidate files need timestamp/date mapping into basis preview.")
    if has_iv:
        available_not_mapped.append("IV aliases are available in canonical IV output.")
    exact_change = (
        "Add an importer option that maps detected XAU spot OHLC columns to canonical spot rows, "
        "then runs the same nearest-timestamp futures-minus-spot basis preview before validation grading."
    )
    return _safe_report(
        "\n".join(
            [
                "# Fetch Tool Next Changes",
                "",
                "1. Did we actually fetch all usable CME components?",
                f"   - OI: {has_oi}; IV: {has_iv}; futures: {has_futures}; spot/basis remains the main join gap.",
                "2. Which components are available but not mapped correctly?",
                "   - " + (" ".join(available_not_mapped) if available_not_mapped else "No additional local mapping gap was detected by this layer."),
                "3. Which components require manual export or login?",
                "   - CME/QuikStrike option tables that are not already in local exports still require manual export/login boundaries.",
                "4. Which components can be fetched/imported from existing local OHLC?",
                f"   - XAU spot/OHLC candidates: {spot_audit.height}; basis preview available: {has_basis_preview}.",
                "5. What exact script/importer change should be made next?",
                f"   - {exact_change}",
            ]
        )
    )


def append_research_report_sections(
    path: Path,
    replay: pl.DataFrame,
    basis: pl.DataFrame,
    guru_filter: pl.DataFrame,
    validation_upgrade: pl.DataFrame,
    recommendation: str,
) -> None:
    """Append/replace replay sections in an existing generated research report."""

    marker = "\n## Current-Week CME/Guru Replay\n"
    result = CurrentWeekReplayResult(
        spot_audit=pl.DataFrame(),
        spot_backfilled=pl.DataFrame(),
        basis_backfilled=basis,
        join_preview=basis,
        replay=replay,
        guru_filter_replay=guru_filter,
        validation_upgrade=validation_upgrade,
        fetch_tool_next_changes="",
        final_recommendation=recommendation,
    )
    section = "\n".join(current_week_replay_report_lines(result))
    existing = path.read_text(encoding="utf-8") if path.exists() else "# XAU/USD Vol-OI Research Report\n"
    if marker in existing:
        existing = existing.split(marker, 1)[0].rstrip()
    path.write_text(_safe_report(existing.rstrip() + "\n\n" + section + "\n"), encoding="utf-8")


def write_wall_replay_svg(path: Path, replay: pl.DataFrame) -> None:
    """Write a compact wall-level SVG."""

    values = [_float(row.get("top_oi_wall_1")) for row in replay.to_dicts()] if not replay.is_empty() else []
    _write_line_svg(path, title="Current-week wall replay", values=[value for value in values if value is not None])


def write_basis_replay_svg(path: Path, replay: pl.DataFrame) -> None:
    """Write a compact basis-availability SVG."""

    values = [1.0 if row.get("basis_available") else 0.0 for row in replay.to_dicts()] if not replay.is_empty() else []
    _write_bar_svg(path, title="Current-week basis availability", values=values)


def write_guru_filter_overlay_svg(path: Path, frame: pl.DataFrame) -> None:
    """Write a compact no-trade filter overlay SVG."""

    counts: dict[str, int] = {}
    for row in frame.to_dicts() if not frame.is_empty() else []:
        if row.get("would_block_trade"):
            counts[str(row.get("trade_date"))] = counts.get(str(row.get("trade_date")), 0) + 1
    _write_bar_svg(path, title="Current-week guru filter overlay", values=[float(value) for value in counts.values()])


def _load_optional(path: Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    try:
        return pl.read_parquet(path) if path.suffix.lower() == ".parquet" else load_table(path)
    except Exception:
        return pl.DataFrame()


def _candidate_paths(roots: Iterable[str | Path]) -> list[Path]:
    paths: set[Path] = set()
    for root_value in roots:
        root = Path(root_value)
        if not root.exists():
            continue
        if root.is_file():
            if root.name not in GENERATED_REPLAY_OUTPUT_NAMES and root.suffix.lower() in SUPPORTED_SPOT_EXTENSIONS:
                paths.add(root)
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_SPOT_EXTENSIONS:
                continue
            if path.name in GENERATED_REPLAY_OUTPUT_NAMES:
                continue
            if any(part in EXCLUDED_DIR_NAMES for part in path.parts):
                continue
            paths.add(path)
    return sorted(paths, key=lambda item: item.as_posix().lower())


def _detect_spot_frame(path: Path, frame: pl.DataFrame) -> dict[str, Any]:
    columns = frame.columns
    has_timestamp = _find_col(columns, ("timestamp", "datetime", "date", "time")) is not None
    has_ohlc = all(_find_col(columns, aliases) is not None for aliases in _ohlc_aliases())
    symbol_col = _find_col(columns, ("symbol", "ticker", "instrument", "name"), required=False)
    symbol_values = _sample_symbols(frame, symbol_col)
    path_text = path.name.lower()
    symbol_text = " ".join(symbol_values).lower()
    has_symbol_hint = any(token in symbol_text for token in ("xauusd", "xau/usd", "xau usd", "gold spot"))
    has_disallowed_symbol = any(token in symbol_text for token in ("gld", "gc=f", "gc futures", "gold futures"))
    has_path_hint = any(token in path_text for token in ("xau", "gold", "spot"))
    is_futures = "futures" in path_text or "gc=f" in path_text or "gc_futures" in path_text
    is_gld_path = "gld" in path_text
    candidate = (
        has_timestamp
        and has_ohlc
        and not has_disallowed_symbol
        and (has_symbol_hint or (has_path_hint and not is_futures and not is_gld_path))
    )
    detected = symbol_values[0] if symbol_values else ("XAUUSD_OR_GOLD_SPOT_CANDIDATE" if has_path_hint else "UNKNOWN")
    return {
        "is_spot_candidate": candidate,
        "detected_symbol": detected,
        "symbol_col": symbol_col,
        "timestamp_col": _find_col(columns, ("timestamp", "datetime", "date")),
        "time_col": _find_col(columns, ("time",), required=False),
        "open_col": _find_col(columns, ("open", "Open")),
        "high_col": _find_col(columns, ("high", "High")),
        "low_col": _find_col(columns, ("low", "Low")),
        "close_col": _find_col(columns, ("close", "Close", "adj_close", "price", "last")),
    }


def _normalize_spot_frame(frame: pl.DataFrame, path: Path, detection: dict[str, Any]) -> pl.DataFrame:
    rows: list[dict[str, Any]] = []
    source_hash = _source_hash(path)
    for raw in frame.to_dicts():
        timestamp = _parse_timestamp_columns(raw, detection["timestamp_col"], detection.get("time_col"))
        if timestamp is None:
            continue
        close = _float(raw.get(detection["close_col"]))
        open_price = _float(raw.get(detection["open_col"])) or close
        high = _float(raw.get(detection["high_col"])) or close
        low = _float(raw.get(detection["low_col"])) or close
        if close is None or open_price is None or high is None or low is None:
            continue
        if high < low or not low <= close <= high or not low <= open_price <= high:
            continue
        rows.append(
            {
                "timestamp": timestamp,
                "trade_date": timestamp.date().isoformat(),
                "symbol": str(raw.get(detection.get("symbol_col")) or detection["detected_symbol"]),
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "volume": _float(raw.get("volume")),
                "source_hash": source_hash,
                "redacted_path": _redacted_path(path),
                "timestamp_granularity": "",
            }
        )
    result = _frame(rows, _spot_backfill_schema()).sort(["trade_date", "timestamp"])
    granularity = _timestamp_granularity(result)
    return result.with_columns(pl.lit(granularity).alias("timestamp_granularity")) if not result.is_empty() else result


def _select_spot_rows(spot: pl.DataFrame) -> pl.DataFrame:
    if spot.is_empty():
        return spot
    rank = {"INTRADAY": 3, "MULTI_SNAPSHOT_DAILY": 2, "DAILY": 1, "SINGLE_SNAPSHOT": 1}
    rows = []
    for raw in spot.to_dicts():
        item = dict(raw)
        item["_rank"] = rank.get(str(item.get("timestamp_granularity")), 0)
        rows.append(item)
    frame = pl.DataFrame(rows, infer_schema_length=None).sort(["trade_date", "_rank", "timestamp"], descending=[False, True, False])
    return frame.drop("_rank")


def _normalize_futures_frame(frame: pl.DataFrame) -> pl.DataFrame:
    if frame.is_empty():
        return _frame([], _futures_norm_schema())
    rows = []
    for raw in frame.to_dicts():
        timestamp = _parse_datetime(raw.get("timestamp"))
        price = _float(raw.get("settle")) or _float(raw.get("close"))
        if price is None:
            continue
        trade_date = str(raw.get("trade_date") or timestamp.date().isoformat())
        rows.append(
            {
                "timestamp": timestamp,
                "trade_date": trade_date,
                "futures_symbol": str(raw.get("futures_symbol") or "GC"),
                "futures_price": price,
                "high": _float(raw.get("high")),
                "low": _float(raw.get("low")),
                "close": price,
                "source_file_hash": str(raw.get("source_file_hash") or ""),
            }
        )
    return _frame(rows, _futures_norm_schema()).sort(["trade_date", "timestamp"])


def _basis_quality(
    granularity: str,
    delta_minutes: float,
    tolerance_minutes: int,
    *,
    futures_price: float,
    spot_price: float,
) -> str:
    if not _prices_are_plausible(futures_price, spot_price):
        return "LOW_CONFIDENCE"
    if delta_minutes > tolerance_minutes:
        return "LOW_CONFIDENCE"
    if granularity == "INTRADAY":
        return "INTRADAY_JOIN"
    return "DAILY_APPROX"


def _prices_are_plausible(futures_price: float | None, spot_price: float | None) -> bool:
    if futures_price is None or spot_price is None or futures_price <= 0 or spot_price <= 0:
        return False
    return abs(futures_price - spot_price) / futures_price <= 0.20


def _basis_note(quality: str) -> str:
    return {
        "INTRADAY_JOIN": "Nearest timestamp join within tolerance.",
        "DAILY_APPROX": "Daily or single-snapshot OHLC was used as a preview approximation.",
        "LOW_CONFIDENCE": "Nearest timestamp exceeded the configured tolerance.",
    }.get(quality, "Preview basis row.")


def _top_wall_rows(option_oi: pl.DataFrame, *, basis: float | None) -> list[dict[str, Any]]:
    if option_oi.is_empty() or "strike" not in option_oi.columns:
        return []
    rows_by_strike: dict[float, dict[str, float]] = {}
    for row in option_oi.to_dicts():
        strike = _float(row.get("strike"))
        if strike is None:
            continue
        item = rows_by_strike.setdefault(strike, {"strike": strike, "total_oi": 0.0, "oi_change": 0.0, "volume": 0.0})
        item["total_oi"] += _float(row.get("total_oi")) or 0.0
        item["oi_change"] += _float(row.get("total_oi_change")) or 0.0
        item["volume"] += _float(row.get("total_volume")) or 0.0
    max_oi = max((row["total_oi"] for row in rows_by_strike.values()), default=1.0) or 1.0
    walls = []
    for row in rows_by_strike.values():
        level = row["strike"] - basis if basis is not None else row["strike"]
        walls.append({**row, "level": level, "score": row["total_oi"] / max_oi})
    return sorted(walls, key=lambda item: item["total_oi"], reverse=True)


def _nearest_wall_pair(walls: list[dict[str, Any]], price: float | None) -> dict[str, Any]:
    result: dict[str, Any] = {"above": None, "below": None, "score": None, "oi_change": None, "volume": None, "strike": None}
    if not walls:
        return result
    if price is None:
        top = walls[0]
        result.update({"score": top["score"], "oi_change": top["oi_change"], "volume": top["volume"], "strike": top["strike"]})
        return result
    above = [row for row in walls if row["level"] >= price]
    below = [row for row in walls if row["level"] <= price]
    candidates = []
    if above:
        selected = min(above, key=lambda item: abs(item["level"] - price))
        result["above"] = selected["level"]
        candidates.append(selected)
    if below:
        selected = min(below, key=lambda item: abs(item["level"] - price))
        result["below"] = selected["level"]
        candidates.append(selected)
    if candidates:
        selected = max(candidates, key=lambda item: item["score"])
        result.update({"score": selected["score"], "oi_change": selected["oi_change"], "volume": selected["volume"], "strike": selected["strike"]})
    return result


def _iv_near_wall(option_iv: pl.DataFrame, strike: Any) -> float | None:
    target = _float(strike)
    if option_iv.is_empty() or target is None or "strike" not in option_iv.columns:
        return None
    values = []
    for row in option_iv.to_dicts():
        row_strike = _float(row.get("strike"))
        iv = _float(row.get("implied_vol"))
        if row_strike is not None and iv is not None:
            values.append((abs(row_strike - target), iv))
    return min(values)[1] if values else None


def _reaction_flags(price_frame: pl.DataFrame, nearest: dict[str, Any], validation_rows: pl.DataFrame) -> dict[str, str]:
    if price_frame.is_empty():
        unknown = "unknown"
        confidence = "DEBUG_ONLY"
        return {
            "touched_wall": unknown,
            "rejected_wall": unknown,
            "accepted_wall": unknown,
            "broke_range": unknown,
            "stayed_inside_range": unknown,
            "observation_confidence": confidence,
        }
    high = _max_float(price_frame, "high")
    low = _min_float(price_frame, "low")
    close = _float(_last_row(price_frame).get("close")) or _float(_last_row(price_frame).get("settle"))
    above = _float(nearest.get("above"))
    below = _float(nearest.get("below"))
    touched_above = above is not None and high is not None and high >= above
    touched_below = below is not None and low is not None and low <= below
    touched = touched_above or touched_below
    rejected = (touched_above and close is not None and close < above) or (touched_below and close is not None and close > below)
    accepted = (touched_above and close is not None and close >= above) or (touched_below and close is not None and close <= below)
    one_sd_upper = _float(_last_row(validation_rows).get("one_sd_upper"))
    one_sd_lower = _float(_last_row(validation_rows).get("one_sd_lower"))
    if close is not None and one_sd_upper is not None and one_sd_lower is not None:
        broke = close > one_sd_upper or close < one_sd_lower
        stayed = not broke
    else:
        broke = stayed = "unknown"
    confidence = "MEDIUM" if touched else "LOW"
    return {
        "touched_wall": _bool_or_unknown(touched),
        "rejected_wall": _bool_or_unknown(rejected if touched else "unknown"),
        "accepted_wall": _bool_or_unknown(accepted if touched else "unknown"),
        "broke_range": _bool_or_unknown(broke),
        "stayed_inside_range": _bool_or_unknown(stayed),
        "observation_confidence": confidence,
    }


def _pilot_observation_fields(row: dict[str, Any]) -> dict[str, str]:
    missing = []
    if not row["spot_available"]:
        missing.append("XAU spot")
    if not row["basis_available"]:
        missing.append("basis")
    if not row["iv_available"]:
        missing.append("IV")
    if not row["oi_available"]:
        missing.append("OI")
    worked = []
    if row["oi_available"]:
        worked.append("CME OI wall context loaded")
    if row["guru_context_available"]:
        worked.append("guru context available")
    failed = []
    if row["wall_type"] == "FUTURES_STRIKE_LEVEL":
        failed.append("basis-adjusted spot-equivalent mapping unavailable")
    next_fix = "Join XAU spot to GC futures and rebuild basis." if not row["basis_available"] else "Add outcome labels for stronger filter replay."
    return {
        "plain_english_summary": (
            f"{row['trade_date']} can be replayed as pilot context with "
            f"{row['wall_type']} walls."
        ),
        "what_worked": "; ".join(worked) if worked else "No complete replay component loaded.",
        "what_failed": "; ".join(failed) if failed else "No structural failure detected in the replay row.",
        "what_missing": "; ".join(missing) if missing else "No core replay component missing for this date.",
        "next_fix_needed": next_fix,
    }


def _replay_dates(frames: dict[str, pl.DataFrame]) -> list[str]:
    dates = _trade_dates(frames["one_week"])
    if not dates:
        usable = frames["date_usability"]
        if not usable.is_empty():
            for row in usable.to_dicts():
                trade_date = str(row.get("trade_date") or "")
                if trade_date in PILOT_DATES or trade_date in STRICT_FULL_CME_DATES:
                    dates.add(trade_date)
    for source in ("option_oi", "option_iv", "basis", "spot"):
        dates.update(date for date in _trade_dates(frames[source]) if date in PILOT_DATES or date in STRICT_FULL_CME_DATES)
    return sorted(dates)


def _active_guru_logic(guru_kb: pl.DataFrame, priority: pl.DataFrame) -> str:
    if not priority.is_empty() and "logic_name" in priority.columns:
        return "|".join(str(value) for value in priority.get_column("logic_name").head(5).to_list())
    if not guru_kb.is_empty() and "logic_name" in guru_kb.columns:
        return "|".join(str(value) for value in guru_kb.get_column("logic_name").head(5).to_list())
    return ""


def _prefer_backfilled(canonical: pl.DataFrame, backfilled: pl.DataFrame) -> pl.DataFrame:
    if backfilled.is_empty():
        return canonical
    if canonical.is_empty():
        return backfilled
    return pl.concat([canonical, backfilled], how="diagonal_relaxed")


def _prefer_backfilled_spot(canonical: pl.DataFrame, backfilled: pl.DataFrame) -> pl.DataFrame:
    if backfilled.is_empty():
        return canonical
    if canonical.is_empty():
        return backfilled
    return pl.concat([canonical, backfilled], how="diagonal_relaxed")


def _compact_spot_frame(frame: pl.DataFrame, *, max_rows: int = 20_000) -> pl.DataFrame:
    """Reduce large intraday spot frames to date-level OHLC for replay summaries."""

    if frame.is_empty() or frame.height <= max_rows or "trade_date" not in frame.columns:
        return frame
    columns = set(frame.columns)
    aggregations = []
    if "timestamp" in columns:
        aggregations.append(pl.col("timestamp").max().alias("timestamp"))
    for source, op in [
        ("open", "first"),
        ("high", "max"),
        ("low", "min"),
        ("close", "last"),
        ("spot_price", "last"),
    ]:
        if source not in columns:
            continue
        expr = getattr(pl.col(source), op)().alias(source)
        aggregations.append(expr)
    if not aggregations:
        return frame
    sort_col = "timestamp" if "timestamp" in columns else "trade_date"
    return frame.sort(sort_col).group_by("trade_date").agg(aggregations).sort("trade_date")


def _is_large_spot_artifact(path: Path) -> bool:
    try:
        size = path.stat().st_size
    except OSError:
        return False
    if size <= MAX_SPOT_AUDIT_READ_BYTES:
        return False
    lower = path.as_posix().lower()
    return "xau" in lower or "spot" in lower or "dukascopy" in lower


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


def _next_missing_component(flags: dict[str, bool]) -> str:
    missing = _missing_components(flags)
    return missing[0] if missing else ""


def _cme_dates_for_audit(frames: dict[str, pl.DataFrame]) -> set[str]:
    dates = set(PILOT_DATES) | set(STRICT_FULL_CME_DATES)
    for key in ("one_week", "date_usability", "option_oi", "option_iv", "futures", "basis"):
        dates.update(date for date in _trade_dates(frames[key]) if date.startswith("2026-05") or date in STRICT_FULL_CME_DATES)
    return dates


def _recommended_spot_mapping(detection: dict[str, Any], matching_dates: list[str]) -> str:
    if not matching_dates:
        return "Keep as candidate; no current CME date overlap detected."
    return (
        f"Map {detection['timestamp_col']}/{detection['open_col']}/{detection['high_col']}/"
        f"{detection['low_col']}/{detection['close_col']} to canonical XAU spot preview."
    )


def _parse_timestamp_columns(raw: dict[str, Any], timestamp_col: str, time_col: str | None) -> datetime | None:
    value = raw.get(timestamp_col)
    if time_col and timestamp_col != time_col and raw.get(time_col):
        value = f"{value} {raw.get(time_col)}"
    try:
        return _parse_datetime(value)
    except (TypeError, ValueError):
        return None


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    text = str(value or "").strip()
    if not text:
        raise ValueError("timestamp is empty")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y.%m.%d %H:%M:%S", "%Y.%m.%d %H:%M"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=UTC)
        except ValueError:
            pass
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _find_col(columns: Iterable[str], aliases: Iterable[str], *, required: bool = True) -> str | None:
    lookup = {_normalize_name(column): column for column in columns}
    for alias in aliases:
        match = lookup.get(_normalize_name(alias))
        if match is not None:
            return match
    if required:
        return None
    return None


def _ohlc_aliases() -> tuple[tuple[str, ...], ...]:
    return (("open", "Open"), ("high", "High"), ("low", "Low"), ("close", "Close", "adj_close", "price", "last"))


def _sample_symbols(frame: pl.DataFrame, symbol_col: str | None) -> list[str]:
    if not symbol_col or frame.is_empty() or symbol_col not in frame.columns:
        return []
    values = []
    for value in frame.get_column(symbol_col).head(25).to_list():
        if value is not None and str(value).strip():
            values.append(str(value).strip())
    return sorted(set(values))


def _timestamp_granularity(frame: pl.DataFrame) -> str:
    if frame.is_empty():
        return "NONE"
    if frame.height <= 1:
        return "SINGLE_SNAPSHOT"
    if "trade_date" not in frame.columns:
        return "UNKNOWN"
    max_rows = max(frame.group_by("trade_date").len().get_column("len").to_list())
    if max_rows >= 12:
        return "INTRADAY"
    if max_rows > 1:
        return "MULTI_SNAPSHOT_DAILY"
    return "DAILY"


def _source_hash(path: Path) -> str:
    try:
        return hash_source_id(str(path.resolve()))
    except OSError:
        return hash_source_id(str(path))


def _redacted_path(path: Path) -> str:
    safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", path.name)[:80] or "source"
    return f"<REDACTED_PATH>/{safe_name}|{_source_hash(path)[:8]}{path.suffix.lower()}"


def _trade_dates(frame: pl.DataFrame) -> set[str]:
    if frame.is_empty() or "trade_date" not in frame.columns:
        return set()
    return {str(value) for value in frame.get_column("trade_date").to_list() if value}


def _event_dates(frame: pl.DataFrame) -> set[str]:
    if frame.is_empty() or "event_timestamp" not in frame.columns:
        return set()
    return {str(value)[:10] for value in frame.get_column("event_timestamp").to_list() if value}


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


def _last_valid_basis_row(frame: pl.DataFrame) -> dict[str, Any]:
    usable = _usable_basis_frame(frame)
    return _last_row(usable)


def _usable_basis_frame(frame: pl.DataFrame) -> pl.DataFrame:
    if frame.is_empty():
        return frame
    rows = [row for row in frame.to_dicts() if _basis_row_is_usable(row)]
    return (
        _frame(rows, _basis_backfill_schema())
        if rows and "join_tolerance" in frame.columns
        else pl.DataFrame(rows, infer_schema_length=None)
        if rows
        else frame.clear()
    )


def _basis_row_is_usable(row: dict[str, Any]) -> bool:
    if not row:
        return False
    if str(row.get("basis_quality") or "").upper() == "LOW_CONFIDENCE":
        return False
    futures_price = _float(row.get("futures_price"))
    spot_price = _float(row.get("spot_price"))
    if futures_price is not None and spot_price is not None:
        return _prices_are_plausible(futures_price, spot_price)
    basis = _float(row.get("basis"))
    return basis is not None and abs(basis) <= 250.0


def _rows_by_date(frame: pl.DataFrame, column: str) -> dict[str, dict[str, Any]]:
    if frame.is_empty() or column not in frame.columns:
        return {}
    return {str(row[column]): row for row in frame.to_dicts() if row.get(column)}


def _one_week_value(frame: pl.DataFrame, trade_date: str, column: str) -> Any:
    row = _rows_by_date(frame, "trade_date").get(trade_date, {})
    return row.get(column)


def _column_has_value(frame: pl.DataFrame, column: str) -> bool:
    if frame.is_empty() or column not in frame.columns:
        return False
    return any((_float(value) or 0.0) != 0.0 for value in frame.get_column(column).to_list())


def _has_no_trade(frame: pl.DataFrame) -> bool:
    if frame.is_empty() or "signal" not in frame.columns:
        return False
    return any(str(value).startswith("NO_TRADE") for value in frame.get_column("signal").to_list())


def _logic_type_exists(frame: pl.DataFrame, token: str) -> bool:
    if frame.is_empty() or "logic_type" not in frame.columns:
        return False
    return any(token in str(value).upper() for value in frame.get_column("logic_type").to_list())


def _logic_name_contains(frame: pl.DataFrame, tokens: tuple[str, ...]) -> bool:
    if frame.is_empty() or "logic_name" not in frame.columns:
        return False
    return any(any(token in str(value).lower() for token in tokens) for value in frame.get_column("logic_name").to_list())


def _wall_level(walls: list[dict[str, Any]], index: int) -> float | None:
    return _float(walls[index].get("level")) if len(walls) > index else None


def _bool_or_unknown(value: Any) -> str:
    if value == "unknown":
        return "unknown"
    return "true" if bool(value) else "false"


def _max_float(frame: pl.DataFrame, column: str) -> float | None:
    values = [_float(value) for value in frame.get_column(column).to_list()] if column in frame.columns else []
    clean = [value for value in values if value is not None]
    return max(clean) if clean else None


def _min_float(frame: pl.DataFrame, column: str) -> float | None:
    values = [_float(value) for value in frame.get_column(column).to_list()] if column in frame.columns else []
    clean = [value for value in values if value is not None]
    return min(clean) if clean else None


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


def _max_int(frame: pl.DataFrame, column: str) -> int:
    if frame.is_empty() or column not in frame.columns:
        return 0
    values = [int(value or 0) for value in frame.get_column(column).to_list()]
    return max(values) if values else 0


def _true_count(frame: pl.DataFrame, column: str) -> int:
    if frame.is_empty() or column not in frame.columns:
        return 0
    return sum(1 for value in frame.get_column(column).to_list() if bool(value))


def _any_true(frame: pl.DataFrame, column: str) -> bool:
    return _true_count(frame, column) > 0


def _normalize_name(value: str) -> str:
    text = re.sub(r"(?<!^)(?=[A-Z])", "_", str(value).strip())
    return text.lower().replace(" ", "_").replace("-", "_").replace("/", "_")


def _concat_or_empty(frames: list[pl.DataFrame], schema: dict[str, Any]) -> pl.DataFrame:
    frames = [frame for frame in frames if not frame.is_empty()]
    if not frames:
        return pl.DataFrame(schema=schema)
    return pl.concat(frames, how="diagonal_relaxed").select(list(schema))


def _frame(rows: list[dict[str, Any]], schema: dict[str, Any]) -> pl.DataFrame:
    if not rows:
        return pl.DataFrame(schema=schema)
    frame = pl.DataFrame(rows, infer_schema_length=None)
    for column, dtype in schema.items():
        if column not in frame.columns:
            frame = frame.with_columns(pl.lit(None).cast(dtype).alias(column))
        else:
            try:
                frame = frame.with_columns(pl.col(column).cast(dtype, strict=False))
            except Exception:
                pass
    return frame.select(list(schema))


def _frame_markdown(frame: pl.DataFrame, *, limit: int = 20) -> str:
    if frame.is_empty():
        return "_No rows._"
    columns = frame.columns
    rows = ["| " + " | ".join(columns) + " |", "| " + " | ".join("---" for _ in columns) + " |"]
    for raw in frame.head(limit).to_dicts():
        rows.append("| " + " | ".join(_markdown_cell(raw.get(column, "")) for column in columns) + " |")
    return "\n".join(rows)


def _markdown_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _safe_report(text: str) -> str:
    lower = text.lower()
    for phrase in FORBIDDEN_REPORT_PHRASES:
        if phrase in lower:
            raise ValueError(f"Forbidden report phrase: {phrase}")
    return text


def _write_line_svg(path: Path, *, title: str, values: list[float]) -> None:
    width, height = 900, 300
    if not values:
        path.write_text(_svg(title, '<text x="40" y="80">No data available.</text>'), encoding="utf-8")
        return
    minimum, maximum = min(values), max(values)
    span = max(maximum - minimum, 1.0)
    points = []
    for index, value in enumerate(values):
        x = 40 + index * (width - 80) / max(len(values) - 1, 1)
        y = height - 40 - ((value - minimum) / span) * (height - 90)
        points.append(f"{x:.1f},{y:.1f}")
    path.write_text(
        _svg(title, f'<polyline fill="none" stroke="#2563eb" stroke-width="2" points="{" ".join(points)}" />'),
        encoding="utf-8",
    )


def _write_bar_svg(path: Path, *, title: str, values: list[float]) -> None:
    width, height = 900, 300
    if not values:
        path.write_text(_svg(title, '<text x="40" y="80">No data available.</text>'), encoding="utf-8")
        return
    maximum = max(max(values), 1.0)
    bar_width = max(6.0, (width - 80) / max(len(values), 1))
    bars = []
    for index, value in enumerate(values):
        x = 40 + index * bar_width
        bar_height = value / maximum * (height - 90)
        y = height - 40 - bar_height
        bars.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width * 0.8:.1f}" height="{bar_height:.1f}" fill="#0f766e" />')
    path.write_text(_svg(title, "\n".join(bars)), encoding="utf-8")


def _svg(title: str, body: str) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="300" viewBox="0 0 900 300">'
        '<rect width="900" height="300" fill="#ffffff" />'
        f'<text x="40" y="30" font-size="18" font-family="Arial">{html.escape(title)}</text>'
        f"{body}</svg>"
    )


def _empty_basis_backfill() -> pl.DataFrame:
    return pl.DataFrame(schema=_basis_backfill_schema())


def _empty_join_preview() -> pl.DataFrame:
    return pl.DataFrame(schema=_basis_backfill_schema())


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


def _spot_audit_schema() -> dict[str, Any]:
    return {
        "redacted_path": pl.String,
        "source_hash": pl.String,
        "detected_symbol": pl.String,
        "rows_count": pl.Int64,
        "date_start": pl.String,
        "date_end": pl.String,
        "timestamp_granularity": pl.String,
        "can_join_to_cme_dates": pl.Boolean,
        "matching_cme_dates": pl.String,
        "missing_cme_dates": pl.String,
        "recommended_mapping": pl.String,
    }


def _spot_backfill_schema() -> dict[str, Any]:
    return {
        "timestamp": pl.Datetime(time_zone="UTC"),
        "trade_date": pl.String,
        "symbol": pl.String,
        "open": pl.Float64,
        "high": pl.Float64,
        "low": pl.Float64,
        "close": pl.Float64,
        "volume": pl.Float64,
        "source_hash": pl.String,
        "redacted_path": pl.String,
        "timestamp_granularity": pl.String,
    }


def _futures_norm_schema() -> dict[str, Any]:
    return {
        "timestamp": pl.Datetime(time_zone="UTC"),
        "trade_date": pl.String,
        "futures_symbol": pl.String,
        "futures_price": pl.Float64,
        "high": pl.Float64,
        "low": pl.Float64,
        "close": pl.Float64,
        "source_file_hash": pl.String,
    }


def _basis_backfill_schema() -> dict[str, Any]:
    return {
        "trade_date": pl.String,
        "timestamp": pl.Datetime(time_zone="UTC"),
        "futures_price": pl.Float64,
        "spot_price": pl.Float64,
        "basis": pl.Float64,
        "basis_quality": pl.String,
        "join_tolerance": pl.String,
        "source_hashes": pl.String,
        "notes": pl.String,
    }


def _replay_schema() -> dict[str, Any]:
    return {
        "trade_date": pl.String,
        "pilot_usability_grade": pl.String,
        "strict_validation_grade": pl.String,
        "spot_available": pl.Boolean,
        "basis_available": pl.Boolean,
        "basis_quality": pl.String,
        "iv_available": pl.Boolean,
        "oi_available": pl.Boolean,
        "oi_change_available": pl.Boolean,
        "option_volume_available": pl.Boolean,
        "futures_available": pl.Boolean,
        "guru_context_available": pl.Boolean,
        "top_oi_wall_1": pl.Float64,
        "top_oi_wall_2": pl.Float64,
        "top_oi_wall_3": pl.Float64,
        "wall_type": pl.String,
        "wall_score": pl.Float64,
        "oi_change_near_wall": pl.Float64,
        "volume_near_wall": pl.Float64,
        "iv_near_wall": pl.Float64,
        "nearest_wall_above_price": pl.Float64,
        "nearest_wall_below_price": pl.Float64,
        "active_guru_logic": pl.String,
        "no_trade_filter_active": pl.Boolean,
        "market_map_logic_active": pl.Boolean,
        "rejection_logic_active": pl.Boolean,
        "acceptance_logic_active": pl.Boolean,
        "squeeze_or_pin_logic_active": pl.Boolean,
        "touched_wall": pl.String,
        "rejected_wall": pl.String,
        "accepted_wall": pl.String,
        "broke_range": pl.String,
        "stayed_inside_range": pl.String,
        "observation_confidence": pl.String,
        "plain_english_summary": pl.String,
        "what_worked": pl.String,
        "what_failed": pl.String,
        "what_missing": pl.String,
        "next_fix_needed": pl.String,
    }


def _guru_filter_schema() -> dict[str, Any]:
    return {
        "timestamp": pl.String,
        "trade_date": pl.String,
        "base_signal": pl.String,
        "guru_filter_active": pl.Boolean,
        "no_trade_reason": pl.String,
        "would_block_trade": pl.Boolean,
        "blocked_trade_outcome_if_known": pl.String,
        "avoided_loss_proxy": pl.Float64,
        "opportunity_cost_proxy": pl.Float64,
        "net_filter_value_proxy": pl.Float64,
        "evidence_status": pl.String,
    }


def _validation_upgrade_schema() -> dict[str, Any]:
    return {
        "trade_date": pl.String,
        "before_strict_validation_grade": pl.String,
        "after_strict_validation_grade": pl.String,
        "before_complete_validation_days": pl.Int64,
        "after_complete_validation_days": pl.Int64,
        "day_upgraded": pl.Boolean,
        "still_missing_components_by_date": pl.String,
        "next_missing_component": pl.String,
        "money_readiness_changed": pl.Boolean,
        "validation_threshold": pl.Int64,
    }


def main() -> None:
    """CLI entry point for the current-week replay layer."""

    result = run_current_week_replay_layer()
    print(f"final_recommendation: {result.final_recommendation}")
    print(f"spot_candidates: {result.spot_audit.height}")
    print(f"basis_rows: {result.basis_backfilled.height}")
    print(f"replay_rows: {result.replay.height}")


if __name__ == "__main__":
    main()
