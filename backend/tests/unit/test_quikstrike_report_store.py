from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.models.quikstrike import (
    QuikStrikeArtifactFormat,
    QuikStrikeArtifactType,
    QuikStrikeExtractionRequest,
    QuikStrikeViewType,
)
from src.quikstrike.conversion import convert_to_xau_vol_oi_rows
from src.quikstrike.dom_metadata import parse_dom_metadata
from src.quikstrike.extraction import build_extraction_from_request
from src.quikstrike.highcharts_reader import parse_highcharts_chart
from src.quikstrike.report_store import QuikStrikeReportStore


def _chart_fixture() -> dict:
    return {
        "series": [
            {
                "name": "Put",
                "data": [
                    {
                        "x": 4700,
                        "y": 120,
                        "name": "4700",
                        "category": "4700",
                        "Tag": {"StrikeId": "strike-4700"},
                    }
                ],
            },
            {
                "name": "Call",
                "data": [
                    {
                        "x": 4700,
                        "y": 95,
                        "name": "4700",
                        "category": "4700",
                        "Tag": {"StrikeId": "strike-4700"},
                    }
                ],
            },
            {"name": "Vol Settle", "data": [{"x": 4700, "y": 26.7}]},
        ]
    }


def _extraction_bundle():
    view = QuikStrikeViewType.OPEN_INTEREST
    request = QuikStrikeExtractionRequest(
        requested_views=[view],
        dom_metadata_by_view={
            view: parse_dom_metadata(
                "Gold (OG|GC) OG3K6 (2.59 DTE) vs 4722.6 - Open Interest",
                selector_text="OG3K6 15 May 2026",
                selected_view_type=view,
            )
        },
        highcharts_by_view={view: parse_highcharts_chart(_chart_fixture(), view)},
        research_only_acknowledged=True,
    )
    return build_extraction_from_request(
        request,
        extraction_id="quikstrike_report",
        capture_timestamp=datetime(2026, 5, 13, tzinfo=UTC),
    )


def test_report_store_persists_and_reads_report_artifacts(tmp_path: Path):
    bundle = _extraction_bundle()
    conversion = convert_to_xau_vol_oi_rows(
        extraction_result=bundle.result,
        rows=bundle.rows,
        conversion_id="quikstrike_report_xau",
        created_at=datetime(2026, 5, 13, tzinfo=UTC),
    )
    store = QuikStrikeReportStore(reports_dir=tmp_path / "data" / "reports")

    report = store.persist_report(
        extraction_result=bundle.result,
        normalized_rows=bundle.rows,
        conversion_result=conversion.result,
        conversion_rows=conversion.rows,
    )

    report_dir = tmp_path / "data" / "reports" / "quikstrike" / "quikstrike_report"
    assert (report_dir / "metadata.json").exists()
    assert (report_dir / "normalized_rows.json").exists()
    assert (report_dir / "conversion_rows.json").exists()
    assert (report_dir / "artifact_metadata.json").exists()
    assert (report_dir / "report.json").exists()
    assert (report_dir / "report.md").exists()
    assert report.artifacts
    assert all(artifact.path.startswith("data/") for artifact in report.artifacts)

    saved_report = store.read_report("quikstrike_report")
    saved_rows = store.read_normalized_rows("quikstrike_report")
    saved_conversion_rows = store.read_conversion_rows("quikstrike_report")

    assert saved_report.extraction_id == "quikstrike_report"
    assert saved_rows == bundle.rows
    assert saved_conversion_rows == conversion.rows


def test_report_store_rejects_unsafe_ids_and_filenames(tmp_path: Path):
    store = QuikStrikeReportStore(reports_dir=tmp_path / "data" / "reports")

    with pytest.raises(ValueError):
        store.report_dir("../outside")

    with pytest.raises(ValueError):
        store.artifact_path("quikstrike_report", "../outside.json")


def test_report_store_artifact_paths_must_stay_under_report_root(tmp_path: Path):
    store = QuikStrikeReportStore(reports_dir=tmp_path / "data" / "reports")

    with pytest.raises(ValueError, match="report root"):
        store.artifact(
            artifact_type=QuikStrikeArtifactType.REPORT_JSON,
            path=tmp_path / "outside.json",
            artifact_format=QuikStrikeArtifactFormat.JSON,
        )
