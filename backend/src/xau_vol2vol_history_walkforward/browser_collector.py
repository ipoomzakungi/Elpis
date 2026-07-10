from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from src.xau_vol2vol_history_walkforward.collection_manifest import (
    Vol2VolCollectionManifest,
    Vol2VolCollectionRow,
    Vol2VolCollectionStatus,
    atomic_write_json,
    atomic_write_text,
    inspect_payload,
)
from src.xau_vol2vol_history_walkforward.data_lake import daily_raw_path


@dataclass(frozen=True)
class Vol2VolBrowserCollectionConfig:
    cdp_url: str
    base_url: str
    output_root: Path
    session_date: date | None = None
    all_available: bool = False
    refresh: bool = False
    include_current_incomplete_session: bool = False
    dry_run: bool = False
    min_delay_seconds: float = 1.5
    max_retries: int = 3
    timezone: str = "Asia/Bangkok"


class Vol2VolBrowserCollector:
    def __init__(self, config: Vol2VolBrowserCollectionConfig) -> None:
        self.config = config
        parsed = urlparse(config.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("base_url must be an absolute HTTP(S) URL")
        if config.min_delay_seconds < 0:
            raise ValueError("min_delay_seconds must be non-negative")
        if config.max_retries < 1:
            raise ValueError("max_retries must be at least 1")

    async def collect(self) -> Vol2VolCollectionManifest:
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise RuntimeError('Install browser support with: pip install -e ".[browser]"') from exc

        playwright = await async_playwright().start()
        try:
            browser = await playwright.chromium.connect_over_cdp(self.config.cdp_url)
            if not browser.contexts:
                raise RuntimeError("The CDP browser has no visible user-controlled context")
            context = browser.contexts[0]
            page = _matching_page(context.pages, self.config.base_url)
            if page is None:
                page = await context.new_page()
            history_url = f"{self.config.base_url.rstrip('/')}/history"
            if not page.url.startswith(self.config.base_url):
                await page.goto(history_url, wait_until="domcontentloaded")
            catalog_payload, _ = await self._fetch_json(page, "/api/vol2vol-history")
            sessions = _catalog_sessions(catalog_payload)
            selected, incomplete = self._select_sessions(sessions)
            catalog = {
                "availableSessions": sessions,
                "advertised_session_count": len(sessions),
                "selected_session_dates": [item["sessionDate"] for item in selected],
                "incomplete_session_dates": sorted(incomplete),
                "collected_at": datetime.now(ZoneInfo(self.config.timezone)).isoformat(),
                "research_only": True,
                "signal_allowed": False,
            }
            if not self.config.dry_run:
                atomic_write_json(
                    self.config.output_root / "catalog" / "available_sessions.json",
                    catalog,
                )
            rows: list[Vol2VolCollectionRow] = []
            for index, session in enumerate(selected):
                session_date = date.fromisoformat(session["sessionDate"])
                path = daily_raw_path(self.config.output_root, session_date)
                if session["sessionDate"] in incomplete:
                    rows.append(
                        Vol2VolCollectionRow(
                            requested_session_date=session_date,
                            returned_session_date=session_date,
                            status=Vol2VolCollectionStatus.INCOMPLETE,
                            snapshot_count=int(session.get("snapshotCount") or 0),
                            warnings=["Current incomplete session excluded by default."],
                        )
                    )
                    continue
                existing = _valid_existing(path, session_date) if not self.config.refresh else None
                if existing is not None:
                    rows.append(existing)
                    continue
                if self.config.dry_run:
                    rows.append(
                        Vol2VolCollectionRow(
                            requested_session_date=session_date,
                            returned_session_date=session_date,
                            status=Vol2VolCollectionStatus.SKIPPED_EXISTING,
                            warnings=["Dry run; no request was collected."],
                            output_path=path.as_posix(),
                        )
                    )
                    continue
                row = await self._collect_date(page, session_date, path)
                rows.append(row)
                if index < len(selected) - 1:
                    await asyncio.sleep(self.config.min_delay_seconds)
            manifest = Vol2VolCollectionManifest(
                advertised_session_count=len(sessions),
                included_session_count=len(selected),
                rows=rows,
            )
            if not self.config.dry_run:
                atomic_write_json(
                    self.config.output_root / "catalog" / "collection_manifest.json",
                    manifest.model_dump(mode="json"),
                )
            return manifest
        finally:
            await playwright.stop()

    async def _collect_date(
        self,
        page: Any,
        session_date: date,
        path: Path,
    ) -> Vol2VolCollectionRow:
        last_warning = ""
        for attempt in range(1, self.config.max_retries + 1):
            try:
                _, body = await self._fetch_json(
                    page,
                    f"/api/vol2vol-history?sessionDate={session_date.isoformat()}",
                )
                _, row = inspect_payload(
                    requested_session_date=session_date,
                    body=body,
                    output_path=path,
                )
                if row.status == Vol2VolCollectionStatus.COLLECTED:
                    atomic_write_text(path, body)
                return row
            except Exception as exc:  # noqa: BLE001 - bounded retries become manifest evidence
                last_warning = _safe_error(exc)
                if attempt < self.config.max_retries:
                    await asyncio.sleep(self.config.min_delay_seconds)
        return Vol2VolCollectionRow(
            requested_session_date=session_date,
            status=Vol2VolCollectionStatus.FAILED,
            warnings=[last_warning or "Vol2Vol collection failed."],
        )

    async def _fetch_json(self, page: Any, path: str) -> tuple[dict[str, Any], str]:
        result = await page.evaluate(
            """async (path) => {
                const response = await fetch(path, {credentials: 'same-origin'});
                const body = await response.text();
                return {ok: response.ok, status: response.status, body};
            }""",
            path,
        )
        if not result["ok"]:
            raise RuntimeError(f"Vol2Vol returned HTTP {result['status']}")
        try:
            payload = json.loads(result["body"])
        except json.JSONDecodeError as exc:
            raise RuntimeError("Vol2Vol returned a non-JSON response") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("Vol2Vol response must be a JSON object")
        return payload, result["body"]

    def _select_sessions(
        self,
        sessions: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], set[str]]:
        today = datetime.now(ZoneInfo(self.config.timezone)).date().isoformat()
        incomplete = {today} if any(item["sessionDate"] == today for item in sessions) else set()
        if self.config.session_date is not None:
            selected = [
                item
                for item in sessions
                if item["sessionDate"] == self.config.session_date.isoformat()
            ]
            if not selected:
                raise ValueError("Requested session date is not advertised by Vol2Vol")
        elif self.config.all_available:
            selected = sessions
        else:
            raise ValueError("Choose --all-available or --session-date")
        if self.config.include_current_incomplete_session:
            incomplete = set()
        return selected, incomplete


