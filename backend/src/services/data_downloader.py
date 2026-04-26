import polars as pl
from datetime import datetime

from backend.src.services.binance_client import BinanceClient
from backend.src.repositories.parquet_repo import ParquetRepository


class DataDownloader:
    """Orchestrate data download from Binance."""
    
    def __init__(self):
        self.binance_client = BinanceClient()
        self.parquet_repo = ParquetRepository()
    
    async def download_all(
        self,
        symbol: str = "BTCUSDT",
        interval: str = "15m",
        days: int = 30,
    ) -> dict:
        """Download all data types (OHLCV, OI, Funding)."""
        results = {}
        
        # Download OHLCV
        ohlcv_data = await self.binance_client.download_ohlcv(
            symbol=symbol,
            interval=interval,
            days=days,
        )
        if not ohlcv_data.is_empty():
            self.parquet_repo.save_ohlcv(ohlcv_data, symbol=symbol, interval=interval)
            results["ohlcv"] = len(ohlcv_data)
        
        # Download Open Interest
        oi_data = await self.binance_client.download_open_interest(
            symbol=symbol,
            period=interval,
            days=days,
        )
        if not oi_data.is_empty():
            self.parquet_repo.save_open_interest(oi_data, symbol=symbol, interval=interval)
            results["open_interest"] = len(oi_data)
        
        # Download Funding Rate
        funding_data = await self.binance_client.download_funding_rate(
            symbol=symbol,
            days=days,
        )
        if not funding_data.is_empty():
            self.parquet_repo.save_funding_rate(funding_data, symbol=symbol, interval=interval)
            results["funding_rate"] = len(funding_data)
        
        await self.binance_client.close()
        return results
    
    async def download_ohlcv(
        self,
        symbol: str = "BTCUSDT",
        interval: str = "15m",
        days: int = 30,
    ) -> int:
        """Download OHLCV data only."""
        data = await self.binance_client.download_ohlcv(
            symbol=symbol,
            interval=interval,
            days=days,
        )
        if not data.is_empty():
            self.parquet_repo.save_ohlcv(data, symbol=symbol, interval=interval)
        await self.binance_client.close()
        return len(data)
    
    async def download_open_interest(
        self,
        symbol: str = "BTCUSDT",
        interval: str = "15m",
        days: int = 30,
    ) -> int:
        """Download open interest data only."""
        data = await self.binance_client.download_open_interest(
            symbol=symbol,
            period=interval,
            days=days,
        )
        if not data.is_empty():
            self.parquet_repo.save_open_interest(data, symbol=symbol, interval=interval)
        await self.binance_client.close()
        return len(data)
    
    async def download_funding_rate(
        self,
        symbol: str = "BTCUSDT",
        days: int = 30,
    ) -> int:
        """Download funding rate data only."""
        data = await self.binance_client.download_funding_rate(
            symbol=symbol,
            days=days,
        )
        if not data.is_empty():
            self.parquet_repo.save_funding_rate(data, symbol=symbol)
        await self.binance_client.close()
        return len(data)
