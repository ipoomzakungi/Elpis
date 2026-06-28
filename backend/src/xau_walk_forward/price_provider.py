from __future__ import annotations

from datetime import datetime

from src.models.xau_walk_forward_research import (
    XauWalkForwardAlignmentStatus,
    XauWalkForwardPriceSnapshot,
    XauWalkForwardPriceSource,
    XauWalkForwardSourceQuality,
)


class ManualPriceProvider:
    def snapshot(
        self,
        *,
        timestamp: datetime,
        future_reference_price: float,
        traded_reference_price: float,
    ) -> XauWalkForwardPriceSnapshot:
        return XauWalkForwardPriceSnapshot(
            timestamp=timestamp,
            future_reference_price=future_reference_price,
            traded_reference_price=traded_reference_price,
            future_price_source=XauWalkForwardPriceSource.MANUAL,
            traded_price_source=XauWalkForwardPriceSource.MANUAL,
            source_quality=XauWalkForwardSourceQuality.MANUAL,
            alignment_status=XauWalkForwardAlignmentStatus.ALIGNED,
            limitations=["Manual research prices are not broker-exact live prices."],
        )


class StaticFixturePriceProvider:
    def snapshot(
        self,
        *,
        timestamp: datetime,
        future_reference_price: float = 4500.0,
        traded_reference_price: float = 4470.0,
    ) -> XauWalkForwardPriceSnapshot:
        return XauWalkForwardPriceSnapshot(
            timestamp=timestamp,
            future_reference_price=future_reference_price,
            traded_reference_price=traded_reference_price,
            future_price_source=XauWalkForwardPriceSource.FIXTURE,
            traded_price_source=XauWalkForwardPriceSource.FIXTURE,
            source_quality=XauWalkForwardSourceQuality.FIXTURE,
            alignment_status=XauWalkForwardAlignmentStatus.ALIGNED,
            limitations=["Fixture prices are for tests and local smoke validation only."],
        )


class YahooResearchPriceProvider:
    def snapshot(
        self,
        *,
        timestamp: datetime,
        future_symbol: str = "GC=F",
        traded_symbol: str = "XAUUSD=X",
    ) -> XauWalkForwardPriceSnapshot:
        try:
            import yfinance as yf  # type: ignore[import-untyped]
        except ImportError:
            return XauWalkForwardPriceSnapshot(
                timestamp=timestamp,
                future_price_source=XauWalkForwardPriceSource.UNAVAILABLE,
                traded_price_source=XauWalkForwardPriceSource.UNAVAILABLE,
                source_quality=XauWalkForwardSourceQuality.UNAVAILABLE,
                alignment_status=XauWalkForwardAlignmentStatus.UNAVAILABLE,
                limitations=["yfinance is not installed; Yahoo research fallback unavailable."],
            )

        future_price = _last_price(yf, future_symbol)
        traded_price = _last_price(yf, traded_symbol)
        limitations = [
            "Yahoo Finance is a research fallback and is not broker-exact.",
        ]
        if future_price is None or traded_price is None:
            limitations.append("Yahoo research fallback did not return both prices.")
        return XauWalkForwardPriceSnapshot(
            timestamp=timestamp,
            future_reference_price=future_price,
            traded_reference_price=traded_price,
            future_price_source=(
                XauWalkForwardPriceSource.YAHOO_RESEARCH
                if future_price is not None
                else XauWalkForwardPriceSource.UNAVAILABLE
            ),
            traded_price_source=(
                XauWalkForwardPriceSource.YAHOO_RESEARCH
                if traded_price is not None
                else XauWalkForwardPriceSource.UNAVAILABLE
            ),
            source_quality=(
                XauWalkForwardSourceQuality.RESEARCH_FALLBACK
                if future_price is not None and traded_price is not None
                else XauWalkForwardSourceQuality.UNAVAILABLE
            ),
            alignment_status=XauWalkForwardAlignmentStatus.UNKNOWN,
            limitations=limitations,
        )


def _last_price(yf, symbol: str) -> float | None:
    try:
        ticker = yf.Ticker(symbol)
        history = ticker.history(period="1d", interval="1m")
    except Exception:
        return None
    if history.empty or "Close" not in history:
        return None
    value = history["Close"].dropna().iloc[-1]
    return float(value)


__all__ = [
    "ManualPriceProvider",
    "StaticFixturePriceProvider",
    "YahooResearchPriceProvider",
]
