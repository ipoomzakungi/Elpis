from datetime import UTC, datetime
from pathlib import Path

from src.models.xau_quikstrike_fusion import (
    XauFusionContextStatus,
    XauFusionReportStatus,
    XauQuikStrikeFusionRequest,
)
from src.xau_quikstrike_fusion.orchestration import create_xau_quikstrike_fusion_report
from src.xau_quikstrike_fusion.report_store import XauQuikStrikeFusionReportStore
from tests.helpers.test_xau_quikstrike_fusion_data import (
    make_matrix_store,
    make_vol2vol_store,
    persist_sample_matrix_report,
    persist_sample_vol2vol_report,
)


def test_synthetic_vol2vol_and_matrix_reports_fuse_and_persist(tmp_path: Path):
    vol2vol_store = make_vol2vol_store(tmp_path)
    matrix_store = make_matrix_store(tmp_path)
    fusion_store = XauQuikStrikeFusionReportStore(
        reports_dir=tmp_path / "data" / "reports"
    )
    persist_sample_vol2vol_report(vol2vol_store)
    persist_sample_matrix_report(matrix_store)

    report = create_xau_quikstrike_fusion_report(
        XauQuikStrikeFusionRequest(
            vol2vol_report_id="vol2vol_report",
            matrix_report_id="matrix_report",
            candle_context=[],
            persist_report=True,
            research_only_acknowledged=True,
        ),
        vol2vol_store=vol2vol_store,
        matrix_store=matrix_store,
        report_store=fusion_store,
        report_id="fusion_report",
        created_at=datetime(2026, 5, 13, tzinfo=UTC),
    )

    assert report.status == XauFusionReportStatus.PARTIAL
    assert report.fused_row_count == 4
    assert report.coverage is not None
    assert report.coverage.matched_key_count == 4
    assert report.context_summary is not None
    assert report.context_summary.source_agreement_status == XauFusionContextStatus.AVAILABLE
    assert all(row.vol2vol_value and row.matrix_value for row in report.fused_rows)
    assert (fusion_store.report_dir("fusion_report") / "metadata.json").exists()
    assert (fusion_store.report_dir("fusion_report") / "fused_rows.json").exists()
    assert (fusion_store.report_dir("fusion_report") / "report.json").exists()
    assert (fusion_store.report_dir("fusion_report") / "report.md").exists()
    assert all(
        artifact.path.startswith("data/reports/xau_quikstrike_fusion/")
        for artifact in report.artifacts
    )


def test_missing_source_reports_create_blocked_research_report(tmp_path: Path):
    report = create_xau_quikstrike_fusion_report(
        XauQuikStrikeFusionRequest(
            vol2vol_report_id="missing_vol2vol",
            matrix_report_id="missing_matrix",
            candle_context=[],
            persist_report=False,
            research_only_acknowledged=True,
        ),
        vol2vol_store=make_vol2vol_store(tmp_path),
        matrix_store=make_matrix_store(tmp_path),
        report_id="blocked_fusion",
        created_at=datetime(2026, 5, 13, tzinfo=UTC),
    )

    assert report.status == XauFusionReportStatus.BLOCKED
    assert report.fused_rows == []
    assert report.context_summary is not None
    assert report.context_summary.missing_context
    assert all(item.blocks_fusion for item in report.context_summary.missing_context)
