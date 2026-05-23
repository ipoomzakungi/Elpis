from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from research_xau_vol_oi.current_week_replay import (
    build_current_week_cme_guru_replay,
    build_guru_filter_replay,
    build_spot_basis_backfill,
    build_validation_upgrade_report,
    current_week_cme_guru_replay_markdown,
    detect_spot_ohlc_files,
    guru_filter_replay_markdown,
    run_current_week_replay_layer,
    validation_upgrade_markdown,
)


def test_spot_detector_finds_synthetic_xau_ohlc_file(tmp_path: Path) -> None:
    source = tmp_path / "xauusd_spot_20260514.csv"
    pl.DataFrame(
        [
            {
                "timestamp": "2026-05-14T12:00:00Z",
                "symbol": "XAUUSD",
                "open": 2400.0,
                "high": 2410.0,
                "low": 2390.0,
                "close": 2405.0,
            }
        ]
    ).write_csv(source)

    audit, spot = detect_spot_ohlc_files([tmp_path], cme_dates={"2026-05-14"})

    assert audit.height == 1
    assert spot.height == 1
    assert audit.row(0, named=True)["detected_symbol"] == "XAUUSD"
    assert audit.row(0, named=True)["can_join_to_cme_dates"] is True


def test_basis_backfill_computes_futures_minus_spot_correctly() -> None:
    spot = _spot_rows("2026-05-14", close=2401.0)
    futures = _futures_rows("2026-05-14", price=2407.5)

    _, basis, _ = build_spot_basis_backfill(
        futures=futures,
        detected_spot=spot,
        join_tolerance_minutes=1440,
    )

    row = basis.row(0, named=True)
    assert row["futures_price"] == 2407.5
    assert row["spot_price"] == 2401.0
    assert row["basis"] == 6.5


def test_daily_ohlc_join_marks_daily_approx() -> None:
    spot = _spot_rows("2026-05-14", close=2401.0, granularity="DAILY")
    futures = _futures_rows("2026-05-14", price=2407.5)

    _, basis, _ = build_spot_basis_backfill(
        futures=futures,
        detected_spot=spot,
        join_tolerance_minutes=1440,
    )

    assert basis.row(0, named=True)["basis_quality"] == "DAILY_APPROX"


def test_intraday_ohlc_join_marks_intraday_join() -> None:
    spot = _spot_rows("2026-05-14", close=2401.0, granularity="INTRADAY")
    futures = _futures_rows("2026-05-14", price=2407.5)

    _, basis, _ = build_spot_basis_backfill(
        futures=futures,
        detected_spot=spot,
        join_tolerance_minutes=60,
    )

    assert basis.row(0, named=True)["basis_quality"] == "INTRADAY_JOIN"


def test_pilot_replay_works_without_spot_and_marks_futures_strike_level() -> None:
    replay = build_current_week_cme_guru_replay(
        frames=_frames(
            date_usability=_date_usability("2026-05-14"),
            one_week=pl.DataFrame(
                [{"trade_date": "2026-05-14", "pilot_grade": "CME_OI_VOLUME_NEEDS_SPOT_BASIS"}]
            ),
            option_oi=_oi_rows("2026-05-14"),
            futures=_futures_rows("2026-05-14", price=2405.0),
        ),
        backfilled_basis=pl.DataFrame(),
        backfilled_spot=pl.DataFrame(),
    )

    row = replay.row(0, named=True)
    assert row["wall_type"] == "FUTURES_STRIKE_LEVEL"
    assert row["oi_available"] is True
    assert row["spot_available"] is False


