"""Local Playwright/CDP adapter for user-controlled QuikStrike Matrix extraction.

The adapter attaches to a browser that the user controls. It does not log in,
does not replay endpoints, and does not persist browser/session data.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from src.models.quikstrike_matrix import (
    QuikStrikeMatrixExtractionReport,
    QuikStrikeMatrixExtractionRequest,
    QuikStrikeMatrixTableSnapshot,
    QuikStrikeMatrixViewType,
    ensure_no_forbidden_quikstrike_matrix_content,
)
from src.quikstrike_matrix.conversion import convert_to_xau_vol_oi_rows
from src.quikstrike_matrix.extraction import build_extraction_from_request
from src.quikstrike_matrix.metadata import parse_matrix_metadata
from src.quikstrike_matrix.report_store import QuikStrikeMatrixReportStore
from src.quikstrike_matrix.table_reader import parse_matrix_table

DEFAULT_CDP_URL = "http://127.0.0.1:9222"
SUPPORTED_PAGE_TEXT = "OPEN INTEREST"

MATRIX_VIEW_LABELS = {
    QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX: "OI Matrix",
    QuikStrikeMatrixViewType.OI_CHANGE_MATRIX: "OI Change Matrix",
    QuikStrikeMatrixViewType.VOLUME_MATRIX: "Volume Matrix",
}

MATRIX_VIEW_TOKENS = {
    QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX: ("oi matrix", "open interest matrix"),
    QuikStrikeMatrixViewType.OI_CHANGE_MATRIX: ("oi change", "open interest change"),
    QuikStrikeMatrixViewType.VOLUME_MATRIX: ("volume matrix", "volume"),
}

MATRIX_VIEW_CLICK_LABELS = {
    QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX: ("OI Matrix", "OI"),
    QuikStrikeMatrixViewType.OI_CHANGE_MATRIX: ("OI Change Matrix", "OI Change"),
    QuikStrikeMatrixViewType.VOLUME_MATRIX: ("Volume Matrix", "Volume"),
}

MATRIX_SANITIZER_SCRIPT = """
() => {
  const cleanText = (value) => String(value || "").replace(/\\s+/g, " ").trim();
  const escapeHtml = (value) => cleanText(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  const attrs = (cell) => {
    const parts = [];
    const colspan = Number(cell.getAttribute("colspan") || "1");
    const rowspan = Number(cell.getAttribute("rowspan") || "1");
    if (Number.isFinite(colspan) && colspan > 1) parts.push(`colspan="${colspan}"`);
    if (Number.isFinite(rowspan) && rowspan > 1) parts.push(`rowspan="${rowspan}"`);
    return parts.length ? ` ${parts.join(" ")}` : "";
  };
  const titleTexts = (cell) => Array.from(cell.querySelectorAll("[title]"))
    .map((node) => cleanText(node.getAttribute("title")))
    .filter(Boolean);
  const cellText = (cell) => {
    const title = cleanText(cell.getAttribute("title"));
    return [cleanText(cell.innerText || cell.textContent), title, ...titleTexts(cell)]
      .filter(Boolean)
      .join(" ");
  };
  const sanitizedTable = (table) => {
    const rows = Array.from(table.querySelectorAll("tr")).map((row) => {
      const cells = Array.from(row.children).filter((cell) => {
        const tag = cell.tagName.toLowerCase();
        return tag === "th" || tag === "td";
      });
      if (!cells.length) return "";
      const htmlCells = cells.map((cell) => {
        const tag = cell.tagName.toLowerCase() === "th" ? "th" : "td";
        return `<${tag}${attrs(cell)}>${escapeHtml(cellText(cell))}</${tag}>`;
      });
      return `<tr>${htmlCells.join("")}</tr>`;
    }).filter(Boolean);
    return rows.length ? `<table>${rows.join("")}</table>` : "";
  };
  const filteredVisibleTexts = Array.from(
    document.querySelectorAll("h1,h2,h3,h4,a,button,span,div")
  ).map((node) => cleanText(node.innerText || node.textContent))
    .filter((text) => /Gold|OG\\|GC|Open Interest|OI Change|Matrix|Volume/i.test(text))
    .slice(0, 80);
  const tables = Array.from(document.querySelectorAll("table")).map((table) => ({
    caption: cleanText(table.caption && table.caption.innerText),
    html_table: sanitizedTable(table),
    text: cleanText(table.innerText || table.textContent),
  })).filter((table) => table.html_table);
  return {
    visible_text: filteredVisibleTexts.join(" "),
    tables,
  };
}
"""


@dataclass(frozen=True)
class QuikStrikeMatrixBrowserExtraction:
    report: QuikStrikeMatrixExtractionReport
    request: QuikStrikeMatrixExtractionRequest


class QuikStrikeMatrixPlaywrightUnavailableError(RuntimeError):
    """Raised when the optional Playwright dependency is not installed."""


class QuikStrikeMatrixBrowserPageNotReadyError(RuntimeError):
    """Raised when no manually prepared Gold Matrix page is available."""


class QuikStrikeMatrixCdpConnectionError(RuntimeError):
    """Raised when the user-controlled browser debugging endpoint is unavailable."""


def extract_from_cdp(
    *,
    cdp_url: str = DEFAULT_CDP_URL,
    views: Sequence[QuikStrikeMatrixViewType | str] | None = None,
    drive_views: bool = False,
    manual_views: bool = True,
    view_prompt: Callable[[QuikStrikeMatrixViewType], None] | None = None,
    wait_seconds: int = 600,
    poll_seconds: int = 5,
    store: QuikStrikeMatrixReportStore | None = None,
) -> QuikStrikeMatrixBrowserExtraction:
    """Attach to a user-controlled browser and persist a sanitized Matrix report."""

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - exercised without optional dep
        raise QuikStrikeMatrixPlaywrightUnavailableError(
            "Install the optional browser dependency with: pip install -e .[browser]"
        ) from exc

    normalized_views = _normalize_views(views)
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.connect_over_cdp(cdp_url)
        except Exception as exc:
            raise QuikStrikeMatrixCdpConnectionError(
                "Could not connect to the local browser debugging endpoint. Start "
                "Chrome or Edge manually with --remote-debugging-port=9222, log in "
                "manually, and navigate to Gold OPEN INTEREST Matrix."
            ) from exc
        page = _find_gold_matrix_page(browser)
        if view_prompt is not None:
            request = build_prompted_request_from_page(
                page,
                normalized_views,
                view_prompt=view_prompt,
            )
        elif manual_views:
            request = build_manual_request_from_page(
                page,
                normalized_views,
                wait_seconds=wait_seconds,
                poll_seconds=poll_seconds,
            )
        else:
            request = build_request_from_page(page, normalized_views, drive_views=drive_views)

    extraction = build_extraction_from_request(request)
    conversion = convert_to_xau_vol_oi_rows(
        extraction_result=extraction.result,
        rows=extraction.rows,
    )
    report = (store or QuikStrikeMatrixReportStore()).persist_report(
        extraction_result=extraction.result,
        normalized_rows=extraction.rows,
        conversion_result=conversion.result,
        conversion_rows=conversion.rows,
    )
    return QuikStrikeMatrixBrowserExtraction(report=report, request=request)


def build_request_from_page(
    page: Any,
    views: Sequence[QuikStrikeMatrixViewType | str] | None = None,
    *,
    drive_views: bool = False,
) -> QuikStrikeMatrixExtractionRequest:
    """Collect sanitized Matrix payloads and build an extraction request."""

    normalized_views = _normalize_views(views)
    payloads: dict[QuikStrikeMatrixViewType, Mapping[str, Any]] = {}
    for view in normalized_views:
        if drive_views:
            _click_view(page, view)
        payloads[view] = collect_sanitized_page_payload(page)
    return build_request_from_browser_payloads(payloads)


def build_manual_request_from_page(
    page: Any,
    views: Sequence[QuikStrikeMatrixViewType | str] | None = None,
    *,
    wait_seconds: int = 600,
    poll_seconds: int = 5,
) -> QuikStrikeMatrixExtractionRequest:
    """Wait for each Matrix view to be manually selected, then collect payloads."""

    normalized_views = _normalize_views(views)
    payloads: dict[QuikStrikeMatrixViewType, Mapping[str, Any]] = {}
    for view in normalized_views:
        payloads[view] = _wait_for_manual_view(
            page,
            view,
            wait_seconds=wait_seconds,
            poll_seconds=poll_seconds,
        )
    return build_request_from_browser_payloads(payloads)


def build_prompted_request_from_page(
    page: Any,
    views: Sequence[QuikStrikeMatrixViewType | str] | None = None,
    *,
    view_prompt: Callable[[QuikStrikeMatrixViewType], None],
) -> QuikStrikeMatrixExtractionRequest:
    """Prompt before each view and then collect the current sanitized table payload."""

    normalized_views = _normalize_views(views)
    payloads: dict[QuikStrikeMatrixViewType, Mapping[str, Any]] = {}
    for view in normalized_views:
        view_prompt(view)
        payloads[view] = collect_sanitized_page_payload(page)
    return build_request_from_browser_payloads(payloads)


def build_request_from_browser_payloads(
    payloads: Mapping[QuikStrikeMatrixViewType | str, Mapping[str, Any]],
) -> QuikStrikeMatrixExtractionRequest:
    """Build a strict Matrix extraction request from sanitized browser payloads."""

    ensure_no_forbidden_quikstrike_matrix_content(dict(payloads))
    normalized_payloads = {
        QuikStrikeMatrixViewType(view): payload for view, payload in payloads.items()
    }
    metadata_by_view = {}
    tables_by_view = {}
    for view, payload in normalized_payloads.items():
        visible_text = _required_text(payload, "visible_text")
        table_payload = select_matrix_table_payload(payload.get("tables"), view)
        metadata_by_view[view] = parse_matrix_metadata(
            raw_visible_text=visible_text,
            view_type=view,
            selected_view_label=MATRIX_VIEW_LABELS[view],
        )
        tables_by_view[view] = QuikStrikeMatrixTableSnapshot(
            view_type=view,
            html_table=str(table_payload["html_table"]),
            caption=_optional_text(table_payload.get("caption")),
        )
    return QuikStrikeMatrixExtractionRequest(
        requested_views=list(normalized_payloads),
        metadata_by_view=metadata_by_view,
        tables_by_view=tables_by_view,
        research_only_acknowledged=True,
    )


def collect_sanitized_page_payload(page: Any) -> Mapping[str, Any]:
    """Read only visible Matrix text and sanitized HTML table cells."""

    payload = page.evaluate(MATRIX_SANITIZER_SCRIPT)
    if not isinstance(payload, Mapping):
        raise ValueError("QuikStrike Matrix page extraction returned an invalid shape")
    ensure_no_forbidden_quikstrike_matrix_content(dict(payload))
    return payload


def page_has_gold_matrix_table(page: Any) -> bool:
    """Return whether a page appears to be a manually prepared Gold Matrix page."""

    try:
        payload = collect_sanitized_page_payload(page)
        select_matrix_table_payload(
            payload.get("tables"),
            QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX,
        )
    except Exception:
        return False
    visible_text = str(payload.get("visible_text") or "")
    return (
        ("Gold" in visible_text or "OG|GC" in visible_text)
        and SUPPORTED_PAGE_TEXT.lower() in visible_text.lower()
    )


def select_matrix_table_payload(
    tables: Any,
    view: QuikStrikeMatrixViewType | str,
) -> Mapping[str, Any]:
    """Select the sanitized table with the strongest Matrix structure."""

    normalized_view = QuikStrikeMatrixViewType(view)
    if not isinstance(tables, Sequence) or isinstance(tables, (str, bytes, bytearray)):
        raise ValueError("QuikStrike Matrix browser payload must include a tables list")
    table_mappings = [table for table in tables if isinstance(table, Mapping)]
    if not table_mappings:
        raise ValueError("QuikStrike Matrix browser payload did not include table data")

    def score(table: Mapping[str, Any]) -> tuple[int, int, int]:
        html_table = str(table.get("html_table") or "")
        text = f"{table.get('caption') or ''} {table.get('text') or ''}".lower()
        try:
            parsed = parse_matrix_table(
                QuikStrikeMatrixTableSnapshot(
                    view_type=normalized_view,
                    html_table=html_table,
                )
            )
        except Exception:
            return 0, 0, 0
        token_match = int(any(token in text for token in MATRIX_VIEW_TOKENS[normalized_view]))
        expiration_count = len({cell.expiration for cell in parsed.body_cells if cell.expiration})
        return len(parsed.body_cells), expiration_count, token_match

    best = max(table_mappings, key=score)
    if score(best)[0] <= 0:
        raise ValueError("QuikStrike Matrix table data must include strike rows")
    return best


def _wait_for_manual_view(
    page: Any,
    view: QuikStrikeMatrixViewType,
    *,
    wait_seconds: int,
    poll_seconds: int,
) -> Mapping[str, Any]:
    deadline = time.monotonic() + max(wait_seconds, 1)
    poll_ms = max(poll_seconds, 1) * 1000
    while time.monotonic() < deadline:
        if _page_payload_matches_view(page, view):
            return collect_sanitized_page_payload(page)
        page.wait_for_timeout(poll_ms)
    raise QuikStrikeMatrixBrowserPageNotReadyError(
        f"Timed out waiting for manual selection of QuikStrike Matrix view {view.value}."
    )


def _page_payload_matches_view(page: Any, view: QuikStrikeMatrixViewType) -> bool:
    try:
        payload = collect_sanitized_page_payload(page)
        select_matrix_table_payload(payload.get("tables"), view)
    except Exception:
        return False
    page_text = " ".join(
        [
            str(payload.get("visible_text") or ""),
            " ".join(
                str(table.get("text") or "")
                for table in payload.get("tables", [])
                if isinstance(table, Mapping)
            ),
        ]
    ).lower()
    return any(token in page_text for token in MATRIX_VIEW_TOKENS[view])


def _find_gold_matrix_page(browser: Any) -> Any:
    for context in browser.contexts:
        for page in context.pages:
            if page_has_gold_matrix_table(page):
                return page
    raise QuikStrikeMatrixBrowserPageNotReadyError(
        "No Gold OPEN INTEREST Matrix page was found. Use the user-controlled browser "
        "to log in manually, select Gold (OG|GC), and open an OPEN INTEREST Matrix view."
    )


def _click_view(page: Any, view: QuikStrikeMatrixViewType) -> None:
    for label in MATRIX_VIEW_CLICK_LABELS[view]:
        try:
            page.get_by_text(label, exact=True).click(timeout=1500)
            page.wait_for_timeout(1500)
            return
        except Exception:
            continue
    raise QuikStrikeMatrixBrowserPageNotReadyError(
        f"Could not click Matrix view {view.value}; use --manual-views and select it manually."
    )


def _normalize_views(
    views: Sequence[QuikStrikeMatrixViewType | str] | None,
) -> list[QuikStrikeMatrixViewType]:
    if not views:
        return [
            QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX,
            QuikStrikeMatrixViewType.OI_CHANGE_MATRIX,
            QuikStrikeMatrixViewType.VOLUME_MATRIX,
        ]
    return [QuikStrikeMatrixViewType(view) for view in views]


def _required_text(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"QuikStrike Matrix browser payload missing {key}")
    return " ".join(value.split())


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = " ".join(str(value).split())
    return normalized or None
