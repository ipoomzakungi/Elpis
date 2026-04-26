import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

import httpx
import polars as pl

from src.config import get_settings


logger = logging.getLogger(__name__)


class BinanceClient:
    """Binance Futures API client with rate limiting."""

    def __init__(self):
        self.settings = get_settings()
        self.base_url = self.settings.binance_base_url
        self.rate_limit = self.settings.binance_rate_limit
        self.request_count = 0
        self.last_reset = datetime.utcnow()
        self.client = httpx.AsyncClient(timeout=30.0)

    async def _request_json(self, path: str, params: dict) -> list | dict:
        """Execute a Binance API request and return JSON data."""
        await self._check_rate_limit()

        try:
            response = await self.client.get(f"{self.base_url}{path}", params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError:
            logger.exception("Binance API returned an error for %s", path)
            raise
        except httpx.HTTPError:
            logger.exception("Binance API request failed for %s", path)
            raise

    async def _check_rate_limit(self):
        """Check and enforce rate limiting."""
        now = datetime.utcnow()
        if (now - self.last_reset).total_seconds() >= 60:
            self.request_count = 0
            self.last_reset = now

        if self.request_count >= self.rate_limit:
            wait_time = 60 - (now - self.last_reset).total_seconds()
            if wait_time > 0:
                await asyncio.sleep(wait_time)
            self.request_count = 0
            self.last_reset = datetime.utcnow()

        self.request_count += 1

    async def get_klines(
        self,
        symbol: str = "BTCUSDT",
        interval: str = "15m",
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 1500,
    ) -> list[list]:
        """Get kline/candlestick data."""
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        }
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time

        data = await self._request_json("/fapi/v1/klines", params)
        return data if isinstance(data, list) else []

    async def get_open_interest_history(
        self,
        symbol: str = "BTCUSDT",
        period: str = "15m",
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 500,
    ) -> list[dict]:
        """Get open interest history."""
        params = {
            "symbol": symbol,
            "period": period,
            "limit": limit,
        }
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time

        data = await self._request_json("/futures/data/openInterestHist", params)
        return data if isinstance(data, list) else []

    async def get_funding_rate(
        self,
        symbol: str = "BTCUSDT",
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 1000,
    ) -> list[dict]:
        """Get funding rate history."""
        params = {
            "symbol": symbol,
            "limit": limit,
        }
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time

        data = await self._request_json("/fapi/v1/fundingRate", params)
        return data if isinstance(data, list) else []

    async def download_ohlcv(
        self,
        symbol: str = "BTCUSDT",
        interval: str = "15m",
        days: int = 30,
    ) -> pl.DataFrame:
        """Download OHLCV data for specified number of days."""
        logger.info("Downloading OHLCV data for %s %s over %s days", symbol, interval, days)
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=days)

        start_ms = int(start_time.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)

        all_data = []
        current_start = start_ms

        while current_start < end_ms:
            data = await self.get_klines(
                symbol=symbol,
                interval=interval,
                start_time=current_start,
                end_time=end_ms,
                limit=1500,
            )
            if not data:
                break

            all_data.extend(data)
            current_start = data[-1][0] + 1  # Next millisecond after last candle

            # Small delay to be nice to the API
            await asyncio.sleep(0.1)

        if not all_data:
            return pl.DataFrame()

        try:
            df = pl.DataFrame(
                {
                    "timestamp": [datetime.fromtimestamp(d[0] / 1000) for d in all_data],
                    "open": [float(d[1]) for d in all_data],
                    "high": [float(d[2]) for d in all_data],
                    "low": [float(d[3]) for d in all_data],
                    "close": [float(d[4]) for d in all_data],
                    "volume": [float(d[5]) for d in all_data],
                    "quote_volume": [float(d[7]) for d in all_data],
                    "trades": [int(d[8]) for d in all_data],
                    "taker_buy_volume": [float(d[9]) for d in all_data],
                }
            )
        except (IndexError, TypeError, ValueError) as exc:
            logger.exception("Malformed OHLCV payload from Binance")
            raise ValueError("Malformed OHLCV payload from Binance") from exc

        # Remove duplicates and sort
        df = df.unique(subset=["timestamp"]).sort("timestamp")
        return df

    async def download_open_interest(
        self,
        symbol: str = "BTCUSDT",
        period: str = "15m",
        days: int = 30,
    ) -> pl.DataFrame:
        """Download open interest data for specified number of days."""
        logger.info("Downloading open interest data for %s %s over %s days", symbol, period, days)
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=days)

        start_ms = int(start_time.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)

        all_data = []
        current_start = start_ms

        while current_start < end_ms:
            data = await self.get_open_interest_history(
                symbol=symbol,
                period=period,
                start_time=current_start,
                end_time=end_ms,
                limit=500,
            )
            if not data:
                break

            all_data.extend(data)
            current_start = int(data[-1]["timestamp"]) + 1

            await asyncio.sleep(0.1)

        if not all_data:
            return pl.DataFrame()

        try:
            df = pl.DataFrame(
                {
                    "timestamp": [
                        datetime.fromtimestamp(int(d["timestamp"]) / 1000) for d in all_data
                    ],
                    "symbol": [d["symbol"] for d in all_data],
                    "open_interest": [float(d["sumOpenInterest"]) for d in all_data],
                    "open_interest_value": [float(d["sumOpenInterestValue"]) for d in all_data],
                }
            )
        except (KeyError, TypeError, ValueError) as exc:
            logger.exception("Malformed open interest payload from Binance")
            raise ValueError("Malformed open interest payload from Binance") from exc

        df = df.unique(subset=["timestamp"]).sort("timestamp")
        return df

    async def download_funding_rate(
        self,
        symbol: str = "BTCUSDT",
        days: int = 30,
    ) -> pl.DataFrame:
        """Download funding rate data for specified number of days."""
        logger.info("Downloading funding rate data for %s over %s days", symbol, days)
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=days)

        start_ms = int(start_time.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)

        all_data = []
        current_start = start_ms

        while current_start < end_ms:
            data = await self.get_funding_rate(
                symbol=symbol,
                start_time=current_start,
                end_time=end_ms,
                limit=1000,
            )
            if not data:
                break

            all_data.extend(data)
            current_start = int(data[-1]["fundingTime"]) + 1

            await asyncio.sleep(0.1)

        if not all_data:
            return pl.DataFrame()

        try:
            df = pl.DataFrame(
                {
                    "timestamp": [
                        datetime.fromtimestamp(int(d["fundingTime"]) / 1000) for d in all_data
                    ],
                    "symbol": [d["symbol"] for d in all_data],
                    "funding_rate": [float(d["fundingRate"]) for d in all_data],
                    "mark_price": [float(d["markPrice"]) for d in all_data],
                }
            )
        except (KeyError, TypeError, ValueError) as exc:
            logger.exception("Malformed funding rate payload from Binance")
            raise ValueError("Malformed funding rate payload from Binance") from exc

        df = df.unique(subset=["timestamp"]).sort("timestamp")
        return df

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
