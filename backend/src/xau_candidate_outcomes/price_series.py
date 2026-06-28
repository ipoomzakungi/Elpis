from __future__ import annotations

import json
from datetime import UTC, datetime
from math import isfinite
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import polars as pl

from src.models.xau_candidate_outcome import (
    XauCandidateOutcomeRunRequest,
    XauCandidatePriceBar,
    XauCandidatePriceSeriesSource,
    XauCandidatePriceSourceKind,
)


class XauCandidatePriceSeriesError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "INVALID_PRICE_SERIES",
        details: list[dict[str, str]] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or []


class XauCandidatePriceSeriesNotFoundError(XauCandidatePriceSeriesError):
    def __init__(self, path: Path) -> None:
        super().__init__(
            "Price bars file was not found",
            code="PRICE_SERIES_NOT_FOUND",
            details=[{"field": "price_bars_path", "message": str(path)}],
        )


class StaticFixturePriceSeriesProvider:
    """In-memory price-bar provider for tests and fixture research runs."""

    def __init__(
        self,
        bars: list[XauCandidatePriceBar],
        *,
        source_path: str = "static_fixture",
    ) -> None:
        self.bars = sorted(bars, key=lambda bar: bar.timestamp)
        self.source_path = source_path

    def load(self) -> tuple[list[XauCandidatePriceBar], XauCandidatePriceSeriesSource]:
        return self.bars, _source(
            kind=XauCandidatePriceSourceKind.STATIC_FIXTURE,
            path=self.source_path,
            bars=self.bars,
            limitations=["Static fixture price bars are for local tests only."],
        )


def load_price_bars_from_path(
    path: Path,
    *,
    timestamp_column: str = "timestamp",
    open_column: str = "open",
    high_column: str = "high",
    low_column: str = "low",
    close_column: str = "close",
    volume_column: str | None = "volume",
    timezone: str = "UTC",
) -> tuple[list[XauCandidatePriceBar], XauCandidatePriceSeriesSource]:
    resolved = path.resolve()
    if not resolved.exists():
        raise XauCandidatePriceSeriesNotFoundError(resolved)
    kind = _kind_for_path(resolved)
    frame = _read_frame(resolved, kind)
    bars = normalize_price_bar_frame(
        frame,
        timestamp_column=timestamp_column,
        open_column=open_column,
        high_column=high_column,
        low_column=low_column,
        close_column=close_column,
        volume_column=volume_column,
        timezone=timezone,
        source=resolved.name,
    )
    return bars, _source(
        kind=kind,
        path=_display_path(resolved),
        bars=bars,
        limitations=[
            "Local price bars require researcher review of whether the source is "
            "true XAUUSD spot, GC futures, or another proxy."
        ],
    )


def load_price_bars_for_request(
    request: XauCandidateOutcomeRunRequest,
) -> tuple[list[XauCandidatePriceBar], XauCandidatePriceSeriesSource]:
    return load_price_bars_from_path(
        request.price_bars_path,
        timestamp_column=request.timestamp_column,
        open_column=request.open_column,
        high_column=request.high_column,
        low_column=request.low_column,
        close_column=request.close_column,
        volume_column=request.volume_column,
        timezone=request.timezone,
    )


