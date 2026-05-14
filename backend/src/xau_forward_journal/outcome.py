from __future__ import annotations

from src.models.xau_forward_journal import (
    XauForwardJournalNote,
    XauForwardOutcomeLabel,
    XauForwardOutcomeObservation,
    XauForwardOutcomeStatus,
    XauForwardOutcomeWindow,
)


def create_default_pending_outcomes() -> list[XauForwardOutcomeObservation]:
    """Create deterministic pending outcome windows without assigning labels."""

    return [
        XauForwardOutcomeObservation(
            window=window,
            status=XauForwardOutcomeStatus.PENDING,
            label=XauForwardOutcomeLabel.PENDING,
            notes=[
                XauForwardJournalNote(
                    text="Outcome data has not been attached.",
                    source="system",
                )
            ],
        )
        for window in (
            XauForwardOutcomeWindow.THIRTY_MINUTES,
            XauForwardOutcomeWindow.ONE_HOUR,
            XauForwardOutcomeWindow.FOUR_HOURS,
            XauForwardOutcomeWindow.SESSION_CLOSE,
            XauForwardOutcomeWindow.NEXT_DAY,
        )
    ]
