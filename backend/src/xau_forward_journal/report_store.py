from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.config import get_settings
from src.models.xau_forward_journal import (
    XauForwardArtifactFormat,
    XauForwardArtifactType,
    XauForwardJournalArtifact,
    XauForwardJournalBaseModel,
    validate_xau_forward_journal_safe_id,
)


class XauForwardJournalReportStore:
    """Path-safe helper for local-only XAU forward journal artifacts."""

    REPORT_ROOT_NAME = "xau_forward_journal"

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

    def report_dir(self, journal_id: str) -> Path:
        safe_journal_id = validate_xau_forward_journal_safe_id(journal_id, "journal_id")
        report_dir = (self._report_root / safe_journal_id).resolve()
        self._validate_report_scope(report_dir)
        return report_dir

    def ensure_report_dir(self, journal_id: str) -> Path:
        report_dir = self.report_dir(journal_id)
        report_dir.mkdir(parents=True, exist_ok=True)
        return report_dir

    def artifact_path(self, journal_id: str, filename: str) -> Path:
        if not filename or Path(filename).name != filename:
            raise ValueError("artifact filename must be a plain filename")
        artifact_path = (self.report_dir(journal_id) / filename).resolve()
        self._validate_report_scope(artifact_path)
        return artifact_path

    def artifact(
        self,
        *,
        artifact_type: XauForwardArtifactType,
        path: Path,
        artifact_format: XauForwardArtifactFormat,
        rows: int | None = None,
    ) -> XauForwardJournalArtifact:
        resolved = path.resolve()
        self._validate_report_scope(resolved)
        return XauForwardJournalArtifact(
            artifact_type=artifact_type,
            path=self._project_relative_path(resolved),
            format=artifact_format,
            rows=rows,
        )

    def artifact_for_filename(
        self,
        journal_id: str,
        filename: str,
        *,
        artifact_type: XauForwardArtifactType,
        artifact_format: XauForwardArtifactFormat,
        rows: int | None = None,
    ) -> XauForwardJournalArtifact:
        return self.artifact(
            artifact_type=artifact_type,
            path=self.artifact_path(journal_id, filename),
            artifact_format=artifact_format,
            rows=rows,
        )

    def serialize_json(self, payload: Any) -> str:
        return json.dumps(_jsonable(payload), indent=2, sort_keys=True)

    def write_json_artifact(
        self,
        journal_id: str,
        filename: str,
        payload: Any,
        *,
        artifact_type: XauForwardArtifactType,
        rows: int | None = None,
    ) -> XauForwardJournalArtifact:
        path = self.artifact_path(journal_id, filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.serialize_json(payload) + "\n", encoding="utf-8")
        return self.artifact(
            artifact_type=artifact_type,
            path=path,
            artifact_format=XauForwardArtifactFormat.JSON,
            rows=rows,
        )

    def _validate_report_scope(self, path: Path) -> None:
        try:
            path.resolve().relative_to(self._report_root)
        except ValueError as exc:
            raise ValueError("path must remain under xau_forward_journal report root") from exc

    def _project_relative_path(self, path: Path) -> str:
        resolved = path.resolve()
        for base in (self.repo_root, self.reports_dir.resolve().parent.parent):
            try:
                return resolved.relative_to(base).as_posix()
            except ValueError:
                continue
        return resolved.as_posix()


def _jsonable(payload: Any) -> Any:
    if isinstance(payload, XauForwardJournalBaseModel):
        return payload.model_dump(mode="json")
    if isinstance(payload, dict):
        return {key: _jsonable(value) for key, value in payload.items()}
    if isinstance(payload, list):
        return [_jsonable(value) for value in payload]
    if isinstance(payload, tuple):
        return [_jsonable(value) for value in payload]
    return payload
