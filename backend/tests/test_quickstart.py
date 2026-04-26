import polars as pl
from fastapi.testclient import TestClient

from src.api.routes import market_data
from src.config import get_settings
from src.main import app
from src.repositories.parquet_repo import ParquetRepository


def test_quickstart_backend_flow(
    monkeypatch,
    sample_ohlcv: pl.DataFrame,
    sample_open_interest: pl.DataFrame,
    sample_funding_rate: pl.DataFrame,
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
        assert client.get("/health").status_code == 200
        assert client.get("/docs").status_code == 200

        download_response = client.post(
            "/api/v1/download",
            json={"symbol": "BTCUSDT", "interval": "15m", "days": 1},
        )
        assert download_response.status_code == 202

        settings = get_settings()
        assert (settings.data_raw_path / "btcusdt_15m_ohlcv.parquet").exists()
        assert (settings.data_raw_path / "btcusdt_15m_oi.parquet").exists()
        assert (settings.data_raw_path / "btcusdt_15m_funding.parquet").exists()

        process_response = client.post(
            "/api/v1/process",
            json={"symbol": "BTCUSDT", "interval": "15m"},
        )
        assert process_response.status_code == 202
        assert (settings.data_processed_path / "btcusdt_15m_features.parquet").exists()

        for endpoint in [
            "/api/v1/market-data/ohlcv?limit=5",
            "/api/v1/market-data/open-interest?limit=5",
            "/api/v1/market-data/funding-rate?limit=5",
            "/api/v1/features?limit=5",
            "/api/v1/regimes?limit=5",
            "/api/v1/data-quality",
        ]:
            assert client.get(endpoint).status_code == 200
