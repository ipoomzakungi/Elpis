import csv
import json
from pathlib import Path

import pytest

from src.free_derivatives.orchestration import assemble_placeholder_bootstrap_run
from src.free_derivatives.report_store import FreeDerivativesReportStore
from src.models.free_derivatives import (
    FreeDerivativesArtifactFormat,
    FreeDerivativesArtifactType,
    FreeDerivativesBootstrapRequest,
    FreeDerivativesRunStatus,
    FreeDerivativesSource,
    FreeDerivativesSourceStatus,
)


def test_free_derivatives_report_store_uses_ignored_generated_roots(tmp_path):
    store = FreeDerivativesReportStore(
        raw_dir=tmp_path / "raw",
        processed_dir=tmp_path / "processed",
        reports_dir=tmp_path / "reports",
    )

    assert store.raw_source_root(FreeDerivativesSource.CFTC_COT) == tmp_path / "raw" / "cftc"
    assert store.raw_source_root(FreeDerivativesSource.GVZ) == tmp_path / "raw" / "gvz"
    assert (
        store.raw_source_root(FreeDerivativesSource.DERIBIT_PUBLIC_OPTIONS)
        == tmp_path / "raw" / "deribit"
    )
    assert (
        store.processed_source_root(FreeDerivativesSource.CFTC_COT)
        == tmp_path / "processed" / "cftc"
    )
    assert store.report_root() == tmp_path / "reports" / "free_derivatives"


def test_free_derivatives_report_store_rejects_unsafe_ids_and_artifact_names(tmp_path):
    store = FreeDerivativesReportStore(reports_dir=tmp_path / "reports")

    for run_id in ("", "../outside", "nested/report", "bad run"):
        with pytest.raises(ValueError):
            store.run_dir(run_id)

    with pytest.raises(ValueError):
        store.artifact_path("free_derivatives_20260512", "../report.json")


def test_free_derivatives_report_store_builds_path_safe_artifact_metadata(tmp_path):
    store = FreeDerivativesReportStore(
        raw_dir=tmp_path / "raw",
        processed_dir=tmp_path / "processed",
        reports_dir=tmp_path / "reports",
    )
    raw_path = store.raw_source_root(FreeDerivativesSource.CFTC_COT) / "cot.csv"
    processed_path = (
        store.processed_source_root(FreeDerivativesSource.GVZ) / "gvz_daily.parquet"
    )
    report_path = store.artifact_path("free_derivatives_20260512", "report.json")

    for path in (raw_path, processed_path, report_path):
        path.parent.mkdir(parents=True, exist_ok=True)

    raw_artifact = store.artifact(
        artifact_type=FreeDerivativesArtifactType.RAW_CFTC,
        source=FreeDerivativesSource.CFTC_COT,
        path=raw_path,
        artifact_format=FreeDerivativesArtifactFormat.CSV,
        rows=3,
    )
    processed_artifact = store.artifact(
        artifact_type=FreeDerivativesArtifactType.PROCESSED_GVZ,
        source=FreeDerivativesSource.GVZ,
        path=processed_path,
        artifact_format=FreeDerivativesArtifactFormat.PARQUET,
        rows=5,
    )
    report_artifact = store.artifact(
        artifact_type=FreeDerivativesArtifactType.RUN_JSON,
        source=FreeDerivativesSource.CFTC_COT,
        path=report_path,
        artifact_format=FreeDerivativesArtifactFormat.JSON,
    )

    assert raw_artifact.path.endswith(str(Path("raw") / "cftc" / "cot.csv"))
    assert processed_artifact.rows == 5
    assert report_artifact.path.endswith(
        str(Path("free_derivatives") / "free_derivatives_20260512" / "report.json")
    )

    with pytest.raises(ValueError, match="generated roots"):
        store.artifact(
            artifact_type=FreeDerivativesArtifactType.RUN_JSON,
            source=FreeDerivativesSource.CFTC_COT,
            path=tmp_path / "outside.json",
            artifact_format=FreeDerivativesArtifactFormat.JSON,
        )


def test_free_derivatives_report_store_persists_and_reads_full_run_report(tmp_path):
    cftc_fixture = _write_cftc_csv(tmp_path / "cot.csv")
    store = FreeDerivativesReportStore(
        raw_dir=tmp_path / "raw",
        processed_dir=tmp_path / "processed",
        reports_dir=tmp_path / "reports",
    )
    request = FreeDerivativesBootstrapRequest(
        include_cftc=True,
        include_gvz=False,
        include_deribit=False,
        run_label="store_persist",
        cftc={"local_fixture_paths": [cftc_fixture]},
        research_only_acknowledged=True,
    )
    run = assemble_placeholder_bootstrap_run(request, store=store)

    persisted = store.persist_run(run)
    read_run = store.read_run(persisted.run_id)
    summaries = store.list_run_summaries()
    metadata = json.loads(
        store.artifact_path(persisted.run_id, "metadata.json").read_text(encoding="utf-8")
    )
    markdown = store.artifact_path(persisted.run_id, "report.md").read_text(
        encoding="utf-8"
    )

    assert persisted.status == FreeDerivativesRunStatus.COMPLETED
    assert read_run.run_id == persisted.run_id
    assert read_run.source_results[0].status == FreeDerivativesSourceStatus.COMPLETED
    assert summaries[0].run_id == persisted.run_id
    assert metadata["run_id"] == persisted.run_id
    assert metadata["sources"][0]["source"] == "cftc_cot"
    assert "Research-only public/local data expansion report" in markdown
    assert {"run_metadata", "run_json", "run_markdown"}.issubset(
        {artifact.artifact_type.value for artifact in persisted.artifacts}
    )
    assert store.artifact_path(persisted.run_id, "report.json").exists()


def _write_cftc_csv(path: Path) -> Path:
    rows = [
        {
            "report_category": "futures_only",
            "As_of_Date_In_Form_YYMMDD": "250107",
            "Market_and_Exchange_Names": "GOLD - COMMODITY EXCHANGE INC.",
            "Open_Interest_All": "1000",
            "Noncommercial_Long_All": "130",
            "Noncommercial_Short_All": "70",
            "Commercial_Long_All": "200",
            "Commercial_Short_All": "210",
        },
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return path
