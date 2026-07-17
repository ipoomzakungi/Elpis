from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

from src.models.xau_market_context import XauPriceBar
from src.xau_options_research.candidate_validation import load_candidate_registry
from src.xau_options_research.event_independence import enforce_non_overlapping_positions
from src.xau_options_research.strategy_simulator import simulate_frozen_candidate

EXPECTED_MANIFEST_SHA256 = "b316fa3a5694ffd3432c8b4e1158713b3fa999e2893a1b726f120522109ec9be"
ENGINE_REVISION = "032B-candidate-validation-v2-runner-v1"


@dataclass(frozen=True)
class SessionGateResult:
    accepted: bool
    reason: str


def load_frozen_manifest(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != EXPECTED_MANIFEST_SHA256:
        raise ValueError("Candidate v2 manifest hash mismatch; create validation v3")
    manifest = load_candidate_registry(path)
    expected = {
        "data_cutoff": "2026-07-16",
        "validation_start_date": "2026-07-17",
        "mapping_mode": "same_time_basis",
        "concurrency_rule": "one_active_position_per_experiment_side_series",
    }
    for field, value in expected.items():
        if manifest.get(field) != value:
            raise ValueError(f"Frozen manifest mismatch: {field}")
    if manifest.get("costs") != {
        "spread_points": 1.0,
        "slippage_points_per_side": 0.0,
    }:
        raise ValueError("Frozen candidate cost assumptions changed")
    enabled = {
        row["candidate_id"]
        for row in manifest["candidates"]
        if row["enablement"] == "enabled"
    }
    if enabled != {"C1", "C2"}:
        raise ValueError("Only C1 and C2 may be enabled in validation v2")
    return manifest


def validate_completed_session(
    *,
    requested_date: date,
    returned_date: str,
    source_status: str,
    price_coverage_complete: bool,
    manifest: dict[str, Any],
) -> SessionGateResult:
    if requested_date <= date.fromisoformat(manifest["data_cutoff"]):
        return SessionGateResult(False, "PRE_CUTOFF_SESSION")
    if source_status == "date_mismatch" or (
        source_status == "complete" and returned_date != requested_date.isoformat()
    ):
        return SessionGateResult(False, "RETURNED_DATE_MISMATCH")
    if source_status != "complete":
        return SessionGateResult(False, "SESSION_INCOMPLETE")
    if returned_date != requested_date.isoformat():
        return SessionGateResult(False, "RETURNED_DATE_MISMATCH")
    if not price_coverage_complete:
        return SessionGateResult(False, "PRICE_COVERAGE_INCOMPLETE")
    return SessionGateResult(True, "ACCEPTED")


def run_frozen_candidates(
    *,
    manifest: dict[str, Any],
    episode_events: list[dict[str, Any]],
    bars: list[XauPriceBar],
) -> dict[str, Any]:
    candidates = {
        row["candidate_id"]: row
        for row in manifest["candidates"]
        if row["candidate_id"] in {"C1", "C2"}
    }
    costs = manifest["costs"]
    outcomes = []
    for candidate_id in ("C1", "C2"):
        outcomes.extend(
            simulate_frozen_candidate(
                candidates[candidate_id],
                episode_events,
                bars,
                spread_points=float(costs["spread_points"]),
                slippage_points_per_side=float(costs["slippage_points_per_side"]),
            )
        )
    event_index = {row["episode_id"]: row for row in episode_events}
    outcomes, blocked = enforce_non_overlapping_positions(outcomes, event_index)
    opportunities = _opportunities(outcomes, event_index)
    c3_eligible = [row for row in episode_events if _c3_eligible(row)]
    bo0_monitor = [row for row in episode_events if row["event_type"].startswith("close_beyond_")]
    return {
        "opportunities": opportunities,
        "outcomes": outcomes,
        "c3_descriptive_eligibility_count": len(c3_eligible),
        "c3_outcome_count": 0,
        "bo0_monitor_observation_count": len(bo0_monitor),
        "bo0_candidate_outcome_count": 0,
        "blocked_concurrent_outcome_count": blocked,
        "research_only": True,
        "signal_allowed": False,
        "order_submission_allowed": False,
    }


def complete_price_coverage(
    bars: list[XauPriceBar],
    *,
    session_date: date,
    timezone,
) -> bool:
    start = datetime.combine(session_date, time(7, 0), tzinfo=timezone)
    end = datetime.combine(session_date, time(23, 59), tzinfo=timezone)
    timestamps = {
        bar.timestamp.astimezone(timezone).replace(second=0, microsecond=0)
        for bar in bars
        if start <= bar.timestamp.astimezone(timezone) <= end
    }
    return len(timestamps) == 1020 and min(timestamps, default=None) == start and max(
        timestamps, default=None
    ) == end


def hash_price_bars(bars: list[XauPriceBar], session_date: date, timezone) -> str:
    payload = [
        {
            "timestamp": bar.timestamp.astimezone(timezone).isoformat(),
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
        }
        for bar in bars
        if bar.timestamp.astimezone(timezone).date() == session_date
    ]
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def engine_revision_hash() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _opportunities(
    outcomes: list[dict[str, Any]], event_index: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    records = []
    seen = set()
    for outcome in outcomes:
        key = (outcome["candidate_id"], outcome["episode_id"])
        if key in seen:
            continue
        seen.add(key)
        event = event_index[outcome["episode_id"]]
        records.append(
            {
                "opportunity_id": f"{outcome['candidate_id']}:{outcome['episode_id']}",
                "candidate_id": outcome["candidate_id"],
                "candidate_hash": outcome["candidate_hash"],
                "episode_id": outcome["episode_id"],
                "session_date": outcome["session_date"],
                "side": outcome["side"],
                "entry_zone": "1.5SD" if "1_5sd" in outcome["event_type"] else "1SD",
                "event_timestamp": outcome["entry_timestamp"],
                "selected_series": event.get("selected_series"),
                "dte": event.get("dte"),
                "iv_state": event.get("iv_state"),
                "oi_distance_sd": event.get("oi_distance_sd"),
                "research_only": True,
                "signal_allowed": False,
                "order_submission_allowed": False,
            }
        )
    return records


def _c3_eligible(event: dict[str, Any]) -> bool:
    return bool(
        event["planning_mode"] == "fixed_morning"
        and event["event_type"]
        in {
            "lower_1sd_touch",
            "lower_1_5sd_touch",
            "upper_1sd_touch",
            "upper_1_5sd_touch",
        }
        and event.get("oi_rank") is not None
        and event["oi_rank"] <= 5
        and event.get("oi_distance_sd") is not None
        and event["oi_distance_sd"] <= 0.25
    )
