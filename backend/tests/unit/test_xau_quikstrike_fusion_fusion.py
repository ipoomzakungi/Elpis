import pytest

from src.models.xau_quikstrike_fusion import (
    XauFusionAgreementStatus,
    XauFusionContextStatus,
    XauFusionMatchStatus,
    XauFusionReportStatus,
    XauFusionSourceType,
    XauFusionSourceValue,
    XauQuikStrikeFusionRequest,
)
from src.xau_quikstrike_fusion.basis import calculate_basis_state
from src.xau_quikstrike_fusion.fusion import (
    attach_context_to_rows,
    build_conservative_downstream_result,
    build_context_summary,
    build_fusion_rows,
    build_missing_context_items,
    build_xau_vol_oi_input_rows,
    detect_iv_range_status,
    determine_source_agreement_status,
    stable_fusion_row_id,
)
from src.xau_quikstrike_fusion.matching import build_match_key_from_source
from tests.helpers.test_xau_quikstrike_fusion_data import (
    sample_matrix_source_value,
    sample_vol2vol_source_value,
)


def test_stable_fusion_row_id_uses_report_id_and_match_key():
    row_id = stable_fusion_row_id(
        "fusion_report",
        build_match_key_from_source(sample_vol2vol_source_value()),
    )

    assert row_id == "fusion_report_G2RK6_4700_call_open_interest"


def test_build_fusion_rows_preserves_both_source_values_without_overwrite():
    rows, coverage, blocked_reasons = build_fusion_rows(
        fusion_report_id="fusion_report",
        vol2vol_values=[sample_vol2vol_source_value()],
        matrix_values=[sample_matrix_source_value()],
    )

    assert blocked_reasons == []
    assert coverage.matched_key_count == 1
    assert len(rows) == 1
    row = rows[0]
    assert row.source_type == XauFusionSourceType.FUSED
    assert row.match_status == XauFusionMatchStatus.MATCHED
    assert row.agreement_status == XauFusionAgreementStatus.AGREEMENT
    assert row.vol2vol_value is not None
    assert row.matrix_value is not None
    assert row.vol2vol_value.value == 120
    assert row.matrix_value.value == 120
    assert row.vol2vol_value.source_report_id == "vol2vol_report"
    assert row.matrix_value.source_report_id == "matrix_report"


def test_build_fusion_rows_marks_disagreement_without_overwriting_values():
    rows, coverage, blocked_reasons = build_fusion_rows(
        fusion_report_id="fusion_report",
        vol2vol_values=[sample_vol2vol_source_value()],
        matrix_values=[sample_matrix_source_value().model_copy(update={"value": 118.0})],
    )

    assert blocked_reasons == []
    assert coverage.matched_key_count == 1
    row = rows[0]
    assert row.agreement_status == XauFusionAgreementStatus.DISAGREEMENT
    assert row.vol2vol_value is not None
    assert row.matrix_value is not None
    assert row.vol2vol_value.value == 120
    assert row.matrix_value.value == 118
    assert any("differ" in note for note in row.source_agreement_notes)


def test_build_fusion_rows_keeps_source_only_provenance():
    rows, coverage, _ = build_fusion_rows(
        fusion_report_id="fusion_report",
        vol2vol_values=[sample_vol2vol_source_value()],
        matrix_values=[],
    )

    assert coverage.vol2vol_only_key_count == 1
    assert rows[0].source_type == XauFusionSourceType.VOL2VOL
    assert rows[0].matrix_value is None


def test_iv_range_status_detects_vol2vol_range_and_volatility_context():
    vol2vol_value = sample_vol2vol_source_value().model_copy(
        update={"vol_settle": 26.7, "range_label": "1SD"}
    )
    rows, _, _ = build_fusion_rows(
        fusion_report_id="fusion_report",
        vol2vol_values=[vol2vol_value],
        matrix_values=[sample_matrix_source_value()],
    )

    assert detect_iv_range_status(rows) == XauFusionContextStatus.AVAILABLE


def test_missing_context_checklist_covers_required_reaction_contexts():
    basis_state = calculate_basis_state()
    checklist = build_missing_context_items(
        basis_state=basis_state,
        iv_range_status=XauFusionContextStatus.UNAVAILABLE,
        open_regime_status=XauFusionContextStatus.UNAVAILABLE,
        candle_acceptance_status=XauFusionContextStatus.UNAVAILABLE,
        realized_volatility_status=XauFusionContextStatus.UNAVAILABLE,
        source_quality_status=XauFusionContextStatus.AVAILABLE,
        source_agreement_status=XauFusionContextStatus.AVAILABLE,
        source_refs=["vol2vol_report", "matrix_report"],
    )

    assert {item.context_key for item in checklist} == {
        "basis",
        "iv_range",
        "session_open",
        "candle_acceptance",
        "realized_volatility",
        "source_quality",
        "source_agreement",
    }
    assert all("buy" not in item.message.lower() for item in checklist)
    assert all("sell" not in item.message.lower() for item in checklist)
    assert all("execution" not in item.message.lower() for item in checklist)
    assert all("profit" not in item.message.lower() for item in checklist)
    assert next(item for item in checklist if item.context_key == "basis").status == (
        XauFusionContextStatus.UNAVAILABLE
    )


