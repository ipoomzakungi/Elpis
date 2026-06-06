import json
from datetime import UTC, date, datetime
from pathlib import Path

import polars as pl
import pytest

from src.models.xau import XauDailyStructuralMapReadiness, XauExpectedRangeSource
from src.xau_daily_structural_map.bundle_adapter import (
    LOCAL_BUNDLE_LIMITATION,
    NO_WALL_ROWS_LIMITATION,
    generate_xau_daily_structural_map_from_bundle,
)
from src.xau_daily_structural_map.report_store import XauDailyStructuralMapReportStore
from src.xau_quikstrike_fusion.daily_structural_map import (
    BASIS_UNAVAILABLE_NO_SIGNAL_REASON,
    EXPECTED_RANGE_UNAVAILABLE_NO_SIGNAL_REASON,
    MAP_ONLY_NO_SIGNAL_REASON,
    NO_WALLS_NO_SIGNAL_REASON,
)
from src.xau_quikstrike_fusion.expected_range import (
    RANGE_LABEL_LIMITATION,
    build_expected_range_snapshot,
)


def test_full_bundle_context_persists_ready_map_and_roundtrips(tmp_path: Path) -> None:
    report_path = _write_report_json(tmp_path, expected_range_snapshot=_snapshot_payload())
    walls_path = _write_walls_parquet(
        tmp_path,
        [
            _wall_row(
                wall_id="wall_4550_call",
                oi_change=25.0,
                volume=80.0,
            )
        ],
    )
    output_root = tmp_path / "data" / "reports"

    result = generate_xau_daily_structural_map_from_bundle(
        map_id="test_xau_bundle_full",
        session_date=date(2026, 6, 2),
        xau_vol_oi_report_path=report_path,
        walls_path=walls_path,
        fused_rows_path=None,
        traded_instrument="XAUUSD",
        traded_reference_price=4536.7,
        gc_reference_price=None,
        manual_basis=12.5,
        session_open_price=4538.0,
        session_open_source="manual_research_input",
        output_root=output_root,
    )

    store = XauDailyStructuralMapReportStore(reports_dir=output_root)
    loaded_map = store.read_map("test_xau_bundle_full")

    assert result.metadata.readiness == XauDailyStructuralMapReadiness.STRUCTURAL_MAP_READY
    assert result.metadata.wall_count == 1
    assert result.daily_map == loaded_map
    assert result.daily_map.signal_allowed is False
    assert result.daily_map.no_signal_reasons == [MAP_ONLY_NO_SIGNAL_REASON]
    assert result.daily_map.walls[0].spot_equivalent_level == pytest.approx(4537.5)
    assert result.daily_map.walls[0].oi_change == 25.0
    assert result.daily_map.walls[0].volume == 80.0
    assert LOCAL_BUNDLE_LIMITATION in result.daily_map.limitations
    assert (store.report_dir("test_xau_bundle_full") / "metadata.json").exists()
    assert (store.report_dir("test_xau_bundle_full") / "map.json").exists()
    assert (store.report_dir("test_xau_bundle_full") / "map.md").exists()
    assert (store.report_dir("test_xau_bundle_full") / "walls.json").exists()


def test_missing_basis_persists_partial_map_without_spot_levels(tmp_path: Path) -> None:
    report_path = _write_report_json(tmp_path, expected_range_snapshot=_snapshot_payload())
    walls_path = _write_walls_parquet(tmp_path, [_wall_row()])

    result = generate_xau_daily_structural_map_from_bundle(
        map_id="test_xau_bundle_missing_basis",
        session_date=date(2026, 6, 2),
        xau_vol_oi_report_path=report_path,
        walls_path=walls_path,
        traded_instrument="XAUUSD",
        traded_reference_price=4536.7,
        gc_reference_price=None,
        manual_basis=None,
        session_open_price=4538.0,
        session_open_source="manual_research_input",
        output_root=tmp_path / "data" / "reports",
    )

    assert result.daily_map.data_quality_state == (
        XauDailyStructuralMapReadiness.PARTIAL_MISSING_BASIS
    )
    assert result.daily_map.walls[0].spot_equivalent_level is None
    assert result.daily_map.walls[0].distance_to_traded_price is None
    assert BASIS_UNAVAILABLE_NO_SIGNAL_REASON in result.daily_map.no_signal_reasons


