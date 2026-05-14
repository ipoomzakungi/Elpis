from datetime import UTC, datetime
from pathlib import Path

import src.xau_quikstrike_fusion.orchestration as fusion_orchestration
from src.models.xau_quikstrike_fusion import (
    XauFusionContextStatus,
    XauFusionReportStatus,
    XauFusionSourceType,
    XauFusionSourceValue,
    XauQuikStrikeFusionRequest,
)
from src.xau_quikstrike_fusion.loaders import LoadedFusionSource
from src.xau_quikstrike_fusion.orchestration import create_xau_quikstrike_fusion_report
from src.xau_quikstrike_fusion.report_store import XauQuikStrikeFusionReportStore
from tests.helpers.test_xau_quikstrike_fusion_data import (
    make_matrix_store,
    make_vol2vol_store,
    persist_sample_matrix_report,
    persist_sample_vol2vol_report,
    sample_matrix_source_ref,
    sample_vol2vol_source_ref,
)


def test_synthetic_vol2vol_and_matrix_reports_fuse_and_persist(tmp_path: Path):
    vol2vol_store = make_vol2vol_store(tmp_path)
    matrix_store = make_matrix_store(tmp_path)
    fusion_store = XauQuikStrikeFusionReportStore(
        reports_dir=tmp_path / "data" / "reports"
    )
    persist_sample_vol2vol_report(vol2vol_store)
    persist_sample_matrix_report(matrix_store)

    report = create_xau_quikstrike_fusion_report(
        XauQuikStrikeFusionRequest(
            vol2vol_report_id="vol2vol_report",
            matrix_report_id="matrix_report",
            candle_context=[],
            persist_report=True,
            research_only_acknowledged=True,
        ),
        vol2vol_store=vol2vol_store,
        matrix_store=matrix_store,
        report_store=fusion_store,
        report_id="fusion_report",
        created_at=datetime(2026, 5, 13, tzinfo=UTC),
    )

    assert report.status == XauFusionReportStatus.PARTIAL
    assert report.fused_row_count == 4
    assert report.coverage is not None
    assert report.coverage.matched_key_count == 4
    assert report.context_summary is not None
    assert report.context_summary.source_agreement_status == XauFusionContextStatus.AVAILABLE
    assert report.context_summary.basis_status == XauFusionContextStatus.UNAVAILABLE
    assert report.context_summary.open_regime_status == XauFusionContextStatus.UNAVAILABLE
    assert report.context_summary.candle_acceptance_status == (
        XauFusionContextStatus.UNAVAILABLE
    )
    assert report.downstream_result is not None
    assert "NO_TRADE" in report.downstream_result.notes[0]
    assert all(row.vol2vol_value and row.matrix_value for row in report.fused_rows)
    assert all(row.spot_equivalent_level is None for row in report.fused_rows)
    assert all(row.missing_context_notes for row in report.fused_rows)
    assert (fusion_store.report_dir("fusion_report") / "metadata.json").exists()
    assert (fusion_store.report_dir("fusion_report") / "fused_rows.json").exists()
    assert (fusion_store.report_dir("fusion_report") / "report.json").exists()
    assert (fusion_store.report_dir("fusion_report") / "report.md").exists()
    report_md = (fusion_store.report_dir("fusion_report") / "report.md").read_text(
        encoding="utf-8"
    )
    assert "Missing Context Checklist" in report_md
    assert "session_open" in report_md
    assert all(
        artifact.path.startswith("data/reports/xau_quikstrike_fusion/")
        for artifact in report.artifacts
    )


def test_missing_source_reports_create_blocked_research_report(tmp_path: Path):
    report = create_xau_quikstrike_fusion_report(
        XauQuikStrikeFusionRequest(
            vol2vol_report_id="missing_vol2vol",
            matrix_report_id="missing_matrix",
            candle_context=[],
            persist_report=False,
            research_only_acknowledged=True,
        ),
        vol2vol_store=make_vol2vol_store(tmp_path),
        matrix_store=make_matrix_store(tmp_path),
        report_id="blocked_fusion",
        created_at=datetime(2026, 5, 13, tzinfo=UTC),
    )

    assert report.status == XauFusionReportStatus.BLOCKED
    assert report.fused_rows == []
    assert report.context_summary is not None
    assert report.context_summary.missing_context
    assert any(item.blocks_fusion for item in report.context_summary.missing_context)


def test_available_basis_adds_spot_equivalent_levels_without_open_or_candle_context(
    tmp_path: Path,
):
    vol2vol_store = make_vol2vol_store(tmp_path)
    matrix_store = make_matrix_store(tmp_path)
    persist_sample_vol2vol_report(vol2vol_store)
    persist_sample_matrix_report(matrix_store)

    report = create_xau_quikstrike_fusion_report(
        XauQuikStrikeFusionRequest(
            vol2vol_report_id="vol2vol_report",
            matrix_report_id="matrix_report",
            xauusd_spot_reference=4692.1,
            gc_futures_reference=4696.7,
            candle_context=[],
            persist_report=False,
            research_only_acknowledged=True,
        ),
        vol2vol_store=vol2vol_store,
        matrix_store=matrix_store,
        report_id="fusion_with_basis",
        created_at=datetime(2026, 5, 13, tzinfo=UTC),
    )

    assert report.basis_state is not None
    assert report.basis_state.status == XauFusionContextStatus.AVAILABLE
    assert all(row.basis_points is not None for row in report.fused_rows)
    assert all(row.spot_equivalent_level is not None for row in report.fused_rows)
    assert report.context_summary is not None
    assert report.context_summary.open_regime_status == XauFusionContextStatus.UNAVAILABLE
    assert report.context_summary.candle_acceptance_status == (
        XauFusionContextStatus.UNAVAILABLE
    )
    assert report.downstream_result is not None
    assert "session_open" in report.downstream_result.notes[0]
    assert "candle_acceptance" in report.downstream_result.notes[0]


