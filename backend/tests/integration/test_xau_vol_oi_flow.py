import pytest

from src.models.xau import XauBasisSource, XauVolatilitySource
from src.xau.orchestration import XauReportOrchestrator
from src.xau.report_store import XauReportStore
from tests.helpers.test_xau_data import (
    sample_xau_report_request,
    write_sample_xau_options_csv,
    write_sample_xau_options_parquet,
)


def test_xau_vol_oi_flow_returns_computed_basis_and_iv_expected_range(tmp_path):
    source_path = write_sample_xau_options_csv(tmp_path / "gold_options.csv")
    store = XauReportStore(reports_dir=tmp_path / "reports")
    request = sample_xau_report_request(source_path)

    report = XauReportOrchestrator(report_store=store).run(request)

    assert report.source_validation.source_row_count == 2
    assert report.source_validation.accepted_row_count == 2
    assert report.source_validation.rejected_row_count == 0
    assert report.basis_snapshot is not None
    assert report.basis_snapshot.basis == 7.0
    assert report.basis_snapshot.basis_source == XauBasisSource.COMPUTED
    assert report.basis_snapshot.mapping_available is True
    assert report.expected_range is not None
    assert report.expected_range.source == XauVolatilitySource.IV
    assert report.expected_range.reference_price == 2403.0
    assert report.expected_range.expected_move == pytest.approx(53.2447, abs=0.0001)
    assert report.expected_range.lower_1sd == pytest.approx(2349.7553, abs=0.0001)
    assert report.expected_range.upper_1sd == pytest.approx(2456.2447, abs=0.0001)
    assert report.expected_range.lower_2sd == pytest.approx(2296.5106, abs=0.0001)
    assert report.expected_range.upper_2sd == pytest.approx(2509.4894, abs=0.0001)
    assert any(artifact.artifact_type == "source_validation" for artifact in report.artifacts)


def test_xau_vol_oi_flow_marks_expected_range_unavailable_without_iv(tmp_path):
    source_path = write_sample_xau_options_parquet(
        tmp_path / "gold_options.parquet",
        include_optional=False,
    )
    store = XauReportStore(reports_dir=tmp_path / "reports")
    request = sample_xau_report_request(source_path)
    request.volatility_snapshot = None

    report = XauReportOrchestrator(report_store=store).run(request)

    assert report.expected_range is not None
    assert report.expected_range.source == XauVolatilitySource.UNAVAILABLE
    assert report.expected_range.expected_move is None
    assert report.expected_range.lower_1sd is None
    assert report.expected_range.upper_1sd is None
    assert report.expected_range.unavailable_reason == "Volatility snapshot is unavailable."
    assert any("implied_volatility" in item for item in report.missing_data_instructions)
    assert "Volatility snapshot is unavailable." in report.missing_data_instructions


def test_xau_vol_oi_flow_marks_mapping_unavailable_without_basis_inputs(tmp_path):
    source_path = write_sample_xau_options_csv(tmp_path / "gold_options.csv")
    store = XauReportStore(reports_dir=tmp_path / "reports")
    request = sample_xau_report_request(source_path)
    request.futures_reference = None
    request.manual_basis = None

    report = XauReportOrchestrator(report_store=store).run(request)

    assert report.basis_snapshot is not None
    assert report.basis_snapshot.basis is None
    assert report.basis_snapshot.basis_source == XauBasisSource.UNAVAILABLE
    assert report.basis_snapshot.mapping_available is False
    assert any(
        "spot" in item.lower() and "futures" in item.lower()
        for item in report.basis_snapshot.notes
    )
    assert any(
        "spot_reference and futures_reference" in item
        for item in report.missing_data_instructions
    )
