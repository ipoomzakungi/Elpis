from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class DataQuality(BaseModel):
    """Data quality metrics."""
    
    data_type: str = Field(..., description="Type of data (ohlcv, oi, funding)")
    total_records: int = Field(..., ge=0, description="Total number of records")
    missing_timestamps: int = Field(..., ge=0, description="Number of gaps")
    duplicate_timestamps: int = Field(..., ge=0, description="Number of duplicates")
    first_timestamp: Optional[datetime] = Field(None, description="Earliest record")
    last_timestamp: Optional[datetime] = Field(None, description="Latest record")
    last_updated: datetime = Field(..., description="When data was last fetched")

    class Config:
        json_schema_extra = {
            "example": {
                "data_type": "ohlcv",
                "total_records": 2880,
                "missing_timestamps": 5,
                "duplicate_timestamps": 0,
                "first_timestamp": "2026-03-27T00:00:00Z",
                "last_timestamp": "2026-04-26T00:00:00Z",
                "last_updated": "2026-04-26T12:30:00Z",
            }
        }


class DataQualityResponse(BaseModel):
    """Response for data quality query."""
    
    ohlcv: DataQuality = Field(..., description="OHLCV data quality")
    open_interest: DataQuality = Field(..., description="Open interest data quality")
    funding_rate: DataQuality = Field(..., description="Funding rate data quality")
