from datetime import UTC, datetime

import pytest

from src.models.xau_walk_forward_research import XauWalkForwardSdSource
from src.xau_walk_forward.sd_source import (
    RANGE_LABEL_NOT_NUMERIC_LIMITATION,
    sd_snapshot_from_range_bands_payload,
)


def test_range_bands_with_numeric_sd_produces_cme_native_snapshot() -> None:
    snapshot = sd_snapshot_from_range_bands_payload(
        _range_bands_payload(),
        timestamp=datetime(2026, 6, 8, 10, 10, tzinfo=UTC),
    )

    assert snapshot.sd_source == XauWalkForwardSdSource.CME_NATIVE
    assert snapshot.dte == pytest.approx(0.68)
    assert snapshot.native_1sd == pytest.approx(25.0)
    assert snapshot.native_2sd == pytest.approx(50.0)
    assert snapshot.native_3sd == pytest.approx(75.0)
    assert snapshot.lower_2_5sd == pytest.approx(4437.5)
    assert snapshot.upper_2_5sd == pytest.approx(4562.5)


def test_range_label_only_does_not_create_numeric_sd() -> None:
    snapshot = sd_snapshot_from_range_bands_payload(
        {
            "extraction_id": "range_label_only",
            "views": [
                {
                    "view_type": "open_interest",
                    "future_reference_price": 4500.0,
                    "segments": [{"range_label": "1", "lower_strike": 4475.0}],
                    "cumulative_bands": [],
                }
            ],
        },
        timestamp=datetime(2026, 6, 8, 10, 10, tzinfo=UTC),
    )

    assert snapshot.sd_source == XauWalkForwardSdSource.UNAVAILABLE
    assert RANGE_LABEL_NOT_NUMERIC_LIMITATION in snapshot.limitations


def _range_bands_payload():
    return {
        "extraction_id": "quikstrike_fixture",
        "views": [
            {
                "view_type": "open_interest",
                "expiration_code": "OG2M6",
                "dte": 0.68,
                "future_reference_price": 4500.0,
                "cumulative_bands": [
                    {
                        "sigma": 1,
                        "cme_numeric_sd": 25.0,
                        "lower_strike": 4475.0,
                        "upper_strike": 4525.0,
                    },
                    {
                        "sigma": 2,
                        "cme_numeric_sd": 50.0,
                        "lower_strike": 4450.0,
                        "upper_strike": 4550.0,
                    },
                    {
                        "sigma": 3,
                        "cme_numeric_sd": 75.0,
                        "lower_strike": 4425.0,
                        "upper_strike": 4575.0,
                    },
                ],
            }
        ],
    }
