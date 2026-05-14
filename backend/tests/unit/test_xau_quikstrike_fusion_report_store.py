from pathlib import Path

import pytest

from src.models.xau_quikstrike_fusion import (
    XauFusionArtifactFormat,
    XauFusionArtifactType,
    XauFusionContextStatus,
    XauFusionContextSummary,
    XauFusionReportStatus,
    XauQuikStrikeFusionReport,
    XauQuikStrikeFusionSummary,
)
from src.xau_quikstrike_fusion.basis import calculate_basis_state
from src.xau_quikstrike_fusion.report_store import XauQuikStrikeFusionReportStore
from tests.helpers.test_xau_quikstrike_fusion_data import (
    sample_coverage_summary,
    sample_fused_row,
    sample_matrix_source_ref,
    sample_matrix_source_value,
    sample_vol2vol_source_ref,
    sample_vol2vol_source_value,
)


def test_report_store_roots_are_path_safe(tmp_path: Path):
    store = XauQuikStrikeFusionReportStore(reports_dir=tmp_path / "data" / "reports")

    assert store.report_root() == tmp_path / "data" / "reports" / "xau_quikstrike_fusion"
    assert store.ensure_report_root().exists()
    assert store.report_dir("fusion_report") == (
        tmp_path / "data" / "reports" / "xau_quikstrike_fusion" / "fusion_report"
    )

    with pytest.raises(ValueError):
        store.report_dir("../outside")


def test_report_store_rejects_nested_or_parent_traversal_artifact_filenames(tmp_path: Path):
    store = XauQuikStrikeFusionReportStore(reports_dir=tmp_path / "data" / "reports")

    with pytest.raises(ValueError):
        store.artifact_path("fusion_report", "../outside.json")

    with pytest.raises(ValueError):
        store.artifact_path("fusion_report", "nested/report.json")


def test_artifact_metadata_helper_uses_ignored_local_report_paths(tmp_path: Path):
    store = XauQuikStrikeFusionReportStore(reports_dir=tmp_path / "data" / "reports")
    artifact_path = store.artifact_path("fusion_report", "report.json")
    artifact = store.artifact(
        artifact_type=XauFusionArtifactType.REPORT_JSON,
        path=artifact_path,
        artifact_format=XauFusionArtifactFormat.JSON,
        rows=3,
    )

    assert artifact.path == "data/reports/xau_quikstrike_fusion/fusion_report/report.json"
    assert artifact.rows == 3


def test_report_store_serializes_models_and_writes_json_artifacts(tmp_path: Path):
    store = XauQuikStrikeFusionReportStore(reports_dir=tmp_path / "data" / "reports")
    summary = XauQuikStrikeFusionSummary(
        report_id="fusion_report",
        status=XauFusionReportStatus.PARTIAL,
        vol2vol_report_id="vol2vol_report",
        matrix_report_id="matrix_report",
        fused_row_count=0,
        strike_count=0,
        expiration_count=0,
    )

    artifact = store.write_json_artifact(
        "fusion_report",
        "metadata.json",
        {"summary": summary},
        artifact_type=XauFusionArtifactType.METADATA,
        rows=1,
    )
    saved = store.artifact_path("fusion_report", "metadata.json").read_text(encoding="utf-8")

    assert artifact.path == "data/reports/xau_quikstrike_fusion/fusion_report/metadata.json"
    assert '"report_id": "fusion_report"' in saved
    assert '"status": "partial"' in saved


def test_report_store_artifact_paths_must_stay_under_report_root(tmp_path: Path):
    store = XauQuikStrikeFusionReportStore(reports_dir=tmp_path / "data" / "reports")

    with pytest.raises(ValueError, match="report root"):
        store.artifact(
            artifact_type=XauFusionArtifactType.REPORT_JSON,
            path=tmp_path / "outside.json",
            artifact_format=XauFusionArtifactFormat.JSON,
        )


