from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from src.models.xau_forward_journal import (
    XauForwardJournalCreateRequest,
    XauForwardJournalEntry,
    XauForwardJournalSourceType,
    XauForwardOutcomeLabel,
    XauForwardOutcomeResponse,
    XauForwardOutcomeStatus,
    XauForwardOutcomeUpdateRequest,
    XauForwardPriceCoverageRequest,
    XauForwardPriceCoverageResponse,
    XauForwardPriceDataUpdateRequest,
    XauForwardPriceOutcomeUpdateReport,
    XauForwardPriceOutcomeUpdateResponse,
)
from src.xau_forward_journal.content_fingerprint import build_snapshot_content_fingerprint
from src.xau_forward_journal.entry_builder import (
    XauForwardJournalBuildError,
    build_journal_entry_from_loaded,
    load_source_reports,
)
from src.xau_forward_journal.outcome import apply_outcome_update
from src.xau_forward_journal.price_data import load_price_candles
from src.xau_forward_journal.price_outcome import (
    OUTCOME_PRICE_UPDATE_LIMITATION,
    build_price_coverage_summary,
    build_price_outcome_observations,
)
from src.xau_forward_journal.report_store import XauForwardJournalReportStore


class XauForwardJournalConflictError(XauForwardJournalBuildError):
    def __init__(self, journal_id: str, snapshot_key: str) -> None:
        super().__init__(
            "A journal entry with this snapshot key already has non-pending outcomes",
            code="JOURNAL_ENTRY_CONFLICT",
            details=[
                {"field": "journal_id", "message": journal_id},
                {"field": "snapshot_key", "message": snapshot_key},
                {
                    "field": "resolution",
                    "message": (
                        "Create revision behavior is not implemented in this slice, "
                        "and immutable snapshots with completed outcomes are not overwritten."
                    ),
                },
            ],
        )


@dataclass(frozen=True)
class XauForwardJournalCreateResult:
    status: str
    entry: XauForwardJournalEntry
    content_fingerprint: str | None = None
    previous_journal_id: str | None = None


def create_xau_forward_journal_entry(
    request: XauForwardJournalCreateRequest,
    *,
    report_store: XauForwardJournalReportStore | None = None,
    reports_dir: Path | None = None,
) -> XauForwardJournalEntry:
    return create_xau_forward_journal_entry_result(
        request,
        report_store=report_store,
        reports_dir=reports_dir,
    ).entry


def create_xau_forward_journal_entry_result(
    request: XauForwardJournalCreateRequest,
    *,
    report_store: XauForwardJournalReportStore | None = None,
    reports_dir: Path | None = None,
) -> XauForwardJournalCreateResult:
    store = report_store or XauForwardJournalReportStore(reports_dir=reports_dir)
    loaded = load_source_reports(request, reports_dir=reports_dir or store.reports_dir)
    entry = build_journal_entry_from_loaded(loaded)
    fingerprint = build_snapshot_content_fingerprint(loaded)
    entry = entry.model_copy(
        update={
            "content_fingerprint": fingerprint.fingerprint,
            "content_fingerprint_components": fingerprint.component_fingerprints,
        }
    )

    if not request.force_create:
        duplicate = _find_latest_duplicate_content_entry(store, entry, fingerprint.fingerprint)
        if duplicate is not None:
            return XauForwardJournalCreateResult(
                status="duplicate_content",
                entry=duplicate,
                content_fingerprint=fingerprint.fingerprint,
                previous_journal_id=duplicate.journal_id,
            )

    existing = store.find_entry_by_snapshot_key(entry.snapshot_key)
    if existing is not None:
        if _all_outcomes_pending(existing):
            return XauForwardJournalCreateResult(
                status="existing_snapshot",
                entry=existing,
                content_fingerprint=existing.content_fingerprint or fingerprint.fingerprint,
                previous_journal_id=existing.journal_id,
            )
        raise XauForwardJournalConflictError(existing.journal_id, existing.snapshot_key)

    if not request.persist_report:
        return XauForwardJournalCreateResult(
            status="built",
            entry=entry,
            content_fingerprint=fingerprint.fingerprint,
        )
    persisted = store.persist_entry(entry)
    return XauForwardJournalCreateResult(
        status="created",
        entry=persisted,
        content_fingerprint=fingerprint.fingerprint,
    )


