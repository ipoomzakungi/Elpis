from __future__ import annotations

import json
from datetime import date

from src.xau_vol2vol_history_walkforward.data_lake import (
    daily_metadata_path,
    daily_raw_path,
    load_vol2vol_data_lake,
    monthly_raw_path,
)


def test_vol2vol_data_lake_loads_daily_and_monthly_payloads(tmp_path) -> None:
    daily = daily_raw_path(tmp_path, date(2026, 7, 8))
    monthly = monthly_raw_path(tmp_path, "2026-06")
    daily.parent.mkdir(parents=True)
    monthly.parent.mkdir(parents=True)
    daily.write_text(json.dumps({"snapshots": [{"id": "daily"}]}), encoding="utf-8")
    monthly.write_text(json.dumps({"snapshots": [{"id": "monthly"}]}), encoding="utf-8")

    result = load_vol2vol_data_lake(
        root=tmp_path,
        session_date_from=date(2026, 7, 8),
        session_date_to=date(2026, 7, 8),
        monthly_target="2026-06",
    )

    assert len(result.payloads) == 2
    assert result.source_paths == [daily, monthly]
    assert result.warnings == []


def test_vol2vol_data_lake_reports_missing_daily_file(tmp_path) -> None:
    result = load_vol2vol_data_lake(
        root=tmp_path,
        session_date_from=date(2026, 7, 8),
        session_date_to=date(2026, 7, 8),
    )

    assert result.payloads == []
    assert "Missing Vol2Vol daily data-lake file" in result.warnings[0]


def test_vol2vol_data_lake_excludes_incomplete_daily_file(tmp_path) -> None:
    daily = daily_raw_path(tmp_path, date(2026, 7, 15))
    metadata = daily_metadata_path(tmp_path, date(2026, 7, 15))
    daily.parent.mkdir(parents=True)
    daily.write_text(json.dumps({"snapshots": [{"id": "partial"}]}), encoding="utf-8")
    metadata.write_text(json.dumps({"complete": False}), encoding="utf-8")

    result = load_vol2vol_data_lake(
        root=tmp_path,
        session_date_from=date(2026, 7, 15),
        session_date_to=date(2026, 7, 15),
    )

    assert result.payloads == []
    assert result.source_paths == []
    assert "Incomplete Vol2Vol daily data-lake file excluded" in result.warnings[0]
