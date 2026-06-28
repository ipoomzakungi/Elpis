from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from src.api.routes.xau_walk_forward import get_xau_walk_forward_service
from src.main import app
from src.xau_walk_forward.service import XauWalkForwardResearchService


def test_walk_forward_run_endpoint_returns_research_only_result(tmp_path: Path) -> None:
    app.dependency_overrides[get_xau_walk_forward_service] = lambda: (
        XauWalkForwardResearchService(reports_dir=tmp_path)
    )
    client = TestClient(app)

    response = client.post(
        "/api/v1/research/xau/walk-forward/run",
        json={
            "session_date": str(date(2026, 6, 8)),
            "schedule_config": {"include_planning_times_only": True},
            "cme_source": "fixture",
            "price_source": "manual",
            "future_reference_price": 4500,
            "traded_reference_price": 4470,
            "research_only_acknowledged": True,
        },
    )

    app.dependency_overrides.clear()
    assert response.status_code == 200
    payload = response.json()
    assert payload["signal_allowed"] is False
    assert payload["research_only"] is True
    assert payload["snapshot_count"] == 2
    assert payload["order_plan_count"] == 8
