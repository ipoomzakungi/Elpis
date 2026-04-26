from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class RegimeType(str, Enum):
    """Regime classification types."""
    
    RANGE = "RANGE"
    BREAKOUT_UP = "BREAKOUT_UP"
    BREAKOUT_DOWN = "BREAKOUT_DOWN"
    AVOID = "AVOID"


class Feature(BaseModel):
    """Computed features for a bar."""
    
    timestamp: datetime = Field(..., description="Bar time (UTC)")
    open: float = Field(..., gt=0, description="Opening price")
    high: float = Field(..., gt=0, description="Highest price")
    low: float = Field(..., gt=0, description="Lowest price")
    close: float = Field(..., gt=0, description="Closing price")
    volume: float = Field(..., ge=0, description="Trading volume")
    
    # Computed features
    atr: float = Field(..., ge=0, description="Average True Range (14-period)")
    range_high: float = Field(..., description="20-period rolling high")
    range_low: float = Field(..., description="20-period rolling low")
    range_mid: float = Field(..., description="Midpoint of range")
    
    # OI features
    open_interest: Optional[float] = Field(None, gt=0, description="Open interest")
    oi_change_pct: Optional[float] = Field(None, description="OI change percentage")
    
    # Volume features
    volume_ratio: float = Field(..., ge=0, description="Volume / 20-period avg")
    
    # Funding features
    funding_rate: Optional[float] = Field(None, ge=-0.05, le=0.05, description="Funding rate")
    funding_rate_change: Optional[float] = Field(None, description="Rate change from previous")
    funding_rate_cumsum: Optional[float] = Field(None, description="Cumulative funding rate")

    class Config:
        json_schema_extra = {
            "example": {
                "timestamp": "2026-04-26T00:00:00Z",
                "open": 65000.50,
                "high": 65100.00,
                "low": 64900.25,
                "close": 65050.75,
                "volume": 1234.567,
                "atr": 150.25,
                "range_high": 65200.00,
                "range_low": 64800.00,
                "range_mid": 65000.00,
                "open_interest": 12345.678,
                "oi_change_pct": 2.5,
                "volume_ratio": 1.35,
                "funding_rate": 0.00010000,
                "funding_rate_change": 0.00005000,
                "funding_rate_cumsum": 0.00350000,
            }
        }


class Regime(BaseModel):
    """Regime classification for a bar."""
    
    timestamp: datetime = Field(..., description="Bar time (UTC)")
    regime: RegimeType = Field(..., description="Regime classification")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Classification confidence")
    reason: Optional[str] = Field(None, description="Human-readable reason")

    class Config:
        json_schema_extra = {
            "example": {
                "timestamp": "2026-04-26T00:00:00Z",
                "regime": "RANGE",
                "confidence": 0.85,
                "reason": "Price near range mid, low OI change, normal volume",
            }
        }


class ProcessRequest(BaseModel):
    """Request to process data."""
    
    symbol: str = Field(default="BTCUSDT", description="Trading pair")
    interval: str = Field(default="15m", description="Timeframe")


class ProcessResponse(BaseModel):
    """Response for process request."""
    
    status: str = Field(..., description="Status of processing")
    task_id: str = Field(..., description="Task ID")
    message: str = Field(..., description="Message")


class FeatureResponse(BaseModel):
    """Response for features query."""
    
    data: list[Feature] = Field(..., description="List of features")
    meta: dict = Field(..., description="Metadata")


class RegimeResponse(BaseModel):
    """Response for regimes query."""
    
    data: list[Regime] = Field(..., description="List of regimes")
    meta: dict = Field(..., description="Metadata")
