from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from src.xau_ft2_candidate.policy import load_candidate_policy


def integrity_hash(payload: dict[str, Any]) -> str:
    canonical = dict(payload)
    canonical.pop("engine_hash", None)
    encoded = json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def load_integrity_policy(
    path: Path,
    *,
    candidate_policy_path: Path,
) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("engine_hash") != integrity_hash(payload):
        raise ValueError("FT2 integrity engine hash does not match its rules")
    candidate = load_candidate_policy(candidate_policy_path)
    if payload.get("candidate_id") != candidate["candidate_id"]:
        raise ValueError("FT2 integrity candidate id does not match frozen candidate")
    if payload.get("candidate_hash") != candidate["candidate_hash"]:
        raise ValueError("FT2 integrity candidate hash does not match frozen candidate")
    return payload


def synchronized_reference_accepted(
    plan: Any | None,
    *,
    maximum_gap_seconds: float,
) -> bool:
    return (
        plan is not None
        and plan.closed_bar_status == "closed"
        and 0 <= plan.source_gap_seconds <= maximum_gap_seconds
    )
