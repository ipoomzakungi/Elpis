"""Normalize QuikStrike WebForms API responses into local research artifacts."""

from __future__ import annotations

import html
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import httpx

from src.models.quikstrike import QuikStrikeViewType, ensure_no_forbidden_quikstrike_content
from src.models.quikstrike_matrix import (
    QuikStrikeMatrixViewType,
    ensure_no_forbidden_quikstrike_matrix_content,
)
from src.quikstrike.conversion import convert_to_xau_vol_oi_rows
from src.quikstrike.extraction import build_extraction_from_request
from src.quikstrike.playwright_local import build_request_from_browser_payloads
from src.quikstrike.report_store import QuikStrikeReportStore
from src.quikstrike.webforms_client import (
    MATRIX_EVENT_TARGETS,
    SUPPLEMENTAL_EVENT_TARGETS,
    TOP_NAV_EVENT_TARGETS,
    VOL2VOL_EVENT_TARGETS,
    QuikStrikeWebFormsClient,
    QuikStrikeWebFormsCredentials,
    QuikStrikeWebFormsError,
    _assert_sanitized,
    _response_payload_summary,
)
from src.quikstrike_matrix.conversion import (
    convert_to_xau_vol_oi_rows as convert_matrix_to_xau_vol_oi_rows,
)
from src.quikstrike_matrix.extraction import (
    build_extraction_from_request as build_matrix_extraction_from_request,
)
from src.quikstrike_matrix.playwright_local import (
    MATRIX_VIEW_LABELS,
)
from src.quikstrike_matrix.playwright_local import (
    build_request_from_browser_payloads as build_matrix_request_from_browser_payloads,
)
from src.quikstrike_matrix.report_store import QuikStrikeMatrixReportStore

VOL2VOL_VIEWS = tuple(VOL2VOL_EVENT_TARGETS)
MATRIX_VIEWS = tuple(MATRIX_EVENT_TARGETS)
DEFAULT_NORMALIZED_VIEWS = (*VOL2VOL_VIEWS, *MATRIX_VIEWS, *SUPPLEMENTAL_EVENT_TARGETS)
SOURCE_LIMITATION = (
    "Captured through authenticated QuikStrike ASP.NET WebForms responses for local "
    "research only; independently verify vendor data before research conclusions."
)


@dataclass(frozen=True)
class WebFormsNormalizedArtifacts:
    digest: dict[str, Any]
    digest_path: Path
    vol2vol_report_id: str | None
    matrix_report_id: str | None


