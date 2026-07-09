from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from scripts.run_xau_vol2vol_history_walkforward import (
    _enrich_range_snapshots_with_bars,
    _has_sd_plan_inputs,
)
from src.models.xau_market_context import XauPriceBar
from src.models.xau_vol2vol_history_walkforward import XauVol2VolRangeDeskSnapshot


def test_enrich_range_snapshot_computes_cfd_open_and_diff_from_bars() -> None:
    snapshot = XauVol2VolRangeDeskSnapshot(
        session_date=date(2026, 7, 8),
        observed_at=datetime.fromisoformat("2026-07-08T10:00:00+00:00"),
        future_open=4106.5,
        future_buy_2sd=4071.7,
    )
    bars = [_bar(datetime(2026, 7, 8, 17, 0, tzinfo=ZoneInfo("Asia/Bangkok")), 4096.17)]

    enriched = _enrich_range_snapshots_with_bars([snapshot], bars)[0]

    assert enriched.cfd_open == 4096.17
    assert enriched.diff == pytest.approx(10.33)


def test_monthly_oi_without_sd_ranges_is_not_plan_input() -> None:
    snapshot = XauVol2VolRangeDeskSnapshot(
        session_date=date(2026, 6, 1),
        observed_at=datetime.fromisoformat("2026-06-01T10:00:00+00:00"),
        future_open=4100,
    )

    assert _has_sd_plan_inputs(snapshot) is False


def _bar(timestamp: datetime, close: float) -> XauPriceBar:
    return XauPriceBar(
        timestamp=timestamp,
        open=close,
        high=close + 1,
        low=close - 1,
        close=close,
        volume=1,
    )
