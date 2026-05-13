"""Parse sanitized QuikStrike Open Interest Matrix HTML table snapshots."""

import re
from dataclasses import dataclass
from html.parser import HTMLParser

from src.models.quikstrike_matrix import (
    QuikStrikeMatrixBodyCell,
    QuikStrikeMatrixCellState,
    QuikStrikeMatrixHeaderCell,
    QuikStrikeMatrixOptionType,
    QuikStrikeMatrixTableSnapshot,
)

EXPIRATION_CODE_PATTERN = re.compile(r"\b[A-Z0-9]{1,5}[FGHJKMNQUVXZ]\d{1,2}\b")
DTE_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*DTE", re.IGNORECASE)
FUTURES_SYMBOL_PATTERN = re.compile(r"\bGC[A-Z]\d{1,2}\b|\bGC\b", re.IGNORECASE)
NUMBER_PATTERN = re.compile(r"[-+]?\(?\d[\d,]*(?:\.\d+)?\)?")
STRIKE_MIN = 500.0
STRIKE_MAX = 10000.0


@dataclass(frozen=True)
class ParsedMatrixTable:
    header_cells: list[QuikStrikeMatrixHeaderCell]
    body_cells: list[QuikStrikeMatrixBodyCell]
    warnings: list[str]
    limitations: list[str]


@dataclass(frozen=True)
class _RawCell:
    text: str
    colspan: int
    rowspan: int
    is_header: bool


@dataclass(frozen=True)
class _ColumnContext:
    column_index: int
    label: str
    expiration: str | None
    dte: float | None
    futures_symbol: str | None
    future_reference_price: float | None
    option_type: QuikStrikeMatrixOptionType | None


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[_RawCell]] = []
        self._current_row: list[_RawCell] | None = None
        self._current_tag: str | None = None
        self._current_text: list[str] = []
        self._current_attrs: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized = tag.lower()
        if normalized == "tr":
            self._current_row = []
            return
        if normalized in {"th", "td"} and self._current_row is not None:
            self._current_tag = normalized
            self._current_text = []
            self._current_attrs = {key.lower(): value or "" for key, value in attrs}

    def handle_data(self, data: str) -> None:
        if self._current_tag is not None:
            self._current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        if normalized in {"th", "td"} and self._current_tag is not None:
            colspan = _safe_span(self._current_attrs.get("colspan"))
            rowspan = _safe_span(self._current_attrs.get("rowspan"))
            text = " ".join("".join(self._current_text).split())
            self._current_row.append(
                _RawCell(
                    text=text,
                    colspan=colspan,
                    rowspan=rowspan,
                    is_header=self._current_tag == "th",
                )
            )
            self._current_tag = None
            self._current_text = []
            self._current_attrs = {}
            return
        if normalized == "tr" and self._current_row is not None:
            self.rows.append(self._current_row)
            self._current_row = None


def parse_matrix_table(snapshot: QuikStrikeMatrixTableSnapshot) -> ParsedMatrixTable:
    """Parse one sanitized table snapshot into header and body cells."""

    rows = _rows_from_snapshot(snapshot)
    if not rows:
        return ParsedMatrixTable(
            header_cells=[],
            body_cells=[],
            warnings=["Matrix table did not contain any rows."],
            limitations=[],
        )

    first_body_index = _first_body_row_index(rows)
    if first_body_index is None:
        return ParsedMatrixTable(
            header_cells=[],
            body_cells=[],
            warnings=["Matrix table did not contain numeric strike rows."],
            limitations=[],
        )

    header_rows = rows[:first_body_index]
    body_rows = rows[first_body_index:]
    column_contexts = _column_contexts(header_rows)
    header_cells = _header_cells(header_rows, column_contexts)
    body_cells: list[QuikStrikeMatrixBodyCell] = []
    warnings: list[str] = []

    for body_row_index, row in enumerate(body_rows):
        expanded = _expand_row(row)
        if not expanded:
            continue
        strike = parse_strike(expanded[0].text)
        if strike is None:
            continue
        for column_index, raw_cell in enumerate(expanded[1:], start=1):
            context = column_contexts.get(column_index)
            if context is None:
                warnings.append(f"No expiration header mapped for column {column_index}.")
                continue
            numeric_value, state = parse_numeric_cell(raw_cell.text)
            body_cells.append(
                QuikStrikeMatrixBodyCell(
                    row_index=body_row_index,
                    column_index=column_index,
                    strike=strike,
                    row_label=expanded[0].text,
                    column_label=context.label,
                    raw_value=raw_cell.text,
                    numeric_value=numeric_value,
                    cell_state=state,
                    option_type=context.option_type,
                    expiration=context.expiration,
                    dte=context.dte,
                    futures_symbol=context.futures_symbol,
                    future_reference_price=context.future_reference_price,
                )
            )

    return ParsedMatrixTable(
        header_cells=header_cells,
        body_cells=body_cells,
        warnings=_dedupe(warnings),
        limitations=snapshot.limitations,
    )


