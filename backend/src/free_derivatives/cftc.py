"""CFTC COT fixture/request planning and gold positioning normalization."""

import csv
import io
import zipfile
from pathlib import Path

from src.free_derivatives.processing import CFTC_WEEKLY_POSITIONING_LIMITATION
from src.models.free_derivatives import (
    CftcCotGoldRecord,
    CftcCotReportCategory,
    CftcCotRequest,
    FreeDerivativesBaseModel,
)

COMEX_ALIASES = {"comex", "commodity exchange", "commodity exchange inc"}

DATE_ALIASES = [
    "report_date",
    "as_of_date_in_form_yymmdd",
    "as_of_date_in_form_yyymmdd",
    "report_date_as_yyyy_mm_dd",
    "report_date_as_yyyy-mm-dd",
    "as_of_date",
]
MARKET_EXCHANGE_ALIASES = [
    "market_and_exchange_names",
    "market_and_exchange_name",
    "market_exchange",
]
MARKET_ALIASES = ["market_name", "commodity_name", "market"]
EXCHANGE_ALIASES = ["exchange_name", "exchange"]
CATEGORY_ALIASES = ["report_category", "category", "cot_report_category"]

NUMERIC_ALIASES: dict[str, list[str]] = {
    "open_interest": ["open_interest", "open_interest_all", "open_interest_"],
    "noncommercial_long": [
        "noncommercial_long",
        "noncommercial_long_all",
        "noncomm_positions_long_all",
        "noncommercial_positions_long_all",
    ],
    "noncommercial_short": [
        "noncommercial_short",
        "noncommercial_short_all",
        "noncomm_positions_short_all",
        "noncommercial_positions_short_all",
    ],
    "noncommercial_spread": [
        "noncommercial_spread",
        "noncommercial_spread_all",
        "noncomm_postions_spread_all",
        "noncommercial_positions_spread_all",
    ],
    "commercial_long": [
        "commercial_long",
        "commercial_long_all",
        "commercial_positions_long_all",
    ],
    "commercial_short": [
        "commercial_short",
        "commercial_short_all",
        "commercial_positions_short_all",
    ],
    "total_reportable_long": [
        "total_reportable_long",
        "tot_rept_long_all",
        "total_reportable_positions_long_all",
    ],
    "total_reportable_short": [
        "total_reportable_short",
        "tot_rept_short_all",
        "total_reportable_positions_short_all",
    ],
    "nonreportable_long": [
        "nonreportable_long",
        "nonrept_long_all",
        "nonreportable_positions_long_all",
    ],
    "nonreportable_short": [
        "nonreportable_short",
        "nonrept_short_all",
        "nonreportable_positions_short_all",
    ],
}


class CftcCotRequestPlanItem(FreeDerivativesBaseModel):
    year: int | None
    category: CftcCotReportCategory
    source_url: str | None = None
    local_fixture_paths: list[Path]
    requested_item: str


def create_cftc_request_plan(request: CftcCotRequest) -> list[CftcCotRequestPlanItem]:
    """Build deterministic CFTC plan items without downloading external data."""

    years: list[int | None] = request.years or [None]
    plan: list[CftcCotRequestPlanItem] = []
    source_urls = request.source_urls
    url_index = 0
    for year in years:
        for category in request.categories:
            source_url = source_urls[url_index] if url_index < len(source_urls) else None
            if source_url is not None:
                url_index += 1
            plan.append(
                CftcCotRequestPlanItem(
                    year=year,
                    category=category,
                    source_url=source_url,
                    local_fixture_paths=request.local_fixture_paths,
                    requested_item=_requested_item(year, category),
                )
            )
    return plan


def read_cftc_fixture_rows(paths: list[Path]) -> list[dict[str, str]]:
    """Read local CFTC CSV or zipped CSV fixture rows with source metadata."""

    rows: list[dict[str, str]] = []
    for path in paths:
        if path.suffix.lower() == ".zip":
            rows.extend(_read_zipped_csv(path))
        else:
            rows.extend(_read_csv(path, source_label=path.as_posix()))
    return rows


def normalize_cftc_rows(
    rows: list[dict[str, str]],
    *,
    default_category: CftcCotReportCategory,
) -> list[CftcCotGoldRecord]:
    """Normalize CFTC rows into broad positioning records before gold filtering."""

    normalized_records: list[CftcCotGoldRecord] = []
    for row in rows:
        normalized_row = {_normalize_key(key): value for key, value in row.items()}
        market_name, exchange_name = _market_and_exchange(normalized_row)
        category = _category_from_row(normalized_row, default_category)
        numeric_values = {
            field_name: _parse_optional_float(_first_value(normalized_row, aliases))
            for field_name, aliases in NUMERIC_ALIASES.items()
        }
        normalized_records.append(
            CftcCotGoldRecord(
                report_date=_parse_report_date(_first_value(normalized_row, DATE_ALIASES)),
                report_category=category,
                market_name=market_name,
                exchange_name=exchange_name,
                cftc_contract_market_code=_first_value(
                    normalized_row,
                    ["cftc_contract_market_code", "contract_market_code"],
                ),
                commodity_name=_first_value(normalized_row, ["commodity_name"]) or market_name,
                source_file=(
                    _first_value(normalized_row, ["_source_file"])
                    or "unknown_cftc_fixture"
                ),
                source_row_number=int(
                    _first_value(normalized_row, ["_source_row_number"]) or "1"
                ),
                limitations=[CFTC_WEEKLY_POSITIONING_LIMITATION],
                **numeric_values,
            )
        )
    return normalized_records


