import logging

import polars as pl

from src.config import get_settings
from src.repositories.parquet_repo import ParquetRepository

logger = logging.getLogger(__name__)


class FeatureEngine:
    """Compute features from raw market data."""

    def __init__(self):
        self.settings = get_settings()
        self.parquet_repo = ParquetRepository()

    def _require_columns(self, df: pl.DataFrame, required_columns: set[str], context: str) -> None:
        missing = sorted(required_columns.difference(df.columns))
        if missing:
            raise ValueError(f"Missing columns for {context}: {', '.join(missing)}")

    def compute_atr(self, df: pl.DataFrame, period: int = 14) -> pl.DataFrame:
        """Compute Average True Range."""
        self._require_columns(df, {"high", "low", "close"}, "ATR computation")
        return (
            df.with_columns(
                [
                    (pl.col("high") - pl.col("low")).alias("tr1"),
                    (pl.col("high") - pl.col("close").shift(1)).abs().alias("tr2"),
                    (pl.col("low") - pl.col("close").shift(1)).abs().alias("tr3"),
                ]
            )
            .with_columns([pl.max_horizontal("tr1", "tr2", "tr3").alias("true_range")])
            .with_columns([pl.col("true_range").rolling_mean(window_size=period).alias("atr")])
            .drop(["tr1", "tr2", "tr3", "true_range"])
        )

    def compute_range_levels(self, df: pl.DataFrame, period: int = 20) -> pl.DataFrame:
        """Compute range high, low, and mid."""
        self._require_columns(df, {"high", "low"}, "range level computation")
        return df.with_columns(
            [
                pl.col("high").rolling_max(window_size=period).alias("range_high"),
                pl.col("low").rolling_min(window_size=period).alias("range_low"),
            ]
        ).with_columns([((pl.col("range_high") + pl.col("range_low")) / 2).alias("range_mid")])

    def compute_oi_change(self, df: pl.DataFrame) -> pl.DataFrame:
        """Compute OI change percentage."""
        self._require_columns(df, {"open_interest"}, "OI change computation")
        return df.with_columns(
            [
                (
                    (pl.col("open_interest") - pl.col("open_interest").shift(1))
                    / pl.col("open_interest").shift(1)
                    * 100
                ).alias("oi_change_pct")
            ]
        )

    def compute_volume_ratio(self, df: pl.DataFrame, period: int = 20) -> pl.DataFrame:
        """Compute volume ratio (current / average)."""
        self._require_columns(df, {"volume"}, "volume ratio computation")
        return (
            df.with_columns([pl.col("volume").rolling_mean(window_size=period).alias("volume_avg")])
            .with_columns([(pl.col("volume") / pl.col("volume_avg")).alias("volume_ratio")])
            .drop("volume_avg")
        )

    def compute_funding_features(self, df: pl.DataFrame) -> pl.DataFrame:
        """Compute funding rate features."""
        self._require_columns(df, {"funding_rate"}, "funding feature computation")
        df = df.with_columns(pl.col("funding_rate").forward_fill().alias("funding_rate"))
        return df.with_columns(
            [
                (pl.col("funding_rate") - pl.col("funding_rate").shift(1)).alias(
                    "funding_rate_change"
                ),
                pl.col("funding_rate").cum_sum().alias("funding_rate_cumsum"),
            ]
        )

    def _has_non_null_values(self, df: pl.DataFrame, column: str) -> bool:
        if column not in df.columns or df.is_empty():
            return False
        return bool(df.select(pl.col(column).is_not_null().any()).item())

    def _drop_required_feature_nulls(self, df: pl.DataFrame) -> pl.DataFrame:
        required_columns = [
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "atr",
            "range_high",
            "range_low",
            "range_mid",
            "volume_ratio",
        ]
        present_required_columns = [column for column in required_columns if column in df.columns]
        return df.drop_nulls(subset=present_required_columns)

    def merge_data(
        self,
        ohlcv: pl.DataFrame,
        oi: pl.DataFrame | None = None,
        funding: pl.DataFrame | None = None,
    ) -> pl.DataFrame:
        """Merge OHLCV with OI and funding data by timestamp."""
        self._require_columns(
            ohlcv,
            {"timestamp", "open", "high", "low", "close", "volume"},
            "data merge",
        )
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
            funding_filled = funding.select(
                [
                    "timestamp",
                    "funding_rate",
                    "mark_price",
                ]
            ).sort("timestamp")

            # Join and forward fill
            df = df.join(funding_filled, on="timestamp", how="left")
            df = df.with_columns(
                [
                    pl.col("funding_rate").forward_fill(),
                    pl.col("mark_price").forward_fill(),
                ]
            )

        return df.sort("timestamp")

    def compute_all_features(
        self,
        symbol: str = "BTCUSDT",
        interval: str = "15m",
    ) -> pl.DataFrame | None:
        """Compute all features from raw data."""
        try:
            logger.info("Computing features for %s %s", symbol, interval)
            ohlcv = self.parquet_repo.load_ohlcv(symbol=symbol, interval=interval)
            if ohlcv is None or ohlcv.is_empty():
                logger.warning("No OHLCV data found for %s %s", symbol, interval)
                return None

            oi = self.parquet_repo.load_open_interest(symbol=symbol, interval=interval)
            funding = self.parquet_repo.load_funding_rate(symbol=symbol, interval=interval)

            df = self.merge_data(ohlcv, oi, funding)
            df = self.compute_atr(df, period=self.settings.atr_period)
            df = self.compute_range_levels(df, period=self.settings.range_period)
            df = self.compute_volume_ratio(df, period=self.settings.volume_ratio_period)

            if self._has_non_null_values(df, "open_interest"):
                df = self.compute_oi_change(df)

            if self._has_non_null_values(df, "funding_rate"):
                df = self.compute_funding_features(df)

            df = self._drop_required_feature_nulls(df)
            logger.info("Computed %s feature rows for %s %s", len(df), symbol, interval)
            return df
        except Exception:
            logger.exception("Feature computation failed for %s %s", symbol, interval)
            raise
