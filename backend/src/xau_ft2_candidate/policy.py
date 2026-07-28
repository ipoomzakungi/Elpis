from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def load_candidate_policy(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = payload.get("candidate_hash")
    actual = candidate_hash(payload)
    if expected != actual:
        raise ValueError(
            "FT2 candidate hash mismatch; create a new candidate version instead "
            f"of editing v1 (expected={expected}, actual={actual})."
        )
    return payload


def candidate_hash(payload: dict[str, Any]) -> str:
    canonical = dict(payload)
    canonical.pop("candidate_hash", None)
    encoded = json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
