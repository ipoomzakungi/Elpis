from __future__ import annotations

import builtins
import sys
import types
from datetime import datetime
from zoneinfo import ZoneInfo

from src.xau_market_context.yfinance_provider import fetch_yfinance_price


def test_yfinance_provider_returns_unavailable_if_yfinance_is_not_installed(
    monkeypatch,
) -> None:
    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "yfinance":
            raise ImportError("missing")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    price = fetch_yfinance_price(symbol="XAUUSD=X")

    assert price.price is None
    assert price.provider == "yfinance"
    assert price.provider_quality == "unavailable"


def test_yfinance_provider_is_optional_and_can_be_mocked(monkeypatch) -> None:
    fake_module = types.SimpleNamespace(Ticker=lambda symbol: _FakeTicker(symbol))
    monkeypatch.setitem(sys.modules, "yfinance", fake_module)

    price = fetch_yfinance_price(symbol="XAUUSD=X", timezone="Asia/Bangkok")

    assert price.price == 4052
    assert price.provider_quality == "research_fallback"
    assert price.timestamp == datetime(2026, 6, 29, 14, 15, tzinfo=ZoneInfo("Asia/Bangkok"))
    assert any("research fallback" in warning for warning in price.warnings)


def test_yfinance_provider_does_not_break_backend_import() -> None:
    from src.main import app

    assert app is not None


class _FakeTicker:
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol

    def history(self, *, period: str, interval: str):
        assert period == "1d"
        assert interval == "1m"
        return _FakeFrame()


class _FakeFrame:
    empty = False

    def iterrows(self):
        yield (
            datetime(2026, 6, 29, 14, 15, tzinfo=ZoneInfo("Asia/Bangkok")),
            {
                "Open": 4051,
                "High": 4053,
                "Low": 4050,
                "Close": 4052,
                "Volume": 10,
            },
        )

