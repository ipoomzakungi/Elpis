from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
import polars as pl

from src.config import get_settings


class ParquetRepository:
    """Repository for Parquet file operations."""

    def __init__(self):
        self.settings = get_settings()
        self.settings.data_raw_path.mkdir(parents=True, exist_ok=True)
        self.settings.data_processed_path.mkdir(parents=True, exist_ok=True)

    def save_ohlcv(
        self, data: pl.DataFrame, symbol: str = "BTCUSDT", interval: str = "15m"
    ) -> Path:
        """Save OHLCV data to Parquet."""
        filename = f"{symbol.lower()}_{interval}_ohlcv.parquet"
        filepath = self.settings.data_raw_path / filename
        data.write_parquet(filepath)
        return filepath

    def save_open_interest(
        self, data: pl.DataFrame, symbol: str = "BTCUSDT", interval: str = "15m"
    ) -> Path:
        """Save open interest data to Parquet."""
        filename = f"{symbol.lower()}_{interval}_oi.parquet"
        filepath = self.settings.data_raw_path / filename
        data.write_parquet(filepath)
        return filepath

    def save_funding_rate(
        self, data: pl.DataFrame, symbol: str = "BTCUSDT", interval: str = "15m"
    ) -> Path:
        """Save funding rate data to Parquet."""
        filename = f"{symbol.lower()}_{interval}_funding.parquet"
        filepath = self.settings.data_raw_path / filename
        data.write_parquet(filepath)
        return filepath

    def save_features(
        self, data: pl.DataFrame, symbol: str = "BTCUSDT", interval: str = "15m"
    ) -> Path:
        """Save feature data to Parquet."""
        filename = f"{symbol.lower()}_{interval}_features.parquet"
        filepath = self.settings.data_processed_path / filename
        data.write_parquet(filepath)
        return filepath

    def load_ohlcv(self, symbol: str = "BTCUSDT", interval: str = "15m") -> Optional[pl.DataFrame]:
        """Load OHLCV data from Parquet."""
        filename = f"{symbol.lower()}_{interval}_ohlcv.parquet"
        filepath = self.settings.data_raw_path / filename
        if filepath.exists():
            return pl.read_parquet(filepath)
        return None

    def load_open_interest(
        self, symbol: str = "BTCUSDT", interval: str = "15m"
    ) -> Optional[pl.DataFrame]:
        """Load open interest data from Parquet."""
        filename = f"{symbol.lower()}_{interval}_oi.parquet"
        filepath = self.settings.data_raw_path / filename
        if filepath.exists():
            return pl.read_parquet(filepath)
        return None

    def load_funding_rate(
        self, symbol: str = "BTCUSDT", interval: str = "15m"
    ) -> Optional[pl.DataFrame]:
        """Load funding rate data from Parquet."""
        filename = f"{symbol.lower()}_{interval}_funding.parquet"
        filepath = self.settings.data_raw_path / filename
        if filepath.exists():
            return pl.read_parquet(filepath)
        return None

    def load_features(
        self, symbol: str = "BTCUSDT", interval: str = "15m"
    ) -> Optional[pl.DataFrame]:
        """Load feature data from Parquet."""
        filename = f"{symbol.lower()}_{interval}_features.parquet"
        filepath = self.settings.data_processed_path / filename
        if filepath.exists():
            return pl.read_parquet(filepath)
        return None

    def get_data_quality(self, data: pl.DataFrame, data_type: str) -> dict:
        """Calculate data quality metrics."""
        now = datetime.utcnow()

        if data.is_empty():
            return {
                "data_type": data_type,
                "total_records": 0,
                "missing_timestamps": 0,
                "duplicate_timestamps": 0,
                "first_timestamp": None,
                "last_timestamp": None,
                "last_updated": now,
            }

        # Check for duplicates
        duplicates = data.filter(data["timestamp"].is_duplicated())

        # Check for missing timestamps (gaps)
        if len(data) > 1:
            timestamps = data["timestamp"].sort()
            diffs = timestamps.diff().drop_nulls()
            expected_diff = timedelta(minutes=15)
            missing = int((diffs > expected_diff).sum())
        else:
            missing = 0

        return {
            "data_type": data_type,
            "total_records": len(data),
            "missing_timestamps": missing,
            "duplicate_timestamps": len(duplicates),
            "first_timestamp": data["timestamp"].min(),
            "last_timestamp": data["timestamp"].max(),
            "last_updated": now,
        }
