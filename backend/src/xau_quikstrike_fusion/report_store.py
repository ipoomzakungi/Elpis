from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.config import get_settings
from src.models.xau_quikstrike_fusion import (
    XauFusionArtifact,
    XauFusionArtifactFormat,
    XauFusionArtifactType,
    XauFusionBaseModel,
    XauQuikStrikeFusionReport,
    validate_xau_fusion_safe_id,
)


class XauQuikStrikeFusionReportStore:
    """Path-safe helper for local-only XAU QuikStrike fusion report artifacts."""

    REPORT_ROOT_NAME = "xau_quikstrike_fusion"

    def __init__(self, reports_dir: Path | None = None) -> None:
        self.settings = get_settings()
        self.reports_dir = reports_dir or self.settings.data_reports_path
        self.repo_root = Path(__file__).resolve().parents[3]
        self._report_root = (self.reports_dir / self.REPORT_ROOT_NAME).resolve()

    def report_root(self) -> Path:
        return self._report_root

    def ensure_report_root(self) -> Path:
        self._report_root.mkdir(parents=True, exist_ok=True)
        return self._report_root

    def report_dir(self, report_id: str) -> Path:
        safe_report_id = validate_xau_fusion_safe_id(report_id, "report_id")
        report_dir = (self._report_root / safe_report_id).resolve()
        self._validate_report_scope(report_dir)
        return report_dir

    def ensure_report_dir(self, report_id: str) -> Path:
        report_dir = self.report_dir(report_id)
        report_dir.mkdir(parents=True, exist_ok=True)
        return report_dir

    def artifact_path(self, report_id: str, filename: str) -> Path:
        if not filename or Path(filename).name != filename:
            raise ValueError("artifact filename must be a plain filename")
        artifact_path = (self.report_dir(report_id) / filename).resolve()
        self._validate_report_scope(artifact_path)
        return artifact_path

    def artifact(
        self,
        *,
        artifact_type: XauFusionArtifactType,
        path: Path,
        artifact_format: XauFusionArtifactFormat,
        rows: int | None = None,
    ) -> XauFusionArtifact:
        resolved = path.resolve()
        self._validate_report_scope(resolved)
        return XauFusionArtifact(
            artifact_type=artifact_type,
            path=self._project_relative_path(resolved),
            format=artifact_format,
            rows=rows,
        )

    def artifact_for_filename(
        self,
        report_id: str,
        filename: str,
        *,
        artifact_type: XauFusionArtifactType,
        artifact_format: XauFusionArtifactFormat,
        rows: int | None = None,
    ) -> XauFusionArtifact:
        return self.artifact(
            artifact_type=artifact_type,
            path=self.artifact_path(report_id, filename),
            artifact_format=artifact_format,
            rows=rows,
        )

    def serialize_json(self, payload: Any) -> str:
        return json.dumps(_jsonable(payload), indent=2, sort_keys=True)

    def write_json_artifact(
        self,
        report_id: str,
        filename: str,
        payload: Any,
        *,
        artifact_type: XauFusionArtifactType,
        rows: int | None = None,
    ) -> XauFusionArtifact:
        path = self.artifact_path(report_id, filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.serialize_json(payload), encoding="utf-8")
        return self.artifact(
            artifact_type=artifact_type,
            path=path,
            artifact_format=XauFusionArtifactFormat.JSON,
            rows=rows,
        )

    def persist_report(
        self,
        report: XauQuikStrikeFusionReport,
    ) -> XauQuikStrikeFusionReport:
        """Persist MVP fusion metadata, rows, JSON, and Markdown artifacts."""

        report_dir = self.ensure_report_dir(report.report_id)
        metadata_path = report_dir / "metadata.json"
        fused_rows_path = report_dir / "fused_rows.json"
        report_json_path = report_dir / "report.json"
        report_markdown_path = report_dir / "report.md"

        artifacts = [
            self.artifact(
                artifact_type=XauFusionArtifactType.METADATA,
                path=metadata_path,
                artifact_format=XauFusionArtifactFormat.JSON,
                rows=1,
            ),
            self.artifact(
                artifact_type=XauFusionArtifactType.FUSED_ROWS_JSON,
                path=fused_rows_path,
                artifact_format=XauFusionArtifactFormat.JSON,
                rows=len(report.fused_rows),
            ),
            self.artifact(
                artifact_type=XauFusionArtifactType.REPORT_JSON,
                path=report_json_path,
                artifact_format=XauFusionArtifactFormat.JSON,
                rows=1,
            ),
            self.artifact(
                artifact_type=XauFusionArtifactType.REPORT_MARKDOWN,
                path=report_markdown_path,
                artifact_format=XauFusionArtifactFormat.MARKDOWN,
                rows=1,
            ),
        ]
        saved_report = report.model_copy(update={"artifacts": artifacts})
        metadata_path.write_text(
            self.serialize_json(_metadata_payload(saved_report)) + "\n",
            encoding="utf-8",
        )
        fused_rows_path.write_text(
            self.serialize_json(saved_report.fused_rows) + "\n",
            encoding="utf-8",
        )
        report_json_path.write_text(
            self.serialize_json(saved_report) + "\n",
            encoding="utf-8",
        )
        report_markdown_path.write_text(_report_markdown(saved_report), encoding="utf-8")
        return saved_report

    def _validate_report_scope(self, path: Path) -> None:
        try:
            path.resolve().relative_to(self._report_root)
        except ValueError as exc:
            raise ValueError("path must remain under xau_quikstrike_fusion report root") from exc

    def _project_relative_path(self, path: Path) -> str:
        resolved = path.resolve()
        for base in (self.repo_root, self.reports_dir.resolve().parent.parent):
            try:
                return resolved.relative_to(base).as_posix()
            except ValueError:
                continue
        return resolved.as_posix()


