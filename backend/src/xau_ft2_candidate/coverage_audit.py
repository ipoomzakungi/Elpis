from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from src.xau_first_touch_study.models import MappingMode, TimeAnchor, as_record
from src.xau_first_touch_study.selection import (
    load_source_snapshots,
    map_selection,
    select_snapshot,
)
from src.xau_vol2vol_history_walkforward.data_lake import (
    daily_raw_path,
    evaluate_daily_session_eligibility,
)
from src.xau_vol2vol_history_walkforward.walkforward_simulator import (
    load_traded_bars_folder,
)

SOURCE_HAS_NO_DTE_080_SERIES = "SOURCE_HAS_NO_DTE_080_SERIES"
DTE_FIELD_MISSING = "DTE_FIELD_MISSING"
DTE_PARSE_FAILURE = "DTE_PARSE_FAILURE"
SERIES_SELECTION_FAILURE = "SERIES_SELECTION_FAILURE"
SNAPSHOT_TIME_INVALID = "SNAPSHOT_TIME_INVALID"
XAU_PRICE_UNAVAILABLE = "XAU_PRICE_UNAVAILABLE"
MAPPING_RECONCILIATION_FAILURE = "MAPPING_RECONCILIATION_FAILURE"
SESSION_INCOMPLETE = "SESSION_INCOMPLETE"
RETURNED_DATE_MISMATCH = "RETURNED_DATE_MISMATCH"
SOURCE_PAYLOAD_MISSING = "SOURCE_PAYLOAD_MISSING"
SOURCE_PAYLOAD_INVALID = "SOURCE_PAYLOAD_INVALID"
ELIGIBLE = "ELIGIBLE"

@dataclass(frozen=True)
class CoverageAuditConfig:
    vol2vol_root: Path
    price_bars_folder: Path
    session_date_from: date
    session_date_to: date
    as_of_date: date
    target_dte: float = 0.8
    minimum_dte: float = 0.75
    maximum_dte: float = 0.85
    timezone: str = "Asia/Bangkok"


def run_coverage_audit(config: CoverageAuditConfig) -> dict[str, Any]:
    price_result = load_traded_bars_folder(
        config.price_bars_folder,
        timezone=config.timezone,
    )
    bars_by_date = _bars_by_date(price_result.bars, config.timezone)
    rows = []
    current = config.session_date_from
    while current <= config.session_date_to:
        rows.append(
            _audit_session(
                config,
                current,
                bars_by_date.get(current, []),
            )
        )
        current += timedelta(days=1)
    completed = [item for item in rows if item["backtest_eligible"]]
    excluded_completed = [item for item in completed if not item["final_plan_eligible"]]
    classifications = Counter(item["classification"] for item in rows)
    report = {
        "session_date_from": config.session_date_from.isoformat(),
        "session_date_to": config.session_date_to.isoformat(),
        "completed_sessions": len(completed),
        "source_qualified_sessions": sum(
            item["source_dte_qualified"] for item in completed
        ),
        "parser_qualified_sessions": sum(
            item["parser_dte_qualified"] for item in completed
        ),
        "mapped_plans": sum(item["final_plan_eligible"] for item in completed),
        "recoverable_exclusions": sum(
            item["recoverable"] for item in excluded_completed
        ),
        "irrecoverable_exclusions": sum(
            not item["recoverable"] for item in excluded_completed
        ),
        "classification_counts": dict(sorted(classifications.items())),
        "rows": rows,
        "price_source_paths": [item.as_posix() for item in price_result.source_paths],
        "research_only": True,
        "signal_allowed": False,
        "order_submission_allowed": False,
    }
    return report


def write_coverage_audit(output_dir: Path, report: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "strict_dte_coverage_audit.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    (output_dir / "strict_dte_coverage_audit.md").write_text(
        _markdown(report),
        encoding="utf-8",
    )


