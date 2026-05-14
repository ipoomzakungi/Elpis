from pathlib import Path

import pytest

from src.models.xau_forward_journal import (
    XauForwardArtifactFormat,
    XauForwardArtifactType,
    XauForwardJournalCreateRequest,
    XauForwardJournalEntryStatus,
    XauForwardJournalSummary,
    XauForwardOutcomeLabel,
    XauForwardOutcomeStatus,
    XauForwardOutcomeUpdateRequest,
)
from src.xau_forward_journal.entry_builder import build_journal_entry
from src.xau_forward_journal.outcome import apply_outcome_update
from src.xau_forward_journal.report_store import XauForwardJournalReportStore
from tests.helpers.test_xau_forward_journal_data import (
    synthetic_forward_journal_create_payload,
    write_synthetic_source_reports,
)


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
        snapshot_key="20260514_daily_snapshot_g2rk6_abcdef123456",
        status=XauForwardJournalEntryStatus.PARTIAL,
        snapshot_time="2026-05-14T03:08:04Z",
        capture_window="daily_snapshot",
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


def test_report_store_persists_created_entry_artifacts_and_reads_by_snapshot_key(
    tmp_path: Path,
):
    reports_dir = tmp_path / "data" / "reports"
    write_synthetic_source_reports(reports_dir)
    request = XauForwardJournalCreateRequest.model_validate(
        synthetic_forward_journal_create_payload()
    )
    entry = build_journal_entry(request, reports_dir=reports_dir)
    store = XauForwardJournalReportStore(reports_dir=reports_dir)

    saved_entry = store.persist_entry(entry)

    report_dir = store.report_dir(saved_entry.journal_id)
    assert (report_dir / "metadata.json").exists()
    assert (report_dir / "entry.json").exists()
    assert (report_dir / "outcomes.json").exists()
    assert (report_dir / "report.json").exists()
    assert (report_dir / "report.md").exists()
    assert len(saved_entry.artifacts) == 5
    assert saved_entry.artifacts[0].path.startswith("data/reports/xau_forward_journal/")

    loaded_entry = store.read_entry(saved_entry.journal_id)
    loaded_outcomes = store.read_outcomes(saved_entry.journal_id)
    found_entry = store.find_entry_by_snapshot_key(saved_entry.snapshot_key)
    listed = store.list_entries()

    assert loaded_entry.snapshot_key == saved_entry.snapshot_key
    assert len(loaded_outcomes) == 5
    assert found_entry is not None
    assert found_entry.journal_id == saved_entry.journal_id
    assert listed.entries[0].snapshot_key == saved_entry.snapshot_key


def test_report_store_artifact_paths_must_stay_under_report_root(tmp_path: Path):
    store = XauForwardJournalReportStore(reports_dir=tmp_path / "data" / "reports")

    with pytest.raises(ValueError, match="report root"):
        store.artifact(
            artifact_type=XauForwardArtifactType.REPORT_JSON,
            path=tmp_path / "outside.json",
            artifact_format=XauForwardArtifactFormat.JSON,
        )


def test_report_store_persists_outcome_updates_without_rewriting_snapshot(
    tmp_path: Path,
):
    reports_dir = tmp_path / "data" / "reports"
    write_synthetic_source_reports(reports_dir)
    request = XauForwardJournalCreateRequest.model_validate(
        synthetic_forward_journal_create_payload()
    )
    entry = build_journal_entry(request, reports_dir=reports_dir)
    store = XauForwardJournalReportStore(reports_dir=reports_dir)
    saved_entry = store.persist_entry(entry)
    original_snapshot = saved_entry.snapshot.model_dump(mode="json")

    updated_entry = apply_outcome_update(
        saved_entry,
        XauForwardOutcomeUpdateRequest(
            outcomes=[
                {
                    "window": "30m",
                    "label": "stayed_inside_range",
                    "observation_start": "2026-05-14T03:08:04Z",
                    "observation_end": "2026-05-14T03:38:04Z",
                    "open": 4707.2,
                    "high": 4712.0,
                    "low": 4701.5,
                    "close": 4706.0,
                    "reference_wall_id": "wall_1",
                    "reference_wall_level": 4675.0,
                    "notes": ["Synthetic outcome observation."],
                }
            ],
            update_note="Attach first synthetic outcome observation.",
            research_only_acknowledged=True,
        ),
    )

    persisted = store.persist_outcome_update(updated_entry)
    loaded_entry = store.read_entry(saved_entry.journal_id)
    loaded_outcomes = store.read_outcomes(saved_entry.journal_id)
    response = store.read_outcome_response(saved_entry.journal_id)

    assert persisted.snapshot.model_dump(mode="json") == original_snapshot
    assert loaded_entry.snapshot.model_dump(mode="json") == original_snapshot
    assert loaded_outcomes[0].status == XauForwardOutcomeStatus.COMPLETED
    assert loaded_outcomes[0].label == XauForwardOutcomeLabel.STAYED_INSIDE_RANGE
    assert response.journal_id == saved_entry.journal_id
    assert response.outcomes[0].label == XauForwardOutcomeLabel.STAYED_INSIDE_RANGE
    assert (store.report_dir(saved_entry.journal_id) / "outcomes.json").exists()
