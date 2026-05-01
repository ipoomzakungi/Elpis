import polars as pl

from src.models.xau import XauOptionType
from src.xau.imports import validate_options_oi_file, validate_options_oi_frame


def valid_options_frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "timestamp": ["2026-04-30T16:00:00Z", "2026-04-30T16:00:00Z"],
            "expiry": ["2026-05-07", "2026-05-07"],
            "strike": [2400.0, 2380.0],
            "option_type": ["call", "put"],
            "open_interest": [12500.0, 8300.0],
            "oi_change": [250.0, -100.0],
            "volume": [900.0, 400.0],
            "implied_volatility": [0.16, 0.17],
            "underlying_futures_price": [2410.0, 2410.0],
            "xauusd_spot_price": [2403.0, 2403.0],
            "delta": [0.45, -0.35],
            "gamma": [0.02, 0.018],
        }
    )


def test_validate_options_oi_csv_accepts_required_and_optional_columns(tmp_path):
    path = tmp_path / "gold_options.csv"
    valid_options_frame().write_csv(path)

    report = validate_options_oi_file(path)

    assert report.is_valid is True
    assert report.source_row_count == 2
    assert report.accepted_row_count == 2
    assert report.rejected_row_count == 0
    assert report.timestamp_column == "timestamp"
    assert "implied_volatility" in report.optional_columns_present
    assert report.rows[0].option_type == XauOptionType.CALL
    assert report.rows[0].days_to_expiry == 7


def test_validate_options_oi_parquet_accepts_date_column(tmp_path):
    path = tmp_path / "gold_options.parquet"
    valid_options_frame().rename({"timestamp": "date"}).write_parquet(path)

    report = validate_options_oi_file(path)

    assert report.is_valid is True
    assert report.timestamp_column == "date"
    assert report.accepted_row_count == 2


def test_validate_options_oi_frame_reports_missing_required_columns():
    frame = pl.DataFrame(
        {
            "date": ["2026-04-30"],
            "strike": [2400.0],
            "option_type": ["call"],
        }
    )

    report = validate_options_oi_frame(frame, file_path="memory.csv")

    assert report.is_valid is False
    assert report.required_columns_missing == ["expiry", "open_interest"]
    assert "Provide a local CSV or Parquet file" in report.instructions[0]


def test_validate_options_oi_frame_rejects_unparseable_rows():
    frame = pl.DataFrame(
        {
            "timestamp": ["not-a-date", "2026-04-30", "2026-04-30T00:00:00"],
            "expiry": ["2026-05-07", "2026-05-07", "2026-04-29"],
            "strike": ["bad", "2400", "2400"],
            "option_type": ["call", "put", "put"],
            "open_interest": ["12500", "-1", "10"],
        }
    )

    report = validate_options_oi_frame(frame, file_path="memory.csv")

    assert report.is_valid is False
    assert report.accepted_row_count == 0
    assert report.rejected_row_count == 3
    assert any("timestamp is not parseable" in error for error in report.errors)
    assert any("expiry must not be before" in error for error in report.errors)


def test_validate_options_oi_file_rejects_unsafe_path():
    report = validate_options_oi_file("../gold_options.csv")

    assert report.is_valid is False
    assert "Unsafe file path" in report.errors[0]
    assert "data/raw/xau" in report.instructions[0]


def test_validate_options_oi_file_reports_missing_file(tmp_path):
    report = validate_options_oi_file(tmp_path / "missing.csv")

    assert report.is_valid is False
    assert "File not found" in report.errors[0]


def test_validate_options_oi_frame_keeps_unknown_option_type_with_warning():
    frame = valid_options_frame().with_columns(pl.lit("straddle").alias("option_type"))

    report = validate_options_oi_frame(frame, file_path="memory.csv")

    assert report.is_valid is True
    assert report.rows[0].option_type == XauOptionType.UNKNOWN
    assert "put/call wall classification will be limited" in report.warnings[0]
