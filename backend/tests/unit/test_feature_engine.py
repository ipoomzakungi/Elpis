from datetime import datetime

import polars as pl
import pytest

from src.repositories.parquet_repo import ParquetRepository
from src.services.feature_engine import FeatureEngine


def test_compute_atr_adds_expected_rolling_values(sample_ohlcv: pl.DataFrame):
    engine = FeatureEngine()

    result = engine.compute_atr(sample_ohlcv, period=3)

    assert "atr" in result.columns
    assert result["atr"][0] is None
    assert result["atr"][2] == pytest.approx(2.5)


def test_compute_range_levels_adds_high_low_mid(sample_ohlcv: pl.DataFrame):
    engine = FeatureEngine()

    result = engine.compute_range_levels(sample_ohlcv, period=3)

    row = result.row(2, named=True)

    assert row["range_high"] == pytest.approx(103.5)
    assert row["range_low"] == pytest.approx(99.0)
    assert row["range_mid"] == pytest.approx(101.25)


def test_compute_oi_change_uses_previous_open_interest(sample_open_interest: pl.DataFrame):
    engine = FeatureEngine()

    result = engine.compute_oi_change(sample_open_interest)

    assert result["oi_change_pct"][0] is None
    assert result["oi_change_pct"][1] == pytest.approx(1.0)


def test_compute_volume_ratio_uses_rolling_average(sample_ohlcv: pl.DataFrame):
    engine = FeatureEngine()

    result = engine.compute_volume_ratio(sample_ohlcv, period=3)

    assert result["volume_ratio"][0] is None
    assert result["volume_ratio"][2] == pytest.approx(102.0 / 101.0)


def test_compute_funding_features_forward_fills_before_derivatives():
    engine = FeatureEngine()
    data = pl.DataFrame(
        {
            "timestamp": [
                datetime(2026, 4, 1, 0, 0),
                datetime(2026, 4, 1, 0, 15),
                datetime(2026, 4, 1, 0, 30),
            ],
            "funding_rate": [0.001, None, 0.002],
        }
    )

    result = engine.compute_funding_features(data)

    assert result["funding_rate"].to_list() == [0.001, 0.001, 0.002]
    assert result["funding_rate_change"][1] == pytest.approx(0.0)
    assert result["funding_rate_cumsum"][2] == pytest.approx(0.004)


def test_merge_data_combines_raw_inputs(
    sample_ohlcv: pl.DataFrame,
    sample_open_interest: pl.DataFrame,
    sample_funding_rate: pl.DataFrame,
):
    engine = FeatureEngine()

    result = engine.merge_data(sample_ohlcv, sample_open_interest, sample_funding_rate)

    assert "open_interest" in result.columns
    assert "funding_rate" in result.columns
    assert result["funding_rate"][1] == pytest.approx(0.0001)


def test_compute_all_features_from_parquet(
    sample_ohlcv: pl.DataFrame,
    sample_open_interest: pl.DataFrame,
    sample_funding_rate: pl.DataFrame,
):
    repo = ParquetRepository()
    repo.save_ohlcv(sample_ohlcv)
    repo.save_open_interest(sample_open_interest)
    repo.save_funding_rate(sample_funding_rate)
    engine = FeatureEngine()

    result = engine.compute_all_features()

    assert result is not None
    assert not result.is_empty()
    assert {"atr", "range_high", "oi_change_pct", "volume_ratio", "funding_rate_cumsum"}.issubset(
        result.columns
    )


def test_compute_atr_rejects_missing_columns():
    engine = FeatureEngine()

    with pytest.raises(ValueError, match="Missing columns"):
        engine.compute_atr(pl.DataFrame({"high": [1.0]}))
