from functools import lru_cache
from src.repositories.parquet_repo import ParquetRepository
from src.repositories.duckdb_repo import DuckDBRepository


@lru_cache()
def get_parquet_repo() -> ParquetRepository:
    """Get Parquet repository instance."""
    return ParquetRepository()


@lru_cache()
def get_duckdb_repo() -> DuckDBRepository:
    """Get DuckDB repository instance."""
    return DuckDBRepository()
