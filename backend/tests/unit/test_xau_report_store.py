import pytest

from src.reports.collision_guard import ReportIdCollisionError, ReportSourceKindIsolationError
from src.xau.report_store import XauReportStore
from tests.helpers.test_xau_reaction_data import sample_feature006_xau_report


def test_xau_report_store_blocks_report_id_collisions_and_unisolated_smoke_ids(
    tmp_path,
):
    store = XauReportStore(reports_dir=tmp_path / "reports")
    report = sample_feature006_xau_report()

    saved = store.save_source_validation_report(report)

    assert saved.source_kind == "synthetic"
    assert '"source_kind": "synthetic"' in (
        store.xau_dir / report.report_id / "metadata.json"
    ).read_text(encoding="utf-8")

    with pytest.raises(ReportIdCollisionError):
        store.save_source_validation_report(report)

    with pytest.raises(ReportSourceKindIsolationError):
        store.save_source_validation_report(
            report.model_copy(update={"report_id": "xau_vol_oi_unisolated"}),
            source_kind="smoke",
        )


def test_xau_report_store_list_skips_legacy_unreadable_metadata(tmp_path):
    store = XauReportStore(reports_dir=tmp_path / "reports")
    legacy_dir = store.xau_dir / "xau_vol_oi_legacy"
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "metadata.json").write_text(
        """
        {
          "report_id": "xau_vol_oi_legacy",
          "status": "partial",
          "created_at": "2026-06-07T00:00:00Z",
          "source_row_count": 2,
          "wall_count": 2,
          "zone_count": 0,
          "walls": [],
          "zones": [],
          "artifacts": []
        }
        """,
        encoding="utf-8",
    )

    report = sample_feature006_xau_report()
    store.save_source_validation_report(report)

    listed = store.list_reports()

    assert [summary.report_id for summary in listed.reports] == [report.report_id]
