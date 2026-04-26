from datetime import datetime
import logging

from fastapi import APIRouter, HTTPException, Query, status
from typing import Optional

from src.api.validation import parse_time_range, validate_interval, validate_symbol
from src.models.features import (
    ProcessRequest,
    ProcessResponse,
    FeatureResponse,
)
from src.services.feature_engine import FeatureEngine
from src.services.regime_classifier import RegimeClassifier
from src.repositories.parquet_repo import ParquetRepository

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/process", response_model=ProcessResponse, status_code=status.HTTP_202_ACCEPTED)
async def process_data(request: ProcessRequest):
    """Process raw data into features and classify regimes."""
    try:
        feature_engine = FeatureEngine()
        regime_classifier = RegimeClassifier()
        parquet_repo = ParquetRepository()

        # Compute features
        features_df = feature_engine.compute_all_features(
            symbol=request.symbol,
            interval=request.interval,
        )

        if features_df is None or features_df.is_empty():
            raise HTTPException(
                status_code=404,
                detail="No raw data found. Run /download first.",
            )

        # Classify regimes
        result_df = regime_classifier.classify_dataframe(features_df)

        # Save to Parquet
        parquet_repo.save_features(result_df, symbol=request.symbol, interval=request.interval)

        task_id = f"process_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

        return ProcessResponse(
            status="completed",
            task_id=task_id,
            message=f"Processed {len(result_df)} bars with features and regimes",
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Feature processing failed for %s %s", request.symbol, request.interval)
        raise HTTPException(status_code=500, detail="Data processing failed") from exc


@router.get("/features", response_model=FeatureResponse)
async def get_features(
    symbol: str = Query(default="BTCUSDT"),
    interval: str = Query(default="15m"),
    start_time: Optional[str] = Query(default=None),
    end_time: Optional[str] = Query(default=None),
    limit: int = Query(default=1000, ge=1, le=5000),
):
    """Get computed features."""
    symbol = validate_symbol(symbol)
    interval = validate_interval(interval)
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

    # Sort and limit
    df = df.sort("timestamp", descending=True).head(limit)

    # Convert to response
    data = df.to_dicts()

    return FeatureResponse(
        data=data,
        meta={
            "symbol": symbol,
            "interval": interval,
            "count": len(data),
        },
    )
