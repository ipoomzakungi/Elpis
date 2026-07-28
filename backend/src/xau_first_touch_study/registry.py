from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def load_registry(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = payload.get("experiment_hash")
    actual = registry_hash(payload)
    if expected != actual:
        raise ValueError(
            "First-touch registry hash mismatch; create a new registry version "
            f"instead of editing v1 (expected={expected}, actual={actual})."
        )
    return payload


def registry_hash(payload: dict[str, Any]) -> str:
    canonical = dict(payload)
    canonical.pop("experiment_hash", None)
    encoded = json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
