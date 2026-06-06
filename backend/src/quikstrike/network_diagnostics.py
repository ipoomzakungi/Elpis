"""Sanitized browser-level network diagnostics for QuikStrike research runs.

This module records only browser Performance Resource Timing metadata. It does
not store headers, cookies, request bodies, response bodies, HAR files, full
URLs, viewstate values, screenshots, or replay material.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlparse

SENSITIVE_QUERY_KEY_PATTERN = re.compile(
    r"auth|bearer|cookie|credential|eventvalidation|key|password|secret|session|"
    r"ticket|token|username|viewstate",
    re.IGNORECASE,
)
OPAQUE_PATH_SEGMENT_PATTERN = re.compile(r"^[A-Za-z0-9_-]{24,}$")
API_HINT_PATTERN = re.compile(
    r"api|ajax|json|service|handler|data|quote|matrix|vol|interest|openinterest|"
    r"\.asmx$|\.ashx$|\.svc$",
    re.IGNORECASE,
)
STATIC_ASSET_PATTERN = re.compile(
    r"\.(css|gif|ico|jpg|jpeg|js|map|png|svg|ttf|woff|woff2)$",
    re.IGNORECASE,
)
DOCUMENT_LIKE_PATTERN = re.compile(r"\.(aspx|asp|html|htm)$", re.IGNORECASE)


class QuikStrikeNetworkDiagnosticsUnavailableError(RuntimeError):
    """Raised when Playwright is unavailable for diagnostics collection."""


def collect_browser_network_diagnostics(
    *,
    cdp_url: str,
    phase: str,
) -> dict[str, Any]:
    """Collect sanitized resource timing entries from all CDP browser pages."""

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - exercised without optional dep
        raise QuikStrikeNetworkDiagnosticsUnavailableError(
            "Install the optional browser dependency with: pip install -e .[browser]"
        ) from exc

    collected_at = datetime.now(UTC).isoformat()
    pages: list[dict[str, Any]] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(cdp_url)
        for context_index, context in enumerate(browser.contexts):
            for page_index, page in enumerate(context.pages):
                pages.append(
                    _sanitize_page_snapshot(
                        _evaluate_page_resource_snapshot(page),
                        context_index=context_index,
                        page_index=page_index,
                    )
                )
    return {
        "phase": phase,
        "collected_at": collected_at,
        "page_count": len(pages),
        "pages": pages,
    }


def build_network_diagnostics_report(
    snapshots: Sequence[Mapping[str, Any]],
    *,
    analyze: bool = True,
) -> dict[str, Any]:
    """Build a persisted diagnostics report from sanitized snapshots."""

    clean_snapshots = [dict(snapshot) for snapshot in snapshots]
    report: dict[str, Any] = {
        "report_kind": "quikstrike_browser_network_diagnostics",
        "created_at": datetime.now(UTC).isoformat(),
        "sanitization_policy": {
            "stores_headers": False,
            "stores_cookies": False,
            "stores_request_bodies": False,
            "stores_response_bodies": False,
            "stores_har": False,
            "stores_full_locations": False,
            "stores_query_values": False,
            "stores_viewstate": False,
        },
        "snapshots": clean_snapshots,
        "limitations": [
            "Browser Performance Resource Timing can identify host/path/resource patterns.",
            "It cannot prove endpoint replayability because headers, cookies, bodies, "
            "viewstate, and full locations are intentionally excluded.",
            "Use observed API candidates only for documented-public-API research, not "
            "endpoint replay.",
        ],
    }
    if analyze:
        report["analysis"] = analyze_network_diagnostics(clean_snapshots)
    return report


def analyze_network_diagnostics(snapshots: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Summarize whether browser traffic suggests API-only feasibility."""

    resources = list(_iter_resources(snapshots))
    host_count = len({resource.get("host") for resource in resources if resource.get("host")})
    xhr_fetch = [
        resource
        for resource in resources
        if resource.get("initiator_type") in {"fetch", "xmlhttprequest"}
    ]
    api_candidates = [resource for resource in resources if resource.get("api_candidate")]
    document_like = [resource for resource in resources if resource.get("document_like")]
    postback_like = [
        resource
        for resource in resources
        if resource.get("document_like")
        and resource.get("initiator_type") in {"navigation", "other"}
    ]
    candidate_paths = sorted(
        {
            f"{resource.get('host', '')}{resource.get('path', '')}"
            for resource in api_candidates
            if resource.get("host") and resource.get("path")
        }
    )[:50]
    assessment = _assess_api_only_feasibility(
        xhr_fetch_count=len(xhr_fetch),
        api_candidate_count=len(api_candidates),
        document_like_count=len(document_like),
        postback_like_count=len(postback_like),
    )
    return {
        "resource_count": len(resources),
        "host_count": host_count,
        "xhr_fetch_count": len(xhr_fetch),
        "api_candidate_count": len(api_candidates),
        "document_like_count": len(document_like),
        "postback_like_count": len(postback_like),
        "candidate_host_paths": candidate_paths,
        "api_only_assessment": assessment,
        "recommended_next_step": (
            "Inspect candidate host/path names for official documented APIs. Keep browser "
            "automation as the supported path unless a documented public API can supply the "
            "same Vol2Vol and Matrix fields without private session replay."
        ),
    }


