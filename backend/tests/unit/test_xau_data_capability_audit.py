from datetime import UTC, date, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from src.api.routes.xau_data_capability_audit import (
    get_xau_data_capability_audit_service,
)
from src.main import app
from src.models.xau import XauOptionsImportReport, XauOptionsOiRow, XauOptionType
from src.models.xau_data_capability_audit import (
    XauDataCapabilityAuditRequest,
    XauDataCapabilityName,
    XauDataCapabilityStatus,
)
from src.xau.report_store import XauReportStore
from src.xau_data_capability_audit.service import XauDataCapabilityAuditService
from tests.helpers.test_xau_quikstrike_fusion_data import (
    make_matrix_store,
    make_vol2vol_store,
    persist_sample_matrix_report,
    persist_sample_vol2vol_report,
)
from tests.helpers.test_xau_reaction_data import sample_feature006_xau_report


def test_audit_detects_quikstrike_oi_oi_change_dte_and_missing_gamma(
    tmp_path: Path,
) -> None:
    reports_dir = tmp_path / "data" / "reports"
    persist_sample_vol2vol_report(make_vol2vol_store(tmp_path))
    persist_sample_matrix_report(make_matrix_store(tmp_path))

    result = XauDataCapabilityAuditService(reports_dir=reports_dir).run(
        XauDataCapabilityAuditRequest(max_reports_per_source=1)
    )
    capabilities = _capabilities(result)

    assert capabilities[XauDataCapabilityName.HAS_OI].status == (
        XauDataCapabilityStatus.AVAILABLE
    )
    assert capabilities[XauDataCapabilityName.HAS_OI_CHANGE].status == (
        XauDataCapabilityStatus.AVAILABLE
    )
    assert capabilities[XauDataCapabilityName.HAS_DTE].status == (
        XauDataCapabilityStatus.AVAILABLE
    )
    assert capabilities[XauDataCapabilityName.HAS_GAMMA].status == (
        XauDataCapabilityStatus.UNAVAILABLE
    )
    assert capabilities[XauDataCapabilityName.HAS_GEX_POSSIBLE].status == (
        XauDataCapabilityStatus.BLOCKED
    )
    assert result.signal_allowed is False
    assert result.research_only is True


def test_audit_marks_gamma_and_gex_possible_when_xau_rows_include_gamma(
    tmp_path: Path,
) -> None:
    reports_dir = tmp_path / "data" / "reports"
    store = XauReportStore(reports_dir=reports_dir)
    report = sample_feature006_xau_report().model_copy(
        update={
            "source_validation": XauOptionsImportReport(
                file_path="C:/synthetic/xau_options.csv",
                is_valid=True,
                source_row_count=1,
                accepted_row_count=1,
                rejected_row_count=0,
                rows=[
                    XauOptionsOiRow(
                        source_row_id="row_1",
                        timestamp=datetime(2026, 6, 7, 12, 0, tzinfo=UTC),
                        expiry=date(2026, 6, 14),
                        days_to_expiry=7,
                        strike=4500.0,
                        option_type=XauOptionType.CALL,
                        open_interest=1000.0,
                        oi_change=25.0,
                        volume=200.0,
                        implied_volatility=0.18,
                        underlying_futures_price=4500.0,
                        delta=0.45,
                        gamma=0.02,
                    )
                ],
            ),
            "source_row_count": 1,
            "accepted_row_count": 1,
            "rejected_row_count": 0,
        }
    )
    store.save_source_validation_report(report)

    result = XauDataCapabilityAuditService(reports_dir=reports_dir).run(
        XauDataCapabilityAuditRequest(max_reports_per_source=1)
    )
    capabilities = _capabilities(result)

    assert capabilities[XauDataCapabilityName.HAS_DELTA].status == (
        XauDataCapabilityStatus.AVAILABLE
    )
    assert capabilities[XauDataCapabilityName.HAS_GAMMA].status == (
        XauDataCapabilityStatus.AVAILABLE
    )
    assert capabilities[XauDataCapabilityName.HAS_GEX_POSSIBLE].status == (
        XauDataCapabilityStatus.AVAILABLE
    )


def test_data_capability_audit_endpoint_returns_research_only_result(
    tmp_path: Path,
) -> None:
    reports_dir = tmp_path / "data" / "reports"
    persist_sample_vol2vol_report(make_vol2vol_store(tmp_path))
    service = XauDataCapabilityAuditService(reports_dir=reports_dir)
    app.dependency_overrides[get_xau_data_capability_audit_service] = lambda: service
    client = TestClient(app)

    response = client.post(
        "/api/v1/research/xau/data-capability-audit/run",
        json={"max_reports_per_source": 1, "research_only_acknowledged": True},
    )

    app.dependency_overrides.clear()
    assert response.status_code == 200
    payload = response.json()
    assert payload["signal_allowed"] is False
    assert payload["research_only"] is True
    assert any(
        capability["capability"] == "has_oi"
        and capability["status"] == "available"
        for capability in payload["capabilities"]
    )


def _capabilities(result):
    return {capability.capability: capability for capability in result.capabilities}
