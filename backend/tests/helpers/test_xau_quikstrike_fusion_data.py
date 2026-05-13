from datetime import UTC, datetime
from pathlib import Path

from src.models.quikstrike import (
    QuikStrikeExtractionRequest,
    QuikStrikeViewType,
)
from src.models.quikstrike_matrix import (
    QuikStrikeMatrixExtractionRequest,
    QuikStrikeMatrixMetadata,
    QuikStrikeMatrixTableSnapshot,
    QuikStrikeMatrixViewType,
)
from src.models.xau_quikstrike_fusion import (
    XauFusionAgreementStatus,
    XauFusionContextStatus,
    XauFusionCoverageSummary,
    XauFusionMatchKey,
    XauFusionMatchStatus,
    XauFusionMissingContextItem,
    XauFusionReportStatus,
    XauFusionRow,
    XauFusionSourceType,
    XauFusionSourceValue,
    XauQuikStrikeFusionRequest,
    XauQuikStrikeFusionSummary,
    XauQuikStrikeSourceRef,
)
from src.quikstrike.conversion import convert_to_xau_vol_oi_rows
from src.quikstrike.dom_metadata import parse_dom_metadata
from src.quikstrike.extraction import build_extraction_from_request as build_vol2vol
from src.quikstrike.highcharts_reader import parse_highcharts_chart
from src.quikstrike.report_store import QuikStrikeReportStore
from src.quikstrike_matrix.conversion import (
    convert_to_xau_vol_oi_rows as convert_matrix_to_xau,
)
from src.quikstrike_matrix.extraction import build_extraction_from_request as build_matrix
from src.quikstrike_matrix.report_store import QuikStrikeMatrixReportStore


def sample_xau_fusion_request() -> XauQuikStrikeFusionRequest:
    return XauQuikStrikeFusionRequest(
        vol2vol_report_id="vol2vol_report",
        matrix_report_id="matrix_report",
        candle_context=[],
        research_only_acknowledged=True,
    )


def sample_vol2vol_source_ref() -> XauQuikStrikeSourceRef:
    return XauQuikStrikeSourceRef(
        source_type=XauFusionSourceType.VOL2VOL,
        report_id="vol2vol_report",
        status="completed",
        product="Gold",
        option_product_code="OG|GC",
        row_count=2,
        conversion_status="completed",
        limitations=["Synthetic Vol2Vol fixture for fusion tests."],
    )


def sample_matrix_source_ref() -> XauQuikStrikeSourceRef:
    return XauQuikStrikeSourceRef(
        source_type=XauFusionSourceType.MATRIX,
        report_id="matrix_report",
        status="completed",
        product="Gold",
        option_product_code="OG|GC",
        row_count=2,
        conversion_status="completed",
        limitations=["Synthetic Matrix fixture for fusion tests."],
    )


def sample_fusion_match_key() -> XauFusionMatchKey:
    return XauFusionMatchKey(
        strike=4700.0,
        expiration_code="G2RK6",
        option_type="call",
        value_type="open_interest",
    )


def sample_vol2vol_source_value() -> XauFusionSourceValue:
    return XauFusionSourceValue(
        source_type=XauFusionSourceType.VOL2VOL,
        source_report_id="vol2vol_report",
        source_row_id="vol2vol_row_1",
        value=120.0,
        value_type="open_interest",
        source_view="open_interest",
        strike=4700.0,
        expiration_code="G2RK6",
        option_type="call",
        future_reference_price=4696.7,
        dte=2,
    )


def sample_matrix_source_value() -> XauFusionSourceValue:
    return XauFusionSourceValue(
        source_type=XauFusionSourceType.MATRIX,
        source_report_id="matrix_report",
        source_row_id="matrix_row_1",
        value=120.0,
        value_type="open_interest",
        source_view="open_interest_matrix",
        strike=4700.0,
        expiration_code="G2RK6",
        option_type="call",
    )


def sample_fused_row() -> XauFusionRow:
    return XauFusionRow(
        fusion_row_id="fusion_row_1",
        fusion_report_id="fusion_report",
        match_key=sample_fusion_match_key(),
        match_status=XauFusionMatchStatus.MATCHED,
        agreement_status=XauFusionAgreementStatus.AGREEMENT,
        vol2vol_value=sample_vol2vol_source_value(),
        matrix_value=sample_matrix_source_value(),
        source_agreement_notes=["Synthetic source values agree."],
    )


def sample_coverage_summary() -> XauFusionCoverageSummary:
    return XauFusionCoverageSummary(
        matched_key_count=1,
        vol2vol_only_key_count=0,
        matrix_only_key_count=0,
        conflict_key_count=0,
        blocked_key_count=0,
        strike_count=1,
        expiration_count=1,
        option_type_count=1,
        value_type_count=1,
    )


def sample_missing_context_item() -> XauFusionMissingContextItem:
    return XauFusionMissingContextItem(
        context_key="basis",
        status=XauFusionContextStatus.UNAVAILABLE,
        message="Synthetic fixture omits spot/futures basis references.",
        blocks_reaction_confidence=True,
    )


def sample_fusion_summary() -> XauQuikStrikeFusionSummary:
    return XauQuikStrikeFusionSummary(
        report_id="fusion_report",
        status=XauFusionReportStatus.PARTIAL,
        created_at=datetime(2026, 5, 14, tzinfo=UTC),
        vol2vol_report_id="vol2vol_report",
        matrix_report_id="matrix_report",
        fused_row_count=1,
        strike_count=1,
        expiration_count=1,
        warning_count=1,
    )


