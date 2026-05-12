from fastapi.testclient import TestClient

from src.main import app
from src.xau.report_store import XauReportStore
from src.xau_reaction.report_store import XauReactionReportStore
from tests.helpers.test_xau_reaction_data import (
    sample_feature006_xau_report,
    sample_xau_reaction_full_context_request,
)


def test_synthetic_xau_reaction_report_api_flow_persists_and_reads_sections():
    source_report = XauReportStore().save_source_validation_report(sample_feature006_xau_report())
    request = sample_xau_reaction_full_context_request().model_copy(
        update={"source_report_id": source_report.report_id}
    )
    client = TestClient(app)

    create_response = client.post(
        "/api/v1/xau/reaction-reports",
        json=request.model_dump(mode="json"),
    )

    assert create_response.status_code == 200
    created = create_response.json()
    report_id = created["report_id"]
    assert created["source_report_id"] == source_report.report_id
    assert created["reaction_count"] == 1
    assert created["risk_plan_count"] == 1

    detail = client.get(f"/api/v1/xau/reaction-reports/{report_id}").json()
    reactions = client.get(f"/api/v1/xau/reaction-reports/{report_id}/reactions").json()
    risk_plan = client.get(f"/api/v1/xau/reaction-reports/{report_id}/risk-plan").json()

    assert detail["report_id"] == report_id
    assert reactions["data"][0]["source_report_id"] == source_report.report_id
    assert reactions["data"][0]["wall_id"] == "wall_2400_call"
    assert risk_plan["data"][0]["reaction_id"] == reactions["data"][0]["reaction_id"]
    assert risk_plan["data"][0]["entry_condition_text"]

    store = XauReactionReportStore()
    report_dir = store.report_dir(report_id)
    assert (report_dir / "metadata.json").exists()
    assert (report_dir / "report.json").exists()
    assert (report_dir / "report.md").exists()
    assert (report_dir / "reactions.parquet").exists()
    assert (report_dir / "risk_plans.parquet").exists()

    response_text = str({"detail": detail, "reactions": reactions, "risk_plan": risk_plan}).lower()
    for forbidden_term in (
        "buy",
        "sell",
        "execute",
        "execution",
        "live",
        "guaranteed",
        "profitable",
        "safe",
        "signal",
    ):
        assert forbidden_term not in response_text
