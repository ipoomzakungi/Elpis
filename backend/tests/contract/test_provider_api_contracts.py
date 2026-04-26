from fastapi.testclient import TestClient

from src.api.routes import market_data
from src.api.routes import providers as provider_routes
from src.main import app
from src.models.providers import (
    DataArtifact,
    ProviderDataType,
    ProviderDownloadResult,
    ProviderDownloadStatus,
    UnsupportedCapability,
)
from src.repositories.parquet_repo import ParquetRepository


def test_backward_compatible_download_endpoint_contract(
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
        response = client.post(
            "/api/v1/download",
            json={"symbol": "BTCUSDT", "interval": "15m", "days": 1},
        )

    payload = response.json()
    assert response.status_code == 202
    assert payload["status"] == "completed"
    assert payload["task_id"].startswith("download_")
    assert "Downloaded" in payload["message"]


def test_provider_aware_binance_download_endpoint_contract(monkeypatch):
    class FakeDownloader:
        async def download_provider_data(self, request):
            return ProviderDownloadResult(
                status=ProviderDownloadStatus.COMPLETED,
                provider="binance",
                symbol="BTCUSDT",
                timeframe="15m",
                completed_data_types=[
                    ProviderDataType.OHLCV,
                    ProviderDataType.OPEN_INTEREST,
                    ProviderDataType.FUNDING_RATE,
                ],
                skipped_data_types=[],
                artifacts=[
                    DataArtifact(
                        data_type=ProviderDataType.OHLCV,
                        path="data/raw/btcusdt_15m_ohlcv.parquet",
                        rows=30,
                        provider="binance",
                        symbol="BTCUSDT",
                        timeframe="15m",
                    )
                ],
                message="Downloaded Binance research data",
                warnings=[],
            )

    monkeypatch.setattr(provider_routes, "DataDownloader", FakeDownloader)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/data/download",
            json={
                "provider": "binance",
                "symbol": "BTCUSDT",
                "timeframe": "15m",
                "days": 1,
                "data_types": ["ohlcv", "open_interest", "funding_rate"],
            },
        )

    payload = response.json()
    assert response.status_code == 200
    assert payload["status"] == "completed"
    assert payload["provider"] == "binance"
    assert payload["completed_data_types"] == ["ohlcv", "open_interest", "funding_rate"]
    assert payload["artifacts"][0]["path"] == "data/raw/btcusdt_15m_ohlcv.parquet"


def test_provider_aware_yahoo_download_endpoint_contract(monkeypatch):
    class FakeDownloader:
        async def download_provider_data(self, request):
            return ProviderDownloadResult(
                status=ProviderDownloadStatus.PARTIAL,
                provider="yahoo_finance",
                symbol="SPY",
                timeframe="1d",
                completed_data_types=[ProviderDataType.OHLCV],
                skipped_data_types=[
                    UnsupportedCapability(
                        provider="yahoo_finance",
                        data_type=ProviderDataType.OPEN_INTEREST,
                        reason=(
                            "Yahoo Finance does not provide open interest for this research layer"
                        ),
                    ),
                    UnsupportedCapability(
                        provider="yahoo_finance",
                        data_type=ProviderDataType.FUNDING_RATE,
                        reason="Yahoo Finance does not provide funding rates",
                    ),
                ],
                artifacts=[
                    DataArtifact(
                        data_type=ProviderDataType.OHLCV,
                        path="data/raw/yahoo_finance_spy_1d_ohlcv.parquet",
                        rows=252,
                        provider="yahoo_finance",
                        symbol="SPY",
                        timeframe="1d",
                    )
                ],
                message="Downloaded supported Yahoo Finance data; skipped unsupported capabilities",
                warnings=[],
            )

    monkeypatch.setattr(provider_routes, "DataDownloader", FakeDownloader)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/data/download",
            json={
                "provider": "yahoo_finance",
                "symbol": "SPY",
                "timeframe": "1d",
                "days": 365,
                "data_types": ["ohlcv", "open_interest", "funding_rate"],
            },
        )

    payload = response.json()
    assert response.status_code == 200
    assert payload["status"] == "partial"
    assert payload["completed_data_types"] == ["ohlcv"]
    assert payload["skipped_data_types"][0]["data_type"] == "open_interest"
    assert payload["artifacts"][0]["path"] == "data/raw/yahoo_finance_spy_1d_ohlcv.parquet"


def test_provider_aware_local_file_download_endpoint_contract(monkeypatch):
    class FakeDownloader:
        async def download_provider_data(self, request):
            return ProviderDownloadResult(
                status=ProviderDownloadStatus.COMPLETED,
                provider="local_file",
                symbol="SAMPLE",
                timeframe="1d",
                completed_data_types=[ProviderDataType.OHLCV],
                skipped_data_types=[],
                artifacts=[
                    DataArtifact(
                        data_type=ProviderDataType.OHLCV,
                        path="data/raw/local_file_sample_1d_ohlcv.parquet",
                        rows=2,
                        provider="local_file",
                        symbol="SAMPLE",
                        timeframe="1d",
                    )
                ],
                message="Downloaded Local File research data",
                warnings=[],
            )

    monkeypatch.setattr(provider_routes, "DataDownloader", FakeDownloader)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/data/download",
            json={
                "provider": "local_file",
                "symbol": "SAMPLE",
                "timeframe": "1d",
                "local_file_path": "data/imports/sample_ohlcv.csv",
                "data_types": ["ohlcv"],
            },
        )

    payload = response.json()
    assert response.status_code == 200
    assert payload["status"] == "completed"
    assert payload["provider"] == "local_file"
    assert payload["artifacts"][0]["path"] == "data/raw/local_file_sample_1d_ohlcv.parquet"


def test_list_providers_contract():
    with TestClient(app) as client:
        response = client.get("/api/v1/providers")

    payload = response.json()
    providers = {provider["provider"]: provider for provider in payload["providers"]}
    assert response.status_code == 200
    assert {"binance", "yahoo_finance", "local_file"}.issubset(providers)
    assert providers["binance"]["supports_open_interest"] is True
    assert providers["yahoo_finance"]["supports_open_interest"] is False
    assert providers["local_file"]["requires_auth"] is False


def test_get_provider_details_contract():
    with TestClient(app) as client:
        response = client.get("/api/v1/providers/yahoo_finance")

    payload = response.json()
    assert response.status_code == 200
    assert payload["provider"] == "yahoo_finance"
    assert payload["supports_ohlcv"] is True
    assert payload["supports_open_interest"] is False
    assert payload["capabilities"][1]["data_type"] == "open_interest"


def test_get_provider_symbols_contract():
    with TestClient(app) as client:
        response = client.get("/api/v1/providers/yahoo_finance/symbols")

    payload = response.json()
    symbols = {symbol["symbol"]: symbol for symbol in payload["symbols"]}
    assert response.status_code == 200
    assert payload["provider"] == "yahoo_finance"
    assert {"SPY", "GC=F"}.issubset(symbols)
    assert symbols["SPY"]["supports_open_interest"] is False


def test_unknown_provider_contract_returns_structured_error():
    with TestClient(app) as client:
        response = client.get("/api/v1/providers/unknown")

    payload = response.json()
    assert response.status_code == 404
    assert payload["error"]["code"] == "PROVIDER_NOT_FOUND"
    assert "unknown" in payload["error"]["message"]
