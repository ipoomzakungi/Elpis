from __future__ import annotations

import csv
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.models.xau_price_plan_tracker import (
    XauDukasCaptureResult,
    XauDukasCaptureStatus,
    XauDukasCliCaptureRequest,
    XauDukasPriceBar,
)

_TIMESTAMP_COLUMNS = ("timestamp", "time", "datetime")
_OPEN_COLUMNS = ("open", "bid_open")
_HIGH_COLUMNS = ("high", "bid_high")
_LOW_COLUMNS = ("low", "bid_low")
_CLOSE_COLUMNS = ("close", "bid_close")
_VOLUME_COLUMNS = ("volume", "tick_volume")


def run_dukas_cli_capture(request: XauDukasCliCaptureRequest) -> XauDukasCaptureResult:
    capture_id = f"xau_dukas_{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}"
    output_dir = request.output_dir or Path("data/imports")
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"{capture_id}_{request.symbol}_{request.timeframe}.csv"
    if request.dukas_cli_path is None or not request.command_template:
        return XauDukasCaptureResult(
            capture_id=capture_id,
            created_at=datetime.now(UTC),
            status=XauDukasCaptureStatus.UNAVAILABLE,
            bars_count=0,
            bars_path=output,
            limitations=["Dukascopy CLI path and command_template are required."],
        )

    command = request.command_template.format(
        cli=str(request.dukas_cli_path),
        symbol=request.symbol,
        timeframe=request.timeframe,
        start=request.start_time.isoformat(),
        end=request.end_time.isoformat(),
        output=str(output),
    )
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            shell=True,
            timeout=request.timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return XauDukasCaptureResult(
            capture_id=capture_id,
            created_at=datetime.now(UTC),
            status=XauDukasCaptureStatus.FAILED,
            bars_count=0,
            bars_path=output,
            limitations=[f"Dukascopy CLI command failed: {_sanitize(str(exc))}"],
        )

    if completed.returncode != 0:
        message = _sanitize(completed.stderr or completed.stdout or "command returned non-zero")
        return XauDukasCaptureResult(
            capture_id=capture_id,
            created_at=datetime.now(UTC),
            status=XauDukasCaptureStatus.FAILED,
            bars_count=0,
            bars_path=output,
            limitations=[f"Dukascopy CLI returned {completed.returncode}: {message}"],
        )
    if not output.exists():
        return XauDukasCaptureResult(
            capture_id=capture_id,
            created_at=datetime.now(UTC),
            status=XauDukasCaptureStatus.UNAVAILABLE,
            bars_count=0,
            bars_path=output,
            limitations=["Dukascopy CLI completed but did not create the output file."],
        )
    bars = load_price_bars(output, symbol=request.symbol, timeframe=request.timeframe)
    return XauDukasCaptureResult(
        capture_id=capture_id,
        created_at=datetime.now(UTC),
        status=XauDukasCaptureStatus.COMPLETED if bars else XauDukasCaptureStatus.UNAVAILABLE,
        bars_count=len(bars),
        bars_path=output,
        latest_price=bars[-1].close if bars else None,
        limitations=[] if bars else ["Dukascopy output contained no valid bars."],
    )


def load_price_bars(
    path: Path,
    *,
    symbol: str = "XAUUSD",
    timeframe: str = "1m",
) -> list[XauDukasPriceBar]:
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload.get("bars", payload) if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            raise ValueError("JSON price bars must be a list or object with bars list")
        return [_bar_from_mapping(row, symbol=symbol, timeframe=timeframe) for row in rows]
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [
            _bar_from_mapping(row, symbol=symbol, timeframe=timeframe)
            for row in csv.DictReader(handle)
        ]


def _bar_from_mapping(
    row: dict[str, Any],
    *,
    symbol: str,
    timeframe: str,
) -> XauDukasPriceBar:
    timestamp_value = _first(row, _TIMESTAMP_COLUMNS)
    if timestamp_value is None:
        raise ValueError("price bars require timestamp/time/datetime")
    return XauDukasPriceBar(
        timestamp=_parse_datetime(timestamp_value),
        open=_required_float(row, _OPEN_COLUMNS, "open"),
        high=_required_float(row, _HIGH_COLUMNS, "high"),
        low=_required_float(row, _LOW_COLUMNS, "low"),
        close=_required_float(row, _CLOSE_COLUMNS, "close"),
        volume=_optional_float(_first(row, _VOLUME_COLUMNS)),
        symbol=symbol,
        timeframe=timeframe,
    )


def _first(row: dict[str, Any], names: tuple[str, ...]) -> Any:
    normalized = {str(key).strip().lower(): value for key, value in row.items()}
    for name in names:
        value = normalized.get(name)
        if value not in (None, ""):
            return value
    return None


def _required_float(row: dict[str, Any], names: tuple[str, ...], label: str) -> float:
    value = _first(row, names)
    if value is None:
        raise ValueError(f"price bars require {label}")
    return float(value)


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


def _sanitize(value: str) -> str:
    redacted = value
    for marker in ("password=", "token=", "cookie=", "secret="):
        lower = redacted.lower()
        index = lower.find(marker)
        if index >= 0:
            end = redacted.find(" ", index)
            end = len(redacted) if end < 0 else end
            redacted = redacted[: index + len(marker)] + "[REDACTED]" + redacted[end:]
    return " ".join(redacted.split())[:500]


__all__ = ["load_price_bars", "run_dukas_cli_capture"]