def normalize_price_bar_frame(
    frame: pl.DataFrame,
    *,
    timestamp_column: str,
    open_column: str,
    high_column: str,
    low_column: str,
    close_column: str,
    volume_column: str | None,
    timezone: str,
    source: str,
) -> list[XauCandidatePriceBar]:
    required = {
        timestamp_column: "timestamp",
        open_column: "open",
        high_column: "high",
        low_column: "low",
        close_column: "close",
    }
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise XauCandidatePriceSeriesError(
            "Price bars file is missing required OHLC columns",
            details=[
                {"field": column, "message": "required column is missing"}
                for column in missing
            ],
        )
    selected_columns = list(required.keys())
    rename_map = dict(required)
    if volume_column and volume_column in frame.columns:
        selected_columns.append(volume_column)
        rename_map[volume_column] = "volume"
    selected = frame.select(selected_columns).rename(rename_map)
    bars: list[XauCandidatePriceBar] = []
    errors: list[dict[str, str]] = []
    for index, row in enumerate(selected.to_dicts()):
        try:
            bars.append(
                XauCandidatePriceBar(
                    timestamp=_parse_timestamp(row["timestamp"], timezone),
                    open=_as_float(row["open"], "open"),
                    high=_as_float(row["high"], "high"),
                    low=_as_float(row["low"], "low"),
                    close=_as_float(row["close"], "close"),
                    volume=_as_optional_float(row.get("volume"), "volume"),
                    source=source,
                )
            )
        except (TypeError, ValueError) as exc:
            errors.append({"field": f"rows[{index}]", "message": str(exc)})
    if errors:
        raise XauCandidatePriceSeriesError("Price bars file has invalid rows", details=errors)
    if not bars:
        raise XauCandidatePriceSeriesError(
            "Price bars file is empty",
            details=[{"field": "rows", "message": "at least one price bar is required"}],
        )
    bars = sorted(bars, key=lambda bar: bar.timestamp)
    timestamps = [bar.timestamp for bar in bars]
    if len(set(timestamps)) != len(timestamps):
        raise XauCandidatePriceSeriesError(
            "Price bars file contains duplicate timestamps",
            details=[{"field": "timestamp", "message": "duplicate timestamps are not allowed"}],
        )
    return bars


def _kind_for_path(path: Path) -> XauCandidatePriceSourceKind:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return XauCandidatePriceSourceKind.LOCAL_CSV
    if suffix == ".json":
        return XauCandidatePriceSourceKind.LOCAL_JSON
    if suffix == ".parquet":
        return XauCandidatePriceSourceKind.LOCAL_PARQUET
    raise XauCandidatePriceSeriesError(
        "Only CSV, JSON, and Parquet price bar files are supported",
        details=[{"field": "price_bars_path", "message": path.suffix}],
    )


def _read_frame(path: Path, kind: XauCandidatePriceSourceKind) -> pl.DataFrame:
    try:
        if kind == XauCandidatePriceSourceKind.LOCAL_CSV:
            return pl.read_csv(path)
        if kind == XauCandidatePriceSourceKind.LOCAL_PARQUET:
            return pl.read_parquet(path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload.get("bars", payload) if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            raise ValueError("JSON price bars must be a list or {'bars': [...]}")
        return pl.DataFrame(rows)
    except Exception as exc:  # pragma: no cover - parser error details vary
        raise XauCandidatePriceSeriesError(
            "Price bars file could not be read",
            details=[{"field": "price_bars_path", "message": str(exc)}],
        ) from exc


def _source(
    *,
    kind: XauCandidatePriceSourceKind,
    path: str,
    bars: list[XauCandidatePriceBar],
    limitations: list[str],
) -> XauCandidatePriceSeriesSource:
    return XauCandidatePriceSeriesSource(
        source_kind=kind,
        source_path=path,
        row_count=len(bars),
        first_timestamp=bars[0].timestamp if bars else None,
        last_timestamp=bars[-1].timestamp if bars else None,
        limitations=limitations,
    )


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
    if converted <= 0 or not isfinite(converted):
        raise ValueError(f"{field_name} must be a positive finite number")
    return converted


def _as_optional_float(value: Any, field_name: str) -> float | None:
    if value is None:
        return None
    try:
        converted = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be numeric") from exc
    if converted < 0 or not isfinite(converted):
        raise ValueError(f"{field_name} must be a non-negative finite number")
    return converted


def _display_path(path: Path) -> str:
    repo_root = Path(__file__).resolve().parents[3]
    try:
        return path.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        return path.resolve().as_posix()


__all__ = [
    "StaticFixturePriceSeriesProvider",
    "XauCandidatePriceSeriesError",
    "XauCandidatePriceSeriesNotFoundError",
    "load_price_bars_for_request",
    "load_price_bars_from_path",
    "normalize_price_bar_frame",
]