def update_xau_forward_journal_outcomes(
    journal_id: str,
    request: XauForwardOutcomeUpdateRequest,
    *,
    report_store: XauForwardJournalReportStore | None = None,
    reports_dir: Path | None = None,
) -> XauForwardOutcomeResponse:
    store = report_store or XauForwardJournalReportStore(reports_dir=reports_dir)
    entry = store.read_entry(journal_id)
    updated_entry = apply_outcome_update(entry, request)
    persisted_entry = store.persist_outcome_update(updated_entry)
    return store.read_outcome_response(persisted_entry.journal_id)


def get_xau_forward_journal_outcomes(
    journal_id: str,
    *,
    report_store: XauForwardJournalReportStore | None = None,
    reports_dir: Path | None = None,
) -> XauForwardOutcomeResponse:
    store = report_store or XauForwardJournalReportStore(reports_dir=reports_dir)
    return store.read_outcome_response(journal_id)


def get_xau_forward_journal_price_coverage(
    journal_id: str,
    request: XauForwardPriceCoverageRequest,
    *,
    report_store: XauForwardJournalReportStore | None = None,
    reports_dir: Path | None = None,
) -> XauForwardPriceCoverageResponse:
    store = report_store or XauForwardJournalReportStore(reports_dir=reports_dir)
    entry = store.read_entry(journal_id)
    candles, source = load_price_candles(request, base_dir=store.repo_root)
    coverage = build_price_coverage_summary(entry, candles, source)
    return XauForwardPriceCoverageResponse(
        journal_id=entry.journal_id,
        coverage=coverage,
        warnings=coverage.warnings,
        limitations=["Coverage checks do not update journal outcomes.", *coverage.limitations],
    )


def update_xau_forward_journal_outcomes_from_price_data(
    journal_id: str,
    request: XauForwardPriceDataUpdateRequest,
    *,
    report_store: XauForwardJournalReportStore | None = None,
    reports_dir: Path | None = None,
) -> XauForwardPriceOutcomeUpdateResponse:
    store = report_store or XauForwardJournalReportStore(reports_dir=reports_dir)
    entry = store.read_entry(journal_id)
    candles, source = load_price_candles(request, base_dir=store.repo_root)
    coverage = build_price_coverage_summary(entry, candles, source)
    price_update_id = _price_update_id()
    price_outcomes = build_price_outcome_observations(
        entry,
        candles,
        coverage,
        price_update_id=price_update_id,
    )
    updated_entry = apply_outcome_update(
        entry,
        XauForwardOutcomeUpdateRequest(
            outcomes=price_outcomes,
            update_note=request.update_note,
            research_only_acknowledged=True,
        ),
    )
    report = XauForwardPriceOutcomeUpdateReport(
        update_id=price_update_id,
        journal_id=entry.journal_id,
        source=source,
        coverage_summary=coverage,
        updated_outcomes=price_outcomes,
        missing_candle_checklist=coverage.missing_candle_checklist,
        proxy_limitations=coverage.proxy_limitations,
        warnings=coverage.warnings,
        limitations=[OUTCOME_PRICE_UPDATE_LIMITATION, *coverage.limitations],
    )
    if request.persist_report:
        persisted_entry, report = store.persist_price_update_report(updated_entry, report)
    else:
        persisted_entry = store.persist_outcome_update(updated_entry)

    return XauForwardPriceOutcomeUpdateResponse(
        journal_id=persisted_entry.journal_id,
        update_report=report,
        outcomes=persisted_entry.outcomes,
        coverage=coverage,
        artifacts=report.artifacts,
        warnings=report.warnings,
        limitations=report.limitations,
    )


