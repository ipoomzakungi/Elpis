from __future__ import annotations

from datetime import UTC, datetime

from src.models.xau_forward_journal import (
    XauForwardJournalEntry,
    XauForwardJournalNote,
    XauForwardOutcomeLabel,
    XauForwardOutcomeObservation,
    XauForwardOutcomeStatus,
    XauForwardOutcomeUpdateRequest,
    XauForwardOutcomeWindow,
)

SUPPORTED_OUTCOME_WINDOWS = (
    XauForwardOutcomeWindow.THIRTY_MINUTES,
    XauForwardOutcomeWindow.ONE_HOUR,
    XauForwardOutcomeWindow.FOUR_HOURS,
    XauForwardOutcomeWindow.SESSION_CLOSE,
    XauForwardOutcomeWindow.NEXT_DAY,
)

COMPLETED_OUTCOME_LABELS = {
    XauForwardOutcomeLabel.WALL_HELD,
    XauForwardOutcomeLabel.WALL_REJECTED,
    XauForwardOutcomeLabel.WALL_ACCEPTED_BREAK,
    XauForwardOutcomeLabel.MOVED_TO_NEXT_WALL,
    XauForwardOutcomeLabel.REVERSED_BEFORE_TARGET,
    XauForwardOutcomeLabel.STAYED_INSIDE_RANGE,
    XauForwardOutcomeLabel.NO_TRADE_WAS_CORRECT,
}

OUTCOME_RESEARCH_LIMITATION = "Outcome labels are forward research annotations only."


class XauForwardOutcomeUpdateError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "INVALID_OUTCOME_UPDATE",
        details: list[dict[str, str]] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or []


class XauForwardOutcomeConflictError(XauForwardOutcomeUpdateError):
    def __init__(self, window: XauForwardOutcomeWindow) -> None:
        super().__init__(
            "Existing non-pending outcome label requires an explicit update note",
            code="OUTCOME_CONFLICT",
            details=[
                {"field": "outcomes.window", "message": window.value},
                {
                    "field": "update_note",
                    "message": "Provide an update note explaining why the label changed",
                },
            ],
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
        for window in SUPPORTED_OUTCOME_WINDOWS
    ]


def normalize_outcome_observation(
    outcome: XauForwardOutcomeObservation,
) -> XauForwardOutcomeObservation:
    """Apply conservative status rules without inventing missing candle values."""

    if outcome.window not in SUPPORTED_OUTCOME_WINDOWS:
        raise XauForwardOutcomeUpdateError(
            "Unsupported outcome window",
            details=[{"field": "outcomes.window", "message": outcome.window.value}],
        )

    limitations = list(outcome.limitations)
    status = outcome.status
    label = outcome.label

    if label == XauForwardOutcomeLabel.PENDING:
        status = XauForwardOutcomeStatus.PENDING
    elif label == XauForwardOutcomeLabel.INCONCLUSIVE:
        status = XauForwardOutcomeStatus.INCONCLUSIVE
    elif label in COMPLETED_OUTCOME_LABELS:
        if not _has_any_ohlc(outcome):
            label = XauForwardOutcomeLabel.INCONCLUSIVE
            status = XauForwardOutcomeStatus.INCONCLUSIVE
            limitations.append(
                "Outcome OHLC data is missing; completed label was kept inconclusive."
            )
        elif not _has_full_ohlc(outcome):
            label = XauForwardOutcomeLabel.INCONCLUSIVE
            status = XauForwardOutcomeStatus.INCONCLUSIVE
            limitations.append(
                "Outcome OHLC data is partial; completed label was kept inconclusive."
            )
        elif outcome.observation_start is None or outcome.observation_end is None:
            label = XauForwardOutcomeLabel.INCONCLUSIVE
            status = XauForwardOutcomeStatus.INCONCLUSIVE
            limitations.append(
                "Outcome observation timestamps are missing; completed label was kept inconclusive."
            )
        else:
            status = XauForwardOutcomeStatus.COMPLETED
    else:
        raise XauForwardOutcomeUpdateError(
            "Unsupported outcome label",
            details=[{"field": "outcomes.label", "message": label.value}],
        )

    return outcome.model_copy(
        update={
            "status": status,
            "label": label,
            "limitations": _dedupe([*limitations, OUTCOME_RESEARCH_LIMITATION]),
            "updated_at": datetime.now(UTC),
        }
    )


def apply_outcome_update(
    entry: XauForwardJournalEntry,
    request: XauForwardOutcomeUpdateRequest,
) -> XauForwardJournalEntry:
    """Return a new entry with updated outcomes while preserving snapshot fields."""

    existing_by_window = {outcome.window: outcome for outcome in entry.outcomes}
    updated_by_window = dict(existing_by_window)
    seen_windows: set[XauForwardOutcomeWindow] = set()

    for requested in request.outcomes:
        if requested.window in seen_windows:
            raise XauForwardOutcomeUpdateError(
                "Outcome update includes the same window more than once",
                details=[{"field": "outcomes.window", "message": requested.window.value}],
            )
        seen_windows.add(requested.window)

        normalized = normalize_outcome_observation(requested)
        existing = existing_by_window.get(requested.window)
        if (
            existing is not None
            and _is_non_pending(existing)
            and _outcome_label_or_status_changed(existing, normalized)
            and request.update_note is None
        ):
            raise XauForwardOutcomeConflictError(requested.window)

        if request.update_note is not None:
            normalized = normalized.model_copy(
                update={
                    "notes": [
                        *normalized.notes,
                        XauForwardJournalNote(
                            text=request.update_note,
                            source="outcome_update",
                        ),
                    ]
                }
            )
        updated_by_window[requested.window] = normalized

    ordered_outcomes = [
        updated_by_window.get(window)
        or XauForwardOutcomeObservation(
            window=window,
            status=XauForwardOutcomeStatus.PENDING,
            label=XauForwardOutcomeLabel.PENDING,
        )
        for window in SUPPORTED_OUTCOME_WINDOWS
    ]

    return entry.model_copy(
        update={
            "outcomes": ordered_outcomes,
            "updated_at": datetime.now(UTC),
        }
    )


def _has_any_ohlc(outcome: XauForwardOutcomeObservation) -> bool:
    return any(
        value is not None
        for value in (outcome.open, outcome.high, outcome.low, outcome.close)
    )


def _has_full_ohlc(outcome: XauForwardOutcomeObservation) -> bool:
    return None not in (outcome.open, outcome.high, outcome.low, outcome.close)


def _is_non_pending(outcome: XauForwardOutcomeObservation) -> bool:
    return (
        outcome.status != XauForwardOutcomeStatus.PENDING
        or outcome.label != XauForwardOutcomeLabel.PENDING
    )


def _outcome_label_or_status_changed(
    existing: XauForwardOutcomeObservation,
    requested: XauForwardOutcomeObservation,
) -> bool:
    return existing.label != requested.label or existing.status != requested.status


def _dedupe(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = value.strip()
        if cleaned and cleaned not in seen:
            deduped.append(cleaned)
            seen.add(cleaned)
    return deduped