def test_no_fabricated_context_when_optional_inputs_are_absent():
    rows, _, _ = build_fusion_rows(
        fusion_report_id="fusion_report",
        vol2vol_values=[sample_vol2vol_source_value()],
        matrix_values=[sample_matrix_source_value()],
    )
    request = XauQuikStrikeFusionRequest(
        vol2vol_report_id="vol2vol_report",
        matrix_report_id="matrix_report",
        candle_context=[],
        persist_report=False,
        research_only_acknowledged=True,
    )
    basis_state = calculate_basis_state()
    context_summary = build_context_summary(
        rows=rows,
        basis_state=basis_state,
        request=request,
        source_quality_status=XauFusionContextStatus.AVAILABLE,
        source_agreement_status=determine_source_agreement_status(rows),
        source_refs=["vol2vol_report", "matrix_report"],
    )
    enriched_rows = attach_context_to_rows(
        rows,
        basis_state=basis_state,
        missing_context=context_summary.missing_context,
    )

    assert context_summary.basis_status == XauFusionContextStatus.UNAVAILABLE
    assert context_summary.iv_range_status == XauFusionContextStatus.UNAVAILABLE
    assert context_summary.open_regime_status == XauFusionContextStatus.UNAVAILABLE
    assert context_summary.candle_acceptance_status == XauFusionContextStatus.UNAVAILABLE
    assert context_summary.realized_volatility_status == XauFusionContextStatus.UNAVAILABLE
    assert enriched_rows[0].basis_points is None
    assert enriched_rows[0].spot_equivalent_level is None
    assert enriched_rows[0].missing_context_notes


def test_context_summary_uses_available_optional_inputs_without_fabricating_missing_ones():
    rows, _, _ = build_fusion_rows(
        fusion_report_id="fusion_report",
        vol2vol_values=[
            sample_vol2vol_source_value().model_copy(
                update={"vol_settle": 26.7, "range_label": "1SD"}
            )
        ],
        matrix_values=[sample_matrix_source_value()],
    )
    request = XauQuikStrikeFusionRequest(
        vol2vol_report_id="vol2vol_report",
        matrix_report_id="matrix_report",
        xauusd_spot_reference=4692.1,
        gc_futures_reference=4696.7,
        session_open_price=4690.0,
        realized_volatility=0.18,
        candle_context=[{"state": "synthetic_rejection"}],
        persist_report=False,
        research_only_acknowledged=True,
    )
    basis_state = calculate_basis_state(
        xauusd_spot_reference=request.xauusd_spot_reference,
        gc_futures_reference=request.gc_futures_reference,
    )

    context_summary = build_context_summary(
        rows=rows,
        basis_state=basis_state,
        request=request,
        source_quality_status=XauFusionContextStatus.AVAILABLE,
        source_agreement_status=determine_source_agreement_status(rows),
        source_refs=["vol2vol_report", "matrix_report"],
    )
    enriched_rows = attach_context_to_rows(
        rows,
        basis_state=basis_state,
        missing_context=context_summary.missing_context,
    )

    assert context_summary.basis_status == XauFusionContextStatus.AVAILABLE
    assert context_summary.iv_range_status == XauFusionContextStatus.AVAILABLE
    assert context_summary.open_regime_status == XauFusionContextStatus.AVAILABLE
    assert context_summary.candle_acceptance_status == XauFusionContextStatus.AVAILABLE
    assert context_summary.realized_volatility_status == XauFusionContextStatus.AVAILABLE
    assert enriched_rows[0].basis_points == pytest.approx(4.6)
    assert enriched_rows[0].spot_equivalent_level == pytest.approx(4695.4)


