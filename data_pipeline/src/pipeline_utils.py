from __future__ import annotations

import json
import math
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import polars as pl

DATA_PIPELINE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BID_CSV = DATA_PIPELINE_ROOT / "data/raw/dukascopy/xauusd_m1_bid_2024_to_now.csv"
DEFAULT_ASK_CSV = DATA_PIPELINE_ROOT / "data/raw/dukascopy/xauusd_m1_ask_2024_to_now.csv"
DEFAULT_PROCESSED_PARQUET = DATA_PIPELINE_ROOT / "data/processed/xauusd_m1_2024_to_now.parquet"
DEFAULT_REPORTS_DIR = DATA_PIPELINE_ROOT / "data/reports"
UTC = timezone.utc

OHLC_ALIASES = {
    "datetime": [
        "timestamp",
        "time",
        "datetime",
        "date",
        "date_time",
        "date time",
        "gmt time",
        "utc",
        "time_utc",
    ],
    "open": ["open", "o"],
    "high": ["high", "h"],
    "low": ["low", "l"],
    "close": ["close", "c", "last"],
    "volume": ["volume", "vol", "tick_volume", "tickvolume"],
}


def resolve_path(path: str | Path | None, default: Path | None = None) -> Path:
    if path is None:
        if default is None:
            raise ValueError("path and default cannot both be None")
        return default
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return DATA_PIPELINE_ROOT / candidate


def ensure_pipeline_dirs() -> None:
    for path in [
        DATA_PIPELINE_ROOT / "data/raw/dukascopy",
        DATA_PIPELINE_ROOT / "data/processed",
        DATA_PIPELINE_ROOT / "data/reports",
    ]:
        path.mkdir(parents=True, exist_ok=True)


def normalize_column_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def _alias_candidates(canonical: str, side: str | None = None) -> list[str]:
    aliases = list(OHLC_ALIASES[canonical])
    if side and canonical != "datetime":
        aliases.extend(
            [
                f"{side}_{canonical}",
                f"{side}{canonical}",
                f"{canonical}_{side}",
                f"{canonical}{side}",
            ]
        )
        for alias in OHLC_ALIASES[canonical]:
            aliases.extend([f"{side}_{alias}", f"{side}{alias}", f"{alias}_{side}"])
    return [normalize_column_name(alias) for alias in aliases]


def resolve_ohlc_columns(columns: list[str], side: str | None = None) -> dict[str, str]:
    available = {normalize_column_name(column): column for column in columns}
    resolved: dict[str, str] = {}
    for canonical in ["datetime", "open", "high", "low", "close"]:
        for alias in _alias_candidates(canonical, side):
            if alias in available:
                resolved[canonical] = available[alias]
                break
        if canonical not in resolved:
            raise ValueError(
                f"Could not resolve required '{canonical}' column from CSV columns: {columns}"
            )

    for alias in _alias_candidates("volume", side):
        if alias in available:
            resolved["volume"] = available[alias]
            break
    return resolved


def parse_timestamp_value(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime(value.year, value.month, value.day)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, float) and not math.isfinite(value):
            return None
        absolute = abs(float(value))
        if absolute > 1e14:
            seconds = float(value) / 1_000_000_000
        elif absolute > 1e11:
            seconds = float(value) / 1_000
        else:
            seconds = float(value)
        return datetime.fromtimestamp(seconds, UTC)
    else:
        text = str(value).strip()
        if not text:
            return None
        if re.fullmatch(r"-?\d+(\.\d+)?", text):
            return parse_timestamp_value(float(text))

        normalized = text.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            parsed = None
            for fmt in (
                "%Y-%m-%d %H:%M:%S.%f",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M",
                "%Y.%m.%d %H:%M:%S",
                "%d.%m.%Y %H:%M:%S",
            ):
                try:
                    parsed = datetime.strptime(text, fmt)
                    break
                except ValueError:
                    continue
            if parsed is None:
                raise ValueError(f"Unsupported timestamp value: {value!r}")

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def to_iso(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return value


def to_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, datetime):
        return to_iso(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(to_jsonable(payload), indent=2, sort_keys=True), encoding="utf-8")


def read_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("Install PyYAML first: python -m pip install -r requirements.txt") from exc
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"YAML config must be a mapping: {path}")
    return payload


def write_yaml(path: Path, payload: Any) -> None:
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("Install PyYAML first: python -m pip install -r requirements.txt") from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(to_jsonable(payload), handle, sort_keys=False)


