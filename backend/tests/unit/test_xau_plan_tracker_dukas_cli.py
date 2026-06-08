from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from src.models.xau_price_plan_tracker import (
    XauDukasCaptureStatus,
    XauDukasCliCaptureRequest,
)
from src.xau_price_plan_tracker.dukas_cli import load_price_bars, run_dukas_cli_capture


def test_load_price_bars_reads_csv_aliases(tmp_path: Path) -> None:
    path = tmp_path / "xau.csv"
    path.write_text(
        "datetime,bid_open,bid_high,bid_low,bid_close,tick_volume\n"
        "2026-06-08T10:10:00,4470,4472,4468,4471,12\n",
        encoding="utf-8",
    )

    bars = load_price_bars(path)

    assert len(bars) == 1
    assert bars[0].timestamp == datetime.fromisoformat("2026-06-08T10:10:00")
    assert bars[0].open == 4470
    assert bars[0].volume == 12


def test_run_dukas_cli_capture_failed_command_returns_failed(tmp_path: Path) -> None:
    result = run_dukas_cli_capture(
        XauDukasCliCaptureRequest(
            start_time=datetime.fromisoformat("2026-06-08T10:10:00"),
            end_time=datetime.fromisoformat("2026-06-08T10:20:00"),
            dukas_cli_path=Path(sys.executable),
            command_template='"{cli}" -c "import sys; sys.exit(3)"',
            output_dir=tmp_path,
        )
    )

    assert result.status == XauDukasCaptureStatus.FAILED
    assert result.bars_count == 0
    assert result.signal_allowed is False