def run_webforms_normalized_fetch(
    *,
    credentials: QuikStrikeWebFormsCredentials,
    start_url: str,
    views: Sequence[str] | None = None,
    output_root: Path | None = None,
    http_client: httpx.Client | None = None,
    vol2vol_store: QuikStrikeReportStore | None = None,
    matrix_store: QuikStrikeMatrixReportStore | None = None,
    overwrite_allowed: bool = False,
) -> WebFormsNormalizedArtifacts:
    requested = _normalize_requested_views(views)
    timestamp = datetime.now(UTC)
    digest_id = f"quikstrike_webforms_normalized_{timestamp.strftime('%Y%m%d_%H%M%S')}"
    vol2vol_payloads: dict[QuikStrikeViewType, Mapping[str, Any]] = {}
    matrix_payloads: dict[QuikStrikeMatrixViewType, Mapping[str, Any]] = {}
    supplemental_payloads: list[dict[str, Any]] = []
    view_summaries: list[dict[str, Any]] = []

    with QuikStrikeWebFormsClient(
        credentials=credentials,
        start_url=start_url,
        client=http_client,
    ) as client:
        client.login()
        if any(view in VOL2VOL_EVENT_TARGETS for view in requested):
            nav_response = client.postback_response(
                label="nav_vol2vol",
                event_target=TOP_NAV_EVENT_TARGETS["vol2vol"],
            )
            view_summaries.append(_view_summary("nav_vol2vol", nav_response))
            for view in [item for item in requested if item in VOL2VOL_EVENT_TARGETS]:
                response = _select_and_load_full_page(
                    client,
                    label=view,
                    event_target=VOL2VOL_EVENT_TARGETS[view],
                )
                summary = _view_summary(view, response)
                try:
                    payload = build_vol2vol_payload_from_webforms_page(
                        response.text,
                        QuikStrikeViewType(view),
                    )
                    vol2vol_payloads[QuikStrikeViewType(view)] = payload
                    summary["normalized_status"] = "completed"
                    summary["normalized_row_source"] = "json_settings"
                except Exception as exc:
                    summary["normalized_status"] = "blocked"
                    summary["blocked_reason"] = _safe_reason(exc)
                view_summaries.append(summary)

        open_interest_views = {**MATRIX_EVENT_TARGETS, **SUPPLEMENTAL_EVENT_TARGETS}
        if any(view in open_interest_views for view in requested):
            nav_response = client.postback_response(
                label="nav_open_interest",
                event_target=TOP_NAV_EVENT_TARGETS["open_interest"],
            )
            view_summaries.append(_view_summary("nav_open_interest", nav_response))

        for view in [item for item in requested if item in MATRIX_EVENT_TARGETS]:
            response = _select_and_load_full_page(
                client,
                label=view,
                event_target=MATRIX_EVENT_TARGETS[view],
            )
            summary = _view_summary(view, response)
            try:
                payload = build_matrix_payload_from_webforms_page(
                    response.text,
                    QuikStrikeMatrixViewType(view),
                )
                matrix_payloads[QuikStrikeMatrixViewType(view)] = payload
                summary["normalized_status"] = "completed"
                summary["normalized_row_source"] = "sanitized_html_table"
            except Exception as exc:
                summary["normalized_status"] = "blocked"
                summary["blocked_reason"] = _safe_reason(exc)
            view_summaries.append(summary)

        for view in [item for item in requested if item in SUPPLEMENTAL_EVENT_TARGETS]:
            response = _select_and_load_full_page(
                client,
                label=view,
                event_target=SUPPLEMENTAL_EVENT_TARGETS[view],
            )
            summary = _view_summary(view, response)
            supplemental = build_supplemental_payload_from_webforms_page(response.text, view)
            supplemental_payloads.append(supplemental)
            summary["normalized_status"] = "completed"
            summary["table_count"] = len(supplemental["tables"])
            view_summaries.append(summary)

    vol2vol_report_id = None
    vol2vol_counts = {"row_count": 0, "conversion_row_count": 0, "status": "not_requested"}
    if vol2vol_payloads:
        request = build_request_from_browser_payloads(vol2vol_payloads)
        extraction = build_extraction_from_request(
            request,
            extraction_id=f"quikstrike_api_{timestamp.strftime('%Y%m%d_%H%M%S')}",
            capture_timestamp=timestamp,
        )
        conversion = convert_to_xau_vol_oi_rows(
            extraction_result=extraction.result,
            rows=extraction.rows,
        )
        report = (vol2vol_store or QuikStrikeReportStore()).persist_report(
            extraction_result=extraction.result,
            normalized_rows=extraction.rows,
            conversion_result=conversion.result,
            conversion_rows=conversion.rows,
            source_kind="operational",
            overwrite_allowed=overwrite_allowed,
        )
        vol2vol_report_id = report.extraction_id
        vol2vol_counts = {
            "row_count": len(extraction.rows),
            "conversion_row_count": len(conversion.rows),
            "status": extraction.result.status.value,
        }

    matrix_report_id = None
    matrix_counts = {"row_count": 0, "conversion_row_count": 0, "status": "not_requested"}
    if matrix_payloads:
        matrix_request = build_matrix_request_from_browser_payloads(matrix_payloads)
        matrix_extraction = build_matrix_extraction_from_request(
            matrix_request,
            extraction_id=f"quikstrike_matrix_api_{timestamp.strftime('%Y%m%d_%H%M%S')}",
        )
        matrix_conversion = convert_matrix_to_xau_vol_oi_rows(
            extraction_result=matrix_extraction.result,
            rows=matrix_extraction.rows,
        )
        matrix_report = (matrix_store or QuikStrikeMatrixReportStore()).persist_report(
            extraction_result=matrix_extraction.result,
            normalized_rows=matrix_extraction.rows,
            conversion_result=matrix_conversion.result,
            conversion_rows=matrix_conversion.rows,
            source_kind="operational",
            overwrite_allowed=overwrite_allowed,
        )
        matrix_report_id = matrix_report.extraction_id
        matrix_counts = {
            "row_count": len(matrix_extraction.rows),
            "conversion_row_count": len(matrix_conversion.rows),
            "status": matrix_extraction.result.status.value,
        }

    digest = {
        "report_kind": "quikstrike_webforms_normalized_digest",
        "digest_id": digest_id,
        "created_at": timestamp.isoformat(),
        "status": "completed",
        "requested_views": requested,
        "completed_views": [
            item["label"]
            for item in view_summaries
            if item["label"] in requested and item.get("normalized_status") == "completed"
        ],
        "vol2vol": {
            "report_id": vol2vol_report_id,
            **vol2vol_counts,
        },
        "matrix": {
            "report_id": matrix_report_id,
            **matrix_counts,
        },
        "supplemental": {
            "view_count": len(supplemental_payloads),
            "views": supplemental_payloads,
        },
        "view_summaries": view_summaries,
        "limitations": [
            SOURCE_LIMITATION,
            "No credentials, cookies, headers, request bodies, response bodies, "
            "viewstate values, SAML values, screenshots, HAR files, or full private URLs "
            "are persisted.",
        ],
    }
    _assert_sanitized(digest)
    ensure_no_forbidden_quikstrike_content(digest)
    ensure_no_forbidden_quikstrike_matrix_content(digest)
    digest_path = write_normalized_digest(
        digest,
        output_root=output_root,
    )
    return WebFormsNormalizedArtifacts(
        digest=digest,
        digest_path=digest_path,
        vol2vol_report_id=vol2vol_report_id,
        matrix_report_id=matrix_report_id,
    )


