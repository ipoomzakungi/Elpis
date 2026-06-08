from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from src.api.routes.xau_plan_tracker import get_xau_plan_tracker_service
from src.main import app
from src.xau_price_plan_tracker.service import XauPlanTrackerService


def test_plan_tracker_run_endpoint_returns_research_only_result(tmp_path: Path) -> None:
    bars_path = tmp_path / "xau_bars.csv"
    bars_path.write_text(
        "timestamp,open,high,low,close\n"
        "2026-06-08T10:10:00,4470,4471,4469,4470\n"
        "2026-06-08T10:11:00,4470,4471,4425,4430\n"
        "2026-06-08T18:10:00,4470,4471,4469,4470\n",
        encoding="utf-8",
    )
    app.dependency_overrides[get_xau_plan_tracker_service] = lambda: (
        XauPlanTrackerService(reports_dir=tmp_path)
    )
    client = TestClient(app)

    response = client.post(
        "/api/v1/research/xau/plan-tracker/run",
        json={
            "session_date": str(date(2026, 6, 8)),
            "planning_times": ["10:10", "18:10"],
            "cme_source": "fixture",
            "price_bars_path": str(bars_path),
            "output_root": str(tmp_path),
            "near_miss_threshold_points": 0.25,
            "research_only_acknowledged": True,
        },
    )

    app.dependency_overrides.clear()
    assert response.status_code == 200
    payload = response.json()
    assert payload["signal_allowed"] is False
    assert payload["research_only"] is True
    assert payload["snapshot_count"] == 2
    assert payload["tracked_order_count"] == 4
