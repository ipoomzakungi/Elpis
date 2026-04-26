import logging

from src.services.binance_client import BinanceClient
from src.repositories.parquet_repo import ParquetRepository


logger = logging.getLogger(__name__)


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

        try:
            logger.info(
                "Starting full data download for %s %s over %s days", symbol, interval, days
            )

            ohlcv_data = await self.binance_client.download_ohlcv(
                symbol=symbol,
                interval=interval,
                days=days,
            )
            if not ohlcv_data.is_empty():
                self.parquet_repo.save_ohlcv(ohlcv_data, symbol=symbol, interval=interval)
                results["ohlcv"] = len(ohlcv_data)
            else:
                logger.warning("No OHLCV data downloaded for %s %s", symbol, interval)

            oi_data = await self.binance_client.download_open_interest(
                symbol=symbol,
                period=interval,
                days=days,
            )
            if not oi_data.is_empty():
                self.parquet_repo.save_open_interest(oi_data, symbol=symbol, interval=interval)
                results["open_interest"] = len(oi_data)
            else:
                logger.warning("No open interest data downloaded for %s %s", symbol, interval)

            funding_data = await self.binance_client.download_funding_rate(
                symbol=symbol,
                days=days,
            )
            if not funding_data.is_empty():
                self.parquet_repo.save_funding_rate(funding_data, symbol=symbol, interval=interval)
                results["funding_rate"] = len(funding_data)
            else:
                logger.warning("No funding rate data downloaded for %s", symbol)

            if not results:
                raise RuntimeError("No data downloaded from Binance")

            logger.info("Completed data download for %s: %s", symbol, results)
            return results
        except Exception:
            logger.exception("Data download failed for %s %s", symbol, interval)
            raise
        finally:
            await self.binance_client.close()

    async def download_ohlcv(
        self,
        symbol: str = "BTCUSDT",
        interval: str = "15m",
        days: int = 30,
    ) -> int:
        """Download OHLCV data only."""
        try:
            data = await self.binance_client.download_ohlcv(
                symbol=symbol,
                interval=interval,
                days=days,
            )
            if not data.is_empty():
                self.parquet_repo.save_ohlcv(data, symbol=symbol, interval=interval)
            return len(data)
        except Exception:
            logger.exception("OHLCV download failed for %s %s", symbol, interval)
            raise
        finally:
            await self.binance_client.close()

    async def download_open_interest(
        self,
        symbol: str = "BTCUSDT",
        interval: str = "15m",
        days: int = 30,
    ) -> int:
        """Download open interest data only."""
        try:
            data = await self.binance_client.download_open_interest(
                symbol=symbol,
                period=interval,
                days=days,
            )
            if not data.is_empty():
                self.parquet_repo.save_open_interest(data, symbol=symbol, interval=interval)
            return len(data)
        except Exception:
            logger.exception("Open interest download failed for %s %s", symbol, interval)
            raise
        finally:
            await self.binance_client.close()

    async def download_funding_rate(
        self,
        symbol: str = "BTCUSDT",
        days: int = 30,
    ) -> int:
        """Download funding rate data only."""
        try:
            data = await self.binance_client.download_funding_rate(
                symbol=symbol,
                days=days,
            )
            if not data.is_empty():
                self.parquet_repo.save_funding_rate(data, symbol=symbol)
            return len(data)
        except Exception:
            logger.exception("Funding rate download failed for %s", symbol)
            raise
        finally:
            await self.binance_client.close()
