"""Normal browser-login helper for QuikStrike CDP sessions.

The helper fills ordinary visible login forms in the user-controlled browser.
It does not read cookies, browser passwords, headers, tokens, HAR files,
viewstate values, or page response bodies.
"""

from __future__ import annotations

import re
import time
from collections.abc import Mapping
from typing import Any
from urllib.parse import parse_qsl, urlparse

from src.quikstrike.api_probe import DEFAULT_QUIKSTRIKE_START_URL

QUIKSTRIKE_READY_PATTERN = re.compile(
    r"QUIKOPTIONS|OPEN INTEREST|Gold\s*\(OG\|GC\)",
    re.IGNORECASE,
)
SENSITIVE_QUERY_KEY_PATTERN = re.compile(
    r"auth|bearer|cookie|credential|eventvalidation|key|password|secret|session|"
    r"ticket|token|username|viewstate",
    re.IGNORECASE,
)
OPAQUE_PATH_SEGMENT_PATTERN = re.compile(r"^[A-Za-z0-9_-]{24,}$")

BROWSER_LOGIN_SCRIPT = """
({ username, password }) => {
  const visible = (element) => {
    if (!element) return false;
    const style = window.getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.visibility !== "hidden"
      && style.display !== "none"
      && rect.width > 0
      && rect.height > 0
      && !element.disabled
      && !element.readOnly;
  };
  const setValue = (element, value) => {
    if (!element || value === undefined || value === null || value === "") return false;
    const setter = Object.getOwnPropertyDescriptor(element.__proto__, "value")?.set;
    if (setter) setter.call(element, value);
    else element.value = value;
    element.dispatchEvent(new Event("input", { bubbles: true }));
    element.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  };
  const normalized = (value) => String(value || "").toLowerCase();
  const inputs = Array.from(document.querySelectorAll("input")).filter(visible);
  const passwordInput = inputs.find((input) => normalized(input.type) === "password");
  const usernameInput = inputs.find((input) => {
    const haystack = [
      input.type,
      input.name,
      input.id,
      input.autocomplete,
      input.placeholder,
      input.getAttribute("aria-label"),
    ].map(normalized).join(" ");
    return !["hidden", "password", "submit", "button", "checkbox", "radio"].includes(
      normalized(input.type)
    ) && /(user|email|login|account)/.test(haystack);
  }) || inputs.find((input) => {
    const type = normalized(input.type || "text");
    return !["hidden", "password", "submit", "button", "checkbox", "radio"].includes(type);
  });
  const form = passwordInput?.form || usernameInput?.form || null;
  const filledUsername = setValue(usernameInput, username);
  const filledPassword = setValue(passwordInput, password);
  const buttons = Array.from(
    (form || document).querySelectorAll("button,input[type=submit],input[type=button]")
  ).filter(visible);
  const submitButton = buttons.find((button) => {
    const text = normalized(button.innerText || button.value || button.getAttribute("aria-label"));
    return /(sign|log|next|continue|submit)/.test(text);
  }) || buttons[0] || null;
  if (submitButton && (filledUsername || filledPassword)) {
    submitButton.click();
  } else if (form && (filledUsername || filledPassword)) {
    form.requestSubmit ? form.requestSubmit() : form.submit();
  }
  return {
    filled_username: filledUsername,
    filled_password: filledPassword,
    submitted: Boolean((submitButton || form) && (filledUsername || filledPassword)),
    had_username_input: Boolean(usernameInput),
    had_password_input: Boolean(passwordInput),
    button_count: buttons.length,
  };
}
"""

DISCLAIMER_CONTINUE_SCRIPT = """
() => {
  const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim().toLowerCase();
  const visible = (element) => {
    if (!element) return false;
    const style = window.getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.visibility !== "hidden"
      && style.display !== "none"
      && rect.width > 0
      && rect.height > 0
      && !element.disabled;
  };
  const checkbox = Array.from(document.querySelectorAll("input[type=checkbox]"))
    .find(visible);
  if (checkbox && !checkbox.checked) {
    checkbox.click();
    if (!checkbox.checked) checkbox.checked = true;
    checkbox.dispatchEvent(new Event("input", { bubbles: true }));
    checkbox.dispatchEvent(new Event("change", { bubbles: true }));
  }
  const controls = Array.from(
    document.querySelectorAll("button,input[type=submit],input[type=button],a")
  ).filter(visible);
  const control = controls.find((node) => {
    const text = clean(node.innerText || node.value || node.getAttribute("aria-label"));
    return /(continue|accept|agree)/.test(text);
  });
  if (!control) return { clicked: false, control_count: controls.length };
  control.click();
  return { clicked: true, control_count: controls.length };
}
"""


class QuikStrikeBrowserLoginUnavailableError(RuntimeError):
    """Raised when Playwright is unavailable for browser login."""


class QuikStrikeBrowserLoginCdpError(RuntimeError):
    """Raised when the CDP browser is unavailable."""


