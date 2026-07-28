from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def load_policy(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = payload.get("policy_hash")
    actual = policy_hash(payload)
    if expected != actual:
        raise ValueError(
            "Tiered manual-signal policy hash mismatch; create a new policy "
            f"version instead of editing v1 (expected={expected}, actual={actual})."
        )
    return payload


def policy_hash(payload: dict[str, Any]) -> str:
    canonical = dict(payload)
    canonical.pop("policy_hash", None)
    encoded = json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