def _jsonable(payload: Any) -> Any:
    if isinstance(payload, XauFusionBaseModel):
        return payload.model_dump(mode="json")
    if isinstance(payload, dict):
        return {key: _jsonable(value) for key, value in payload.items()}
    if isinstance(payload, list):
        return [_jsonable(value) for value in payload]
    if isinstance(payload, tuple):
        return [_jsonable(value) for value in payload]
    return payload


def _metadata_payload(report: XauQuikStrikeFusionReport) -> dict[str, Any]:
    return {
        "report_id": report.report_id,
        "status": report.status.value,
        "created_at": report.created_at.isoformat(),
        "completed_at": report.completed_at.isoformat() if report.completed_at else None,
        "vol2vol_report_id": report.vol2vol_source.report_id,
        "matrix_report_id": report.matrix_source.report_id,
        "fused_row_count": report.fused_row_count,
        "coverage": report.coverage.model_dump(mode="json") if report.coverage else None,
        "warnings": report.warnings,
        "limitations": report.limitations,
        "research_only_warnings": report.research_only_warnings,
    }


def _report_markdown(report: XauQuikStrikeFusionReport) -> str:
    lines = [
        f"# XAU QuikStrike Fusion Report {report.report_id}",
        "",
        "Local-only research report. No cookies, tokens, headers, HAR files, screenshots, "
        "viewstate values, credentials, private URLs, browser sessions, or endpoint replay "
        "payloads are persisted.",
        "",
        f"- Status: `{report.status.value}`",
        f"- Vol2Vol report: `{report.vol2vol_source.report_id}`",
        f"- Matrix report: `{report.matrix_source.report_id}`",
        f"- Fused rows: `{report.fused_row_count}`",
    ]
    if report.coverage is not None:
        lines.extend(
            [
                f"- Matched keys: `{report.coverage.matched_key_count}`",
                f"- Vol2Vol-only keys: `{report.coverage.vol2vol_only_key_count}`",
                f"- Matrix-only keys: `{report.coverage.matrix_only_key_count}`",
                f"- Conflicting keys: `{report.coverage.conflict_key_count}`",
                f"- Blocked keys: `{report.coverage.blocked_key_count}`",
            ]
        )
    lines.extend(["", "## Warnings"])
    lines.extend(f"- {warning}" for warning in report.warnings)
    lines.extend(["", "## Limitations"])
    lines.extend(f"- {limitation}" for limitation in report.limitations)
    lines.extend(["", "## Artifacts"])
    lines.extend(f"- `{artifact.path}`" for artifact in report.artifacts)
    return "\n".join(lines) + "\n"
