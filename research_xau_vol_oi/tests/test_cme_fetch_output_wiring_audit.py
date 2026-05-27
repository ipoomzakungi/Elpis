from __future__ import annotations

import re
from pathlib import Path

import polars as pl

from research_xau_vol_oi.cme_fetch_output_wiring_audit import (
    build_cme_fetched_data_usability_gap,
    build_cme_overlap_backtest_rerun,
    cme_fetch_output_wiring_audit_report_lines,
    report_text_is_safe,
    run_cme_fetch_output_wiring_audit,
)
from research_xau_vol_oi.quikstrike_intraday_volume_snapshot import (
    map_fetched_cme_rows_to_snapshot_schema,
    run_quikstrike_intraday_volume_snapshot,
)


def test_fetched_cme_file_preferred_over_manual_csv(tmp_path: Path) -> None:
    output = tmp_path / "outputs"
    fetched_root = tmp_path / "backend" / "data" / "reports" / "xau_quikstrike_fusion"
    output.mkdir(parents=True)
    _manual_rows(strike=4999.0).write_csv(output / "quikstrike_intraday_volume_manual.csv")
    _write_fetched_rows(fetched_root)

    result = run_quikstrike_intraday_volume_snapshot(
        output_dir=output,
        fetched_roots=[fetched_root],
        allow_fallback_example=True,
    )
    strikes = set(result.snapshot.get_column("strike").to_list())

    assert result.source_resolution.row(0, named=True)["selected_source_type"] == "FETCHED_CME_DATA"
    assert 4550.0 in strikes
    assert 4999.0 not in strikes


def test_fallback_example_not_used_when_fetched_data_exists(tmp_path: Path) -> None:
    output = tmp_path / "outputs"
    fetched_root = tmp_path / "backend" / "data" / "reports" / "xau_quikstrike_fusion"
    output.mkdir(parents=True)
    _write_fetched_rows(fetched_root)

    result = run_quikstrike_intraday_volume_snapshot(
        output_dir=output,
        fetched_roots=[fetched_root],
        allow_fallback_example=True,
    )

    assert result.source_resolution.row(0, named=True)["selected_source_type"] == "FETCHED_CME_DATA"
    assert result.source_resolution.row(0, named=True)["selected_source_type"] != "FALLBACK_EXAMPLE"


def test_source_resolution_reports_selected_source(tmp_path: Path) -> None:
    output = tmp_path / "outputs"
    fetched_root = tmp_path / "backend" / "data" / "reports" / "xau_quikstrike_fusion"
    output.mkdir(parents=True)
    _write_fetched_rows(fetched_root)

    result = run_quikstrike_intraday_volume_snapshot(
        output_dir=output,
        fetched_roots=[fetched_root],
    )
    row = result.source_resolution.row(0, named=True)

    assert row["selected_source_type"] == "FETCHED_CME_DATA"
    assert row["rows_loaded"] == result.snapshot.height
    assert row["selected_source_hash"]


def test_fetched_data_schema_maps_to_snapshot_schema() -> None:
    mapped = map_fetched_cme_rows_to_snapshot_schema(_fetched_rows())
    rows = {row["strike"]: row for row in mapped.to_dicts()}

    assert rows[4550.0]["call_volume"] == 155.0
    assert rows[4500.0]["put_volume"] == 78.0
    assert rows[4550.0]["future_price"] == 4532.6


def test_missing_columns_create_usability_gap() -> None:
    inventory = pl.DataFrame(
        [
            {
                "redacted_path": "<PROJECT_ROOT>/bad.csv",
                "source_hash": "abc",
                "file_name": "bad.csv",
                "detected_type": "QUIKSTRIKE_INTRADAY_VOLUME",
                "rows_count": 1,
                "date_start": "2026-05-27",
                "date_end": "2026-05-27",
                "key_columns": "timestamp,option_type,intraday_volume",
                "can_feed_quikstrike_snapshot": False,
                "can_feed_cme_overlap_backtest": False,
                "notes": "missing strike",
            }
        ],
        infer_schema_length=None,
    )
    source = pl.DataFrame(
        [
            {
                "selected_source_type": "NONE",
                "selected_source_hash": "",
                "selected_date": "",
                "selected_expiration": "",
                "rows_loaded": 0,
                "reason": "none",
            }
        ],
        infer_schema_length=None,
    )

    gap = build_cme_fetched_data_usability_gap(inventory=inventory, source_resolution=source)
    row = gap.row(0, named=True)

    assert row["no_strike_column"] is True
    assert "strike" in row["missing_columns"]


def test_cme_overlap_rerun_creates_output(tmp_path: Path) -> None:
    output = _write_overlap_inputs(tmp_path)

    result = run_cme_fetch_output_wiring_audit(output_dir=output)

    assert result.paths["overlap_rerun_csv"].exists()
    assert "CME_WALL_FILTER" in set(result.overlap_rerun.get_column("scenario").to_list())


