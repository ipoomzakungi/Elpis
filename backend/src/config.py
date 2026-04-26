from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

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

    def ensure_data_paths(self) -> None:
        """Create local research data directories if they do not exist."""
        self.data_raw_path.mkdir(parents=True, exist_ok=True)
        self.data_processed_path.mkdir(parents=True, exist_ok=True)
        self.data_reports_path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings."""
    return Settings()


def get_reports_path(settings: Settings | None = None) -> Path:
    """Return the configured generated-report artifact directory."""
    resolved_settings = settings or get_settings()
    resolved_settings.data_reports_path.mkdir(parents=True, exist_ok=True)
    return resolved_settings.data_reports_path
