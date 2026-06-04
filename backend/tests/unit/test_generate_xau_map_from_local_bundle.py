import json
from datetime import UTC, date, datetime
from pathlib import Path

import polars as pl
import pytest

from scripts.generate_xau_map_from_local_bundle import (
    FUSED_ROWS_FILENAME,
    REPORT_JSON_FILENAME,
    WALLS_PARQUET_FILENAME,
    LocalBundleRunConfig,
    generate_from_local_bundle,
)
from src.models.xau import XauDailyStructuralMap
from src.xau_daily_structural_map.report_store import XauDailyStructuralMapReportStore
from src.xau_quikstrike_fusion.expected_range import build_expected_range_snapshot


def test_missing_input_folder_gives_clear_error(tmp_path: Path) -> None:
    missing_dir = tmp_path / "missing_bundle"

    with pytest.raises(FileNotFoundError, match="Input directory does not exist"):
        generate_from_local_bundle(
            LocalBundleRunConfig(
                input_dir=missing_dir,
                session_date=date(2026, 6, 2),
                expiration_code="OG1M6",
                traded_instrument="XAUUSD",
            )
        )


def test_missing_required_report_json_gives_clear_error(tmp_path: Path) -> None:
    input_dir = tmp_path / "bundle"
    input_dir.mkdir()

    with pytest.raises(FileNotFoundError, match=REPORT_JSON_FILENAME):
        generate_from_local_bundle(
            LocalBundleRunConfig(
                input_dir=input_dir,
                session_date=date(2026, 6, 2),
                expiration_code="OG1M6",
                traded_instrument="XAUUSD",
            )
        )


def test_temp_bundle_writes_structural_map_artifacts_and_roundtrips(
    tmp_path: Path,
) -> None:
    input_dir = _write_temp_bundle(tmp_path)
    output_root = tmp_path / "data" / "reports"

    result = generate_from_local_bundle(
        LocalBundleRunConfig(
            input_dir=input_dir,
            session_date=date(2026, 6, 2),
            expiration_code="OG1M6",
            traded_instrument="XAUUSD",
            gc_reference_price=4549.2,
            traded_reference_price=4536.7,
            session_open_price=4538.0,
            output_root=output_root / "xau_daily_structural_map",
        )
    )

    store = XauDailyStructuralMapReportStore(reports_dir=output_root)
    report_dir = store.report_dir("xau_daily_structural_map_2026-06-02_OG1M6")

    assert (report_dir / "metadata.json").exists()
    assert (report_dir / "map.json").exists()
    assert (report_dir / "map.md").exists()
    assert (report_dir / "walls.json").exists()
    assert result.daily_map.signal_allowed is False
    assert store.read_map(result.metadata.map_id) == result.daily_map
    assert XauDailyStructuralMap.model_validate_json(
        (report_dir / "map.json").read_text(encoding="utf-8")
    )


def _write_temp_bundle(tmp_path: Path) -> Path:
    input_dir = tmp_path / "xau_quikstrike_20260602"
    input_dir.mkdir()
    (input_dir / REPORT_JSON_FILENAME).write_text(
        json.dumps(
            {
                "report": {
                    "report_id": "test_xau_vol_oi_20260602",
                    "session_date": "2026-06-02",
                    "expected_range_snapshot": _snapshot_payload(),
                    "limitations": ["Fixture local XAU Vol-OI report."],
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (input_dir / FUSED_ROWS_FILENAME).write_text("[]\n", encoding="utf-8")
    pl.DataFrame(
        [
            {
                "wall_id": "wall_4550_call",
                "expiry": "2026-06-05",
                "expiration_code": "OG1M6",
                "strike": 4550.0,
                "option_type": "call",
                "open_interest": 1000.0,
                "oi_change": None,
                "volume": None,
                "wall_score": 0.42,
                "freshness_state": "confirmed",
            }
        ],
        schema_overrides={"oi_change": pl.Float64, "volume": pl.Float64},
    ).write_parquet(input_dir / WALLS_PARQUET_FILENAME)
    return input_dir


def _snapshot_payload() -> dict:
    return build_expected_range_snapshot(
        source_report_id="vol2vol_20260604",
        source_view="QUIKOPTIONS VOL2VOL",
        capture_timestamp=datetime(2026, 6, 4, 12, 0, tzinfo=UTC),
        product="Gold",
        option_product_code="OG|GC",
        futures_symbol="GC",
        expiration_code="OG1M6",
        expiry_date=date(2026, 6, 5),
        reference_futures_price=4549.2,
        report_level_iv=0.2508,
        vol_settle=0.2508,
        fractional_dte=3.47,
        cme_numeric_1sd=111.3,
        cme_numeric_2sd=222.6,
        cme_numeric_3sd=333.9,
        upper_1sd=4660.5,
        lower_1sd=4437.9,
        upper_2sd=4771.8,
        lower_2sd=4326.6,
        upper_3sd=4883.1,
        lower_3sd=4215.3,
    ).model_dump(mode="json")
