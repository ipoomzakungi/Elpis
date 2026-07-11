from __future__ import annotations

from datetime import date

from scripts.fetch_xau_dukascopy_range import (
    fetch_chunk,
    fetch_realtime_json_chunk,
    write_coverage_manifest,
    write_monthly_files,
)
from src.xau_vol2vol_history_walkforward.walkforward_simulator import (
    load_traded_bars_folder,
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


def test_realtime_json_transport_filters_requested_range(monkeypatch) -> None:
    class Response:
        text = (
            "_callbacks____elpisxau("
            "[[1782777540000,1,2,0.5,1.5,3],"
            "[1782777600000,10,12,9,11,4]]);"
        )

        def raise_for_status(self) -> None:
            return None

    monkeypatch.setattr(
        "scripts.fetch_xau_dukascopy_range.httpx.get",
        lambda *args, **kwargs: Response(),
    )

    rows, warnings = fetch_realtime_json_chunk(
        symbol="xauusd",
        timeframe="m1",
        date_from=date(2026, 6, 30),
        date_to=date(2026, 7, 1),
        timeout_seconds=30,
        max_retries=1,
    )

    assert warnings == []
    assert len(rows) == 1
    assert rows[0]["timestamp"] == "2026-06-30T00:00:00Z"
    assert rows[0]["close"] == "11.0"


def test_coverage_manifest_reports_dates_without_bars(tmp_path) -> None:
    write_monthly_files(
        rows=[
            {
                "timestamp": "2026-07-01T00:00:00Z",
                "open": "1",
                "high": "2",
                "low": "0.5",
                "close": "1.5",
                "volume": "1",
            }
        ],
        output_dir=tmp_path,
        append=False,
        overwrite=False,
    )

    manifest = write_coverage_manifest(
        output_dir=tmp_path,
        date_from=date(2026, 6, 30),
        date_to=date(2026, 7, 2),
        transport="realtime-json",
    )

    payload = manifest.read_text(encoding="utf-8")
    assert '"date": "2026-06-30"' in payload
    assert '"has_bars": false' in payload
    assert '"row_count": 1' in payload


def test_price_bars_folder_loads_months_and_deduplicates_timestamps(tmp_path) -> None:
    header = "timestamp,open,high,low,close,volume\n"
    (tmp_path / "2026-06.csv").write_text(
        header + "2026-06-30T23:59:00Z,1,2,0.5,1.5,1\n",
        encoding="utf-8",
    )
    (tmp_path / "2026-07.csv").write_text(
        header
        + "2026-06-30T23:59:00Z,1,3,0.5,2.5,1\n"
        + "2026-07-01T00:00:00Z,2,3,1.5,2.5,1\n",
        encoding="utf-8",
    )
    (tmp_path / "coverage_manifest.json").write_text("{}", encoding="utf-8")

    result = load_traded_bars_folder(tmp_path, timezone="UTC")

    assert len(result.bars) == 2
    assert result.duplicate_timestamp_count == 1
    assert result.bars[0].close == 2.5
    assert result.warnings == []
