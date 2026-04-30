from datetime import UTC, datetime

from fastapi import HTTPException

from src.models.features import RegimeType

SUPPORTED_SYMBOLS = {"BTCUSDT"}
SUPPORTED_INTERVALS = {"15m"}


def bad_request(message: str) -> None:
    raise HTTPException(status_code=400, detail=message)


def api_error(
    status_code: int,
    code: str,
    message: str,
    details: list[dict[str, str]] | None = None,
) -> None:
    raise HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message, "details": details or []},
    )


def invalid_backtest_config(message: str, details: list[dict[str, str]] | None = None) -> None:
    api_error(400, "VALIDATION_ERROR", message, details)


def backtest_not_found(run_id: str) -> None:
    api_error(404, "NOT_FOUND", f"Backtest run '{run_id}' was not found")


def validation_report_not_found(validation_run_id: str) -> None:
    api_error(404, "NOT_FOUND", f"Validation run '{validation_run_id}' was not found")


def validation_processed_features_not_found(
    symbol: str,
    timeframe: str,
    feature_path: str,
) -> None:
    api_error(
        404,
        "NOT_FOUND",
        f"Processed features not found for {symbol} {timeframe}",
        [
            {
                "field": "feature_path",
                "message": (
                    f"Expected processed feature file {feature_path}. "
                    "Run the existing public-data research flow first: "
                    "POST /api/v1/download, then POST /api/v1/process."
                ),
            },
            {
                "field": "download",
                "message": (
                    "Use POST /api/v1/download with the required symbol/timeframe before "
                    "running validation."
                ),
            },
            {
                "field": "process",
                "message": (
                    "Use POST /api/v1/process to create "
                    f"{symbol.lower()}_{timeframe}_features.parquet."
                ),
            },
        ],
    )


def validation_not_implemented() -> None:
    api_error(
        501,
        "NOT_IMPLEMENTED",
        "Validation report execution is not implemented in this phase",
    )


def invalid_validation_config(message: str, details: list[dict[str, str]] | None = None) -> None:
    api_error(400, "VALIDATION_ERROR", message, details)


def processed_features_not_found(symbol: str, timeframe: str, feature_path: str) -> None:
    api_error(
        404,
        "NOT_FOUND",
        f"Processed features not found for {symbol} {timeframe}",
        [{"field": "feature_path", "message": f"{feature_path} does not exist"}],
    )


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
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)

    return parsed
