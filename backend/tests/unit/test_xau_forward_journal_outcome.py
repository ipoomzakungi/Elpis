from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.models.xau_forward_journal import (
    XauForwardJournalCreateRequest,
    XauForwardOutcomeLabel,
    XauForwardOutcomeObservation,
    XauForwardOutcomeStatus,
    XauForwardOutcomeUpdateRequest,
    XauForwardOutcomeWindow,
)
from src.xau_forward_journal.entry_builder import build_journal_entry
from src.xau_forward_journal.outcome import (
    XauForwardOutcomeConflictError,
    apply_outcome_update,
    create_default_pending_outcomes,
    normalize_outcome_observation,
)
from tests.helpers.test_xau_forward_journal_data import (
    synthetic_forward_journal_create_payload,
    write_synthetic_source_reports,
)


def _entry(tmp_path: Path):
    reports_dir = tmp_path / "data" / "reports"
    write_synthetic_source_reports(reports_dir)
    request = XauForwardJournalCreateRequest.model_validate(
        synthetic_forward_journal_create_payload()
    )
    return build_journal_entry(request, reports_dir=reports_dir)


def _full_observation(
    label: XauForwardOutcomeLabel,
    *,
    window: XauForwardOutcomeWindow = XauForwardOutcomeWindow.THIRTY_MINUTES,
) -> XauForwardOutcomeObservation:
    return XauForwardOutcomeObservation(
        window=window,
        label=label,
        observation_start=datetime(2026, 5, 14, 3, 8, 4, tzinfo=UTC),
        observation_end=datetime(2026, 5, 14, 3, 38, 4, tzinfo=UTC),
        open=4707.2,
        high=4712.0,
        low=4701.5,
        close=4706.0,
        reference_wall_id="wall_1",
        reference_wall_level=4675.0,
        notes=["Synthetic outcome observation."],
    )


def test_default_pending_outcomes_cover_supported_windows():
    outcomes = create_default_pending_outcomes()

    assert [outcome.window for outcome in outcomes] == [
        XauForwardOutcomeWindow.THIRTY_MINUTES,
        XauForwardOutcomeWindow.ONE_HOUR,
        XauForwardOutcomeWindow.FOUR_HOURS,
        XauForwardOutcomeWindow.SESSION_CLOSE,
        XauForwardOutcomeWindow.NEXT_DAY,
    ]
    assert all(outcome.status == XauForwardOutcomeStatus.PENDING for outcome in outcomes)
    assert all(outcome.label == XauForwardOutcomeLabel.PENDING for outcome in outcomes)


def test_outcome_window_validation_rejects_bad_timestamps_and_ohlc_consistency():
    with pytest.raises(ValidationError, match="observation_end"):
        XauForwardOutcomeObservation(
            window=XauForwardOutcomeWindow.ONE_HOUR,
            observation_start="2026-05-14T04:00:00Z",
            observation_end="2026-05-14T03:00:00Z",
        )

    with pytest.raises(ValidationError, match="high"):
        XauForwardOutcomeObservation(
            window=XauForwardOutcomeWindow.FOUR_HOURS,
            open=4707.2,
            high=4700.0,
            low=4701.5,
            close=4706.0,
        )


@pytest.mark.parametrize(
    ("label", "expected_status"),
    [
        (XauForwardOutcomeLabel.PENDING, XauForwardOutcomeStatus.PENDING),
        (XauForwardOutcomeLabel.INCONCLUSIVE, XauForwardOutcomeStatus.INCONCLUSIVE),
        (XauForwardOutcomeLabel.WALL_HELD, XauForwardOutcomeStatus.COMPLETED),
        (XauForwardOutcomeLabel.WALL_REJECTED, XauForwardOutcomeStatus.COMPLETED),
        (XauForwardOutcomeLabel.WALL_ACCEPTED_BREAK, XauForwardOutcomeStatus.COMPLETED),
        (XauForwardOutcomeLabel.MOVED_TO_NEXT_WALL, XauForwardOutcomeStatus.COMPLETED),
        (XauForwardOutcomeLabel.REVERSED_BEFORE_TARGET, XauForwardOutcomeStatus.COMPLETED),
        (XauForwardOutcomeLabel.STAYED_INSIDE_RANGE, XauForwardOutcomeStatus.COMPLETED),
        (XauForwardOutcomeLabel.NO_TRADE_WAS_CORRECT, XauForwardOutcomeStatus.COMPLETED),
    ],
)
def test_outcome_label_rules_are_conservative(label, expected_status):
    outcome = normalize_outcome_observation(_full_observation(label))

    assert outcome.label == label
    assert outcome.status == expected_status


