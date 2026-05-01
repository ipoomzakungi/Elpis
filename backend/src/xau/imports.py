from datetime import date, datetime, time
from pathlib import Path
from typing import Any

import polars as pl

from src.models.xau import XauOptionsImportReport, XauOptionsOiRow, XauOptionType

DATE_COLUMNS = ("timestamp", "date")
REQUIRED_OPTION_COLUMNS = ("expiry", "strike", "option_type", "open_interest")
OPTIONAL_OPTION_COLUMNS = (
    "oi_change",
    "volume",
    "implied_volatility",
    "underlying_futures_price",
    "xauusd_spot_price",
    "delta",
    "gamma",
)
SUPPORTED_SUFFIXES = {".csv", ".parquet"}


def validate_options_oi_file(
    file_path: str | Path,
    *,
    base_dir: str | Path | None = None,
) -> XauOptionsImportReport:
    """Validate and normalize a local gold options OI CSV or Parquet file."""

    path = Path(file_path)
    try:
        resolved = resolve_options_oi_path(path, base_dir=base_dir)
        frame = read_options_oi_file(resolved)
    except ValueError as exc:
        return _invalid_file_report(path, str(exc))
    except OSError as exc:
        return _invalid_file_report(path, f"Unable to read file: {exc}")
    except Exception as exc:
        return _invalid_file_report(path, f"Unable to parse file: {exc}")
    return validate_options_oi_frame(frame, file_path=str(resolved))


def resolve_options_oi_path(
    file_path: str | Path,
    *,
    base_dir: str | Path | None = None,
) -> Path:
    """Resolve a local options file path while rejecting traversal-style input."""

    path = Path(file_path)
    if ".." in path.parts:
        raise ValueError("Unsafe file path: parent-directory traversal is not allowed")
    if path.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise ValueError("Only CSV and Parquet gold options OI files are supported")

    resolved = path.resolve()
    if base_dir is not None:
        base = Path(base_dir).resolve()
        try:
            resolved.relative_to(base)
        except ValueError as exc:
            raise ValueError(
                "Unsafe file path: file must be under the configured base_dir"
            ) from exc
    if not resolved.exists():
        raise ValueError(f"File not found: {path}")
    return resolved


def read_options_oi_file(file_path: str | Path) -> pl.DataFrame:
    path = Path(file_path)
    if path.suffix.lower() == ".csv":
        return pl.read_csv(path)
    if path.suffix.lower() == ".parquet":
        return pl.read_parquet(path)
    raise ValueError("Only CSV and Parquet gold options OI files are supported")


def validate_options_oi_frame(
    frame: pl.DataFrame,
    *,
    file_path: str = "memory",
) -> XauOptionsImportReport:
    """Validate a Polars DataFrame and return normalized XAU options rows."""

    timestamp_column = _timestamp_column(frame)
    missing = _missing_required_columns(frame, timestamp_column)
    optional_present = [column for column in OPTIONAL_OPTION_COLUMNS if column in frame.columns]

    if missing:
        return XauOptionsImportReport(
            file_path=file_path,
            is_valid=False,
            source_row_count=frame.height,
            accepted_row_count=0,
            rejected_row_count=frame.height,
            required_columns_missing=missing,
            optional_columns_present=optional_present,
            timestamp_column=timestamp_column,
            errors=[f"Missing required columns: {', '.join(missing)}"],
            instructions=[
                "Provide a local CSV or Parquet file with date or timestamp, expiry, strike, "
                "option_type, and open_interest columns."
            ],
        )

    accepted: list[XauOptionsOiRow] = []
    errors: list[str] = []
    warnings: list[str] = []
    for index, raw_row in enumerate(frame.to_dicts(), start=1):
        row, row_errors, row_warnings = _parse_row(raw_row, index, timestamp_column)
        if row_errors:
            errors.extend(f"row {index}: {message}" for message in row_errors)
            continue
        if row is not None:
            accepted.append(row)
        warnings.extend(f"row {index}: {message}" for message in row_warnings)

    rejected = frame.height - len(accepted)
    return XauOptionsImportReport(
        file_path=file_path,
        is_valid=not errors and bool(accepted),
        source_row_count=frame.height,
        accepted_row_count=len(accepted),
        rejected_row_count=rejected,
        required_columns_missing=[],
        optional_columns_present=optional_present,
        timestamp_column=timestamp_column,
        rows=accepted,
        errors=errors,
        warnings=warnings,
        instructions=_instructions(errors),
    )


def _invalid_file_report(file_path: Path, error: str) -> XauOptionsImportReport:
    return XauOptionsImportReport(
        file_path=str(file_path),
        is_valid=False,
        source_row_count=0,
        accepted_row_count=0,
        rejected_row_count=0,
        errors=[error],
        instructions=[
            "Place a readable CSV or Parquet gold options OI file under an ignored research "
            "data folder such as data/raw/xau/."
        ],
    )


