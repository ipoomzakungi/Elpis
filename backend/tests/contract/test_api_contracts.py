import polars as pl
from fastapi.testclient import TestClient

from src.api.routes import market_data
from src.main import app
from src.repositories.parquet_repo import ParquetRepository
from src.services.feature_engine import FeatureEngine
from src.services.regime_classifier import RegimeClassifier


def seed_raw_data(
    sample_ohlcv: pl.DataFrame,
    sample_open_interest: pl.DataFrame,
    sample_funding_rate: pl.DataFrame,
) -> ParquetRepository:
    repo = ParquetRepository()
    repo.save_ohlcv(sample_ohlcv)
    repo.save_open_interest(sample_open_interest)
    repo.save_funding_rate(sample_funding_rate)
    return repo


def seed_processed_data(
    sample_ohlcv: pl.DataFrame,
    sample_open_interest: pl.DataFrame,
    sample_funding_rate: pl.DataFrame,
) -> ParquetRepository:
    repo = seed_raw_data(sample_ohlcv, sample_open_interest, sample_funding_rate)
    features = FeatureEngine().compute_all_features()
    assert features is not None
    classified = RegimeClassifier().classify_dataframe(features)
    repo.save_features(classified)
    return repo


def test_download_endpoint_contract(
    monkeypatch, sample_ohlcv, sample_open_interest, sample_funding_rate
):
    class FakeDownloader:
        async def download_all(self, symbol: str, interval: str, days: int) -> dict:
            repo = ParquetRepository()
            repo.save_ohlcv(sample_ohlcv, symbol=symbol, interval=interval)
            repo.save_open_interest(sample_open_interest, symbol=symbol, interval=interval)
            repo.save_funding_rate(sample_funding_rate, symbol=symbol, interval=interval)
            return {
                "ohlcv": len(sample_ohlcv),
                "open_interest": len(sample_open_interest),
                "funding_rate": 1,
            }

    monkeypatch.setattr(market_data, "DataDownloader", FakeDownloader)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/download", json={"symbol": "BTCUSDT", "interval": "15m", "days": 1}
        )

    payload = response.json()
    assert response.status_code == 202
    assert payload["status"] == "completed"
    assert payload["task_id"].startswith("download_")
    assert "Downloaded" in payload["message"]


def test_process_endpoint_contract(sample_ohlcv, sample_open_interest, sample_funding_rate):
    seed_raw_data(sample_ohlcv, sample_open_interest, sample_funding_rate)

    with TestClient(app) as client:
        response = client.post("/api/v1/process", json={"symbol": "BTCUSDT", "interval": "15m"})

    payload = response.json()
    assert response.status_code == 202
    assert payload["status"] == "completed"
    assert payload["task_id"].startswith("process_")


def test_market_data_query_contracts(sample_ohlcv, sample_open_interest, sample_funding_rate):
    seed_raw_data(sample_ohlcv, sample_open_interest, sample_funding_rate)

    with TestClient(app) as client:
        ohlcv = client.get("/api/v1/market-data/ohlcv?limit=5")
        open_interest = client.get("/api/v1/market-data/open-interest?limit=5")
        funding_rate = client.get("/api/v1/market-data/funding-rate?limit=5")

    for response in [ohlcv, open_interest, funding_rate]:
        payload = response.json()
        assert response.status_code == 200
        assert isinstance(payload["data"], list)
        assert payload["meta"]["count"] <= 5


def test_features_and_regimes_contracts(sample_ohlcv, sample_open_interest, sample_funding_rate):
    seed_processed_data(sample_ohlcv, sample_open_interest, sample_funding_rate)

    with TestClient(app) as client:
        features = client.get("/api/v1/features?limit=5")
        regimes = client.get("/api/v1/regimes?limit=5")

    features_payload = features.json()
    regimes_payload = regimes.json()
    assert features.status_code == 200
    assert regimes.status_code == 200
    assert {"data", "meta"}.issubset(features_payload)
    assert {"data", "meta"}.issubset(regimes_payload)
    assert "regime_counts" in regimes_payload["meta"]


def test_data_quality_contract(sample_ohlcv, sample_open_interest, sample_funding_rate):
    seed_raw_data(sample_ohlcv, sample_open_interest, sample_funding_rate)

    with TestClient(app) as client:
        response = client.get("/api/v1/data-quality")

    payload = response.json()
    assert response.status_code == 200
    assert {"ohlcv", "open_interest", "funding_rate"}.issubset(payload)
    assert payload["ohlcv"]["total_records"] == 30


def test_validation_error_contract():
    with TestClient(app) as client:
        response = client.get("/api/v1/features?symbol=ETHUSDT")

    payload = response.json()
    assert response.status_code == 400
    assert payload["error"]["code"] == "VALIDATION_ERROR"
    assert "BTCUSDT" in payload["error"]["message"]
