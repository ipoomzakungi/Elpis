"""Local Playwright/CDP adapter for user-controlled QuikStrike extraction.

The adapter attaches to an already-open browser that the user controls. It does
not log in, does not replay endpoints, and does not persist browser/session data.
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlparse

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
DEFAULT_START_URL = "https://cmegroup-sso.quikstrike.net//User/QuikStrikeView.aspx?mode="
DEFAULT_TARGET_URL = ""
SUPPORTED_PAGE_TEXT = "QUIKOPTIONS VOL2VOL"

VIEW_LINK_LABELS = {
    QuikStrikeViewType.INTRADAY_VOLUME: "Intraday",
    QuikStrikeViewType.EOD_VOLUME: "EOD",
    QuikStrikeViewType.OPEN_INTEREST: "OI",
    QuikStrikeViewType.OI_CHANGE: "OI Change",
    QuikStrikeViewType.CHURN: "Churn",
}

VIEW_MENU_PATHS = {
    QuikStrikeViewType.INTRADAY_VOLUME: ("Volume", "Intraday"),
    QuikStrikeViewType.EOD_VOLUME: ("Volume", "EOD"),
    QuikStrikeViewType.OPEN_INTEREST: ("Open Interest", "OI"),
    QuikStrikeViewType.OI_CHANGE: ("Open Interest", "OI Change"),
    QuikStrikeViewType.CHURN: ("Open Interest", "Churn"),
}

VIEW_LINK_SELECTORS = {
    QuikStrikeViewType.INTRADAY_VOLUME: (
        "#MainContent_ucViewControl_QuikOptionsV2V_lbIntradayVolume"
    ),
    QuikStrikeViewType.EOD_VOLUME: "#MainContent_ucViewControl_QuikOptionsV2V_lbEODVolume",
    QuikStrikeViewType.OPEN_INTEREST: "#MainContent_ucViewControl_QuikOptionsV2V_lbOI",
    QuikStrikeViewType.OI_CHANGE: "#MainContent_ucViewControl_QuikOptionsV2V_lbOIChg",
    QuikStrikeViewType.CHURN: "#MainContent_ucViewControl_QuikOptionsV2V_lbChurn",
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


class QuikStrikeBrowserLaunchError(RuntimeError):
    """Raised when Playwright cannot launch a local visible browser."""


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


def extract_from_launched_browser(
    *,
    start_url: str = DEFAULT_START_URL,
    target_url: str = DEFAULT_TARGET_URL,
    views: Sequence[QuikStrikeViewType | str] | None = None,
    drive_views: bool = False,
    manual_views: bool = False,
    wait_seconds: int = 600,
    poll_seconds: int = 5,
    headless: bool = False,
    channel: str | None = "chrome",
    debug_page_state: bool = False,
    store: QuikStrikeReportStore | None = None,
) -> QuikStrikeBrowserExtraction:
    """Launch a local browser window and wait for manual QuikStrike preparation.

    This opens a visible browser, but authentication and product navigation remain
    user-controlled. The function reads only sanitized DOM and Highcharts memory
    after the Gold Vol2Vol page is available.
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
            try:
                browser = playwright.chromium.launch(
                    channel=channel,
                    headless=headless,
                )
            except Exception:
                browser = playwright.chromium.launch(headless=headless)
        except Exception as exc:
            raise QuikStrikeBrowserLaunchError(
                "Could not launch a local Playwright browser. Install a browser with "
                "`python -m playwright install chromium` or use an installed Chrome "
                "channel, then retry."
            ) from exc
        page = browser.new_page()
        page.goto(start_url)
        ready_page = _wait_for_gold_vol2vol_page(
            browser,
            wait_seconds=wait_seconds,
            poll_seconds=poll_seconds,
            target_url=target_url,
            auto_prepare=not manual_views,
            debug_page_state=debug_page_state,
        )
        if ready_page is None:
            browser.close()
            raise QuikStrikeBrowserPageNotReadyError(
                "Timed out waiting for manual QuikStrike login and Gold Vol2Vol "
                "navigation. Keep the launched browser open, sign in manually, select "
                "QUIKOPTIONS VOL2VOL, select Gold (OG|GC), and retry."
            )
        if manual_views:
            request = build_manual_request_from_page(
                ready_page,
                normalized_views,
                wait_seconds=wait_seconds,
                poll_seconds=poll_seconds,
            )
        else:
            request = build_request_from_page(
                ready_page,
                normalized_views,
                drive_views=drive_views,
            )
        browser.close()

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


