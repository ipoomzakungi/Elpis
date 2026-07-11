from __future__ import annotations

import csv

from scripts.fetch_xau_yahoo_range import _safe_name, _write_atomic, build_parser


def test_yahoo_symbol_uses_separate_safe_folder() -> None:
    assert _safe_name("GC=F") == "gc_f"


def test_yahoo_monthly_write_is_atomic_and_normalized(tmp_path) -> None:
    path = tmp_path / "2026-06.csv"
    rows = [
        {
            "timestamp": "2026-06-01T00:05:00Z",
            "open": "101",
            "high": "102",
            "low": "100",
            "close": "101.5",
            "volume": "5",
        },
        {
            "timestamp": "2026-06-01T00:00:00Z",
            "open": "100",
            "high": "101",
            "low": "99",
            "close": "100.5",
            "volume": "4",
        },
    ]

    _write_atomic(path, rows)

    with path.open("r", encoding="utf-8", newline="") as handle:
        stored = list(csv.DictReader(handle))
    assert [item["timestamp"] for item in stored] == [
        "2026-06-01T00:00:00Z",
        "2026-06-01T00:05:00Z",
    ]
    assert not path.with_suffix(".csv.tmp").exists()


def test_yahoo_fetch_cli_requires_date_range() -> None:
    parser = build_parser()
    args = parser.parse_args(["--date-from", "2026-05-30", "--date-to", "2026-07-11"])

    assert args.symbol == "GC=F"
    assert args.interval == "5m"
