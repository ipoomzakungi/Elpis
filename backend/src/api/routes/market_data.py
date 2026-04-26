from datetime import datetime
from fastapi import APIRouter, HTTPException, Query
from typing import Optional

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


@router.post("/download", response_model=DownloadResponse)
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/market-data/ohlcv", response_model=MarketDataResponse)
async def get_ohlcv(
    symbol: str = Query(default="BTCUSDT"),
    interval: str = Query(default="15m"),
    start_time: Optional[str] = Query(default=None),
    end_time: Optional[str] = Query(default=None),
    limit: int = Query(default=1000, ge=1, le=5000),
):
    """Get OHLCV candlestick data."""
    repo = get_parquet_repo()
    df = repo.load_ohlcv(symbol=symbol, interval=interval)
    
    if df is None:
        raise HTTPException(status_code=404, detail="No OHLCV data found. Run /download first.")
    
    # Filter by time range
    if start_time:
        start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        df = df.filter(df["timestamp"] >= start_dt)
    if end_time:
        end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
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
    repo = get_parquet_repo()
    df = repo.load_open_interest(symbol=symbol, interval=interval)
    
    if df is None:
        raise HTTPException(status_code=404, detail="No open interest data found. Run /download first.")
    
    if start_time:
        start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        df = df.filter(df["timestamp"] >= start_dt)
    if end_time:
        end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
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
    repo = get_parquet_repo()
    df = repo.load_funding_rate(symbol=symbol)
    
    if df is None:
        raise HTTPException(status_code=404, detail="No funding rate data found. Run /download first.")
    
    if start_time:
        start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        df = df.filter(df["timestamp"] >= start_dt)
    if end_time:
        end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
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
