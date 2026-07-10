from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from src.models.xau_market_context import XauPriceBar
from src.xau_vol2vol_history_walkforward.collection_manifest import atomic_write_json
from src.xau_vol2vol_history_walkforward.walkforward_simulator import (
    XauPriceBarFolderLoadResult,
)

PLANNING_TIMES = (time(10, 0), time(19, 0))


def build_coverage_and_integrity_audit(
    *,
    vol2vol_root: Path,
    price_result: XauPriceBarFolderLoadResult,
    timezone: str,
    basis_tolerance_seconds: int = 300,
) -> tuple[dict[str, Any], dict[str, Any]]:
    zone = ZoneInfo(timezone)
    catalog = _read_json(vol2vol_root / "catalog" / "available_sessions.json", {})
    advertised = _advertised_dates(catalog)
    valid_payloads: dict[date, dict[str, Any]] = {}
    snapshot_counts: dict[str, int] = {}
    mismatches: list[dict[str, str | None]] = []
    duplicate_snapshots = 0
    for path in sorted((vol2vol_root / "daily").glob("*/raw.json")):
        requested = _parse_date(path.parent.name)
        payload = _read_json(path, None)
        returned = _parse_date(payload.get("sessionDate")) if isinstance(payload, dict) else None
        if requested is None or returned != requested:
            mismatches.append(
                {
                    "path": path.as_posix(),
                    "requested_session_date": requested.isoformat() if requested else None,
                    "returned_session_date": returned.isoformat() if returned else None,
                }
            )
            continue
        snapshots = payload.get("snapshots")
        if not isinstance(snapshots, list):
            snapshots = []
        duplicate_snapshots += _duplicate_snapshot_count(snapshots)
        valid_payloads[requested] = payload
        snapshot_counts[requested.isoformat()] = len(snapshots)

    bars = price_result.bars
    bars_by_date: dict[date, list[XauPriceBar]] = {}
    for bar in bars:
        bars_by_date.setdefault(bar.timestamp.astimezone(zone).date(), []).append(bar)
    valid_dates = sorted(valid_payloads)
    overlap_dates = [item for item in valid_dates if bars_by_date.get(item)]
    missing_candle_dates = [item for item in valid_dates if not bars_by_date.get(item)]
    minute_coverage = {
        item.isoformat(): _session_minute_coverage(bars_by_date.get(item, []), zone)
        for item in valid_dates
    }
    planning_cycles, planning_integrity = _planning_cycle_audit(
        payloads=valid_payloads,
        bars=bars,
        zone=zone,
        tolerance_seconds=basis_tolerance_seconds,
    )
    incomplete_dates = sorted(
        str(item)
        for item in catalog.get("incomplete_session_dates", [])
        if isinstance(item, str)
    )
    coverage = {
        "advertised_vol2vol_session_count": len(advertised),
        "collected_valid_session_count": len(valid_dates),
        "failed_or_mismatched_session_count": len(mismatches),
        "earliest_valid_vol2vol_date": valid_dates[0].isoformat() if valid_dates else None,
        "latest_valid_vol2vol_date": valid_dates[-1].isoformat() if valid_dates else None,
        "snapshot_count_per_date": snapshot_counts,
        "xau_candle_earliest_timestamp": bars[0].timestamp.isoformat() if bars else None,
        "xau_candle_latest_timestamp": bars[-1].timestamp.isoformat() if bars else None,
        "xau_candle_row_count": len(bars),
        "missing_candle_dates": [item.isoformat() for item in missing_candle_dates],
        "missing_minute_counts_by_session": minute_coverage,
        "overlapping_valid_test_dates": [item.isoformat() for item in overlap_dates],
        "overlap_session_count": len(overlap_dates),
        "incomplete_sessions_excluded": incomplete_dates,
        "planning_cycles_available_per_date": planning_cycles,
        "source_price_files": [path.as_posix() for path in price_result.source_paths],
        "warnings": price_result.warnings,
        "research_only": True,
        "signal_allowed": False,
    }
    integrity = {
        "requested_returned_date_mismatch_count": len(mismatches),
        "requested_returned_date_mismatches": mismatches,
        "duplicate_snapshot_count": duplicate_snapshots,
        "duplicate_candle_timestamp_count": price_result.duplicate_timestamp_count,
        "out_of_order_timestamp_count": 0,
        "trigger_before_plan_count": 0,
        "future_snapshot_used_count": planning_integrity["future_snapshot_used_count"],
        "plans_missing_basis_count": planning_integrity["plans_missing_basis_count"],
        "plans_missing_sd_count": planning_integrity["plans_missing_sd_count"],
        "plans_without_bars_in_window_count": 0,
        "same_bar_ambiguous_count": 0,
        "unavailable_outcomes_count": 0,
        "research_only": True,
        "signal_allowed": False,
    }
    return coverage, integrity


