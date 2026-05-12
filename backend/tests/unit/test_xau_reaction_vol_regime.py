import pytest

from src.models.xau_reaction import (
    XauIvEdgeState,
    XauRvExtensionState,
    XauVolRegimeInput,
    XauVrpRegime,
)
from src.xau_reaction.vol_regime import calculate_realized_volatility, evaluate_vol_regime


def test_evaluate_vol_regime_computes_vrp_and_iv_premium():
    result = evaluate_vol_regime(
        XauVolRegimeInput(
            implied_volatility=0.24,
            realized_volatility=0.16,
            price=2400.0,
            iv_lower=2350.0,
            iv_upper=2450.0,
            rv_lower=2360.0,
            rv_upper=2440.0,
        )
    )

    assert result.vrp == pytest.approx(0.08)
    assert result.realized_volatility == 0.16
    assert result.vrp_regime == XauVrpRegime.IV_PREMIUM
    assert result.iv_edge_state == XauIvEdgeState.INSIDE
    assert result.rv_extension_state == XauRvExtensionState.INSIDE


def test_evaluate_vol_regime_marks_iv_edge_stress_and_rv_extension_separately():
    result = evaluate_vol_regime(
        XauVolRegimeInput(
            implied_volatility=0.18,
            realized_volatility=0.17,
            price=2455.0,
            iv_lower=2350.0,
            iv_upper=2450.0,
            rv_lower=2360.0,
            rv_upper=2460.0,
        )
    )

    assert result.vrp_regime == XauVrpRegime.BALANCED
    assert result.iv_edge_state == XauIvEdgeState.BEYOND_EDGE
    assert result.rv_extension_state == XauRvExtensionState.EXTENDED
    assert any("stress or squeeze warning" in note for note in result.notes)


def test_evaluate_vol_regime_can_calculate_realized_volatility_from_price_series():
    realized_volatility = calculate_realized_volatility(
        [2400.0, 2406.0, 2398.0, 2412.0],
        annualization_periods=252,
    )
    result = evaluate_vol_regime(
        XauVolRegimeInput(
            implied_volatility=0.20,
            price_series=[2400.0, 2406.0, 2398.0, 2412.0],
            annualization_periods=252,
        )
    )

    assert realized_volatility > 0
    assert result.realized_volatility == pytest.approx(realized_volatility)
    assert result.vrp is not None


def test_evaluate_vol_regime_returns_unknown_when_iv_or_rv_is_missing():
    result = evaluate_vol_regime(XauVolRegimeInput(implied_volatility=0.20))

    assert result.vrp is None
    assert result.vrp_regime == XauVrpRegime.UNKNOWN
    assert result.iv_edge_state == XauIvEdgeState.UNKNOWN
    assert result.rv_extension_state == XauRvExtensionState.UNKNOWN


def test_evaluate_vol_regime_marks_rv_premium_when_realized_vol_exceeds_iv():
    result = evaluate_vol_regime(
        XauVolRegimeInput(
            implied_volatility=0.15,
            realized_volatility=0.21,
            price=2400.0,
            iv_lower=2350.0,
            iv_upper=2450.0,
            rv_lower=2360.0,
            rv_upper=2440.0,
        )
    )

    assert result.vrp == pytest.approx(-0.06)
    assert result.vrp_regime == XauVrpRegime.RV_PREMIUM
