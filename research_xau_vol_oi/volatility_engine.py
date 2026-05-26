"""Realized volatility, IV/RV/VRP, and simple SD-only baseline features."""

from __future__ import annotations

import polars as pl

from research_xau_vol_oi.config import VolRegime


def add_realized_volatility(
    price: pl.DataFrame,
    *,
    window: int = 20,
    annualization_bars: int = 252,
) -> pl.DataFrame:
    """Add rolling realized volatility percent from log returns."""

    if window <= 1:
        raise ValueError("window must be greater than 1")
    if price.is_empty():
        return price
    return (
        price.sort("timestamp")
        .with_columns(
            (pl.col("close") / pl.col("close").shift(1)).log().alias("log_return")
        )
        .with_columns(
            (
                pl.col("log_return").rolling_std(window_size=window)
                * (annualization_bars**0.5)
                * 100.0
            ).alias("rv_percent")
        )
    )


def classify_vrp_regime(
    *,
    iv_percent: float | None,
    rv_percent: float | None,
    stress_sigma: float | None = None,
) -> VolRegime:
    """Classify IV/RV spread without implying predictive edge."""

    if iv_percent is None or rv_percent is None or rv_percent <= 0:
        return VolRegime.UNKNOWN
    if stress_sigma is not None and abs(stress_sigma) > 2.5:
        return VolRegime.STRESS
    vrp = iv_percent - rv_percent
    if vrp >= 3.0:
        return VolRegime.IV_PREMIUM
    if vrp <= -3.0:
        return VolRegime.RV_PREMIUM
    return VolRegime.BALANCED


def add_volatility_regime(price: pl.DataFrame) -> pl.DataFrame:
    """Add VRP and IV/RV regime labels to an expected-move feature table."""

    rows = []
    for raw in price.to_dicts():
        iv_percent = raw.get("annualized_iv_percent")
        rv_percent = raw.get("rv_percent")
        regime = classify_vrp_regime(
            iv_percent=float(iv_percent) if iv_percent is not None else None,
            rv_percent=float(rv_percent) if rv_percent is not None else None,
            stress_sigma=raw.get("sigma_position"),
        )
        rows.append(
            {
                **raw,
                "vrp": (iv_percent - rv_percent)
                if iv_percent is not None and rv_percent is not None
                else None,
                "vol_regime": regime.value,
            }
        )
    return pl.DataFrame(rows, infer_schema_length=None) if rows else price


def add_bollinger_baseline(
    price: pl.DataFrame,
    *,
    window: int = 20,
    width: float = 2.0,
) -> pl.DataFrame:
    """Add a simple rolling SD/Bollinger-style control baseline."""

    if window <= 1:
        raise ValueError("window must be greater than 1")
    if price.is_empty():
        return price
    return (
        price.sort("timestamp")
        .with_columns(
            pl.col("close").rolling_mean(window_size=window).alias("bb_mid"),
            pl.col("close").rolling_std(window_size=window).alias("bb_std"),
        )
        .with_columns(
            (pl.col("bb_mid") + width * pl.col("bb_std")).alias("bb_upper"),
            (pl.col("bb_mid") - width * pl.col("bb_std")).alias("bb_lower"),
        )
    )
