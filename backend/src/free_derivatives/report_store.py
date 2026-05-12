import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

from src.config import get_settings
from src.models.free_derivatives import (
    CftcCotGoldRecord,
    CftcGoldPositioningSummary,
    DeribitOptionSummarySnapshot,
    DeribitOptionWallSnapshot,
    FreeDerivativesArtifact,
    FreeDerivativesArtifactFormat,
    FreeDerivativesArtifactType,
    FreeDerivativesBootstrapRun,
    FreeDerivativesBootstrapRunListResponse,
    FreeDerivativesBootstrapRunSummary,
    FreeDerivativesSource,
    FreeDerivativesSourceStatus,
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

    def write_deribit_raw_instruments(
        self,
        run_id: str,
        rows: list[dict[str, Any]],
    ) -> FreeDerivativesArtifact:
        self.raw_source_root(FreeDerivativesSource.DERIBIT_PUBLIC_OPTIONS).mkdir(
            parents=True,
            exist_ok=True,
        )
        safe_run_id = validate_filesystem_safe_id(run_id, label="run_id")
        path = self.raw_source_root(FreeDerivativesSource.DERIBIT_PUBLIC_OPTIONS) / (
            f"{safe_run_id}_instruments.json"
        )
        self._write_json(path, rows)
        return self.artifact(
            artifact_type=FreeDerivativesArtifactType.RAW_DERIBIT_INSTRUMENTS,
            source=FreeDerivativesSource.DERIBIT_PUBLIC_OPTIONS,
            path=path,
            artifact_format=FreeDerivativesArtifactFormat.JSON,
            rows=len(rows),
        )

    def write_deribit_raw_summary(
        self,
        run_id: str,
        rows: list[dict[str, Any]],
    ) -> FreeDerivativesArtifact:
        self.raw_source_root(FreeDerivativesSource.DERIBIT_PUBLIC_OPTIONS).mkdir(
            parents=True,
            exist_ok=True,
        )
        safe_run_id = validate_filesystem_safe_id(run_id, label="run_id")
        path = self.raw_source_root(FreeDerivativesSource.DERIBIT_PUBLIC_OPTIONS) / (
            f"{safe_run_id}_book_summary.json"
        )
        self._write_json(path, rows)
        return self.artifact(
            artifact_type=FreeDerivativesArtifactType.RAW_DERIBIT_SUMMARY,
            source=FreeDerivativesSource.DERIBIT_PUBLIC_OPTIONS,
            path=path,
            artifact_format=FreeDerivativesArtifactFormat.JSON,
            rows=len(rows),
        )

    def write_deribit_options(
        self,
        run_id: str,
        snapshots: list[DeribitOptionSummarySnapshot],
    ) -> FreeDerivativesArtifact:
        self.processed_source_root(FreeDerivativesSource.DERIBIT_PUBLIC_OPTIONS).mkdir(
            parents=True,
            exist_ok=True,
        )
        safe_run_id = validate_filesystem_safe_id(run_id, label="run_id")
        path = self.processed_source_root(FreeDerivativesSource.DERIBIT_PUBLIC_OPTIONS) / (
            f"{safe_run_id}_options.parquet"
        )
        self._write_parquet(
            path,
            [snapshot.model_dump(mode="json") for snapshot in snapshots],
        )
        return self.artifact(
            artifact_type=FreeDerivativesArtifactType.PROCESSED_DERIBIT_OPTIONS,
            source=FreeDerivativesSource.DERIBIT_PUBLIC_OPTIONS,
            path=path,
            artifact_format=FreeDerivativesArtifactFormat.PARQUET,
            rows=len(snapshots),
        )

    def write_deribit_walls(
        self,
        run_id: str,
        walls: list[DeribitOptionWallSnapshot],
    ) -> FreeDerivativesArtifact:
        self.processed_source_root(FreeDerivativesSource.DERIBIT_PUBLIC_OPTIONS).mkdir(
            parents=True,
            exist_ok=True,
        )
        safe_run_id = validate_filesystem_safe_id(run_id, label="run_id")
        path = self.processed_source_root(FreeDerivativesSource.DERIBIT_PUBLIC_OPTIONS) / (
            f"{safe_run_id}_option_walls.parquet"
        )
        self._write_parquet(path, [wall.model_dump(mode="json") for wall in walls])
        return self.artifact(
            artifact_type=FreeDerivativesArtifactType.PROCESSED_DERIBIT_WALLS,
            source=FreeDerivativesSource.DERIBIT_PUBLIC_OPTIONS,
            path=path,
            artifact_format=FreeDerivativesArtifactFormat.PARQUET,
            rows=len(walls),
        )

    def persist_run(self, run: FreeDerivativesBootstrapRun) -> FreeDerivativesBootstrapRun:
        """Persist a complete bootstrap run and return it with report artifacts attached."""

        self.ensure_run_dir(run.run_id)
        metadata_path = self.artifact_path(run.run_id, "metadata.json")
        json_path = self.artifact_path(run.run_id, "report.json")
        markdown_path = self.artifact_path(run.run_id, "report.md")
        report_source = (
            run.source_results[0].source
            if run.source_results
            else FreeDerivativesSource.CFTC_COT
        )

        report_artifacts = [
            self.artifact(
                artifact_type=FreeDerivativesArtifactType.RUN_METADATA,
                source=report_source,
                path=metadata_path,
                artifact_format=FreeDerivativesArtifactFormat.JSON,
            ),
            self.artifact(
                artifact_type=FreeDerivativesArtifactType.RUN_JSON,
                source=report_source,
                path=json_path,
                artifact_format=FreeDerivativesArtifactFormat.JSON,
            ),
            self.artifact(
                artifact_type=FreeDerivativesArtifactType.RUN_MARKDOWN,
                source=report_source,
                path=markdown_path,
                artifact_format=FreeDerivativesArtifactFormat.MARKDOWN,
            ),
        ]
        persisted_run = run.model_copy(
            update={
                "artifacts": _dedupe_artifacts([*run.artifacts, *report_artifacts]),
            }
        )

        self._write_json_document(metadata_path, self._run_metadata(persisted_run))
        self._write_json_document(json_path, persisted_run.model_dump(mode="json"))
        markdown_path.write_text(self._run_markdown(persisted_run), encoding="utf-8")
        return persisted_run

    def read_run(self, run_id: str) -> FreeDerivativesBootstrapRun:
        path = self.artifact_path(run_id, "report.json")
        if not path.exists():
            raise FileNotFoundError(f"Free derivatives run '{run_id}' was not found")
        payload = json.loads(path.read_text(encoding="utf-8"))
        return FreeDerivativesBootstrapRun.model_validate(payload)

    def list_run_summaries(self) -> list[FreeDerivativesBootstrapRunSummary]:
        root = self.report_root()
        if not root.exists():
            return []

        summaries: list[FreeDerivativesBootstrapRunSummary] = []
        for report_path in root.glob("*/report.json"):
            try:
                run = FreeDerivativesBootstrapRun.model_validate(
                    json.loads(report_path.read_text(encoding="utf-8"))
                )
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            summaries.append(self.summarize_run(run))
        return sorted(summaries, key=lambda item: item.created_at, reverse=True)

    def list_runs(self) -> FreeDerivativesBootstrapRunListResponse:
        return FreeDerivativesBootstrapRunListResponse(runs=self.list_run_summaries())

    def summarize_run(
        self,
        run: FreeDerivativesBootstrapRun,
    ) -> FreeDerivativesBootstrapRunSummary:
        return FreeDerivativesBootstrapRunSummary(
            run_id=run.run_id,
            status=run.status,
            created_at=run.created_at,
            completed_at=run.completed_at,
            completed_source_count=sum(
                result.status == FreeDerivativesSourceStatus.COMPLETED
                for result in run.source_results
            ),
            partial_source_count=sum(
                result.status == FreeDerivativesSourceStatus.PARTIAL
                for result in run.source_results
            ),
            failed_source_count=sum(
                result.status == FreeDerivativesSourceStatus.FAILED
                for result in run.source_results
            ),
            artifact_count=len(run.artifacts),
            warning_count=len(run.warnings)
            + sum(len(result.warnings) for result in run.source_results),
            limitation_count=len(run.limitations),
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

    def _write_json(self, path: Path, rows: list[dict[str, Any]]) -> None:
        with path.open("w", encoding="utf-8") as handle:
            json.dump(rows, handle, indent=2, sort_keys=True, default=str)

    def _write_json_document(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, default=str)

    def _run_metadata(self, run: FreeDerivativesBootstrapRun) -> dict[str, Any]:
        return {
            "run_id": run.run_id,
            "status": run.status.value,
            "created_at": run.created_at.isoformat(),
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "source_count": len(run.source_results),
            "artifact_count": len(run.artifacts),
            "warning_count": len(run.warnings)
            + sum(len(result.warnings) for result in run.source_results),
            "limitation_count": len(run.limitations),
            "sources": [
                {
                    "source": result.source.value,
                    "status": result.status.value,
                    "row_count": result.row_count,
                    "instrument_count": result.instrument_count,
                    "artifact_count": len(result.artifacts),
                }
                for result in run.source_results
            ],
            "research_only_warnings": run.research_only_warnings,
        }

    def _run_markdown(self, run: FreeDerivativesBootstrapRun) -> str:
        lines = [
            f"# Free Derivatives Bootstrap Run {run.run_id}",
            "",
            "Research-only public/local data expansion report. It is not order routing, "
            "account access, or a paid vendor workflow.",
            "",
            "## Summary",
            "",
            f"- Status: {run.status.value}",
            f"- Created at: {run.created_at.isoformat()}",
            f"- Completed at: {run.completed_at.isoformat() if run.completed_at else 'n/a'}",
            f"- Sources: {len(run.source_results)}",
            f"- Artifacts: {len(run.artifacts)}",
            "",
            "## Source Results",
            "",
            "| Source | Status | Rows | Instruments | Coverage | Snapshot |",
            "| --- | --- | ---: | ---: | --- | --- |",
        ]
        for result in run.source_results:
            coverage_start = (
                result.coverage_start.isoformat() if result.coverage_start else "n/a"
            )
            coverage_end = result.coverage_end.isoformat() if result.coverage_end else "n/a"
            snapshot = (
                result.snapshot_timestamp.isoformat()
                if result.snapshot_timestamp
                else "n/a"
            )
            lines.append(
                "| "
                f"{result.source.value} | {result.status.value} | {result.row_count} | "
                f"{result.instrument_count} | {coverage_start} to {coverage_end} | "
                f"{snapshot} |"
            )
        lines.extend(["", "## Artifacts", ""])
        if run.artifacts:
            for artifact in run.artifacts:
                rows = artifact.rows if artifact.rows is not None else "n/a"
                lines.append(
                    f"- {artifact.artifact_type.value}: {artifact.path} "
                    f"({artifact.format.value}, rows={rows})"
                )
        else:
            lines.append("- No artifacts were written.")

        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {limitation}" for limitation in run.limitations)
        lines.extend(["", "## Missing Data Actions", ""])
        if run.missing_data_actions:
            lines.extend(f"- {action}" for action in run.missing_data_actions)
        else:
            lines.append("- No missing-data actions reported.")
        lines.extend(["", "## Research-Only Warnings", ""])
        lines.extend(f"- {warning}" for warning in run.research_only_warnings)
        lines.append("")
        return "\n".join(lines)


def _dedupe_artifacts(
    artifacts: list[FreeDerivativesArtifact],
) -> list[FreeDerivativesArtifact]:
    deduped: list[FreeDerivativesArtifact] = []
    seen: set[tuple[str, str]] = set()
    for artifact in artifacts:
        key = (artifact.artifact_type.value, artifact.path)
        if key not in seen:
            deduped.append(artifact)
            seen.add(key)
    return deduped
