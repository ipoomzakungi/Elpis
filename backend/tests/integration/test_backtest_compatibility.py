from fastapi.testclient import TestClient

from src.api.routes import market_data
from src.main import app
from src.repositories.parquet_repo import ParquetRepository


def test_backtest_feature_preserves_existing_research_api_flows(
	monkeypatch,
	sample_ohlcv,
	sample_open_interest,
	sample_funding_rate,
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
				"funding_rate": len(sample_funding_rate),
			}

	monkeypatch.setattr(market_data, "DataDownloader", FakeDownloader)

	with TestClient(app) as client:
		providers = client.get("/api/v1/providers")
		provider = client.get("/api/v1/providers/binance")
		symbols = client.get("/api/v1/providers/binance/symbols")
		download = client.post(
			"/api/v1/download",
			json={"symbol": "BTCUSDT", "interval": "15m", "days": 1},
		)
		process = client.post(
			"/api/v1/process",
			json={"symbol": "BTCUSDT", "interval": "15m"},
		)

		dashboard_endpoints = [
			"/api/v1/market-data/ohlcv?limit=5",
			"/api/v1/market-data/open-interest?limit=5",
			"/api/v1/market-data/funding-rate?limit=5",
			"/api/v1/features?limit=5",
			"/api/v1/regimes?limit=5",
			"/api/v1/data-quality",
			"/api/v1/backtests",
		]
		dashboard_responses = [client.get(endpoint) for endpoint in dashboard_endpoints]

	assert providers.status_code == 200
	assert any(item["provider"] == "binance" for item in providers.json()["providers"])
	assert provider.status_code == 200
	assert provider.json()["provider"] == "binance"
	assert symbols.status_code == 200
	assert any(item["symbol"] == "BTCUSDT" for item in symbols.json()["symbols"])
	assert download.status_code == 202
	assert process.status_code == 202
	assert all(response.status_code == 200 for response in dashboard_responses)