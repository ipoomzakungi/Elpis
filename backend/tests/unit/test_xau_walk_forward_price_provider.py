from src.xau_walk_forward.price_provider import _last_price


class _FailingTicker:
    def history(self, *, period: str, interval: str):
        raise RuntimeError("upstream reset")


class _FailingYf:
    @staticmethod
    def Ticker(symbol: str):  # noqa: N802 - mimic yfinance's public API.
        return _FailingTicker()


def test_last_price_returns_none_when_research_fallback_provider_fails() -> None:
    assert _last_price(_FailingYf, "XAUUSD=X") is None
