from __future__ import annotations

import json
from datetime import date

from src.xau_vol2vol_history_walkforward.data_lake import (
    daily_metadata_path,
    daily_raw_path,
    evaluate_daily_session_eligibility,
    load_vol2vol_data_lake,
    monthly_raw_path,
    session_is_eligible_for_observation,
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


def test_current_incomplete_session_is_forward_only(tmp_path) -> None:
    session_date = date(2026, 7, 16)
    daily = daily_raw_path(tmp_path, session_date)
    metadata = daily_metadata_path(tmp_path, session_date)
    daily.parent.mkdir(parents=True)
    daily.write_text(
        json.dumps({"sessionDate": session_date.isoformat(), "snapshots": []}),
        encoding="utf-8",
    )
    metadata.write_text(
        json.dumps(
            {
                "complete": False,
                "collection_history": [{"sha256": "first"}],
            }
        ),
        encoding="utf-8",
    )

    eligibility = evaluate_daily_session_eligibility(
        root=tmp_path,
        session_date=session_date,
        current_date=session_date,
    )

    assert eligibility.source_session_status == "current_incomplete"
    assert eligibility.forward_plan_eligible is True
    assert eligibility.backtest_eligible is False
    assert eligibility.collection_history_count == 1
    assert session_is_eligible_for_observation(eligibility, "true_forward") is True
    assert (
        session_is_eligible_for_observation(eligibility, "retrospective_replay")
        is False
    )
    assert (
        session_is_eligible_for_observation(eligibility, "historical_backtest")
        is False
    )


def test_completed_refresh_promotes_session_to_backtest_eligible(tmp_path) -> None:
    session_date = date(2026, 7, 15)
    daily = daily_raw_path(tmp_path, session_date)
    metadata = daily_metadata_path(tmp_path, session_date)
    daily.parent.mkdir(parents=True)
    daily.write_text(
        json.dumps({"sessionDate": session_date.isoformat(), "snapshots": []}),
        encoding="utf-8",
    )
    metadata.write_text(
        json.dumps(
            {
                "complete": True,
                "collection_history": [
                    {"sha256": "partial", "complete": False},
                    {"sha256": "complete", "complete": True},
                ],
            }
        ),
        encoding="utf-8",
    )

    eligibility = evaluate_daily_session_eligibility(
        root=tmp_path,
        session_date=session_date,
        current_date=date(2026, 7, 16),
    )

    assert eligibility.source_session_status == "complete"
    assert eligibility.forward_plan_eligible is True
    assert eligibility.backtest_eligible is True
    assert eligibility.collection_history_count == 2


def test_daily_session_eligibility_rejects_returned_date_mismatch(tmp_path) -> None:
    daily = daily_raw_path(tmp_path, date(2026, 7, 15))
    daily.parent.mkdir(parents=True)
    daily.write_text(
        json.dumps({"sessionDate": "2026-07-16", "snapshots": []}),
        encoding="utf-8",
    )

    eligibility = evaluate_daily_session_eligibility(
        root=tmp_path,
        session_date=date(2026, 7, 15),
        current_date=date(2026, 7, 16),
    )

    assert eligibility.source_session_status == "date_mismatch"
    assert eligibility.forward_plan_eligible is False
    assert eligibility.backtest_eligible is False
