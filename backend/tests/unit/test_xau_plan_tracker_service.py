from __future__ import annotations

from datetime import date
from pathlib import Path

from src.models.xau_price_plan_tracker import (
    XauPlanTrackerReadiness,
    XauPlanTrackerRequest,
)
from src.xau_price_plan_tracker.service import XauPlanTrackerService


def test_plan_tracker_service_uses_fixture_sd_and_bars(tmp_path: Path) -> None:
    bars_path = tmp_path / "xau_bars.csv"
    bars_path.write_text(
        "timestamp,open,high,low,close,volume\n"
        "2026-06-08T10:10:00,4470,4471,4469,4470,1\n"
        "2026-06-08T10:11:00,4470,4471,4425,4430,1\n"
        "2026-06-08T10:12:00,4430,4446,4418,4440,1\n"
        "2026-06-08T18:10:00,4470,4471,4469,4470,1\n"
        "2026-06-08T18:11:00,4470,4521,4469,4510,1\n"
        "2026-06-08T18:12:00,4510,4525,4500,4505,1\n",
        encoding="utf-8",
    )

    result = XauPlanTrackerService(reports_dir=tmp_path).run(
        XauPlanTrackerRequest(
            session_date=date(2026, 6, 8),
            planning_times=["10:10", "18:10"],
            cme_source="fixture",
            price_bars_path=bars_path,
            output_root=tmp_path,
        )
    )

    assert result.readiness == XauPlanTrackerReadiness.COMPLETE
    assert result.snapshot_count == 2
    assert result.tracked_order_count == 4
    assert (tmp_path / "xau_plan_tracker" / result.run_id / "tracked_orders.json").exists()
    snapshots = XauPlanTrackerService(reports_dir=tmp_path).get_snapshots(result.run_id)
    assert snapshots[0].diff_points == 30
    assert snapshots[0].long_plan is not None
