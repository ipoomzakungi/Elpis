from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MarketData(BaseModel):
    """OHLCV candlestick data from Binance Futures."""

    timestamp: datetime = Field(..., description="Bar open time (UTC)")
    open: float = Field(..., gt=0, description="Opening price")
    high: float = Field(..., gt=0, description="Highest price")
    low: float = Field(..., gt=0, description="Lowest price")
    close: float = Field(..., gt=0, description="Closing price")
    volume: float = Field(..., ge=0, description="Trading volume")
    quote_volume: float = Field(..., ge=0, description="Quote asset volume")
    trades: int = Field(..., ge=0, description="Number of trades")
    taker_buy_volume: float = Field(..., ge=0, description="Taker buy volume")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "timestamp": "2026-04-26T00:00:00Z",
                "open": 65000.50,
                "high": 65100.00,
                "low": 64900.25,
                "close": 65050.75,
                "volume": 1234.567,
                "quote_volume": 80234567.89,
                "trades": 5678,
                "taker_buy_volume": 617.283,
            }
        }
    )


class OpenInterest(BaseModel):
    """Open interest at a specific timestamp."""

    timestamp: datetime = Field(..., description="Measurement time (UTC)")
    symbol: str = Field(default="BTCUSDT", description="Trading pair")
    open_interest: float = Field(..., gt=0, description="Open interest in base asset")
    open_interest_value: float = Field(..., gt=0, description="Open interest in quote currency")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "timestamp": "2026-04-26T00:00:00Z",
                "symbol": "BTCUSDT",
                "open_interest": 12345.678,
                "open_interest_value": 802345678.90,
            }
        }
    )


class FundingRate(BaseModel):
    """Funding rate data."""

    timestamp: datetime = Field(..., description="Funding time (UTC)")
    symbol: str = Field(default="BTCUSDT", description="Trading pair")
    funding_rate: float = Field(..., ge=-0.05, le=0.05, description="Funding rate")
    mark_price: float = Field(..., gt=0, description="Mark price at funding time")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "timestamp": "2026-04-26T00:00:00Z",
                "symbol": "BTCUSDT",
                "funding_rate": 0.00010000,
                "mark_price": 65000.50,
            }
        }
    )


class DownloadRequest(BaseModel):
    """Request to download market data."""

    symbol: str = Field(default="BTCUSDT", description="Trading pair")
    interval: Literal["15m"] = Field(default="15m", description="Timeframe")
    days: int = Field(default=30, ge=1, le=365, description="Days of history")

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        normalized = value.upper().strip()
        if normalized != "BTCUSDT":
            raise ValueError("Only BTCUSDT is supported in OI Regime Lab v0")
        return normalized


class DownloadResponse(BaseModel):
    """Response for download request."""

    status: str = Field(..., description="Status of download")
    task_id: str = Field(..., description="Task ID")
    message: str = Field(..., description="Message")


class MarketDataResponse(BaseModel):
    """Response for market data query."""

    data: list[MarketData] = Field(..., description="List of market data")
    meta: dict = Field(..., description="Metadata")


class OpenInterestResponse(BaseModel):
    """Response for open interest query."""

    data: list[OpenInterest] = Field(..., description="List of open interest")
    meta: dict = Field(..., description="Metadata")


class FundingRateResponse(BaseModel):
    """Response for funding rate query."""

    data: list[FundingRate] = Field(..., description="List of funding rates")
    meta: dict = Field(..., description="Metadata")