def test_build_xau_vol_oi_input_rows_maps_matrix_values_and_preserves_vol2vol_context():
    vol2vol_open_interest = sample_vol2vol_source_value().model_copy(
        update={
            "value": 118.0,
            "expiration": "2026-05-15",
            "vol_settle": 26.7,
            "range_label": "1SD",
        }
    )
    matrix_open_interest = sample_matrix_source_value().model_copy(
        update={"value": 120.0, "expiration": "2026-05-15"}
    )
    matrix_oi_change = _source_value(
        source_type=XauFusionSourceType.MATRIX,
        source_row_id="matrix_oi_change",
        value=5.0,
        value_type="oi_change",
        source_view="oi_change_matrix",
        expiration="2026-05-15",
    )
    matrix_volume = _source_value(
        source_type=XauFusionSourceType.MATRIX,
        source_row_id="matrix_volume",
        value=44.0,
        value_type="volume",
        source_view="volume_matrix",
        expiration="2026-05-15",
    )
    vol2vol_churn = _source_value(
        source_type=XauFusionSourceType.VOL2VOL,
        source_row_id="vol2vol_churn",
        value=0.4,
        value_type="churn",
        source_view="churn",
        expiration="2026-05-15",
        future_reference_price=4696.7,
    )
    rows, _, blocked_reasons = build_fusion_rows(
        fusion_report_id="fusion_report",
        vol2vol_values=[vol2vol_open_interest, vol2vol_churn],
        matrix_values=[matrix_open_interest, matrix_oi_change, matrix_volume],
    )

    enriched_rows = attach_context_to_rows(
        rows,
        basis_state=calculate_basis_state(
            xauusd_spot_reference=4692.1,
            gc_futures_reference=4696.7,
        ),
        missing_context=[],
    )
    conversion = build_xau_vol_oi_input_rows(
        enriched_rows,
        upstream_blocked_reasons=blocked_reasons,
    )

    assert conversion.status == XauFusionReportStatus.COMPLETED
    assert conversion.blocked_reasons == []
    assert len(conversion.rows) == 1
    row = conversion.rows[0]
    assert row.expiry == "2026-05-15"
    assert row.expiration_code == "G2RK6"
    assert row.strike == 4700
    assert row.spot_equivalent_strike == pytest.approx(4695.4)
    assert row.option_type == "call"
    assert row.open_interest == 120
    assert row.oi_change == 5
    assert row.volume == 44
    assert row.churn == 0.4
    assert row.implied_volatility == 26.7
    assert row.underlying_futures_price == 4696.7
    assert set(row.source_report_ids) == {"matrix_report", "vol2vol_report"}
    assert any("local research annotation" in limitation for limitation in row.limitations)


def test_build_xau_vol_oi_input_rows_reports_upstream_missing_key_blockers():
    missing_strike = sample_vol2vol_source_value().model_copy(update={"strike": None})
    missing_expiration = sample_matrix_source_value().model_copy(
        update={"expiration": None, "expiration_code": None}
    )
    missing_option = sample_matrix_source_value().model_copy(update={"option_type": None})

    rows, _, blocked_reasons = build_fusion_rows(
        fusion_report_id="fusion_report",
        vol2vol_values=[missing_strike],
        matrix_values=[missing_expiration, missing_option],
    )
    conversion = build_xau_vol_oi_input_rows(
        rows,
        upstream_blocked_reasons=blocked_reasons,
    )

    assert conversion.status == XauFusionReportStatus.BLOCKED
    assert conversion.rows == []
    reason_text = " ".join(conversion.blocked_reasons).lower()
    assert "missing strike" in reason_text
    assert "expiration" in reason_text
    assert "option_type" in reason_text


def test_build_xau_vol_oi_input_rows_blocks_unsupported_value_mapping():
    unsupported = _source_value(
        source_type=XauFusionSourceType.MATRIX,
        source_row_id="matrix_unknown",
        value=3.0,
        value_type="unknown_metric",
        source_view="unknown_metric",
    )
    rows, _, blocked_reasons = build_fusion_rows(
        fusion_report_id="fusion_report",
        vol2vol_values=[],
        matrix_values=[unsupported],
    )

    conversion = build_xau_vol_oi_input_rows(
        rows,
        upstream_blocked_reasons=blocked_reasons,
    )

    assert conversion.status == XauFusionReportStatus.BLOCKED
    assert conversion.rows == []
    assert any("value_type" in reason for reason in conversion.blocked_reasons)


def test_downstream_conservative_notes_avoid_forbidden_wording():
    result = build_conservative_downstream_result(
        build_missing_context_items(
            basis_state=calculate_basis_state(),
            iv_range_status=XauFusionContextStatus.UNAVAILABLE,
            open_regime_status=XauFusionContextStatus.UNAVAILABLE,
            candle_acceptance_status=XauFusionContextStatus.UNAVAILABLE,
            realized_volatility_status=XauFusionContextStatus.UNAVAILABLE,
            source_quality_status=XauFusionContextStatus.AVAILABLE,
            source_agreement_status=XauFusionContextStatus.AVAILABLE,
            source_refs=["vol2vol_report", "matrix_report"],
        )
    )

    assert result is not None
    notes = " ".join(result.notes).lower()
    for forbidden in ("buy", "sell", "execution", "profit", "profitable", "live-ready"):
        assert forbidden not in notes


def _source_value(
    *,
    source_type: XauFusionSourceType,
    source_row_id: str,
    value: float,
    value_type: str,
    source_view: str,
    expiration: str | None = None,
    expiration_code: str = "G2RK6",
    future_reference_price: float | None = None,
) -> XauFusionSourceValue:
    return XauFusionSourceValue(
        source_type=source_type,
        source_report_id=f"{source_type.value}_report",
        source_row_id=source_row_id,
        value=value,
        value_type=value_type,
        source_view=source_view,
        strike=4700.0,
        expiration=expiration,
        expiration_code=expiration_code,
        option_type="call",
        future_reference_price=future_reference_price,
    )
