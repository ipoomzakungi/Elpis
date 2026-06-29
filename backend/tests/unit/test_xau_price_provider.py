from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts.run_xau_market_context_snapshot import _resolve_traded_price
from src.models.xau_price_provider import XauPriceProviderKind
from src.xau_market_context.price_provider import (
    build_resolved_market_inputs,
    manual_price,
    resolve_latest_price_from_bars,
    should_pass_gc_price_to_builder,
)


def test_local_bars_resolver_uses_latest_close_and_timestamp(tmp_path: Path) -> None:
    path = tmp_path / "xauusd_1m.csv"
    path.write_text(
        "\n".join(
            [
                "timestamp,open,high,low,close",
                "2026-06-29T14:14:00+07:00,4050,4052,4049,4051",
                "2026-06-29T14:15:00+07:00,4051,4053,4050,4052",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    price = resolve_latest_price_from_bars(path, symbol="XAUUSD")

    assert price.price == 4052
    assert price.timestamp == datetime.fromisoformat("2026-06-29T14:15:00+07:00")
    assert price.provider_quality == "research_good"


def test_current_timestamp_defaults_to_latest_traded_bar_timestamp(tmp_path: Path) -> None:
    path = tmp_path / "xauusd_1m.csv"
    path.write_text(
        "timestamp,open,high,low,close\n"
        "2026-06-29T14:15:00+07:00,4051,4053,4050,4052\n",
        encoding="utf-8",
    )

    price = resolve_latest_price_from_bars(path, symbol="XAUUSD")

    assert price.timestamp == datetime.fromisoformat("2026-06-29T14:15:00+07:00")


def test_basis_alignment_seconds_computed_and_stale_blocks_builder_input() -> None:
    tz = ZoneInfo("Asia/Bangkok")
    traded = manual_price(
        symbol="XAUUSD",
        price=4050,
        timestamp=datetime(2026, 6, 29, 14, 15, tzinfo=tz),
    )
    gc = manual_price(
        symbol="GC",
        price=4070,
        timestamp=datetime(2026, 6, 29, 14, 10, tzinfo=tz),
    )

    inputs = build_resolved_market_inputs(
        traded_price=traded,
        gc_futures_price=gc,
        current_timestamp=traded.timestamp,
        price_bars_path=None,
        fusion_report_path=None,
        max_basis_alignment_seconds=120,
        allow_stale_basis=False,
    )

    assert inputs.basis_alignment_seconds == 300
    assert "basis_alignment" in inputs.missing_inputs
    assert should_pass_gc_price_to_builder(
        inputs,
        max_basis_alignment_seconds=120,
        allow_stale_basis=False,
    ) is False
    assert should_pass_gc_price_to_builder(
        inputs,
        max_basis_alignment_seconds=120,
        allow_stale_basis=True,
    ) is True


def test_manual_cli_input_overrides_provider_inputs(tmp_path: Path) -> None:
    path = tmp_path / "xauusd_1m.csv"
    path.write_text(
        "timestamp,open,high,low,close\n"
        "2026-06-29T14:15:00+07:00,4051,4053,4050,4052\n",
        encoding="utf-8",
    )
    args = argparse.Namespace(
        xauusd_spot_price=4060,
        traded_symbol="XAUUSD",
        auto_price_provider="latest_local_import",
        spot_symbol="XAUUSD=X",
        yfinance_interval="1m",
        yfinance_period="1d",
        timezone="Asia/Bangkok",
    )

    resolved = _resolve_traded_price(
        args=args,
        price_bars_path=path,
        current_timestamp=datetime.fromisoformat("2026-06-29T14:15:00+07:00"),
    )

    assert resolved.price == 4060
    assert resolved.provider == XauPriceProviderKind.MANUAL


def test_no_null_price_becomes_zero() -> None:
    missing = manual_price(symbol="XAUUSD", price=None, timestamp=None)

    assert missing.price is None
    assert missing.provider_quality == "unavailable"

