from src.models.xau_quikstrike_fusion import (
    XauFusionAgreementStatus,
    XauFusionMatchStatus,
    XauFusionSourceType,
)
from src.xau_quikstrike_fusion.fusion import build_fusion_rows, stable_fusion_row_id
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
