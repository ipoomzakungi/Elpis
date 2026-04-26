import polars as pl

from src.repositories.parquet_repo import ParquetRepository
from src.services.feature_engine import FeatureEngine
from src.services.regime_classifier import RegimeClassifier


def test_feature_processing_flow_saves_classified_features(
    sample_ohlcv: pl.DataFrame,
    sample_open_interest: pl.DataFrame,
    sample_funding_rate: pl.DataFrame,
):
    repo = ParquetRepository()
    repo.save_ohlcv(sample_ohlcv)
    repo.save_open_interest(sample_open_interest)
    repo.save_funding_rate(sample_funding_rate)

    features = FeatureEngine().compute_all_features()
    assert features is not None

    classified = RegimeClassifier().classify_dataframe(features)
    feature_path = repo.save_features(classified)
    loaded = repo.load_features()

    assert feature_path.exists()
    assert loaded is not None
    assert not loaded.is_empty()
    assert {"regime", "confidence", "reason"}.issubset(loaded.columns)