def test_pilot_replay_uses_spot_equivalent_walls_when_basis_exists() -> None:
    replay = build_current_week_cme_guru_replay(
        frames=_frames(
            date_usability=_date_usability("2026-05-14"),
            one_week=pl.DataFrame(
                [{"trade_date": "2026-05-14", "pilot_grade": "FULL_CME_VOL_OI"}]
            ),
            option_oi=_oi_rows("2026-05-14"),
            futures=_futures_rows("2026-05-14", price=2405.0),
        ),
        backfilled_basis=pl.DataFrame(
            [
                {
                    "trade_date": "2026-05-14",
                    "timestamp": datetime(2026, 5, 14, 12, tzinfo=UTC),
                    "futures_price": 2405.0,
                    "spot_price": 2400.0,
                    "basis": 5.0,
                    "basis_quality": "INTRADAY_JOIN",
                    "join_tolerance": "60m",
                    "source_hashes": "a|b",
                    "notes": "test",
                }
            ]
        ),
        backfilled_spot=_spot_rows("2026-05-14", close=2400.0),
    )

    row = replay.row(0, named=True)
    assert row["wall_type"] == "SPOT_EQUIVALENT_LEVEL"
    assert row["top_oi_wall_1"] == 2400.0


def test_no_trade_filter_replay_retains_no_trade_rows() -> None:
    replay = build_guru_filter_replay(
        frames=_frames(
            signal_events=pl.DataFrame(
                [
                    {
                        "event_timestamp": "2026-05-14T12:00:00Z",
                        "signal": "NO_TRADE",
                        "reason": "data_quality_or_mapping_block",
                    },
                    {
                        "event_timestamp": "2026-05-14T12:15:00Z",
                        "signal": "WATCH_WALL",
                        "reason": "context",
                    },
                ]
            )
        ),
        replay_dates={"2026-05-14"},
    )

    blocked = replay.filter(pl.col("would_block_trade"))
    assert replay.height == 2
    assert blocked.height == 1
    assert blocked.row(0, named=True)["base_signal"] == "NO_TRADE"


def test_validation_upgrade_report_does_not_claim_money_readiness() -> None:
    report = build_validation_upgrade_report(
        date_usability=_date_usability("2026-05-14"),
        backfilled_basis=pl.DataFrame(
            [
                {
                    "trade_date": "2026-05-14",
                    "timestamp": datetime(2026, 5, 14, 12, tzinfo=UTC),
                    "futures_price": 2405.0,
                    "spot_price": 2400.0,
                    "basis": 5.0,
                    "basis_quality": "INTRADAY_JOIN",
                    "join_tolerance": "60m",
                    "source_hashes": "a|b",
                    "notes": "test",
                }
            ]
        ),
        validation_day_threshold=20,
    )

    row = report.row(0, named=True)
    assert row["money_readiness_changed"] is False
    assert "Money-readiness changed: `false`" in validation_upgrade_markdown(report, 20)


def test_redacted_paths_only(tmp_path: Path) -> None:
    source = tmp_path / "xau spot.csv"
    pl.DataFrame(
        [
            {
                "timestamp": "2026-05-14T12:00:00Z",
                "symbol": "XAU/USD",
                "open": 2400.0,
                "high": 2410.0,
                "low": 2390.0,
                "close": 2405.0,
            }
        ]
    ).write_csv(source)

    audit, _ = detect_spot_ohlc_files([tmp_path], cme_dates={"2026-05-14"})
    text = audit.row(0, named=True)["redacted_path"]

    assert str(tmp_path) not in text
    assert text.startswith("<REDACTED_PATH>/")


def test_reports_say_pilot_not_validated_edge(tmp_path: Path) -> None:
    output = tmp_path / "outputs"
    output.mkdir()
    _date_usability("2026-05-14").write_csv(output / "current_cme_date_usability.csv")
    pl.DataFrame(
        [{"trade_date": "2026-05-14", "pilot_grade": "CME_OI_VOLUME_NEEDS_SPOT_BASIS"}]
    ).write_csv(output / "one_week_cme_pilot_summary.csv")
    _oi_rows("2026-05-14").write_parquet(output / "cme_canonical_option_oi_by_strike.parquet")
    _futures_rows("2026-05-14", price=2405.0).write_parquet(output / "cme_canonical_futures_price.parquet")
    pl.DataFrame(
        [
            {
                "event_timestamp": "2026-05-14T12:00:00Z",
                "signal": "NO_TRADE",
                "reason": "data_quality_or_mapping_block",
            }
        ]
    ).write_csv(output / "signal_events.csv")

    result = run_current_week_replay_layer(output_dir=output, spot_roots=[tmp_path])
    replay_report = current_week_cme_guru_replay_markdown(result.replay, result.final_recommendation)
    filter_report = guru_filter_replay_markdown(result.guru_filter_replay)

    assert "pilot" in replay_report.lower()
    assert "validated edge" in replay_report.lower()
    assert "pilot" in filter_report.lower()
    assert "profitable" not in replay_report.lower()


