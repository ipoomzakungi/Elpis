from __future__ import annotations

import argparse
import csv
import json
import os
from collections.abc import Sequence
from datetime import date
from pathlib import Path

import yfinance as yf


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch a separate Yahoo gold futures research dataset.",
    )
    parser.add_argument("--symbol", default="GC=F")
    parser.add_argument("--interval", default="5m")
    parser.add_argument("--date-from", required=True)
    parser.add_argument("--date-to", required=True)
    parser.add_argument("--output-root", default="data/imports/xau/yahoo")
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)
    frame = yf.download(
        args.symbol,
        start=args.date_from,
        end=args.date_to,
        interval=args.interval,
        auto_adjust=False,
        prepost=True,
        progress=False,
        threads=False,
    )
    if frame.empty:
        parser.error(f"Yahoo returned no rows for {args.symbol}")
    if getattr(frame.columns, "nlevels", 1) > 1:
        frame.columns = frame.columns.get_level_values(0)
    output_dir = (
        Path(args.output_root)
        / _safe_name(args.symbol)
        / args.interval.lower()
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    rows_by_month: dict[str, list[dict[str, str]]] = {}
    for timestamp, row in frame.iterrows():
        utc_timestamp = (
            timestamp.tz_convert("UTC")
            if timestamp.tzinfo
            else timestamp.tz_localize("UTC")
        )
        record = {
            "timestamp": utc_timestamp.isoformat().replace("+00:00", "Z"),
            "open": str(float(row["Open"])),
            "high": str(float(row["High"])),
            "low": str(float(row["Low"])),
            "close": str(float(row["Close"])),
            "volume": str(float(row["Volume"])),
        }
        rows_by_month.setdefault(record["timestamp"][:7], []).append(record)
    written = []
    for month, rows in sorted(rows_by_month.items()):
        path = output_dir / f"{month}.csv"
        if path.exists() and not args.overwrite:
            raise FileExistsError(path)
        _write_atomic(path, rows)
        written.append(path)
    print(
        json.dumps(
            {
                "provider": "yahoo_finance",
                "instrument": "GC gold futures continuous front-month",
                "symbol": args.symbol,
                "interval": args.interval,
                "date_from": date.fromisoformat(args.date_from).isoformat(),
                "date_to": date.fromisoformat(args.date_to).isoformat(),
                "row_count": len(frame),
                "files": [path.resolve().as_posix() for path in written],
                "not_spot_or_broker_cfd": True,
                "research_only": True,
                "signal_allowed": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _write_atomic(path: Path, rows: list[dict[str, str]]) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["timestamp", "open", "high", "low", "close", "volume"],
        )
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda item: item["timestamp"]))
        handle.flush()
        os.fsync(handle.fileno())
    temp.replace(path)


def _safe_name(symbol: str) -> str:
    return "".join(char.lower() if char.isalnum() else "_" for char in symbol).strip("_")


if __name__ == "__main__":
    raise SystemExit(main())