def test_optional_downstream_xau_vol_oi_report_is_created_from_eligible_fused_input(
    tmp_path: Path,
    monkeypatch,
):
    _patch_calendar_source_loaders(monkeypatch)
    fusion_store = XauQuikStrikeFusionReportStore(
        reports_dir=tmp_path / "data" / "reports"
    )

    report = create_xau_quikstrike_fusion_report(
        XauQuikStrikeFusionRequest(
            vol2vol_report_id="vol2vol_report",
            matrix_report_id="matrix_report",
            xauusd_spot_reference=4692.1,
            gc_futures_reference=4696.7,
            create_xau_vol_oi_report=True,
            candle_context=[],
            persist_report=True,
            research_only_acknowledged=True,
        ),
        report_store=fusion_store,
        report_id="fusion_downstream_xau",
        created_at=datetime(2026, 5, 13, tzinfo=UTC),
    )

    assert report.xau_vol_oi_input_row_count >= 1
    assert report.downstream_result is not None
    assert report.downstream_result.xau_vol_oi_report_id is not None
    assert report.downstream_result.xau_report_status in {"partial", "completed"}
    assert report.downstream_result.xau_reaction_report_id is None
    assert (fusion_store.report_dir("fusion_downstream_xau") / "xau_vol_oi_input.csv").exists()
    assert (
        fusion_store.report_dir("fusion_downstream_xau") / "xau_vol_oi_report_input.csv"
    ).exists()


def test_optional_downstream_xau_reaction_report_keeps_conservative_no_trade_notes(
    tmp_path: Path,
    monkeypatch,
):
    _patch_calendar_source_loaders(monkeypatch)
    fusion_store = XauQuikStrikeFusionReportStore(
        reports_dir=tmp_path / "data" / "reports"
    )

    report = create_xau_quikstrike_fusion_report(
        XauQuikStrikeFusionRequest(
            vol2vol_report_id="vol2vol_report",
            matrix_report_id="matrix_report",
            xauusd_spot_reference=4692.1,
            gc_futures_reference=4696.7,
            create_xau_vol_oi_report=True,
            create_xau_reaction_report=True,
            candle_context=[],
            persist_report=True,
            research_only_acknowledged=True,
        ),
        report_store=fusion_store,
        report_id="fusion_downstream_reaction",
        created_at=datetime(2026, 5, 13, tzinfo=UTC),
    )

    assert report.downstream_result is not None
    assert report.downstream_result.xau_vol_oi_report_id is not None
    assert report.downstream_result.xau_reaction_report_id is not None
    assert report.downstream_result.reaction_row_count
    assert report.downstream_result.no_trade_count == report.downstream_result.reaction_row_count
    assert report.downstream_result.all_reactions_no_trade is True
    note_text = " ".join(report.downstream_result.notes)
    assert "NO_TRADE" in note_text
    assert "confirmation context is incomplete" in note_text


def _patch_calendar_source_loaders(monkeypatch) -> None:
    monkeypatch.setattr(
        fusion_orchestration,
        "load_vol2vol_source",
        lambda report_id, store=None: LoadedFusionSource(
            ref=sample_vol2vol_source_ref().model_copy(update={"row_count": 2}),
            values=[
                _source_value(
                    source_type=XauFusionSourceType.VOL2VOL,
                    source_row_id="vol_open_interest",
                    value=118.0,
                    value_type="open_interest",
                    source_view="open_interest",
                    future_reference_price=4696.7,
                    vol_settle=0.22,
                ),
                _source_value(
                    source_type=XauFusionSourceType.VOL2VOL,
                    source_row_id="vol_churn",
                    value=0.3,
                    value_type="churn",
                    source_view="churn",
                    future_reference_price=4696.7,
                ),
            ],
        ),
    )
    monkeypatch.setattr(
        fusion_orchestration,
        "load_matrix_source",
        lambda report_id, store=None: LoadedFusionSource(
            ref=sample_matrix_source_ref().model_copy(update={"row_count": 3}),
            values=[
                _source_value(
                    source_type=XauFusionSourceType.MATRIX,
                    source_row_id="matrix_open_interest",
                    value=120.0,
                    value_type="open_interest",
                    source_view="open_interest_matrix",
                ),
                _source_value(
                    source_type=XauFusionSourceType.MATRIX,
                    source_row_id="matrix_oi_change",
                    value=6.0,
                    value_type="oi_change",
                    source_view="oi_change_matrix",
                ),
                _source_value(
                    source_type=XauFusionSourceType.MATRIX,
                    source_row_id="matrix_volume",
                    value=40.0,
                    value_type="volume",
                    source_view="volume_matrix",
                ),
            ],
        ),
    )


def _source_value(
    *,
    source_type: XauFusionSourceType,
    source_row_id: str,
    value: float,
    value_type: str,
    source_view: str,
    future_reference_price: float | None = None,
    vol_settle: float | None = None,
) -> XauFusionSourceValue:
    return XauFusionSourceValue(
        source_type=source_type,
        source_report_id=f"{source_type.value}_report",
        source_row_id=source_row_id,
        value=value,
        value_type=value_type,
        source_view=source_view,
        strike=4700.0,
        expiration="2026-05-15",
        expiration_code="G2RK6",
        option_type="call",
        future_reference_price=future_reference_price,
        dte=2,
        vol_settle=vol_settle,
    )
