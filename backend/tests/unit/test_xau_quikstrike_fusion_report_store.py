from pathlib import Path

import pytest

from src.models.xau_quikstrike_fusion import XauFusionArtifactFormat, XauFusionArtifactType
from src.xau_quikstrike_fusion.report_store import XauQuikStrikeFusionReportStore


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


def test_report_store_artifact_paths_must_stay_under_report_root(tmp_path: Path):
    store = XauQuikStrikeFusionReportStore(reports_dir=tmp_path / "data" / "reports")

    with pytest.raises(ValueError, match="report root"):
        store.artifact(
            artifact_type=XauFusionArtifactType.REPORT_JSON,
            path=tmp_path / "outside.json",
            artifact_format=XauFusionArtifactFormat.JSON,
        )
