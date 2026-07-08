from __future__ import annotations

import csv
import subprocess
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from src.models.xau_systematic_research import (
    XauDukascopyNodeFetchResult,
    XauSystematicSourceStatus,
)
from src.xau_market_context.price_loader import load_price_bars

DUKASCOPY_RESEARCH_WARNING = (
    "Dukascopy price is research-side traded reference, not broker execution feed."
)


class DukascopyNodeProvider:
    def __init__(self, *, import_root: Path | None = None, timeout_seconds: int = 120) -> None:
        self.import_root = import_root or _default_import_root()
        self.timeout_seconds = timeout_seconds

    def build_command(
        self,
        *,
        command_template: str,
        symbol: str,
        from_time: datetime,
        to_time: datetime,
        timeframe: str,
        output_path: Path,
    ) -> str:
        return command_template.format(
            symbol=symbol,
            from_iso=from_time.isoformat(),
            to_iso=to_time.isoformat(),
            timeframe=timeframe,
            output_path=str(output_path),
        )

    def fetch(
        self,
        *,
        command_template: str | None,
        session_date: date,
        symbol: str = "xauusd",
        timeframe: str = "m1",
        from_time: datetime | None = None,
        to_time: datetime | None = None,
    ) -> XauDukascopyNodeFetchResult:
        output_dir = self.import_root / "dukascopy" / session_date.isoformat()
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"dukascopy_{symbol}_{timeframe}_{_stamp()}.csv"
        if not command_template or from_time is None or to_time is None:
            return XauDukascopyNodeFetchResult(
                provider_status=XauSystematicSourceStatus.UNAVAILABLE,
                bars_path=output_path,
                warnings=["Dukascopy-node command template and from/to times are required."],
                limitations=[DUKASCOPY_RESEARCH_WARNING],
            )

        command = self.build_command(
            command_template=command_template,
            symbol=symbol,
            from_time=from_time,
            to_time=to_time,
            timeframe=timeframe,
            output_path=output_path,
        )
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                shell=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return _unavailable_result(
                output_path=output_path,
                command=command,
                message=f"Dukascopy-node command failed: {_sanitize(str(exc))}",
            )

        if completed.returncode != 0:
            return _unavailable_result(
                output_path=output_path,
                command=command,
                message=(
                    f"Dukascopy-node returned {completed.returncode}: "
                    f"{_sanitize(completed.stderr or completed.stdout or 'command failed')}"
                ),
            )
        if not output_path.exists():
            return _unavailable_result(
                output_path=output_path,
                command=command,
                message="Dukascopy-node completed but did not create the output file.",
            )

        warnings = [DUKASCOPY_RESEARCH_WARNING]
        try:
            normalized_path, converted_bid_ask = normalize_dukascopy_output(output_path)
            if converted_bid_ask:
                warnings.append("Bid/ask OHLC columns were converted to mid OHLC.")
            bars = load_price_bars(normalized_path, default_symbol=symbol.upper())
        except (OSError, ValueError) as exc:
            return _unavailable_result(
                output_path=output_path,
                command=command,
                message=f"Dukascopy-node output could not be normalized: {_sanitize(str(exc))}",
            )
        if not bars:
            return _unavailable_result(
                output_path=output_path,
                command=command,
                message="Dukascopy-node output contained no bars.",
            )
        latest = bars[-1]
        return XauDukascopyNodeFetchResult(
            provider_status=XauSystematicSourceStatus.AVAILABLE,
            bars_path=normalized_path,
            bars_count=len(bars),
            latest_price=latest.close,
            latest_timestamp=latest.timestamp,
            command=command,
            warnings=warnings,
            limitations=[DUKASCOPY_RESEARCH_WARNING],
        )


def normalize_dukascopy_output(path: Path) -> tuple[Path, bool]:
    rows = _read_rows(path)
    if not rows:
        return path, False
    fieldnames = {key.strip().lower() for key in rows[0]}
    has_standard = {"timestamp", "open", "high", "low", "close"}.issubset(fieldnames)
    has_bid_ask = {"bid_open", "ask_open", "bid_high", "ask_high"}.issubset(fieldnames)
    if has_standard and not has_bid_ask:
        return path, False

    normalized = path.with_name(f"{path.stem}_normalized.csv")
    with normalized.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["timestamp", "open", "high", "low", "close", "volume"],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(_normalized_row(row, use_bid_ask=has_bid_ask))
    return normalized, has_bid_ask


def _normalized_row(row: dict[str, Any], *, use_bid_ask: bool) -> dict[str, Any]:
    if not use_bid_ask:
        return {
            "timestamp": _first(row, "timestamp", "time", "datetime", "date"),
            "open": _first(row, "open"),
            "high": _first(row, "high"),
            "low": _first(row, "low"),
            "close": _first(row, "close"),
            "volume": _first(row, "volume", "tick_volume"),
        }
    return {
        "timestamp": _first(row, "timestamp", "time", "datetime", "date"),
        "open": _mid(row, "bid_open", "ask_open"),
        "high": _mid(row, "bid_high", "ask_high"),
        "low": _mid(row, "bid_low", "ask_low"),
        "close": _mid(row, "bid_close", "ask_close"),
        "volume": _first(row, "volume", "tick_volume"),
    }


def _read_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _first(row: dict[str, Any], *names: str) -> Any:
    normalized = {str(key).strip().lower(): value for key, value in row.items()}
    for name in names:
        value = normalized.get(name)
        if value not in (None, ""):
            return value
    return None


def _mid(row: dict[str, Any], bid_key: str, ask_key: str) -> float | None:
    bid = _optional_float(_first(row, bid_key))
    ask = _optional_float(_first(row, ask_key))
    if bid is None or ask is None:
        return None
    return (bid + ask) / 2


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _unavailable_result(
    *,
    output_path: Path,
    command: str,
    message: str,
) -> XauDukascopyNodeFetchResult:
    return XauDukascopyNodeFetchResult(
        provider_status=XauSystematicSourceStatus.UNAVAILABLE,
        bars_path=output_path,
        command=command,
        stderr=message,
        warnings=[message],
        limitations=[DUKASCOPY_RESEARCH_WARNING],
    )


def _sanitize(value: str) -> str:
    redacted = value
    for marker in ("password=", "token=", "cookie=", "secret=", "authorization="):
        lower = redacted.lower()
        index = lower.find(marker)
        if index >= 0:
            end = redacted.find(" ", index)
            end = len(redacted) if end < 0 else end
            redacted = redacted[: index + len(marker)] + "[REDACTED]" + redacted[end:]
    return " ".join(redacted.split())[:500]


def _stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S")


def _default_import_root() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "imports"
