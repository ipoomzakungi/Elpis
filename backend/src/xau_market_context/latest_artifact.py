from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def find_latest_fusion_report(root: Path) -> Path | None:
    candidates: list[tuple[datetime, Path]] = []
    if not root.exists():
        return None
    for folder in root.iterdir():
        if not folder.is_dir():
            continue
        if not _is_valid_fusion_folder(folder):
            continue
        created_at = _created_at_from_json(folder / "metadata.json")
        if created_at is None:
            created_at = _created_at_from_json(folder / "report.json")
        if created_at is None:
            try:
                created_at = datetime.fromtimestamp(folder.stat().st_mtime, tz=UTC)
            except OSError:
                continue
        candidates.append((created_at, folder))
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


def find_latest_price_bars(root: Path, symbol_hint: str = "xau") -> Path | None:
    if not root.exists():
        return None
    supported_suffixes = {".csv", ".json"}
    preferred_tokens = (
        symbol_hint.lower(),
        "xau",
        "xauusd",
        "go",
        "gold",
        "1m",
    )
    candidates: list[tuple[int, float, Path]] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in supported_suffixes:
            continue
        normalized_name = path.name.lower()
        score = sum(1 for token in preferred_tokens if token and token in normalized_name)
        try:
            modified = path.stat().st_mtime
        except OSError:
            continue
        candidates.append((score, modified, path))
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item[0], item[1]))[2]


def _is_valid_fusion_folder(folder: Path) -> bool:
    fused_rows_path = folder / "fused_rows.json"
    report_path = folder / "report.json"
    if fused_rows_path.exists():
        try:
            payload = json.loads(fused_rows_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        return isinstance(payload, list)
    if report_path.exists():
        try:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        return isinstance(payload, dict)
    return False


def _created_at_from_json(path: Path) -> datetime | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return _parse_created_at(payload)


def _parse_created_at(payload: Any) -> datetime | None:
    if not isinstance(payload, dict):
        return None
    for key in ("created_at", "completed_at", "capture_time", "timestamp"):
        value = payload.get(key)
        if value:
            parsed = _parse_datetime(value)
            if parsed is not None:
                return parsed
    nested = payload.get("metadata")
    if isinstance(nested, dict):
        return _parse_created_at(nested)
    return None


def _parse_datetime(value: Any) -> datetime | None:
    try:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed
