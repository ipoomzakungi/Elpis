from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.models.quikstrike_matrix import (
    QuikStrikeMatrixArtifactFormat,
    QuikStrikeMatrixArtifactType,
    QuikStrikeMatrixExtractionRequest,
    QuikStrikeMatrixMetadata,
    QuikStrikeMatrixTableSnapshot,
    QuikStrikeMatrixViewType,
)
from src.quikstrike_matrix.conversion import convert_to_xau_vol_oi_rows
from src.quikstrike_matrix.extraction import build_extraction_from_request
from src.quikstrike_matrix.report_store import QuikStrikeMatrixReportStore


def test_report_store_roots_are_path_safe(tmp_path: Path):
    store = QuikStrikeMatrixReportStore(reports_dir=tmp_path / "data" / "reports")

    assert store.raw_root() == tmp_path / "data" / "raw" / "quikstrike_matrix"
    assert store.processed_root() == tmp_path / "data" / "processed" / "quikstrike_matrix"
    assert store.report_root() == tmp_path / "data" / "reports" / "quikstrike_matrix"

    with pytest.raises(ValueError):
        store.artifact_path("matrix_path_safe", "../outside.json")

    with pytest.raises(ValueError):
        store.report_dir("../outside")


def test_artifact_metadata_helper_uses_ignored_local_paths(tmp_path: Path):
    store = QuikStrikeMatrixReportStore(reports_dir=tmp_path / "data" / "reports")
    artifact_path = store.raw_root() / "matrix_path_safe_metadata.json"
    artifact = store.artifact(
        artifact_type=QuikStrikeMatrixArtifactType.RAW_METADATA,
        path=artifact_path,
        artifact_format=QuikStrikeMatrixArtifactFormat.JSON,
    )

    assert artifact.path == "data/raw/quikstrike_matrix/matrix_path_safe_metadata.json"


def test_report_store_persists_and_reads_report_rows_and_conversion(tmp_path: Path):
    store = QuikStrikeMatrixReportStore(reports_dir=tmp_path / "data" / "reports")
    extraction = build_extraction_from_request(
        _request(),
        extraction_id="matrix_store",
        capture_timestamp=datetime(2026, 5, 13, tzinfo=UTC),
    )
    conversion = convert_to_xau_vol_oi_rows(
        extraction_result=extraction.result,
        rows=extraction.rows,
        conversion_id="matrix_store_xau",
        created_at=datetime(2026, 5, 13, tzinfo=UTC),
    )

    report = store.persist_report(
        extraction_result=extraction.result,
        normalized_rows=extraction.rows,
        conversion_result=conversion.result,
        conversion_rows=conversion.rows,
    )

    assert report.row_count == len(extraction.rows)
    assert (store.report_dir("matrix_store") / "report.json").exists()
    assert (store.report_dir("matrix_store") / "report.md").exists()
    assert store.read_report("matrix_store").extraction_id == "matrix_store"
    assert len(store.read_normalized_rows("matrix_store")) == len(extraction.rows)
    assert len(store.read_conversion_rows("matrix_store")) == len(conversion.rows)
    assert store.list_reports().extractions[0].extraction_id == "matrix_store"


def test_report_store_does_not_persist_secret_like_content(tmp_path: Path):
    store = QuikStrikeMatrixReportStore(reports_dir=tmp_path / "data" / "reports")
    extraction = build_extraction_from_request(
        _request(),
        extraction_id="matrix_no_secret_store",
        capture_timestamp=datetime(2026, 5, 13, tzinfo=UTC),
    )
    conversion = convert_to_xau_vol_oi_rows(
        extraction_result=extraction.result,
        rows=extraction.rows,
        conversion_id="matrix_no_secret_store_xau",
        created_at=datetime(2026, 5, 13, tzinfo=UTC),
    )

    store.persist_report(
        extraction_result=extraction.result,
        normalized_rows=extraction.rows,
        conversion_result=conversion.result,
        conversion_rows=conversion.rows,
    )
    persisted = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (tmp_path / "data").rglob("*")
        if path.is_file()
    ).lower()

    assert "bearer" not in persisted
    assert "__viewstate" not in persisted
    assert "set-cookie:" not in persisted


def _request() -> QuikStrikeMatrixExtractionRequest:
    view = QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX
    return QuikStrikeMatrixExtractionRequest(
        requested_views=[view],
        metadata_by_view={view: _metadata(view)},
        tables_by_view={view: _snapshot(view)},
        research_only_acknowledged=True,
    )


def _metadata(view: QuikStrikeMatrixViewType) -> QuikStrikeMatrixMetadata:
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


def _snapshot(view_type: QuikStrikeMatrixViewType) -> QuikStrikeMatrixTableSnapshot:
    return QuikStrikeMatrixTableSnapshot(
        view_type=view_type,
        html_table=(
            "<table><thead><tr><th>Strike</th><th colspan='2'>G2RK6 GC 2 DTE 4722.6</th></tr>"
            "<tr><th></th><th>Call</th><th>Put</th></tr></thead>"
            "<tbody><tr><th>4700</th><td>120</td><td>95</td></tr></tbody></table>"
        ),
    )
