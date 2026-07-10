from __future__ import annotations

import json
from datetime import datetime

from src.models.xau_market_context import XauPriceBar
from src.xau_vol2vol_history_walkforward.coverage_audit import (
    build_coverage_and_integrity_audit,
    integrity_blocks_backtest,
)
from src.xau_vol2vol_history_walkforward.walkforward_simulator import (
    XauPriceBarFolderLoadResult,
)


def test_coverage_audit_reports_mismatch_and_overlap(tmp_path) -> None:
    catalog = tmp_path / "catalog" / "available_sessions.json"
    catalog.parent.mkdir(parents=True)
    catalog.write_text(
        json.dumps(
            {
                "availableSessions": [
                    {"sessionDate": "2026-07-07"},
                    {"sessionDate": "2026-07-08"},
                ],
                "incomplete_session_dates": ["2026-07-08"],
            }
        ),
        encoding="utf-8",
    )
    valid = tmp_path / "daily" / "2026-07-07" / "raw.json"
    mismatch = tmp_path / "daily" / "2026-07-08" / "raw.json"
    valid.parent.mkdir(parents=True)
    mismatch.parent.mkdir(parents=True)
    valid.write_text(json.dumps(_payload("2026-07-07")), encoding="utf-8")
    mismatch.write_text(json.dumps(_payload("2026-07-10")), encoding="utf-8")
    bars = [
        XauPriceBar(
            timestamp=datetime.fromisoformat("2026-07-07T10:00:00+07:00"),
            open=4100,
            high=4101,
            low=4099,
            close=4100,
            volume=1,
        )
    ]

    coverage, integrity = build_coverage_and_integrity_audit(
        vol2vol_root=tmp_path,
        price_result=XauPriceBarFolderLoadResult(bars=bars),
        timezone="Asia/Bangkok",
    )

    assert coverage["advertised_vol2vol_session_count"] == 2
    assert coverage["collected_valid_session_count"] == 1
    assert coverage["overlap_session_count"] == 1
    assert integrity["requested_returned_date_mismatch_count"] == 1
    assert "requested_returned_date_mismatch_count=1" in integrity_blocks_backtest(integrity)


def _payload(session_date: str) -> dict:
    return {
        "sessionDate": session_date,
        "snapshots": [
            {
                "id": "one",
                "kind": "intraday_volume",
                "observedAt": f"{session_date}T02:55:00Z",
                "currentPrice": 4120,
                "ranges": [
                    {"sd": 2, "down": 20, "up": 20},
                    {"sd": 3, "down": 30, "up": 30},
                ],
            }
        ],
    }
