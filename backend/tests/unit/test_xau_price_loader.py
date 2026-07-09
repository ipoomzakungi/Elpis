from __future__ import annotations

from src.xau_market_context.price_loader import load_price_bars


def test_load_price_bars_accepts_dukascopy_epoch_milliseconds(tmp_path) -> None:
    path = tmp_path / "bars.csv"
    path.write_text(
        "timestamp,open,high,low,close,volume\n"
        "1783468800000,4098.205,4101.515,4096.625,4096.805,0.063\n",
        encoding="utf-8",
    )

    bars = load_price_bars(path, default_timezone="Asia/Bangkok")

    assert len(bars) == 1
    assert bars[0].timestamp.isoformat() == "2026-07-08T07:00:00+07:00"
    assert bars[0].close == 4096.805
