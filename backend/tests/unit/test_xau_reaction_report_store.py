from pathlib import Path

import pytest

from src.models.xau_reaction import XauReactionArtifactFormat, XauReactionArtifactType
from src.xau_reaction.report_store import XauReactionReportStore


def test_reaction_report_store_uses_ignored_xau_reaction_report_root(tmp_path):
    store = XauReactionReportStore(reports_dir=tmp_path / "reports")

    assert store.report_root() == tmp_path / "reports" / "xau_reaction"
    assert store.report_dir("xau_reaction_20260512").parent == store.report_root()


def test_reaction_report_store_rejects_unsafe_report_ids_and_artifact_names(tmp_path):
    store = XauReactionReportStore(reports_dir=tmp_path / "reports")

    for report_id in ("", "../outside", "nested/report", "bad report"):
        with pytest.raises(ValueError):
            store.report_dir(report_id)

    with pytest.raises(ValueError):
        store.artifact_path("xau_reaction_20260512", "../metadata.json")


def test_reaction_report_store_builds_artifacts_only_under_report_root(tmp_path):
    store = XauReactionReportStore(reports_dir=tmp_path / "reports")
    report_dir = store.ensure_report_dir("xau_reaction_20260512")
    artifact_path = report_dir / "metadata.json"

    artifact = store.artifact(
        artifact_type=XauReactionArtifactType.METADATA,
        path=artifact_path,
        artifact_format=XauReactionArtifactFormat.JSON,
        rows=1,
    )

    assert artifact.artifact_type == XauReactionArtifactType.METADATA
    expected_suffix = Path("xau_reaction") / "xau_reaction_20260512" / "metadata.json"
    assert artifact.path.endswith(str(expected_suffix))

    with pytest.raises(ValueError):
        store.artifact(
            artifact_type=XauReactionArtifactType.METADATA,
            path=tmp_path / "outside.json",
            artifact_format=XauReactionArtifactFormat.JSON,
        )
