from datetime import datetime
import logging

import httpx
from fastapi import APIRouter, HTTPException, Query, status
from typing import Optional

from src.api.validation import parse_time_range, validate_interval, validate_symbol
from src.models.market_data import (
    DownloadRequest,
    DownloadResponse,
    MarketDataResponse,
    OpenInterestResponse,
    FundingRateResponse,
)
from src.services.data_downloader import DataDownloader
from src.api.dependencies import get_parquet_repo

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/download", response_model=DownloadResponse, status_code=status.HTTP_202_ACCEPTED)
async def download_data(request: DownloadRequest):
    """Download market data from Binance Futures."""
    try:
        downloader = DataDownloader()
        task_id = f"download_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

        # Start download in background
        await downloader.download_all(
            symbol=request.symbol,
            interval=request.interval,
            days=request.days,
        )

        return DownloadResponse(
            status="completed",
            task_id=task_id,
            message=f"Downloaded {request.days} days of {request.symbol} {request.interval} data",
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 429:
            logger.warning("Binance rate limit while downloading %s", request.symbol)
            raise HTTPException(status_code=429, detail="Binance API rate limit reached") from exc
        logger.exception("Binance API error while downloading %s", request.symbol)
        raise HTTPException(status_code=500, detail="Data download failed") from exc
    except Exception as exc:
        logger.exception("Data download failed for %s", request.symbol)
        raise HTTPException(status_code=500, detail="Data download failed") from exc


@router.get("/market-data/ohlcv", response_model=MarketDataResponse)
async def get_ohlcv(
    symbol: str = Query(default="BTCUSDT"),
    interval: str = Query(default="15m"),
    start_time: Optional[str] = Query(default=None),
    end_time: Optional[str] = Query(default=None),
    limit: int = Query(default=1000, ge=1, le=5000),
):
    """Get OHLCV candlestick data."""
    symbol = validate_symbol(symbol)
    interval = validate_interval(interval)
    start_dt, end_dt = parse_time_range(start_time, end_time)

    repo = get_parquet_repo()
    df = repo.load_ohlcv(symbol=symbol, interval=interval)

    if df is None:
        raise HTTPException(status_code=404, detail="No OHLCV data found. Run /download first.")

    # Filter by time range
    if start_dt:
        df = df.filter(df["timestamp"] >= start_dt)
    if end_dt:
        df = df.filter(df["timestamp"] <= end_dt)

    # Sort and limit
    df = df.sort("timestamp", descending=True).head(limit)

    # Convert to response
    data = df.to_dicts()

    return MarketDataResponse(
        data=data,
        meta={
            "symbol": symbol,
            "interval": interval,
            "count": len(data),
        },
    )


@router.get("/market-data/open-interest", response_model=OpenInterestResponse)
async def get_open_interest(
    symbol: str = Query(default="BTCUSDT"),
    interval: str = Query(default="15m"),
    start_time: Optional[str] = Query(default=None),
    end_time: Optional[str] = Query(default=None),
    limit: int = Query(default=1000, ge=1, le=5000),
):
    """Get open interest data."""
    symbol = validate_symbol(symbol)
    interval = validate_interval(interval)
    start_dt, end_dt = parse_time_range(start_time, end_time)

    repo = get_parquet_repo()
    df = repo.load_open_interest(symbol=symbol, interval=interval)

    if df is None:
        raise HTTPException(
            status_code=404, detail="No open interest data found. Run /download first."
        )

    if start_dt:
        df = df.filter(df["timestamp"] >= start_dt)
    if end_dt:
        df = df.filter(df["timestamp"] <= end_dt)

    df = df.sort("timestamp", descending=True).head(limit)
    data = df.to_dicts()

    return OpenInterestResponse(
        data=data,
        meta={
            "symbol": symbol,
            "interval": interval,
            "count": len(data),
        },
    )


@router.get("/market-data/funding-rate", response_model=FundingRateResponse)
async def get_funding_rate(
    symbol: str = Query(default="BTCUSDT"),
    start_time: Optional[str] = Query(default=None),
    end_time: Optional[str] = Query(default=None),
    limit: int = Query(default=1000, ge=1, le=5000),
):
    """Get funding rate data."""
    symbol = validate_symbol(symbol)
    start_dt, end_dt = parse_time_range(start_time, end_time)

    repo = get_parquet_repo()
    df = repo.load_funding_rate(symbol=symbol)

    if df is None:
        raise HTTPException(
            status_code=404, detail="No funding rate data found. Run /download first."
        )

    if start_dt:
        df = df.filter(df["timestamp"] >= start_dt)
    if end_dt:
        df = df.filter(df["timestamp"] <= end_dt)

    df = df.sort("timestamp", descending=True).head(limit)
    data = df.to_dicts()

    return FundingRateResponse(
        data=data,
        meta={
            "symbol": symbol,
            "count": len(data),
        },
    )
