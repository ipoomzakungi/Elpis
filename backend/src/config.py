from pathlib import Path
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings."""
    
    # Paths
    data_raw_path: Path = Path("data/raw")
    data_processed_path: Path = Path("data/processed")
    data_reports_path: Path = Path("data/reports")
    data_duckdb_path: Path = Path("data/elpis.duckdb")
    
    # Binance API
    binance_base_url: str = "https://fapi.binance.com"
    binance_rate_limit: int = 1200  # requests per minute
    
    # Feature computation
    atr_period: int = 14
    range_period: int = 20
    volume_ratio_period: int = 20
    
    # Regime classification
    oi_change_threshold: float = 5.0  # percentage
    volume_ratio_threshold: float = 1.2
    range_position_threshold: float = 0.2  # 20% of range
    
    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings."""
    return Settings()