def write_network_diagnostics_report(
    report: Mapping[str, Any],
    output_path: Path,
) -> Path:
    """Write a diagnostics report to a local ignored artifact path."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return output_path


def default_network_diagnostics_path(*, repo_backend_dir: Path) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    return (
        repo_backend_dir
        / "data"
        / "reports"
        / "quikstrike_network_diag"
        / f"network_diag_{timestamp}.json"
    )


def _evaluate_page_resource_snapshot(page: Any) -> Mapping[str, Any]:
    return page.evaluate(
        """
        () => {
          const nav = performance.getEntriesByType("navigation")[0];
          const resources = performance.getEntriesByType("resource");
          const entryPayload = (entry) => ({
            name: String(entry.name || ""),
            initiatorType: String(entry.initiatorType || ""),
            duration: Number.isFinite(entry.duration) ? entry.duration : null,
            transferSize: Number.isFinite(entry.transferSize) ? entry.transferSize : null,
            encodedBodySize: Number.isFinite(entry.encodedBodySize) ? entry.encodedBodySize : null,
            decodedBodySize: Number.isFinite(entry.decodedBodySize) ? entry.decodedBodySize : null,
            responseStatus: Number.isFinite(entry.responseStatus) ? entry.responseStatus : null
          });
          return {
            title: String(document.title || ""),
            location: String(window.location.href || ""),
            navigation: nav ? entryPayload(nav) : null,
            resources: Array.from(resources).map(entryPayload)
          };
        }
        """
    )


def _sanitize_page_snapshot(
    snapshot: Mapping[str, Any],
    *,
    context_index: int,
    page_index: int,
) -> dict[str, Any]:
    resources = snapshot.get("resources")
    if not isinstance(resources, Sequence) or isinstance(resources, (str, bytes, bytearray)):
        resources = []
    sanitized_resources = [
        _sanitize_resource_entry(resource)
        for resource in resources
        if isinstance(resource, Mapping)
    ]
    return {
        "context_index": context_index,
        "page_index": page_index,
        "title_hint": _safe_title(snapshot.get("title")),
        "page_location": _sanitize_location(snapshot.get("location")),
        "navigation": _sanitize_resource_entry(snapshot.get("navigation")),
        "resource_count": len(sanitized_resources),
        "resources": sanitized_resources,
    }


def _sanitize_resource_entry(entry: object) -> dict[str, Any] | None:
    if not isinstance(entry, Mapping):
        return None
    location = _sanitize_location(entry.get("name"))
    path = str(location.get("path") or "")
    initiator_type = str(entry.get("initiatorType") or entry.get("initiator_type") or "unknown")
    api_candidate = _is_api_candidate(path=path, initiator_type=initiator_type)
    document_like = bool(DOCUMENT_LIKE_PATTERN.search(path))
    return {
        "host": location.get("host"),
        "path": path,
        "query_keys": location.get("query_keys", []),
        "query_key_count": location.get("query_key_count", 0),
        "redacted_query_key_count": location.get("redacted_query_key_count", 0),
        "initiator_type": initiator_type,
        "status": _optional_int(entry.get("responseStatus")),
        "duration_ms": _optional_float(entry.get("duration")),
        "transfer_size": _optional_int(entry.get("transferSize")),
        "encoded_body_size": _optional_int(entry.get("encodedBodySize")),
        "decoded_body_size": _optional_int(entry.get("decodedBodySize")),
        "static_asset": bool(STATIC_ASSET_PATTERN.search(path)),
        "document_like": document_like,
        "api_candidate": api_candidate,
    }


def _sanitize_location(value: object) -> dict[str, Any]:
    parsed = urlparse(str(value or ""))
    query_keys: list[str] = []
    redacted_query_key_count = 0
    for key, _value in parse_qsl(parsed.query, keep_blank_values=True):
        if SENSITIVE_QUERY_KEY_PATTERN.search(key):
            redacted_query_key_count += 1
            continue
        query_keys.append(key)
    return {
        "scheme": parsed.scheme if parsed.scheme in {"http", "https"} else "",
        "host": parsed.netloc,
        "path": _redact_path(parsed.path),
        "query_keys": sorted(set(query_keys)),
        "query_key_count": len(query_keys) + redacted_query_key_count,
        "redacted_query_key_count": redacted_query_key_count,
    }


def _redact_path(path: str) -> str:
    safe_segments: list[str] = []
    for segment in path.split("/"):
        if not segment:
            safe_segments.append(segment)
            continue
        if (
            SENSITIVE_QUERY_KEY_PATTERN.search(segment)
            or OPAQUE_PATH_SEGMENT_PATTERN.match(segment)
        ):
            safe_segments.append(":redacted")
        else:
            safe_segments.append(segment[:120])
    return "/".join(safe_segments)


def _safe_title(value: object) -> str:
    return " ".join(str(value or "").split())[:160]


def _optional_int(value: object) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: object) -> float | None:
    try:
        if value is None:
            return None
        return round(float(value), 3)
    except (TypeError, ValueError):
        return None


def _is_api_candidate(*, path: str, initiator_type: str) -> bool:
    if initiator_type in {"fetch", "xmlhttprequest"}:
        return True
    if STATIC_ASSET_PATTERN.search(path):
        return False
    return bool(API_HINT_PATTERN.search(path))


def _iter_resources(snapshots: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    resources: list[Mapping[str, Any]] = []
    for snapshot in snapshots:
        pages = snapshot.get("pages")
        if not isinstance(pages, Sequence) or isinstance(pages, (str, bytes, bytearray)):
            continue
        for page in pages:
            if not isinstance(page, Mapping):
                continue
            page_resources = page.get("resources")
            if not isinstance(page_resources, Sequence) or isinstance(
                page_resources, (str, bytes, bytearray)
            ):
                continue
            resources.extend(
                resource for resource in page_resources if isinstance(resource, Mapping)
            )
    return resources


def _assess_api_only_feasibility(
    *,
    xhr_fetch_count: int,
    api_candidate_count: int,
    document_like_count: int,
    postback_like_count: int,
) -> str:
    if xhr_fetch_count == 0 and api_candidate_count == 0:
        return (
            "No browser-visible XHR/fetch or API-like resources were observed. Based on "
            "sanitized browser metadata only, API-only capture is not supported by this run."
        )
    if postback_like_count > 0 and xhr_fetch_count == 0:
        return (
            "API-like paths were observed, but traffic appears dominated by document or "
            "postback-style browser pages. Browser automation remains the defensible path."
        )
    if xhr_fetch_count > 0:
        return (
            "XHR/fetch API candidates were observed, but replayability is unproven because "
            "session headers, cookies, bodies, viewstate, and full locations are intentionally "
            "not captured. Treat API-only capture as possible only after documented-public-API "
            "verification."
        )
    if document_like_count > 0:
        return (
            "Some API-like host/path names were observed alongside document pages. The evidence "
            "is insufficient for API-only capture without official API documentation."
        )
    return "Sanitized network metadata is inconclusive for API-only capture."
