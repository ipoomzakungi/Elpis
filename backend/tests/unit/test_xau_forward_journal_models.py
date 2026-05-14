from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.models.xau_forward_journal import (
    XAU_FORWARD_JOURNAL_FORWARD_ONLY_LIMITATION,
    XAU_FORWARD_JOURNAL_RESEARCH_ONLY_WARNING,
    XauForwardArtifactFormat,
    XauForwardArtifactType,
    XauForwardJournalArtifact,
    XauForwardJournalCreateRequest,
    XauForwardJournalEntry,
    XauForwardJournalEntryStatus,
    XauForwardJournalNote,
    XauForwardJournalSourceType,
    XauForwardJournalSummary,
    XauForwardMissingContextItem,
    XauForwardOutcomeLabel,
    XauForwardOutcomeObservation,
    XauForwardOutcomeStatus,
    XauForwardOutcomeUpdateRequest,
    XauForwardOutcomeWindow,
    XauForwardPriceCoverageRequest,
    XauForwardPriceCoverageStatus,
    XauForwardPriceDataUpdateRequest,
    XauForwardPriceDirection,
    XauForwardPriceSourceLabel,
    XauForwardReactionSummary,
    XauForwardSnapshotContext,
    XauForwardSourceReportRef,
    XauForwardWallSummary,
    validate_xau_forward_journal_safe_id,
)


def _snapshot() -> XauForwardSnapshotContext:
    return XauForwardSnapshotContext(
        snapshot_time=datetime(2026, 5, 14, 3, 8, 4),
        capture_session="quikstrike_gold_am",
        product="Gold (OG|GC)",
        expiration_code="G2RK6",
        missing_context=["spot_price_at_snapshot", "spot_price_at_snapshot"],
    )


def _source_ref() -> XauForwardSourceReportRef:
    return XauForwardSourceReportRef(
        source_type=XauForwardJournalSourceType.XAU_QUIKSTRIKE_FUSION,
        report_id="fusion_report",
        status="partial",
        product="Gold (OG|GC)",
        row_count=365,
        warnings=["Basis unavailable.", "Basis unavailable."],
        limitations=["Local-only research artifact."],
    )


def test_forward_journal_enums_are_research_terms():
    assert XauForwardJournalSourceType.QUIKSTRIKE_VOL2VOL == "quikstrike_vol2vol"
    assert XauForwardJournalSourceType.XAU_REACTION == "xau_reaction"
    assert XauForwardJournalEntryStatus.PARTIAL == "partial"
    assert XauForwardOutcomeWindow.THIRTY_MINUTES == "30m"
    assert XauForwardOutcomeLabel.NO_TRADE_WAS_CORRECT == "no_trade_was_correct"
    assert XauForwardOutcomeStatus.PENDING == "pending"
    assert XauForwardArtifactType.REPORT_MARKDOWN == "report_markdown"
    assert XauForwardArtifactType.PRICE_COVERAGE_JSON == "price_coverage_json"
    assert XauForwardPriceSourceLabel.YAHOO_GC_F_PROXY == "yahoo_gc_f_proxy"
    assert XauForwardPriceCoverageStatus.PARTIAL == "partial"
    assert XauForwardPriceDirection.DOWN_FROM_SNAPSHOT == "down_from_snapshot"


def test_safe_ids_reject_path_traversal_spaces_and_empty_values():
    assert validate_xau_forward_journal_safe_id("journal_20260514") == "journal_20260514"

    for value in ("", "../outside", "nested/id", "bad id"):
        with pytest.raises(ValueError):
            validate_xau_forward_journal_safe_id(value)


def test_create_request_requires_safe_ids_and_research_acknowledgement():
    request = XauForwardJournalCreateRequest(
        snapshot_time="2026-05-14T03:08:04Z",
        capture_session="quikstrike_gold_am",
        vol2vol_report_id="vol2vol_report",
        matrix_report_id="matrix_report",
        fusion_report_id="fusion_report",
        xau_vol_oi_report_id="xau_vol_oi_report",
        xau_reaction_report_id="xau_reaction_report",
        futures_price_at_snapshot=4707.2,
        notes=[{"text": "Forward evidence snapshot from local reports."}],
        research_only_acknowledged=True,
    )

    assert request.snapshot_time.tzinfo is not None
    assert request.capture_session == "quikstrike_gold_am"
    assert request.persist_report is True
    assert request.notes[0].text == "Forward evidence snapshot from local reports."

    with pytest.raises(ValidationError, match="research_only_acknowledged"):
        XauForwardJournalCreateRequest(
            snapshot_time="2026-05-14T03:08:04Z",
            capture_session="quikstrike_gold_am",
            vol2vol_report_id="vol2vol_report",
            matrix_report_id="matrix_report",
            fusion_report_id="fusion_report",
            xau_vol_oi_report_id="xau_vol_oi_report",
            xau_reaction_report_id="xau_reaction_report",
            research_only_acknowledged=False,
        )

    with pytest.raises(ValidationError):
        XauForwardJournalCreateRequest(
            snapshot_time="2026-05-14T03:08:04Z",
            capture_session="bad/session",
            vol2vol_report_id="vol2vol_report",
            matrix_report_id="matrix_report",
            fusion_report_id="fusion_report",
            xau_vol_oi_report_id="xau_vol_oi_report",
            xau_reaction_report_id="xau_reaction_report",
            research_only_acknowledged=True,
        )


