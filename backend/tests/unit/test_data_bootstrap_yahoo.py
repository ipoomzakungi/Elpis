from src.data_bootstrap.yahoo_public import (
    YAHOO_OHLCV_ONLY_LIMITATION,
    YAHOO_UNSUPPORTED_CAPABILITIES,
    plan_yahoo_public_requests,
    yahoo_source_limitations,
)
from src.models.data_bootstrap import PublicDataBootstrapRequest


def test_yahoo_public_request_planning_is_ohlcv_only():
    request = PublicDataBootstrapRequest(
        include_binance=False,
        yahoo_symbols=["SPY", "QQQ", "GLD", "GC=F", "BTC-USD"],
        yahoo_timeframes=["1d"],
        research_only_acknowledged=True,
    )

    plan = plan_yahoo_public_requests(request)

    assert {(item.symbol, item.timeframe) for item in plan} == {
        ("SPY", "1d"),
        ("QQQ", "1d"),
        ("GLD", "1d"),
        ("GC=F", "1d"),
        ("BTC-USD", "1d"),
    }
    assert all(item.data_types == ["ohlcv"] for item in plan)


def test_yahoo_public_labels_unsupported_derivative_and_execution_capabilities():
    request = PublicDataBootstrapRequest(
        include_binance=False,
        yahoo_symbols=["SPY"],
        research_only_acknowledged=True,
    )

    item = plan_yahoo_public_requests(request)[0]

    for unsupported in [
        "open_interest",
        "funding",
        "iv",
        "gold_options_oi",
        "futures_oi",
        "xauusd_spot_execution",
    ]:
        assert unsupported in item.unsupported_capabilities
        assert unsupported in YAHOO_UNSUPPORTED_CAPABILITIES


def test_yahoo_public_gold_proxy_limitations_are_explicit():
    limitations = yahoo_source_limitations("GC=F")

    assert YAHOO_OHLCV_ONLY_LIMITATION in limitations
    assert any("gold options OI" in note for note in limitations)
    assert any("XAUUSD execution" in note for note in limitations)