def build_vol2vol_payload_from_webforms_page(
    text: str,
    view: QuikStrikeViewType,
) -> Mapping[str, Any]:
    settings = extract_json_settings(text)
    chart = _chart_from_json_settings(settings, view)
    header_text = _header_text(text, fallback=chart["chart_title"])
    selector_text = _selector_text(text)
    payload = {
        "header_text": header_text,
        "selector_text": selector_text,
        "charts": [chart],
    }
    ensure_no_forbidden_quikstrike_content(payload)
    return payload


def build_matrix_payload_from_webforms_page(
    text: str,
    view: QuikStrikeMatrixViewType,
) -> Mapping[str, Any]:
    tables = _sanitized_tables(text)
    payload = {
        "visible_text": _visible_text(text, fallback=f"Gold (OG|GC) {MATRIX_VIEW_LABELS[view]}"),
        "tables": tables,
    }
    # Validate with the existing Matrix selector/parser before returning.
    build_matrix_request_from_browser_payloads({view: payload})
    ensure_no_forbidden_quikstrike_matrix_content(payload)
    return payload


def build_supplemental_payload_from_webforms_page(text: str, view: str) -> dict[str, Any]:
    tables = _sanitized_tables(text)
    return {
        "view": view,
        "title": _visible_text(text, fallback=f"Gold (OG|GC) {view}")[:240],
        "tables": [
            {
                "caption": table.get("caption") or None,
                "row_count_estimate": table["html_table"].lower().count("<tr"),
                "text_hint": table["text"][:500],
            }
            for table in tables[:6]
        ],
        "limitations": [
            "Supplemental Open Interest views are normalized as table digests only; "
            "they are not converted into XAU Vol-OI strike rows yet."
        ],
    }


