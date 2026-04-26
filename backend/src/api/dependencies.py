from functools import lru_cache

from src.providers.registry import ProviderRegistry, create_default_provider_registry
from src.repositories.duckdb_repo import DuckDBRepository
from src.repositories.parquet_repo import ParquetRepository


@lru_cache
def get_parquet_repo() -> ParquetRepository:
    """Get Parquet repository instance."""
    return ParquetRepository()


@lru_cache
def get_duckdb_repo() -> DuckDBRepository:
    """Get DuckDB repository instance."""
    return DuckDBRepository()


@lru_cache
def get_provider_registry() -> ProviderRegistry:
    """Get provider registry instance."""
    return create_default_provider_registry()
