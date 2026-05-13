from src.models.xau_quikstrike_fusion import (
    XauFusionAgreementStatus,
    XauFusionMatchStatus,
    XauFusionSourceType,
)
from src.xau_quikstrike_fusion.matching import (
    build_match_key,
    build_match_key_from_source,
    evaluate_source_agreement,
    match_source_rows,
)
from tests.helpers.test_xau_quikstrike_fusion_data import (
    sample_matrix_source_value,
    sample_vol2vol_source_value,
)


def test_match_key_normalizes_strike_expiration_code_option_and_value_type():
    key = build_match_key(
        strike=4700,
        expiration_code=" G2RK6 ",
        option_type="CALL",
        value_type="EOD_VOLUME",
    )

    assert key.strike == 4700
    assert key.expiration_key == "G2RK6"
    assert key.option_type == "call"
    assert key.value_type == "volume"


def test_match_key_can_be_built_from_source_value():
    key = build_match_key_from_source(sample_vol2vol_source_value())

    assert key.expiration_code == "G2RK6"
    assert key.option_type == "call"
    assert key.value_type == "open_interest"


def test_source_agreement_and_disagreement_are_visible():
    agreement_status, agreement_notes = evaluate_source_agreement(
        sample_vol2vol_source_value(),
        sample_matrix_source_value(),
    )
    disagreement_status, disagreement_notes = evaluate_source_agreement(
        sample_vol2vol_source_value(),
        sample_matrix_source_value().model_copy(update={"value": 119.0}),
    )

    assert agreement_status == XauFusionAgreementStatus.AGREEMENT
    assert "agree" in agreement_notes[0]
    assert disagreement_status == XauFusionAgreementStatus.DISAGREEMENT
    assert "differ" in disagreement_notes[0]


def test_match_source_rows_reports_matched_source_only_and_conflict_statuses():
    vol2vol_matched = sample_vol2vol_source_value()
    matrix_matched = sample_matrix_source_value()
    vol2vol_only = sample_vol2vol_source_value().model_copy(
        update={"source_row_id": "vol2vol_only", "strike": 4710.0}
    )
    matrix_only = sample_matrix_source_value().model_copy(
        update={"source_row_id": "matrix_only", "strike": 4720.0}
    )
    duplicate_matrix = sample_matrix_source_value().model_copy(
        update={"source_row_id": "matrix_duplicate"}
    )

    result = match_source_rows(
        [vol2vol_matched, vol2vol_only],
        [matrix_matched, matrix_only, duplicate_matrix],
    )

    statuses = {pair.match_status for pair in result.pairs}
    assert XauFusionMatchStatus.CONFLICT in statuses
    assert XauFusionMatchStatus.VOL2VOL_ONLY in statuses
    assert XauFusionMatchStatus.MATRIX_ONLY in statuses
    assert result.coverage.conflict_key_count == 1
    assert result.coverage.vol2vol_only_key_count == 1
    assert result.coverage.matrix_only_key_count == 1


def test_match_source_rows_counts_blocked_unmatchable_source_values():
    blocked = sample_vol2vol_source_value().model_copy(update={"strike": None})

    result = match_source_rows([blocked], [])

    assert result.coverage.blocked_key_count == 1
    assert result.blocked_reasons
    assert XauFusionSourceType.VOL2VOL.value in result.blocked_reasons[0]
