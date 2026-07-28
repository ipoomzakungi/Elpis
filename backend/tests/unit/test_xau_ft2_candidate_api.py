from pathlib import Path

from fastapi.testclient import TestClient

from src.api.routes.xau_ft2_candidate import get_xau_ft2_candidate_service
from src.main import app
from src.xau_ft2_candidate.service import XauFt2CandidateService

POLICY = Path("config/xau_ft2_raw_candidate_v1.json")


def test_latest_ft2_candidate_is_empty_before_first_run(tmp_path: Path) -> None:
    service = _service(tmp_path)
    app.dependency_overrides[get_xau_ft2_candidate_service] = lambda: service
    try:
        response = TestClient(app).get("/api/v1/research/xau/ft2-candidate/latest")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["alert"] is None
    assert response.json()["order_submission_allowed"] is False


def test_acknowledging_unknown_ft2_alert_returns_not_found(tmp_path: Path) -> None:
    service = _service(tmp_path)
    app.dependency_overrides[get_xau_ft2_candidate_service] = lambda: service
    try:
        response = TestClient(app).post(
            "/api/v1/research/xau/ft2-candidate/missing/acknowledge",
            json={"acknowledged_by": "researcher"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def _service(tmp_path: Path) -> XauFt2CandidateService:
    return XauFt2CandidateService(
        journal_root=tmp_path / "journal",
        policy_path=POLICY,
        vol2vol_root=tmp_path / "vol",
        price_bars_folder=tmp_path / "bars",
    )
