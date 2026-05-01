from src.models.xau import XauReportStatus
from src.xau.orchestration import XauReportOrchestrator
from src.xau.report_store import XauReportStore
from tests.helpers.test_xau_data import (
    sample_xau_report_request,
    write_sample_xau_options_csv,
    write_sample_xau_options_parquet,
)


def test_xau_import_flow_persists_source_validation_for_csv(tmp_path):
    source_path = write_sample_xau_options_csv(tmp_path / "gold_options.csv")
    store = XauReportStore(reports_dir=tmp_path / "reports")
    request = sample_xau_report_request(source_path)

    report = XauReportOrchestrator(report_store=store).run(request)
    saved = store.read_report(report.report_id)

    assert report.status == XauReportStatus.PARTIAL
    assert report.source_row_count == 2
    assert report.accepted_row_count == 2
    assert report.rejected_row_count == 0
    assert report.wall_count == 2
    assert report.zone_count >= 1
    assert report.basis_snapshot is not None
    assert report.basis_snapshot.basis == 7.0
    assert report.expected_range is not None
    assert report.expected_range.expected_move is not None
    assert saved.report_id == report.report_id
    assert saved.wall_count == report.wall_count
    assert saved.zone_count == report.zone_count
    assert any(artifact.artifact_type == "source_validation" for artifact in report.artifacts)


def test_xau_import_flow_accepts_parquet_and_emits_missing_optional_instructions(tmp_path):
    source_path = write_sample_xau_options_parquet(
        tmp_path / "gold_options.parquet",
        include_optional=False,
    )
    store = XauReportStore(reports_dir=tmp_path / "reports")
    request = sample_xau_report_request(source_path)
    request.volatility_snapshot = None

    report = XauReportOrchestrator(report_store=store).run(request)

    assert report.status == XauReportStatus.PARTIAL
    assert report.accepted_row_count == 2
    assert any("implied_volatility" in item for item in report.missing_data_instructions)
    assert any("oi_change or volume" in item for item in report.missing_data_instructions)