def _audit_session(
    config: CoverageAuditConfig,
    session_date: date,
    bars: list[Any],
) -> dict[str, Any]:
    eligibility = evaluate_daily_session_eligibility(
        root=config.vol2vol_root,
        session_date=session_date,
        current_date=config.as_of_date,
    )
    base = {
        "session_date": session_date.isoformat(),
        "source_session_status": eligibility.source_session_status,
        "backtest_eligible": eligibility.backtest_eligible,
        "source_dte_qualified": False,
        "parser_dte_qualified": False,
        "xau_mapping_available": False,
        "final_plan_eligible": False,
        "available_series": [],
        "series_observations": [],
        "all_unique_observed_dte": [],
        "closest_positive_dte": None,
        "absolute_dte_error": None,
        "chosen_snapshot": None,
        "selection_reason": None,
        "exclusion_reason": None,
        "parser_warnings": [],
        "raw_dte_qualified_complete_range_count": 0,
        "recoverable": False,
        "payload_sha256": eligibility.payload_sha256,
    }
    raw_path = daily_raw_path(config.vol2vol_root, session_date)
    if not raw_path.exists():
        return {
            **base,
            "classification": SOURCE_PAYLOAD_MISSING,
            "exclusion_reason": "Exact-date Vol2Vol payload is missing.",
        }
    try:
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            **base,
            "classification": SOURCE_PAYLOAD_INVALID,
            "exclusion_reason": str(exc),
        }
    returned_date = str(payload.get("sessionDate") or "")[:10]
    if returned_date != session_date.isoformat():
        return {
            **base,
            "classification": RETURNED_DATE_MISMATCH,
            "exclusion_reason": (
                f"Requested {session_date.isoformat()} but payload returned {returned_date!r}."
            ),
        }
    if not eligibility.backtest_eligible:
        return {
            **base,
            "classification": SESSION_INCOMPLETE,
            "exclusion_reason": "; ".join(eligibility.reasons)
            or "Session is not complete for backtesting.",
        }

    raw_rows = payload.get("snapshots")
    raw_rows = raw_rows if isinstance(raw_rows, list) else []
    inspection = _inspect_raw_rows(
        raw_rows,
        session_date,
        config.target_dte,
        config.minimum_dte,
        config.maximum_dte,
    )
    base.update(inspection)
    valid_positive = inspection["_valid_positive_dte"]
    base.pop("_valid_positive_dte")
    base["source_dte_qualified"] = any(
        config.minimum_dte <= value <= config.maximum_dte
        for value in valid_positive
    )
    if not raw_rows or inspection["_missing_dte_count"] == len(raw_rows):
        return _excluded(
            base,
            DTE_FIELD_MISSING,
            "No snapshot contained a DTE value.",
        )
    if not valid_positive:
        reason = (
            DTE_PARSE_FAILURE
            if inspection["_dte_parse_failure_count"]
            else SOURCE_HAS_NO_DTE_080_SERIES
        )
        return _excluded(
            base,
            reason,
            "No valid positive DTE observation was available.",
            recoverable=reason == DTE_PARSE_FAILURE,
        )
    if not base["source_dte_qualified"]:
        return _excluded(
            base,
            SOURCE_HAS_NO_DTE_080_SERIES,
            "The source had positive DTE values, but none were inside 0.75-0.85.",
        )

    try:
        parsed = load_source_snapshots(raw_path, session_date)
    except ValueError as exc:
        base["parser_warnings"].append(str(exc))
        return _excluded(
            base,
            SERIES_SELECTION_FAILURE,
            str(exc),
            recoverable=base["raw_dte_qualified_complete_range_count"] > 0,
        )
    selection = select_snapshot(
        parsed,
        anchor=TimeAnchor.T0_DTE_080,
        session_date=session_date,
        timezone=config.timezone,
        target_dte=config.target_dte,
        dte_tolerance=config.maximum_dte - config.target_dte,
    )
    if selection is None:
        reason = (
            SNAPSHOT_TIME_INVALID
            if inspection["_timestamp_failure_count"]
            else SERIES_SELECTION_FAILURE
        )
        complete_rows = base["raw_dte_qualified_complete_range_count"]
        return _excluded(
            base,
            reason,
            (
                "Raw DTE-qualified rows did not contain complete literal 1/2/3SD ranges."
                if complete_rows == 0
                else "A complete raw DTE-qualified row was lost during normalization."
            ),
            recoverable=complete_rows > 0,
        )
    base["chosen_snapshot"] = as_record(selection)
    base["selection_reason"] = selection.selection_reason
    base["parser_dte_qualified"] = selection.strict_dte_eligible
    if not selection.strict_dte_eligible:
        return _excluded(
            base,
            SERIES_SELECTION_FAILURE,
            (
                "The strict raw DTE rows lacked complete literal 1/2/3SD ranges, "
                "so normalization selected a non-strict complete snapshot."
                if base["raw_dte_qualified_complete_range_count"] == 0
                else "Normalized selection did not preserve a complete raw strict-DTE row."
            ),
            recoverable=base["raw_dte_qualified_complete_range_count"] > 0,
        )
    if not bars:
        return _excluded(
            base,
            XAU_PRICE_UNAVAILABLE,
            "No retained XAUUSD bars exist for the session date.",
            recoverable=True,
        )
    plan = map_selection(
        selection,
        bars,
        mapping_mode=MappingMode.DISTANCE_REANCHORED,
    )
    if plan is None:
        return _excluded(
            base,
            MAPPING_RECONCILIATION_FAILURE,
            "XAUUSD bars exist, but no fully closed bar reconciled to plan activation.",
            recoverable=True,
        )
    base["xau_mapping_available"] = True
    base["final_plan_eligible"] = True
    base["classification"] = ELIGIBLE
    base["recoverable"] = False
    return _clean_internal_counts(base)


