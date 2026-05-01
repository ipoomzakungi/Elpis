from math import sqrt

from src.models.xau import XauExpectedRange, XauVolatilitySnapshot, XauVolatilitySource

TRADING_DAYS_PER_YEAR = 365.0
RESEARCH_RANGE_NOTE = "Expected ranges are research context only and are not predictions."


def compute_expected_move(
    *,
    reference_price: float,
    annualized_volatility: float,
    days_to_expiry: int,
) -> float:
    """Compute a one-standard-deviation expected move from annualized volatility."""

    if reference_price <= 0:
        raise ValueError("reference_price must be greater than 0")
    if annualized_volatility <= 0:
        raise ValueError("annualized_volatility must be greater than 0")
    if days_to_expiry < 0:
        raise ValueError("days_to_expiry must be greater than or equal to 0")
    return reference_price * annualized_volatility * sqrt(days_to_expiry / TRADING_DAYS_PER_YEAR)


def expected_range_from_snapshot(
    *,
    snapshot: XauVolatilitySnapshot | None,
    reference_price: float | None,
    include_2sd_range: bool = False,
) -> XauExpectedRange:
    """Create an IV, realized-volatility, manual, or unavailable expected range."""

    if reference_price is None or reference_price <= 0:
        return unavailable_expected_range("A positive reference price is required.")
    if snapshot is None:
        return unavailable_expected_range("Volatility snapshot is unavailable.")

    if snapshot.source == XauVolatilitySource.MANUAL:
        if snapshot.manual_expected_move is None:
            return unavailable_expected_range("Manual expected move is required for manual range.")
        return _range_from_move(
            source=XauVolatilitySource.MANUAL,
            reference_price=reference_price,
            expected_move=snapshot.manual_expected_move,
            days_to_expiry=snapshot.days_to_expiry,
            include_2sd_range=include_2sd_range,
            notes=[*snapshot.notes, "Manual expected range supplied by researcher."],
        )

    volatility = _select_volatility(snapshot)
    if volatility is None:
        return unavailable_expected_range(
            f"{snapshot.source.value} volatility input is unavailable."
        )
    if snapshot.days_to_expiry is None:
        return unavailable_expected_range("days_to_expiry is required for volatility ranges.")

    expected_move = compute_expected_move(
        reference_price=reference_price,
        annualized_volatility=volatility,
        days_to_expiry=snapshot.days_to_expiry,
    )
    return _range_from_move(
        source=snapshot.source,
        reference_price=reference_price,
        expected_move=expected_move,
        days_to_expiry=snapshot.days_to_expiry,
        include_2sd_range=include_2sd_range,
        notes=[*snapshot.notes, RESEARCH_RANGE_NOTE],
    )


def unavailable_expected_range(reason: str) -> XauExpectedRange:
    return XauExpectedRange(
        source=XauVolatilitySource.UNAVAILABLE,
        unavailable_reason=reason,
        notes=[reason],
    )


def _select_volatility(snapshot: XauVolatilitySnapshot) -> float | None:
    if snapshot.source == XauVolatilitySource.IV:
        return snapshot.implied_volatility
    if snapshot.source == XauVolatilitySource.REALIZED_VOLATILITY:
        return snapshot.realized_volatility
    return None


def _range_from_move(
    *,
    source: XauVolatilitySource,
    reference_price: float,
    expected_move: float,
    days_to_expiry: int | None,
    include_2sd_range: bool,
    notes: list[str],
) -> XauExpectedRange:
    lower_1sd = reference_price - expected_move
    upper_1sd = reference_price + expected_move
    return XauExpectedRange(
        source=source,
        reference_price=reference_price,
        expected_move=expected_move,
        lower_1sd=lower_1sd,
        upper_1sd=upper_1sd,
        lower_2sd=reference_price - (2 * expected_move) if include_2sd_range else None,
        upper_2sd=reference_price + (2 * expected_move) if include_2sd_range else None,
        days_to_expiry=days_to_expiry,
        unavailable_reason=None,
        notes=notes,
    )
