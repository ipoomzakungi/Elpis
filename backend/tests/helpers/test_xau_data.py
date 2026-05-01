from pathlib import Path

import polars as pl

from src.models.xau import (
    XauReferencePrice,
    XauReferenceType,
    XauVolatilitySnapshot,
    XauVolatilitySource,
    XauVolOiReportRequest,
)


def sample_xau_options_frame(include_optional: bool = True) -> pl.DataFrame:
    data = {
        "timestamp": ["2026-04-30T16:00:00Z", "2026-04-30T16:00:00Z"],
        "expiry": ["2026-05-07", "2026-05-07"],
        "strike": [2400.0, 2380.0],
        "option_type": ["call", "put"],
        "open_interest": [12500.0, 8300.0],
    }
    if include_optional:
        data.update(
            {
                "oi_change": [250.0, -100.0],
                "volume": [900.0, 400.0],
                "implied_volatility": [0.16, 0.17],
                "underlying_futures_price": [2410.0, 2410.0],
                "xauusd_spot_price": [2403.0, 2403.0],
            }
        )
    return pl.DataFrame(data)


def write_sample_xau_options_csv(path: Path, include_optional: bool = True) -> Path:
    sample_xau_options_frame(include_optional=include_optional).write_csv(path)
    return path


def write_sample_xau_options_parquet(path: Path, include_optional: bool = True) -> Path:
    sample_xau_options_frame(include_optional=include_optional).write_parquet(path)
    return path


def sample_xau_report_request(path: Path) -> XauVolOiReportRequest:
    return XauVolOiReportRequest(
        options_oi_file_path=path,
        spot_reference=XauReferencePrice(
            source="manual",
            symbol="XAUUSD",
            price=2403.0,
            reference_type=XauReferenceType.SPOT,
        ),
        futures_reference=XauReferencePrice(
            source="manual",
            symbol="GC",
            price=2410.0,
            reference_type=XauReferenceType.FUTURES,
        ),
        volatility_snapshot=XauVolatilitySnapshot(
            implied_volatility=0.16,
            source=XauVolatilitySource.IV,
            days_to_expiry=7,
        ),
        include_2sd_range=True,
    )
