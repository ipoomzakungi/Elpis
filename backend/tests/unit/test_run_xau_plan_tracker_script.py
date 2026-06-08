from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_run_xau_plan_tracker_help_works() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/run_xau_plan_tracker.py", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "research-only XAU plan tracker" in result.stdout


def test_run_xau_plan_tracker_fixture_run_writes_artifacts(tmp_path: Path) -> None:
    bars_path = tmp_path / "xau_bars.csv"
    bars_path.write_text(
        "timestamp,open,high,low,close\n"
        "2026-06-08T10:10:00,4470,4471,4469,4470\n"
        "2026-06-08T10:11:00,4470,4471,4425,4430\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_xau_plan_tracker.py",
            "--session-date",
            "2026-06-08",
            "--planning-time",
            "10:10",
            "--price-bars-path",
            str(bars_path),
            "--cme-source",
            "fixture",
            "--output-root",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert '"signal_allowed": false' in result.stdout
    assert list((tmp_path / "xau_plan_tracker").glob("*/plan_tracker_metadata.json"))