def _frames(**overrides: pl.DataFrame) -> dict[str, pl.DataFrame]:
    frames = {
        "date_usability": pl.DataFrame(),
        "one_week": pl.DataFrame(),
        "ohlc_guru": pl.DataFrame(),
        "option_oi": pl.DataFrame(),
        "option_iv": pl.DataFrame(),
        "futures": pl.DataFrame(),
        "spot": pl.DataFrame(),
        "basis": pl.DataFrame(),
        "validation_dataset": pl.DataFrame(),
        "guru_kb": pl.DataFrame(),
        "guru_priority": pl.DataFrame(),
        "signal_events": pl.DataFrame(),
        "backtest_summary": pl.DataFrame(),
    }
    frames.update(overrides)
    return frames


def _date_usability(trade_date: str) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "trade_date": trade_date,
                "current_validation_grade": "UNUSABLE",
                "strict_validation_grade": "UNUSABLE",
                "pilot_usability_grade": "CME_OI_VOLUME_NEEDS_SPOT_BASIS",
                "complete_validation_grade": False,
                "has_xau_spot_price": False,
                "has_gc_futures_price": True,
                "has_basis": False,
                "has_option_oi_by_strike": True,
                "has_option_oi_change": True,
                "has_option_volume": True,
                "has_option_iv": True,
                "has_option_settlement": False,
                "has_expiry_dte": True,
                "has_macro_event_flag": False,
                "missing_components": "xau_spot_price|basis",
            }
        ]
    )


def _spot_rows(trade_date: str, *, close: float, granularity: str = "INTRADAY") -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "timestamp": datetime.fromisoformat(f"{trade_date}T12:00:00+00:00"),
                "trade_date": trade_date,
                "symbol": "XAUUSD",
                "open": close,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": None,
                "source_hash": "spot_hash",
                "redacted_path": "<REDACTED_PATH>/xau.csv",
                "timestamp_granularity": granularity,
            }
        ]
    )


def _futures_rows(trade_date: str, *, price: float) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "timestamp": datetime.fromisoformat(f"{trade_date}T12:00:00+00:00"),
                "trade_date": trade_date,
                "product": "Gold",
                "contract_month": "",
                "futures_symbol": "GC",
                "open": price,
                "high": price + 2.0,
                "low": price - 2.0,
                "close": price,
                "settle": price,
                "volume": 1.0,
                "open_interest": None,
                "source_file_hash": "future_hash",
            }
        ]
    )


def _oi_rows(trade_date: str) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "asof_timestamp": datetime.fromisoformat(f"{trade_date}T12:00:00+00:00"),
                "trade_date": trade_date,
                "expiry": "2026-05-22",
                "dte": 5.0,
                "option_type": "call",
                "strike": 2405.0,
                "total_oi": 100.0,
                "total_oi_change": 10.0,
                "total_volume": 25.0,
            },
            {
                "asof_timestamp": datetime.fromisoformat(f"{trade_date}T12:00:00+00:00"),
                "trade_date": trade_date,
                "expiry": "2026-05-22",
                "dte": 5.0,
                "option_type": "put",
                "strike": 2390.0,
                "total_oi": 50.0,
                "total_oi_change": -5.0,
                "total_volume": 12.0,
            },
        ]
    )