def test_missing_expected_range_persists_partial_map_with_null_sd_fields(
    tmp_path: Path,
) -> None:
    report_path = _write_report_json(tmp_path, expected_range_snapshot=None)
    walls_path = _write_walls_parquet(tmp_path, [_wall_row()])

    result = generate_xau_daily_structural_map_from_bundle(
        map_id="test_xau_bundle_missing_range",
        session_date=date(2026, 6, 2),
        xau_vol_oi_report_path=report_path,
        walls_path=walls_path,
        traded_instrument="XAUUSD",
        traded_reference_price=4536.7,
        gc_reference_price=4549.2,
        manual_basis=None,
        session_open_price=4538.0,
        session_open_source="manual_research_input",
        output_root=tmp_path / "data" / "reports",
    )

    assert result.daily_map.data_quality_state == (
        XauDailyStructuralMapReadiness.PARTIAL_MISSING_EXPECTED_RANGE
    )
    assert result.daily_map.expected_range_source is None
    assert result.daily_map.lower_1sd is None
    assert result.daily_map.upper_2sd is None
    assert result.daily_map.walls[0].inside_1sd is None
    assert EXPECTED_RANGE_UNAVAILABLE_NO_SIGNAL_REASON in result.daily_map.no_signal_reasons


def test_range_label_only_does_not_create_numeric_sd_fields(tmp_path: Path) -> None:
    report_path = _write_report_json(
        tmp_path,
        expected_range_snapshot=None,
        expected_range={
            "range_label": "3",
            "reference_price": 4549.2,
            "vol_settle": 0.3628798179067303,
            "fractional_dte": 3.47,
        },
    )
    walls_path = _write_walls_parquet(tmp_path, [_wall_row()])

    result = generate_xau_daily_structural_map_from_bundle(
        map_id="test_xau_bundle_range_label_only",
        session_date=date(2026, 6, 2),
        xau_vol_oi_report_path=report_path,
        walls_path=walls_path,
        traded_instrument="XAUUSD",
        traded_reference_price=4536.7,
        gc_reference_price=4549.2,
        manual_basis=None,
        session_open_price=4538.0,
        session_open_source="manual_research_input",
        output_root=tmp_path / "data" / "reports",
    )

    assert result.daily_map.expected_range_source == XauExpectedRangeSource.UNAVAILABLE
    assert result.daily_map.lower_1sd is None
    assert result.daily_map.upper_1sd is None
    assert EXPECTED_RANGE_UNAVAILABLE_NO_SIGNAL_REASON in result.daily_map.no_signal_reasons
    assert RANGE_LABEL_LIMITATION in result.daily_map.limitations


def test_null_oi_change_and_volume_remain_null_after_write_read(tmp_path: Path) -> None:
    report_path = _write_report_json(tmp_path, expected_range_snapshot=_snapshot_payload())
    walls_path = _write_walls_parquet(
        tmp_path,
        [
            _wall_row(
                wall_id="wall_4550_call",
                oi_change=None,
                volume=None,
            )
        ],
    )
    output_root = tmp_path / "data" / "reports"

    generate_xau_daily_structural_map_from_bundle(
        map_id="test_xau_bundle_null_wall_fields",
        session_date=date(2026, 6, 2),
        xau_vol_oi_report_path=report_path,
        walls_path=walls_path,
        traded_instrument="XAUUSD",
        traded_reference_price=4536.7,
        gc_reference_price=4549.2,
        manual_basis=None,
        session_open_price=4538.0,
        session_open_source="manual_research_input",
        output_root=output_root,
    )

    store = XauDailyStructuralMapReportStore(reports_dir=output_root)
    walls_payload = json.loads(
        (store.report_dir("test_xau_bundle_null_wall_fields") / "walls.json").read_text(
            encoding="utf-8"
        )
    )
    loaded_walls = store.read_walls("test_xau_bundle_null_wall_fields")

    assert walls_payload[0]["oi_change"] is None
    assert walls_payload[0]["volume"] is None
    assert loaded_walls[0].oi_change is None
    assert loaded_walls[0].volume is None


