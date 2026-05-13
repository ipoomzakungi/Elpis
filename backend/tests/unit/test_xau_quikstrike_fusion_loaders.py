from pathlib import Path

from src.models.xau_quikstrike_fusion import XauFusionContextStatus
from src.xau_quikstrike_fusion.loaders import (
    load_matrix_source,
    load_vol2vol_source,
    validate_source_compatibility,
)
from tests.helpers.test_xau_quikstrike_fusion_data import (
    make_matrix_store,
    make_vol2vol_store,
    persist_sample_matrix_report,
    persist_sample_vol2vol_report,
    sample_matrix_source_ref,
    sample_vol2vol_source_ref,
)


def test_loaders_read_saved_vol2vol_and_matrix_source_reports(tmp_path: Path):
    vol2vol_store = make_vol2vol_store(tmp_path)
    matrix_store = make_matrix_store(tmp_path)
    persist_sample_vol2vol_report(vol2vol_store)
    persist_sample_matrix_report(matrix_store)

    vol2vol_source = load_vol2vol_source("vol2vol_report", store=vol2vol_store)
    matrix_source = load_matrix_source("matrix_report", store=matrix_store)

    assert vol2vol_source.ref.product == "Gold"
    assert vol2vol_source.ref.option_product_code == "OG|GC"
    assert vol2vol_source.ref.row_count == 4
    assert {value.value_type for value in vol2vol_source.values} == {
        "open_interest",
        "oi_change",
    }
    assert matrix_source.ref.product == "Gold (OG|GC)"
    assert matrix_source.ref.option_product_code == "OG|GC"
    assert matrix_source.ref.row_count == 4
    assert {value.value_type for value in matrix_source.values} == {
        "open_interest",
        "oi_change",
    }


def test_source_compatibility_accepts_gold_og_gc_reports():
    issues = validate_source_compatibility(
        sample_vol2vol_source_ref(),
        sample_matrix_source_ref(),
    )

    assert issues == []


def test_source_compatibility_blocks_incompatible_product_and_missing_rows():
    bad_matrix = sample_matrix_source_ref().model_copy(
        update={
            "product": "Corn (OZC|ZC)",
            "option_product_code": "OZC|ZC",
            "row_count": 0,
        }
    )

    issues = validate_source_compatibility(sample_vol2vol_source_ref(), bad_matrix)

    assert {issue.context_key for issue in issues} == {
        "matrix_rows",
        "matrix_product",
    }
    assert all(issue.status == XauFusionContextStatus.BLOCKED for issue in issues)
    assert all(issue.blocks_fusion for issue in issues)
