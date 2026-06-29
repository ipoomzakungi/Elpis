from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from src.models.xau_market_context import (
    XauContextAvailabilityStatus,
    XauPriceBar,
    XauSessionName,
    XauSessionOpen,
)


@dataclass(frozen=True)
class SessionDefinition:
    name: XauSessionName
    local_time: time
    timezone: str


DEFAULT_SESSIONS = (
    SessionDefinition(XauSessionName.DAILY_ROLL, time(0, 0), "Asia/Bangkok"),
    SessionDefinition(XauSessionName.ASIA, time(9, 0), "Asia/Tokyo"),
    SessionDefinition(XauSessionName.LONDON, time(8, 0), "Europe/London"),
    SessionDefinition(XauSessionName.NY_MACRO, time(8, 30), "America/New_York"),
    SessionDefinition(XauSessionName.NY_CASH, time(9, 30), "America/New_York"),
)


def build_session_opens(
    *,
    bars: list[XauPriceBar],
    current_timestamp: datetime,
    traded_price: float | None,
    session_date: date | None = None,
    target_timezone: str = "Asia/Bangkok",
    tolerance_minutes: int = 5,
) -> tuple[list[XauSessionOpen], XauSessionOpen | None]:
    target_tz = ZoneInfo(target_timezone)
    current_local = _to_tz(current_timestamp, target_tz)
    local_session_date = session_date or current_local.date()
    opens = [
        _build_open(
            definition=definition,
            session_date=local_session_date,
            bars=bars,
            traded_price=traded_price,
            target_tz=target_tz,
            tolerance=timedelta(minutes=tolerance_minutes),
        )
        for definition in DEFAULT_SESSIONS
    ]
    eligible = [item for item in opens if item.open_time <= current_local]
    active = max(eligible, key=lambda item: item.open_time) if eligible else None
    return sorted(opens, key=lambda item: item.open_time), active


def _build_open(
    *,
    definition: SessionDefinition,
    session_date: date,
    bars: list[XauPriceBar],
    traded_price: float | None,
    target_tz: ZoneInfo,
    tolerance: timedelta,
) -> XauSessionOpen:
    source_tz = ZoneInfo(definition.timezone)
    source_open = datetime.combine(session_date, definition.local_time, source_tz)
    open_time = source_open.astimezone(target_tz)
    matched_bar = _first_bar_at_or_after(bars, open_time, tolerance)
    status = (
        XauContextAvailabilityStatus.AVAILABLE
        if matched_bar is not None
        else XauContextAvailabilityStatus.UNAVAILABLE
    )
    open_price = matched_bar.open if matched_bar is not None else None
    notes = (
        [f"Open price matched from first bar at {matched_bar.timestamp.isoformat()}."]
        if matched_bar is not None
        else ["No traded-side bar was available near the configured session open."]
    )
    open_side: str | None = None
    open_distance: float | None = None
    if open_price is not None and traded_price is not None:
        open_distance = traded_price - open_price
        if abs(open_distance) < 1e-9:
            open_side = "at_open"
        elif open_distance > 0:
            open_side = "above_open"
        else:
            open_side = "below_open"
    return XauSessionOpen(
        session_name=definition.name,
        timezone=definition.timezone,
        open_time=open_time,
        open_price=open_price,
        status=status,
        notes=notes,
        open_side=open_side,
        open_distance_points=open_distance,
    )


def _first_bar_at_or_after(
    bars: list[XauPriceBar],
    open_time: datetime,
    tolerance: timedelta,
) -> XauPriceBar | None:
    for bar in sorted(bars, key=lambda item: item.timestamp):
        if open_time <= bar.timestamp <= open_time + tolerance:
            return bar
    return None


def _to_tz(value: datetime, timezone: ZoneInfo) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone)
    return value.astimezone(timezone)

