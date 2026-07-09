from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FORBIDDEN_BROWSER_CAPTURE_MATERIAL = (
    "cookies",
    "headers",
    "cf_clearance",
    "auth tokens",
    "csrf tokens",
    "browser session material",
)


def save_browser_json_response(payload: Any, output_path: Path) -> Path:
    """Persist only a sanitized JSON response body captured by the user-controlled browser."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_path