def _timestamp_column(frame: pl.DataFrame) -> str | None:
    for column in DATE_COLUMNS:
        if column in frame.columns:
            return column
    return None


def _missing_required_columns(frame: pl.DataFrame, timestamp_column: str | None) -> list[str]:
    missing = []
    if timestamp_column is None:
        missing.append("date or timestamp")
    missing.extend(column for column in REQUIRED_OPTION_COLUMNS if column not in frame.columns)
    return missing


def _parse_row(
    raw_row: dict[str, Any],
    index: int,
    timestamp_column: str | None,
) -> tuple[XauOptionsOiRow | None, list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    timestamp = _parse_datetime(raw_row.get(timestamp_column), "timestamp", errors)
    expiry = _parse_date(raw_row.get("expiry"), "expiry", errors)
    strike = _parse_float(raw_row.get("strike"), "strike", errors)
    open_interest = _parse_float(raw_row.get("open_interest"), "open_interest", errors)
    option_type = _normalize_option_type(raw_row.get("option_type"))
    if option_type == XauOptionType.UNKNOWN:
        warnings.append("option_type is unknown; put/call wall classification will be limited")

    if timestamp is None or expiry is None or strike is None or open_interest is None:
        return None, errors, warnings
    if strike <= 0:
        errors.append("strike must be greater than 0")
        return None, errors, warnings
    if open_interest < 0:
        errors.append("open_interest must be greater than or equal to 0")
        return None, errors, warnings

    days_to_expiry = (expiry - timestamp.date()).days
    if days_to_expiry < 0:
        errors.append("expiry must not be before the source timestamp date")
        return None, errors, warnings

    row = XauOptionsOiRow(
        source_row_id=f"row_{index}",
        timestamp=timestamp,
        expiry=expiry,
        days_to_expiry=days_to_expiry,
        strike=strike,
        option_type=option_type,
        open_interest=open_interest,
        oi_change=_optional_float(raw_row.get("oi_change"), "oi_change", warnings),
        volume=_optional_float(raw_row.get("volume"), "volume", warnings, min_value=0.0),
        implied_volatility=_optional_float(
            raw_row.get("implied_volatility"),
            "implied_volatility",
            warnings,
            min_value=0.0,
            strict_min=True,
        ),
        underlying_futures_price=_optional_float(
            raw_row.get("underlying_futures_price"),
            "underlying_futures_price",
            warnings,
            min_value=0.0,
            strict_min=True,
        ),
        xauusd_spot_price=_optional_float(
            raw_row.get("xauusd_spot_price"),
            "xauusd_spot_price",
            warnings,
            min_value=0.0,
            strict_min=True,
        ),
        delta=_optional_float(raw_row.get("delta"), "delta", warnings),
        gamma=_optional_float(raw_row.get("gamma"), "gamma", warnings),
        validation_notes=warnings.copy(),
    )
    return row, errors, warnings


def _normalize_option_type(value: Any) -> XauOptionType:
    return XauOptionsOiRow.normalize_option_type(value)


def _parse_datetime(value: Any, field: str, errors: list[str]) -> datetime | None:
    if value is None:
        errors.append(f"{field} is required")
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min)
    text = str(value).strip()
    if not text:
        errors.append(f"{field} is required")
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed_date = date.fromisoformat(text)
        except ValueError:
            errors.append(f"{field} is not parseable")
            return None
        return datetime.combine(parsed_date, time.min)
    return parsed


def _parse_date(value: Any, field: str, errors: list[str]) -> date | None:
    if value is None:
        errors.append(f"{field} is required")
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        errors.append(f"{field} is required")
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        errors.append(f"{field} is not parseable")
        return None


def _parse_float(
    value: Any,
    field: str,
    errors: list[str],
) -> float | None:
    if value is None:
        errors.append(f"{field} is required")
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        errors.append(f"{field} is not numeric")
        return None
    return parsed


def _optional_float(
    value: Any,
    field: str,
    warnings: list[str],
    *,
    min_value: float | None = None,
    strict_min: bool = False,
) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        warnings.append(f"{field} is not numeric and was ignored")
        return None
    if min_value is not None:
        invalid = parsed <= min_value if strict_min else parsed < min_value
        if invalid:
            warnings.append(f"{field} is outside the supported range and was ignored")
            return None
    return parsed


def _instructions(errors: list[str]) -> list[str]:
    if not errors:
        return []
    return [
        "Correct invalid rows or provide a clean local gold options OI export before running "
        "wall analysis."
    ]
