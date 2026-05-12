from math import log, sqrt
from statistics import stdev

from src.models.xau_reaction import (
    XauConfidenceLabel,
    XauIvEdgeState,
    XauRvExtensionState,
    XauVolRegimeInput,
    XauVolRegimeResult,
    XauVrpRegime,
)

VRP_BALANCED_THRESHOLD = 0.02
EDGE_TOLERANCE_POINTS = 0.0
RV_EXTENSION_FRACTION = 0.10


def evaluate_vol_regime(input_data: XauVolRegimeInput) -> XauVolRegimeResult:
    """Evaluate IV/RV/VRP context as research annotations only."""

    realized_volatility = input_data.realized_volatility
    if realized_volatility is None and input_data.price_series:
        realized_volatility = calculate_realized_volatility(
            input_data.price_series,
            annualization_periods=input_data.annualization_periods,
        )

    vrp = None
    vrp_regime = XauVrpRegime.UNKNOWN
    notes: list[str] = []
    if input_data.implied_volatility is not None and realized_volatility is not None:
        vrp = input_data.implied_volatility - realized_volatility
        vrp_regime = _vrp_regime(vrp)
        notes.append("VRP is calculated as implied volatility minus realized volatility.")
    else:
        notes.append("IV/RV comparison is unavailable because IV or RV is missing.")

    iv_edge_state = _range_state_for_iv(
        price=input_data.price,
        lower=input_data.iv_lower,
        upper=input_data.iv_upper,
    )
    rv_extension_state = _range_state_for_rv(
        price=input_data.price,
        lower=input_data.rv_lower,
        upper=input_data.rv_upper,
    )
    confidence = _confidence_label(
        vrp_regime=vrp_regime,
        iv_edge_state=iv_edge_state,
        rv_extension_state=rv_extension_state,
    )
    notes.extend(_state_notes(vrp_regime, iv_edge_state, rv_extension_state))

    return XauVolRegimeResult(
        realized_volatility=realized_volatility,
        vrp=vrp,
        vrp_regime=vrp_regime,
        iv_edge_state=iv_edge_state,
        rv_extension_state=rv_extension_state,
        confidence_label=confidence,
        notes=notes,
    )


def calculate_realized_volatility(
    price_series: list[float],
    *,
    annualization_periods: int | None,
) -> float:
    """Calculate annualized realized volatility from log returns."""

    if len(price_series) < 2:
        raise ValueError("price_series requires at least two values")
    if annualization_periods is None or annualization_periods <= 0:
        raise ValueError("annualization_periods must be greater than 0")
    if any(price <= 0 for price in price_series):
        raise ValueError("price_series values must be greater than 0")

    returns = [
        log(price_series[index] / price_series[index - 1])
        for index in range(1, len(price_series))
    ]
    if len(returns) == 1:
        return abs(returns[0]) * sqrt(annualization_periods)
    return stdev(returns) * sqrt(annualization_periods)


def _vrp_regime(vrp: float) -> XauVrpRegime:
    if vrp > VRP_BALANCED_THRESHOLD:
        return XauVrpRegime.IV_PREMIUM
    if vrp < -VRP_BALANCED_THRESHOLD:
        return XauVrpRegime.RV_PREMIUM
    return XauVrpRegime.BALANCED


def _range_state_for_iv(
    *,
    price: float | None,
    lower: float | None,
    upper: float | None,
) -> XauIvEdgeState:
    if price is None or lower is None or upper is None:
        return XauIvEdgeState.UNKNOWN
    if price < lower - EDGE_TOLERANCE_POINTS or price > upper + EDGE_TOLERANCE_POINTS:
        return XauIvEdgeState.BEYOND_EDGE
    if price == lower or price == upper:
        return XauIvEdgeState.AT_EDGE
    return XauIvEdgeState.INSIDE


def _range_state_for_rv(
    *,
    price: float | None,
    lower: float | None,
    upper: float | None,
) -> XauRvExtensionState:
    if price is None or lower is None or upper is None:
        return XauRvExtensionState.UNKNOWN
    if price < lower or price > upper:
        return XauRvExtensionState.BEYOND_RANGE
    width = upper - lower
    edge_band = width * RV_EXTENSION_FRACTION
    if price <= lower + edge_band or price >= upper - edge_band:
        return XauRvExtensionState.EXTENDED
    return XauRvExtensionState.INSIDE


def _confidence_label(
    *,
    vrp_regime: XauVrpRegime,
    iv_edge_state: XauIvEdgeState,
    rv_extension_state: XauRvExtensionState,
) -> XauConfidenceLabel:
    if iv_edge_state == XauIvEdgeState.BEYOND_EDGE:
        return XauConfidenceLabel.LOW
    if vrp_regime == XauVrpRegime.IV_PREMIUM:
        return XauConfidenceLabel.MEDIUM
    if rv_extension_state in {XauRvExtensionState.EXTENDED, XauRvExtensionState.BEYOND_RANGE}:
        return XauConfidenceLabel.MEDIUM
    if vrp_regime == XauVrpRegime.UNKNOWN:
        return XauConfidenceLabel.UNKNOWN
    return XauConfidenceLabel.HIGH


def _state_notes(
    vrp_regime: XauVrpRegime,
    iv_edge_state: XauIvEdgeState,
    rv_extension_state: XauRvExtensionState,
) -> list[str]:
    notes: list[str] = []
    if vrp_regime == XauVrpRegime.IV_PREMIUM:
        notes.append("IV is greater than RV; simple mean-reversion confidence is reduced.")
    if iv_edge_state == XauIvEdgeState.BEYOND_EDGE:
        notes.append("Price is beyond the IV range edge; treat as stress or squeeze warning.")
    if rv_extension_state == XauRvExtensionState.BEYOND_RANGE:
        notes.append("Price is beyond the RV range without necessarily confirming IV edge stress.")
    elif rv_extension_state == XauRvExtensionState.EXTENDED:
        notes.append("Price is extended near an RV range edge.")
    notes.append("Volatility context is a research annotation only.")
    return notes
