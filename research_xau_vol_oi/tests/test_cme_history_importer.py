from datetime import datetime

import polars as pl

from research_xau_vol_oi.cme_history_importer import (
    build_basis_table,
    build_canonical_cme_tables,
    classify_validation_grade_days,
    compare_basis_adjustment_precision,
    detect_cme_export_type,
    load_and_detect_cme_files,
    run_cme_history_importer,
)
from research_xau_vol_oi.research_decision_gate import evaluate_research_decision_gates


def _write_full_sources(tmp_path, *, include_iv: bool = True, include_futures: bool = True) -> list:
    paths = []
    option = tmp_path / "quikstrike_open_interest_heatmap_20260514.csv"
    option_row = {
        "timestamp": "2026-05-14T14:00:00Z",
        "expiry": "2026-05-15",
        "dte": 1,
        "strike": 2410,
        "call_oi": 120,
        "put_oi": 80,
        "call_oi_change": 15,
        "put_oi_change": -5,
        "call_volume": 40,
        "put_volume": 30,
        "settlement_price": 12.5,
        "option_type": "call",
    }
    if include_iv:
        option_row["implied_vol"] = 0.22
    pl.DataFrame([option_row]).write_csv(option)
    paths.append(option)

    if include_futures:
        futures = tmp_path / "gc_futures_price_20260514.csv"
        pl.DataFrame(
            [
                {
                    "timestamp": "2026-05-14T14:00:00Z",
                    "futures_symbol": "GC",
                    "open": 2412,
                    "high": 2420,
                    "low": 2405,
                    "close": 2415,
                    "settle": 2415,
                    "volume": 1000,
                    "open_interest": 5000,
                }
            ]
        ).write_csv(futures)
        paths.append(futures)

    spot = tmp_path / "xau_spot_price_20260514.csv"
    pl.DataFrame(
        [
            {
                "timestamp": "2026-05-14T14:00:00Z",
                "symbol": "XAUUSD",
                "open": 2400,
                "high": 2410,
                "low": 2390,
                "close": 2405,
                "volume": 100,
            }
        ]
    ).write_csv(spot)
    paths.append(spot)
    return paths


def test_file_type_detection_works_with_synthetic_quikstrike_csv(tmp_path) -> None:
    option_path = _write_full_sources(tmp_path)[0]
    frame = pl.read_csv(option_path)

    detection = detect_cme_export_type(option_path, frame)

    assert detection["detected_type"] == "OPEN_INTEREST_HEATMAP"
    assert detection["confidence"] > 0
    assert "strike" in detection["matched_columns"]


def test_canonical_schema_output_columns_exist(tmp_path) -> None:
    loaded = load_and_detect_cme_files(_write_full_sources(tmp_path))
    canonical = build_canonical_cme_tables(loaded)

    assert {
        "asof_timestamp",
        "trade_date",
        "strike",
        "call_oi",
        "put_oi",
        "total_oi",
        "source_file_hash",
    }.issubset(canonical["option_oi_by_strike"].columns)
    assert {"timestamp", "trade_date", "futures_symbol", "close", "settle"}.issubset(
        canonical["futures_price"].columns
    )
    assert {"timestamp", "trade_date", "basis", "basis_quality"}.issubset(
        canonical["basis"].columns
    )


def test_validation_grade_classifier_marks_full_cme_vol_oi(tmp_path) -> None:
    loaded = load_and_detect_cme_files(_write_full_sources(tmp_path))
    canonical = build_canonical_cme_tables(loaded)
    days = classify_validation_grade_days(canonical)

    row = days.row(0, named=True)
    assert row["validation_grade"] == "FULL_CME_VOL_OI"
    assert row["complete_validation_grade"] is True


def test_missing_iv_prevents_full_cme_vol_oi(tmp_path) -> None:
    loaded = load_and_detect_cme_files(_write_full_sources(tmp_path, include_iv=False))
    canonical = build_canonical_cme_tables(loaded)
    days = classify_validation_grade_days(canonical)

    row = days.row(0, named=True)
    assert row["validation_grade"] == "CME_OI_ONLY"
    assert row["complete_validation_grade"] is False
    assert "option_iv" in row["missing_components"]


def test_missing_basis_prevents_full_cme_vol_oi(tmp_path) -> None:
    loaded = load_and_detect_cme_files(_write_full_sources(tmp_path, include_futures=False))
    canonical = build_canonical_cme_tables(loaded)
    days = classify_validation_grade_days(canonical)

    row = days.row(0, named=True)
    assert row["complete_validation_grade"] is False
    assert "basis" in row["missing_components"]


