from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.models.xau_quikstrike_fusion import (
    XAU_FUSION_RESEARCH_ONLY_WARNING,
    XauFusionAgreementStatus,
    XauFusionArtifact,
    XauFusionArtifactFormat,
    XauFusionArtifactType,
    XauFusionBasisState,
    XauFusionContextStatus,
    XauFusionContextSummary,
    XauFusionCoverageSummary,
    XauFusionDownstreamResult,
    XauFusionMatchKey,
    XauFusionMatchStatus,
    XauFusionMissingContextItem,
    XauFusionReportStatus,
    XauFusionRow,
    XauFusionSourceType,
    XauFusionSourceValue,
    XauFusionVolOiInputRow,
    XauQuikStrikeFusionReport,
    XauQuikStrikeFusionRequest,
    XauQuikStrikeFusionSummary,
    XauQuikStrikeSourceRef,
    validate_xau_fusion_safe_id,
)


def _vol2vol_value() -> XauFusionSourceValue:
    return XauFusionSourceValue(
        source_type=XauFusionSourceType.VOL2VOL,
        source_report_id="vol2vol_report",
        source_row_id="vol2vol_row_1",
        value=120.0,
        value_type="open_interest",
        source_view="QUIKOPTIONS VOL2VOL",
        strike=4700.0,
        expiration_code="G2RK6",
        option_type="call",
        future_reference_price=4722.6,
        dte=2,
    )


def _matrix_value() -> XauFusionSourceValue:
    return XauFusionSourceValue(
        source_type=XauFusionSourceType.MATRIX,
        source_report_id="matrix_report",
        source_row_id="matrix_row_1",
        value=118.0,
        value_type="open_interest",
        source_view="OPEN INTEREST Matrix",
        strike=4700.0,
        expiration_code="G2RK6",
        option_type="call",
    )


def _match_key() -> XauFusionMatchKey:
    return XauFusionMatchKey(
        strike=4700.0,
        expiration_code="G2RK6",
        option_type="call",
        value_type="open_interest",
    )


def test_core_enums_are_research_fusion_terms():
    assert XauFusionSourceType.VOL2VOL == "vol2vol"
    assert XauFusionSourceType.MATRIX == "matrix"
    assert XauFusionSourceType.FUSED == "fused"
    assert XauFusionMatchStatus.MATCHED == "matched"
    assert XauFusionAgreementStatus.DISAGREEMENT == "disagreement"
    assert XauFusionContextStatus.UNAVAILABLE == "unavailable"
    assert XauFusionReportStatus.PARTIAL == "partial"


def test_source_ref_validates_safe_ids_and_external_sources():
    source = XauQuikStrikeSourceRef(
        source_type=XauFusionSourceType.VOL2VOL,
        report_id="vol2vol_report",
        status="available",
        product="Gold (OG|GC)",
        row_count=910,
        warnings=["local-only research artifact", "local-only research artifact"],
    )

    assert source.report_id == "vol2vol_report"
    assert source.warnings == ["local-only research artifact"]

    with pytest.raises(ValidationError, match="vol2vol or matrix"):
        XauQuikStrikeSourceRef(source_type=XauFusionSourceType.FUSED, report_id="fused")

    with pytest.raises(ValidationError):
        XauQuikStrikeSourceRef(source_type=XauFusionSourceType.MATRIX, report_id="../outside")


def test_request_requires_safe_source_ids_and_research_acknowledgement():
    request = XauQuikStrikeFusionRequest(
        vol2vol_report_id="vol2vol_report",
        matrix_report_id="matrix_report",
        xauusd_spot_reference=4715.25,
        gc_futures_reference=4722.5,
        research_only_acknowledged=True,
    )

    assert request.persist_report is True
    assert request.create_xau_vol_oi_report is False

    with pytest.raises(ValidationError, match="research_only_acknowledged"):
        XauQuikStrikeFusionRequest(
            vol2vol_report_id="vol2vol_report",
            matrix_report_id="matrix_report",
            research_only_acknowledged=False,
        )

    with pytest.raises(ValidationError):
        XauQuikStrikeFusionRequest(
            vol2vol_report_id="../outside",
            matrix_report_id="matrix_report",
            research_only_acknowledged=True,
        )


