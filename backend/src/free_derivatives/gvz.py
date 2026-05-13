"""GVZ public/fixture request planning and daily-close normalization."""

import csv
import io
from datetime import date, datetime
from pathlib import Path

from src.free_derivatives.processing import (
    GVZ_NOT_STRIKE_LEVEL_OI_LIMITATION,
    GVZ_PROXY_LIMITATION,
)
from src.models.free_derivatives import (
    FreeDerivativesBaseModel,
    GvzDailyCloseRecord,
    GvzRequest,
)

DATE_ALIASES = ["date", "observation_date", "timestamp"]
CLOSE_ALIASES = ["close", "value", "gvzcls", "gvz"]
MISSING_CLOSE_MARKERS = {"", ".", "NA", "N/A", "NULL", "NONE"}


class GvzRequestPlanItem(FreeDerivativesBaseModel):
    series_id: str
    start_date: date | None = None
    end_date: date | None = None
    source_url: str | None = None
    local_fixture_path: Path | None = None
    requested_item: str


def create_gvz_request_plan(request: GvzRequest) -> GvzRequestPlanItem:
    """Build deterministic GVZ request metadata without downloading data."""

    start_label = request.start_date.isoformat() if request.start_date else "unbounded"
    end_label = request.end_date.isoformat() if request.end_date else "unbounded"
    return GvzRequestPlanItem(
        series_id=request.series_id,
        start_date=request.start_date,
        end_date=request.end_date,
        source_url=request.source_url,
        local_fixture_path=request.local_fixture_path,
        requested_item=f"{request.series_id}:{start_label}:{end_label}",
    )


def read_gvz_fixture_rows(path: Path) -> list[dict[str, str]]:
    """Read local GVZ CSV fixture rows with source metadata."""

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return _read_csv_handle(handle, source_label=path.as_posix())


def normalize_gvz_rows(
    rows: list[dict[str, str]],
    *,
    series_id: str = "GVZCLS",
) -> list[GvzDailyCloseRecord]:
    """Normalize GVZ CSV/public payload rows into daily close records."""

    normalized_records: list[GvzDailyCloseRecord] = []
    for row in rows:
        normalized_row = {_normalize_key(key): value for key, value in row.items()}
        raw_close = _first_value(
            normalized_row,
            [_normalize_key(series_id), *CLOSE_ALIASES],
            allow_missing_marker=True,
        )
        close_value = _parse_optional_float(raw_close)
        normalized_records.append(
            GvzDailyCloseRecord(
                date=_parse_date(_first_value(normalized_row, DATE_ALIASES)),
                series_id=series_id,
                close=close_value,
                source=_first_value(normalized_row, ["_source_file"]) or "gvz_public_payload",
                is_missing=close_value is None,
                limitations=[GVZ_PROXY_LIMITATION, GVZ_NOT_STRIKE_LEVEL_OI_LIMITATION],
            )
        )
    return sorted(normalized_records, key=lambda record: record.date)


def filter_gvz_records_by_date(
    records: list[GvzDailyCloseRecord],
    *,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[GvzDailyCloseRecord]:
    """Apply inclusive GVZ date-window filtering."""

    filtered = records
    if start_date is not None:
        filtered = [record for record in filtered if record.date >= start_date]
    if end_date is not None:
        filtered = [record for record in filtered if record.date <= end_date]
    return filtered


def load_gvz_daily_close_records(request: GvzRequest) -> list[GvzDailyCloseRecord]:
    """Load and normalize a local GVZ daily close fixture for the requested window."""

    if request.local_fixture_path is None:
        return []
    rows = read_gvz_fixture_rows(request.local_fixture_path)
    records = normalize_gvz_rows(rows, series_id=request.series_id)
    return filter_gvz_records_by_date(
        records,
        start_date=request.start_date,
        end_date=request.end_date,
    )


def _read_csv_handle(handle: io.TextIOBase, *, source_label: str) -> list[dict[str, str]]:
    reader = csv.DictReader(handle)
    rows: list[dict[str, str]] = []
    for row_number, row in enumerate(reader, start=1):
        row_with_metadata = {key: value for key, value in row.items() if key is not None}
        row_with_metadata["_source_file"] = source_label
        row_with_metadata["_source_row_number"] = str(row_number)
        rows.append(row_with_metadata)
    return rows


def _parse_date(value: str | None):
    if not value:
        raise ValueError("GVZ date is required")
    normalized = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y%m%d"):
        try:
            return datetime.strptime(normalized, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unsupported GVZ date format: {value}")


def _parse_optional_float(value: str | None) -> float | None:
    if value is None:
        return None
    normalized = value.strip().replace(",", "")
    if normalized.upper() in MISSING_CLOSE_MARKERS:
        return None
    return float(normalized)


def _first_value(
    row: dict[str, str],
    aliases: list[str],
    *,
    allow_missing_marker: bool = False,
) -> str | None:
    for alias in aliases:
        value = row.get(_normalize_key(alias))
        if value is None:
            continue
        if value.strip() != "" or allow_missing_marker:
            return value.strip()
    return None


def _normalize_key(value: str) -> str:
    return value.strip().lower().replace(" ", "_").replace("-", "_")