def filter_gold_comex_records(
    records: list[CftcCotGoldRecord],
    *,
    market_filters: list[str],
) -> list[CftcCotGoldRecord]:
    """Keep gold/COMEX rows and store the matched filter metadata on each record."""

    filtered: list[CftcCotGoldRecord] = []
    for record in records:
        matched_filters = _matched_filters(record, market_filters)
        expected_filters = {_normalize_filter(value) for value in market_filters}
        if expected_filters.issubset(set(matched_filters)):
            filtered.append(record.model_copy(update={"matched_filters": matched_filters}))
    return filtered


def load_cftc_gold_records(request: CftcCotRequest) -> list[CftcCotGoldRecord]:
    """Load and normalize local CFTC fixtures for the requested COT categories."""

    if not request.local_fixture_paths:
        return []
    raw_rows = read_cftc_fixture_rows(request.local_fixture_paths)
    default_category = request.categories[0]
    records = normalize_cftc_rows(raw_rows, default_category=default_category)
    requested_categories = set(request.categories)
    records = [
        record for record in records if record.report_category in requested_categories
    ]
    return filter_gold_comex_records(records, market_filters=request.market_filters)


def _read_zipped_csv(path: Path) -> list[dict[str, str]]:
    with zipfile.ZipFile(path) as archive:
        csv_names = [
            name
            for name in archive.namelist()
            if name.lower().endswith((".csv", ".txt"))
        ]
        if not csv_names:
            raise ValueError(f"CFTC fixture archive has no CSV/TXT file: {path}")
        with archive.open(csv_names[0]) as handle:
            text_handle = io.TextIOWrapper(handle, encoding="utf-8-sig", newline="")
            return _read_csv_handle(
                text_handle,
                source_label=f"{path.as_posix()}:{csv_names[0]}",
            )


def _read_csv(path: Path, *, source_label: str) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return _read_csv_handle(handle, source_label=source_label)


def _read_csv_handle(handle: io.TextIOBase, *, source_label: str) -> list[dict[str, str]]:
    reader = csv.DictReader(handle)
    rows: list[dict[str, str]] = []
    for row_number, row in enumerate(reader, start=1):
        row_with_metadata = {key: value for key, value in row.items() if key is not None}
        row_with_metadata["_source_file"] = source_label
        row_with_metadata["_source_row_number"] = str(row_number)
        rows.append(row_with_metadata)
    return rows


def _market_and_exchange(row: dict[str, str]) -> tuple[str, str]:
    market_exchange = _first_value(row, MARKET_EXCHANGE_ALIASES)
    market_name = _first_value(row, MARKET_ALIASES)
    exchange_name = _first_value(row, EXCHANGE_ALIASES)
    if market_exchange:
        if " - " in market_exchange:
            left, right = market_exchange.split(" - ", 1)
            market_name = market_name or left.strip()
            exchange_name = exchange_name or right.strip()
        else:
            market_name = market_name or market_exchange
    return market_name or "UNKNOWN", exchange_name or "UNKNOWN"


def _category_from_row(
    row: dict[str, str],
    default_category: CftcCotReportCategory,
) -> CftcCotReportCategory:
    raw_category = _first_value(row, CATEGORY_ALIASES)
    if not raw_category:
        return default_category
    normalized = raw_category.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "futures": CftcCotReportCategory.FUTURES_ONLY,
        "futures_only": CftcCotReportCategory.FUTURES_ONLY,
        "legacy_futures_only": CftcCotReportCategory.FUTURES_ONLY,
        "combined": CftcCotReportCategory.FUTURES_AND_OPTIONS_COMBINED,
        "futures_and_options": CftcCotReportCategory.FUTURES_AND_OPTIONS_COMBINED,
        "futures_and_options_combined": (
            CftcCotReportCategory.FUTURES_AND_OPTIONS_COMBINED
        ),
    }
    try:
        return CftcCotReportCategory(normalized)
    except ValueError:
        return aliases.get(normalized, default_category)


def _matched_filters(record: CftcCotGoldRecord, market_filters: list[str]) -> list[str]:
    haystack = " ".join(
        [
            record.market_name,
            record.exchange_name,
            record.commodity_name or "",
        ]
    ).lower()
    matches: list[str] = []
    for market_filter in market_filters:
        normalized = _normalize_filter(market_filter)
        if normalized == "comex":
            if any(alias in haystack for alias in COMEX_ALIASES):
                matches.append("comex")
        elif normalized and normalized in haystack:
            matches.append(normalized)
    return list(dict.fromkeys(matches))


def _parse_report_date(value: str | None):
    if not value:
        raise ValueError("CFTC report date is required")
    normalized = value.strip()
    compact_formats = ["%y%m%d"] if len(normalized) == 6 else ["%Y%m%d"]
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", *compact_formats):
        try:
            from datetime import datetime

            return datetime.strptime(normalized, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unsupported CFTC report date format: {value}")


def _parse_optional_float(value: str | None) -> float | None:
    if value is None:
        return None
    normalized = value.strip().replace(",", "")
    if normalized in {"", ".", "NA", "N/A"}:
        return None
    return float(normalized)


def _first_value(row: dict[str, str], aliases: list[str]) -> str | None:
    for alias in aliases:
        value = row.get(_normalize_key(alias))
        if value is not None and value.strip() != "":
            return value.strip()
    return None


def _normalize_filter(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"commodity_exchange", "commodity exchange inc"}:
        return "comex"
    return normalized


def _normalize_key(value: str) -> str:
    return value.strip().lower().replace(" ", "_").replace("-", "_")


def _requested_item(year: int | None, category: CftcCotReportCategory) -> str:
    if year is None:
        return category.value
    return f"{year}:{category.value}"
