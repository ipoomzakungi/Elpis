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
