import polars as pl
from typing import Optional

from src.config import get_settings
from src.models.features import RegimeType


class RegimeClassifier:
    """Classify market regimes based on features."""
    
    def __init__(self):
        self.settings = get_settings()
    
    def classify_bar(
        self,
        price: float,
        range_high: float,
        range_low: float,
        range_mid: float,
        oi_change_pct: Optional[float],
        volume_ratio: float,
    ) -> tuple[RegimeType, float, str]:
        """Classify a single bar into a regime."""
        range_size = range_high - range_low
        if range_size <= 0:
            return RegimeType.AVOID, 0.0, "Invalid range"
        
        # Calculate price position relative to range (0 = low, 1 = high)
        price_position = (price - range_low) / range_size
        
        # Get thresholds
        oi_threshold = self.settings.oi_change_threshold
        vol_threshold = self.settings.volume_ratio_threshold
        range_threshold = self.settings.range_position_threshold
        
        # Check for BREAKOUT_UP
        if price_position > (1 - range_threshold):  # Near range high
            if oi_change_pct is not None and oi_change_pct > oi_threshold:
                if volume_ratio > vol_threshold:
                    return RegimeType.BREAKOUT_UP, 0.9, (
                        f"Price near range high ({price_position:.1%}), "
                        f"OI up {oi_change_pct:.1f}%, volume ratio {volume_ratio:.2f}"
                    )
                else:
                    return RegimeType.BREAKOUT_UP, 0.7, (
                        f"Price near range high ({price_position:.1%}), "
                        f"OI up {oi_change_pct:.1f}%, but low volume"
                    )
        
        # Check for BREAKOUT_DOWN
        if price_position < range_threshold:  # Near range low
            if oi_change_pct is not None and oi_change_pct > oi_threshold:
                if volume_ratio > vol_threshold:
                    return RegimeType.BREAKOUT_DOWN, 0.9, (
                        f"Price near range low ({price_position:.1%}), "
                        f"OI up {oi_change_pct:.1f}%, volume ratio {volume_ratio:.2f}"
                    )
                else:
                    return RegimeType.BREAKOUT_DOWN, 0.7, (
                        f"Price near range low ({price_position:.1%}), "
                        f"OI up {oi_change_pct:.1f}%, but low volume"
                    )
        
        # Check for RANGE
        if (range_threshold <= price_position <= (1 - range_threshold)):
            if oi_change_pct is not None and oi_change_pct < oi_threshold:
                if volume_ratio < vol_threshold:
                    return RegimeType.RANGE, 0.85, (
                        f"Price in range ({price_position:.1%}), "
                        f"OI stable ({oi_change_pct:.1f}%), normal volume"
                    )
        
        # Default to AVOID
        return RegimeType.AVOID, 0.5, (
            f"Conflicting signals: price position {price_position:.1%}, "
            f"OI change {oi_change_pct:.1f}% if oi_change_pct is not None else 'N/A'"
        )
    
    def classify_dataframe(self, df: pl.DataFrame) -> pl.DataFrame:
        """Classify all bars in a DataFrame."""
        regimes = []
        confidences = []
        reasons = []
        
        for row in df.iter_rows(named=True):
            regime, confidence, reason = self.classify_bar(
                price=row["close"],
                range_high=row["range_high"],
                range_low=row["range_low"],
                range_mid=row["range_mid"],
                oi_change_pct=row.get("oi_change_pct"),
                volume_ratio=row["volume_ratio"],
            )
            regimes.append(regime.value)
            confidences.append(confidence)
            reasons.append(reason)
        
        return df.with_columns([
            pl.Series("regime", regimes),
            pl.Series("confidence", confidences),
            pl.Series("reason", reasons),
        ])