def test_report_store_persists_mvp_report_metadata_rows_json_and_markdown(tmp_path: Path):
    store = XauQuikStrikeFusionReportStore(reports_dir=tmp_path / "data" / "reports")
    report = XauQuikStrikeFusionReport(
        report_id="fusion_report",
        status=XauFusionReportStatus.PARTIAL,
        vol2vol_source=sample_vol2vol_source_ref(),
        matrix_source=sample_matrix_source_ref(),
        coverage=sample_coverage_summary(),
        basis_state=calculate_basis_state(
            xauusd_spot_reference=4692.1,
            gc_futures_reference=4696.7,
        ),
        context_summary=XauFusionContextSummary(
            basis_status=XauFusionContextStatus.AVAILABLE,
            iv_range_status=XauFusionContextStatus.UNAVAILABLE,
            open_regime_status=XauFusionContextStatus.UNAVAILABLE,
            candle_acceptance_status=XauFusionContextStatus.UNAVAILABLE,
            realized_volatility_status=XauFusionContextStatus.UNAVAILABLE,
            source_agreement_status=XauFusionContextStatus.AVAILABLE,
        ),
        fused_row_count=1,
        fused_rows=[sample_fused_row()],
    )

    saved = store.persist_report(report)

    assert (store.report_dir("fusion_report") / "metadata.json").exists()
    assert (store.report_dir("fusion_report") / "fused_rows.json").exists()
    assert (store.report_dir("fusion_report") / "report.json").exists()
    assert (store.report_dir("fusion_report") / "report.md").exists()
    assert {artifact.artifact_type for artifact in saved.artifacts} == {
        XauFusionArtifactType.METADATA,
        XauFusionArtifactType.FUSED_ROWS_JSON,
        XauFusionArtifactType.REPORT_JSON,
        XauFusionArtifactType.REPORT_MARKDOWN,
    }
    report_json = (store.report_dir("fusion_report") / "report.json").read_text(
        encoding="utf-8"
    )
    metadata_json = (store.report_dir("fusion_report") / "metadata.json").read_text(
        encoding="utf-8"
    )
    assert '"fused_row_count": 1' in report_json
    assert '"basis_state"' in metadata_json
    assert '"missing_context_count": 0' in metadata_json
    assert "local-only research report" in (
        store.report_dir("fusion_report") / "report.md"
    ).read_text(encoding="utf-8").lower()


def test_report_store_persists_fused_xau_input_csv_and_metadata(tmp_path: Path):
    from src.xau_quikstrike_fusion.fusion import (
        build_fusion_rows,
        build_xau_vol_oi_input_rows,
    )

    store = XauQuikStrikeFusionReportStore(reports_dir=tmp_path / "data" / "reports")
    rows, _, blocked_reasons = build_fusion_rows(
        fusion_report_id="fusion_report",
        vol2vol_values=[
            sample_vol2vol_source_value().model_copy(update={"expiration": "2026-05-15"})
        ],
        matrix_values=[
            sample_matrix_source_value().model_copy(update={"expiration": "2026-05-15"})
        ],
    )
    conversion = build_xau_vol_oi_input_rows(
        rows,
        upstream_blocked_reasons=blocked_reasons,
    )
    report = XauQuikStrikeFusionReport(
        report_id="fusion_report",
        status=XauFusionReportStatus.PARTIAL,
        vol2vol_source=sample_vol2vol_source_ref(),
        matrix_source=sample_matrix_source_ref(),
        coverage=sample_coverage_summary(),
        basis_state=calculate_basis_state(),
        context_summary=XauFusionContextSummary(
            basis_status=XauFusionContextStatus.UNAVAILABLE,
            iv_range_status=XauFusionContextStatus.UNAVAILABLE,
            open_regime_status=XauFusionContextStatus.UNAVAILABLE,
            candle_acceptance_status=XauFusionContextStatus.UNAVAILABLE,
            realized_volatility_status=XauFusionContextStatus.UNAVAILABLE,
            source_agreement_status=XauFusionContextStatus.AVAILABLE,
        ),
        fused_row_count=len(rows),
        xau_vol_oi_input_row_count=len(conversion.rows),
        fused_rows=rows,
    )

    saved = store.persist_report(report, xau_vol_oi_input_rows=conversion.rows)

    input_path = store.report_dir("fusion_report") / "xau_vol_oi_input.csv"
    metadata_json = (store.report_dir("fusion_report") / "metadata.json").read_text(
        encoding="utf-8"
    )
    report_md = (store.report_dir("fusion_report") / "report.md").read_text(
        encoding="utf-8"
    )

    assert input_path.exists()
    assert "open_interest" in input_path.read_text(encoding="utf-8")
    assert '"xau_vol_oi_input_row_count": 1' in metadata_json
    assert "XAU Vol-OI input rows" in report_md
    assert XauFusionArtifactType.XAU_VOL_OI_INPUT_CSV in {
        artifact.artifact_type for artifact in saved.artifacts
    }