def extract_json_settings(text: str) -> dict[str, Any]:
    match = re.search(r'"JSONSettings"\s*:\s*"((?:\\.|[^"\\])*)"', text or "")
    if match is None:
        raise ValueError("WebForms page did not contain JSONSettings")
    decoded = json.loads(f'"{match.group(1)}"')
    payload = json.loads(decoded)
    if not isinstance(payload, dict):
        raise ValueError("JSONSettings did not decode to an object")
    return payload


def write_normalized_digest(
    digest: Mapping[str, Any],
    *,
    output_root: Path | None = None,
) -> Path:
    _assert_sanitized(digest)
    root = output_root or Path(__file__).resolve().parents[3] / "data" / "reports"
    output_dir = root / "quikstrike_webforms_normalized" / str(digest["digest_id"])
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "digest.json"
    path.write_text(json.dumps(digest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _select_and_load_full_page(
    client: QuikStrikeWebFormsClient,
    *,
    label: str,
    event_target: str,
) -> httpx.Response:
    client.postback_response(label=label, event_target=event_target)
    response = client._request("GET", client.app_url, label=f"{label}_full_page")
    client._capture_form_fields(response.text)
    client._capture_hidden_fields(response.text)
    return response


def _chart_from_json_settings(
    settings: Mapping[str, Any],
    view: QuikStrikeViewType,
) -> dict[str, Any]:
    series: list[dict[str, Any]] = []
    for key, value in settings.items():
        if not isinstance(value, Mapping) or not isinstance(value.get("data"), list):
            continue
        name = _series_name(str(key), value)
        series.append({"name": name, "data": value["data"]})
    if not any(item["name"] == "Call" for item in series) or not any(
        item["name"] == "Put" for item in series
    ):
        raise ValueError("JSONSettings did not include Call and Put data")
    value_name = str(settings.get("ValueName") or _view_title(view))
    return {
        "chart_title": f"Gold (OG|GC) {value_name}",
        "series": series,
    }


def _series_name(key: str, value: Mapping[str, Any]) -> str:
    explicit = str(value.get("name") or "").strip()
    if explicit:
        return explicit
    normalized = key.lower().replace("_", " ")
    if "call" in normalized:
        return "Call"
    if "put" in normalized:
        return "Put"
    if "range" in normalized:
        return "Ranges"
    if "vol" in normalized:
        return "Vol Settle"
    return key


def _view_title(view: QuikStrikeViewType) -> str:
    titles = {
        QuikStrikeViewType.INTRADAY_VOLUME: "Intraday Volume",
        QuikStrikeViewType.EOD_VOLUME: "EOD Volume",
        QuikStrikeViewType.OPEN_INTEREST: "Open Interest",
        QuikStrikeViewType.OI_CHANGE: "Open Interest Change",
        QuikStrikeViewType.CHURN: "Churn",
    }
    return titles[view]


def _header_text(text: str, *, fallback: str) -> str:
    parser = _HeadingParser()
    parser.feed(text or "")
    for heading in parser.headings:
        if "Gold" in heading and "OG|GC" in heading:
            return heading
    return fallback


def _selector_text(text: str) -> str:
    visible = _visible_text(text, fallback="Gold (OG|GC)")
    fragments = []
    for pattern in (
        r"Gold\s*\(OG\|GC\)",
        r"Expiration:\s*[A-Z0-9]+",
        r"\b[A-Z0-9]{2,8}[FGHJKMNQUVXZ]\d{1,2}\b",
    ):
        match = re.search(pattern, visible)
        if match:
            fragments.append(match.group(0))
    return " ".join(dict.fromkeys(fragments))


def _visible_text(text: str, *, fallback: str) -> str:
    parser = _VisibleTextParser()
    parser.feed(text or "")
    normalized = " ".join(" ".join(parser.fragments).split())
    if normalized:
        return normalized[:4000]
    return fallback


def _sanitized_tables(text: str) -> list[dict[str, str]]:
    parser = _SanitizedTableParser()
    parser.feed(text or "")
    return [
        {
            "caption": table.get("caption", ""),
            "html_table": table["html_table"],
            "text": table["text"],
        }
        for table in parser.tables
        if table.get("html_table")
    ]


def _view_summary(label: str, response: httpx.Response) -> dict[str, Any]:
    summary = _response_payload_summary(label=label, response=response)
    return {
        "label": label,
        "status_code": summary["status_code"],
        "content_type": summary["content_type"],
        "body_length": summary["body_length"],
        "markers": summary["markers"],
        "title_hints": summary["title_hints"],
    }


def _normalize_requested_views(views: Sequence[str] | None) -> list[str]:
    requested = list(views or DEFAULT_NORMALIZED_VIEWS)
    supported = set(DEFAULT_NORMALIZED_VIEWS)
    unknown = sorted(set(requested) - supported)
    if unknown:
        raise QuikStrikeWebFormsError(f"unsupported normalized view(s): {', '.join(unknown)}")
    return list(dict.fromkeys(requested))


def _safe_reason(exc: Exception) -> str:
    return " ".join(str(exc).split())[:240] or type(exc).__name__


class _HeadingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.headings: list[str] = []
        self._capture = False
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"h1", "h2", "h3", "h4"}:
            self._capture = True
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"h1", "h2", "h3", "h4"} and self._capture:
            value = " ".join(" ".join(self._parts).split())
            if value:
                self.headings.append(value)
            self._capture = False
            self._parts = []


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.fragments: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style"} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        value = " ".join(html.unescape(data).split())
        if value:
            self.fragments.append(value)


