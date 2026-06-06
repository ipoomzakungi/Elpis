import json
import shutil
from datetime import UTC, datetime

from scripts import xau_daily_quikstrike_snapshot
from scripts.xau_daily_quikstrike_snapshot import (
    _capture_matrix_supplemental_views,
    _resolve_data_date,
)


def test_cme_bangkok_noon_policy_uses_previous_day_before_noon():
    data_date = _resolve_data_date(
        explicit_data_date=None,
        policy="cme-bangkok-noon",
        capture_time=datetime(2026, 5, 21, 1, 0, tzinfo=UTC),
    )

    assert data_date.isoformat() == "2026-05-20"


def test_cme_bangkok_noon_policy_uses_same_day_after_noon():
    data_date = _resolve_data_date(
        explicit_data_date=None,
        policy="cme-bangkok-noon",
        capture_time=datetime(2026, 5, 21, 6, 0, tzinfo=UTC),
    )

    assert data_date.isoformat() == "2026-05-21"


def test_explicit_data_date_overrides_policy():
    data_date = _resolve_data_date(
        explicit_data_date="2026-05-19",
        policy="capture-date",
        capture_time=datetime(2026, 5, 21, 6, 0, tzinfo=UTC),
    )

    assert data_date.isoformat() == "2026-05-19"


def test_capture_matrix_supplemental_views_writes_sanitized_sidecar(monkeypatch):
    def fake_collect(**_kwargs):
        return {
            "settlements": {"visible_text": "Gold Settlements", "tables": []},
            "futures_volume_oi": {"visible_text": "Gold Futures Volume & OI", "tables": []},
        }

    monkeypatch.setattr(
        xau_daily_quikstrike_snapshot,
        "collect_supplemental_views_from_cdp",
        fake_collect,
    )

    path, status, views = _capture_matrix_supplemental_views(
        cdp_url="http://127.0.0.1:9222",
        matrix_report_id="test_matrix_supplemental",
        wait_seconds=1,
        poll_seconds=1,
    )

    assert status == "completed"
    assert views == ["settlements", "futures_volume_oi"]
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["status"] == "completed"
    assert payload["view_count"] == 2
    assert "headers" in " ".join(payload["limitations"])
    shutil.rmtree(path.parent, ignore_errors=True)