def test_missing_ohlc_keeps_requested_completed_label_inconclusive_without_fabrication():
    outcome = normalize_outcome_observation(
        XauForwardOutcomeObservation(
            window=XauForwardOutcomeWindow.THIRTY_MINUTES,
            label=XauForwardOutcomeLabel.WALL_HELD,
            notes=["Synthetic missing candle example."],
        )
    )

    assert outcome.status == XauForwardOutcomeStatus.INCONCLUSIVE
    assert outcome.label == XauForwardOutcomeLabel.INCONCLUSIVE
    assert outcome.open is None
    assert outcome.high is None
    assert outcome.low is None
    assert outcome.close is None
    assert any("missing" in limitation.lower() for limitation in outcome.limitations)


def test_partial_ohlc_is_inconclusive_and_does_not_fill_missing_prices():
    outcome = normalize_outcome_observation(
        XauForwardOutcomeObservation(
            window=XauForwardOutcomeWindow.ONE_HOUR,
            label=XauForwardOutcomeLabel.WALL_REJECTED,
            observation_start="2026-05-14T03:08:04Z",
            observation_end="2026-05-14T04:08:04Z",
            open=4707.2,
            high=4712.0,
        )
    )

    assert outcome.status == XauForwardOutcomeStatus.INCONCLUSIVE
    assert outcome.label == XauForwardOutcomeLabel.INCONCLUSIVE
    assert outcome.open == 4707.2
    assert outcome.high == 4712.0
    assert outcome.low is None
    assert outcome.close is None
    assert any("partial" in limitation.lower() for limitation in outcome.limitations)


def test_conflicting_non_pending_label_update_requires_update_note(tmp_path: Path):
    entry = _entry(tmp_path)
    first_request = XauForwardOutcomeUpdateRequest(
        outcomes=[_full_observation(XauForwardOutcomeLabel.WALL_HELD)],
        research_only_acknowledged=True,
    )
    updated = apply_outcome_update(entry, first_request)

    with pytest.raises(XauForwardOutcomeConflictError) as exc:
        apply_outcome_update(
            updated,
            XauForwardOutcomeUpdateRequest(
                outcomes=[_full_observation(XauForwardOutcomeLabel.WALL_REJECTED)],
                research_only_acknowledged=True,
            ),
        )

    assert exc.value.code == "OUTCOME_CONFLICT"
    assert any(detail["field"] == "update_note" for detail in exc.value.details)

    resolved = apply_outcome_update(
        updated,
        XauForwardOutcomeUpdateRequest(
            outcomes=[_full_observation(XauForwardOutcomeLabel.WALL_REJECTED)],
            update_note="Correct the synthetic review label after candle inspection.",
            research_only_acknowledged=True,
        ),
    )

    assert resolved.outcomes[0].label == XauForwardOutcomeLabel.WALL_REJECTED
    assert resolved.outcomes[0].status == XauForwardOutcomeStatus.COMPLETED


def test_outcome_update_does_not_mutate_original_snapshot_fields(tmp_path: Path):
    entry = _entry(tmp_path)
    original_snapshot = entry.snapshot.model_dump(mode="json")

    updated = apply_outcome_update(
        entry,
        XauForwardOutcomeUpdateRequest(
            outcomes=[_full_observation(XauForwardOutcomeLabel.STAYED_INSIDE_RANGE)],
            update_note="Attach synthetic outcome observation.",
            research_only_acknowledged=True,
        ),
    )

    assert entry.snapshot.model_dump(mode="json") == original_snapshot
    assert updated.snapshot.model_dump(mode="json") == original_snapshot
    assert updated.outcomes[0].label == XauForwardOutcomeLabel.STAYED_INSIDE_RANGE
