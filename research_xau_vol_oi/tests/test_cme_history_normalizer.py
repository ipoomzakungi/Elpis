from datetime import UTC, datetime

import polars as pl

from research_xau_vol_oi.cme_history_normalizer import (
    build_coverage_report,
    build_daily_strike_expiry_panel,
    build_duplicate_conflict_report,
    build_missing_field_report,
    classify_cme_history_frame,
    discover_cme_history_files,
    build_session_regime_panel,
    normalize_cme_history_sources,
    run_cme_history_normalizer,
)


def test_row_options_build_daily_panel_with_basis_and_event_tags(tmp_path) -> None:
    options_path = tmp_path / "cme_options.csv"
    price_path = tmp_path / "xau_spot.csv"
    event_path = tmp_path / "event_calendar.csv"
    pl.DataFrame(
        [
            {
                "timestamp": "2026-05-14T14:00:00Z",
                "expiry": "2026-05-15",
                "strike": 2400,
                "option_type": "call",
                "open_interest": 100,
                "oi_change": 10,
                "volume": 30,
                "implied_volatility": 0.20,
                "underlying_futures_price": 2412,
                "xauusd_spot_price": 2405,
                "session_open": 2401,
            },
            {
                "timestamp": "2026-05-14T14:00:00Z",
                "expiry": "2026-05-15",
                "strike": 2400,
                "option_type": "put",
                "open_interest": 80,
                "oi_change": -5,
                "volume": 20,
                "implied_volatility": 0.22,
                "underlying_futures_price": 2412,
                "xauusd_spot_price": 2405,
                "session_open": 2401,
            },
        ]
    ).write_csv(options_path)
    pl.DataFrame(
        [
            {
                "timestamp": "2026-05-14T00:00:00Z",
                "symbol": "XAUUSD",
                "open": 2401,
                "high": 2410,
                "low": 2395,
                "close": 2405,
            }
        ]
    ).write_csv(price_path)
    pl.DataFrame(
        [
            {
                "timestamp": "2026-05-14T12:30:00Z",
                "event_name": "CPI release",
                "dollar_regime": "USD_EVENT",
            }
        ]
    ).write_csv(event_path)

    option_rows, price_rows, event_rows, _inventory = normalize_cme_history_sources(
        [options_path, price_path, event_path]
    )
    conflicts = build_duplicate_conflict_report(option_rows)
    daily = build_daily_strike_expiry_panel(
        option_rows,
        price_rows=price_rows,
        event_rows=event_rows,
        duplicate_conflicts=conflicts,
    )
    row = daily.row(0, named=True)

    assert row["call_oi"] == 100
    assert row["put_oi"] == 80
    assert row["basis"] == 7
    assert row["spot_equivalent_strike"] == 2393
    assert row["event_tags"] == "CPI"
    assert row["validation_grade"] is True


def test_wide_matrix_normalizes_volume_cells(tmp_path) -> None:
    matrix_path = tmp_path / "volume_matrix_20260514.csv"
    pl.DataFrame(
        [
            {"strike": 2400, "2026-05-15 C": 11, "2026-05-15 P": 12},
            {"strike": 2410, "2026-05-15 C": 13, "2026-05-15 P": 14},
        ]
    ).write_csv(matrix_path)

    option_rows, _price_rows, _event_rows, _inventory = normalize_cme_history_sources([matrix_path])

    assert option_rows.height == 4
    assert set(option_rows.get_column("option_type").to_list()) == {"call", "put"}
    assert set(option_rows.get_column("volume").to_list()) == {11.0, 12.0, 13.0, 14.0}