def _all_outcomes_pending(entry: XauForwardJournalEntry) -> bool:
    return all(
        outcome.status == XauForwardOutcomeStatus.PENDING
        and outcome.label == XauForwardOutcomeLabel.PENDING
        for outcome in entry.outcomes
    )


def _find_latest_duplicate_content_entry(
    store: XauForwardJournalReportStore,
    candidate: XauForwardJournalEntry,
    candidate_fingerprint: str,
) -> XauForwardJournalEntry | None:
    for summary in store.list_entries().entries:
        if summary.snapshot_key == candidate.snapshot_key:
            continue
        if not _same_capture_scope(summary, candidate):
            continue
        try:
            previous = store.read_entry(summary.journal_id)
            previous_fingerprint = previous.content_fingerprint or _compute_entry_fingerprint(
                previous,
                store,
            )
        except (OSError, ValueError):
            continue
        if previous_fingerprint == candidate_fingerprint:
            return previous
        return None
    return None


def _same_capture_scope(summary: object, candidate: XauForwardJournalEntry) -> bool:
    return (
        _normalized_text(getattr(summary, "capture_window", None))
        == _normalized_text(candidate.snapshot.capture_window)
        and _normalized_text(getattr(summary, "product", None))
        == _normalized_text(candidate.snapshot.product)
        and _expiration_token(
            getattr(summary, "expiration", None),
            getattr(summary, "expiration_code", None),
        )
        == _expiration_token(candidate.snapshot.expiration, candidate.snapshot.expiration_code)
    )


def _compute_entry_fingerprint(
    entry: XauForwardJournalEntry,
    store: XauForwardJournalReportStore,
) -> str:
    request = XauForwardJournalCreateRequest(
        snapshot_time=entry.snapshot.snapshot_time,
        capture_window=entry.snapshot.capture_window,
        capture_session=entry.snapshot.capture_session,
        vol2vol_report_id=_entry_source_report_id(
            entry,
            XauForwardJournalSourceType.QUIKSTRIKE_VOL2VOL,
        ),
        matrix_report_id=_entry_source_report_id(
            entry,
            XauForwardJournalSourceType.QUIKSTRIKE_MATRIX,
        ),
        fusion_report_id=_entry_source_report_id(
            entry,
            XauForwardJournalSourceType.XAU_QUIKSTRIKE_FUSION,
        ),
        xau_vol_oi_report_id=_entry_source_report_id(
            entry,
            XauForwardJournalSourceType.XAU_VOL_OI,
        ),
        xau_reaction_report_id=_entry_source_report_id(
            entry,
            XauForwardJournalSourceType.XAU_REACTION,
        ),
        spot_price_at_snapshot=entry.snapshot.spot_price_at_snapshot,
        futures_price_at_snapshot=entry.snapshot.futures_price_at_snapshot,
        basis=entry.snapshot.basis,
        session_open_price=entry.snapshot.session_open_price,
        event_news_flag=entry.snapshot.event_news_flag,
        force_create=True,
        research_only_acknowledged=True,
    )
    loaded = load_source_reports(request, reports_dir=store.reports_dir)
    return build_snapshot_content_fingerprint(loaded).fingerprint


def _entry_source_report_id(
    entry: XauForwardJournalEntry,
    source_type: XauForwardJournalSourceType,
) -> str:
    for ref in entry.source_reports:
        if ref.source_type == source_type:
            return ref.report_id
    raise ValueError(f"entry is missing source report {source_type.value}")


def _expiration_token(expiration: object, expiration_code: object) -> str:
    return _normalized_text(expiration_code) or _normalized_text(expiration)


def _normalized_text(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().lower().split())


def _price_update_id() -> str:
    return f"price_update_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S_%f')}"