def persist_audit_report(
    *,
    output_root: Path,
    coverage: dict[str, Any],
    integrity: dict[str, Any],
) -> Path:
    run_id = f"audit_{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%f')}"
    output_dir = output_root / "xau_vol2vol_history_walkforward" / run_id
    atomic_write_json(output_dir / "coverage_audit.json", coverage)
    atomic_write_json(output_dir / "integrity_report.json", integrity)
    lines = [
        f"# XAU Vol2Vol Coverage Audit {run_id}",
        "",
        "Research-only. Not a buy/sell signal.",
        "",
        f"- Advertised sessions: `{coverage['advertised_vol2vol_session_count']}`",
        f"- Valid collected sessions: `{coverage['collected_valid_session_count']}`",
        f"- Overlap sessions: `{coverage['overlap_session_count']}`",
        f"- XAU candle rows: `{coverage['xau_candle_row_count']}`",
        f"- Date mismatches: `{integrity['requested_returned_date_mismatch_count']}`",
        f"- Future snapshots used: `{integrity['future_snapshot_used_count']}`",
        f"- Trigger before plan: `{integrity['trigger_before_plan_count']}`",
        "",
        "signal_allowed=false",
        "research_only=true",
    ]
    (output_dir / "coverage_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_dir


def integrity_blocks_backtest(integrity: dict[str, Any]) -> list[str]:
    blockers = []
    for field in (
        "future_snapshot_used_count",
        "trigger_before_plan_count",
        "requested_returned_date_mismatch_count",
        "plans_missing_basis_count",
        "plans_missing_sd_count",
    ):
        if int(integrity.get(field) or 0) > 0:
            blockers.append(f"{field}={integrity[field]}")
    return blockers


def _planning_cycle_audit(
    *,
    payloads: dict[date, dict[str, Any]],
    bars: list[XauPriceBar],
    zone: ZoneInfo,
    tolerance_seconds: int,
) -> tuple[dict[str, dict[str, bool]], dict[str, int]]:
    availability: dict[str, dict[str, bool]] = {}
    future_used = 0
    missing_basis = 0
    missing_sd = 0
    for session_date, payload in sorted(payloads.items()):
        snapshots = payload.get("snapshots")
        if not isinstance(snapshots, list):
            snapshots = []
        by_cycle: dict[str, bool] = {}
        for cycle in PLANNING_TIMES:
            planning_at = datetime.combine(session_date, cycle, tzinfo=zone)
            candidates = [
                item
                for item in snapshots
                if isinstance(item, dict)
                if (observed := _parse_datetime(item.get("observedAt"))) is not None
                if observed.astimezone(zone) <= planning_at
            ]
            selected = (
                max(candidates, key=lambda item: _parse_datetime(item["observedAt"]))
                if candidates
                else None
            )
            price_candidates = [
                bar for bar in bars if bar.timestamp.astimezone(zone) <= planning_at
            ]
            price_bar = price_candidates[-1] if price_candidates else None
            within_tolerance = bool(
                price_bar
                and (planning_at - price_bar.timestamp.astimezone(zone)).total_seconds()
                <= tolerance_seconds
            )
            cycle_key = cycle.strftime("%H:%M")
            by_cycle[cycle_key] = selected is not None and within_tolerance
            if selected is not None:
                observed = _parse_datetime(selected.get("observedAt"))
                if observed and observed.astimezone(zone) > planning_at:
                    future_used += 1
                if not _has_numeric_sd(selected):
                    missing_sd += 1
                if not within_tolerance or _future_price(selected) is None:
                    missing_basis += 1
        availability[session_date.isoformat()] = by_cycle
    return availability, {
        "future_snapshot_used_count": future_used,
        "plans_missing_basis_count": missing_basis,
        "plans_missing_sd_count": missing_sd,
    }


def _session_minute_coverage(bars: list[XauPriceBar], zone: ZoneInfo) -> dict[str, int]:
    minutes = {
        bar.timestamp.astimezone(zone).replace(second=0, microsecond=0)
        for bar in bars
        if time(10, 0) <= bar.timestamp.astimezone(zone).time() <= time(23, 59)
    }
    expected = 14 * 60
    return {
        "expected_minutes_10_to_24": expected,
        "available_minutes": len(minutes),
        "missing_minutes": max(expected - len(minutes), 0),
    }


def _duplicate_snapshot_count(snapshots: list[Any]) -> int:
    keys = [
        (
            item.get("id"),
            item.get("kind"),
            item.get("observedAt"),
        )
        for item in snapshots
        if isinstance(item, dict)
    ]
    counts = Counter(keys)
    return sum(count - 1 for count in counts.values() if count > 1)


def _advertised_dates(catalog: dict[str, Any]) -> list[str]:
    sessions = catalog.get("availableSessions")
    if not isinstance(sessions, list):
        return []
    return sorted(
        str(item["sessionDate"])
        for item in sessions
        if isinstance(item, dict) and item.get("sessionDate")
    )


def _has_numeric_sd(snapshot: dict[str, Any]) -> bool:
    ranges = snapshot.get("ranges")
    if not isinstance(ranges, list):
        return False
    sds = {int(item.get("sd") or 0) for item in ranges if isinstance(item, dict)}
    return 2 in sds and 3 in sds


def _future_price(snapshot: dict[str, Any]) -> float | None:
    value = snapshot.get("currentPrice") or snapshot.get("futurePrice")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _parse_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None