def test_models_reject_extra_secret_session_and_claim_values():
    with pytest.raises(ValidationError):
        XauForwardSourceReportRef(
            source_type=XauForwardJournalSourceType.XAU_VOL_OI,
            report_id="xau_report",
            unexpected="value",
        )

    with pytest.raises(ValidationError, match="sensitive/session"):
        XauForwardSourceReportRef(
            source_type=XauForwardJournalSourceType.XAU_VOL_OI,
            report_id="xau_report",
            headers={"Cookie": "not allowed"},
        )

    with pytest.raises(ValidationError, match="sensitive/session"):
        XauForwardJournalNote(text="Bearer secret-token")

    with pytest.raises(ValidationError, match="unsupported claim"):
        XauForwardJournalNote(text="This snapshot is profitable.")


def test_source_ref_normalizes_warnings_and_rejects_unsafe_artifact_paths():
    source = _source_ref()

    assert source.warnings == ["Basis unavailable."]
    assert source.limitations == ["Local-only research artifact."]

    disclaimer = XauForwardSourceReportRef(
        source_type=XauForwardJournalSourceType.XAU_VOL_OI,
        report_id="xau_report",
        warnings=[
            (
                "XAU Vol-OI outputs are research annotations only and do not imply "
                "profitability, predictive power, safety, or live readiness."
            )
        ],
    )
    assert disclaimer.warnings == [
        (
            "XAU Vol-OI outputs are research annotations only and do not imply "
            "profitability, predictive power, safety, or live readiness."
        )
    ]

    with pytest.raises(ValidationError, match="parent traversal"):
        XauForwardSourceReportRef(
            source_type=XauForwardJournalSourceType.XAU_REACTION,
            report_id="reaction_report",
            artifact_paths=["data/reports/../secrets.json"],
        )


def test_snapshot_context_and_wall_reaction_summaries_validate_core_rules():
    snapshot = _snapshot()
    wall = XauForwardWallSummary(
        summary_id="wall_1",
        wall_type="open_interest",
        source_report_id="xau_report",
        strike=4700.0,
        expiration_code="G2RK6",
        option_type="call",
        open_interest=120.0,
        rank=1,
    )
    reaction = XauForwardReactionSummary(
        reaction_id="reaction_1",
        source_report_id="reaction_report",
        wall_id="wall_1",
        reaction_label="NO_TRADE",
        no_trade_reasons=["Basis unavailable.", "Basis unavailable."],
    )
    missing = XauForwardMissingContextItem(
        context_key="basis",
        status="unavailable",
        message="Basis inputs were not provided.",
        source_report_ids=["fusion_report"],
    )

    assert snapshot.snapshot_time.tzinfo is not None
    assert snapshot.missing_context == ["spot_price_at_snapshot"]
    assert wall.open_interest == 120.0
    assert reaction.no_trade_reasons == ["Basis unavailable."]
    assert missing.blocks_outcome_label is False

    with pytest.raises(ValidationError, match="at least one value"):
        XauForwardWallSummary(
            summary_id="wall_2",
            wall_type="open_interest",
            source_report_id="xau_report",
            strike=4700.0,
            rank=1,
        )


def test_outcome_observation_schema_defaults_to_pending_without_label_logic():
    outcome = XauForwardOutcomeObservation(
        window=XauForwardOutcomeWindow.THIRTY_MINUTES,
        observation_start="2026-05-14T03:08:04Z",
        observation_end="2026-05-14T03:38:04Z",
        open=4707.2,
        high=4712.0,
        low=4701.5,
        close=4706.0,
    )
    update = XauForwardOutcomeUpdateRequest(
        outcomes=[outcome],
        update_note="Attach first observation.",
        research_only_acknowledged=True,
    )

    assert outcome.status == XauForwardOutcomeStatus.PENDING
    assert outcome.label == XauForwardOutcomeLabel.PENDING
    assert update.outcomes[0].window == XauForwardOutcomeWindow.THIRTY_MINUTES

    with pytest.raises(ValidationError, match="observation_end"):
        XauForwardOutcomeObservation(
            window=XauForwardOutcomeWindow.ONE_HOUR,
            observation_start="2026-05-14T04:00:00Z",
            observation_end="2026-05-14T03:00:00Z",
        )

    with pytest.raises(ValidationError, match="high"):
        XauForwardOutcomeObservation(
            window=XauForwardOutcomeWindow.ONE_HOUR,
            open=4707.2,
            high=4700.0,
            low=4701.5,
            close=4706.0,
        )


