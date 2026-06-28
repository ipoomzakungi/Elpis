from pathlib import Path

from fastapi.testclient import TestClient

from src.api.routes.xau_candidate_outcomes import get_xau_candidate_outcome_service
from src.main import app
from src.xau_candidate_outcomes.service import XauCandidateOutcomeService
from tests.unit.test_xau_candidate_outcome_store import (
    _write_candidate_set,
    _write_price_bars,
)


def test_candidate_outcome_run_latest_and_read_endpoints(tmp_path: Path) -> None:
    service = XauCandidateOutcomeService(reports_dir=tmp_path / "data" / "reports")
    candidate_path = _write_candidate_set(tmp_path)
    price_path = _write_price_bars(tmp_path)
    app.dependency_overrides[get_xau_candidate_outcome_service] = lambda: service
    client = TestClient(app)

    try:
        response = client.post(
            "/api/v1/research/xau/candidate-outcomes/run",
            json={
                "candidate_set_path": str(candidate_path),
                "price_bars_path": str(price_path),
                "windows": ["30m"],
                "research_only_acknowledged": True,
            },
        )
        assert response.status_code == 200
        payload = response.json()
        outcome_run_id = payload["outcome_run_id"]
        assert payload["outcome_count"] == 1
        assert payload["signal_allowed"] is False

        latest = client.get("/api/v1/research/xau/candidate-outcomes/latest")
        assert latest.status_code == 200
        assert latest.json()["latest_run"]["outcome_run_id"] == outcome_run_id

        read = client.get(f"/api/v1/research/xau/candidate-outcomes/{outcome_run_id}")
        assert read.status_code == 200
        assert read.json()["outcome_run_id"] == outcome_run_id
    finally:
        app.dependency_overrides.clear()
