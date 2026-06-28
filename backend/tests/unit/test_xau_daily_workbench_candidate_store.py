from datetime import UTC, date, datetime
from pathlib import Path

from src.models.xau_daily_workbench import (
    XauDailyWorkbenchCandidateMetadata,
    XauDailyWorkbenchReadiness,
    research_only_no_signal_reasons,
)
from src.xau_daily_structural_map.report_store import XauDailyStructuralMapReportStore
from src.xau_daily_structural_map.sample_run import generate_xau_daily_structural_map_report
from src.xau_daily_workbench.candidate_store import XauDailyWorkbenchCandidateStore
from src.xau_daily_workbench.report_store import XauDailyWorkbenchReportStore
from src.xau_quikstrike_fusion.basis import calculate_basis_state
from src.xau_sd_oi_candidate.classifier import build_xau_sd_oi_candidate_set
from tests.unit.test_xau_daily_structural_map_store import (
    _native_expected_range_snapshot,
    _wall,
)


def test_candidate_store_persists_and_roundtrips_null_wall_fields(tmp_path: Path) -> None:
    map_store = XauDailyStructuralMapReportStore(reports_dir=tmp_path / "data" / "reports")
    workbench_store = XauDailyWorkbenchReportStore(reports_dir=tmp_path / "data" / "reports")
    daily_map = generate_xau_daily_structural_map_report(
        map_id="test_xau_candidate_store_map",
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
        output_dir=tmp_path / "data" / "reports",
    ).daily_map
    candidate_set = build_xau_sd_oi_candidate_set(
        daily_map,
        timestamp=datetime(2026, 6, 4, 12, 30, tzinfo=UTC),
        traded_price=4536.7,
        gc_price=4549.2,
        confirmation_state="neutral",
        iv_state="stable",
        flow_state="neutral",
    )
    metadata = XauDailyWorkbenchCandidateMetadata(
        candidate_set_id="test_candidate_set",
        map_id=daily_map.map_id,
        created_at=datetime(2026, 6, 4, 12, 30, tzinfo=UTC),
        candidate_count=candidate_set.candidate_count,
        readiness=XauDailyWorkbenchReadiness.COMPLETED,
        no_signal_reasons=research_only_no_signal_reasons(),
    )
    store = XauDailyWorkbenchCandidateStore(
        map_store=map_store,
        workbench_store=workbench_store,
    )

    paths = store.persist_candidate_set(daily_map.map_id, candidate_set, metadata)
    loaded = store.read_candidates(daily_map.map_id)

    assert paths["candidates_json"].endswith("candidates.json")
    assert loaded.candidate_set.candidates[0].nearest_wall_oi_change is None
    assert loaded.candidate_set.candidates[0].nearest_wall_volume is None
    assert loaded.candidate_set.signal_allowed is False
    assert loaded.candidate_metadata.signal_allowed is False
