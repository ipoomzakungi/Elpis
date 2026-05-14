from pathlib import Path

import pytest

from src.models.xau_forward_journal import (
    XauForwardArtifactFormat,
    XauForwardArtifactType,
    XauForwardJournalEntryStatus,
    XauForwardJournalSummary,
)
from src.xau_forward_journal.report_store import XauForwardJournalReportStore


def test_report_store_roots_are_path_safe(tmp_path: Path):
    store = XauForwardJournalReportStore(reports_dir=tmp_path / "data" / "reports")

    assert store.report_root() == tmp_path / "data" / "reports" / "xau_forward_journal"
    assert store.ensure_report_root().exists()
    assert store.report_dir("journal_report") == (
        tmp_path / "data" / "reports" / "xau_forward_journal" / "journal_report"
    )

    with pytest.raises(ValueError):
        store.report_dir("../outside")


def test_report_store_rejects_nested_or_parent_traversal_artifact_filenames(tmp_path: Path):
    store = XauForwardJournalReportStore(reports_dir=tmp_path / "data" / "reports")

    with pytest.raises(ValueError):
        store.artifact_path("journal_report", "../outside.json")

    with pytest.raises(ValueError):
        store.artifact_path("journal_report", "nested/report.json")


def test_artifact_metadata_helper_uses_ignored_local_report_paths(tmp_path: Path):
    store = XauForwardJournalReportStore(reports_dir=tmp_path / "data" / "reports")
    artifact_path = store.artifact_path("journal_report", "report.json")
    artifact = store.artifact(
        artifact_type=XauForwardArtifactType.REPORT_JSON,
        path=artifact_path,
        artifact_format=XauForwardArtifactFormat.JSON,
        rows=3,
    )

    assert artifact.path == "data/reports/xau_forward_journal/journal_report/report.json"
    assert artifact.rows == 3


def test_report_store_serializes_models_and_writes_json_artifacts(tmp_path: Path):
    store = XauForwardJournalReportStore(reports_dir=tmp_path / "data" / "reports")
    summary = XauForwardJournalSummary(
        journal_id="journal_report",
        status=XauForwardJournalEntryStatus.PARTIAL,
        snapshot_time="2026-05-14T03:08:04Z",
        capture_session="quikstrike_gold_am",
        fusion_report_id="fusion_report",
        xau_vol_oi_report_id="xau_report",
        xau_reaction_report_id="reaction_report",
        pending_outcome_count=5,
    )

    artifact = store.write_json_artifact(
        "journal_report",
        "metadata.json",
        {"summary": summary},
        artifact_type=XauForwardArtifactType.METADATA,
        rows=1,
    )
    saved = store.artifact_path("journal_report", "metadata.json").read_text(
        encoding="utf-8"
    )

    assert artifact.path == "data/reports/xau_forward_journal/journal_report/metadata.json"
    assert '"journal_id": "journal_report"' in saved
    assert '"status": "partial"' in saved


def test_report_store_artifact_paths_must_stay_under_report_root(tmp_path: Path):
    store = XauForwardJournalReportStore(reports_dir=tmp_path / "data" / "reports")

    with pytest.raises(ValueError, match="report root"):
        store.artifact(
            artifact_type=XauForwardArtifactType.REPORT_JSON,
            path=tmp_path / "outside.json",
            artifact_format=XauForwardArtifactFormat.JSON,
        )
