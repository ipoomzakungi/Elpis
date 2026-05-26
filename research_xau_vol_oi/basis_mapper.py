"""Futures-to-spot basis mapping for CME gold option strikes."""

from __future__ import annotations

from typing import Any

import polars as pl


def compute_basis(gold_futures_price: float, xauusd_spot_price: float) -> float:
    """Compute ``gold_futures_price - xauusd_spot_price``."""

    if gold_futures_price <= 0:
        raise ValueError("gold_futures_price must be greater than 0")
    if xauusd_spot_price <= 0:
        raise ValueError("xauusd_spot_price must be greater than 0")
    return gold_futures_price - xauusd_spot_price


def map_strike_to_spot_equivalent(cme_option_strike: float, basis: float) -> float:
    """Convert a CME futures/options strike into a spot-equivalent XAU/USD level."""

    if cme_option_strike <= 0:
        raise ValueError("cme_option_strike must be greater than 0")
    return cme_option_strike - basis


def add_basis_columns(
    options: pl.DataFrame,
    *,
    manual_basis: float | None = None,
) -> pl.DataFrame:
    """Add basis and spot-equivalent strike columns to standardized option rows.

    If ``manual_basis`` is absent, each row must provide ``futures_price`` and
    ``spot_price`` for basis mapping. Missing basis is left explicit instead of
    being guessed.
    """

    rows: list[dict[str, Any]] = []
    for raw in options.to_dicts():
        basis: float | None = manual_basis
        basis_source = "manual" if manual_basis is not None else "computed"
        if basis is None:
            futures_price = raw.get("futures_price")
            spot_price = raw.get("spot_price")
            if futures_price is not None and spot_price is not None:
                basis = compute_basis(float(futures_price), float(spot_price))
            else:
                basis_source = "missing"
        level = (
            map_strike_to_spot_equivalent(float(raw["strike"]), basis)
            if basis is not None
            else None
        )
        rows.append(
            {
                **raw,
                "basis": basis,
                "basis_source": basis_source,
                "spot_equivalent_strike": level,
                "basis_available": basis is not None,
            }
        )
    return pl.DataFrame(rows, infer_schema_length=None) if rows else options
