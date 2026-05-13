from __future__ import annotations

from pathlib import Path

from src.config import get_settings
from src.models.xau_quikstrike_fusion import (
    XauFusionArtifact,
    XauFusionArtifactFormat,
    XauFusionArtifactType,
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