def test_models_reject_extra_secret_session_fields_and_values():
    with pytest.raises(ValidationError):
        XauQuikStrikeSourceRef(
            source_type=XauFusionSourceType.VOL2VOL,
            report_id="vol2vol_report",
            unexpected="value",
        )

    with pytest.raises(ValidationError, match="sensitive/session"):
        XauQuikStrikeSourceRef(
            source_type=XauFusionSourceType.VOL2VOL,
            report_id="vol2vol_report",
            headers={"Cookie": "not allowed"},
        )

    with pytest.raises(ValidationError, match="sensitive/session"):
        XauQuikStrikeSourceRef(
            source_type=XauFusionSourceType.VOL2VOL,
            report_id="vol2vol_report",
            warnings=["Bearer secret-token"],
        )


def test_match_key_requires_expiration_or_expiration_code():
    key = _match_key()

    assert key.option_type == "call"
    assert key.expiration_code == "G2RK6"
    assert key.expiration_key == "G2RK6"

    with pytest.raises(ValidationError, match="expiration"):
        XauFusionMatchKey(strike=4700.0, option_type="call", value_type="open_interest")


def test_coverage_summary_counts_are_non_negative():
    coverage = XauFusionCoverageSummary(
        matched_key_count=1,
        vol2vol_only_key_count=2,
        matrix_only_key_count=3,
        conflict_key_count=0,
        blocked_key_count=0,
        strike_count=31,
        expiration_count=10,
        option_type_count=2,
        value_type_count=3,
    )

    assert coverage.expiration_count == 10

    with pytest.raises(ValidationError):
        XauFusionCoverageSummary(
            matched_key_count=-1,
            vol2vol_only_key_count=0,
            matrix_only_key_count=0,
            conflict_key_count=0,
            blocked_key_count=0,
            strike_count=0,
            expiration_count=0,
            option_type_count=0,
            value_type_count=0,
        )


def test_fusion_row_preserves_both_source_values_and_agreement_notes():
    row = XauFusionRow(
        fusion_row_id="fusion_row_1",
        fusion_report_id="fusion_report",
        match_key=_match_key(),
        match_status=XauFusionMatchStatus.MATCHED,
        agreement_status=XauFusionAgreementStatus.DISAGREEMENT,
        vol2vol_value=_vol2vol_value(),
        matrix_value=_matrix_value(),
        source_agreement_notes=["vol2vol and matrix OI differ"],
    )

    assert row.source_type == XauFusionSourceType.FUSED
    assert row.vol2vol_value is not None
    assert row.matrix_value is not None
    assert row.source_agreement_notes == ["vol2vol and matrix OI differ"]

    with pytest.raises(ValidationError, match="at least one source"):
        XauFusionRow(
            fusion_row_id="fusion_row_2",
            fusion_report_id="fusion_report",
            match_key=_match_key(),
            match_status=XauFusionMatchStatus.MATCHED,
        )


def test_blocked_fusion_row_requires_visible_reason():
    with pytest.raises(ValidationError, match="blocked fusion rows"):
        XauFusionRow(
            fusion_row_id="fusion_row_blocked",
            fusion_report_id="fusion_report",
            match_key=_match_key(),
            match_status=XauFusionMatchStatus.BLOCKED,
            vol2vol_value=_vol2vol_value(),
        )

    row = XauFusionRow(
        fusion_row_id="fusion_row_blocked",
        fusion_report_id="fusion_report",
        match_key=_match_key(),
        match_status=XauFusionMatchStatus.BLOCKED,
        vol2vol_value=_vol2vol_value(),
        missing_context_notes=["matrix expiration mapping unavailable"],
    )
    assert row.match_status == XauFusionMatchStatus.BLOCKED


def test_missing_context_item_and_report_summary_validate_ids():
    item = XauFusionMissingContextItem(
        context_key="basis",
        status=XauFusionContextStatus.UNAVAILABLE,
        blocks_reaction_confidence=True,
        message="XAUUSD spot and GC futures references were not provided.",
    )
    summary = XauQuikStrikeFusionSummary(
        report_id="fusion_report",
        status=XauFusionReportStatus.PARTIAL,
        created_at=datetime(2026, 5, 13, tzinfo=UTC),
        vol2vol_report_id="vol2vol_report",
        matrix_report_id="matrix_report",
        fused_row_count=1,
        strike_count=1,
        expiration_count=1,
        warning_count=1,
    )

    assert item.context_key == "basis"
    assert summary.basis_status == XauFusionContextStatus.UNAVAILABLE

    with pytest.raises(ValidationError):
        XauQuikStrikeFusionSummary(
            report_id="bad/report",
            status=XauFusionReportStatus.PARTIAL,
            vol2vol_report_id="vol2vol_report",
            matrix_report_id="matrix_report",
            fused_row_count=0,
            strike_count=0,
            expiration_count=0,
        )


