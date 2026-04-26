from datetime import datetime, timezone

from fastapi import HTTPException

from src.models.features import RegimeType


SUPPORTED_SYMBOLS = {"BTCUSDT"}
SUPPORTED_INTERVALS = {"15m"}


def bad_request(message: str) -> None:
    raise HTTPException(status_code=400, detail=message)


def validate_symbol(symbol: str) -> str:
    normalized = symbol.upper().strip()
    if normalized not in SUPPORTED_SYMBOLS:
        bad_request("Only BTCUSDT is supported in OI Regime Lab v0")
    return normalized


def validate_interval(interval: str) -> str:
    normalized = interval.strip()
    if normalized not in SUPPORTED_INTERVALS:
        bad_request("Only 15m interval is supported in OI Regime Lab v0")
    return normalized


def parse_time_range(
    start_time: str | None,
    end_time: str | None,
) -> tuple[datetime | None, datetime | None]:
    start_dt = _parse_datetime("start_time", start_time)
    end_dt = _parse_datetime("end_time", end_time)

    if start_dt and end_dt and start_dt > end_dt:
        bad_request("start_time must be before or equal to end_time")

    return start_dt, end_dt


def validate_regime_filter(regime: str | None) -> str | None:
    if regime is None:
        return None

    normalized = regime.upper().strip()
    valid_regimes = {regime_type.value for regime_type in RegimeType}
    if normalized not in valid_regimes:
        bad_request(f"regime must be one of: {', '.join(sorted(valid_regimes))}")

    return normalized


def _parse_datetime(field_name: str, value: str | None) -> datetime | None:
    if value is None:
        return None

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        bad_request(f"{field_name} must be an ISO 8601 datetime")

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)

    return parsed
