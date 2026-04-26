from datetime import datetime
from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from backend.src.models.features import (
    ProcessRequest,
    ProcessResponse,
    FeatureResponse,
)
from backend.src.services.feature_engine import FeatureEngine
from backend.src.services.regime_classifier import RegimeClassifier
from backend.src.repositories.parquet_repo import ParquetRepository

router = APIRouter()


@router.post("/process", response_model=ProcessResponse)
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/features", response_model=FeatureResponse)
async def get_features(
    symbol: str = Query(default="BTCUSDT"),
    interval: str = Query(default="15m"),
    start_time: Optional[str] = Query(default=None),
    end_time: Optional[str] = Query(default=None),
    limit: int = Query(default=1000, ge=1, le=5000),
):
    """Get computed features."""
    parquet_repo = ParquetRepository()
    df = parquet_repo.load_features(symbol=symbol, interval=interval)
    
    if df is None:
        raise HTTPException(
            status_code=404,
            detail="No features found. Run /process first.",
        )
    
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
    
    return FeatureResponse(
        data=data,
        meta={
            "symbol": symbol,
            "interval": interval,
            "count": len(data),
        },
    )
