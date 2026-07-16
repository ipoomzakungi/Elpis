from __future__ import annotations

from datetime import date, datetime

import pytest

from scripts.run_xau_forward_daily import _observation_mode


def test_late_prepare_cannot_be_labeled_true_forward() -> None:
    planning_at = datetime.fromisoformat("2026-07-16T07:00:00+07:00")

    with pytest.raises(ValueError, match="true_forward prepare must be recorded"):
        _observation_mode(
            explicit="true_forward",
            stage="prepare",
            successful_prepare=None,
            session_date=date(2026, 7, 16),
            planning_at=planning_at,
            recorded_at=datetime.fromisoformat("2026-07-16T08:00:00+07:00"),
        )


def test_monitor_inherits_true_forward_after_successful_prepare() -> None:
    planning_at = datetime.fromisoformat("2026-07-16T07:00:00+07:00")

    mode = _observation_mode(
        explicit=None,
        stage="monitor",
        successful_prepare={"observation_mode": "true_forward"},
        session_date=date(2026, 7, 16),
        planning_at=planning_at,
        recorded_at=datetime.fromisoformat("2026-07-16T15:00:00+07:00"),
    )

    assert mode == "true_forward"