def parse_strike(value: str) -> float | None:
    normalized = " ".join(str(value).split())
    if not normalized or _is_non_strike_label(normalized):
        return None
    match = NUMBER_PATTERN.search(normalized)
    if not match:
        return None
    number = _parse_numeric_text(match.group(0))
    if number is None or not STRIKE_MIN <= number <= STRIKE_MAX:
        return None
    return number


def parse_numeric_cell(value: str | None) -> tuple[float | None, QuikStrikeMatrixCellState]:
    normalized = " ".join(str(value or "").split())
    if normalized == "":
        return None, QuikStrikeMatrixCellState.BLANK
    if normalized.lower() in {"-", "--", "—", "n/a", "na", "null"}:
        return None, QuikStrikeMatrixCellState.UNAVAILABLE
    parsed = _parse_numeric_text(normalized)
    if parsed is None:
        return None, QuikStrikeMatrixCellState.INVALID
    return parsed, QuikStrikeMatrixCellState.AVAILABLE


def parse_expiration_from_header(value: str) -> str | None:
    match = EXPIRATION_CODE_PATTERN.search(value)
    if match:
        return match.group(0).upper()
    date_match = re.search(r"\b\d{1,2}\s+[A-Z][a-z]{2}\s+\d{4}\b", value)
    if date_match:
        return date_match.group(0)
    return None


def parse_dte_from_header(value: str) -> float | None:
    match = DTE_PATTERN.search(value)
    return float(match.group(1)) if match else None


def parse_futures_symbol_from_header(value: str) -> str | None:
    match = FUTURES_SYMBOL_PATTERN.search(value)
    return match.group(0).upper() if match else None


def parse_reference_price_from_header(value: str) -> float | None:
    matches = NUMBER_PATTERN.findall(value)
    candidates = [_parse_numeric_text(match) for match in matches]
    for candidate in candidates:
        if candidate is not None and 500 <= candidate <= 10000:
            return candidate
    return None


def _rows_from_snapshot(snapshot: QuikStrikeMatrixTableSnapshot) -> list[list[_RawCell]]:
    if snapshot.html_table is not None:
        parser = _TableParser()
        parser.feed(snapshot.html_table)
        return parser.rows
    rows: list[list[_RawCell]] = []
    for raw_row in [*snapshot.header_rows, *snapshot.body_rows]:
        rows.append(
            [
                _RawCell(text=str(cell), colspan=1, rowspan=1, is_header=True)
                for cell in raw_row
            ]
        )
    return rows


def _first_body_row_index(rows: list[list[_RawCell]]) -> int | None:
    for index, row in enumerate(rows):
        expanded = _expand_row(row)
        if expanded and parse_strike(expanded[0].text) is not None:
            return index
    return None


