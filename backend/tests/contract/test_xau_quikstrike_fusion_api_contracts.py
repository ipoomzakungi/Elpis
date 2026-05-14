from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.routes.xau_quikstrike_fusion import get_xau_quikstrike_fusion_report_store
from src.main import app
from src.models.xau_quikstrike_fusion import (
    XauFusionContextStatus,
    XauFusionContextSummary,
    XauFusionMissingContextItem,
    XauFusionReportStatus,
    XauQuikStrikeFusionReport,
)
from src.quikstrike.report_store import QuikStrikeReportStore
from src.quikstrike_matrix.report_store import QuikStrikeMatrixReportStore
from src.xau_quikstrike_fusion.report_store import XauQuikStrikeFusionReportStore
from tests.helpers.test_xau_quikstrike_fusion_data import (
    persist_sample_matrix_report,
    persist_sample_vol2vol_report,
    sample_coverage_summary,
    sample_matrix_source_ref,
    sample_vol2vol_source_ref,
)


@pytest.fixture()
def client_and_store(tmp_path: Path) -> Iterator[tuple[TestClient, XauQuikStrikeFusionReportStore]]:
    store = XauQuikStrikeFusionReportStore(reports_dir=tmp_path / "data" / "reports")
    app.dependency_overrides[get_xau_quikstrike_fusion_report_store] = lambda: store
    with TestClient(app) as client:
        yield client, store
    app.dependency_overrides.clear()


def test_xau_quikstrike_fusion_routes_are_registered_in_openapi():
    client = TestClient(app)

    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/xau/quikstrike-fusion/reports" in paths
    assert "/api/v1/xau/quikstrike-fusion/reports/{report_id}" in paths
    assert "/api/v1/xau/quikstrike-fusion/reports/{report_id}/rows" in paths
    assert "/api/v1/xau/quikstrike-fusion/reports/{report_id}/missing-context" in paths


