from datetime import date

from src.models.xau_walk_forward_research import (
    XauWalkForwardScheduleConfig,
    XauWalkForwardScheduleTag,
)
from src.xau_walk_forward.schedule import build_xau_walk_forward_schedule


def test_weekday_generates_ten_minute_schedule_and_planning_tags() -> None:
    scheduled = build_xau_walk_forward_schedule(
        date(2026, 6, 8),
        XauWalkForwardScheduleConfig(),
    )

    assert len(scheduled) == 71
    assert scheduled[0].timestamp.hour == 10
    assert scheduled[0].timestamp.minute == 10
    assert scheduled[-1].timestamp.hour == 21
    assert scheduled[-1].timestamp.minute == 50
    assert scheduled[0].tag == XauWalkForwardScheduleTag.PLANNING_1010
    assert any(item.tag == XauWalkForwardScheduleTag.PLANNING_1910 for item in scheduled)


def test_weekend_schedule_is_empty_when_weekdays_only() -> None:
    scheduled = build_xau_walk_forward_schedule(
        date(2026, 6, 7),
        XauWalkForwardScheduleConfig(),
    )

    assert scheduled == []


def test_planning_only_mode_returns_two_planning_times() -> None:
    scheduled = build_xau_walk_forward_schedule(
        date(2026, 6, 8),
        XauWalkForwardScheduleConfig(include_planning_times_only=True),
    )

    assert [item.tag for item in scheduled] == [
        XauWalkForwardScheduleTag.PLANNING_1010,
        XauWalkForwardScheduleTag.PLANNING_1910,
    ]
