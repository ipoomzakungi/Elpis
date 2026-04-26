import polars as pl
from datetime import datetime
from typing import Optional

from src.config import get_settings
from src.repositories.parquet_repo import ParquetRepository


class FeatureEngine:
    """Compute features from raw market data."""
    
    def __init__(self):
        self.settings = get_settings()
        self.parquet_repo = ParquetRepository()
    
    def compute_atr(self, df: pl.DataFrame, period: int = 14) -> pl.DataFrame:
        """Compute Average True Range."""
        return df.with_columns([
            (pl.col("high") - pl.col("low")).alias("tr1"),
            (pl.col("high") - pl.col("close").shift(1)).abs().alias("tr2"),
            (pl.col("low") - pl.col("close").shift(1)).abs().alias("tr3"),
        ]).with_columns([
            pl.max_horizontal("tr1", "tr2", "tr3").alias("true_range")
        ]).with_columns([
            pl.col("true_range").rolling_mean(window_size=period).alias("atr")
        ]).drop(["tr1", "tr2", "tr3", "true_range"])
    
    def compute_range_levels(self, df: pl.DataFrame, period: int = 20) -> pl.DataFrame:
        """Compute range high, low, and mid."""
        return df.with_columns([
            pl.col("high").rolling_max(window_size=period).alias("range_high"),
            pl.col("low").rolling_min(window_size=period).alias("range_low"),
        ]).with_columns([
            ((pl.col("range_high") + pl.col("range_low")) / 2).alias("range_mid")
        ])
    
    def compute_oi_change(self, df: pl.DataFrame) -> pl.DataFrame:
        """Compute OI change percentage."""
        return df.with_columns([
            ((pl.col("open_interest") - pl.col("open_interest").shift(1)) 
             / pl.col("open_interest").shift(1) * 100).alias("oi_change_pct")
        ])
    
    def compute_volume_ratio(self, df: pl.DataFrame, period: int = 20) -> pl.DataFrame:
        """Compute volume ratio (current / average)."""
        return df.with_columns([
            pl.col("volume").rolling_mean(window_size=period).alias("volume_avg")
        ]).with_columns([
            (pl.col("volume") / pl.col("volume_avg")).alias("volume_ratio")
        ]).drop("volume_avg")
    
    def compute_funding_features(self, df: pl.DataFrame) -> pl.DataFrame:
        """Compute funding rate features."""
        return df.with_columns([
            pl.col("funding_rate").forward_fill().alias("funding_rate"),
            (pl.col("funding_rate") - pl.col("funding_rate").shift(1)).alias("funding_rate_change"),
            pl.col("funding_rate").cum_sum().alias("funding_rate_cumsum"),
        ])
    
    def merge_data(
        self,
        ohlcv: pl.DataFrame,
        oi: Optional[pl.DataFrame] = None,
        funding: Optional[pl.DataFrame] = None,
    ) -> pl.DataFrame:
        """Merge OHLCV with OI and funding data by timestamp."""
        df = ohlcv.clone()
        
        # Merge OI data
        if oi is not None and not oi.is_empty():
            df = df.join(
                oi.select(["timestamp", "open_interest", "open_interest_value"]),
                on="timestamp",
                how="left",
            )
        
        # Merge funding data (forward-fill to 15m intervals)
        if funding is not None and not funding.is_empty():
            # Forward fill funding rate to 15m intervals
            funding_filled = funding.select([
                "timestamp",
                "funding_rate",
                "mark_price",
            ]).sort("timestamp")
            
            # Join and forward fill
            df = df.join(funding_filled, on="timestamp", how="left")
            df = df.with_columns([
                pl.col("funding_rate").forward_fill(),
                pl.col("mark_price").forward_fill(),
            ])
        
        return df.sort("timestamp")
    
    def compute_all_features(
        self,
        symbol: str = "BTCUSDT",
        interval: str = "15m",
    ) -> Optional[pl.DataFrame]:
        """Compute all features from raw data."""
        # Load raw data
        ohlcv = self.parquet_repo.load_ohlcv(symbol=symbol, interval=interval)
        if ohlcv is None or ohlcv.is_empty():
            return None
        
        oi = self.parquet_repo.load_open_interest(symbol=symbol, interval=interval)
        funding = self.parquet_repo.load_funding_rate(symbol=symbol, interval=interval)
        
        # Merge data
        df = self.merge_data(ohlcv, oi, funding)
        
        # Compute features
        df = self.compute_atr(df, period=self.settings.atr_period)
        df = self.compute_range_levels(df, period=self.settings.range_period)
        df = self.compute_volume_ratio(df, period=self.settings.volume_ratio_period)
        
        # Compute OI features if available
        if "open_interest" in df.columns:
            df = self.compute_oi_change(df)
        
        # Compute funding features if available
        if "funding_rate" in df.columns:
            df = self.compute_funding_features(df)
        
        # Drop rows with NaN from rolling calculations
        df = df.drop_nulls()
        
        return df
