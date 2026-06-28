from pathlib import Path

from fastapi.testclient import TestClient

from src.api.routes.xau_daily_workbench import get_xau_daily_workbench_service
from src.main import app
from src.xau_daily_workbench.service import XauDailyWorkbenchService


def test_workbench_run_endpoint_cleanly_reports_api_only_unavailable(tmp_path: Path) -> None:
    service = XauDailyWorkbenchService(reports_dir=tmp_path / "data" / "reports")
    app.dependency_overrides[get_xau_daily_workbench_service] = lambda: service
    client = TestClient(app)

    response = client.post(
        "/api/v1/research/xau/workbench/run",
        json={
            "traded_instrument": "XAUUSD",
            "cme_source": "api_only",
            "research_only_acknowledged": True,
        },
    )

    app.dependency_overrides.clear()
    assert response.status_code == 200
    payload = response.json()
    assert payload["readiness"] == "blocked"
    assert payload["missing_inputs"][0]["input_name"] == "cme_source.api_only"
    assert payload["signal_allowed"] is False
