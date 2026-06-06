"""Local-only QuikStrike HTTP/API login probe.

This module is intentionally a probe, not a production extractor. It may use
runtime credentials in memory, but it persists only sanitized request/response
metadata and never writes cookies, headers, tokens, viewstate, full URLs,
credentials, request bodies, or response bodies.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urljoin, urlparse

import httpx

DEFAULT_QUIKSTRIKE_START_URL = (
    "https://cmegroup-sso.quikstrike.net//User/QuikStrikeView.aspx?mode="
)
DEFAULT_API_PROBE_TIMEOUT_SECONDS = 30.0
SENSITIVE_KEY_PATTERN = re.compile(
    r"auth|bearer|cookie|credential|eventvalidation|key|password|secret|session|"
    r"ticket|token|username|viewstate",
    re.IGNORECASE,
)
OPAQUE_PATH_SEGMENT_PATTERN = re.compile(r"^[A-Za-z0-9_-]{24,}$")
USERNAME_FIELD_PATTERN = re.compile(r"user|email|login", re.IGNORECASE)
PASSWORD_FIELD_PATTERN = re.compile(r"pass", re.IGNORECASE)
API_HINT_PATTERN = re.compile(
    r"api|ajax|json|service|handler|data|quote|matrix|vol|interest|openinterest|"
    r"BatchLoadCommand|QuikScript",
    re.IGNORECASE,
)
QUIKSTRIKE_READY_PATTERN = re.compile(
    r"QUIKOPTIONS|OPEN INTEREST|QuikStrike|Gold\s*\(OG\|GC\)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class QuikStrikeApiProbeCredentials:
    username: str
    password: str


class QuikStrikeApiProbeError(RuntimeError):
    """Raised when the API probe cannot be completed."""


def default_api_probe_path(*, repo_backend_dir: Path) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    return (
        repo_backend_dir
        / "data"
        / "reports"
        / "quikstrike_api_probe"
        / f"api_probe_{timestamp}.json"
    )


def run_quikstrike_api_probe(
    *,
    credentials: QuikStrikeApiProbeCredentials,
    start_url: str = DEFAULT_QUIKSTRIKE_START_URL,
    max_login_steps: int = 8,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Attempt local HTTP login and authenticated QuikStrike reachability."""

    if not credentials.username or not credentials.password:
        raise QuikStrikeApiProbeError("username and password are required")
    own_client = client is None
    http_client = client or httpx.Client(
        follow_redirects=True,
        timeout=DEFAULT_API_PROBE_TIMEOUT_SECONDS,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    steps: list[dict[str, Any]] = []
    try:
        response = _request(http_client, "GET", start_url, steps=steps)
        login_steps = 0
        while login_steps < max_login_steps:
            page = response.text
            if _looks_authenticated(page):
                break
            form = _select_login_form(page)
            if form is None:
                break
            action = urljoin(str(response.url), form.action or str(response.url))
            payload = _login_payload(form, credentials)
            response = _request(
                http_client,
                form.method,
                action,
                steps=steps,
                data=payload,
                submitted_form=_form_summary(form),
            )
            login_steps += 1

        final_response = _request(http_client, "GET", start_url, steps=steps)
        ready = _looks_authenticated(final_response.text)
        api_candidates = _discover_api_candidates(
            final_response.text,
            base_url=str(final_response.url),
        )
        report = {
            "report_kind": "quikstrike_api_login_probe",
            "created_at": datetime.now(UTC).isoformat(),
            "status": "authenticated_page_reachable" if ready else "blocked_or_unverified",
            "authenticated_page_reachable": ready,
            "login_step_count": login_steps,
            "request_step_count": len(steps),
            "steps": steps,
            "api_candidate_count": len(api_candidates),
            "api_candidates": api_candidates[:50],
            "sanitization_policy": _sanitization_policy(),
            "limitations": [
                "This probe tests HTTP form-login reachability only.",
                "It does not persist cookies, headers, request bodies, response bodies, "
                "viewstate values, credentials, full URLs, screenshots, or HAR files.",
                "Authenticated page reachability does not prove that QuikStrike chart data "
                "can be extracted through a stable documented API.",
                "API candidates are sanitized host/path hints discovered from authenticated "
                "HTML, not replay instructions.",
            ],
        }
        _assert_sanitized_report(report)
        return report
    finally:
        if own_client:
            http_client.close()


def write_api_probe_report(report: Mapping[str, Any], output_path: Path) -> Path:
    _assert_sanitized_report(report)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return output_path


def _request(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    steps: list[dict[str, Any]],
    data: Mapping[str, str] | None = None,
    submitted_form: Mapping[str, Any] | None = None,
) -> httpx.Response:
    response = client.request(method.upper(), url, data=data)
    response.raise_for_status()
    steps.append(
        {
            "method": method.upper(),
            "location": _sanitize_location(str(response.url)),
            "status_code": response.status_code,
            "redirect_count": len(response.history),
            "content_type": _safe_content_type(response.headers.get("content-type")),
            "content_length": len(response.content),
            "has_login_form": _select_login_form(response.text) is not None,
            "has_quikstrike_marker": _looks_authenticated(response.text),
            "submitted_form": dict(submitted_form or {}),
        }
    )
    return response


def _looks_authenticated(html: str) -> bool:
    return bool(QUIKSTRIKE_READY_PATTERN.search(html or ""))


def _discover_api_candidates(html: str, *, base_url: str) -> list[dict[str, Any]]:
    parser = _LinkAndScriptParser()
    parser.feed(html or "")
    candidates: list[dict[str, Any]] = []
    for value in parser.values:
        if not API_HINT_PATTERN.search(value):
            continue
        absolute = urljoin(base_url, value)
        sanitized = _sanitize_location(absolute)
        if sanitized not in candidates:
            candidates.append(sanitized)
    return candidates


def _select_login_form(html: str) -> _HtmlForm | None:
    parser = _FormParser()
    parser.feed(html or "")
    candidates = [form for form in parser.forms if form.has_password()]
    if candidates:
        return candidates[0]
    candidates = [form for form in parser.forms if form.username_field()]
    return candidates[0] if candidates else None


def _login_payload(
    form: _HtmlForm,
    credentials: QuikStrikeApiProbeCredentials,
) -> dict[str, str]:
    payload: dict[str, str] = {}
    for field in form.inputs:
        name = field.get("name")
        if not name:
            continue
        input_type = field.get("type", "text").lower()
        value = field.get("value", "")
        if input_type in {"submit", "button", "image", "file"}:
            continue
        payload[name] = value

    username_field = form.username_field()
    password_field = form.password_field()
    if username_field:
        payload[username_field] = credentials.username
    if password_field:
        payload[password_field] = credentials.password
    return payload


def _form_summary(form: _HtmlForm) -> dict[str, Any]:
    return {
        "method": form.method,
        "field_count": len([field for field in form.inputs if field.get("name")]),
        "has_username_field": form.username_field() is not None,
        "has_password_field": form.password_field() is not None,
        "hidden_field_count": len(
            [
                field
                for field in form.inputs
                if str(field.get("type", "")).lower() == "hidden" and field.get("name")
            ]
        ),
    }


def _sanitization_policy() -> dict[str, bool]:
    return {
        "stores_credentials": False,
        "stores_cookies": False,
        "stores_headers": False,
        "stores_request_bodies": False,
        "stores_response_bodies": False,
        "stores_har": False,
        "stores_full_locations": False,
        "stores_query_values": False,
        "stores_viewstate": False,
    }


def _sanitize_location(value: str) -> dict[str, Any]:
    parsed = urlparse(value)
    query_keys: list[str] = []
    redacted_query_key_count = 0
    for key, _value in parse_qsl(parsed.query, keep_blank_values=True):
        if SENSITIVE_KEY_PATTERN.search(key):
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
        if SENSITIVE_KEY_PATTERN.search(segment) or OPAQUE_PATH_SEGMENT_PATTERN.match(segment):
            safe_segments.append(":redacted")
        else:
            safe_segments.append(segment[:120])
    return "/".join(safe_segments)


def _safe_content_type(value: str | None) -> str:
    if not value:
        return ""
    return value.split(";", 1)[0].strip().lower()[:80]


def _assert_sanitized_report(report: Mapping[str, Any]) -> None:
    serialized = json.dumps(report, sort_keys=True)
    forbidden_patterns = (
        r"\bAuthorization\s*:",
        r"\bCookie\s*:",
        r"\bSet-Cookie\s*:",
        r"\bBearer\s+[A-Za-z0-9._-]+",
        r"__VIEWSTATE",
        r"__EVENTVALIDATION",
    )
    for pattern in forbidden_patterns:
        if re.search(pattern, serialized, re.IGNORECASE):
            raise QuikStrikeApiProbeError("sanitized API probe report contains sensitive data")


@dataclass(frozen=True)
class _HtmlForm:
    method: str
    action: str
    inputs: list[dict[str, str]]

    def username_field(self) -> str | None:
        for field in self.inputs:
            name = field.get("name", "")
            input_type = field.get("type", "text")
            if input_type.lower() == "hidden":
                continue
            if USERNAME_FIELD_PATTERN.search(name):
                return name
        return None

    def password_field(self) -> str | None:
        for field in self.inputs:
            name = field.get("name", "")
            input_type = field.get("type", "")
            if input_type.lower() == "password" or PASSWORD_FIELD_PATTERN.search(name):
                return name
        return None

    def has_password(self) -> bool:
        return self.password_field() is not None


class _FormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.forms: list[_HtmlForm] = []
        self._form_attrs: dict[str, str] | None = None
        self._inputs: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized = tag.lower()
        attr_map = {key.lower(): value or "" for key, value in attrs}
        if normalized == "form":
            self._form_attrs = attr_map
            self._inputs = []
            return
        if self._form_attrs is not None and normalized in {"input", "button"}:
            self._inputs.append(attr_map)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "form" or self._form_attrs is None:
            return
        self.forms.append(
            _HtmlForm(
                method=self._form_attrs.get("method", "GET").upper() or "GET",
                action=self._form_attrs.get("action", ""),
                inputs=list(self._inputs),
            )
        )
        self._form_attrs = None
        self._inputs = []


class _LinkAndScriptParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.values: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for key, value in attrs:
            if key.lower() in {"href", "src", "action"} and value:
                self.values.append(value)

    def handle_data(self, data: str) -> None:
        for match in re.finditer(r"['\"]([^'\"]{1,240})['\"]", data or ""):
            value = match.group(1)
            if "/" in value or API_HINT_PATTERN.search(value):
                self.values.append(value)
