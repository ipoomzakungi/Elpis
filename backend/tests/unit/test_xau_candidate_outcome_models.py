from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.models.xau_candidate_outcome import (
    XauCandidateOutcome,
    XauCandidateOutcomeCoverageStatus,
    XauCandidateOutcomeLabel,
    XauCandidateOutcomeRunRequest,
    XauCandidateOutcomeSet,
    XauCandidateOutcomeWindow,
    XauCandidatePriceSeriesSource,
    XauCandidatePriceSourceKind,
)


def test_outcome_models_keep_signal_disabled() -> None:
    with pytest.raises(ValidationError):
        XauCandidateOutcome(
            candidate_id="candidate_1",
            map_id="map_1",
            session_date=date(2026, 6, 2),
            window=XauCandidateOutcomeWindow.THIRTY_MINUTES,
            outcome_label=XauCandidateOutcomeLabel.UNRESOLVED,
            price_source="fixture",
            coverage_status=XauCandidateOutcomeCoverageStatus.COMPLETE,
            signal_allowed=True,
        )


def test_run_request_rejects_remote_paths() -> None:
    with pytest.raises(ValidationError):
        XauCandidateOutcomeRunRequest(
            candidate_set_path="https://example.com/candidates.json",
            price_bars_path=Path("bars.csv"),
            research_only_acknowledged=True,
        )


def test_outcome_set_validates_counts() -> None:
    source = XauCandidatePriceSeriesSource(
        source_kind=XauCandidatePriceSourceKind.STATIC_FIXTURE,
        source_path="fixture",
        row_count=0,
    )

    with pytest.raises(ValidationError):
        XauCandidateOutcomeSet(
            outcome_run_id="outcome_run",
            map_id="map_1",
            candidate_set_id="candidate_set_1",
            session_date=date(2026, 6, 2),
            windows=[XauCandidateOutcomeWindow.THIRTY_MINUTES],
            candidate_count=1,
            outcome_count=2,
            unavailable_count=0,
            price_source=source,
            outcomes=[],
        )


def test_price_source_timestamps_are_normalized_to_utc() -> None:
    source = XauCandidatePriceSeriesSource(
        source_kind=XauCandidatePriceSourceKind.STATIC_FIXTURE,
        source_path="fixture",
        row_count=1,
        first_timestamp=datetime(2026, 6, 2, 12, 0),
    )

    assert source.first_timestamp == datetime(2026, 6, 2, 12, 0, tzinfo=UTC)