def read_dukascopy_csv(path: Path, side: str) -> tuple[pl.DataFrame, dict[str, Any]]:
    if side not in {"bid", "ask"}:
        raise ValueError("side must be 'bid' or 'ask'")
    original_path = path
    appended_csv_path = Path(f"{path}.csv")
    if not path.exists() and path.suffix.lower() == ".csv" and appended_csv_path.exists():
        path = appended_csv_path
    if not path.exists():
        raise FileNotFoundError(original_path)

    try:
        raw = pl.read_csv(path, try_parse_dates=False, infer_schema_length=5000)
        columns = resolve_ohlc_columns(list(raw.columns), side)
    except ValueError:
        raw = pl.read_csv(path, has_header=False, try_parse_dates=False, infer_schema_length=5000)
        if len(raw.columns) < 5:
            raise ValueError(f"{side} CSV must contain at least timestamp, open, high, low, close")
        fallback_columns = ["timestamp", "open", "high", "low", "close", "volume"]
        raw = raw.rename(
            {
                original: replacement
                for original, replacement in zip(raw.columns, fallback_columns, strict=False)
            }
        )
        columns = resolve_ohlc_columns(list(raw.columns), side)

    selected = [
        pl.col(columns["datetime"])
        .map_elements(parse_timestamp_value, return_dtype=pl.Datetime("us", "UTC"))
        .alias("datetime")
    ]
    for canonical in ["open", "high", "low", "close"]:
        selected.append(
            pl.col(columns[canonical]).cast(pl.Float64, strict=False).alias(f"{side}_{canonical}")
        )
    if "volume" in columns:
        selected.append(
            pl.col(columns["volume"]).cast(pl.Float64, strict=False).alias(f"{side}_volume")
        )

    normalized = raw.select(selected)
    required = ["datetime", f"{side}_open", f"{side}_high", f"{side}_low", f"{side}_close"]
    null_counts = normalized.select([pl.col(column).null_count().alias(column) for column in required])
    null_payload = null_counts.to_dicts()[0]
    bad_nulls = {column: count for column, count in null_payload.items() if count}
    if bad_nulls:
        raise ValueError(f"{side} CSV has null required values after parsing: {bad_nulls}")

    bad_ohlc = normalized.filter(
        (pl.col(f"{side}_high") < pl.col(f"{side}_low"))
        | (pl.col(f"{side}_open") > pl.col(f"{side}_high"))
        | (pl.col(f"{side}_open") < pl.col(f"{side}_low"))
        | (pl.col(f"{side}_close") > pl.col(f"{side}_high"))
        | (pl.col(f"{side}_close") < pl.col(f"{side}_low"))
    )
    if bad_ohlc.height:
        raise ValueError(f"{side} CSV has {bad_ohlc.height} internally inconsistent OHLC rows")

    before = normalized.height
    duplicate_count = before - normalized.select("datetime").n_unique()
    normalized = normalized.sort("datetime").unique(subset=["datetime"], keep="first").sort("datetime")
    return normalized, {
        "path": path.as_posix(),
        "requested_path": original_path.as_posix(),
        "side": side,
        "rows_before": before,
        "rows_after": normalized.height,
        "duplicate_timestamps_removed": duplicate_count,
        "resolved_columns": columns,
    }


def detect_missing_minute_ranges(datetimes: list[datetime]) -> dict[str, Any]:
    if not datetimes:
        return {"missing_candle_count": 0, "ranges": [], "sample_missing_minutes": []}

    sorted_datetimes = sorted(
        value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
        for value in datetimes
    )
    ranges: list[dict[str, Any]] = []
    samples: list[str] = []
    total_missing = 0
    for previous, current in zip(sorted_datetimes, sorted_datetimes[1:]):
        delta_minutes = int((current - previous).total_seconds() // 60)
        if delta_minutes <= 1:
            continue
        missing_count = delta_minutes - 1
        start = previous + timedelta(minutes=1)
        end = current - timedelta(minutes=1)
        ranges.append(
            {
                "start": start,
                "end": end,
                "missing_minutes": missing_count,
                "previous_available": previous,
                "next_available": current,
            }
        )
        total_missing += missing_count
        while len(samples) < 100 and start <= end:
            samples.append(to_iso(start))
            start += timedelta(minutes=1)

    return {
        "missing_candle_count": total_missing,
        "range_count": len(ranges),
        "ranges": ranges,
        "sample_missing_minutes": samples,
    }


def timeframe_to_polars_every(timeframe: str) -> str:
    normalized = timeframe.lower().strip()
    mapping = {
        "m1": "1m",
        "1m": "1m",
        "m5": "5m",
        "5m": "5m",
        "m15": "15m",
        "15m": "15m",
        "m30": "30m",
        "30m": "30m",
        "h1": "1h",
        "1h": "1h",
        "h4": "4h",
        "4h": "4h",
        "d1": "1d",
        "1d": "1d",
    }
    if normalized not in mapping:
        raise ValueError(f"Unsupported resample timeframe: {timeframe}")
    return mapping[normalized]
