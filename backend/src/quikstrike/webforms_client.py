"""HTTP WebForms client for QuikStrike research probes.

This client performs a stateful HTTP login and ASP.NET postback sequence. It
keeps cookies, credentials, and hidden field values in memory only. Persisted
reports must use the sanitized summaries returned by this module, not raw
responses or request bodies.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urljoin, urlparse

import httpx

from src.quikstrike.api_probe import (
DEFAULT_API_PROBE_TIMEOUT_SECONDS,
    DEFAULT_QUIKSTRIKE_START_URL,
)

DEFAULT_WEBFORMS_TIMEOUT_SECONDS = 120.0

SENSITIVE_KEY_PATTERN = re.compile(
    r"auth|bearer|cookie|credential|eventvalidation|key|password|secret|session|"
    r"ticket|token|username|viewstate|saml",
    re.IGNORECASE,
)
OPAQUE_PATH_SEGMENT_PATTERN = re.compile(r"^[A-Za-z0-9_-]{24,}$")

VOL2VOL_EVENT_TARGETS = {
    "intraday_volume": "ctl00$MainContent$ucViewControl_QuikOptionsV2V$lbIntradayVolume",
    "eod_volume": "ctl00$MainContent$ucViewControl_QuikOptionsV2V$lbEODVolume",
    "open_interest": "ctl00$MainContent$ucViewControl_QuikOptionsV2V$lbOI",
    "oi_change": "ctl00$MainContent$ucViewControl_QuikOptionsV2V$lbOIChg",
    "churn": "ctl00$MainContent$ucViewControl_QuikOptionsV2V$lbChurn",
}

MATRIX_EVENT_TARGETS = {
    "open_interest_matrix": "ctl00$MainContent$ucViewControl_OpenInterestV2$lbOIMatrix",
    "oi_change_matrix": "ctl00$MainContent$ucViewControl_OpenInterestV2$lbOIChgMatrix",
    "volume_matrix": "ctl00$MainContent$ucViewControl_OpenInterestV2$lbVolumeMatrix",
}

SUPPLEMENTAL_EVENT_TARGETS = {
    "settlements": "ctl00$MainContent$ucViewControl_OpenInterestV2$lbSettles",
    "futures_volume_oi": "ctl00$MainContent$ucViewControl_OpenInterestV2$lbFutureOI",
}

TOP_NAV_EVENT_TARGETS = {
    "vol2vol": "ctl00$ucMenuBar$lvMenuBar$ctrl7$lbMenuItem",
    "open_interest": "ctl00$ucMenuBar$lvMenuBar$ctrl2$lbMenuItem",
}


@dataclass(frozen=True)
class QuikStrikeWebFormsCredentials:
    username: str
    password: str


class QuikStrikeWebFormsError(RuntimeError):
    """Raised when the HTTP WebForms flow cannot continue."""


class QuikStrikeWebFormsClient:
    """Stateful QuikStrike WebForms client with in-memory session state."""

    def __init__(
        self,
        *,
        credentials: QuikStrikeWebFormsCredentials,
        start_url: str = DEFAULT_QUIKSTRIKE_START_URL,
        client: httpx.Client | None = None,
    ) -> None:
        if not credentials.username or not credentials.password:
            raise QuikStrikeWebFormsError("username and password are required")
        self.credentials = credentials
        self.start_url = start_url
        self._own_client = client is None
        self.client = client or httpx.Client(
            follow_redirects=True,
            timeout=httpx.Timeout(
                DEFAULT_WEBFORMS_TIMEOUT_SECONDS,
                connect=DEFAULT_API_PROBE_TIMEOUT_SECONDS,
            ),
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
                ),
            },
        )
        self.app_url = start_url
        self.hidden_fields: dict[str, str] = {}
        self.form_fields: dict[str, str] = {}
        self.steps: list[dict[str, Any]] = []

    def close(self) -> None:
        if self._own_client:
            self.client.close()

    def __enter__(self) -> QuikStrikeWebFormsClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def login(self) -> None:
        response = self._request("GET", self.start_url, label="initial_get")
        response = self._post_first_form(response, label="saml_to_login")

        xsrf = self._xsrf_token()
        json_headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if xsrf:
            json_headers["X-XSRF-TOKEN"] = xsrf

        self._request(
            "POST",
            "https://login.cmegroup.com/sso/authservice/federatedCheck.action",
            label="federated_check",
            json={"identifier": self.credentials.username},
            headers=json_headers,
        )
        auth_response = self._request(
            "POST",
            "https://login.cmegroup.com/sso/authservice/authenticateCredential.action",
            label="authenticate_credential",
            json={
                "userName": self.credentials.username,
                "password": self.credentials.password,
                "rememberMe": False,
                "captchaResponse": "",
            },
            headers=json_headers,
        )
        auth_payload = _safe_json(auth_response)
        if auth_payload.get("status") != "CREDENTIAL_MATCHES":
            raise QuikStrikeWebFormsError(
                f"QuikStrike SSO credential step returned {auth_payload.get('status')!r}"
            )

        process_response = self._request(
            "GET",
            "https://login.cmegroup.com/sso/accountstatus/processAuth.action",
            label="process_auth",
            headers={"Accept": "application/json", **({"X-XSRF-TOKEN": xsrf} if xsrf else {})},
        )
        process_payload = _safe_json(process_response)
        data = process_payload.get("data") if isinstance(process_payload, Mapping) else None
        if not isinstance(data, Mapping) or not data.get("targetUrl") or not data.get("ref"):
            raise QuikStrikeWebFormsError("QuikStrike SSO processAuth did not return target")

        response = self._request(
            "POST",
            str(data["targetUrl"]),
            label="resume_saml",
            data={"REF": str(data["ref"])},
        )
        response = self._post_first_form(response, label="post_saml_to_quikstrike")
        if "Disclaimer" in response.text or "chkAccept" in response.text:
            response = self._post_disclaimer(response)
        self._capture_form_fields(response.text)
        self._capture_hidden_fields(response.text)
        if not self.hidden_fields.get("__VIEWSTATE"):
            raise QuikStrikeWebFormsError("QuikStrike app page did not expose __VIEWSTATE")
        self.app_url = _resolve_app_url(response)

    def postback(self, *, label: str, event_target: str) -> dict[str, Any]:
        response = self.postback_response(label=label, event_target=event_target)
        return _response_payload_summary(label=label, response=response)

    def postback_response(self, *, label: str, event_target: str) -> httpx.Response:
        if not self.hidden_fields.get("__VIEWSTATE"):
            raise QuikStrikeWebFormsError("login() must complete before postback()")
        payload = dict(self.form_fields)
        payload.update(self.hidden_fields)
        payload["__EVENTTARGET"] = event_target
        payload["__EVENTARGUMENT"] = ""
        payload["__ASYNCPOST"] = "true"
        response = self._request(
            "POST",
            self.app_url,
            label=label,
            data=payload,
            headers={
                "Accept": "*/*",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-MicrosoftAjax": "Delta=true",
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        self._capture_form_fields(response.text)
        self._capture_hidden_fields(response.text)
        return response

    def _xsrf_token(self) -> str:
        token = self.client.cookies.get("XSRF-TOKEN")
        return str(token or "")

    def _request(
        self,
        method: str,
        url: str,
        *,
        label: str,
        data: Mapping[str, str] | None = None,
        json: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        try:
            response = self.client.request(
                method,
                url,
                data=data,
                json=json,
                headers=headers,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise QuikStrikeWebFormsError(
                f"{label}: HTTP {exc.response.status_code} from "
                f"{_sanitize_location(str(exc.response.url))['host']}"
            ) from exc
        except httpx.RequestError as exc:
            raise QuikStrikeWebFormsError(
                f"{label}: HTTP request failed ({type(exc).__name__})"
            ) from exc
        self.steps.append(
            _sanitized_step(
                label=label,
                method=method,
                response=response,
                submitted_field_count=len(data or json or {}),
            )
        )
        return response

    def _post_first_form(self, response: httpx.Response, *, label: str) -> httpx.Response:
        forms = _parse_forms(response.text)
        if not forms:
            raise QuikStrikeWebFormsError(f"{label}: no HTML form was available")
        form = forms[0]
        target_url = urljoin(str(response.url), form.action or str(response.url))
        return self._request(
            form.method,
            target_url,
            label=label,
            data=form.payload(),
            headers=_form_post_headers(str(response.url), target_url, form.method),
        )

    def _post_disclaimer(self, response: httpx.Response) -> httpx.Response:
        forms = _parse_forms(response.text)
        if not forms:
            raise QuikStrikeWebFormsError("QuikStrike disclaimer page had no form")
        payload = forms[0].payload()
        payload["chkAccept"] = "on"
        payload["btnContinue"] = "Continue"
        target_url = urljoin(str(response.url), forms[0].action or str(response.url))
        return self._request(
            "POST",
            target_url,
            label="post_disclaimer",
            data=payload,
            headers=_form_post_headers(str(response.url), target_url, "POST"),
        )

    def _capture_hidden_fields(self, text: str) -> None:
        hidden = _extract_hidden_fields(text)
        if hidden:
            self.hidden_fields.update(hidden)

    def _capture_form_fields(self, text: str) -> None:
        fields = _extract_form_fields(text)
        if fields:
            self.form_fields = fields


def run_webforms_probe(
    *,
    credentials: QuikStrikeWebFormsCredentials,
    start_url: str = DEFAULT_QUIKSTRIKE_START_URL,
    views: Sequence[str] | None = None,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    requested = list(
        views
        or [
            "intraday_volume",
            "eod_volume",
            "open_interest",
            "oi_change",
            "churn",
            "open_interest_matrix",
            "oi_change_matrix",
            "volume_matrix",
        ]
    )
    event_targets = {
        **VOL2VOL_EVENT_TARGETS,
        **MATRIX_EVENT_TARGETS,
        **SUPPLEMENTAL_EVENT_TARGETS,
    }
    unknown_views = sorted(set(requested) - set(event_targets))
    if unknown_views:
        raise QuikStrikeWebFormsError(
            f"unsupported QuikStrike WebForms view(s): {', '.join(unknown_views)}"
        )
    view_summaries: list[dict[str, Any]] = []
    with QuikStrikeWebFormsClient(
        credentials=credentials,
        start_url=start_url,
        client=client,
    ) as webforms:
        webforms.login()
        webforms.postback(label="nav_vol2vol", event_target=TOP_NAV_EVENT_TARGETS["vol2vol"])
        for view in requested:
            if view in MATRIX_EVENT_TARGETS and not any(
                item.get("label") == "nav_open_interest" for item in view_summaries
            ):
                view_summaries.append(
                    webforms.postback(
                        label="nav_open_interest",
                        event_target=TOP_NAV_EVENT_TARGETS["open_interest"],
                    )
                )
            view_summaries.append(
                webforms.postback(label=view, event_target=event_targets[view])
            )
        report = {
            "report_kind": "quikstrike_webforms_api_probe",
            "created_at": datetime.now(UTC).isoformat(),
            "status": "completed",
            "requested_views": requested,
            "completed_views": [
                item["label"]
                for item in view_summaries
                if item.get("label") in requested
            ],
            "login_steps": webforms.steps,
            "view_summaries": view_summaries,
            "sanitization_policy": {
                "stores_credentials": False,
                "stores_cookies": False,
                "stores_headers": False,
                "stores_request_bodies": False,
                "stores_response_bodies": False,
                "stores_full_urls": False,
                "stores_query_values": False,
                "stores_viewstate_values": False,
            },
            "limitations": [
                "This is a stateful ASP.NET WebForms postback probe, not a documented JSON API.",
                "Cookies, credentials, headers, request bodies, raw responses, and viewstate "
                "values are kept in memory only and are not persisted.",
            ],
        }
    _assert_sanitized(report)
    return report


def default_webforms_probe_path(*, repo_backend_dir: Path) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    return (
        repo_backend_dir
        / "data"
        / "reports"
        / "quikstrike_webforms_probe"
        / f"webforms_probe_{timestamp}.json"
    )


def write_webforms_probe_report(report: Mapping[str, Any], output_path: Path) -> Path:
    _assert_sanitized(report)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return output_path


@dataclass(frozen=True)
class _HtmlForm:
    method: str
    action: str
    inputs: list[dict[str, str]]

    def payload(self) -> dict[str, str]:
        payload: dict[str, str] = {}
        for field in self.inputs:
            name = field.get("name")
            if not name:
                continue
            input_type = field.get("type", "text").lower()
            if input_type in {"submit", "button", "image", "file"}:
                continue
            payload[name] = field.get("value", "")
        return payload


class _FormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.forms: list[_HtmlForm] = []
        self._attrs: dict[str, str] | None = None
        self._inputs: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key.lower(): value or "" for key, value in attrs}
        if tag.lower() == "form":
            self._attrs = attr_map
            self._inputs = []
            return
        if self._attrs is not None and tag.lower() in {"input", "button"}:
            self._inputs.append(attr_map)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "form" or self._attrs is None:
            return
        self.forms.append(
            _HtmlForm(
                method=(self._attrs.get("method") or "GET").upper(),
                action=self._attrs.get("action", ""),
                inputs=list(self._inputs),
            )
        )
        self._attrs = None
        self._inputs = []


def _parse_forms(text: str) -> list[_HtmlForm]:
    parser = _FormParser()
    parser.feed(text or "")
    return parser.forms


def _extract_hidden_fields(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for form in _parse_forms(text):
        for field in form.inputs:
            if field.get("type", "").lower() == "hidden" and field.get("name"):
                fields[field["name"]] = field.get("value", "")
    if fields:
        return fields

    # ASP.NET async postbacks return pipe-delimited delta records.
    parts = (text or "").split("|")
    for index, value in enumerate(parts[:-2]):
        if value == "hiddenField":
            fields[parts[index + 1]] = parts[index + 2]
    return fields


class _FormFieldParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.fields: dict[str, str] = {}
        self._select_name = ""
        self._select_value = ""
        self._select_selected = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key.lower(): value or "" for key, value in attrs}
        normalized_tag = tag.lower()
        if normalized_tag == "input":
            name = attr_map.get("name")
            if not name:
                return
            input_type = attr_map.get("type", "text").lower()
            if input_type in {"submit", "button", "image", "file"}:
                return
            if input_type in {"checkbox", "radio"} and "checked" not in attr_map:
                return
            self.fields[name] = attr_map.get("value", "")
            return
        if normalized_tag == "select":
            self._select_name = attr_map.get("name", "")
            self._select_value = ""
            self._select_selected = False
            return
        if normalized_tag == "option" and self._select_name:
            value = attr_map.get("value", "")
            if not self._select_value:
                self._select_value = value
            if "selected" in attr_map:
                self._select_value = value
                self._select_selected = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "select" or not self._select_name:
            return
        self.fields[self._select_name] = self._select_value
        self._select_name = ""
        self._select_value = ""
        self._select_selected = False


def _extract_form_fields(text: str) -> dict[str, str]:
    parser = _FormFieldParser()
    parser.feed(text or "")
    return parser.fields


def _resolve_app_url(response: httpx.Response) -> str:
    forms = _parse_forms(response.text)
    for form in forms:
        if "QuikStrikeView.aspx" in form.action:
            return urljoin(str(response.url), form.action)
    return str(response.url)


def _form_post_headers(referrer: str, target_url: str, method: str) -> dict[str, str]:
    headers = {"Referer": referrer}
    if method.upper() == "POST":
        parsed = urlparse(target_url)
        if parsed.scheme and parsed.netloc:
            headers["Origin"] = f"{parsed.scheme}://{parsed.netloc}"
    return headers


def _response_payload_summary(*, label: str, response: httpx.Response) -> dict[str, Any]:
    text = response.text or ""
    return {
        "label": label,
        "status_code": response.status_code,
        "location": _sanitize_location(str(response.url)),
        "content_type": _safe_content_type(response.headers.get("content-type")),
        "body_length": len(response.content),
        "markers": {
            "has_updatepanel_delta": text.startswith("|") or "|updatePanel|" in text[:1000],
            "has_viewstate": "__VIEWSTATE" in text,
            "has_highcharts": "Highcharts" in text,
            "has_quikoptions_v2v": "QuikOptionsV2V" in text,
            "has_openinterest_v2": "OpenInterestV2" in text,
            "has_matrix_value": "Matrix Value" in text,
            "has_gold": "Gold (OG|GC)" in text,
            "has_intraday_volume": "Intraday Volume" in text,
            "has_eod_volume": "EOD Volume" in text,
            "has_open_interest": "Open Interest" in text,
            "has_oi_change": "Open Interest Change" in text or "OI Change" in text,
            "has_churn": "Churn" in text,
            "has_settlements": "Settlements" in text,
            "has_futures_volume_oi": "Volume & OI" in text,
        },
        "title_hints": _title_hints(text),
    }


def _title_hints(text: str) -> list[str]:
    hints: list[str] = []
    for pattern in (
        r"Gold \(OG\|GC\)[^<|\n]{0,180}",
        r"OG\w+[^<|\n]{0,120}(?:Volume|Open Interest|Churn|Matrix)[^<|\n]{0,120}",
        r"Matrix Value:[^<|\n]{0,120}",
    ):
        for match in re.finditer(pattern, text or ""):
            value = " ".join(match.group(0).split())[:220]
            if value not in hints:
                hints.append(value)
            if len(hints) >= 12:
                return hints
    return hints


def _sanitized_step(
    *,
    label: str,
    method: str,
    response: httpx.Response,
    submitted_field_count: int,
) -> dict[str, Any]:
    text = response.text or ""
    return {
        "label": label,
        "method": method.upper(),
        "status_code": response.status_code,
        "location": _sanitize_location(str(response.url)),
        "redirect_count": len(response.history),
        "content_type": _safe_content_type(response.headers.get("content-type")),
        "content_length": len(response.content),
        "submitted_field_count": submitted_field_count,
        "markers": {
            "has_saml_form": "SAMLResponse" in text or "SAMLRequest" in text,
            "has_disclaimer": "Disclaimer" in text or "chkAccept" in text,
            "has_quikstrike_app": "Gold (OG|GC)" in text or "QUIKOPTIONS" in text,
            "has_viewstate": "__VIEWSTATE" in text,
        },
        "json_status": _json_status(response),
    }


def _json_status(response: httpx.Response) -> str | None:
    if "json" not in _safe_content_type(response.headers.get("content-type")):
        return None
    payload = _safe_json(response)
    value = payload.get("status") or payload.get("viewSelector")
    return str(value)[:120] if value else None


def _safe_json(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


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


def _assert_sanitized(report: Mapping[str, Any]) -> None:
    serialized = json.dumps(report, sort_keys=True)
    forbidden_patterns = (
        r"\bAuthorization\s*:",
        r"\bCookie\s*:",
        r"\bSet-Cookie\s*:",
        r"\bBearer\s+[A-Za-z0-9._-]+",
        r"__VIEWSTATE[^a-z]",
        r"__EVENTVALIDATION[^a-z]",
        r"SAML(Response|Request)",
    )
    for pattern in forbidden_patterns:
        if re.search(pattern, serialized, re.IGNORECASE):
            raise QuikStrikeWebFormsError("sanitized WebForms report contains sensitive data")
