from datetime import UTC, datetime
from typing import Any

from src.models.xau_forward_journal import (
    XauForwardJournalEntryStatus,
    XauForwardJournalSourceType,
    XauForwardOutcomeStatus,
    XauForwardOutcomeWindow,
)


def synthetic_forward_journal_create_payload() -> dict[str, Any]:
    return {
        "snapshot_time": "2026-05-14T03:08:04Z",
        "capture_session": "quikstrike-gold-am-session",
        "vol2vol_report_id": "quikstrike_20260513_101537",
        "matrix_report_id": "quikstrike_matrix_20260513_155058",
        "fusion_report_id": "xau_quikstrike_fusion_20260514_030803",
        "xau_vol_oi_report_id": "xau_vol_oi_20260514_030804",
        "xau_reaction_report_id": "xau_reaction_20260514_030804",
        "futures_price_at_snapshot": 4707.2,
        "event_news_flag": "none_known",
        "notes": ["Synthetic local-only forward evidence snapshot."],
        "persist_report": True,
        "research_only_acknowledged": True,
    }


def synthetic_source_report_ref(
    source_type: XauForwardJournalSourceType,
    report_id: str,
) -> dict[str, Any]:
    return {
        "source_type": source_type.value,
        "report_id": report_id,
        "status": "available",
        "created_at": datetime(2026, 5, 14, 3, 8, 4, tzinfo=UTC).isoformat(),
        "product": "Gold (OG|GC)",
        "expiration_code": "G2RK6",
        "row_count": 10,
        "warnings": ["Synthetic source report for tests."],
        "limitations": ["Local-only research fixture."],
        "artifact_paths": [],
    }


def synthetic_forward_journal_summary_payload() -> dict[str, Any]:
    return {
        "journal_id": "journal_report",
        "status": XauForwardJournalEntryStatus.PARTIAL.value,
        "snapshot_time": "2026-05-14T03:08:04Z",
        "capture_session": "quikstrike-gold-am-session",
        "product": "Gold (OG|GC)",
        "expiration_code": "G2RK6",
        "fusion_report_id": "xau_quikstrike_fusion_20260514_030803",
        "xau_vol_oi_report_id": "xau_vol_oi_20260514_030804",
        "xau_reaction_report_id": "xau_reaction_20260514_030804",
        "outcome_status": XauForwardOutcomeStatus.PENDING.value,
        "pending_outcome_count": 5,
        "warning_count": 1,
    }


def synthetic_outcome_update_payload() -> dict[str, Any]:
    return {
        "outcomes": [
            {
                "window": XauForwardOutcomeWindow.THIRTY_MINUTES.value,
                "status": XauForwardOutcomeStatus.PENDING.value,
                "label": "pending",
                "notes": ["Synthetic outcome data has not been attached."],
            }
        ],
        "update_note": "Synthetic outcome placeholder.",
        "research_only_acknowledged": True,
    }

