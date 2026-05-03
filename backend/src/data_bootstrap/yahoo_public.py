"""Yahoo Finance OHLCV-only bootstrap planning helpers."""

from src.data_sources.bootstrap import (
    YAHOO_OHLCV_ONLY_LIMITATION,
    YahooPublicOhlcvClient,
    build_public_bootstrap_plan,
)
from src.data_sources.capabilities import YAHOO_UNSUPPORTED_CAPABILITIES
from src.models.data_sources import DataSourceBootstrapProvider, DataSourceBootstrapRequest


def plan_yahoo_public_requests(request: DataSourceBootstrapRequest):
    """Return Yahoo OHLCV-only plan items from a full bootstrap request."""

    return [
        item
        for item in build_public_bootstrap_plan(request)
        if item.provider == DataSourceBootstrapProvider.YAHOO_FINANCE
    ]


def yahoo_source_limitations(symbol: str) -> list[str]:
    """Return user-facing limitations for a Yahoo proxy symbol."""

    limitations = [YAHOO_OHLCV_ONLY_LIMITATION]
    if symbol.upper() in {"GC=F", "GLD"}:
        limitations.append(
            "GC=F and GLD are OHLCV proxies only, not gold options OI, "
            "futures OI, IV, or XAUUSD execution sources."
        )
    return limitations


__all__ = [
    "YAHOO_OHLCV_ONLY_LIMITATION",
    "YAHOO_UNSUPPORTED_CAPABILITIES",
    "YahooPublicOhlcvClient",
    "plan_yahoo_public_requests",
    "yahoo_source_limitations",
]
