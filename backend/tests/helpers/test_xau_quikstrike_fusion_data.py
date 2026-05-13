from datetime import UTC, datetime

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
