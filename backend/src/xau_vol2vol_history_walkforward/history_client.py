from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from src.config import get_settings
from src.models.xau_vol2vol_history_walkforward import XauHistorySourceMode


@dataclass(frozen=True)
class XauHistoryLoadResult:
    payloads: list[Any] = field(default_factory=list)
    source_paths: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def load_history_payloads(
    *,
    source_mode: XauHistorySourceMode,
    session_date_from: date,
    session_date_to: date,
    history_file: Path | None = None,
    history_folder: Path | None = None,
    endpoint_template: str | None = None,
    cache_root: Path | None = None,
    rate_limit_seconds: float = 1.0,
) -> XauHistoryLoadResult:
    if source_mode == XauHistorySourceMode.LOCAL_FILE:
        if history_file is None:
            return XauHistoryLoadResult(warnings=["history_file is required for local_file mode."])
        return _load_files([history_file])
    if source_mode == XauHistorySourceMode.LOCAL_FOLDER:
        if history_folder is None:
            return XauHistoryLoadResult(
                warnings=["history_folder is required for local_folder mode."]
            )
        return _load_files(sorted(history_folder.rglob("*.json")))
    if source_mode == XauHistorySourceMode.HTTP_ENDPOINT:
        if not endpoint_template:
            return XauHistoryLoadResult(
                warnings=["history_endpoint_template is required for http_endpoint mode."]
            )
        return _fetch_range(
            session_date_from=session_date_from,
            session_date_to=session_date_to,
            endpoint_template=endpoint_template,
            cache_root=cache_root,
            rate_limit_seconds=rate_limit_seconds,
        )
    if source_mode == XauHistorySourceMode.LATEST_EXISTING:
        root = history_folder or (_default_imports_root() / "vol2vol_history")
        files = sorted(root.rglob("raw.json"), key=lambda path: path.stat().st_mtime, reverse=True)
        return _load_files(files[:1]) if files else XauHistoryLoadResult(
            warnings=[f"No cached Vol2Vol history files found under {root}."]
        )
    return XauHistoryLoadResult(warnings=["Vol2Vol history source mode is unavailable."])


def _load_files(files: list[Path]) -> XauHistoryLoadResult:
    payloads: list[Any] = []
    warnings: list[str] = []
    source_paths: list[Path] = []
    for path in files:
        try:
            payloads.append(json.loads(path.read_text(encoding="utf-8")))
            source_paths.append(path)
        except (OSError, json.JSONDecodeError) as exc:
            warnings.append(f"Could not load {path}: {exc}")
    if not payloads:
        warnings.append("No Vol2Vol history payloads were loaded.")
    return XauHistoryLoadResult(payloads=payloads, source_paths=source_paths, warnings=warnings)


def _fetch_range(
    *,
    session_date_from: date,
    session_date_to: date,
    endpoint_template: str,
    cache_root: Path | None,
    rate_limit_seconds: float,
) -> XauHistoryLoadResult:
    root = cache_root or (_default_imports_root() / "vol2vol_history")
    payloads: list[Any] = []
    source_paths: list[Path] = []
    warnings: list[str] = []
    current = session_date_from
    while current <= session_date_to:
        url = _format_url(endpoint_template, current)
        target = root / current.isoformat() / "raw.json"
        try:
            payload = _fetch_json(url)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            warnings.append(f"{current.isoformat()} fetch failed: {exc}")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            payloads.append(payload)
            source_paths.append(target)
        if rate_limit_seconds > 0:
            time.sleep(rate_limit_seconds)
        current += timedelta(days=1)
    if not payloads:
        warnings.append("No HTTP Vol2Vol history payloads were fetched.")
    return XauHistoryLoadResult(payloads=payloads, source_paths=source_paths, warnings=warnings)


def _format_url(template: str, session_date: date) -> str:
    month = session_date.strftime("%Y-%m")
    return template.format(session_date=session_date.isoformat(), target_month=month)


def _fetch_json(url: str) -> Any:
    request = Request(url, headers={"User-Agent": "Elpis research data client"})
    with urlopen(request, timeout=30) as response:  # noqa: S310 - user-configured public source.
        return json.loads(response.read().decode("utf-8"))


def _default_imports_root() -> Path:
    return get_settings().data_reports_path.parent / "imports"
