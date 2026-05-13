"""Path-safe persistence for local-only QuikStrike extraction reports."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.config import get_settings
from src.models.quikstrike import (
    QuikStrikeArtifact,
    QuikStrikeArtifactFormat,
    QuikStrikeArtifactType,
    QuikStrikeConversionResult,
    QuikStrikeExtractionReport,
    QuikStrikeExtractionResult,
    QuikStrikeNormalizedRow,
    QuikStrikeXauVolOiRow,
    validate_quikstrike_safe_id,
)


class QuikStrikeReportStore:
    """Local report store that never persists browser/session material."""

    def __init__(self, reports_dir: Path | None = None) -> None:
        self.reports_dir = reports_dir or get_settings().data_reports_path
        self.repo_root = Path(__file__).resolve().parents[3]
        self.quikstrike_reports_dir = self.reports_dir / "quikstrike"

    def report_root(self) -> Path:
        return self.quikstrike_reports_dir

    def ensure_report_root(self) -> Path:
        self.quikstrike_reports_dir.mkdir(parents=True, exist_ok=True)
        return self.quikstrike_reports_dir

    def report_dir(self, extraction_id: str) -> Path:
        safe_extraction_id = validate_quikstrike_safe_id(extraction_id)
        return self.quikstrike_reports_dir / safe_extraction_id

    def ensure_report_dir(self, extraction_id: str) -> Path:
        path = self.report_dir(extraction_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def artifact_path(self, extraction_id: str, filename: str) -> Path:
        if Path(filename).name != filename:
            raise ValueError("artifact filename must not contain path separators")
        return self.report_dir(extraction_id) / filename

    def persist_report(
        self,
        *,
        extraction_result: QuikStrikeExtractionResult,
        normalized_rows: list[QuikStrikeNormalizedRow],
        conversion_result: QuikStrikeConversionResult | None = None,
        conversion_rows: list[QuikStrikeXauVolOiRow] | None = None,
    ) -> QuikStrikeExtractionReport:
        """Persist metadata, rows, artifact metadata, and report JSON/Markdown."""

        self.ensure_report_root()
        report_dir = self.ensure_report_dir(extraction_result.extraction_id)
        metadata_path = report_dir / "metadata.json"
        normalized_rows_path = report_dir / "normalized_rows.json"
        conversion_rows_path = report_dir / "conversion_rows.json"
        artifact_metadata_path = report_dir / "artifact_metadata.json"
        report_json_path = report_dir / "report.json"
        report_markdown_path = report_dir / "report.md"

        artifacts = [
            self.artifact(
                artifact_type=QuikStrikeArtifactType.RAW_METADATA,
                path=metadata_path,
                artifact_format=QuikStrikeArtifactFormat.JSON,
            ),
            self.artifact(
                artifact_type=QuikStrikeArtifactType.RAW_NORMALIZED_ROWS_JSON,
                path=normalized_rows_path,
                artifact_format=QuikStrikeArtifactFormat.JSON,
                rows=len(normalized_rows),
            ),
            self.artifact(
                artifact_type=QuikStrikeArtifactType.RAW_METADATA,
                path=artifact_metadata_path,
                artifact_format=QuikStrikeArtifactFormat.JSON,
            ),
            self.artifact(
                artifact_type=QuikStrikeArtifactType.REPORT_JSON,
                path=report_json_path,
                artifact_format=QuikStrikeArtifactFormat.JSON,
            ),
            self.artifact(
                artifact_type=QuikStrikeArtifactType.REPORT_MARKDOWN,
                path=report_markdown_path,
                artifact_format=QuikStrikeArtifactFormat.MARKDOWN,
            ),
        ]
        if conversion_rows is not None:
            artifacts.append(
                self.artifact(
                    artifact_type=QuikStrikeArtifactType.CONVERSION_METADATA,
                    path=conversion_rows_path,
                    artifact_format=QuikStrikeArtifactFormat.JSON,
                    rows=len(conversion_rows),
                )
            )
        report = QuikStrikeExtractionReport(
            extraction_id=extraction_result.extraction_id,
            status=extraction_result.status,
            created_at=extraction_result.created_at,
            completed_at=extraction_result.completed_at,
            request_summary=_request_summary(extraction_result),
            view_summaries=_view_summaries(extraction_result, normalized_rows),
            row_count=len(normalized_rows),
            strike_mapping=extraction_result.strike_mapping,
            conversion_result=conversion_result,
            artifacts=_dedupe_artifacts(artifacts),
            warnings=extraction_result.warnings,
            limitations=extraction_result.limitations,
            research_only_warnings=extraction_result.research_only_warnings,
        )

        self._write_json(metadata_path, _metadata_payload(report))
        self._write_json(
            normalized_rows_path,
            [row.model_dump(mode="json") for row in normalized_rows],
        )
        if conversion_rows is not None:
            self._write_json(
                conversion_rows_path,
                [row.model_dump(mode="json") for row in conversion_rows],
            )
        self._write_json(
            artifact_metadata_path,
            [artifact.model_dump(mode="json") for artifact in report.artifacts],
        )
        self._write_json(report_json_path, report.model_dump(mode="json"))
        report_markdown_path.write_text(_report_markdown(report), encoding="utf-8")
        return report

    def read_report(self, extraction_id: str) -> QuikStrikeExtractionReport:
        path = self.report_dir(extraction_id) / "report.json"
        if not path.exists():
            raise FileNotFoundError(extraction_id)
        return QuikStrikeExtractionReport.model_validate_json(path.read_text(encoding="utf-8"))

    def read_normalized_rows(self, extraction_id: str) -> list[QuikStrikeNormalizedRow]:
        path = self.report_dir(extraction_id) / "normalized_rows.json"
        if not path.exists():
            raise FileNotFoundError(extraction_id)
        payload = json.loads(path.read_text(encoding="utf-8"))
        return [QuikStrikeNormalizedRow.model_validate(row) for row in payload]

    def read_conversion_rows(self, extraction_id: str) -> list[QuikStrikeXauVolOiRow]:
        path = self.report_dir(extraction_id) / "conversion_rows.json"
        if not path.exists():
            raise FileNotFoundError(extraction_id)
        payload = json.loads(path.read_text(encoding="utf-8"))
        return [QuikStrikeXauVolOiRow.model_validate(row) for row in payload]

    def artifact(
        self,
        *,
        artifact_type: QuikStrikeArtifactType,
        path: Path,
        artifact_format: QuikStrikeArtifactFormat,
        rows: int | None = None,
    ) -> QuikStrikeArtifact:
        self._validate_report_scope(path)
        return QuikStrikeArtifact(
            artifact_type=artifact_type,
            path=self._project_relative_path(path),
            format=artifact_format,
            rows=rows,
            created_at=datetime.now(UTC),
        )

    def _validate_report_scope(self, path: Path) -> None:
        resolved_root = self.quikstrike_reports_dir.resolve()
        resolved_path = path.resolve()
        if resolved_root not in (resolved_path, *resolved_path.parents):
            raise ValueError("QuikStrike report artifact path must stay under report root")

    def _project_relative_path(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.repo_root)).replace("\\", "/")
        except ValueError:
            pass
        data_root = self.reports_dir.parent
        try:
            return str(path.relative_to(data_root.parent)).replace("\\", "/")
        except ValueError:
            return str(path).replace("\\", "/")

    def _write_json(self, path: Path, payload: Any) -> None:
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _request_summary(result: QuikStrikeExtractionResult) -> dict[str, Any]:
    return {
        "requested_views": [view.value for view in result.requested_views],
        "completed_views": [view.value for view in result.completed_views],
        "partial_views": [view.value for view in result.partial_views],
        "missing_views": [view.value for view in result.missing_views],
        "conversion_eligible": result.conversion_eligible,
    }


def _view_summaries(
    result: QuikStrikeExtractionResult,
    rows: list[QuikStrikeNormalizedRow],
) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for view in result.requested_views:
        view_rows = [row for row in rows if row.view_type == view]
        summaries.append(
            {
                "view_type": view.value,
                "row_count": len(view_rows),
                "put_row_count": sum(
                    row.option_type.value == "put" for row in view_rows
                ),
                "call_row_count": sum(
                    row.option_type.value == "call" for row in view_rows
                ),
            }
        )
    return summaries


def _metadata_payload(report: QuikStrikeExtractionReport) -> dict[str, Any]:
    return {
        "extraction_id": report.extraction_id,
        "status": report.status.value,
        "created_at": report.created_at.isoformat(),
        "completed_at": report.completed_at.isoformat() if report.completed_at else None,
        "row_count": report.row_count,
        "strike_mapping": report.strike_mapping.model_dump(mode="json"),
        "artifact_count": len(report.artifacts),
        "warnings": report.warnings,
        "limitations": report.limitations,
        "research_only_warnings": report.research_only_warnings,
    }


def _report_markdown(report: QuikStrikeExtractionReport) -> str:
    lines = [
        f"# QuikStrike Extraction Report {report.extraction_id}",
        "",
        "Local-only research report. No browser cookies, tokens, headers, viewstate, "
        "HAR files, screenshots, or private full URLs are persisted.",
        "",
        f"- Status: `{report.status.value}`",
        f"- Row count: `{report.row_count}`",
        f"- Strike mapping: `{report.strike_mapping.confidence.value}`",
        f"- Conversion eligible: `{report.request_summary.get('conversion_eligible', False)}`",
        "",
        "## View Summary",
    ]
    for summary in report.view_summaries:
        lines.append(
            "- {view_type}: {row_count} rows ({put_row_count} put, "
            "{call_row_count} call)".format(**summary)
        )
    lines.extend(["", "## Limitations"])
    lines.extend(f"- {limitation}" for limitation in report.limitations)
    lines.extend(["", "## Artifacts"])
    lines.extend(f"- `{artifact.path}`" for artifact in report.artifacts)
    return "\n".join(lines) + "\n"


def _dedupe_artifacts(artifacts: list[QuikStrikeArtifact]) -> list[QuikStrikeArtifact]:
    deduped: list[QuikStrikeArtifact] = []
    seen: set[tuple[str, str]] = set()
    for artifact in artifacts:
        key = (artifact.artifact_type.value, artifact.path)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(artifact)
    return deduped
