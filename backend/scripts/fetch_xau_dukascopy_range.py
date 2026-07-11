from __future__ import annotations

import argparse
import csv
import json
import subprocess
import time
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import httpx

DEFAULT_TEMPLATE = (
    "npx dukascopy-node -i {symbol} -from {date_from} -to {date_to} "
    "-t {timeframe} -f csv -v -dir {download_dir} -fn {file_name}"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch research-only XAUUSD Dukascopy bars into reusable monthly files.",
    )
    parser.add_argument("--symbol", default="xauusd")
    parser.add_argument("--timeframe", default="m1")
    parser.add_argument("--date-from", required=True)
    parser.add_argument("--date-to", required=True)
    parser.add_argument("--output-root", default="data/imports/xau/dukascopy")
    parser.add_argument("--chunk-days", type=int, default=30)
    parser.add_argument("--dukascopy-node-command-template", default=DEFAULT_TEMPLATE)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--append", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument(
        "--transport",
        choices=("historical-bi5", "realtime-json"),
        default="historical-bi5",
    )
    parser.add_argument("--max-retries", type=int, default=3)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)

    start = date.fromisoformat(args.date_from)
    end = date.fromisoformat(args.date_to)
    output_dir = Path(args.output_root) / args.symbol.lower() / args.timeframe.lower()
    output_dir.mkdir(parents=True, exist_ok=True)
    all_rows: list[dict[str, str]] = []
    warnings: list[str] = [
        "Dukascopy XAUUSD bars are research-side traded references, not broker execution feed."
    ]

    with TemporaryDirectory(prefix="elpis_dukas_") as temp_dir:
        for chunk_start, chunk_end in _date_chunks(start, end, args.chunk_days):
            if args.transport == "realtime-json":
                chunk_rows, chunk_warnings = fetch_realtime_json_chunk(
                    symbol=args.symbol,
                    timeframe=args.timeframe,
                    date_from=chunk_start,
                    date_to=chunk_end,
                    timeout_seconds=args.timeout_seconds,
                    max_retries=args.max_retries,
                )
            else:
                chunk_rows, chunk_warnings = fetch_chunk(
                    command_template=args.dukascopy_node_command_template,
                    symbol=args.symbol,
                    timeframe=args.timeframe,
                    date_from=chunk_start,
                    date_to=chunk_end,
                    download_dir=Path(temp_dir),
                    timeout_seconds=args.timeout_seconds,
                )
            all_rows.extend(chunk_rows)
            warnings.extend(chunk_warnings)

    written = write_monthly_files(
        rows=all_rows,
        output_dir=output_dir,
        append=args.append,
        overwrite=args.overwrite,
    )
    manifest_path = write_coverage_manifest(
        output_dir=output_dir,
        date_from=start,
        date_to=end,
        transport=args.transport,
    )
    summary = {
        "symbol": args.symbol,
        "timeframe": args.timeframe,
        "date_from": args.date_from,
        "date_to": args.date_to,
        "rows": len(all_rows),
        "files": [path.as_posix() for path in written],
        "coverage_manifest": manifest_path.as_posix(),
        "transport": args.transport,
        "warnings": warnings,
        "research_only": True,
        "signal_allowed": False,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def fetch_chunk(
    *,
    command_template: str,
    symbol: str,
    timeframe: str,
    date_from: date,
    date_to: date,
    download_dir: Path,
    timeout_seconds: int,
) -> tuple[list[dict[str, str]], list[str]]:
    file_name = f"{symbol}_{timeframe}_{date_from.isoformat()}_{date_to.isoformat()}"
    command = command_template.format(
        symbol=symbol,
        timeframe=timeframe,
        date_from=date_from.isoformat(),
        date_to=date_to.isoformat(),
        download_dir=str(download_dir),
        file_name=file_name,
    )
    try:
        completed = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return [], [f"Dukascopy command timed out for {date_from} to {date_to}."]
    if completed.returncode != 0:
        message = _sanitize(completed.stderr or completed.stdout)
        return [], [f"Dukascopy command failed for {date_from} to {date_to}: {message}"]
    csv_path = download_dir / f"{file_name}.csv"
    if not csv_path.exists():
        return [], [f"Dukascopy command did not create {csv_path}."]
    return normalize_dukascopy_csv(csv_path), []


def fetch_realtime_json_chunk(
    *,
    symbol: str,
    timeframe: str,
    date_from: date,
    date_to: date,
    timeout_seconds: int,
    max_retries: int,
) -> tuple[list[dict[str, str]], list[str]]:
    if symbol.lower() != "xauusd" or timeframe.lower() != "m1":
        return [], ["realtime-json currently supports only xauusd/m1."]
    start = datetime.combine(date_from, datetime.min.time(), tzinfo=UTC)
    end = datetime.combine(date_to, datetime.min.time(), tzinfo=UTC)
    callback = "_callbacks____elpisxau"
    params = {
        "path": "chart/json3",
        "instrument": "XAU/USD",
        "offer_side": "B",
        "interval": "1MIN",
        "splits": "true",
        "stocks": "true",
        "init": "true",
        "time_direction": "N",
        "jsonp": callback,
    }
    warnings: list[str] = []
    for attempt in range(max(max_retries, 1)):
        try:
            start_ms = start.timestamp() * 1000
            end_ms = end.timestamp() * 1000
            target_ms = end_ms
            by_timestamp: dict[float, list[Any]] = {}
            while target_ms > start_ms:
                response = httpx.get(
                    "https://freeserv.dukascopy.com/2.0/index.php",
                    params={**params, "timestamp": str(int(target_ms))},
                    headers={"Referer": "https://freeserv.dukascopy.com/2.0"},
                    timeout=timeout_seconds,
                )
                response.raise_for_status()
                payload = _parse_jsonp(response.text, callback)
                if not payload:
                    break
                for item in payload:
                    by_timestamp[float(item[0])] = item
                earliest = min(float(item[0]) for item in payload)
                if earliest >= target_ms or earliest <= start_ms:
                    break
                target_ms = earliest
            rows = [
                _normalize_realtime_row(by_timestamp[timestamp])
                for timestamp in sorted(by_timestamp)
                if start_ms <= timestamp < end_ms
            ]
            return rows, warnings
        except (httpx.HTTPError, ValueError, TypeError, IndexError) as exc:
            warnings.append(
                f"Dukascopy realtime-json attempt {attempt + 1} failed for "
                f"{date_from} to {date_to}: {_sanitize(str(exc))}"
            )
            if attempt + 1 < max(max_retries, 1):
                time.sleep(min(2**attempt, 8))
    return [], warnings


def normalize_dukascopy_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [_normalize_row(row) for row in csv.DictReader(handle)]


def write_monthly_files(
    *,
    rows: list[dict[str, str]],
    output_dir: Path,
    append: bool,
    overwrite: bool,
) -> list[Path]:
    grouped: dict[str, dict[str, dict[str, str]]] = {}
    for row in rows:
        month = row["timestamp"][:7]
        grouped.setdefault(month, {})[row["timestamp"]] = row
    written: list[Path] = []
    for month, by_timestamp in sorted(grouped.items()):
        path = output_dir / f"{month}.csv"
        merged = dict(by_timestamp)
        if path.exists() and append and not overwrite:
            with path.open("r", encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    merged[row["timestamp"]] = row
        elif path.exists() and not overwrite and not append:
            raise FileExistsError(path)
        temporary = path.with_suffix(path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["timestamp", "open", "high", "low", "close", "volume"],
            )
            writer.writeheader()
            for timestamp in sorted(merged):
                writer.writerow(merged[timestamp])
        temporary.replace(path)
        written.append(path)
    return written


def write_coverage_manifest(
    *,
    output_dir: Path,
    date_from: date,
    date_to: date,
    transport: str,
) -> Path:
    counts: dict[str, int] = {}
    for path in sorted(output_dir.glob("????-??.csv")):
        with path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                day = _parse_timestamp(row["timestamp"]).date().isoformat()
                counts[day] = counts.get(day, 0) + 1
    current = date_from
    dates = []
    while current < date_to:
        text = current.isoformat()
        dates.append(
            {
                "date": text,
                "row_count": counts.get(text, 0),
                "has_bars": counts.get(text, 0) > 0,
            }
        )
        current += timedelta(days=1)
    payload = {
        "symbol": "xauusd",
        "timeframe": "m1",
        "price_side": "bid",
        "provider": "dukascopy",
        "transport": transport,
        "date_from": date_from.isoformat(),
        "date_to_exclusive": date_to.isoformat(),
        "dates": dates,
        "research_only": True,
        "signal_allowed": False,
    }
    path = output_dir / "coverage_manifest.json"
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path


def _normalize_row(row: dict[str, Any]) -> dict[str, str]:
    timestamp = _parse_timestamp(row["timestamp"])
    return {
        "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
        "open": str(float(row["open"])),
        "high": str(float(row["high"])),
        "low": str(float(row["low"])),
        "close": str(float(row["close"])),
        "volume": str(float(row["volume"])) if row.get("volume") not in (None, "") else "",
    }


def _normalize_realtime_row(row: list[Any]) -> dict[str, str]:
    return {
        "timestamp": datetime.fromtimestamp(float(row[0]) / 1000, tz=UTC)
        .isoformat()
        .replace("+00:00", "Z"),
        "open": str(float(row[1])),
        "high": str(float(row[2])),
        "low": str(float(row[3])),
        "close": str(float(row[4])),
        "volume": str(float(row[5])) if len(row) > 5 and row[5] is not None else "",
    }


def _parse_jsonp(value: str, callback: str) -> list[list[Any]]:
    prefix = f"{callback}("
    if not value.startswith(prefix) or not value.endswith(");"):
        raise ValueError("unexpected Dukascopy JSONP response")
    payload = json.loads(value[len(prefix) : -2])
    if not isinstance(payload, list):
        raise ValueError("Dukascopy JSONP payload is not a list")
    return payload


def _parse_timestamp(value: Any) -> datetime:
    text = str(value).strip()
    if text.replace(".", "", 1).isdigit():
        number = float(text)
        seconds = number / 1000 if number > 10_000_000_000 else number
        return datetime.fromtimestamp(seconds, tz=UTC)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _date_chunks(start: date, end: date, chunk_days: int) -> list[tuple[date, date]]:
    if end <= start:
        raise ValueError("date-to must be after date-from")
    chunks: list[tuple[date, date]] = []
    current = start
    while current < end:
        chunk_end = min(current + timedelta(days=chunk_days), end)
        chunks.append((current, chunk_end))
        current = chunk_end
    return chunks


def _sanitize(value: str) -> str:
    return " ".join(value.split())[:500]


if __name__ == "__main__":
    raise SystemExit(main())
