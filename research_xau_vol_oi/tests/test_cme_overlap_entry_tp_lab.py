from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import polars as pl

from research_xau_vol_oi.cme_overlap_entry_tp_lab import (
    CmeOverlapEntryTpLabResult,
    basis_adjusted_wall_level,
    build_overlap_date_audit,
    build_pilot_decision,
    date_audit_markdown,
    detect_low_oi_gap_squeeze_entries,
    detect_no_trade_middle_range_blocks,
    detect_wall_acceptance_breakout_entries,
    detect_wall_rejection_fade_entries,
    entry_tp_report_markdown,
    resample_price_bars,
    simulate_trade_exit,
    summarize_entry_tp_trades,
)


def test_overlap_date_audit_marks_usable_date_correctly() -> None:
    audit = build_overlap_date_audit(
        dates=[date(2026, 5, 15)],
        price_by_timeframe={"15m": _price_frame()},
        cme_oi=_cme_oi(datetime(2026, 5, 15, 0, 0, tzinfo=UTC)),
        cme_iv=_cme_iv(datetime(2026, 5, 15, 0, 0, tzinfo=UTC)),
        cme_futures=_futures(),
        basis=_basis(),
        guru_context=pl.DataFrame([{"trade_date": "2026-05-15"}]),
        pine_signals=pl.DataFrame([{"timestamp": "2026-05-15T01:00:00Z"}]),
    )
    row = audit.row(0, named=True)

    assert row["has_dukascopy_price"]
    assert row["has_cme_oi"]
    assert row["has_cme_iv"]
    assert row["has_basis"]
    assert row["usable_for_entry_tp_pilot"]


def test_cme_asof_after_session_becomes_post_event_replay_only() -> None:
    audit = build_overlap_date_audit(
        dates=[date(2026, 5, 15)],
        price_by_timeframe={"15m": _price_frame(row_count=2)},
        cme_oi=_cme_oi(datetime(2026, 5, 16, 0, 0, tzinfo=UTC)),
        cme_iv=pl.DataFrame(),
        cme_futures=pl.DataFrame(),
        basis=pl.DataFrame(),
        guru_context=pl.DataFrame(),
        pine_signals=pl.DataFrame(),
    )
    row = audit.row(0, named=True)

    assert row["can_use_cme_only_as_post_event_replay"]
    assert not row["usable_for_entry_tp_pilot"]
    assert "POST_EVENT_REPLAY_ONLY" in row["reason_plain_english"]


def test_basis_adjusted_wall_formula() -> None:
    assert basis_adjusted_wall_level(4700.0, -4.5) == 4704.5
    assert basis_adjusted_wall_level(4700.0, 7.0) == 4693.0


def test_2h_resample_works() -> None:
    frame = _price_frame(row_count=240, minutes=1)
    resampled = resample_price_bars(frame, "2h")

    assert resampled.height == 2
    assert resampled.row(0, named=True)["open"] == frame.row(0, named=True)["open"]
    assert resampled.row(0, named=True)["high"] == frame.head(120).select(pl.max("high")).item()
    assert resampled.row(1, named=True)["timeframe"] == "2h"


def test_wall_rejection_fade_entry_logic() -> None:
    bars = _bars_from_closes([98.0, 100.5, 98.8, 98.2], highs=[99.0, 101.0, 99.0, 98.5])
    entries = detect_wall_rejection_fade_entries(bars, wall_above=100.0, wall_below=None)

    assert entries
    assert entries[0]["direction"] == "short"
    assert entries[0]["entry_pattern"] == "RESISTANCE_REJECTION"


def test_wall_acceptance_breakout_entry_logic() -> None:
    bars = _bars_from_closes([99.0, 101.0, 101.2, 102.0], highs=[99.5, 101.5, 101.8, 102.2])
    entries = detect_wall_acceptance_breakout_entries(bars, wall_above=100.0, wall_below=None)

    assert entries
    assert entries[0]["direction"] == "long"
    assert entries[0]["entry_pattern"] == "ACCEPTED_RESISTANCE_BREAK"


def test_low_oi_gap_squeeze_logic() -> None:
    bars = _bars_from_closes([98.0, 100.8, 104.0, 108.0], lows=[97.0, 100.0, 103.0, 107.0])
    entries = detect_low_oi_gap_squeeze_entries(bars, wall_above=120.0, wall_below=100.0)

    assert entries
    assert entries[0]["direction"] == "long"
    assert entries[0]["entry_pattern"] == "LOW_OI_GAP_BREAK_UP"


def test_no_trade_middle_blocks_entries() -> None:
    bars = _bars_from_closes([99.0, 100.0, 101.0])
    blocks = detect_no_trade_middle_range_blocks(bars, wall_above=110.0, wall_below=90.0)

    assert blocks
    assert blocks[0]["entry_pattern"] == "BLOCK_MIDDLE_RANGE"


def test_tp_sl_hit_detection_uses_bid_ask_correctly() -> None:
    bars = _bars_from_closes([100.0, 104.0, 105.0])
    result = simulate_trade_exit(
        bars,
        entry_index=0,
        direction="long",
        entry_price=bars[0]["ask_open"],
        tp_level=104.5,
        sl_level=98.0,
        timeout_bars=3,
    )

    assert bars[0]["ask_open"] > bars[0]["bid_open"]
    assert result["exit_reason"] == "TP_HIT"
    assert result["pnl_after_spread_cost"] == 104.5 - bars[0]["ask_open"]


