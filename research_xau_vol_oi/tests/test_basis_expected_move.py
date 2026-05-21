from math import isclose, sqrt

from research_xau_vol_oi.basis_mapper import compute_basis, map_strike_to_spot_equivalent
from research_xau_vol_oi.expected_move import compute_expected_move


def test_basis_mapping_formula() -> None:
    basis = compute_basis(gold_futures_price=2410.0, xauusd_spot_price=2403.0)

    assert basis == 7.0
    assert map_strike_to_spot_equivalent(2400.0, basis) == 2393.0


def test_expected_move_formula() -> None:
    move = compute_expected_move(
        reference_price=2400.0,
        annualized_iv_percent=16.0,
        time_remaining_fraction=0.25,
        spot_price=2412.0,
        session_open=2400.0,
    )

    expected_full_day = 2400.0 * (16.0 / 100.0) / sqrt(252)
    assert isclose(move.one_sd_full_day, expected_full_day)
    assert isclose(move.one_sd_remaining, expected_full_day * sqrt(0.25))
    assert isclose(move.two_sd_remaining, 2.0 * move.one_sd_remaining)
    assert isclose(move.three_sd_remaining, 3.0 * move.one_sd_remaining)
    assert isclose(move.sigma_position, 12.0 / move.one_sd_remaining)