def _inspect_raw_rows(
    rows: list[dict[str, Any]],
    expected_date: date,
    target_dte: float,
    minimum_dte: float,
    maximum_dte: float,
) -> dict[str, Any]:
    by_series: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"dte": set(), "timestamps": []}
    )
    valid_positive = []
    missing_dte = 0
    dte_failures = 0
    timestamp_failures = 0
    qualified_complete_ranges = 0
    warnings = []
    for index, row in enumerate(rows):
        series = str(row.get("series") or "").strip() or "<missing>"
        raw_dte = row.get("dte")
        if raw_dte in (None, ""):
            missing_dte += 1
            warnings.append(f"snapshot[{index}] {series}: DTE field missing")
        else:
            try:
                value = float(raw_dte)
                by_series[series]["dte"].add(value)
                if value > 0:
                    valid_positive.append(value)
                if (
                    minimum_dte <= value <= maximum_dte
                    and _has_complete_ranges(row)
                ):
                    qualified_complete_ranges += 1
                elif minimum_dte <= value <= maximum_dte:
                    warnings.append(
                        f"snapshot[{index}] {series}: strict-DTE row lacks "
                        "complete literal 1/2/3SD ranges"
                    )
            except (TypeError, ValueError):
                dte_failures += 1
                warnings.append(
                    f"snapshot[{index}] {series}: DTE parse failure for {raw_dte!r}"
                )
        try:
            observed = _parse_datetime(row.get("observedAt"))
            by_series[series]["timestamps"].append(observed)
        except (TypeError, ValueError):
            timestamp_failures += 1
            warnings.append(f"snapshot[{index}] {series}: observedAt is invalid")
        returned = str(row.get("sessionDate") or "")[:10]
        if returned and returned != expected_date.isoformat():
            warnings.append(
                f"snapshot[{index}] {series}: row session date {returned} mismatches payload"
            )
    closest = (
        min(valid_positive, key=lambda value: (abs(value - target_dte), value))
        if valid_positive
        else None
    )
    series_rows = []
    for series, values in sorted(by_series.items()):
        timestamps = sorted(values["timestamps"])
        series_rows.append(
            {
                "series": series,
                "unique_observed_dte": sorted(values["dte"]),
                "first_observed_at": timestamps[0].isoformat() if timestamps else None,
                "last_observed_at": timestamps[-1].isoformat() if timestamps else None,
            }
        )
    return {
        "available_series": sorted(by_series),
        "series_observations": series_rows,
        "all_unique_observed_dte": sorted(
            {value for values in by_series.values() for value in values["dte"]}
        ),
        "closest_positive_dte": closest,
        "absolute_dte_error": (
            abs(closest - target_dte) if closest is not None else None
        ),
        "parser_warnings": warnings,
        "_valid_positive_dte": valid_positive,
        "_missing_dte_count": missing_dte,
        "_dte_parse_failure_count": dte_failures,
        "_timestamp_failure_count": timestamp_failures,
        "raw_dte_qualified_complete_range_count": qualified_complete_ranges,
    }


def _excluded(
    base: dict[str, Any],
    classification: str,
    reason: str,
    *,
    recoverable: bool = False,
) -> dict[str, Any]:
    base["classification"] = classification
    base["exclusion_reason"] = reason
    base["recoverable"] = recoverable
    return _clean_internal_counts(base)


def _clean_internal_counts(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if not key.startswith("_")}


def _bars_by_date(bars: list[Any], timezone: str) -> dict[date, list[Any]]:
    zone = ZoneInfo(timezone)
    grouped: dict[date, list[Any]] = defaultdict(list)
    for bar in bars:
        grouped[bar.timestamp.astimezone(zone).date()].append(bar)
    return dict(grouped)


def _parse_datetime(value: Any) -> datetime:
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def _has_complete_ranges(row: dict[str, Any]) -> bool:
    tiers = set()
    for item in row.get("ranges") or []:
        try:
            tier = int(item["sd"])
            down = item.get("down", item.get("fix"))
            up = item.get("up", item.get("fix"))
            float(down)
            float(up)
        except (KeyError, TypeError, ValueError):
            continue
        if tier in {1, 2, 3}:
            tiers.add(tier)
    return tiers == {1, 2, 3}


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Strict T0 DTE-0.80 Coverage Audit",
        "",
        f"- Completed sessions: {report['completed_sessions']}",
        f"- Source-qualified sessions: {report['source_qualified_sessions']}",
        f"- Parser-qualified sessions: {report['parser_qualified_sessions']}",
        f"- Mapped plans: {report['mapped_plans']}",
        f"- Recoverable completed-session exclusions: {report['recoverable_exclusions']}",
        f"- Irrecoverable completed-session exclusions: {report['irrecoverable_exclusions']}",
        "",
        "## Completed Sessions",
        "",
        "| Date | Closest DTE | Source qualified | Parser qualified | Mapped | Classification |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for row in report["rows"]:
        if not row["backtest_eligible"]:
            continue
        closest = row["closest_positive_dte"]
        lines.append(
            f"| {row['session_date']} | "
            f"{closest if closest is not None else 'n/a'} | "
            f"{row['source_dte_qualified']} | {row['parser_dte_qualified']} | "
            f"{row['final_plan_eligible']} | {row['classification']} |"
        )
    lines.extend(
        [
            "",
            "## Classification Counts",
            "",
        ]
    )
    for name, count in report["classification_counts"].items():
        lines.append(f"- {name}: {count}")
    lines.extend(
        [
            "",
            "The audit does not relax the frozen DTE tolerance. Recoverable means a "
            "parser, timing, or retained-price limitation may be repairable; it does "
            "not mean the session is silently included.",
            "",
        ]
    )
    return "\n".join(lines)