def test_xau_quikstrike_fusion_create_persists_report(client_and_store):
    client, store = client_and_store
    _persist_source_reports(store)

    response = client.post(
        "/api/v1/xau/quikstrike-fusion/reports",
        json=_request_payload(),
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["report_id"].startswith("xau_quikstrike_fusion_")
    assert payload["vol2vol_source"]["report_id"] == "vol2vol_report"
    assert payload["matrix_source"]["report_id"] == "matrix_report"
    assert payload["fused_row_count"] >= 1
    assert payload["xau_vol_oi_input_row_count"] >= 1
    assert payload["limitations"]
    assert "artifacts" in payload
    assert (store.report_dir(payload["report_id"]) / "report.json").exists()


def test_xau_quikstrike_fusion_list_detail_rows_and_missing_context(client_and_store):
    client, store = client_and_store
    _persist_source_reports(store)
    created = client.post(
        "/api/v1/xau/quikstrike-fusion/reports",
        json=_request_payload(),
    ).json()
    report_id = created["report_id"]

    listing = client.get("/api/v1/xau/quikstrike-fusion/reports")
    detail = client.get(f"/api/v1/xau/quikstrike-fusion/reports/{report_id}")
    rows = client.get(f"/api/v1/xau/quikstrike-fusion/reports/{report_id}/rows")
    missing = client.get(
        f"/api/v1/xau/quikstrike-fusion/reports/{report_id}/missing-context"
    )

    assert listing.status_code == 200
    assert listing.json()["reports"][0]["report_id"] == report_id
    assert detail.status_code == 200
    assert detail.json()["report_id"] == report_id
    assert rows.status_code == 200
    assert rows.json()["report_id"] == report_id
    assert rows.json()["rows"]
    assert missing.status_code == 200
    assert missing.json()["report_id"] == report_id
    assert isinstance(missing.json()["missing_context"], list)


def test_xau_quikstrike_fusion_missing_source_report_is_structured(client_and_store):
    client, _store = client_and_store

    response = client.post(
        "/api/v1/xau/quikstrike-fusion/reports",
        json=_request_payload(vol2vol_report_id="missing_vol2vol"),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SOURCE_NOT_FOUND"
    assert response.json()["error"]["details"][0]["field"] == "vol2vol_report_id"


def test_xau_quikstrike_fusion_incompatible_source_report_is_structured(
    client_and_store,
    monkeypatch: pytest.MonkeyPatch,
):
    client, _store = client_and_store
    from src.api.routes import xau_quikstrike_fusion as route_module

    monkeypatch.setattr(
        route_module,
        "orchestrate_xau_quikstrike_fusion_report",
        lambda *args, **kwargs: _incompatible_report(),
    )

    response = client.post(
        "/api/v1/xau/quikstrike-fusion/reports",
        json=_request_payload(),
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INCOMPATIBLE_SOURCE_REPORTS"
    assert response.json()["error"]["details"][0]["field"] == "matrix_product"


def test_xau_quikstrike_fusion_missing_report_and_invalid_request_are_structured(
    client_and_store,
):
    client, _store = client_and_store

    missing = client.get("/api/v1/xau/quikstrike-fusion/reports/unknown_report")
    invalid_ack = client.post(
        "/api/v1/xau/quikstrike-fusion/reports",
        json={**_request_payload(), "research_only_acknowledged": False},
    )
    invalid_id = client.get("/api/v1/xau/quikstrike-fusion/reports/bad%20id")

    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "NOT_FOUND"
    assert invalid_ack.status_code == 400
    assert invalid_ack.json()["error"]["code"] == "VALIDATION_ERROR"
    assert invalid_id.status_code == 400
    assert invalid_id.json()["error"]["code"] == "VALIDATION_ERROR"


def _persist_source_reports(store: XauQuikStrikeFusionReportStore) -> None:
    persist_sample_vol2vol_report(
        QuikStrikeReportStore(reports_dir=store.reports_dir),
        extraction_id="vol2vol_report",
    )
    persist_sample_matrix_report(
        QuikStrikeMatrixReportStore(reports_dir=store.reports_dir),
        extraction_id="matrix_report",
    )


def _request_payload(
    *,
    vol2vol_report_id: str = "vol2vol_report",
    matrix_report_id: str = "matrix_report",
) -> dict:
    return {
        "vol2vol_report_id": vol2vol_report_id,
        "matrix_report_id": matrix_report_id,
        "xauusd_spot_reference": 4692.1,
        "gc_futures_reference": 4696.7,
        "session_open_price": None,
        "realized_volatility": None,
        "candle_context": [],
        "create_xau_vol_oi_report": False,
        "create_xau_reaction_report": False,
        "run_label": "contract",
        "persist_report": True,
        "research_only_acknowledged": True,
    }


def _incompatible_report() -> XauQuikStrikeFusionReport:
    matrix_ref = sample_matrix_source_ref().model_copy(update={"product": "Corn (OZC|ZC)"})
    return XauQuikStrikeFusionReport(
        report_id="fusion_blocked",
        status=XauFusionReportStatus.BLOCKED,
        vol2vol_source=sample_vol2vol_source_ref(),
        matrix_source=matrix_ref,
        coverage=sample_coverage_summary().model_copy(update={"matched_key_count": 0}),
        context_summary=XauFusionContextSummary(
            basis_status=XauFusionContextStatus.UNAVAILABLE,
            iv_range_status=XauFusionContextStatus.UNAVAILABLE,
            open_regime_status=XauFusionContextStatus.UNAVAILABLE,
            candle_acceptance_status=XauFusionContextStatus.UNAVAILABLE,
            realized_volatility_status=XauFusionContextStatus.UNAVAILABLE,
            source_agreement_status=XauFusionContextStatus.BLOCKED,
            missing_context=[
                XauFusionMissingContextItem(
                    context_key="matrix_product",
                    status=XauFusionContextStatus.BLOCKED,
                    severity="error",
                    blocks_fusion=True,
                    message="matrix source report is not Gold/OG/GC compatible.",
                    source_refs=["matrix_report"],
                )
            ],
        ),
        fused_row_count=0,
        warnings=["matrix source report is not Gold/OG/GC compatible."],
    )
