from pathlib import Path

import polars as pl
import pytest

from src.models.xau_reaction import XauReactionArtifactFormat, XauReactionArtifactType
from src.xau_reaction.orchestration import assemble_reaction_report
from src.xau_reaction.report_store import XauReactionReportStore
from tests.helpers.test_xau_reaction_data import (
    sample_feature006_xau_report,
    sample_xau_reaction_full_context_request,
)


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


def test_reaction_report_store_persists_metadata_rows_json_and_markdown(tmp_path):
    store = XauReactionReportStore(reports_dir=tmp_path / "reports")
    report = assemble_reaction_report(
        request=sample_xau_reaction_full_context_request(),
        source_report=sample_feature006_xau_report(),
    )

    saved = store.save_report(report)
    report_dir = store.report_dir(saved.report_id)

    assert (report_dir / "metadata.json").exists()
    assert (report_dir / "report.json").exists()
    assert (report_dir / "report.md").exists()
    assert (report_dir / "reactions.parquet").exists()
    assert (report_dir / "risk_plans.parquet").exists()

    loaded = store.read_report(saved.report_id)
    reactions = store.read_reactions(saved.report_id)
    risk_plan = store.read_risk_plan(saved.report_id)
    report_json = (report_dir / "report.json").read_text(encoding="utf-8")
    report_markdown = (report_dir / "report.md").read_text(encoding="utf-8")

    assert loaded.report_id == saved.report_id
    assert loaded.reaction_count == 1
    assert reactions.report_id == saved.report_id
    assert reactions.data[0].reaction_id == loaded.reactions[0].reaction_id
    assert risk_plan.report_id == saved.report_id
    assert risk_plan.data[0].reaction_id == loaded.reactions[0].reaction_id
    assert "XAU Reaction Report" in report_markdown
    assert "research_disclaimer" in report_json

    reaction_frame = pl.read_parquet(report_dir / "reactions.parquet")
    risk_frame = pl.read_parquet(report_dir / "risk_plans.parquet")
    assert reaction_frame.height == 1
    assert risk_frame.height == 1

    listed = store.list_reports()
    assert [summary.report_id for summary in listed.reports] == [saved.report_id]
