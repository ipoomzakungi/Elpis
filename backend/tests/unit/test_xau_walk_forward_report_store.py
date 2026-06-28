from datetime import date
from pathlib import Path

from src.models.xau_walk_forward_research import (
    XauWalkForwardCmeSource,
    XauWalkForwardPriceSource,
    XauWalkForwardReadiness,
    XauWalkForwardRunRequest,
    XauWalkForwardScheduleConfig,
)
from src.xau_walk_forward.service import XauWalkForwardResearchService


def test_walk_forward_service_persists_fixture_run(tmp_path: Path) -> None:
    result = XauWalkForwardResearchService(reports_dir=tmp_path).run(
        XauWalkForwardRunRequest(
            session_date=date(2026, 6, 8),
            schedule_config=XauWalkForwardScheduleConfig(
                include_planning_times_only=True,
            ),
            cme_source=XauWalkForwardCmeSource.FIXTURE,
            price_source=XauWalkForwardPriceSource.MANUAL,
            future_reference_price=4500.0,
            traded_reference_price=4470.0,
        )
    )

    assert result.readiness == XauWalkForwardReadiness.COMPLETE
    assert result.snapshot_count == 2
    assert result.order_plan_count == 8
    assert result.signal_allowed is False
    report_dir = tmp_path / "xau_walk_forward" / result.run_id
    assert (report_dir / "run_metadata.json").exists()
    assert (report_dir / "snapshots.json").exists()
    assert (report_dir / "research_orders.json").exists()
    assert (report_dir / "run.md").exists()
