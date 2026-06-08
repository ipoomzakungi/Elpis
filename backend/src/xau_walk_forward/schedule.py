from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from src.models.xau_walk_forward_research import (
    XauWalkForwardScheduleConfig,
    XauWalkForwardScheduledTimestamp,
    XauWalkForwardScheduleTag,
)


def build_xau_walk_forward_schedule(
    session_date: date,
    config: XauWalkForwardScheduleConfig,
) -> list[XauWalkForwardScheduledTimestamp]:
    if config.weekdays_only and session_date.weekday() >= 5:
        return []

    tz = ZoneInfo(config.timezone)
    planning = set(config.planning_times)
    if config.include_planning_times_only:
        times = sorted(planning)
    else:
        current = datetime.combine(session_date, config.capture_start_time, tzinfo=tz)
        end = datetime.combine(session_date, config.capture_end_time, tzinfo=tz)
        times = []
        while current <= end:
            times.append(current.timetz().replace(tzinfo=None))
            current += timedelta(minutes=config.capture_interval_minutes)
        times = sorted(set(times).union(planning))

    return [
        XauWalkForwardScheduledTimestamp(
            timestamp=datetime.combine(session_date, item, tzinfo=tz),
            tag=_schedule_tag(item),
        )
        for item in times
    ]


def _schedule_tag(item) -> XauWalkForwardScheduleTag:
    if item.hour == 10 and item.minute == 10:
        return XauWalkForwardScheduleTag.PLANNING_1010
    if item.hour == 19 and item.minute == 10:
        return XauWalkForwardScheduleTag.PLANNING_1910
    return XauWalkForwardScheduleTag.WALK_FORWARD


__all__ = ["build_xau_walk_forward_schedule"]
