from pathlib import Path
from typing import Optional
import duckdb
import polars as pl

from backend.src.config import get_settings


class DuckDBRepository:
    """Repository for DuckDB operations."""
    
    def __init__(self):
        self.settings = get_settings()
        self.settings.data_duckdb_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = duckdb.connect(str(self.settings.data_duckdb_path))
        self._create_views()
    
    def _create_views(self):
        """Create views for Parquet files."""
        raw_path = self.settings.data_raw_path
        processed_path = self.settings.data_processed_path
        
        # Create views for raw data
        ohlcv_path = raw_path / "btcusdt_15m_ohlcv.parquet"
        oi_path = raw_path / "btcusdt_15m_oi.parquet"
        funding_path = raw_path / "btcusdt_15m_funding.parquet"
        features_path = processed_path / "btcusdt_15m_features.parquet"
        
        if ohlcv_path.exists():
            self.conn.execute(f"""
                CREATE OR REPLACE VIEW ohlcv AS 
                SELECT * FROM '{ohlcv_path}'
            """)
        
        if oi_path.exists():
            self.conn.execute(f"""
                CREATE OR REPLACE VIEW open_interest AS 
                SELECT * FROM '{oi_path}'
            """)
        
        if funding_path.exists():
            self.conn.execute(f"""
                CREATE OR REPLACE VIEW funding_rate AS 
                SELECT * FROM '{funding_path}'
            """)
        
        if features_path.exists():
            self.conn.execute(f"""
                CREATE OR REPLACE VIEW features AS 
                SELECT * FROM '{features_path}'
            """)
    
    def refresh_views(self):
        """Refresh views after new data is saved."""
        self._create_views()
    
    def query(self, sql: str) -> pl.DataFrame:
        """Execute SQL query and return Polars DataFrame."""
        result = self.conn.execute(sql)
        return pl.from_arrow(result.fetch_arrow_table())
    
    def query_ohlcv(self, limit: int = 1000) -> Optional[pl.DataFrame]:
        """Query OHLCV data."""
        try:
            return self.query(f"SELECT * FROM ohlcv ORDER BY timestamp DESC LIMIT {limit}")
        except Exception:
            return None
    
    def query_open_interest(self, limit: int = 1000) -> Optional[pl.DataFrame]:
        """Query open interest data."""
        try:
            return self.query(f"SELECT * FROM open_interest ORDER BY timestamp DESC LIMIT {limit}")
        except Exception:
            return None
    
    def query_funding_rate(self, limit: int = 1000) -> Optional[pl.DataFrame]:
        """Query funding rate data."""
        try:
            return self.query(f"SELECT * FROM funding_rate ORDER BY timestamp DESC LIMIT {limit}")
        except Exception:
            return None
    
    def query_features(self, limit: int = 1000) -> Optional[pl.DataFrame]:
        """Query feature data."""
        try:
            return self.query(f"SELECT * FROM features ORDER BY timestamp DESC LIMIT {limit}")
        except Exception:
            return None
    
    def close(self):
        """Close DuckDB connection."""
        self.conn.close()
