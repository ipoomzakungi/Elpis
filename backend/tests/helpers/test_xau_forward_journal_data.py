import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.models.xau_forward_journal import (
    XauForwardJournalEntryStatus,
    XauForwardJournalSourceType,
    XauForwardOutcomeStatus,
    XauForwardOutcomeWindow,
)

VOL2VOL_ID = "quikstrike_20260513_101537"
MATRIX_ID = "quikstrike_matrix_20260513_155058"
FUSION_ID = "xau_quikstrike_fusion_20260514_030803"
XAU_VOL_OI_ID = "xau_vol_oi_20260514_030804"
XAU_REACTION_ID = "xau_reaction_20260514_030804"


def synthetic_forward_journal_create_payload() -> dict[str, Any]:
    return {
        "snapshot_time": "2026-05-14T03:08:04Z",
        "capture_window": "daily_snapshot",
        "vol2vol_report_id": VOL2VOL_ID,
        "matrix_report_id": MATRIX_ID,
        "fusion_report_id": FUSION_ID,
        "xau_vol_oi_report_id": XAU_VOL_OI_ID,
        "xau_reaction_report_id": XAU_REACTION_ID,
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
        "snapshot_key": "20260514_daily_snapshot_g2rk6_abcdef123456",
        "status": XauForwardJournalEntryStatus.PARTIAL.value,
        "snapshot_time": "2026-05-14T03:08:04Z",
        "capture_window": "daily_snapshot",
        "capture_session": None,
        "product": "Gold (OG|GC)",
        "expiration_code": "G2RK6",
        "fusion_report_id": FUSION_ID,
        "xau_vol_oi_report_id": XAU_VOL_OI_ID,
        "xau_reaction_report_id": XAU_REACTION_ID,
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


def write_synthetic_source_reports(
    reports_dir: Path,
    *,
    product: str = "Gold (OG|GC)",
    fusion_status: str = "completed",
    fusion_warning: str | None = None,
    reaction_source_report_id: str = XAU_VOL_OI_ID,
) -> dict[str, str]:
    _write_json(
        reports_dir / "quikstrike" / VOL2VOL_ID / "report.json",
        {
            "extraction_id": VOL2VOL_ID,
            "status": "completed",
            "created_at": "2026-05-14T03:00:00Z",
            "row_count": 10,
            "conversion_result": {"status": "completed", "row_count": 2},
            "warnings": [],
            "limitations": ["Vol2Vol local-only fixture."],
            "research_only_warnings": ["Vol2Vol research-only fixture."],
            "artifacts": [],
        },
    )
    _write_json(
        reports_dir / "quikstrike" / VOL2VOL_ID / "normalized_rows.json",
        [
            {
                "product": product,
                "option_product_code": "OG|GC",
                "expiration_code": "G2RK6",
                "expiration": "2026-06-25",
            }
        ],
    )
    _write_json(
        reports_dir / "quikstrike_matrix" / MATRIX_ID / "report.json",
        {
            "extraction_id": MATRIX_ID,
            "status": "completed",
            "created_at": "2026-05-14T03:01:00Z",
            "product": product,
            "row_count": 30,
            "strike_count": 5,
            "expiration_count": 2,
            "warnings": [],
            "limitations": ["Matrix local-only fixture."],
            "research_only_warnings": ["Matrix research-only fixture."],
            "artifacts": [],
        },
    )
    _write_json(
        reports_dir / "xau_quikstrike_fusion" / FUSION_ID / "report.json",
        {
            "report_id": FUSION_ID,
            "status": fusion_status,
            "created_at": "2026-05-14T03:02:00Z",
            "vol2vol_source": {
                "report_id": VOL2VOL_ID,
                "status": "completed",
                "product": product,
                "row_count": 10,
                "warnings": [],
                "limitations": ["Vol2Vol source fixture."],
            },
            "matrix_source": {
                "report_id": MATRIX_ID,
                "status": "completed",
                "product": product,
                "row_count": 30,
                "warnings": [],
                "limitations": ["Matrix source fixture."],
            },
            "context_summary": {
                "missing_context": [
                    {
                        "context_key": "basis",
                        "status": "unavailable",
                        "severity": "warning",
                        "message": "Basis inputs were not provided.",
                        "source_refs": [FUSION_ID],
                        "blocks_reaction_confidence": True,
                    }
                ]
            },
            "downstream_result": {
                "xau_vol_oi_report_id": XAU_VOL_OI_ID,
                "xau_reaction_report_id": XAU_REACTION_ID,
            },
            "fused_row_count": 3,
            "fused_rows": [
                _fusion_row("fusion_oi_1", 4700.0, "open_interest", 120.0, "call"),
                _fusion_row("fusion_oi_change_1", 4725.0, "oi_change", 42.0, "call"),
                _fusion_row("fusion_volume_1", 4675.0, "volume", 88.0, "put"),
            ],
            "warnings": [fusion_warning] if fusion_warning else [],
            "limitations": ["Fusion local-only fixture."],
            "research_only_warnings": ["Fusion research-only fixture."],
            "artifacts": [],
        },
    )
    _write_json(
        reports_dir / "xau_vol_oi" / XAU_VOL_OI_ID / "metadata.json",
        {
            "report_id": XAU_VOL_OI_ID,
            "status": "completed",
            "created_at": "2026-05-14T03:03:00Z",
            "session_date": "2026-05-14",
            "source_row_count": 2,
            "wall_count": 2,
            "zone_count": 2,
            "walls": [
                _xau_wall("wall_1", 4700.0, "call", 200.0, 0.35),
                _xau_wall("wall_2", 4675.0, "put", 150.0, 0.25),
            ],
            "zones": [],
            "warnings": [],
            "limitations": ["XAU Vol-OI local-only fixture."],
            "artifacts": [],
        },
    )
    _write_json(
        reports_dir / "xau_reaction" / XAU_REACTION_ID / "metadata.json",
        {
            "report_id": XAU_REACTION_ID,
            "source_report_id": reaction_source_report_id,
            "status": "partial",
            "created_at": "2026-05-14T03:04:00Z",
            "reaction_count": 2,
            "no_trade_count": 1,
            "risk_plan_count": 2,
            "reactions": [
                {
                    "reaction_id": "reaction_1",
                    "source_report_id": XAU_VOL_OI_ID,
                    "wall_id": "wall_1",
                    "zone_id": "zone_1",
                    "reaction_label": "NO_TRADE",
                    "confidence_label": "blocked",
                    "no_trade_reasons": [
                        "Basis mapping is unavailable.",
                        "Opening-price regime context is unavailable.",
                    ],
                },
                {
                    "reaction_id": "reaction_2",
                    "source_report_id": XAU_VOL_OI_ID,
                    "wall_id": "wall_2",
                    "zone_id": "zone_2",
                    "reaction_label": "PIN_MAGNET",
                    "confidence_label": "low",
                    "no_trade_reasons": [],
                },
            ],
            "risk_plans": [
                {"plan_id": "plan_1", "reaction_id": "reaction_1"},
                {"plan_id": "plan_2", "reaction_id": "reaction_2"},
            ],
            "warnings": ["Reaction context is partial."],
            "limitations": ["XAU reaction local-only fixture."],
            "artifacts": [],
        },
    )
    return {
        "vol2vol_report_id": VOL2VOL_ID,
        "matrix_report_id": MATRIX_ID,
        "fusion_report_id": FUSION_ID,
        "xau_vol_oi_report_id": XAU_VOL_OI_ID,
        "xau_reaction_report_id": XAU_REACTION_ID,
    }


def _fusion_row(
    row_id: str,
    strike: float,
    value_type: str,
    value: float,
    option_type: str,
) -> dict[str, Any]:
    return {
        "fusion_row_id": row_id,
        "match_key": {
            "strike": strike,
            "expiration": "2026-06-25",
            "expiration_code": "G2RK6",
            "option_type": option_type,
            "value_type": value_type,
        },
        "matrix_value": {
            "value": value,
            "value_type": value_type,
            "limitations": ["Matrix value fixture."],
        },
        "limitations": ["Fusion row fixture."],
    }


def _xau_wall(
    wall_id: str,
    strike: float,
    option_type: str,
    open_interest: float,
    wall_score: float,
) -> dict[str, Any]:
    return {
        "wall_id": wall_id,
        "expiry": "2026-06-25",
        "strike": strike,
        "option_type": option_type,
        "open_interest": open_interest,
        "total_expiry_open_interest": 350.0,
        "oi_share": open_interest / 350.0,
        "expiry_weight": 1.0,
        "freshness_factor": 1.0,
        "wall_score": wall_score,
        "freshness_status": "confirmed",
        "notes": ["Synthetic wall summary."],
        "limitations": ["XAU wall fixture."],
    }


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
