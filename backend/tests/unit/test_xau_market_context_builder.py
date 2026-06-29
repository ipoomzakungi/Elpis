from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from src.models.xau_market_context import (
    XauMarketContextReadiness,
    XauPriceBar,
    XauSessionName,
)
from src.xau_market_context.context_builder import (
    XauMarketContextBuilder,
    XauMarketContextBuilderRequest,
)
from src.xau_market_context.session_calendar import build_session_opens


def test_session_calendar_london_dst_conversion_and_active_selection() -> None:
    tz = ZoneInfo("Asia/Bangkok")
    current = datetime(2026, 6, 29, 14, 15, tzinfo=tz)
    bars = [_bar(datetime(2026, 6, 29, 14, 0, tzinfo=tz), 4050)]

    session_opens, active = build_session_opens(
        bars=bars,
        current_timestamp=current,
        traded_price=4052,
        session_date=current.date(),
    )
    london = next(item for item in session_opens if item.session_name == XauSessionName.LONDON)

    assert london.open_time.hour == 14
    assert london.open_time.minute == 0
    assert london.open_price == 4050
    assert active is not None
    assert active.session_name == XauSessionName.LONDON


def test_context_builder_blocks_when_basis_is_missing(tmp_path: Path) -> None:
    bars = _many_bars()
    snapshot = XauMarketContextBuilder(reports_dir=tmp_path, fusion_reports_dir=tmp_path).build(
        XauMarketContextBuilderRequest(
            price_bars=bars,
            xauusd_spot_price=4050,
            current_timestamp=bars[-1].timestamp,
            output_root=tmp_path,
        )
    )

    assert snapshot.readiness == XauMarketContextReadiness.BLOCKED
    assert "basis" in snapshot.missing_context
    assert snapshot.signal_allowed is False
    assert snapshot.research_only is True


def test_context_builder_returns_partial_when_basis_exists_but_fusion_walls_are_absent(
    tmp_path: Path,
) -> None:
    bars = _many_bars()
    snapshot = XauMarketContextBuilder(reports_dir=tmp_path, fusion_reports_dir=tmp_path).build(
        XauMarketContextBuilderRequest(
            price_bars=bars,
            xauusd_spot_price=4050,
            gc_futures_price=4070,
            current_timestamp=bars[-1].timestamp,
            output_root=tmp_path,
        )
    )

    assert snapshot.basis.basis_points == 20
    assert snapshot.readiness == XauMarketContextReadiness.PARTIAL
    assert "fusion_context" in snapshot.missing_context
    assert (tmp_path / "xau_market_context" / snapshot.snapshot_id / "context.json").exists()


def _many_bars() -> list[XauPriceBar]:
    start = datetime(2026, 6, 29, 13, 0, tzinfo=ZoneInfo("Asia/Bangkok"))
    return [_bar(start + timedelta(minutes=index), 4040 + (index * 0.1)) for index in range(76)]


def _bar(timestamp: datetime, close: float) -> XauPriceBar:
    return XauPriceBar(
        timestamp=timestamp,
        open=close,
        high=close + 1,
        low=close - 1,
        close=close,
        volume=1,
        symbol="XAUUSD",
        timeframe="1m",
    )
