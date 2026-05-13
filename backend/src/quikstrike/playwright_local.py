"""Local Playwright/CDP adapter for user-controlled QuikStrike extraction.

The adapter attaches to an already-open browser that the user controls. It does
not log in, does not replay endpoints, and does not persist browser/session data.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from src.models.quikstrike import (
    QuikStrikeExtractionReport,
    QuikStrikeExtractionRequest,
    QuikStrikeViewType,
    ensure_no_forbidden_quikstrike_content,
)
from src.quikstrike.conversion import convert_to_xau_vol_oi_rows
from src.quikstrike.dom_metadata import parse_dom_metadata
from src.quikstrike.extraction import build_extraction_from_request
from src.quikstrike.highcharts_reader import parse_highcharts_chart
from src.quikstrike.report_store import QuikStrikeReportStore

DEFAULT_CDP_URL = "http://127.0.0.1:9222"
SUPPORTED_PAGE_TEXT = "QUIKOPTIONS VOL2VOL"

VIEW_LINK_LABELS = {
    QuikStrikeViewType.INTRADAY_VOLUME: "Intraday",
    QuikStrikeViewType.EOD_VOLUME: "EOD",
    QuikStrikeViewType.OPEN_INTEREST: "OI",
    QuikStrikeViewType.OI_CHANGE: "OI Change",
    QuikStrikeViewType.CHURN: "Churn",
}

HIGHCHARTS_SANITIZER_SCRIPT = """
() => {
  const cleanText = (value) => String(value || "").replace(/\\s+/g, " ").trim();
  const finite = (value) => Number.isFinite(Number(value)) ? Number(value) : null;
  const safeTag = (tag) => {
    if (!tag || typeof tag !== "object") return {};
    const output = {};
    for (const key of ["StrikeId", "strikeId", "strike_id", "Range", "range", "Sigma", "sigma"]) {
      if (Object.prototype.hasOwnProperty.call(tag, key)) output[key] = cleanText(tag[key]);
    }
    return output;
  };
  const texts = (selector) => Array.from(document.querySelectorAll(selector)).map(
    (node) => cleanText(node.innerText || node.textContent)
  );
  const headerText = texts("h1,h2,h3,h4").find(
    (text) => /Gold|OG\\|GC|DTE|Intraday|Open Interest|Churn|EOD/i.test(text)
  ) || "";
  const productText = texts("a,button,span,div").find(
    (text) => /Gold\\s*\\(OG\\|GC\\)/i.test(text)
  ) || "";
  const expirationText = texts("a,button,span,div").find(
    (text) => /Expiration\\s*:/i.test(text)
  ) || "";
  const charts = ((window.Highcharts && window.Highcharts.charts) || [])
    .filter(Boolean)
    .map((chart) => ({
    chart_title: cleanText(
      (chart.title && chart.title.textStr)
        || (chart.options && chart.options.title && chart.options.title.text)
    ),
    series: (chart.series || []).filter(Boolean).map((series) => ({
      name: cleanText(series.name),
      data: (series.points || []).map((point) => ({
        x: finite(point.x),
        y: finite(point.y),
        x2: finite(point.x2 ?? point.options?.x2),
        name: cleanText(point.name ?? point.options?.name ?? point.key),
        category: cleanText(point.category ?? point.options?.category),
        Tag: safeTag(point.options?.Tag || point.options?.tag || point.Tag || point.tag),
      })),
    })),
  }));
  return {
    header_text: headerText,
    selector_text: [productText, expirationText].filter(Boolean).join(" "),
    charts,
  };
}
"""


@dataclass(frozen=True)
class QuikStrikeBrowserExtraction:
    report: QuikStrikeExtractionReport
    request: QuikStrikeExtractionRequest


class QuikStrikePlaywrightUnavailableError(RuntimeError):
    """Raised when the optional Playwright dependency is not installed."""


class QuikStrikeBrowserPageNotReadyError(RuntimeError):
    """Raised when no manually prepared Gold Vol2Vol page is available."""


class QuikStrikeCdpConnectionError(RuntimeError):
    """Raised when the user-controlled browser debugging endpoint is unavailable."""


def extract_from_cdp(
    *,
    cdp_url: str = DEFAULT_CDP_URL,
    views: Sequence[QuikStrikeViewType | str] | None = None,
    drive_views: bool = False,
    store: QuikStrikeReportStore | None = None,
) -> QuikStrikeBrowserExtraction:
    """Attach to a user-controlled browser and persist a sanitized extraction report.

    The user must start Chrome/Edge with a local debugging port, log in manually,
    and navigate manually to Gold QUIKOPTIONS VOL2VOL before this function runs.
    """

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - exercised without optional dep
        raise QuikStrikePlaywrightUnavailableError(
            "Install the optional browser dependency with: pip install -e .[browser]"
        ) from exc

    normalized_views = _normalize_views(views)
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.connect_over_cdp(cdp_url)
        except Exception as exc:
            raise QuikStrikeCdpConnectionError(
                "Could not connect to the local browser debugging endpoint. Start "
                "Chrome or Edge manually with --remote-debugging-port=9222, log in "
                "manually, and navigate to Gold QUIKOPTIONS VOL2VOL."
            ) from exc
        page = _find_gold_vol2vol_page(browser)
        request = build_request_from_page(page, normalized_views, drive_views=drive_views)

    extraction = build_extraction_from_request(request)
    conversion = convert_to_xau_vol_oi_rows(
        extraction_result=extraction.result,
        rows=extraction.rows,
    )
    report = (store or QuikStrikeReportStore()).persist_report(
        extraction_result=extraction.result,
        normalized_rows=extraction.rows,
        conversion_result=conversion.result,
        conversion_rows=conversion.rows,
    )
    return QuikStrikeBrowserExtraction(report=report, request=request)


def build_request_from_page(
    page: Any,
    views: Sequence[QuikStrikeViewType | str] | None = None,
    *,
    drive_views: bool = False,
) -> QuikStrikeExtractionRequest:
    """Collect sanitized page payloads and build an extraction request."""

    normalized_views = _normalize_views(views)
    payloads: dict[QuikStrikeViewType, Mapping[str, Any]] = {}
    for view in normalized_views:
        if drive_views:
            _click_view(page, view)
        payloads[view] = collect_sanitized_page_payload(page)
    return build_request_from_browser_payloads(payloads)


def build_request_from_browser_payloads(
    payloads: Mapping[QuikStrikeViewType | str, Mapping[str, Any]],
) -> QuikStrikeExtractionRequest:
    """Build a strict 012 extraction request from sanitized browser payloads."""

    ensure_no_forbidden_quikstrike_content(dict(payloads))
    normalized_payloads = {
        QuikStrikeViewType(view): payload for view, payload in payloads.items()
    }
    dom_metadata_by_view = {}
    highcharts_by_view = {}
    for view, payload in normalized_payloads.items():
        header_text = _required_text(payload, "header_text")
        selector_text = _optional_text(payload.get("selector_text"))
        dom_metadata_by_view[view] = parse_dom_metadata(
            header_text,
            selector_text=selector_text,
            selected_view_type=view,
        )
        highcharts_by_view[view] = parse_highcharts_chart(
            select_chart_payload(payload.get("charts"), view),
            view,
        )
    return QuikStrikeExtractionRequest(
        requested_views=list(normalized_payloads),
        dom_metadata_by_view=dom_metadata_by_view,
        highcharts_by_view=highcharts_by_view,
        run_label="playwright_local",
        research_only_acknowledged=True,
    )


def collect_sanitized_page_payload(page: Any) -> Mapping[str, Any]:
    """Read only visible text and sanitized Highcharts series from a Playwright page."""

    payload = page.evaluate(HIGHCHARTS_SANITIZER_SCRIPT)
    if not isinstance(payload, Mapping):
        raise ValueError("QuikStrike page extraction returned an invalid payload shape")
    ensure_no_forbidden_quikstrike_content(dict(payload))
    return payload


def select_chart_payload(charts: Any, view: QuikStrikeViewType | str) -> Mapping[str, Any]:
    """Select the chart payload that contains Put/Call series for the requested view."""

    normalized_view = QuikStrikeViewType(view)
    if not isinstance(charts, Sequence) or isinstance(charts, (str, bytes, bytearray)):
        raise ValueError("QuikStrike browser payload must include a charts list")
    chart_mappings = [chart for chart in charts if isinstance(chart, Mapping)]
    if not chart_mappings:
        raise ValueError("QuikStrike browser payload did not include chart data")

    def score(chart: Mapping[str, Any]) -> tuple[int, int]:
        title = str(chart.get("chart_title") or "").lower()
        series = chart.get("series", [])
        names = [
            str(item.get("name") or "").lower()
            for item in series
            if isinstance(item, Mapping)
        ]
        has_put_call = int("put" in names) + int("call" in names)
        title_match = 1 if _view_title_token(normalized_view) in title else 0
        return has_put_call, title_match

    best = max(chart_mappings, key=score)
    if score(best)[0] < 2:
        raise ValueError("QuikStrike chart data must include separate Put and Call series")
    return best


def _find_gold_vol2vol_page(browser: Any) -> Any:
    for context in browser.contexts:
        for page in context.pages:
            try:
                payload = collect_sanitized_page_payload(page)
            except Exception:
                continue
            page_text = " ".join(
                [
                    str(payload.get("header_text") or ""),
                    str(payload.get("selector_text") or ""),
                ]
            )
            if "Gold" in page_text and "OG|GC" in page_text:
                return page
    raise QuikStrikeBrowserPageNotReadyError(
        "Open QuikStrike manually, log in manually, navigate to QUIKOPTIONS VOL2VOL, "
        "and select Gold (OG|GC) before extraction."
    )


def _click_view(page: Any, view: QuikStrikeViewType) -> None:
    label = VIEW_LINK_LABELS[view]
    page.get_by_role("link", name=label, exact=True).click()
    page.wait_for_load_state("load")
    page.wait_for_timeout(1500)


def _normalize_views(
    views: Sequence[QuikStrikeViewType | str] | None,
) -> list[QuikStrikeViewType]:
    if views is None:
        return [
            QuikStrikeViewType.INTRADAY_VOLUME,
            QuikStrikeViewType.EOD_VOLUME,
            QuikStrikeViewType.OPEN_INTEREST,
            QuikStrikeViewType.OI_CHANGE,
            QuikStrikeViewType.CHURN,
        ]
    normalized = [QuikStrikeViewType(view) for view in views]
    return list(dict.fromkeys(normalized))


def _view_title_token(view: QuikStrikeViewType) -> str:
    return {
        QuikStrikeViewType.INTRADAY_VOLUME: "intraday",
        QuikStrikeViewType.EOD_VOLUME: "eod",
        QuikStrikeViewType.OPEN_INTEREST: "open interest",
        QuikStrikeViewType.OI_CHANGE: "change",
        QuikStrikeViewType.CHURN: "churn",
    }[view]


def _required_text(payload: Mapping[str, Any], key: str) -> str:
    value = _optional_text(payload.get(key))
    if not value:
        raise ValueError(f"QuikStrike browser payload missing {key}")
    return value


def _optional_text(value: Any) -> str:
    return " ".join(str(value or "").split())
