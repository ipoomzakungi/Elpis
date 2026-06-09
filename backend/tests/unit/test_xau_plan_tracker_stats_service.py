from __future__ import annotations

from datetime import date
from pathlib import Path

from src.models.xau_plan_tracker_statistics import XauPlanTrackerStatsRequest
from src.models.xau_price_plan_tracker import (
    XauPlanTrackerRequest,
    XauResearchOrderSide,
)
from src.xau_plan_tracker_statistics.service import XauPlanTrackerStatisticsService
from src.xau_price_plan_tracker.service import XauPlanTrackerService


def test_stats_service_aggregates_multiple_runs_and_session_filters(tmp_path: Path) -> None:
    _create_plan_tracker_run(tmp_path, date(2026, 6, 8), "4470")
    _create_plan_tracker_run(tmp_path, date(2026, 6, 9), "4480")

    stats_service = XauPlanTrackerStatisticsService(reports_dir=tmp_path)
    result = stats_service.run(
        XauPlanTrackerStatsRequest(
            session_date_from=date(2026, 6, 8),
            session_date_to=date(2026, 6, 9),
        )
    )

    assert result.run_count == 2
    assert result.order_count == 8
    assert result.snapshot_count == 4
    assert len(result.run_summaries) == 2
    assert result.run_summaries[0].snapshot_count == 2
    assert result.run_summaries[1].snapshot_count == 2


def test_stats_service_filters_by_planning_time_and_side(tmp_path: Path) -> None:
    run = _create_plan_tracker_run(tmp_path, date(2026, 6, 8), "4470")

    stats_service = XauPlanTrackerStatisticsService(reports_dir=tmp_path)
    result = stats_service.run(
        XauPlanTrackerStatsRequest(
            planning_times=["10:10"],
            sides=[XauResearchOrderSide.LONG_REVERSION],
        )
    )

    assert result.run_count == 1
    assert result.order_count == 1
    assert result.snapshot_count == 1
    assert len(result.run_summaries) == 1
    assert result.run_summaries[0].run_id == run.run_id
    assert result.run_summaries[0].order_count == 1


def test_run_for_run_only_uses_requested_run(tmp_path: Path) -> None:
    _create_plan_tracker_run(tmp_path, date(2026, 6, 8), "4470")
    run_2 = _create_plan_tracker_run(tmp_path, date(2026, 6, 9), "4480")

    stats_service = XauPlanTrackerStatisticsService(reports_dir=tmp_path)
    result = stats_service.run_for_run(
        run_id=run_2.run_id,
        request=XauPlanTrackerStatsRequest(),
    )

    assert result.run_count == 1
    assert result.run_ids == [run_2.run_id]
    assert result.snapshot_count == 2
    assert result.order_count == 4


def _create_plan_tracker_run(tmp_path: Path, session_date: date, open_value: str):
    bars_path = tmp_path / f"xau_bars_{session_date}.csv"
    bars_path.write_text(
        "\n".join(
            [
                "timestamp,open,high,low,close",
                f"{session_date}T10:10:00,{open_value},{int(open_value)+1},{int(open_value)-1},{open_value}",
                f"{session_date}T18:10:00,{open_value},{int(open_value)+1},{int(open_value)-1},{open_value}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return XauPlanTrackerService(reports_dir=tmp_path).run(
        XauPlanTrackerRequest(
            session_date=session_date,
            planning_times=["10:10", "18:10"],
            price_bars_path=bars_path,
            output_root=tmp_path,
            cme_source="fixture",
        )
    )
