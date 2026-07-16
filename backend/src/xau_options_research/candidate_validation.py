from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any


def candidate_hash(candidate: dict[str, Any]) -> str:
    canonical = {key: value for key, value in candidate.items() if key != "candidate_hash"}
    return hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def load_candidate_registry(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("research_only") is not True or payload.get("signal_allowed") is not False:
        raise ValueError("Candidate validation registry must remain research-only")
    for candidate in payload["candidates"]:
        if candidate_hash(candidate) != candidate.get("candidate_hash"):
            raise ValueError(f"Candidate hash mismatch: {candidate['candidate_id']}")
    return {**payload, "registry_hash": hashlib.sha256(path.read_bytes()).hexdigest()}


def build_candidate_manifest(
    registry: dict[str, Any],
    matched_controls: dict[str, Any],
) -> dict[str, Any]:
    candidates = []
    for row in registry["candidates"]:
        enabled = row["enablement"] == "enabled"
        if row["candidate_id"] == "C3":
            enabled = bool(matched_controls["mr2_beats_controls"])
        candidates.append({**row, "enabled_for_validation_v2": enabled})
    return {
        **registry,
        "candidates": candidates,
        "c3_audit_gate_passed": bool(matched_controls["mr2_beats_controls"]),
        "candidate_rules_frozen": True,
        "future_rule_change_requires": "candidate_validation_v3",
        "research_only": True,
        "signal_allowed": False,
    }


def build_validation_v2_status(
    outcomes: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    cutoff = date.fromisoformat(manifest["data_cutoff"])
    eligible = [row for row in outcomes if date.fromisoformat(row["session_date"]) > cutoff]
    pre_cutoff = [row for row in eligible if date.fromisoformat(row["session_date"]) <= cutoff]
    sessions = sorted({row["session_date"] for row in eligible})
    return {
        "data_cutoff": manifest["data_cutoff"],
        "validation_start_date": manifest["validation_start_date"],
        "validation_v2_sessions": sessions,
        "validation_v2_session_count": len(sessions),
        "pre_cutoff_row_count": len(pre_cutoff),
        "append_each_completed_session_once": True,
        "review_schedule_sessions": manifest["review_schedule_sessions"],
        "evidence_status": "insufficient_sample",
        "research_only": True,
        "signal_allowed": False,
    }