def test_missing_parquet_falls_back_to_embedded_report_walls(tmp_path: Path) -> None:
    report_path = _write_report_json(
        tmp_path,
        expected_range_snapshot=_snapshot_payload(),
        embedded_walls=[_wall_row(wall_id="embedded_4550_call")],
    )

    result = generate_xau_daily_structural_map_from_bundle(
        map_id="test_xau_bundle_embedded_walls",
        session_date=date(2026, 6, 2),
        xau_vol_oi_report_path=report_path,
        walls_path=tmp_path / "missing_walls.parquet",
        traded_instrument="XAUUSD",
        traded_reference_price=4536.7,
        gc_reference_price=4549.2,
        manual_basis=None,
        session_open_price=4538.0,
        session_open_source="manual_research_input",
        output_root=tmp_path / "data" / "reports",
    )

    assert result.daily_map.wall_count == 1
    assert result.daily_map.walls[0].wall_id == "embedded_4550_call"
    assert result.daily_map.data_quality_state == (
        XauDailyStructuralMapReadiness.STRUCTURAL_MAP_READY
    )


def test_no_wall_rows_still_persists_blocked_map_with_limitation(tmp_path: Path) -> None:
    report_path = _write_report_json(tmp_path, expected_range_snapshot=_snapshot_payload())

    result = generate_xau_daily_structural_map_from_bundle(
        map_id="test_xau_bundle_no_walls",
        session_date=date(2026, 6, 2),
        xau_vol_oi_report_path=report_path,
        walls_path=None,
        traded_instrument="XAUUSD",
        traded_reference_price=4536.7,
        gc_reference_price=4549.2,
        manual_basis=None,
        session_open_price=4538.0,
        session_open_source="manual_research_input",
        output_root=tmp_path / "data" / "reports",
    )

    assert result.daily_map.wall_count == 0
    assert result.daily_map.data_quality_state == (
        XauDailyStructuralMapReadiness.BLOCKED_INSUFFICIENT_CONTEXT
    )
    assert NO_WALLS_NO_SIGNAL_REASON in result.daily_map.no_signal_reasons
    assert NO_WALL_ROWS_LIMITATION in result.daily_map.limitations


def _write_report_json(
    tmp_path: Path,
    *,
    expected_range_snapshot: dict | None,
    expected_range: dict | None = None,
    embedded_walls: list[dict] | None = None,
) -> Path:
    report = {
        "report_id": "test_xau_vol_oi_20260602",
        "session_date": "2026-06-02",
        "limitations": ["Fixture local XAU Vol-OI report."],
        "warnings": [],
    }
    if expected_range_snapshot is not None:
        report["expected_range_snapshot"] = expected_range_snapshot
    if expected_range is not None:
        report["expected_range"] = expected_range
    if embedded_walls is not None:
        report["walls"] = embedded_walls
    payload = {
        "report": report,
        "walls": embedded_walls or [],
        "limitations": ["Fixture wrapper limitation."],
    }
    report_path = tmp_path / "04_xau_vol_oi_report_report.json"
    report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return report_path


def _write_walls_parquet(tmp_path: Path, rows: list[dict]) -> Path:
    walls_path = tmp_path / "04_xau_vol_oi_report_walls.parquet"
    pl.DataFrame(
        rows,
        schema_overrides={
            "oi_change": pl.Float64,
            "volume": pl.Float64,
        },
    ).write_parquet(walls_path)
    return walls_path


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


def _wall_row(
    *,
    wall_id: str = "wall_4550_call",
    oi_change: float | None = 25.0,
    volume: float | None = 80.0,
) -> dict:
    return {
        "wall_id": wall_id,
        "expiry": "2026-06-05",
        "expiration_code": "OG1M6",
        "strike": 4550.0,
        "option_type": "call",
        "open_interest": 1000.0,
        "oi_change": oi_change,
        "volume": volume,
        "wall_score": 0.42,
        "freshness_state": "confirmed",
    }
