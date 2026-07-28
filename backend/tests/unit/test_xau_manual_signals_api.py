from pathlib import Path

from fastapi.testclient import TestClient

from src.api.routes.xau_manual_signals import (
    get_xau_tiered_manual_signal_service,
)
from src.main import app
from src.xau_tiered_manual_signal.service import XauTieredManualSignalService

POLICY = Path("config/xau_tiered_first_touch_manual_signal_v1.json")


def test_latest_manual_signal_is_empty_before_first_run(tmp_path: Path) -> None:
    service = _service(tmp_path)
    app.dependency_overrides[get_xau_tiered_manual_signal_service] = lambda: service
    try:
        response = TestClient(app).get("/api/v1/research/xau/manual-signals/latest")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["signal"] is None
    assert response.json()["order_submission_allowed"] is False


def test_acknowledgement_is_immutable_and_does_not_submit_order(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.journal.append(
        "signals",
        {
            "signal_id": "signal-1",
            "status": "REFERENCE_ALERT",
        },
        id_field="signal_id",
    )
    app.dependency_overrides[get_xau_tiered_manual_signal_service] = lambda: service
    try:
        response = TestClient(app).post(
            "/api/v1/research/xau/manual-signals/signal-1/acknowledge",
            json={"acknowledged_by": "researcher", "note": "Observed only"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "MANUAL_ACKNOWLEDGED"
    assert response.json()["order_submission_allowed"] is False
    assert len(service.journal.read("acknowledgements")) == 1


def test_acknowledging_unknown_signal_returns_not_found(tmp_path: Path) -> None:
    service = _service(tmp_path)
    app.dependency_overrides[get_xau_tiered_manual_signal_service] = lambda: service
    try:
        response = TestClient(app).post(
            "/api/v1/research/xau/manual-signals/missing/acknowledge",
            json={"acknowledged_by": "researcher"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def _service(tmp_path: Path) -> XauTieredManualSignalService:
    return XauTieredManualSignalService(
        journal_root=tmp_path / "journal",
        policy_path=POLICY,
        vol2vol_root=tmp_path / "vol2vol",
        price_bars_folder=tmp_path / "bars",
    )
