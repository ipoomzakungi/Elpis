import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.models.xau_forward_journal import XauForwardJournalCreateRequest
from src.xau_forward_journal.content_fingerprint import build_snapshot_content_fingerprint
from src.xau_forward_journal.entry_builder import load_source_reports
from src.xau_forward_journal.orchestration import create_xau_forward_journal_entry_result


def test_identical_content_returns_duplicate_content(tmp_path: Path):
    reports_dir = tmp_path / "data" / "reports"
    first_ids = _write_snapshot(reports_dir, "first")
    second_ids = _write_snapshot(reports_dir, "second")

    first = create_xau_forward_journal_entry_result(
        _request(first_ids, snapshot_time="2026-05-14T03:00:00Z"),
        reports_dir=reports_dir,
    )
    second = create_xau_forward_journal_entry_result(
        _request(second_ids, snapshot_time="2026-05-14T10:00:00Z"),
        reports_dir=reports_dir,
    )

    assert first.status == "created"
    assert second.status == "duplicate_content"
    assert second.previous_journal_id == first.entry.journal_id
    assert second.entry.journal_id == first.entry.journal_id
    assert len(list((reports_dir / "xau_forward_journal").glob("*"))) == 1


def test_changed_oi_or_volume_creates_new_snapshot(tmp_path: Path):
    reports_dir = tmp_path / "data" / "reports"
    first_ids = _write_snapshot(reports_dir, "first", matrix_oi=120.0, vol2vol_volume=8.0)
    changed_ids = _write_snapshot(reports_dir, "changed", matrix_oi=121.0, vol2vol_volume=9.0)

    first = create_xau_forward_journal_entry_result(
        _request(first_ids, snapshot_time="2026-05-14T03:00:00Z"),
        reports_dir=reports_dir,
    )
    changed = create_xau_forward_journal_entry_result(
        _request(changed_ids, snapshot_time="2026-05-14T10:00:00Z"),
        reports_dir=reports_dir,
    )

    assert first.status == "created"
    assert changed.status == "created"
    assert changed.entry.journal_id != first.entry.journal_id
    assert changed.content_fingerprint != first.content_fingerprint


def test_new_date_same_content_is_duplicate_unless_force_create(tmp_path: Path):
    reports_dir = tmp_path / "data" / "reports"
    first_ids = _write_snapshot(reports_dir, "first")
    next_day_ids = _write_snapshot(reports_dir, "nextday")
    forced_ids = _write_snapshot(reports_dir, "forced")

    first = create_xau_forward_journal_entry_result(
        _request(first_ids, snapshot_time="2026-05-14T03:00:00Z"),
        reports_dir=reports_dir,
    )
    duplicate = create_xau_forward_journal_entry_result(
        _request(next_day_ids, snapshot_time="2026-05-15T03:00:00Z"),
        reports_dir=reports_dir,
    )
    forced = create_xau_forward_journal_entry_result(
        _request(
            forced_ids,
            snapshot_time="2026-05-15T04:00:00Z",
            force_create=True,
        ),
        reports_dir=reports_dir,
    )

    assert first.status == "created"
    assert duplicate.status == "duplicate_content"
    assert duplicate.previous_journal_id == first.entry.journal_id
    assert forced.status == "created"
    assert forced.entry.journal_id != first.entry.journal_id


def test_fingerprint_ignores_timestamps_report_ids_and_local_paths(tmp_path: Path):
    reports_dir = tmp_path / "data" / "reports"
    first_ids = _write_snapshot(
        reports_dir,
        "first",
        capture_timestamp="2026-05-14T03:00:00Z",
        artifact_path="C:/Users/example/AppData/Local/Elpis/run-a.json",
    )
    second_ids = _write_snapshot(
        reports_dir,
        "second",
        capture_timestamp="2026-05-15T11:59:00Z",
        artifact_path="D:/Other/Profile/run-b.json",
    )

    first = build_snapshot_content_fingerprint(
        load_source_reports(_request(first_ids), reports_dir=reports_dir)
    )
    second = build_snapshot_content_fingerprint(
        load_source_reports(_request(second_ids), reports_dir=reports_dir)
    )

    assert first.fingerprint == second.fingerprint
    assert first.component_fingerprints == second.component_fingerprints


def _request(
    ids: dict[str, str],
    *,
    snapshot_time: str = "2026-05-14T03:00:00Z",
    force_create: bool = False,
) -> XauForwardJournalCreateRequest:
    return XauForwardJournalCreateRequest(
        snapshot_time=snapshot_time,
        capture_window="daily_snapshot",
        vol2vol_report_id=ids["vol2vol_report_id"],
        matrix_report_id=ids["matrix_report_id"],
        fusion_report_id=ids["fusion_report_id"],
        xau_vol_oi_report_id=ids["xau_vol_oi_report_id"],
        xau_reaction_report_id=ids["xau_reaction_report_id"],
        futures_price_at_snapshot=4707.2,
        event_news_flag="none_known",
        force_create=force_create,
        research_only_acknowledged=True,
    )