def test_price_update_request_and_extended_outcome_fields_validate_research_guardrails():
    request = XauForwardPriceDataUpdateRequest(
        source_label=XauForwardPriceSourceLabel.YAHOO_GC_F_PROXY,
        source_symbol="GC=F",
        ohlc_path="data/raw/yahoo/gc=f_1m_ohlcv.parquet",
        update_note="Attach synthetic OHLC validation outcomes.",
        research_only_acknowledged=True,
    )
    coverage_request = XauForwardPriceCoverageRequest(
        source_label=XauForwardPriceSourceLabel.LOCAL_CSV,
        source_symbol="XAUUSD local fixture",
        ohlc_path="data/raw/xau/local_fixture.csv",
        research_only_acknowledged=True,
    )
    outcome = XauForwardOutcomeObservation(
        window=XauForwardOutcomeWindow.THIRTY_MINUTES,
        status=XauForwardOutcomeStatus.COMPLETED,
        label=XauForwardOutcomeLabel.STAYED_INSIDE_RANGE,
        observation_start="2026-05-14T03:08:04Z",
        observation_end="2026-05-14T03:38:04Z",
        open=4707.2,
        high=4712.0,
        low=4701.5,
        close=4706.0,
        range=10.5,
        direction=XauForwardPriceDirection.DOWN_FROM_SNAPSHOT,
        price_source_label=XauForwardPriceSourceLabel.YAHOO_GC_F_PROXY,
        price_source_symbol="GC=F",
        coverage_status=XauForwardPriceCoverageStatus.COMPLETE,
        price_update_id="price_update_fixture",
    )

    assert request.source_label == XauForwardPriceSourceLabel.YAHOO_GC_F_PROXY
    assert coverage_request.source_label == XauForwardPriceSourceLabel.LOCAL_CSV
    assert outcome.range == 10.5
    assert outcome.direction == XauForwardPriceDirection.DOWN_FROM_SNAPSHOT

    with pytest.raises(ValidationError, match="research_only_acknowledged"):
        XauForwardPriceDataUpdateRequest(
            source_label=XauForwardPriceSourceLabel.LOCAL_PARQUET,
            ohlc_path="data/raw/xau/local_fixture.parquet",
            research_only_acknowledged=False,
        )

    with pytest.raises(ValidationError, match="sensitive/session"):
        XauForwardPriceCoverageRequest(
            source_label=XauForwardPriceSourceLabel.LOCAL_CSV,
            ohlc_path="https://example.com/xau.csv",
            research_only_acknowledged=True,
        )

    with pytest.raises(ValidationError, match="parent traversal"):
        XauForwardPriceDataUpdateRequest(
            source_label=XauForwardPriceSourceLabel.LOCAL_CSV,
            ohlc_path="data/raw/../secret.csv",
            research_only_acknowledged=True,
        )


def test_entry_summary_and_artifact_models_validate_foundation_rules():
    artifact = XauForwardJournalArtifact(
        artifact_type=XauForwardArtifactType.REPORT_JSON,
        path="data/reports/xau_forward_journal/journal_report/report.json",
        format=XauForwardArtifactFormat.JSON,
        rows=1,
    )
    entry = XauForwardJournalEntry(
        journal_id="journal_report",
        snapshot_key="20260514_daily_snapshot_g2rk6_abcdef123456",
        status=XauForwardJournalEntryStatus.PARTIAL,
        snapshot=_snapshot(),
        source_reports=[_source_ref()],
        warnings=["Optional spot context unavailable."],
        artifacts=[artifact],
    )
    summary = XauForwardJournalSummary(
        journal_id="journal_report",
        snapshot_key="20260514_daily_snapshot_g2rk6_abcdef123456",
        status=XauForwardJournalEntryStatus.PARTIAL,
        snapshot_time=datetime(2026, 5, 14, tzinfo=UTC),
        capture_window="daily_snapshot",
        capture_session="quikstrike_gold_am",
        fusion_report_id="fusion_report",
        xau_vol_oi_report_id="xau_report",
        xau_reaction_report_id="reaction_report",
        pending_outcome_count=5,
        warning_count=1,
    )

    assert XAU_FORWARD_JOURNAL_FORWARD_ONLY_LIMITATION in entry.limitations
    assert XAU_FORWARD_JOURNAL_RESEARCH_ONLY_WARNING in entry.research_only_warnings
    assert artifact.path == "data/reports/xau_forward_journal/journal_report/report.json"
    assert summary.pending_outcome_count == 5

    with pytest.raises(ValidationError, match="xau_forward_journal"):
        XauForwardJournalArtifact(
            artifact_type=XauForwardArtifactType.REPORT_JSON,
            path="data/reports/xau_quikstrike_fusion/journal_report/report.json",
            format=XauForwardArtifactFormat.JSON,
        )

    with pytest.raises(ValidationError, match="blocked journal entry"):
        XauForwardJournalEntry(
            journal_id="journal_blocked",
            snapshot_key="20260514_daily_snapshot_g2rk6_blocked",
            status=XauForwardJournalEntryStatus.BLOCKED,
            snapshot=_snapshot(),
            source_reports=[],
        )
