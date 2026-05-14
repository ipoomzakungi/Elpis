import pytest

from src.models.xau_forward_journal import (
    XauForwardJournalCreateRequest,
    XauForwardOutcomeLabel,
    XauForwardOutcomeStatus,
)
from src.xau_forward_journal.orchestration import (
    XauForwardJournalConflictError,
    create_xau_forward_journal_entry,
)
from src.xau_forward_journal.report_store import XauForwardJournalReportStore
from tests.helpers.test_xau_forward_journal_data import (
    synthetic_forward_journal_create_payload,
    write_synthetic_source_reports,
)


def _request(**updates) -> XauForwardJournalCreateRequest:
    payload = synthetic_forward_journal_create_payload()
    payload.update(updates)
    return XauForwardJournalCreateRequest.model_validate(payload)


def test_create_entry_flow_persists_snapshot_and_is_idempotent_when_outcomes_pending(tmp_path):
    reports_dir = tmp_path / "data" / "reports"
    write_synthetic_source_reports(reports_dir)
    store = XauForwardJournalReportStore(reports_dir=reports_dir)

    first = create_xau_forward_journal_entry(_request(), report_store=store)
    second = create_xau_forward_journal_entry(_request(), report_store=store)

    assert first.journal_id == second.journal_id
    assert first.snapshot_key == second.snapshot_key
    assert first.snapshot.capture_window == "daily_snapshot"
    assert first.snapshot.capture_session is None
    assert len(first.top_oi_walls) == 2
    assert len(first.top_oi_change_walls) == 1
    assert len(first.top_volume_walls) == 1
    assert len(first.reaction_summaries) == 2
    assert len(first.outcomes) == 5
    assert len(list(store.report_root().glob("*"))) == 1


def test_create_entry_conflicts_when_matching_snapshot_has_non_pending_outcome(tmp_path):
    reports_dir = tmp_path / "data" / "reports"
    write_synthetic_source_reports(reports_dir)
    store = XauForwardJournalReportStore(reports_dir=reports_dir)

    first = create_xau_forward_journal_entry(_request(), report_store=store)
    completed_outcome = first.outcomes[0].model_copy(
        update={
            "status": XauForwardOutcomeStatus.COMPLETED,
            "label": XauForwardOutcomeLabel.INCONCLUSIVE,
        }
    )
    store.persist_entry(
        first.model_copy(update={"outcomes": [completed_outcome, *first.outcomes[1:]]})
    )

    with pytest.raises(XauForwardJournalConflictError) as exc:
        create_xau_forward_journal_entry(_request(), report_store=store)

    assert exc.value.code == "JOURNAL_ENTRY_CONFLICT"
    assert any(detail["field"] == "snapshot_key" for detail in exc.value.details)