def test_basis_context_downstream_and_vol_oi_input_schemas_validate_core_rules():
    basis = XauFusionBasisState(
        status=XauFusionContextStatus.AVAILABLE,
        xauusd_spot_reference=4715.25,
        gc_futures_reference=4722.5,
        basis_points=7.25,
        calculation_note="Spot-equivalent levels are research annotations only.",
    )
    context = XauFusionContextSummary(
        basis_status=XauFusionContextStatus.AVAILABLE,
        iv_range_status=XauFusionContextStatus.PARTIAL,
        open_regime_status=XauFusionContextStatus.UNAVAILABLE,
        candle_acceptance_status=XauFusionContextStatus.UNAVAILABLE,
        realized_volatility_status=XauFusionContextStatus.UNAVAILABLE,
        source_agreement_status=XauFusionContextStatus.PARTIAL,
        missing_context=[],
    )
    downstream = XauFusionDownstreamResult(
        xau_vol_oi_report_id="xau_report",
        xau_report_status="not_requested",
        notes=["Downstream creation was not requested in this schema slice."],
    )
    row = XauFusionVolOiInputRow(
        expiration_code="G2RK6",
        strike=4700.0,
        option_type="call",
        open_interest=120.0,
        source_report_ids=["vol2vol_report", "matrix_report"],
        source_agreement_status=XauFusionAgreementStatus.AGREEMENT,
    )

    assert basis.basis_points == 7.25
    assert context.source_agreement_status == XauFusionContextStatus.PARTIAL
    assert downstream.xau_vol_oi_report_id == "xau_report"
    assert row.open_interest == 120.0

    with pytest.raises(ValidationError, match="basis_points"):
        XauFusionBasisState(
            status=XauFusionContextStatus.AVAILABLE,
            xauusd_spot_reference=4715.25,
            gc_futures_reference=4722.5,
        )

    with pytest.raises(ValidationError, match="at least one"):
        XauFusionVolOiInputRow(
            expiration_code="G2RK6",
            strike=4700.0,
            option_type="call",
            source_report_ids=["vol2vol_report"],
            source_agreement_status=XauFusionAgreementStatus.AGREEMENT,
        )


def test_report_defaults_to_research_only_limitation():
    report = XauQuikStrikeFusionReport(
        report_id="fusion_report",
        status=XauFusionReportStatus.PARTIAL,
        vol2vol_source=XauQuikStrikeSourceRef(
            source_type=XauFusionSourceType.VOL2VOL,
            report_id="vol2vol_report",
        ),
        matrix_source=XauQuikStrikeSourceRef(
            source_type=XauFusionSourceType.MATRIX,
            report_id="matrix_report",
        ),
        fused_row_count=0,
    )

    assert XAU_FUSION_RESEARCH_ONLY_WARNING in report.limitations


def test_artifact_paths_are_limited_to_ignored_fusion_report_scope():
    artifact = XauFusionArtifact(
        artifact_type=XauFusionArtifactType.REPORT_JSON,
        path="data/reports/xau_quikstrike_fusion/fusion_report/report.json",
        format=XauFusionArtifactFormat.JSON,
        rows=1,
    )

    assert artifact.path == "data/reports/xau_quikstrike_fusion/fusion_report/report.json"

    with pytest.raises(ValidationError, match="xau_quikstrike_fusion"):
        XauFusionArtifact(
            artifact_type=XauFusionArtifactType.REPORT_JSON,
            path="data/reports/quikstrike/fusion_report/report.json",
            format=XauFusionArtifactFormat.JSON,
        )


def test_validate_xau_fusion_safe_id_rejects_unsafe_values():
    assert validate_xau_fusion_safe_id("fusion_20260513") == "fusion_20260513"
    for value in ("", "../outside", "nested/id", "bad id"):
        with pytest.raises(ValueError):
            validate_xau_fusion_safe_id(value)
