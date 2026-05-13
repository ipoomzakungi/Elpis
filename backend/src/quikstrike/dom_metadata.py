"""Parse sanitized QuikStrike visible DOM/header text."""

import re
from datetime import date

from src.models.quikstrike import (
    QuikStrikeDomMetadata,
    QuikStrikeViewType,
    ensure_no_forbidden_quikstrike_content,
)

PRODUCT_PATTERN = re.compile(r"(?P<product>[A-Za-z][A-Za-z\s]+?)\s*\((?P<code>[^)]+)\)")
DTE_PATTERN = re.compile(r"\((?P<dte>\d+(?:\.\d+)?)\s*DTE\)", re.IGNORECASE)
REFERENCE_PRICE_PATTERN = re.compile(r"\bvs\s+(?P<price>\d+(?:\.\d+)?)", re.IGNORECASE)
EXPIRATION_PATTERN = re.compile(
    r"\b(?P<day>\d{1,2})\s+"
    r"(?P<month>Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+"
    r"(?P<year>\d{4})\b",
    re.IGNORECASE,
)
MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def parse_dom_metadata(
    header_text: str,
    *,
    selector_text: str | None = None,
    selected_view_type: QuikStrikeViewType | str | None = None,
    source_view: str = "QUIKOPTIONS VOL2VOL",
    surface: str = "QUIKOPTIONS VOL2VOL",
) -> QuikStrikeDomMetadata:
    """Parse sanitized synthetic DOM/header text into QuikStrike metadata."""

    payload = {
        "header_text": header_text,
        "selector_text": selector_text,
        "source_view": source_view,
        "surface": surface,
    }
    ensure_no_forbidden_quikstrike_content(payload)
    normalized_header = _normalize_text(header_text)
    normalized_selector = _normalize_optional_text(selector_text)
    combined = f"{normalized_header} {normalized_selector}".strip()
    product, option_product_code = _parse_product_and_code(combined)
    view_type = (
        QuikStrikeViewType(selected_view_type)
        if selected_view_type is not None
        else infer_view_type(normalized_header)
    )
    warnings: list[str] = []
    expiration = _parse_expiration(combined)
    if expiration is None:
        warnings.append("Expiration was not available in sanitized DOM text.")
    dte = _parse_dte(normalized_header)
    if dte is None:
        warnings.append("DTE was not available in sanitized DOM text.")
    future_reference_price = _parse_reference_price(normalized_header)
    if future_reference_price is None:
        warnings.append("Future reference price was not available in sanitized DOM text.")

    return QuikStrikeDomMetadata(
        product=product,
        option_product_code=option_product_code,
        futures_symbol=_futures_symbol_from_code(option_product_code),
        expiration=expiration,
        dte=dte,
        future_reference_price=future_reference_price,
        source_view=source_view,
        selected_view_type=view_type,
        surface=surface,
        raw_header_text=normalized_header,
        raw_selector_text=normalized_selector or None,
        warnings=warnings,
        limitations=["Sanitized visible DOM text only; no session data stored."],
    )


def infer_view_type(text: str) -> QuikStrikeViewType:
    normalized = _normalize_text(text).lower()
    if "intraday volume" in normalized:
        return QuikStrikeViewType.INTRADAY_VOLUME
    if "eod volume" in normalized:
        return QuikStrikeViewType.EOD_VOLUME
    if "open interest change" in normalized or "oi change" in normalized:
        return QuikStrikeViewType.OI_CHANGE
    if "open interest" in normalized:
        return QuikStrikeViewType.OPEN_INTEREST
    if "churn" in normalized:
        return QuikStrikeViewType.CHURN
    raise ValueError("Could not infer supported QuikStrike view type from DOM text")


def _parse_product_and_code(text: str) -> tuple[str, str]:
    match = PRODUCT_PATTERN.search(text)
    if match is None:
        raise ValueError("Could not parse QuikStrike product and option code")
    return _normalize_text(match.group("product")), _normalize_text(match.group("code"))


def _parse_dte(text: str) -> float | None:
    match = DTE_PATTERN.search(text)
    return float(match.group("dte")) if match else None


def _parse_reference_price(text: str) -> float | None:
    match = REFERENCE_PRICE_PATTERN.search(text)
    return float(match.group("price")) if match else None


def _parse_expiration(text: str) -> date | None:
    match = EXPIRATION_PATTERN.search(text)
    if match is None:
        return None
    month = MONTHS[match.group("month")[:3].lower()]
    return date(int(match.group("year")), month, int(match.group("day")))


def _futures_symbol_from_code(option_product_code: str) -> str | None:
    parts = [part.strip().upper() for part in option_product_code.split("|") if part.strip()]
    if len(parts) >= 2:
        return parts[-1]
    return parts[0] if parts else None


def _normalize_text(value: str) -> str:
    normalized = " ".join(str(value).split())
    if not normalized:
        raise ValueError("QuikStrike DOM text must not be blank")
    return normalized


def _normalize_optional_text(value: str | None) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())
