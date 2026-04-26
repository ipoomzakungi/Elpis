from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from src.api.validation import (
    parse_time_range,
    validate_interval,
    validate_regime_filter,
    validate_symbol,
)
from src.models.features import RegimeResponse
from src.repositories.parquet_repo import ParquetRepository

router = APIRouter()


@router.get("/regimes", response_model=RegimeResponse)
async def get_regimes(
    symbol: str = Query(default="BTCUSDT"),
    interval: str = Query(default="15m"),
    start_time: Optional[str] = Query(default=None),
    end_time: Optional[str] = Query(default=None),
    regime: Optional[str] = Query(default=None),
    limit: int = Query(default=1000, ge=1, le=5000),
):
    """Get regime classifications."""
    symbol = validate_symbol(symbol)
    interval = validate_interval(interval)
    regime = validate_regime_filter(regime)
    start_dt, end_dt = parse_time_range(start_time, end_time)

    parquet_repo = ParquetRepository()
    df = parquet_repo.load_features(symbol=symbol, interval=interval)

    if df is None:
        raise HTTPException(
            status_code=404,
            detail="No features found. Run /process first.",
        )

    # Filter by time range
    if start_dt:
        df = df.filter(df["timestamp"] >= start_dt)
    if end_dt:
        df = df.filter(df["timestamp"] <= end_dt)

    # Filter by regime type
    if regime:
        df = df.filter(df["regime"] == regime)

    # Sort and limit
    df = df.sort("timestamp", descending=True).head(limit)

    # Convert to response
    data = df.select(["timestamp", "regime", "confidence", "reason"]).to_dicts()

    # Calculate regime counts
    regime_counts = df.group_by("regime").len().to_dicts()
    counts = {r["regime"]: r["len"] for r in regime_counts}

    return RegimeResponse(
        data=data,
        meta={
            "symbol": symbol,
            "interval": interval,
            "count": len(data),
            "regime_counts": counts,
        },
    )
