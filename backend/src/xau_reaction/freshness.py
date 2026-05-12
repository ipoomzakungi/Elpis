from datetime import UTC

from src.models.xau_reaction import (
    XauConfidenceLabel,
    XauFreshnessInput,
    XauFreshnessResult,
    XauFreshnessState,
)


def classify_freshness(input_data: XauFreshnessInput) -> XauFreshnessResult:
    """Classify whether intraday options OI context is usable for research."""

    if input_data.intraday_timestamp is None or input_data.current_timestamp is None:
        return _result(
            XauFreshnessState.UNKNOWN,
            XauConfidenceLabel.BLOCKED,
            "Intraday and current timestamps are required for freshness classification.",
        )

    intraday_timestamp = _as_utc(input_data.intraday_timestamp)
    current_timestamp = _as_utc(input_data.current_timestamp)
    if intraday_timestamp > current_timestamp:
        return _result(
            XauFreshnessState.UNKNOWN,
            XauConfidenceLabel.BLOCKED,
            "Intraday timestamp is after the current timestamp.",
        )

    age_minutes = (current_timestamp - intraday_timestamp).total_seconds() / 60
    contract_count = input_data.total_intraday_contracts
    if contract_count is None or contract_count <= 0:
        return _result(
            XauFreshnessState.UNKNOWN,
            XauConfidenceLabel.BLOCKED,
            "Intraday contract count is missing or not positive.",
            age_minutes=age_minutes,
        )

    if intraday_timestamp.date() < current_timestamp.date():
        return _result(
            XauFreshnessState.PRIOR_DAY,
            XauConfidenceLabel.BLOCKED,
            "Prior-day options data must not be treated as fresh intraday flow.",
            age_minutes=age_minutes,
        )

    if age_minutes > input_data.max_allowed_age_minutes:
        return _result(
            XauFreshnessState.STALE,
            XauConfidenceLabel.BLOCKED,
            "Intraday options snapshot is older than the maximum allowed age.",
            age_minutes=age_minutes,
        )

    if contract_count < input_data.min_contract_threshold:
        return _result(
            XauFreshnessState.THIN,
            XauConfidenceLabel.LOW,
            "Intraday contract count is below the minimum threshold.",
            age_minutes=age_minutes,
            no_trade_reason=None,
        )

    return XauFreshnessResult(
        state=XauFreshnessState.VALID,
        age_minutes=age_minutes,
        confidence_label=XauConfidenceLabel.HIGH,
        notes=["Intraday options context is current and above the contract threshold."],
    )


def _result(
    state: XauFreshnessState,
    confidence_label: XauConfidenceLabel,
    note: str,
    *,
    age_minutes: float | None = None,
    no_trade_reason: str | None = "",
) -> XauFreshnessResult:
    return XauFreshnessResult(
        state=state,
        age_minutes=age_minutes,
        confidence_label=confidence_label,
        no_trade_reason=note if no_trade_reason == "" else no_trade_reason,
        notes=[note],
    )


def _as_utc(value):
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
