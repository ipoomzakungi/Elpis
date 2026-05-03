from datetime import UTC, datetime, timedelta

from src.data_bootstrap.binance_public import (
    BINANCE_LIMITED_DERIVATIVES_NOTE,
    binance_derivative_limitations,
    chronological_request_windows,
    plan_binance_public_requests,
)
from src.models.data_bootstrap import PublicDataBootstrapRequest


def test_binance_public_request_planning_uses_default_and_optional_assets():
    request = PublicDataBootstrapRequest(
        binance_symbols=["BTCUSDT", "ETHUSDT"],
        optional_binance_symbols=["SOLUSDT"],
        binance_timeframes=["15m", "1h"],
        include_yahoo=False,
        research_only_acknowledged=True,
    )

    plan = plan_binance_public_requests(request)

    assert {(item.symbol, item.timeframe) for item in plan} == {
        ("BTCUSDT", "15m"),
        ("BTCUSDT", "1h"),
        ("ETHUSDT", "15m"),
        ("ETHUSDT", "1h"),
        ("SOLUSDT", "15m"),
        ("SOLUSDT", "1h"),
    }
    assert all("ohlcv" in item.data_types for item in plan)
    assert all("open_interest" in item.data_types for item in plan)
    assert all("funding_rate" in item.data_types for item in plan)


def test_binance_public_pagination_windows_are_chronological_and_bounded():
    start = datetime(2026, 5, 1, tzinfo=UTC)
    end = start + timedelta(hours=3)

    windows = chronological_request_windows(start, end, timeframe="15m", limit=4)

    assert windows == [
        (1777593600000, 1777597200000),
        (1777597200001, 1777600800001),
        (1777600800002, 1777604400000),
    ]


def test_binance_public_derivative_limitations_label_shallow_history():
    now = datetime(2026, 5, 1, tzinfo=UTC)

    limitations = binance_derivative_limitations(
        data_type="open_interest",
        row_count=2,
        start_timestamp=now,
        end_timestamp=now + timedelta(hours=1),
        requested_days=30,
    )

    assert BINANCE_LIMITED_DERIVATIVES_NOTE in limitations
    assert any("shallow" in note.lower() for note in limitations)
