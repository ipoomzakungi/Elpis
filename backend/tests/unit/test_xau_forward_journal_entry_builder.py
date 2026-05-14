import json

import pytest

from src.models.xau_forward_journal import XauForwardJournalCreateRequest
from src.xau_forward_journal.entry_builder import (
    XauForwardIncompatibleSourceReportError,
    XauForwardSourceReportNotFoundError,
    build_journal_entry,
    build_reaction_summaries,
    build_snapshot_context,
    build_source_refs,
    build_top_fusion_value_walls,
    build_top_oi_walls,
    load_source_reports,
    validate_source_compatibility,
)
from tests.helpers.test_xau_forward_journal_data import (
    FUSION_ID,
    MATRIX_ID,
    VOL2VOL_ID,
    XAU_REACTION_ID,
    XAU_VOL_OI_ID,
    synthetic_forward_journal_create_payload,
    write_synthetic_source_reports,
)


def _request(**updates) -> XauForwardJournalCreateRequest:
    payload = synthetic_forward_journal_create_payload()
    payload.update(updates)
    return XauForwardJournalCreateRequest.model_validate(payload)


def test_loads_source_report_refs_for_all_required_report_families(tmp_path):
    reports_dir = tmp_path / "data" / "reports"
    write_synthetic_source_reports(reports_dir)

    loaded = load_source_reports(_request(), reports_dir=reports_dir)
    refs = build_source_refs(loaded)

    assert [ref.report_id for ref in refs] == [
        VOL2VOL_ID,
        MATRIX_ID,
        FUSION_ID,
        XAU_VOL_OI_ID,
        XAU_REACTION_ID,
    ]
    assert [ref.source_type for ref in refs] == [
        "quikstrike_vol2vol",
        "quikstrike_matrix",
        "xau_quikstrike_fusion",
        "xau_vol_oi",
        "xau_reaction",
    ]
    assert refs[0].product == "Gold (OG|GC)"
    assert refs[2].expiration_code == "G2RK6"
    assert refs[3].row_count == 2
    assert refs[4].status == "partial"


def test_source_compatibility_rejects_missing_reports_and_non_gold_products(tmp_path):
    reports_dir = tmp_path / "data" / "reports"

    with pytest.raises(XauForwardSourceReportNotFoundError) as missing_error:
        load_source_reports(_request(), reports_dir=reports_dir)
    assert {detail["field"] for detail in missing_error.value.details} == {
        "vol2vol_report_id",
        "matrix_report_id",
        "fusion_report_id",
        "xau_vol_oi_report_id",
        "xau_reaction_report_id",
    }

    write_synthetic_source_reports(reports_dir, product="Copper (HX|HG)")
    loaded = load_source_reports(_request(), reports_dir=reports_dir)
    with pytest.raises(XauForwardIncompatibleSourceReportError) as product_error:
        validate_source_compatibility(loaded)
    assert product_error.value.code == "INCOMPATIBLE_SOURCE_REPORTS"
    assert any("product" in detail["field"] for detail in product_error.value.details)


def test_source_compatibility_rejects_broken_source_links(tmp_path):
    reports_dir = tmp_path / "data" / "reports"
    write_synthetic_source_reports(reports_dir, reaction_source_report_id="other_xau_report")

    loaded = load_source_reports(_request(), reports_dir=reports_dir)

    with pytest.raises(XauForwardIncompatibleSourceReportError) as exc:
        validate_source_compatibility(loaded)
    assert any("reaction report" in detail["message"] for detail in exc.value.details)


def test_partial_source_warnings_are_preserved_on_entry(tmp_path):
    reports_dir = tmp_path / "data" / "reports"
    write_synthetic_source_reports(
        reports_dir,
        fusion_status="partial",
        fusion_warning="Optional basis context is unavailable.",
    )

    entry = build_journal_entry(_request(), reports_dir=reports_dir)

    assert entry.status == "partial"
    assert "xau_quikstrike_fusion source status is partial." in entry.warnings
    assert "Optional basis context is unavailable." in entry.warnings


