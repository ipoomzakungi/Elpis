from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RegimeType(StrEnum):
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
    open_interest: float | None = Field(None, gt=0, description="Open interest")
    oi_change_pct: float | None = Field(None, description="OI change percentage")

    # Volume features
    volume_ratio: float = Field(..., ge=0, description="Volume / 20-period avg")

    # Funding features
    funding_rate: float | None = Field(None, ge=-0.05, le=0.05, description="Funding rate")
    funding_rate_change: float | None = Field(None, description="Rate change from previous")
    funding_rate_cumsum: float | None = Field(None, description="Cumulative funding rate")

    model_config = ConfigDict(
        json_schema_extra={
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
    )


class Regime(BaseModel):
    """Regime classification for a bar."""

    timestamp: datetime = Field(..., description="Bar time (UTC)")
    regime: RegimeType = Field(..., description="Regime classification")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Classification confidence")
    reason: str | None = Field(None, description="Human-readable reason")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "timestamp": "2026-04-26T00:00:00Z",
                "regime": "RANGE",
                "confidence": 0.85,
                "reason": "Price near range mid, low OI change, normal volume",
            }
        }
    )


class ProcessRequest(BaseModel):
    """Request to process data."""

    symbol: str = Field(default="BTCUSDT", description="Trading pair")
    interval: Literal["15m"] = Field(default="15m", description="Timeframe")

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        normalized = value.upper().strip()
        if normalized != "BTCUSDT":
            raise ValueError("Only BTCUSDT is supported in OI Regime Lab v0")
        return normalized


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
