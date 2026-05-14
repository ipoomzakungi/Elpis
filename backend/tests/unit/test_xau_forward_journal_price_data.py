from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest

from src.models.xau_forward_journal import (
    XauForwardPriceCoverageRequest,
    XauForwardPriceDataUpdateRequest,
    XauForwardPriceSourceLabel,
)
from src.xau_forward_journal.price_data import (
    XauForwardOhlcSchemaError,
    XauForwardPriceDataNotFoundError,
    XauForwardPriceSourceError,
    load_price_candles,
    proxy_limitations_for_source,
)


def _price_request(path: Path, **updates) -> XauForwardPriceDataUpdateRequest:
    payload = {
        "source_label": XauForwardPriceSourceLabel.LOCAL_PARQUET,
        "source_symbol": "XAUUSD local fixture",
        "ohlc_path": str(path),
        "research_only_acknowledged": True,
    }
    payload.update(updates)
    return XauForwardPriceDataUpdateRequest.model_validate(payload)


def _coverage_request(path: Path, **updates) -> XauForwardPriceCoverageRequest:
    payload = {
        "source_label": XauForwardPriceSourceLabel.LOCAL_PARQUET,
        "source_symbol": "XAUUSD local fixture",
        "ohlc_path": str(path),
        "research_only_acknowledged": True,
    }
    payload.update(updates)
    return XauForwardPriceCoverageRequest.model_validate(payload)


def _rows(start: datetime, count: int) -> list[dict]:
    return [
        {
            "timestamp": (start + timedelta(minutes=index)).isoformat(),
            "open": 4707.0 + index * 0.1,
            "high": 4708.0 + index * 0.1,
            "low": 4706.0 + index * 0.1,
            "close": 4707.5 + index * 0.1,
            "volume": 10 + index,
        }
        for index in range(count)
    ]


def _write_parquet(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows).write_parquet(path)
    return path


def _write_csv(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows).write_csv(path)
    return path


def test_load_price_candles_from_parquet_normalizes_metadata(tmp_path: Path):
    path = _write_parquet(
        tmp_path / "xau_fixture.parquet",
        list(reversed(_rows(datetime(2026, 5, 14, 3, 8, 4, tzinfo=UTC), 3))),
    )

    candles, source = load_price_candles(_price_request(path))

    assert [candle.timestamp for candle in candles] == sorted(
        candle.timestamp for candle in candles
    )
    assert source.source_label == XauForwardPriceSourceLabel.LOCAL_PARQUET
    assert source.format == "parquet"
    assert source.row_count == 3
    assert source.first_timestamp == candles[0].timestamp
    assert source.last_timestamp == candles[-1].timestamp
    assert source.limitations


def test_load_price_candles_from_csv_with_aliases(tmp_path: Path):
    path = _write_csv(
        tmp_path / "xau_fixture.csv",
        [
            {
                "time": "2026-05-14T03:08:04Z",
                "o": 4707.2,
                "h": 4710.0,
                "l": 4706.5,
                "c": 4709.0,
            }
        ],
    )

    candles, source = load_price_candles(
        _coverage_request(
            path,
            source_label=XauForwardPriceSourceLabel.LOCAL_CSV,
            timestamp_column="time",
            open_column="o",
            high_column="h",
            low_column="l",
            close_column="c",
        )
    )

    assert candles[0].close == 4709.0
    assert source.format == "csv"


def test_ohlc_schema_validation_rejects_missing_duplicate_and_impossible_values(
    tmp_path: Path,
):
    missing = _write_parquet(
        tmp_path / "missing.parquet",
        [{"timestamp": "2026-05-14T03:08:04Z", "open": 1, "high": 2, "low": 1}],
    )
    with pytest.raises(XauForwardOhlcSchemaError, match="invalid"):
        load_price_candles(_price_request(missing))

    duplicate = _write_parquet(
        tmp_path / "duplicate.parquet",
        [
            {
                "timestamp": "2026-05-14T03:08:04Z",
                "open": 4707,
                "high": 4708,
                "low": 4706,
                "close": 4707,
            },
            {
                "timestamp": "2026-05-14T03:08:04Z",
                "open": 4708,
                "high": 4709,
                "low": 4707,
                "close": 4708,
            },
        ],
    )
    with pytest.raises(XauForwardOhlcSchemaError, match="Duplicate"):
        load_price_candles(_price_request(duplicate))

    impossible = _write_parquet(
        tmp_path / "impossible.parquet",
        [
            {
                "timestamp": "2026-05-14T03:08:04Z",
                "open": 4707,
                "high": 4706,
                "low": 4708,
                "close": 4707,
            }
        ],
    )
    with pytest.raises(XauForwardOhlcSchemaError, match="invalid"):
        load_price_candles(_price_request(impossible))


def test_missing_files_and_source_file_format_mismatches_are_structured(tmp_path: Path):
    with pytest.raises(XauForwardPriceDataNotFoundError) as missing:
        load_price_candles(_price_request(tmp_path / "missing.parquet"))
    assert missing.value.code == "PRICE_DATA_NOT_FOUND"

    csv_path = _write_csv(
        tmp_path / "xau_fixture.csv",
        _rows(datetime(2026, 5, 14, 3, 8, 4, tzinfo=UTC), 1),
    )
    with pytest.raises(XauForwardPriceSourceError) as mismatch:
        load_price_candles(
            _price_request(
                csv_path,
                source_label=XauForwardPriceSourceLabel.LOCAL_PARQUET,
            )
        )
    assert mismatch.value.code == "INVALID_PRICE_SOURCE"


@pytest.mark.parametrize(
    ("label", "symbol", "should_raise"),
    [
        (XauForwardPriceSourceLabel.TRUE_XAUUSD_SPOT, "XAUUSD", False),
        (XauForwardPriceSourceLabel.TRUE_XAUUSD_SPOT, "GC=F", True),
        (XauForwardPriceSourceLabel.GC_FUTURES, "GCM26", False),
        (XauForwardPriceSourceLabel.GC_FUTURES, "GLD", True),
        (XauForwardPriceSourceLabel.YAHOO_GC_F_PROXY, "GC=F", False),
        (XauForwardPriceSourceLabel.YAHOO_GC_F_PROXY, "GCM26", True),
        (XauForwardPriceSourceLabel.GLD_ETF_PROXY, "GLD", False),
        (XauForwardPriceSourceLabel.GLD_ETF_PROXY, "XAUUSD", True),
        (XauForwardPriceSourceLabel.UNKNOWN_PROXY, "MANUAL_PROXY", False),
    ],
)
def test_source_symbol_consistency(label, symbol, should_raise, tmp_path: Path):
    path = _write_parquet(
        tmp_path / f"{label.value}.parquet",
        _rows(datetime(2026, 5, 14, 3, 8, 4, tzinfo=UTC), 1),
    )
    request = _price_request(path, source_label=label, source_symbol=symbol)

    if should_raise:
        with pytest.raises(XauForwardPriceSourceError):
            load_price_candles(request)
    else:
        _, source = load_price_candles(request)
        assert source.source_label == label


def test_proxy_limitations_are_labeled_for_all_required_sources():
    for label in XauForwardPriceSourceLabel:
        limitations = proxy_limitations_for_source(label)
        if label == XauForwardPriceSourceLabel.TRUE_XAUUSD_SPOT:
            assert limitations == []
        else:
            assert limitations
