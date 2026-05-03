"""Binance public bootstrap planning and limitation helpers."""

from datetime import datetime

from src.data_sources.bootstrap import (
    BINANCE_LIMITED_DERIVATIVES_NOTE,
    INTERVAL_MS,
    binance_derivative_limitations,
    binance_request_windows,
    build_public_bootstrap_plan,
)
from src.models.data_sources import DataSourceBootstrapProvider, DataSourceBootstrapRequest


def plan_binance_public_requests(request: DataSourceBootstrapRequest):
    """Return public Binance plan items from a full bootstrap request."""

    return [
        item
        for item in build_public_bootstrap_plan(request)
        if item.provider == DataSourceBootstrapProvider.BINANCE_PUBLIC
    ]


def chronological_request_windows(
    start: datetime,
    end: datetime,
    *,
    timeframe: str,
    limit: int,
) -> list[tuple[int, int]]:
    """Create chronological Binance request windows for a timeframe."""

    return binance_request_windows(start, end, timeframe=timeframe, limit=limit)


__all__ = [
    "BINANCE_LIMITED_DERIVATIVES_NOTE",
    "INTERVAL_MS",
    "binance_derivative_limitations",
    "binance_request_windows",
    "chronological_request_windows",
    "plan_binance_public_requests",
]
