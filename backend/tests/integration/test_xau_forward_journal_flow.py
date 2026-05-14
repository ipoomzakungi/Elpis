import pytest

from src.models.xau_forward_journal import (
    XauForwardJournalCreateRequest,
    XauForwardOutcomeLabel,
    XauForwardOutcomeStatus,
    XauForwardOutcomeUpdateRequest,
)
from src.xau_forward_journal.orchestration import (
    XauForwardJournalConflictError,
    create_xau_forward_journal_entry,
    update_xau_forward_journal_outcomes,
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
        first.model_copy(update={"outcomes": [completed_outcome, *first.outcomes[1:]]}),
        overwrite_allowed=True,
    )

    with pytest.raises(XauForwardJournalConflictError) as exc:
        create_xau_forward_journal_entry(_request(), report_store=store)

    assert exc.value.code == "JOURNAL_ENTRY_CONFLICT"
    assert any(detail["field"] == "snapshot_key" for detail in exc.value.details)


def test_outcome_update_flow_preserves_immutable_snapshot_fields(tmp_path):
    reports_dir = tmp_path / "data" / "reports"
    write_synthetic_source_reports(reports_dir)
    store = XauForwardJournalReportStore(reports_dir=reports_dir)

    entry = create_xau_forward_journal_entry(_request(), report_store=store)
    original_snapshot = entry.snapshot.model_dump(mode="json")

    response = update_xau_forward_journal_outcomes(
        entry.journal_id,
        XauForwardOutcomeUpdateRequest(
            outcomes=[
                {
                    "window": "30m",
                    "label": "no_trade_was_correct",
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
        report_store=store,
    )
    loaded = store.read_entry(entry.journal_id)

    assert response.outcomes[0].status == XauForwardOutcomeStatus.COMPLETED
    assert response.outcomes[0].label == XauForwardOutcomeLabel.NO_TRADE_WAS_CORRECT
    assert loaded.snapshot.model_dump(mode="json") == original_snapshot
    assert loaded.outcomes[0].label == XauForwardOutcomeLabel.NO_TRADE_WAS_CORRECT
