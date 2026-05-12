import csv
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

from src.config import get_settings
from src.models.free_derivatives import (
    CftcCotGoldRecord,
    CftcGoldPositioningSummary,
    FreeDerivativesArtifact,
    FreeDerivativesArtifactFormat,
    FreeDerivativesArtifactType,
    FreeDerivativesSource,
    GvzDailyCloseRecord,
    GvzGapSummary,
    validate_filesystem_safe_id,
)

SOURCE_DIRECTORY_NAMES = {
    FreeDerivativesSource.CFTC_COT: "cftc",
    FreeDerivativesSource.GVZ: "gvz",
    FreeDerivativesSource.DERIBIT_PUBLIC_OPTIONS: "deribit",
}


class FreeDerivativesReportStore:
    """Path-safe local storage surface for free derivatives research artifacts."""

    def __init__(
        self,
        raw_dir: Path | None = None,
        processed_dir: Path | None = None,
        reports_dir: Path | None = None,
    ) -> None:
        settings = get_settings()
        self.raw_dir = raw_dir or settings.data_raw_path
        self.processed_dir = processed_dir or settings.data_processed_path
        self.reports_dir = reports_dir or settings.data_reports_path
        self.repo_root = Path(__file__).resolve().parents[3]
        self.free_derivatives_reports_dir = self.reports_dir / "free_derivatives"

    def raw_source_root(self, source: FreeDerivativesSource) -> Path:
        return self.raw_dir / SOURCE_DIRECTORY_NAMES[source]

    def processed_source_root(self, source: FreeDerivativesSource) -> Path:
        return self.processed_dir / SOURCE_DIRECTORY_NAMES[source]

    def report_root(self) -> Path:
        return self.free_derivatives_reports_dir

    def ensure_roots(self) -> None:
        for source in FreeDerivativesSource:
            self.raw_source_root(source).mkdir(parents=True, exist_ok=True)
            self.processed_source_root(source).mkdir(parents=True, exist_ok=True)
        self.free_derivatives_reports_dir.mkdir(parents=True, exist_ok=True)

    def run_dir(self, run_id: str) -> Path:
        safe_run_id = validate_filesystem_safe_id(run_id, label="run_id")
        return self.free_derivatives_reports_dir / safe_run_id

    def ensure_run_dir(self, run_id: str) -> Path:
        path = self.run_dir(run_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def artifact_path(self, run_id: str, filename: str) -> Path:
        if Path(filename).name != filename:
            raise ValueError("artifact filename must not contain path separators")
        return self.run_dir(run_id) / filename

    def write_cftc_raw_rows(
        self,
        run_id: str,
        rows: list[dict[str, str]],
    ) -> FreeDerivativesArtifact:
        self.raw_source_root(FreeDerivativesSource.CFTC_COT).mkdir(
            parents=True,
            exist_ok=True,
        )
        safe_run_id = validate_filesystem_safe_id(run_id, label="run_id")
        path = self.raw_source_root(FreeDerivativesSource.CFTC_COT) / (
            f"{safe_run_id}_raw_rows.csv"
        )
        self._write_csv(path, rows)
        return self.artifact(
            artifact_type=FreeDerivativesArtifactType.RAW_CFTC,
            source=FreeDerivativesSource.CFTC_COT,
            path=path,
            artifact_format=FreeDerivativesArtifactFormat.CSV,
            rows=len(rows),
        )

    def write_cftc_processed_records(
        self,
        run_id: str,
        records: list[CftcCotGoldRecord],
    ) -> FreeDerivativesArtifact:
        self.processed_source_root(FreeDerivativesSource.CFTC_COT).mkdir(
            parents=True,
            exist_ok=True,
        )
        safe_run_id = validate_filesystem_safe_id(run_id, label="run_id")
        path = self.processed_source_root(FreeDerivativesSource.CFTC_COT) / (
            f"{safe_run_id}_gold_positioning.parquet"
        )
        self._write_parquet(path, [record.model_dump(mode="json") for record in records])
        return self.artifact(
            artifact_type=FreeDerivativesArtifactType.PROCESSED_CFTC,
            source=FreeDerivativesSource.CFTC_COT,
            path=path,
            artifact_format=FreeDerivativesArtifactFormat.PARQUET,
            rows=len(records),
        )

    def write_cftc_positioning_summary(
        self,
        run_id: str,
        summaries: list[CftcGoldPositioningSummary],
    ) -> FreeDerivativesArtifact:
        self.processed_source_root(FreeDerivativesSource.CFTC_COT).mkdir(
            parents=True,
            exist_ok=True,
        )
        safe_run_id = validate_filesystem_safe_id(run_id, label="run_id")
        path = self.processed_source_root(FreeDerivativesSource.CFTC_COT) / (
            f"{safe_run_id}_gold_positioning_summary.parquet"
        )
        self._write_parquet(path, [summary.model_dump(mode="json") for summary in summaries])
        return self.artifact(
            artifact_type=FreeDerivativesArtifactType.PROCESSED_CFTC,
            source=FreeDerivativesSource.CFTC_COT,
            path=path,
            artifact_format=FreeDerivativesArtifactFormat.PARQUET,
            rows=len(summaries),
        )

    def write_gvz_raw_rows(
        self,
        run_id: str,
        rows: list[dict[str, str]],
    ) -> FreeDerivativesArtifact:
        self.raw_source_root(FreeDerivativesSource.GVZ).mkdir(
            parents=True,
            exist_ok=True,
        )
        safe_run_id = validate_filesystem_safe_id(run_id, label="run_id")
        path = self.raw_source_root(FreeDerivativesSource.GVZ) / (
            f"{safe_run_id}_raw_rows.csv"
        )
        self._write_csv(path, rows)
        return self.artifact(
            artifact_type=FreeDerivativesArtifactType.RAW_GVZ,
            source=FreeDerivativesSource.GVZ,
            path=path,
            artifact_format=FreeDerivativesArtifactFormat.CSV,
            rows=len(rows),
        )

    def write_gvz_daily_close(
        self,
        run_id: str,
        records: list[GvzDailyCloseRecord],
    ) -> FreeDerivativesArtifact:
        self.processed_source_root(FreeDerivativesSource.GVZ).mkdir(
            parents=True,
            exist_ok=True,
        )
        safe_run_id = validate_filesystem_safe_id(run_id, label="run_id")
        path = self.processed_source_root(FreeDerivativesSource.GVZ) / (
            f"{safe_run_id}_gvz_daily_close.parquet"
        )
        self._write_parquet(path, [record.model_dump(mode="json") for record in records])
        return self.artifact(
            artifact_type=FreeDerivativesArtifactType.PROCESSED_GVZ,
            source=FreeDerivativesSource.GVZ,
            path=path,
            artifact_format=FreeDerivativesArtifactFormat.PARQUET,
            rows=len(records),
        )

    def write_gvz_gap_summary(
        self,
        run_id: str,
        summary: GvzGapSummary,
    ) -> FreeDerivativesArtifact:
        self.processed_source_root(FreeDerivativesSource.GVZ).mkdir(
            parents=True,
            exist_ok=True,
        )
        safe_run_id = validate_filesystem_safe_id(run_id, label="run_id")
        path = self.processed_source_root(FreeDerivativesSource.GVZ) / (
            f"{safe_run_id}_gvz_gap_summary.parquet"
        )
        self._write_parquet(path, [summary.model_dump(mode="json")])
        return self.artifact(
            artifact_type=FreeDerivativesArtifactType.PROCESSED_GVZ,
            source=FreeDerivativesSource.GVZ,
            path=path,
            artifact_format=FreeDerivativesArtifactFormat.PARQUET,
            rows=1,
        )

    def artifact(
        self,
        *,
        artifact_type: FreeDerivativesArtifactType,
        source: FreeDerivativesSource,
        path: Path,
        artifact_format: FreeDerivativesArtifactFormat,
        rows: int | None = None,
        limitations: list[str] | None = None,
    ) -> FreeDerivativesArtifact:
        self._validate_artifact_scope(path)
        try:
            artifact_path = str(path.relative_to(self.repo_root))
        except ValueError:
            artifact_path = str(path)
        return FreeDerivativesArtifact(
            artifact_type=artifact_type,
            source=source,
            path=artifact_path,
            format=artifact_format,
            rows=rows,
            created_at=datetime.now(UTC),
            limitations=limitations or [],
        )

    def _validate_artifact_scope(self, path: Path) -> None:
        resolved_path = path.resolve()
        allowed_roots = [
            self.raw_dir.resolve(),
            self.processed_dir.resolve(),
            self.free_derivatives_reports_dir.resolve(),
        ]
        if not any(root in (resolved_path, *resolved_path.parents) for root in allowed_roots):
            raise ValueError("free derivatives artifact path must stay under generated roots")

    def _write_csv(self, path: Path, rows: list[dict[str, str]]) -> None:
        fieldnames = sorted({key for row in rows for key in row})
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def _write_parquet(self, path: Path, rows: list[dict[str, Any]]) -> None:
        if rows:
            pl.DataFrame(rows).write_parquet(path)
            return
        pl.DataFrame().write_parquet(path)
