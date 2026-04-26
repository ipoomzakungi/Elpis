import logging
from datetime import datetime

from src.repositories.parquet_repo import ParquetRepository


logger = logging.getLogger(__name__)


class DataQualityService:
    """Service for data quality checks."""

    def __init__(self):
        self.parquet_repo = ParquetRepository()

    def check_data_quality(self, symbol: str = "BTCUSDT", interval: str = "15m") -> dict:
        """Check data quality for all data types."""
        logger.info("Checking data quality for %s %s", symbol, interval)
        result = {}

        # Check OHLCV
        ohlcv = self.parquet_repo.load_ohlcv(symbol=symbol, interval=interval)
        if ohlcv is not None:
            result["ohlcv"] = self.parquet_repo.get_data_quality(ohlcv, "ohlcv")
        else:
            result["ohlcv"] = {
                "data_type": "ohlcv",
                "total_records": 0,
                "missing_timestamps": 0,
                "duplicate_timestamps": 0,
                "first_timestamp": None,
                "last_timestamp": None,
                "last_updated": datetime.utcnow(),
            }

        # Check Open Interest
        oi = self.parquet_repo.load_open_interest(symbol=symbol, interval=interval)
        if oi is not None:
            result["open_interest"] = self.parquet_repo.get_data_quality(oi, "open_interest")
        else:
            result["open_interest"] = {
                "data_type": "open_interest",
                "total_records": 0,
                "missing_timestamps": 0,
                "duplicate_timestamps": 0,
                "first_timestamp": None,
                "last_timestamp": None,
                "last_updated": datetime.utcnow(),
            }

        # Check Funding Rate
        funding = self.parquet_repo.load_funding_rate(symbol=symbol, interval=interval)
        if funding is not None:
            result["funding_rate"] = self.parquet_repo.get_data_quality(funding, "funding_rate")
        else:
            result["funding_rate"] = {
                "data_type": "funding_rate",
                "total_records": 0,
                "missing_timestamps": 0,
                "duplicate_timestamps": 0,
                "first_timestamp": None,
                "last_timestamp": None,
                "last_updated": datetime.utcnow(),
            }

        return result