def test_tiny_sample_remains_pilot_only(tmp_path: Path) -> None:
    output = _write_overlap_inputs(tmp_path)

    rerun = build_cme_overlap_backtest_rerun(output_root=output)
    warnings = " ".join(str(row["pilot_warning"]) for row in rerun.to_dicts())

    assert "NEED_MORE_CME_DAYS" in warnings
    assert bool(rerun.get_column("sample_size_warning").all())


def test_reports_avoid_direct_order_terms_and_money_claims(tmp_path: Path) -> None:
    output = _write_overlap_inputs(tmp_path)
    result = run_cme_fetch_output_wiring_audit(output_dir=output)
    report = "\n".join(cme_fetch_output_wiring_audit_report_lines(result))
    direct_order_pattern = re.compile(r"\b(?:bu[y]|se[ll])\b", flags=re.IGNORECASE)

    assert direct_order_pattern.search(report) is None
    assert "profitable" not in report.lower()
    assert "profitability" not in report.lower()
    assert report_text_is_safe(report)


def test_redacted_paths_only() -> None:
    text = report_text_is_safe(r"C:\Users\example\private\cme.csv")

    assert text is True


def _write_overlap_inputs(tmp_path: Path) -> Path:
    output = tmp_path / "outputs"
    fetched_root = tmp_path / "backend" / "data" / "reports" / "xau_quikstrike_fusion"
    output.mkdir(parents=True)
    _write_fetched_rows(fetched_root)
    _latest_indicator_state().write_csv(output / "xau_indicator_latest_state.csv")
    _filter_rows().write_csv(output / "cme_overlap_filter_backtest.csv")
    _candidate_rows().write_csv(output / "cme_overlap_trade_candidates.csv")
    _date_audit_rows().write_csv(output / "cme_overlap_backtest_date_audit.csv")
    return output


def _fetched_rows() -> pl.DataFrame:
    rows = [
        _fetched_row(4500.0, "put", 78.0),
        _fetched_row(4500.0, "call", 5.0),
        _fetched_row(4550.0, "put", 20.0),
        _fetched_row(4550.0, "call", 155.0),
        _fetched_row(4600.0, "call", 50.0),
    ]
    return pl.DataFrame(rows, infer_schema_length=None)


def _write_fetched_rows(fetched_root: Path) -> None:
    path = fetched_root / "run_20260527" / "xau_vol_oi_input.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    _fetched_rows().write_csv(path)


def _fetched_row(strike: float, option_type: str, volume: float) -> dict[str, object]:
    return {
        "date": "2026-05-27",
        "timestamp": "2026-05-27T06:07:57+00:00",
        "expiry": "2026-05-29",
        "expiration_code": "OG5K6",
        "strike": strike,
        "option_type": option_type,
        "open_interest": volume * 2,
        "oi_change": 0.0,
        "volume": volume,
        "intraday_volume": volume,
        "implied_volatility": 0.24,
        "underlying_futures_price": 4532.6,
    }


def _manual_rows(*, strike: float) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "snapshot_timestamp": "2026-05-27T08:00:00+00:00",
                "product": "Gold",
                "expiration": "MANUAL",
                "dte": 0.53,
                "future_price": 4532.6,
                "strike": strike,
                "put_volume": 1.0,
                "call_volume": 1.0,
                "total_volume": 2.0,
                "volatility": 24.56,
                "volatility_change": 0.11,
                "future_change": -2.4,
                "range_label": "manual",
                "notes": "manual fallback row",
            }
        ],
        infer_schema_length=None,
    )


def _filter_rows() -> pl.DataFrame:
    rows = [
        {
            "scenario": "RAW_CANDIDATES",
            "candidate_count": 2,
            "allowed_count": 2,
            "blocked_count": 0,
            "average_return": -4.9,
            "expectancy_proxy": -4.9,
            "net_filter_value_proxy": 0.0,
            "blocked_winning_candidates": 0,
            "false_block_rate": 0.0,
        },
        {
            "scenario": "CME_WALL_FILTER_ONLY",
            "candidate_count": 2,
            "allowed_count": 1,
            "blocked_count": 1,
            "average_return": -4.5,
            "expectancy_proxy": -4.5,
            "net_filter_value_proxy": 1.0,
            "blocked_winning_candidates": 0,
            "false_block_rate": 0.0,
        },
    ]
    return pl.DataFrame(rows, infer_schema_length=None)


def _candidate_rows() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {"trade_date": "2026-05-26", "raw_pnl": -5.0, "guru_filter_context": "OK"},
            {
                "trade_date": "2026-05-27",
                "raw_pnl": -4.0,
                "guru_filter_context": "BLOCK_STALE_DATA_PERIOD",
            },
        ],
        infer_schema_length=None,
    )


def _date_audit_rows() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {"trade_date": "2026-05-26", "can_run_cme_filter_test": True},
            {"trade_date": "2026-05-27", "can_run_cme_filter_test": True},
        ],
        infer_schema_length=None,
    )


def _latest_indicator_state() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "latest_price": 4542.5,
                "final_action": "WATCH_ONLY",
            }
        ],
        infer_schema_length=None,
    )