def test_sample_warning_appears_for_one_day_test() -> None:
    trades = pl.DataFrame(
        [
            {
                "trade_date": "2026-05-15",
                "timeframe": "15m",
                "rule_template": "WALL_REJECTION_FADE",
                "exit_reason": "TP_HIT",
                "pnl_after_spread_cost": 2.0,
                "mfe": 3.0,
                "mae": -1.0,
            }
        ]
    )
    summary = summarize_entry_tp_trades(trades)

    assert summary.row(0, named=True)["sample_size_warning"]


def test_report_does_not_claim_profitability() -> None:
    result = CmeOverlapEntryTpLabResult(
        date_audit=pl.DataFrame(),
        market_map=pl.DataFrame(),
        rule_templates=pl.DataFrame(),
        trades=pl.DataFrame(),
        summary=pl.DataFrame(),
        timeframe_comparison=pl.DataFrame(),
        decision=build_pilot_decision(
            date_audit=pl.DataFrame(),
            market_map=pl.DataFrame(),
            trades=pl.DataFrame(),
            summary=pl.DataFrame(),
        ),
        chart_paths=(),
        final_decision="CME_WALL_CONTEXT_ONLY",
    )
    markdown = entry_tp_report_markdown(result).lower()

    assert "profitable" not in markdown
    assert "safe to trade" not in markdown
    assert "live ready" not in markdown


def test_redacted_paths_only() -> None:
    markdown = date_audit_markdown(
        pl.DataFrame(
            [
                {
                    "trade_date": "2026-05-15",
                    "has_dukascopy_price": True,
                    "has_cme_oi": True,
                    "has_cme_iv": True,
                    "has_cme_futures": True,
                    "has_basis": True,
                    "has_guru_context": False,
                    "has_pine_python_signals": False,
                    "cme_asof_timestamp": "2026-05-15T00:00:00Z",
                    "can_use_cme_before_session": True,
                    "can_use_cme_during_session": True,
                    "can_use_cme_only_as_post_event_replay": False,
                    "usable_for_entry_tp_pilot": True,
                    "missing_components": "",
                    "reason_plain_english": r"C:\Users\example\secret.parquet",
                }
            ]
        )
    )

    assert r"C:\Users" not in markdown
    assert "<REDACTED_PATH>" in markdown


def _price_frame(row_count: int = 8, minutes: int = 15) -> pl.DataFrame:
    start = datetime(2026, 5, 15, 0, 0, tzinfo=UTC)
    rows = []
    for index in range(row_count):
        timestamp = start + timedelta(minutes=minutes * index)
        close = 100.0 + index
        rows.append(
            {
                "timestamp": timestamp,
                "trade_date": timestamp.date().isoformat(),
                "timeframe": f"{minutes}m",
                "open": close - 0.5,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "spread_points": 0.2,
                "bid_open": close - 0.6,
                "bid_high": close + 0.9,
                "bid_low": close - 1.1,
                "bid_close": close - 0.1,
                "ask_open": close - 0.4,
                "ask_high": close + 1.1,
                "ask_low": close - 0.9,
                "ask_close": close + 0.1,
                "spread_available": True,
                "price_source_label": "DUKASCOPY_XAUUSD_BID_ASK",
            }
        )
    return pl.DataFrame(rows)


def _bars_from_closes(
    closes: list[float],
    *,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
) -> list[dict[str, object]]:
    start = datetime(2026, 5, 15, 0, 0, tzinfo=UTC)
    rows = []
    for index, close in enumerate(closes):
        high = highs[index] if highs is not None else close + 1.0
        low = lows[index] if lows is not None else close - 1.0
        rows.append(
            {
                "timestamp": start + timedelta(minutes=15 * index),
                "open": close - 0.2,
                "high": high,
                "low": low,
                "close": close,
                "bid_open": close - 0.3,
                "bid_high": high - 0.1,
                "bid_low": low - 0.1,
                "bid_close": close - 0.1,
                "ask_open": close - 0.1,
                "ask_high": high + 0.1,
                "ask_low": low + 0.1,
                "ask_close": close + 0.1,
                "spread_available": True,
            }
        )
    return rows


def _cme_oi(asof: datetime) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "asof_timestamp": asof,
                "trade_date": "2026-05-15",
                "strike": 100.0,
                "call_oi": 10.0,
                "put_oi": 20.0,
                "total_oi": 30.0,
                "total_volume": 5.0,
                "total_oi_change": 2.0,
            },
            {
                "asof_timestamp": asof,
                "trade_date": "2026-05-15",
                "strike": 110.0,
                "call_oi": 40.0,
                "put_oi": 10.0,
                "total_oi": 50.0,
                "total_volume": 6.0,
                "total_oi_change": 3.0,
            },
        ]
    )


def _cme_iv(asof: datetime) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "asof_timestamp": asof,
                "trade_date": "2026-05-15",
                "strike": 100.0,
                "implied_vol": 20.0,
            }
        ]
    )


def _futures() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "timestamp": datetime(2026, 5, 15, 0, 0, tzinfo=UTC),
                "trade_date": "2026-05-15",
                "close": 101.0,
            }
        ]
    )


def _basis() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "timestamp": datetime(2026, 5, 15, 0, 0, tzinfo=UTC),
                "trade_date": "2026-05-15",
                "basis": 1.0,
            }
        ]
    )