def collect_browser_history(config: Vol2VolBrowserCollectionConfig) -> Vol2VolCollectionManifest:
    try:
        return asyncio.run(Vol2VolBrowserCollector(config).collect())
    except (OSError, RuntimeError, ValueError):
        raise
    except Exception as exc:  # noqa: BLE001 - browser failures become sanitized CLI errors
        raise RuntimeError(_safe_error(exc)) from None


def _catalog_sessions(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = payload.get("availableSessions")
    if not isinstance(raw, list):
        raise ValueError("Vol2Vol did not advertise availableSessions")
    sessions: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict) or not item.get("sessionDate"):
            continue
        sessions.append(
            {
                "sessionDate": str(item["sessionDate"])[:10],
                "displayDate": item.get("displayDate"),
                "seriesLabel": item.get("seriesLabel"),
                "label": item.get("label"),
                "snapshotCount": int(item.get("snapshotCount") or 0),
                "latestAt": item.get("latestAt"),
            }
        )
    sessions.sort(key=lambda item: item["sessionDate"])
    if not sessions:
        raise ValueError("Vol2Vol advertised no usable sessions")
    return sessions


def _valid_existing(path: Path, requested: date) -> Vol2VolCollectionRow | None:
    if not path.exists():
        return None
    try:
        body = path.read_text(encoding="utf-8")
        _, inspected = inspect_payload(
            requested_session_date=requested,
            body=body,
            output_path=path,
        )
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if inspected.status != Vol2VolCollectionStatus.COLLECTED:
        return None
    return inspected.model_copy(update={"status": Vol2VolCollectionStatus.SKIPPED_EXISTING})


def _matching_page(pages: list[Any], base_url: str) -> Any | None:
    return next((page for page in pages if page.url.startswith(base_url)), None)


def _safe_error(exc: Exception) -> str:
    text = " ".join(str(exc).split())
    forbidden = ("cookie", "authorization", "cf_clearance", "csrf", "token", "header")
    if any(item in text.lower() for item in forbidden):
        return "Browser collection failed; sensitive diagnostic text was redacted."
    return text[:500]
