import json
import subprocess
import sys
from datetime import date
from pathlib import Path

from src.models.xau_price_plan_tracker import XauPlanTrackerRequest
from src.xau_price_plan_tracker.service import XauPlanTrackerService


def test_script_help_returns_zero() -> None:
    from scripts.run_xau_plan_tracker_stats import main

    exit_code = main(["--help"])

    assert exit_code == 0


def test_script_run_for_run_id_writes_json(tmp_path: Path) -> None:
    bars_path = tmp_path / "xau_bars.csv"
    bars_path.write_text(
        "\n".join(
            [
                "timestamp,open,high,low,close",
                "2026-06-08T10:10:00,4470,4471,4469,4470",
                "2026-06-08T18:10:00,4470,4471,4469,4470",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = XauPlanTrackerService(reports_dir=tmp_path).run(
        XauPlanTrackerRequest(
            session_date=date(2026, 6, 8),
            planning_times=["10:10", "18:10"],
            price_bars_path=bars_path,
            output_root=tmp_path,
            cme_source="fixture",
        )
    )

    process = subprocess.run(
        [
            sys.executable,
            "backend/scripts/run_xau_plan_tracker_stats.py",
            "--run-id",
            result.run_id,
            "--output-root",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert process.returncode == 0
    payload = json.loads(process.stdout)
    assert payload["run_count"] == 1
    assert payload["run_ids"] == [result.run_id]
    assert payload["signal_allowed"] is False
    assert payload["research_only"] is True