class _SanitizedTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[dict[str, str]] = []
        self._in_table = False
        self._in_row = False
        self._cell_tag = ""
        self._cell_attrs: dict[str, str] = {}
        self._cell_text: list[str] = []
        self._rows: list[list[tuple[str, dict[str, str], str]]] = []
        self._current_row: list[tuple[str, dict[str, str], str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized = tag.lower()
        if normalized == "table" and not self._in_table:
            self._in_table = True
            self._rows = []
            return
        if not self._in_table:
            return
        if normalized == "tr":
            self._in_row = True
            self._current_row = []
            return
        if normalized in {"th", "td"} and self._in_row:
            self._cell_tag = normalized
            self._cell_attrs = {key.lower(): value or "" for key, value in attrs}
            self._cell_text = []

    def handle_data(self, data: str) -> None:
        if self._cell_tag:
            self._cell_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        if normalized in {"th", "td"} and self._cell_tag:
            text = " ".join(html.unescape(" ".join(self._cell_text)).split())
            self._current_row.append((self._cell_tag, dict(self._cell_attrs), text))
            self._cell_tag = ""
            self._cell_attrs = {}
            self._cell_text = []
            return
        if normalized == "tr" and self._in_row:
            if self._current_row:
                self._rows.append(list(self._current_row))
            self._in_row = False
            self._current_row = []
            return
        if normalized == "table" and self._in_table:
            html_table, text = self._render_table()
            self.tables.append({"caption": "", "html_table": html_table, "text": text})
            self._in_table = False
            self._rows = []

    def _render_table(self) -> tuple[str, str]:
        row_html = []
        text_rows = []
        for row in self._rows:
            cells = []
            text_cells = []
            for tag, attrs, value in row:
                attr_text = _span_attrs(attrs)
                cells.append(f"<{tag}{attr_text}>{html.escape(value)}</{tag}>")
                text_cells.append(value)
            row_html.append(f"<tr>{''.join(cells)}</tr>")
            text_rows.append(" ".join(text_cells))
        return f"<table>{''.join(row_html)}</table>", " ".join(text_rows)


def _span_attrs(attrs: Mapping[str, str]) -> str:
    parts = []
    for key in ("colspan", "rowspan"):
        value = attrs.get(key)
        if value and value.isdigit() and int(value) > 1:
            parts.append(f'{key}="{int(value)}"')
    return f" {' '.join(parts)}" if parts else ""
