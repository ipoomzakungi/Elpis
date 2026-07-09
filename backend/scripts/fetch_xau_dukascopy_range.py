from __future__ import annotations

import argparse
import csv
import json
import subprocess
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

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
    summary = {
        "symbol": args.symbol,
        "timeframe": args.timeframe,
        "date_from": args.date_from,
        "date_to": args.date_to,
        "rows": len(all_rows),
        "files": [path.as_posix() for path in written],
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
    completed = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    if completed.returncode != 0:
        message = _sanitize(completed.stderr or completed.stdout)
        return [], [f"Dukascopy command failed for {date_from} to {date_to}: {message}"]
    csv_path = download_dir / f"{file_name}.csv"
    if not csv_path.exists():
        return [], [f"Dukascopy command did not create {csv_path}."]
    return normalize_dukascopy_csv(csv_path), []


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
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["timestamp", "open", "high", "low", "close", "volume"],
            )
            writer.writeheader()
            for timestamp in sorted(merged):
                writer.writerow(merged[timestamp])
        written.append(path)
    return written


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
