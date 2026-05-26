"""File discovery, transcript loading, and schema normalization."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any, Iterable

import polars as pl

from research_xau_vol_oi.config import ResearchConfig


class DataLoadError(ValueError):
    """Raised when a source file cannot be loaded or standardized safely."""


@dataclass(frozen=True)
class TranscriptDocument:
    """A transcript-like text artifact with source metadata."""

    path: Path
    text: str
    line_count: int
    char_count: int


def discover_data_files(
    roots: Iterable[str | Path] | None = None,
    *,
    config: ResearchConfig | None = None,
) -> pl.DataFrame:
    """Return an inventory of local research data files.

    The inventory includes ignored local data/report folders because the
    research pipeline must be able to inspect generated or user-supplied
    artifacts without committing them.
    """

    cfg = config or ResearchConfig()
    rows: list[dict[str, Any]] = []
    for root_value in roots or cfg.data_roots:
        root = Path(root_value)
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or _is_excluded(path, cfg):
                continue
            extension = path.suffix.lower()
            if extension not in cfg.accepted_file_extensions:
                continue
            stat = path.stat()
            rows.append(
                {
                    "path": str(path),
                    "extension": extension,
                    "size_bytes": stat.st_size,
                    "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=UTC),
                    "category": categorize_data_file(path),
                }
            )
    if not rows:
        return pl.DataFrame(
            schema={
                "path": pl.String,
                "extension": pl.String,
                "size_bytes": pl.Int64,
                "modified_at": pl.Datetime(time_zone="UTC"),
                "category": pl.String,
            }
        )
    return pl.DataFrame(rows, infer_schema_length=None).sort("path")


def categorize_data_file(path: str | Path) -> str:
    """Classify an input by path hints for report inventory purposes."""

    text = str(path).replace("\\", "/").lower()
    suffix = Path(path).suffix.lower()
    if "youtube_transcripts" in text or suffix in {".txt", ".srt", ".md"}:
        return "transcript_or_notes"
    if "quikstrike" in text or "options_oi" in text or "xau_vol_oi" in text:
        return "xau_cme_options_or_wall"
    if "yahoo" in text or "ohlcv" in text or "gc=f" in text:
        return "price_ohlcv_proxy"
    if "xau_reaction" in text or "signal" in text:
        return "xau_signal_or_reaction"
    if "reports" in text:
        return "report_artifact"
    return "other_research_data"


def load_table(path: str | Path) -> pl.DataFrame:
    """Load CSV, Parquet, or Excel data with explicit format handling."""

    source = Path(path)
    if not source.exists():
        raise DataLoadError(f"Data file does not exist: {source}")
    suffix = source.suffix.lower()
    if suffix == ".csv":
        return pl.read_csv(source)
    if suffix == ".parquet":
        return pl.read_parquet(source)
    if suffix in {".xlsx", ".xls"}:
        try:
            return pl.read_excel(source)
        except Exception as exc:  # pragma: no cover - depends on optional Excel backend
            raise DataLoadError(
                "Excel loading requires an installed Polars Excel backend such as xlsx2csv."
            ) from exc
    raise DataLoadError(f"Unsupported tabular format: {suffix}")


def load_transcript_file(path: str | Path, *, encoding: str = "utf-8") -> TranscriptDocument:
    """Load one transcript or notes file as text."""

    source = Path(path)
    if not source.exists():
        raise DataLoadError(f"Transcript file does not exist: {source}")
    text = source.read_text(encoding=encoding, errors="replace")
    return TranscriptDocument(
        path=source,
        text=text,
        line_count=len(text.splitlines()),
        char_count=len(text),
    )


def load_transcripts(paths: Iterable[str | Path]) -> pl.DataFrame:
    """Load transcript-like text files into a compact metadata table."""

    rows = []
    for path in paths:
        doc = load_transcript_file(path)
        rows.append(
            {
                "path": str(doc.path),
                "line_count": doc.line_count,
                "char_count": doc.char_count,
                "text": doc.text,
            }
        )
    return pl.DataFrame(rows, infer_schema_length=None) if rows else pl.DataFrame()


def standardize_price_frame(
    frame: pl.DataFrame,
    *,
    source_path: str | Path | None = None,
    config: ResearchConfig | None = None,
) -> pl.DataFrame:
    """Normalize OHLCV price data to timestamp, symbol, open, high, low, close, volume."""

    cfg = config or ResearchConfig()
    aliases = cfg.aliases
    timestamp_col = _find_column(frame.columns, aliases.timestamp)
    open_col = _find_column(frame.columns, aliases.open)
    high_col = _find_column(frame.columns, aliases.high)
    low_col = _find_column(frame.columns, aliases.low)
    close_col = _find_column(frame.columns, aliases.close)
    symbol_col = _find_column(frame.columns, aliases.symbol, required=False)
    volume_col = _find_column(frame.columns, aliases.volume, required=False)
    source_label_col = _find_column(frame.columns, ("source_label",), required=False)

    rows: list[dict[str, Any]] = []
    for index, raw in enumerate(frame.to_dicts(), start=1):
        timestamp = _parse_datetime(raw.get(timestamp_col), field="timestamp", row=index)
        open_price = _required_float(raw.get(open_col), field="open", row=index)
        high = _required_float(raw.get(high_col), field="high", row=index)
        low = _required_float(raw.get(low_col), field="low", row=index)
        close = _required_float(raw.get(close_col), field="close", row=index)
        if high < low or not low <= open_price <= high or not low <= close <= high:
            raise DataLoadError(f"row {index}: invalid OHLC ordering")
        rows.append(
            {
                "timestamp": timestamp,
                "symbol": str(raw.get(symbol_col) or "UNKNOWN"),
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "volume": _optional_float(raw.get(volume_col), default=0.0),
                "source_label": str(raw.get(source_label_col) or "unknown"),
                "source_path": str(source_path or ""),
                "session_date": timestamp.date().isoformat(),
            }
        )

    if not rows:
        raise DataLoadError("Price frame is empty")
    return pl.DataFrame(rows, infer_schema_length=None).sort("timestamp")


def standardize_options_frame(
    frame: pl.DataFrame,
    *,
    source_path: str | Path | None = None,
    config: ResearchConfig | None = None,
) -> pl.DataFrame:
    """Normalize CME/QuikStrike-style option OI rows.

    Supported shapes include either one row per option type with
    ``open_interest`` or one row per strike with explicit ``call_oi`` and
    ``put_oi`` columns.
    """

    cfg = config or ResearchConfig()
    aliases = cfg.aliases
    columns = frame.columns
    timestamp_col = _find_column(columns, aliases.timestamp)
    strike_col = _find_column(columns, aliases.strike)
    expiry_col = _find_column(columns, aliases.expiry, required=False)
    dte_col = _find_column(columns, aliases.dte, required=False)
    option_type_col = _find_column(columns, aliases.option_type, required=False)
    oi_col = _find_column(columns, aliases.open_interest, required=False)
    call_oi_col = _find_column(columns, aliases.call_oi, required=False)
    put_oi_col = _find_column(columns, aliases.put_oi, required=False)
    oi_change_col = _find_column(columns, aliases.oi_change, required=False)
    volume_col = _find_column(columns, aliases.volume, required=False)
    iv_col = _find_column(columns, aliases.iv, required=False)
    futures_col = _find_column(columns, aliases.futures_price, required=False)
    spot_col = _find_column(columns, aliases.spot_price, required=False)
    symbol_col = _find_column(columns, aliases.symbol, required=False)

    if oi_col is None and call_oi_col is None and put_oi_col is None:
        raise DataLoadError("Options frame requires open_interest or call_oi/put_oi")

    rows: list[dict[str, Any]] = []
    for index, raw in enumerate(frame.to_dicts(), start=1):
        timestamp = _parse_datetime(raw.get(timestamp_col), field="timestamp", row=index)
        expiry = _parse_date(raw.get(expiry_col)) if expiry_col else None
        dte = _parse_dte(raw.get(dte_col), timestamp=timestamp, expiry=expiry)
        strike = _required_float(raw.get(strike_col), field="strike", row=index)
        option_type = _normalize_option_type(raw.get(option_type_col)) if option_type_col else "unknown"
        open_interest = _optional_float(raw.get(oi_col), default=0.0)
        call_oi = _optional_float(raw.get(call_oi_col), default=0.0)
        put_oi = _optional_float(raw.get(put_oi_col), default=0.0)
        if option_type == "call" and open_interest:
            call_oi += open_interest
        elif option_type == "put" and open_interest:
            put_oi += open_interest
        elif not call_oi and not put_oi:
            call_oi = open_interest / 2.0
            put_oi = open_interest / 2.0
        total_oi = call_oi + put_oi
        if strike <= 0 or total_oi < 0:
            raise DataLoadError(f"row {index}: strike and OI values must be valid")

        iv_percent = _optional_float(raw.get(iv_col), default=None)
        if iv_percent is not None and iv_percent <= 1.0:
            iv_percent *= 100.0
        rows.append(
            {
                "timestamp": timestamp,
                "symbol": str(raw.get(symbol_col) or "GC"),
                "expiry": expiry.isoformat() if expiry else str(raw.get(expiry_col) or ""),
                "dte": dte,
                "strike": strike,
                "option_type": option_type,
                "call_oi": call_oi,
                "put_oi": put_oi,
                "total_oi": total_oi,
                "oi_change": _optional_float(raw.get(oi_change_col), default=None),
                "volume": _optional_float(raw.get(volume_col), default=None),
                "iv_percent": iv_percent,
                "futures_price": _optional_float(raw.get(futures_col), default=None),
                "spot_price": _optional_float(raw.get(spot_col), default=None),
                "source_path": str(source_path or ""),
            }
        )

    if not rows:
        raise DataLoadError("Options frame is empty")
    return pl.DataFrame(rows, infer_schema_length=None).sort(["timestamp", "expiry", "strike"])


def _is_excluded(path: Path, config: ResearchConfig) -> bool:
    return any(part in config.exclude_dir_names for part in path.parts)


def _find_column(
    columns: Iterable[str],
    aliases: Iterable[str],
    *,
    required: bool = True,
) -> str | None:
    lookup = {column.lower(): column for column in columns}
    for alias in aliases:
        match = lookup.get(alias.lower())
        if match is not None:
            return match
    if required:
        raise DataLoadError(f"Missing required column matching one of: {', '.join(aliases)}")
    return None


def _parse_datetime(value: Any, *, field: str, row: int) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, time.min)
    else:
        text = str(value or "").strip()
        if not text:
            raise DataLoadError(f"row {row}: {field} is required")
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise DataLoadError(f"row {row}: {field} is not parseable") from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _parse_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _parse_dte(value: Any, *, timestamp: datetime, expiry: date | None) -> float | None:
    parsed = _optional_float(value, default=None)
    if parsed is not None:
        return parsed
    if expiry is None:
        return None
    return float((expiry - timestamp.date()).days)


def _required_float(value: Any, *, field: str, row: int) -> float:
    parsed = _optional_float(value, default=None)
    if parsed is None:
        raise DataLoadError(f"row {row}: {field} is required and must be numeric")
    return parsed


def _optional_float(value: Any, *, default: float | None) -> float | None:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_option_type(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"c", "call", "calls"}:
        return "call"
    if normalized in {"p", "put", "puts"}:
        return "put"
    return "unknown"