def test_session_coverage_reports_missing_fields_and_complete_days(tmp_path) -> None:
    option_rows = pl.DataFrame(
        [
            {
                "timestamp": datetime(2026, 5, 14, 14, tzinfo=UTC),
                "session_date": "2026-05-14",
                "source_id_hash": "a",
                "redacted_file_path": "<REDACTED_PATH>/a.csv",
                "file_name": "a.csv",
                "source_kind": "open_interest_matrix",
                "source_view": "",
                "futures_symbol": "GC",
                "expiry": "2026-05-15",
                "expiry_date": "2026-05-15",
                "dte": 1.0,
                "strike": 2400.0,
                "option_type": "call",
                "open_interest": 100.0,
                "oi_change": None,
                "volume": None,
                "iv_percent": None,
                "expected_range": None,
                "settlement_price": None,
                "futures_price": 2412.0,
                "spot_price": None,
                "session_open": None,
            }
        ]
    )
    daily = build_daily_strike_expiry_panel(option_rows)
    session = build_session_regime_panel(daily)
    coverage = build_coverage_report(session)
    missing = build_missing_field_report(coverage)

    assert coverage.row(0, named=True)["complete_validation_day"] is False
    assert "futures_to_spot_basis" in set(missing.get_column("missing_field").to_list())
    assert "iv_context" in set(missing.get_column("missing_field").to_list())


def test_duplicate_conflict_report_flags_conflicting_snapshots(tmp_path) -> None:
    options_path = tmp_path / "oi_matrix.csv"
    pl.DataFrame(
        [
            {
                "timestamp": "2026-05-14T14:00:00Z",
                "expiry": "2026-05-15",
                "strike": 2400,
                "option_type": "call",
                "open_interest": 100,
            },
            {
                "timestamp": "2026-05-14T15:00:00Z",
                "expiry": "2026-05-15",
                "strike": 2400,
                "option_type": "call",
                "open_interest": 125,
            },
        ]
    ).write_csv(options_path)

    option_rows, _price_rows, _event_rows, _inventory = normalize_cme_history_sources([options_path])
    conflicts = build_duplicate_conflict_report(option_rows)

    assert conflicts.height == 1
    assert conflicts.row(0, named=True)["has_conflict"] is True
    assert "open_interest" in conflicts.row(0, named=True)["conflict_fields"]


def test_run_normalizer_writes_required_outputs(tmp_path) -> None:
    options_path = tmp_path / "cme_options.csv"
    pl.DataFrame(
        [
            {
                "timestamp": "2026-05-14T14:00:00Z",
                "expiry": "2026-05-15",
                "strike": 2400,
                "option_type": "call",
                "open_interest": 100,
                "oi_change": 10,
                "volume": 30,
                "implied_volatility": 0.20,
                "underlying_futures_price": 2412,
                "xauusd_spot_price": 2405,
                "session_open": 2401,
            }
        ]
    ).write_csv(options_path)

    result = run_cme_history_normalizer(output_dir=tmp_path, input_paths=[options_path])

    assert result.daily_panel.height == 1
    assert (tmp_path / "cme_daily_strike_expiry_panel.parquet").exists()
    assert (tmp_path / "cme_session_regime_panel.parquet").exists()
    assert (tmp_path / "cme_history_coverage_report.csv").exists()
    assert (tmp_path / "cme_history_missing_field_report.csv").exists()
    assert (tmp_path / "cme_history_duplicate_conflict_report.csv").exists()


def test_discovery_skips_generated_cme_outputs_and_signal_events(tmp_path) -> None:
    generated = tmp_path / "cme_daily_strike_expiry_panel.parquet"
    signal_events = tmp_path / "signal_events.csv"
    source = tmp_path / "quikstrike_oi_matrix.csv"
    pl.DataFrame({"session_date": ["2026-05-14"], "strike": [2400]}).write_parquet(generated)
    pl.DataFrame({"event_timestamp": ["2026-05-14T00:00:00Z"], "signal": ["NO_TRADE"]}).write_csv(
        signal_events
    )
    pl.DataFrame(
        {
            "timestamp": ["2026-05-14T00:00:00Z"],
            "strike": [2400],
            "option_type": ["call"],
            "open_interest": [100],
        }
    ).write_csv(source)

    discovered = discover_cme_history_files([tmp_path])
    names = {path.name for path in discovered}

    assert source.name in names
    assert generated.name not in names
    assert "event_calendar" not in classify_cme_history_frame(signal_events, pl.read_csv(signal_events))