def run_browser_login(
    *,
    cdp_url: str,
    username: str | None,
    password: str | None,
    start_url: str = DEFAULT_QUIKSTRIKE_START_URL,
    wait_seconds: int = 90,
    attempt_count: int = 4,
) -> dict[str, Any]:
    """Fill normal visible login forms in an existing CDP browser."""

    if not username or not password:
        return {
            "status": "missing_credentials",
            "authenticated_page_reachable": False,
            "attempts": [],
            "page_location": None,
            "limitations": _limitations(),
        }

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - optional dependency boundary
        raise QuikStrikeBrowserLoginUnavailableError(
            "Install the optional browser dependency with: pip install -e .[browser]"
        ) from exc

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.connect_over_cdp(cdp_url)
        except Exception as exc:
            raise QuikStrikeBrowserLoginCdpError(
                "Could not connect to local CDP browser. Start it with "
                "scripts/start_quikstrike_session.ps1 first."
            ) from exc
        page = _select_page(browser)
        if _page_ready(page):
            return _result(
                status="authenticated_page_reachable",
                page=page,
                attempts=[],
                authenticated=True,
            )
        page.goto(start_url)
        deadline = time.monotonic() + max(wait_seconds, 1)
        attempts: list[dict[str, Any]] = []
        login_attempt_count = 0
        while login_attempt_count < max(attempt_count, 1) and time.monotonic() < deadline:
            disclaimer = _click_disclaimer_continue(page)
            if disclaimer.get("clicked"):
                attempts.append({"disclaimer_continue_clicked": True})
                page.wait_for_timeout(2500)
                try:
                    page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass
                if _page_ready(page):
                    return _result(
                        status="authenticated_page_reachable",
                        page=page,
                        attempts=attempts,
                        authenticated=True,
                    )
                continue
            if _page_ready(page):
                return _result(
                    status="authenticated_page_reachable",
                    page=page,
                    attempts=attempts,
                    authenticated=True,
                )
            try:
                outcome = page.evaluate(
                    BROWSER_LOGIN_SCRIPT,
                    {"username": username, "password": password},
                )
                attempts.append(_safe_attempt(outcome))
            except Exception:
                attempts.append({"navigation_in_progress": True})
            login_attempt_count += 1
            page.wait_for_timeout(2500)
            try:
                page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass
        authenticated = _page_ready(page)
        return _result(
            status="authenticated_page_reachable" if authenticated else "blocked_or_unverified",
            page=page,
            attempts=attempts,
            authenticated=authenticated,
        )


def _select_page(browser: Any) -> Any:
    for context in browser.contexts:
        for page in context.pages:
            if "quikstrike" in str(getattr(page, "url", "")).lower():
                return page
    for context in browser.contexts:
        if context.pages:
            return context.pages[0]
    return browser.new_page()


def _page_ready(page: Any) -> bool:
    try:
        text = page.locator("body").inner_text(timeout=1000)
    except Exception:
        return False
    return bool(QUIKSTRIKE_READY_PATTERN.search(text))


def _click_disclaimer_continue(page: Any) -> dict[str, Any]:
    try:
        url = str(getattr(page, "url", ""))
        text = page.locator("body").inner_text(timeout=1000)
        if "Disclaimer" not in text and "Disclaimer" not in url:
            return {"clicked": False}
        try:
            checkbox = page.locator("#chkAccept")
            if checkbox.count() and not checkbox.is_checked(timeout=1000):
                checkbox.click(timeout=2000)
            page.locator("#btnContinue").click(timeout=2000)
            return {"clicked": True, "native_click": True, "checked_accept": True}
        except Exception:
            outcome = page.evaluate(DISCLAIMER_CONTINUE_SCRIPT)
    except Exception:
        return {"clicked": False}
    return outcome if isinstance(outcome, dict) else {"clicked": False}


def _result(
    *,
    status: str,
    page: Any,
    attempts: list[dict[str, Any]],
    authenticated: bool,
) -> dict[str, Any]:
    return {
        "status": status,
        "authenticated_page_reachable": authenticated,
        "attempt_count": len(attempts),
        "attempts": attempts,
        "page_location": _sanitize_location(str(getattr(page, "url", ""))),
        "limitations": _limitations(),
    }


def _safe_attempt(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {
        "filled_username": bool(value.get("filled_username")),
        "filled_password": bool(value.get("filled_password")),
        "submitted": bool(value.get("submitted")),
        "had_username_input": bool(value.get("had_username_input")),
        "had_password_input": bool(value.get("had_password_input")),
        "button_count": _optional_int(value.get("button_count")),
    }


def _sanitize_location(value: str) -> dict[str, Any]:
    parsed = urlparse(value)
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


def _optional_int(value: object) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _limitations() -> list[str]:
    return [
        "Normal browser login helper fills visible page fields only.",
        "It does not read browser saved passwords, cookies, headers, tokens, viewstate, "
        "HAR files, screenshots, request bodies, response bodies, or private full URLs.",
        "If credentials are missing, use the browser password manager or reset the "
        "QuikStrike password manually.",
    ]