def make_vol2vol_store(tmp_path: Path) -> QuikStrikeReportStore:
    return QuikStrikeReportStore(reports_dir=tmp_path / "data" / "reports")


def make_matrix_store(tmp_path: Path) -> QuikStrikeMatrixReportStore:
    return QuikStrikeMatrixReportStore(reports_dir=tmp_path / "data" / "reports")


def persist_sample_vol2vol_report(
    store: QuikStrikeReportStore,
    *,
    extraction_id: str = "vol2vol_report",
) -> None:
    views = [QuikStrikeViewType.OPEN_INTEREST, QuikStrikeViewType.OI_CHANGE]
    request = QuikStrikeExtractionRequest(
        requested_views=views,
        dom_metadata_by_view={
            view: parse_dom_metadata(
                f"Gold (OG|GC) G2RK6 (2 DTE) vs 4722.6 - {view.value}",
                selected_view_type=view,
            )
            for view in views
        },
        highcharts_by_view={
            view: parse_highcharts_chart(_vol2vol_chart_fixture(view), view)
            for view in views
        },
        research_only_acknowledged=True,
    )
    bundle = build_vol2vol(
        request,
        extraction_id=extraction_id,
        capture_timestamp=datetime(2026, 5, 13, tzinfo=UTC),
    )
    conversion = convert_to_xau_vol_oi_rows(
        extraction_result=bundle.result,
        rows=bundle.rows,
        conversion_id=f"{extraction_id}_xau",
        created_at=datetime(2026, 5, 13, tzinfo=UTC),
    )
    store.persist_report(
        extraction_result=bundle.result,
        normalized_rows=bundle.rows,
        conversion_result=conversion.result,
        conversion_rows=conversion.rows,
    )


def persist_sample_matrix_report(
    store: QuikStrikeMatrixReportStore,
    *,
    extraction_id: str = "matrix_report",
) -> None:
    request = _matrix_request()
    extraction = build_matrix(
        request,
        extraction_id=extraction_id,
        capture_timestamp=datetime(2026, 5, 13, tzinfo=UTC),
    )
    conversion = convert_matrix_to_xau(
        extraction_result=extraction.result,
        rows=extraction.rows,
        conversion_id=f"{extraction_id}_xau",
        created_at=datetime(2026, 5, 13, tzinfo=UTC),
    )
    store.persist_report(
        extraction_result=extraction.result,
        normalized_rows=extraction.rows,
        conversion_result=conversion.result,
        conversion_rows=conversion.rows,
    )


def _vol2vol_chart_fixture(view: QuikStrikeViewType) -> dict:
    values = {
        QuikStrikeViewType.OPEN_INTEREST: (120, 95),
        QuikStrikeViewType.OI_CHANGE: (5, -2),
    }
    put_value, call_value = values[view]
    return {
        "title": {"text": "G2RK6 Open Interest"},
        "series": [
            {
                "name": "Put",
                "data": [
                    {
                        "x": 4700,
                        "y": put_value,
                        "name": "4700",
                        "category": "4700",
                        "Tag": {"StrikeId": "internal-put"},
                    }
                ],
            },
            {
                "name": "Call",
                "data": [
                    {
                        "x": 4700,
                        "y": call_value,
                        "name": "4700",
                        "category": "4700",
                        "Tag": {"StrikeId": "internal-call"},
                    }
                ],
            },
        ],
    }


def _matrix_request() -> QuikStrikeMatrixExtractionRequest:
    snapshots = {
        QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX: _matrix_snapshot(
            QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX,
            value="120",
            extra_value="95",
        ),
        QuikStrikeMatrixViewType.OI_CHANGE_MATRIX: _matrix_snapshot(
            QuikStrikeMatrixViewType.OI_CHANGE_MATRIX,
            value="5",
            extra_value="-2",
        ),
    }
    return QuikStrikeMatrixExtractionRequest(
        requested_views=list(snapshots),
        metadata_by_view={view: _matrix_metadata(view) for view in snapshots},
        tables_by_view=snapshots,
        research_only_acknowledged=True,
    )


def _matrix_metadata(view: QuikStrikeMatrixViewType) -> QuikStrikeMatrixMetadata:
    return QuikStrikeMatrixMetadata(
        capture_timestamp=datetime(2026, 5, 13, tzinfo=UTC),
        product="Gold (OG|GC)",
        option_product_code="OG|GC",
        futures_symbol="GC",
        source_menu="OPEN INTEREST Matrix",
        selected_view_type=view,
        selected_view_label=view.value,
        raw_visible_text="Gold (OG|GC) OPEN INTEREST Matrix",
    )


def _matrix_snapshot(
    view_type: QuikStrikeMatrixViewType,
    *,
    value: str,
    extra_value: str,
) -> QuikStrikeMatrixTableSnapshot:
    return QuikStrikeMatrixTableSnapshot(
        view_type=view_type,
        html_table=(
            "<table><thead><tr><th>Strike</th><th colspan='2'>G2RK6 GC 2 DTE 4722.6</th></tr>"
            "<tr><th></th><th>Put</th><th>Call</th></tr></thead>"
            f"<tbody><tr><th>4700</th><td>{value}</td><td>{extra_value}</td></tr></tbody></table>"
        ),
    )