def test_snapshot_context_defaults_to_daily_window_and_computes_explicit_basis(tmp_path):
    reports_dir = tmp_path / "data" / "reports"
    write_synthetic_source_reports(reports_dir)
    loaded = load_source_reports(
        _request(
            spot_price_at_snapshot=4700.0,
            futures_price_at_snapshot=4707.2,
            session_open_price=4690.0,
            event_news_flag="none_known",
            capture_session=None,
        ),
        reports_dir=reports_dir,
    )

    snapshot = build_snapshot_context(loaded)

    assert snapshot.capture_window == "daily_snapshot"
    assert snapshot.capture_session is None
    assert snapshot.product == "Gold (OG|GC)"
    assert snapshot.expiration == "2026-06-25"
    assert snapshot.expiration_code == "G2RK6"
    assert snapshot.basis == pytest.approx(7.2)
    assert "basis" not in snapshot.missing_context
    assert "spot_price_at_snapshot" not in snapshot.missing_context


def test_wall_summaries_select_top_oi_change_and_volume_levels(tmp_path):
    reports_dir = tmp_path / "data" / "reports"
    write_synthetic_source_reports(reports_dir)
    loaded = load_source_reports(_request(), reports_dir=reports_dir)

    oi_walls = build_top_oi_walls(loaded)
    oi_change_walls = build_top_fusion_value_walls(loaded, "oi_change")
    volume_walls = build_top_fusion_value_walls(loaded, "volume")

    assert oi_walls[0].strike == 4700.0
    assert oi_walls[0].open_interest == 200.0
    assert oi_change_walls[0].strike == 4725.0
    assert oi_change_walls[0].oi_change == 42.0
    assert volume_walls[0].strike == 4675.0
    assert volume_walls[0].volume == 88.0


def test_reaction_summaries_preserve_no_trade_reasons_and_risk_counts(tmp_path):
    reports_dir = tmp_path / "data" / "reports"
    write_synthetic_source_reports(reports_dir)
    loaded = load_source_reports(_request(), reports_dir=reports_dir)

    reactions = build_reaction_summaries(loaded)

    assert reactions[0].reaction_label == "NO_TRADE"
    assert reactions[0].bounded_risk_annotation_count == 1
    assert "Basis mapping is unavailable." in reactions[0].no_trade_reasons
    assert reactions[0].limitations == ["XAU reaction local-only fixture."]


def test_reaction_summaries_ignore_non_list_reaction_payloads(tmp_path):
    reports_dir = tmp_path / "data" / "reports"
    write_synthetic_source_reports(reports_dir)
    reaction_report_path = reports_dir / "xau_reaction" / XAU_REACTION_ID / "metadata.json"
    reaction_report = json.loads(reaction_report_path.read_text(encoding="utf-8"))
    reaction_report["reactions"] = None
    reaction_report["risk_plans"] = {"reaction_id": "reaction_1"}
    reaction_report_path.write_text(
        json.dumps(reaction_report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    loaded = load_source_reports(_request(), reports_dir=reports_dir)

    reactions = build_reaction_summaries(loaded)
    entry = build_journal_entry(_request(), reports_dir=reports_dir)

    assert reactions == []
    assert entry.reaction_summaries == []


def test_build_journal_entry_includes_snapshot_key_and_pending_outcomes(tmp_path):
    reports_dir = tmp_path / "data" / "reports"
    write_synthetic_source_reports(reports_dir)

    entry = build_journal_entry(_request(), reports_dir=reports_dir)

    assert entry.journal_id.startswith("xau_forward_journal_")
    assert entry.snapshot_key in entry.journal_id
    assert entry.snapshot.capture_window == "daily_snapshot"
    assert len(entry.source_reports) == 5
    assert len(entry.outcomes) == 5
    assert {outcome.label for outcome in entry.outcomes} == {"pending"}
    assert any(item.context_key == "basis" for item in entry.missing_context)
