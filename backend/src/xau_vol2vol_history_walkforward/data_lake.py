from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class XauVol2VolDataLakeLoadResult:
    payloads: list[Any] = field(default_factory=list)
    source_paths: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def daily_raw_path(root: Path, session_date: date) -> Path:
    return root / "daily" / session_date.isoformat() / "raw.json"


def daily_metadata_path(root: Path, session_date: date) -> Path:
    return root / "daily" / session_date.isoformat() / "collection_meta.json"


def monthly_raw_path(root: Path, target_month: str) -> Path:
    return root / "monthly" / target_month / "raw.json"


def load_vol2vol_data_lake(
    *,
    root: Path,
    session_date_from: date,
    session_date_to: date,
    monthly_target: str | None = None,
) -> XauVol2VolDataLakeLoadResult:
    payloads: list[Any] = []
    source_paths: list[Path] = []
    warnings: list[str] = []
    current = session_date_from
    while current <= session_date_to:
        path = daily_raw_path(root, current)
        if path.exists():
            metadata_path = daily_metadata_path(root, current)
            if _is_incomplete(metadata_path):
                warnings.append(f"Incomplete Vol2Vol daily data-lake file excluded: {path}")
            else:
                _append_payload(path, payloads, source_paths, warnings)
        else:
            warnings.append(f"Missing Vol2Vol daily data-lake file: {path}")
        current += timedelta(days=1)
    if monthly_target:
        path = monthly_raw_path(root, monthly_target)
        if path.exists():
            _append_payload(path, payloads, source_paths, warnings)
        else:
            warnings.append(f"Missing Vol2Vol monthly data-lake file: {path}")
    return XauVol2VolDataLakeLoadResult(
        payloads=payloads,
        source_paths=source_paths,
        warnings=warnings,
    )


def _is_incomplete(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return True
    return payload.get("complete") is False


def _append_payload(
    path: Path,
    payloads: list[Any],
    source_paths: list[Path],
    warnings: list[str],
) -> None:
    try:
        payloads.append(json.loads(path.read_text(encoding="utf-8")))
        source_paths.append(path)
    except (OSError, json.JSONDecodeError) as exc:
        warnings.append(f"Could not load {path}: {exc}")
