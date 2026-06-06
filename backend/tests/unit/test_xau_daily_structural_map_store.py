import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from src.models.xau import (
    XauDailyStructuralMap,
    XauDailyStructuralMapReadiness,
    XauFreshnessFactorStatus,
    XauOiWall,
    XauWallType,
)
from src.models.xau_daily_structural_map import XauDailyStructuralMapArtifactType
from src.xau_daily_structural_map.report_store import XauDailyStructuralMapReportStore
from src.xau_daily_structural_map.sample_run import (
    generate_xau_daily_structural_map_report,
)
from src.xau_quikstrike_fusion.basis import calculate_basis_state
from src.xau_quikstrike_fusion.daily_structural_map import (
    BASIS_UNAVAILABLE_NO_SIGNAL_REASON,
    EXPECTED_RANGE_UNAVAILABLE_NO_SIGNAL_REASON,
    MAP_ONLY_NO_SIGNAL_REASON,
    SESSION_OPEN_UNAVAILABLE_NO_SIGNAL_REASON,
    build_daily_structural_map,
)
from src.xau_quikstrike_fusion.expected_range import build_expected_range_snapshot


def test_full_context_persistence_writes_artifacts_and_roundtrips(tmp_path: Path) -> None:
    store = XauDailyStructuralMapReportStore(reports_dir=tmp_path / "data" / "reports")
    daily_map = _daily_map(
        map_id="test_xau_daily_map_full",
        wall_oi_change_by_id={"wall_4550_call": 25.0},
        wall_volume_by_id={"wall_4550_call": 80.0},
    )

    result = store.persist_map(
        daily_map,
        source_report_ids=["vol2vol_20260604", "xau_vol_oi_20260602"],
    )

    report_dir = store.report_dir(daily_map.map_id)
    assert (report_dir / "metadata.json").exists()
    assert (report_dir / "map.json").exists()
    assert (report_dir / "map.md").exists()
    assert (report_dir / "walls.json").exists()
    assert {artifact.artifact_type for artifact in result.artifacts} == {
        XauDailyStructuralMapArtifactType.METADATA,
        XauDailyStructuralMapArtifactType.MAP_JSON,
        XauDailyStructuralMapArtifactType.MAP_MARKDOWN,
        XauDailyStructuralMapArtifactType.WALLS_JSON,
    }

    metadata = store.read_metadata(daily_map.map_id)
    loaded_map = store.read_map(daily_map.map_id)

    assert metadata.map_id == daily_map.map_id
    assert metadata.readiness == XauDailyStructuralMapReadiness.STRUCTURAL_MAP_READY
    assert metadata.signal_allowed is False
    assert metadata.source_report_ids == ["vol2vol_20260604", "xau_vol_oi_20260602"]
    assert metadata.wall_count == 1
    assert loaded_map == daily_map
    assert XauDailyStructuralMap.model_validate_json(
        (report_dir / "map.json").read_text(encoding="utf-8")
    )
    assert "not a signal" in (report_dir / "map.md").read_text(encoding="utf-8")


def test_missing_basis_persistence_keeps_mapped_fields_null(tmp_path: Path) -> None:
    store = XauDailyStructuralMapReportStore(reports_dir=tmp_path / "data" / "reports")
    daily_map = _daily_map(
        map_id="test_xau_daily_map_missing_basis",
        basis_state=calculate_basis_state(gc_futures_reference=4549.2),
    )

    store.persist_map(daily_map)
    loaded_map = store.read_map(daily_map.map_id)

    assert loaded_map.data_quality_state == XauDailyStructuralMapReadiness.PARTIAL_MISSING_BASIS
    assert BASIS_UNAVAILABLE_NO_SIGNAL_REASON in loaded_map.no_signal_reasons
    assert loaded_map.walls[0].spot_equivalent_level is None
    assert loaded_map.walls[0].distance_to_traded_price is None


def test_missing_expected_range_persistence_keeps_sd_fields_null(tmp_path: Path) -> None:
    store = XauDailyStructuralMapReportStore(reports_dir=tmp_path / "data" / "reports")
    daily_map = _daily_map(
        map_id="test_xau_daily_map_missing_range",
        expected_range_snapshot=None,
    )

    store.persist_map(daily_map)
    loaded_map = store.read_map(daily_map.map_id)

    assert loaded_map.data_quality_state == (
        XauDailyStructuralMapReadiness.PARTIAL_MISSING_EXPECTED_RANGE
    )
    assert EXPECTED_RANGE_UNAVAILABLE_NO_SIGNAL_REASON in loaded_map.no_signal_reasons
    assert loaded_map.lower_1sd is None
    assert loaded_map.upper_2sd is None
    assert loaded_map.walls[0].inside_1sd is None