def _write_snapshot(
    reports_dir: Path,
    suffix: str,
    *,
    matrix_oi: float = 120.0,
    vol2vol_volume: float = 8.0,
    capture_timestamp: str = "2026-05-14T03:00:00Z",
    artifact_path: str = "data/reports/local/report.json",
) -> dict[str, str]:
    ids = {
        "vol2vol_report_id": f"synthetic_quikstrike_{suffix}",
        "matrix_report_id": f"synthetic_quikstrike_matrix_{suffix}",
        "fusion_report_id": f"synthetic_xau_quikstrike_fusion_{suffix}",
        "xau_vol_oi_report_id": f"synthetic_xau_vol_oi_{suffix}",
        "xau_reaction_report_id": f"synthetic_xau_reaction_{suffix}",
    }
    vol2vol_row = {
        "capture_timestamp": capture_timestamp,
        "extraction_id": ids["vol2vol_report_id"],
        "row_id": f"{ids['vol2vol_report_id']}_row",
        "product": "Gold",
        "expiration": "2026-06-25",
        "expiration_code": "G2RK6",
        "view_type": "intraday_volume",
        "strike": 4700.0,
        "option_type": "call",
        "value_type": "intraday_volume",
        "value": vol2vol_volume,
    }
    matrix_row = {
        "capture_timestamp": capture_timestamp,
        "extraction_id": ids["matrix_report_id"],
        "row_id": f"{ids['matrix_report_id']}_row",
        "product": "Gold",
        "expiration": "G2RK6",
        "view_type": "open_interest_matrix",
        "strike": 4700.0,
        "option_type": "call",
        "value_type": "open_interest",
        "value": matrix_oi,
    }
    fused_rows = [
        {
            "fusion_report_id": ids["fusion_report_id"],
            "fusion_row_id": f"{ids['fusion_report_id']}_row",
            "source_type": "both",
            "match_key": {
                "expiration": "2026-06-25",
                "expiration_code": "G2RK6",
                "strike": 4700.0,
                "option_type": "call",
                "value_type": "open_interest",
            },
            "matrix_value": {"value_type": "open_interest", "value": matrix_oi},
            "vol2vol_value": {"value_type": "intraday_volume", "value": vol2vol_volume},
        }
    ]
    _write_json(
        reports_dir / "quikstrike" / ids["vol2vol_report_id"] / "report.json",
        _source_report(ids["vol2vol_report_id"], artifact_path, row_count=1),
    )
    _write_json(
        reports_dir / "quikstrike" / ids["vol2vol_report_id"] / "normalized_rows.json",
        [vol2vol_row],
    )
    _write_json(
        reports_dir / "quikstrike_matrix" / ids["matrix_report_id"] / "report.json",
        _source_report(ids["matrix_report_id"], artifact_path, row_count=1),
    )
    _write_json(
        reports_dir / "quikstrike_matrix" / ids["matrix_report_id"] / "normalized_rows.json",
        [matrix_row],
    )
    _write_json(
        reports_dir / "xau_quikstrike_fusion" / ids["fusion_report_id"] / "report.json",
        {
            **_source_report(ids["fusion_report_id"], artifact_path, row_count=1),
            "report_id": ids["fusion_report_id"],
            "vol2vol_source": {
                "report_id": ids["vol2vol_report_id"],
                "source_kind": "synthetic",
                "status": "completed",
                "product": "Gold",
                "row_count": 1,
            },
            "matrix_source": {
                "report_id": ids["matrix_report_id"],
                "source_kind": "synthetic",
                "status": "completed",
                "product": "Gold",
                "row_count": 1,
            },
            "downstream_result": {
                "xau_vol_oi_report_id": ids["xau_vol_oi_report_id"],
                "xau_reaction_report_id": ids["xau_reaction_report_id"],
            },
            "context_summary": {"missing_context": []},
            "fused_row_count": len(fused_rows),
            "fused_rows": fused_rows,
        },
    )
    _write_json(
        reports_dir / "xau_vol_oi" / ids["xau_vol_oi_report_id"] / "metadata.json",
        {
            **_source_report(ids["xau_vol_oi_report_id"], artifact_path, row_count=1),
            "report_id": ids["xau_vol_oi_report_id"],
            "source_row_count": 1,
            "walls": [
                {
                    "wall_id": "wall_1",
                    "expiry": "2026-06-25",
                    "strike": 4700.0,
                    "option_type": "call",
                    "open_interest": matrix_oi,
                    "wall_score": 1.0,
                    "freshness_status": "confirmed",
                }
            ],
            "zones": [],
        },
    )
    _write_json(
        reports_dir / "xau_reaction" / ids["xau_reaction_report_id"] / "metadata.json",
        {
            **_source_report(ids["xau_reaction_report_id"], artifact_path, row_count=1),
            "report_id": ids["xau_reaction_report_id"],
            "source_report_id": ids["xau_vol_oi_report_id"],
            "reaction_count": 1,
            "no_trade_count": 1,
            "risk_plan_count": 0,
            "reactions": [
                {
                    "reaction_id": "reaction_1",
                    "source_report_id": ids["xau_vol_oi_report_id"],
                    "wall_id": "wall_1",
                    "reaction_label": "NO_TRADE",
                    "confidence_label": "blocked",
                    "no_trade_reasons": ["Synthetic duplicate-content fixture."],
                }
            ],
            "risk_plans": [],
        },
    )
    return ids


def _source_report(report_id: str, artifact_path: str, *, row_count: int) -> dict[str, Any]:
    return {
        "report_id": report_id,
        "extraction_id": report_id,
        "source_kind": "synthetic",
        "status": "completed",
        "created_at": datetime(2026, 5, 14, 3, 0, tzinfo=UTC).isoformat(),
        "product": "Gold",
        "row_count": row_count,
        "warnings": [],
        "limitations": ["Synthetic local-only duplicate-content fixture."],
        "research_only_warnings": ["Research-only fixture."],
        "artifacts": [{"artifact_type": "report_json", "path": artifact_path}],
    }


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