def _column_contexts(header_rows: list[list[_RawCell]]) -> dict[int, _ColumnContext]:
    expanded_rows = [_expand_row(row) for row in header_rows]
    max_columns = max((len(row) for row in expanded_rows), default=0)
    contexts: dict[int, _ColumnContext] = {}
    for column_index in range(1, max_columns):
        header_texts = [
            row[column_index].text
            for row in expanded_rows
            if column_index < len(row) and row[column_index].text
        ]
        context_texts = [
            text for text in header_texts if not _is_side_or_strike_header(text)
        ]
        side_texts = [
            text for text in header_texts if _option_type_from_text(text) is not None
        ]
        expiration_source = " ".join(context_texts)
        leaf_label = " ".join(header_texts)
        expiration = parse_expiration_from_header(expiration_source)
        contexts[column_index] = _ColumnContext(
            column_index=column_index,
            label=leaf_label or f"column_{column_index}",
            expiration=expiration,
            dte=parse_dte_from_header(expiration_source),
            futures_symbol=parse_futures_symbol_from_header(expiration_source),
            future_reference_price=parse_reference_price_from_header(expiration_source),
            option_type=(
                _option_type_from_text(side_texts[-1])
                if side_texts
                else QuikStrikeMatrixOptionType.COMBINED
            ),
        )
    return contexts


def _header_cells(
    header_rows: list[list[_RawCell]],
    contexts: dict[int, _ColumnContext],
) -> list[QuikStrikeMatrixHeaderCell]:
    cells: list[QuikStrikeMatrixHeaderCell] = []
    for row_index, row in enumerate(header_rows):
        column_index = 0
        for raw_cell in row:
            context = contexts.get(column_index)
            cells.append(
                QuikStrikeMatrixHeaderCell(
                    text=raw_cell.text,
                    column_index=column_index,
                    row_index=row_index,
                    colspan=raw_cell.colspan,
                    rowspan=raw_cell.rowspan,
                    expiration=(
                        context.expiration
                        if context
                        else parse_expiration_from_header(raw_cell.text)
                    ),
                    dte=context.dte if context else parse_dte_from_header(raw_cell.text),
                    futures_symbol=(
                        context.futures_symbol
                        if context
                        else parse_futures_symbol_from_header(raw_cell.text)
                    ),
                    future_reference_price=(
                        context.future_reference_price
                        if context
                        else parse_reference_price_from_header(raw_cell.text)
                    ),
                    option_type=(
                        context.option_type if context else _option_type_from_text(raw_cell.text)
                    ),
                )
            )
            column_index += raw_cell.colspan
    return cells


def _expand_row(row: list[_RawCell]) -> list[_RawCell]:
    expanded: list[_RawCell] = []
    for cell in row:
        expanded.extend([cell] * cell.colspan)
    return expanded


def _option_type_from_text(value: str) -> QuikStrikeMatrixOptionType | None:
    normalized = value.strip().lower()
    if normalized in {"call", "calls", "c"}:
        return QuikStrikeMatrixOptionType.CALL
    if normalized in {"put", "puts", "p"}:
        return QuikStrikeMatrixOptionType.PUT
    if normalized in {"combined", "total", "both"}:
        return QuikStrikeMatrixOptionType.COMBINED
    return None


def _is_side_or_strike_header(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized in {"", "strike", "strikes"} or _option_type_from_text(value) is not None


def _is_non_strike_label(value: str) -> bool:
    normalized = value.strip().lower()
    return any(
        token in normalized
        for token in ("total", "subtotal", "strike", "calls", "puts", "expiration")
    )


def _parse_numeric_text(value: str) -> float | None:
    normalized = value.strip()
    negative = normalized.startswith("(") and normalized.endswith(")")
    normalized = normalized.replace(",", "").replace("(", "").replace(")", "")
    try:
        parsed = float(normalized)
    except ValueError:
        return None
    return -parsed if negative else parsed


def _safe_span(value: str | None) -> int:
    try:
        parsed = int(value or "1")
    except ValueError:
        return 1
    return max(parsed, 1)


def _dedupe(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        if value and value not in deduped:
            deduped.append(value)
    return deduped