def test_missing_session_open_persistence_marks_partial(tmp_path: Path) -> None:
    store = XauDailyStructuralMapReportStore(reports_dir=tmp_path / "data" / "reports")
    daily_map = _daily_map(
        map_id="test_xau_daily_map_missing_open",
        session_open_price=None,
    )

    store.persist_map(daily_map)
    loaded_map = store.read_map(daily_map.map_id)

    assert loaded_map.data_quality_state == (
        XauDailyStructuralMapReadiness.PARTIAL_MISSING_SESSION_OPEN
    )
    assert SESSION_OPEN_UNAVAILABLE_NO_SIGNAL_REASON in loaded_map.no_signal_reasons
    assert loaded_map.session_open_price is None
    assert loaded_map.open_distance_points is None
    assert loaded_map.walls[0].distance_to_session_open is None


def test_null_oi_change_and_volume_remain_null_in_walls_artifact(tmp_path: Path) -> None:
    store = XauDailyStructuralMapReportStore(reports_dir=tmp_path / "data" / "reports")
    daily_map = _daily_map(map_id="test_xau_daily_map_null_walls")

    store.persist_map(daily_map)
    walls_payload = json.loads(
        (store.report_dir(daily_map.map_id) / "walls.json").read_text(encoding="utf-8")
    )

    assert walls_payload[0]["oi_change"] is None
    assert walls_payload[0]["volume"] is None
    assert walls_payload[0]["oi_change"] != 0
    assert walls_payload[0]["volume"] != 0


def test_sample_run_helper_builds_and_persists_report(tmp_path: Path) -> None:
    result = generate_xau_daily_structural_map_report(
        map_id="test_xau_daily_map_sample_run",
        session_date=date(2026, 6, 2),
        created_at=datetime(2026, 6, 4, 12, 0, tzinfo=UTC),
        source_product="Gold",
        traded_instrument="XAUUSD",
        traded_reference_price=4536.7,
        expected_range_snapshot=_native_expected_range_snapshot(),
        basis_state=calculate_basis_state(
            xauusd_spot_reference=4536.7,
            gc_futures_reference=4549.2,
        ),
        walls=[_wall()],
        session_open_price=4538.0,
        session_open_source="manual_research_input",
        source_report_ids=["vol2vol_20260604"],
        output_dir=tmp_path / "data" / "reports",
    )

    artifact_paths = [artifact.path for artifact in result.artifacts]

    assert result.metadata.map_id == "test_xau_daily_map_sample_run"
    assert result.metadata.readiness == XauDailyStructuralMapReadiness.STRUCTURAL_MAP_READY
    assert result.metadata.wall_count == 1
    assert result.daily_map.signal_allowed is False
    assert MAP_ONLY_NO_SIGNAL_REASON in result.daily_map.no_signal_reasons
    assert all(
        path.startswith("data/reports/xau_daily_structural_map/")
        for path in artifact_paths
    )


def test_report_store_rejects_unsafe_paths(tmp_path: Path) -> None:
    store = XauDailyStructuralMapReportStore(reports_dir=tmp_path / "data" / "reports")

    with pytest.raises(ValueError):
        store.report_dir("../outside")

    with pytest.raises(ValueError):
        store.artifact_path("test_xau_daily_map_safe", "nested/map.json")


def _daily_map(
    *,
    map_id: str,
    expected_range_snapshot=None,
    basis_state=None,
    session_open_price: float | None = 4538.0,
    wall_oi_change_by_id=None,
    wall_volume_by_id=None,
) -> XauDailyStructuralMap:
    if expected_range_snapshot is None and map_id != "test_xau_daily_map_missing_range":
        expected_range_snapshot = _native_expected_range_snapshot()
    if basis_state is None:
        basis_state = calculate_basis_state(
            xauusd_spot_reference=4536.7,
            gc_futures_reference=4549.2,
        )
    return build_daily_structural_map(
        map_id=map_id,
        session_date=date(2026, 6, 2),
        created_at=datetime(2026, 6, 4, 12, 0, tzinfo=UTC),
        source_product="Gold",
        traded_instrument="XAUUSD",
        traded_reference_price=4536.7,
        expected_range_snapshot=expected_range_snapshot,
        basis_state=basis_state,
        walls=[_wall()],
        session_open_price=session_open_price,
        session_open_source=(
            "manual_research_input" if session_open_price is not None else None
        ),
        wall_oi_change_by_id=wall_oi_change_by_id,
        wall_volume_by_id=wall_volume_by_id,
    )


def _native_expected_range_snapshot():
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
    )


def _wall() -> XauOiWall:
    return XauOiWall(
        wall_id="wall_4550_call",
        expiry=date(2026, 6, 5),
        strike=4550.0,
        option_type=XauWallType.CALL,
        open_interest=1000.0,
        total_expiry_open_interest=5000.0,
        oi_share=0.2,
        expiry_weight=1.0,
        freshness_factor=1.0,
        wall_score=0.42,
        freshness_status=XauFreshnessFactorStatus.CONFIRMED,
    )
