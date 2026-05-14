from __future__ import annotations

from datetime import UTC, datetime
from math import isfinite
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import polars as pl

from src.models.xau_forward_journal import (
    XauForwardOhlcCandle,
    XauForwardPriceCoverageRequest,
    XauForwardPriceDataRequestBase,
    XauForwardPriceDataUpdateRequest,
    XauForwardPriceSource,
    XauForwardPriceSourceLabel,
)


class XauForwardPriceDataError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "INVALID_PRICE_DATA",
        details: list[dict[str, str]] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or []


class XauForwardPriceSourceError(XauForwardPriceDataError):
    def __init__(self, message: str, details: list[dict[str, str]] | None = None) -> None:
        super().__init__(message, code="INVALID_PRICE_SOURCE", details=details)


class XauForwardPriceDataNotFoundError(XauForwardPriceDataError):
    def __init__(self, ohlc_path: str) -> None:
        super().__init__(
            "OHLC price data file was not found",
            code="PRICE_DATA_NOT_FOUND",
            details=[{"field": "ohlc_path", "message": ohlc_path}],
        )


class XauForwardOhlcSchemaError(XauForwardPriceDataError):
    def __init__(self, message: str, details: list[dict[str, str]] | None = None) -> None:
        super().__init__(message, code="INVALID_OHLC_SCHEMA", details=details)


PROXY_LIMITATIONS = {
    XauForwardPriceSourceLabel.TRUE_XAUUSD_SPOT: [],
    XauForwardPriceSourceLabel.GC_FUTURES: [
        "GC futures are not true XAUUSD spot and may differ because of contract, "
        "basis, and session effects."
    ],
    XauForwardPriceSourceLabel.YAHOO_GC_F_PROXY: [
        "Yahoo GC=F is a futures proxy OHLCV source and is not true XAUUSD spot."
    ],
    XauForwardPriceSourceLabel.GLD_ETF_PROXY: [
        "GLD is an ETF proxy and is not true XAUUSD spot."
    ],
    XauForwardPriceSourceLabel.LOCAL_CSV: [
        "Local CSV source requires researcher review of whether the candles represent "
        "spot, futures, or proxy data."
    ],
    XauForwardPriceSourceLabel.LOCAL_PARQUET: [
        "Local Parquet source requires researcher review of whether the candles represent "
        "spot, futures, or proxy data."
    ],
    XauForwardPriceSourceLabel.UNKNOWN_PROXY: [
        "Unknown proxy source is not true XAUUSD spot until independently verified."
    ],
}


def load_price_candles(
    request: XauForwardPriceDataUpdateRequest | XauForwardPriceCoverageRequest,
    *,
    base_dir: Path | None = None,
) -> tuple[list[XauForwardOhlcCandle], XauForwardPriceSource]:
    """Load and validate local OHLC candles for a journal price update."""

    validate_price_source(request)
    path = resolve_ohlc_path(request.ohlc_path, base_dir=base_dir)
    if not path.exists():
        raise XauForwardPriceDataNotFoundError(request.ohlc_path)
    file_format = _detect_format(path)
    validate_source_file_format(request.source_label, file_format)
    frame = _read_frame(path, file_format)
    candles = normalize_ohlc_frame(frame, request)
    source = XauForwardPriceSource(
        source_label=request.source_label,
        source_symbol=source_symbol_for_label(request),
        source_path=_display_path(path, base_dir=base_dir),
        format=file_format,
        row_count=len(candles),
        first_timestamp=candles[0].timestamp if candles else None,
        last_timestamp=candles[-1].timestamp if candles else None,
        warnings=[],
        limitations=proxy_limitations_for_source(request.source_label),
    )
    return candles, source


def validate_price_source(request: XauForwardPriceDataRequestBase) -> None:
    symbol = (request.source_symbol or "").upper().replace(" ", "")
    label = request.source_label
    if label == XauForwardPriceSourceLabel.TRUE_XAUUSD_SPOT and symbol:
        if symbol not in {"XAUUSD", "XAUUSDSPOT", "XAU/USD"}:
            raise XauForwardPriceSourceError(
                "Price data source is invalid",
                [{"field": "source_symbol", "message": "true_xauusd_spot requires XAUUSD spot"}],
            )
    if label == XauForwardPriceSourceLabel.GC_FUTURES and symbol:
        if not symbol.startswith("GC"):
            raise XauForwardPriceSourceError(
                "Price data source is invalid",
                [{"field": "source_symbol", "message": "gc_futures requires a GC symbol"}],
            )
    if label == XauForwardPriceSourceLabel.YAHOO_GC_F_PROXY and symbol:
        if symbol != "GC=F":
            raise XauForwardPriceSourceError(
                "Price data source is invalid",
                [{"field": "source_symbol", "message": "yahoo_gc_f_proxy requires GC=F"}],
            )
    if label == XauForwardPriceSourceLabel.GLD_ETF_PROXY and symbol:
        if symbol != "GLD":
            raise XauForwardPriceSourceError(
                "Price data source is invalid",
                [{"field": "source_symbol", "message": "gld_etf_proxy requires GLD"}],
            )


def source_symbol_for_label(request: XauForwardPriceDataRequestBase) -> str | None:
    if request.source_symbol:
        return request.source_symbol
    if request.source_label == XauForwardPriceSourceLabel.TRUE_XAUUSD_SPOT:
        return "XAUUSD"
    if request.source_label == XauForwardPriceSourceLabel.YAHOO_GC_F_PROXY:
        return "GC=F"
    if request.source_label == XauForwardPriceSourceLabel.GLD_ETF_PROXY:
        return "GLD"
    return None


