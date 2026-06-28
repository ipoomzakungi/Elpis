from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from src.api.routes.xau_plan_tracker import (
    get_xau_plan_tracker_service,
    get_xau_plan_tracker_statistics_service,
)
from src.main import app
from src.models.xau_price_plan_tracker import (
    XauPlanTrackerRequest,
    XauResearchOrderSide,
)
from src.xau_plan_tracker_statistics.service import XauPlanTrackerStatisticsService
from src.xau_price_plan_tracker.service import XauPlanTrackerService


def test_plan_tracker_stats_endpoint_returns_aggregated_result(tmp_path: Path) -> None:
    run = _create_plan_tracker_run(tmp_path, date(2026, 6, 8))
    app.dependency_overrides[get_xau_plan_tracker_service] = lambda: (
        XauPlanTrackerService(reports_dir=tmp_path)
    )
    app.dependency_overrides[get_xau_plan_tracker_statistics_service] = lambda: (
        XauPlanTrackerStatisticsService(reports_dir=tmp_path)
    )
    client = TestClient(app)

    response = client.post(
        "/api/v1/research/xau/plan-tracker/stats",
        json={"session_date_from": str(run.session_date), "session_date_to": str(run.session_date)},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_count"] == 1
    assert payload["order_count"] == 4
    assert payload["signal_allowed"] is False
    assert payload["research_only"] is True


def test_plan_tracker_run_stats_endpoint_filters_by_time(tmp_path: Path) -> None:
    run = _create_plan_tracker_run(tmp_path, date(2026, 6, 8))
    app.dependency_overrides[get_xau_plan_tracker_service] = lambda: (
        XauPlanTrackerService(reports_dir=tmp_path)
    )
    app.dependency_overrides[get_xau_plan_tracker_statistics_service] = lambda: (
        XauPlanTrackerStatisticsService(reports_dir=tmp_path)
    )
    client = TestClient(app)

    response = client.get(
        f"/api/v1/research/xau/plan-tracker/stats/{run.run_id}",
        params={
            "planning_times": ["10:10"],
            "sides": [XauResearchOrderSide.LONG_REVERSION.value],
        },
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_count"] == 1
    assert payload["snapshot_count"] == 1
    assert payload["order_count"] == 1


def _create_plan_tracker_run(tmp_path: Path, session_date: date):
    bars_path = tmp_path / "xau_bars.csv"
    bars_path.write_text(
        "\n".join(
            [
                "timestamp,open,high,low,close",
                f"{session_date}T10:10:00,4470,4471,4469,4470",
                f"{session_date}T18:10:00,4470,4471,4469,4470",
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
