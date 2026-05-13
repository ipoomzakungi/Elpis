"""Parse sanitized visible metadata for QuikStrike Matrix tables."""

import re
from datetime import UTC, datetime

from src.models.quikstrike_matrix import (
    QuikStrikeMatrixMetadata,
    QuikStrikeMatrixViewType,
)

OPTION_CODE_PATTERN = re.compile(r"\(([^()]*OG\|GC[^()]*)\)", re.IGNORECASE)
FUTURES_SYMBOL_PATTERN = re.compile(r"\bGC[A-Z]\d{1,2}\b|\bGC\b", re.IGNORECASE)


def parse_matrix_metadata(
    *,
    raw_visible_text: str,
    view_type: QuikStrikeMatrixViewType,
    capture_timestamp: datetime | None = None,
    selected_view_label: str | None = None,
) -> QuikStrikeMatrixMetadata:
    """Create strict metadata from sanitized visible page text."""

    normalized = " ".join(raw_visible_text.split())
    product = "Gold" if "gold" in normalized.lower() else "Gold"
    option_code = _option_product_code(normalized)
    return QuikStrikeMatrixMetadata(
        capture_timestamp=capture_timestamp or datetime.now(UTC),
        product=product,
        option_product_code=option_code,
        futures_symbol=_futures_symbol(normalized),
        source_menu="OPEN INTEREST Matrix",
        selected_view_type=view_type,
        selected_view_label=selected_view_label or _view_label(view_type),
        table_title=_table_title(normalized, view_type),
        raw_visible_text=normalized,
        limitations=["Local user-controlled QuikStrike table extraction only."],
    )


def _option_product_code(value: str) -> str:
    match = OPTION_CODE_PATTERN.search(value)
    if match:
        return match.group(1).strip()
    if "og|gc" in value.lower():
        return "OG|GC"
    return "OG|GC"


def _futures_symbol(value: str) -> str | None:
    match = FUTURES_SYMBOL_PATTERN.search(value)
    return match.group(0).upper() if match else "GC"


def _view_label(view_type: QuikStrikeMatrixViewType) -> str:
    labels = {
        QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX: "OI Matrix",
        QuikStrikeMatrixViewType.OI_CHANGE_MATRIX: "OI Change Matrix",
        QuikStrikeMatrixViewType.VOLUME_MATRIX: "Volume Matrix",
    }
    return labels[view_type]


def _table_title(value: str, view_type: QuikStrikeMatrixViewType) -> str:
    if "gold" in value.lower():
        return f"Gold {_view_label(view_type)}"
    return _view_label(view_type)
