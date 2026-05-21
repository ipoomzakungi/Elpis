from math import isclose, sqrt
from datetime import UTC, datetime

import polars as pl

from research_xau_vol_oi.basis_mapper import compute_basis, map_strike_to_spot_equivalent
from research_xau_vol_oi.expected_move import (
    add_expected_move_columns_asof_options,
    compute_expected_move,
)


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


def test_expected_move_uses_only_asof_option_iv() -> None:
    price = pl.DataFrame(
        [
            {
                "timestamp": datetime(2026, 5, 21, 9, 0, tzinfo=UTC),
                "symbol": "GC=F",
                "open": 2400.0,
                "high": 2402.0,
                "low": 2399.0,
                "close": 2401.0,
                "volume": 1.0,
                "source_label": "test",
                "source_path": "",
                "session_date": "2026-05-21",
            },
            {
                "timestamp": datetime(2026, 5, 21, 10, 0, tzinfo=UTC),
                "symbol": "GC=F",
                "open": 2401.0,
                "high": 2404.0,
                "low": 2400.0,
                "close": 2403.0,
                "volume": 1.0,
                "source_label": "test",
                "source_path": "",
                "session_date": "2026-05-21",
            },
        ]
    )
    options = pl.DataFrame(
        [
            {
                "timestamp": datetime(2026, 5, 21, 9, 30, tzinfo=UTC),
                "iv_percent": 16.0,
            }
        ]
    )

    features = add_expected_move_columns_asof_options(price, options)

    assert features.row(0, named=True)["data_quality_state"] == "MISSING_IV"
    assert features.row(0, named=True)["one_sd_remaining"] is None
    assert features.row(1, named=True)["iv_available_timestamp"] <= features.row(
        1,
        named=True,
    )["timestamp"]
    assert features.row(1, named=True)["one_sd_remaining"] is not None
