import re
from datetime import datetime, timedelta
from pathlib import Path

import polars as pl

from src.config import get_settings


class ParquetRepository:
    """Repository for Parquet file operations."""

    RAW_DATA_SUFFIXES = {
        "ohlcv": "ohlcv",
        "open_interest": "oi",
        "funding_rate": "funding",
    }

    def __init__(self):
        self.settings = get_settings()
        self.settings.data_raw_path.mkdir(parents=True, exist_ok=True)
        self.settings.data_processed_path.mkdir(parents=True, exist_ok=True)

    def _sanitize_filename_part(self, value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")

    def _raw_filename(
        self,
        data_type: str,
        provider: str,
        symbol: str,
        interval: str,
    ) -> str:
        suffix = self.RAW_DATA_SUFFIXES[data_type]
        normalized_provider = provider.lower().strip()
        normalized_symbol = symbol.upper().strip()
        normalized_interval = interval.strip()

        if normalized_provider == "binance":
            return f"{normalized_symbol.lower()}_{normalized_interval}_{suffix}.parquet"

        safe_symbol = self._sanitize_filename_part(normalized_symbol)
        safe_interval = self._sanitize_filename_part(normalized_interval)
        safe_provider = self._sanitize_filename_part(normalized_provider)
        return f"{safe_provider}_{safe_symbol}_{safe_interval}_{suffix}.parquet"

    def _raw_path(self, data_type: str, provider: str, symbol: str, interval: str) -> Path:
        return self.settings.data_raw_path / self._raw_filename(
            data_type=data_type,
            provider=provider,
            symbol=symbol,
            interval=interval,
        )

    def save_provider_data(
        self,
        data: pl.DataFrame,
        data_type: str,
        provider: str,
        symbol: str,
        interval: str,
    ) -> Path:
        """Save a provider-normalized raw dataset to Parquet."""
        filepath = self._raw_path(data_type, provider, symbol, interval)
        data.write_parquet(filepath)
        return filepath

    def load_provider_data(
        self,
        data_type: str,
        provider: str,
        symbol: str,
        interval: str,
    ) -> pl.DataFrame | None:
        """Load a provider-normalized raw dataset from Parquet."""
        filepath = self._raw_path(data_type, provider, symbol, interval)
        if filepath.exists():
            return pl.read_parquet(filepath)
        return None

    def save_ohlcv(
        self,
        data: pl.DataFrame,
        symbol: str = "BTCUSDT",
        interval: str = "15m",
        provider: str | None = None,
    ) -> Path:
        """Save OHLCV data to Parquet."""
        if provider:
            return self.save_provider_data(data, "ohlcv", provider, symbol, interval)
        filename = f"{symbol.lower()}_{interval}_ohlcv.parquet"
        filepath = self.settings.data_raw_path / filename
        data.write_parquet(filepath)
        return filepath

    def save_open_interest(
        self,
        data: pl.DataFrame,
        symbol: str = "BTCUSDT",
        interval: str = "15m",
        provider: str | None = None,
    ) -> Path:
        """Save open interest data to Parquet."""
        if provider:
            return self.save_provider_data(data, "open_interest", provider, symbol, interval)
        filename = f"{symbol.lower()}_{interval}_oi.parquet"
        filepath = self.settings.data_raw_path / filename
        data.write_parquet(filepath)
        return filepath

    def save_funding_rate(
        self,
        data: pl.DataFrame,
        symbol: str = "BTCUSDT",
        interval: str = "15m",
        provider: str | None = None,
    ) -> Path:
        """Save funding rate data to Parquet."""
        if provider:
            return self.save_provider_data(data, "funding_rate", provider, symbol, interval)
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

    def load_ohlcv(
        self,
        symbol: str = "BTCUSDT",
        interval: str = "15m",
        provider: str | None = None,
    ) -> pl.DataFrame | None:
        """Load OHLCV data from Parquet."""
        if provider:
            return self.load_provider_data("ohlcv", provider, symbol, interval)
        filename = f"{symbol.lower()}_{interval}_ohlcv.parquet"
        filepath = self.settings.data_raw_path / filename
        if filepath.exists():
            return pl.read_parquet(filepath)
        return None

    def load_open_interest(
        self,
        symbol: str = "BTCUSDT",
        interval: str = "15m",
        provider: str | None = None,
    ) -> pl.DataFrame | None:
        """Load open interest data from Parquet."""
        if provider:
            return self.load_provider_data("open_interest", provider, symbol, interval)
        filename = f"{symbol.lower()}_{interval}_oi.parquet"
        filepath = self.settings.data_raw_path / filename
        if filepath.exists():
            return pl.read_parquet(filepath)
        return None

    def load_funding_rate(
        self,
        symbol: str = "BTCUSDT",
        interval: str = "15m",
        provider: str | None = None,
    ) -> pl.DataFrame | None:
        """Load funding rate data from Parquet."""
        if provider:
            return self.load_provider_data("funding_rate", provider, symbol, interval)
        filename = f"{symbol.lower()}_{interval}_funding.parquet"
        filepath = self.settings.data_raw_path / filename
        if filepath.exists():
            return pl.read_parquet(filepath)
        return None

    def load_features(
        self, symbol: str = "BTCUSDT", interval: str = "15m"
    ) -> pl.DataFrame | None:
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
