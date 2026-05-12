from pathlib import Path

import pytest

from src.free_derivatives.report_store import FreeDerivativesReportStore
from src.models.free_derivatives import (
    FreeDerivativesArtifactFormat,
    FreeDerivativesArtifactType,
    FreeDerivativesSource,
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