def build_manual_request_from_page(
    page: Any,
    views: Sequence[QuikStrikeViewType | str] | None = None,
    *,
    wait_seconds: int = 600,
    poll_seconds: int = 5,
) -> QuikStrikeExtractionRequest:
    """Wait for each view to be manually selected, then collect sanitized payloads."""

    normalized_views = _normalize_views(views)
    payloads: dict[QuikStrikeViewType, Mapping[str, Any]] = {}
    for view in normalized_views:
        ready_payload = _wait_for_manual_view(
            page,
            view,
            wait_seconds=wait_seconds,
            poll_seconds=poll_seconds,
        )
        payloads[view] = ready_payload
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


def _wait_for_manual_view(
    page: Any,
    view: QuikStrikeViewType,
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
    raise QuikStrikeBrowserPageNotReadyError(
        f"Timed out waiting for manual selection of QuikStrike view {view.value}."
    )


def collect_sanitized_page_payload(page: Any) -> Mapping[str, Any]:
    """Read only visible text and sanitized Highcharts series from a Playwright page."""

    payload = page.evaluate(HIGHCHARTS_SANITIZER_SCRIPT)
    if not isinstance(payload, Mapping):
        raise ValueError("QuikStrike page extraction returned an invalid payload shape")
    ensure_no_forbidden_quikstrike_content(dict(payload))
    return payload


def page_has_gold_vol2vol_highcharts(page: Any) -> bool:
    """Return whether a page is the manually prepared Gold Vol2Vol chart page."""

    try:
        payload = collect_sanitized_page_payload(page)
    except Exception:
        return False
    page_text = " ".join(
        [
            str(payload.get("header_text") or ""),
            str(payload.get("selector_text") or ""),
        ]
    )
    charts = payload.get("charts")
    return (
        "Gold" in page_text
        and "OG|GC" in page_text
        and isinstance(charts, Sequence)
        and not isinstance(charts, (str, bytes, bytearray))
        and bool(charts)
    )


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


def _wait_for_gold_vol2vol_page(
    browser: Any,
    *,
    wait_seconds: int,
    poll_seconds: int,
    target_url: str,
    auto_prepare: bool,
    debug_page_state: bool,
) -> Any | None:
    deadline = time.monotonic() + max(wait_seconds, 1)
    poll_ms = max(poll_seconds, 1) * 1000
    last_page = None
    while time.monotonic() < deadline:
        for context in browser.contexts:
            for page in context.pages:
                last_page = page
                if debug_page_state:
                    _print_page_state(page, "poll")
                if _continue_disclaimer_if_present(page):
                    if debug_page_state:
                        _print_page_state(page, "continued_disclaimer")
                    continue
                if page_has_gold_vol2vol_highcharts(page):
                    if debug_page_state:
                        _print_page_state(page, "ready")
                    return page
        if auto_prepare:
            _prepare_gold_vol2vol_from_mode(
                browser,
                target_url,
                debug_page_state=debug_page_state,
            )
        elif debug_page_state and last_page is not None:
            _print_page_state(last_page, "waiting_manual")
        if last_page is not None:
            last_page.wait_for_timeout(poll_ms)
        else:
            time.sleep(max(poll_seconds, 1))
    return None


def _prepare_gold_vol2vol_from_mode(
    browser: Any,
    target_url: str,
    *,
    debug_page_state: bool,
) -> None:
    for context in browser.contexts:
        for page in context.pages:
            if _continue_disclaimer_if_present(page):
                if debug_page_state:
                    _print_page_state(page, "continued_disclaimer")
                continue
            try:
                current_url = page.url
            except Exception:
                continue
            if (
                target_url
                and "cmegroup-sso.quikstrike.net" in current_url
                and "QuikStrikeView.aspx?mode=" in current_url
            ):
                try:
                    page.goto(target_url)
                except Exception:
                    continue
            if (
                "cmegroup-sso.quikstrike.net" in current_url
                and "QuikStrikeView.aspx?mode=" in current_url
            ):
                if debug_page_state:
                    _print_page_state(page, "mode_page")
                if not _page_is_vol2vol_surface(page):
                    _click_quikoptions_vol2vol(page)
                    if debug_page_state:
                        _print_page_state(page, "clicked_vol2vol")
                page.wait_for_timeout(750)
                _select_gold_product(page, debug_page_state=debug_page_state)
                if debug_page_state:
                    _print_page_state(page, "after_product_attempt")


def _print_page_state(page: Any, stage: str) -> None:
    try:
        current_url = page.url
        parsed = urlparse(current_url)
        query_keys = sorted(parse_qs(parsed.query).keys())
        title = page.title()
        labels = _visible_debug_labels(page)
    except Exception as exc:
        print(f"[quikstrike:{stage}] page-state unavailable: {exc}", flush=True)
        return
    print(
        {
            "stage": stage,
            "host": parsed.netloc,
            "path": parsed.path,
            "query_keys": query_keys,
            "title": title,
            "labels": labels,
        },
        flush=True,
    )


def _visible_debug_labels(page: Any) -> list[str]:
    try:
        labels = page.evaluate(
            """
            () => {
              const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
              const visible = (node) => {
                const style = window.getComputedStyle(node);
                const rect = node.getBoundingClientRect();
                return style && style.visibility !== "hidden" && style.display !== "none"
                  && rect.width > 0 && rect.height > 0;
              };
              const pattern = new RegExp(
                "vol2vol|quik|product|gold|corn|metals|volume|open interest|"
                + "churn|eod|intraday",
                "i"
              );
              return Array.from(document.querySelectorAll("a,button,span,div,li,select,option"))
                .filter((node) => visible(node))
                .map((node) => clean(node.innerText || node.textContent || node.value))
                .filter((text) => text && text.length <= 100 && pattern.test(text))
                .slice(0, 40);
            }
            """
        )
    except Exception:
        return []
    return [str(label) for label in labels if label]


def _page_is_vol2vol_surface(page: Any) -> bool:
    return _page_text_matches_any(page, ("QUIKOPTIONS VOL2VOL", "Vol2Vol", "VOL2VOL"))


def _click_quikoptions_vol2vol(page: Any) -> None:
    if _click_exact_selector(page, "#ctl00_ucMenuBar_lvMenuBar_ctrl7_lbMenuItem"):
        page.wait_for_timeout(1500)
        return
    if _click_vol2vol_nav_item(page):
        page.wait_for_timeout(750)
        return
    for label in ("QUIKOPTIONS VOL2VOL", "QuikOptions Vol2Vol", "VOL2VOL", "Vol2Vol"):
        if _click_visible_text(page, label):
            page.wait_for_timeout(750)
            return
    for opener in ("Options Info", "Options", "QuikStrike"):
        if _click_visible_text(page, opener):
            page.wait_for_timeout(500)
            if _click_vol2vol_nav_item(page):
                page.wait_for_timeout(750)
                return


def _click_vol2vol_nav_item(page: Any) -> bool:
    try:
        return bool(
            page.evaluate(
                """
                () => {
                  const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
                  const visible = (node) => {
                    const style = window.getComputedStyle(node);
                    const rect = node.getBoundingClientRect();
                    return style && style.visibility !== "hidden" && style.display !== "none"
                      && rect.width > 0 && rect.height > 0;
                  };
                  const nodes = Array.from(document.querySelectorAll("a,button,[role='tab']"));
                  const match = nodes.find((node) => {
                    const text = clean(node.innerText || node.textContent).toLowerCase();
                    return text.includes("vol2vol") && visible(node);
                  });
                  if (!match) return false;
                  match.click();
                  return true;
                }
                """
            )
        )
    except Exception:
        return False


def _select_gold_product(page: Any, *, debug_page_state: bool = False) -> None:
    if _page_text_contains(page, "Gold (OG|GC)"):
        return
    if _select_native_gold_option(page):
        page.wait_for_timeout(1500)
        return
    _open_product_selector(page, debug_page_state=debug_page_state)
    page.wait_for_timeout(500)
    _click_product_selector_link(page, ".groups .items a[groupid='6']")
    page.wait_for_timeout(500)
    _click_product_selector_link(page, ".families .items a[familyid='6']")
    page.wait_for_timeout(500)
    if _click_product_selector_link(page, ".products .items a[title='Gold']"):
        page.wait_for_load_state("load")
        page.wait_for_timeout(1500)
        return
    if _click_product_selector_link(page, ".products .items a[href*='pid=40'][href*='pf=6']"):
        page.wait_for_load_state("load")
        page.wait_for_timeout(1500)
        return
    for label in ("Metals", "Precious Metals", "Gold (OG|GC)", "Gold"):
        if _page_text_contains(page, "Gold (OG|GC)"):
            return
        _click_visible_text(page, label)
        page.wait_for_timeout(500)


def _open_product_selector(page: Any, *, debug_page_state: bool = False) -> bool:
    if _click_exact_selector(page, "#ctl11_hlProductArrow"):
        if debug_page_state:
            print({"stage": "product_selector", "result": "clicked_product_arrow"}, flush=True)
        return True
    try:
        result = page.evaluate(
                """
                () => {
                  const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
                  const summary = (node) => ({
                    tag: node.tagName,
                    id: node.id || "",
                    className: String(node.className || "").slice(0, 80),
                    text: clean(node.innerText || node.textContent).slice(0, 80),
                    onclick: Boolean(node.onclick || node.getAttribute("onclick")),
                    role: node.getAttribute("role") || "",
                  });
                  const visible = (node) => {
                    const style = window.getComputedStyle(node);
                    const rect = node.getBoundingClientRect();
                    return style && style.visibility !== "hidden" && style.display !== "none"
                      && rect.width > 0 && rect.height > 0;
                  };
                  const nodes = Array.from(document.querySelectorAll("a,button,span,div"));
                  const candidates = nodes
                    .filter((node) => visible(node))
                    .map((node) => ({ node, text: clean(node.innerText || node.textContent) }))
                    .filter((item) => (
                      /corn\\s*\\(ozc\\|zc\\)/i.test(item.text)
                      || /product/i.test(item.text)
                      || /\\([A-Z0-9|]{3,}\\)/.test(item.text)
                    ))
                    .sort((a, b) => {
                      const score = (item) => /corn\\s*\\(ozc\\|zc\\)/i.test(item.text) ? 0 : 1;
                      return score(a) - score(b) || a.text.length - b.text.length;
                    });
                  const match = candidates[0];
                  if (!match) return { clicked: false, candidates: [] };
                  let clickable = match.node.closest("a,button,[role='button']");
                  let cursor = match.node;
                  const ancestors = [];
                  for (let i = 0; !clickable && cursor && i < 8; i += 1) {
                    ancestors.push(summary(cursor));
                    const style = window.getComputedStyle(cursor);
                    if (
                      cursor.onclick
                      || cursor.getAttribute("onclick")
                      || style.cursor === "pointer"
                      || cursor.getAttribute("role") === "button"
                    ) {
                      clickable = cursor;
                      break;
                    }
                    cursor = cursor.parentElement;
                  }
                  clickable = clickable || match.node.parentElement || match.node;
                  clickable.click();
                  return {
                    clicked: true,
                    match: summary(match.node),
                    clickable: summary(clickable),
                    ancestors,
                    candidates: candidates.slice(0, 8).map((item) => summary(item.node)),
                  };
                }
                """
        )
        if debug_page_state:
            print({"stage": "product_selector", "result": result}, flush=True)
        return bool(result.get("clicked") if isinstance(result, Mapping) else result)
    except Exception:
        return False


def _click_product_selector_link(page: Any, selector: str) -> bool:
    try:
        return bool(
            page.evaluate(
                """
                (selector) => {
                  const item = document.querySelector(selector);
                  if (!item) return false;
                  item.click();
                  return true;
                }
                """,
                selector,
            )
        )
    except Exception:
        return False


def _click_exact_selector(page: Any, selector: str) -> bool:
    try:
        return bool(
            page.evaluate(
                """
                (selector) => {
                  const item = document.querySelector(selector);
                  if (!item) return false;
                  item.click();
                  return true;
                }
                """,
                selector,
            )
        )
    except Exception:
        return False


def _select_native_gold_option(page: Any) -> bool:
    try:
        return bool(
            page.evaluate(
                """
                () => {
                  for (const select of Array.from(document.querySelectorAll("select"))) {
                    const option = Array.from(select.options || []).find((item) => (
                      /Gold\\s*\\(OG\\|GC\\)|\\bGold\\b/i.test(item.text || item.label || "")
                    ));
                    if (!option) continue;
                    select.value = option.value;
                    select.dispatchEvent(new Event("input", { bubbles: true }));
                    select.dispatchEvent(new Event("change", { bubbles: true }));
                    return true;
                  }
                  return false;
                }
                """
            )
        )
    except Exception:
        return False


def _page_text_contains(page: Any, text: str) -> bool:
    return _page_text_matches_any(page, (text,))


def _page_text_matches_any(page: Any, texts: Sequence[str]) -> bool:
    try:
        return bool(
            page.evaluate(
                """
                (texts) => {
                  const body = document.body ? document.body.innerText : "";
                  const normalizedBody = body.toLowerCase();
                  return texts.some((text) => normalizedBody.includes(String(text).toLowerCase()));
                }
                """,
                list(texts),
            )
        )
    except Exception:
        return False


def _continue_disclaimer_if_present(page: Any) -> bool:
    try:
        current_url = page.url
    except Exception:
        return False
    if "Disclaimer.aspx" not in current_url:
        return False
    try:
        return bool(
            page.evaluate(
                """
                () => {
                  const checkbox = document.querySelector(
                    'input[name="chkAccept"], input[type="checkbox"]'
                  );
                  if (checkbox && !checkbox.checked) {
                    checkbox.checked = true;
                    checkbox.dispatchEvent(new Event("change", { bubbles: true }));
                  }
                  const submit = document.querySelector(
                    'input[name="btnContinue"], input[type="submit"], button[type="submit"]'
                  );
                  if (!submit) return false;
                  submit.click();
                  return true;
                }
                """
            )
        )
    except Exception:
        return False


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
    if _page_payload_matches_view(page, view):
        return
    if _click_exact_selector(page, VIEW_LINK_SELECTORS[view]):
        if _wait_for_view_match(page, view):
            return
    parent_label, child_label = VIEW_MENU_PATHS[view]
    _click_visible_text(page, parent_label)
    page.wait_for_timeout(500)
    clicked = _click_visible_text(page, child_label)
    if not clicked and child_label != VIEW_LINK_LABELS[view]:
        clicked = _click_visible_text(page, VIEW_LINK_LABELS[view])
    if not clicked:
        raise QuikStrikeBrowserPageNotReadyError(
            f"Could not find a visible QuikStrike view control for {view.value}."
        )
    if not _wait_for_view_match(page, view):
        raise QuikStrikeBrowserPageNotReadyError(
            f"QuikStrike view control for {view.value} did not finish loading."
        )


def _click_visible_text(page: Any, label: str) -> bool:
    return bool(
        page.evaluate(
            """
            (label) => {
              const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
              const visible = (node) => {
                const style = window.getComputedStyle(node);
                const rect = node.getBoundingClientRect();
                return style && style.visibility !== "hidden" && style.display !== "none"
                  && rect.width > 0 && rect.height > 0;
              };
              const labels = label === "OI" ? ["OI", "Open Interest"] : [label];
              const target = (value) => clean(value).toLowerCase();
              const nodes = Array.from(document.querySelectorAll("a,button,span,div,li"));
              for (const wanted of labels) {
                const wantedText = target(wanted);
                const exact = nodes.find((node) => (
                  target(node.innerText || node.textContent) === wantedText && visible(node)
                ));
                if (exact) {
                  exact.click();
                  return true;
                }
              }
              for (const wanted of labels) {
                const wantedText = target(wanted);
                const partial = nodes.find((node) => {
                  const text = clean(node.innerText || node.textContent);
                  return text.length <= 80 && target(text).includes(wantedText) && visible(node);
                });
                if (partial) {
                  partial.click();
                  return true;
                }
              }
              return false;
            }
            """,
            label,
        )
    )


def _page_payload_matches_view(page: Any, view: QuikStrikeViewType) -> bool:
    try:
        payload = collect_sanitized_page_payload(page)
        chart = select_chart_payload(payload.get("charts"), view)
    except Exception:
        return False
    title = str(chart.get("chart_title") or "").lower()
    return _view_title_token(view) in title


def _wait_for_view_match(
    page: Any,
    view: QuikStrikeViewType,
    *,
    timeout_ms: int = 10000,
    poll_ms: int = 500,
) -> bool:
    deadline = time.monotonic() + (timeout_ms / 1000)
    while time.monotonic() < deadline:
        if _page_payload_matches_view(page, view):
            return True
        page.wait_for_timeout(poll_ms)
    return False


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