def test_oi_only_day_is_not_treated_as_full_validation(tmp_path) -> None:
    option = tmp_path / "quikstrike_open_interest_heatmap_20260514.csv"
    pl.DataFrame(
        [
            {
                "timestamp": "2026-05-14T14:00:00Z",
                "expiry": "2026-05-15",
                "dte": 1,
                "strike": 2410,
                "call_oi": 120,
                "put_oi": 80,
            }
        ]
    ).write_csv(option)

    loaded = load_and_detect_cme_files([option])
    days = classify_validation_grade_days(build_canonical_cme_tables(loaded))

    row = days.row(0, named=True)
    assert row["validation_grade"] == "UNUSABLE"
    assert row["complete_validation_grade"] is False


def test_basis_adjustment_formula_and_precision(tmp_path) -> None:
    loaded = load_and_detect_cme_files(_write_full_sources(tmp_path))
    canonical = build_canonical_cme_tables(loaded)
    basis = build_basis_table(canonical["futures_price"], canonical["xau_spot_price"])
    validation_days = classify_validation_grade_days(canonical)
    from research_xau_vol_oi.cme_history_importer import build_validation_dataset

    dataset = build_validation_dataset(canonical, validation_days)
    precision = compare_basis_adjustment_precision(canonical, dataset)

    assert basis.row(0, named=True)["basis"] == 10
    assert dataset.row(0, named=True)["nearest_spot_equivalent_wall_below"] == 2400
    assert not precision.is_empty()


def test_redacted_path_output(tmp_path) -> None:
    result = run_cme_history_importer(output_dir=tmp_path / "out", input_paths=_write_full_sources(tmp_path))
    redacted = result.file_detection.get_column("redacted_file_path").to_list()

    assert redacted
    assert all(str(value).startswith("<REDACTED_PATH>/") for value in redacted)
    assert all(str(tmp_path) not in str(value) for value in redacted)


def test_duplicate_snapshot_handling(tmp_path) -> None:
    option = tmp_path / "quikstrike_open_interest_heatmap_20260514.csv"
    pl.DataFrame(
        [
            {
                "timestamp": "2026-05-14T14:00:00Z",
                "expiry": "2026-05-15",
                "dte": 1,
                "strike": 2410,
                "option_type": "call",
                "open_interest": 120,
            },
            {
                "timestamp": "2026-05-14T15:00:00Z",
                "expiry": "2026-05-15",
                "dte": 1,
                "strike": 2410,
                "option_type": "call",
                "open_interest": 140,
            },
        ]
    ).write_csv(option)

    result = run_cme_history_importer(output_dir=tmp_path / "out", input_paths=[option])

    assert result.duplicate_conflict_report.height == 1
    assert result.duplicate_conflict_report.row(0, named=True)["has_conflict"] is True


def test_decision_gate_blocks_when_validation_grade_days_below_threshold() -> None:
    days = pl.DataFrame(
        [
            {
                "trade_date": "2026-05-14",
                "has_xau_spot_price": True,
                "has_gc_futures_price": True,
                "has_basis": True,
                "has_option_oi_by_strike": True,
                "has_option_oi_change": True,
                "has_option_volume": True,
                "has_option_iv": True,
                "has_option_settlement": True,
                "has_expiry_dte": True,
                "has_macro_event_flag": True,
                "complete_validation_grade": True,
                "missing_components": "",
                "validation_grade": "FULL_CME_VOL_OI",
            }
        ]
    )
    uplift = pl.DataFrame(
        [
            {
                "stage": "FULL_CME_VOL_OI",
                "event_count": 1,
                "trade_count": 0,
                "expectancy": None,
                "profit_factor": None,
                "max_drawdown": None,
                "win_rate": None,
                "walk_forward_pass": False,
                "placebo_pass": False,
                "sample_size_warning": True,
                "cost_stress_survival": False,
                "uplift_vs_price_only": None,
                "uplift_vs_bollinger": None,
                "uplift_vs_sd_only": None,
                "notes": "small sample",
            }
        ]
    )

    result = evaluate_research_decision_gates(
        {"cme_validation_grade_days": days, "cme_validation_grade_uplift": uplift},
        min_validation_dates=2,
    )

    assert result.final_label == "NOT_READY_DATA_INSUFFICIENT"
    row = result.gate_report.filter(pl.col("gate_name") == "DATA_COVERAGE_GATE").row(0, named=True)
    assert row["status"] == "FAIL"
    assert "enough_cme_validation_dates" in row["blocking_issues"]


def test_timestamp_columns_are_timezone_aware_in_canonical_tables(tmp_path) -> None:
    result = run_cme_history_importer(output_dir=tmp_path / "out", input_paths=_write_full_sources(tmp_path))

    assert result.option_oi_by_strike.get_column("asof_timestamp").dtype.time_zone == "UTC"
    assert result.futures_price.get_column("timestamp").dtype.time_zone == "UTC"
    assert isinstance(result.option_oi_by_strike.row(0, named=True)["asof_timestamp"], datetime)
