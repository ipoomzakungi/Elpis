from __future__ import annotations

from datetime import date

from scripts.fetch_xau_dukascopy_range import (
    fetch_chunk,
    write_monthly_files,
)


def test_fetch_chunk_uses_mocked_subprocess_and_normalizes_epoch_ms(
    monkeypatch,
    tmp_path,
) -> None:
    def fake_run(command, shell, capture_output, text, timeout, check):
        output = tmp_path / "xauusd_m1_2026-07-08_2026-07-09.csv"
        output.write_text(
            "timestamp,open,high,low,close,volume\n"
            "1783468800000,4098.205,4101.515,4096.625,4096.805,0.063\n",
            encoding="utf-8",
        )

        class Completed:
            returncode = 0
            stdout = ""
            stderr = ""

        return Completed()

    monkeypatch.setattr("scripts.fetch_xau_dukascopy_range.subprocess.run", fake_run)

    rows, warnings = fetch_chunk(
        command_template=(
            "npx dukascopy-node -i {symbol} -from {date_from} -to {date_to} "
            "-t {timeframe} -f csv -dir {download_dir} -fn {file_name}"
        ),
        symbol="xauusd",
        timeframe="m1",
        date_from=date(2026, 7, 8),
        date_to=date(2026, 7, 9),
        download_dir=tmp_path,
        timeout_seconds=30,
    )

    assert warnings == []
    assert rows[0]["timestamp"] == "2026-07-08T00:00:00Z"
    assert rows[0]["close"] == "4096.805"


def test_write_monthly_files_deduplicates_by_timestamp(tmp_path) -> None:
    rows = [
        {
            "timestamp": "2026-07-08T00:00:00Z",
            "open": "1",
            "high": "2",
            "low": "0.5",
            "close": "1.5",
            "volume": "1",
        },
        {
            "timestamp": "2026-07-08T00:00:00Z",
            "open": "1",
            "high": "3",
            "low": "0.5",
            "close": "2.5",
            "volume": "1",
        },
    ]

    written = write_monthly_files(rows=rows, output_dir=tmp_path, append=False, overwrite=False)

    assert written == [tmp_path / "2026-07.csv"]
    lines = written[0].read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert lines[1].endswith(",2.5,1")