def validate_source_file_format(
    source_label: XauForwardPriceSourceLabel,
    file_format: str,
) -> None:
    if source_label == XauForwardPriceSourceLabel.LOCAL_CSV and file_format != "csv":
        raise XauForwardPriceSourceError(
            "Price data source is invalid",
            [{"field": "source_label", "message": "local_csv requires a CSV OHLC file"}],
        )
    if source_label == XauForwardPriceSourceLabel.LOCAL_PARQUET and file_format != "parquet":
        raise XauForwardPriceSourceError(
            "Price data source is invalid",
            [
                {
                    "field": "source_label",
                    "message": "local_parquet requires a Parquet OHLC file",
                }
            ],
        )


def proxy_limitations_for_source(label: XauForwardPriceSourceLabel) -> list[str]:
    return list(PROXY_LIMITATIONS[label])


def resolve_ohlc_path(ohlc_path: str, *, base_dir: Path | None = None) -> Path:
    cleaned = ohlc_path.replace("\\", "/").strip()
    if cleaned.startswith(("http://", "https://")):
        raise XauForwardPriceDataError(
            "OHLC path must be a local research file path",
            code="VALIDATION_ERROR",
            details=[{"field": "ohlc_path", "message": "Remote URLs are not accepted"}],
        )
    path = Path(cleaned)
    if path.is_absolute():
        return path.resolve()
    base = base_dir or Path(__file__).resolve().parents[3]
    return (base / path).resolve()


def normalize_ohlc_frame(
    frame: pl.DataFrame,
    request: XauForwardPriceDataRequestBase,
) -> list[XauForwardOhlcCandle]:
    required = {
        request.timestamp_column: "timestamp",
        request.open_column: "open",
        request.high_column: "high",
        request.low_column: "low",
        request.close_column: "close",
    }
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise XauForwardOhlcSchemaError(
            "OHLC candle data is invalid",
            [{"field": column, "message": "Required OHLC column is missing"} for column in missing],
        )

    selected_columns = list(required.keys())
    if "volume" in frame.columns:
        selected_columns.append("volume")
    selected = frame.select(selected_columns).rename(required)
    candles: list[XauForwardOhlcCandle] = []
    errors: list[dict[str, str]] = []
    for index, row in enumerate(selected.to_dicts()):
        try:
            candle = XauForwardOhlcCandle(
                timestamp=_parse_timestamp(row["timestamp"], request.timezone),
                open=_as_float(row["open"], "open"),
                high=_as_float(row["high"], "high"),
                low=_as_float(row["low"], "low"),
                close=_as_float(row["close"], "close"),
                volume=_as_optional_float(row.get("volume"), "volume"),
            )
            candles.append(candle)
        except (TypeError, ValueError) as exc:
            errors.append({"field": f"rows[{index}]", "message": str(exc)})
    if errors:
        raise XauForwardOhlcSchemaError("OHLC candle data is invalid", errors)
    if not candles:
        raise XauForwardOhlcSchemaError(
            "OHLC candle data is invalid",
            [{"field": "rows", "message": "OHLC candle data is empty"}],
        )
    candles = sorted(candles, key=lambda candle: candle.timestamp)
    timestamps = [candle.timestamp for candle in candles]
    if len(set(timestamps)) != len(timestamps):
        raise XauForwardOhlcSchemaError(
            "OHLC candle data is invalid: Duplicate candle timestamps are not allowed",
            [{"field": "timestamp", "message": "Duplicate candle timestamps are not allowed"}],
        )
    return candles


def _detect_format(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return "csv"
    if suffix == ".parquet":
        return "parquet"
    raise XauForwardOhlcSchemaError(
        "OHLC candle data is invalid",
        [{"field": "ohlc_path", "message": "Only CSV and Parquet OHLC files are supported"}],
    )


def _read_frame(path: Path, file_format: str) -> pl.DataFrame:
    try:
        if file_format == "csv":
            return pl.read_csv(path)
        return pl.read_parquet(path)
    except Exception as exc:  # pragma: no cover - exact parser errors vary by backend
        raise XauForwardOhlcSchemaError(
            "OHLC candle data is invalid",
            [{"field": "ohlc_path", "message": str(exc)}],
        ) from exc


def _parse_timestamp(value: Any, timezone: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("timestamp must be ISO 8601 compatible") from exc
    else:
        raise ValueError("timestamp must be a datetime or ISO 8601 string")

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_timezone_info(timezone))
    return parsed.astimezone(UTC)


def _timezone_info(timezone: str):
    if timezone.upper() == "UTC":
        return UTC
    try:
        return ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"unknown timezone: {timezone}") from exc


def _as_float(value: Any, field_name: str) -> float:
    if value is None:
        raise ValueError(f"{field_name} is required")
    try:
        converted = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be numeric") from exc
    if converted <= 0:
        raise ValueError(f"{field_name} must be positive")
    if not isfinite(converted):
        raise ValueError(f"{field_name} must be finite")
    return converted


def _as_optional_float(value: Any, field_name: str) -> float | None:
    if value is None:
        return None
    try:
        converted = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be numeric") from exc
    if converted < 0:
        raise ValueError(f"{field_name} must be non-negative")
    if not isfinite(converted):
        raise ValueError(f"{field_name} must be finite")
    return converted


def _display_path(path: Path, *, base_dir: Path | None = None) -> str:
    repo_root = base_dir or Path(__file__).resolve().parents[3]
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()
